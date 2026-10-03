from types import SimpleNamespace

import pytest

from app.agents.guardrail import GuardrailAgent, is_agent_actor, lab_url_is_private
from app.agents.runtime import AgentRuntime
from app.core.config import settings


def make():
    return GuardrailAgent(AgentRuntime())


def action(**kw):
    base = {
        "id": "ACT-1", "actionType": "apply_qos_policy", "approvalStatus": "pending",
        "plan": {"requiresApproval": True, "autoExecutable": False},
    }
    return {**base, **kw}


INC = SimpleNamespace(id="INC-1", status="awaiting_approval", needs_investigation=False, impact_path=[])


@pytest.mark.parametrize("who", ["", "  ", "system", "SYSTEM", "Agent:copilot", "agent:x", "orchestrator", "AI", "copilot", "system:cron"])
def test_agents_and_system_can_never_approve(who):
    assert is_agent_actor(who)
    v = make().evaluate("approve", action=action(), incident=INC, decided_by=who, mode="sim")
    assert not v.allowed and "human" in v.denial.lower()


def test_named_human_can_approve_in_sim():
    v = make().evaluate("approve", action=action(), incident=INC, decided_by="Ahmed", mode="sim")
    assert v.allowed and v.execute


def test_reject_also_requires_a_human():
    assert not make().evaluate("reject", action=action(), incident=INC, decided_by="bot").allowed
    assert make().evaluate("reject", action=action(), incident=INC, decided_by="Sara").allowed


def test_unknown_action_type_is_blocked():
    v = make().evaluate("approve", action=action(actionType="rm_rf"), incident=INC, decided_by="Ahmed", mode="sim")
    assert not v.allowed and "whitelist" in v.denial


@pytest.mark.parametrize("status", ["executed", "rejected", "approved"])
def test_only_pending_actions_can_be_approved(status):
    v = make().evaluate("approve", action=action(approvalStatus=status), incident=INC, decided_by="Ahmed", mode="sim")
    assert not v.allowed


def test_resolved_incident_cannot_accept_approval():
    inc = SimpleNamespace(id="I", status="resolved", needs_investigation=False, impact_path=[])
    assert not make().evaluate("approve", action=action(), incident=inc, decided_by="Ahmed", mode="sim").allowed


def test_recommendation_must_require_human_approval():
    bad = action(plan={"requiresApproval": False, "autoExecutable": True})
    assert not make().evaluate("recommend", action=bad, incident=INC).allowed
    assert make().evaluate("recommend", action=action(), incident=INC).allowed


def test_rate_limit_blocks_after_max_executions(monkeypatch):
    monkeypatch.setattr(settings, "guardrail_max_executions", 2)
    g = make()
    for _ in range(2):
        g.record_execution()
    v = g.evaluate("approve", action=action(), incident=INC, decided_by="Ahmed", mode="sim")
    assert not v.allowed and "executions" in v.denial


@pytest.mark.parametrize(
    "url,ok",
    [
        ("http://127.0.0.1:9000", True), ("http://localhost:9000", True), ("http://10.10.30.10:9000", True),
        ("http://192.168.1.5", True), ("http://lab-agent:9000", True), ("http://agent.lab", True),
        ("http://8.8.8.8:9000", False), ("https://lab-agent.example.com", False), ("", False),
    ],
)
def test_lab_scope_requires_private_address(url, ok):
    assert lab_url_is_private(url) is ok


def test_live_mode_blocks_public_lab_agent(monkeypatch):
    monkeypatch.setattr(settings, "lab_agent_url", "http://8.8.8.8:9000")
    v = make().evaluate("approve", action=action(), incident=INC, decided_by="Ahmed", mode="live")
    assert not v.allowed and "isolation" in v.denial


def test_execution_switch_turns_live_remediation_into_dry_run(monkeypatch):
    monkeypatch.setattr(settings, "rootiq_execution_enabled", False)
    live = make().evaluate("approve", action=action(), incident=INC, decided_by="Ahmed", mode="live")
    assert live.allowed and not live.execute and any("switched off" in w for w in live.warnings)
    sim = make().evaluate("approve", action=action(), incident=INC, decided_by="Ahmed", mode="sim")
    assert sim.allowed and sim.execute  # simulation is always a controlled, safe function


def test_low_confidence_and_wide_blast_are_warnings_not_blocks():
    inc = SimpleNamespace(id="I", status="awaiting_approval", needs_investigation=True, impact_path=list("abcdefgh"))
    v = make().evaluate("approve", action=action(), incident=inc, decided_by="Ahmed", mode="sim")
    assert v.allowed and len(v.warnings) == 2


@pytest.mark.asyncio
async def test_denial_is_traced_and_audited():
    g = make()
    v = await g.check("approve", incident=INC, action=action(), decided_by="system", mode="sim")
    assert not v.allowed
    step = g.rt.trace.recent()[-1]
    assert step["status"] == "denied" and step["decision"] == "deny"
    assert g.rt.audit.list()[0]["action"] == "guardrail_denied"
