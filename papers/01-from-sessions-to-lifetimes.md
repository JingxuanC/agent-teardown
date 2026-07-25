# From Sessions to Lifetimes: Infrastructure Gaps for Long-Running AI Agents

**Anonymous Submission**

---

## Abstract

Current LLM-based agent frameworks (Claude Code, kimi-code, Grok Build) are designed for sessions lasting minutes to hours. As model capabilities approach the AGI threshold, the next frontier is **continuous 7×24 operation** — agents that work autonomously for days to months. Through systematic source-code analysis of two production agent frameworks (kimi-code: ~100K lines TypeScript; Grok Build: ~1.34M lines Rust, 70+ crates), we identify **five systemic failure modes** that emerge when current architectures are scaled to long-running operation: cumulative compaction degradation, cost explosion from resilience operations, unbounded state log growth, identity drift, and slow-timescale behavioral loops. We argue that these failures are **infrastructure gaps**, not model capability gaps, and propose five capabilities required to bridge them: multi-scale memory hierarchies, offline consolidation ("sleep"), self-evolving prompts, adaptive verification, and cost-aware resource management. We contribute a concrete short/medium/long-term roadmap for agent framework developers.

---

## 1. Introduction

The gap between "an LLM that answers questions" and "an agent that works autonomously" is measured not in model parameters, but in **session length**. An agent that completes a coding task in 30 minutes and an agent that runs for 30 days face fundamentally different challenges — even with the same underlying model.

Industry leaders (Anthropic [1], OpenAI [2], Google [3]) have published extensively on agent design *patterns* (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer). However, these patterns address **task-level** orchestration, not **lifecycle-level** resilience. The question "what happens after 500 compactions?" is absent from current design taxonomies.

We address this gap through two contributions:

1. **Empirical analysis**: Systematic source-code teardown of two production agent frameworks, identifying the timescale limits of current resilience mechanisms (§3).
2. **Infrastructure roadmap**: Five capabilities required for 7×24 operation, with concrete engineering proposals (§4) and a phased roadmap (§5).

---

## 2. Background and Related Work

### 2.1 Agent Frameworks

We analyze two open-source agent frameworks representing different design philosophies:

- **kimi-code** (Moonshot AI): TypeScript, ~100K lines. Uses a custom DI × Scope architecture with event-sourced persistence (wire.jsonl). 25 subsystems analyzed.
- **Grok Build** (SpaceXAI): Rust, ~1.34M lines, 70+ crates. Uses actor-based architecture with SQLite journaling. 10 subsystems analyzed.

Both are **terminal-based coding agents** with full tool integration (shell, file I/O, MCP), goal management, subagent orchestration, and context compaction. They represent the current state-of-the-art in open-source agent infrastructure.

### 2.2 Context Management

Compaction (summarizing old context to free token budget) is the primary resilience mechanism in current agents. Approaches include single-pass summarization (kimi-code [4]) and two-pass summarization (Grok Build [5]), both relying on LLM self-summarization.

### 2.3 Verification and Safety

Goal-completion verification varies: kimi-code trusts the model's self-report with a 3-round blocked audit [6]; Grok Build uses an adversarial skeptic panel (N independent subagents vote via majority-refute [7]). Both are designed for per-goal verification within a single session.

### 2.4 Long-Running Agent Research

Generative Agents (Park et al. [8]) demonstrated multi-day agent simulation with memory streams and reflection. Reflexion (Shinn et al. [9]) introduced verbal reinforcement for episodic learning. However, these are research prototypes, not production infrastructure. **No published framework addresses continuous operation at the week-to-month timescale.**

---

## 3. Failure Modes at 7×24 Timescale

### 3.1 Scale Transformation

Table 1 shows the qualitative shift from session-scale to lifetime-scale operation.

| Dimension | Current (hours) | 7×24 (days–months) |
|---|---|---|
| Turns | ~100 | ~10,000+ |
| Compactions | 2–3 | ~200–500 |
| Goals completed | 1–5 | ~100–1,000 |
| Tokens consumed | ~100K | ~10⁸+ |
| State log size | ~MB | ~GB–TB |

### 3.2 Failure Mode 1: Cumulative Compaction Degradation

Current compaction replaces old messages with an LLM-generated summary ("handoff note"). After *k* compactions, the effective summary is a *k*-fold lossy compression:

$$\text{Note}_k = \text{LLM}(\text{LLM}(\cdots\text{LLM}(\text{history}_0)\cdots))$$

Unlike fixed-rate compression (where per-step error is bounded), LLM summarization exhibits **semantic drift** — each pass may preserve different aspects, causing progressive loss of early context. Two-pass approaches [5] improve single-pass quality but cannot prevent cumulative drift across hundreds of iterations.

**Evidence**: kimi-code's handoff instruction [4] explicitly asks the model to preserve "what you genuinely need to continue." But after 200 passes, the model has no access to the original context — only to increasingly abstract summaries of summaries.

### 3.3 Failure Mode 2: Resilience Cost Explosion

Table 2 estimates the monthly cost of resilience operations (not task execution) at 7×24 scale.

| Operation | Cost/invocation | Frequency | Monthly cost |
|---|---|---|---|
| Context compaction | $0.01–0.05 | ~20/day | $6–300 |
| Goal verification (skeptic panel) | $0.05–0.20 | ~10 goals/day | $15–600 |
| Continuation prompt injection | $0.001 | every turn | ~$70 |
| Goal planning/strategy | $0.02–0.05 | ~5/day | $3–75 |
| **Total** | | | **$94–1,045** |

At AGI-grade model pricing (estimated 5–10× current), this reaches **$500–10,000/month** — for *maintenance alone*, excluding task execution.

### 3.4 Failure Mode 3: Unbounded State Growth

Current frameworks use append-only logs (wire.jsonl) or SQLite journals. At 7×24 scale:

- Daily: ~10–50 MB
- Monthly: ~300 MB–1.5 GB
- Annually: ~3.6–18 GB

Recovery from full replay becomes infeasible at GB scale (hours of processing). Checkpoint mechanisms exist in grok-build [10] but lack automatic log compaction (merging old operations into snapshots and discarding intermediates).

### 3.5 Failure Mode 4: Identity Drift

After hundreds of compactions, the agent's effective context diverges completely from its initial state. The static system prompt remains unchanged, but the agent's *interpretation* of it drifts — the same instruction ("write clean code") means different things depending on what the agent has "experienced" (i.e., what survived compaction).

This is analogous to Parfit's [11] concern about psychological continuity: is an agent that retains only abstracted summaries of its earlier decisions still "the same agent"?

Current frameworks have no mechanism for **identity persistence** — a substrate that survives compaction and maintains causal continuity.

### 3.6 Failure Mode 5: Slow-Timescale Behavioral Loops

Grok Build's doom-loop detector [12] operates on **single SSE streams** (seconds). But at 7×24 scale, a more insidious failure emerges: **slow-timescale loops** where the agent:

- Repeatedly attempts the same bug fix across compactions (forgetting prior attempts)
- Produces goals that are always "almost complete" but never pass verification
- Cycles between 100 tasks, completing none

These patterns are invisible to per-stream detectors and require **cross-session behavioral analysis**.

---

## 4. Required Capabilities

### 4.1 Multi-Scale Memory Hierarchy

Drawing on cognitive science models of human memory (Atkinson & Shiffrin, 1968), we propose a **tiered memory architecture** with distinct consolidation frequencies:

| Tier | Timescale | Capacity | Consolidation |
|---|---|---|---|
| Working | seconds | ~200K tokens | per-turn compaction |
| Episodic | minutes–hours | ~5K tokens | hourly structured extraction |
| Daily | hours–day | ~2K tokens | daily summarization |
| Weekly | days–week | ~1K tokens | weekly review |
| Identity | permanent | ~200 tokens | never compacted |

Each tier performs **structured extraction** (decisions, outcomes, lessons) rather than free-form summarization, producing stable schemas that resist cumulative drift.

### 4.2 Offline Consolidation ("Sleep")

Biological memory consolidation occurs during sleep via hippocampal replay (Diekelmann & Born, 2010). We propose a **consolidation cycle** for 7×24 agents:

1. **Active phase** (16h): Normal operation, accumulating episodic memory
2. **Consolidation phase** (4h): Offline processing — replay recent experience, extract lessons, discard redundancy, update long-term store
3. **Deep maintenance** (4h): Log compaction, knowledge graph update, prompt optimization

This requires the agent to **pause task execution** periodically — a fundamental departure from "always-on" design.

### 4.3 Self-Evolving Prompts

Current system prompts are human-authored and static. For long-running agents, we propose a **prompt evolution layer** that adjusts behavioral instructions based on accumulated experience:

- Track action-outcome pairs (e.g., "rm -rf rejected 10× → add 'prefer trash' instruction")
- Propose prompt patches subject to an **immutable safety constitution** (non-modifiable constraints)
- Version-control prompt changes for auditability

This is related to Reflexion [9] but applied to *system-level* prompt evolution rather than episodic task learning.

### 4.4 Adaptive Verification

Current verification (e.g., Grok Build's skeptic panel [7]) applies uniform rigor regardless of task complexity. At 7×24 scale, this is economically infeasible.

We propose **risk-tiered verification**:

| Risk level | Method | Example |
|---|---|---|
| Low | Diff non-empty check | Typo fix |
| Medium | Single-skeptic | Function refactor |
| High | 3–5 skeptic panel | New feature |
| Critical | Full panel + human approval | Production deploy |

Risk classification can use heuristics (file type, blast radius) or a lightweight classifier model.

### 4.5 Cost-Aware Resource Management

Long-running agents need **budget awareness**: tracking per-operation costs, enforcing daily/weekly/monthly budgets, and optimizing resilience costs through:

- Small-model delegation for verification (not requiring full-capability LLMs)
- Algorithmic summarization for routine compaction (extractive rather than abstractive)
- Verification result caching (identical diffs need not be re-verified)
- Low-load scheduling for deep consolidation

---

## 5. Roadmap

### Short-term (implementable on current frameworks)

1. **Automatic log compaction**: Merge old operations into snapshots; cap log size at GB-scale.
2. **Structured compaction**: Replace free-form handoff notes with schema-based extraction (decisions/outcomes/lessons).
3. **Daily/weekly budgets**: Extend per-turn budgets to multi-day horizons.
4. **Verification caching**: Cache skeptic results by diff hash.

### Medium-term (new modules required)

5. **Multi-scale memory**: Implement the 5-tier hierarchy (§4.1).
6. **Consolidation mode**: Agent enters offline state for periodic memory consolidation (§4.2).
7. **Knowledge graph**: Extract entities/relations/decisions from conversation history into structured storage.
8. **Adaptive verification**: Risk-tiered skeptic allocation (§4.4).

### Long-term (fundamental redesign)

9. **Self-evolving prompts**: Experience-driven prompt modification with safety constraints (§4.3).
10. **Identity persistence**: Causal-chain continuity across compactions (§4.5).
11. **Slow-timescale loop detection**: Cross-session behavioral pattern analysis.
12. **Cost-optimal resilience**: 10× reduction in resilience costs via model/approach mix.

---

## 6. Threats to Validity

- **Sample size**: Our analysis covers two frameworks. Generalization to Claude Code, Cursor, or Devin requires further study.
- **Cost estimates**: Token costs are based on 2025–2026 pricing; future model efficiency improvements may reduce resilience costs.
- **Multi-scale memory proposal**: The tiered architecture is inspired by cognitive science but lacks empirical validation in agent systems.
- **7×24 timescale**: Some failure modes (e.g., slow doom loops) are extrapolated rather than directly observed.

---

## 7. Conclusion

The path to 7×24 AI agents is **not blocked by model capability** but by **infrastructure gaps** in context management, verification, state persistence, and cost control. Current agent frameworks — sophisticated as they are — remain session-scale artifacts. Extending them to lifetime-scale operation requires fundamentally new mechanisms: multi-scale memory, offline consolidation, adaptive verification, and cost-aware resource management.

We call on the research community to treat **agent longevity** as a first-class research problem, not an afterthought to model capability.

---

## References

[1] Anthropic. *Building Effective Agents*. https://www.anthropic.com/engineering/building-effective-agents (2024).

[2] OpenAI. *Agents SDK Documentation*. https://developers.openai.com/api/docs/guides/agents (2025).

[3] Google. *Choose a design pattern for your agentic AI system*. https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system (2026).

[4] kimi-code. *Context Memory and Compaction*. Source: `packages/agent-core-v2/src/agent/contextMemory/` and `fullCompaction/compaction-instruction.md`. https://github.com/MoonshotAI/kimi-code

[5] Grok Build. *Two-pass compaction*. Source: `crates/codegen/xai-grok-shell/src/session/two_pass.rs` and `compaction.rs`. https://github.com/xai-org/grok-build

[6] kimi-code. *Goal Mode state machine*. Source: `packages/agent-core-v2/src/agent/goal/goalService.ts`. https://github.com/MoonshotAI/kimi-code

[7] Grok Build. *Adversarial skeptic panel*. Source: `crates/codegen/xai-grok-shell/src/session/goal_classifier.rs`. https://github.com/xai-org/grok-build

[8] Park, J.S. et al. *Generative Agents: Interactive Simulacra of Human Behavior*. UIST 2023. arXiv:2304.03442. https://arxiv.org/abs/2304.03442

[9] Shinn, N. et al. *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023. arXiv:2303.11366. https://arxiv.org/abs/2303.11366

[10] Grok Build. *SQLite journal and checkpoint*. Source: `crates/codegen/xai-sqlite-journal/` and `xai-chat-state/src/persistence.rs`. https://github.com/xai-org/grok-build

[11] Parfit, D. *Reasons and Persons*. Oxford University Press (1984).

[12] Grok Build. *Doom loop detection*. Source: `crates/codegen/xai-grok-sampler/src/doom_loop.rs` and `xai-grok-sampling-types/src/doom_loop.rs`. https://github.com/xai-org/grok-build

[13] Atkinson, R.C. & Shiffrin, R.M. *Human Memory: A Proposed System and its Control Processes*. In *The Psychology of Learning and Motivation* (1968).

[14] Diekelmann, S. & Born, J. *The memory function of sleep*. Nature Reviews Neuroscience 11, 114–126 (2010).

[15] Masi, M. et al. *Understanding large language models demands moving beyond metaphors*. Nature HSSC (2026). https://www.nature.com/articles/s44271-026-00508-6

[16] Oguntola, I. *Theory of Mind in Multi-Agent Systems*. CMU PhD Thesis CMU-ML-25-118 (2025). https://ml.cmu.edu/research/phd-dissertation-pdfs/ioguntol_phd_mld_2025.pdf

[17] Mei, K. et al. *AIOS: LLM Agent Operating System*. arXiv:2403.16971 (2024). https://arxiv.org/abs/2403.16971

[18] Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023. arXiv:2210.03629. https://arxiv.org/abs/2210.03629

[19] Wang, L. et al. *A Survey on Large Language Model based Autonomous Agents*. arXiv:2308.11432. https://arxiv.org/abs/2308.11432

[20] ETC Journal. *AI-Native Operating Systems: From Procedural to Intent-Based to Ambient* (2026). https://etcjournal.com/2026/03/13/ai-native-operating-systems-from-procedural-to-intent-based-to-ambient/
