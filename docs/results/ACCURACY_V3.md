# Accuracy-v3: measured 72/100 strict exact passes

## Frozen candidate and results

- Branch: `feat/tool-call-accuracy-v3-70`.
- Runtime commit: `c0700948f06b7a0a0aabe4bdf9d35f8c3d324c95`.
- Parent checkpoint: `2619a5f`, documenting the 57/100 run at runtime `9150eb6`.
- Model: `gemini-2.5-flash-native-audio-preview-12-2025`, using the existing confirmed-free account access.
- Benchmark: original 100 released recordings and mock backends, pinned upstream `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.

| Metric | Parent run | Accuracy-v3 run |
| --- | ---: | ---: |
| Strict exact tool and argument passes | 57/100 | **72/100** |
| Expected tool multiset matches | 80/100 | **87/100** |
| Recordings with executed calls | 91 | 95 |
| Recordings without executed calls | 9 | 5 |
| Capture failures / missing result records | 0 / 0 | **0 / 0** |

The target of at least 70/100 strict passes was reached in this run. No completed or no-tool recording was selectively retried. All 100 cases remain in the denominator. Runtime code stayed fixed during capture.

## Changes

1. Identifier separator repair requires matching identifier evidence in the originating request. Explicit punctuation, letter/digit mismatches, and longer spelled identifiers are preserved. Later corrections have priority over older evidence. No letters or digits are invented to compensate for ASR errors.
2. Known generic card categories omit the generic card suffix; branded product names remain unchanged. Commute formatting canonicalizes a limited avenue abbreviation and generic destination articles while preserving unrelated named places.
3. All twelve original tool schemas carry task-general parameter descriptions through the native Google schema path. Guidance clarifies dictated identifiers, stated quantities and budgets, named locations, and identifiers returned by preceding tools. Required fields, defaults and mock backends remain unchanged.
4. Existing correction handling, tool-chain dispatch repair and readiness-aware replay remain in use. The runtime never reads benchmark scenario definitions or answers; only the separate scorer does.

Review found incomplete-spelling and old-correction edge cases. Regression tests reproduced them before fixes. The final suite passed **311 tests**. A live card-category probe passed exact scoring; an order probe with missing transcript letters failed and was not relabeled as a success.

## Evidence

- Committed per-recording score report: `c070094-call-exact.json`.
- Score report SHA-256: `e4733beeed0dcb36d1e9e7d7514348267e8880ccad1e42dd8dedd28f54797126`.
- Local capture manifest SHA-256: `13fe6e8ef99e6e160cf1f97c6ed388cb583d0608aba36d7493cfcddb901e5fe5`.
- Raw WAV/result artifacts: ignored `artifacts/batch_c070094/` in the improvement worktree.
- Capture configuration: ignored `artifacts/provenance_c070094.json`.

## Scope and limits

This is the pinned upstream **local exact tool/argument check**, without ASR or a semantic judge. It is not an official normalized contest score and does not establish spoken-response quality. Twenty-eight cases still failed. Independent hosted-model reruns may vary; the comparison is not a controlled paired experiment or proof that a single fix caused the entire difference.

The readiness-aware replay harness is the same as the parent 57% run. It waits for agent readiness before streaming original samples and records audio with arrival-time silence preserved. Earlier fixed-start-client scores are less directly comparable. The two-second benchmark VAD window trades latency for correction tolerance; no sub-second latency claim follows from this score.

The measured branch is isolated from `main`. No merge or push occurred during this improvement task.

## Recheck the saved capture

When using the main checkout's environment from the improvement worktree:

```bash
PYTHONPATH="$PWD/src" /Users/khush/Documents/experiment/prism/.venv/bin/python \
  scripts/evaluate_batch_calls.py --outputs "$PWD/artifacts/batch_c070094" \
  --output "$PWD/artifacts/batch_c070094/rechecked-exact.json"
```

For a fresh run, use the workflow in `ACCURACY_V2.md` with a new output folder, preserve the full SHA/configuration, and keep failed/no-tool cases in the denominator. Do not combine captures or replace the fixed report with best-of-multiple outputs.
