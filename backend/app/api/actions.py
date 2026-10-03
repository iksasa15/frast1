from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["actions"])


class DecideBody(BaseModel):
    decidedBy: str = Field(min_length=1)


class RejectBody(BaseModel):
    decidedBy: str = Field(min_length=1)
    reason: str = ""


@router.post("/actions/{action_id}/approve")
async def approve(action_id: str, body: DecideBody, request: Request):
    try:
        return await request.app.state.actions.approve(action_id, body.decidedBy)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError:
        raise HTTPException(status_code=404, detail="action or incident not found") from None


@router.post("/actions/{action_id}/reject")
async def reject(action_id: str, body: RejectBody, request: Request):
    try:
        return await request.app.state.actions.reject(action_id, body.decidedBy, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError:
        raise HTTPException(status_code=404, detail="action or incident not found") from None


@router.get("/audit")
def audit(request: Request):
    return request.app.state.audit.list()


@router.get("/runs")
def runs(request: Request):
    items = request.app.state.actions.runs
    if not items:
        return {"runs": [], "summary": {"count": 0, "top1Accuracy": None, "avgTimeToRootCause": None, "avgNoiseReduction": None}}
    corrects = [1 if r["metrics"].get("correct") else 0 for r in items]
    ttrs = [r["metrics"]["timeToRootCause"] for r in items if r["metrics"].get("timeToRootCause") is not None]
    noises = [r["metrics"]["noiseReduction"] for r in items if r["metrics"].get("noiseReduction") is not None]
    return {
        "runs": items,
        "summary": {
            "count": len(items),
            "top1Accuracy": sum(corrects) / len(corrects) if corrects else None,
            "avgTimeToRootCause": (sum(ttrs) / len(ttrs)) if ttrs else None,
            "avgNoiseReduction": (sum(noises) / len(noises)) if noises else None,
        },
    }
