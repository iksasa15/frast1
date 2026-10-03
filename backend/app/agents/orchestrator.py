from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import settings
from app.intelligence.explain import template
from app.intelligence.rca import LOW_CONFIDENCE

from .base import Agent
from .playbooks import kind_for_entity
from .roster import SPECS


@dataclass
class Investigation:
    top: list
    confidence: float
    root: object
    kind: str
    candidates: list[dict]
    impact_path: list[str]
    cause_path: list[str]
    needs_investigation: bool
    mv_evidence: dict | None = None
    explanation: dict | None = None
    knowledge: dict | None = None
    vendor: dict | None = None
    facts: dict = field(default_factory=dict)


class Orchestrator(Agent):
    """Runs the diagnosis pipeline. It can call agents; it cannot approve or execute."""

    spec = SPECS["orchestrator"]

    async def safe(self, agent_id: str, action: str, incident_id: str, coro, default=None):
        """Run one agent call with timeout + fallback; never let an optional agent break the incident."""
        agent = self.rt.agents[agent_id]
        if not agent.enabled():
            coro.close()
            self.rt.record_skip(agent_id, action, incident_id, "agent disabled by operator — deterministic fallback used")
            return default
        try:
            return await asyncio.wait_for(coro, timeout=settings.agent_timeout_s)
        except asyncio.TimeoutError:
            self.rt.record_error(agent_id, action, incident_id, f"timed out after {settings.agent_timeout_s}s — fallback used")
        except Exception:
            pass  # the agent's own step already recorded the error
        return default

    async def investigate(self, inc, affected: list[str], facts_fn) -> Investigation | None:
        rt = self.rt
        t0 = time.perf_counter()
        async with self.step("investigate", inc.id) as st:
            await self.safe("telemetry", "assess_sources", inc.id, rt.telemetry.incident_context(inc))
            await self.safe("correlation", "collapse_storm", inc.id, rt.correlation.storm_summary(inc))
            await self.safe("topology", "scope_dependencies", inc.id, rt.topology_agent.scope(inc, affected))

            top, conf = await rt.rca.rank(inc, affected)  # critical path: errors propagate to caller
            inc.timings["analyzedAt"] = datetime.now(timezone.utc).isoformat()
            if not top:
                st.decision = "needs_investigation"
                st.summary = "no root-cause candidates — escalated to the engineer"
                return None
            root = top[0]
            impact = rt.topology_agent.impact(root.entity_id)
            mv = await self.safe("detection", "multivariate_score", inc.id, rt.detection.multivariate(inc, root.entity_id))
            kind = kind_for_entity(root.entity_id)
            facts = facts_fn(inc, root.entity_id, conf)
            explanation = await self.safe(
                "explanation", "write_explanation", inc.id, rt.explanation.write(inc, kind, facts),
                default=template(kind, facts),  # deterministic fallback if the agent is off / slow / failing
            )
            knowledge = await self.safe("knowledge", "retrieve_context", inc.id, rt.knowledge.related(inc, root.entity_id))
            vendor = await self.safe("vendor", "enrich_incident", inc.id, rt.vendor.enrich(inc, root.entity_id))

            ms = round((time.perf_counter() - t0) * 1000, 1)
            st.data = {"root": root.entity_id, "confidence": conf, "pipelineMs": ms}
            st.decision = "diagnosed"
            st.summary = f"diagnosis complete in {ms} ms — {root.label} at {conf:.0%} confidence"
            return Investigation(
                top=top,
                confidence=conf,
                root=root,
                kind=kind,
                candidates=[c.to_dict() for c in top],
                impact_path=impact["impactPath"],
                cause_path=[root.entity_id],
                needs_investigation=conf < LOW_CONFIDENCE,
                mv_evidence=mv,
                explanation=explanation,
                knowledge=knowledge,
                vendor=vendor,
                facts=facts,
            )

    async def handoff(self, inc):
        """Last step before the human: the pipeline stops here until Approve/Reject."""
        async with self.step("handoff_to_human", inc.id) as st:
            action = inc.action or {}
            first = inc.timings.get("firstAnomalyAt")
            ana = inc.timings.get("analyzedAt")
            gap = None
            if first and ana:
                gap = round(
                    datetime.fromisoformat(ana.replace("Z", "+00:00")).timestamp()
                    - datetime.fromisoformat(first.replace("Z", "+00:00")).timestamp(), 1)
            st.data = {"action": action.get("id"), "playbook": (action.get("plan") or {}).get("playbookId"), "secondsSinceFirstSymptom": gap}
            st.decision = "awaiting_human"
            st.summary = (
                f"waiting for an engineer to approve or reject {action.get('id', 'the recommendation')} — "
                "nothing will run before that"
            )

    async def closed(self, inc):
        async with self.step("incident_closed", inc.id) as st:
            v = getattr(inc, "verification", None) or {}
            st.data = {"verification": v.get("status"), "resolvedAt": inc.resolved_at}
            st.decision = "resolved"
            st.summary = f"incident closed — recovery {v.get('status', 'n/a')}, postmortem generated"
