# REACTOR demo script (3–5 minutes)

Use a single screen recording with the LiveKit room, spoken output, and room-keyed actual-call log visible. Keep the video under five minutes. The benchmark recording and the kitchen extension must both run end to end; do not substitute the scripted offline demo for the kitchen voice demonstration.

## 0:00–0:40: Problem and runtime

"A half-duplex assistant can act on a stale request when a person changes their mind. REACTOR adds session revisions, a write gate, and a ledger around a LiveKit voice model. We use the FDB-v3 tool interface and keep the conversation responsive while calls run."

Show the README architecture and the project revision used for the video. Identify the provider and the source of the mock tools.

## 0:40–1:55: Benchmark audio

Run `python scripts/smoke_fdb.py --run` against a real released recording. Show the captured audio and actual tool call with room ID. Use a correction example only after it has passed live testing; do not narrate a correction that the trace does not show.

The three recorded development examples as of 29 September 2026: `ecommerce_01` passed the local exact-match tool check, `travel_01` selected the expected tool but failed strict date formatting, and `finance_01` passed on one run but was intermittent on repeats. These are **not** official benchmark results and should not be presented as a full score.

## 1:55–3:15: Kitchen extension

In a live kitchen-mode room, say "Set a timer for ten minutes—actually seven." Show a single timer with `duration_seconds=420`. Then say "Cancel the pasta timer." Show `cancel_timer` reporting `cancelled` and verify with `list_timers`. Record this live before claiming an end-to-end extension. The offline `reactor-demo` proves only controller behavior.

## 3:15–4:10: Evidence and limitations

Show the exact run manifest, full-suite tests, and any Kaggle report that has actually completed. Describe the evaluator mode precisely: local exact matching without the paid semantic judge. State the number of completed recordings as the denominator, including timeouts and missing results. Call out the remaining live failure classes if they persist.

## 4:10–4:40: Reproduction

Point to `README.md`, the pinned FDB-v3 commit, the private dataset setup instructions, and the one-command reproduction path. Explain that credentials are supplied by the evaluator and not included in the repository.

## Final recording checklist

- Screen and audio clearly show a **real** benchmark interruption or self-correction, with tool evidence matching the narrated result.
- Screen and audio clearly show a **real** kitchen timer correction and cancellation.
- No secrets or private account pages are visible.
- Results are named as exact-match or official semantic-judge results according to how they were generated.
- The final video link is in the README and slide deck before submission.
