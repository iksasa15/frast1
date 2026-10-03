# Documentation sources for RootIQ Copilot

When Copilot cites a source, map it as follows:

| Source label / path | Origin | Trust |
|---------------------|--------|-------|
| Live topology / طوبولوجيا حية | Current Operations snapshot (`nodes`, `links`, `services`) from discovery or sim fixture | Authoritative for counts and health |
| `docs/network/*` | This curated network ops pack (FAQ + troubleshooting) | Authoritative for procedure text |
| `docs/*.md` | Project docs (architecture, runbooks, UI notes) | Background |
| `knowledge/problems.json` + `knowledge/vendors/*` | Built-in vendor/problem catalogue under `backend/app/knowledge/data/` | Vendor CLI & problem patterns |
| Playbooks | `backend/app/agents/playbooks.py` | Remediation steps shown in the UI |
| Thresholds | `backend/app/intelligence/thresholds.py` | Metric breach definitions |
| Incidents / postmortems | Runtime incident store + learning agent | What happened in this deployment |
| Lab configs | `lab/configs/*` (secrets redacted in the index) | Lab-only reference |

## What is *not* a source

- Model free-recall: the LLM (OpenRouter) may only reword facts already present in the draft answer and retrieved CONTEXT.
- Chat history guesses about device counts — always prefer the live topology tool.

## Reindex

After editing this pack: `POST /api/knowledge/reindex` or restart the backend.
