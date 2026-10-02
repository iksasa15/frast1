import pytest

from app.services.action_service import ActionService
from app.services.audit import AuditLog


@pytest.mark.asyncio
async def test_reject_requires_reason_unit():
    class Incidents:
        open: dict = {}

    incidents = Incidents()
    svc = ActionService(
        incidents=incidents,
        detector=type("D", (), {"active": {}})(),
        history=type("H", (), {"record": lambda self, e: None})(),
        audit=AuditLog(),
    )
    svc.actions["ACT-1"] = {
        "id": "ACT-1",
        "incidentId": "INC-1",
        "actionType": "x",
        "description": "d",
        "riskLevel": "low",
        "approvalStatus": "pending",
        "scenario": "uplink-congestion",
        "alternatives": [],
    }

    class Inc:
        id = "INC-1"
        action = svc.actions["ACT-1"]
        status = "awaiting_approval"
        timings: dict = {}

        def to_dict(self):
            return {}

    incidents.open["INC-1"] = Inc()

    with pytest.raises(ValueError, match="reason"):
        await svc.reject("ACT-1", "Ahmed", "no")
