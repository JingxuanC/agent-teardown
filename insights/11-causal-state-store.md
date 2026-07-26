# Insights · 因果状态库 —— 7×24 记忆架构的最大空白

> 本篇是 [10-memory-frameworks.md](10-memory-frameworks.md) §6 识别的最大空白的**设计展开**。
>
> [10](10-memory-frameworks.md) 诊断出:Zep 的 Graphiti 是实体关系图(实体 → 关系 → 实体),不是因果图(决策 → 导致 → 结果)。没有任何一家生产级记忆公司做了因果状态库。本篇回答:**因果状态库长什么样?它和 Zep 的时序图谱差在哪?怎么从 wire log 自动构建?它为什么能同时解决身份持久化、任务感知检索、失败归因三个问题?**
>
> 这不是哲学思辨(那个在 [07](07-philosophy-deep-dive.md)),是**一个可落地的数据结构设计**。它是整个 insights 系列里最工程化的一篇 —— 因为最大的空白需要最具体的方案。

## 0. 起点:10 §6 的空白,为什么是"最大"的

[10](10-memory-frameworks.md) §6 用 [09](09-stateless-function.md) §9 的诊断框架,检查了 Mem0 / Zep / Letta 三家记忆公司。结果:

| 09 §9 的研发方向 | Mem0 | Zep | Letta |
|---|---|---|---|
| ① 任务感知的检索器 | ❌ | ❌ | ⚠️ |
| **② 因果状态库结构化** | **❌** | **❌(实体关系图,非因果图)** | **❌** |
| ③ 检索策略的元学习 | ❌ | ❌ | ⚠️ |
| ④ 分层压缩精度优化 | ❌ | ⚠️ | ✅ |

**② 是唯一一家都没碰的方向。** 而它恰恰是三个 7×24 核心需求的交汇点:

- [07](07-philosophy-deep-dive.md) §4 Parfit 因果连续性 → 身份 = 因果链不断 → 需要存因果链
- [06](06-open-questions.md) ① 失败归因 → 需要知道哪个决策导致了哪个错误 → 需要存因果链
- [09](09-stateless-function.md) §5 任务感知检索 → 检索应该按因果关系召回 → 需要存因果链

**三个需求,同一个答案:因果状态库。** 这不是巧合 —— 因果关系是"身份""归因""检索"的共同底层。

## 1. 实体关系图 vs 因果图:本质区别

先说清楚 Zep 的 Graphiti 和本篇提议的因果状态库,到底差在哪。

### Zep(Graphiti)存的是什么

```
[用户:小明] —[在套餐:Pro]→ [套餐:Pro]    valid: 2026-01..2026-06
[用户:小明] —[在套餐:Enterprise]→ [套餐:Enterprise]  valid: 2026-06..
[用户:小明] —[在项目:agent-teardown]→ [项目]  valid: 2026-03..
```

**实体关系图回答的问题**:"什么是什么""X 在 T 时的状态是什么"。它的边是**静态关系**(属于、在、喜欢),时间窗口标注这个关系的有效期。

### 因果图存的是什么

```
[决策:用 Redis 做缓存] —[导致]→ [结果:缓存击穿,服务挂了]    置信度: 0.9
[决策:改用 mutex 加锁] —[导致]→ [结果:死锁,测试失败]       置信度: 0.8
[决策:改用 channel 通信] —[导致]→ [结果:race condition 修复]  置信度: 0.95
```

**因果图回答的问题**:"什么导致了什么""X 是被哪个决策造成的""决策 X 产生了什么后果"。它的边是**因果关系**(导致、启用、阻止),带因果置信度。

### 一张对比表

| 维度 | Zep(实体关系图) | 因果状态库 |
|---|---|---|
| **节点** | 实体(用户、套餐、项目) | 决策点 + 结果 |
| **边** | 静态关系(属于、在、喜欢) | 因果关系(导致、启用、阻止) |
| **时间语义** | 状态的有效期(valid-from / valid-to) | 事件发生时间 + 因果被发现时间 |
| **核心查询** | "X 现在是什么状态" / "X 在 T 时是什么状态" | "X 是被哪个决策导致的" / "决策 X 导致了什么" |
| **回答不了** | "为什么服务挂了" | (它的目标就是回答这个) |
| **7×24 场景** | 用户个性化、状态追踪 | debug、失败归因、经验积累、身份持久化 |

**关键洞察:这是两种完全不同的图谱,回答完全不同的问题。** Zep 回答"是什么",因果图回答"为什么"。7×24 AGI 两者都需要 —— 但当前只有前者被 Zep 产品化了,后者是空白。

## 2. 因果状态库的最小 schema

基于上面的区分,给出一个可落地的数据结构设计:

```typescript
// 决策节点:agent 做了一个选择
interface Decision {
  id: string
  timestamp: string          // 决策发生时间
  type: 'tool_call' | 'plan_step' | 'goal_set' | 'hypothesis' | 'code_edit'
  content: string            // 决策内容("用 Redis 做缓存")
  rationale: string          // 为什么这么决策("因为需要降低延迟")
  context_hash: string       // 决策时的 context 快照(用于回溯)
  agent_confidence: number   // agent 自己的置信度
}

// 结果节点:一个决策产生了后果
interface Outcome {
  id: string
  timestamp: string          // 结果被发现的时间
  type: 'success' | 'failure' | 'partial' | 'side_effect'
  content: string            // 实际发生了什么("缓存击穿,服务挂了")
  evidence: string           // 怎么知道的("测试失败 / 用户反馈 / error log")
  severity: number           // 严重程度(0-1)
}

// 因果边:决策导致了结果
interface CausalEdge {
  from: string               // Decision.id
  to: string                 // Outcome.id
  relation: 'caused' | 'enabled' | 'prevented' | 'no_effect'
  confidence: number         // 因果置信度(0-1)
  discovered_at: string      // 这个因果关系是什么时候被确认的
  discovered_by: 'temporal' | 'rule' | 'llm_inferred' | 'user_feedback'
}

// 元因果边:跨任务的决策模式
interface MetaCausalEdge {
  from: string               // Decision.id
  to: string                 // Decision.id
  relation: 'similar_to' | 'repeated' | 'contradicts' | 'refines'
  pattern: string            // 共性模式("都是并发问题的修复尝试")
  confidence: number
}
```

### 两类边的分工

**CausalEdge(决策 → 结果)**:回答"这个决策导致了什么"。用于**失败归因**([06](06-open-questions.md) ①)—— agent 出错时,沿 CausalEdge 回溯"是哪个决策导致的"。

**MetaCausalEdge(决策 → 决策)**:回答"这个决策和过去哪个决策相似"。用于**任务感知检索**([09](09-stateless-function.md) §5)—— agent 遇到新任务时,沿 MetaCausalEdge 找到"过去类似的决策及其因果后果"。

**这两类边合在一起,就是 7×24 的经验积累机制**:不只是"记住发生了什么",而是"记住什么导致了什么,以及过去的什么和现在的什么相似"。

## 3. 怎么从 wire log 自动构建因果图

这是最工程化的一步。wire log 已经记录了 agent 的所有行为(kimi-code 的 Op 流、grok-build 的事件流)。从事件流到因果图,分三步:

### 步骤一:决策点识别(机械的)

wire log 里哪些事件是"决策"?根据类型过滤:

```
tool_call("edit_file", ...)      → Decision(type='tool_call')
plan_step("重构这个函数")         → Decision(type='plan_step')
goal_set("修复 race condition")  → Decision(type='goal_set')
```

**这一步是机械的** —— wire log 已经按 Op 类型标注了,直接映射。每个决策点提取 `content`、`timestamp`、`context_hash`。

### 步骤二:结果链接(半机械的)

为每个 Decision 找到它的 Outcome。启发式:

1. **时间邻近**:决策后最近的结果(测试输出、error log、用户反馈)是候选
2. **内容关联**:结果内容提到决策涉及的文件 / 函数 / 概念
3. **工具链**:决策 → 同一文件的下一次 edit / test → 结果

```
Decision("edit_file: 用 Redis 做缓存", t=100s)
  → Outcome("test failed: 缓存击穿", t=120s)   ← 时间邻近 + 内容关联
  → CausalEdge(confidence=0.8, discovered_by='temporal')
```

**这一步半机械** —— 时间邻近和工具链是规则,内容关联可以用轻量 LLM 或 embedding 辅助。

### 步骤三:因果置信度标注(最难的)

步骤二的 `temporal`(时间邻近)只给出**相关性**,不是因果性。"决策 A 之后发生了 B" ≠ "决策 A 导致了 B"。确认因果需要:

| 方法 | 怎么做 | 置信度 |
|---|---|---|
| **时间邻近** | 决策后最近的结果 | 0.3-0.5(弱,只是相关) |
| **规则匹配** | "edit → test fail" 模式 | 0.6-0.8(中,经验规则) |
| **LLM 推断** | 轻量 LLM 判断"A 是否导致 B" | 0.5-0.7(中,但可规模化) |
| **用户反馈** | 用户明确说"这个改动导致了那个 bug" | 0.9-1.0(强,但稀疏) |
| **重复验证** | 同一类决策反复导致同一类结果 | 0.8-0.95(强,统计因果) |

**最佳实践是分层标注**:先用 `temporal` 快速建边(覆盖率高、置信度低),再用 `rule` 和 `llm_inferred` 逐步提升置信度,`user_feedback` 作为金标准校准。

## 4. Pearl 的因果阶梯:诚实地说明能到哪一层

这一步必须诚实 —— 因果推断是一个有严格定义的学科,不能假装"建了图就等于理解了因果"。

Jude Pearl 的因果阶梯(3 层):

| 阶梯 | 层级 | 回答的问题 | agent 能做到吗 |
|---|---|---|---|
| **第 1 层** | Association(关联) | "观察到 X 时,Y 是什么?" → $P(y \mid x)$ | ✅ 时间邻近 + 统计 |
| **第 2 层** | Intervention(干预) | "如果我做 X,Y 会怎样?" → $P(y \mid do(x))$ | ⚠️ 需要 A/B 测试不同决策 |
| **第 3 层** | Counterfactual(反事实) | "如果当时没做 X,会怎样?" → $P(y_x \mid x', y')$ | ❌ 需要世界模型 / 模拟 |

**当前因果状态库能到第 1 层(关联),勉强摸到第 2 层(通过重复决策的统计)。第 3 层(反事实)对 agent 基本不可能 —— 你没法重跑一次 session 看看"如果当时不这么决策会怎样"。**

这是诚实的边界。因果状态库不解决因果推断问题,它只是给因果推断一个**数据结构**。但拥有这个数据结构,已经比当前的 wire log(扁平事件流)和实体关系图(无因果语义)强一个维度。

> **2026-07 学术更新**:搜索发现学术界已经有人开始做因果图 for agent memory —— REMI(arXiv:2509.06269, 2025)用个人因果图做记忆遍历,Dynamic Causal-Graph Memory(OpenReview 2025-06)做百万 token 推理的结构化检索。但这些是**学术雏形**,不是生产系统,**且没有连接到 7×24 / 身份持久化 / 失败归因**这三个问题。生产级记忆公司(Mem0 / Zep / Letta)没有采用因果图。**学术上有萌芽,工业上无人采用,框架层面无人系统化 —— 这仍然是一个空白,只是不是"零存在"的空白。**

## 5. 因果状态库如何同时解决三个 7×24 问题

这是这篇的核心论证:一个数据结构,解开三个结。

### 解决问题一:任务感知检索([09](09-stateless-function.md) §5)

当前检索的问题([10](10-memory-frameworks.md) §5):Mem0 盲召回(语义相似度),Zep 盲遍历(图结构),Letta 太贵(LLM-in-the-loop)。

**因果检索**走一条完全不同的路:

```
当前任务:"debug 一个 race condition"
         ↓
查询 MetaCausalEdge: 找到过去 type='hypothesis' 且 content ~ 'race condition' 的 Decision
         ↓
命中:[决策:用 mutex 加锁] —[导致]→ [结果:死锁]
      [决策:用 channel 通信] —[导致]→ [结果:成功修复]
         ↓
注入 context:"上次遇到 race condition,mutex 导致死锁;channel 修复成功。建议用 channel。"
```

**这不是语义相似度,是因果相似度。** 它召回的不是"文本上和当前任务像的东西",而是"过去在类似因果场景下,什么决策导致了什么结果"。这是 [09](09-stateless-function.md) §5 说的"按当前任务动态召回"的具体实现。

### 解决问题二:失败归因([06](06-open-questions.md) ①)

06 问"agent 犯错时是哪个环节的锅"。当前框架把所有失败归为"熵"([04](04-anti-entropy.md)),太粗糙。

**因果归因**沿 CausalEdge 回溯:

```
agent 给了错误答案
  ↓ 为什么?
沿因果链回溯:这个答案依赖了哪个 context 片段?
  ↓
发现:context 里的"文件 X 的签名是 Y"来自 3 轮前的一个工具调用
  ↓ 沿因果链回溯
发现:那个工具调用返回了错误数据(API 版本变了,签名已废弃)
  ↓
归因完成:不是 LLM 推理错,是工具数据过时(环境问题)
```

**这就是 06 ① 想要的"因果归因"。** 沿因果链,可以精确地把失败定位到"LLM 推理 / context 组装 / 工具数据 / 权限约束"中的某一层。这比 04 的"都是熵"精细一个数量级。

### 解决问题三:身份持久化([07](07-philosophy-deep-dive.md) §4 + [05](05-agi-7x24.md) 死法④)

07 用 Parfit 的因果连续性论证:agent 的身份不在"内容相同",在"因果链不断"。05 死法④说 compaction 会断裂因果链 → 身份漂移。

**因果状态库就是 Parfit 因果链的工程实现:**

```
day 1 的决策 → (因果链) → day 50 的状态 → (因果链) → day 200 的状态
                                                    ↑
                                         compaction 可以压扁 context,
                                         但因果图保留 "day 1 的决策 A 导致了 day 50 的状态 B"
```

**关键:因果图不被 compaction 压缩。** 它是 [07](07-philosophy-deep-dive.md) §4 说的"不可压缩的身份层"的具体形态 —— 记录"我是谁、我做过什么决策、它们导致了什么"。500 次 compaction 后,context 全换了,但因果图还在,因果链还在。

**这就是 05 §3.1 提出的"身份层"需求,第一次有了具体的数据结构。**

### 三个问题的统一

| 问题 | 当前方案 | 因果状态库的解 |
|---|---|---|
| 任务感知检索(09 §5) | 盲召回 / 太贵 | MetaCausalEdge:因果相似度召回 |
| 失败归因(06 ①) | "都是熵"(太粗糙) | CausalEdge 回溯:精确定位到哪一层 |
| 身份持久化(07 §4 + 05) | 不存在 | 因果图 = 不被压缩的身份层 |

**一个数据结构,三个解。这就是为什么它是"最大空白" —— 它的杠杆率最高。**

## 6. 因果状态库 vs 当前的 wire log

当前框架(kimi-code / grok-build)的状态存储是 wire log / SQLite —— 扁平的事件流。因果状态库是它的**升级**,不是替代:

| | wire log(当前) | 因果状态库(提议) |
|---|---|---|
| 结构 | 扁平事件流(Op 序列) | 因果图(决策 + 结果 + 因果边) |
| 查询 | "t=100s 时发生了什么" | "决策 A 导致了什么" |
| compaction 行为 | 全压缩(信息有损) | 只压 context,**不压因果图** |
| 回放能力 | 完整重放(但 GB 级太慢) | 按因果链回放(只回放相关路径) |
| 构建方式 | 直接记录(已有) | **从 wire log 自动构建**(§3 的三步) |

**落地路径:wire log 是源头,因果状态库是它的索引层。** 不需要替换 wire log,而是在它上面建一个因果索引 —— 类似数据库给原始表建索引。wire log 保持追加写入(可靠),因果索引异步构建(从 wire log 提取决策、链接结果、标注置信度)。

## 7. 这可能是创业 / 研究机会

[10](10-memory-frameworks.md) §6 说"没人做因果状态库"。本篇 §4 更新了这个判断:学术有萌芽(REMI / Dynamic Causal-Graph Memory),工业无人采用。

### 类比 Zep 的成功路径

Zep 把**时间**从实体关系图的"事后标签"提升为"一等公民"(validity window),在 LongMemEval 上比 Mem0 高 15 分。这证明:**把一个之前被忽略的维度做成一等公民,能创造一个新品类。**

因果状态库做的事完全类似 —— 把**因果**从 wire log 的"隐含信息"提升为"一等公民"(CausalEdge)。

```
Zep:  时间(validity window)从隐含 → 一等公民 → 新品类(时序记忆)
因果库:因果关系(causal edge)从隐含 → 一等公民 → 新品类(因果记忆)
```

### "Causal Memory Layer" 作为产品形态

如果有人做这个,产品形态可能长这样:

- **输入**:agent 的 wire log / SQLite / 事件流(任何 agent 框架的输出)
- **输出**:因果图 API —— `query("为什么服务挂了")` / `query("类似的 race condition 之前怎么修的")` / `inject(task="debug race condition")`(返回应该注入 context 的因果链)
- **差异化**:不是"记得什么"(Mem0),不是"什么时候是真的"(Zep),而是"**为什么**"(因果)

这是 Mem0 / Zep / Letta **都不覆盖**的维度。它和它们是正交的 —— 一个完整的 7×24 记忆架构可能同时需要 Zep(时序状态)+ 因果库(因果链)+ Letta(agent 自管理)。

## 8. 难点和开放问题

诚实地说,因果状态库不是"建了就能用"。几个真实的难点:

### 难点一:因果推断本身是 open problem

§4 说了,只能到 Pearl 阶梯第 1 层(关联)。`temporal` 邻近不等于因果。一个 agent session 里,"决策 A 之后发生 B"可能是:
- A 导致了 B(真因果)
- C 同时导致了 A 和 B(共因)
- 纯巧合(时间邻近)

**区分这三种,需要第 2-3 层的因果推断,这是 Pearl 学派都没有完全解决的。** 因果状态库只能给出"候选因果边 + 置信度",不能保证因果正确。

### 难点二:规模爆炸

一个 agent session 跑 10,000 turn,可能有 1,000 个决策点。两两配对的因果边是 O(n²)。7×24 跑一个月,决策点可能上十万。

**需要剪枝策略**:只保留高置信度的边、合并相似的决策、定期做"因果图压缩"(类似 wire log 的 merge)。但压缩本身可能丢因果信息 —— 这又回到 [04](04-anti-entropy.md) 的反熵问题,只不过这次是在因果图层面。

### 难点三:"决策"的边界模糊

什么算一个"决策"?一次 tool call 算一个决策,还是一个 plan step 算一个决策?如果 agent 在一个 goal 下做了 5 个 tool call,这算 1 个决策还是 5 个?

**这没有唯一正确答案**,取决于应用场景。debug 场景可能按 tool call 粒度(精细归因),规划场景可能按 plan step 粒度(粗粒度因果)。需要可配置的决策粒度。

### 难点四:LLM 推断因果的可靠性

§3 步骤三提到用轻量 LLM 判断"A 是否导致 B"。但 LLM 本身就不可靠(见 [09](09-stateless-function.md) §2 幻觉)。用不可靠的工具判断因果,引入了新的不确定性。**这和 Letta 的 "LLM-in-the-loop 检索"问题([10](10-memory-frameworks.md) §5)是同一类软肋。**

## 9. 这篇如何嵌入整个 insights 系列

这篇第一次让 04-10 形成一个**闭环工程方案**:

```
04 反熵增(理论) → 08 自我反驳(修正为信息论) → 09 无状态函数(物理基础)
                                                      ↓
05 7×24 五种死法 ← compaction 断裂因果链 ← 需要因果状态库(本篇)
                                                      ↓
06 ① 失败归因太粗糙 ← 需要因果回溯 ← 因果状态库(本篇)
                                                      ↓
07 §4 Parfit 身份连续性 ← 需要因果链不断 ← 因果状态库(本篇)
                                                      ↓
09 §5 任务感知检索 ← 需要因果相似度 ← 因果状态库(本篇)
                                                      ↓
10 §6 最大空白 ← 本篇给出方案
```

**因果状态库是连接"理论(04/09)"和"工程(05/06/07 需求)"的那座桥。** 之前的 insights 系列在理论层(反熵、无状态)和需求层(7×24 要什么)之间有一个断层 —— 知道要什么,但不知道具体的数据结构是什么。本篇填了这个断层。

## 10. 最终的一句话

> **因果状态库是 7×24 记忆架构的最大空白,也是杠杆率最高的一步。它用一个数据结构(决策 + 结果 + 因果边),同时解决任务感知检索([09](09-stateless-function.md) §5)、失败归因([06](06-open-questions.md) ①)、身份持久化([07](07-philosophy-deep-dive.md) §4)三个问题。**
>
> 学术上有萌芽(REMI、Dynamic Causal-Graph Memory,2025),但生产级记忆公司没有采用,且无人将其系统化地连接到 7×24 三大需求。因果状态库从 wire log 自动构建(三步:决策识别 → 结果链接 → 置信度标注),不替代 wire log,而是它的因果索引层 —— 类似 Zep 把时间从隐含信息提升为一等公民,因果库把因果关系提升为一等公民。
>
> 诚实的边界:它只能到 Pearl 因果阶梯第 1 层(关联),第 3 层(反事实)对 agent 基本不可能。但拥有因果数据结构,已经比当前的扁平事件流和无因果语义的实体关系图强一个维度。**这是 7×24 AGI 记忆架构里,从"知道缺什么"到"知道怎么建"的关键一步。**

---

## 参考资料

完整的参考文献（论文、博客、书籍）已集中维护在 [REFERENCES.md](REFERENCES.md)，所有链接均已验证。本篇涉及的核心参考：

- **Pearl, J. & Mackenzie, D.** (2018) · *The Book of Why: The New Science of Cause and Effect* —— 因果阶梯(关联/干预/反事实),§4 的理论依据
- **Pearl, J.** (2009) · *Causality: Models, Reasoning, and Inference* —— 因果推断的形式化,§4 阶梯定义来源
- **REMI** (2025) · *A Novel Causal Schema Memory Architecture* · arXiv:2509.06269 —— 学术界因果记忆的萌芽
- **Chen, T.Y.** (2025) · *Dynamic Causal-Graph Memory: Structured Retrieval for Million-Token Reasoning* · OpenReview —— 因果图做结构化检索的学术尝试

> 完整链接见 [REFERENCES.md](REFERENCES.md)。
