# Blind Google judge comparison: calibrated, subset quota-blocked

## Measured outcome

At code revision `7684f4b`, the approved comparison produced:

| Model | Grouped controls | Single-call checks | Requests | Reported tokens | Outcome |
| --- | --- | --- | --- | --- | --- |
| `gemini-2.5-pro` | No valid verdicts | Not run | 1 | 0 | HTTP 404; no quality conclusion |
| `gemini-2.5-flash` | 24/24 | 4/4 | 5 | 9,374 | Qualified, zero false positives/negatives |

Google returned `gemini-2.5-flash` as the Flash model version. The calibration finished at `2026-10-02T17:59:28.050265+00:00`. Pro's published standard text free tier did not establish endpoint availability for this request. We did not retry Pro or substitute another model for it.

We then attempted to judge the same 25 failures from the saved `9f1128c` exact capture. Offline preflight confirmed all 25 result files and the 75 baseline passes excluded from rescoring.

The subset judge made **two API requests**, then latched on HTTP 429. It supplied **no usable semantic verdicts**. The evaluator recorded 25 attempted argument comparisons and **25 exact fallbacks** across the 14 recordings with matching tool sets. Eleven recordings still failed tool selection and required no argument judgments. The report contains zero returned model versions and zero reported tokens for this stage; absent usage metadata does not establish zero server-side token use.

The raw fallback report has zero passes among the selected failures and a combined count of 75. Those numbers reproduce exact matching after judge failure. **This attempt establishes no revised semantic benchmark result.** The runtime result remains **75/100 exact**, and the earlier **77/100 mixed diagnostic** remains a separate preserved experiment.

## Protocol and limits

We used `blind-controls-v2` and rubric `google-semantic-v2-category-query`:

- 24 independent controls, nine positive and fifteen negative, with opaque IDs and mixed label order. The provider received argument pairs and function names, with descriptive names and answer labels omitted.
- Four repeated controls in the scalar request format: two equivalent category queries and two changed quantity/feature cases. Flash answered all four consistently with the grouped judgments.
- A category-query grammatical-number rule that retains explicit quantities, brands, features, negation and constraints. The controls did not include the captured keyboard queries.
- A predeclared selection rule: valid complete responses, zero grouped false positives, at most one grouped false negative, and all four scalar checks correct. Ties prefer Gemma, Pro, stable Flash, then newest Flash. Only Pro and stable Flash took part in this comparison.

The expanded calibration validates these controls, not general judge reliability. Since Pro returned no verdicts, we cannot compare its semantic quality with Flash. We changed the rubric as well as calibration, so a later result cannot isolate a model effect from a rubric effect.

All eight hosted requests in this continuation used Google standard text generation under the user's confirmed free-tier arrangement: six calibration requests plus two subset requests. We made no OpenAI requests, used no paid Batch API or grounding, and made no automatic retries after the quota latch. Token metadata is not a billing statement.

## Preserved evidence

`GOOGLE_JUDGE_V2.json` records the measured summaries and the complete compact calibration verdict set. The raw artifact files retain full subset details locally; they are ignored by Git. SHA-256 checks confirmed that the earlier calibration, earlier subset report and original exact baseline retained their bytes.

| Evidence | Path | SHA-256 |
| --- | --- | --- |
| Blind calibration | `artifacts/google-blind-v2-calibration.json` | `7dbf4549899771afe388848bebbd1623497a1c59dc66dc833ad877c8a75b2b64` |
| Quota-blocked subset | `artifacts/failed25_9f1128c/google-blind-v2-semantic-subset.json` | `c159bb3565319317fb68f231d756827c5d0ce921e0ed7fe52d5b0f5b87f69036` |
| Earlier Flash calibration | `artifacts/google-stable-judge-calibration.json` | `a5638a2068ae708a39b36af7444a2b23b3de7a35616ad79afb7984fb2e17aa19` |
| Earlier mixed subset | `artifacts/failed25_9f1128c/google-semantic-subset.json` | `6d45d4cb1411412bffaf085d679360b94c5d8e744f6ea492c761c9a7185eef3b` |
| Exact baseline | `docs/results/9f1128c-call-exact.json` | `da03ccc1440b166aaa81a111e73c11358eb8695027057f4b0807c9fa44502aaf` |

The blind control payload hash is `5bcd043d784194d91376893a95e73a245919ee21fbf227672696371b9a71d65e`.

Verification: **358 automated tests passed**, `git diff --check` passed, and an offline replay of all saved calls generated a byte-identical 75/100 exact report. Main remained clean at `7f83a731db493d6e6ff6939762cc8cbc0e0d305e`.

## Remaining step

Finish the failed-subset semantic evaluation when confirmed-free Google quota is available. Reuse the pinned rubric and capture, retain the blocked report, and choose a new output path. The current report does not retain per-request failure metadata, so the first unsuccessful subset request's cause is unknown; the quota latch establishes a later HTTP 429.
