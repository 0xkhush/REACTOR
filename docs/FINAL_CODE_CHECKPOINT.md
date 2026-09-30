# REACTOR final code verification checkpoint

This checkpoint completes the current implementation and documents its remaining submission and evaluation limits. It does not claim that all contest requirements or score targets are satisfied.

## Verification evidence

- Development environment: Python 3.12 on Apple M1, 209 pytest tests passing after the benchmark fixes.
- Fresh Python environment: installed `.[dev,voice]` into an empty virtual environment; full suite and `pip check` passed. This is a fresh environment on the same Mac, not a second physical machine or a fresh Linux test.
- Reproduction CLI: direct script and module help checked; offline `--check` verifies all 100 inputs and configuration without hosted requests. `bash scripts/reproduce.sh --check` provides install/preflight; full CUDA combined reproduction is not independently validated on a clean Linux host.
- Kaggle GPU: Parakeet sample transcription passed. The final ASR-only notebook completed and its reports/transcript records were downloaded and archived.
- Live kitchen: room `reactor-kitchen-dc7a039eb6d5` logged create at 420 seconds, list, cancel, and authoritative local spoken confirmations after tool success. Synthesized user speech was used. This is not a spontaneous human interruption test.
- No API secrets were placed in Git or the private audio/results datasets. Kaggle account authorization remained in the user's local CLI configuration.

## Independent review and fixes

A read-only fresh reviewer found seven significant voice/router problems. Regression tests reproduced them and the fixes were followed by full-suite verification:

1. Negated, compound, decimal or unsupported timer commands are rejected instead of extracting a different action.
2. Kitchen confirmations use local `say`/`espeak-ng` PCM audio supplied to LiveKit, rather than calling `say(text)` without a configured TTS. Unverified native-model audio is suppressed in kitchen mode.
3. Explicit logical action IDs distinguish identical intentional actions. Spoken repeat markers are recognized, while duplicate proposals can coalesce within one request.
4. Provider call IDs and known speech-generation IDs remain bound to their originating request. Replayed obsolete calls cannot execute as a new current request.
5. Seen final-event IDs are remembered across inputs; delayed known events cannot resolve a newer input. The SDK bridge uses provider ChatMessage IDs, not delivery timestamps.
6. Callback tasks are owned, exceptions retrieved, and error classes logged without exposing exception text.
7. Failed/superseded timer listing evidence produces an inability-to-verify response, not a false zero-timer or missing-timer claim.

Room-prefix mode selection additionally prevents concurrent unnamed smoke/batch workers from choosing kitchen tools for benchmark rooms.

## Remaining code/runtime limits

- Native speech perception and end-of-turn timing still depend on Gemini/LiveKit. Final transcripts can arrive after model generation begins. A previously unseen delayed generation cannot be attributed retroactively without provider provenance.
- Intent classification in benchmark mode is a conservative text heuristic, not a validated general semantic slot extractor.
- Repeat detection is intentionally limited; arbitrary identical actions in one utterance need explicit logical IDs or clarification. It is not universal exactly-once semantic inference.
- Already-dispatched writes cannot be undone by coroutine cancellation. There is no durable external transaction or crash-safe exactly-once guarantee.
- Network faults/rate limits can interrupt live runs. The known local kitchen router supports one clear timer action per utterance, not arbitrary combined commands.
- Docker configuration is supplied but has not been built in this environment. Linux kitchen mode needs `espeak-ng`; the CUDA ASR route needs an NVIDIA-capable runtime separately.
- Candidate `36a798b` received a dedicated full 100-recording capture: **42 expected tool selections and 23 strict exact passes**. Historical mixed-revision capture scored 12. The 40% strict target was not met. The new capture has no Parakeet transcription or semantic judge; see `docs/results/README.md`.

## Remaining user submission fields

- Team/college/member/contact details for the title slide and organizer form.
- Human review of the deck and demo narration; final public/accessible video link.
- Signed official AI usage disclosure where required; an AI cannot sign for the team.
- Final GitHub publication, merge choice and release-tag confirmation after the intended artifacts exist.
- Google Form submission and receipt. No portal submission has been performed.

Media rendering is deferred until the user approves proceeding beyond this code checkpoint.
