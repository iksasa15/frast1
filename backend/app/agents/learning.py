from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .base import Agent
from .playbooks import kind_for_entity
from .roster import SPECS

IMPROVEMENTS = {
    "link": [
        "Alert earlier: add a sustained-utilization alert (above 70% for 5 minutes) on this uplink",
        "Plan capacity or a second path for this uplink",
        "If bulk transfers are expected, make the QoS policy permanent and schedule them off-peak",
    ],
    "svc-dns": [
        "Add a secondary DNS resolver and client-side failover",
        "Add a service watchdog (systemd Restart=on-failure) for the DNS daemon",
        "Alert on DNS success rate below 95% for one minute",
    ],
    "server": [
        "Apply CPU/memory limits (cgroups) to non-critical jobs on this server",
        "Add a standby node or scale out the web tier",
        "Alert on sustained CPU above 80%",
    ],
}


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def default_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "postmortems"


class LearningAgent(Agent):
    spec = SPECS["learning"]

    def __init__(self, runtime, out_dir: Path | None = None):
        super().__init__(runtime)
        self.out_dir = out_dir or default_dir()
        self.postmortems: dict[str, dict] = {}

    def kpis(self, inc) -> dict:
        t = inc.timings
        det, ana, rec = (_ts(t.get(k)) for k in ("detectedAt", "analyzedAt", "recoveredAt"))
        base = _ts(t.get("firstAnomalyAt")) or det
        d = lambda a, b: round(b - a, 2) if a is not None and b is not None else None
        return {
            "timeToDetect": d(base, det),
            "timeToRootCause": d(base, ana),
            "timeToRecover": d(base, rec),
            "rawAlerts": inc.raw_alert_count,
            "noiseReduction": round(1 - 1 / max(inc.raw_alert_count, 1), 4),
        }

    def _timeline(self, inc) -> list[dict]:
        t = inc.timings
        rows = [
            ("firstAnomalyAt", "First anomaly detected"),
            ("analyzedAt", "Root cause ranked"),
            ("rejectedAt", "Engineer rejected the first recommendation"),
            ("decidedAt", "Engineer decision recorded"),
            ("executedAt", "Remediation executed"),
            ("recoveredAt", "Recovery confirmed"),
        ]
        out = [{"ts": t[k], "event": label} for k, label in rows if t.get(k)]
        return sorted(out, key=lambda r: r["ts"])

    def _audit_for(self, inc) -> list[dict]:
        aid = (inc.action or {}).get("id")
        out = []
        for e in reversed(self.rt.audit.list()):
            d = e.get("detail") or {}
            if e["target"] in (inc.id, aid) or d.get("incidentId") == inc.id or d.get("replacement") == aid:
                out.append(e)
        return out

    def build(self, inc) -> dict:
        rc = inc.root_cause or {}
        kind = kind_for_entity(rc.get("entityId") or "")
        kpis = self.kpis(inc)
        trace = self.rt.trace.for_incident(inc.id)
        audit = self._audit_for(inc)
        action = inc.action or {}
        ver = getattr(inc, "verification", None) or {}
        expl = inc.explanation or {}
        went_well = [
            f"{inc.raw_alert_count} raw symptom(s) were collapsed into one incident ({kpis['noiseReduction']:.0%} noise reduction)",
            f"Root cause ranked in {kpis['timeToRootCause']} s" if kpis["timeToRootCause"] is not None else "Root cause ranked automatically",
        ]
        if action.get("decidedBy"):
            went_well.append(f"Human decision recorded ({action['decidedBy']}) before any change")
        if ver.get("status") == "verified":
            went_well.append("Recovery was verified against the playbook's numeric criteria")
        improve = list(IMPROVEMENTS.get(kind, []))
        if ver.get("status") in ("partial", "unverified"):
            improve.insert(0, f"Verification was {ver['status']} — review the playbook and consider its rollback")
        if inc.needs_investigation:
            improve.insert(0, "Confidence was below 55% — collect more telemetry for this element")
        rejected = [e for e in audit if e["action"] == "reject"]
        if rejected:
            improve.append(f"A recommendation was rejected first: \"{rejected[0]['detail'].get('reason', '')}\" — feed this into the playbook preconditions")

        pm = {
            "incidentId": inc.id,
            "title": inc.title,
            "status": inc.status,
            "severity": inc.severity,
            "openedAt": inc.opened_at,
            "resolvedAt": inc.resolved_at,
            "rootCause": rc,
            "summary": {"en": expl.get("en"), "ar": expl.get("ar")},
            "impact": {"affectedServices": inc.affected_services, "impactPath": inc.impact_path},
            "evidence": [e["text"] for e in inc.evidence[:10]],
            "candidates": [{"label": c["label"], "score": c["score"]} for c in inc.candidates],
            "timeline": self._timeline(inc),
            "decision": {
                "action": action.get("actionType"),
                "playbook": (action.get("plan") or {}).get("playbookId"),
                "risk": action.get("riskLevel"),
                "decidedBy": action.get("decidedBy"),
                "status": action.get("approvalStatus"),
            },
            "verification": ver,
            "kpis": kpis,
            "auditTrail": audit,
            "agentTrace": [
                {"agent": s["agent"], "action": s["action"], "durationMs": s["durationMs"], "decision": s["decision"], "status": s["status"]}
                for s in trace
            ],
            "wentWell": went_well,
            "improvements": improve,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
        pm["markdown"] = self._markdown(pm)
        return pm

    @staticmethod
    def _markdown(pm: dict) -> str:
        k = pm["kpis"]
        fmt = lambda v: "n/a" if v is None else f"{v} s"
        rc = pm["rootCause"] or {}
        L = [
            f"# Postmortem — {pm['incidentId']}: {pm['title']}",
            "",
            f"- Severity: {pm['severity']} · Status: {pm['status']}",
            f"- Opened: {pm['openedAt']} · Resolved: {pm['resolvedAt']}",
            "",
            "## Summary",
            pm["summary"]["en"] or "(no explanation generated)",
            "",
            pm["summary"]["ar"] or "",
            "",
            "## Root cause",
            f"{rc.get('label', 'unknown')} ({rc.get('entityId', '')}) — confidence {round(float(rc.get('confidence', 0)) * 100)}%.",
            "",
            "Candidates: " + ", ".join(f"{c['label']} ({c['score']})" for c in pm["candidates"]),
            "",
            "## Impact",
            f"Affected services: {', '.join(pm['impact']['affectedServices']) or 'none'}. "
            f"Impact path: {' -> '.join(pm['impact']['impactPath']) or 'n/a'}.",
            "",
            "## Evidence",
            *[f"- {e}" for e in pm["evidence"]],
            "",
            "## Timeline",
            *[f"- {r['ts']} — {r['event']}" for r in pm["timeline"]],
            "",
            "## Decision and action",
            f"Playbook {pm['decision']['playbook']} ({pm['decision']['action']}), risk {pm['decision']['risk']}, "
            f"decided by {pm['decision']['decidedBy']}, final status {pm['decision']['status']}.",
            f"Verification: {pm['verification'].get('status', 'n/a')} "
            f"({pm['verification'].get('passed', 0)}/{pm['verification'].get('total', 0)} criteria).",
            "",
            "## KPIs",
            f"Time to detect {fmt(k['timeToDetect'])} · time to root cause {fmt(k['timeToRootCause'])} · "
            f"time to recover {fmt(k['timeToRecover'])} · raw alerts {k['rawAlerts']} · noise reduction {k['noiseReduction']:.0%}.",
            "",
            "## Agent trace",
            *[f"- {s['agent']}.{s['action']} — {s['durationMs']} ms — {s['decision'] or s['status']}" for s in pm["agentTrace"]],
            "",
            "## What went well",
            *[f"- {w}" for w in pm["wentWell"]],
            "",
            "## What to improve",
            *[f"- {w}" for w in pm["improvements"]],
            "",
        ]
        return "\n".join(L)

    async def close_out(self, inc) -> dict:
        async with self.step("close_out", inc.id) as st:
            root = (inc.root_cause or {}).get("entityId")
            pm = self.build(inc)
            self.postmortems[inc.id] = pm
            if root:
                self.rt.history.record(root)
            saved = None
            try:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                path = self.out_dir / f"{inc.id}.md"
                path.write_text(pm["markdown"], encoding="utf-8")
                saved = str(path)
            except OSError:
                saved = None
            try:
                self.rt.knowledge.index_postmortem(pm)
            except Exception:
                pass
            st.data = {"historyRecorded": root, "postmortem": saved, "improvements": len(pm["improvements"])}
            st.decision = "postmortem_written"
            st.summary = (
                f"history +1 for {root}; postmortem written ({len(pm['improvements'])} improvement(s)) "
                "and indexed for future retrieval"
            )
        return pm
