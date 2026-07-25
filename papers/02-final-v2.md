# From Sessions to Lifetimes: Infrastructure Gaps for Long-Running AI Agents

**Anonymous Submission**

---

## Abstract

Current LLM-based agent frameworks are designed for sessions lasting minutes to hours. As model capabilities approach general-purpose thresholds, the next frontier is **continuous autonomous operation** at the scale of days to months. Through systematic source-code analysis of seven open-source agent frameworks spanning four languages (kimi-code: ~100K lines TypeScript; Grok Build: ~1.34M lines Rust; OpenAI Codex CLI: ~80K lines Rust; Vela AI: ~50K lines Go; Pi: ~15K lines TypeScript; OpenAI Agents SDK and Google ADK: ~40K lines Python combined), we map the current state of long-running agent infrastructure across five capability dimensions: multi-scale memory, offline consolidation, identity persistence, adaptive verification, and cost-aware resource management. We find that while individual frameworks have begun implementing pieces of this infrastructure—most notably Vela AI's Mem0-style reflective memory with half-life decay, distributed autonomous goal scheduling, and per-agent identity isolation—**no single framework integrates all five capabilities**, and critical gaps remain in cross-session identity continuity, slow-timescale loop detection, and economically viable cost structures at continuous-operation scale. We characterize these gaps and propose a phased engineering roadmap, grounded in patterns already proven in individual frameworks rather than purely theoretical proposals.

---

## 1. Introduction

The gap between "an LLM that answers questions" and "an agent that works autonomously" is measured not in model parameters but in **session length**. An agent that completes a coding task in 30 minutes and an agent that runs for 30 days face fundamentally different challenges, even with the same underlying model.

Industry leaders have published extensively on agent design patterns, including prompt chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer workflows [1, 2, 3]. However, these patterns address **task-level** orchestration: how to decompose and execute a single user request. They do not address **lifecycle-level** resilience: how an agent maintains coherent operation across hundreds of tasks, thousands of turns, and continuous context compression over extended periods.

**The gap we address**: while recent frameworks have begun implementing lifecycle-oriented mechanisms—reflective memory consolidation, autonomous goal loops, per-agent identity—these remain isolated islands. No framework provides the integrated infrastructure stack required for verified continuous operation.

We contribute:

1. **Comparative source-code analysis** of seven production agent frameworks across five lifecycle-capability dimensions, identifying what exists, what is missing, and where partial implementations reveal integration challenges (Section 3).
2. **Evidence that core proposals are engineering-feasible**: Vela AI's production implementation of half-life memory decay, distributed goal scheduling, and per-agent identity isolation validates three of our five proposed capabilities in a real multi-tenant SaaS deployment (Section 4).
3. **Identification of structural gaps that no framework addresses**: cross-session identity continuity beyond compaction, slow-timescale behavioral loop detection, and the economic unsustainability of resilience costs at continuous scale (Section 4.6).
4. **A grounded roadmap**: Rather than purely theoretical proposals, we specify capabilities by referencing patterns already proven in specific frameworks, reducing implementation risk (Section 5).

---

## 2. Background and Related Work

### 2.1 Frameworks Analyzed

We analyze seven open-source agent frameworks representing diverse design philosophies and deployment targets:

| Framework | Language | Scale | Domain | Long-running features |
|---|---|---|---|---|
| **kimi-code** (Moonshot) | TypeScript | ~100K lines | Coding CLI | DI×Scope, wire event-sourcing, goal mode, subagent swarm |
| **Grok Build** (xAI) | Rust | ~1.34M lines | Coding CLI | Doom-loop detection, skeptic panel, worktree isolation, two-pass compaction |
| **Codex CLI** (OpenAI) | Rust | ~80K lines | Coding CLI | Dual-stage memory (Stage1+Stage2), ExecPolicy DSL, multi-agent |
| **Vela AI** | Go | ~50K lines | E-commerce SaaS | Mem0 Reflect+half-life, DAG-of-Agents, distributed AutoGoal, per-agent identity, MCP bidirectional, evals |
| **Pi** (earendil) | TypeScript | ~15K lines | General | Session Tree branching, 8+ provider support |
| **OpenAI Agents SDK** | Python | ~15K lines | SDK | Handoffs, guardrails, tracing |
| **Google ADK** | Python | ~25K lines | SDK | Sequential/parallel agents, built-in memory |

All seven were analyzed from source code. The first four received deep teardowns (9–10 documents each); the latter three received comparative analysis. Source-code-level findings are cited as `framework/file:line` throughout.

### 2.2 Context Management

Context compaction remains the primary resilience mechanism. Approaches observed: single-pass summarization (kimi-code [4]), two-pass summarization (Grok Build [5]), dual-stage memory with offline consolidation (Codex Stage1+Stage2), and Mem0-style additive fact extraction with half-life decay (Vela AI). The biological analogy of memory consolidation [13, 14] has influenced Vela's design (its Reflector explicitly follows the Mem0 additive pattern), demonstrating that cognitive-science-inspired architectures are entering production.

### 2.3 Verification and Safety

Goal-completion verification varies significantly: kimi-code trusts the model's self-report with a three-round blocked audit [6]; Grok Build uses an adversarial skeptic panel with majority-refute voting [7]; Codex applies an ExecPolicy DSL; Vela AI uses a four-rule AutonomyGate (hard-confirm for money/customer-visible actions, explicit per-tool declarations, prefix fallback, and confidence-based downgrade) combined with LLM-judge verification and stall detection. Vela additionally includes a six-dimension, eleven-scenario evaluation suite (`evals/`) with LLM-as-judge scoring and anti-markers to detect AI-slop patterns—a quality-assurance loop absent from all other frameworks analyzed.

### 2.4 Long-Running Agent Research

**Generative Agents** [8] demonstrated memory streams, reflection, and daily planning for simulated agents. **Reflexion** [9] introduced verbal reinforcement learning. Both are research prototypes. Vela AI's production implementation brings related concepts (reflective memory, self-evolving skills) into a real multi-tenant deployment with real costs and real safety requirements, providing the first production-scale evidence we are aware of that these concepts are engineering-feasible.

---

## 3. Lifecycle Capability Mapping

### 3.1 Scale Transformation

| Dimension | Session-scale (hours) | Continuous (days–months) |
|---|---|---|
| Turns | ~100 | ~10,000+ |
| Compaction/consolidation events | 2–3 | ~200–500 |
| Goals/autonomous cycles completed | 1–5 | ~100–1,000 |
| Tokens consumed | ~100K | ~10⁸+ |
| State log size | ~MB | ~GB–TB |

### 3.2 Capability Coverage Matrix

Table 1 maps the five lifecycle capabilities across the seven frameworks. "Partial" indicates the capability exists but with known limitations; "Absent" indicates no source-code-level evidence.

| Capability | kimi-code | Grok Build | Codex | **Vela AI** | Pi | Agents SDK | ADK |
|---|---|---|---|---|---|---|---|
| **Multi-scale memory** | Partial (session+cross-session) | Partial (wire Op) | Partial (Stage1+Stage2) | **Implemented** (3-tier scope + 4-band half-life) | Absent | Absent | Partial (built-in) |
| **Offline consolidation** | Absent | Absent | Partial (Stage2 offline) | **Implemented** (Reflector 5-step, advisory lock) | Absent | Absent | Absent |
| **Identity persistence** | Absent | Absent | Partial (agent identity) | **Partial** (persistent agentID, per-agent recall) | Absent | Absent | Absent |
| **Adaptive verification** | Partial (3-round audit) | Partial (skeptic panel) | Partial (ExecPolicy) | **Implemented** (AutonomyGate 4-rule + stall detection) | Absent | Partial (guardrails) | Absent |
| **Cost-aware management** | Absent | Absent | Absent | **Partial** (per-shop/per-agent billing) | Absent | Absent | Absent |

**Key finding**: Vela AI implements or partially implements all five capabilities—more than any other framework. However, even Vela lacks cross-session identity continuity beyond compaction, integrated slow-timescale loop detection, and economically optimized resilience cost structures. No framework achieves full coverage.

### 3.3 Detailed Analysis of Leading Implementations

#### 3.3.1 Vela AI: Mem0-Style Reflective Memory

Vela's `Reflector` (`service/agent/memory/reflect.go`) implements a five-step consolidation cycle protected by a PostgreSQL advisory lock to prevent concurrent reflection on the same shop:

1. **Select** unreflected agent decisions (batch of 100, oldest first)
2. **LLM extraction**: a single call extracts structured facts (with scope, half-life, entity tags, confidence), cross-decision insights (with category and source references), and one-line L0 summaries—following the Mem0 additive pattern where existing facts are shown to the LLM to prevent re-extraction
3. **Three-level deduplication**: content hash (exact) → Qdrant semantic similarity (threshold 0.95) → PostgreSQL ILIKE substring matching (fallback)
4. **UPSERT facts** with `ON CONFLICT (content_hash)` and half-life assignment (2160h/720h/168h/24h corresponding to 90d/30d/7d/1d business-semantic decay)
5. **Mark decisions reflected** and persist L0 summaries

Facts carry a three-level scope (`agent` for cross-shop behavioral patterns, `shop` for store-specific observations, `session` for temporary context) and are recalled via Reciprocal Rank Fusion (RRF) of Qdrant semantic search and PostgreSQL recency-ordered results.

**Limitation**: while this is the most sophisticated memory system we observed in production, it operates per-shop and per-agent-goal. Cross-agent knowledge transfer (e.g., a pattern learned by the SEO agent informing the inventory agent) occurs only through the shared blackboard within a single DAG-of-Agents run, not persistently across sessions.

#### 3.3.2 Vela AI: Distributed Autonomous Goal Scheduling

Vela's `Scheduler` (`service/autogoal/scheduler.go`) drives persistent goals on a cadence with three production-grade distributed-systems mechanisms:

- **PostgreSQL advisory locks** (`TryLockGoal`) prevent two horizontally-scaled replicas from advancing the same goal simultaneously
- **Cross-replica cancel broadcasting**: a `Cancel` on one replica publishes to all replicas via pub/sub; the replica actually running the goal receives the signal and interrupts via `context.Cancel`
- **Concurrency-bounded tick**: at most `maxConcurrency` goals advance per tick (default 5), bounded by a semaphore

Each `GoalEngine.Advance` cycle: reads steering messages from the goal's per-goal conversation thread → executes (single-agent React or multi-agent Coordinator DAG) → verifies (metric comparison or LLM judge) → reflects → appends a cycle summary to the conversation → persists state.

**Limitation**: goal state and conversation are JSONB columns on a single `Goal` row. At thousands of cycles over months, the conversation thread grows unbounded—Vela's own ADR 0004 acknowledges this as a known issue to be addressed in future phases.

#### 3.3.3 Vela AI: Per-Agent Identity Isolation

Vela assigns each persona (e.g., "SEO specialist," "inventory manager") a **persistent agent UUID** via `AgentRegistry.ResolveAgentID`. This identity propagates through a zero-dependency `agentctx` package to the deepest call sites (LLM providers, MCP billing decorators), enabling:

- Per-agent memory recall (`RecallByAgentGoal` filters Qdrant + PG by `agent_id` and `goal_id`)
- Per-agent service resolution (`ServiceRegistry` three-level: agent-specific → shop-specific → global)
- Per-agent billing (`BillingMCPService` decorator attributes MCP tool costs to `agentctx.AgentIDFrom(ctx)`)
- Tool whitelisting via context (`WithToolWhitelist` → Oracle `filterToolsByWhitelist`)

**Limitation**: identity is persona-based, not truly persistent across framework restarts or persona reassignment. There is no mechanism for an agent to reflect on "who I am" beyond its current persona assignment.

---

## 4. Failure Modes and Remaining Gaps

Despite Vela's advances, structural gaps remain that no framework addresses.

### 4.1 Cumulative Compaction Degradation

Even Vela's structured fact extraction does not solve the fundamental problem of lossy compression chains. After *k* consolidation cycles, early context is progressively lost. Vela mitigates this with half-life decay (old facts naturally fade) and entity-tag-based retrieval, but cannot guarantee that a fact critical at cycle 1 remains accessible at cycle 200 if it has not been recently reinforced.

We **hypothesize** that LLM summarization exhibits semantic drift: each consolidation pass may preserve different aspects, causing progressive loss. Validating this (measuring recall of early-cycle facts after 10, 50, and 200 consolidations) is a priority for future work.

### 4.2 Unbounded State Growth

Vela persists goal state as JSONB on a single row; kimi-code uses append-only wire logs; Grok Build uses SQLite journals. At continuous scale, all approaches face growth-to-GB challenges. Vela's `DAGRunStore` with per-node state persistence and recovery is the most sophisticated approach observed, but even it lacks automatic snapshot merging across long time horizons.

### 4.3 Identity Drift Beyond Compaction

Vela's persistent agentID is a persona-to-UUID mapping, not a causal chain of decisions. True identity persistence (Section 3.5 of the original problem statement) requires maintaining a non-compactable store of: (a) the original mission/goal statement, (b) all key decisions and their rationale, and (c) all safety constraint invocations. No framework implements this.

### 4.4 Slow-Timescale Behavioral Loops

Grok Build's doom-loop detector operates on single inference streams (seconds). Vela's stall detection (score plateau + no new suggestions → `stalled`) is more sophisticated but still within a single goal cycle. The predicted failure—loops spanning compaction events, where the agent repeatedly attempts the same approach after forgetting prior failures—requires cross-session behavioral analysis that no framework provides.

### 4.5 Resilience Cost Escalation

Table 2 provides illustrative monthly costs of resilience operations at continuous scale:

| Operation | Cost/invocation | Frequency | Monthly cost |
|---|---|---|---|
| Memory consolidation (Vela Reflect) | $0.02–$0.10 | ~20/day | $12–$60 |
| Goal verification (LLM judge) | $0.05–$0.20 | ~10/day | $15–$60 |
| Context compaction | $0.01–$0.05 | ~20/day | $6–$30 |
| Continuation prompts | $0.001 | every turn | ~$70 |
| Eval quality checks | $0.02–$0.05 | ~5/day | $3–$8 |
| **Total** | | | **$106–$228** |

Vela's per-agent billing (`agentctx` propagation) is the only framework that makes these costs attributable, but even it does not enforce budget caps or optimize via small-model delegation.

### 4.6 The Integration Gap

The most significant finding is not that individual capabilities are missing, but that **no framework integrates them into a coherent lifecycle stack**. Vela comes closest—it has memory, goals, identity, verification, and cost tracking as separate subsystems—but these are not designed as an integrated lifecycle management layer. The gaps between subsystems (memory does not feed back into prompt evolution; identity does not influence verification strictness; cost tracking does not trigger behavioral mode changes) represent the true frontier.

---

## 5. Roadmap

Our roadmap is grounded in patterns already proven in specific frameworks, reducing implementation risk.

### Short-term (patterns exist, need integration)

1. **Structured compaction** (Vela's Mem0-pattern facts + half-life): replace free-form summaries with schema-based extraction. *Reference: Vela `reflect.go`*
2. **Automatic log compaction** (Vela's DAGRunStore recovery): merge old operations into snapshots. *Reference: Vela `dag_store.go`*
3. **Risk-tiered verification** (Vela's AutonomyGate 4-rule): adaptive rigor based on tool classification. *Reference: Vela `autonomy.go`*
4. **Per-agent cost attribution** (Vela's `agentctx`): propagate agent identity for billing. *Reference: Vela `agentctx/agentctx.go`*

### Medium-term (new integration required)

5. **Multi-scale memory integration**: combine Vela's fact extraction with Codex's Stage1/Stage2 and kimi-code's session/cross-session layers into a unified hierarchy.
6. **Consolidation as a first-class mode**: agent enters offline state periodically (Vela's Reflect is a prototype; generalizing it to a full consolidation mode is needed).
7. **Cross-session loop detection**: combine Grok Build's doom-loop detection with Vela's stall detection, extended across compaction boundaries.
8. **Evaluation-driven prompt evolution**: Vela's evals suite (6 dimensions × 11 scenarios) should feed back into PromptContextProvider adjustments.

### Long-term (fundamental new mechanisms)

9. **Causal-chain identity store**: a non-compactable record of mission, key decisions, and safety invocations.
10. **Cost-optimal resilience**: small-model delegation for routine consolidation, algorithmic summarization, and verification caching.
11. **Integrated lifecycle manager**: a subsystem that coordinates memory, identity, verification, and cost across all timescales—Vela's subsystems as points in a coherent design space, not isolated modules.

---

## 6. Generalizability

Our analysis spans coding agents (kimi-code, Grok Build, Codex), an e-commerce SaaS agent (Vela), a general-purpose agent (Pi), and SDK frameworks (Agents SDK, ADK). The five capability dimensions are observed across all domains, though their implementation details vary. The integration gap (Section 4.6) is expected to be universal: any agent operating at continuous scale will need coordinated memory, identity, verification, and cost management, regardless of domain.

---

## 7. Threats to Validity

- **Analysis depth**: Seven frameworks were analyzed, but at varying depths (9–10 teardown documents for kimi-code, Grok Build, Codex, and Vela; comparative analysis for Pi, Agents SDK, ADK). Deeper analysis of the latter three may reveal additional patterns.
- **Single-framework evidence for advanced capabilities**: Vela AI is the primary evidence for feasibility of reflective memory, distributed scheduling, and per-agent identity. Confirming these patterns in other production frameworks would strengthen the claims.
- **Cost estimates**: Illustrative, based on 2025–2026 pricing and assumed workloads, not measured from deployment.
- **Speculative failure modes**: Compaction degradation and slow-timescale loops are analytically motivated but not empirically observed in deployed systems at the timescales discussed.

---

## 8. Conclusion

The path to continuously operating AI agents is not blocked by model capability but by infrastructure integration gaps. Our analysis of seven frameworks reveals that individual pieces of the lifecycle stack—multi-scale memory, offline consolidation, adaptive verification, per-agent identity—already exist in production, most advanced in Vela AI's e-commerce agent platform. However, no framework integrates these into a coherent lifecycle management layer, and critical gaps remain in cross-session identity continuity, slow-timescale loop detection, and economic cost structures. The next step is not inventing new mechanisms from scratch, but integrating proven patterns into a unified lifecycle infrastructure. We call on the research community to treat agent longevity as a first-class integration problem.

---

## References

[1] Anthropic. *Building Effective Agents*. https://www.anthropic.com/engineering/building-effective-agents (2024).

[2] OpenAI. *Agents SDK Documentation*. https://developers.openai.com/api/docs/guides/agents (2025).

[3] Google. *Choose a design pattern for your agentic AI system*. https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system (2026).

[4] kimi-code. *Context Memory and Compaction*. Source: `packages/agent-core-v2/src/agent/contextMemory/`. https://github.com/MoonshotAI/kimi-code

[5] Grok Build. *Two-pass compaction*. Source: `crates/codegen/xai-grok-shell/src/session/two_pass.rs`. https://github.com/xai-org/grok-build

[6] kimi-code. *Goal Mode state machine*. Source: `packages/agent-core-v2/src/agent/goal/goalService.ts`.

[7] Grok Build. *Adversarial skeptic panel*. Source: `crates/codegen/xai-grok-shell/src/session/goal_classifier.rs`.

[8] Park, J.S. et al. *Generative Agents: Interactive Simulacra of Human Behavior*. UIST 2023. arXiv:2304.03442.

[9] Shinn, N. et al. *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023. arXiv:2303.11366.

[10] Grok Build. *SQLite journal and checkpoint*. Source: `crates/codegen/xai-sqlite-journal/`.

[11] Parfit, D. *Reasons and Persons*. Oxford University Press (1984).

[12] Grok Build. *Doom loop detection*. Source: `crates/codegen/xai-grok-sampler/src/doom_loop.rs`.

[13] Atkinson, R.C. & Shiffrin, R.M. *Human Memory: A Proposed System and its Control Processes*. In *The Psychology of Learning and Motivation* (1968).

[14] Diekelmann, S. & Born, J. *The memory function of sleep*. Nature Reviews Neuroscience 11, 114–126 (2010).

[15] Masi, M. et al. *Understanding large language models demands moving beyond metaphors*. Nature HSSC (2026).

[16] Oguntola, I. *Theory of Mind in Multi-Agent Systems*. CMU PhD Thesis CMU-ML-25-118 (2025).

[17] Mei, K. et al. *AIOS: LLM Agent Operating System*. arXiv:2403.16971 (2024).

[18] Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023. arXiv:2210.03629.

[19] Wang, L. et al. *A Survey on Large Language Model based Autonomous Agents*. arXiv:2308.11432.

[20] Vela AI. *Memory system (Reflect + half-life)*. Source: `api-server-go/internal/service/agent/memory/reflect.go`.

[21] Vela AI. *Distributed autonomous goal scheduler*. Source: `api-server-go/internal/service/autogoal/scheduler.go`.

[22] Vela AI. *Per-agent identity (agentctx)*. Source: `api-server-go/internal/service/agent/agentctx/agentctx.go`.

[23] Vela AI. *AutonomyGate (4-rule verification)*. Source: `api-server-go/internal/service/orchestrator/autonomy.go`.

[24] Vela AI. *Evaluation suite*. Source: `api-server-go/evals/scheme.go` and `judge.go`.

[25] OpenAI Codex CLI. *Dual-stage memory*. Source: `codex-rs/core/src/` (Stage1+Stage2 architecture).

[26] Google ADK. *Agent Development Kit Documentation*. https://google.github.io/adk-docs/ (2025).
