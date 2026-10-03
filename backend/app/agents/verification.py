from __future__ import annotations

import operator

from .base import Agent
from .roster import SPECS

OPS = {"<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge}


class VerificationAgent(Agent):
    spec = SPECS["verification"]

    def evaluate(self, criteria: list[dict]) -> dict:
        state = self.rt.state
        checks = []
        for c in criteria:
            observed = None
            if state is not None:
                observed = state.metrics.get(c["entity"], {}).get(c["metric"])
            ok = observed is not None and OPS[c["op"]](observed, c["value"])
            checks.append({
                "entity": c["entity"], "metric": c["metric"], "op": c["op"], "target": c["value"],
                "observed": None if observed is None else round(observed, 2), "ok": bool(ok),
            })
        passed = sum(1 for c in checks if c["ok"])
        if not checks or state is None:
            status = "no_criteria"
        elif passed == len(checks):
            status = "verified"
        elif passed == 0:
            status = "unverified"
        else:
            status = "partial"
        return {"status": status, "passed": passed, "total": len(checks), "checks": checks}

    async def verify(self, inc) -> dict:
        async with self.step("verify_recovery", inc.id) as st:
            criteria = ((inc.action or {}).get("plan") or {}).get("verification") or []
            result = self.evaluate(criteria)
            st.data = result
            st.decision = result["status"]
            st.summary = (
                f"recovery {result['status']}: {result['passed']}/{result['total']} criteria met"
                if result["total"]
                else "no verification criteria available"
            )
            if result["status"] in ("unverified", "partial"):
                st.summary += " — consider the playbook rollback or escalation"
        return result
