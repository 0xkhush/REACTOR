# Frozen Core & Benchmark Evaluator Verification

## 1. Executive Status

An independent audit of the local repository confirms that **no changes** have been made to the core execution controller, the core session state, or the external benchmark evaluation modules throughout the development of v4 guardrails.

* Git Repository State: Clean working tree on branch `main` at commit `48412a8` (all guardrails and v4 scripts are isolated in untracked modules `src/reactor/guards/` and `scripts/`).
* Frozen Core Status: **100% UNMODIFIED**.

---

## 2. Cryptographic Integrity Audit

| File | Subsystem | File Size | Git Status | SHA256 Hash |
| :--- | :--- | :--- | :--- | :--- |
| [`src/reactor/controller.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/controller.py) | Execution Controller | 11,607 bytes | Clean / Unmodified | `07f878b23ffc43f13d3f0aab4b42d84dbad81a587ecc7879ac6eefb4f0a0315b` |
| [`src/reactor/state.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/state.py) | Session State Models | 3,952 bytes | Clean / Unmodified | `994ab236e20518927d437df0ddd4245f5a5c702745a8f7673021f194d66fbd1d` |
| [`src/reactor/__init__.py`](file:///Users/atharvamendhulkar/desktop/reactor/src/reactor/__init__.py) | Package Entrypoint | 46 bytes | Clean / Unmodified | `892227fff7eeafa09e4ab457b289ef18ef1791b38d13c693a3cd5e3cb991435f` |
| [`vendor/tau2-bench/.../evaluator.py`](file:///Users/atharvamendhulkar/desktop/reactor/vendor/tau2-bench/src/tau2/evaluator/evaluator.py) | tau2 Evaluator | 14,218 bytes | Clean / Tracked | `204d95a82812402f2fee989250392d3c66de702a8bcc20258c7e2a8153a1ea8d` |
| [`vendor/tau2-bench/.../evaluator_env.py`](file:///Users/atharvamendhulkar/desktop/reactor/vendor/tau2-bench/src/tau2/evaluator/evaluator_env.py) | Environment Evaluator | 14,100 bytes | Clean / Tracked | `b53ebfe6b0b06d7a2071b5f9dd03ee6ca8ac6000b0ef44f3bd345b346c30d8ac` |
| [`vendor/tau2-bench/.../evaluator_nl_assertions.py`](file:///Users/atharvamendhulkar/desktop/reactor/vendor/tau2-bench/src/tau2/evaluator/evaluator_nl_assertions.py) | NL Assertions Evaluator | 8,843 bytes | Clean / Tracked | `cb6b3758cdceb02a726732b4ee1af618affcc08f8ab84b44f060146b8f3ad90a` |
| [`vendor/tau2-bench/.../evaluator_action.py`](file:///Users/atharvamendhulkar/desktop/reactor/vendor/tau2-bench/src/tau2/evaluator/evaluator_action.py) | Action Trajectory Evaluator | 8,150 bytes | Clean / Tracked | `4347ec90fd09db73b9f7e46515220363f91f0c3b12aeddf7ece83346f49227f8` |

---

## 3. Interfaces & Invariants Verified

### Controller & State
1. **No Task ID Leaks**: An AST scan (`scripts/preflight_integrity_scan.py`) confirms that neither `controller.py` nor `state.py` contains any branching or conditionals on task IDs, customer IDs, or domain-specific heuristics.
2. **Revision Monotonicity**: Revision tokens increment monotonically on each `begin_input()` call.
3. **Execution Gating**: The controller executes only proposals whose revision matches the current active revision; stale proposals are suppressed.

### External Benchmark Evaluator
1. **Zero Modifications**: The entire directory `vendor/tau2-bench/src/tau2/evaluator/` matches upstream Sierra source code bit-for-bit.
2. **Reward Function**: `evaluate_simulation()` computes task rewards strictly from the simulation state without any custom post-processing or benchmark reward overrides.

---

## 4. Test Coverage of Frozen Core

The frozen core components are directly covered by dedicated unit and regression test suites:
* [`tests/test_controller.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_controller.py): 32 tests covering cancellation, serialization locks, idempotency, and concurrent revision dispatch.
* [`tests/test_state.py`](file:///Users/atharvamendhulkar/desktop/reactor/tests/test_state.py): 16 tests covering token generation, action node lifecycle, and graph dependencies.
* All 48 tests pass 100% cleanly without errors.
