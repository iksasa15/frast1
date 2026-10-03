"""Demo controls.

Sim campus: offline inject/reset against the in-process Simulator.
Live lab: opt-in uplink-down endpoints (unchanged).
Hot-switch: POST /demo/mode swaps the in-memory graph; discovery file for LIVE LAB is never overwritten by the sim fixture.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services import lab_client
from app.services.hub import hub

router = APIRouter(tags=["demo"])
SCENARIOS = {"uplink-congestion", "dns-failure", "server-spike"}


class ModeBody(BaseModel):
    mode: str


def _require_sim(request: Request) -> None:
    demo = getattr(request.app.state, "demo", None) or {}
    if demo.get("mode") != "sim":
        raise HTTPException(
            status_code=503,
            detail="Simulator demos require Simulation mode. Use the TopBar to switch from LIVE LAB.",
        )
    if not getattr(request.app.state, "simulator", None):
        raise HTTPException(status_code=503, detail="Simulator is not running")


async def _clear_ops(st) -> None:
    await st.incidents.archive_all()
    st.detector.active.clear()
    st.detector.alert_level.clear()
    st.pipeline.alerts.clear()
    if hasattr(st, "state") and st.state is not None:
        st.state.metrics.clear()
        st.state.dirty.clear()
    if hasattr(st, "actions") and st.actions:
        st.actions.actions.clear()
        st.actions._recovering.clear()
    st.demo.update(scenario=None, state="idle", injectedAt=None)


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
    await _clear_ops(st)
    await hub.broadcast("demo", st.demo)
    await hub.broadcast("snapshot", st.snapshot())
    return st.demo


@router.post("/demo/mode")
async def set_mode(body: ModeBody, request: Request):
    """Hot-switch Simulation ↔ LIVE LAB without destroying the discovery snapshot on disk."""
    import asyncio

    if body.mode not in ("live", "sim"):
        raise HTTPException(status_code=400, detail="mode must be live|sim")
    st = request.app.state
    if st.demo.get("mode") == body.mode:
        return st.demo

    st.demo["mode"] = body.mode

    if body.mode == "sim":
        st.topology.activate_sim()
        if st.simulator:
            st.simulator.paused = False
            st.simulator.reset()
        else:
            from app.collectors.simulator import Simulator

            sim = Simulator(st.pipeline)
            st.simulator = sim
            st.tasks.append(asyncio.create_task(sim.run()))
    else:
        # Pause sim; restore live discovery graph — never call the lab agent here.
        if st.simulator:
            st.simulator.paused = True
            st.simulator.reset()
        st.topology.activate_live()

    st.refresh_graph()
    await _clear_ops(st)
    await hub.broadcast("demo", st.demo)
    await hub.broadcast("snapshot", st.snapshot())
    return st.demo
