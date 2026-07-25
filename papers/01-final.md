# From Sessions to Lifetimes: Infrastructure Gaps for Long-Running AI Agents

**Anonymous Submission**

---

## Abstract

Current LLM-based agent frameworks are designed for sessions lasting minutes to hours. As model capabilities approach general-purpose thresholds, the next frontier is **continuous autonomous operation** at the scale of days to months. Through systematic source-code analysis of two production frameworks (kimi-code: ~100K lines TypeScript; Grok Build: ~1.34M lines Rust), we identify **five failure modes** that emerge when current architectures operate beyond their design timescale: cumulative compaction degradation, resilience cost escalation, unbounded state log growth, identity drift, and slow-timescale behavioral loops. These failures are infrastructure-level, not model-level. We propose five capabilities required to bridge the gap: multi-scale memory hierarchies, offline consolidation cycles, self-evolving prompts, adaptive verification, and cost-aware resource management, accompanied by a phased engineering roadmap. While our analysis is grounded in coding-agent frameworks, the failure modes and proposed solutions are expected to generalize to other agent domains (research, web automation, embodied AI), as they stem from fundamental properties of LLM-based systems rather than domain-specific design choices.

---

## 1. Introduction

The gap between "an LLM that answers questions" and "an agent that works autonomously" is measured not in model parameters but in **session length**. An agent that completes a coding task in 30 minutes and an agent that runs for 30 days face fundamentally different challenges, even with the same underlying model.

Industry leaders have published extensively on agent design patterns, including prompt chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer workflows [1, 2, 3]. However, these patterns address **task-level** orchestration: how to decompose and execute a single user request. They do not address **lifecycle-level** resilience: how an agent maintains coherent operation across hundreds of tasks, thousands of turns, and continuous context compression over extended periods.

**The specific gap we address**: among the major open-source agent frameworks we analyzed, none provides mechanisms designed for continuous operation beyond the hour timescale. Current architectures assume session boundaries (explicit start, bounded duration, clean termination), and their resilience mechanisms (context compaction, goal verification, state persistence) are calibrated for this regime.

We contribute:

1. **Empirical analysis**: Systematic source-code teardown of two production agent frameworks, identifying the timescale limits of current resilience mechanisms (Section 3).
2. **Differentiation from prior research prototypes**: We distinguish our infrastructure-level proposals from research-system concepts such as Generative Agents [8] and Reflexion [9], which demonstrated multi-day operation in prototype settings but have not been integrated into production agent infrastructure (Section 2.4, Section 4).
3. **Infrastructure roadmap**: Five capabilities required for continuous operation, with concrete engineering proposals (Section 4) and a phased development roadmap (Section 5).

---

## 2. Background and Related Work

### 2.1 Agent Frameworks

We analyze two open-source agent frameworks representing different design philosophies:

- **kimi-code** (Moonshot AI): TypeScript, ~100K lines. Uses a custom dependency-injection architecture with event-sourced persistence (wire.jsonl). Twenty-five subsystems analyzed from source.
- **Grok Build** (SpaceXAI): Rust, ~1.34M lines, 70+ crates. Uses actor-based architecture with SQLite journaling. Ten subsystems analyzed from source.

Both are terminal-based coding agents with full tool integration (shell, file I/O, MCP support), goal management, subagent orchestration, and context compaction. They represent the current state of the art in open-source agent infrastructure. While our analysis is limited to these two frameworks, the architectural patterns we identify (event-sourced state, LLM-based compaction, per-goal verification) are shared across the broader agent ecosystem, including Claude Code, Cursor, and OpenAI Codex, based on their public documentation and observed behavior.

### 2.2 Context Management

Context compaction (summarizing older conversation history to free token budget) is the primary resilience mechanism in current agents. Approaches include single-pass summarization [4] and two-pass summarization [5], both relying on LLM self-summarization. The biological analogy of memory consolidation [13, 14] has been discussed in agent research but not implemented in production frameworks.

### 2.3 Verification and Safety

Goal-completion verification varies across frameworks. kimi-code trusts the model's self-report, augmented by a three-round blocked audit [6]. Grok Build uses an adversarial skeptic panel, in which multiple independent subagents vote via majority-refute to accept or reject completion claims [7]. Both approaches are designed for per-goal verification within a single session.

### 2.4 Long-Running Agent Research and Differentiation

Prior research has explored aspects of long-running agency:

**Generative Agents** [8] implemented memory streams, reflection, and daily planning for simulated agents running over multiple simulated days. Their memory architecture (observation, reflection, planning) shares conceptual overlap with our proposed multi-scale memory hierarchy (Section 4.1). However, Generative Agents operated in a simulated environment with no real tool execution, no cost constraints, and no adversarial verification. Our proposal extends the concept to production infrastructure with cost-aware tiered consolidation and non-compactable identity layers.

**Reflexion** [9] introduced verbal reinforcement learning, in which agents maintain textual self-reflections in episodic memory to improve subsequent trials. Our proposed self-evolving prompts (Section 4.3) extend Reflexion from episodic task-level learning to system-level prompt evolution: modifying the agent's behavioral instructions (not just task-specific reflections) based on accumulated experience, subject to an immutable safety constitution.

**Key distinction**: both Generative Agents and Reflexion are research prototypes demonstrating capability in controlled settings. Neither has been integrated into production agent infrastructure with real users, real costs, and real safety requirements. Our work analyzes what production frameworks currently lack and proposes concrete engineering mechanisms to bridge the gap from prototype to deployment.

---

## 3. Failure Modes at Extended Timescales

### 3.1 Scale Transformation

Table 1 shows the qualitative shift from session-scale to continuous operation.

| Dimension | Current (hours) | Continuous (days to months) |
|---|---|---|
| Turns | ~100 | ~10,000+ |
| Compaction events | 2 to 3 | ~200 to 500 |
| Goals completed | 1 to 5 | ~100 to 1,000 |
| Tokens consumed | ~100K | ~10⁸+ |
| State log size | ~MB | ~GB to TB |

### 3.2 Failure Mode 1: Cumulative Compaction Degradation

Current compaction replaces old messages with an LLM-generated summary. After *k* compaction events, the effective summary is a *k*-fold lossy compression:

$$S_k = f(f(\cdots f(H_0) \cdots))$$

where $f$ is the summarization function and $H_0$ is the original history. We **hypothesize** that, unlike fixed-rate compression where per-step error is bounded, LLM summarization exhibits **semantic drift**: each pass may preserve different aspects of the source, causing progressive loss of early context. Two-pass approaches [5] improve single-pass quality but cannot prevent cumulative drift across hundreds of iterations. This hypothesis is analytically motivated by the information-theoretic properties of lossy compression chains but has not yet been empirically validated at scale. Validating it (e.g., by measuring recall of early-session facts after 10, 50, and 200 compaction events) is an important direction for future work.

### 3.3 Failure Mode 2: Resilience Cost Escalation

Table 2 provides illustrative estimates of the monthly cost of resilience operations (excluding task execution) at continuous-operation scale. These estimates are based on assumed workloads derived from the analyzed frameworks' default configurations and 2025 to 2026 model pricing; they are intended to convey order-of-magnitude rather than precise predictions.

| Operation | Cost per invocation | Frequency | Monthly cost |
|---|---|---|---|
| Context compaction | $0.01 to $0.05 | ~20 per day | $6 to $300 |
| Goal verification | $0.05 to $0.20 | ~10 goals per day | $15 to $600 |
| Continuation prompt | $0.001 | every turn | ~$70 |
| Goal planning | $0.02 to $0.05 | ~5 per day | $3 to $75 |
| **Total** | | | **$94 to $1,045** |

At projected next-generation model pricing (estimated 5 to 10 times current rates), this reaches $500 to $10,000 per month for maintenance operations alone, excluding task execution. These costs threaten the economic viability of continuous agents and motivate cost-aware resource management (Section 4.5).

### 3.4 Failure Mode 3: Unbounded State Growth

Current frameworks use append-only logs (wire.jsonl) or SQLite journals without automatic log compaction. At continuous-operation scale, state stores grow to 300 MB to 1.5 GB monthly and 3.6 to 18 GB annually. Recovery from full replay becomes infeasible at gigabyte scale (requiring hours of processing). Checkpoint mechanisms exist in Grok Build [10] but lack automatic merging of old operations into snapshots.

### 3.5 Failure Mode 4: Identity Drift

After hundreds of compaction events, the agent's effective context diverges from its initial state. The system prompt remains unchanged, but the agent's interpretation of it drifts, because the same instruction ("write clean code") acquires different operational meanings depending on what experience survived compaction.

We define **identity persistence** operationally as a causally linked chain of key decisions and their rationales, maintained in a non-compactable store that survives all compaction events. Without such a mechanism, an agent that has undergone hundreds of context compressions cannot be verified to be "the same agent" that started the session, in the sense that its current behavior is causally traceable to its original configuration and early decisions. This is related to Parfit's concern about psychological continuity [11] but is specified here in engineering terms: the persistence substrate must contain (a) the original goal or mission statement, (b) all decisions where the agent chose between alternatives and the rationale recorded, and (c) all instances where a safety constraint was invoked or modified.

Current frameworks have no such mechanism.

### 3.6 Failure Mode 5: Slow-Timescale Behavioral Loops

Grok Build's doom-loop detector [12] operates on single inference streams (seconds). At continuous-operation scale, a more insidious failure emerges: slow-timescale loops in which the agent repeatedly attempts the same bug fix across compaction events (forgetting prior attempts), produces goals that consistently fail verification by narrow margins, or cycles between multiple incomplete tasks. These patterns are invisible to per-stream detectors and require cross-session behavioral analysis. This failure mode is predicted from architectural analysis rather than directly observed in deployed systems; validating it requires long-running deployment studies.

---

## 4. Required Capabilities

### 4.1 Multi-Scale Memory Hierarchy

Drawing on models of human memory [13], we propose a tiered architecture with distinct consolidation frequencies:

| Tier | Timescale | Capacity target | Consolidation method |
|---|---|---|---|
| Working | seconds | ~200K tokens | per-turn compaction |
| Episodic | minutes to hours | ~5K tokens | hourly structured extraction |
| Daily | hours to one day | ~2K tokens | daily summarization |
| Weekly | days to one week | ~1K tokens | weekly review |
| Identity | permanent | ~200 tokens | never compacted |

Each tier performs structured extraction (decisions, outcomes, lessons) rather than free-form summarization, producing stable schemas that resist cumulative drift (Section 3.2). This extends the Generative Agents [8] memory stream concept by introducing tiered consolidation frequencies, a non-compactable identity layer, and cost-aware design constraints specific to production deployment.

### 4.2 Offline Consolidation

Biological memory consolidation occurs during sleep via hippocampal replay [14]. We propose a periodic offline batch processing cycle for continuous agents, inspired by but not dependent on this biological analogy. The cycle comprises three phases: an active phase (approximately 16 hours of normal operation, accumulating episodic memory), a consolidation phase (approximately 4 hours of offline processing, including replay of recent experience, extraction of lessons, and discarding of redundancy), and a deep maintenance phase (approximately 4 hours of log compaction, knowledge graph updates, and prompt optimization). The biological sleep analogy provides design inspiration (periodic, offline, replay-based), but the engineering justification stands independently: batch processing is more cost-effective than interleaving consolidation with active task execution, and offline processing avoids interference between memory consolidation and real-time tool use.

### 4.3 Self-Evolving Prompts

Current system prompts are human-authored and static. For long-running agents, we propose a prompt evolution layer that adjusts behavioral instructions based on accumulated experience (e.g., detecting that a command pattern was rejected repeatedly and adding a preventive instruction). This extends Reflexion [9] from episodic, task-level self-reflection to system-level behavioral evolution: modifying the agent's standing instructions rather than its per-task memory. Proposed changes are subject to an immutable safety constitution (non-modifiable constraints, analogous to constitutional AI principles) and version-controlled for auditability.

### 4.4 Adaptive Verification

Current verification (e.g., the skeptic panel [7]) applies uniform rigor regardless of task complexity. At continuous-operation scale, this is economically infeasible. We propose risk-tiered verification: low-risk changes (e.g., typo fixes) receive automated diff checks, medium-risk changes receive single-skeptic verification, high-risk changes trigger a three-to-five skeptic panel, and critical changes require full verification plus human approval.

### 4.5 Cost-Aware Resource Management

Long-running agents need budget awareness: tracking per-operation costs, enforcing daily, weekly, and monthly budgets, and optimizing resilience costs through small-model delegation for verification, algorithmic (extractive) summarization for routine compaction, verification result caching by diff hash, and low-load scheduling for deep consolidation.

---

## 5. Roadmap

### Short-term (implementable on current frameworks)

1. Automatic log compaction: merge old operations into snapshots; cap log size.
2. Structured compaction: replace free-form handoff notes with schema-based extraction.
3. Daily and weekly budgets: extend per-turn budgets to multi-day horizons.
4. Verification caching: cache skeptic results by diff hash.

### Medium-term (new modules required)

5. Multi-scale memory: implement the five-tier hierarchy (Section 4.1).
6. Consolidation mode: agent enters offline state for periodic memory consolidation (Section 4.2).
7. Knowledge graph: extract entities, relations, and decisions from conversation history.
8. Adaptive verification: risk-tiered skeptic allocation (Section 4.4).

### Long-term (fundamental redesign)

9. Self-evolving prompts: experience-driven prompt modification with safety constraints (Section 4.3).
10. Identity persistence: non-compactable causal-chain store (Section 3.5).
11. Slow-timescale loop detection: cross-session behavioral pattern analysis.
12. Cost-optimal resilience: tenfold reduction in resilience costs via model and approach mix.

---

## 6. Scope and Generalizability

Our analysis is grounded in coding-agent frameworks, but the five failure modes are expected to generalize to other agent domains for the following reasons:

- **Compaction degradation** affects any LLM-based agent with finite context windows, regardless of domain.
- **Cost escalation** is domain-independent; it scales with the number of resilience operations, not with task type.
- **State growth** is a property of append-only logging, used across agent domains.
- **Identity drift** is a consequence of lossy context compression, which affects all agents using compaction.
- **Slow-timescale loops** are a behavioral failure mode of LLM-based systems, not specific to coding tasks.

Domains where additional failure modes may emerge (not covered here) include embodied AI (physical safety constraints), multi-agent systems (coordination breakdown at scale), and web agents (session management across heterogeneous services). We leave these to future work.

---

## 7. Threats to Validity

- **External validity**: Our source-code analysis covers two frameworks. While the architectural patterns identified are shared across the broader agent ecosystem (Section 2.1), confirming the five failure modes in Claude Code, Cursor, or Devin requires further study.
- **Cost estimates**: Token costs are based on 2025 to 2026 pricing and assumed workloads. They are illustrative, not measured. Future model efficiency improvements may reduce resilience costs significantly.
- **Speculative proposals**: The multi-scale memory hierarchy and offline consolidation cycle are inspired by cognitive science [13, 14] but lack empirical validation in agent systems.
- **Extrapolated failure modes**: The compaction degradation hypothesis (Section 3.2) and slow-timescale loop prediction (Section 3.6) are analytically motivated but not empirically observed in deployed systems. Validating them is a priority for future work.

---

## 8. Conclusion

The path to continuously operating AI agents is not blocked by model capability but by infrastructure gaps in context management, verification, state persistence, and cost control. Current agent frameworks, sophisticated as they are, remain session-scale artifacts. Extending them to continuous operation requires new mechanisms: multi-scale memory, offline consolidation, adaptive verification, and cost-aware resource management. We call on the research community to treat agent longevity as a first-class problem, not an afterthought to model capability.

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

[14] Diekelmann, S. & Born, J. *The memory function of sleep*. Nature Reviews Neuroscience 11, 114 to 126 (2010).

[15] Masi, M. et al. *Understanding large language models demands moving beyond metaphors*. Nature HSSC (2026). https://www.nature.com/articles/s44271-026-00508-6

[16] Oguntola, I. *Theory of Mind in Multi-Agent Systems*. CMU PhD Thesis CMU-ML-25-118 (2025). https://ml.cmu.edu/research/phd-dissertation-pdfs/ioguntol_phd_mld_2025.pdf

[17] Mei, K. et al. *AIOS: LLM Agent Operating System*. arXiv:2403.16971 (2024). https://arxiv.org/abs/2403.16971

[18] Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023. arXiv:2210.03629. https://arxiv.org/abs/2210.03629

[19] Wang, L. et al. *A Survey on Large Language Model based Autonomous Agents*. arXiv:2308.11432. https://arxiv.org/abs/2308.11432

[20] ETC Journal. *AI-Native Operating Systems: From Procedural to Intent-Based to Ambient* (2026). https://etcjournal.com/2026/03/13/ai-native-operating-systems-from-procedural-to-intent-based-to-ambient/
