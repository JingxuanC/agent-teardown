# Insights · Agent 的第二定律 —— 信息论重构版

> 本篇是拆解**六个 agent 框架**(kimi-code 25 篇 + grok-build 10 篇 + Pi + Codex 4 篇 + OpenAI Agents SDK + Google ADK,共 ~42 篇)后,对"agent 到底是什么"的**核心思考**。
>
> **2026-07 信息论重构**:本篇原版用热力学熵(Boltzmann)作类比,[08-self-rebuttal.md](08-self-rebuttal.md) 反驳 1 指出这是偷换概念(热力学熵 ≠ 信息熵),反驳 2 指出 doom loop 反而是熵减。本版用 [09-stateless-function.md](09-stateless-function.md) 给出的信息论基础重构:Shannon 熵的物理位置被精确定位到 **context 的组装过程**。原版的植物类比保留为**修辞工具(不是论证)**,移到末尾附录。
>
> 核心论点不变:**Agent 的本质是对抗运行时的不确定性增长。所有工程努力都是在对抗系统的自然退化。** 但这次,它建立在 Shannon 信息论上,不是建立在修辞上。

## 0. 起点:一个尴尬的事实

拆完 42 篇文档(六个框架)后,我发现一个尴尬的事实:

**LLM + 工具 + 记忆 + 循环 = 人人都知道的东西**。GPT 一下就能出来。这不是"洞察",是"描述"。

真正的问题是:**为什么 agent 这么难做好?**

如果你有一块 200K context 的 LLM,给它 10 个工具,让它循环跑 —— 它**立刻就会出问题**:
- 20 轮后 context 爆了
- 30 轮后开始重复(陷入 doom loop)
- 50 轮后"忘记"了用户最初的请求
- 100 轮后可能还没完成,但 token 已经烧了几十块

**这不是 LLM 不够聪明的问题。这是信息论问题。**

## 1. Agent 的第二定律(信息论版)

> 在每一轮推理中,context 组装过程必然产生信息损失。这个损失如果不被对抗,会累积到系统失效。

关键起点来自 [09](09-stateless-function.md):**LLM 是无状态的纯函数**。它的宇宙 = 当前 context。context 之外皆不存在。这意味着每一轮推理前,框架都要从外部状态库里**重新组装 context** —— 而组装过程必然有损。

### 只有一种熵:Shannon 信息熵

原版列了"五种熵"(上下文/状态/工具/行为/错误)。[08](08-self-rebuttal.md) 反驳 2 指出这是过度归类 —— "熵"被滥用成了"任何不好的东西",而且 doom loop 实际上是**熵减**(deterministic 循环比随机探索的熵更低)。

**修正:只有一种熵 —— Shannon 信息熵,即"不确定性"。它的物理位置是 context 组装过程。**

```
每轮推理 = 从外部状态库组装 context → 喂给无状态的 LLM
                ↑
         组装过程产生信息损失 = Shannon 熵增
```

### 四种退化源(不是"四种熵")

组装过程的信息损失有四个来源。它们不是"熵",是**信息退化的不同机制**:

| 退化源 | 机制 | 表现 | 不干预的后果 |
|---|---|---|---|
| **信噪比下降** | context 越来越长,有用信息被无用信息稀释 | LLM 注意力分散,回复质量下降 | "上下文熵"(原版) |
| **状态复杂度膨胀** | goal / plan / mode 状态变化累积,状态空间爆炸 | 状态机不可逆,bug 堆积 | "状态熵"(原版) |
| **召回失败** | compaction 压掉了关键信息,或检索没召回该召回的 | 幻觉(见 [09](09-stateless-function.md) §2) | "上下文熵" + "错误熵" |
| **行为收敛**(注意:不是发散) | agent 陷入确定性循环(doom loop) | 行为模式锁死,无法探索新路径 | "行为熵"(原版,但方向搞反了) |

### doom loop 的修正

原版把 doom loop 归为"行为熵增"。这是**方向错误** —— [08](08-self-rebuttal.md) 反驳 2 正确地指出:deterministic 循环比随机探索的熵**更低**。doom loop 实际上是**信息退化的第四种形式:行为锁死**。

```
正常探索:  高信息熵(多种可能路径)→ 找到正确路径 → 熵减(收敛到答案)
doom loop: 熵已经太低(只有一种重复路径)→ 无法逃逸 → 信息冻结
```

doom loop 不是"太混乱",是**"太确定"** —— agent 的行为空间坍缩到一个循环里,失去了探索新路径的能力。对抗 doom loop 的手段(doom loop 检测、goal strategist)不是"减熵",是**"注入随机性 / 打破锁定"**。这和压缩 / 验证等其他反熵措施的机制不同。

**Agent 框架的全部工作 = 对抗这四种退化。**

## 2. 所有模块 = 反退化措施

回头看拆过的 42 篇文档,**每一个模块**都能对应到一种退化源的对症:

### 反信噪比下降

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Compaction** | kimi-code | LLM 写 handoff note 替换旧消息 |
| **两遍压缩** | grok-build | pass1 压 95% → pass2 合并尾部,保留更多细节 |
| **StepSummary 折叠** | kimi-code | 老 step 藏成"… thinking 5 times" |
| **Subagent 隔离** | 两者 | 子 agent 的 context 不污染父 |
| **reminder 变体** | kimi-code | full/sparse/reentry,省 token |

### 反行为收敛(doom loop)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Doom Loop 检测** | grok-build | 服务端实时检测重复 + mid-stream abort |
| **Stop Detector** | grok-build | regex 检测"I'll stop here"等过早放弃信号 |
| **Goal Strategist** | grok-build | stall 时 spawn 独立 agent 重组策略 |
| **3 轮 blocked 审计** | kimi-code | 连续 3 次才能声明 blocked(防偷懒) |
| **max_steps** | 两者 | 硬上限(1000),最后的防线 |
| **Goal continuation prompt** | 两者 | 每轮注入目标,防止"忘了一开始要干嘛" |

### 反状态复杂度膨胀

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Wire Op/Model** | kimi-code | 状态变更走纯函数 apply,可重放 |
| **DeepReadonly** | kimi-code | Object.freeze 防篡改 |
| **SQLite + checkpoint** | grok-build | 快照 + 增量恢复 |
| **Hunk Tracker** | grok-build | 行级别变更追踪,精确 undo |
| **Worktree Pool** | grok-build | 预创建隔离环境,防交叉污染 |
| **Scope 生命周期** | kimi-code | App/Session/Agent 三层,销毁即清理 |

### 反召回失败

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Skeptic Panel** | grok-build | N 个独立 agent 对抗验证 goal 完成 |
| **Circuit Breaker** | grok-build | 滑动窗口熔断,防 provider 故障雪崩 |
| **Sandbox** | grok-build | 物理隔离(landlock/seatbelt),即使权限误判也兜底 |
| **Permission 链** | 两者 | 多 policy 决策,单点失误不致命 |
| **错误归一化** | kimi-code | kosong 把 5 种 provider 错误统一 |
| **abort 理由传播** | 两者 | 区分用户取消 vs 超时 vs 错误 |

### 反工具膨胀

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **BM25 工具搜索** | grok-build | 100+ 工具时用搜索引擎而非全量列表 |
| **tool dedup** | kimi-code | 同名工具去重 |
| **MCP 工具上限** | 两者 | 最多 100 个,防撑爆 LLM tool list |
| **profile 工具集** | 两者 | explore 不注册写工具(减少选择空间) |

## 3. 反退化的"信息处理成本"

热力学第二定律说:要减少熵,必须从外部输入能量。Agent 不交换物理能量,它交换**信息**。所以更准确的说法是:

> 要减少 context 组装过程的信息损失,必须投入**信息处理成本**。

```
信息处理成本 = LLM 算力(token 费)+ 工程约束(代码)+ 检索计算
```

每次反退化操作都要**花钱**:

| 反退化操作 | 成本 |
|---|---|
| Compaction(一次 LLM 调用) | ~$0.01-0.05 |
| Skeptic panel(N 个 LLM 调用) | ~$0.05-0.20 |
| 两遍压缩(两次 LLM 调用) | ~$0.02-0.10 |
| Doom loop abort + retry | 额外一轮 LLM 调用 |
| Goal continuation prompt | 每轮多 ~200 token |
| 检索器召回(向量 / 图谱) | ~ms 级延迟 + 存储成本 |

**这就是为什么 agent 比 chatbot 贵得多** —— 不是因为"功能多",是因为**反退化需要持续的信息处理投入**。每次 compaction、每次 skeptic 验证、每次 continuation prompt、每次检索召回,都是"花钱买信息确定性"。

**推论**:一个完全不做反退化的 agent 最便宜,但会在 20 轮后崩溃。一个"过度反退化"的 agent 很贵,但稳定。**好的 agent 框架在成本和信息确定性之间找平衡。**

> **2026-07 更新**:[10-memory-frameworks.md](10-memory-frameworks.md) §3 的 LongMemEval 数字给出了成本vs精度的硬数据:Zep 用 1.6K token 达到 63.8% 精度,Full-context 用 115K token 达到更低精度。**精准检索比无脑全塞便宜 72 倍,精度还更高。** 这证明反退化的最优解不是"花更多钱",而是"更聪明地组装 context"。

## 4. 五种反退化策略

从 42 篇拆解中,我抽象出**五种反退化策略**:

> **更新(2026-07-25)**:这五种策略已在**六个框架**(kimi-code / grok-build / Pi / Codex / OpenAI Agents SDK / Google ADK)中得到验证,跨三种语言(TS / Rust / Python)、两种形态(CLI / 库 SDK)、四个组织的设计团队。虽然仍不可说"穷尽"(参见 [08 自我反驳](08-self-rebuttal.md) 反驳 5),但六个独立实现的收敛提供了强证据。更进一步,[10](10-memory-frameworks.md) 加入四家记忆公司后,**十个独立实现**全部收敛到同一策略集。

### ① 压缩(Compress)

把大量信息**有损压缩**成少量精华。对抗信噪比下降。

- kimi-code:单遍 compaction(LLM 写 handoff)
- grok-build:两遍 compaction(pass1 + pass2)

### ② 隔离(Isolate)

把**不相关的部分**隔开,防止交叉污染。对抗状态膨胀和信噪比下降。

- Subagent 隔离:子 agent 的 context 不进父 agent
- Worktree 隔离:不同任务在不同 git worktree
- Sandbox 隔离:子进程在沙箱里,碰不到主系统

### ③ 验证(Verify)

不信任系统自身的判断,用**独立的第三方**复核。对抗召回失败(幻觉)。

- Skeptic panel:N 个独立 agent 投票
- Stop detector:regex 检测 bail 信号
- Permission policy:多个独立规则链式决策

### ④ 恢复(Recover)

当系统已经退化,**回到已知好的状态**。对抗所有退化源的累积。

- Wire restore:重放 Op 序列重建状态
- Checkpoint + rewind:回到快照点
- Circuit breaker:熔断后等冷却再半开试探
- Doom loop retry:abort 后重试(注入随机性打破锁定)

### ⑤ 约束(Constrain)

在系统**开始退化前**就限制行为空间。对抗所有退化源。

- max_steps:防止无限循环
- Goal 状态机:只允许特定状态转换
- Budget(turn/token/wall-clock):限制资源消耗
- Sandbox profile:限制文件/网络访问

### 策略 vs 退化源的映射

| 策略 | 信噪比下降 | 状态膨胀 | 召回失败 | 行为收敛 |
|---|---|---|---|---|
| 压缩 | ✅ 主力 | ⚠️ 辅助 | ❌ | ❌ |
| 隔离 | ✅ | ✅ 主力 | ❌ | ❌ |
| 验证 | ❌ | ❌ | ✅ 主力 | ⚠️ 辅助 |
| 恢复 | ✅ | ✅ | ✅ | ✅(注入随机性) |
| 约束 | ⚠️ 辅助 | ✅ | ⚠️ | ✅ 主力 |

**没有一个策略只对一种退化源。也没有一种退化源只被一个策略对抗。** 这是一个多对多的防护网。

## 5. 反退化密度 = 框架质量

回到核心论点:

> **Agent 框架的好坏 = 反退化措施的密度和质量。**

kimi-code vs grok-build:

| 维度 | kimi-code | grok-build |
|---|---|---|
| **反退化措施数** | ~15 个 | ~25 个 |
| **反退化策略** | 压缩 + 恢复 + 约束(少而精) | 五种全覆盖(多而全) |
| **反退化质量** | **架构级**(DI/wire 是根本性的) | **功能级**(每个是独立补丁) |
| **反退化成本** | 低(靠架构,不靠额外 LLM 调用) | 高(skeptic panel + 两遍压缩 = 多次 LLM) |

**这不是谁好谁坏**,是两种反退化哲学:
- **kimi-code**:从架构层面防退化(DI 让状态天然有序,wire 让变更天然可恢复)
- **grok-build**:从功能层面反退化(每个退化模式都有专门的对抗措施)

## 6. 为什么 agent 比传统软件难

传统软件的信息退化很慢:
- 代码写好了,不变就不退化
- 内存满了?重启就好(状态全清)
- 程序员**手动控制**所有状态转换

Agent 的信息退化**极快**:
- 每个 turn 都产生新信息(信噪比下降)
- LLM 每次返回不同内容(不可预测)
- agent 跑 100 轮,状态空间爆炸(状态膨胀)
- compaction 有损压缩(召回失败)
- **没有人类在中间干预**每个决定

这就是为什么 agent 需要**远比传统软件多的工程基础设施**:不是因为它"功能多",是因为它的**信息退化速率远高于传统软件**。而退化的物理位置,精确地在 [09](09-stateless-function.md) 指出的那个地方:**每轮重新组装 context 的过程**。

## 7. 预测

如果"反退化"是 agent 的本质,那么:

### 预测 1:未来的 agent 框架会有更多反退化功能

- **任务感知检索**:根据当前任务动态决定召回什么([09](09-stateless-function.md) §5,[11](11-causal-state-store.md) §5 的因果检索)
- **因果状态库**:把 wire log 升级为因果图,按因果关系而非时间召回([11](11-causal-state-store.md))
- **自适应压缩**:根据 context 内容**动态决定**保留什么(不只是按比例)
- **预测性 doom loop 检测**:在循环发生**之前**就预判(基于行为模式)

> **2026-07 更新**:预测 1 的前两项已有行业验证 —— [10](10-memory-frameworks.md) §4 显示 Letta 的 Sleep-time Compute / Context Constitution / Continual Learning 正在做这些。

### 预测 2:反退化成本会成为 agent 的主要成本

随着 LLM 价格下降,反退化(skeptic / compaction / 检索)的成本占比会**越来越高**。未来的优化方向是**减少反退化的 LLM 调用**:
- 用小模型做 skeptic(不需要全能力)
- 用算法替代部分 compaction(例如提取式摘要)
- 用因果图替代相似度检索([11](11-causal-state-store.md) §5,精度更高,召回更少)
- 用缓存减少重复验证

### 预测 3:Agent 的"天花板"由反退化能力决定

不是 LLM 的智商决定 agent 上限,是**反退化措施的效率**决定。一个 70 分的 LLM + 优秀的反退化 = 比 99 分的 LLM + 糟糕的反退化更好的 agent。

> 但注意:这只覆盖了 agent 的**维护性**([12-generativity.md](12-generativity.md) 将展开)。agent 的**生成性**(写出正确的代码、找到 bug)来自 LLM 本身。反退化保证 LLM 有好的 context 可用,但**生成价值的那个动作,发生在 LLM 的推理里,不在框架里**。

## 8. 最终定义

> **Agent 是一个通过持续的信息处理(压缩、隔离、验证、恢复、约束)来对抗 context 组装过程的信息损失,同时生成有价值输出的系统。**
>
> 它不是"数字生命体"(这个类比太强了,见附录)。它是**一个需要持续维护才能保持有效的信息处理系统** —— 和任何复杂软件系统一样,只是维护的频率和方式更接近"代谢"而非"打补丁"。

不是"LLM + 工具 + 记忆"(那只描述了结构)。
不是"自主决策"(那只描述了行为)。

**Agent 的本质是对抗信息退化** —— 需要持续维护才能保持有效,和任何复杂系统一样。但维护只是**一半**;另一半是**生成有价值的输出**(代码、分析、决策)。反退化(维护) + 生成(创造) = 完整的 agent 定义。详见 [12-generativity.md](12-generativity.md)。

之前定义的五个特征(自主性/反馈环/持久性/约束/可组合性)**都是反退化的手段**:

| 特征 | 对应的反退化策略 |
|---|---|
| 自主性(Autonomy) | 约束(限制决策空间,防止发散) |
| 反馈环(Feedback Loop) | 验证(通过结果修正方向) |
| 持久性(Persistence) | 恢复(崩溃后重建秩序) |
| 约束(Constraint) | 约束(直接限制行为) |
| 可组合性(Composability) | 隔离(分而治之,防交叉污染) |

五个特征不是并列的,是**从属于"反退化"这一根本目标的具体手段**。

---

## 9. 行业全景(佐证)

以下是大厂对 agent 的公开探索,作为本篇的**佐证** —— 你会发现他们的所有设计**都能归入五种反退化策略**:

### Anthropic

五种 workflow 模式:
- Prompt chaining = **约束**(固定序列防发散)
- Routing = **约束**(分类后定向处理)
- Parallelization = **隔离**(独立子任务不干扰)
- Orchestrator-workers = **隔离**(动态分解)
- Evaluator-optimizer = **验证**(迭代改进)

### OpenAI

Agents SDK 核心:
- Guardrails = **约束**(输入/输出校验)
- Handoff = **隔离**(agent 间干净交接)
- Tracing = **恢复**(可回溯调试)
- Sandbox = **隔离**(容器化执行)

### Google

A2A 协议:
- Agent Card = **约束**(能力声明)
- Task lifecycle = **恢复**(状态可追踪)

### Grok Build

- Doom loop 检测 = **恢复**(abort + retry,注入随机性)
- Skeptic panel = **验证**(对抗审查)
- Circuit breaker = **恢复**(熔断 + 冷却)
- Sandbox = **隔离**(物理隔离)
- Compaction = **压缩**(两遍压缩)
- Stop detector = **约束**(检测过早放弃)

**所有大厂的设计,无一例外,都是五种反退化策略的具体实现。**

---

## 10. 本仓库的拆解(反退化的证据)

kimi-code(25 篇):
- [01-architecture.md](../frameworks/kimi-code/01-architecture.md) —— DI × Scope(反状态膨胀)
- [03-goal-mode.md](../frameworks/kimi-code/03-goal-mode.md) —— goal 状态机(反行为收敛)
- [06-tool-system.md](../frameworks/kimi-code/06-tool-system.md) —— 权限链(反召回失败)
- [07-wire-protocol.md](../frameworks/kimi-code/07-wire-protocol.md) —— Op/Model(反状态膨胀)
- [08-context-memory.md](../frameworks/kimi-code/08-context-memory.md) —— Compaction(反信噪比下降)
- [24-harness-testing.md](../frameworks/kimi-code/24-harness-testing.md) —— 测试(反召回失败)
- [25-eval-benchmark.md](../frameworks/kimi-code/25-eval-benchmark.md) —— 评测(反行为收敛)

grok-build(10 篇):
- [02-doom-loop.md](../frameworks/grok-build/02-doom-loop.md) —— Doom loop(反行为收敛)
- [03-skeptic-panel.md](../frameworks/grok-build/03-skeptic-panel.md) —— Skeptic(反召回失败)
- [04-permission-sandbox.md](../frameworks/grok-build/04-permission-sandbox.md) —— Sandbox(反召回失败)
- [05-sampler.md](../frameworks/grok-build/05-sampler.md) —— Circuit breaker(反召回失败)
- [07-goal-complete.md](../frameworks/grok-build/07-goal-complete.md) —— Goal 6 子系统(反行为收敛)
- [08-compaction-two-pass.md](../frameworks/grok-build/08-compaction-two-pass.md) —— 两遍压缩(反信噪比下降)

codex(4 篇):
- [02-dual-stage-memory.md](../frameworks/codex/02-dual-stage-memory.md) —— 双阶段记忆(反信噪比下降 + 反状态膨胀)
- [03-multi-agent-execpolicy.md](../frameworks/codex/03-multi-agent-execpolicy.md) —— ExecPolicy DSL + agent graph(反召回失败 + 隔离)
- [04-compaction.md](../frameworks/codex/04-compaction.md) —— 服务端压缩 + window 追踪(反信噪比下降)

Pi(1 篇):
- [01-architecture.md](../frameworks/pi/01-architecture.md) —— Session Tree + branch summarization(反状态膨胀 + 恢复)

OpenAI Agents SDK + Google ADK(1 篇):
- [01-comparison.md](../frameworks/openai-agents-adk/01-comparison.md) —— 六框架反退化策略全覆盖(验证)

记忆公司(4 家,见 [10](10-memory-frameworks.md)):
- Letta / Mem0 / Zep / Cognee —— 全部在做反退化(反召回失败 + 反信噪比下降),无一例外

---

## 附录:Agent 与植物 —— 一个类比(不是同构)

> ⚠️ **本节是修辞工具,不是论证**。[08-self-rebuttal.md](08-self-rebuttal.md) 反驳 3 已指出:植物类比不是同构,物理层级不同(阳光是电磁辐射,LLM 算力是矩阵乘法)。保留本节是因为它有**沟通价值** —— 它帮助直觉地理解"为什么 agent 需要持续维护",但不要把它当成论证。

一个 agent 能持续工作而不崩溃,和一株植物能持续生长而不枯萎,**在信息处理层面有结构性的相似**(不是热力学同构):

| 植物 | Agent | 功能角色 |
|---|---|---|
| 阳光 | LLM 算力 | **信息处理能力的来源** |
| 光合作用 | Compaction / handoff | **把混乱合成秩序**(局部信息熵减) |
| 根系吸收 | System prompt + reminder 注入 | **信息输入**(维持结构) |
| 蒸腾作用 | 旧消息丢弃 / 折叠 | **排出冗余**(丢掉不再需要的信息) |
| DNA 修复 | Skeptic panel + 错误归一化 | **错误纠正**(对抗变异累积) |
| 细胞凋亡 | Abort + rewind + kill task | **程序性丢弃**(牺牲局部保护整体) |
| 向光性 | Goal continuation driver | **趋向性**(朝目标方向) |
| 免疫系统 | Permission + sandbox | **防御系统**(对抗外部入侵) |

**这个类比的两个实际推论(不依赖热力学同构):**

**推论 1:Agent 需要"代谢"**。植物不"存储阳光",它把阳光**持续转化**成化学能。agent 不能"存一次 context 就用到底",它必须**持续压缩、持续验证、持续恢复**。停止代谢 = 崩溃。

**推论 2:Agent 的"寿命"由反退化能力决定**。一棵 5000 年的狐尾松,不是因为它基因好,是因为它**修复损伤的效率极高**。同样,一个 agent 能跑多久不崩溃,不是由 LLM 的智商决定,是由反退化措施的效率决定。

**但类比到此为止。** 植物的代谢是化学反应(物理必然),agent 的反退化是工程设计(工程选择)。如果换一个工程团队,完全可能设计出不依赖 compaction 的 agent(例如无限的 context window + 不需要压缩的模型架构 —— 见 [09](09-stateless-function.md) §4)。植物不能"不光合作用",但 agent 可以"不 compaction"。**植物类比隐藏了"工程是可选的,物理是必然的"这个区别。**

---

## 参考资料

完整的参考文献（论文、博客、书籍）已集中维护在 [REFERENCES.md](REFERENCES.md)，所有链接均已验证。本篇涉及的核心参考：

- **Shannon, C.E.** (1948) · *A Mathematical Theory of Communication* —— **信息论重构的理论基础**。本版用它替代原版的热力学类比。Shannon 熵的物理位置被 [09](09-stateless-function.md) 精确定位到 context 组装过程。
- ~~Schrödinger · *What is Life?*（负熵）~~ —— 原版引用,本版降级为附录修辞。热力学类比经 [08](08-self-rebuttal.md) 反驳后被信息论替代。
- ~~Prigogine · *Order Out of Chaos*（耗散结构）~~ —— 同上。

> 完整链接见 [REFERENCES.md](REFERENCES.md)。
