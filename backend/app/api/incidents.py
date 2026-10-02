from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
def list_incidents(request: Request):
    return request.app.state.incidents.list_incidents()


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, request: Request):
    inc = request.app.state.incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@router.get("/incidents/{incident_id}/replay")
def replay_incident(incident_id: str, request: Request):
    """Chronological steps for UI replay (evidence + milestones + alerts)."""
    inc = request.app.state.incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="incident not found")
    steps: list[dict] = []
    t = inc.get("timings") or {}

    def add(ts_iso: str | None, kind: str, label: str, entity_id: str | None = None, value=None):
        if not ts_iso:
            return
        try:
            ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            return
        steps.append(
            {
                "ts": ts,
                "kind": kind,
                "label": label,
                "entityId": entity_id,
                "value": value,
            }
        )

    add(t.get("firstAnomalyAt") or t.get("detectedAt"), "anomaly", "First anomaly")
    add(inc.get("openedAt"), "opened", f"Incident {inc.get('id')} opened")
    for ev in inc.get("evidence") or []:
        add(
            ev.get("ts"),
            "evidence",
            ev.get("text") or f"{ev.get('metric')}={ev.get('value')}",
            ev.get("entityId"),
            ev.get("value"),
        )
    root = (inc.get("rootCause") or {}).get("entityId")
    add(t.get("analyzedAt"), "root_cause", f"Root cause: {root}", root)
    add(t.get("decidedAt"), "decision", "Action decision")
    add(t.get("executedAt"), "executed", "Remediation executed")
    add(t.get("recoveredAt") or inc.get("resolvedAt"), "recovered", "Recovered")

    members = set(inc.get("members") or [])
    for a in list(request.app.state.pipeline.alerts):
        if a.get("sourceId") in members:
            add(
                a.get("ts"),
                "alert",
                f"Alert {a.get('metric')}={a.get('value')}",
                a.get("sourceId"),
                a.get("value"),
            )

    steps.sort(key=lambda s: s["ts"])
    return {"incidentId": incident_id, "steps": steps}


@router.post("/incidents/{incident_id}/analyze")
async def analyze_incident(incident_id: str, request: Request):
    result = await request.app.state.incidents.analyze(incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="incident not found or no anomalies")
    return result
