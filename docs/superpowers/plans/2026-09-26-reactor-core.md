# REACTOR Offline Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user approved inline execution in the current folder on a new branch and requested a commit after each verified implementation task.

**Goal:** Deliver a credential-free, tested session controller and kitchen-timer demo that the LiveKit adapter can use in the next milestone.

**Architecture:** A single event-loop owner manages revisions and an operation ledger. Tool calls execute in owned tasks, with a serialized write lane, shielded results, argument validation, and append-only execution evidence. Timers are local async tools with monotonic deadlines.

**Tech Stack:** Python 3.12, asyncio, dataclasses, JSON Schema validation, pytest, pytest-asyncio. No hosted model or GPU required for this milestone.

**Spec:** `docs/superpowers/specs/2026-09-26-reactor-design.md` (approved).

## Global Constraints

- Budget: ₹0; no paid model calls, paid infrastructure, or automatic provider fallback that incurs charges.
- Submission deadline supplied by the user: 30 September.
- All conversation state is session-local. No cross-scenario answer cache.
- No API secrets in source, logs, sample configuration, or submission artifacts.
- Keep the local dataset at `fdb_v3_data_released/`.
- The agent cannot read scenario labels, expected calls, metadata answers, or evaluation transcripts. Only the evaluator reads ground truth.
- Commit each verified implementation task as requested. Do not push unless explicitly requested.
- Keep controller tests independent of LiveKit, network access, and API credentials.
- Preserve actual execution evidence even when a call becomes superseded.
- This milestone demonstrates control semantics, not natural-language understanding or acoustic interruption recovery.

## Scope and follow-on milestone

This is the first independently testable subsystem in the approved design. It implements state, control, local tool execution, trace output, timers, and a scripted offline demo. After it passes, create the second implementation plan for upstream FDB provenance, the 12 wrappers, LiveKit/Gemini integration, credential preflight, recording/evaluation scripts, Colab transcription, and submission documentation. Those tasks must use inspected SDK interfaces and a pinned upstream revision; they are not implied to exist after this milestone.

## Review Focus

1. Duplicate writes arriving concurrently: one execution, shared result, one telemetry entry (Task 2).
2. A correction while a write waits for another write: no obsolete dispatch after acquiring the lane (Task 3).
3. Caller cancellation after a blocking write starts: eventual outcome remains owned and logged (Task 3).
4. A harmless acknowledgment versus a genuine repeat: resuming the old request does not create duplicates; a new action can execute (Tasks 1 and 2).
5. Timer deadline, cancellation, and shutdown races: one authoritative terminal state, no orphan tasks (Task 4).

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package, dependency bounds, pytest configuration, offline demo command |
| `.gitignore` | Local data, environments, secrets, generated outputs |
| `src/reactor/__init__.py` | Package marker |
| `src/reactor/state.py` | Revision tokens, slot values, proposal/result/operation data |
| `src/reactor/tools/__init__.py` | Package marker |
| `src/reactor/tools/base.py` | Tool definition, schema validation, async/sync invocation boundary |
| `src/reactor/controller.py` | Admission, request resolution, deduplication, execution ownership |
| `src/reactor/trace.py` | Immutable event serialization and actual-call telemetry |
| `src/reactor/tools/timers.py` | Session-owned timers |
| `src/reactor/demo.py` | Credential-free scripted controller demonstration |
| `tests/test_state.py` | Request/revision semantics |
| `tests/test_controller.py` | Execution, idempotency, dependency, and race tests |
| `tests/test_trace.py` | JSONL shape and immutable evidence |
| `tests/test_timers.py` | Timer lifecycle and isolation |
| `README.md` | Current capability, local setup, tests, known integration work |

## Task 1: Request state, package setup, and tool contracts

**Files:** create `pyproject.toml`, `.gitignore`, package markers, `state.py`, `tools/base.py`, `tests/test_state.py`.

**Interfaces:**

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

@dataclass(frozen=True)
class RequestToken:
    request_id: int
    intent_revision: int

@dataclass(frozen=True)
class Slot:
    value: Any
    intent_revision: int

@dataclass(frozen=True)
class Proposal:
    request: RequestToken
    action_id: str
    tool: str
    args: dict[str, Any]
    depends_on: tuple[str, ...] = ()

@dataclass(frozen=True)
class Outcome:
    operation_id: str
    status: Literal[
        "succeeded", "failed", "cancelled_before_dispatch", "outcome_unknown"
    ]
    superseded: bool
    result: Any = None
    error: str | None = None

@dataclass
class Operation:
    operation_id: str
    proposal: Proposal
    state_modifying: bool
    status: str = "proposed"
    started_at: float | None = None
    ended_at: float | None = None
    result: Any = None
    error: str | None = None

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    state_modifying: bool
    schema: dict[str, Any]
    handler: Callable[..., Any]
    blocking: bool = False
```

`SessionState(session_id: str)` exposes:

```python
def begin_input(self) -> int: ...
def resolve_input(
    self,
    input_revision: int,
    *,
    mode: Literal["new", "correction", "resume"],
    changes: dict[str, Any] | None = None,
) -> RequestToken: ...
def is_current(self, request: RequestToken) -> bool: ...
def snapshot(self) -> dict[str, Any]: ...
```

These ellipses specify interfaces, not implementation placeholders. Implement the state transition rules below in full.

- [ ] **Step 1: Configure an isolated package and test environment.**

Use this package configuration:

```toml
[build-system]
requires = ["setuptools>=75,<81"]
build-backend = "setuptools.build_meta"

[project]
name = "reactor-agent"
version = "0.1.0"
requires-python = ">=3.10,<3.13"
dependencies = ["jsonschema>=4.23,<5"]

[project.optional-dependencies]
dev = ["pytest>=8.3,<9", "pytest-asyncio>=0.24,<1"]

[project.scripts]
reactor-demo = "reactor.demo:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
```

Ignore `.DS_Store`, `.venv/`, `__pycache__/`, `*.pyc`, `*.egg-info/`, `.pytest_cache/`, `.env`, `.env.*` except `.env.example`, `/fdb_v3_data_released/`, `/artifacts/`, and `/vendor/`. Do not delete the existing dataset.

Verify the workspace parent exists with `ls` before creating the environment. Run `python3.12 -m venv .venv`, then `.venv/bin/python -m pip install -e '.[dev]'`. No global package changes. After successful verification, save the resolved dependency versions for reproduction using an explicit patch, not shell redirection.

- [ ] **Step 2: Write and run failing request-state tests.**

```python
import pytest
from reactor.state import SessionState

def test_correction_preserves_unaffected_slots_and_rejects_old_token():
    state = SessionState("s1")
    first = state.resolve_input(
        state.begin_input(), mode="new",
        changes={"destination": "Boston", "date": "Friday"},
    )
    second = state.resolve_input(
        state.begin_input(), mode="correction",
        changes={"destination": "Chicago"},
    )
    snapshot = state.snapshot()
    assert snapshot["slots"]["destination"]["value"] == "Chicago"
    assert snapshot["slots"]["date"]["value"] == "Friday"
    assert not state.is_current(first)
    assert state.is_current(second)

def test_late_interpretation_cannot_overwrite_newer_input():
    state = SessionState("s1")
    old_revision = state.begin_input()
    new_revision = state.begin_input()
    current = state.resolve_input(new_revision, mode="new", changes={"n": 7})
    with pytest.raises(ValueError, match="stale input"):
        state.resolve_input(old_revision, mode="correction", changes={"n": 10})
    assert state.is_current(current)
    assert state.snapshot()["slots"]["n"]["value"] == 7

def test_resume_keeps_action_identity():
    state = SessionState("s1")
    initial = state.resolve_input(state.begin_input(), mode="new")
    resumed = state.resolve_input(state.begin_input(), mode="resume")
    assert resumed == initial
```

Run `.venv/bin/python -m pytest tests/test_state.py -q`; expect import failures before implementation.

- [ ] **Step 3: Implement state and validation contracts.**

Initial state has revision counters zero, no resolved request, empty slots, and unresolved input. `begin_input` increments the input revision and marks unresolved. `resolve_input` rejects stale or already-resolved input revisions. `new` advances request ID and intent revision; `correction` preserves request ID but advances intent revision and requires a preceding request; `resume` preserves both and rejects nonempty slot changes. Copy JSON-compatible slot values on entry and snapshot output. `is_current` compares request ID and intent revision; unresolved input is a separate dispatch hold, not itself supersession.

Validate tool schemas when registering them using `Draft202012Validator.check_schema`. Validate argument objects before reservation; reject non-finite numbers and unsupported JSON values before they enter traces or identity fingerprints. `blocking=True` requires a synchronous handler and invokes it via `asyncio.to_thread`; `blocking=False` requires an async handler and awaits it. Reject invalid handler combinations at registration.

- [ ] **Step 4: Verify state and input boundaries.**

Add parameterized cases for duplicate resolution, correction before a first request, mutable values supplied by callers, resume with changes, and non-finite JSON numbers. Run the state tests. Record the actual environment versions. Do not commit unless requested.

## Task 2: Operation ledger, dependency checks, and immutable traces

**Files:** create `controller.py`, `trace.py`, `tests/test_controller.py`, `tests/test_trace.py`.

**Consumes:** all Task 1 types and `SessionState`.

**Produces:**

```python
class TraceRecorder:
    # io.TextIOBase-like writable streams; neither path creation nor credentials.
    def __init__(self, session_id, diagnostic_stream, tool_stream): ...
    def event(self, name: str, **fields) -> None: ...
    def tool_call(self, operation: Operation) -> None: ...

class Controller:
    def __init__(self, session_id: str, tools: list[ToolDefinition], trace=None): ...
    async def begin_input(self) -> int: ...
    async def resolve_input(self, input_revision: int, *, mode, changes=None) -> RequestToken: ...
    async def execute(self, proposal: Proposal) -> Outcome: ...
    async def close(self) -> None: ...
    def snapshot(self) -> dict: ...
```

- [ ] **Step 1: Write a concurrent duplicate-write regression.**

```python
import asyncio
import pytest
from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.base import ToolDefinition

EMPTY_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

async def test_duplicate_writes_execute_once_but_new_request_executes_again():
    calls = []
    entered = asyncio.Event()
    release = asyncio.Event()

    async def write():
        calls.append("write")
        entered.set()
        await release.wait()
        return {"status": "success", "count": len(calls)}

    controller = Controller("s1", [ToolDefinition("write", True, EMPTY_ARGS, write)])
    try:
        request = await controller.resolve_input(await controller.begin_input(), mode="new")
        proposal = Proposal(request, "action-1", "write", {})
        first = asyncio.create_task(controller.execute(proposal))
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = asyncio.create_task(controller.execute(proposal))
        release.set()
        a, b = await asyncio.gather(first, second)
        assert a.operation_id == b.operation_id
        assert a.status == b.status == "succeeded"
        assert len(calls) == 1
        new_request = await controller.resolve_input(await controller.begin_input(), mode="new")
        await controller.execute(Proposal(new_request, "action-1", "write", {}))
        assert len(calls) == 2
    finally:
        release.set()
        await controller.close()
```

Run the test and confirm it fails before controller implementation.

- [ ] **Step 2: Implement reservation and identity checks.**

Use a single controller lock for state changes/reservation and a separate write lock for serialized writes. Store owned tasks strongly until session close. No await of tool I/O occurs while holding the state lock.

Use `(request_id, intent_revision, action_id)` as the operation identity. For an existing identity, compare the complete tool/arguments/dependencies fingerprint. A changed fingerprint raises `ValueError("action identity conflict")`; identical proposals share the owned execution task. A different action ID represents a distinct action. The later semantic adapter is responsible for stable logical action IDs; this milestone cannot infer them from natural language.

The reservation portion uses this ordering:

```python
async with self._lock:
    if self._closed:
        raise RuntimeError("session closed")
    # Copy and validate proposal data before reserving it.
    # Existing identity must match its stored fingerprint.
    # A new identity receives a session-local operation ID.
    # Store its Operation and its newly created owned task atomically.
    task = self._tasks[identity]
await asyncio.shield(task)
async with self._lock:
    return self._outcome(self._operations[identity])
```

Implement `_outcome` to calculate relevance at delivery time, not only at tool completion. Deep-copy returned payloads. For obsolete reads, return `superseded=True` and `result=None`. For obsolete successful writes, retain their results with `superseded=True`. A completed tool's history remains in the ledger.

Dependency IDs must identify already-reserved operations in this controller and the same request revision. Await dependency tasks outside the state lock, then check for success and current relevance. Unknown, failed, superseded, or uncertain dependencies prevent dispatch. Requiring earlier reservations prevents dependency cycles without a general DAG engine.

- [ ] **Step 3: Implement trace serialization before adding more control paths.**

Serialize each event immediately with `json.dumps(..., allow_nan=False)` and a timestamp. Never store references to mutable caller dictionaries as historical evidence. If a stream write fails, surface a trace-specific exception and stop admitting further actions; retain the already-known execution outcome in memory. Do not convert a completed side effect into an apparent tool failure that would invite a retry.

Actual-call telemetry has this exact outer shape:

```python
record = {
    "room": self.session_id,
    "call": {
        "function": operation.proposal.tool,
        "args": operation.proposal.args,
        "timestamp_start": operation.started_at,
        "timestamp_end": operation.ended_at,
    },
}
```

Use wall-clock timestamps for upstream compatibility and monotonic measurements for local durations. Emit one completed telemetry record for each actual invocation, including failed/superseded calls; emit no invocation for cancelled-before-dispatch proposals. Diagnostic records distinguish execution failure, uncertainty, and trace failure.

- [ ] **Step 4: Verify ledger and trace boundaries.**

Add tests for a conflicting same action ID, distinct action IDs within one request, a duplicate read, dependencies with real returned IDs, unknown/failed dependencies, separate sessions using identical IDs, and schema rejection before execution. Use `io.StringIO` to parse telemetry and assert the exact shape and count. Mutate input and returned dictionaries after execution and confirm existing trace lines and ledger outcomes are unchanged. Add a failing-stream test proving an executed write is not silently retried.

Run `.venv/bin/python -m pytest tests/test_state.py tests/test_controller.py tests/test_trace.py -q`.

## Task 3: Interruption-safe admission, owned execution, and failures

**Files:** update `controller.py`; expand `tests/test_controller.py` and `tests/test_trace.py`.

**Consumes:** Task 2 ledger and trace contracts.

**Produces:** unchanged public signatures; complete request holds, cancellation relevance, exception outcomes, and shutdown behavior.

- [ ] **Step 1: Write a deterministic correction/queued-write test.**

```python
async def test_correction_prevents_a_waiting_write_from_dispatching():
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def write(name):
        calls.append(name)
        if name == "first":
            entered.set()
            await release.wait()
        return {"status": "success", "name": name}

    schema = {
        "type": "object", "properties": {"name": {"type": "string"}},
        "required": ["name"], "additionalProperties": False,
    }
    controller = Controller("s1", [ToolDefinition("write", True, schema, write)])
    try:
        request = await controller.resolve_input(await controller.begin_input(), mode="new")
        first = asyncio.create_task(controller.execute(Proposal(request, "a", "write", {"name": "first"})))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(controller.execute(Proposal(request, "b", "write", {"name": "second"})))
        await asyncio.sleep(0)
        await controller.resolve_input(await controller.begin_input(), mode="correction", changes={"name": "third"})
        release.set()
        first_result, second_result = await asyncio.gather(first, second)
        assert calls == ["first"]
        assert first_result.status == "succeeded"
        assert first_result.superseded
        assert second_result.status == "cancelled_before_dispatch"
    finally:
        release.set()
        await controller.close()
```

The test uses events to control execution ordering; the single `sleep(0)` only schedules reservation, not a timing guess. Additional instrumentation should make it possible to assert queued status before correction if scheduling changes.

- [ ] **Step 2: Implement unresolved-input holds and final admission checks.**

Maintain an `asyncio.Event` indicating resolved input. `begin_input` clears it while holding the controller lock. Successful resolution sets it. All new tool dispatches conservatively wait for resolved input; this avoids unnecessary speculative benchmark calls. Existing executions continue to be observed.

After dependency completion and, for writes, after acquiring the write lane, wait for resolution and acquire the state lock. Recheck the event, closed state, and proposal relevance. If input became unresolved again, release the state lock and wait again. If stale, mark cancelled-before-dispatch. Otherwise set running and `started_at` before invoking the tool boundary, with no intervening await in that admission decision. Do not equate cancellation of the model's await with cancellation of backend execution.

- [ ] **Step 3: Complete exception and close semantics.**

For an async tool, await its handler; for a blocking tool use `asyncio.to_thread` inside the owned task. An explicitly returned backend error maps to failed. A thrown exception after dispatch maps conservatively to outcome-unknown for writes and failed for reads, retaining a sanitized error type/message. Non-JSON output after a write is an unknown outcome, not permission to retry. Unexpected `CancelledError` in an owned task is recorded before being handled or propagated; do not leave the operation permanently running.

`close()` marks the controller closed and wakes unresolved waiters so queued work is cancelled-before-dispatch. It drains already-dispatched owned tasks and preserves telemetry. It is idempotent. For this local core it does not forcibly terminate worker threads. The adapter must apply its overall session deadline and explicitly report unfinished outcomes if the process cannot drain; this is not a claim of durable exactly-once behavior after crashes.

- [ ] **Step 4: Verify caller cancellation and non-blocking behavior.**

Use a blocking write controlled by `threading.Event`, with a five-second safety timeout in its wait to prevent a hung test. While the worker is active, call `begin_input()` under `asyncio.wait_for(..., timeout=1)` and verify it returns. Cancel only the caller task, resolve the new input as `resume`, release the thread, and call `execute()` again with the original proposal. Assert one actual invocation and a successful recorded outcome. Release the worker in `finally` before closing the controller.

Also test: correction before any dispatch; stale read arriving after correction; duplicate completed read after a newer correction returns no obsolete result; unresolved write resumes after a harmless acknowledgment; thrown write exception is uncertain; returned backend error is failed; session close while operations wait for input; session close while a write is in flight. Add telemetry assertions for superseded executions.

Run `.venv/bin/python -m pytest tests/test_controller.py tests/test_trace.py -q`. Use bounded event waits, never unbounded sleeps in race tests.

## Task 4: Session timers and a truthful offline demonstration

**Files:** create `tools/timers.py`, `tests/test_timers.py`, `demo.py`; update `README.md`.

**Consumes:** Task 1 `ToolDefinition`, Task 3 controller, Task 2 traces.

**Produces:**

```python
class TimerService:
    async def create_timer(self, name: str, duration_seconds: float) -> dict: ...
    async def list_timers(self) -> dict: ...
    async def cancel_timer(self, timer_id: str) -> dict: ...
    def definitions(self) -> list[ToolDefinition]: ...
    async def close(self) -> None: ...

async def run_demo() -> dict: ...
def main() -> None: ...
```

- [ ] **Step 1: Write timer lifecycle tests before implementation.**

```python
from reactor.tools.timers import TimerService

async def test_cancel_is_verified_and_session_local():
    first, second = TimerService(), TimerService()
    try:
        created = await first.create_timer("pasta", 420)
        assert created["state"] == "running"
        assert (await second.list_timers())["timers"] == []
        cancelled = await first.cancel_timer(created["timer_id"])
        assert cancelled["state"] == "cancelled"
        assert (await first.list_timers())["timers"][0]["state"] == "cancelled"
        assert (await first.cancel_timer(created["timer_id"]))["state"] == "cancelled"
    finally:
        await first.close()
        await second.close()
```

Run the test and observe the expected missing-module failure.

- [ ] **Step 2: Implement timer semantics.**

Validate a nonblank name and a finite positive duration no greater than 86,400 seconds. Assign a session-local timer ID. Store monotonic deadline, running/cancelled/completed state, and the owned expiry task. Duplicate names are allowed because cancellation uses ID; the voice adapter must disambiguate names.

Before listing or cancelling a timer, reconcile any deadline already reached using the monotonic clock. Completion wins if the deadline has passed; cancelling an already-completed timer returns completed without claiming cancellation. Cancelling a running timer changes its state before cancelling and awaiting its expiry task. `close()` cancels outstanding timers and awaits owned tasks; repeated close is harmless. Reject new timers after close. Use copied result dictionaries.

Provide three tool schemas with `additionalProperties=False`: create(name, duration_seconds), list(no args), and cancel(timer_id). Create and cancel are state modifying; list is read-only. All handlers are async and run on the owning loop.

- [ ] **Step 3: Verify completion/cancellation races without minute-long tests.**

Inject a clock and a sleep callable into `TimerService` as keyword-only constructor arguments, defaulting to `time.monotonic` and `asyncio.sleep`. Tests use a fake clock and event-controlled sleep. Advance past the deadline and call cancel before releasing the expiry wait; assert completed. Cancel before the deadline, then release expiry; assert cancelled. Cover invalid durations (zero, negative, bool, infinity, NaN), empty names, unknown IDs, repeated close, and no leftover expiry tasks after shutdown.

- [ ] **Step 4: Implement an offline controller demo.**

The demo explicitly supplies interpreted slot updates; it does not pretend to recognize speech. Create a new request for a ten-minute timer, immediately apply a correction to seven minutes, and attempt the obsolete proposal. Assert it was cancelled-before-dispatch. Execute the corrected create action twice with the same logical identity and assert a single timer ID. Start a new request to cancel it and assert cancelled state.

Print strict JSON containing `mode: "scripted_offline"`, the cancelled obsolete proposal outcome, the single created timer, the duplicate's operation ID, the final cancellation, and the session snapshot. Raise if assertions fail. Close controller and timers in `finally`. `main()` calls `asyncio.run(run_demo())` and prints the returned summary. Diagnostics may go to stderr; do not mix prose into machine-readable stdout.

- [ ] **Step 5: Document and verify only implemented capabilities.**

Update README with:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/reactor-demo
```

Explain that the demo is scripted controller verification, not a voice demo or FDB score. Preserve the dataset location. Describe the next integration milestone and pending credentials/GPU transcription/judge access. Run the full tests once after final changes, run the demo, and run `git diff --check`. Inspect changes without staging the dataset or creating a commit.

## Milestone acceptance

- Offline tests demonstrate all eleven control/timer regression classes listed in the design, to the extent they do not require the unimplemented upstream registry.
- Actual-call telemetry serialization is tested; upstream reader compatibility is verified in the next milestone.
- No API key, remote model, GPU, or benchmark answer file is needed to run tests or the demo.
- Scripted demo shows correction, duplicate suppression, and verified timer cancellation.
- README clearly distinguishes completed core work from pending voice/benchmark integration.
- No claim of natural-language correction recognition, live voice performance, official score, or crash-safe external exactly-once execution.

## Self-review summary

- Approved design sections 4 and 6 map to Tasks 1–4; trace serialization from section 7 maps to Task 2.
- Race and shutdown concerns have explicit tests, not just happy-path examples.
- All public interfaces are named in this document; methods with ellipses are interface declarations accompanied by implementation rules, not executable stubs to retain.
- LiveKit, provider access, upstream tool wiring, benchmark reproduction, Colab compatibility, and submission assets are explicitly reserved for the follow-on integration plan.
- The next step is user review of this plan and confirmation of inline execution, then `executing-plans`.
