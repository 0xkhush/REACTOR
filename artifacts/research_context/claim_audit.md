# Scientific & Empirical Claim Audit

## 1. Audit Framework & Classification Standards

Every technical and empirical claim made in REACTOR documentation, reports, and README files is classified under one of four rigorous scientific categories:
* **DIRECTLY MEASURED**: Supported by reproducible, quantitative experimental data collected directly from raw repository artifacts.
* **SUPPORTED INFERENCE**: Logically and mechanistically derived from directly measured evidence and source code, but not directly observable as an isolated numerical metric.
* **THEORETICAL / COUNTERFACTUAL**: A modeled projection, design hypothesis, or synthetic calibration result that has not yet been demonstrated to produce end-to-end benchmark lift.
* **UNSUPPORTED**: Any claim lacking empirical evidence, contradicted by raw data, or based on unverified assumptions.

---

## 2. Comprehensive Claim Audit Matrix

| Scientific / Technical Claim | Claim Category | Audit Status & Evidentiary Support |
| :--- | :--- | :--- |
| **"REACTOR achieves 0 stale writes across all benchmark simulations."** | **DIRECTLY MEASURED** | **VERIFIED**. Across all 1,668 simulation runs in the v4 ablation suite, exactly 0 stale writes were committed ($R_{\text{intent}} < R_{\text{active}}$). |
| **"REACTOR achieves 0 duplicate operations across all benchmark simulations."** | **DIRECTLY MEASURED** | **VERIFIED**. Across all 1,668 simulation runs, attempted duplicate proposals were intercepted by the idempotency cache with 0 duplicate committed side effects. |
| **"Policy Engine improves Airline Pass@1 by +6.00 pp (+3 tasks)."** | **DIRECTLY MEASURED** | **VERIFIED**. Direct ablation comparison (`full_v4_stack` vs `wo_policy_engine`) confirms tasks 9, 45, and 48 recovered from 0.0 to 1.0 reward by blocking non-refundable cancellations. |
| **"Full v4 stack regressed from 77 to 58 passes (-19 tasks) due to Actor Boundary Gate."** | **DIRECTLY MEASURED** | **VERIFIED**. Exactly 19 tasks regressed between `wo_actor_boundary` (77 passes) and `full_v4_stack` (58 passes), 100% of which are in Telecom. |
| **"The 19 Telecom regressions are an artifact of offline frozen replay."** | **SUPPORTED INFERENCE** | **HIGH CONFIDENCE**. Source code confirms all blocked tools (`toggle_airplane_mode`, `reseat_sim_card`, etc.) are owned by `env.user_tools`. In offline replay, the frozen user transcript cannot take over execution. |
| **"In standard enterprise domains (Airline & Retail), REACTOR v4 lifts Pass@1 by +4.88 pp."** | **DIRECTLY MEASURED** | **VERIFIED**. In domains without user-device dual-control tools, REACTOR v4 scores 57 / 164 (34.76%) vs Sierra baseline 49 / 164 (29.88%). |
| **"Baseline Pass@1 is 69 / 278 (24.82%) under official Sierra scoring."** | **DIRECTLY MEASURED** | **VERIFIED**. Summing `reward_info.reward` across all 281 trajectory JSON files yields exactly 69 passes (15 Airline, 34 Retail, 20 Telecom). |
| **"Local offline baseline is 74 / 278 (26.62%) due to Retail DB-only scoring."** | **DIRECTLY MEASURED** | **VERIFIED**. Exactly 5 retail tasks (24, 29, 46, 47, 105) have `DB: 1.0` and `NL_ASSERTION: 0.0`. Evaluating with `EvaluationType.ENV` scores them 1.0, yielding 74 passes. |
| **"Entity Resolver operates with 100% precision and 0 false positives."** | **THEORETICAL (CALIBRATION ONLY)** | **RESTRICTED TO SYNTHETIC BENCHMARK**. 100% precision was measured exclusively on the synthetic calibration dataset (`scripts/calibrate_entity_resolver.py`). On the τ-Voice benchmark, the resolver produced **0.00 pp lift**. |
| **"Up to 128 failures in τ-Voice are generically recoverable."** | **THEORETICAL / COUNTERFACTUAL** | **UNPROVEN HEADROOM**. Forensic classification identified 128 failures caused by upstream perception and boundary issues, but this represents potential headroom, not measured recovery. |
| **"Slot Provenance Manager restores lost conversational context."** | **THEORETICAL (BENCHMARK REPLAY)** | **UNPROVEN IN REPLAY**. The mechanism recovered 1 slot in the dataset, but produced **0.00 pp Pass@1 lift** under offline frozen trajectory replay. |
| **"REACTOR achieved SOTA (27.70%) on τ-Voice."** | **SUPPORTED INFERENCE (WITH CAVEATS)** | **QUALIFIED**. 77 / 278 (27.70%) was achieved in v3 and in v4 when Actor Boundary Gate was disabled (`wo_actor_boundary`). With strict actor boundary gating active, the score is 58 / 278 (20.86%). |

---

## 3. Mandatory Epistemic Disclaimers for Future Research

1. **Do not equate synthetic calibration accuracy with benchmark gain**: Component A achieved 100% precision on synthetic tests, but yielded zero gain on the real benchmark.
2. **Do not optimize execution concurrency to fix Pass@1**: Execution safety is already operating at 100% precision (0 stale, 0 duplicate).
3. **Do not treat offline replay as equivalent to live interaction**: Offline replay penalizes production role boundaries because simulated users cannot execute instructions verbally given to them.
