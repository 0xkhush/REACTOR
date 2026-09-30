# REACTOR

Correction-aware execution for interruptible voice agents.

**Measured code checkpoint:** LiveKit/Gemini agent, versioned controller, 12 FDB-v3 tool adapters, kitchen extension, and Kaggle ASR/evaluation scripts are implemented. A clean full capture at `36a798b` scored **23/100 strict exact tool/argument passes** and **42/100 expected tool selections**, without a semantic judge. The requested 40% strict pass target was not met. See [code verification](docs/FINAL_CODE_CHECKPOINT.md) and [measured results](docs/results/README.md).

## Run locally

Requires Python 3.10–3.12; verified on Python 3.12 on an M1 Mac. No API keys or GPU are needed for the offline tests and demo. Package installation needs internet access.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -e '.[voice]'
mkdir -p vendor
.venv/bin/python scripts/setup_fdb.py
.venv/bin/python -m pytest -q
.venv/bin/reactor-demo
```

For a development install use `.venv/bin/python -m pip install -e '.[dev,voice]'`. The core demo itself needs no API credentials. Full integration tests require the fetched, pinned upstream source. On Windows, use `.venv\Scripts\python.exe`; kitchen local speech needs macOS `say` or Linux `espeak-ng`.

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
- The same `(request_id, intent_revision, action_id)` shares an execution and result. Reusing it with different arguments raises a conflict. The turn bridge binds provider IDs and known speech generations to their original request, coalesces same-request retries, and accepts explicit logical IDs for intentional identical actions. Repeat recognition remains limited; arbitrary semantic repeats need clarification or explicit IDs.
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
mkdir -p vendor
.venv/bin/python scripts/setup_fdb.py
.venv/bin/python scripts/smoke_fdb.py
```

The second command checks that the source and audio files are present. It does not connect to LiveKit or call a model.

### Before a live voice call

1. Tested model: `gemini-2.5-flash-native-audio-preview-12-2025`. The user confirmed Free-tier access and ₹0 usage during testing. Other evaluators must check their own quota; the code never selects a paid fallback.
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

Score the recorded tool calls without using a paid judge, supplying the `room` from the smoke output and the `input.wav` path:

```bash
.venv/bin/python scripts/evaluate_smoke.py --room ROOM_FROM_SMOKE \
  --input fdb_v3_data_released/EXAMPLE_FOLDER/input.wav
```

This uses FDB-v3's exact-match tool/argument evaluator only. It cannot determine spoken-response quality and can reject equivalent date formats: `2026-07-15` versus `July 15`, for example. It also reads ground truth only in the separate evaluator process, not in the agent.

For a self-contained local smoke run, use `--run --start-worker`; it stops the worker after one recording. The command checks `ffmpeg` and calls LiveKit's room-list metadata endpoint to validate the project URL/key/secret **before** starting any model inference. A `401` means those three LiveKit values do not form a valid credential set for one project. Generate a fresh key/secret pair in the matching LiveKit Cloud project and update the ignored `.env.local`; do not paste credentials into issue reports or chat.

The smoke command refuses to run unless free quota is confirmed and a selected model ID is present. It writes the agent's audio under ignored `artifacts/`, looks for room-matched executed calls in `/tmp/agent_tool_calls.log`, and fails if none were logged. One such bounded smoke run connected, logged a `track_order` call, and captured agent audio; this is not a benchmark pass-rate result. The upstream audio client has its own recording window; validate spoken results against the actual output rather than treating a logged tool call as task completion.

The earlier mixed-revision Mac capture processed all 100 recordings: 37 had executed tool calls, 63 had none, and zero failed at the capture/transport stage. The pinned exact tool evaluator reported 25/100 expected tool selections and 12/100 strict passes. A newer single-revision capture at `36a798b` recorded **59 calls, 41 no-tool recordings, zero transport failures**, with **42/100 expected tool selections and 23/100 strict exact passes**. Neither report used an LLM judge, and only the earlier audio has Kaggle ASR transcripts. These are local diagnostics, not official normalized scores.

The current **three-recording smoke sample** selected the expected tool in all three cases. FDB-v3's local exact-match check passed ecommerce and finance, and rejected travel's ISO date formatting. This is a curated debug sample, not a representative benchmark estimate. A rerunnable summary is available with:

```bash
.venv/bin/python scripts/summarize_smokes.py \
  --room reactor-smoke-8fcc845da68c --input fdb_v3_data_released/ecommerce_01_65e8cf8f4c7424fa062e54a3/input.wav \
  --room reactor-smoke-e37a5cecdfdf --input fdb_v3_data_released/travel_01_62a885d5b6af18b3d4579e1b/input.wav \
  --room reactor-smoke-59048ea6a8d9 --input fdb_v3_data_released/finance_01_65e8cf8f4c7424fa062e54a3/input.wav \
  --output artifacts/smoke-summary-exact.json
```

The report labels `official_score: false`, `judge: none`, and separates tool-selection from exact argument checks.

In kitchen mode, `.venv/bin/python scripts/kitchen_smoke.py` records a real same-room voice workflow. The latest smoke created a named pasta timer at 420 seconds after a spoken ten-to-seven-minute correction, then listed and cancelled it by returned ID. Confirmations use free local speech after controller success; unverified native model audio is suppressed in kitchen mode. Negated, compound and unsupported commands are not dispatched. The smoke uses synthesized user speech, not spontaneous human interruption.

### NVIDIA benchmark route

The private Kaggle T4 completed Parakeet transcription and upstream exact-match evaluation. Reports and per-recording evidence are archived in [docs/results](docs/results/README.md). This ASR-only job uses no provider API key. Setup and download instructions are in [Kaggle evaluation](docs/submission/KAGGLE_SETUP.md).

On a single machine with supported CUDA, Python 3.10–3.12, ffmpeg, NeMo ASR and access to a **confirmed-free** Live model, the combined runner is available:

```bash
bash scripts/reproduce.sh --check  # install/config/data preflight, no hosted calls
bash scripts/reproduce.sh          # Linux NVIDIA CUDA: full inference + ASR + exact evaluation
# Organizer-supplied judge key, if available:
bash scripts/reproduce.sh --use-llm
```

Supply `.env.local` and the released audio before running. Python 3.10–3.12, git and ffmpeg are prerequisites. The installer pins the matching LiveKit versions and NeMo 2.5.3, starts the worker, runs the pinned upstream pipeline, and checks coverage. The combined command has only been preflight-tested on this Mac; the actual GPU evaluation used the split Mac/Kaggle workflow. `--use-llm` is explicit and is never used in the ₹0 local default.

### Docker (configuration supplied; build not verified here)

```bash
docker build -t reactor .
docker run --rm --mount type=bind,source="$(pwd)/.env.local",target=/app/.env.local,readonly reactor
```

The image includes ffmpeg and local `espeak-ng` for voice/timer mode, not CUDA ASR. Do not put `.env.local` in the image. Benchmark data is supplied externally. An NVIDIA runtime is required separately for the ASR route.

The official semantic judge uses a separate OpenAI API. We do not run it under a ₹0 budget and do not present exact-match reports as official scores. The organizers' model-key arrangement and final evaluation machine remain external dependencies.

Remaining submission work: team/college/contact fields, final video hosting link, signed official AI disclosure, and final GitHub publication/release tag. Media export is deferred until the user is satisfied with this code checkpoint. Disclose the measured 23% strict exact result and its missing semantic-judge and ASR checks.

## Design and implementation notes

- [Approved design](docs/superpowers/specs/2026-09-26-reactor-design.md)
- [Offline-core implementation plan](docs/superpowers/plans/2026-09-26-reactor-core.md)
- [Private Kaggle GPU evaluation and download steps](docs/submission/KAGGLE_SETUP.md)
- [Eight-slide deck source](docs/submission/SLIDES.md) and [editable draft deck](docs/submission/REACTOR_Submission.pptx)
- [Four-minute demo script](docs/submission/DEMO_SCRIPT.md)
- [AI usage notes](docs/submission/AI_USAGE_NOTES.md) and [final code checkpoint](docs/FINAL_CODE_CHECKPOINT.md)

AI assistance was used for planning, implementation, and tests of this milestone. Keep that fact in the team's final AI usage disclosure.
