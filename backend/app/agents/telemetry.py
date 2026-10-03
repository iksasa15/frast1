from __future__ import annotations

import math
import time
from collections import Counter

from .base import Agent
from .roster import SPECS

# metric -> canonical unit; ranges are enforced only for the percent metrics
METRIC_UNIT = {
    "link_utilization": "percent",
    "link_packet_loss": "percent",
    "dns_success_rate": "percent",
    "cpu_percent": "percent",
    "mem_percent": "percent",
    "link_latency_ms": "ms",
    "dns_latency_ms": "ms",
    "http_latency_ms": "ms",
    "if_out_discards_rate": "pps",
    "http_ok": "bool",
    "syslog_link_down": "bool",
}
UNIT_ALIASES = {
    "percent": {"percent", "%", "pct"},
    "ms": {"ms", "millisecond", "milliseconds"},
    "pps": {"pps", "packets/s", "pkt/s"},
    "bool": {"bool", "boolean", "0/1"},
}
STALE_AFTER_S = 20.0


class TelemetryAgent(Agent):
    spec = SPECS["telemetry"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.last_seen: dict[str, float] = {}
        self.per_source: Counter = Counter()
        self.flag_counts: Counter = Counter()
        self.events = 0
        self._last_sample: dict[tuple[str, str], tuple] = {}

    def observe(self, ev) -> list[str]:
        """Hot path (called for every event): validate and remember freshness. No trace step."""
        flags: list[str] = []
        v = ev.value
        if not math.isfinite(v):
            flags.append("non_finite")
        else:
            unit = METRIC_UNIT.get(ev.metric)
            if unit == "percent" and not (0.0 <= v <= 100.0):
                flags.append("out_of_range")
            if ev.metric.endswith("_ms") and v < 0:
                flags.append("negative_value")
            if unit and (ev.unit or "").lower() not in UNIT_ALIASES[unit]:
                flags.append("unit_mismatch")
        key = (ev.source_id, ev.metric)
        sample = (ev.timestamp, ev.value)
        if self._last_sample.get(key) == sample:
            flags.append("duplicate")
        self._last_sample[key] = sample

        self.events += 1
        self.per_source[ev.source_id] += 1
        self.last_seen[ev.source_id] = time.time()
        for f in flags:
            self.flag_counts[f] += 1
        self.stats.runs += 1
        if flags:
            self.stats.last_status = "flagged"
            self.stats.last_summary = f"{ev.source_id}.{ev.metric}: {', '.join(flags)}"
        return flags

    def freshness(self, now: float | None = None) -> dict[str, float]:
        now = now or time.time()
        return {s: round(now - t, 1) for s, t in self.last_seen.items()}

    def stale_sources(self, stale_after: float = STALE_AFTER_S) -> list[str]:
        return sorted(s for s, age in self.freshness().items() if age > stale_after)

    def quality(self) -> dict:
        flagged = sum(self.flag_counts.values())
        return {
            "eventsSeen": self.events,
            "sources": len(self.last_seen),
            "stale": self.stale_sources(),
            "flags": dict(self.flag_counts),
            "qualityScore": round(1 - flagged / self.events, 4) if self.events else 1.0,
        }

    async def incident_context(self, inc) -> dict:
        """Before RCA: are the sources behind this incident still reporting?"""
        async with self.step("assess_sources", inc.id) as st:
            ages = self.freshness()
            members = sorted(inc.members)
            stale = [m for m in members if ages.get(m, 0.0) > STALE_AFTER_S]
            ctx = {
                "members": members,
                "ageSeconds": {m: ages.get(m) for m in members},
                "stale": stale,
                "qualityScore": self.quality()["qualityScore"],
            }
            st.data = ctx
            st.decision = "degraded" if stale else "trusted"
            st.summary = (
                f"{len(members)} source(s) fresh, data quality {ctx['qualityScore']:.0%}"
                if not stale
                else f"stale sources: {', '.join(stale)} — RCA confidence may be overstated"
            )
        return ctx
