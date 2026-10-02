"""AgentRuntime: builds the 16 agents, owns the trace store and the operator kill-switches."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.services.audit import AuditLog

from .base import TraceStore
from .copilot import CopilotAgent
from .correlation import CorrelationAgent
from .detection import DetectionAgent
from .execution import ExecutionAgent
from .explanation import ExplanationAgent
from .guardrail import GuardrailAgent
from .knowledge import KnowledgeAgent
from .learning import LearningAgent
from .logs import LogsAgent
from .orchestrator import Orchestrator
from .rca import RCAAgent
from .remediation import RemediationAgent
from .roster import EDGES, FLOW, ORDER
from .telemetry import TelemetryAgent
from .topology import TopologyAgent
from .vendor import VendorAgent
from .verification import VerificationAgent


class AgentRuntime:
    def __init__(
        self,
        *,
        graph=None,
        history=None,
        topology=None,
        correlator=None,
        detector=None,
        audit: AuditLog | None = None,
        postmortem_dir: Path | None = None,
    ):
        self.graph = graph
        self.history = history
        self.topology = topology
        self.correlator = correlator
        self.detector = detector
        self.audit = audit if audit is not None else AuditLog()
        # bound after construction (they need the services that need this runtime)
        self.state = None
        self.incidents = None
        self.actions = None
        self.pipeline = None
        self.execution_adapter_ref = lambda: None

        self.trace = TraceStore()
        self._disabled: set[str] = set()

        self.orchestrator = Orchestrator(self)
        self.telemetry = TelemetryAgent(self)
        self.detection = DetectionAgent(self)
        self.topology_agent = TopologyAgent(self)
        self.vendor = VendorAgent(self)
        self.logs = LogsAgent(self)
        self.correlation = CorrelationAgent(self)
        self.rca = RCAAgent(self)
        self.explanation = ExplanationAgent(self)
        self.knowledge = KnowledgeAgent(self)
        self.copilot = CopilotAgent(self)
        self.remediation = RemediationAgent(self)
        self.guardrail = GuardrailAgent(self)
        self.execution = ExecutionAgent(self)
        self.verification = VerificationAgent(self)
        self.learning = LearningAgent(self, out_dir=postmortem_dir)
        self.agents = {
            a.spec.id: a
            for a in [
                self.orchestrator, self.telemetry, self.logs, self.detection, self.topology_agent, self.vendor,
                self.correlation, self.rca, self.explanation, self.knowledge, self.copilot, self.remediation,
                self.guardrail, self.execution, self.verification, self.learning,
            ]
        }

    def bind(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        return self

    # ---- operator controls
    def enabled(self, agent_id: str) -> bool:
        return agent_id not in self._disabled

    def set_enabled(self, agent_id: str, flag: bool, actor: str = "operator"):
        agent = self.agents.get(agent_id)
        if agent is None:
            raise KeyError(agent_id)
        if not agent.spec.can_disable and not flag:
            raise PermissionError(f"{agent.spec.name} is a safety/core agent and cannot be disabled")
        (self._disabled.discard if flag else self._disabled.add)(agent_id)
        self.audit.log(actor, "agent_enabled" if flag else "agent_disabled", agent_id, {})

    # ---- helpers for the orchestrator / agents
    def topology_agent_label(self, entity_id: str) -> str:
        try:
            return self.topology_agent.label(entity_id)
        except Exception:
            return entity_id

    def _direct_step(self, agent_id, action, incident_id, status, summary):
        agent = self.agents[agent_id]
        agent.stats.skipped += status == "skipped"
        agent.stats.errors += status == "error"
        agent.stats.last_at = datetime.now(timezone.utc).isoformat()
        agent.stats.last_status, agent.stats.last_summary = status, summary
        return self.trace.add(
            agent=agent_id, action=action, incident_id=incident_id, status=status,
            started_at=agent.stats.last_at, duration_ms=0.0, summary=summary,
        )

    def record_skip(self, agent_id, action, incident_id, reason):
        return self._direct_step(agent_id, action, incident_id, "skipped", reason)

    def record_error(self, agent_id, action, incident_id, reason):
        return self._direct_step(agent_id, action, incident_id, "error", reason)

    # ---- introspection
    def roster(self) -> list[dict]:
        return [self.agents[i].describe() for i in ORDER]

    def flow(self) -> dict:
        return {"stages": FLOW, "edges": EDGES}

    def health(self) -> dict:
        from app.llm import client as llm

        return {
            "agents": len(self.agents),
            "disabled": sorted(self._disabled),
            "llm": llm.info(),
            "telemetry": self.telemetry.quality(),
            "knowledge": self.knowledge.index.stats() if self.knowledge._loaded else {"chunks": 0, "loaded": False},
            "traceSteps": len(self.trace.steps),
            "vendors": self.vendor.kb.stats(),
            "syslog": self.logs.stats_view(),
        }
