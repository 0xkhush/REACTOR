# REACTOR: Two-Day Voice Agent Design

Status: approved by the user on 26 September 2026. This document does not claim implementation or benchmark results.

## 1. Goal and constraints

Build one interruptible LiveKit voice agent for Full-Duplex-Bench v3 (FDB-v3), plus a small working kitchen-timer extension. Optimize for correct tool execution, correction handling, reproducibility, and a demonstrable submission within two working days.

- Budget: ₹0; no paid model calls, paid infrastructure, or automatic provider fallback that incurs charges.
- Submission deadline supplied by the user: 30 September.
- Development machine: Apple M1 MacBook Air, 8 GB RAM, Python 3.12.
- Remote compute: a Colab T4 allocation has been demonstrated, but future availability is not guaranteed.
- Colab currently uses Python 3.13; NeMo/Parakeet compatibility remains unverified. Plan to test evaluation dependencies in a Python 3.10–3.12 environment.
- Google AI Studio and LiveKit accounts exist. Credentials, model availability, and free quotas will be configured later.
- All conversation state is session-local. No cross-scenario answer cache.
- Follow the newer LiveKit/FDB-v3 participant guide rather than the original custom two-queue PRD.
- No API secrets in source, logs, sample configuration, or submission artifacts.

Success means a tested local control layer, an integrated voice adapter, preserved benchmark telemetry, one end-to-end timer extension, and documented reproduction. Live voice success and official-compatible scores require actual execution and cannot be inferred from offline tests.

## 2. Recommended approach

Use the upstream native realtime LiveKit template as the integration reference, with Gemini Live as the first provider candidate. Keep model construction behind one adapter and configure its model identifier externally. Do not depend on a particular preview model continuing to exist.

Alternatives considered:

1. Native realtime model with a small controller: least integration work, but transcript and cancellation behavior depend on provider events. Selected, subject to a live compatibility check.
2. Cascaded STT/LLM/TTS: more direct access to text, but more dependencies and latency. Deferred fallback if free realtime access fails.
3. Fully local pipeline: no API billing, but memory pressure and additional integration on an 8 GB machine. Deferred.

Avoid a second planner model, general DAG compiler, custom UI, camera processing, general compensation engine, and model training. The existing model tool loop handles multi-step chains.

## 3. System boundaries

```text
Microphone or FDB recording
          |
          v
LiveKit AgentSession + Gemini adapter
     |                         |
speech/turn events       tool invocation
     |                         |
     +------> Session controller
               | intent/slot state
               | operation ledger
               | argument validation
               | dispatch coordination
               v
        Non-blocking tool executor
           |               |
       FDB mock tools   Kitchen timers
           |               |
           +--> Result reconciliation
                        |
                 Model tool result
                        |
                 Grounded speech

Controller events -> diagnostic JSONL
Actual FDB calls  -> upstream-compatible telemetry
```

One application process may host multiple sessions. Each session owns its controller, registry, ledger, timers, and diagnostic context. Shared model downloads are allowed; shared conversation answers are not.

## 4. Controller semantics

### Session state

Maintain a session ID, input revision, intent revision, slots with provenance, and operation records. Speech start advances the input revision and marks the turn unresolved. A semantic correction updates only affected slots and advances the intent revision.

Speech start is not itself proof of changed intent. It should yield the conversational floor and prevent new writes until the input is resolved. Acknowledgments such as “thanks” must not erase the task.

The core exposes explicit turn and correction methods that offline tests can exercise. The voice adapter must map SDK events and semantic decisions to them. SDK transcript timing must be tested: a transcript arriving after a tool call is insufficient evidence to claim prevention of premature actions.

The first version uses conservative invalidation: a confirmed correction supersedes pending work from the old intent revision and prevents dependent dispatch. Unaffected slot values and completed action history remain available. Finer-grained reuse is deferred.

### Operation identity and status

Each operation has a controller ID, provider call ID if available, logical request ID, tool name, validated arguments, intent revision, dependency references, timestamps, and outcome.

Statuses: proposed, running, succeeded, failed, cancelled-before-dispatch, outcome-unknown. Relevance (current or superseded) is separate from execution status. A completed but superseded write still happened.

Within one resolved user request, repeated equivalent write proposals map to the same logical operation and share its in-flight task or recorded result. A later explicit request gets a new request identity, allowing “add another one.” Do not deduplicate by arguments across the entire conversation. Repeated identical actions within one request need distinct semantic action identities or clarification; do not silently assume they are retries.

Do not retry writes automatically after dispatch failures with uncertain outcomes. Read retries, if introduced, are bounded and logged.

### Dispatch and concurrency

Validate against tool schemas before dispatch. Under a short session lock, check request relevance and dependencies, reserve the operation identity, and mark dispatch ownership. Never hold that lock while awaiting tool I/O or model inference.

Independent reads can overlap. State-changing operations are serialized per session. Recheck request relevance immediately before dispatch after waiting for the write lane.

Blocking upstream mock execution runs outside the event loop. Retain ownership of the underlying execution even if the model-facing await is cancelled. A thread cannot be forcibly stopped by cancelling its awaiting coroutine.

Cancellation guarantees are deliberately bounded:

- Before dispatch: the tool is not invoked.
- Dispatched read: record execution, but exclude obsolete results from current reasoning.
- Dispatched write: observe the outcome where possible; do not claim rollback.
- Completed write: retain its confirmed history. Reverse only through an available tool.

The dispatch gate protects local dispatch decisions; it does not create a transaction with an external backend. Process termination or lost remote responses can leave an unknown outcome.

### Result handling

Return structured success, failure, superseded, or uncertain outcomes to the adapter. Superseded search content must not be passed to the model as current evidence. Successful obsolete writes must still be represented truthfully as completed actions, not discarded from history.

Tool output supplies identifiers for dependent calls. Do not invent identifiers or expose expected benchmark answers to the model. Enforce argument schemas locally; semantic correctness remains a measured property of the complete agent.

## 5. Voice behavior and integration

Use one native realtime model for speech and tool reasoning. Configure concise, correction-aware instructions and retain upstream tool signatures for benchmark mode.

- Yield speech when interrupted, using LiveKit/provider-supported controls.
- Avoid acknowledgments on every partial transcript.
- Give progress feedback when helpful, without claiming completion.
- Wait for sufficiently resolved arguments before executing actions.
- Ground responses in actual tool outcomes.
- Register only benchmark tools in benchmark mode and only extension tools in the timer demo.

Offline controller tests cannot establish acoustic interruption quality. Live acceptance requires a real microphone/recording test with the chosen provider. If the SDK lacks timely events required by a control, document the limitation and avoid claiming the control applies to unseen audio.

## 6. Tools and extension

Benchmark mode uses the upstream 12 mock tools with unchanged result semantics. Record the upstream commit used. There are no general booking/cart reversal tools in this registry, so the demo must not imply such support.

Extension scope: named kitchen timers, with create, list, and cancel operations. Timers use a monotonic clock. Cancellation returns verified local timer state. Session shutdown stops owned timer tasks. Recipe features are optional only after the required paths work.

Extension acceptance: the user creates a timer with a self-correction, the agent creates one timer with the corrected duration, and a later cancellation changes the timer to cancelled before the agent confirms cancellation. Also test an intentional second timer to ensure duplicate protection is not overbroad.

## 7. Logs, benchmark integrity, and evaluation

Preserve the upstream room-keyed actual-call JSON shape: function, args, timestamp_start, timestamp_end. Record actual executions even when superseded. Proposed operations that never dispatch belong in diagnostics, not fabricated execution records. Include failures/uncertainty in diagnostics and retain complete execution evidence.

The agent cannot read scenario labels, expected calls, metadata answers, or evaluation transcripts. Only the evaluator reads ground truth. Each scenario starts fresh.

Keep the local dataset at `fdb_v3_data_released/`. Ignore raw data, generated recordings, secrets, environments, and scratch logs in Git. Selected sanitized result artifacts may be explicitly included for submission.

Development runs compare the upstream baseline and candidate under the same provider configuration. Report full dataset coverage and missing/failed examples alongside scores; never report a partial denominator as a full run.

For the Mac/Colab split, record audio and calls locally, then transcribe in Colab with the upstream Parakeet model. Preserve room IDs, original timestamps, and input/output associations. Provide a standard single-machine NVIDIA reproduction route for organizers. Check the split workflow against the standard route before describing it as equivalent.

Exact-match evaluation is available without a judge, but differs from official semantic judging. The organizer's pinned judge and API credential arrangements remain external dependencies. Do not report exact-match results as official scores.

## 8. Proposed repository structure

```text
src/reactor/
  config.py              # environment and mode validation
  state.py               # session, revision, and operation models
  controller.py          # admission, cancellation, deduplication, reconciliation
  trace.py               # diagnostic and benchmark telemetry
  tools/benchmark.py     # upstream registry boundary and schema adapters
  tools/timers.py        # local timer lifecycle
  voice/agent.py         # LiveKit session and provider event integration
  voice/prompts.py       # general conversational/tool instructions
tests/                   # controller, timer, and telemetry regression tests
scripts/                 # upstream setup, smoke runs, reproduction
notebooks/               # Colab transcription setup and artifact processing
docs/                    # architecture, setup, demo, AI usage notes
```

Keep controller tests independent of LiveKit, network access, and API credentials. Missing configuration should fail with a clear message before connection attempts.

## 9. Verification and two-day sequence

Day 1:
1. Establish an offline test environment and upstream provenance.
2. Implement tested controller and timer primitives.
3. Integrate benchmark wrappers and telemetry.
4. Connect the realtime adapter when credentials become available; establish a baseline smoke run.

Day 2:
1. Fix failures observed in correction handling and tool chains.
2. Validate the timer voice extension.
3. Run available benchmark paths and retain honest evidence.
4. Freeze features, test reproduction, and prepare README, at-most-eight-slide deck, and 3–5 minute demo.

Required offline regression cases:
- A corrected argument preserves other slots and prevents obsolete pending dispatch.
- A late read result does not become current evidence.
- Duplicate concurrent write requests execute once.
- A new intentional repeat executes again.
- A write waiting for the lane rechecks revision before execution.
- Cancelled model-facing awaits do not erase a dispatched write's eventual outcome.
- Slow synchronous tools do not block controller event processing.
- Tool failures and uncertain writes are reported without false success.
- Sessions do not share operations, registry state, or timers.
- Actual benchmark call logs include superseded executions.
- Timer cancellation and completion races produce one authoritative outcome.

Release evidence must distinguish offline tests, live voice checks, benchmark smoke tests, and full evaluations. No paid resource may be introduced to resolve a blocker without revisiting the user's budget constraint.

## 10. Review and implementation handoff

The user approved this design, the offline-core implementation plan, and inline execution. Work in the current folder on a new branch, as requested. Commit each verified implementation task; do not push unless explicitly requested.

Resource choices that remain unverified are isolated behind configuration and adapters. They do not prevent offline controller implementation after design and implementation-plan approval, but they do prevent claims of end-to-end voice or benchmark success.
