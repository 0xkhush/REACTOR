# REACTOR LiveKit and FDB-v3 Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Keep the user's requested per-task commit checkpoints. No push unless explicitly requested.

**Goal:** Connect the verified controller to FDB-v3's twelve tools and a Gemini Live LiveKit agent, with a credential-free integration test path and a reproducible voice smoke-run procedure.

**Architecture:** Keep each LiveKit room's registry, controller, telemetry streams, and semantic turn state isolated. Wrap the upstream mock registry without changing its behavior; expose the twelve original tool signatures to the realtime model. A small turn adapter owns input resolution and logical action IDs; where LiveKit lacks timely correction events, describe and test the resulting limitation rather than claiming pre-tool cancellation.

**Tech Stack:** Python 3.12, existing asyncio/jsonschema/pytest core, LiveKit Agents 1.3-compatible Google plugin, python-dotenv, pinned FDB-v3 revision `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`, Google AI Studio and LiveKit Cloud free allowances.

**Spec:** `docs/superpowers/specs/2026-09-26-reactor-design.md` (approved).

## Global Constraints

- Budget: ₹0. No hosted requests until the selected model's free quota and absence of paid overage have been confirmed in the provider account; never silently switch providers.
- Deadline: 30 September 2026. Keep the integration and demo narrower than a general agent framework.
- Do not print, store in logs, or commit contents of `.env.local`.
- Do not expose FDB ground-truth metadata, expected calls, or evaluation transcripts to the agent.
- Reuse the upstream twelve mock calls and their external names/argument shapes. Do not add benchmark-only shortcuts or hardcoded scenario branches.
- Every testable task runs tests then gets its own commit; no push without a separate user request.
- The upstream source cloned under ignored `vendor/Full-Duplex-Bench/` is development reference only. A reproducible checkout script must fetch its pinned commit, or a small attribution-preserving copy of the needed files must be committed.
- A CUDA T4 was demonstrated in Colab, but NeMo/Python compatibility and a paid LLM judge remain unverified.

## Review Focus

1. Speech-start event arrives without a final transcript: do not deadlock tool calls or misclassify an acknowledgment as a correction (Task 3).
2. Two identical tool calls for two different order IDs, or an explicit repeat: do not suppress a legitimate second call (Tasks 2–3).
3. Delayed mock tool call with `time.sleep`: do not stall LiveKit's event loop; preserve its actual-call timestamp and output (Task 2).
4. Missing/placeholder credentials or a model outside free quota: fail locally before any provider request and without logging keys (Task 1).
5. An executed write invalidated during model interruption: show its real result; do not claim it was undone (Task 3).

## Proposed files and responsibilities

| File | Responsibility |
|---|---|
| `src/reactor/config.py` | Load `.env.local` without exposing values, validate URL/key/model/mode |
| `src/reactor/tools/benchmark.py` | Twelve tool contracts and per-room upstream registry adapter |
| `src/reactor/voice/turns.py` | Map provider turn events to explicit request tokens and action IDs |
| `src/reactor/voice/prompts.py` | Voice instructions for corrections, chains, and truthful status |
| `src/reactor/voice/agent.py` | LiveKit AgentServer, Gemini model, tools and room lifecycle |
| `scripts/setup_fdb.py` | Reproducible pinned upstream checkout; do not read dataset answers |
| `scripts/smoke_fdb.py` | Check one end-to-end inference example and artifact coverage, no fake scores |
| `tests/test_config.py` | Credential validation without real values |
| `tests/test_benchmark_tools.py` | Contract parity with upstream registry and telemetry reader format |
| `tests/test_turns.py` | Timely turn state / correction / stable vs distinct action identity |
| `tests/test_voice.py` | LiveKit registration/configuration with SDK test doubles, no hosted calls |
| `README.md` | Exact commands and honest run status |

## Task 1: Environment preflight and pinned upstream source

- [ ] **Test first:** assert that missing, placeholder, or malformed LiveKit URL/API credentials and Google key fail with a nonsecret, actionable exception; validate `REACTOR_MODE` is `benchmark` or `kitchen`, and the selected `GOOGLE_LIVE_MODEL` is explicit and permitted by a local free-access allowlist set by the user. A good config object contains only fields needed by the chosen mode; no `repr` with credentials.
- [ ] **Run red:** `.venv/bin/python -m pytest tests/test_config.py -q`, confirm expected missing-module/behavior failure.
- [ ] **Implement:** use `dotenv_values` to read `.env.local` only at process startup. Copy values to in-memory configuration, but never print or serialize secrets. Free quota confirmation is a separate explicit flag (`REACTOR_FREE_QUOTA_CONFIRMED=yes`) supplied only after the user checks the account; the preflight must refuse a live connection otherwise. Do not assume setting a key means a model is free.
- [ ] **Pinned upstream:** `scripts/setup_fdb.py` checks out the exact SHA above into ignored `vendor/Full-Duplex-Bench`; when already present, verifies commit equality without overwriting user work. It must never download the separate recordings automatically or copy metadata to agent paths. For builds from GitHub, provide the script in the repo.
- [ ] **Verify:** run all tests and a no-secrets preflight; inspect `git diff --check`, `git status`, and staged files; commit only intended files, not vendor/ or `.env.local`.

## Task 2: Benchmark registry wrapper and telemetry

- [ ] **Test first:** with a real pinned upstream registry, build exactly 12 definitions and check each external name, required/optional argument, result shape, and state-modifying classification. Test a two-step search→cart call using returned `product_id`, concurrent independent reads, and duplicate write protection with a stable logical action ID. Assert no expected answers are read by agent code.
- [ ] **Run red:** `.venv/bin/python -m pytest tests/test_benchmark_tools.py -q` must fail for missing adapter behavior.
- [ ] **Implement:** import the pinned `mock_apis.py`/`latency_injector.py` through a contained path boundary. Instantiate `MockAPIRegistry` per room; each synchronous `registry.call(name, **args)` is a `blocking=True` ToolDefinition so the controller offloads the sleep to a thread. Preserve upstream defaults (`search_products.max_price=None`, `calculate_commute.mode='driving'`, `add_to_cart.quantity=1`), result semantics, and exact tool signatures exposed to the model. Use one `TraceRecorder` per room. For upstream inference, write the actual-call stream to the expected `/tmp/agent_tool_calls.log` or a compatible explicit path; use one append operation/lock to avoid interleaved lines across rooms. Verify a test fixture can be parsed by upstream `run_tool_benchmark.py` logic without providing labels to the agent.
- [ ] **Verify:** run targeted tests, then full `pytest -q`; commit after reviewing the diff. Do not claim a benchmark pass rate based on local unit tests.

## Task 3: Turn bridge and voice instructions

- [ ] **Test first:** simulate partial and final transcripts and a user speech start. Verify: prompt acknowledgments do not erase a request; a semantic correction updates only changed slots; a call waiting for new input is withheld; a call from an older resolved request is cancelled; independent explicit actions have unique action IDs; retries reuse the same ID only with the same arguments. Test repeated named orders with different IDs and repeated identical actions explicitly requested by the user.
- [ ] **Run red:** `.venv/bin/python -m pytest tests/test_turns.py -q`.
- [ ] **Implement:** a single per-room adapter consumes the SDK's actual event types (inspect the installed version before coding). Use `begin_input()` on a reliable speech-start signal if supported, and `resolve_input()` only once per input revision when stable semantic input is available. The model can directly propose tools before final transcripts in some realtime models; if so, map a proposal to the latest confirmed request and use conservative gating, but explicitly log and document that pre-final corrections may not be prevented. Never hold the controller input event unresolved permanently. Provider-generated call IDs alone are not semantic retry IDs: use a bounded per-request logical-action map only when the same call is a proven retry, otherwise allocate a distinct ID. Treat an unknown or ambiguous repeat as distinct rather than silently suppressing it.
- [ ] **Verify:** targeted tests, full suite, diff and commit. Do not assert that unit tests prove acoustic latency.

## Task 4: LiveKit agent entry point and local smoke procedure

- [ ] **Test first:** import the entry point without `.env.local` or LiveKit Cloud access, validate tool registration for benchmark vs kitchen mode and room-scoped controller/registry/timer cleanup. In dry-run construction, ensure `GOOGLE_API_KEY` is supplied only to the Google plugin, not written to logs; check SDK signatures against the installed pinned version.
- [ ] **Run red:** `.venv/bin/python -m pytest tests/test_voice.py -q`.
- [ ] **Implement:** adapt the upstream `AgentServer`/`AgentSession` pattern in `src/reactor/voice/agent.py`; use the installed LiveKit Google realtime plugin and a model identifier explicitly confirmed on a free quota. Keep the twelve upstream `@function_tool` signatures in benchmark mode and the three timer tools in kitchen mode. Route handlers through the controller; return structured JSON from `Outcome` and explain `superseded`/`outcome_unknown` honestly to the model. Instantiate and close per-room resources with `try/finally`. Add a CLI module entry point (`python -m reactor.voice.agent dev`) and `.env.example` with blank keys only. Do not silently connect to any model on import.
- [ ] **Verify offline:** full tests and package import, `git diff --check`, staged-file review; commit. After explicit free-quota confirmation, run one LiveKit voice session and one benchmark recording. Capture model ID, elapsed time, tool calls, and errors. If a session fails, record the failure accurately and debug before broader runs.

## Task 5: Benchmark smoke and submission readiness

- [ ] **Test first:** create a smoke runner that refuses an empty dataset or missing upstream revision and reports incomplete examples as failures rather than treating them as a pass. Ensure it does not require CUDA just to check recorded tool calls or invoke the exact-match evaluator on existing results.
- [ ] **Run red** before implementation. Use the actual upstream runner for audio inference; keep any Mac-only no-ASR path labelled as a development adaptation, not an official-equivalent evaluation.
- [ ] **Implement:** README commands for local `dev` and two-stage benchmark evaluation; provision a Colab T4 transcription notebook or script only after Python/NeMo installation works. Generate an artifact manifest with upstream SHA, dependency versions, model ID, mode, count of completed/failed examples, and timestamp, without secrets or full private recordings. Include the kitchen demo script and AI usage notes.
- [ ] **Verify:** run the full local suite, dry preflight, any credential-free upstream mock scenario, and a real voice/recording smoke test only under confirmed free quota. Avoid claiming official semantic results without an organizer-provided judge. Commit all verified changes; do not push without a new explicit user request.

## Execution handoff

First review and approve this integration plan. The user previously selected inline implementation and per-task commits; continue that method after plan approval. Live provider runs remain gated on verified free quota. Merge/push decisions remain with the user.
