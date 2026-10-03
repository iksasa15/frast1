"""Priority vendors (Juniper, Fortinet, Aruba, Arista next to the Cisco lab): identity, commands, config model, syslog, Copilot."""
from pathlib import Path

import pytest

from app.agents.runtime import AgentRuntime
from app.core.config import settings
from app.intelligence.graph import TopologyGraph
from app.knowledge import get_kb
from app.services.topology_service import TopologyService

EXAMPLE = Path(__file__).resolve().parents[2] / "configs" / "topology.multivendor.example.json"
kb = get_kb()


@pytest.fixture()
def rt(monkeypatch):
    monkeypatch.setattr(settings, "topology_path", str(EXAMPLE))
    topo = TopologyService()
    return AgentRuntime(graph=TopologyGraph(topo.raw), topology=topo)


class Sink:
    def __init__(self):
        self.events = []

    async def ingest(self, ev):
        self.events.append(ev)


def test_example_topology_is_valid_and_each_node_is_identified(rt):
    inv = {d["id"]: d for d in rt.vendor.inventory()}
    assert (inv["r1"]["vendor"], inv["r1"]["os"]) == ("cisco", "ios")
    assert (inv["swjun"]["vendor"], inv["swjun"]["os"], inv["swjun"]["version"]) == ("juniper", "junos", "19.4R1.10")
    assert (inv["swarista"]["vendor"], inv["swarista"]["os"], inv["swarista"]["version"]) == ("arista", "eos", "4.30.5M")
    assert (inv["fw1"]["vendor"], inv["fw1"]["os"]) == ("fortinet", "fortios")
    assert (inv["swaruba"]["vendor"], inv["swaruba"]["os"], inv["swaruba"]["version"]) == ("hpe-aruba", "aos-cx", "FL.10.09.1020")
    assert {d["configModel"]["style"] for d in inv.values() if d["configModel"]} == {"running-startup", "candidate-commit", "auto-save"}


def test_same_problem_gets_each_vendors_own_syntax_with_the_right_port(rt):
    ctx = rt.vendor.build_context("link-fw1-swaruba", ["syslog_link_down"])
    assert ctx["problems"][0]["id"] == "interface-flapping"
    diag = {d["device"]: d for d in ctx["problems"][0]["diagnose"]}
    assert set(diag) == {"fw1", "swaruba"}
    first = lambda d: next(c["commands"][0] for c in d["checks"] if c["available"])
    assert first(diag["fw1"]) != first(diag["swaruba"])
    assert any("port2" in c for chk in diag["fw1"]["checks"] for c in chk["commands"])
    assert any("1/1/1" in c for chk in diag["swaruba"]["checks"] for c in chk["commands"])
    assert all(kb.is_read_only(c) for d in diag.values() for chk in d["checks"] for c in chk["commands"])


def test_interface_error_command_differs_across_all_five_vendors(rt):
    cmds = {}
    for link, dev in (("link-r1-swjun", "swjun"), ("link-r1-swarista", "swarista"), ("link-r1-fw1", "fw1"), ("link-fw1-swaruba", "swaruba"), ("link-r1-fw1", "r1")):
        d = next(x for x in rt.vendor.devices_for(link) if x["id"] == dev)
        entry = kb.commands(d["vendor"], d["os"], "show_interface_errors", d["interface"])
        assert entry and entry["read"], dev
        cmds[dev] = entry["read"][0]
    assert len(set(cmds.values())) == 5, cmds
    assert "xe-0/0/0" in cmds["swjun"] and "Ethernet1" in cmds["swarista"] and "port1" in cmds["fw1"] and "1/1/1" in cmds["swaruba"] and "Gi0/2" in cmds["r1"]


def test_fix_commands_follow_each_vendors_change_model(rt):
    prob = kb.problems["err-disabled-port"]
    jun = rt.vendor._problem_view(prob, rt.vendor.devices_for("link-r1-swjun"))["fixes"][0]["commands"]
    forti = rt.vendor._problem_view(prob, rt.vendor.devices_for("link-fw1-swaruba"))["fixes"][0]["commands"]
    jun_cmds = next(c["commands"] for c in jun if c["device"] == "swjun")
    forti_cmds = next(c["commands"] for c in forti if c["device"] == "fw1")
    assert "commit" in jun_cmds and any("disable" in c for c in jun_cmds)          # Junos: candidate config, needs commit
    assert "commit" not in forti_cmds and "set status down" in forti_cmds and forti_cmds[-1] == "end"  # FortiOS: applied on `end`
    assert all(f["needsApproval"] for f in rt.vendor._problem_view(prob, rt.vendor.devices_for("link-r1-swjun"))["fixes"])


def test_config_models_of_the_priority_vendors():
    style = lambda v, o: kb.config_model(v, o)["style"]
    assert style("cisco", "ios") == style("cisco", "ios-xe") == style("arista", "eos") == style("hpe-aruba", "aos-cx") == "running-startup"
    assert style("juniper", "junos") == "candidate-commit" and style("cisco", "ios-xr") == "candidate-commit"
    assert style("fortinet", "fortios") == style("fortinet", "fortiswitchos") == "auto-save"
    assert kb.config_model("juniper", "junos")["save"] == ["commit"] and "commit confirmed 5" in kb.config_model("juniper", "junos")["safe_change"]
    assert "write memory" in kb.config_model("arista", "eos")["save"] and "write memory" in kb.config_model("hpe-aruba", "arubaos-switch")["save"]
    assert kb.config_model("fortinet", "fortios")["save"] == []                     # nothing to save separately
    assert kb.config_model("tp-link", None) is None and kb.config_model("cisco", "no-such-os") is None
    for v in ("cisco", "juniper", "arista", "hpe-aruba", "fortinet"):
        for o in kb.vendor(v)["os_families"]:
            style_en, style_ar = kb.cli_style(v, o["id"])
            assert style_en and style_ar and kb.config_model(v, o["id"]), (v, o["id"])


def test_priority_vendors_have_syslog_patterns_and_command_depth():
    for v in ("cisco", "juniper", "arista", "fortinet", "hpe-aruba"):
        assert kb.vendor(v)["syslog"], v
    for v, os_id in (("cisco", "ios"), ("juniper", "junos"), ("arista", "eos"), ("hpe-aruba", "aos-cx"), ("fortinet", "fortios"), ("fortinet", "fortiswitchos")):
        have = [c for c in kb.capabilities if (kb.commands(v, os_id, c) or {}).get("read")]
        assert len(have) >= 9, (v, os_id, len(have))
    assert kb.commands("fortinet", "fortios", "show_ospf")["read"] == ["get router info ospf neighbor"]


def test_virtual_lab_images_are_recognized_from_their_names():
    assert kb.identify(hint="Juniper vQFX")["vendor"] == "juniper"
    assert kb.identify(hint="Arista vEOS")["vendor"] == "arista"
    assert kb.identify(hint="FortiGate-VM")["os"] == "fortios"
    assert kb.identify(hint="Aruba AOS-CX")["os"] == "aos-cx"
    assert kb.find_vendors("compare Junos, then FortiGate, then Cisco") == ["juniper", "fortinet", "cisco"]  # in the order mentioned


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device,line,vendor,link",
    [
        ("r1", "%LINK-3-UPDOWN: Interface GigabitEthernet0/2, changed state to down", "cisco", "link-r1-fw1"),
        ("swjun", "mib2d[1234]: SNMP_TRAP_LINK_DOWN: ifIndex 501, ifAdminStatus up(1), ifOperStatus down(2), ifName xe-0/0/0", "juniper", "link-r1-swjun"),
        ("swarista", "%LINEPROTO-5-UPDOWN: Line protocol on Interface Ethernet1, changed state to down", "arista", "link-r1-swarista"),
        ("fw1", 'date=2026-09-29 time=10:02:11 devname="FGT-LAB" logid="0100020007" type="event" subtype="system" level="warning" logdesc="Interface status changed" status="DOWN" interface="port2"', "fortinet", "link-fw1-swaruba"),
        ("swaruba", "I 09/29/26 10:02:11 00077 ports: port 1/1/1 is now off-line", "hpe-aruba", "link-fw1-swaruba"),
    ],
)
async def test_each_vendors_link_down_line_lands_on_the_right_link(rt, device, line, vendor, link):
    sink = Sink()
    out = await rt.logs.ingest([line], device, sink)
    r = out["results"][0]
    assert r["parsed"] and r["vendor"] == vendor and r["state"] == "down" and r["link"] == link, r
    assert out["pushed"] == 1 and sink.events[0].source_id == link and sink.events[0].value == 1.0 and sink.events[0].metric == "syslog_link_down"


@pytest.mark.asyncio
async def test_link_up_is_zero_and_config_change_lines_are_recorded_but_never_open_incidents(rt):
    sink = Sink()
    out = await rt.logs.ingest(
        ["I 09/29/26 10:03:11 00076 ports: port 1/1/1 is now on-line", "%SYS-5-CONFIG_I: Configured from console by admin on vty0 (10.0.0.5)"],
        "swaruba", sink, vendor_hint="hpe-aruba",
    )
    up = out["results"][0]
    assert up["state"] == "up" and sink.events[0].value == 0.0
    cfg = rt.logs.normalize("mgd[1234]: UI_COMMIT: User 'admin' requested 'commit' operation (comment: fix uplink)", "swjun")
    assert cfg["event"] == "config_change" and cfg["vendor"] == "juniper" and cfg["details"]["user"] == "admin"
    assert len(sink.events) == 1  # only the link-state line was pushed


@pytest.mark.asyncio
async def test_copilot_answers_the_save_and_cli_style_questions_for_these_vendors(rt):
    ask = lambda q, lang=None: rt.copilot.ask(q, None, lang)
    a = await ask("How do I save the config on Juniper, Arista, Aruba and Fortinet?")
    assert a["intent"] == "vendor_help" and a["source"] == "deterministic"
    text = a["answer"]
    assert "`commit`" in text and "`write memory`" in text and "There is no separate save step." in text and "RootIQ does not run them" in text
    assert a["facts"]["vendors"] == ["juniper", "arista", "hpe-aruba", "fortinet"]  # every vendor asked about (up to four), in the order asked
    ar = await ask("ما الفرق بين حفظ الإعداد في سيسكو وجونيبر وطريقة كتابة الأوامر؟")
    assert ar["intent"] == "vendor_help" and "`commit`" in ar["answer"] and "`copy running-config startup-config`" in ar["answer"]
    assert "أسلوب الأوامر" in ar["answer"] and "لا ينفّذها" in ar["answer"]
    rb = await ask("how do I rollback a bad change on Arista")
    assert "`configure replace flash:<backup>`" in rb["answer"]
    none = await ask("how do I save the config on TP-Link")
    assert "no curated command" in none["answer"].lower()
    act = await ask("please commit the change on Juniper for me now, approve it")
    assert act["intent"] == "action_request"  # a request to act is still refused first
