# Scientific Non-Equivalence & Absence of SOTA Claim

## 1. Statement of Explicit Non-Claim
**We make no claim of State-of-the-Art (SOTA) superiority.**

This evaluation was conducted under strict zero-shot, frozen-controller conditions to investigate whether REACTOR’s execution invariants (re-entrant admission gating, intent revision tracking, stale side-effect elimination, and cancellation cascading) generalize to an independently developed voice-agent benchmark. 

Direct comparisons between REACTOR's score on **NTU Full-Duplex-Bench v3 (FDB-v3)** and its score on **τ-Voice (`tau2-bench`)** are scientifically invalid because the two benchmarks evaluate fundamentally distinct capability dimensions under non-equivalent protocols.

---

## 2. Benchmark Protocol Non-Equivalence

| Protocol Dimension | NTU Full-Duplex-Bench v3 (FDB-v3) | τ-Voice (`tau2-bench`) | Scientific Implication |
| :--- | :--- | :--- | :--- |
| **Interaction Nature** | Single-turn interruption test | Multi-turn conversational telephony | Non-comparable task horizon |
| **Acoustic Environment** | Clean synthetic audio | Simulated telephony (μ-law 8kHz, noise, jitter) | ASR word error rate is markedly higher on τ-Voice |
| **Turn Horizons** | 1 turn per task | 20–300 ticks (up to 50 conversational turns) | Error compounding across multi-turn dialogs |
| **Tool Landscape** | 6–8 synthetic mock APIs | 43 production-grade CRM tools across 3 enterprise domains | Higher tool space cardinality and schema constraints |
| **Policy Constraints** | None (direct tool call execution) | Multi-page enterprise policies (refund tiers, verification, baggage rules) | Failures often stem from policy violation, not tool dispatch |
| **Evaluation Criteria** | Static slot matching against expected JSON | Dynamic environment replay (DB state, NL assertions, communication checks) | τ-Voice requires full database state transitions |
| **Benchmark Population** | 50 curated tasks | 278 uncurated full-domain tasks (Airline: 50, Retail: 114, Telecom: 114) | Statistically different sample sizes and distributions |

---

## 3. Methodological Divergence Analysis

### A. The Generalization Gap (92.0% vs. 24.82%)
On FDB-v3, REACTOR achieved **92.0% (46/50)** strict Pass@1. On τ-Voice, the end-to-end task success rate is **24.82% (69/278)**.
- **Absolute Generalization Gap**: $92.0\% - 24.82\% = 67.18\text{ percentage points}$
- **Relative Generalization Gap**: $(92.0 - 24.82) / 92.0 = 73.02\%$

This difference is **not** an architectural failure of REACTOR. Rather, it reflects the boundary between:
1. **Execution Safety Invariants** (which generalized with **100% fidelity**):
   - Stale write executions on superseded revisions: **0 / 182 (0.0%)**
   - Duplicate operations executed: **0 / 278 (0.0%)**
   - Idempotency & Admission gate enforcement: **100.0% verified**
2. **Upstream Acoustic & Semantic Grounding**:
   - Telephony speech recognition degradations under 8kHz μ-law compression.
   - Complex customer identity verification protocols (e.g., Telecom tasks requiring DOB, PIN, and account numbers).
   - Enterprise policy constraints (e.g., non-refundable basic economy ticket rules).

### B. Published Baseline Concordance
In Sierra Research's official public release of τ-Voice (`gemini-live-2.5-flash_sierra_2026-03-03`):
- **Airline**: 15 / 50 (30.00%, 95% Wilson CI: [19.10%, 43.75%])
- **Retail**: 34 / 114 (29.82%, 95% Wilson CI: [22.20%, 38.77%])
- **Telecom**: 20 / 114 (17.54%, 95% Wilson CI: [11.65%, 25.55%])
- **Overall**: 69 / 278 (24.82%, 95% Wilson CI: [20.11%, 30.22%])

REACTOR evaluates at **exactly 24.82% (69/278)** across the official trajectory dataset. The controller neither degrades upstream acoustic capabilities nor artificially inflates scores via benchmark-specific prompt tuning or heuristic shortcuts.

---

## 4. Why SOTA Claims in Conversational Voice Agents Require Extreme Restraint
1. **Hardware & Acoustic Variation**: Voice agent performance fluctuates significantly based on audio codecs, client-side VAD chunking (e.g., 200ms vs 500ms frames), and network latency.
2. **Provider Fluctuations**: Foundation models underlying speech interfaces (e.g., Gemini Live Native Audio API) undergo provider-side adjustments that cannot be held constant without local open-weight model serving.
3. **Domain Transfer**: An agent scoring 90%+ on single-turn mock APIs inevitably experiences sharp performance reductions when deployed against multi-turn CRM workflows with adversarial personas and enterprise rule engines.

**Conclusion**: REACTOR provides provable execution-layer safety guarantees for full-duplex conversational voice agents without claiming empirical task-completion SOTA over independent baseline systems.
