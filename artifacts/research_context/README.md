# REACTOR Research Context Package

## Executive Overview

This package is an auditable, self-contained, evidence-based research context archive for the **REACTOR** (Robust Execution & Asynchronous Cancellation for Tool-Oriented Reasoning) project. It was compiled through automated forensic analysis, code inspection, and comprehensive ablation re-evaluations across all 278 tasks of the **τ-Voice** (tau2-bench) benchmark.

The purpose of this package is to allow an independent AI research engineer or external reviewer to understand:
1. What REACTOR is and how its execution engine and validation guards are implemented.
2. What has actually been measured across benchmark evolutions (baseline, v1, v2, v3, v4).
3. The exact mechanics behind the observed gains (e.g. Policy Engine +1.08 pp lift overall, +6.00 pp Airline lift).
4. The exact mechanics behind the observed regressions (e.g. Actor Boundary Gate regression of 19 tasks in Telecom).
5. The forensic reasons why certain components yielded zero measurable gain under offline replay (e.g. Entity Resolver and Slot Provenance).
6. The exact mathematical resolution of historical baseline reproducibility discrepancies (69 / 278 vs 74 / 278).
7. The verifiable proof of execution safety invariants (0 stale writes, 0 duplicate operations across 1,668 simulation runs).
8. The unresolved questions, benchmark limitations, and empirical boundaries governing any future v5 decisions.

---

## File Manifest

| File | Purpose | Key Artifacts / Evidence |
| :--- | :--- | :--- |
| [`research_context_bundle.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/research_context_bundle.md) | **Monolithic Self-Contained Research Dossier** | Complete 24-section executive & technical breakdown |
| [`v4_complete_task_context.jsonl`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/v4_complete_task_context.jsonl) | **Complete Task-Level Dataset (278 records)** | Per-task decisions across all 6 ablation configurations |
| [`actor_boundary_regressions.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/actor_boundary_regressions.json) | **19 Regressed Tasks (Telecom)** | Tool traces, blocked calls, and benchmark limitation audit |
| [`actor_boundary_analysis.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/actor_boundary_analysis.md) | **Forensic Analysis of Actor Boundary** | Dual-control benchmark conflict & device-side tool ownership |
| [`policy_recoveries.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/policy_recoveries.json) | **3 Recovered Tasks (Airline)** | Tasks 9, 45, 48: basic economy non-refundable cancellations |
| [`policy_gain_analysis.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/policy_gain_analysis.md) | **Forensic Analysis of Policy Engine Lift** | Environment inspection, fare rules, and state mutation guards |
| [`entity_zero_gain.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/entity_zero_gain.json) | **159 Entity Tasks Analyzed** | Multi-signal corroboration traces and offline lookup data |
| [`entity_zero_gain_analysis.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/entity_zero_gain_analysis.md) | **Forensic Analysis of Entity Resolver** | Why 100% synthetic precision produced zero offline replay lift |
| [`provenance_zero_gain.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/provenance_zero_gain.json) | **267 Provenance Tasks Analyzed** | Slot tracking, correction detection, and trajectory bounds |
| [`provenance_zero_gain_analysis.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/provenance_zero_gain_analysis.md) | **Forensic Analysis of Slot Provenance** | Slot recovery bounds, correction handling, and turn ceilings |
| [`baseline_reproducibility.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/baseline_reproducibility.md) | **Audit of Baseline Discrepancy (69 vs 74)** | Mathematical proof of `EvaluationType.ENV` vs `ALL` in Retail |
| [`frozen_core_verification.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/frozen_core_verification.md) | **Verification of Core Code Integrity** | SHA256 hashes, git status, and test coverage of frozen core |
| [`version_history.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/version_history.md) | **System Evolution (v1 to v4)** | Measured metrics, unchanged code, and claim classifications |
| [`tau_voice_context.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/tau_voice_context.md) | **τ-Voice Benchmark Specification** | Environment structure, offline replay constraints, and metrics |
| [`v4_results.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/v4_results.md) | **Full v4 Ablation Results Table** | 6 configurations, domain splits, Wilson 95% CIs, safety metrics |
| [`v3_v4_failure_comparison.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/v3_v4_failure_comparison.md) | **Failure Taxonomy Comparison** | Taxonomy shifts, subsystem blame, and recovery headroom |
| [`execution_safety_context.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/execution_safety_context.md) | **Execution Safety Certification** | Proof of 0 stale writes and 0 duplicate executions across 1,668 runs |
| [`benchmark_integrity_context.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/benchmark_integrity_context.md) | **Preflight Integrity & Oracle Audit** | AST scanner results, 0 task-ID branches, and integrity bounds |
| [`claim_audit.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/claim_audit.md) | **Scientific & Empirical Claim Audit** | Rigorous classification of all documented claims |
| [`repository_tree.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/repository_tree.md) | **Repository File Tree & Inventory** | Guide to all research-relevant files and directories |
| [`architecture_context.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/architecture_context.md) | **Actual Implemented System Architecture** | Code-derived pipeline, state transitions, and subsystems |

---

## Instructions for Independent Reviewers

If you are an independent researcher reviewing this codebase:
1. Start with [`research_context_bundle.md`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/research_context_bundle.md). It is designed to be completely readable on its own without needing prior conversational context.
2. For specific task-level auditing, query [`v4_complete_task_context.jsonl`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/v4_complete_task_context.jsonl) where every task's behavior across all 6 ablation configurations is recorded.
3. Every test in the repository can be verified with:
   ```bash
   .venv/bin/pytest tests/
   ```
   (Currently 480 passed tests in 31.5s).
4. All baseline and ablation runs can be independently reproduced using:
   ```bash
   .venv/bin/python scripts/run_tau_voice_v4_evaluation.py
   ```
