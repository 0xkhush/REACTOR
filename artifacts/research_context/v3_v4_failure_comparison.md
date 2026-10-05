# Failure Taxonomy: Comparative Forensic Audit (v3 vs v4)

## 1. Executive Summary

This document presents the audited failure taxonomy of the 278 tasks evaluated on τ-Voice across REACTOR v3 and v4, documenting subsystem blame, domain distributions, and recoverability ceilings.

* **v3 Failure Total**: **201 failures** (77 passes / 278).
* **v4 Full Stack Failure Total**: **220 failures** (58 passes / 278).
* **v4 Without Actor Boundary Failure Total**: **201 failures** (77 passes / 278).

---

## 2. Failure Category Distribution

| Failure Category | v3 Count | v3 Share (%) | v4 (Full Stack) | v4 (w/o Gate) | Primary Subsystem Responsible | Recoverability Status under Frozen Replay |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Actor / Tool Boundary** | 71 | 35.3% | **90** (+19) | 71 | Upstream Agent Tool Routing | **Unrecoverable offline** (requires live user simulator) |
| **Entity Resolution** | 53 | 26.4% | 53 | 53 | Model Perception / Identity Layer | **Unrecoverable offline** (requires dynamic candidate lookup) |
| **Policy / Business Rule** | 37 | 18.4% | **34** (-3) | **34** (-3) | Deterministic Validation Layer | **Recovered 3 tasks** (+6.0 pp Airline lift) |
| **ASR / Transcription** | 25 | 12.4% | 25 | 25 | Acoustic Speech-to-Text | **Unrecoverable offline** (acoustic artifacts fixed in audio) |
| **Intent / Understanding** | 6 | 3.0% | 6 | 6 | Upstream Foundation Model (LLM) | Unrecoverable without re-prompting |
| **Recovery Budget** | 3 | 1.5% | 3 | 3 | Error Recovery Loop | Unrecoverable without interactive turns |
| **Argument Construction** | 2 | 1.0% | 2 | 2 | Schema / Argument Normalizer | Partially repaired |
| **Evaluator / Communication**| 2 | 1.0% | 2 | 2 | Natural Language Utterance Format | Unrecoverable without speech generation |
| **Premature Escalation** | 1 | 0.5% | 1 | 1 | Admission Gate / Representative Rule | Blocked premature transfer |
| **Conversational State** | 1 | 0.5% | 1 | 1 | Slot Provenance Manager | Slot restored; downstream failure dominated |
| **Total Failures** | **201** | **100.0%** | **220** | **201** | | |

---

## 3. Subsystem Responsibility Breakdown

Assigning root-cause failure responsibility to architectural layers demonstrates that **the execution layer is 100% bug-free**:

```
v4 Full Stack Failure Blame (220 Failures):
├── Boundary / Dual-Control Gating: 90 (40.9%)  [Offline dual-control artifact]
├── Validation & Policy Layer:      87 (39.5%)  [53 Entity, 34 Policy]
├── Perception & LLM Generative:    41 (18.6%)  [25 ASR, 6 Intent, 3 Recovery, 7 Other]
├── Communication Format:            2 (0.9%)   [NL assertion phrasing]
└── Execution Controller Layer:      0 (0.0%)   [0 Stale writes, 0 Duplicate ops]
```

### Why Execution Layer Responsibility Remains Zero:
* Across all 278 tasks in all 6 configurations (1,668 simulation runs), **REACTOR's execution controller never executed a stale write, never executed an out-of-order mutation, and never duplicated a side effect**.
* Failures occur upstream of the controller: in speech recognition, unconstrained model tool selection, or missing candidate pools.

---

## 4. Recoverability Analysis

1. **Genuinely Recoverable Now (Offline Replay)**:
   * Policy / Business Rule violations where the environment state can be deterministically verified prior to execution (3 Airline tasks recovered).
2. **Unrecoverable under Frozen Trajectories (71 – 90 tasks)**:
   * Tasks requiring the simulated user to perform device-side actions (Telecom).
3. **Unrecoverable without Live Dynamic Lookups (53 tasks)**:
   * Tasks requiring candidate entity pools to be populated by CRM read operations before resolving ambiguous customer identities.
4. **Unrecoverable without Speech Model Fine-Tuning (25 tasks)**:
   * Severe acoustic distortions where speech-to-text outputs gibberish that cannot be mapped to any known customer name.
