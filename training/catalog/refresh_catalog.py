"""Refresh training/catalog/hf_catalog.json and CATALOG.md from the public Hugging Face API.

    python training/catalog/refresh_catalog.py            # needs internet; reads public metadata only, downloads no data files

The *policy* (how RootIQ may use each asset) is written here by hand, on purpose: a licence or a source that is
unclear means "do not ship a model trained on it" until someone with authority decides otherwise.
Use values: train | train_optional | eval_only | reference_only | excluded | future
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent

DATASETS = {
    "Elfsong/Cisco_CCNA": ("eval_only", "Networking", "343 CCNA exam questions (volume1 187, volume2 156). Used ONLY to check that fine-tuning did not make the model forget general networking. Licence not stated."),
    "zilalzihar/mikrotik-routeros-qa-dataset": ("train_optional", "MikroTik RouterOS Q&A", "instruction/input/output/source. Apache-2.0. Good fit for the MikroTik command gap (RootIQ's own KB has 22 RouterOS commands). Check the `source` column and spot-check answers before mixing."),
    "witfoo/syslog-to-artifact": ("train_optional", "Syslog -> structured artifact", "155k rows of raw syslog to WitFoo artifact JSON (Apache-2.0). Different output schema from RootIQ's normalized event, so use it as a small (<=5%) auxiliary mix to teach log structure, not as the syslog task itself."),
    "NetConfEval/NetConfEval": ("future", "Network configuration benchmarks", "MIT. Config generation / policy translation benchmarks, not vendor troubleshooting. Relevant for a future `config` agent."),
    "rachid-abdou/NetConfEval": ("future", "NetConfEval, augmented", "CC-BY-4.0 (attribution required). Same purpose as NetConfEval."),
    "shaunak1234/snmp-diagnostic-agent-traces": ("future", "SNMP diagnostic agent traces", "Apache-2.0. 2,136 tool-calling trajectories (train 1,459 / val 197 / test 480). A different format (messages + tools): useful later to teach tool-use for a diagnostic agent."),
    "AliMaatouk/TelecomTS": ("future", "Telecom KPI time series", "MIT. 5G telecom KPIs with Q&A. Not switch-related; only relevant for time-series anomaly explanations."),
    "ndavidson/cisco_inam_chatml": ("excluded", "Cisco Q&A (33k)", "Built from Cisco product documentation and no licence is stated. Fine for private experiments, do not ship a model trained on it."),
    "vivek-dodia/mikrotik-docs": ("reference_only", "MikroTik documentation sections", "Tagged MIT, but the content is the vendor's own documentation: use for retrieval/reading, not as training text."),
    "jack0503/junos_cli_qa": ("excluded", "Junos CLI Q&A (29.8k)", "No licence stated; derived from Juniper documentation. Excluded until the licence is clarified."),
    "jack0503/junos_cli_command": ("excluded", "Junos CLI command reference (11.5k)", "No licence stated; derived from Juniper documentation. Excluded until the licence is clarified."),
    "Coldyuja/junos-user-manual-markdown-raw": ("excluded", "Junos manuals (markdown)", "Raw vendor manual text, no licence stated."),
    "bolu61/loghub_2": ("excluded", "LogHub 2 (unofficial mirror)", "Unofficial upload, single `text` column, no licence. Use the official LogHub release from logpai if generic log data is ever needed."),
}
MODELS = {
    "Qwen/Qwen3-4B-Instruct-2507": ("train", "Default base model", "Apache-2.0. Fits a Colab T4 in 4-bit. Multilingual, follows the JSON output formats well."),
    "humain-ai/ALLaM-7B-Instruct-preview": ("train_optional", "Arabic/Saudi base model", "Apache-2.0. Better Arabic; needs an L4/A100. Same fine-tuning code (BASE_KEY = 'allam')."),
    "intfloat/multilingual-e5-small": ("future", "Embedding model (small)", "MIT. Candidate to replace TF-IDF in the Knowledge agent; needs the prefixes 'query: ' / 'passage: '."),
    "intfloat/multilingual-e5-base": ("future", "Embedding model (base)", "MIT."),
    "intfloat/multilingual-e5-large": ("future", "Embedding model (large)", "MIT."),
    "BAAI/bge-m3": ("future", "Embedding model (multilingual, long input)", "MIT. Strongest of the shortlist for Arabic + English retrieval; largest."),
    "BAAI/bge-reranker-v2-m3": ("future", "Re-ranker", "Apache-2.0. Re-order the top-k retrieved passages before the Copilot uses them."),
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rootiq-catalog/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(kind, hf_id):
    d = get(f"https://huggingface.co/api/{kind}/{hf_id}")
    card = d.get("cardData") or {}
    lic = card.get("license") or next((t.split(":", 1)[1] for t in d.get("tags", []) if t.startswith("license:")), None)
    row = {"license": lic or "not stated", "downloads": d.get("downloads"), "gated": d.get("gated"), "lastModified": (d.get("lastModified") or "")[:10]}
    if kind == "datasets":
        try:
            info = get("https://datasets-server.huggingface.co/info?dataset=" + urllib.parse.quote(hf_id, safe=""))
            cfgs = {}
            for cfg, meta in (info.get("dataset_info") or {}).items():
                cols = list(meta.get("features") or {})
                cfgs[cfg] = {"columns": cols if len(cols) <= 14 else cols[:6] + [f"... ({len(cols)} columns)"],
                             "rows": {s: v.get("num_examples") for s, v in (meta.get("splits") or {}).items()}}
            row["configs"] = cfgs
        except Exception as e:  # noqa: BLE001
            row["configs_error"] = f"{type(e).__name__}: {e}"
    return row


def main():
    catalog = {"verified_on": date.today().isoformat(), "source": "huggingface.co public API (metadata only)", "datasets": {}, "models": {}}
    for kind, table, key in (("datasets", DATASETS, "datasets"), ("models", MODELS, "models")):
        for hf_id, (use, title, note) in table.items():
            try:
                meta = fetch(kind, hf_id)
            except Exception as e:  # noqa: BLE001
                meta = {"error": f"{type(e).__name__}: {e}"}
            catalog[key][hf_id] = {"use": use, "title": title, "note": note, **meta}
            print(kind, hf_id, meta.get("license", meta.get("error")))
    (HERE / "hf_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "CATALOG.md").write_text(render(catalog), encoding="utf-8")


def render(c) -> str:
    order = ["train", "train_optional", "eval_only", "future", "reference_only", "excluded"]
    label = {"train": "Use for training", "train_optional": "Optional training data (check the notes)", "eval_only": "Evaluation only",
             "future": "Not used yet (future work)", "reference_only": "Reference / retrieval only", "excluded": "Excluded (licence or provenance unclear)"}
    out = [f"# Hugging Face catalog\n\nVerified on **{c['verified_on']}** against the public Hugging Face API (metadata only; nothing is downloaded by this file).\n"
           "Licences are copied from each repository's card. **\"not stated\" means the author did not declare one: treat it as all rights reserved.** "
           "Regenerate with `python training/catalog/refresh_catalog.py`.\n"]
    for section, title in (("datasets", "Datasets"), ("models", "Models")):
        out.append(f"\n## {title}\n")
        for use in order:
            items = [(k, v) for k, v in c[section].items() if v["use"] == use]
            if not items:
                continue
            out.append(f"\n### {label[use]}\n\n| Repository | Licence | Size | What it is / how RootIQ uses it |\n|---|---|---|---|")
            for k, v in items:
                size = ""
                for cfg, m in (v.get("configs") or {}).items():
                    rows = ", ".join(f"{s} {n:,}" for s, n in m["rows"].items() if n is not None)
                    size += (f"{cfg}: " if len(v["configs"]) > 1 else "") + rows + "; "
                size = size.rstrip("; ") or ("gated" if v.get("gated") else "-")
                out.append(f"| [`{k}`](https://huggingface.co/{'datasets/' if section == 'datasets' else ''}{k}) | {v.get('license', '?')} | {size} | **{v['title']}.** {v['note']} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
