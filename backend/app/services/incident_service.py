import asyncio
from datetime import datetime, timezone
from itertools import count

from app.agents.runtime import AgentRuntime
from app.services.hub import hub


class IncidentState:
    def __init__(self, id_: str, title: str, opened_at: str):
        self.id = id_
        self.title = title
        self.status = "open"
        self.severity = "high"
        self.opened_at = opened_at
        self.resolved_at: str | None = None
        self.members: set[str] = set()
        self.evidence: list[dict] = []
        self.anomalies: list = []
        self.raw_alert_count = 0
        self.last_activity = 0.0
        self.opened_epoch = datetime.now(timezone.utc).timestamp()
        self.timings = {
            "firstAnomalyAt": opened_at,
            "detectedAt": opened_at,
        }
        self.needs_investigation = True
        self.candidates: list = []
        self.affected_services: list[str] = []
        self.cause_path: list[str] = []
        self.impact_path: list[str] = []
        self.root_cause = None
        self.explanation = None
        self.action = None
        self.acknowledged_by: str | None = None
        self.acknowledged_at: str | None = None
        self.verification: dict | None = None
        self.knowledge: dict | None = None
        self.vendor_context: dict | None = None
        self._analyze_task: asyncio.Task | None = None
        self._analyzing = False  # True while analyze() is running (it may wait on LLM/RAG)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "openedAt": self.opened_at,
            "resolvedAt": self.resolved_at,
            "rootCause": self.root_cause,
            "needsInvestigation": self.needs_investigation,
            "candidates": self.candidates,
            "evidence": self.evidence,
            "affectedServices": self.affected_services,
            "causePath": self.cause_path,
            "impactPath": self.impact_path,
            "explanation": self.explanation,
            "action": self.action,
            "rawAlertCount": self.raw_alert_count,
            "timings": self.timings,
            "members": sorted(self.members),
            "acknowledgedBy": self.acknowledged_by,
            "acknowledgedAt": self.acknowledged_at,
            "verification": self.verification,
            "knowledge": self.knowledge,
            "vendorContext": self.vendor_context,
        }


def _title_for(root_id: str, metric: str) -> str:
    if root_id.startswith("link-"):
        return "Uplink congestion on R1 Gi0/0" if "r1-sw1" in root_id else f"Link congestion on {root_id}"
    if root_id == "svc-dns" or metric.startswith("dns_"):
        return "DNS service failure on APP-01"
    if root_id == "app01" or metric in ("cpu_percent", "mem_percent"):
        return "Resource pressure on APP-01"
    return f"Root cause on {root_id}"


def _kind_for(root_id: str) -> str:
    if root_id.startswith("link-"):
        return "link"
    if root_id == "svc-dns" or root_id.startswith("svc-dns"):
        return "svc-dns"
    return "server"


class IncidentService:
    def __init__(
        self, correlator, graph, history, persist=None, topology=None, actions=None, agents=None
    ):
        self.correlator = correlator
        self.graph = graph
        self.history = history
        self.persist = persist
        self.topology = topology
        self.actions = actions
        self.open: dict[str, IncidentState] = {}
        self.history_list: list[IncidentState] = []
        self._seq = count(1)
        self.agents = agents or AgentRuntime(
            graph=graph, history=history, topology=topology, correlator=correlator
        )
        self.agents.bind(incidents=self)

    def _open_list(self) -> list[IncidentState]:
        return [i for i in self.open.values() if i.status != "resolved"]

    async def on_anomaly(self, anomaly):
        ts = anomaly.last_seen
        pick = self.agents.correlation.pick(anomaly.entity_id, ts, self._open_list())
        opened_new = pick is None
        if pick is None:
            iid = f"INC-{next(self._seq):04d}"
            now = datetime.now(timezone.utc).isoformat()
            pick = IncidentState(iid, title="Correlated incident · 1 symptoms", opened_at=now)
            pick.status = "investigating"
            self.open[iid] = pick
            pick.timings["firstAnomalyAt"] = now
            pick.timings["detectedAt"] = now

        pick.members.add(anomaly.entity_id)
        pick.last_activity = ts
        pick.raw_alert_count += 1
        # Keep latest anomaly per entity|metric
        key = (anomaly.entity_id, anomaly.metric)
        pick.anomalies = [a for a in pick.anomalies if (a.entity_id, a.metric) != key]
        pick.anomalies.append(anomaly)
        if pick.status in ("open", "investigating") or not pick.root_cause:
            pick.title = f"Correlated incident · {len(pick.members)} symptoms"
        pick.evidence.append(
            {
                "id": f"ev-{len(pick.evidence)+1}",
                "entityId": anomaly.entity_id,
                "metric": anomaly.metric,
                "value": anomaly.value,
                "baseline": anomaly.baseline,
                "unit": "",
                "ts": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "text": f"{anomaly.metric}={anomaly.value}",
            }
        )
        pick.affected_services = self.agents.topology_agent.services_for(pick.members)
        if pick.status == "open":
            pick.status = "investigating"
        if opened_new:
            await self.agents.correlation.opened(pick, anomaly.entity_id, anomaly.metric)

        if self.persist:
            self.persist(pick)

        await hub.broadcast("incident", pick.to_dict())
        self._schedule_analyze(pick)

    def _schedule_analyze(self, inc: IncidentState):
        if inc.status in ("recommendation_ready", "awaiting_approval", "approved", "resolved"):
            # Still allow re-analyze if not yet analyzed
            if inc.root_cause and inc.status != "investigating":
                return
        if inc._analyzing:
            # Never cancel an analysis that is already running: with a slow LLM/RAG each new symptom
            # used to cancel it, so the root cause only appeared after the symptoms stopped arriving.
            return

        async def _debounced():
            # Max 10s from open, or 3s quiet
            opened = inc.opened_epoch
            while True:
                await asyncio.sleep(0.5)
                now = datetime.now(timezone.utc).timestamp()
                quiet = now - inc.last_activity >= 3.0
                deadline = now - opened >= 10.0
                if quiet or deadline:
                    break
            inc._analyzing = True
            try:
                await self.analyze(inc.id)
            finally:
                inc._analyzing = False

        if inc._analyze_task and not inc._analyze_task.done():
            inc._analyze_task.cancel()
        inc._analyze_task = asyncio.create_task(_debounced())

    async def analyze(self, incident_id: str) -> dict | None:
        inc = self.open.get(incident_id)
        if not inc:
            for h in self.history_list:
                if h.id == incident_id:
                    inc = h
                    break
        if not inc or not inc.anomalies:
            return None

        affected = [s for s in inc.affected_services if s in self.graph.services]
        if not affected:
            affected = [s for s in inc.members if s in self.graph.services]

        # The orchestrator runs telemetry -> correlation -> topology -> RCA -> detection ->
        # explanation -> knowledge, with per-agent timeouts and deterministic fallbacks.
        result = await self.agents.orchestrator.investigate(inc, affected, self._facts)
        if result is None:
            return inc.to_dict()

        root = result.root
        inc.candidates = result.candidates
        inc.needs_investigation = result.needs_investigation
        inc.root_cause = {
            "entityId": root.entity_id,
            "label": root.label,
            "confidence": result.confidence,
        }
        inc.cause_path = result.cause_path
        inc.impact_path = result.impact_path
        top_metric = max(
            (a for a in inc.anomalies if a.entity_id == root.entity_id),
            key=lambda a: a.severity,
        ).metric
        inc.title = _title_for(root.entity_id, top_metric)
        if inc.status in ("open", "investigating"):
            inc.status = "recommendation_ready"

        if result.mv_evidence:  # Isolation Forest: supporting evidence only, never decides the root
            inc.evidence.append(result.mv_evidence)
        inc.explanation = result.explanation
        if result.knowledge:
            inc.knowledge = result.knowledge
        inc.vendor_context = result.vendor  # set before the plan is built: the planner adds vendor commands from it

        # Attach pending action recommendation (planner + guardrail agents)
        if self.actions and not (inc.action and inc.action.get("approvalStatus") == "pending"):
            await self.actions.recommend(inc)
        if inc.action and inc.action.get("approvalStatus") == "pending":
            await self.agents.orchestrator.handoff(inc)

        if self.persist:
            self.persist(inc)
        try:
            self.agents.knowledge.index_incident(inc.to_dict())
        except Exception:
            pass
        await hub.broadcast("incident", inc.to_dict())
        return inc.to_dict()

    def _facts(self, inc: IncidentState, root_id: str, conf: float) -> dict:
        by_m = {a.metric: a for a in inc.anomalies if a.entity_id == root_id}
        util = by_m.get("link_utilization")
        lat = by_m.get("link_latency_ms")
        dns = by_m.get("dns_success_rate")
        dns_lat = by_m.get("dns_latency_ms")
        cpu = by_m.get("cpu_percent")
        http = next((a for a in inc.anomalies if a.metric == "http_latency_ms"), None)
        speed = 10
        if self.topology and root_id in self.topology.links:
            try:
                speed = self.topology.speed_of(root_id)
            except Exception:
                speed = 10
        t0 = min(a.first_seen for a in inc.anomalies)
        lead = 0
        svc_first = [a.first_seen for a in inc.anomalies if a.entity_id.startswith("svc-")]
        root_first = min(a.first_seen for a in inc.anomalies if a.entity_id == root_id)
        if svc_first:
            lead = max(0, int(min(svc_first) - root_first))
        return {
            "label": self.graph.label(root_id),
            "conf": int(round(conf * 100)),
            "util": int(round(util.value)) if util else 0,
            "speed": int(speed),
            "lat0": int(round(lat.baseline)) if lat else 0,
            "lat": int(round(lat.value)) if lat else 0,
            "lead": lead or int(t0 % 10),
            "n": len(inc.affected_services) or 1,
            "dns": int(round(dns.value)) if dns else 0,
            "dnsLat": int(round(dns_lat.value)) if dns_lat else 0,
            "cpu": int(round(cpu.value)) if cpu else 0,
            "http": int(round(http.value)) if http else 0,
        }

    async def archive_all(self):
        for inc in list(self.open.values()):
            if inc.status == "resolved":
                continue
            if inc._analyze_task and not inc._analyze_task.done():
                inc._analyze_task.cancel()
            inc.status = "resolved"
            inc.resolved_at = datetime.now(timezone.utc).isoformat()
            self.history_list.append(inc)
            if self.persist:
                self.persist(inc)
            await hub.broadcast("incident", inc.to_dict())
        self.open.clear()

    def resume_sequence(self, existing_ids: list[str]) -> None:
        """Continue numbering after the highest persisted INC-#### id."""
        nums = [
            int(i.split("-", 1)[1]) for i in existing_ids if i.startswith("INC-") and i.split("-", 1)[1].isdigit()
        ]
        self._seq = count(max(nums, default=0) + 1)

    def acknowledge(self, iid: str, by: str) -> dict | None:
        inc = self.open.get(iid) or next((h for h in self.history_list if h.id == iid), None)
        if inc is None:
            return None
        inc.acknowledged_by = by
        inc.acknowledged_at = datetime.now(timezone.utc).isoformat()
        if self.persist:
            self.persist(inc)
        return inc.to_dict()

    def list_incidents(self, limit: int = 50) -> list[dict]:
        items = list(self.open.values()) + self.history_list
        items.sort(key=lambda i: i.opened_at, reverse=True)
        return [i.to_dict() for i in items[:limit]]

    def get(self, iid: str) -> dict | None:
        if iid in self.open:
            return self.open[iid].to_dict()
        for i in self.history_list:
            if i.id == iid:
                return i.to_dict()
        return None
