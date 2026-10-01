# Measured evaluation evidence

**Improvement branch checkpoint:** candidate `9150eb6` scored **57/100 strict exact passes** and **80/100 expected tool selections**, with zero capture failures. See [accuracy-v2 evidence and limits](ACCURACY_V2.md) and [per-recording report](9150eb6-call-exact.json). The requested strict pass rate above 80% is not met. The older captures below retain their own revisions and provenance.

`FDB_v3_exact_reports.zip` contains the historical Kaggle reports and 100 per-recording transcript/tool-result records. `SUMMARY.json` gives their hashes, counts, and limits. `CANDIDATE_SUMMARY.json` records a newer, single-revision Mac capture. The agent loads none of these documents.

## New candidate at `36a798b` (30 September)

- 100/100 recordings captured in one clean, dedicated-worker run: 59 with calls, 41 without, zero transport failures.
- Pinned upstream local tool/argument exact check: **42/100 expected tool selections; 23/100 strict exact passes (23%)**. The requested 40% strict pass target was **not** reached.
- No ASR or semantic judge was run on this candidate's audio. Spoken-response quality, interruption timing, and official normalized score remain unmeasured for this candidate.
- The full local report is ignored at `artifacts/batch_36a798b/call-exact.json`; `CANDIDATE_SUMMARY.json` records its SHA-256. Regenerate the report from captured files with `.venv/bin/python scripts/evaluate_batch_calls.py --outputs artifacts/batch_36a798b --output artifacts/batch_36a798b/call-exact.json`. The agent never sees scenario answers; only the separate scorer reads them.
- Housing remained a major failure source. Traces show Gemini asking for unnecessary details instead of using available tool fields. The current prompt and alias changes did not reach 40%.

## Earlier mixed-revision capture and Kaggle ASR

- Released FDB-v3: 100 recordings, pinned upstream `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.
- Model used during capture: `gemini-2.5-flash-native-audio-preview-12-2025` through LiveKit Cloud.
- All 100 capture attempts produced result records; 37 contained executed tool calls, 63 did not; no final capture attempt failed at transport.
- Strict exact tool/argument pass: **12/100 (12%)**. Expected tool multiset matched in 25/100 recordings. Executing a tool is not equivalent to passing a task.
- ASR: `nvidia/parakeet-tdt-0.6b-v2`, NeMo 2.5.3, Kaggle Tesla T4. No training or fine-tuning was performed.
- Judge: **none**. The official organizer rerun uses a separate pinned semantic judge, so these are not official normalized scores. Exact matching can reject semantically equivalent formats.

## Important provenance limits

The recordings were captured across pre-release code changes, not in a single clean final-candidate run. Per-recording code hashes and hosted-model seeds were not stored. Early transport failures were retried only where no output WAV existed. Completed/no-tool examples were not silently rerun to cherry-pick better results.

Some early capture sessions ran while unnamed kitchen and benchmark workers shared a LiveKit project; a trace showed a benchmark room receiving kitchen-mode behavior. The final code chooses the mode from the known room prefix to prevent that mix-up. This correction does not repair historical recordings. The 12% figure describes the captured dataset, **not** the measured quality of the final reviewed candidate.

The later clean capture evaluated commit `36a798b` on all 100 inputs. Its 23% exact pass rate and the older 12% describe different captures, not a controlled paired comparison. The newer candidate's audio was not transcribed by Parakeet.

Word timestamps and call timestamps are diagnostic. The upstream recording client writes received frames into its output buffer, and equivalent live audio-timeline behavior has not been independently validated. Do not present those values as proof of the sub-second latency target.

## Reproduce / inspect

Configure credentials locally, download released input audio, then run the documented reproduction commands. For existing capture logs:

```bash
.venv/bin/python scripts/evaluate_batch_calls.py
```

For GPU transcription over private audio/results datasets, use `remote_eval/asr_eval` as documented in `docs/submission/KAGGLE_SETUP.md`. Keep all failed/no-tool attempts in the denominator. The agent runtime never reads ground-truth scenario definitions; the separate evaluator does.
