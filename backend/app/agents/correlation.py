from __future__ import annotations

from .base import Agent
from .roster import SPECS


class CorrelationAgent(Agent):
    spec = SPECS["correlation"]

    def pick(self, entity: str, ts: float, open_incidents: list):
        """Hot path: which open incident does this symptom belong to (None -> open a new one)."""
        self.stats.runs += 1
        return self.rt.correlator.pick(entity, ts, open_incidents)

    @staticmethod
    def noise_reduction(raw_alerts: int, incidents: int = 1) -> float:
        return round(1 - incidents / max(raw_alerts, 1), 4)

    async def opened(self, inc, entity: str, metric: str):
        async with self.step("open_incident", inc.id) as st:
            st.data = {"firstSymptom": {"entityId": entity, "metric": metric}}
            st.decision = "new_incident"
            st.summary = f"first symptom {entity}.{metric} — no related open incident, opened {inc.id}"

    async def storm_summary(self, inc) -> dict:
        async with self.step("collapse_storm", inc.id) as st:
            data = {
                "rawAlerts": inc.raw_alert_count,
                "incidents": 1,
                "noiseReduction": self.noise_reduction(inc.raw_alert_count),
                "members": sorted(inc.members),
            }
            st.data = data
            st.summary = (
                f"{inc.raw_alert_count} raw symptom(s) across {len(inc.members)} element(s) "
                f"-> 1 incident ({data['noiseReduction']:.0%} noise reduction)"
            )
        return data
