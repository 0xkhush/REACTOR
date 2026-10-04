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

Full-denominator evaluation across all 100 released FDB-v3 recordings: 100 audio sessions completed (0 transport failures, 0 no-tool dropouts). Pinned FDB-v3 exact tool/argument evaluation: **92/100 (92.0%) strict exact passes** (95% CI: [85.0%, 95.9%]) and **98/100 (98.0%) tool selection accuracy** (up from baseline 12% exact / 25% tool selection). With fair semantic argument evaluation (Google Gemma-4-31B-IT): **94/100 (94.0%)**. All 100 capture traces and actual-call logs are saved for independent inspection.

## Slide 6: Extension demonstration

Hands-free kitchen timer extension: a live same-room smoke created one named 420-second timer after a spoken correction, then listed and cancelled it by returned ID. Actual-call logs show `create_timer`, `list_timers`, and `cancel_timer`. This smoke uses synthesized speech and a kitchen-only final-transcript router, not a spontaneous human interruption.

## Slide 7: Reproduction and limitations

Python 3.12, LiveKit Agents 1.3.12, Gemini 2.5 Native Audio, original FDB-v3 mock tools, pinned upstream. Kaggle T4 transcribed the historical capture; the new capture has tool-call exact scoring only. Provider quotas and already-dispatched writes limit cancellation guarantees.

## Slide 8: Next steps

Improve correction grounding across live audio, validate longer tool chains, and compare against the unmodified upstream Gemini template on all recordings. Add a supported reversal tool only when the environment offers one. Include the full GitHub repo and recorded demo link.

## Attribution and disclosure notes

FDB-v3 code/data by National Taiwan University; cite Lin et al. 2026 (arXiv:2604.04847), repository `https://github.com/DanielLin94144/Full-Duplex-Bench`, licensed CC BY-NC 4.0. Disclose that AI assistance was used for architecture, code, tests, documentation, and debugging; describe team modifications and validation accurately in the organizer's AI usage form.
