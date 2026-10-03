from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from networkx import NetworkXException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.intelligence.graph import TopologyGraph
from app.services.topology_service import TopologyError
from app.services.hub import hub

router = APIRouter(tags=["topology"])


class LayoutBody(BaseModel):
    positions: dict[str, dict[str, float]] = Field(default_factory=dict)


class DiscoveryBody(BaseModel):
    site: str = Field(min_length=1, max_length=128)
    vantage: str = Field(max_length=128)
    collector_id: str = Field(alias="collectorId", min_length=1, max_length=128)
    observed_at: datetime = Field(alias="observedAt")
    nodes: list[dict[str, Any]] = Field(max_length=500)
    links: list[dict[str, Any]] = Field(max_length=1000)
    services: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    errors: list[str] = Field(default_factory=list, max_length=100)


@router.get("/topology")
def get_topology(request: Request):
    # Prefer live snapshot (status + metrics) when state is available
    snap_fn = getattr(request.app.state, "snapshot", None)
    if callable(snap_fn):
        return snap_fn()["topology"]
    return request.app.state.topology.snapshot()


@router.put("/topology/layout")
def put_layout(body: LayoutBody, request: Request):
    try:
        request.app.state.topology.save_layout(body.positions)
    except TopologyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.post("/topology/discovery", status_code=202)
async def ingest_discovery(
    body: DiscoveryBody,
    request: Request,
    x_rootiq_token: str | None = Header(None),
):
    if x_rootiq_token != settings.ingest_token:
        raise HTTPException(status_code=401, detail="bad ingest token")
    raw = {
        "site": body.site,
        "vantage": body.vantage,
        "nodes": body.nodes,
        "links": body.links,
        "services": body.services,
    }
    try:
        TopologyGraph(raw)
        request.app.state.topology.replace_observed(
            raw,
            collector_id=body.collector_id,
            observed_at=body.observed_at.isoformat(),
            errors=body.errors,
        )
        # In sim mode discovery is persisted for LIVE LAB but the campus fixture stays on screen.
        if request.app.state.topology.source_mode != "sim":
            request.app.state.refresh_graph()
    except (TopologyError, NetworkXException, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.app.state.topology.source_mode == "sim":
        return {
            "accepted": True,
            "deferred": True,
            "nodes": len(body.nodes),
            "links": len(body.links),
            "services": len(body.services),
        }
    snapshot = request.app.state.snapshot()["topology"]
    await hub.broadcast("topology", snapshot)
    return {
        "accepted": True,
        "nodes": len(body.nodes),
        "links": len(body.links),
        "services": len(body.services),
    }


@router.get("/devices/{device_id}")
def get_device(device_id: str, request: Request):
    device = request.app.state.topology.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"unknown device: {device_id}")
    return device


@router.get("/links/{link_id}/metrics")
def get_link_metrics(link_id: str, request: Request, minutes: float = 5):
    if link_id not in request.app.state.topology.links:
        raise HTTPException(status_code=404, detail=f"unknown link: {link_id}")
    return request.app.state.state.link_metrics(link_id, minutes)
