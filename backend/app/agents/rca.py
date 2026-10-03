from __future__ import annotations

from app.intelligence.rca import LOW_CONFIDENCE, SUPPRESSION, WEIGHTS, rank

from .base import Agent
from .roster import SPECS

COMPONENT_LABEL = {
    "metric_anomaly": ("metric severity", "شدة المقياس"),
    "dependency_overlap": ("dependency overlap", "تداخل الاعتماديات"),
    "temporal_proximity": ("temporal proximity", "القرب الزمني"),
    "blast_radius": ("blast radius", "نطاق التأثر"),
    "historical_support": ("historical support", "الدعم التاريخي"),
}


class RCAAgent(Agent):
    spec = SPECS["rca"]

    async def rank(self, inc, affected: list[str]):
        async with self.step("rank_causes", inc.id) as st:
            top, conf = rank(inc.anomalies, affected, self.rt.graph, self.rt.history)
            st.data = {
                "confidence": conf,
                "weights": WEIGHTS,
                "candidates": [
                    {
                        "entityId": c.entity_id,
                        "score": c.score,
                        "suppressedBy": c.suppressed_by,
                    }
                    for c in top
                ],
            }
            if not top:
                st.summary = "no candidates"
                st.decision = "needs_investigation"
                return top, conf
            st.decision = "needs_investigation" if conf < LOW_CONFIDENCE else "root_cause_selected"
            runner = f"; runner-up {top[1].label} ({top[1].score:.2f})" if len(top) > 1 else ""
            st.summary = f"top cause {top[0].label} — confidence {conf:.0%}{runner}"
        return top, conf

    def why_not(self, incident: dict, entity_id: str, lang: str = "en") -> dict:
        """Explain why `entity_id` is NOT the chosen root cause of `incident` (a to_dict() blob)."""
        cands = incident.get("candidates") or []
        root = (incident.get("rootCause") or {}).get("entityId")
        top = cands[0] if cands else None
        me = next((c for c in cands if c["entityId"] == entity_id), None)
        label = self.rt.topology_agent_label(entity_id)
        ar = lang == "ar"

        if entity_id == root:
            reason = (
                f"{label} IS the selected root cause."
                if not ar
                else f"{label} هو السبب الجذري المختار فعلًا."
            )
            kind = "is_root"
        elif me and me.get("suppressedBy"):
            up = self.rt.topology_agent_label(me["suppressedBy"])
            reason = (
                f"{label} also shows symptoms, but the upstream element {up} is anomalous too, so its score "
                f"was multiplied by {SUPPRESSION} (a symptom downstream of a failing element is treated as an effect)."
                if not ar
                else f"{label} تظهر عليه أعراض أيضًا، لكن العنصر السابق له {up} شاذّ كذلك، لذلك ضُربت درجته في {SUPPRESSION} "
                "(العرض الواقع بعد عنصر معطوب يُعامل كنتيجة لا كسبب)."
            )
            kind = "suppressed"
        elif me and top:
            gaps = {
                k: top["components"][k] - me["components"][k]
                for k in WEIGHTS
                if k in top["components"] and k in me["components"]
            }
            k, gap = max(gaps.items(), key=lambda kv: kv[1] * WEIGHTS[kv[0]])
            name = COMPONENT_LABEL[k][1 if ar else 0]
            reason = (
                f"{label} scored {me['score']:.2f} versus {top['score']:.2f} for the top cause; the biggest gap is {name} "
                f"({top['components'][k]:.2f} vs {me['components'][k]:.2f})."
                if not ar
                else f"{label} حصل على {me['score']:.2f} مقابل {top['score']:.2f} للسبب الأول؛ أكبر فرق في {name} "
                f"({top['components'][k]:.2f} مقابل {me['components'][k]:.2f})."
            )
            kind = "lower_score"
        elif entity_id in (incident.get("members") or []):
            reason = (
                f"{label} showed symptoms but ranked below the top 3 candidates."
                if not ar
                else f"{label} أظهر أعراضًا لكنه جاء خارج أفضل 3 مرشحين."
            )
            kind = "below_top3"
        else:
            reason = (
                f"No anomaly was observed on {label} during this incident, so it is not a candidate."
                if not ar
                else f"لم تُرصد أي شذوذات على {label} خلال هذه الحادثة، لذلك ليس مرشحًا."
            )
            kind = "no_symptoms"
        return {"entityId": entity_id, "kind": kind, "reason": reason, "candidate": me}
