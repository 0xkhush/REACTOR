# CRB-v1: Empirical Statistical Report

## Executive Benchmark Summary

* **Benchmark**: Correction-Recovery Benchmark (CRB-v1)
* **Design**: Asynchronous Concurrency with Instrumented Simulated Latencies
* **Sample Size**: N = 40 Scenarios (Pre-Dispatch: 10, In-Flight: 10, Partial Mutation: 10, Rapid/Isolation: 10)
* **Systems Compared**:
  1. `Naive`: Blind immediate dispatch (Lower bound control)
  2. `AsyncCancel`: Standard Python `asyncio.Task.cancel()` on interruption (Engineering baseline)
  3. `HoldConfirm`: 300 ms hold window before dispatch (Safety-latency tradeoff baseline)
  4. `REACTOR`: Core versioned admission controller (Unmodified core)

---

## 1. Primary Empirical Results

| System | First-Intent Leakage Rate (FILR) ↓ | Wilson 95% CI | Correction Recovery Rate (CRR) ↑ | Wilson 95% CI | Partial Mutation Rate (PMR) | False Cancellation Rate (FCR) | p95 Cancellation Latency | p99 Gate Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Naive** | **62.5%** (25/40) | [47.0%, 75.8%] | **32.5%** (13/40) | [20.1%, 48.0%] | 0.0% (0/40) | 0.0% (0/40) | N/A | N/A |
| **AsyncCancel** | **0.0%** (0/40) | [0.0%, 8.8%] | **85.0%** (34/40) | [70.9%, 92.9%] | 0.0% (0/40) | 37.5% (15/40) | 0.18 ms | N/A |
| **HoldConfirm** | **0.0%** (0/40) | [0.0%, 8.8%] | **100.0%** (40/40) | [91.2%, 100.0%] | 0.0% (0/40) | 37.5% (15/40) | N/A | N/A |
| **REACTOR** | **0.0%** (0/40) | [0.0%, 8.8%] | **85.0%** (34/40) | [70.9%, 92.9%] | 0.0% (0/40) | 37.5% (15/40) | 0.32 ms | 179.25 µs |

---

## 2. Performance by Timing Class (FILR ↓ / CRR ↑)

| Timing Class | Scenarios | Naive Dispatch | AsyncCancel | HoldConfirm (300ms) | REACTOR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **pre_dispatch** | 10 | 80% / 50% | 0% / 100% | 0% / 100% | 0% / 100% |
| **in_flight** | 10 | 80% / 60% | 0% / 100% | 0% / 100% | 0% / 100% |
| **partial_mutation** | 10 | 0% / 0% | 0% / 40% | 0% / 100% | 0% / 40% |
| **rapid_correction** | 8 | 88% / 25% | 0% / 100% | 0% / 100% | 0% / 100% |
| **concurrency_isolation** | 2 | 100% / 0% | 0% / 100% | 0% / 100% | 0% / 100% |

---

## 3. High-Resolution Admission Gate Microbenchmark (N = 10,000 iterations)

* **Mean Gate Latency**: 10.995 µs
* **p50 (Median)**: 3.750 µs
* **p95**: 8.541 µs
* **p99**: 16.000 µs
* **Max**: 65759.000 µs

---

## 4. Key Empirical Findings

1. **Pre-Dispatch Invalidation**:
   In Pre-Dispatch scenarios, REACTOR achieves 0.0% FILR and 100.0% CRR, validating its monotonic admission gating.
2. **In-Flight Cancellation**:
   Under genuine asynchronous concurrency where a tool is actively executing I/O when speech arrives, standard `AsyncCancel` successfully cancels the coroutine before commit, while REACTOR's unchanged controller (which currently only cancels `proposed` operations in `_cancel_pending`) demonstrates where core in-flight cancellation propagation must be enhanced.
3. **Partial Mutation**:
   When mutations occur in stages prior to cancellation, neither REACTOR nor AsyncCancel can undo already-committed database writes without compensation logic, empirically proving that REACTOR is an admission gate rather than an ACID rollback engine.
