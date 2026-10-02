from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from app.services import lab_client
from app.services.hub import hub

router = APIRouter(prefix="/demo", tags=["demo"])
SCENARIOS = {"uplink-congestion", "dns-failure", "server-spike"}


async def _lab(path: str) -> dict:
    """Call the lab agent; surface connection failures as 503 instead of 500."""
    try:
        return await lab_client.call(path)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        raise HTTPException(
            status_code=503,
            detail=f"Live lab agent unreachable ({e}). Start or repair the lab agent before retrying.",
        ) from e


@router.post("/inject/{scenario}")
async def inject(scenario: str, request: Request):
    st = request.app.state
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="unknown scenario")
    if st.demo["state"] != "idle":
        raise HTTPException(status_code=409, detail="reset first")
    await _lab(f"/inject/{scenario}")
    st.demo.update(
        scenario=scenario,
        state="injected",
        injectedAt=datetime.now(timezone.utc).isoformat(),
    )
    await hub.broadcast("demo", st.demo)
    return st.demo


@router.post("/reset")
async def reset(request: Request):
    st = request.app.state
    await _lab("/reset")
    await st.incidents.archive_all()
    st.detector.active.clear()
    st.detector.alert_level.clear()
    st.pipeline.alerts.clear()
    if hasattr(st, "actions") and st.actions:
        st.actions.actions.clear()
        st.actions._recovering.clear()
    st.demo.update(scenario=None, state="idle", injectedAt=None)
    await hub.broadcast("demo", st.demo)
    await hub.broadcast("snapshot", st.snapshot())
    return st.demo
