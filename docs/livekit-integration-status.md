# LiveKit/FDB-v3 integration checkpoint

Branch: `feat/reactor-livekit` (not merged or pushed).

## Live smoke evidence (29 September 2026)

After replacing the invalid LiveKit credential pair, the bounded smoke command connected to a LiveKit room, dispatched the local agent, streamed one 45.84-second FDB-v3 recording, and saved a WAV containing agent audio. The room-keyed actual-call log contains exactly one executed call: `track_order(order_id="ABC123")`. The diagnostic trace recorded proposal, launch, and success for that call. The worker shut down after the attempt. This demonstrates connectivity and one tool execution, not correctness over the whole benchmark or a semantic-judge score.

Command used with nonsecret temporary environment overrides (values in `.env.local` stayed ignored):

```bash
GOOGLE_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025 \
REACTOR_FREE_QUOTA_CONFIRMED=yes \
.venv/bin/python scripts/smoke_fdb.py --run --start-worker
```

The local account's Free-tier pricing was checked by the user and a bounded direct Gemini Live API request returned audio. The test result does not independently report how Google billed the request; the user should confirm ₹0 in AI Studio Usage before a full run.

## Verified offline

- The local `.env.local` has LiveKit and Google credentials; the file is ignored by Git and the values were not printed or committed.
- FDB-v3 source is pinned at `3e799c45a045256f47d5f1c9cda90157e2d2ec9e` under the ignored `vendor/` directory. `python scripts/setup_fdb.py` can restore this checkout from source.
- Twelve upstream mock tool contracts use per-room registries and the existing session controller; blocking mock latency runs outside the conversation event loop.
- The turn bridge, prompts, LiveKit entry point, Google raw function-tool registration, kitchen-timer tool routing and smoke/reproduction CLIs have offline checks.
- LiveKit Agents and its Google plugin are pinned together at `1.3.12`; installing mismatched `1.3.12` + `1.5.2` failed import and was resolved by pinning both.
- `pytest -q` passed 109 tests after smoke preflight hardening. `python scripts/smoke_fdb.py` found 100 audio recordings at the pinned revision. These two checks use no hosted model.
- A short direct Gemini Live request with the existing Google API key returned audio. This proves access but does not report billing; the account screenshot shows published free-tier prices for the model.
- On the first FDB audio smoke attempt, `ffmpeg` was missing; Homebrew `ffmpeg` has now been installed. The next attempt failed during LiveKit room connection with `401 invalid token`, before audio reached Gemini. A read-only room-list check independently returned 401 for the old LiveKit URL/key/secret. Updated credentials resolved that blocker.
- `smoke_fdb.py` now validates `ffmpeg` and the LiveKit credential set before starting the worker. Full local suite: 109 passing tests after these additions.

## Not yet verified

- Broader LiveKit/Gemini voice coverage, transcription-event timing across pauses, actual speech interruption, and audio-based self-correction.
- An actual FDB inference run, official-style tool telemetry extraction from a recorded session, Parakeet on Colab, and semantic judge results.
- `scripts/reproduce.py` has not been executed on a CUDA Linux machine; its `--help` and offline components were checked only. Exact-match reports from that script are not official scores.

The local `.env.local` currently has no selected `GOOGLE_LIVE_MODEL` or persistent free-quota flag. A one-off, nonsecret process-environment override was used for the bounded smoke attempt. The CLI refuses live calls unless the model and explicit free-quota flag are supplied.

## Next interactive test

1. Confirm AI Studio Usage remained at ₹0 after the bounded Live test; only then budget further hosted calls.
2. Evaluate the single smoke example with the pinned local exact-match evaluator or add a more varied small sample; use no benchmark metadata in the agent runtime.
3. Verify the full NVIDIA/Parakeet path or a labelled Mac/Colab split before reporting full benchmark numbers.
4. Diagnose the actual output, record one benchmark result, then repeat only if the free quota allows it.
