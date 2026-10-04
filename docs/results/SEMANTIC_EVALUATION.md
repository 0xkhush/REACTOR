# Opt-in pinned FDB semantic argument evaluation

## Purpose and current result

The saved-capture scorer supports FDB-v3's original `--use-llm` argument-judge policy, using `gpt-4o`. It can accept meaning-equivalent descriptive arguments rather than requiring literal equality. The upstream checkout and reference answers remain unchanged, and no judge logic enters the agent runtime.

**No real semantic evaluation has run in this environment.** Preflight found no judge key or confirmed judge access. The measured strict exact result stays **75/100**, and rechecking it after these changes produced a byte-identical report.

Accepting the two singular/plural product-query cases alone would yield 77/100 on this capture if other judgments stayed unchanged. An 80%+ semantic result cannot be claimed before a real run. Because only 89/100 recordings matched the expected tool multiset, this saved capture's strict semantic pass rate cannot exceed 89/100 without different agent calls.

The hackathon guide says the organizers rerun FDB-v3 with one pinned judge enabled for semantic argument matching and spoken-response quality. Our optional local argument report does not replace their rerun and is not an official normalized score.

## Judge access

Install the optional judge SDK when needed:

```bash
python -m pip install -e '.[judge]'
```

Configure these values in the ignored repository-root `.env.local`, or export them in the environment:

```dotenv
OPENAI_API_KEY=your-evaluator-provided-key
REACTOR_JUDGE_QUOTA_CONFIRMED=yes
```

Set confirmation only after verifying judge access and budget. The existing Google AI Studio key does not authenticate GPT-4o. OpenAI API use is typically billable; under a ₹0 budget use an organizer-provided or confirmed no-cost arrangement. Do not paste keys into chat, source, reports, screenshots, or Git.

The saved-capture semantic scorer requires both a key and explicit confirmation before constructing a judge client. It disables SDK retries and uses a 30-second request timeout. `--check` only reports prerequisite booleans and input/result-file counts; it makes no hosted requests and writes no report.

## Saved-capture workflow

The commands below use the existing main-checkout environment from the isolated improvement worktree. `PYTHONPATH` ensures the candidate's scripts/source are used.

```bash
# Offline check: prints no key values and makes zero judge/model requests.
PYTHONPATH="$PWD/src" /Users/khush/Documents/experiment/prism/.venv/bin/python \
  scripts/evaluate_batch_calls.py --use-llm --check \
  --inputs "$PWD/fdb_v3_data_released" --outputs "$PWD/artifacts/batch_9f1128c"

# Actual semantic argument judging, only after access is configured and confirmed.
PYTHONPATH="$PWD/src" /Users/khush/Documents/experiment/prism/.venv/bin/python \
  scripts/evaluate_batch_calls.py --use-llm \
  --inputs "$PWD/fdb_v3_data_released" --outputs "$PWD/artifacts/batch_9f1128c" \
  --output "$PWD/artifacts/batch_9f1128c/call-semantic.json"
```

One-room scoring also accepts `scripts/evaluate_smoke.py --use-llm --room ROOM --input INPUT_WAV`. Without `--use-llm`, both scorers retain exact matching. Batch defaults are separate: `artifacts/batch-call-eval-exact.json` and `artifacts/batch-call-eval-semantic.json`.

## Report interpretation

- Tool selection stays the original strict multiset comparison. Semantic judging cannot supply a missing tool or remove an extra execution.
- Argument judging retains the original FDB prompt, including its treatment of formatting, common aliases, dynamic references and numeric tolerance. This is not a blanket singular/plural shortcut or an embedding-based product search.
- `judge.attempts` records argument comparisons sent to the judge path. `judge.exact_fallbacks` exposes the upstream fallback when requests fail, JSON is unusable, or a nonboolean verdict violates the judge response contract. The boolean check prevents truthy string verdicts from inflating scores.
- If a fallback occurs, the report identifies its mode as `captured_calls_mixed_semantic_exact_arguments_no_asr`. It is not presented as fully semantic. `arguments_passed` includes successful fallback checks; `semantic_arguments_passed` counts passing cases with judge attempts and no fallback.
- All input recordings remain in the denominator, including missing and no-tool results. The raw captured calls are not rewritten or selectively rerun.
- These commands judge **tool arguments only**. They do not transcribe audio, judge spoken-response quality or establish latency. Reports state `official_score: false`, `asr_used: false`, and `response_quality_evaluated: false`.

For the full inference + ASR + response-quality pipeline, the existing CUDA reproduction route uses `scripts/reproduce.py --use-llm` and an evaluator-supplied `OPENAI_API_KEY` in its environment. That route requires NVIDIA CUDA and has not been validated on a clean Linux host here. Use the participant guide and pinned FDB instructions for organizer-style end-to-end evaluation; the saved-call report is a narrower diagnostic.

## Verification

The full suite passed **334 tests**. Semantic tests use the actual pinned classifier and substitute only the external API. They cover accepted semantic verdicts, missing-tool failure, request fallback, malformed boolean verdicts, distinct report defaults, offline preflight and client cleanup. These are integration tests for the runner; mocked verdicts are not a measured semantic benchmark score.
