"""The vendor knowledge base: data integrity, identification, versions, commands, syslog and problems."""
import json
import shutil

import pytest

from app.knowledge import KnowledgeBase, get_kb
from app.knowledge.loader import DATA_DIR

kb = get_kb()


def test_kb_validates_with_no_errors():
    assert kb.validate() == []


def test_kb_scale_and_honest_coverage_levels():
    st = kb.stats()
    assert st["vendors"] >= 40 and st["problems"] >= 25 and st["osFamilies"] >= 55
    assert st["coverage"]["full"] >= 5 and st["coverage"]["profile-only"] >= 20  # most vendors are profile-only, and say so
    for v in kb.vendors.values():
        assert v["coverage"] in ("full", "partial", "profile-only") and v["confidence"] in ("high", "medium", "low")
        assert v["pen_verification"], f"{v['id']}: PEN verification note missing"
        if v["coverage"] == "profile-only":
            assert not v["commands"], f"{v['id']}: profile-only vendors must not carry command tables"


def test_enterprise_numbers_are_unique_and_real_for_the_big_vendors():
    pens = {}
    for vid, v in kb.vendors.items():
        for e in v["enterprise_oids"]:
            assert e["pen"] not in pens, f"PEN {e['pen']} used by {pens[e['pen']]} and {vid}"
            pens[e["pen"]] = vid
    # IANA private enterprise numbers (verified against the IANA registry when the KB was written)
    assert (pens[9], pens[2636], pens[30065], pens[2011], pens[14988]) == ("cisco", "juniper", "arista", "huawei", "mikrotik")


@pytest.mark.parametrize(
    "sys_descr,vendor,os_id,version",
    [
        ("Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a, RELEASE SOFTWARE (fc3)", "cisco", "ios-xe", "17.9.4a"),
        ("Juniper Networks, Inc. ex4300-48t Ethernet Switch, kernel JUNOS 21.4R3-S5.4, Build date: 2023-06-01 10:00:00 UTC Copyright (c) 1996-2023 Juniper Networks, Inc.", "juniper", "junos", "21.4R3-S5.4"),
    ],
)
def test_identify_from_sysdescr(sys_descr, vendor, os_id, version):
    r = kb.identify(sys_descr)
    assert (r["vendor"], r["os"], r["version"]) == (vendor, os_id, version)
    assert r["confidence"] in ("high", "medium") and r["netmiko"]


def test_every_sysdescr_example_in_the_data_identifies_its_own_vendor_and_os():
    checked = 0
    for vid, v in kb.vendors.items():
        for o in v["os_families"]:
            for ex in o.get("examples", {}).get("sysdescr", []):
                r = kb.identify(ex)
                assert (r["vendor"], r["os"]) == (vid, o["id"]), f"{vid}/{o['id']} -> {r['vendor']}/{r['os']}"
                checked += 1
    assert checked >= 15


def test_identify_from_sysobjectid_alone_and_with_hint():
    r = kb.identify(sys_object_id="1.3.6.1.4.1.2636.1.1.1.2.31")
    assert r["vendor"] == "juniper" and r["os"] is None and r["confidence"] == "medium"
    assert kb.identify(sys_object_id=".1.3.6.1.4.1.9.1.2504")["vendor"] == "cisco"
    assert kb.identify(hint="Cisco vIOS-L2")["os"] == "ios"
    r = kb.identify(hint="Ubuntu 24.04")
    assert r["vendor"] == "linux"


def test_identify_unknown_is_reported_not_guessed():
    r = kb.identify("Totally Unknown Appliance v1")
    assert r["vendor"] is None and r["os"] is None and r["confidence"] == "none"
    assert kb.identify()["vendor"] is None


def test_hpe_aruba_has_two_enterprise_numbers_and_separate_os_families():
    hpe = kb.vendor("hpe-aruba")
    assert {e["pen"] for e in hpe["enterprise_oids"]} >= {14823, 11}
    assert {"aos-cx", "arubaos-switch"} <= {o["id"] for o in hpe["os_families"]}


def test_version_normalization_and_ordering():
    # IOS-XE 'show version' zero-pads, sysDescr does not
    assert kb.normalize_version("ios-xe", "17.09.04a") == "17.9.4a"
    assert kb.normalize_version("junos", "21.4R3-S5.4") == "21.4R3-S5.4"
    assert kb.version_tuple("4.30.5M") < kb.version_tuple("4.32.1F")
    assert kb.version_tuple("17.3.8") < kb.version_tuple("17.9.4")
    assert kb.version_tuple(None) == ()


def test_commands_resolve_per_os_with_interface_and_never_leak_placeholders():
    xe = kb.commands("cisco", "ios-xe", "show_interface_errors", "Gi1/0/1")
    assert xe["read"] and all("<if>" not in c for c in xe["read"]) and any("Gi1/0/1" in c for c in xe["read"])
    nx = kb.commands("cisco", "nx-os", "show_interface_errors", "Ethernet1/1")
    assert nx["read"] != xe["read"] or any("Ethernet1/1" in c for c in nx["read"])
    junos = kb.commands("juniper", "junos", "show_interface_errors", "ge-0/0/1")
    assert junos["read"] and any("ge-0/0/1" in c for c in junos["read"])
    assert kb.commands("no-such-vendor", None, "show_version") is None
    assert kb.commands("cisco", "ios-xe", "no-such-capability") is None


def test_unsafe_interface_names_are_rejected():
    for bad in ("Gi0/0; reload", "Gi0/0 | include", "$(reboot)", "a" * 60):
        with pytest.raises(ValueError):
            kb.commands("cisco", "ios-xe", "show_interface_detail", bad)


def test_all_read_commands_are_read_only_and_change_commands_are_confined():
    reads = changes = 0
    for v in kb.vendors.values():
        for table in v["commands"].values():
            for cap, entry in table.items():
                for c in entry.get("read", []):
                    assert kb.is_read_only(c), f"{v['id']}/{cap}: {c}"
                    reads += 1
                for c in entry.get("change", []):
                    assert cap in ("clear_counters", "bounce_interface")
                    changes += 1
    assert reads > 150 and changes > 0


@pytest.mark.parametrize("cmd", ["shutdown", "reload", "show version; reload", "write memory", "configure terminal", "rm -rf /", "clear counters", "", "  "])
def test_is_read_only_rejects_changes(cmd):
    assert not kb.is_read_only(cmd)


@pytest.mark.parametrize("cmd", ["show ip interface brief", "display interface brief", "show interfaces Gi0/0", "systemctl status named", "free -m"])
def test_is_read_only_accepts_inspection(cmd):
    assert kb.is_read_only(cmd)


def test_fix_commands_always_need_approval_and_only_for_change_capabilities():
    for pid in kb.problems:
        for f in kb.fix_commands(pid, "cisco", "ios-xe", "Gi0/1"):
            assert f["needsApproval"] is True
            for c in f["commands"]:
                assert c["capability"] in ("clear_counters", "bounce_interface")


def test_syslog_examples_parse_to_their_own_vendor_and_pattern():
    total = 0
    for vid, v in kb.vendors.items():
        for pat in v["syslog"]:
            r = kb.parse_syslog(pat["example"], vid)
            assert r and r["vendor"] == vid and r["pattern"] == pat["id"], f"{vid}/{pat['id']}"
            total += 1
    assert total >= 20


@pytest.mark.parametrize(
    "line,vendor,interface,state",
    [
        ("%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down", "cisco", "GigabitEthernet0/1", "down"),
        ("Sep 29 10:00:00 crs326 ether1 link down", "mikrotik", "ether1", "down"),
        ("rpd[1234]: SNMP_TRAP_LINK_DOWN: ifIndex 501, ifAdminStatus up(1), ifOperStatus down(2), ifName ge-0/0/1", "juniper", "ge-0/0/1", "down"),
    ],
)
def test_syslog_link_state_lines_normalize(line, vendor, interface, state):
    r = kb.parse_syslog(line)
    assert r["vendor"] == vendor and r["event"] == "interface_state"
    assert r["interface"] == interface and r["state"] == state


def test_shared_syslog_formats_report_every_vendor_that_matches():
    line = "%LINEPROTO-5-UPDOWN: Line protocol on Interface Ethernet1, changed state to down"
    assert kb.parse_syslog(line)["vendor"] == "cisco"  # most common owner wins by default
    assert "arista" in kb.parse_syslog(line)["alsoMatches"]
    assert kb.parse_syslog(line, "arista")["vendor"] == "arista"  # an explicit hint wins
    assert kb.parse_syslog("just some chatter that matches nothing") is None


def test_problem_matching_uses_metrics_events_and_kind():
    top = lambda **kw: [p["id"] for p in kb.problems_for(**kw)]
    assert top(metrics=["link_utilization", "link_latency_ms", "link_packet_loss"], kind="link")[0] == "link-congestion"
    assert top(metrics=["dns_success_rate", "dns_latency_ms"], kind="svc-dns") == ["dns-failure"]
    assert top(metrics=["cpu_percent", "http_latency_ms"], kind="server")[0] == "server-resource-pressure"
    # a server incident must never be told it has a layer-2 loop
    assert "layer2-loop-broadcast-storm" not in top(metrics=["cpu_percent"], kind="server")
    assert "interface-flapping" in top(metrics=["syslog_link_down"], kind="link")
    assert kb.problems_for(metrics=["nothing_known"], kind="link") == []


@pytest.mark.parametrize(
    "text,problem",
    [
        ("the port has crc errors", "crc-errors"),
        ("ospf neighbor stuck in exstart", "ospf-neighbor-down"),
        ("المنفذ يتذبذب flapping", "interface-flapping"),
        ("hello there", None),
    ],
)
def test_find_problem_english_and_arabic(text, problem):
    assert kb.find_problem(text) == problem


def test_every_problem_is_bilingual_and_only_verifies_with_real_rootiq_metrics():
    from app.intelligence.thresholds import THRESHOLDS

    for p in kb.problems.values():
        assert p["title_ar"].strip() and p["summary_ar"].strip()
        assert all(f["needs_approval"] for f in p["fixes"])
        assert all(v["metric"] in THRESHOLDS for v in p["verify"])  # event-only problems may have no metric criteria
    assert sum(1 for p in kb.problems.values() if p["verify"]) >= 8


# ---------------------------------------------------------------- the validator itself must catch bad data
def _copy_kb(tmp_path):
    dst = tmp_path / "data"
    shutil.copytree(DATA_DIR, dst)
    return dst


def test_validator_rejects_a_change_command_hidden_in_a_read_list(tmp_path):
    dst = _copy_kb(tmp_path)
    f = dst / "vendors" / "cisco.json"
    v = json.loads(f.read_text(encoding="utf-8"))
    v["commands"]["default"]["show_version"]["read"].append("reload")
    f.write_text(json.dumps(v), encoding="utf-8")
    errs = KnowledgeBase(dst).validate()
    assert any("read command not read-only" in e for e in errs)


def test_validator_rejects_duplicate_pen_bad_regex_and_unapproved_fix(tmp_path):
    dst = _copy_kb(tmp_path)
    f = dst / "vendors" / "juniper.json"
    v = json.loads(f.read_text(encoding="utf-8"))
    v["enterprise_oids"].append({"pen": 9, "org": "duplicate of Cisco"})
    v["os_families"][0]["sysdescr_regex"].append("(unclosed")
    f.write_text(json.dumps(v), encoding="utf-8")
    pf = dst / "problems.json"
    d = json.loads(pf.read_text(encoding="utf-8"))
    d["problems"][0]["fixes"][0]["needs_approval"] = False
    pf.write_text(json.dumps(d), encoding="utf-8")
    errs = " | ".join(KnowledgeBase(dst).validate())
    assert "PEN 9" in errs and "bad regex" in errs and "must require approval" in errs
