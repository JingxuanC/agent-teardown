# Insights · Agent 的第二定律 —— 反熵增

> 本篇是拆解 kimi-code(25 篇)+ grok-build(10 篇)后,对"agent 到底是什么"的**最终思考**。不是行业调研(那个在 §9),是我自己的洞察。
>
> 核心论点:**Agent 的本质是反熵增。所有工程努力都是在对抗系统的自然退化。**

## 0. 起点:一个尴尬的事实

拆完 35 篇文档后,我发现一个尴尬的事实:

**LLM + 工具 + 记忆 + 循环 = 人人都知道的东西**。GPT 一下就能出来。这不是"洞察",是"描述"。

真正的问题是:**为什么 agent 这么难做好?**

如果你有一块 200K context 的 LLM,给它 10 个工具,让它循环跑 —— 它**立刻就会出问题**:
- 20 轮后 context 爆了
- 30 轮后开始重复(陷入 doom loop)
- 50 轮后"忘记"了用户最初的请求
- 100 轮后可能还没完成,但 token 已经烧了几十块

**这不是 LLM 不够聪明的问题。这是热力学问题。**

## 1. Agent 的第二定律

> 在一个孤立系统中,熵(混乱度)总是增加的。Agent 也不例外。

Agent 的运行**天然会产生熵**。这不是 bug,是物理定律:

```
用户输入 → LLM 推理 → 工具执行 → 结果反馈 → LLM 再推理 → ...
              ↑                                          ↑
         每一步都在产生熵                            熵不断累积
```

| 熵的种类 | 产生原因 | 不干预的后果 |
|---|---|---|
| **上下文熵** | 对话越来越长,信息堆积 | LLM 注意力分散,回复质量下降 |
| **状态熵** | goal / plan / mode 状态变化累积 | 状态机不可逆,bug 堆积 |
| **工具熵** | 工具结果堆积,有用和无用混杂 | context 爆炸,token 浪费 |
| **行为熵** | agent 偏离正轨(重复、绕圈、放弃) | doom loop,用户体验崩溃 |
| **错误熵** | 错误累积,retry 失败叠加 | 系统崩溃或 hang |

**Agent 框架的全部工作 = 对抗这五种熵。**

## 2. 所有模块 = 反熵措施

回头看拆过的 **35 篇文档**,**每一个模块**都能对应到一种"反熵":

### 反上下文熵(对抗信息堆积)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Compaction** | kimi-code | LLM 写 handoff note 替换旧消息 |
| **两遍压缩** | grok-build | pass1 压 95% → pass2 合并尾部,保留更多细节 |
| **StepSummary 折叠** | kimi-code | 老 step 藏成"… thinking 5 times" |
| **Subagent 隔离** | 两者 | 子 agent 的 context 不污染父 |
| **reminder 变体** | kimi-code | full/sparse/reentry,省 token |

### 反行为熵(对抗偏离正轨)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Doom Loop 检测** | grok-build | 服务端实时检测重复 + mid-stream abort |
| **Stop Detector** | grok-build | regex 检测"I'll stop here"等过早放弃信号 |
| **Goal Strategist** | grok-build | stall 时 spawn 独立 agent 重组策略 |
| **3 轮 blocked 审计** | kimi-code | 连续 3 次才能声明 blocked(防偷懒) |
| **max_steps** | 两者 | 硬上限(1000),最后的防线 |
| **Goal continuation prompt** | 两者 | 每轮注入目标,防止"忘了一开始要干嘛" |

### 反状态熵(对抗状态混乱)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Wire Op/Model** | kimi-code | 状态变更走纯函数 apply,可重放 |
| **DeepReadonly** | kimi-code | Object.freeze 防篡改 |
| **SQLite + checkpoint** | grok-build | 快照 + 增量恢复 |
| **Hunk Tracker** | grok-build | 行级别变更追踪,精确 undo |
| **Worktree Pool** | grok-build | 预创建隔离环境,防交叉污染 |
| **Scope 生命周期** | kimi-code | App/Session/Agent 三层,销毁即清理 |

### 反错误熵(对抗错误累积)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **Skeptic Panel** | grok-build | N 个独立 agent 对抗验证 goal 完成 |
| **Circuit Breaker** | grok-build | 滑动窗口熔断,防 provider 故障雪崩 |
| **Sandbox** | grok-build | 物理隔离(landlock/seatbelt),即使权限误判也兜底 |
| **Permission 链** | 两者 | 多 policy 决策,单点失误不致命 |
| **错误归一化** | kimi-code | kosong 把 5 种 provider 错误统一 |
| **abort 理由传播** | 两者 | 区分用户取消 vs 超时 vs 错误 |

### 反工具熵(对抗工具膨胀)

| 措施 | 框架 | 怎么做 |
|---|---|---|
| **BM25 工具搜索** | grok-build | 100+ 工具时用搜索引擎而非全量列表 |
| **tool dedup** | kimi-code | 同名工具去重 |
| **MCP 工具上限** | 两者 | 最多 100 个,防撑爆 LLM tool list |
| **profile 工具集** | 两者 | explore 不注册写工具(减少选择空间) |

## 3. 反熵的"能量投入"

热力学第二定律说:要减少熵,必须**从外部输入能量**。

Agent 的"能量"是什么?

```
能量 = LLM 算力(token 成本)+ 工程约束(代码)
```

每次反熵操作都要**花钱**:

| 反熵操作 | 成本 |
|---|---|
| Compaction(一次 LLM 调用) | ~$0.01-0.05 |
| Skeptic panel(N 个 LLM 调用) | ~$0.05-0.20 |
| 两遍压缩(两次 LLM 调用) | ~$0.02-0.10 |
| Doom loop abort + retry | 额外一轮 LLM 调用 |
| Goal continuation prompt | 每轮多 ~200 token |

**这就是为什么 agent 比 chatbot 贵得多** —— 不是因为"功能多",是因为**反熵需要持续的能量投入**。每次 compaction、每次 skeptic 验证、每次 continuation prompt,都是"花钱买秩序"。

**推论**:一个完全不做反熵的 agent 最便宜,但会在 20 轮后崩溃。一个"过度反熵"的 agent 很贵,但稳定。**好的 agent 框架在成本和秩序之间找平衡**。

## 4. 五种反熵策略

从 35 篇拆解中,我抽象出**五种反熵策略**:

### ① 压缩(Compress)

把大量信息**有损压缩**成少量精华。

- kimi-code:单遍 compaction(LLM 写 handoff)
- grok-build:两遍 compaction(pass1 + pass2)

**类比**:空调压缩机(把气态制冷剂压缩成液态,释放热量)。

### ② 隔离(Isolate)

把**不相关的部分**隔开,防止交叉污染。

- Subagent 隔离:子 agent 的 context 不进父 agent
- Worktree 隔离:不同任务在不同 git worktree
- Sandbox 隔离:子进程在沙箱里,碰不到主系统

**类比**:防火门(把火灾控制在局部)。

### ③ 验证(Verify)

不信任系统自身的判断,用**独立的第三方**复核。

- Skeptic panel:N 个独立 agent 投票
- Stop detector:regex 检测 bail 信号
- Permission policy:多个独立规则链式决策

**类比**:审计制度(自己说的不算,要第三方审)。

### ④ 恢复(Recover)

当系统已经退化,**回到已知好的状态**。

- Wire restore:重放 Op 序列重建状态
- Checkpoint + rewind:回到快照点
- Circuit breaker:熔断后等冷却再半开试探
- Doom loop retry:abort 后重试

**类比**:自动备份(崩溃后还原)。

### ⑤ 约束(Constrain)

在系统**开始退化前**就限制行为空间。

- max_steps:防止无限循环
- Goal 状态机:只允许特定状态转换
- Budget(turn/token/wall-clock):限制资源消耗
- Sandbox profile:限制文件/网络访问

**类比**:限速器(车开不快就不会翻)。

## 5. 反熵密度 = 框架质量

回到核心论点:

> **Agent 框架的好坏 = 反熵措施的密度和质量。**

kimi-code vs grok-build:

| 维度 | kimi-code | grok-build |
|---|---|---|
| **反熵措施数** | ~15 个 | ~25 个 |
| **反熵策略** | 压缩 + 恢复 + 约束(少而精) | 五种全覆盖(多而全) |
| **反熵质量** | **架构级**(DI/wire 是根本性的) | **功能级**(每个是独立补丁) |
| **反熵成本** | 低(靠架构,不靠额外 LLM 调用) | 高(skeptic panel + 两遍压缩 = 多次 LLM) |

**这不是谁好谁坏**,是两种反熵哲学:
- **kimi-code**:从架构层面防熵(DI 让状态天然有序,wire 让变更天然可恢复)
- **grok-build**:从功能层面反熵(每个退化模式都有专门的对抗措施)

## 6. 为什么 agent 比传统软件难

传统软件的熵增很慢:
- 代码写好了,不变就不增熵
- 内存满了?重启就好(状态全清)
- 程序员**手动控制**所有状态转换

Agent 的熵增**极快**:
- 每个 turn 都产生新信息(上下文熵)
- LLM 每次返回不同内容(不可预测)
- agent 跑 100 轮,状态空间爆炸
- **没有人类在中间干预**每个决定

这就是为什么 agent 需要**远比传统软件多的工程基础设施**:不是因为它"功能多",是因为它的**熵增速率远高于传统软件**。

## 7. 一个预测

如果"反熵增"是 agent 的本质,那么:

### 预测 1:未来的 agent 框架会有更多反熵功能

- **主动反思**:agent 跑完后自动复盘,把经验存入长期记忆(grok-build 的 memory crate 是雏形)
- **自适应压缩**:根据 context 内容**动态决定**保留什么(不只是按比例)
- **预测性 doom loop 检测**:在循环发生**之前**就预判(基于行为模式)
- **多模态 compaction**:不只压缩文本,还压缩图片/代码 diff

### 预测 2:反熵成本会成为 agent 的主要成本

随着 LLM 价格下降,反熵(skeptic / compaction / continuation)的 LLM 调用成本占比会**越来越高**。未来的优化方向是**减少反熵的 LLM 调用**:
- 用小模型做 skeptic(不需要全能力)
- 用算法替代部分 compaction(例如提取式摘要)
- 用缓存减少重复验证

### 预测 3:Agent 的"天花板"由反熵能力决定

不是 LLM 的智商决定 agent 上限,是**反熵措施的效率**决定。一个 70 分的 LLM + 优秀的反熵 = 比 99 分的 LLM + 糟糕的反熵更好的 agent。

## 8. 最终定义

> **Agent 是一个在不可逆的熵增中,通过持续的能量投入(压缩、隔离、验证、恢复、约束),维持秩序和目标导向性的系统。**

不是"LLM + 工具 + 记忆"(那只描述了结构)。
不是"自主决策"(那只描述了行为)。

**Agent 的本质是反熵增** —— 和生命体、建筑物、社会组织一样,存在的意义就是对抗自然的混乱趋势。

之前定义的五个特征(自主性/反馈环/持久性/约束/可组合性)**都是反熵的手段**:

| 特征 | 对应的反熵策略 |
|---|---|
| 自主性(Autonomy) | 约束(限制决策空间,防止发散) |
| 反馈环(Feedback Loop) | 验证(通过结果修正方向) |
| 持久性(Persistence) | 恢复(崩溃后重建秩序) |
| 约束(Constraint) | 约束(直接限制行为) |
| 可组合性(Composability) | 隔离(分而治之,防交叉污染) |

五个特征不是并列的,是**从属于"反熵增"这一根本目标的具体手段**。

---

## 9. 行业全景(之前的调研,保留作参考)

以下是大厂对 agent 的公开探索,作为本篇的**佐证** —— 你会发现他们的所有设计**都能归入五种反熵策略**:

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

### Grok Build(我自己)

- Doom loop 检测 = **恢复**(abort + retry)
- Skeptic panel = **验证**(对抗审查)
- Circuit breaker = **恢复**(熔断 + 冷却)
- Sandbox = **隔离**(物理隔离)
- Compaction = **压缩**(两遍压缩)
- Stop detector = **约束**(检测过早放弃)

**所有大厂的设计,无一例外,都是五种反熵策略的具体实现。**

---

## 10. 参考资料

### 本仓库的拆解(反熵的证据)

kimi-code(25 篇):
- [01-architecture.md](../frameworks/kimi-code/01-architecture.md) —— DI × Scope(反状态熵)
- [03-goal-mode.md](../frameworks/kimi-code/03-goal-mode.md) —— goal 状态机(反行为熵)
- [06-tool-system.md](../frameworks/kimi-code/06-tool-system.md) —— 权限链(反错误熵)
- [07-wire-protocol.md](../frameworks/kimi-code/07-wire-protocol.md) —— Op/Model(反状态熵)
- [08-context-memory.md](../frameworks/kimi-code/08-context-memory.md) —— Compaction(反上下文熵)
- [24-harness-testing.md](../frameworks/kimi-code/24-harness-testing.md) —— 测试(反错误熵)
- [25-eval-benchmark.md](../frameworks/kimi-code/25-eval-benchmark.md) —— 评测(反行为熵)

grok-build(10 篇):
- [02-doom-loop.md](../frameworks/grok-build/02-doom-loop.md) —— Doom loop(反行为熵)
- [03-skeptic-panel.md](../frameworks/grok-build/03-skeptic-panel.md) —— Skeptic(反错误熵)
- [04-permission-sandbox.md](../frameworks/grok-build/04-permission-sandbox.md) —— Sandbox(反错误熵)
- [05-sampler.md](../frameworks/grok-build/05-sampler.md) —— Circuit breaker(反错误熵)
- [07-goal-complete.md](../frameworks/grok-build/07-goal-complete.md) —— Goal 6 子系统(反行为熵)
- [08-compaction-two-pass.md](../frameworks/grok-build/08-compaction-two-pass.md) —— 两遍压缩(反上下文熵)

### 外部参考

- **Anthropic** · [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **OpenAI** · [Agents SDK](https://developers.openai.com/api/docs/guides/agents)
- **Google** · [Design patterns](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)
- **Schrödinger** · *What is Life?*(1944)—— "生命以负熵为食"。Agent 也是。
