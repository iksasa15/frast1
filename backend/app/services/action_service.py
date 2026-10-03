from datetime import datetime, timezone
from itertools import count

from app.agents.playbooks import PLAYBOOKS, kind_for_entity  # noqa: F401  (kind_for_entity re-exported)
from app.agents.runtime import AgentRuntime
from app.core.config import settings
from app.services.hub import hub

# Backward-compatible view of the playbook catalogue (single source: app/agents/playbooks.py)
RECOMMENDATIONS = {
    kind: {
        "actionType": pb["actionType"],
        "risk": pb["risk"],
        "scenario": pb["scenario"],
        "description": pb["description"],
        "alternatives": pb["alternatives"],
    }
    for kind, pb in PLAYBOOKS.items()
}

class ActionService:
    def __init__(
        self,
        incidents,
        detector,
        history,
        audit,
        agents=None,
        execution_adapter_ref=None,
        demo_ref=None,
        simulator_ref=None,
    ):
        self.incidents = incidents
        self.detector = detector
        self.history = history
        self.audit = audit
        self.demo_ref = demo_ref or (lambda: {})
        self.actions: dict[str, dict] = {}
        self.runs: list[dict] = []
        self._seq = count(1)
        self._recovering: dict[str, float] = {}  # incident_id -> clear_since
        self.agents = agents or AgentRuntime(
            graph=getattr(incidents, "graph", None),
            history=history,
            topology=getattr(incidents, "topology", None),
            detector=detector,
            audit=audit,
        )
        self.agents.bind(
            actions=self,
            execution_adapter_ref=execution_adapter_ref or (lambda: None),
            demo_ref=self.demo_ref,
            simulator_ref=simulator_ref or (lambda: None),
        )
        if self.agents.audit is not audit:
            self.agents.audit = audit

    async def recommend(self, inc) -> dict | None:
        """Planner agent drafts the playbook; guardrail agent vets it. Nothing runs from here."""
        fields = await self.agents.remediation.plan(inc)
        aid = f"ACT-{next(self._seq):04d}"
        action = {
            "id": aid,
            "incidentId": inc.id,
            **fields,
            "approvalStatus": "pending",
        }
        verdict = await self.agents.guardrail.check(
            "recommend", incident=inc, action=action, mode="live"
        )
        if not verdict.allowed:
            self.audit.log("system", "recommendation_blocked", inc.id, {"reason": verdict.denial})
            return None
        action["guardrailWarnings"] = verdict.warnings
        self.actions[aid] = action
        inc.action = action
        inc.status = "awaiting_approval"
        return action

    async def approve(self, action_id: str, decided_by: str) -> dict:
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(action_id)
        inc = self.incidents.open.get(action["incidentId"])
        if not inc:
            raise KeyError(action["incidentId"])

        demo = self.demo_ref() or {}
        mode = demo.get("mode") or "live"
        verdict = await self.agents.guardrail.check(
            "approve", incident=inc, action=action, decided_by=decided_by, mode=mode
        )
        if not verdict.allowed:
            raise PermissionError(verdict.denial)

        now = datetime.now(timezone.utc).isoformat()
        action["approvalStatus"] = "approved"
        action["decidedBy"] = decided_by
        action["decidedAt"] = now
        inc.timings["decidedAt"] = now
        inc.status = "approved"
        inc.action = action
        self.audit.log(decided_by, "approve", action_id, {"incidentId": inc.id})

        scenario = action.get("scenario")
        if not scenario:
            raise ValueError("approved action has no execution target")
        try:
            result = await self.agents.execution.execute(action, inc.id, scenario, mode, verdict)
            if not result["executed"]:
                action["dryRun"] = True
                inc.status = "approved"
                self.audit.log(decided_by, "dry_run", action_id, {"scenario": scenario, "commands": result["commands"]})
            else:
                action["approvalStatus"] = "executed"
                action["executedAt"] = datetime.now(timezone.utc).isoformat()
                inc.timings["executedAt"] = action["executedAt"]
                inc.status = "approved"  # recovery monitor moves to resolved
                # Drop active anomalies for this blast radius so the 15s recovery clock can start
                for key in list(self.detector.active):
                    if key[0] in inc.members:
                        del self.detector.active[key]
                self._recovering[inc.id] = datetime.now(timezone.utc).timestamp()
                demo["state"] = "remediating"
                await hub.broadcast("demo", demo)
                self.audit.log(decided_by, "execute", action_id, {"scenario": scenario, "ok": True})
        except Exception as e:
            action["approvalStatus"] = "failed"
            self.audit.log(decided_by, "execute_failed", action_id, {"error": str(e)})

        inc.action = action
        if self.incidents.persist:
            self.incidents.persist(inc)
        await hub.broadcast("incident", inc.to_dict())
        return action

    async def reject(self, action_id: str, decided_by: str, reason: str) -> dict:
        if not reason or len(reason.strip()) < 5:
            raise ValueError("reason must be at least 5 characters")
        action = self.actions.get(action_id)
        if not action:
            raise KeyError(action_id)
        inc = self.incidents.open.get(action["incidentId"])
        if not inc:
            raise KeyError(action["incidentId"])
        verdict = await self.agents.guardrail.check(
            "reject", incident=inc, action=action, decided_by=decided_by
        )
        if not verdict.allowed:
            raise PermissionError(verdict.denial)

        now = datetime.now(timezone.utc).isoformat()
        action["approvalStatus"] = "rejected"
        action["decidedBy"] = decided_by
        action["reason"] = reason.strip()
        action["decidedAt"] = now
        inc.timings["decidedAt"] = now
        inc.timings["rejectedAt"] = now
        # Stay awaiting_approval with a fresh pending action
        new_action = {
            **{k: v for k, v in action.items() if k not in ("id", "approvalStatus", "decidedBy", "reason", "decidedAt", "executedAt")},
            "id": f"ACT-{next(self._seq):04d}",
            "approvalStatus": "pending",
        }
        self.actions[new_action["id"]] = new_action
        inc.action = new_action
        inc.status = "awaiting_approval"
        self.audit.log(
            decided_by,
            "reject",
            action_id,
            {"incidentId": inc.id, "reason": reason.strip(), "replacement": new_action["id"]},
        )
        if self.incidents.persist:
            self.incidents.persist(inc)
        await hub.broadcast("incident", inc.to_dict())
        return new_action

    async def recovery_tick(self):
        now = datetime.now(timezone.utc).timestamp()
        for inc in list(self.incidents.open.values()):
            action = inc.action or {}
            if action.get("approvalStatus") != "executed":
                continue
            started = self._recovering.get(inc.id)
            if started is None:
                # Backfill if process restarted mid-recovery
                exe = (action.get("executedAt") or inc.timings.get("executedAt"))
                if exe:
                    started = datetime.fromisoformat(exe.replace("Z", "+00:00")).timestamp()
                    self._recovering[inc.id] = started
                else:
                    self._recovering[inc.id] = now
                    continue
            # Prefer a clean detector, but don't let residual post-remediation noise
            # reset the clock forever — resolve once 15s have elapsed since execute.
            members_clear = all(
                not any(k[0] == m for k in self.detector.active) for m in inc.members
            )
            if not members_clear and now - started < 15:
                continue
            if now - started < 15:
                continue
            # Give slow-to-recover services a bounded grace: resolve when the playbook's numeric
            # criteria hold, or once the grace window is over (then recorded as unverified).
            criteria = ((inc.action or {}).get("plan") or {}).get("verification") or []
            if (
                criteria
                and self.agents.enabled("verification")
                and now - started < 15 + settings.verify_grace_s
                and self.agents.verification.evaluate(criteria)["status"] != "verified"
            ):
                continue
            # Resolved — the verification agent checks the playbook's numeric criteria first
            inc.verification = await self.agents.orchestrator.safe(
                "verification", "verify_recovery", inc.id, self.agents.verification.verify(inc)
            )
            recovered_at = datetime.now(timezone.utc).isoformat()
            inc.status = "resolved"
            inc.resolved_at = recovered_at
            inc.timings["recoveredAt"] = recovered_at
            root = (inc.root_cause or {}).get("entityId")
            demo = self.demo_ref() or {}
            demo["state"] = "recovered"
            await hub.broadcast("demo", demo)
            self._record_run(inc, demo)
            self._recovering.pop(inc.id, None)
            self.audit.log("system", "resolved", inc.id, {"root": root})
            # learning agent: history + postmortem (plain history update if the agent is off)
            pm = await self.agents.orchestrator.safe(
                "learning", "close_out", inc.id, self.agents.learning.close_out(inc)
            )
            if pm is None and root:
                self.history.record(root)
            await self.agents.orchestrator.closed(inc)
            self.incidents.history_list.append(inc)
            del self.incidents.open[inc.id]
            if self.incidents.persist:
                self.incidents.persist(inc)
            try:
                self.agents.knowledge.index_incident(inc.to_dict())
            except Exception:
                pass
            await hub.broadcast("incident", inc.to_dict())

    def _record_run(self, inc, context: dict):
        def parse(ts: str | None):
            if not ts:
                return None
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()

        t = inc.timings
        inj = parse(t.get("firstAnomalyAt") or t.get("detectedAt"))
        det = parse(t.get("detectedAt"))
        ana = parse(t.get("analyzedAt"))
        rec = parse(t.get("recoveredAt"))
        scenario = context.get("scenario") or (inc.action or {}).get("scenario")
        root = (inc.root_cause or {}).get("entityId")
        metrics = {
            "timeToDetect": (det - inj) if inj and det else None,
            "timeToRootCause": (ana - inj) if inj and ana else None,
            "timeToRecover": (rec - inj) if inj and rec else None,
            "rawAlerts": inc.raw_alert_count,
            "incidents": 1,
            "noiseReduction": 1 - 1 / max(inc.raw_alert_count, 1),
            "correct": None,
        }
        self.runs.append(
            {
                "scenario": scenario,
                "mode": context.get("mode") or "live",
                "incidentId": inc.id,
                "metrics": metrics,
            }
        )
        try:
            from app.db.models import RunRow
            from app.db.session import SessionLocal

            with SessionLocal() as s:
                s.add(
                    RunRow(
                        scenario=scenario or "unknown",
                        mode="live",
                        incident_id=inc.id,
                        metrics=metrics,
                    )
                )
                s.commit()
        except Exception:
            pass
