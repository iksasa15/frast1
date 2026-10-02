from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import lab_client
from app.services.hub import hub

router = APIRouter(prefix="/demo", tags=["demo"])
SCENARIOS = {"uplink-congestion", "dns-failure", "server-spike"}


class ModeBody(BaseModel):
    mode: str


async def _lab(path: str) -> dict:
    """Call the lab agent; surface connection failures as 503 instead of 500."""
    try:
        return await lab_client.call(path)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        raise HTTPException(
            status_code=503,
            detail=f"Live lab agent unreachable ({e}). Switch TopBar to Simulation, or start the lab agent.",
        ) from e


@router.post("/inject/{scenario}")
async def inject(scenario: str, request: Request):
    st = request.app.state
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="unknown scenario")
    if st.demo["state"] != "idle":
        raise HTTPException(status_code=409, detail="reset first")
    if st.demo["mode"] == "sim":
        st.simulator.inject(scenario)
    else:
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
    if st.demo["mode"] == "sim":
        st.simulator.reset()
    else:
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


@router.post("/mode")
async def set_mode(body: ModeBody, request: Request):
    """Hot-switch sim ↔ live: pause/resume simulator, reset state, broadcast snapshot."""
    import asyncio

    if body.mode not in ("live", "sim"):
        raise HTTPException(status_code=400, detail="mode must be live|sim")
    st = request.app.state
    prev = st.demo.get("mode")
    st.demo["mode"] = body.mode

    # Reset operational state
    if hasattr(st, "simulator") and st.simulator:
        if body.mode == "sim":
            st.simulator.paused = False
            st.simulator.reset()
        else:
            st.simulator.paused = True
            st.simulator.reset()
    elif body.mode == "sim" and not hasattr(st, "simulator"):
        from app.collectors.simulator import Simulator

        sim = Simulator(st.pipeline)
        st.simulator = sim
        st.tasks.append(asyncio.create_task(sim.run()))

    await st.incidents.archive_all()
    st.detector.active.clear()
    st.detector.alert_level.clear()
    st.pipeline.alerts.clear()
    if hasattr(st, "actions") and st.actions:
        st.actions.actions.clear()
        st.actions._recovering.clear()
    st.demo.update(scenario=None, state="idle", injectedAt=None)

    if body.mode == "live" and prev == "sim":
        try:
            await lab_client.call("/reset")
        except Exception:
            pass

    await hub.broadcast("demo", st.demo)
    await hub.broadcast("snapshot", st.snapshot())
    return st.demo
