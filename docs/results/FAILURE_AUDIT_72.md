# Audit of the 28 failures in the 72% capture

Source: `c070094-call-exact.json`, raw results at `artifacts/batch_c070094/`, and matching room events in `artifacts/trace.jsonl`. The audit uses the separate pinned evaluator; none of its reference arguments enter the agent runtime.

## All failed recordings

The final column describes observed evidence, not a proven repair or hypothetical new score. Suffixes distinguish recordings of the same scenario.

| Scenario / recording suffix | Failure | Evidence |
| --- | --- | --- |
| ecommerce_08 / 5ff07b5e | Arguments | User and agent use singular product wording; reference uses plural. |
| ecommerce_08 / 61517db6 | Arguments | Same singular/plural mismatch. |
| ecommerce_10 / 6998abd7 | Missing step | Only tracking executed; its first call started near the replay window's end. |
| ecommerce_12 / 6998abd7 | Arguments | Audio transcript describes electronics; reference expects a gift query and category, which the current tool contract does not expose. |
| ecommerce_13 / 5ff07b5e | Arguments | ASR and calls retain ID dashes; reference removes them. |
| ecommerce_14 / 5ff07b5e | Arguments | ASR/call retain ID dashes; reference removes them. |
| ecommerce_15 / 56780a5a | Arguments | Model and transcript use separated letter/number groups; reference uses compact form. |
| ecommerce_21 / 69a9cf80 | Missing steps | Request split into partial turns; search and cart step never executed. |
| finance_06 / 66f59c76 | Missing tool | Model asks for a card name despite the supplied category. |
| finance_20 / 66c4f3cb | Missing tool | User leaves exchange-rate acceptability subjective; agent asks before modifying autopay. |
| finance_22 / 5f4a4da1 | Missing tool | Second autopay call appears in assistant text but not actual SDK execution. |
| housing_06 / 5f4a4da1 | Arguments | Reference omits the article before the generic gym label. |
| housing_10 / 66f59c76 | Arguments | Neighborhood compound has different spacing. |
| housing_11 / 62a885d5 | Wrong tools | Model updates filters instead of searching; city is absent from the captured user transcript. |
| housing_13 / 5f4a4da1 | Missing tools | No transcript, proposals or assistant response recorded. Cause unproven. |
| housing_17 / 65e8cf8f | Arguments | Current article normalization drops the user-stated office article; reference retains it. |
| housing_17 / 69a9cf80 | Arguments | Same office-article mismatch. |
| housing_18 / 66c4f3cb | Arguments | Budget ASR loses the leading thousand; destination label also differs in ordinal/article wording. |
| housing_20 / 62a885d5 | Missing steps | Model refuses supported commute/conditional budget workflow after apartment search. |
| housing_21 / 66c4f3cb | Missing tools | Model asks for missing city/origin; captured transcript does not supply city. |
| housing_22 / 695bd157 | Missing step | Filter and search executed; assistant says it is calculating commute but no call was captured. |
| housing_24 / 65e8cf8f | Arguments | Model omits user-stated grocery-store article; reference retains it. |
| housing_25 / 66f59c76 | Missing steps | Model searches with constraints but omits explicitly requested filter writes. |
| travel_02 / 5e3c1fbe | Arguments | Passport number differs from the reference; transcript itself is unreliable for that identifier. |
| travel_07 / 5ff07b5e | Missing tool | Transcript begins at the last digit, losing opening document context. |
| travel_20 / 62a885d5 | Missing tools | Model refuses conditional workflow; the reference also expects both alternate writes despite the user condition and mock price. |
| travel_21 / 65e8cf8f | Arguments | Model adds a year in long-form date wording; passenger spelling differs from reference/ASR. |
| travel_24 / 695bd157 | Arguments | Same long-form inferred-year gap; spelled identifier dashes differ from reference. |

## Implications for the next design

- Fifteen failures selected the correct tool multiset but failed exact arguments; thirteen failed tool selection.
- A genuine adapter defect remains: inferred-year grounding only recognizes ISO output, so long-form model-added years escape it. Another is over-broad generic office article stripping.
- Several failures require better speech perception or action completion, rather than representational normalization.
- Some exact failures are semantically equivalent forms. Others need unspecified context or have conditional references inconsistent with the captured request and mock result. Do not make an unauthorized write, guess missing context, or rewrite the reference to force a pass.
- A controlled comparison with a newer supported Live model may help perception and SDK tool emission. Model-list access does not establish free-tier pricing/quota. No additional-model inference has been authorized or performed in this audit.
- Late tool calls warrant timing investigation. Extending the response window would change the harness and score interpretation; it must not be presented as a like-for-like performance gain.

The measured result remains **72/100**. This audit does not establish a 90% score or a counterfactual pass rate.
