# REACTOR offline-core checkpoint

Branch: `feat/reactor-core`. The offline milestone is implemented; live voice and FDB-v3 integration remain next.

## Verification

- `.venv/bin/python -m pytest -q`: 75 tests passed on Python 3.12, Apple M1 macOS.
- `.venv/bin/reactor-demo`: strict JSON output showing an obsolete 600-second proposal cancelled, one 420-second timer for duplicate proposals, and verified cancellation.
- `git diff --check`: no whitespace errors at the verified checkpoint.
- No API keys, hosted calls, CUDA, or benchmark labels were used by the tests or demo.
- No benchmark scores or live voice success are claimed.

## Implementation commits

| Commit | Checkpoint |
|---|---|
| `0c72baa` | Approved design, plan, and local-file exclusions |
| `ec4d0f8` | Session revisions and validated tool contracts |
| `40de6da` | Operation ledger and actual-call telemetry |
| `7da4953` | Interruption admission and execution ownership |
| `53aef44` | Kitchen timers, scripted demo, and setup README |
| `57a1ffc` | Hold read delivery while user input is unresolved |
| `f07df80` | Cancel pending obsolete work before predecessors finish |
| `9d7ff76` | Distinguish JSON booleans from numeric arguments |
| `8d0ab4f` | Report detached logging failures after draining session work |

Every implementation checkpoint passed the then-current full suite before commit. All commits are local; no push or merge was performed.

## Review

A fresh read-only review identified four important issues. Each was reproduced in a failing regression test, fixed, and followed by a passing full suite. No minor findings were deferred. The final fixes were verified with tests rather than a second review dispatch.

## Decisions and remaining boundaries

1. Logical action identity is explicit in the controller. The later semantic adapter must distinguish retries from intentional repeats; bad identity assignment can still suppress or duplicate actions.
2. Offline control semantics are the first milestone. Acoustic interruption, speech interpretation, and Gemini tool-call behavior require real provider integration and tests.
3. The telemetry shape is implemented, but upstream FDB reader compatibility, the 12 wrappers, full recordings, transcription, and scoring remain unverified. Integration may require further changes.
4. In-memory ownership is not crash-safe exactly-once execution. A running thread cannot be forcibly terminated; a permanently blocked backend can delay draining. The adapter must supply backend timeouts and a scenario deadline. Superseded operations that have not dispatched now cancel without waiting for that backend.
5. The environment tested is the existing M1/Python 3.12 setup. Fresh-machine installation, other Python versions, Colab/NeMo dependencies, and the organizers' Linux environment still need verification.

## Next milestone

Pin the upstream benchmark code; implement its tool adapters and the LiveKit/Gemini bridge; add credential preflight and baseline smoke runs; validate the Mac/Colab artifact workflow; then collect real benchmark evidence and a voice demo. The model identifier and free quota must be verified before any hosted run. Continue committing each verified implementation task as requested.
