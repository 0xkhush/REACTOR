# REACTOR Repository Inventory and Research Tree

## 1. Top-Level Directory Layout

```
.
├── artifacts/                  # Benchmark runs, trajectory datasets, evaluation reports
│   ├── research_context/       # Self-contained research dossier & audit package
│   ├── tau_voice/              # v1 frozen baseline evaluation artifacts (278 tasks)
│   ├── tau_voice_v2/           # v2 evaluation artifacts & initial guardrails
│   ├── tau_voice_v3/           # v3 failure forensics & SOTA run artifacts
│   └── tau_voice_v4/           # v4 official evaluation, ablations, & calibration report
├── configs/                    # Hydra and experiment runtime configurations
├── docs/                       # Architectural specs, RFCs, and API documentation
├── notebooks/                  # Interactive analysis, visualization, and audio exploration
├── scripts/                    # Benchmark harnesses, evaluation scripts, and calibration tools
├── src/                        # Core production source code
│   └── reactor/                # REACTOR package
│       ├── controller.py       # [FROZEN] Core execution controller and cancellation engine
│       ├── state.py            # [FROZEN] SessionState, revisions, tokens, and action states
│       ├── guards/             # Upstream proposal validation, boundary, & policy guardrails
│       └── tools/              # Tool definitions, interfaces, and registries
├── tests/                      # Pytest suite (480 total tests, 92 v4 guardrail tests)
└── vendor/                     # Tracked external benchmark suites
    ├── Full-Duplex-Bench/      # Full-duplex conversational audio benchmark
    └── tau2-bench/             # Sierra tau2 benchmark suite (airline, retail, telecom)
```

---

## 2. Core Execution Engine (`src/reactor/`)

* [`src/reactor/controller.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/controller.py):
  * **Status**: **FROZEN CORE**.
  * **Role**: Deterministic execution controller for interruptible, real-time voice agents.
  * **Key Primitives**: `Controller` class managing revision tokens, asynchronous action queues, cancellation cascades, write serialization, and idempotency protection.
  * **Safety Guarantees**: Guarantees that stale proposals (intent revision < active revision) never commit side effects and idempotent operations are deduplicated.
* [`src/reactor/state.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/state.py):
  * **Status**: **FROZEN CORE**.
  * **Role**: State definitions and lifecycle models.
  * **Key Models**: `SessionState`, `RequestToken`, `Proposal`, `ExecutionResult`, `ActionNode`, `ActionState` (enum: PENDING, DISPATCHED, COMPLETED, CANCELLED, FAILED).
* [`src/reactor/tools/base.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/tools/base.py):
  * **Role**: Standardized tool interface defining execution handlers, schemas, and state-modifying flags.

---

## 3. Upstream Proposal Validation & Guardrails (`src/reactor/guards/`)

* [`src/reactor/guards/__init__.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/__init__.py):
  * **Role**: Exposes the modular guardrail subsystem and the unified validation pipeline.
* [`src/reactor/guards/boundary.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/boundary.py):
  * **Role**: Implements `ActorBoundaryGate` and `ToolAdmissionResult`. Enforces strict actor-role boundaries (blocking agent from executing user-side device actions and ensuring tools match the active domain).
* [`src/reactor/guards/normalizer.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/normalizer.py):
  * **Role**: Implements `ProposalNormalizer`. Recursively sanitizes JSON strings, handles casing/type coercions, strips quotation artifacts, and normalizes date/boolean formats against JSON schemas.
* [`src/reactor/guards/entity.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/entity.py):
  * **Role**: Implements `EntityResolver` (Component A). Performs multi-signal corroboration (exact ID, email, phone suffix, name similarity, and postal code cross-validation) with conservative safety cutoffs (`confidence_cutoff=0.88`, `margin_cutoff=0.10`).
* [`src/reactor/guards/policy.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/policy.py):
  * **Role**: Implements `PolicyEngine` (Component B). Deterministic policy validation inspecting authoritative domain state (e.g. blocking basic economy ticket cancellations without insurance, enforcing retail order return windows, and checking customer KYC).
* [`src/reactor/guards/provenance.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/provenance.py):
  * **Role**: Implements `SlotProvenanceManager` and `SlotRecord` (Component C). Monotonically tracks slot bindings across conversation turns, recording source, timestamp, and revision to enable context recovery after interruptions.
* [`src/reactor/guards/pipeline.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/pipeline.py):
  * **Role**: Unified pipeline orchestrator sequentially routing proposed actions through:
    1. Actor Boundary Gate
    2. Proposal Normalizer
    3. Slot Provenance Recovery
    4. Entity Resolver
    5. Policy Engine
    6. REACTOR Execution Controller Admission
* [`src/reactor/guards/types.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/guards/types.py):
  * **Role**: Common data types including `ToolSpec`, `ToolAdmissionResult`, `EntityResolutionResult`, and `PolicyEvaluationResult`.

---

## 4. Benchmark Harnesses & Scripts (`scripts/`)

* [`scripts/run_tau_voice_v4_evaluation.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/run_tau_voice_v4_evaluation.py):
  * **Role**: Official v4 evaluation and ablation runner. Evaluates all 278 tasks across 6 configurations (`full_v4_stack`, `wo_entity_resolver`, `wo_policy_engine`, `wo_slot_provenance`, `wo_actor_boundary`, `frozen_baseline`).
* [`scripts/calibrate_entity_resolver.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/calibrate_entity_resolver.py):
  * **Role**: Calibration suite testing multi-signal entity matching across candidate pools to maximize F1 while strictly guaranteeing zero false positives (calibrated parameters: `confidence_cutoff=0.88`, `margin_cutoff=0.10`).
* [`scripts/preflight_integrity_scan.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/preflight_integrity_scan.py):
  * **Role**: Static AST analysis verifying benchmark integrity: scans for hardcoded task IDs, environment tampering, oracle leaks, and evaluator modifications.
* [`scripts/forensic_analysis_v4.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/forensic_analysis_v4.py):
  * **Role**: Comprehensive forensic analyzer diagnosing failure mechanisms across trajectories.
* [`scripts/tau_voice_adapter.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/tau_voice_adapter.py):
  * **Role**: Simulation runner bridging tau2-bench environments and trajectories with REACTOR's controller.
* [`scripts/run_tau_voice_evaluation.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/run_tau_voice_evaluation.py):
  * **Role**: Original v1 baseline evaluation script.
* [`scripts/run_tau_voice_v2_evaluation.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/run_tau_voice_v2_evaluation.py):
  * **Role**: v2 evaluation harness.
* [`scripts/run_tau_voice_v3_sota.py`](file:///Users/atharvamendhulkar/desktop/reactor/scripts/run_tau_voice_v3_sota.py):
  * **Role**: v3 evaluation harness reporting 77 / 278 (27.70%).

---

## 5. Test Suites (`tests/`)

* [`tests/test_v4_guardrails.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_v4_guardrails.py):
  * **Role**: 92 unit and integration tests strictly validating v4 components (Entity Resolver, Policy Engine, Slot Provenance, and Actor Boundary Gate).
* [`tests/test_controller.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_controller.py):
  * **Role**: Core controller tests validating cancellation cascades, execution queues, write serialization, and idempotency.
* [`tests/test_state.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_state.py):
  * **Role**: Validates `SessionState`, revision monotonicity, and proposal status transitions.
* [`tests/test_argument_normalization.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_argument_normalization.py):
  * **Role**: Unit tests for schema validation and recursive argument normalization.
* [`tests/test_v2_guardrails.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_v2_guardrails.py):
  * **Role**: Tests for v2 guardrail behaviors.
* [`tests/test_tau_voice_adapter.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_tau_voice_adapter.py):
  * **Role**: Adapter regression tests ensuring compatibility with tau2 simulation data models.

---

## 6. Evaluation Artifacts & Data (`artifacts/`)

* `artifacts/tau_voice/`:
  * `official_trajectories/`: 281 trajectory JSON files (278 unique tasks: 50 airline, 114 retail, 114 telecom) recorded from Gemini Live conversations on τ-Voice.
  * `summary.json`: Original v1 summary reporting 69 / 278 (24.82%).
  * `failure_attribution.json`: Initial 209 failure attribution breakdown.
* `artifacts/tau_voice_v3/`:
  * `failure_analysis.json`: Granular record of all 201 failure cases in v3 with primary/secondary classifications, first failure points, and evidence.
  * `v3_summary.json`: Summary reporting 77 / 278 (27.70%).
* `artifacts/tau_voice_v4/`:
  * `v4_summary.json`: Primary v4 summary reporting 58 / 278 (20.86%).
  * `v4_ablation.json`: Full 6-configuration ablation results.
  * `v4_results.jsonl`: Per-task primary evaluation results.
  * `calibration_report.json`: Calibration results of Entity Resolver.
  * `preflight_integrity.json`: Static analysis integrity audit report.
* `artifacts/research_context/`:
  * All granular audit files, task-level JSONL records, and markdown analyses compiled for independent review.

---

## 7. Vendor Benchmarks (`vendor/`)

* `vendor/tau2-bench/`:
  * **Source**: Sierra Research `tau2-bench`.
  * **Evaluator**: [`vendor/tau2-bench/src/tau2/evaluator/evaluator.py`](file:///Users/atharvamendhulkar/desktop/reactor/vendor/tau2-bench/src/tau2/evaluator/evaluator.py).
  * **Tasks**: 50 Airline tasks, 114 Retail tasks, 114 Telecom tasks.
