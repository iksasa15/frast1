---
name: vendor-kb
description: Adds or corrects vendors, OS families, commands, syslog patterns and problem patterns in the RootIQ vendor knowledge base, and keeps the derived training data and docs/VENDORS.md in sync.
---

You maintain the RootIQ vendor knowledge base in `backend/app/knowledge/data/` (one JSON file per vendor, plus `problems.json` and `capabilities.json`).

Rules:
- Edit JSON only. Copy the structure of a similar vendor (`cisco.json`, `juniper.json`, `fortinet.json`). Never touch `training/data/generated/*` or `docs/VENDORS.md` by hand.
- Only add facts you can source (official vendor documentation, a real device capture pasted in the issue, the IANA enterprise-number registry). If you cannot, leave it out
  and lower the vendor's `confidence`. Never invent a command, an OID or a log format.
- Read-only lists (`"read": [...]`) contain inspection commands only. Change commands are allowed only for `clear_counters` and `bounce_interface`.
- Every regex needs a real `example` that matches it. Every OS with a `default` command table must be listed in the vendor's `default_for`.
- For a full-coverage vendor add a `config_model` (how a change is applied, saved and rolled back) and a `cli_style` (EN and AR) for each OS.

After every change, run and paste the results in the pull request:
```bash
cd backend && python -c "from app.knowledge import get_kb; print(get_kb().validate())"   # must print []
cd backend && ROOTIQ_MODE=sim python -m pytest -q
python training/build_dataset.py && python scripts/gen_vendors_doc.py                     # regenerate, then commit the result
```
Open the pull request against `main` of this fork, and list which facts came from which source.
