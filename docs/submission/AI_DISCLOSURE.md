# AI Usage DISCLOSURE FORM
**Samsung PRISM Generative AI Hackathon — 3rd Edition (2026 – 2027)**  
**Theme 05: Full-Duplex Voice Agents**

---

### 1. Team Details
- **Team Name:** REACTOR
- **Project / Product Name:** REACTOR (Correction-Aware Execution Engine for Interruptible Voice Agents)
- **Organization / Institution (if any):** Vellore Institute of Technology, Vellore (VIT Vellore)
- **Submission Date:** September 30, 2026

**Team Members:**
1. Atharva Mendhulkar (`atharvamendhulkar01@gmail.com`) — Team Representative
2. Khushvendra Singh (`0xkhush@gmail.com`)
3. Ritwij Tripathi (`vasutr2007@gmail.com`)

---

### 2. AI Usage Declaration
- **Did your team use any Artificial Intelligence (AI) in developing this project?**  
  **Yes**  
- **Context & Scope:** AI tools were utilized as an assistive pair-programming companion for initial architecture exploration, asyncio boilerplate scaffolding, unit test coverage, and documentation drafting under strict human oversight and manual verification. Additionally, Google Gemini 2.5 Flash is integrated as the runtime conversational voice LLM.

---

### 3. Purpose of AI Usage (Brief Details)
- **Idea generation / brainstorming:** Explored state-machine designs for voice barge-in, turn-taking race condition edge cases, and cascade cancellation patterns for interrupted tool calls.
- **Code generation or assistance:** Assisted in generating Python 3.12 asyncio primitives, jsonschema contract validation routines, LiveKit agent adapter boilerplate, and Kaggle GPU automation scripts.
- **UI / UX design:** N/A (Project is a headless backend execution engine with real-time WebRTC audio transport and terminal/JSONL diagnostic telemetry).
- **Content creation:** Assisted in drafting documentation, presentation slide text (`VITV_Team-REACTOR.pptx`, `docs/submission/SLIDES.md`), and demo script narration (`docs/submission/DEMO_SCRIPT.md`).
- **Data analysis:** Automated aggregation and tabular formatting of Full-Duplex-Bench v3 evaluation metrics, latency percentiles, and ASR word-error/accuracy reports.
- **Testing / debugging:** Assisted in creating the comprehensive 203-test offline suite (`pytest`, `pytest-asyncio`), mocking race conditions, and diagnosing Linux dependency conflicts on Kaggle.
- **Other:** Formatting benchmark reproducibility commands and GitHub submission compliance checklists.

---

### 4. Feature Origin Classification

#### Feature 1: Versioned Intent Controller (`src/reactor/controller.py`, `src/reactor/state.py`)
- **Origin:** **Both** (Human-architected, AI-assisted implementation)
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity / Claude 3.5 Sonnet / Gemini.
  - **Prompts Used:** *"Design an asyncio execution engine that assigns monotonic revision IDs to user speech turns, allowing in-flight tool proposals to be superseded when a correction is detected."*
  - **Output Summary:** Drafted `SessionController` and `OperationLedger` classes tracking request revisions and pending futures.
  - **Human Modifications & Review:** Manually refined state transition locks, added strict state invariants (`PROPOSED` &rarr; `IN_FLIGHT` &rarr; `EXECUTED`/`CANCELLED`), and enforced zero dead-air during async execution.

#### Feature 2: Cascade Cancellation & Deduplication Engine (`src/reactor/state.py`)
- **Origin:** **Both**
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity / Gemini.
  - **Prompts Used:** *"Implement an idempotency hash and cancellation cascade that drops superseded tool calls before network dispatch while sharing identical requests."*
  - **Output Summary:** Generated `action_identity` hashing function and cancellation trigger hooks for superseded revision IDs.
  - **Human Modifications & Review:** Verified against race condition tests to ensure cancelled tasks cleanly release locks and return immediately without unhandled exceptions.

#### Feature 3: Write-Serialization Gate (`src/reactor/controller.py`)
- **Origin:** **Both**
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity.
  - **Prompts Used:** *"Implement a concurrency gate that permits parallel read tools but strictly serializes state-mutating writes."*
  - **Output Summary:** Drafted reader-writer lock wrapper around tool dispatch.
  - **Human Modifications & Review:** Replaced generic locks with a lightweight asyncio FIFO write queue to guarantee deterministic write order without deadlocks.

#### Feature 4: Full-Duplex-Bench v3 Adapter & Reproducibility Harness (`src/reactor/tools/benchmark.py`, `scripts/reproduce.py`)
- **Origin:** **Both** (Upstream NTU Benchmark + AI/Human Adapters)
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity.
  - **Prompts Used:** *"Create a non-intrusive adapter wrapping NTU Full-Duplex-Bench v3 mock APIs into LiveKit tool schemas without modifying upstream benchmark ground truth."*
  - **Output Summary:** Adapter dynamically importing `mock_apis.py` from pinned upstream checkout (`3e799c45`) with typed schema generation.
  - **Human Modifications & Review:** Enforced strict zero-answer leakage invariant: verified `src/reactor/` contains zero benchmark scenario data or precomputed answers.

#### Feature 5: Realtime Voice Transport & Gemini Live Bridge (`src/reactor/voice/`)
- **Origin:** **Both**
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity.
  - **Prompts Used:** *"Bridge LiveKit agent audio streaming events to REACTOR controller turns, enabling seamless barge-in interruption and low-latency response generation."*
  - **Output Summary:** Scaffolded LiveKit Agent worker and event listeners for user speech start/stop.
  - **Human Modifications & Review:** Tuned VAD thresholds, added fallback safety-prompt overrides for simulated banking/passport tools to prevent external model refusals, and added token redaction for logging.

#### Feature 6: Kitchen Timer Mid-Turn Correction Extension (`src/reactor/tools/kitchen_timer.py`)
- **Origin:** **Both**
- **Description:**
  - **AI Tools / Platform Used:** Google Antigravity.
  - **Prompts Used:** *"Create a standalone kitchen timer tool that demonstrates cancelling a 10-minute timer and replacing it with a 7-minute timer mid-sentence."*
  - **Output Summary:** Created `KitchenTimerTool` with async duration tracking and cancel-by-id semantics.
  - **Human Modifications & Review:** Added duration boundary validation (rejecting negative or ambiguous timer inputs) and wrote unit tests verifying atomic replacement.

---

### 5. Ethical & Compliance Confirmation
- **AI usage complies with guidelines and policies:** **Yes**
- **No proprietary or copyrighted data misused:** **I Agree**
  - *Data Integrity Statement:* No proprietary, private, or benchmark-test split data was used for model training or fine-tuning. Upstream Full-Duplex-Bench v3 is an open academic benchmark (NTU) cited under its research license. No answer caching, hardcoding, or memorization exists in the codebase.

---

### 6. Declaration & Sign-Off
- **Name of Team Representative:** Atharva Mendhulkar
- **Role:** Team Representative / Lead Developer
- **Signature:** *Atharva Mendhulkar*
- **Date:** September 30, 2026
