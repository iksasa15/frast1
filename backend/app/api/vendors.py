"""Vendor knowledge, problem catalogue and syslog ingestion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.agents.vendor import sanitize_hint
from app.api.events import _auth, _rate_limit

router = APIRouter(tags=["vendors"])


class IdentifyBody(BaseModel):
    sysDescr: str | None = Field(default=None, max_length=2000)
    sysObjectId: str | None = Field(default=None, max_length=200)
    hint: str | None = Field(default=None, max_length=200)


class SyslogBody(BaseModel):
    device: str | None = Field(default=None, max_length=64, description="topology node id that sent the lines")
    vendor: str | None = Field(default=None, max_length=40, description="optional vendor id to disambiguate shared formats")
    lines: list[str] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def _line_length(cls, v: list[str]) -> list[str]:
        if any(len(x) > 2000 for x in v):
            raise ValueError("each syslog line must be at most 2000 characters")
        return v


def _kb(request: Request):
    return request.app.state.agents.vendor.kb


@router.get("/vendors")
def list_vendors(request: Request, coverage: str | None = None, q: str | None = Query(None, max_length=60)):
    kb = _kb(request)
    items = [kb.vendor_summary(vid) for vid in kb.vendors]
    if coverage:
        items = [v for v in items if v["coverage"] == coverage]
    if q:
        ql = q.lower()
        items = [v for v in items if ql in v["id"] or ql in v["name"].lower()]
    return {"stats": kb.stats(), "vendors": items}


@router.get("/vendors/inventory")
def inventory(request: Request):
    """Vendor / OS / version identity of every device in the topology."""
    return request.app.state.agents.vendor.inventory()


@router.post("/vendors/identify")
def identify(body: IdentifyBody, request: Request):
    if not (body.sysDescr or body.sysObjectId or body.hint):
        raise HTTPException(status_code=422, detail="provide sysDescr, sysObjectId or hint")
    return request.app.state.agents.vendor.identify(body.sysDescr, body.sysObjectId, sanitize_hint(body.hint))


@router.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: str, request: Request):
    v = _kb(request).vendor(vendor_id)
    if v is None:
        raise HTTPException(status_code=404, detail="unknown vendor")
    return v


@router.get("/problems")
def list_problems(request: Request):
    kb = _kb(request)
    return [
        {"id": p["id"], "title": p["title"], "titleAr": p["title_ar"], "category": p["category"], "severity": p["severity"],
         "rootiqKind": p.get("rootiq_kind")}
        for p in kb.problems.values()
    ]


@router.get("/problems/{problem_id}")
def get_problem(
    problem_id: str, request: Request, vendor: str | None = None, os: str | None = None, interface: str | None = None
):
    """A problem with the vendor-specific read-only checks (and reference fix commands) for one vendor/OS."""
    kb = _kb(request)
    p = kb.problems.get(problem_id)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown problem")
    out = dict(p)
    if vendor:
        if kb.vendor(vendor) is None:
            raise HTTPException(status_code=404, detail="unknown vendor")
        try:
            out["vendorChecks"] = kb.checks_for(problem_id, vendor, os, interface)
            out["vendorFixes"] = kb.fix_commands(problem_id, vendor, os, interface)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    return out


@router.post("/syslog", status_code=202)
async def post_syslog(body: SyslogBody, request: Request, x_rootiq_token: str | None = Header(None)):
    """Normalize raw syslog lines (any supported vendor); link up/down events are fed into the pipeline."""
    _auth(x_rootiq_token)
    _rate_limit()
    rt = request.app.state.agents
    if not rt.logs.enabled():
        raise HTTPException(status_code=503, detail="syslog agent is disabled")
    topo = rt.topology
    if body.device and topo is not None and body.device not in topo.nodes:
        raise HTTPException(status_code=422, detail=f"unknown device {body.device}")
    if body.vendor and rt.vendor.kb.vendor(body.vendor) is None:
        raise HTTPException(status_code=422, detail=f"unknown vendor {body.vendor}")
    return await rt.logs.ingest(body.lines, body.device, request.app.state.pipeline, body.vendor)


@router.get("/syslog/recent")
def syslog_recent(request: Request, limit: int = Query(50, ge=1, le=500)):
    logs = request.app.state.agents.logs
    return {"stats": logs.stats_view(), "events": list(logs.recent)[-limit:]}
