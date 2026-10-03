from __future__ import annotations

from .base import Agent
from .guardrail import Verdict
from .roster import SPECS


class ExecutionAgent(Agent):
    spec = SPECS["execution"]

    async def execute(self, action: dict, incident_id: str, scenario: str, mode: str, verdict: Verdict) -> dict:
        """Run an approved playbook. Refuses without a fresh, allowing Guardrail verdict."""
        async with self.step("execute_playbook", incident_id) as st:
            if not verdict.allowed:
                raise PermissionError(f"guardrail verdict does not allow execution: {verdict.denial}")
            if action.get("approvalStatus") != "approved":
                raise PermissionError("action is not approved by a human")
            plan = action.get("plan") or {}
            commands = [s["command"] for s in plan.get("steps", []) if s.get("command")]

            adapter = self.rt.execution_adapter_ref()
            if adapter is not None:
                adapter.remediate()
                result = {"executed": True, "dryRun": False, "target": "test-adapter", "commands": commands}
                st.summary = f"test execution adapter completed '{scenario}'"
            elif mode == "sim":
                sim = self.rt.simulator_ref()
                if sim:
                    sim.remediate()
                    await sim.push_baseline()
                result = {"executed": True, "dryRun": False, "target": "simulator", "commands": commands}
                st.summary = f"simulator remediation for '{scenario}' triggered (approved by {action.get('decidedBy')})"
            elif not verdict.execute:
                result = {"executed": False, "dryRun": True, "target": "lab-agent", "commands": commands}
                st.decision = "dry_run"
                st.summary = f"DRY RUN — execution switched off; would run: {'; '.join(commands) or scenario}"
            else:
                from app.services import lab_client

                out = await lab_client.call(f"/remediate/{scenario}")
                result = {"executed": True, "dryRun": False, "target": "lab-agent", "output": out, "commands": commands}
                st.summary = f"lab agent executed whitelisted remediation '{scenario}'"
            if result["executed"]:
                self.rt.guardrail.record_execution()
                st.decision = "executed"
            st.data = {k: v for k, v in result.items() if k != "output"}
        return result
