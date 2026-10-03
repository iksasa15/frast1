"""training/model_eval.py: the accuracy history, the all-runs table (notebook cell F1) and the saved-model test (cell F2)."""
import json
import sys
from pathlib import Path

TRAINING = Path(__file__).resolve().parents[2] / "training"
sys.path.insert(0, str(TRAINING))

import kb_eval  # noqa: E402
import model_eval as me  # noqa: E402


def _rows(split):
    return [json.loads(l) for l in (TRAINING / "data" / "generated" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _measured(ccna=0.5, grounded=1.0, answer_fn=None):
    """A D1-shaped measurement built from the real scorer, so the KB part has the real keys."""
    seen, unseen = me.cap_per_task(_rows("test_seen"), 4, 21), me.cap_per_task(_rows("test_unseen"), 4, 22)   # every task is present
    gold = {r["messages"][1]["content"]: r["messages"][2]["content"] for r in seen + unseen}
    fn = answer_fn or (lambda msgs: gold[msgs[1]["content"]])
    return {"ccna": {"n": 40, "accuracy": ccna, "single_answer_accuracy": ccna},
            "grounding": {"n": 12, "grounded_rate": grounded, "keeps_headline_percent": 1.0, "correct_language": 1.0, "refusals": 0},
            "kb": {"seen": kb_eval.evaluate(seen, fn), "unseen": kb_eval.evaluate(unseen, fn)}}


def _report(when="2026-09-29T07:40:00+00:00", smoke=True, decision="DO NOT SHIP", after_ccna=0.6, teacher=True):
    r = {"base": "Qwen/Qwen3-4B-Instruct-2507", "model_name": "rootiq-network-v1", "measured_at": when, "smoke": smoke,
         "before": _measured(0.45, 0.9, lambda msgs: "I am not sure."), "after": _measured(after_ccna, 1.0), "decision": decision}
    if teacher:
        r["groq_teacher_ccna"] = {"n": 15, "accuracy": 0.9333, "single_answer_accuracy": 0.9}
    return r


def test_parse_letters_and_mcq_accuracy():
    assert [me.parse_letters(t) for t in ("B", "DF", "Answer: D", "A and D", "", None, "no idea")] == ["B", "DF", "D", "AD", "", "", ""]
    items = [{"q": "q1", "choices": "c", "answer": "B"}, {"q": "q2", "choices": "c", "answer": "AD"}]
    res = me.mcq_accuracy(lambda msgs: "B" if "q1" in msgs[1]["content"] else "A and D", items)
    assert res == {"n": 2, "accuracy": 1.0, "single_answer_accuracy": 1.0}
    assert me.mcq_accuracy(lambda msgs: "C", items)["accuracy"] == 0.0


def test_the_module_scores_like_the_notebook_cell_c0():
    """model_eval repeats the notebook's C0 helpers: the two must never drift apart."""
    import types

    nb = json.loads((TRAINING / "RootIQ_Training.ipynb").read_text(encoding="utf-8"))
    c0 = next("".join(c["source"]) for c in nb["cells"] if "".join(c["source"]).startswith("#@title C0)"))
    fake = types.ModuleType("datasets")
    fake.load_dataset = lambda name, split: [{"Question": f"q{i}", "Choices": "c", "Answer": "B"} for i in range(4)]
    old = sys.modules.get("datasets")
    sys.modules["datasets"] = fake
    try:
        import random
        import re

        from app.intelligence.explain import grounded

        ns = {"random": random, "re": re, "SMOKE": True, "grounded": grounded, "AR_CHARS": me.AR_CHARS, "REFUSAL": me.REFUSAL,
              "teacher": lambda *a, **k: "B"}
        exec(compile(c0, "C0", "exec"), ns)
    finally:
        if old is None:
            sys.modules.pop("datasets", None)
        else:
            sys.modules["datasets"] = old
    assert ns["MCQ_SYSTEM"] == me.MCQ_SYSTEM
    for text in ("B", "DF", "Answer: D", "A and D", "", "the answer is c", "AB\nmore"):
        assert ns["parse_letters"](text) == me.parse_letters(text), text
    items = [{"q": "q", "choices": "c", "answer": a} for a in ("B", "AD", "C")]
    for fn in (lambda m: "B", lambda m: "A and D", lambda m: "x"):
        assert ns["mcq_accuracy"](fn, items) == me.mcq_accuracy(fn, items)
    rows = [{"lang": "en", "facts": {"conf": 82, "n": 2}, "messages": [{"content": "s"}, {"content": "u"}, {"content": "Confidence 82%"}]}]
    for fn in (lambda m: "Confidence 82% with 2 signals", lambda m: "I cannot help", lambda m: "invented 999%"):
        assert ns["grounding_eval"](fn, rows) == me.grounding_eval(fn, rows)


def test_cap_per_task_matches_the_notebooks_per_task():
    nb = json.loads((TRAINING / "RootIQ_Training.ipynb").read_text(encoding="utf-8"))
    b0 = next("".join(c["source"]) for c in nb["cells"] if "".join(c["source"]).startswith("#@title B0)"))
    start = b0.index("def per_task")
    end = b0.index("if SMOKE:")
    ns = {"random": __import__("random")}
    exec(b0[start:end], ns)
    rows = _rows("test_seen")
    for n, seed in ((4, 21), (12, 22), (3, 5)):
        assert me.cap_per_task(rows, n, seed) == ns["per_task"](rows, n, seed)


def test_a_d1_report_becomes_base_tuned_and_teacher_rows_and_is_recorded_once(tmp_path):
    rep = _report()
    entries = me.entries_from_report(rep, kb_eval)
    assert [e["kind"] for e in entries] == ["base", "tuned", "teacher"] and {e["run"] for e in entries} == {"rootiq-network-v1-smoke"}
    base, tuned, teacher = entries
    assert (base["ccna"], tuned["ccna"], teacher["ccna"], teacher["ccna_n"]) == (0.45, 0.6, 0.9333, 15)
    assert tuned["decision"] == "DO NOT SHIP" and base["decision"] is None and teacher["kb_seen"] == {}
    assert tuned["kb_seen"]["identify_exact"] == 1.0 and base["kb_seen"]["identify_exact"] == 0.0
    assert me.record(tmp_path, entries) == 3 and me.record(tmp_path, entries) == 0           # never duplicated
    assert len((tmp_path / me.HISTORY).read_text(encoding="utf-8").splitlines()) == 3


def test_all_runs_table_lists_every_run_in_time_order_and_includes_the_latest_report(tmp_path):
    old = _report(when="2026-09-29T07:40:00+00:00", after_ccna=0.6)
    new = _report(when="2026-09-30T09:00:00+00:00", smoke=False, decision="SHIP", after_ccna=0.7, teacher=False)
    me.record(tmp_path, me.entries_from_report(old, kb_eval))
    (tmp_path / "eval_report.json").write_text(json.dumps(new), encoding="utf-8")        # a run made before history.jsonl existed
    merged = {**me.entries_from_report(new, kb_eval)[1], "kind": "merged", "run": "rootiq-network-v1", "when": "2026-09-30T10:00:00+00:00"}
    me.record(tmp_path, [merged])
    hist = me.load_history(tmp_path)
    assert [(e["run"], e["kind"]) for e in hist] == [("rootiq-network-v1-smoke", "base"), ("rootiq-network-v1-smoke", "tuned"), ("rootiq-network-v1-smoke", "teacher"),
                                                     ("rootiq-network-v1", "base"), ("rootiq-network-v1", "tuned"), ("rootiq-network-v1", "merged")]
    text = me.report_text(tmp_path)
    assert "45.0 (n=40)" in text and "93.3 (n=15)" in text and "SHIP" in text and "merged" in text and "teacher" in text
    assert "out of 100" in text and "0.45" not in text          # every score is shown out of 100, never as a 0..1 decimal
    assert "SMOKE run" not in text                       # one of the runs is a full run, so the smoke warning is not shown
    only_smoke = tmp_path / "s"
    me.record(only_smoke, me.entries_from_report(old, kb_eval))
    assert "SMOKE run" in me.report_text(only_smoke)


def test_report_text_without_any_run_and_with_the_anomaly_model(tmp_path):
    assert "No evaluation yet" in me.report_text(tmp_path)
    meta = {"trained_at": "2026-09-29T07:00:00+00:00", "data_source": "RootIQ simulator", "metrics": {
        "auc": 0.97, "fpr_iforest@0.6": 0.01, "fpr_static": 0.02,
        "scenarios": {"link-congestion": {"tpr_iforest@0.6": 0.8, "tpr_static": 0.7}}}}
    (tmp_path / "anomaly_report.json").write_text(json.dumps(meta), encoding="utf-8")
    me.record(tmp_path, me.entries_from_report(_report(), kb_eval))
    text = me.report_text(tmp_path)
    assert "AUC 97.0/100" in text and "link-congestion" in text and "static thresholds 2.0%" in text and "detects 80.0%" in text


def test_evaluate_model_measures_a_model_from_the_files_on_drive(tmp_path):
    """Cell F2 hands two callables to evaluate_model; here they are a perfect and a clueless model."""
    data = tmp_path / "data"
    data.mkdir()
    seen, unseen = _rows("test_seen"), _rows("test_unseen")
    (data / "kb_test_seen.jsonl").write_text("\n".join(json.dumps(r) for r in seen), encoding="utf-8")
    (data / "kb_test_unseen.jsonl").write_text("\n".join(json.dumps(r) for r in unseen), encoding="utf-8")
    fact_rows = [{"task": "explain", "lang": "en", "facts": {"conf": 82, "n": 2}, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                                                                                              {"role": "assistant", "content": "Confidence 82% with 2 signals"}]}]
    (data / "eval_grounded.jsonl").write_text("\n".join(json.dumps(r) for r in fact_rows), encoding="utf-8")
    ccna = [{"q": "q1", "choices": "c", "answer": "B"}, {"q": "q2", "choices": "c", "answer": "C"}]
    kb_gold = {}
    for r in me.cap_per_task(seen, 4, 21) + me.cap_per_task(unseen, 4, 22):
        kb_gold[r["messages"][1]["content"]] = r["messages"][2]["content"]

    def perfect_gen(messages, n):
        if messages[0]["content"] == me.MCQ_SYSTEM:
            return "B" if "q1" in messages[1]["content"] else "C"
        return "Confidence 82% with 2 signals"

    entry = me.evaluate_model(perfect_gen, lambda convs, n: [kb_gold[c[1]["content"]] for c in convs], root=tmp_path, smoke=True, kb_eval=kb_eval,
                              label="rootiq-network-v1-smoke", kind="merged", base="b", ccna_items=ccna)
    assert (entry["kind"], entry["run"], entry["smoke"], entry["ccna"], entry["ccna_n"], entry["grounded"]) == ("merged", "rootiq-network-v1-smoke", True, 1.0, 2, 1.0)
    assert entry["kb_seen"]["identify_exact"] == 1.0 and entry["kb_seen"]["unsafe_command_count"] == 0
    clueless = me.evaluate_model(lambda m, n: "I am not sure.", lambda convs, n: ["I am not sure."] * len(convs), root=tmp_path, smoke=True, kb_eval=kb_eval,
                                 label="x", kind="base", ccna_items=ccna)
    # an answer without any number is trivially "grounded"; the headline-percentage check is what exposes a clueless model
    assert clueless["ccna"] == 0.0 and clueless["kb_seen"]["identify_exact"] == 0.0 and clueless["keeps_percent"] == 0.0


def test_notebook_stage_f_cells_exist_and_f1_prints_the_table(tmp_path, capsys):
    nb = json.loads((TRAINING / "RootIQ_Training.ipynb").read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"]]
    titles = [c.split("\n")[0] for c in cells if c.startswith("#@title")]
    assert [t.split(")")[0].replace("#@title ", "") for t in titles][-5:] == ["E1", "F1", "F2", "F3", "F4"]
    for c in cells:
        if c.startswith("#@title"):
            compile(c, "cell", "exec")
    d1 = next(c for c in cells if c.startswith("#@title D1)"))
    assert "rq_eval.record(" in d1 and "rq_eval.collect_errors(" in d1 and "rq_eval.save_errors(" in d1
    assert "rq_eval.headline_pct(" in d1                                     # the before -> after lines are out of 100 too
    assert me.headline_pct({"identify_exact": 0.6667, "syslog_exact": None, "unsafe_command_count": 1, "invented_command_rate": 0.18}) == {
        "identify_exact": "66.7", "syslog_exact": "-", "unsafe_command_count": 1, "invented_command_rate": "18.0"}
    assert "kb_evaluate.answers[name] = answers" in next(c for c in cells if c.startswith("#@title C1)"))
    f3 = next(c for c in cells if c.startswith("#@title F3)"))
    assert "rq_eval.collect_errors(" in f3 and "rq_eval.load_adapter_model(" in f3 and "rq_eval.answer_batch(" in f3
    import inspect

    loader = inspect.getsource(me.load_adapter_model)
    assert "PeftModel.from_pretrained" in loader and "torchao" in loader and "BitsAndBytesConfig" in loader       # the guard and the 4-bit base live in one shared helper
    f1 = next(c for c in cells if c.startswith("#@title F1)"))
    me.record(tmp_path / "reports", me.entries_from_report(_report(), kb_eval))
    exec(compile(f1, "F1", "exec"), {"ROOT": tmp_path})
    out = capsys.readouterr().out
    assert "rootiq-network-v1-smoke" in out and "60.0 (n=40)" in out and "teacher" in out and "CCNA /100" in out


def test_c2_keeps_the_adapter_of_a_previous_run_trained_on_other_data(tmp_path):
    """Every run saves to models/<run>-lora: a new run on new data must not destroy the old adapter (it is the baseline for an honest before/after)."""
    adapter = tmp_path / "models" / "rootiq-network-v1-lora"
    assert me.archive_previous_adapter(adapter, "aaaa1111") is None                  # nothing saved yet
    adapter.mkdir(parents=True)
    (adapter / "adapter_model.safetensors").write_bytes(b"old weights")
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    kept = me.archive_previous_adapter(adapter, "bbbb2222")                          # saved before rootiq_run.json existed: other data, kept
    assert kept is not None and kept.name.startswith("rootiq-network-v1-lora-before-") and not adapter.exists()
    assert (kept / "adapter_model.safetensors").read_bytes() == b"old weights" and (kept / "adapter_config.json").exists()

    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"new weights")
    me.stamp_adapter(adapter, "bbbb2222", run="rootiq-network-v1", steps=1134)
    assert json.loads((adapter / me.RUN_FILE).read_text(encoding="utf-8"))["data_tag"] == "bbbb2222"
    assert me.archive_previous_adapter(adapter, "bbbb2222") is None and (adapter / "adapter_model.safetensors").read_bytes() == b"new weights"   # the same run, finished again: overwritten, not duplicated
    kept2 = me.archive_previous_adapter(adapter, "cccc3333")                         # new data again: the second adapter is kept too, under another name
    assert kept2 is not None and kept2 != kept and (kept / "adapter_model.safetensors").exists() and (kept2 / "adapter_model.safetensors").read_bytes() == b"new weights"
    nb = json.loads((TRAINING / "RootIQ_Training.ipynb").read_text(encoding="utf-8"))
    c2 = next("".join(c["source"]) for c in nb["cells"] if "".join(c["source"]).startswith("#@title C2)"))
    assert "rq_eval.archive_previous_adapter(ADAPTER, DATA_TAG)" in c2 and c2.index("archive_previous_adapter") < c2.index("save_pretrained") and "rq_eval.stamp_adapter(" in c2


def test_collect_errors_lists_wrong_fields_invented_and_unsafe_commands(tmp_path):
    """The mistake list that explains a failed rule: which rows, which fields, which commands."""
    rows = me.cap_per_task(_rows("test_seen"), 4, 21)
    gold = [r["messages"][2]["content"] for r in rows]
    perfect = me.collect_errors(rows, gold, kb_eval)
    assert perfect["n"] == len(rows) and not perfect["unsafe"] and not perfect["failures"]
    assert all(st["failed"] == 0 for st in perfect["by_task"].values())

    ident = next(i for i, r in enumerate(rows) if r["task"] == "identify")
    wrong = json.loads(gold[ident])
    wrong["os"] = "not-an-os"
    risky = next(i for i, r in enumerate(rows) if r["task"] == "command_lookup" and r.get("vendor"))
    answers = list(gold)
    answers[ident] = json.dumps(wrong)
    answers[risky] = gold[risky] + " Then run `reload` and `write erase`."
    bad = me.collect_errors(rows, answers, kb_eval)

    item = bad["failures"]["identify"][0]
    assert item["field_diff"]["os"] == {"expected": json.loads(gold[ident])["os"], "got": "not-an-os"} and "vendor" not in item["field_diff"]
    assert bad["by_task"]["identify"]["failed"] == 1
    assert bad["unsafe"] and any("reload" in c for it in bad["unsafe"] for c in it["unsafe"])

    text = me.errors_text({"seen": bad})
    assert "UNSAFE" in text and "identify: first mistakes" in text and "not-an-os" in text and "=== seen:" in text
    path = me.save_errors(tmp_path, "run-x", {"seen": bad})
    assert path.name == "errors_run-x.json" and json.loads(path.read_text(encoding="utf-8"))["seen"]["n"] == len(rows)
