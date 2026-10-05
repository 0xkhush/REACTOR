# Forensic Investigation: Baseline Reproducibility Discrepancy (69 vs 74 Passes)

## 1. Executive Summary

An apparent discrepancy exists across benchmark documentation and evaluation artifacts regarding the frozen baseline Pass@1 score on τ-Voice:
* **Historical Baseline (v1/v2/v3 Reports)**: **69 / 278 = 24.82%** (Airline: 15/50, Retail: 34/114, Telecom: 20/114).
* **Current v4 Frozen Baseline Artifact (`v4_ablation.json`)**: **74 / 278 = 26.62%** (Airline: 15/50, Retail: 39/114, Telecom: 20/114).
* **Net Discrepancy**: $+5\text{ tasks}$ ($+1.80\text{ pp}$), located exclusively in the **Retail** domain.

An exhaustive file-level forensic audit of the official trajectory files in `artifacts/tau_voice/official_trajectories/` and the evaluation harness in `scripts/run_tau_voice_v4_evaluation.py` has identified the exact, verified root cause. **100% of the discrepancy is explained by a difference in evaluator configuration (`EvaluationType.ALL` vs `EvaluationType.ENV`) in the Retail domain.**

---

## 2. Mathematical & Empirical Proof

### A. Trajectory File Inspection
In `artifacts/tau_voice/official_trajectories/retail/`, each trajectory JSON file contains precomputed evaluation results stored in `reward_info`:
```json
{
  "task_id": "47",
  "reward_info": {
    "reward": 0.0,
    "reward_breakdown": {
      "DB": 1.0,
      "NL_ASSERTION": 0.0
    }
  }
}
```
Summing `reward_info.reward` across all 278 official trajectory files yields:
* Airline: 15 / 50
* Telecom: 20 / 114
* Retail: **34 / 114**
* **Total Official Baseline**: **69 / 278 (24.82%)**.

### B. Local Replay Harness Configuration
In [`scripts/run_tau_voice_v4_evaluation.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/run_tau_voice_v4_evaluation.py), line 273 specifies:
```python
eval_type = EvaluationType.ENV if domain == "retail" else EvaluationType.ALL
```
* **Why this was configured**: In the Retail domain, running `EvaluationType.ALL` requires querying external OpenAI LLM APIs (specifically `gpt-4o-mini` via LiteLLM) to score natural language assertions against conversational speech. When running offline local evaluations without an active OpenAI API key, `EvaluationType.ALL` throws an authentication error or crashes. Therefore, the harness evaluated Retail using pure database state assertions (`EvaluationType.ENV`).

### C. The 5 Discrepant Tasks Identified
Under `EvaluationType.ENV`, the evaluator inspects **only** the simulated SQL/database state (`DB: 1.0`). Exactly 5 tasks in Retail satisfied the database state perfectly (`DB: 1.0`) but had failed natural language assertions (`NL_ASSERTION: 0.0`) in Sierra's original run:

| Task ID | Official Trajectory File | DB Score | NL Assertion Score | Sierra Reward (`ALL`) | Local Replay Reward (`ENV`) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Task 24** | `6c51d53c-b3e1-452c-aacc-49a5ee9efb66.json` | **1.0** | **0.0** | 0.0 (FAIL) | **1.0 (PASS)** |
| **Task 29** | `d4e35141-7a6d-4397-91dc-c84d7a908804.json` | **1.0** | **0.0** | 0.0 (FAIL) | **1.0 (PASS)** |
| **Task 46** | `6257d411-a034-4820-ad28-4e73ea873420.json` | **1.0** | **0.0** | 0.0 (FAIL) | **1.0 (PASS)** |
| **Task 47** | `a91f057c-df7d-4da0-9da5-a2109fe8a890.json` | **1.0** | **0.0** | 0.0 (FAIL) | **1.0 (PASS)** |
| **Task 105**| `66c34512-5801-43ec-9c98-3980d16b14e2.json` | **1.0** | **0.0** | 0.0 (FAIL) | **1.0 (PASS)** |

$$34\text{ (Official Passes)} + 5\text{ (ENV-only Passes)} = 39\text{ Passes in Retail}$$
$$69\text{ (Official Total)} + 5\text{ (Retail Delta)} = 74\text{ Passes Overall (26.62\%)}$$

---

## 3. Methodological Significance

1. **Both Baselines are Mathematically Legitimate**:
   * **69 / 278 (24.82%)** is the **Strict End-to-End Baseline** requiring both database accuracy and OpenAI LLM conversational assertion approval.
   * **74 / 278 (26.62%)** is the **Deterministic Database Baseline** measuring backend database state mutations exclusively in Retail.
2. **Component Lift is Invariant**:
   * The Policy Engine's $+3\text{ task}$ lift is strictly in Airline (15 -> 18), completely independent of Retail's evaluator mode.
   * The Actor Boundary Gate's $-19\text{ task}$ delta is strictly in Telecom (20 -> 1), completely independent of Retail's evaluator mode.
   * Whether evaluating against 69 or 74, the relative deltas across all ablation configurations remain mathematically identical.
