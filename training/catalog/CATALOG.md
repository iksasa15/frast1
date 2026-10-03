# Hugging Face catalog

Verified on **2026-09-29** against the public Hugging Face API (metadata only; nothing is downloaded by this file).
Licences are copied from each repository's card. **"not stated" means the author did not declare one: treat it as all rights reserved.** Regenerate with `python training/catalog/refresh_catalog.py`.


## Datasets


### Optional training data (check the notes)

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`zilalzihar/mikrotik-routeros-qa-dataset`](https://huggingface.co/datasets/zilalzihar/mikrotik-routeros-qa-dataset) | apache-2.0 | train 1,590, validation 82 | **MikroTik RouterOS Q&A.** instruction/input/output/source. Apache-2.0. Good fit for the MikroTik command gap (RootIQ's own KB has 22 RouterOS commands). Check the `source` column and spot-check answers before mixing. |
| [`witfoo/syslog-to-artifact`](https://huggingface.co/datasets/witfoo/syslog-to-artifact) | apache-2.0 | train 155,304 | **Syslog -> structured artifact.** 155k rows of raw syslog to WitFoo artifact JSON (Apache-2.0). Different output schema from RootIQ's normalized event, so use it as a small (<=5%) auxiliary mix to teach log structure, not as the syslog task itself. |

### Evaluation only

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`Elfsong/Cisco_CCNA`](https://huggingface.co/datasets/Elfsong/Cisco_CCNA) | not stated | volume1 187, volume2 156 | **Networking.** 343 CCNA exam questions (volume1 187, volume2 156). Used ONLY to check that fine-tuning did not make the model forget general networking. Licence not stated. |

### Not used yet (future work)

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`NetConfEval/NetConfEval`](https://huggingface.co/datasets/NetConfEval/NetConfEval) | mit | Configuration Generation: train 5; Formal Specification Translation: train 1,665; Routing Code Generation: train 8; Translation Conflict Detection: train 1,680 | **Network configuration benchmarks.** MIT. Config generation / policy translation benchmarks, not vendor troubleshooting. Relevant for a future `config` agent. |
| [`rachid-abdou/NetConfEval`](https://huggingface.co/datasets/rachid-abdou/NetConfEval) | cc-by-4.0 | - | **NetConfEval, augmented.** CC-BY-4.0 (attribution required). Same purpose as NetConfEval. |
| [`shaunak1234/snmp-diagnostic-agent-traces`](https://huggingface.co/datasets/shaunak1234/snmp-diagnostic-agent-traces) | apache-2.0 | train 1,459, validation 197, test 480 | **SNMP diagnostic agent traces.** Apache-2.0. 2,136 tool-calling trajectories (train 1,459 / val 197 / test 480). A different format (messages + tools): useful later to teach tool-use for a diagnostic agent. |
| [`AliMaatouk/TelecomTS`](https://huggingface.co/datasets/AliMaatouk/TelecomTS) | mit | train 32,000 | **Telecom KPI time series.** MIT. 5G telecom KPIs with Q&A. Not switch-related; only relevant for time-series anomaly explanations. |

### Reference / retrieval only

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`vivek-dodia/mikrotik-docs`](https://huggingface.co/datasets/vivek-dodia/mikrotik-docs) | mit | train 285 | **MikroTik documentation sections.** Tagged MIT, but the content is the vendor's own documentation: use for retrieval/reading, not as training text. |

### Excluded (licence or provenance unclear)

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`ndavidson/cisco_inam_chatml`](https://huggingface.co/datasets/ndavidson/cisco_inam_chatml) | not stated | train 33,170 | **Cisco Q&A (33k).** Built from Cisco product documentation and no licence is stated. Fine for private experiments, do not ship a model trained on it. |
| [`jack0503/junos_cli_qa`](https://huggingface.co/datasets/jack0503/junos_cli_qa) | not stated | train 29,839 | **Junos CLI Q&A (29.8k).** No licence stated; derived from Juniper documentation. Excluded until the licence is clarified. |
| [`jack0503/junos_cli_command`](https://huggingface.co/datasets/jack0503/junos_cli_command) | not stated | train 11,530 | **Junos CLI command reference (11.5k).** No licence stated; derived from Juniper documentation. Excluded until the licence is clarified. |
| [`Coldyuja/junos-user-manual-markdown-raw`](https://huggingface.co/datasets/Coldyuja/junos-user-manual-markdown-raw) | not stated | by_book: train 48; by_chapter: train 1,684 | **Junos manuals (markdown).** Raw vendor manual text, no licence stated. |
| [`bolu61/loghub_2`](https://huggingface.co/datasets/bolu61/loghub_2) | not stated | train 38,288,761, test 74,273 | **LogHub 2 (unofficial mirror).** Unofficial upload, single `text` column, no licence. Use the official LogHub release from logpai if generic log data is ever needed. |

## Models


### Use for training

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | apache-2.0 | - | **Default base model.** Apache-2.0. Fits a Colab T4 in 4-bit. Multilingual, follows the JSON output formats well. |

### Optional training data (check the notes)

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`humain-ai/ALLaM-7B-Instruct-preview`](https://huggingface.co/humain-ai/ALLaM-7B-Instruct-preview) | apache-2.0 | - | **Arabic/Saudi base model.** Apache-2.0. Better Arabic; needs an L4/A100. Same fine-tuning code (BASE_KEY = 'allam'). |

### Not used yet (future work)

| Repository | Licence | Size | What it is / how RootIQ uses it |
|---|---|---|---|
| [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) | mit | - | **Embedding model (small).** MIT. Candidate to replace TF-IDF in the Knowledge agent; needs the prefixes 'query: ' / 'passage: '. |
| [`intfloat/multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base) | mit | - | **Embedding model (base).** MIT. |
| [`intfloat/multilingual-e5-large`](https://huggingface.co/intfloat/multilingual-e5-large) | mit | - | **Embedding model (large).** MIT. |
| [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3) | mit | - | **Embedding model (multilingual, long input).** MIT. Strongest of the shortlist for Arabic + English retrieval; largest. |
| [`BAAI/bge-reranker-v2-m3`](https://huggingface.co/BAAI/bge-reranker-v2-m3) | apache-2.0 | - | **Re-ranker.** Apache-2.0. Re-order the top-k retrieved passages before the Copilot uses them. |
