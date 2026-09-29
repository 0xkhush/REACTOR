# REACTOR

Correction-aware execution for interruptible voice agents.

**Current milestone: tested controller, benchmark mock-tool adapter, and a LiveKit/Gemini entry point.** The local demo supplies interpreted requests programmatically. Live speech and Full-Duplex-Bench results have not yet been verified against a hosted model.

## Run locally

Requires Python 3.10–3.12; verified on Python 3.12 on an M1 Mac. No API keys or GPU are needed for the offline tests and demo. Package installation needs internet access.

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
- Read delivery waits while new input is unresolved; snapshots hide those read payloads. A confirmed correction promptly cancels pending work even when its predecessor is still running. Late obsolete read results are hidden from current consumers. Successful superseded writes remain visible as historical outcomes.
- Cancelling a caller does not cancel an already-dispatched write. The controller observes its owned task and records the result. A thrown write exception becomes `outcome_unknown`, not an automatic retry.
- No crash-safe exactly-once guarantee or general rollback. State is in memory, and a worker thread cannot be forcibly cancelled. `close()` drains owned executions; an indefinitely blocked backend can therefore block shutdown. The future adapter must define overall scenario deadlines and backend timeouts.
- Call `controller.close()` before closing the session's tool resources, and use `finally` to close those resources even if the controller reports a logging failure. Timers use monotonic deadlines; completed timers cannot be retroactively cancelled.

## Traces

`TraceRecorder` accepts diagnostic and actual-call text streams. It writes strict JSONL and flushes each record. Supply streams explicitly when you need evidence; the offline demo returns its summary on stdout.

Actual-call records follow FDB-v3's room-keyed shape:

```json
{"room":"session-id","call":{"function":"tool_name","args":{},"timestamp_start":100.0,"timestamp_end":101.0}}
```

With a functioning recorder, every actual invocation is recorded, including failures and superseded calls. Proposals cancelled before dispatch appear only in diagnostics. Timestamps in actual-call records use wall time; diagnostic durations use a monotonic clock. Failed logging blocks further admission without changing a completed write into a failed write. `snapshot()` exposes the evidence failure, and `close()` drains owned work before raising `TraceError`, including when the original caller was cancelled. These files are append-only by convention, not a tamper-proof audit store.

## Benchmark data and LiveKit integration

The downloaded 100 recordings remain at `fdb_v3_data_released/`, which is Git-ignored. The agent core and LiveKit worker do not read dataset metadata or expected answers. The FDB-v3 checkout is also ignored and fetched at the pinned revision with:

```bash
python scripts/setup_fdb.py
.venv/bin/python scripts/smoke_fdb.py
```

The second command checks that the source and audio files are present. It does not connect to LiveKit or call a model.

### Before a live voice call

1. Check your Google AI Studio account's **specific Gemini Live model** for free-tier availability and quota. We have not confirmed which model is free for your account. An API key alone does not establish that a call costs ₹0.
2. Copy `.env.example` to your ignored `.env.local`. Fill the LiveKit URL, key, secret, Google API key and `GOOGLE_LIVE_MODEL` with the confirmed model ID. Set `REACTOR_MODE=benchmark` or `kitchen`.
3. Only after confirming free access and no paid overage, set `REACTOR_FREE_QUOTA_CONFIRMED=yes` locally. The entry point refuses to connect without this flag. No code here chooses a paid fallback provider.
4. Install the pinned agent and matching Google plugin, then start the worker:

```bash
.venv/bin/python -m pip install -e '.[dev,voice]'
.venv/bin/python -m reactor.voice.agent dev
```

The pinned versions are `livekit-agents==1.3.12` and `livekit-plugins-google==1.3.12`. Installing `livekit-agents[google]==1.3.12` alone can resolve an incompatible newer Google plugin, so install the project voice extra instead.

With the worker running in one terminal, stream **one** FDB recording from another terminal:

```bash
.venv/bin/python scripts/smoke_fdb.py --run
```

For a self-contained local smoke run, use `--run --start-worker`; it stops the worker after one recording. The command checks `ffmpeg` and calls LiveKit's room-list metadata endpoint to validate the project URL/key/secret **before** starting any model inference. A `401` means those three LiveKit values do not form a valid credential set for one project. Generate a fresh key/secret pair in the matching LiveKit Cloud project and update the ignored `.env.local`; do not paste credentials into issue reports or chat.

The smoke command refuses to run unless free quota is confirmed and a selected model ID is present. It writes the agent's audio under ignored `artifacts/`, looks for room-matched executed calls in `/tmp/agent_tool_calls.log`, and fails if none were logged. The upstream audio client has its own recording window; validate spoken results against the actual output rather than treating a logged tool call as task completion.

In kitchen mode, use a LiveKit microphone/console session to try a corrected timer and an interruption. The existing `reactor-demo` command tests only the scripted control path.

### NVIDIA benchmark route

On a machine with supported CUDA, Python 3.10–3.12, ffmpeg, NeMo ASR and access to a **confirmed-free** Live model, install the upstream requirements and run:

```bash
.venv/bin/python scripts/reproduce.py
```

The script starts the LiveKit worker, runs all available recordings through the pinned upstream pipeline, refuses an incomplete result set, and generates **exact-match development reports** under ignored `artifacts/`. This command has **not** been validated on the Colab T4 or a clean Linux machine yet. The upstream runner uses Parakeet and CUDA; your Mac cannot run this path unchanged. A Colab notebook and a cross-platform artifact transfer still need testing.

The official semantic judge uses a separate OpenAI API. We do not run it under a ₹0 budget and do not present exact-match reports as official scores. The organizers' model-key arrangement and final evaluation machine remain external dependencies.

Follow-on integration work:

- Verify free Gemini Live access and complete a real voice+tool smoke run. SDK turn event timing and interrupt handling require observation with audio; tests alone do not prove them.
- Capture benchmark audio/calls on the Mac and validate Parakeet transcription on Colab's T4. The observed Colab Python 3.13 runtime has not been validated against NeMo; target a compatible Python environment. Verify upstream telemetry reader compatibility against real recordings.
- Validate the standard NVIDIA route and any Mac/Colab split workflow on a clean environment.
- Obtain semantic-judge access or clearly label local exact-match results as distinct from official evaluation.
- Record a real voice demo and prepare the submission assets. No live benchmark results are claimed at this stage.

## Design and implementation notes

- [Approved design](docs/superpowers/specs/2026-09-26-reactor-design.md)
- [Offline-core implementation plan](docs/superpowers/plans/2026-09-26-reactor-core.md)

AI assistance was used for planning, implementation, and tests of this milestone. Keep that fact in the team's final AI usage disclosure.
