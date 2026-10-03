"""Optional public Hugging Face data, converted to the same chat format as the generated KB data.

Only datasets whose catalog entry allows training (`use` = train / train_optional) can be loaded: a licence or provenance
question is decided in training/catalog/refresh_catalog.py, not by whoever runs the notebook. Everything is capped
(rows and characters), de-duplicated and screened for secrets, and external rows go to train/val only, never to the
test sets, so the KB test scores stay comparable between runs.

    rows = load_external("zilalzihar/mikrotik-routeros-qa-dataset", limit=1500)   # needs `datasets` (Colab)
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "catalog" / "hf_catalog.json"
SYSTEM = (
    "You are RootIQ's Network Vendor Advisor. Use only the vendor knowledge you were trained on. "
    "If a vendor, OS or command is not covered, say so instead of guessing. You are read-only: you never approve, "
    "run or change anything; any change command is text for a named human engineer to review and approve. "
    "Answer in the user's language and keep commands and device names in English."
)
MAX_USER, MAX_ANSWER = 1500, 1500
SECRET = re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|community)\s*[=:]\s*\S+|gsk_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{20,}")
# Answers that tell the reader to run something destructive are not what a read-only advisor should learn from.
DESTRUCTIVE = re.compile(r"(?i)(^|\s)(/system reset-configuration|factory[- ]reset|erase startup|format flash|rm -rf|reload in \d+)")


def _row(task: str, vendor: str | None, user: str, answer: str, source: str) -> dict:
    rid = hashlib.sha1(f"{task}|{user}".encode()).hexdigest()[:12]
    return {
        "id": rid, "task": task, "lang": "ar" if re.search(r"[؀-ۿ]", user) else "en", "vendor": vendor,
        "group": f"ext/{source}/{rid}", "split": "train",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user.strip()}, {"role": "assistant", "content": answer.strip()}],
        "meta": {"gold": {}, "must_include": [], "source": source},
    }


def ok_text(user: str, answer: str) -> bool:
    if not user.strip() or not answer.strip() or len(user) > MAX_USER or len(answer) > MAX_ANSWER:
        return False
    return not (SECRET.search(user) or SECRET.search(answer) or DESTRUCTIVE.search(answer))


def from_mikrotik_qa(rec: dict) -> dict | None:
    """zilalzihar/mikrotik-routeros-qa-dataset: instruction / input / output / source."""
    user = (rec.get("instruction") or "").strip()
    if rec.get("input"):
        user += "\n" + str(rec["input"]).strip()
    answer = (rec.get("output") or "").strip()
    return _row("ext_mikrotik_qa", "mikrotik", user, answer, "mikrotik-routeros-qa") if ok_text(user, answer) else None


def from_syslog_artifact(rec: dict) -> dict | None:
    """witfoo/syslog-to-artifact: instruction / input_text (raw syslog) / output_text (structured artifact)."""
    user = ((rec.get("instruction") or "Convert this syslog message into a structured artifact.").strip() + "\n" + str(rec.get("input_text") or "").strip())
    answer = str(rec.get("output_text") or "").strip()
    return _row("ext_syslog_artifact", None, user, answer, "witfoo-syslog-to-artifact") if ok_text(user, answer) else None


CONVERTERS = {
    "zilalzihar/mikrotik-routeros-qa-dataset": (from_mikrotik_qa, ("train", "validation")),
    "witfoo/syslog-to-artifact": (from_syslog_artifact, ("train",)),
}


def allowed(name: str) -> bool:
    """True only if the catalog marks the dataset usable for training."""
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))["datasets"].get(name)
    return bool(cat) and cat["use"] in ("train", "train_optional") and name in CONVERTERS


def convert(name: str, records, limit: int, seed: int = 7) -> list[dict]:
    """Pure function (no network): filter, convert, de-duplicate, shuffle deterministically and cap."""
    if not allowed(name):
        raise PermissionError(f"{name} is not approved for training in training/catalog/hf_catalog.json")
    fn = CONVERTERS[name][0]
    seen, out = set(), []
    for rec in records:
        r = fn(rec)
        if r and r["messages"][1]["content"] not in seen:
            seen.add(r["messages"][1]["content"])
            out.append(r)
    random.Random(seed).shuffle(out)
    return out[:limit]


def load_external(name: str, limit: int = 1500, seed: int = 7) -> list[dict]:
    """Download (via `datasets`) and convert. Streams the big datasets so Colab memory stays small."""
    if not allowed(name):
        raise PermissionError(f"{name} is not approved for training in training/catalog/hf_catalog.json")
    from datasets import load_dataset  # imported here: only Colab has it

    splits = CONVERTERS[name][1]
    records = []
    for sp in splits:
        ds = load_dataset(name, split=sp, streaming=True)
        for i, rec in enumerate(ds):
            records.append(rec)
            if i >= limit * 4:  # enough raw rows to survive the filters
                break
    return convert(name, records, limit, seed)
