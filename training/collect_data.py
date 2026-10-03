"""One command that gathers every outside data source into ONE folder of your own, with a manifest that says what each file is.

    python training/collect_data.py --out <RootIQ_AI>/data/external                      # the sources you may train on (tier: train)
    python training/collect_data.py --out ... --tiers train eval reference               # + the evaluation-only and reading-only sets
    python training/collect_data.py --out ... --kaggle owner/dataset-name                # a Kaggle set, only if its licence is open (needs a Kaggle key)
    python training/collect_data.py --out ... --tiers restricted --accept-licence-risk   # sets WITHOUT a usable licence, for private experiments only

Layout written under `<out>/<mode>/` (mode = `full` or `smoke`, so a smoke run never leaves small files for a full run):

    train/       chat rows (the repo's row format) that the training notebook reads: Q&A, syslog, captured CLI output with its parsed fields
    eval/        raw records used only to measure the model (never trained on)
    reference/   raw records for reading / retrieval (documentation, benchmarks, agent traces)
    restricted/  raw records with NO open licence: private experiments only, never read by the notebook, never to be shipped in a model
    manifest.json, README.md   what every file is: source, licence, rows, sha256, revision

Nothing here weakens the licence rule of training/catalog: a source can be trained on only if `external.allowed()` (the catalog) or
`ntc_source.licence_ok()` (its LICENSE file) says so. Needs `datasets` (and `git`) for the downloads: Colab has them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import external
import ntc_source

MAX_RAW_ROWS = 50_000          # per source, for the raw tiers (eval / reference / restricted)


@dataclass(frozen=True)
class Source:
    id: str                    # "hf:<owner>/<name>" or "git:<owner>/<name>"
    tier: str                  # train | eval | reference | restricted
    licence: str               # as the source states it
    what: str                  # one line: what it is
    types: tuple = field(default_factory=tuple)   # document types: qa, syslog, cli-output, docs, benchmark, agent-traces, exam
    limit: int = 1500          # rows kept (train tier) in a full run
    smoke_limit: int = 20

    @property
    def name(self) -> str:
        return self.id.split(":", 1)[1]

    @property
    def kind(self) -> str:
        return self.id.split(":", 1)[0]


SOURCES: tuple[Source, ...] = (
    # ---- train: licence-clean, converted to chat rows
    Source("hf:zilalzihar/mikrotik-routeros-qa-dataset", "train", "apache-2.0", "MikroTik RouterOS question and answer pairs", ("qa",), 1500),
    Source("hf:witfoo/syslog-to-artifact", "train", "apache-2.0", "raw syslog lines (Cisco, Palo Alto, Linux, ...) with the structured artifact", ("syslog",), 500),
    Source("git:networktocode/ntc-templates", "train", "Apache-2.0", "captured show / display / get output of 13 platforms with the fields a parser extracts", ("cli-output", "parsed-fields"), 120, 8),
    # ---- eval: only to measure
    Source("hf:Elfsong/Cisco_CCNA", "eval", "not stated (evaluation only)", "343 CCNA exam questions, the held-out CCNA test", ("exam",)),
    # ---- reference: read or retrieve, do not train
    Source("hf:NetConfEval/NetConfEval", "reference", "mit", "network configuration benchmarks (policy translation, routing code)", ("benchmark",)),
    Source("hf:rachid-abdou/NetConfEval", "reference", "cc-by-4.0", "NetConfEval task 1, augmented (attribution required)", ("benchmark",)),
    Source("hf:shaunak1234/snmp-diagnostic-agent-traces", "reference", "apache-2.0", "2,136 tool-calling trajectories that diagnose SNMP failures", ("agent-traces",)),
    Source("hf:vivek-dodia/mikrotik-docs", "reference", "mit (vendor documentation)", "MikroTik documentation sections, for retrieval", ("docs",)),
    # ---- restricted: no usable licence; private experiments only (opt-in, never read by the notebook)
    Source("hf:ndavidson/cisco_inam_chatml", "restricted", "not stated (derived from Cisco documentation)", "33k Cisco Q&A", ("qa",)),
    Source("hf:jack0503/junos_cli_qa", "restricted", "not stated (derived from Juniper documentation)", "Junos CLI Q&A", ("qa",)),
    Source("hf:jack0503/junos_cli_command", "restricted", "not stated (derived from Juniper documentation)", "Junos CLI command reference", ("docs",)),
    Source("hf:Coldyuja/junos-user-manual-markdown-raw", "restricted", "not stated (vendor manual text)", "Junos manuals in markdown", ("docs",)),
    Source("hf:Rzkoohi/CCNA_medium", "restricted", "apache-2.0 tag, no source stated", "56k CCNA Q&A of unknown origin (overlaps the CCNA test)", ("qa",)),
)
TIERS = ("train", "eval", "reference", "restricted")
KAGGLE_OK = {"cc0", "cc010", "ccby40", "odcby10", "apache20", "mit"}     # normalised licence names Kaggle metadata may carry


def _safe(source_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", source_id.replace(":", "_"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------- default downloaders (Colab: `datasets` and `git` are there)
def hf_records(name: str, limit: int) -> list[dict]:
    """Every config and split of a Hugging Face dataset (streamed, at most `limit` rows in total per split), each record tagged with its config and split."""
    from datasets import get_dataset_config_names, get_dataset_split_names, load_dataset

    try:
        configs = get_dataset_config_names(name) or [None]
    except Exception:  # noqa: BLE001  (a dataset without a loading script may not list configs)
        configs = [None]
    out: list[dict] = []
    for cfg in configs:
        try:
            splits = get_dataset_split_names(name, cfg) if cfg else get_dataset_split_names(name)
        except Exception:  # noqa: BLE001
            splits = ["train"]
        for sp in splits:
            ds = load_dataset(name, cfg, split=sp, streaming=True) if cfg else load_dataset(name, split=sp, streaming=True)
            for i, rec in enumerate(ds):
                if i >= limit:
                    break
                out.append({**dict(rec), "_config": cfg, "_split": sp})
    return out


def ntc_rows(dest: Path, per_platform: int) -> tuple[list[dict], str]:
    commit = ntc_source.clone(dest)
    return ntc_source.convert(dest, per_platform=per_platform), commit


def _hf_revision(name: str) -> str | None:
    try:
        from huggingface_hub import HfApi

        return HfApi().dataset_info(name).sha
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- collecting
def collect(out_dir, tiers=("train",), smoke: bool = False, refresh: bool = False, accept_licence_risk: bool = False,
            hf_fetch=None, ntc_fetch=None, revision_of=None, only: set[str] | None = None) -> dict:
    """Gather the sources of the chosen tiers into <out_dir>/<mode>/<tier>/ and write manifest.json + README.md. One source failing never stops the others.
    hf_fetch(name, limit) -> raw records, ntc_fetch(dest, per_platform) -> (rows, commit), revision_of(name) -> revision: the real downloaders unless a test passes fakes."""
    hf_fetch, ntc_fetch, revision_of = hf_fetch or hf_records, ntc_fetch or ntc_rows, revision_of or _hf_revision
    out_dir = Path(out_dir)
    mode = "smoke" if smoke else "full"
    root = out_dir / mode
    if "restricted" in tiers and not accept_licence_risk:
        raise PermissionError("tier 'restricted' holds data without a usable licence: pass accept_licence_risk=True (--accept-licence-risk) to fetch it for private experiments")
    unknown = [t for t in tiers if t not in TIERS]
    if unknown:
        raise ValueError(f"unknown tier(s): {unknown}; choose from {TIERS}")
    manifest_path = root / "manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("sources", {}) if manifest_path.exists() else {}
    entries: dict = {}
    for src in SOURCES:
        if src.tier not in tiers or (only and src.id not in only):
            continue
        target = root / src.tier / f"{_safe(src.id)}.jsonl"
        entry = {"tier": src.tier, "licence": src.licence, "what": src.what, "types": list(src.types), "file": str(target.relative_to(root)).replace("\\", "/")}
        if target.exists() and not refresh and src.id in previous:
            entries[src.id] = {**previous[src.id], "reused": True}
            continue
        try:
            if src.tier == "train":
                if src.kind == "hf":
                    if not external.allowed(src.name):
                        raise PermissionError(f"{src.name} is not approved for training in training/catalog/hf_catalog.json")
                    limit = src.smoke_limit if smoke else src.limit
                    rows = external.convert(src.name, hf_fetch(src.name, limit * 4), limit)
                    entry["revision"] = revision_of(src.name)
                else:                                   # git:networktocode/ntc-templates
                    rows, commit = ntc_fetch(root / "_cache" / "ntc-templates", src.smoke_limit if smoke else src.limit)
                    entry["revision"] = commit
                entry["rows"] = _write_jsonl(target, rows)
            else:                                        # raw dump: the records exactly as the source has them
                cap = src.smoke_limit if smoke else MAX_RAW_ROWS
                entry["rows"] = _write_jsonl(target, hf_fetch(src.name, cap))
                entry["revision"] = revision_of(src.name)
            entry["sha256"] = _sha256(target)
        except Exception as e:  # noqa: BLE001
            entry["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        entries[src.id] = entry
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": mode, "tiers": list(tiers), "sources": {**previous, **entries}}
    root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "README.md").write_text(readme_text(manifest), encoding="utf-8")
    return manifest


def collect_kaggle(out_dir, slug: str, smoke: bool = False, runner=subprocess.run) -> dict:
    """Download one Kaggle dataset into reference/, only if its licence (from the Kaggle metadata) is an open one. Needs `pip install kaggle` and KAGGLE_USERNAME / KAGGLE_KEY."""
    root = Path(out_dir) / ("smoke" if smoke else "full")
    with tempfile.TemporaryDirectory() as tmp:
        runner(["kaggle", "datasets", "metadata", slug, "-p", tmp], check=True, capture_output=True, text=True)
        meta = json.loads((Path(tmp) / "dataset-metadata.json").read_text(encoding="utf-8"))
    names = [str(lic.get("name", "")) for lic in meta.get("licenses", [])] or ["unknown"]
    ok = all(re.sub(r"[^a-z0-9]", "", n.lower()) in KAGGLE_OK for n in names)
    entry = {"tier": "reference", "licence": ", ".join(names), "what": f"Kaggle dataset {slug}", "types": ["kaggle"], "file": f"reference/kaggle_{_safe(slug)}/"}
    if not ok:
        entry["error"] = f"PermissionError: licence {names} is not an open licence (allowed: {sorted(KAGGLE_OK)}); nothing downloaded"
    else:
        dest = root / "reference" / f"kaggle_{_safe(slug)}"
        dest.mkdir(parents=True, exist_ok=True)
        runner(["kaggle", "datasets", "download", "-d", slug, "-p", str(dest), "--unzip"], check=True, capture_output=True, text=True)
        entry["rows"] = sum(1 for _ in dest.rglob("*") if _.is_file())
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"mode": "smoke" if smoke else "full", "sources": {}}
    manifest["sources"][f"kaggle:{slug}"] = entry
    root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "README.md").write_text(readme_text(manifest), encoding="utf-8")
    return entry


def load_train_rows(out_dir, smoke: bool = False) -> list[dict]:
    """The chat rows of the train tier (all files), de-duplicated by id, train split only. This is what the training notebook mixes in."""
    folder = Path(out_dir) / ("smoke" if smoke else "full") / "train"
    seen, rows = set(), []
    for f in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("split") == "train" and r.get("id") not in seen:
                seen.add(r.get("id"))
                rows.append(r)
    return rows


def summary(manifest: dict) -> str:
    lines = [f"collected into <out>/{manifest.get('mode')}/  ({manifest.get('generated_at', '')[:19]} UTC)", ""]
    lines.append(f"{'source':52s} {'tier':10s} {'rows':>7s}  licence / result")
    for sid, e in manifest["sources"].items():
        result = e.get("error") or e.get("licence", "")
        rows = e.get("rows")
        lines.append(f"{sid:52s} {e['tier']:10s} {('' if rows is None else rows)!s:>7}  {result}{'  (already there)' if e.get('reused') else ''}")
    return "\n".join(lines)


def readme_text(manifest: dict) -> str:
    by_tier = {t: [(sid, e) for sid, e in manifest["sources"].items() if e["tier"] == t] for t in TIERS}
    meaning = {
        "train": "chat rows the training notebook mixes into the training data (licence checked)",
        "eval": "only to measure the model, never trained on",
        "reference": "for reading and retrieval, not for training",
        "restricted": "NO usable licence: private experiments only; never read by the notebook; never ship a model trained on these",
    }
    out = ["# External data collected by training/collect_data.py", "", f"Mode: {manifest.get('mode')}. Written {manifest.get('generated_at', '')}.", ""]
    for tier in TIERS:
        if not by_tier[tier]:
            continue
        out += [f"## {tier}/ : {meaning[tier]}", "", "| source | what | licence | rows | file |", "|---|---|---|---|---|"]
        for sid, e in by_tier[tier]:
            out.append(f"| {sid} | {e['what']} | {e['licence']} | {e.get('rows', e.get('error', ''))} | {e['file']} |")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="the folder to fill, for example <RootIQ_AI>/data/external")
    ap.add_argument("--tiers", nargs="+", default=["train"], choices=TIERS)
    ap.add_argument("--smoke", action="store_true", help="tiny copy (about 20 rows per source) to check the pipeline")
    ap.add_argument("--refresh", action="store_true", help="download again even if the file is already there")
    ap.add_argument("--kaggle", action="append", default=[], metavar="OWNER/NAME", help="a Kaggle dataset (needs a Kaggle key); kept only if its licence is open")
    ap.add_argument("--accept-licence-risk", action="store_true", help="required for the 'restricted' tier")
    args = ap.parse_args(argv)
    manifest = collect(args.out, tuple(args.tiers), smoke=args.smoke, refresh=args.refresh, accept_licence_risk=args.accept_licence_risk)
    for slug in args.kaggle:
        collect_kaggle(args.out, slug, smoke=args.smoke)
        manifest = json.loads((Path(args.out) / ("smoke" if args.smoke else "full") / "manifest.json").read_text(encoding="utf-8"))
    print(summary(manifest))
    return 1 if any("error" in e for e in manifest["sources"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
