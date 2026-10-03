from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    discovery = request.app.state.topology.metadata
    observed = discovery.get("observedAt")
    age = None
    if observed:
        age = max(
            0,
            (datetime.now(timezone.utc) - datetime.fromisoformat(observed.replace("Z", "+00:00"))).total_seconds(),
        )
    fresh = age is not None and age <= settings.discovery_stale_after_s
    # Prefer env mode so live lab health is never rewritten by sim demo state.
    mode = settings.rootiq_mode if settings.rootiq_mode in ("sim", "live") else "live"
    status = "ok" if (mode == "sim" or fresh) else "degraded"
    return {
        "status": status,
        "mode": mode,
        "discovery": {**discovery, "ageSeconds": round(age, 1) if age is not None else None, "fresh": fresh},
    }
