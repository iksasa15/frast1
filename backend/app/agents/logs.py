"""Syslog Normalizer: raw multi-vendor syslog lines -> normalized events -> pipeline.

Only interface up/down events are turned into pipeline events (metric ``syslog_link_down``: 1 = down, 0 = up,
attached to the topology *link* the port belongs to). Everything else is normalized and kept in a bounded ring
buffer so the operator (and the Copilot) can see it, but it cannot open an incident by itself.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from datetime import datetime, timezone

from app.knowledge import get_kb
from app.schemas.event import Event

from .base import Agent
from .roster import SPECS

MAX_LINE = 1000
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Long interface names used in syslog vs. the short names used in the topology file.
_IF_PREFIX = {
    "gigabitethernet": "gi", "gige": "gi", "gig": "gi", "gi": "gi", "ge": "gi",
    "tengigabitethernet": "te", "tengige": "te", "te": "te", "xe": "te",
    "twentyfivegige": "twe", "twe": "twe", "fortygigabitethernet": "fo", "fortygige": "fo", "fo": "fo",
    "hundredgige": "hu", "hu": "hu", "fastethernet": "fa", "fa": "fa",
    "ethernet": "eth", "eth": "eth", "et": "eth", "port-channel": "po", "portchannel": "po", "po": "po",
    "ae": "ae", "vlan": "vlan", "vlanif": "vlan",
}
_IF_SPLIT = re.compile(r"^([A-Za-z\-]+?)\s*(\d[\w/:.\-]*)$")


def canon_interface(name: str | None) -> str | None:
    """Gi0/0, GigabitEthernet0/0 and gigabitethernet 0/0 all map to the same key."""
    if not name:
        return None
    n = name.strip()
    m = _IF_SPLIT.match(n)
    if not m:
        return n.lower()
    prefix, rest = m.group(1).lower(), m.group(2).lower()
    return f"{_IF_PREFIX.get(prefix, prefix)}{rest}"


def clean_line(line: str) -> str:
    return CONTROL.sub(" ", str(line))[:MAX_LINE].strip()


class LogsAgent(Agent):
    spec = SPECS["logs"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.kb = get_kb()
        self.recent: deque[dict] = deque(maxlen=500)
        self.counts: Counter = Counter()
        self._port_map: dict[tuple[str, str], str] | None = None

    # ---- topology port -> link, tolerant to interface naming style
    def _ports(self) -> dict[tuple[str, str], str]:
        if self._port_map is None:
            topo = self.rt.topology
            self._port_map = {}
            if topo is not None:
                for (dev, port), link in topo.port_to_link.items():
                    self._port_map[(dev, canon_interface(port))] = link
        return self._port_map

    def link_for(self, device: str | None, interface: str | None) -> str | None:
        if not device or not interface:
            return None
        return self._ports().get((device, canon_interface(interface)))

    # ---- pure normalization (unit-testable)
    def normalize(self, line: str, device: str | None = None, vendor_hint: str | None = None) -> dict:
        line = clean_line(line)
        hint = vendor_hint
        if hint is None and device:
            ident = self.rt.vendor.node_identity(device) if hasattr(self.rt, "vendor") else None
            hint = (ident or {}).get("vendor")
        parsed = self.kb.parse_syslog(line, hint) if line else None
        base = {"device": device, "line": line[:300]}
        if parsed is None:
            return {**base, "parsed": False, "event": None}
        link = self.link_for(device, parsed.get("interface"))
        return {**base, "parsed": True, "link": link, **parsed}

    async def ingest(self, lines: list[str], device: str | None, pipeline, vendor_hint: str | None = None) -> dict:
        """Normalize a batch; push link-state events into the pipeline. Returns a summary for the API."""
        async with self.step("ingest_syslog") as st:
            results, pushed = [], 0
            for raw in lines:
                r = self.normalize(raw, device, vendor_hint)
                r["ts"] = datetime.now(timezone.utc).isoformat()
                r["pushed"] = False
                if not r["parsed"]:
                    self.counts["unparsed"] += 1
                else:
                    self.counts["parsed"] += 1
                    self.counts[f"vendor:{r['vendor']}"] += 1
                    if r["event"] == "interface_state" and r.get("state") in ("up", "down") and r.get("link") and pipeline is not None:
                        down = r["state"] == "down"
                        ev = Event(
                            source_id=r["link"], source_type="link", metric="syslog_link_down",
                            value=1.0 if down else 0.0, unit="bool", interface=r.get("interface"),
                            severity="critical" if down else "info",
                            metadata={"device": device, "vendor": r["vendor"], "pattern": r["pattern"], "via": "syslog"},
                        )
                        await pipeline.ingest(ev)
                        r["pushed"] = True
                        pushed += 1
                self.recent.append(r)
                results.append({k: v for k, v in r.items() if k != "details"})
            parsed_n = sum(1 for r in results if r["parsed"])
            st.data = {"lines": len(results), "parsed": parsed_n, "pushed": pushed, "device": device}
            st.decision = "events_pushed" if pushed else "normalized_only"
            st.summary = f"{len(results)} line(s): {parsed_n} recognised, {pushed} link-state event(s) sent to the pipeline"
        return {"lines": len(results), "parsed": parsed_n, "unparsed": len(results) - parsed_n, "pushed": pushed, "results": results}

    def stats_view(self) -> dict:
        by_vendor = {k.split(":", 1)[1]: v for k, v in self.counts.items() if k.startswith("vendor:")}
        return {"parsed": self.counts["parsed"], "unparsed": self.counts["unparsed"], "byVendor": by_vendor, "buffered": len(self.recent)}
