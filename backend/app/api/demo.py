from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services import lab_client

router = APIRouter(tags=["demo"])


@router.get("/demo/status")
def status():
    return {"enabled": settings.demo_enabled and bool(settings.demo_lab_id), "labId": settings.demo_lab_id or None}


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
