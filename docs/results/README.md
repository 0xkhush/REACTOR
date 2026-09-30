# Measured evaluation evidence

`FDB_v3_exact_reports.zip` contains the downloaded Kaggle reports and 100 per-recording transcript/tool-result records. `SUMMARY.json` gives report hashes, counts, and limits. Nothing in this directory is loaded by the agent.

## What the run measured

- Released FDB-v3: 100 recordings, pinned upstream `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.
- Model used during capture: `gemini-2.5-flash-native-audio-preview-12-2025` through LiveKit Cloud.
- All 100 capture attempts produced result records; 37 contained executed tool calls, 63 did not; no final capture attempt failed at transport.
- Strict exact tool/argument pass: **12/100 (12%)**. Expected tool multiset matched in 25/100 recordings. Executing a tool is not equivalent to passing a task.
- ASR: `nvidia/parakeet-tdt-0.6b-v2`, NeMo 2.5.3, Kaggle Tesla T4. No training or fine-tuning was performed.
- Judge: **none**. The official organizer rerun uses a separate pinned semantic judge, so these are not official normalized scores. Exact matching can reject semantically equivalent formats.

## Important provenance limits

The recordings were captured across pre-release code changes, not in a single clean final-candidate run. Per-recording code hashes and hosted-model seeds were not stored. Early transport failures were retried only where no output WAV existed. Completed/no-tool examples were not silently rerun to cherry-pick better results.

Some early capture sessions ran while unnamed kitchen and benchmark workers shared a LiveKit project; a trace showed a benchmark room receiving kitchen-mode behavior. The final code chooses the mode from the known room prefix to prevent that mix-up. This correction does not repair historical recordings. The 12% figure describes the captured dataset, **not** the measured quality of the final reviewed candidate.

The latest prompt, alias normalization, event-ID/generation binding, duplicate coalescing and kitchen speech changes have targeted tests and a kitchen integration smoke. They have **not** been evaluated on another full 100-recording capture. No baseline improvement or qualification claim is supported by the available evidence.

Word timestamps and call timestamps are diagnostic. The upstream recording client writes received frames into its output buffer, and equivalent live audio-timeline behavior has not been independently validated. Do not present those values as proof of the sub-second latency target.

## Reproduce / inspect

Configure credentials locally, download released input audio, then run the documented reproduction commands. For existing capture logs:

```bash
.venv/bin/python scripts/evaluate_batch_calls.py
```

For GPU transcription over private audio/results datasets, use `remote_eval/asr_eval` as documented in `docs/submission/KAGGLE_SETUP.md`. Keep all failed/no-tool attempts in the denominator. The agent runtime never reads ground-truth scenario definitions; the separate evaluator does.
