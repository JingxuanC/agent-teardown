# Simulated Peer Review — "From Sessions to Lifetimes"

> Generated using `nature-reviewer` skill v6.1.0 (Yuan1z0825/nature-skills), following the 5-axis evaluation protocol with 12-axis technical concern taxonomy.
>
> **Input**: `papers/01-polished.md` (the polished position paper)
> **Venue assumption**: NeurIPS Workshop on LLM Agents (position paper track)

---

## Review setup

- **Input scope**: Full manuscript (Abstract through References), ~2,400 words, 20 references.
- **Assessment boundary**: This is a position paper, not an experimental paper. It presents empirical observations from source-code analysis and proposes a research agenda. There are no controlled experiments, ablations, or quantitative benchmarks in the traditional sense. The review evaluates the strength of the argument, the sufficiency of the evidence for claims made, and the significance of the proposed research direction.
- **Shared manuscript claim summary**: Current agent frameworks are designed for session-scale (hours) operation. Scaling to continuous operation (days to months) exposes five systemic failure modes (compaction degradation, cost escalation, state growth, identity drift, slow loops). These are infrastructure gaps, not model capability gaps. Five new capabilities are required, with a phased roadmap.
- **Visible evidence base**: Source-code analysis of two frameworks (kimi-code ~100K LOC TS; Grok Build ~1.34M LOC Rust). Specific subsystem citations (wire.jsonl, goal_classifier.rs, two_pass.rs, doom_loop.rs). Cost estimates in Table 2. Scale estimates in Table 1.
- **Missing materials affecting confidence**: No analysis of Claude Code, Cursor, Devin, or other frameworks (external validity limited). No empirical measurement of compaction degradation (the k-fold lossy compression claim is analytical, not measured). No prototype implementation of proposed capabilities. Slow-timescale behavioral loops are predicted, not observed.

---

## Reviewer 1

**Emphasis: Technical soundness / Technical failings**

### Overall assessment

The paper identifies a real and timely gap in agent framework research: the mismatch between session-scale design assumptions and the goal of continuous operation. The five failure modes are plausible and well-articulated. However, the empirical evidence base is thinner than the claims require. The paper is stronger as a research agenda than as an empirical contribution.

### Who would be interested in the results, and why

Agent framework developers (engineering teams at Anthropic, OpenAI, Google, Moonshot, SpaceXAI) and systems researchers interested in long-running autonomous systems. The framing is timely given the 2025-2026 convergence toward AGI narratives.

### Major strengths

- The failure mode taxonomy (Section 3) is specific and actionable. Each mode is grounded in concrete architectural features (e.g., compaction as k-fold lossy compression, skeptic panel cost scaling).
- The roadmap (Section 5) is well-structured with clear short/medium/long-term separation.
- The Threats to Validity section is honest about sample size and speculative proposals.

### Major concerns

#### R1-M1: Sample size limits generalizability

- **Axis**: experimental-design, reproducibility
- **Claim pointer**: "Through systematic source-code analysis of two production frameworks..."
- **Evidence pointer**: Section 2.1
- **Evidence status**: located
- **Concern**: Two frameworks (one TypeScript, one Rust) constitute a limited sample. The claim that "all frameworks converge to the same five failure modes" is not supported with this sample. Claude Code, Cursor, Devin, Aider, or OpenAI Codex may have different architectures that avoid some failure modes or introduce new ones.
- **Resolution test**: Analyze at least one additional framework (ideally Claude Code, as it is the most widely used agent framework) to test whether the five failure modes generalize. Alternatively, reframe as "failure modes observed in two frameworks" rather than "systemic failure modes."

#### R1-M2: Compaction degradation claim lacks empirical measurement

- **Axis**: mechanism-evidence, statistical-rigor
- **Claim pointer**: "After k compaction events, the effective summary is a k-fold lossy compression" exhibiting "semantic drift."
- **Evidence pointer**: Section 3.2, Equation (1)
- **Evidence status**: located
- **Concern**: The mathematical framing (S_k = f(f(...f(H_0)...))) is elegant but unvalidated. No experiment measures how much information is actually lost after 10, 50, or 200 compactions. The claim may be true, but the paper presents it as established rather than hypothesized.
- **Resolution test**: Run a controlled experiment: take a real agent session, compact it 1, 5, 10, 50 times, and measure information retention (e.g., ability to answer questions about early context). Even a small-scale experiment would strengthen this claim significantly.

#### R1-M3: Cost estimates lack sensitivity analysis

- **Axis**: statistical-rigor
- **Claim pointer**: Table 2 monthly cost estimates ($94 to $1,045).
- **Evidence pointer**: Section 3.3, Table 2
- **Evidence status**: located
- **Concern**: The cost ranges are extremely wide (10× spread). The assumptions about frequency (20 compactions/day, 10 goals/day) are not justified. Are these based on observed usage patterns, or assumed? Without grounding, the estimates are speculative.
- **Resolution test**: Justify the frequency assumptions with reference to observed agent behavior, or explicitly label them as "illustrative estimates based on assumed workloads."

### Assessment against criteria

| Criterion | Assessment |
|---|---|
| Originality | Moderate. The gap is real but partially acknowledged in existing work [8, 9]. |
| Technical soundness | Weak to moderate. Claims outrun evidence (R1-M1, R1-M2, R1-M3). |
| Scientific importance | Moderate to high. Timely and actionable. |
| Readability | Strong. Well-organized, clear tables, honest limitations. |

### Recommendation posture

**Reject (major revision) for a full-track venue. Accept (with revisions) for a workshop/position paper track.** The core argument is sound and timely, but the empirical evidence needs strengthening. At minimum, the compaction degradation claim (R1-M2) should be downgraded from "established" to "hypothesized" or supported with a pilot experiment.

---

## Reviewer 2

**Emphasis: Originality + Scientific importance**

### Overall assessment

The paper makes a compelling case that agent longevity is an under-explored research frontier. The five required capabilities (Section 4) are well-motivated and the roadmap is practical. The contribution is primarily a research agenda, which is appropriate for a position paper.

### Who would be interested

Broadly: AI safety researchers (identity drift relates to alignment stability), systems researchers (state management, cost optimization), and product teams building agent infrastructure. The framing as "infrastructure gaps, not model gaps" is a useful reframing.

### Major strengths

- The "infrastructure vs. model capability" framing is valuable and under-stated in current discourse. Most AGI discussions focus on model intelligence; this paper correctly identifies that runtime infrastructure is the binding constraint.
- The multi-scale memory hierarchy proposal (Section 4.1) is the strongest contribution. It is concrete, grounded in cognitive science [13], and directly actionable.
- The offline consolidation proposal (Section 4.2) is novel and thought-provoking. The analogy to sleep is compelling without being over-extended.

### Major concerns

#### R2-M1: Insufficient differentiation from Generative Agents and Reflexion

- **Axis**: novelty-significance
- **Claim pointer**: "No published framework provides mechanisms for continuous operation at the week-to-month timescale."
- **Evidence pointer**: Section 2.4
- **Evidence status**: located
- **Concern**: Generative Agents [8] implemented memory streams, reflection, and daily planning for agents that ran for simulated days. Reflexion [9] implemented episodic self-improvement. The paper acknowledges these but does not clearly differentiate its proposals from them. How is the multi-scale memory hierarchy (Section 4.1) different from the Generative Agents memory stream? How is offline consolidation (Section 4.2) different from Reflexion's verbal reinforcement?
- **Resolution test**: Add a comparison table or paragraph explicitly contrasting each proposed capability with the closest prior work, highlighting what is new beyond a production-scale implementation of known research concepts.

#### R2-M2: "Identity persistence" is underdeveloped

- **Axis**: novelty-significance, claim-moderation
- **Claim pointer**: Section 3.5 (Identity Drift) and Section 4.3 (Self-Evolving Prompts)
- **Evidence pointer**: Section 3.5, Section 5 (long-term item 10)
- **Evidence status**: located
- **Concern**: The concept of "identity persistence" is introduced but not operationalized. What exactly needs to persist? The paper references Parfit [11] but does not translate the philosophical concept into an engineering specification. This makes it hard to evaluate the proposed solution.
- **Resolution test**: Define identity persistence operationally (e.g., "a causally linked chain of key decisions and their rationales, maintained in a non-compactable store") and specify what would count as success or failure.

### Assessment against criteria

| Criterion | Assessment |
|---|---|
| Originality | Moderate. The reframing is valuable, but several proposed capabilities overlap with prior research prototypes. |
| Scientific importance | High. The problem is real, timely, and under-addressed. |
| Technical soundness | Moderate. Adequate for a position paper. |
| Interdisciplinary interest | High. Relevant to AI safety, systems, and cognitive science. |

### Recommendation posture

**Accept for a workshop/position paper track.** The reframing and roadmap are the contribution, not empirical validation. However, the differentiation from prior work (R2-M1) must be strengthened before camera-ready.

---

## Reviewer 3

**Emphasis: Interdisciplinary readership + Readability**

### Overall assessment

The paper is clearly written and accessible to a broad audience. The use of tables and structured sections makes it easy to navigate. The position is well-argued. For a workshop audience, this paper will generate productive discussion.

### Who would be interested

Beyond the immediate agent research community: HCI researchers (agent-human interaction over long timescales), DevOps engineers (agent-as-infrastructure reliability), and AI governance researchers (identity drift has safety implications).

### Major strengths

- The paper is unusually well-organized for a position paper. Each failure mode and capability is self-contained and cross-referenced.
- The cost analysis (Table 2) is a strong communication device. It makes the problem concrete in a way that abstract arguments cannot.
- The Threats to Validity section demonstrates intellectual honesty that builds trust.

### Major concerns

#### R3-M1: Narrow framing excludes non-coding agents

- **Axis**: interdisciplinary readership
- **Claim pointer**: The paper analyzes "terminal-based coding agents."
- **Evidence pointer**: Section 2.1
- **Evidence status**: located
- **Concern**: The failure modes and capabilities may apply more broadly (to research agents, web agents, robotic agents), but the paper does not discuss generalization beyond coding agents. This limits the perceived relevance for readers outside the coding-tools community.
- **Resolution test**: Add a short paragraph in the Discussion or Conclusion acknowledging that the analysis is grounded in coding agents but the failure modes likely generalize. Briefly note which modes are coding-agent-specific and which are domain-independent.

#### R3-M2: The "sleep" metaphor may alienate some readers

- **Axis**: readability
- **Claim pointer**: Section 4.2 (Offline Consolidation), drawing on biological sleep.
- **Evidence pointer**: Section 4.2
- **Evidence status**: located
- **Concern**: The analogy to sleep [14] is evocative but risks being perceived as anthropomorphizing. Some reviewers (especially in the ML community) are sensitive to biological analogies for computational processes. The argument stands without the analogy: "periodic offline batch processing for memory consolidation" is sufficient.
- **Resolution test**: Consider framing the proposal primarily as "periodic offline batch processing" with the sleep analogy as a secondary supporting reference, rather than leading with the biological framing.

### Assessment against criteria

| Criterion | Assessment |
|---|---|
| Originality | Moderate. |
| Scientific importance | Moderate to high. |
| Interdisciplinary interest | High, but partially self-limited by coding-agent framing. |
| Readability | Strong. Accessible and well-structured. |

### Recommendation posture

**Accept for a workshop track.** The paper is readable, timely, and will generate discussion. The two concerns are addressable with minor revisions.

---

## Cross-review synthesis

### Consensus strengths

- **Timely reframing** (all three reviewers): The "infrastructure, not model capability" framing is the paper's strongest contribution. This reframing is novel in the current AGI discourse.
- **Clear structure** (all three): The five failure modes map cleanly to five capabilities, and the roadmap is actionable.
- **Intellectual honesty** (R1, R2): The Threats to Validity section is above-average for a position paper.

### Consensus technical risks

- **R1-M1 / R2-M1 (sample size + differentiation)**: Both Reviewer 1 and Reviewer 2 independently flag that the empirical base (two frameworks) and the differentiation from prior work ([8], [9]) are insufficient. This is the most important issue to resolve before camera-ready.
- **R1-M2 (compaction degradation unmeasured)**: Reviewer 1 flags this as a technical failing. Reviewer 2 does not raise it but would likely agree if pressed.

### Where emphasis differs across reviewers

| Issue | R1 | R2 | R3 |
|---|---|---|---|
| Empirical evidence strength | **Major concern** | Acceptable for position paper | Not raised |
| Differentiation from prior work | Not raised | **Major concern** | Not raised |
| Domain scope (coding agents only) | Not raised | Not raised | **Moderate concern** |
| Biological metaphor sensitivity | Not raised | Not raised | **Minor concern** |

### Broad-interest / significance readout

All three reviewers agree the problem is significant and timely. The paper targets a real gap that the community needs to address. The disagreement is about evidence strength, not importance.

### Most important issues to resolve before a strong case is established

1. **Strengthen empirical base** (R1-M1): Analyze at least one more framework, or explicitly scope claims as "observed in two frameworks."
2. **Differentiate from prior work** (R2-M1): Add a comparison with Generative Agents [8] and Reflexion [9] for each proposed capability.
3. **Downgrade or measure compaction degradation** (R1-M2): Either run a pilot experiment or reframe as "hypothesized" rather than "established."
4. **Operationalize identity persistence** (R2-M2): Define what persists, in engineering terms.
5. **Broaden scope statement** (R3-M1): Note that failure modes likely generalize beyond coding agents.

### Risk / unsupported claims

- The claim that "no published framework provides mechanisms for continuous operation" is strong. It is not falsifiable without an exhaustive survey. Consider softening to "no major open-source framework we analyzed..."
- The cost estimates (Table 2) are illustrative, not measured. They should be labeled as such.
- The timeline prediction (Section 5 of the original insight, removed from the paper) was wisely cut. Good editorial judgment.

---

## Summary verdict

| Venue | Decision |
|---|---|
| NeurIPS/ICML Workshop (position paper) | **Accept with minor revisions** |
| COLM / SoLaR | **Borderline; needs stronger differentiation from prior work** |
| Full conference (ICSE, FSE) | **Reject; needs empirical validation (more frameworks + experiments)** |
| Nature / Science | **Not applicable (wrong venue type)** |

**Overall**: The paper is a solid position paper that identifies a real gap and proposes a practical research agenda. Its main weakness is empirical thinness (two frameworks, no experiments). Its main strength is the timely reframing and the actionable roadmap. For a workshop venue, it is above the acceptance bar after addressing the five revision items above.
