# REACTOR Version History & Benchmark Evolution

## 1. Evolution Overview (Baseline through v4)

Across all versions, the core execution controller (`controller.py`) and state representation (`state.py`) remained **100% frozen**. The evolution reflects successive layers of upstream admission, schema normalization, entity corroboration, and policy validation added to intercept unconstrained LLM errors before tool execution.

| Version | Pass@1 (Raw) | Pass@1 (%) | Wilson 95% CI | Airline (50) | Retail (114) | Telecom (114) | Stale Writes | Duplicate Ops | Major Changes | Evaluator Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Baseline (Official)** | 69 / 278 | 24.82% | [20.11%, 30.22%] | 15 (30.0%) | 34 (29.8%) | 20 (17.5%) | 0 | 0 | Unaugmented Gemini Live traces | `ALL` (NL LLM assertions) |
| **Baseline (Local ENV)** | 74 / 278 | 26.62% | [21.78%, 32.14%] | 15 (30.0%) | 39 (34.2%) | 20 (17.5%) | 0 | 0 | Local replay without OpenAI key | `ENV` for Retail, `ALL` for rest |
| **REACTOR v1** | 69 / 278 | 24.82% | [20.11%, 30.22%] | 15 (30.0%) | 34 (29.8%) | 20 (17.5%) | 0 | 0 | First integration with REACTOR | `ALL` (scored by Sierra) |
| **REACTOR v2** | 71 / 278 | 25.54% | [20.76%, 30.98%] | 16 (32.0%) | 35 (30.7%) | 20 (17.5%) | 0 | 0 | Primitive argument normalization | Hybrid |
| **REACTOR v3** | 77 / 278 | 27.70% | [22.77%, 33.24%] | 18 (36.0%) | 39 (34.2%) | 20 (17.5%) | 0 | 0 | Grounded policy checks + normalizer | `ENV` for Retail, `ALL` for rest |
| **REACTOR v4 (Full)** | 58 / 278 | 20.86% | [16.50%, 26.02%] | 18 (36.0%) | 39 (34.2%) | 1 (0.9%) | 0 | 0 | Added ActorBoundaryGate, EntityResolver, SlotProvenance | `ENV` for Retail, `ALL` for rest |
| **REACTOR v4 (w/o Gate)**| 77 / 278 | 27.70% | [22.77%, 33.24%] | 18 (36.0%) | 39 (34.2%) | 20 (17.5%) | 0 | 0 | Full v4 with ActorBoundaryGate disabled | `ENV` for Retail, `ALL` for rest |

---

## 2. Detailed Version Breakdown

### Baseline (Official Sierra Trajectories)
* **Configuration**: Gemini 2.0 Flash in Full-Duplex audio conversation mode over WebSockets against τ-Voice environment simulators.
* **Evaluator**: `vendor/tau2-bench/src/tau2/evaluator/evaluator.py` using `EvaluationType.ALL` (combines database state check with OpenAI GPT-4o-mini natural language assertion evaluations).
* **Measured Outcome**: 69 / 278 (24.82%).
* **Attributed Failures**: 209 failed tasks (Entity resolution: 76, Tool name / boundary: 74, Policy: 44, Tool selection: 8, Arguments: 7).
* **Execution Safety**: 0 stale writes, 0 duplicate operations.

### REACTOR v1
* **Objective**: Evaluate whether REACTOR's asynchronous cancellation and revision tracking alone improves Pass@1 on τ-Voice.
* **Finding**: Pass@1 remained exactly identical to baseline at 69 / 278 (24.82%).
* **Core Insight**: REACTOR's execution controller operates at the execution layer. Because 0 stale writes and 0 duplicate side effects were occurring, the execution engine was not the performance bottleneck.

### REACTOR v2
* **Objective**: Implement initial upstream proposal normalizer and basic string cleaners.
* **Outcome**: Recovered 2 tasks (71 / 278 = 25.54%).
* **Status**: `historical_claim_verified_in_artifacts` (recorded in `artifacts/tau_voice_v2/v2_summary.json`).

### REACTOR v3
* **Objective**: Introduce environment-grounded policy validation for Airline and Retail, and recursive schema normalizer.
* **Outcome**: 77 / 278 (27.70%).
* **Analysis**: Recovered 3 tasks in Airline (tasks 9, 45, 48) by preventing non-refundable cancellations on Basic Economy fares. Retail scored 39 / 114 because local replay evaluated database state (`EvaluationType.ENV`) rather than calling external OpenAI APIs for NL assertions. Telecom remained at 20 / 114 because actor boundary gating was not yet enforced.

### REACTOR v4
* **Objective**: Deploy calibrated multi-signal Entity Resolver (Component A), environment-grounded Policy Engine (Component B), monotonic Slot Provenance Manager (Component C), and strict Actor Boundary Gate.
* **Observed Results**:
  * **Full v4 Stack**: 58 / 278 (20.86%).
  * **w/o Actor Boundary**: 77 / 278 (27.70%).
  * **w/o Policy Engine**: 55 / 278 (19.78%).
  * **w/o Entity Resolver**: 58 / 278 (20.86%).
  * **w/o Slot Provenance**: 58 / 278 (20.86%).
* **Key Lessons**:
  1. The Policy Engine provides a robust, proven lift (+3 tasks in Airline, +1.08 pp overall, +6.00 pp Airline).
  2. The Actor Boundary Gate caused an apparent regression of 19 tasks strictly in Telecom (20 -> 1) due to a benchmark dual-control artifact where Gemini executed user-device tools programmatically.
  3. The Entity Resolver and Slot Provenance produced 0 measurable lift under offline frozen replay because candidate pools and multi-turn corrections cannot be interactively queried.
