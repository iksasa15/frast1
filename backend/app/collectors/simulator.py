"""Simulated telemetry for the lab topology.

Demo spine metrics (BASELINE_CORE + SCENARIOS) stay frozen so RCA demos keep working.
Healthy campus fabric metrics are derived from configs/topology.json so new devices
look alive without stealing the three demo scenarios.
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.schemas.event import Event
from app.services.hub import hub

# Demo spine — IDs must exist in configs/topology.json (edge uplink keeps id link-r1-sw1).
BASELINE_CORE = [
    ("link-r1-sw1", "link", "link_utilization", "percent", 14, 3),
    ("link-r1-sw1", "link", "link_latency_ms", "ms", 2.5, 0.6),
    ("link-r1-sw1", "link", "link_packet_loss", "percent", 0, 0),
    ("link-r1-sw1", "link", "if_out_discards_rate", "pps", 0, 0),
    ("link-sw1-app01", "link", "link_utilization", "percent", 9, 2),
    ("link-sw1-app01", "link", "link_latency_ms", "ms", 0.8, 0.2),
    ("app01", "server", "cpu_percent", "percent", 18, 4),
    ("app01", "server", "mem_percent", "percent", 41, 1),
    ("svc-web", "service", "http_latency_ms", "ms", 42, 8),
    ("svc-web", "service", "http_ok", "bool", 1, 0),
    ("svc-dns", "service", "dns_success_rate", "percent", 100, 0),
    ("svc-dns", "service", "dns_latency_ms", "ms", 4, 1),
]

SCENARIOS = {
    "uplink-congestion": [
        (0, "link-r1-sw1", "link_utilization", 97, 4),
        (1, "link-r1-sw1", "if_out_discards_rate", 180, 4),
        (2, "link-r1-sw1", "link_latency_ms", 86, 6),
        (3, "link-r1-sw1", "link_packet_loss", 2.4, 6),
        (6, "svc-web", "http_latency_ms", 1450, 6),
        (8, "svc-dns", "dns_success_rate", 72, 5),
        (8, "svc-dns", "dns_latency_ms", 620, 5),
    ],
    "dns-failure": [
        (0, "svc-dns", "dns_success_rate", 0, 2),
        (0, "svc-dns", "dns_latency_ms", 1000, 2),
        (2, "svc-web", "http_ok", 0, 1),
    ],
    "server-spike": [
        (0, "app01", "cpu_percent", 98, 5),
        (1, "app01", "mem_percent", 78, 8),
        (4, "svc-web", "http_latency_ms", 1100, 6),
        (6, "svc-dns", "dns_latency_ms", 160, 6),
    ],
}


def _stable(seed: str, lo: int, hi: int) -> int:
    h = sum(ord(c) for c in seed) % (hi - lo + 1)
    return lo + h


def _campus_baseline(topo_path: str | Path | None = None) -> list[tuple]:
    """Healthy metrics for every topology entity not already covered by BASELINE_CORE."""
    path = Path(topo_path or settings.topology_path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    covered = {e for e, _, _, _, _, _ in BASELINE_CORE}
    out: list[tuple] = []

    for link in raw.get("links", []):
        lid = link["id"]
        if lid in covered:
            continue
        util = _stable(lid, 4, 18)
        out.append((lid, "link", "link_utilization", "percent", util, 2))
        out.append((lid, "link", "link_latency_ms", "ms", round(0.4 + util * 0.05, 2), 0.2))

    for node in raw.get("nodes", []):
        nid, ntype = node["id"], node["type"]
        if nid in covered:
            continue
        if ntype in ("server", "collector"):
            out.append((nid, "server", "cpu_percent", "percent", _stable(nid + ":cpu", 8, 28), 3))
            out.append((nid, "server", "mem_percent", "percent", _stable(nid + ":mem", 30, 55), 2))

    for svc in raw.get("services", []):
        sid = svc["id"]
        if sid in covered:
            continue
        port = int(svc.get("port") or 0)
        if port in (53, 389):
            out.append((sid, "service", "dns_success_rate", "percent", 100, 0))
            out.append((sid, "service", "dns_latency_ms", "ms", _stable(sid, 2, 8), 1))
        elif port in (25, 445):
            out.append((sid, "service", "http_ok", "bool", 1, 0))
            out.append((sid, "service", "http_latency_ms", "ms", _stable(sid, 20, 60), 5))
        else:
            out.append((sid, "service", "http_ok", "bool", 1, 0))
            out.append((sid, "service", "http_latency_ms", "ms", _stable(sid, 30, 90), 6))

    return out


BASELINE = BASELINE_CORE + _campus_baseline()


class Simulator:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.current = {(e, m): b for e, _, m, _, b, _ in BASELINE}
        self.active: str | None = None
        self.elapsed = 0.0
        self.recovering = False
        self.paused = False

    def inject(self, scenario: str):
        assert scenario in SCENARIOS
        self.active, self.elapsed, self.recovering = scenario, 0.0, False

    def remediate(self):
        """Engineer approved a fix: snap every metric to its healthy baseline immediately."""
        self.recovering = True
        self.current = {(e, m): float(b) for e, _, m, _, b, _ in BASELINE}

    async def push_baseline(self):
        """Emit clean baseline samples for demo metrics so the topology UI turns green now."""
        now = datetime.now(timezone.utc)
        # Campus fabric was never faulted — only push the demo spine metrics.
        for e, st, m, unit, base, _noise in BASELINE_CORE:
            self.current[(e, m)] = float(base)
            await self.pipeline.ingest(
                Event(
                    source_id=e,
                    source_type=st,
                    metric=m,
                    value=round(float(base), 2),
                    unit=unit,
                    timestamp=now,
                    metadata={"collector": "simulator", "recovery": True},
                )
            )
        dirty, self.pipeline.state.dirty = self.pipeline.state.dirty, set()
        for entity in dirty:
            await hub.broadcast(self.pipeline.state.kind(entity), self.pipeline.state.payload(entity))

    def reset(self):
        self.active, self.recovering = None, False
        self.current = {(e, m): b for e, _, m, _, b, _ in BASELINE}

    def _target(self, e, m, base):
        if not self.active or self.recovering:
            # Stay near baseline after remediation (map already snapped green).
            return base, 1.0
        for off, te, tm, tgt, ramp in SCENARIOS[self.active]:
            if te == e and tm == m and self.elapsed >= off:
                return tgt, ramp
        return base, 4.0

    async def step(self, tick: float = 1.0):
        if self.paused:
            return
        self.elapsed += tick
        now = datetime.now(timezone.utc)
        for e, st, m, unit, base, noise in BASELINE:
            tgt, ramp = self._target(e, m, base)
            cur = self.current[(e, m)]
            cur += (tgt - cur) * min(1.0, tick / ramp)
            self.current[(e, m)] = cur
            val = max(0.0, cur + random.gauss(0, noise))
            if unit == "percent":
                val = min(val, 100.0)
            if unit == "bool":
                val = 1.0 if cur >= 0.5 else 0.0
            await self.pipeline.ingest(
                Event(
                    source_id=e,
                    source_type=st,
                    metric=m,
                    value=round(val, 2),
                    unit=unit,
                    timestamp=now,
                    metadata={"collector": "simulator"},
                )
            )

    async def run(self, tick: float = 1.0):
        while True:
            await asyncio.sleep(tick)
            await self.step(tick)
