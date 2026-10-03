"""training/collect_data.py: every outside source into one folder of yours, licence-gated, tiered, with a manifest."""
import json
import sys
from pathlib import Path

import pytest

TRAINING = Path(__file__).resolve().parents[2] / "training"
sys.path.insert(0, str(TRAINING))

import collect_data as cd  # noqa: E402
import external  # noqa: E402

RAW = {
    "zilalzihar/mikrotik-routeros-qa-dataset": [{"instruction": f"How do I set up item {i}?", "input": "", "output": f"Use /ip firewall rule {i}"} for i in range(200)],
    "witfoo/syslog-to-artifact": [{"instruction": "Convert this syslog message.", "input_text": f"<134>host app[{i}]: link {i} down", "output_text": json.dumps({"n": i})} for i in range(200)],
    "Elfsong/Cisco_CCNA": [{"Question": "What is OSPF?", "Choices": "A. a protocol", "Answer": "A", "_config": None, "_split": "volume1"}],
}


class Fakes:
    """Stand-ins for the network: they count their calls."""

    def __init__(self, fail=()):
        self.hf_calls, self.ntc_calls, self.fail = [], 0, set(fail)

    def hf(self, name, limit):
        self.hf_calls.append((name, limit))
        if name in self.fail:
            raise RuntimeError("network down")
        return (RAW.get(name) or [{"text": f"record of {name}", "n": i} for i in range(50)])[:limit]

    def ntc(self, dest, per_platform):
        self.ntc_calls += 1
        rows = [external._row("ext_cli_parse", "juniper", f"Vendor: Juniper Junos. Command: `show version {i}`.", '[{"model":"mx"}]', "ntc-templates/juniper_junos") for i in range(3)]
        return rows[:per_platform], "abc1234"

    def collect(self, out, **kw):
        return cd.collect(out, hf_fetch=self.hf, ntc_fetch=self.ntc, revision_of=lambda n: "rev-" + n[:3], **kw)


def test_train_tier_writes_chat_rows_with_a_manifest_and_readme(tmp_path):
    fk = Fakes()
    m = fk.collect(tmp_path, tiers=("train",), smoke=True)
    root = tmp_path / "smoke"
    assert sorted(p.name for p in (root / "train").glob("*.jsonl")) == ["git_networktocode_ntc-templates.jsonl", "hf_witfoo_syslog-to-artifact.jsonl", "hf_zilalzihar_mikrotik-routeros-qa-dataset.jsonl"]
    assert (root / "manifest.json").exists() and (root / "README.md").exists()
    e = m["sources"]["hf:zilalzihar/mikrotik-routeros-qa-dataset"]
    assert e["tier"] == "train" and e["licence"] == "apache-2.0" and e["rows"] == 20 and len(e["sha256"]) == 64 and e["revision"] == "rev-zil"
    assert m["sources"]["git:networktocode/ntc-templates"]["revision"] == "abc1234"
    rows = cd.load_train_rows(tmp_path, smoke=True)
    assert {r["task"] for r in rows} == {"ext_mikrotik_qa", "ext_syslog_artifact", "ext_cli_parse"} and all(r["split"] == "train" for r in rows)
    assert "ext_cli_parse" in json.dumps(rows) and "| hf:witfoo/syslog-to-artifact |" in (root / "README.md").read_text(encoding="utf-8")
    assert "hf:witfoo/syslog-to-artifact" in cd.summary(m)


def test_smoke_and_full_never_share_files_and_limits_differ(tmp_path):
    fk = Fakes()
    fk.collect(tmp_path, tiers=("train",), smoke=True)
    full = fk.collect(tmp_path, tiers=("train",), smoke=False)
    assert (tmp_path / "smoke" / "train").is_dir() and (tmp_path / "full" / "train").is_dir()
    assert full["sources"]["hf:zilalzihar/mikrotik-routeros-qa-dataset"]["rows"] == 200          # the fake has 200 rows and the full limit is 1500
    assert len(cd.load_train_rows(tmp_path, smoke=True)) < len(cd.load_train_rows(tmp_path, smoke=False))


def test_existing_files_are_reused_until_refresh(tmp_path):
    fk = Fakes()
    fk.collect(tmp_path, tiers=("train",), smoke=True)
    first = len(fk.hf_calls), fk.ntc_calls
    again = fk.collect(tmp_path, tiers=("train",), smoke=True)
    assert (len(fk.hf_calls), fk.ntc_calls) == first and all(e.get("reused") for e in again["sources"].values())
    fk.collect(tmp_path, tiers=("train",), smoke=True, refresh=True)
    assert len(fk.hf_calls) > first[0] and fk.ntc_calls > first[1]


def test_eval_and_reference_tiers_keep_raw_records_and_are_never_training_rows(tmp_path):
    fk = Fakes()
    m = fk.collect(tmp_path, tiers=("train", "eval", "reference"), smoke=False)
    ccna = tmp_path / "full" / "eval" / "hf_Elfsong_Cisco_CCNA.jsonl"
    assert json.loads(ccna.read_text(encoding="utf-8").splitlines()[0])["Question"] == "What is OSPF?"
    assert m["sources"]["hf:NetConfEval/NetConfEval"]["tier"] == "reference" and (tmp_path / "full" / "reference").is_dir()
    assert not any(r["task"] not in ("ext_mikrotik_qa", "ext_syslog_artifact", "ext_cli_parse") for r in cd.load_train_rows(tmp_path))


def test_restricted_tier_needs_an_explicit_acceptance_and_stays_apart(tmp_path):
    fk = Fakes()
    with pytest.raises(PermissionError, match="licence"):
        fk.collect(tmp_path, tiers=("restricted",))
    m = fk.collect(tmp_path, tiers=("restricted",), accept_licence_risk=True, smoke=True)
    assert (tmp_path / "smoke" / "restricted").is_dir() and all(e["tier"] == "restricted" for e in m["sources"].values())
    assert cd.load_train_rows(tmp_path, smoke=True) == []                          # nothing restricted can reach training
    assert "NO usable licence" in (tmp_path / "smoke" / "README.md").read_text(encoding="utf-8")


def test_a_failing_source_is_recorded_and_does_not_stop_the_others(tmp_path):
    fk = Fakes(fail={"witfoo/syslog-to-artifact"})
    m = fk.collect(tmp_path, tiers=("train",), smoke=True)
    assert "network down" in m["sources"]["hf:witfoo/syslog-to-artifact"]["error"]
    assert m["sources"]["hf:zilalzihar/mikrotik-routeros-qa-dataset"]["rows"] == 20 and "error" not in m["sources"]["git:networktocode/ntc-templates"]


def test_a_train_source_the_catalog_does_not_approve_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(external, "allowed", lambda name: False)
    fk = Fakes()
    m = fk.collect(tmp_path, tiers=("train",), smoke=True, only={"hf:zilalzihar/mikrotik-routeros-qa-dataset"})
    assert "not approved" in m["sources"]["hf:zilalzihar/mikrotik-routeros-qa-dataset"]["error"] and fk.hf_calls == []


def test_the_registry_can_never_train_on_a_restricted_or_evaluation_source():
    ids = [s.id for s in cd.SOURCES]
    assert len(ids) == len(set(ids)) and {s.tier for s in cd.SOURCES} <= set(cd.TIERS)
    for s in cd.SOURCES:
        if s.kind == "hf" and s.tier == "train":
            assert external.allowed(s.name), s.id                                  # approved for training in the catalog
        if s.kind == "hf" and s.tier != "train":
            assert not external.allowed(s.name), s.id                              # so it could never be converted into training rows
    assert any(s.id == "git:networktocode/ntc-templates" and s.tier == "train" for s in cd.SOURCES)


def test_kaggle_only_open_licences_are_downloaded(tmp_path):
    def runner_for(licence):
        calls = []

        def run(cmd, check=True, capture_output=True, text=True):
            calls.append(cmd)
            if cmd[2] == "metadata":
                (Path(cmd[cmd.index("-p") + 1]) / "dataset-metadata.json").write_text(json.dumps({"licenses": [{"name": licence}]}), encoding="utf-8")
            else:
                (Path(cmd[cmd.index("-p") + 1]) / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        return run, calls

    run, calls = runner_for("CC0-1.0")
    e = cd.collect_kaggle(tmp_path, "someone/network-logs", smoke=True, runner=run)
    assert e["rows"] == 1 and (tmp_path / "smoke" / "reference" / "kaggle_someone_network-logs" / "data.csv").exists() and len(calls) == 2
    run2, calls2 = runner_for("other")
    e2 = cd.collect_kaggle(tmp_path, "someone/else", smoke=True, runner=run2)
    assert "not an open licence" in e2["error"] and len(calls2) == 1               # only the metadata was read, nothing downloaded
    manifest = json.loads((tmp_path / "smoke" / "manifest.json").read_text(encoding="utf-8"))
    assert {"kaggle:someone/network-logs", "kaggle:someone/else"} <= set(manifest["sources"])


def test_notebook_b4_collects_into_the_drive_folder_only_when_switched_on(tmp_path, monkeypatch):
    fk = Fakes()
    monkeypatch.setattr(cd, "hf_records", fk.hf)
    monkeypatch.setattr(cd, "ntc_rows", fk.ntc)
    monkeypatch.setattr(cd, "_hf_revision", lambda n: "rev")
    nb = json.loads((TRAINING / "RootIQ_Training.ipynb").read_text(encoding="utf-8"))
    b4 = next("".join(c["source"]) for c in nb["cells"] if "".join(c["source"]).startswith("#@title B4)"))
    off = {"INCLUDE_EXTERNAL": False, "SMOKE": True, "ROOT": tmp_path / "off"}
    exec(compile(b4, "B4", "exec"), off)
    assert off["external_rows"] == [] and not (tmp_path / "off").exists() and fk.hf_calls == []
    on = {"INCLUDE_EXTERNAL": True, "SMOKE": True, "ROOT": tmp_path / "on"}
    exec(compile(b4, "B4", "exec"), on)
    assert {r["task"] for r in on["external_rows"]} == {"ext_mikrotik_qa", "ext_syslog_artifact", "ext_cli_parse"}
    assert (tmp_path / "on" / "data" / "external" / "smoke" / "manifest.json").exists()
    assert not (tmp_path / "on" / "data" / "external" / "smoke" / "eval").exists()        # a smoke run keeps only the train tier
