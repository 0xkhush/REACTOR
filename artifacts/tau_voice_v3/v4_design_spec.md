# REACTOR v4: Generic Improvement Design Specification

**Status**: Pre-Implementation Design Specification (Frozen)  
**Target Benchmark**: τ-Voice (`sierra-research/tau2-bench`)  
**Guiding Principle**: Zero Benchmark-Specific Optimization (YAGNI / Ponytail)  
**Execution Safety Guarantee**: 0 Stale Writes, 0 Duplicate Operations

---

## 1. Forensic Bottleneck Analysis

Our forensic analysis of the 201 remaining τ-Voice failures revealed that **83.58% (168 tasks)** failed within the **Validation Layer**, while the core **REACTOR Execution Layer** achieved **100% safety fidelity** (0 stale writes, 0 duplicate mutations).

The three largest addressable failure bottlenecks are:
1. **Entity Resolution Fragility (53 tasks, 26.37%)**:
   - Audio transcription introduces minor phonetic variations ("Aarav" -> "Arab", "619 Broadway" -> "690 Broadway").
   - Direct database lookups (`find_user_id_by_name_zip`) fail completely on single-character mismatches because they perform strict equality.
2. **Policy Violation Failures (37 tasks, 18.41%)**:
   - LLMs frequently violate complex enterprise guidelines under conversational pressure (e.g., cancelling non-refundable tickets, returning orders that were never delivered, or bypassing cancellation fees).
   - v3 demonstrated that proactive environment database inspection successfully recovers these tasks without altering the execution core.
3. **Conversational Slot Drift & Recovery (6 tasks, 2.99%)**:
   - When an API call fails with a recoverable validation error, the model lacks a structured recovery pathway and either loops indefinitely or escalates prematurely.

---

## 2. Proposed v4 Generic Architecture

```
                                  VOICE INPUT (Audio Stream)
                                              ↓
                                 Model Semantic Proposal
                                              ↓
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                           REACTOR v4 GENERIC VALIDATION STACK                             │
│                                                                                           │
│  1. Actor Boundary & Escalation Gate                                                      │
│     ├── Distinguishes agent API tools from user device tools (prevents illegal calls)     │
│     └── Enforces escalation budget (blocks premature transfers)                           │
│                                                                                           │
│  2. Proposal Normalizer & AST Sanitizer                                                   │
│     ├── Recursively strips quote/whitespace artifacts from dictionary keys and values     │
│     └── Type coercion and enum normalization without value fabrication                    │
│                                                                                           │
│  3. Multi-Signal Entity Resolver (Candidate A)                                            │
│     ├── Multi-attribute corroboration (Name + ZIP + Email + Phone suffix)                 │
│     └── Strict confidence margin (>= 0.88 similarity, >= 0.10 margin)                     │
│                                                                                           │
│  4. Conversational State & Slot Provenance Manager (Candidate B)                         │
│     ├── Tracks active intent, confirmed slots, and invalidated slots                      │
│     └── Prevents regression to obsolete parameters across turns                           │
│                                                                                           │
│  5. Environment-Grounded Policy Engine                                                    │
│     ├── Queries live authoritative state prior to dispatch                                │
│     └── Blocks irreversible violations (fare rules, fulfillment status)                   │
│                                                                                           │
│  6. Bounded Recovery Manager (Candidate C)                                                │
│     └── Translates tool errors into machine-readable clarification prompts (max 2 retries)│
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                              ↓
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                         FROZEN REACTOR CORE EXECUTION ENGINE                              │
│                                                                                           │
│  • Monotonic Request Tokens & Revision Tracking                                           │
│  • Re-entrant Write Serialization Gate                                                    │
│  • Automatic Cancellation Cascades                                                        │
│  • Idempotency & Operation De-duplication                                                 │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                              ↓
                                       COMMITTED WRITE
```

---

## 3. Detailed Mechanism Specifications

### Candidate A: Generic Multi-Signal Entity Resolver
- **Generality Justification**: Operates on arbitrary candidate dictionaries exposed by the local application directory. Uses general mathematical distance metrics (Levenshtein, Jaro-Winkler) combined with attribute intersection. Zero knowledge of specific customer names or IDs.
- **Resolution Pipeline**:
  1. *Exact Stable ID*: If target ID exists in candidates, return `RESOLVED`.
  2. *Secondary Key Intersection*: If `email` or `phone` matches uniquely, return `RESOLVED`.
  3. *Corroborated Fuzzy Match*: If `name` similarity $\ge 0.88$ AND secondary attribute (e.g., ZIP code, domain of email) matches, return `RESOLVED`.
  4. *Ambiguity Gate*: If multiple candidates have similarity within $0.10$ margin, return `AMBIGUOUS`.
- **Safety Rule**: Never silently bind ambiguous identities; reject or prompt for clarification.

### Candidate B: Conversational State Manager
- **Generality Justification**: Tracks slot provenance independent of task domains. Maintains:
  ```python
  class SlotProvenance:
      slot_name: str
      value: Any
      intent_revision: int
      confirmed_by_user: bool
      invalidated: bool
  ```
- **Semantics**: When a user correction occurs (e.g., `"Actually, make that May 20th, not May 19th"`), the slot with name `"date"` is invalidated at revision $R$, while unaffected slots (`"origin"`, `"destination"`) remain confirmed.

### Candidate C: Bounded Recovery Manager
- **Generality Justification**: Maps HTTP/JSON-RPC error codes and Pydantic validation errors into structured recovery directives.
- **Policy**:
  - Maximum recovery budget: 2 attempts per logical action.
  - If identical error repeats twice, force conversational clarification rather than infinite looping.

### Candidate D: Result Verifier
- **Generality Justification**: Reads post-execution state returned by read APIs to verify that requested mutations took effect before issuing user-facing confirmations.

---

## 4. Expected Impact Range & Feasibility

| Mechanism | Addressable Failures | Conservative Recovery Rate | Projected Recovered Tasks | Projected Pass@1 Lift |
| :--- | :---: | :---: | :---: | :---: |
| **Multi-Signal Entity Resolver** | 53 tasks | 40% – 50% | +21 to +26 tasks | +7.5 to +9.3 pp |
| **Expanded Live-DB Policy Engine** | 37 tasks | 30% – 40% | +11 to +15 tasks | +3.9 to +5.4 pp |
| **Conversational State Tracking** | 6 tasks | 50% – 66% | +3 to +4 tasks | +1.0 to +1.4 pp |
| **Bounded Error Recovery** | 3 tasks | 66% – 100% | +2 to +3 tasks | +0.7 to +1.0 pp |
| **TOTAL POTENTIAL** | **99 tasks** | **~38% recovery** | **+37 to +48 tasks** | **+13.3 to +17.2 pp** |

*Note: These estimates represent potential headroom based on observed failure patterns, not guaranteed benchmark lifts.*

---

## 5. Regression Risks & Invariant Safeguards

1. **Risk of Over-Correction (False Positive Blocks)**:
   - *Risk*: A policy engine that is too strict might block legitimate exceptions or valid customer requests.
   - *Safeguard*: Policy rules must only block actions that are strictly forbidden by explicit domain schemas and authoritative environment state.
2. **Risk of Identity Misbinding**:
   - *Risk*: Permissive fuzzy matching might bind the wrong customer.
   - *Safeguard*: Enforce strict $0.88$ similarity threshold and $0.10$ confidence separation margin.
3. **Execution Safety Invariant Preservation**:
   - *Invariant*: Stale writes on superseded revisions must remain strictly **0**.
   - *Invariant*: Duplicate operations must remain strictly **0**.

---

## 6. Independent Synthetic Test Suite Requirements

Prior to evaluating against τ-Voice, all v4 mechanisms must pass an independent synthetic test suite:
- **Entity Resolution Suite**: 15 test cases verifying exact match, 1-character typo, phonetic variation, ambiguous candidates, and empty pool.
- **Conversational State Suite**: 10 test cases verifying slot preservation across revisions, slot invalidation on correction, and cross-turn consistency.
- **Recovery Manager Suite**: 8 test cases verifying bounded retry counts, escalation after 2 identical failures, and schema error translation.
- **Controller Safety Suite**: 32 existing unit tests verifying re-entrancy prevention, write gate locks, and cancellation cascades.

---

## 7. Frozen Components

The following modules must remain strictly unchanged:
- `src/reactor/controller.py` (Core controller)
- `src/reactor/state.py` (State dataclasses)
- `vendor/tau2-bench/` (Official benchmark code and data)
