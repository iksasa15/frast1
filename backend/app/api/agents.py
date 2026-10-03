from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.hub import hub

router = APIRouter(tags=["agents"])


class ToggleBody(BaseModel):
    enabled: bool
    actor: str = Field(default="operator", min_length=1)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    incidentId: str | None = None
    lang: str | None = None


class AckBody(BaseModel):
    by: str = Field(min_length=1)


class Neighbor(BaseModel):
    device: str
    port: str
    neighbor: str
    neighborPort: str


class ReconcileBody(BaseModel):
    neighbors: list[Neighbor] = Field(max_length=500)


@router.get("/agents")
def roster(request: Request):
    rt = request.app.state.agents
    return {"agents": rt.roster(), "flow": rt.flow(), "health": rt.health()}


@router.get("/agents/trace")
def trace(request: Request, incidentId: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    return request.app.state.agents.trace.recent(limit=limit, incident_id=incidentId)


@router.post("/agents/{agent_id}/toggle")
def toggle(agent_id: str, body: ToggleBody, request: Request):
    rt = request.app.state.agents
    try:
        rt.set_enabled(agent_id, body.enabled, body.actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown agent") from None
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return rt.agents[agent_id].describe()


@router.post("/copilot/ask")
async def ask(body: AskBody, request: Request):
    rt = request.app.state.agents
    if not rt.copilot.enabled():
        raise HTTPException(status_code=503, detail="copilot agent is disabled")
    return await rt.copilot.ask(body.question, body.incidentId, body.lang)


@router.get("/knowledge/search")
def knowledge_search(
    request: Request, q: str = Query(min_length=1, max_length=300), k: int = Query(5, ge=1, le=10), kind: str | None = None
):
    hits = request.app.state.agents.knowledge.search(q, k=k, kinds={kind} if kind else None)
    return [{x: v for x, v in h.items() if x != "text"} for h in hits]


@router.get("/knowledge/stats")
def knowledge_stats(request: Request):
    kn = request.app.state.agents.knowledge
    kn.ensure_loaded()
    return kn.index.stats()


@router.post("/knowledge/reindex")
def knowledge_reindex(request: Request):
    return request.app.state.agents.knowledge.reindex()


@router.get("/incidents/{incident_id}/postmortem")
def postmortem(incident_id: str, request: Request):
    st = request.app.state
    pm = st.agents.learning.postmortems.get(incident_id)
    if pm is None:
        inc = st.incidents.open.get(incident_id) or next(
            (h for h in st.incidents.history_list if h.id == incident_id), None
        )
        if inc is None:
            raise HTTPException(status_code=404, detail="incident not found")
        if inc.status != "resolved":
            raise HTTPException(status_code=409, detail="postmortem is written when the incident is resolved")
        pm = st.agents.learning.build(inc)
    return pm


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge(incident_id: str, body: AckBody, request: Request):
    st = request.app.state
    inc = st.incidents.acknowledge(incident_id, body.by)
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    st.audit.log(body.by, "acknowledge", incident_id, {"incidentId": incident_id})
    await hub.broadcast("incident", inc)
    return inc


@router.post("/topology/reconcile")
def reconcile(body: ReconcileBody, request: Request):
    """Compare observed CDP/LLDP neighbours with the declared topology (drift check)."""
    return request.app.state.agents.topology_agent.reconcile([n.model_dump() for n in body.neighbors])
