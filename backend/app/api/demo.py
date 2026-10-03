"""Demo controls.

Sim campus (ROOTIQ_MODE=sim): offline inject/reset against the in-process Simulator.
Live lab: opt-in uplink-down endpoints only — never mixed with sim inject, never hot-switched.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.services import lab_client
from app.services.hub import hub

router = APIRouter(tags=["demo"])
SCENARIOS = {"uplink-congestion", "dns-failure", "server-spike"}


def _require_sim(request: Request) -> None:
    demo = getattr(request.app.state, "demo", None) or {}
    if demo.get("mode") != "sim" or settings.rootiq_mode != "sim":
        raise HTTPException(
            status_code=503,
            detail="Simulator demos are only available when ROOTIQ_MODE=sim. Live lab is left untouched.",
        )
    if not getattr(request.app.state, "simulator", None):
        raise HTTPException(status_code=503, detail="Simulator is not running")


# ── Live lab (unchanged contract) ───────────────────────────────────────────


@router.get("/demo/status")
def status():
    return {
        "enabled": settings.demo_enabled and bool(settings.demo_lab_id),
        "labId": settings.demo_lab_id or None,
    }


@router.post("/demo/uplink-down/trigger")
async def trigger_uplink_down():
    try:
        return await lab_client.demo("/inject/uplink-down")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("/demo/uplink-down/restore")
async def restore_uplink_down():
    try:
        return await lab_client.demo("/remediate/uplink-down")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


# ── Simulator only ──────────────────────────────────────────────────────────


@router.post("/demo/inject/{scenario}")
async def inject(scenario: str, request: Request):
    _require_sim(request)
    st = request.app.state
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="unknown scenario")
    if st.demo["state"] != "idle":
        raise HTTPException(status_code=409, detail="reset first")
    st.simulator.inject(scenario)
    st.demo.update(
        scenario=scenario,
        state="injected",
        injectedAt=datetime.now(timezone.utc).isoformat(),
    )
    await hub.broadcast("demo", st.demo)
    return st.demo


@router.post("/demo/reset")
async def reset(request: Request):
    _require_sim(request)
    st = request.app.state
    st.simulator.reset()
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
