import httpx

from app.core.config import settings


async def call(path: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{settings.lab_agent_url}{path}",
            headers={"x-agent-token": settings.lab_agent_token},
        )
        r.raise_for_status()
        return r.json()


async def demo(path: str) -> dict:
    """Call a fixed lab-agent demo endpoint; no user supplied command is accepted."""
    if not settings.demo_enabled or not settings.demo_lab_id:
        raise PermissionError("Live demo controls are disabled; set DEMO_ENABLED=1 and DEMO_LAB_ID on the isolated lab")
    return await call(path)
