# REACTOR

Correction-aware execution for interruptible voice agents.

**Current milestone: offline controller and kitchen timers.** The local demo supplies interpreted requests programmatically. It is not yet a voice assistant, a LiveKit integration, or a Full-Duplex-Bench score.

## Run locally

Requires Python 3.10–3.12; verified on Python 3.12 on an M1 Mac. No API keys or GPU are needed for this milestone. Package installation needs internet access.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -e .
.venv/bin/python -m pytest -q
.venv/bin/reactor-demo
```

For an unpinned development install, use `.venv/bin/python -m pip install -e '.[dev]'`. On Windows, use the corresponding `.venv\Scripts\python.exe` commands.

The demo prints JSON showing:

1. A ten-minute timer proposal superseded by a seven-minute correction.
2. The old proposal cancelled before execution.
3. Two equivalent proposals sharing one seven-minute timer execution.
4. A new cancellation request returning verified cancelled timer state.

## Architecture

```text
Interpreted request + logical action ID
                   |
                   v
         Session controller / ledger
         | input and intent revisions
         | argument schema validation
         | dependency and duplicate checks
         | unresolved-input dispatch hold
                   |
          +--------+--------+
          v                 v
   Concurrent reads    Serialized writes
          +--------+--------+
                   |
          Owned async execution
       (blocking tools run in threads)
                   |
          Outcome reconciliation
                   |
       Structured results + JSONL traces
```

The controller runs on one event loop. Each instance owns a session's state and operation history. Timer services must also be instantiated per session.

### Guarantees and limits

- Corrections preserve unaffected slots and reject obsolete proposals at dispatch.
- `begin_input()` holds new dispatches; `resolve_input()` explicitly classifies the input as a new request, correction, or resume. This core does not interpret speech or detect semantic corrections.
- The same `(request_id, intent_revision, action_id)` shares an execution and result. Reusing it with different arguments raises a conflict. Different action IDs allow intentional repeats. A future semantic adapter must assign these IDs correctly; arbitrary model call IDs do not provide semantic deduplication.
- Dependent operations wait for successful, relevant parent outcomes. Schema validation does not prove semantic argument correctness.
- Late read results are hidden from current consumers. Successful superseded writes remain visible as historical outcomes.
- Cancelling a caller does not cancel an already-dispatched write. The controller observes its owned task and records the result. A thrown write exception becomes `outcome_unknown`, not an automatic retry.
- No crash-safe exactly-once guarantee or general rollback. State is in memory, and a worker thread cannot be forcibly cancelled. `close()` drains owned executions; an indefinitely blocked backend can therefore block shutdown. The future adapter must define overall scenario deadlines and backend timeouts.
- Call `controller.close()` before closing the session's tool resources. Timers use monotonic deadlines; completed timers cannot be retroactively cancelled.

## Traces

`TraceRecorder` accepts diagnostic and actual-call text streams. It writes strict JSONL and flushes each record. Supply streams explicitly when you need evidence; the offline demo returns its summary on stdout.

Actual-call records follow FDB-v3's room-keyed shape:

```json
{"room":"session-id","call":{"function":"tool_name","args":{},"timestamp_start":100.0,"timestamp_end":101.0}}
```

Every actual invocation is recorded, including failures and superseded calls. Proposals cancelled before dispatch appear only in diagnostics. Timestamps in actual-call records use wall time; diagnostic durations use a monotonic clock. Failed logging blocks further admission without changing a completed write into a failed write. These files are append-only by convention, not a tamper-proof audit store.

## Benchmark data and next milestone

The downloaded recordings remain at `fdb_v3_data_released/`, which is Git-ignored. The agent core does not read dataset metadata or expected answers.

Follow-on integration work:

- Pin and attribute the [FDB-v3 source](https://github.com/DanielLin94144/Full-Duplex-Bench/tree/main/v3), preserve its 12 mock tool interfaces, and verify telemetry with its reader.
- Add LiveKit/Gemini voice integration and verify available free API quotas. Credentials are configured locally, never committed.
- Capture benchmark audio/calls on the Mac and validate Parakeet transcription on Colab's T4. The observed Colab Python 3.13 runtime has not been validated against NeMo; target a compatible Python environment.
- Provide the standard NVIDIA evaluation route and verify any split workflow against it.
- Obtain semantic-judge access or clearly label local exact-match results as distinct from official evaluation.
- Record a real voice demo and prepare the submission assets. No live benchmark results are claimed at this stage.

## Design and implementation notes

- [Approved design](docs/superpowers/specs/2026-09-26-reactor-design.md)
- [Offline-core implementation plan](docs/superpowers/plans/2026-09-26-reactor-core.md)

AI assistance was used for planning, implementation, and tests of this milestone. Keep that fact in the team's final AI usage disclosure.
