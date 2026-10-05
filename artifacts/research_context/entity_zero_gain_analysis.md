# Forensic Analysis: Entity Resolver Zero-Gain Investigation

## 1. Executive Summary

In the initial failure attribution, **Wrong Transcription / Entity Resolution** was identified as the single largest failure category, accounting for **76 / 209 baseline failures (36.4%)** in v1 and **53 / 201 failures** in v3.

To address this, Component A (**Entity Resolver**) was implemented with multi-signal corroboration (exact ID, email, phone suffix, fuzzy name matching, and postal code verification) and calibrated to strict safety thresholds (`confidence_cutoff=0.88`, `margin_cutoff=0.10`) yielding 100% precision on synthetic benchmarks.

However, in the full v4 evaluation across all 278 tasks:
* **Full v4 Stack**: 58 / 278 (20.86%) Pass@1.
* **Without Entity Resolver (`wo_entity_resolver`)**: 58 / 278 (20.86%) Pass@1.
* **Measured Lift**: Exactly **0 tasks (0.00 pp lift)**.

An exhaustive forensic audit of all 159 entity-related tasks (recorded in [`entity_zero_gain.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/entity_zero_gain.json)) reveals the three empirical mechanisms causing this zero-gain result.

---

## 2. Root Cause Analysis: Why Entity Resolver Produced Zero Gain

### Mechanism 1: Absence of Active In-Memory Candidate Pools in Frozen Replay
In a live CRM deployment, an agent queries customer records (`search_customer_by_name`), loading candidate pools into memory for corroboration.
In τ-Voice's recorded offline trajectories:
1. Gemini often bypassed initial lookup queries or directly dispatched state mutations with ungrounded arguments.
2. During offline replay, no interactive query mechanism populated `entity_pool` dynamically before argument admission. Without candidate records to corroborate against, `EntityResolver.resolve()` correctly returned `NOT_FOUND`, leaving raw arguments unmutated.

### Mechanism 2: Strict Safety Cutoff vs Severe ASR Acoustic Corruption
The calibration report (`artifacts/tau_voice_v4/calibration_report.json`) proved that setting `confidence_cutoff < 0.88` introduces dangerous false positive identity misattributions.
In τ-Voice trajectories, spoken names suffered severe phonetic transcription corruptions from speech-to-text:
* e.g., Spoken name *"Aarav Ahmed"* transcribed as *"Arab Ahmad"*, *"Arif Amad"*, or entirely dropped.
* Sequence similarity scores between corrupted speech inputs and gold database identities frequently fell into the range **0.60 – 0.78**.
* Under conservative production thresholds (`confidence_cutoff=0.88`), the resolver correctly refused to guess, returning `LOW_CONFIDENCE` or `NOT_FOUND`.

### Mechanism 3: Fixed Trajectory Horizon (Downstream Failure Cascades)
In frozen offline replay, model outputs are pre-recorded:
* In tasks where an entity name might have been normalized, Gemini's subsequent pre-recorded actions in future turns still failed due to downstream tool selection errors, incorrect dates, or invalid flight numbers.
* In an interactive environment, resolving a customer's ID allows the model to receive valid reservation objects and plan correct subsequent steps. In frozen replay, the subsequent steps are fixed in stone; resolving an argument on tick 2 cannot fix a hallucinated flight number dispatched on tick 5.

---

## 3. Disambiguation & Interactive Clarification Bottleneck

When `EntityResolver` encounters multiple candidates (e.g. two customers sharing a name), it returns:
```python
EntityResolutionResult(status="AMBIGUOUS", details="Found multiple candidates")
```
In a live production voice agent, this triggers an interactive conversational repair:
> *"I see two accounts under that name. Could you please verify your billing zip code or the last four digits of your phone number?"*

In **offline frozen replay**, the user's recorded audio cannot answer this clarification question. The trajectory ends without resolution, and the task fails.

---

## 4. Methodological Conclusion

1. **Synthetic vs Benchmark Divergence**: 100% precision on an isolated synthetic calibration dataset does not translate to benchmark lift if the evaluation environment lacks dynamic candidate retrieval and multi-turn conversational repair.
2. **Headroom vs Recoverability**: While 53–76 tasks suffered from entity errors, they are **unrecoverable under frozen offline replay**. They can only be recovered in a **closed-loop live evaluation** where the agent can interactively query the database and prompt the user for clarifying attributes.
