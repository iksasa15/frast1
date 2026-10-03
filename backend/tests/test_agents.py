from pathlib import Path

import pytest

from app.agents.roster import EDGES, FLOW, ORDER, SPECS
from app.agents.runtime import AgentRuntime

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_roster_has_sixteen_unique_agents_with_complete_specs():
    assert len(ORDER) == 16 == len(set(ORDER))
    for aid in ORDER:
        s = SPECS[aid]
        assert s.id == aid
        for field in ("name", "name_ar", "mission", "mission_ar", "benefit", "benefit_ar"):
            assert getattr(s, field).strip(), f"{aid}.{field} is empty"
        for field in ("inputs", "outputs", "tools", "needs", "guardrails"):
            assert getattr(s, field), f"{aid}.{field} is empty"


def test_flow_only_references_known_agents():
    known = set(SPECS)
    assert {a for st in FLOW for a in st["agents"]} <= known
    assert {x for e in EDGES for x in e} <= known
    # every agent appears somewhere in the pipeline diagram
    assert known == {a for st in FLOW for a in st["agents"]} | {"orchestrator", "copilot", "knowledge"}


def test_every_agent_is_documented():
    doc = (DOCS / "AGENTS.md").read_text(encoding="utf-8")
    missing = [aid for aid in ORDER if f"`{aid}`" not in doc]
    assert not missing, f"docs/AGENTS.md is missing sections for: {missing}"


def test_safety_agents_cannot_be_disabled():
    rt = AgentRuntime()
    for aid in ("guardrail", "execution", "orchestrator", "rca", "detection", "topology", "correlation", "remediation"):
        with pytest.raises(PermissionError):
            rt.set_enabled(aid, False)
        assert rt.enabled(aid)


def test_optional_agents_can_be_toggled_and_audit_logged():
    rt = AgentRuntime()
    rt.set_enabled("copilot", False, "Ahmed")
    assert not rt.enabled("copilot")
    rt.set_enabled("copilot", True, "Ahmed")
    assert rt.enabled("copilot")
    assert [e["action"] for e in rt.audit.list()][:2] == ["agent_enabled", "agent_disabled"]
    with pytest.raises(KeyError):
        rt.set_enabled("nope", False)


@pytest.mark.asyncio
async def test_step_records_trace_and_error_stats():
    rt = AgentRuntime()
    agent = rt.telemetry

    async with agent.step("ok_action", "INC-1") as st:
        st.summary = "fine"
    with pytest.raises(ValueError):
        async with agent.step("bad_action", "INC-1"):
            raise ValueError("boom")

    steps = rt.trace.for_incident("INC-1")
    assert [s["status"] for s in steps] == ["ok", "error"]
    assert steps[1]["summary"].startswith("ValueError: boom")
    assert agent.stats.runs == 2 and agent.stats.errors == 1
    assert agent.describe()["stats"]["lastStatus"] == "error"
