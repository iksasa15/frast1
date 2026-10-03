"""Deterministic test fixture. This module is never packaged into the backend image."""
import random
from datetime import datetime, timezone

from app.schemas.event import Event

# Aligned with configs/topology.json campus spine (edge uplink keeps id link-r1-sw1).
BASELINE = [
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
    "uplink-congestion": [(0, "link-r1-sw1", "link_utilization", 97, 4), (1, "link-r1-sw1", "if_out_discards_rate", 180, 4), (2, "link-r1-sw1", "link_latency_ms", 86, 6), (3, "link-r1-sw1", "link_packet_loss", 2.4, 6), (6, "svc-web", "http_latency_ms", 1450, 6), (8, "svc-dns", "dns_success_rate", 72, 5), (8, "svc-dns", "dns_latency_ms", 620, 5)],
    "dns-failure": [(0, "svc-dns", "dns_success_rate", 0, 2), (0, "svc-dns", "dns_latency_ms", 1000, 2), (2, "svc-web", "http_ok", 0, 1)],
    "server-spike": [(0, "app01", "cpu_percent", 98, 5), (1, "app01", "mem_percent", 78, 8), (4, "svc-web", "http_latency_ms", 1100, 6), (6, "svc-dns", "dns_latency_ms", 160, 6)],
}


class Simulator:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.current = {(entity, metric): baseline for entity, _, metric, _, baseline, _ in BASELINE}
        self.active = None
        self.elapsed = 0.0
        self.recovering = False
        self.paused = False

    def inject(self, scenario):
        assert scenario in SCENARIOS
        self.active, self.elapsed, self.recovering = scenario, 0.0, False

    def remediate(self):
        self.recovering = True

    def reset(self):
        self.active, self.recovering = None, False
        self.current = {(entity, metric): baseline for entity, _, metric, _, baseline, _ in BASELINE}

    def _target(self, entity, metric, baseline):
        if not self.active or self.recovering:
            return baseline, 8.0
        for offset, target_entity, target_metric, target, ramp in SCENARIOS[self.active]:
            if target_entity == entity and target_metric == metric and self.elapsed >= offset:
                return target, ramp
        return baseline, 4.0

    async def step(self, tick=1.0):
        if self.paused:
            return
        self.elapsed += tick
        now = datetime.now(timezone.utc)
        for entity, source_type, metric, unit, baseline, noise in BASELINE:
            target, ramp = self._target(entity, metric, baseline)
            current = self.current[(entity, metric)]
            current += (target - current) * min(1.0, tick / ramp)
            self.current[(entity, metric)] = current
            value = max(0.0, current + random.gauss(0, noise))
            if unit == "percent":
                value = min(value, 100.0)
            if unit == "bool":
                value = 1.0 if current >= 0.5 else 0.0
            await self.pipeline.ingest(Event(source_id=entity, source_type=source_type, metric=metric,
                                             value=round(value, 2), unit=unit, timestamp=now,
                                             metadata={"collector": "test-fixture"}))
