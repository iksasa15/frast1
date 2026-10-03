"""Vendor Intelligence + Syslog agents, and how the planner, guardrail, RAG and Copilot use the vendor knowledge."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agents.copilot import classify, vendor_intent
from app.agents.guardrail import GuardrailAgent
from app.agents.logs import canon_interface, clean_line
from app.agents.runtime import AgentRuntime
from app.api import vendors as vendors_api
from app.core.config import settings
from app.knowledge import get_kb
from tests.helpers import build_stack, run_scenario

CISCO_XE = "Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a, RELEASE SOFTWARE (fc3)"


def api_request(s):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(agents=s.agents, pipeline=s.pipeline)))


# ---------------------------------------------------------------- Vendor agent
def test_lab_devices_are_identified_from_their_topology_hints(tmp_path):
    s = build_stack(tmp_path)
    inv = {d["id"]: d for d in s.agents.vendor.inventory()}
    assert (inv["r1"]["vendor"], inv["r1"]["os"]) == ("cisco", "ios-xe")
    assert (inv["sw1"]["vendor"], inv["sw1"]["os"]) == ("cisco", "ios-xe")
    assert inv["app01"]["vendor"] == "linux"
    assert all(d["coverage"] for d in inv.values() if d["vendor"])


def test_sysdescr_on_a_topology_node_beats_the_free_text_hint(tmp_path):
    s = build_stack(tmp_path)
    s.topo.nodes["sw1"]["sysDescr"] = CISCO_XE
    s.agents.vendor.forget()
    ident = s.agents.vendor.node_identity("sw1")
    assert (ident["os"], ident["version"]) == ("ios-xe", "17.9.4a")
    s.topo.nodes["sw2"]["os"] = "nx-os"
    s.agents.vendor.forget()
    assert s.agents.vendor.node_identity("sw2")["os"] == "nx-os"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,root,problem,vendor",
    [("uplink-congestion", "link-r1-sw1", "link-congestion", "cisco"), ("dns-failure", "svc-dns", "dns-failure", "linux"), ("server-spike", "app01", "server-resource-pressure", "linux")],
)
async def test_every_scenario_gets_vendor_diagnostics_in_the_plan(tmp_path, scenario, root, problem, vendor):
    s = build_stack(tmp_path)
    inc = await run_scenario(s, scenario)
    ctx = inc.vendor_context
    assert ctx["rootEntity"] == root and ctx["problems"][0]["id"] == problem
    assert ctx["devices"][0]["vendor"] == vendor
    vc = inc.action["plan"]["vendorCommands"]
    assert vc["executable"] is False and vc["problem"] == problem
    cmds = [c for d in vc["diagnose"] for chk in d["checks"] for c in chk["commands"]]
    assert cmds and all(get_kb().is_read_only(c) for c in cmds)
    assert all("<if>" not in c for c in cmds)
    assert inc.to_dict()["vendorContext"]["problems"][0]["id"] == problem  # persisted / sent to the UI
    verdict = next(x for x in s.agents.trace.for_incident(inc.id) if x["agent"] == "guardrail" and x["action"] == "policy_recommend")
    assert "vendor_commands_read_only" in [c["id"] for c in verdict["data"]["checks"]] and verdict["status"] == "ok"
    assert any(x["agent"] == "vendor" and x["action"] == "enrich_incident" for x in s.agents.trace.for_incident(inc.id))


@pytest.mark.asyncio
async def test_link_congestion_lists_the_interface_on_both_ends_with_its_own_syntax(tmp_path):
    s = build_stack(tmp_path)
    inc = await run_scenario(s, "uplink-congestion")
    diag = {d["device"]: d for d in inc.action["plan"]["vendorCommands"]["diagnose"]}
    assert set(diag) == {"r1", "sw-core"}
    assert any("Gi0/0" in c for chk in diag["r1"]["checks"] for c in chk["commands"])
    assert any("Gi0/1" in c for chk in diag["sw-core"]["checks"] for c in chk["commands"])


def test_swapping_the_vendor_changes_the_commands_not_the_logic(tmp_path):
    s = build_stack(tmp_path)
    metrics = ["link_utilization", "link_latency_ms", "link_packet_loss"]
    cisco = s.agents.vendor.build_context("link-r1-sw1", metrics)
    s.topo.nodes["r1"]["vendor"] = "Juniper MX204 Junos"
    s.topo.nodes["r1"]["interfaces"][0]["name"] = "Gi0/0"  # port name is irrelevant to which syntax is chosen
    s.agents.vendor.forget()
    juniper = s.agents.vendor.build_context("link-r1-sw1", metrics)
    j = next(d for d in juniper["devices"] if d["id"] == "r1")
    assert j["vendor"] == "juniper" and j["os"] == "junos"
    first = lambda ctx: next(d for d in ctx["problems"][0]["diagnose"] if d["device"] == "r1")["checks"][0]["commands"][0]
    assert first(cisco) != first(juniper)
    assert [p["id"] for p in cisco["problems"]] == [p["id"] for p in juniper["problems"]]


def test_unknown_vendor_is_reported_not_guessed(tmp_path):
    s = build_stack(tmp_path)
    s.topo.nodes["sw1"]["vendor"] = "Acme Widgets 9000"
    s.agents.vendor.forget()
    ctx = s.agents.vendor.build_context("link-dist-a-sw1", ["link_utilization"])
    sw1 = next(d for d in ctx["devices"] if d["id"] == "sw1")
    assert sw1["vendor"] is None
    d = next(d for d in ctx["problems"][0]["diagnose"] if d["device"] == "sw1")
    assert d["checks"] == [] and "not identified" in d["note"]
    assert ctx["known"] == 1


def test_profile_only_vendor_is_identified_without_invented_commands(tmp_path):
    s = build_stack(tmp_path)
    s.topo.nodes["sw2"]["vendor"] = "TP-Link JetStream"
    s.agents.vendor.forget()
    ctx = s.agents.vendor.build_context("link-dist-a-sw2", ["link_utilization"])
    sw2 = next(d for d in ctx["problems"][0]["diagnose"] if d["device"] == "sw2")
    assert sw2["vendor"] == "tp-link" and sw2["coverage"] == "profile-only"
    assert all(not c["available"] and c["commands"] == [] for c in sw2["checks"])


@pytest.mark.asyncio
async def test_disabling_the_vendor_agent_degrades_gracefully(tmp_path):
    s = build_stack(tmp_path)
    s.agents.set_enabled("vendor", False, "Ahmed")
    inc = await run_scenario(s, "uplink-congestion")
    assert inc.root_cause and inc.action and inc.vendor_context is None
    assert "vendorCommands" not in inc.action["plan"]
    steps = s.agents.trace.for_incident(inc.id)
    assert any(x["agent"] == "vendor" and x["status"] == "skipped" for x in steps)


# ---------------------------------------------------------------- Guardrail policy
def _plan(**vc):
    base = {"executable": False, "diagnose": [{"device": "r1", "checks": [{"commands": ["show version"]}]}], "fixes": [{"id": "f", "needsApproval": True}]}
    return {"id": "ACT-1", "actionType": "apply_qos_policy", "approvalStatus": "pending",
            "plan": {"requiresApproval": True, "autoExecutable": False, "vendorCommands": {**base, **vc}}}


def test_guardrail_allows_read_only_vendor_commands():
    v = GuardrailAgent(AgentRuntime()).evaluate("recommend", action=_plan())
    assert v.allowed and "vendor_commands_read_only" in [c.id for c in v.checks]


@pytest.mark.parametrize(
    "vc",
    [
        {"diagnose": [{"device": "r1", "checks": [{"commands": ["show version", "reload"]}]}]},
        {"diagnose": [{"device": "r1", "checks": [{"commands": ["show version; write memory"]}]}]},
        {"executable": True},
        {"fixes": [{"id": "f", "needsApproval": False}]},
    ],
)
def test_guardrail_blocks_vendor_commands_that_could_change_things(vc):
    v = GuardrailAgent(AgentRuntime()).evaluate("recommend", action=_plan(**vc))
    assert not v.allowed and "vendor_commands_read_only" in v.denial or "Vendor diagnostic" in v.denial


# ---------------------------------------------------------------- Syslog agent
@pytest.mark.parametrize(
    "a,b",
    [("GigabitEthernet0/0", "Gi0/0"), ("gigabitethernet 0/0", "gi0/0"), ("TenGigabitEthernet1/0/1", "Te1/0/1"), ("Ethernet1", "Eth1"), ("Port-channel3", "Po3")],
)
def test_interface_names_are_canonicalized(a, b):
    assert canon_interface(a) == canon_interface(b)
    assert canon_interface("Gi0/0") != canon_interface("Gi0/1")
    assert canon_interface(None) is None


def test_clean_line_strips_control_characters_and_limits_length():
    assert "\x00" not in clean_line("a\x00b\x07c")
    assert len(clean_line("x" * 5000)) == 1000


@pytest.mark.asyncio
async def test_cisco_link_down_line_becomes_a_link_event_and_opens_an_incident(tmp_path):
    s = build_stack(tmp_path)
    out = await s.agents.logs.ingest(
        ["%LINK-3-UPDOWN: Interface GigabitEthernet0/0, changed state to down"], "r1", s.pipeline
    )
    r = out["results"][0]
    assert out["pushed"] == 1 and r["link"] == "link-r1-sw1" and r["vendor"] == "cisco" and r["state"] == "down"
    inc = next(iter(s.incidents.open.values()))
    assert "link-r1-sw1" in inc.members
    assert any(a.metric == "syslog_link_down" and a.value == 1.0 for a in inc.anomalies)
    await s.incidents.analyze(inc.id)
    assert inc.root_cause["entityId"] == "link-r1-sw1"
    assert "interface-flapping" in [p["id"] for p in inc.vendor_context["problems"]]


@pytest.mark.asyncio
async def test_unmapped_unknown_and_non_interface_lines_never_reach_the_pipeline(tmp_path):
    s = build_stack(tmp_path)
    out = await s.agents.logs.ingest(
        [
            "rpd[1]: SNMP_TRAP_LINK_DOWN: ifIndex 5, ifAdminStatus up(1), ifOperStatus down(2), ifName ge-0/0/1",  # port not in topology
            "totally unrelated chatter",
            "%OSPF-5-ADJCHG: Process 1, Nbr 10.0.0.2 on GigabitEthernet0/1 from FULL to DOWN, Neighbor Down: Dead timer expired",
            "%LINK-3-UPDOWN: Interface GigabitEthernet0/0, changed state to up",  # 'up' is recorded as value 0, not an anomaly
        ],
        "r1", s.pipeline, vendor_hint="juniper",
    )
    res = out["results"]
    assert res[0]["parsed"] and res[0]["vendor"] == "juniper" and res[0]["link"] is None and not res[0]["pushed"]
    assert not res[1]["parsed"]
    assert res[2]["event"] == "ospf_neighbor_change" and not res[2]["pushed"]
    assert res[3]["pushed"] and res[3]["state"] == "up"
    assert not s.incidents.open
    assert s.agents.logs.stats_view()["unparsed"] == 1


@pytest.mark.asyncio
async def test_device_vendor_from_topology_disambiguates_shared_formats(tmp_path):
    s = build_stack(tmp_path)
    line = "%LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet0/0, changed state to down"
    assert s.agents.logs.normalize(line, "r1")["vendor"] == "cisco"  # r1 is a Cisco in the topology
    s.topo.nodes["r1"]["vendor"] = "Arista EOS"
    s.agents.vendor.forget()
    assert s.agents.logs.normalize(line, "r1")["vendor"] == "arista"


# ---------------------------------------------------------------- API layer
@pytest.mark.asyncio
async def test_syslog_endpoint_requires_the_ingest_token_and_a_known_device(tmp_path):
    s = build_stack(tmp_path)
    body = vendors_api.SyslogBody(device="r1", lines=["%LINK-3-UPDOWN: Interface GigabitEthernet0/0, changed state to down"])
    with pytest.raises(HTTPException) as e:
        await vendors_api.post_syslog(body, api_request(s), x_rootiq_token="wrong")
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        await vendors_api.post_syslog(vendors_api.SyslogBody(device="nope", lines=["x"]), api_request(s), x_rootiq_token=settings.ingest_token)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        await vendors_api.post_syslog(vendors_api.SyslogBody(device="r1", vendor="nope", lines=["x"]), api_request(s), x_rootiq_token=settings.ingest_token)
    assert e.value.status_code == 422
    ok = await vendors_api.post_syslog(body, api_request(s), x_rootiq_token=settings.ingest_token)
    assert ok["pushed"] == 1
    with pytest.raises(ValueError):
        vendors_api.SyslogBody(lines=["x" * 2001])


def test_problem_endpoint_resolves_vendor_specific_checks_and_rejects_bad_input(tmp_path):
    s = build_stack(tmp_path)
    req = api_request(s)
    p = vendors_api.get_problem("crc-errors", req, vendor="juniper", os="junos", interface="ge-0/0/1")
    assert p["vendorChecks"] and any("ge-0/0/1" in c for chk in p["vendorChecks"] for c in chk["commands"])
    with pytest.raises(HTTPException) as e:
        vendors_api.get_problem("crc-errors", req, vendor="juniper", os="junos", interface="ge-0/0/1; reload")
    assert e.value.status_code == 422
    for args in (("nope", None), ("crc-errors", "nope")):
        with pytest.raises(HTTPException) as e:
            vendors_api.get_problem(args[0], req, vendor=args[1])
        assert e.value.status_code == 404


def test_identify_and_list_endpoints(tmp_path):
    s = build_stack(tmp_path)
    req = api_request(s)
    r = vendors_api.identify(vendors_api.IdentifyBody(sysDescr=CISCO_XE), req)
    assert (r["vendor"], r["os"], r["version"]) == ("cisco", "ios-xe", "17.9.4a")
    with pytest.raises(HTTPException) as e:
        vendors_api.identify(vendors_api.IdentifyBody(), req)
    assert e.value.status_code == 422
    listing = vendors_api.list_vendors(req, coverage="full", q=None)
    assert {v["id"] for v in listing["vendors"]} >= {"cisco", "juniper", "arista", "huawei", "hpe-aruba"}
    assert vendors_api.get_vendor("mikrotik", req)["id"] == "mikrotik"
    with pytest.raises(HTTPException):
        vendors_api.get_vendor("nope", req)


# ---------------------------------------------------------------- RAG + Copilot
def test_vendor_and_problem_knowledge_is_indexed_and_retrievable(tmp_path):
    s = build_stack(tmp_path)
    kn = s.agents.knowledge
    stats = kn.reindex()
    assert stats["byKind"]["vendor"] >= 40 and stats["byKind"]["problem"] >= 25 and stats["byKind"]["vendor-cmd"] >= 10
    hits = kn.search("juniper junos show interfaces extensive input errors", k=5)
    assert hits and any(h["kind"] in ("vendor-cmd", "vendor", "problem") and "juniper" in h["text"].lower() for h in hits[:3])
    top = kn.search("what is the CPU threshold for a server", k=1)
    assert top and top[0]["kind"] == "threshold"  # the vendor chunks must not drown the project's own facts


@pytest.mark.parametrize(
    "q,expected",
    [
        ("which command checks crc errors on juniper", "help"),
        ("ما أمر فحص أخطاء CRC على سيسكو", "help"),
        ("How do I show the mac table on Arista?", "help"),
        ("which vendors do you support?", "overview"),
        ("ما الشركات المصنعة المدعومة؟", "overview"),
        ("Why is R1 congested?", None),
        ("How do I run the backend?", None),
        ("juniper", None),
    ],
)
def test_vendor_intent_needs_a_cue_and_a_vendor(q, expected):
    assert vendor_intent(q, get_kb()) == expected


@pytest.mark.asyncio
async def test_copilot_answers_vendor_questions_from_the_kb_and_stays_read_only(tmp_path):
    s = build_stack(tmp_path)
    a = await s.agents.copilot.ask("which command checks crc errors on juniper", None, "en")
    assert a["intent"] == "vendor_help" and a["source"] == "deterministic"
    assert "show interfaces" in a["answer"].lower() and "does not run" in a["answer"]
    assert not any(src["source"].startswith("incident/") for src in a["sources"])
    ar = await s.agents.copilot.ask("ما الشركات المصنعة المدعومة؟", None, "ar")
    assert ar["intent"] == "vendor_help" and "43" in ar["answer"]
    en = await s.agents.copilot.ask("which vendors do you support?", None, "en")
    assert "profile" in en["answer"].lower() or "identification" in en["answer"].lower()
    assert "not every individual sku" in en["answer"].lower()
    blocked = await s.agents.copilot.ask("execute the fix on cisco", None, "en")
    assert blocked["intent"] == "action_request"
    assert classify("How do I run the backend?") == "docs"
