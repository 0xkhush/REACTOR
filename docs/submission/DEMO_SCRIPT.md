# REACTOR demo script (3–5 minutes)

Use a single screen recording with the LiveKit room, spoken output, and room-keyed actual-call log visible. Keep the video under five minutes. The benchmark recording and the kitchen extension must both run end to end; do not substitute the scripted offline demo for the kitchen voice demonstration.

## 0:00–0:40: Problem and runtime

"A half-duplex assistant can act on a stale request when a person changes their mind. REACTOR adds session revisions, a write gate, and a ledger around a LiveKit voice model. We use the FDB-v3 tool interface and keep the conversation responsive while calls run."

Show the README architecture and the project revision used for the video. Identify the provider and the source of the mock tools.

## 0:40–1:55: Benchmark audio

Run `python scripts/smoke_fdb.py --run` against a real released recording. Show the captured audio and actual tool call with room ID. Use a correction example only after it has passed live testing; do not narrate a correction that the trace does not show.

Mac capture batch: 100 audio attempts, 37 with calls, 63 without, 0 capture failures. Local exact tool/argument evaluation: 25/100 expected tool selections and 12/100 strict passes. This is not an official score; the semantic judge was not used. Mention the date-format mismatch and variable finance tool calls.

## 1:55–3:15: Kitchen extension

The live smoke uses synthesized speech in one kitchen-mode room: "Please create a timer called pasta for 10 minutes. Actually, make it seven minutes." Show `create_timer` once with `duration_seconds=420`, then "Please cancel the timer called pasta." Show `list_timers`, `cancel_timer`, and the confirmed response. State that a kitchen-only final-transcript router dispatches clear timer commands; this is not a spontaneous human interruption test.

## 3:15–4:10: Evidence and limitations

Show the full run manifest, exact-match report, and full-suite tests. Describe the evaluator mode precisely: local exact matching without the semantic judge. State attempted, completed, no-tool and failed counts. Explain the 12/100 strict pass result candidly.

## 4:10–4:40: Reproduction

Point to `README.md`, the pinned FDB-v3 commit, the private Kaggle dataset and download instructions. Explain that credentials are configured locally or through Kaggle Secrets, never committed.

## Final recording checklist

- Screen and audio clearly show a **real** benchmark interruption or self-correction, with tool evidence matching the narrated result.
- Screen and audio clearly show a **real** kitchen timer correction and cancellation.
- No secrets or private account pages are visible.
- Results are named as exact-match or official semantic-judge results according to how they were generated.
- The final video link is in the README and slide deck before submission.
