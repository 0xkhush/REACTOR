# Native-schema candidate handoff

## Candidate to benchmark

- Branch: `feat/kaggle-evaluation`.
- Runtime commit: `ceafcee` (native Gemini parameter schemas and continuation identity).
- Local verification: **228 tests passed** with `.venv/bin/python -m pytest -q`.
- No new full benchmark started. The full **23/100 strict exact** result belongs to **`36a798b`**, not this candidate.

## Changes

The runtime registers all 12 original tools as typed LiveKit functions so Google receives native `parameters`, rather than the raw `parameters_json_schema` path. The same raw dispatcher/controller still performs actual execution. It revalidates the complete provider argument JSON, including fields LiveKit's argument model would ignore.

Clear connective sentence fragments can resume the existing request; explicit task verbs/domain requests remain new requests. Equivalent `drive`/`driving` and `walk`/`walking` values normalize before duplicate detection. Filter updates accept string, numeric and boolean scalar values, matching `mock_apis.update_search_filter(value: Any)`. JSON integers retain their exact value; bools cannot become numeric arguments.

Controller schema rejection produces metadata-only `ToolError` repair guidance without execution. **Limitation:** missing/invalid required arguments can fail in LiveKit's native preparation before this handler runs, so some provider errors remain generic. Turn classification remains a conservative heuristic, not complete semantic parsing.

## Live diagnostic probes

- Apartment search: room `reactor-smoke-9ba6aa5feb65`, exact pass after native schemas.
- Filter update: room `reactor-smoke-2254d2e0d57c`, exact pass after numeric filter values.
- Commute: an earlier native-schema probe `reactor-smoke-29c86767201f` executed twice and failed exact selection. Continuation/mode fixes followed; regression tests pass, but the final commute fix has not been replayed live.
- These probes preceded final review fixes. They are development diagnostics, not a measured pass rate for commit `ceafcee`.

## Clean full capture command

Confirm no other unnamed workers are active. Keep `.env.local` ignored and do not log credentials. Use a new **absolute** output directory, since upstream inference runs from its own working directory:

```bash
REACTOR_MODE=benchmark \
GOOGLE_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025 \
REACTOR_FREE_QUOTA_CONFIRMED=yes \
.venv/bin/python scripts/batch_infer.py --output "$PWD/artifacts/batch_ceafcee"

.venv/bin/python scripts/evaluate_batch_calls.py \
  --outputs "$PWD/artifacts/batch_ceafcee" \
  --output "$PWD/artifacts/batch_ceafcee/call-exact.json"
```

Do not combine this folder with previous results or retry completed/no-tool recordings to select better outputs. Keep all 100 inputs in the denominator. Save the full commit SHA and configuration alongside the capture. The local call-only scorer requires no ASR or judge; use Kaggle separately if time permits. This capture previously took about 90 minutes.

## Publication state

Changes are committed locally. No push, merge, release tag, or portal submission occurred. The deck sources still describe the measured `36a798b` run. Team/contact details, final media, disclosure signature, and submission receipt remain outstanding.
