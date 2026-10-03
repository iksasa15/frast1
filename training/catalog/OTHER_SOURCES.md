# Sources that are not in the Hugging Face catalog, and what the 2026-09-29 search found

`CATALOG.md` is generated from the Hugging Face API. This file is written by hand: one extra source that is used, and the result of a search of Hugging Face and Kaggle so nobody repeats it.

## Collected in one place: `training/collect_data.py`

Every source below, and the Hugging Face sets of `CATALOG.md`, can be gathered by one command into one folder with a manifest (source, licence, rows, sha256, revision): `python training/collect_data.py --out <RootIQ_AI>/data/external --tiers train eval reference` (the notebook's cell B4 does it when `INCLUDE_EXTERNAL = True`). Tiers: **train** (chat rows, licence approved: `zilalzihar/mikrotik-routeros-qa-dataset`, `witfoo/syslog-to-artifact`, ntc-templates), **eval** (`Elfsong/Cisco_CCNA`), **reference** (`NetConfEval/NetConfEval`, `rachid-abdou/NetConfEval`, `shaunak1234/snmp-diagnostic-agent-traces`, `vivek-dodia/mikrotik-docs`), and **restricted** (`ndavidson/cisco_inam_chatml`, `jack0503/junos_cli_qa`, `jack0503/junos_cli_command`, `Coldyuja/junos-user-manual-markdown-raw`, `Rzkoohi/CCNA_medium`: no usable licence or unstated provenance; fetched only with `--accept-licence-risk`, for private experiments, never read by the notebook, never for a model you ship). `--kaggle owner/name` downloads a Kaggle dataset only when its licence is CC0, CC BY 4.0, ODC-BY, Apache-2.0 or MIT.

## Used (optional, off by default): real device output from `ntc-templates`

| | |
|---|---|
| Repository | [`networktocode/ntc-templates`](https://github.com/networktocode/ntc-templates) (public GitHub repository, not a Hugging Face dataset) |
| Licence | **Apache-2.0**, read from the repository's `LICENSE` file (GitHub's API says `NOASSERTION` because the file is not byte-identical to the template). `training/ntc_source.py` refuses to load anything if that file stops saying Apache License, Version 2.0 |
| What it is | For 50+ platforms, a **real captured output** of a `show` / `display` / `get` command (`tests/<platform>/<command>/*.raw`) next to the fields the platform's parser extracts from it (`*.yml`, `parsed_sample`) |
| Why it matters | The generated knowledge-base data knows every vendor's commands but has no *captured* output. This shows what a Junos box, a FortiGate, an Aruba switch or a VRP router really prints, in the vendor's own field names |
| Platforms used (14 folders, 10 vendors of the knowledge base) | `cisco_ios` `cisco_nxos` `cisco_xr` `juniper_junos` `arista_eos` `aruba_aoscx` `hp_procurve` `huawei_vrp` `fortinet` `mikrotik_routeros` `extreme_exos` `paloalto_panos` `dell_force10` `dell_powerconnect` (mapping in `PLATFORMS`, checked against the knowledge base by a test) |
| Filters | read-only commands only (`show`, `display`, `get`, `diagnose`, `dir`, or `... print`; nothing with `clear`, `reset`, `reload`, `write`, ...); no secrets (community strings, passwords, keys); at most 1,400 characters of device output and 1,000 of parsed JSON per row; at most 3 samples per command and 120 rows per platform |
| Result on 2026-09-29 (repository checked out, default caps) | 383 rows from 13 platforms: Cisco IOS 120, NX-OS 61, IOS-XR 31, Arista 44, Huawei 36, MikroTik 18, Aruba AOS-CX 17, HP ProCurve 16, Junos 16, Palo Alto 11, Fortinet 6, Dell Force10 4, Extreme 3. Fortinet, Extreme and Dell are small because most of their samples are longer than the size cap |
| Use | **train only** (task `ext_cli_parse`); the vendor-knowledge test files are unchanged, so the scores stay comparable. The task is not part of the D1 ship rule |
| Turn on | `INCLUDE_EXTERNAL = True` in notebook cell 1; cell B4 clones the repository (shallow) and prints the commit it used |

## Searched and not used

Searched on 2026-09-29 through the Hugging Face API (vendor names, task words, Arabic) and, for Kaggle, through public search results without signing in (Kaggle downloads need an API key). Vendors with **no** relevant dataset at all: Arista, Aruba, Huawei VRP, Dell, Extreme, Palo Alto, VyOS.

| Repository | Licence tag | Why it is not used |
|---|---|---|
| `Rzkoohi/CCNA_medium`, `Rzkoohi/CCNA_small` | apache-2.0 | 56.5k Cisco / CCNA Q&A pairs, but the card states no source, and the answers read like text generated from a CCNA study guide (an Apache tag cannot license that). CCNA-style content also overlaps the exam questions we keep for evaluation (`Elfsong/Cisco_CCNA`) |
| `brianlian/fortinet-test` | apache-2.0 | 2 rows, Chinese, not technical |
| `deepak003/juno-sample` | apache-2.0 | unrelated (medical review questions), not Juniper |
| `BytArch/ub-networking-dataset-2024-2` | mit | 102 generic protocol questions from lecture text |
| `yyyyyt/netopsbench-trace` | apache-2.0 | agent traces of third-party proprietary models on simulated fabrics, in archives with another format: later, for tool-use, if ever |
| `vulcansiem/synthetic-syslog-1B` | mit | a generator of generic RFC 5424 events, not vendor formats |
| `vivek-dodia/mikrotik-openAPI`, `-github-repos`, `-gitlab-repos`, `-threads` | mit | derived from vendor documentation, scraped repositories and forum threads: the tag does not license their content |
| `Mohamed77777777777777777777777777/network-topology-troubleshooting-dataset` | cc-by-nc-4.0 | non-commercial |
| `darkknight25/Networking_Commands_Dataset` | mit | built for red-teaming AI models |
| `jack0503/*`, `Coldyuja/junos-user-manual-markdown-raw`, `ndavidson/cisco_*`, `Elfsong/Cisco_*` (except CCNA), `dvilasuero/cisco-exams` | none stated | no licence declared, or derived from vendor documentation or exams |
| Kaggle: "Network Logs Dataset", "IOT Device Network Logs", "system logs", "Server Logs" | not read | generic web / IoT / server logs, no network-device vendor formats; need a Kaggle API key |
| `arbml/CIDAR` (from the user's resource pack, 2026-09-30) | apache-2.0 | 10,000 general Arabic instructions (nothing about networks). Its card says 9,109 rows were selected from Alpagasus (a filtered subset of Alpaca, whose data is CC BY-NC) and translated with ChatGPT, so the Apache tag cannot license them; same rule as `Rzkoohi/CCNA_medium` |
| `NetoAISolutions/NetBench` | mit | gated: the files need a Hugging Face login and manual approval, so the content could not be read or its provenance checked. If the user is approved, run the scout prompt on it first |
| `SOTAagi2030/Juniper-Catalog-Abstracts` | none | not about Juniper Networks: generated abstracts of "Juniper Valley oral-history transcripts" |
| Loghub (`logpai/loghub`, 19 sets on Zenodo; 2,000-line samples of 8 of them in the user's pack) | "freely available for research or academic work" | not an open licence for a model you ship; server, HPC and cloud logs, not network-device syslog; logs are "NOT sanitized" (real IPs and host names). Used once, read-only, as a robustness probe of `kb.parse_syslog`: 16,000 lines from Linux, OpenSSH, Apache, HDFS, Hadoop, Zookeeper, OpenStack and BGL, **0** parsed as a network event (no false positives); nothing was copied into the repository |
| Kaggle "CISCO Dataset", "Network Log Analysis"; the stefanbschneider gist | not read | Kaggle needs an API key and a per-dataset licence check (`collect_data.py --kaggle owner/name` does it); the gist is only an index of other sets |

Re-run the search with [`DATASET_SCOUT_PROMPT.md`](../DATASET_SCOUT_PROMPT.md) when new datasets appear; it already lists everything above as decided.
