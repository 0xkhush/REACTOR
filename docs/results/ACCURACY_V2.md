# Accuracy-v2 measured checkpoint

## Latest completed candidate

Branch: `feat/tool-call-accuracy-v2`. Runtime and replay commit: `9150eb6c8ca831527ce58da15190b64449663886`.

The full local exact tool/argument check covered all 100 released recordings:

| Metric | Count |
| --- | ---: |
| Strict exact tool/argument passes | **57/100 (57%)** |
| Expected tool multiset matches | **80/100** |
| Recordings with executed calls | 91 |
| Recordings without executed calls | 9 |
| Capture failures / missing result records | 0 / 0 |

**The requested strict accuracy above 80% was not reached.** Tool selection is a separate metric from complete strict passes. `9150eb6-call-exact.json` preserves the per-recording score and failure reasons; SHA-256: `4af1a662ca2e09174818e36539e53af74fe5a64a362611235e9a4d1a3069ba22`.

No ASR or semantic judge evaluated this candidate. This is not an official normalized score or proof of spoken-response quality. The pinned scorer reads scenario definitions only in its separate process; the runtime never loads answers or scenario IDs.

## Changes and evidence

- Conservative argument normalization preserves signs and integer precision, removes valid date ordinals, and canonicalizes known account/document labels.
- Benchmark-only VAD waits through two seconds of silence. This trades response latency for tolerance of hesitations; kitchen timing remains unchanged.
- Actual callback tests reproduced a tool-chain deadlock: Google 1.3.12 synthesizes speaking events when it resumes after a tool result. Those events no longer open the controller input hold. Non-empty partial user transcription opens the hold; the provider user item resolves it. SDK audio interruption remains active, but the hold starts with transcript evidence rather than the first audio sample.
- Grounding uses the originating request's transcript, after provider/generation binding. It removes inferred ISO years only when the same user-stated month/day has no explicit year, and joins separately spelled single-character identifiers. Meaningful punctuation and multi-character tokens remain unchanged. Correction-aware repeat intent is kept separate from accumulated date evidence.
- The replay client waits for `reactor.ready=1` from an agent participant before streaming. Input samples remain unchanged, playback uses a monotonic clock, and recorded audio retains arrival-time silence. Receiver errors fail capture instead of silently producing a successful WAV.
- The suite passed **285 tests**. Three-step shopping and flight live probes demonstrated chain completion; they are curated development evidence, not a benchmark pass rate.

## Previous runs and comparability

The historical `ceafcee` capture scored 30/100 strict passes and 54/100 expected tool selections. A full capture at `583ee21` scored 36/100 and 57/100, with three inference failures kept in the denominator.

The `d16b23a` capture was interrupted after traces confirmed agent startup after the upstream client's fixed replay window. Its existing attempts remain in a separate ignored folder; it is not a full-run score and was not resumed with new code.

The latest run uses `scripts/ready_inference.py`, whereas earlier runs used the upstream fixed-two-second-start client. Input audio and the pinned tool scorer are unchanged, but the capture harness and runtime differ. These are independent hosted-model captures, not a controlled paired experiment. Do not attribute the entire measured difference to one fix or claim sub-second latency from it.

## Remaining accuracy work

Twenty-three recordings matched the expected tools but failed exact arguments. Twenty did not match the complete tool multiset. Remaining failures include altered identifier punctuation, shortened/misheard identifiers, product-query phrasing, card-category phrasing, ungrounded location aliases, and incomplete requests. Some are semantic/ASR errors; others are formatting mismatches that a semantic judge could treat differently. No hypothetical judge score is claimed.

A further structured planning or transcript-grounding change needs a separate design and fresh verification. The 57% checkpoint should remain reproducible while that work proceeds.

## Reproduce

From the improvement worktree, supply the ignored local credentials and released audio. When reusing the main checkout's environment, set `PYTHONPATH` to the worktree's `src` so the worker imports the candidate:

```bash
PYTHONPATH="$PWD/src" REACTOR_MODE=benchmark \
GOOGLE_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025 \
REACTOR_FREE_QUOTA_CONFIRMED=yes \
/Users/khush/Documents/experiment/prism/.venv/bin/python scripts/batch_infer.py \
  --output "$PWD/artifacts/NEW_CAPTURE_FOLDER"

PYTHONPATH="$PWD/src" /Users/khush/Documents/experiment/prism/.venv/bin/python \
  scripts/evaluate_batch_calls.py --outputs "$PWD/artifacts/NEW_CAPTURE_FOLDER" \
  --output "$PWD/artifacts/NEW_CAPTURE_FOLDER/call-exact.json"
```

Do not combine captures or replay successful/no-tool cases to select a better result. No merge or push of this branch has occurred.
