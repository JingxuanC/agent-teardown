# Research Note · causal-memory 是外显世界模型吗？

> 本篇回答一个问题：causal-memory 的因果图在多大程度上是一个世界模型？差距在哪？从"记忆系统"到"世界模型"需要补什么？
>
> 源点：Kimi 在 code review 中指出"causal-memory 的因果图本质是外显世界模型"——caused 边就是转移函数样本 f(state, action) → outcome。本文用世界模型的正式定义验证这个判断，诚实标注差距。

## 1. 世界模型是什么——正式定义

### 1.1 Physical Intelligence 的定义（arXiv:2607.06401, 2026-07）

> **世界模型是有限计算资源约束下对物理世界状态转移过程的压缩建模。**

形式化是 POMDP：M = (S, A, O, P\*, O, R, γ)，核心是**转移核**：

```
P*(s' | s, a) = 在状态 s 下执行动作 a 后，转移到状态 s' 的概率
```

世界模型的三层能力（论文 §2.3）：
- **理解**（what is happening, why）——归因，回答"为什么"
- **预测**（what will happen）——前向模拟，回答"如果我做 X 会怎样"
- **干预**（what if I do X instead of Y）——反事实推理

### 1.2 Graph World Model 的定义（arXiv:2604.27895, CUHK + 清华, 2026-04）

GWM 用图 G=(V, E) 建模环境，三个层次：

| 层次 | 关系归纳偏置 | 做什么 |
|---|---|---|
| Graph as Connector | 空间 | 可达性拓扑（导航、路径规划） |
| Graph as Simulator | 物理 | 状态转移规则（物理模拟） |
| **Graph as Reasoner** | **逻辑** | **因果和语义推理** |

论文明确说：第三层（Graph as Reasoner）"使用图来提取语义协议或因果骨架，支持指令遵循和推理"——这**就是 causal-memory 正在做的**。

## 2. causal-memory 对标世界模型

### 2.1 逐能力对标

| 世界模型核心能力 | 正式定义 | causal-memory 的实现 | 状态 |
|---|---|---|---|
| **转移函数 P\*(s'\|s,a)** | 给定状态和动作，预测下一状态 | `caused` 边 = (decision, outcome) 样本 | ✅ 有样本，但离散图遍历，非参数化函数 |
| **向后归因** | 从结果追溯原因 | `trace_cause` / `trace_cause_chain` / `trace_cause_cross_session` | ✅ 完整实现，所有 benchmark 都测这个 |
| **向前模拟（rollout）** | 从决策出发，预测后果链 | `intervention_query`（向前走因果链） | ⚠️ 有 API，但**零 benchmark 测，零竞品** |
| **反事实推理** | "如果做了 Y 而非 X" | `counterfactual_query`（contrastive empirical） | ✅ 有（诚实标注：非 SCM Rung-3） |
| **新状态泛化** | 预测从未经历过的转移 | ❌ 只能走已知边 | **最大差距** |
| **干预 vs 观察** | do(X) ≠ observe(X) | 隐含在边类型（caused=干预样本，fact=观察） | ⚠️ 没有显式 do-operator |
| **在线学习** | 经验积累改善模型 | Q-value（P4）+ Hebbian（P2）+ SWR（P3） | ✅ 动力学已实现 |
| **抑制侧** | "什么阻止了坏结果" | `prevented` 负扩散（−0.3，GABA 类比） | ✅ **独家，无竞品** |

### 2.2 Kimi 的核心判断验证

> "caused 边字面上就是转移函数样本 f(state, action) → outcome"

**完全正确。** 一条 `caused` 边 `[决策: 用 mutex 加锁] →(caused)→ [结果: 死锁]` 在数学上就是 `(s=并发上下文, a=用mutex) → (s'=死锁)` 的样本。整张因果图是从经验中学习到的**离散转移函数**。

> "向后走是归因，向前走是模拟"

**代码验证成立。** `trace_effect_chain_impl`（retrieve.rs:442）是向前走的——`intervention_query` 和 `counterfactual_query` 都调它。所有 benchmark（LoCoMo/LME/Memora）测的都是向后走（归因/检索）。向前走（模拟）是**零 benchmark、零竞品的蓝海**。

> "记忆系统从'记事本'变'模拟器'"

**这是定位级转变。** 当前所有记忆系统的定位都是"记事本"——存事实、检索事实、召回事实。它们回答"发生了什么"。causal-memory 可以回答"如果我做 X，会发生什么"——这是**模拟器**的能力。

## 3. 诚实部分——差距清单

### 3.1 不能泛化到未见过的转移（最大差距）

真世界模型（如 MuZero）学了游戏的隐式规则后，能预测从未经历过的状态。causal-memory 的图只能走已知边——如果没记录过"决策 A → 结果 B"，就不能预测它。

这是**样本级 vs 函数级**的根本区别：
- 样本级（我们）：`[A → B]` 是一条记录，查到就能用，查不到就不知道
- 函数级（真世界模型）：`f(A) ≈ B` 是学到的规则，即使没见过 `(A, B)` 对，也能推断

**弥合路径**：LLM 可以做"零样本推断"——用因果图的已知边作为 few-shot examples，让 LLM 推断未见过的转移。这相当于用 LLM 做"转移函数的近似器"，用因果图做"训练数据"。`reconstruct_lesson` 已经在这个方向上走了一步（从 Markov-blanket 子图重构叙述），但没有显式做转移预测。

### 3.2 因果边覆盖率太低

conv0 有 419 轮对话、19 个 session，但 distill 只提取出 **49 条因果边**。一个对话里大量的隐式因果关系没被抓到。

**根因**：当前 distill prompt 只提取显式的事件/教训（"用户决定 X，结果是 Y"）。但很多因果关系是隐式的——"提到 Redis 后用户说延迟降了"隐含 `Redis →caused→ 低延迟`，但 distill 不会提取它。

**优化方向**：extractor 层需要更强的因果抽取能力。可以用 LLM 做"因果标注"——对每轮对话问"这轮里有什么决策？导致了什么结果？"，而不只是提取"事件/事实"。

### 3.3 没有显式 do-operator

Pearl 的因果阶梯里，世界模型需要区分：
- **观察** P(Y|X)：看到 X 时 Y 的概率（相关性）
- **干预** P(Y|do(X))：强制设 X 时 Y 的概率（因果性）

causal-memory 隐含了这个区分——`caused` 边是干预样本（agent 主动做了决策），`fact` 边是观察样本（用户说了某事实）。但没有形式化的 `do(X)` 操作——不能说"假设我做了 X（即使从没做过），会怎样"。

`counterfactual_query` 接近这个能力——它比较"做了 X 的记录结果" vs "做了 Y 的记录结果"。但它是**经验对比**，不是**干预推断**。

## 4. 我们独有的东西——世界模型视角下的护城河

从世界模型的视角看，causal-memory 有三个**没有任何系统实现**的能力：

### 4.1 prevented 负扩散 = 干预的抑制效应

世界模型需要建模"什么阻止了坏结果"——这是 **negative intervention**。`prevented` 边（−0.3 扩散）精确地表达了这个：决策 C 阻止了坏结果 B。

```
状态: 缓存可能陈旧
  → 不做任何事 → 缓存陈旧（坏结果）
  → 加 TTL 刷新 →(prevented)→ 缓存陈旧被阻止（好结果）
```

在 forward rollout 时，agent 可以问"当前状态有哪些坏结果风险？哪些决策能 prevented 它们？"——这是**风险规避规划**，不是简单检索。

### 4.2 前向模拟的 API 已经实现

`intervention_query` 做的就是世界模型的 forward search：

```
给定: "我打算用 Redis 做缓存"
向前走: Redis →caused→ 缓存击穿 →caused→ 数据库过载
返回: "用 Redis 做缓存可能导致缓存击穿和数据库过载"
```

这是**决策前的 what-if rollout**——agent 在行动前模拟后果。没有 benchmark 测它，没有竞品做它，但 API 已经在代码里了。

### 4.3 动力学 = 在线学习的世界模型

P2（Hebbian）+ P3（SWR）+ P4（Q-value）+ P6（noveltyEntropy）让因果图**随经验演化**——这是世界模型的在线学习：

- Q-value：被证明有用的转移获得更高权重（reward shaping）
- Hebbian：频繁共现的决策对获得更强的关联（统计学习）
- SWR：睡眠时回放因果链，强化重要的、丢弃不重要的（experience replay）
- noveltyEntropy：遇到新颖经验时触发巩固（curiosity-driven learning）

这些在 RL 世界模型里都有对应物（Dyna 架构的 model learning、prioritized replay、curiosity exploration），但**没有任何 agent 记忆系统实现了它们**。

## 5. 从"记忆系统"到"世界模型"的路线图

### Phase 1：证明前向模拟的价值（最高优先）

**设计前向模拟 benchmark**：不是 LoCoMo 式的"记住过去答问题"，而是"给定历史因果图，预测决策后果"。

协议草案：
1. 用 trap-world 的因果图（已有 agent ablation 数据）
2. 对每个任务，在 agent 行动前调 `intervention_query` 预测后果
3. 对比预测后果 vs 实际后果——预测准确率 = 前向模拟质量
4. 对比"有前向模拟的 agent" vs "无前向模拟的 agent"——决策质量差异

**预期**：前向模拟的 agent 在第 2 次遇到同类陷阱时，会在行动前"看到"坏后果，从而避免——而不是踩了坑才记住。

### Phase 2：提高因果边覆盖率（extractor 层）

当前 distill 只提取显式事件。需要更强的因果抽取：
- 对每轮对话问"这轮里有什么决策→结果对"
- 隐式因果（"提到 X 后 Y 发生了"）也要提取
- 目标：从 49 条/conv 提升到 200+ 条/conv

### Phase 3：LLM 零样本转移推断

用因果图的已知边作为 few-shot examples，让 LLM 推断未见过的转移：
```
已知: [mutex →caused→ 死锁] [channel →prevented→ 死锁]
推断: [semaphore →caused→ ?]  ← LLM 推断，不是图遍历
```

这把因果图从"样本集合"升级为"规则学习的数据"——LLM 成为转移函数的近似器。

## 6. 结论

> **causal-memory 不是完整的世界模型，但它是唯一朝世界模型方向走的 agent 记忆系统。**
>
> Kimi 的判断正确：caused 边 = 转移函数样本，向后走 = 归因，向前走 = 模拟。记忆系统从"记事本"到"模拟器"的转变，是比 QA benchmark 分数更锋利的定位。
>
> 三个差距（泛化、覆盖率、do-operator）都有明确的弥合路径。三个独有能力（prevented 负扩散、前向模拟 API、动力学在线学习）没有竞品。
>
> 下一步不是在 LoCoMo 上卷到 91.6%——是设计前向模拟 benchmark，证明"决策前 what-if rollout"的价值。**agent 真正需要的不是"记住过去"，是"预测未来"。**

---

## 参考资料

- **Physical Intelligence** (2026-07) · *A Definition and Roadmap for World Models* · arXiv:2607.06401 · 定义世界模型为"有限计算资源约束下对状态转移过程的压缩建模"，POMDP 形式化
- **Liu et al.** (2026-04) · *Graph World Models: Concepts, Taxonomy, and Future Directions* · arXiv:2604.27895 · CUHK + 清华 · GWM 三层分类法（Connector/Simulator/Reasoner）
- **Sutton** (1990) · *Dyna architectures* · 世界模型的 RL 起源——经验、模型学习、规划、行动的闭环
- **Pearl** (2009) · *Causality* · 因果阶梯：观察（Rung 1）→ 干预（Rung 2）→ 反事实（Rung 3）
- [insights/17](../../insights/17-complete-memory-system.md) — complete-memory-system 架构（One Graph, One Engine, One Loop）
- [insights/11](../../insights/11-causal-state-store.md) — 因果状态库概念设计
- `docs/code-review-retrieval.md` — Kimi 的 code review（边/节点规模分析 + 优化风险）
