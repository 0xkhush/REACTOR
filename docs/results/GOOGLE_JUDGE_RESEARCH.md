# Google-only judge research and selection protocol

## Verified sources (2026-10-02)

- Pricing: https://ai.google.dev/gemini-api/docs/pricing
- Hosted Gemma API: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
- Structured-output documentation: https://ai.google.dev/gemini-api/docs/structured-output
- Authenticated `models.list` metadata confirmed the candidate IDs support `generateContent`. No model inference was performed for that metadata check.

The web-fetch helper failed for these pages; direct HTTPS retrieval returned the official pricing page and Gemma documentation. The pricing page's response reported a 2026-10-01 last-modified date.

| Candidate | Published standard text pricing | Why compare it |
| --- | --- | --- |
| `gemma-4-31b-it` | Input and output free; paid tier not available | Dense 31B instruction model; strongest budget assurance and suitable reasoning candidate. |
| `gemini-3.8-flash` | Input and output free on the free tier | Google's newest and most-intelligent-described Flash model; promising for classification and multi-step reasoning. |
| `gemini-2.5-flash` | Input and output free on the free tier | Stable fallback candidate approved after newer endpoints failed to return usable responses. |

Gemini 2.5 Pro/Flash also have published free-tier text pricing. Gemini 3.1 Pro Preview does not. Model-list availability alone is not evidence of free quota. This comparison is of the two approved candidates, not an exhaustive claim of the best model in every task.

## Approved protocol

The user explicitly prohibited OpenAI API requests and approved a free-tier comparison followed by evaluation of the original 25 exact failures. After the two newer endpoints failed, the user approved checking stable Gemini 2.5 Flash using the same controls.

1. Compare the approved candidates on sixteen independently constructed, human-labelled controls. Positive controls test query paraphrases, plural forms, case/geographic/date formats, document-category presentation and the FDB rule's 5% numeric tolerance. Negative controls test altered quantities, amounts, currency direction, identifiers, dates, people, product features, negation, omitted constraints and instruction-like argument data.
2. Send no `expected_correct` control labels to either model. Neither model sees benchmark outcomes for selection. Use one normal standard `generate_content` request per candidate with the independent controls, not the paid asynchronous Batch API.
3. Require a valid complete verdict set, zero false positives, and at most one false negative. Select the highest control accuracy. A quality tie prefers free-only Gemma 4 31B. If no candidate qualifies, do not perform the failed-case judging.
4. Run the selected model with `--google-judge --judge-model MODEL --failed-from docs/results/9f1128c-call-exact.json`. The selection validates the frozen baseline population and ensures only its 25 failures are rescored. The original 75 exact passes are not rejudged.
5. Preserve original tool-selection checks, captured calls and exact report. Keep Google verdicts and reasons in an alternative diagnostic. A combined count is mixed exact/Google-semantic, not a fully semantic 100-case benchmark or an official score.

## Request and output constraints

Only the three verified candidate IDs are allowed. Google mode requires the existing Google key and `REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED=yes`; GPT-4o confirmation cannot authorize it. The Google path never initializes an OpenAI client. The old explicitly requested GPT-4o mode remains for compatibility, but is not used in this task and is not an automatic fallback.

Requests use standard text generation with temperature zero, bounded output, a 60-second timeout, one SDK attempt and thirteen-second pacing between requests within one judge. Automatic function calling is disabled. No search grounding, maps, cached content or paid service tier is configured. A 429 quota error latches that judge against further requests. Invalid JSON/boolean verdicts or judge errors are recorded as exact fallbacks; they cannot silently count as semantic passes.

Multi-tool argument comparisons for one eligible recording are grouped into a single standard text request, retaining the pinned classifier's FIFO pairing of repeated function names. Verdict state is cleared after that recording; no judge result is cached across recordings. The classifier still receives one verdict per expected tool comparison, so 25 comparisons in the failed subset can use 14 API requests. Grouping is not use of the paid Batch API.

## Observed model availability and calibration

The initial Gemma 4 and Gemini 3.8 calibration requests returned no usable verdicts. Subsequent single-control probes observed Gemma HTTP 500 and Gemini 3.8 HTTP 504. These are endpoint/request failures, not evidence of their semantic judging quality. `artifacts/google-judge-calibration.json` retains the unsuccessful initial comparison.

The approved stable fallback `gemini-2.5-flash` returned valid JSON and passed **16/16 controls with zero false positives and zero false negatives**, using one API request and 4,553 reported tokens. The returned model version was `gemini-2.5-flash`. Its report is `artifacts/google-stable-judge-calibration.json`. This qualifies the stable model for the subset experiment but is not a benchmark score or proof of globally best judging quality.

The Google rubric follows the original FDB argument-judge rules and adds explicit handling of untrusted argument strings and missing constraints. This is an alternative provider/rubric implementation, not a claim of identical outcomes to the organizers' pinned judge.

## Commands

From the isolated improvement worktree, using the existing environment:

```bash
# Independent model comparison after free access has been confirmed.
PYTHONPATH="$PWD/src" REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED=yes \
/Users/khush/Documents/experiment/prism/.venv/bin/python scripts/calibrate_google_judge.py \
  --output "$PWD/artifacts/google-judge-calibration.json"

# Stable fallback control check, approved after the newer endpoint failures.
PYTHONPATH="$PWD/src" REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED=yes \
/Users/khush/Documents/experiment/prism/.venv/bin/python scripts/calibrate_google_judge.py \
  --model gemini-2.5-flash --output "$PWD/artifacts/google-stable-judge-calibration.json"

# Use exactly the model selected in the calibration report.
PYTHONPATH="$PWD/src" REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED=yes \
/Users/khush/Documents/experiment/prism/.venv/bin/python scripts/evaluate_batch_calls.py \
  --google-judge --judge-model SELECTED_MODEL \
  --inputs "$PWD/fdb_v3_data_released" --outputs "$PWD/artifacts/batch_9f1128c" \
  --failed-from "$PWD/docs/results/9f1128c-call-exact.json" \
  --output "$PWD/artifacts/failed25_9f1128c/google-semantic-subset.json"
```

`--check` provides offline scope/access metadata without inference or report writes. All judge access remains an operator-confirmed free-tier arrangement; generated token metadata is not an independent billing statement.

## What a result would mean

This changes evaluation only. It does not improve or rerun the voice agent, and it cannot supply missing tool calls. Eleven failed recordings do not match the expected tool multiset; only fourteen are eligible for argument judging. Any mixed population count combines 75 unchanged exact passes with the selected subset's passes. The fully measured exact result remains 75/100 unless a fresh agent capture changes it.

Tests use only fake external Google responses and the real pinned tool classifier. They do not constitute a real semantic benchmark score. Actual calibration/subset outcomes must be saved separately after execution.
