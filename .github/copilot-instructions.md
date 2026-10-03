# Instructions for GitHub Copilot in this repository (RootIQ)

RootIQ turns an alert storm into one incident with an evidence-backed root cause and an approve-only remediation. It has a FastAPI backend
(`backend/`), a React + Vite frontend (`frontend/`), 16 agents (`backend/app/agents/`), a vendor knowledge base (`backend/app/knowledge/`),
and a training folder (`training/`). Start with `README.md`, then `docs/AGENTS.md` and `docs/VENDORS.md`.

## Non-negotiable rules
1. **Nothing changes a device without a named human approving it.** Never add a code path where an agent, the Copilot, `system` or a script can approve, reject
   or execute. The Guardrail agent is fail-closed and cannot be disabled; do not weaken a policy to make a test pass.
2. **Vendor commands are reference text.** Read-only diagnostic commands must start with an inspection verb and contain no change verb (`validate()` and the
   `vendor_commands_read_only` guardrail policy enforce it). Change commands exist only for `clear_counters` and `bounce_interface`, always need approval and are
   never executed by RootIQ.
3. **The knowledge base JSON is the single source of truth** (`backend/app/knowledge/data/`). Do not hand-edit anything derived from it:
   `training/data/generated/*` and `docs/VENDORS.md` are generated (see the commands below).
4. **Do not invent vendor facts.** A command, syslog format or OID you cannot source stays out; say so and lower the vendor's `confidence` instead. Profile-only
   vendors have no commands on purpose.
5. **No secrets in the repository.** API keys come from the environment (or Colab Secrets). Never write one into a file, test, notebook or log.
6. Open pull requests against `main` of **this fork** only. Never target or reference the upstream repository `iksasa15/frast1`.

## Commands (run these before you finish)
```bash
cd backend && ROOTIQ_MODE=sim python -m pytest -q          # 312 tests must pass
cd frontend && npx tsc --noEmit && npx vitest run src && npm run build
python training/build_dataset.py --check                    # if it fails: python training/build_dataset.py and commit the result
python scripts/gen_vendors_doc.py --check                   # if it fails: python scripts/gen_vendors_doc.py and commit the result
python scripts/audit_wiring.py                              # docs, counts, notebook and frontend agree with the code; it says which number to update
```

## Conventions
- Match the surrounding code: comment density, naming, idiom. Python 3.12, type hints where the neighbours have them; TypeScript strict.
- A new agent needs an `AgentSpec` in `agents/roster.py` (EN and AR text), a section in `docs/AGENTS.md` (a test fails otherwise), a deterministic fallback,
  and tests for both the flow and the failure/disabled case.
- Add or change a vendor by editing its JSON only, then run `validate()` (`cd backend && python -c "from app.knowledge import get_kb; print(get_kb().validate())"`
  must print `[]`), regenerate the training data and `docs/VENDORS.md`, and add a test when behaviour changes.
- Docs are Arabic first for prose and English for tables/commands; keep counts (agents, vendors, tests) consistent across `README.md`, `docs/` and `CHANGELOG.md`.
- Windows note for maintainers: PyTorch and some scikit-learn DLLs can be blocked by Windows App Control on the author's machine; GPU training runs in Colab
  (`training/RootIQ_Training.ipynb`). Do not try to run GPU cells here.

## Where things are
| Topic | Path |
|---|---|
| Agents, roster, guardrail | `backend/app/agents/`, `docs/AGENTS.md` |
| Vendor knowledge base and loader | `backend/app/knowledge/`, `docs/VENDORS.md` |
| RAG and Copilot | `backend/app/rag/`, `backend/app/agents/copilot.py` |
| Tests | `backend/tests/` (`test_multivendor.py`, `test_training_data.py`, ...) |
| Training data, scorer, prompts, notebook | `training/` |
| Multi-vendor example topology | `configs/topology.multivendor.example.json` |
