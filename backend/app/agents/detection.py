from __future__ import annotations

from datetime import datetime, timezone

from app.intelligence.anomaly import MultivariateScorer
from app.intelligence.thresholds import THRESHOLDS

from .base import Agent
from .roster import SPECS


class DetectionAgent(Agent):
    spec = SPECS["detection"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.anomalies_seen = 0
        self.raw_alerts = 0
        self._scorer: MultivariateScorer | None = None

    def observe(self, entity: str, metric: str, value: float, ts: float):
        """Hot path: same contract as Detector.observe -> (anomaly|None, raw_alert_level|None)."""
        detector = self.rt.detector
        anomaly, raw = detector.observe(entity, metric, value, ts)
        self.stats.runs += 1
        if raw:
            self.raw_alerts += 1
        if anomaly is not None and anomaly.first_seen == anomaly.last_seen:
            self.anomalies_seen += 1
        return anomaly, raw

    @staticmethod
    def describe_anomaly(anomaly) -> dict:
        warn, crit, direction = THRESHOLDS.get(anomaly.metric, (None, None, "up"))
        return {
            "entityId": anomaly.entity_id,
            "metric": anomaly.metric,
            "value": anomaly.value,
            "baseline": round(anomaly.baseline, 2),
            "severity": anomaly.severity,
            "method": "static-threshold" if warn is not None else "baseline",
            "thresholds": {"warning": warn, "critical": crit, "direction": direction},
        }

    async def multivariate(self, inc, root_id: str) -> dict | None:
        """Isolation Forest score over the incident's metrics — supporting evidence only."""
        async with self.step("multivariate_score", inc.id) as st:
            if self._scorer is None:
                self._scorer = MultivariateScorer()
            if self._scorer.m is None:
                st.skip("no trained Isolation Forest model — skipped (optional)")
                return None
            metrics: dict[str, dict[str, float]] = {}
            for a in inc.anomalies:
                metrics.setdefault(a.entity_id, {})[a.metric] = a.value
            score = self._scorer.score(metrics)
            st.data = {"score": None if score is None else round(score, 3)}
            if score is None or score <= 0.6:
                st.summary = f"multivariate score {score if score is None else round(score, 2)} — below evidence bar"
                return None
            st.decision = "evidence_added"
            st.summary = f"multivariate anomaly score {score:.2f} added as supporting evidence"
            return {
                "id": f"ev-mv-{len(inc.evidence) + 1}",
                "entityId": root_id,
                "metric": "multivariate_score",
                "value": round(score, 2),
                "baseline": 0.0,
                "unit": "",
                "ts": datetime.now(timezone.utc).isoformat(),
                "text": (
                    f"Multivariate anomaly score {score:.2f} "
                    "(Isolation Forest trained on 15 min of healthy lab data)"
                ),
            }
