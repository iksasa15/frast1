from __future__ import annotations

from app.intelligence.explain import explain, template

from .base import Agent
from .roster import SPECS


class ExplanationAgent(Agent):
    spec = SPECS["explanation"]

    async def write(self, inc, kind: str, facts: dict) -> dict | None:
        async with self.step("write_explanation", inc.id) as st:
            if not self.enabled():
                out = template(kind, facts)
                st.status = "skipped"
                st.summary = "agent disabled — template used"
            else:
                out = await explain(kind, facts)
                st.summary = f"{out['source']} explanation (EN+AR), {facts.get('conf', 0)}% confidence"
            st.data = {"source": out["source"], "kind": kind}
            st.decision = out["source"]
        return out
