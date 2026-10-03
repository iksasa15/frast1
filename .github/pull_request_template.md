## What and why

<!-- One or two sentences. -->

## Checklist
- [ ] `cd backend && ROOTIQ_MODE=sim python -m pytest -q` passes
- [ ] `cd frontend && npx tsc --noEmit && npx vitest run src && npm run build` passes (if the UI changed)
- [ ] Vendor knowledge changed? `validate()` prints `[]`, and I ran `python training/build_dataset.py` and `python scripts/gen_vendors_doc.py`
- [ ] Nothing can approve, run or push a change to a device without a named human (Guardrail untouched or strengthened)
- [ ] No secret, key or token in the diff
- [ ] Docs and `CHANGELOG.md` updated; counts (agents, vendors, tests) still consistent

## What was verified, and what was not
