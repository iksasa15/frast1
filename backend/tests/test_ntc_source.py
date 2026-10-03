"""training/ntc_source.py: real device output from ntc-templates as licence-gated, capped, train-only rows."""
import json
import sys
from pathlib import Path

import pytest

TRAINING = Path(__file__).resolve().parents[2] / "training"
sys.path.insert(0, str(TRAINING))

import ntc_source as ns  # noqa: E402
from app.knowledge import get_kb  # noqa: E402

APACHE = "Copyright 2015 Someone\n\nLicensed under the Apache License, Version 2.0 (the \"License\");\nyou may not use this file except in compliance with the License.\n"


def _sample(base: Path, platform: str, folder: str, name: str, raw: str, parsed: list | None):
    d = base / "tests" / platform / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.raw").write_text(raw, encoding="utf-8")
    if parsed is not None:
        import yaml

        (d / f"{name}.yml").write_text(yaml.safe_dump({"parsed_sample": parsed}), encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    return _make_repo(tmp_path)


def _make_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "LICENSE").write_text(APACHE, encoding="utf-8")
    _sample(tmp_path, "juniper_junos", "show_version", "a", "Hostname: lab\nModel: mx240\nJunos: 13.3R1.4", [{"hostname": "lab", "model": "mx240", "junos_version": "13.3R1.4"}])
    _sample(tmp_path, "juniper_junos", "show_version", "b", "Hostname: lab2\nModel: ex4300\nJunos: 19.4R1.10", [{"hostname": "lab2", "model": "ex4300", "junos_version": "19.4R1.10"}])
    _sample(tmp_path, "fortinet", "get_system_status", "a", "Version: FortiGate-VM64 v7.4.3\nHostname: fw1", [{"version": "v7.4.3", "hostname": "fw1"}])
    _sample(tmp_path, "mikrotik_routeros", "ip_route_print", "a", "Flags: X - disabled\n 0 A S 0.0.0.0/0 10.0.0.1", [{"dst": "0.0.0.0/0", "gateway": "10.0.0.1"}])
    # everything below must be skipped
    _sample(tmp_path, "juniper_junos", "clear_bgp_neighbor", "a", "cleared", [{"x": "1"}])                 # not a read-only command
    _sample(tmp_path, "fortinet", "execute_reboot", "a", "rebooting", [{"x": "1"}])                         # does not start with a read verb
    _sample(tmp_path, "cisco_ios", "show_running-config", "a", "snmp-server community public RO\nhostname r1", [{"hostname": "r1"}])   # secret
    _sample(tmp_path, "cisco_ios", "show_version", "big", "x" * (ns.MAX_RAW + 1), [{"a": "b"}])              # too long
    _sample(tmp_path, "cisco_ios", "show_clock", "noyml", "12:00:00 UTC", None)                              # no parsed sample
    _sample(tmp_path, "some_unknown_os", "show_version", "a", "Version 1", [{"version": "1"}])              # platform not in the knowledge base
    return tmp_path


def test_every_platform_maps_to_a_vendor_and_os_of_the_knowledge_base():
    kb = get_kb()
    for platform, (vendor, os_id, name) in ns.PLATFORMS.items():
        assert kb.vendor(vendor) and os_id in [o["id"] for o in kb.vendor(vendor)["os_families"]], platform
        assert name


def test_only_read_only_commands_are_accepted():
    ok = ["show version", "show ip route", "display version", "get system status", "diagnose sys top", "ip route print", "system resource print"]
    no = ["clear bgp neighbor", "execute reboot", "reload", "show run | write mem", "configure terminal", "debug ip packet", "copy running-config startup-config"]
    assert all(ns.is_read_only(c) for c in ok) and not any(ns.is_read_only(c) for c in no)
    assert ns.command_from_folder("show_ip_route") == "show ip route"


def test_convert_builds_train_only_rows_with_the_parsers_fields(repo):
    rows = ns.convert(repo, per_platform=10, per_command=1)
    assert sorted(r["meta"]["source"] for r in rows) == ["ntc-templates/fortinet", "ntc-templates/juniper_junos", "ntc-templates/mikrotik_routeros"]
    for r in rows:
        assert r["task"] == ns.TASK == "ext_cli_parse" and r["split"] == "train" and r["group"].startswith("ext/ntc-templates/")
        assert [m["role"] for m in r["messages"]] == ["system", "user", "assistant"]
        assert r["meta"]["gold"]["vendor"] == r["vendor"] and r["meta"]["gold"]["command"] in r["messages"][1]["content"]
        assert json.loads(r["messages"][2]["content"])                               # the answer is valid JSON, the parser's records
    junos = next(r for r in rows if r["vendor"] == "juniper")
    assert "Vendor: Juniper Junos. Command: `show version`." in junos["messages"][1]["content"] and "Hostname: lab" in junos["messages"][1]["content"]
    assert json.loads(junos["messages"][2]["content"])[0]["hostname"] in ("lab", "lab2")
    assert junos["meta"]["gold"]["os"] == "junos"


def test_caps_are_respected_and_the_result_is_deterministic(repo):
    assert len([r for r in ns.convert(repo, per_platform=10, per_command=1) if r["vendor"] == "juniper"]) == 1     # per command
    assert len([r for r in ns.convert(repo, per_platform=10, per_command=5) if r["vendor"] == "juniper"]) == 2
    assert len(ns.convert(repo, per_platform=1, per_command=5)) == 3                                                # one per platform
    assert [r["id"] for r in ns.convert(repo)] == [r["id"] for r in ns.convert(repo)]


def test_a_repository_without_the_apache_licence_is_never_used(repo):
    (repo / "LICENSE").write_text("All rights reserved.", encoding="utf-8")
    with pytest.raises(PermissionError, match="Apache-2.0"):
        ns.convert(repo)
    (repo / "LICENSE").unlink()
    assert not ns.licence_ok(repo)
    with pytest.raises(PermissionError):
        ns.convert(repo)
