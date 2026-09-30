# REACTOR: eight-slide submission content

This is slide copy for the participant guide's **at most eight slides**. Replace team/college/contact placeholders before export. Use only verified numbers and working demo clips.

## Slide 1: Title

REACTOR — Interruptible Real-Time Voice Agent · Theme 05 · [College] · [Team members] · https://github.com/0xkhush/REACTOR · [Video link]

## Slide 2: Problem

Users hesitate and correct themselves while an agent talks or uses tools. A stale search may return after the destination changes; repeating a booking or cart action can create a second side effect. A useful agent must speak promptly, act on current intent, and accurately report what happened.

## Slide 3: Architecture

LiveKit voice session → Gemini Live → session turn bridge → versioned intent and operation ledger → FDB-v3 mock tools or kitchen timers → actual-call trace and spoken result. The controller serializes writes, prevents duplicate logical actions, and withholds stale read results. A dispatched write remains recorded even if the user changes intent.

## Slide 4: Benchmark method

Full-Duplex-Bench v3: 100 recordings from 12 speakers across 79 scenarios and 12 tools. Pin upstream commit `3e799c45`; preserve original mock results and tool-call telemetry. Report completed/failed/missing counts, strict tool pass rate, argument accuracy, and first-response latency. The organizer's semantic judge is not part of local ₹0 evaluation.

## Slide 5: Measured evidence

Local smoke evidence before the overnight run: expected tool selected for all three hand-picked recordings; exact arguments passed for two. One travel ISO date differs from the reference's natural-language date and is penalized by exact comparison; repeated finance audio was unreliable. Replace this slide with an actual full-run report only after the GPU job completes. Never report 2/3 as the benchmark score.

## Slide 6: Extension demonstration

Hands-free kitchen timers: revise ten minutes to seven, create one timer, cancel by verified ID, and speak the confirmed state. Include a still/frame from a **live** voice run rather than the scripted core test.

## Slide 7: Reproduction and limitations

Python 3.12, LiveKit Agents 1.3.12, Gemini 2.5 Native Audio, original FDB-v3 mock tools, pinned upstream. `scripts/setup_fdb.py` and `scripts/reproduce.py` document setup. A full NVIDIA ASR + semantic judge path is not yet verified unless the overnight report proves it. Provider quotas and already-dispatched external writes limit cancellation guarantees.

## Slide 8: Next steps

Improve correction grounding across live audio, validate longer tool chains, and compare against the unmodified upstream Gemini template on all recordings. Add a supported reversal tool only when the environment offers one. Include the full GitHub repo and recorded demo link.

## Attribution and disclosure notes

FDB-v3 code/data by National Taiwan University; cite Lin et al. 2026 (arXiv:2604.04847), repository `https://github.com/DanielLin94144/Full-Duplex-Bench`, licensed CC BY-NC 4.0. Disclose that AI assistance was used for architecture, code, tests, documentation, and debugging; describe team modifications and validation accurately in the organizer's AI usage form.
