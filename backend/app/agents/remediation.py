from __future__ import annotations

import copy

from .base import Agent
from .playbooks import PLAYBOOKS, WIDE_BLAST_ELEMENTS, kind_for_entity
from .roster import SPECS

RISK_ORDER = ["low", "medium", "high"]


def _bump(risk: str) -> str:
    i = RISK_ORDER.index(risk)
    return RISK_ORDER[min(i + 1, len(RISK_ORDER) - 1)]


class RemediationAgent(Agent):
    spec = SPECS["remediation"]

    @staticmethod
    def _vendor_commands(ctx: dict | None) -> dict | None:
        """Reference commands (from the Vendor agent) for the top matched problem. Shown to the engineer, never executed."""
        problems = (ctx or {}).get("problems") or []
        if not problems:
            return None
        top = problems[0]
        return {
            "problem": top["id"],
            "title": top["title"],
            "titleAr": top["titleAr"],
            "devices": [
                {k: d[k] for k in ("id", "label", "role", "interface", "vendor", "vendorName", "os", "osName", "confidence", "configModel")}
                for d in ctx["devices"]
            ],
            "diagnose": top["diagnose"],
            "fixes": top["fixes"],
            "executable": False,
            "note": "Reference commands for the engineer. RootIQ does not push them; only the whitelisted playbook runs after approval.",
        }

    def build(self, inc) -> dict:
        """Pure function: incident -> action fields (no id / approval state)."""
        root = (inc.root_cause or {}).get("entityId") or next(iter(sorted(inc.members)), "unknown")
        kind = kind_for_entity(root)
        pb = copy.deepcopy(PLAYBOOKS[kind])
        label = (inc.root_cause or {}).get("label") or root

        factors: list[str] = []
        risk = pb["risk"]
        if inc.needs_investigation:
            factors.append("Root-cause confidence is below 55% — verify manually before approving")
            risk = _bump(risk)
        if len(inc.impact_path) >= WIDE_BLAST_ELEMENTS:
            factors.append(f"Wide blast radius: {len(inc.impact_path)} downstream element(s)")
        factors.append("Live lab: an approved change is applied to running virtual devices")

        vendor_commands = self._vendor_commands(getattr(inc, "vendor_context", None))
        plan = {
            "playbookId": pb["id"],
            "title": pb["title"],
            "preconditions": pb["preconditions"],
            "steps": [{**s, "title": s["title"].format(label=label)} for s in pb["steps"]],
            "rollback": pb["rollback"],
            "verification": [
                {**c, "entity": c["entity"].format(root=root)} for c in pb["verification"]
            ],
            "expectedEffect": pb["expectedEffect"],
            "blastRadius": pb["blastRadius"],
            "riskFactors": factors,
            "labImplementation": pb["labImplementation"],
            "requiresApproval": True,
            "autoExecutable": False,
        }
        if vendor_commands:
            plan["vendorCommands"] = vendor_commands
        return {
            "actionType": pb["actionType"],
            "description": pb["description"],
            "riskLevel": risk,
            "scenario": pb["scenario"],
            "alternatives": pb["alternatives"],
            "plan": plan,
        }

    async def plan(self, inc) -> dict:
        async with self.step("plan_remediation", inc.id) as st:
            fields = self.build(inc)
            plan = fields["plan"]
            st.data = {
                "playbook": plan["playbookId"],
                "risk": fields["riskLevel"],
                "steps": len(plan["steps"]),
                "riskFactors": plan["riskFactors"],
                "vendorCommands": bool(plan.get("vendorCommands")),
            }
            st.decision = plan["playbookId"]
            st.summary = (
                f"playbook {plan['playbookId']} — risk {fields['riskLevel']}, "
                f"{len(plan['steps'])} steps, rollback defined, needs human approval"
            )
        return fields
