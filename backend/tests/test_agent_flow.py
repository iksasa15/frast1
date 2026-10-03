"""End-to-end behaviour of the multi-agent layer on the simulated lab."""
import asyncio
import math
import time

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.event import Event
from app.services import lab_client
from tests.helpers import build_stack, recover, run_scenario


def order(trace):
    return [f"{s['agent']}.{s['action']}" for s in trace]


@pytest.mark.asyncio
async def test_diagnosis_runs_agents_in_order_and_stops_at_the_human(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s, "uplink-congestion")
    trace = s.agents.trace.for_incident(inc.id)
    names = order(trace)

    expected = [
        "correlation.open_incident", "telemetry.assess_sources", "correlation.collapse_storm",
        "topology.scope_dependencies", "rca.rank_causes", "explanation.write_explanation",
        "knowledge.retrieve_context", "remediation.plan_remediation", "guardrail.policy_recommend",
        "orchestrator.handoff_to_human",
    ]
    positions = [names.index(n) for n in expected]
    assert positions == sorted(positions), names
    assert not any(n.startswith(("execution.", "verification.", "learning.")) for n in names)

    a = inc.action
    assert inc.status == "awaiting_approval" and a["approvalStatus"] == "pending"
    plan = a["plan"]
    assert plan["requiresApproval"] is True and plan["autoExecutable"] is False
    assert plan["rollback"] and plan["verification"] and len(plan["steps"]) == 3
    assert any(st["kind"] == "change" and st.get("command") for st in plan["steps"])
    assert s.sim.recovering is False  # nothing ran


@pytest.mark.asyncio
async def test_all_three_scenarios_get_a_matching_playbook(tmp_path):
    expect = {"uplink-congestion": "PB-LINK-QOS", "dns-failure": "PB-DNS-RESTART", "server-spike": "PB-SERVER-KILL-RUNAWAY"}
    for scenario, playbook in expect.items():
        s = build_stack(tmp_path / scenario)
        (tmp_path / scenario).mkdir(exist_ok=True)
        inc = await run_scenario(s, scenario)
        assert inc.action["plan"]["playbookId"] == playbook, scenario


@pytest.mark.asyncio
async def test_agents_and_system_cannot_approve_and_nothing_executes(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s)
    for who in ("system", "agent:copilot", "orchestrator"):
        with pytest.raises(PermissionError):
            await s.actions.approve(inc.action["id"], who)
    assert inc.action["approvalStatus"] == "pending" and s.sim.recovering is False
    assert sum(1 for e in s.audit.list() if e["action"] == "guardrail_denied") == 3
    assert not any(e["action"] in ("approve", "execute") for e in s.audit.list())


@pytest.mark.asyncio
async def test_reject_then_approve_executes_once_and_double_approve_is_denied(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s)
    first = inc.action["id"]
    second = (await s.actions.reject(first, "Ahmed", "Outside change window"))["id"]
    assert second != first and inc.action["approvalStatus"] == "pending"

    done = await s.actions.approve(second, "Ahmed")
    assert done["approvalStatus"] == "executed" and done["decidedBy"] == "Ahmed"
    assert s.sim.recovering is True
    with pytest.raises(PermissionError):
        await s.actions.approve(second, "Ahmed")

    names = order(s.agents.trace.for_incident(inc.id))
    assert names.count("execution.execute_playbook") == 1
    assert names.index("guardrail.policy_reject") < names.index("execution.execute_playbook")


@pytest.mark.asyncio
async def test_recovery_is_verified_and_a_postmortem_is_written_and_learned(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s)
    root = inc.root_cause["entityId"]
    await s.actions.approve(inc.action["id"], "Ahmed")
    await recover(s, inc)

    assert inc.status == "resolved"
    assert inc.verification["status"] == "verified" and inc.verification["passed"] == inc.verification["total"]

    pm = s.agents.learning.postmortems[inc.id]
    assert pm["kpis"]["rawAlerts"] > 5 and pm["decision"]["decidedBy"] == "Ahmed"
    assert pm["improvements"] and pm["wentWell"] and "## Timeline" in pm["markdown"]
    assert (tmp_path / "postmortems" / f"{inc.id}.md").exists()
    assert s.history.count(root) == 1  # learning agent recorded the confirmed root cause

    kb_ids = set(s.agents.knowledge.index.chunks)
    assert f"postmortem:{inc.id}" in kb_ids
    names = order(s.agents.trace.for_incident(inc.id))
    assert names[-3:] == ["verification.verify_recovery", "learning.close_out", "orchestrator.incident_closed"]


@pytest.mark.asyncio
async def test_second_incident_finds_the_first_as_similar(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s)
    await s.actions.approve(inc.action["id"], "Ahmed")
    await recover(s, inc)
    await s.actions.recovery_tick()
    await s.incidents.archive_all()
    s.demo.update(state="idle")
    s.sim.reset()
    s.detector.active.clear()

    inc2 = await run_scenario(s)
    assert inc2.id != inc.id
    similar = [h["id"] for h in (inc2.knowledge or {}).get("similar", [])]
    assert any(inc.id in i for i in similar), similar


@pytest.mark.asyncio
async def test_disabled_optional_agents_degrade_gracefully(tmp_path):
    s = build_stack(tmp_path)
    s.agents.set_enabled("explanation", False)
    s.agents.set_enabled("knowledge", False)
    s.agents.set_enabled("telemetry", False)
    inc = await run_scenario(s)

    assert inc.explanation["source"] == "template" and inc.root_cause["confidence"] >= 0.55
    assert inc.action["approvalStatus"] == "pending"
    skipped = {(t["agent"], t["status"]) for t in s.agents.trace.for_incident(inc.id)}
    assert {("explanation", "skipped"), ("knowledge", "skipped"), ("telemetry", "skipped")} <= skipped


@pytest.mark.asyncio
async def test_slow_knowledge_agent_times_out_without_blocking_the_incident(tmp_path, monkeypatch):
    s = build_stack(tmp_path)

    async def slow(*a, **k):
        await asyncio.sleep(5)

    monkeypatch.setattr(s.agents.knowledge, "related", slow)
    monkeypatch.setattr(settings, "agent_timeout_s", 0.2)
    inc = await run_scenario(s)

    assert inc.status == "awaiting_approval" and inc.action
    errs = [t for t in s.agents.trace.for_incident(inc.id) if t["status"] == "error"]
    assert any(e["agent"] == "knowledge" and "timed out" in e["summary"] for e in errs)


@pytest.mark.asyncio
async def test_live_mode_dry_run_when_execution_is_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rootiq_execution_enabled", False)

    async def must_not_call(path):
        raise AssertionError(f"lab agent called while execution is off: {path}")

    monkeypatch.setattr(lab_client, "call", must_not_call)
    s = build_stack(tmp_path, mode="live")
    inc = await run_scenario(s)
    done = await s.actions.approve(inc.action["id"], "Ahmed")

    assert done["dryRun"] is True and done["approvalStatus"] == "approved"
    assert any(e["action"] == "dry_run" for e in s.audit.list())
    assert inc.id not in s.actions._recovering  # nothing was changed, so no recovery clock


@pytest.mark.asyncio
async def test_live_mode_executes_through_the_whitelisted_lab_agent(tmp_path, monkeypatch):
    calls = []

    async def fake_call(path):
        calls.append(path)
        return {"ok": True}

    monkeypatch.setattr(lab_client, "call", fake_call)
    monkeypatch.setattr(settings, "rootiq_execution_enabled", True)
    s = build_stack(tmp_path, mode="live")
    inc = await run_scenario(s)
    done = await s.actions.approve(inc.action["id"], "Ahmed")
    assert calls == ["/remediate/uplink-congestion"] and done["approvalStatus"] == "executed"


@pytest.mark.asyncio
async def test_execution_agent_refuses_without_approval_or_verdict(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s)
    ok_verdict = s.agents.guardrail.evaluate("approve", action=inc.action, incident=inc, decided_by="Ahmed", mode="live")
    with pytest.raises(PermissionError):  # action is still pending (not approved by a human)
        await s.agents.execution.execute(inc.action, inc.id, "uplink-congestion", "live", ok_verdict)
    bad_verdict = s.agents.guardrail.evaluate("approve", action=inc.action, incident=inc, decided_by="system", mode="live")
    with pytest.raises(PermissionError):
        await s.agents.execution.execute({**inc.action, "approvalStatus": "approved"}, inc.id, "x", "live", bad_verdict)
    assert s.sim.recovering is False


@pytest.mark.asyncio
async def test_telemetry_agent_flags_bad_data_and_rejects_non_finite(tmp_path):
    s = build_stack(tmp_path)
    ok = Event(source_id="link-r1-sw1", source_type="link", metric="link_utilization", value=42, unit="percent")
    await s.pipeline.ingest(ok)
    bad_range = Event(source_id="link-r1-sw1", source_type="link", metric="link_utilization", value=140, unit="percent")
    await s.pipeline.ingest(bad_range)
    bad_unit = Event(source_id="link-r1-sw1", source_type="link", metric="link_latency_ms", value=3, unit="furlongs")
    await s.pipeline.ingest(bad_unit)
    with pytest.raises(HTTPException) as e:
        await s.pipeline.ingest(Event(source_id="link-r1-sw1", source_type="link", metric="link_utilization", value=math.nan, unit="percent"))
    assert e.value.status_code == 422

    q = s.agents.telemetry.quality()
    assert q["flags"]["out_of_range"] == 1 and q["flags"]["unit_mismatch"] == 1 and q["flags"]["non_finite"] == 1
    assert 0 < q["qualityScore"] < 1 and "link-r1-sw1" in s.agents.telemetry.freshness()


@pytest.mark.asyncio
async def test_topology_agent_impact_and_drift(tmp_path):
    s = build_stack(tmp_path)
    ta = s.agents.topology_agent
    imp = ta.impact("link-r1-sw1")
    assert {"svc-dns", "svc-web"} <= set(imp["services"]) and "app01" in imp["impactPath"]
    assert ta.path("collector01", "app01")[0] == "collector01" and ta.path("collector01", "nope") == []

    # DC edge: r1 declares three neighbours (core / collector / firewall)
    partial = [{"device": "r1", "port": "Gi0/0", "neighbor": "sw-core", "neighborPort": "Gi0/1"}]
    assert ta.reconcile(partial)["ok"] is False
    full = partial + [
        {"device": "r1", "port": "Gi0/1", "neighbor": "collector01", "neighborPort": "ens3"},
        {"device": "r1", "port": "Gi0/2", "neighbor": "fw1", "neighborPort": "port1"},
    ]
    assert ta.reconcile(full)["ok"] is True
    rogue = full + [{"device": "r1", "port": "Gi0/0", "neighbor": "sw9", "neighborPort": "Gi0/7"}]
    drift = ta.reconcile(rogue)
    assert drift["ok"] is False and any(u["neighbor"] == "sw9" for u in drift["unexpected"])


@pytest.mark.asyncio
async def test_slow_recovery_waits_for_verification_then_resolves(tmp_path):
    """DNS ramps back slowly in the simulator: the 15 s clock alone must not close it as a success."""
    s = build_stack(tmp_path)
    inc = await run_scenario(s, "dns-failure")
    await s.actions.approve(inc.action["id"], "Ahmed")

    for _ in range(14):
        await s.sim.step(1.0)
    s.actions._recovering[inc.id] = time.time() - 16
    await s.actions.recovery_tick()
    assert inc.status != "resolved"  # 15 s passed but DNS success is still ~82%

    for _ in range(15):
        await s.sim.step(1.0)
    await s.actions.recovery_tick()
    assert inc.status == "resolved" and inc.verification["status"] == "verified"


@pytest.mark.asyncio
async def test_unverified_recovery_closes_after_the_grace_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "verify_grace_s", 0.0)
    s = build_stack(tmp_path)
    inc = await run_scenario(s, "dns-failure")
    await s.actions.approve(inc.action["id"], "Ahmed")
    for _ in range(5):
        await s.sim.step(1.0)
    s.actions._recovering[inc.id] = time.time() - 16
    await s.actions.recovery_tick()
    assert inc.status == "resolved" and inc.verification["status"] == "unverified"
    pm = s.agents.learning.postmortems[inc.id]
    assert "unverified" in pm["improvements"][0]


@pytest.mark.asyncio
async def test_incident_ids_continue_after_persisted_ones(tmp_path):
    s = build_stack(tmp_path)
    s.incidents.resume_sequence(["INC-0001", "INC-0007", "junk", "INC-abc"])
    inc = await run_scenario(s)
    assert inc.id == "INC-0008"


@pytest.mark.asyncio
async def test_slow_agents_do_not_get_their_analysis_cancelled_by_new_symptoms(tmp_path):
    """Regression: a slow explanation/LLM used to be cancelled by every new anomaly (livelock ~80 s)."""
    s = build_stack(tmp_path)
    real_write = s.agents.explanation.write

    async def slow_write(inc, kind, facts):
        await asyncio.sleep(0.8)
        return await real_write(inc, kind, facts)

    s.agents.explanation.write = slow_write
    for _ in range(40):
        await s.sim.step(1.0)
    s.demo.update(scenario="uplink-congestion", state="injected", injectedAt="t0")
    s.sim.inject("uplink-congestion")
    for _ in range(6):
        await s.sim.step(1.0)
        await asyncio.sleep(0)
    inc = next(iter(s.incidents.open.values()))
    inc.opened_epoch -= 60  # the 10 s debounce deadline has passed: analysis starts on the next symptom

    diagnosed_while_symptoms_kept_arriving = False
    for _ in range(6):  # a symptom every 0.6 s: the next one lands while the 0.8 s analysis is in flight
        await s.sim.step(1.0)
        await asyncio.sleep(0.6)
        diagnosed_while_symptoms_kept_arriving = diagnosed_while_symptoms_kept_arriving or bool(inc.root_cause)
    await asyncio.sleep(2.0)

    assert diagnosed_while_symptoms_kept_arriving  # not only after the symptoms stopped
    assert inc.root_cause and inc.status == "awaiting_approval" and inc.action
    assert sum(1 for t in s.agents.trace.for_incident(inc.id) if t["action"] == "handoff_to_human") == 1
