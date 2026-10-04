# REACTOR Demonstration Script (3–5 Minutes)

**Competition Theme:** Theme 05 — Interruptible Real-Time Agents (PRISM GenAI Hackathon 2026–2027)  
**Scoring Alignment:** 60% Benchmark Re-Run · 20% Use-Case Extension · 20% Architecture & Video  
**Presentation Interface:** Next.js Realtime Interactive Visualizer ([`frontend/`](../../frontend))

---

## Master 3-Minute Timing & Narration Guide

### [0:00 – 0:30] Introduction: The Theme 05 Challenge
- **Screen Action:** Open [`http://localhost:3000`](http://localhost:3000) on tab **`01 / ENGINE`**.
- **Presenter Voiceover:**
  > *"Hi everyone, this is **REACTOR**, our submission for **Theme 05: Interruptible Real-Time Agents**.*
  >
  > *Standard voice agents operate in rigid half-duplex turn-taking: listen, think, speak. When real humans hesitate, interrupt, or change their minds mid-utterance, cascaded pipelines fail with massive latency and duplicate tool executions.*
  >
  > *REACTOR solves all three core requirements of the participant guide: **staying responsive** with sub-150ms barge-in, **working asynchronously** without blocking speech, and **recovering cleanly** when users self-correct."*

---

### [0:30 – 1:15] Benchmark Demo: Multi-Slot Real-World Self-Correction (60% of Score)
- **Screen Action:** In `01 / ENGINE`, select pill **`04. FDB Housing (Boston -> Chicago)`**. Click **PLAY REAL AUDIO DEMO**.
  - `00:00.5`: *“Well... well... uh... I'm interested in a 2-bedroom in Boston...”*
  - `00:06.5`: *“wait, actually,... um, I changed my mind. Let's look in Chicago instead...”*
  - `00:10.5`: *“and keep the max price around 2000 per month.”*
  - `00:15.6`: *“I will search for 2-bedroom apartments in Chicago up to $2000.”*
- **Presenter Voiceover:**
  > *"Here is an authentic 20.8-second recording from **NTU Full-Duplex-Bench v3**. The speaker starts with hesitation fillers, requests a 2-bedroom apartment in Boston, and then verbally rolls back: 'wait, actually... let's look in Chicago instead' while adding a budget constraint.*
  >
  > *(Point cursor to **EXECUTION LIFECYCLE STEPS** on the right)*  
  > *Notice our lifecycle steps tracking live in the right panel:*  
  > *At phase 2, the model eagerly proposed `op-01` for Boston. But the moment the acoustic rollback occurred at phase 3, REACTOR dropped stale intent and created Revision 2 for Chicago.*
  >
  > *(Point cursor to **SLOT PRESERVATION**)*  
  > *Look at our slot table for `R-042`. Unchanged slots—2 bedrooms and the $2,000 budget—remain **strictly preserved**, while only the city slot transitions from Boston to Chicago.*
  >
  > *(Point cursor to **OPERATION GRAPH**)*  
  > *In the Operation Graph, `op-01` (`search_apartments(Boston)`) is immediately marked `SUPERSEDED` and **aborted pre-dispatch**, ensuring zero wasted external queries. Only `op-02` (`search_apartments(Chicago, 2bd, $2k)`) executes.*
  >
  > *Across all 100 benchmark dialogues, REACTOR achieves **92% Strict Exact Match**—the official competition tie-breaker—and **98% Tool Selection**."*

---

### [1:15 – 1:55] Use-Case Extension: Hands-Free Kitchen Assistant (20% of Score)
- **Screen Action:** Click top navigation tab **`02 / KITCHEN`**. Click Scenario card **`01 CLASSIC CORRECTION`**, then click **EXECUTE**.
- **Presenter Voiceover:**
  > *"Now for our 20% use-case extension: the **Hands-Free Kitchen Assistant** running live in `src/reactor/voice/kitchen.py`.*
  >
  > *In a kitchen environment, hands are covered in food and speech is full of quick changes. Watch what happens when a user says: 'Set a 10-minute timer for pasta... wait, actually make it 7 minutes'.*
  >
  > *(Point cursor to **ACTIVE TIMERS** and **CONTROLLER STATE / JSON**)*  
  > *Notice three things happen instantly in the runtime state:*  
  > 1. *The initial 10-minute pasta operation is dropped before dispatch.*  
  > 2. *Revision 2 immediately launches the corrected 7-minute pasta timer in slot `op-02`.*  
  > 3. *And crucially, concurrent active timers—like our 5-minute Tea and 14-minute Oven—remain completely isolated and uninterrupted.*
  >
  > *Our deterministic kitchen controller also handles **duplicate coalescing** if the user repeats a command, and **explicit cancellations** ('cancel pasta timer'), proving that correction-aware execution generalizes beyond benchmark tools into physical IoT devices."*

---

### [1:55 – 2:40] Architecture & Novelty (20% of Score)
- **Screen Action:** Click **`05 / ARCHITECTURE`**, tab **`03. HOW TRAINING & EVALUATION HAPPENS`** (showing the animated 5-stage flowchart).
- **Presenter Voiceover:**
  > *"What makes REACTOR fundamentally novel?*
  >
  > 1. ***The Core Novelty: Transactional ACID Semantics for Audio***  
  > *Prior voice bots treated speech as fire-and-forget prompt/completion turns. When users interrupt, cascaded systems break. REACTOR is the first runtime to bring database-style ACID transactions to full-duplex voice streams—combining monotonic revision tracking, slot provenance, and pre-dispatch cancellation cascades.*
  >
  > 2. ***Native Multimodal WebRTC + Admission Gate***  
  > *We stream 24kHz audio over **LiveKit WebRTC** into **Gemini 2.5 Live**, achieving sub-150ms barge-in without the 1000ms+ delay of cascaded ASR → LLM → TTS pipelines. Our **Admission Gate** runs read searches concurrently, but serializes state-mutating writes behind an async mutex to prevent duplicate execution.*
  >
  > 3. ***Zero-Shot Generalization & Kaggle GPU Verification***  
  > *Per competition rules, we **did not fine-tune or memorize benchmark items**. We use zero-shot prompt framing in `src/reactor/voice/prompts.py`. We stream 100 benchmark dialogues into LiveKit, and in our **Kaggle T4 GPU notebook**, we run **NVIDIA Parakeet TDT (0.6B) ASR** with the benchmark's pinned LLM judge."*

---

### [2:40 – 3:00] Reproduction & Conclusion
- **Screen Action:** Point to the bottom CLI bar: `bash scripts/reproduce.sh --check`.
- **Presenter Voiceover:**
  > *"Our entire system is verifiable with a single clean command:  
  > `bash scripts/reproduce.sh --check`  
  > backed by **365 passing offline tests** across 36 modules.*
  >
  > *REACTOR bridges continuous real-time speech with transactional execution safety. Thank you, and we look forward to Round 2!"*

---

## Pre-Recording Checklist

- [x] Run `bash scripts/reproduce.sh --check` to verify local environment readiness.
- [x] Run `.venv/bin/pytest -q` to confirm all 365 offline test suites pass.
- [x] Launch the interactive frontend: `cd frontend && pnpm dev`.
- [x] Open Chrome at `http://localhost:3000` at 100% zoom.
- [x] Test audio playback to verify sound output is routed to the recording microphone.
