# Accuracy-v4 current-model repair checkpoint: 75/100

## Candidate and full-run result

- Branch: `feat/tool-call-accuracy-v4-90`.
- Frozen runtime commit: `9f1128ced7e367bc134af1b01bf4ac4e8469810c`.
- Model: `gemini-2.5-flash-native-audio-preview-12-2025`.
- Inputs: all 100 original released recordings; pinned original mock backends and scorer at `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.

| Metric | 72% checkpoint | v4 current-model run |
| --- | ---: | ---: |
| Strict exact tool/argument passes | 72/100 | **75/100** |
| Expected tool multiset matches | 87/100 | **89/100** |
| Recordings containing executed calls | 95 | 94 |
| Recordings without calls | 5 | 6 |
| Capture failures / missing records | 0 / 0 | **0 / 0** |

**The requested 90%+ strict target was not reached.** Twenty-five recordings failed. Fourteen selected the expected tools but failed arguments; eleven failed the complete tool-selection check. Both reports count all 100 attempts and use independent hosted-model outputs, not a controlled paired experiment. Do not attribute the entire difference to one change.

## Repairs after the failure audit

`FAILURE_AUDIT_72.md` documents all 28 failures of the preceding capture, including each transcript/call/scorer category.

- Model-added years now use validated calendar-day parsing across ISO, long-form and supported numeric formats. Grounding still requires the matching user-named month/day and no explicit four-digit year in that request; invalid or mismatched dates stay unchanged.
- Office wording no longer loses the user-stated article through generic-location normalization. Personal labels such as `my office` and `the grocery store` remain intact.
- Completion instructions explicitly retain separate requested actions, use real SDK calls, and prevent unrequested follow-up calls. Numeric conditions use returned values; subjective or ambiguous write conditions require clarification. A contradicted write is not authorized to satisfy a scorer.

The suite passed **322 tests**. A baseline dual-autopay diagnostic passed without the new prompt, demonstrating intermittent model behavior. A baseline conditional-housing replay added an extra search; a subsequent revised-prompt replay completed exactly its three requested tools and passed the local exact check. These probes are development diagnostics, not a benchmark percentage.

## Evidence and reproduction

- Committed per-recording report: `9f1128c-call-exact.json`.
- Report SHA-256: `da03ccc1440b166aaa81a111e73c11358eb8695027057f4b0807c9fa44502aaf`.
- Local manifest SHA-256: `38a72777603375f684a1478a2a1496de0154fd3119ce5c3a5e68f4a9eaeac6a3`.
- Raw WAV/result records: ignored `artifacts/batch_9f1128c/`.
- Frozen configuration: ignored `artifacts/provenance_9f1128c.json`.

Recheck the saved capture from the isolated worktree:

```bash
PYTHONPATH="$PWD/src" /Users/khush/Documents/experiment/prism/.venv/bin/python \
  scripts/evaluate_batch_calls.py --outputs "$PWD/artifacts/batch_9f1128c" \
  --output "$PWD/artifacts/batch_9f1128c/rechecked-exact.json"
```

For new inference, use a fresh output folder with the same readiness-aware harness and preserve SHA/configuration. Never mix captures or replay completed/no-tool cases to select a better score.

## Limits and next decision

This is **local exact tool/argument scoring** without ASR or a semantic judge, not an official normalized contest score. It does not establish spoken-response quality or sub-second latency. Perception loss, missing context, intermittent SDK tool emission, and literal-format reference mismatches remain. The original failure audit also identifies contradictory or subjective conditional expectations; no reference answers were injected into runtime and no scoring rules were changed.

The user selected current-model repairs first. A metadata-only model listing showed newer Live models available to the key, but it does not prove free-tier quota or pricing. No other model was invoked. A controlled model comparison needs confirmation of free access before inference; a separate planner would need a separate design.

The branch remains isolated from `main`; no merge or push occurred for this repair task.
