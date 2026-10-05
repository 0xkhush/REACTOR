# CRB-v1 Methodology Specification

## 1. Experimental Design
CRB-v1 evaluates the execution-safety characteristics of voice agent execution layers under mid-turn user interruptions and corrections.

## 2. Timing Engine
All scenarios execute under an asynchronous scheduler using `asyncio.sleep()`, simulating realistic network/tool latencies (typically 150 ms) and user speech barge-in arrival offsets (typically 50 ms).

## 3. Evaluated Systems
- **System A (Naive Dispatch)**: Immediate execution without cancellation.
- **System B (AsyncCancel)**: Real-world cooperative cancellation (`asyncio.Task.cancel()`).
- **System C (HoldConfirm)**: Delayed dispatch with a 300 ms hold window.
- **System D (REACTOR)**: Monotonic intent-revision admission control via `Controller`.

## 4. Primary Metrics
- **First-Intent Leakage Rate (FILR)**: Proportion of correction scenarios where any mutation from a superseded revision commits to state.
- **Correction Recovery Rate (CRR)**: Proportion of scenarios whose final state matches gold state.
- **Partial Mutation Rate (PMR)**: Proportion of multi-stage mutations partially committed before cancellation.
- **False Cancellation Rate (FCR)**: Proportion of un-superseded valid operations incorrectly cancelled.
