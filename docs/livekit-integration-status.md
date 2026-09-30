# LiveKit/FDB-v3 integration checkpoint

The LiveKit integration was fast-forward merged and pushed to `main` at `b2622ba`. Kaggle evaluation work continues on `feat/kaggle-evaluation`.

## Live smoke evidence (29 September 2026)

After replacing the invalid LiveKit credential pair, the bounded smoke command connected to a LiveKit room, dispatched the local agent, streamed one 45.84-second FDB-v3 recording, and saved a WAV containing agent audio. The room-keyed actual-call log contains exactly one executed call: `track_order(order_id="ABC123")`. The diagnostic trace recorded proposal, launch, and success for that call. The worker shut down after the attempt. This demonstrates connectivity and one tool execution, not correctness over the whole benchmark or a semantic-judge score.

Command used with nonsecret temporary environment overrides (values in `.env.local` stayed ignored):

```bash
GOOGLE_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025 \
REACTOR_FREE_QUOTA_CONFIRMED=yes \
.venv/bin/python scripts/smoke_fdb.py --run --start-worker
```

The local account's Free-tier pricing was checked by the user and a bounded direct Gemini Live API request returned audio. The test result does not independently report how Google billed the request; the user should confirm ₹0 in AI Studio Usage before a full run.

### Three-domain development sample

Each row is a separate LiveKit room with an actual agent audio output and one pinned FDB-v3 exact-match check; no LLM judge or full-benchmark denominator was used for the curated smoke rows.

| Recording | Observed tool calls | Local exact-match tool result | Interpretation |
|---|---|---|---|
| `ecommerce_01` | `track_order(order_id="ABC123")` | Pass | Correct tool and argument in this run |
| `travel_01` | `search_flights(destination="Tokyo", date="2026-07-15")` | Fail | Reference date is `July 15`; semantic equivalence is plausible but unjudged |
| `finance_01` | `get_exchange_rate(amount=500, from_currency="USD", to_currency="EUR")` | Pass **once** | Repeated runs varied; see full exact pass results below |

Rerunnable, generated evidence lives at ignored `artifacts/smoke-summary-exact.json` (not checked in). It reports: 3 recordings; tool selection 3/3; exact argument comparison 2/3; strict tool result 2/3. This is a hand-selected smoke sample, not a statistically representative score, not scored by the pinned semantic judge, and not comparable to the contest's official normalized benchmark result.

On failed finance runs, traces showed intermittent behavior: sometimes no tool proposal; sometimes a `get_exchange_rate` proposal followed by an SDK validation error before controller dispatch; and one run succeeded. The root cause remains unresolved. Do not claim the error is fixed. Tool-proposal and SDK error diagnostics record only call IDs, argument types, and exception classes, not credentials or raw model arguments.

## Verified offline

- The local `.env.local` has LiveKit and Google credentials; the file is ignored by Git and the values were not printed or committed.
- FDB-v3 source is pinned at `3e799c45a045256f47d5f1c9cda90157e2d2ec9e` under the ignored `vendor/` directory. `python scripts/setup_fdb.py` can restore this checkout from source.
- Twelve upstream mock tool contracts use per-room registries and the existing session controller; blocking mock latency runs outside the conversation event loop.
- The turn bridge, prompts, LiveKit entry point, Google raw function-tool registration, kitchen-timer tool routing and smoke/reproduction CLIs have offline checks.
- LiveKit Agents and its Google plugin are pinned together at `1.3.12`; installing mismatched `1.3.12` + `1.5.2` failed import and was resolved by pinning both.
- `pytest -q` passed 120 tests after smoke preflight and diagnostics. `python scripts/smoke_fdb.py` found 100 audio recordings at the pinned revision. These two checks use no hosted model.
- A short direct Gemini Live request with the existing Google API key returned audio. This proves access but does not report billing; the account screenshot shows published free-tier prices for the model.
- On the first FDB audio smoke attempt, `ffmpeg` was missing; Homebrew `ffmpeg` has now been installed. The next attempt failed during LiveKit room connection with `401 invalid token`, before audio reached Gemini. A read-only room-list check independently returned 401 for the old LiveKit URL/key/secret. Updated credentials resolved that blocker.
- `smoke_fdb.py` now validates `ffmpeg` and the LiveKit credential set before starting the worker. Full local suite: 109 passing tests after these additions.

## Full capture and tool scoring (30 September 2026)

The Mac retry batch finished processing the full 100 recordings: **37 had one or more executed tool calls, 63 produced no tool call, and 0 failed at audio/LiveKit capture**. The pinned exact tool/argument evaluator scored **25/100 expected tool selections and 12/100 strict passes**. This is a full-denominator, local exact-match diagnostic; it is **not** the organizers' normalized score or semantic-judge evaluation. `artifacts/batch-call-eval-exact.json` and `artifacts/batch_inference/batch-manifest.json` contain the local evidence and are Git-ignored.

## Not yet verified

- Broader LiveKit/Gemini voice coverage, transcription-event timing across pauses, actual speech interruption, and audio-based self-correction.
- An actual FDB inference run, official-style tool telemetry extraction from a recorded session, Parakeet on Colab, and semantic judge results.
- `scripts/reproduce.py` has not been executed on a CUDA Linux machine; its `--help` and offline components were checked only. Exact-match reports from that script are not official scores.

## Kitchen voice extension status (30 September)

The live kitchen smoke now works end to end in a same-room, synthesized two-turn exchange. It creates a `pasta` timer at 420 seconds from a ten-to-seven-minute self-correction, lists timers on the next turn, cancels using the returned ID, and speaks the confirmed status. The actual tool log contains `create_timer`, `list_timers`, and `cancel_timer`. This uses a conservative kitchen-only transcript command parser because Gemini repeatedly refused the timer tool calls. It demonstrates the intended extension scenario using generated audio, not a human spontaneous interruption. Ambiguous timer commands are not locally dispatched.

The private Kaggle input dataset contains 100 audio files and excludes scenario answers and API keys. Kaggle's T4 successfully loaded `nvidia/parakeet-tdt-0.6b-v2` and transcribed a sample. The full overnight-inference kernel stopped at a Kaggle Secrets grant gate; **no Gemini inference ran there**. A separate ASR-only Kaggle run scored the currently uploaded partial result bundle. Its local exact report indicates 100 result records with 26 captures complete, 7 with no tool call, and 67 inference failures in that packaged version; strict pass rate 10/100, judge disabled. This was superseded by the final Mac capture batch and must not be cited as its score.

The local `.env.local` is Git-ignored. One-off nonsecret environment overrides select the Gemini model and confirm free-tier intent. User confirmed AI Studio balance remained ₹0 and no card is connected. The Kaggle ASR-only notebook needs no API secrets.

## Next interactive test

1. Refresh the private Kaggle result dataset from final batch artifacts and rerun `remote_eval/asr_eval`; gather the final ASR/transcript and exact-match outputs.
2. Do not present the 12/100 local strict pass rate as official or claim qualification from these results.
3. Complete title slide details, record the video from the verified artifacts/live kitchen workflow, sign the AI disclosure, and publish the final release tag.
