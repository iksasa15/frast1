from itertools import count
from collections import deque

from fastapi import HTTPException

from app.schemas.event import Event
from app.services.hub import hub


class Pipeline:
    def __init__(self, topo, state, detector, incidents):
        self.topo = topo
        self.state = state
        self.detector = detector
        self.incidents = incidents
        self.alerts: deque = deque(maxlen=200)
        self._seq = count(1)
        self.recorder = None
        self.agents = None  # AgentRuntime (set by main); None -> plain detector path

    async def ingest(self, ev: Event):
        if (
            ev.source_type in ("router", "switch")
            and ev.interface
            and ev.metric.startswith(("link_", "if_"))
        ):
            link = self.topo.port_to_link.get((ev.source_id, ev.interface))
            if link:
                ev.source_id, ev.source_type = link, "link"
        known = set(self.topo.nodes) | set(self.topo.links) | set(self.topo.services)
        if ev.source_id not in known:
            raise HTTPException(status_code=422, detail=f"unknown sourceId {ev.source_id}")
        if self.agents is not None and "non_finite" in self.agents.telemetry.observe(ev):
            raise HTTPException(status_code=422, detail="non-finite value rejected by telemetry agent")
        ts = ev.timestamp.timestamp()
        self.state.update(ev.source_id, ev.metric, ev.value, ts)
        if self.recorder:
            self.recorder.write(ev)
        detect = self.agents.detection if self.agents is not None else self.detector
        anomaly, raw_level = detect.observe(ev.source_id, ev.metric, ev.value, ts)
        if raw_level:
            alert = {
                "id": f"alr-{next(self._seq):05d}",
                "sourceId": ev.source_id,
                "metric": ev.metric,
                "value": ev.value,
                "severity": "critical" if raw_level >= 1 else "warning",
                "ts": ev.timestamp.isoformat(),
            }
            self.alerts.appendleft(alert)
            await hub.broadcast("alert", alert)
        if anomaly:
            await self.incidents.on_anomaly(anomaly)
