"""Accuracy of every training run in one place, plus a way to measure any saved model.

Used by the notebook cells D1 (writes one history row per measurement), F1 (prints the accuracy of ALL runs from Drive) and
F2 (measures a saved model, e.g. the merged model E1 exported, with the same tests as D1). Pure Python: no GPU, no network,
no keys, except `load_ccna` (Hugging Face `datasets`) and the model callables that F2 passes in.

    reports/history.jsonl    one JSON line per measurement (appended by D1 and F2; never rewritten)
    reports/eval_report.json the newest D1 report (also read here, so runs made before this file existed still show up)
    reports/anomaly_report.json  stage A (Isolation Forest)
"""
from __future__ import annotations

import json
import random
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

HISTORY = "history.jsonl"
RUN_FILE = "rootiq_run.json"      # written next to every adapter C2 saves: which training data it was trained on
MCQ_SYSTEM = "You are a CCNA exam expert. Reply with ONLY the letter(s) of the correct answer(s), for example B or DF."
AR_CHARS = re.compile(r"[؀-ۿ]")
REFUSAL = re.compile(r"(?i)(as an ai|i cannot|i can't help|لا أستطيع|لا يمكنني)")


# ---------------------------------------------------------------- the tests (same rules as notebook cells C0 / D1)
def parse_letters(text: str | None) -> str:
    """'B', 'DF', 'Answer: D', 'A and D' -> sorted unique letters A-G (first line only)."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    tokens = re.findall(r"\b[A-G]{1,6}\b", line.upper())
    multi = [t for t in tokens if len(t) > 1]
    return "".join(sorted(set(multi[0] if multi else "".join(tokens))))


def load_ccna(limit: int | None = None) -> list[dict]:
    """The held-out CCNA questions, in the same order and cut as the notebook (needs the `datasets` package and internet)."""
    from datasets import load_dataset

    items = []
    for split in ("volume1", "volume2"):
        for r in load_dataset("Elfsong/Cisco_CCNA", split=split):
            items.append({"q": r["Question"], "choices": r["Choices"], "answer": "".join(sorted(re.findall(r"[A-G]", r["Answer"].upper())))})
    random.Random(3).shuffle(items)
    return items[:limit] if limit else items


def mcq_accuracy(answer_fn, items: list[dict]) -> dict:
    ok = single_ok = single_n = 0
    for it in items:
        pred = parse_letters(answer_fn([{"role": "system", "content": MCQ_SYSTEM}, {"role": "user", "content": f"{it['q']}\n{it['choices']}"}]))
        hit = pred == it["answer"]
        ok += hit
        if len(it["answer"]) == 1:
            single_n += 1
            single_ok += hit
    return {"n": len(items), "accuracy": round(ok / len(items), 4), "single_answer_accuracy": round(single_ok / max(single_n, 1), 4)}


def grounding_eval(answer_fn, rows: list[dict]) -> dict:
    from app.intelligence.explain import grounded   # the product's own anti-hallucination check (backend must be on sys.path)

    ok = pct = lang_ok = refusals = 0
    for r in rows:
        text = answer_fn(r["messages"][:2]) or ""
        ok += bool(grounded(text, r["facts"]))
        pcts = re.findall(r"\d+%", r["messages"][2]["content"])
        pct += (not pcts) or any(p in text for p in pcts)
        is_ar = len(AR_CHARS.findall(text)) / max(len(text), 1) > 0.2
        lang_ok += (is_ar == (r["lang"] == "ar"))
        refusals += bool(REFUSAL.search(text))
    n = len(rows)
    return {"n": n, "grounded_rate": round(ok / n, 4), "keeps_headline_percent": round(pct / n, 4), "correct_language": round(lang_ok / n, 4), "refusals": refusals}


def cap_per_task(rows: list[dict], n: int, seed: int = 5) -> list[dict]:
    """Stratified cap: at most n rows per task (the same rule as cell B0's per_task)."""
    rnd, by = random.Random(seed), {}
    for x in rows:
        by.setdefault(x["task"], []).append(x)
    out = []
    for t in sorted(by):
        items = by[t][:]
        rnd.shuffle(items)
        out += items[:n]
    return out


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_model(gen, gen_batch, *, root, smoke: bool, kb_eval, label: str, kind: str, base: str | None = None, ccna_items: list[dict] | None = None) -> dict:
    """Measure one model with the same tests as D1 and return a history entry.

    gen(messages, max_new_tokens) -> str          one greedy answer
    gen_batch(list_of_messages, max_new_tokens) -> list[str]     greedy answers for many prompts
    root: the RootIQ_AI folder (data/eval_grounded.jsonl, data/kb_test_seen.jsonl, data/kb_test_unseen.jsonl written by cell B5)
    """
    root = Path(root)
    ccna = ccna_items if ccna_items is not None else load_ccna(40 if smoke else None)
    held = _read_rows(root / "data" / "eval_grounded.jsonl")
    seen = cap_per_task(_read_rows(root / "data" / "kb_test_seen.jsonl"), 4 if smoke else 12, seed=21)
    unseen = cap_per_task(_read_rows(root / "data" / "kb_test_unseen.jsonl"), 4 if smoke else 12, seed=22)
    kb = {name: kb_eval.evaluate_answers(rows, gen_batch([r["messages"][:2] for r in rows], 256)) for name, rows in (("seen", seen), ("unseen", unseen))}
    measured = {
        "ccna": mcq_accuracy(lambda m: gen(m, 8), ccna),
        "grounding": grounding_eval(lambda m: gen(m, 160), held),
        "kb": kb,
    }
    return entry_from(measured, kb_eval=kb_eval, run=label, kind=kind, base=base, smoke=smoke, decision=None)


# ---------------------------------------------------------------- history
def entry_from(measured: dict, *, kb_eval, run: str, kind: str, base: str | None, smoke: bool, decision: str | None, when: str | None = None) -> dict:
    from datetime import datetime, timezone

    return {
        "when": when or datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": run, "kind": kind, "base": base, "smoke": bool(smoke),
        "ccna": measured["ccna"]["accuracy"], "ccna_n": measured["ccna"]["n"], "ccna_single": measured["ccna"].get("single_answer_accuracy"),
        "grounded": measured["grounding"].get("grounded_rate"), "keeps_percent": measured["grounding"].get("keeps_headline_percent"),
        "correct_language": measured["grounding"].get("correct_language"),
        "kb_seen": kb_eval.headline(measured["kb"]["seen"]), "kb_unseen": kb_eval.headline(measured["kb"]["unseen"]),
        "decision": decision,
    }


def entries_from_report(report: dict, kb_eval=None) -> list[dict]:
    """A D1 report holds two measurements: the base model before training and the tuned model after it."""
    if kb_eval is None:
        import kb_eval  # noqa: PLW0621  (training/kb_eval.py, same folder)
    run = report["model_name"] + ("-smoke" if report.get("smoke") else "")
    common = dict(kb_eval=kb_eval, run=run, base=report.get("base"), smoke=report.get("smoke", False), when=report.get("measured_at"))
    out = [entry_from(report["before"], kind="base", decision=None, **common), entry_from(report["after"], kind="tuned", decision=report.get("decision"), **common)]
    teacher = report.get("groq_teacher_ccna")        # the Groq teacher on (a part of) the same CCNA questions: the reference ceiling
    if teacher:
        out.append({"when": report.get("measured_at"), "run": run, "kind": "teacher", "base": None, "smoke": bool(report.get("smoke")),
                    "ccna": teacher["accuracy"], "ccna_n": teacher["n"], "ccna_single": teacher.get("single_answer_accuracy"),
                    "grounded": None, "keeps_percent": None, "correct_language": None, "kb_seen": {}, "kb_unseen": {}, "decision": None})
    return out


def _key(e: dict) -> tuple:
    return (e.get("when"), e.get("run"), e.get("kind"))


def record(reports_dir, entries: list[dict]) -> int:
    """Append entries to reports/history.jsonl, skipping any already there. Returns how many were added."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    have = {_key(e) for e in load_history(reports_dir, include_latest=False)}
    new = [e for e in entries if _key(e) not in have]
    if new:
        with (reports_dir / HISTORY).open("a", encoding="utf-8") as f:
            for e in new:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(new)


def load_history(reports_dir, include_latest: bool = True) -> list[dict]:
    reports_dir = Path(reports_dir)
    entries = _read_rows(reports_dir / HISTORY) if (reports_dir / HISTORY).exists() else []
    latest = reports_dir / "eval_report.json"
    if include_latest and latest.exists():          # runs made before history.jsonl existed still show up
        have = {_key(e) for e in entries}
        entries += [e for e in entries_from_report(json.loads(latest.read_text(encoding="utf-8"))) if _key(e) not in have]
    order = {"base": 0, "tuned": 1, "merged": 2, "teacher": 3}     # within one run: untrained, trained, exported, then the Groq reference
    return sorted(entries, key=lambda e: (e.get("when") or "", e.get("run") or "", order.get(e.get("kind"), 9)))


# ---------------------------------------------------------------- keep the adapter of the previous run (cell C2)
def archive_previous_adapter(adapter, data_tag: str) -> Path | None:
    """C2 saves every run to the same folder (models/<run>-lora). Before it does, move an adapter trained on OTHER data to `<folder>-before-<date>` next to it, so a new
    run never destroys the old one (measure both with F3 / F4 on the same new tests to see what the new data changed). Returns the new folder, or None when there was
    nothing to keep: no adapter yet, or the same data (the same run being finished again)."""
    adapter = Path(adapter)
    weights = adapter / "adapter_model.safetensors"
    if not weights.exists():
        return None
    try:
        if json.loads((adapter / RUN_FILE).read_text(encoding="utf-8")).get("data_tag") == data_tag:
            return None
    except (OSError, ValueError):
        pass                                                        # an adapter saved before this file existed: other data, keep it
    stamp = datetime.fromtimestamp(weights.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%d-%H%M")
    dest, n = adapter.with_name(f"{adapter.name}-before-{stamp}"), 2
    while dest.exists():
        dest, n = adapter.with_name(f"{adapter.name}-before-{stamp}-{n}"), n + 1
    shutil.move(str(adapter), str(dest))
    return dest


def stamp_adapter(adapter, data_tag: str, **extra) -> None:
    """Record next to the saved adapter which training data it came from (read by `archive_previous_adapter` in the next run)."""
    Path(adapter).mkdir(parents=True, exist_ok=True)
    (Path(adapter) / RUN_FILE).write_text(json.dumps({"data_tag": data_tag, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- the report you read
def _f(x) -> str:
    if x is None:
        return "-"
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def _pct(x) -> str:
    """A 0..1 rate as a score out of 100 with one decimal (0.933 -> '93.3'); None -> '-'."""
    if x is None:
        return "-"
    return f"{float(x) * 100:.1f}"


def headline_pct(h: dict) -> dict:
    """kb_eval.headline() with every rate as a score out of 100 ('67.0'); the unsafe-command count stays a plain count."""
    return {k: (v if k == "unsafe_command_count" else _pct(v)) for k, v in h.items()}


COLUMNS = (("run", 24), ("when (UTC)", 16), ("model", 7), ("CCNA /100", 14), ("ground", 6), ("ident", 5), ("syslog", 6), ("cmd", 5), ("diag", 5),
           ("config", 6), ("refuse", 6), ("invent", 6), ("unsafe", 6), ("decision", 12))


def table(entries: list[dict]) -> str:
    def row(e):
        s, u = e.get("kb_seen") or {}, e.get("kb_unseen") or {}
        return [e["run"], (e.get("when") or "")[:16].replace("T", " "), e["kind"], f"{_pct(e.get('ccna'))} (n={e.get('ccna_n')})", _pct(e.get("grounded")),
                _pct(s.get("identify_exact")), _pct(s.get("syslog_exact")), _pct(s.get("command_lookup")), _pct(s.get("problem_diagnose")),
                _pct(s.get("config_model")), _pct(s.get("refusal")), _pct(u.get("invented_command_rate")),
                "-" if not s else _f((s.get("unsafe_command_count") or 0) + (u.get("unsafe_command_count") or 0)),
                e.get("decision") or "-"]

    head = "  ".join(name.ljust(w) for name, w in COLUMNS)
    lines = [head, "-" * len(head)]
    last_run = None
    for e in entries:
        cells = row(e)
        if e["run"] == last_run and e["kind"] != "base":       # same run: do not repeat its name and time
            cells[0] = cells[1] = ""
        last_run = e["run"]
        lines.append("  ".join(str(c).ljust(w) for c, (_, w) in zip(cells, COLUMNS)))
    return "\n".join(lines)


def anomaly_text(reports_dir) -> str:
    path = Path(reports_dir) / "anomaly_report.json"
    if not path.exists():
        return "Stage A (anomaly model): no report yet (run cells A1 and A2)."
    meta = json.loads(path.read_text(encoding="utf-8"))
    m = meta["metrics"]
    lines = [f"Stage A, Isolation Forest ({meta.get('data_source', '?')}, trained {meta.get('trained_at', '?')[:16].replace('T', ' ')}): "
             f"AUC {_pct(m.get('auc'))}/100, false alarms {_pct(m.get('fpr_iforest@0.6'))}% (static thresholds {_pct(m.get('fpr_static'))}%)"]
    for sc, v in m.get("scenarios", {}).items():
        lines.append(f"  {sc:18s} detects {_pct(v.get('tpr_iforest@0.6'))}% of fault windows (static thresholds {_pct(v.get('tpr_static'))}%)")
    return "\n".join(lines)


def report_text(reports_dir) -> str:
    entries = load_history(reports_dir)
    if not entries:
        return "No evaluation yet: run cells C1 to D1 (or F2) first."
    smoke_only = all(e.get("smoke") for e in entries)
    notes = [
        "Every score is out of 100 (93.3 = 93.3 of 100 answers right); unsafe is a plain count and must be 0.",
        "ground = answers whose numbers are all in the facts; ident/syslog/cmd/diag/config/refuse = vendor-knowledge accuracy on test_seen;",
        "invent = share of commands not in the knowledge base (test_unseen, lower is better); unsafe = change commands that are not approved fixes (must be 0).",
        "'base' rows are the untrained model, 'tuned' rows are after training, 'merged' rows are a saved model measured later (F2),",
        "'teacher' rows are the Groq teacher on the same kind of CCNA questions (a reference ceiling; n is its own sample size).",
    ]
    if smoke_only:
        notes.append("Every row so far is a SMOKE run (tiny data, 20 steps): it proves the pipeline works, not that the model is good.")
    return "Vendor knowledge, CCNA and grounding, every run:\n\n" + table(entries) + "\n\n" + "\n".join(notes) + "\n\n" + anomaly_text(reports_dir)


# ---------------------------------------------------------------- why a run fails (cell F3, and cell D1 after every evaluation)
def collect_errors(rows: list[dict], answers: list[str], kb_eval, per_task_limit: int = 8) -> dict:
    """The vendor-knowledge rows the score did not pass: the question, what was expected, what the model said, and why (fields, invented or unsafe commands)."""
    assert len(rows) == len(answers), "one answer per row"
    kb = kb_eval.get_kb()
    known = kb_eval._Known(kb)
    by_task: dict = {}
    unsafe: list = []
    failures: dict = {}
    for row, ans in zip(rows, answers):
        s = kb_eval.score_row(row, ans, kb, known)
        task = row["task"]
        st = by_task.setdefault(task, {"n": 0, "failed": 0})
        st["n"] += 1
        item = {"task": task, "vendor": row.get("vendor"), "lang": row.get("lang"), "question": row["messages"][1]["content"][:400],
                "expected": row["messages"][2]["content"][:400], "answer": (ans or "")[:600]}
        if s.get("fields") and not s.get("ok"):
            gold = row["meta"]["gold"]
            got = kb_eval.extract_json(ans) or {}
            item["field_diff"] = {f: {"expected": gold.get(f), "got": got.get(f)} for f, good in s["fields"].items() if not good}
        if s.get("invented"):
            item["invented"] = s["invented"]
        if s.get("unsafe"):
            item["unsafe"] = s["unsafe"]
            unsafe.append(item)
        if not s["ok"]:
            st["failed"] += 1
            bucket = failures.setdefault(task, [])
            if len(bucket) < per_task_limit:
                bucket.append(item)
    return {"n": len(rows), "by_task": by_task, "unsafe": unsafe, "failures": failures}


def errors_text(errors: dict, max_items: int = 4) -> str:
    """A readable list of the mistakes: worst tasks first, every unsafe command in full, field-by-field differences for identify / syslog."""
    out: list[str] = []
    for split, e in errors.items():
        out.append(f"=== {split}: {e['n']} rows ===")
        for task, st in sorted(e["by_task"].items(), key=lambda kv: (-kv[1]["failed"] / max(kv[1]["n"], 1), kv[0])):
            out.append(f"  {task:22s} failed {st['failed']} of {st['n']}")
        if e["unsafe"]:
            out.append("  -- UNSAFE: change commands that are not approved fixes (must be 0) --")
            for it in e["unsafe"][:max_items * 2]:
                out.append(f"  [{it['task']} | {it['vendor']}] {it['unsafe']}\n      question: {it['question'][:200]!r}\n      answer:   {it['answer'][:300]!r}")
        for task, items in e["failures"].items():
            out.append(f"  -- {task}: first mistakes --")
            for it in items[:max_items]:
                out.append(f"  [{it['vendor']} | {it['lang']}] {it['question'][:140]!r}")
                if it.get("field_diff"):
                    out.append("      fields: " + "; ".join(f"{f}: expected {d['expected']!r}, got {d['got']!r}" for f, d in it["field_diff"].items()))
                else:
                    out.append(f"      expected: {it['expected'][:160]!r}\n      answer:   {it['answer'][:160]!r}")
                if it.get("invented"):
                    out.append(f"      commands not in the knowledge base: {it['invented'][:5]}")
        out.append("")
    return "\n".join(out)


def save_errors(reports_dir, name: str, errors: dict) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"errors_{name}.json"
    path.write_text(json.dumps(errors, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# ---------------------------------------------------------------- reload a saved adapter (cells F3 and F4; needs a GPU)
def load_adapter_model(adapter, *, in_colab: bool = True):
    """Reload a saved LoRA adapter on its 4-bit base model, the model D1 measured. Returns (model, tokenizer)."""
    import importlib.metadata as md
    import subprocess
    import sys

    import torch
    from packaging.version import Version
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    adapter = Path(adapter)
    assert adapter.exists(), f"no adapter at {adapter}: check the name with the DRIVE tab (models/)"
    try:   # peft refuses a torchao older than 0.16 (Colab ships 0.10); this notebook does not use it
        tao = Version(md.version("torchao"))
    except md.PackageNotFoundError:
        tao = None
    if tao is not None and tao < Version("0.16.0"):
        if not in_colab:
            raise RuntimeError(f"torchao {tao} is older than peft accepts: run `pip uninstall torchao` in this environment, then try again.")
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=True)
    from peft import PeftModel

    base_id = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))["base_model_name_or_path"]
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16      # the same choice as cell C1
    tk = AutoTokenizer.from_pretrained(str(adapter))
    if tk.pad_token is None:
        tk.pad_token = tk.eos_token
    tk.padding_side = "left"
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    base = AutoModelForCausalLM.from_pretrained(base_id, quantization_config=bnb, device_map="auto")
    return PeftModel.from_pretrained(base, str(adapter)).eval(), tk


def answer_batch(model, tk, conversations: list, max_new_tokens: int = 256, batch_size: int = 8) -> list[str]:
    """Greedy answers for many chat prompts at once (left padding), as in cell C1."""
    import torch

    outs: list[str] = []
    with torch.no_grad():
        for i in range(0, len(conversations), batch_size):
            texts = [tk.apply_chat_template(c, tokenize=False, add_generation_prompt=True) for c in conversations[i:i + batch_size]]
            enc = tk(texts, return_tensors="pt", padding=True).to(model.device)
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tk.pad_token_id)
            outs += [tk.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for g in gen]
    return outs
