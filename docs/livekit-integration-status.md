# LiveKit/FDB-v3 integration checkpoint

Branch: `feat/reactor-livekit` (not merged or pushed).

## Verified offline

- The local `.env.local` has LiveKit and Google credentials; the file is ignored by Git and the values were not printed or committed.
- FDB-v3 source is pinned at `3e799c45a045256f47d5f1c9cda90157e2d2ec9e` under the ignored `vendor/` directory. `python scripts/setup_fdb.py` can restore this checkout from source.
- Twelve upstream mock tool contracts use per-room registries and the existing session controller; blocking mock latency runs outside the conversation event loop.
- The turn bridge, prompts, LiveKit entry point, Google raw function-tool registration, kitchen-timer tool routing and smoke/reproduction CLIs have offline checks.
- LiveKit Agents and its Google plugin are pinned together at `1.3.12`; installing mismatched `1.3.12` + `1.5.2` failed import and was resolved by pinning both.
- `pytest -q` passed 105 tests. `python scripts/smoke_fdb.py` found 100 audio recordings at the pinned revision. Both checks use no hosted model.

## Not yet verified

- LiveKit/Gemini voice connection, model free-tier availability, transcription-event timing, actual speech interruption, and audio-based self-correction.
- An actual FDB inference run, official-style tool telemetry extraction from a recorded session, Parakeet on Colab, and semantic judge results.
- `scripts/reproduce.py` has not been executed on a CUDA Linux machine; its `--help` and offline components were checked only. Exact-match reports from that script are not official scores.

The local `.env.local` currently has no selected `GOOGLE_LIVE_MODEL` and no confirmed free-quota flag. The CLI deliberately refuses a live connection until those are supplied. Inspect the model's plan and quotas in Google AI Studio before setting `REACTOR_FREE_QUOTA_CONFIRMED=yes`; the presence of an API key alone does not establish free inference.

## Next interactive test

1. User confirms the exact Live API model covered by their free quota, without sharing API keys.
2. User adds `GOOGLE_LIVE_MODEL=<model ID>` and `REACTOR_FREE_QUOTA_CONFIRMED=yes` to ignored `.env.local`.
3. Run `.venv/bin/python -m reactor.voice.agent dev` in one terminal and `.venv/bin/python scripts/smoke_fdb.py --run` in another.
4. Diagnose the actual output, record one benchmark result, then repeat only if the free quota allows it.
