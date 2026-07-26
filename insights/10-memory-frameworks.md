# Insights · 记忆公司赛道 —— 09 命题的外部验证与诊断

> 本篇是 [09-stateless-function.md](09-stateless-function.md) 的**外部验证**:用专门做 AI 记忆的头部公司(Letta / Mem0 / Zep)的公开架构和 benchmark,检验"LLM 是无状态函数,记忆 = 检索 + 注入"这个命题。
>
> 结论先说:**整个赛道的存在本身,就是 09 命题的最强实证。** 没有一家记忆公司押注"把记忆写进模型参数",它们全部默认 `llm(context) -> output` 这个签名不变,然后在这个约束下做工程。但它们各自的召回策略,都没有做对 09 §5 说的"按当前任务动态决定召回什么"。
>
> 这篇同时回应 [papers/01-review.md](../papers/01-review.md) R1-M1 的样本量质疑 —— 不用拆 Claude Code,而是用"整个记忆公司赛道都印证了同一论点"作为更强的外部证据。

## 0. 起点:一个市场的存在,就是命题的实证

[09-stateless-function.md](09-stateless-function.md) 的核心命题:**LLM 是无状态的纯函数,context 之外皆不存在**。由此推出:**所有"记忆"都是每轮重新组装 context 的检索系统**。

如果这个命题是对的,那应该有人专门做这种检索系统,而且应该形成一个市场。

**事实:这个市场已经存在,而且至少八家公司在认真做。** 2026-07 更新:原版只列了三家(美国为主),本版补全中国和开源社区的玩家。

| 公司 / 项目 | 背景 | 开源 | 核心哲学 |
|---|---|---|---|
| **Letta** | MemGPT (UC Berkeley Sky Computing Lab) | Apache 2.0 | Agent 用工具调用**自己管理**记忆 |
| **Mem0** | YC 孵化 | 开源 | 后台**自动抽取**事实 + 混合检索 |
| **Zep** | Graphiti 时序图谱 | Apache 2.0 | 事实带**时间窗口**的知识图谱 |
| **Cognee** | ECL 管道 → 类型化图谱 | 开源 | 文档密集型知识图谱 |
| **OpenViking** | 字节跳动火山引擎 | 开源 | **虚拟文件系统**组织记忆(L0/L1/L2 分层加载) |
| **M3-Agent** | 字节跳动研究院 | 开源 | 多模态 agent + 长期记忆 |
| **MemOS / 记忆张量** | 中国公司,近亿元天使轮 | 部分开源 | 记忆**操作系统** + 跨 LLM 记忆协议(MIP) |
| **OpenMemory**(mem0 出品) | mem0 的 MCP 产品线 | 开源 | **MCP server** 形态,挂载到 coding agent |

**关键事实:八家里没有一家把记忆写进模型参数。** 它们全部在"模型外部的存储 + 检索 + 注入"这个框架内做工程。这不是偶然 —— 这是 `llm(context) -> output` 这个接口契约的直接后果,跨越美国、中国、欧洲的设计团队的共识。

Letta 团队(Sleep-time Compute 论文,2025-04)自己说的一句话,几乎就是 09 开篇命题的复刻:

> "Today's language models are **fundamentally stateless**, as they have no persistent memory of their experiences or learnings. **Persistent context forms the bridge** that allows insights gained during sleep time to improve future capability."

**他们的工程起点,就是 09 的命题起点。** 区别只在于:他们先发了论文(2025-04),我的 09 写于 2026-07 —— 他们动手更早,但框架更窄(单点解法);我的框架更抽象(统一命题),但动手更晚。

## 1. 三家公司的架构哲学

### Mem0:Extract-and-Retrieve(后台抽取)+ MCP 挂载

最简单直接:`add()` 在每轮后调用,LLM 自动从对话里抽取"值得记的事实";`search()` 在下一轮前调用,按相似度召回。

```
对话 → LLM 抽取事实 → 三层混合存储(vector + graph + KV) → 相似度召回 → 注入 context
```

**三层存储**:vector index 做语义召回,graph layer 存实体关系,key-value 存快速结构化查询。自动抽取意味着开发者不用写"该记什么"的逻辑。

**2026-07 更新:Mem0 现在主推 MCP 形态挂载到 agent。** mem0 出了一个独立产品 **OpenMemory**,作为 MCP server,把记忆能力作为**两个工具**暴露给 agent:

```
Coding Agent (Claude Code / Cursor / CoCo)
    │ stdio (MCP 协议)
    ▼
mem0-mcp server (Python 进程)
    │
    ├──► Qdrant (向量库,存 embedding)
    │
    └──► Ollama (本地 embedding 模型,可选)
```

Agent 看到的是两个 MCP 工具:`search_memories(query)` 和 `add_memory(text)`。每轮推理前调一次 search,有新事实时调 add。**这恰好是 [09](09-stateless-function.md) 说的"检索 + 注入",MCP 只是让检索/注入成为 agent 的工具调用,不是新机制。**

一个真实实践里的细节(Cortex Code + mem0 部署)值得一提:用户必须在 `AGENTS.md` 里强制写"Do NOT ask the user before searching — do it proactively"。**因为 agent 不会主动调记忆工具,必须靠 prompt 强制它。** 这反向印证了 §5 的诊断 —— Mem0 是"盲召回",不理解任务,需要外部规则强制它检索。

### Zep:时序知识图谱(Graphiti)

押注完全不同的架构:**每条事实都是带时间窗口的边**。

```
事实变化时:不覆盖旧边 → 标记 valid-to → 创建新边带 valid-from
查询时:"现在什么是真的" / "3 月时什么是真的" 都能精确回答
```

这就是 Graphiti(Temporal Knowledge Graph)的核心。"用户在 Pro 套餐"不会被删掉,而是在升级时间戳后被标记失效,同时新建一条"用户在 Enterprise 套餐"的边。图谱保留了**完整的时间历史**。

### Letta:Agent 自管理记忆(OS 范式)

最激进的一家。不是"应用调用的记忆服务",而是**有状态的 agent 运行时**。

```
main context (RAM)  ↔  archival memory (disk)
        ↑
  agent 自己用工具调用决定:
  - 什么放进 main context
  - 什么 evict 到 archival
  - 什么时候从 archival 拉回来
```

Agent 通过 `core_memory_append` / `core_memory_replace` / `archival_memory_insert` / `archival_memory_search` 等工具调用,**自己决定**记忆的分配。这是 MemGPT 论文("Towards LLMs as Operating Systems")的直接产品化。

**区别于 Mem0/Zep**:那两家是**你调用的记忆服务**(store this, fetch that);Letta 是**你部署的 agent 运行时**(agent 自己管记忆)。Agent 是 long-lived、stateful 的,它"拥有"自己的记忆预算,就像进程拥有自己的地址空间。

### OpenViking:虚拟文件系统(字节火山引擎,2026 新增)

2026 年字节火山引擎开源的**第五种架构**。不用向量库、不用知识图谱,而是把记忆/资源/技能组织成**一个虚拟文件系统**:

```
viking://user/adrian/preferences/         # 用户偏好(持久)
viking://user/adrian/projects/agent-teardown/  # 项目相关
viking://agent/coder-001/skills/          # agent 的技能
viking://agent/coder-001/episodes/        # agent 的对话历史
```

然后用**目录递归检索(Directory Recursive Retrieval)** + L0/L1/L2 分层加载:

| 层 | 加载什么 | 何时加载 | Token 消耗 |
|---|---|---|---|
| L0 | 目录元信息(目录名/摘要) | 总是加载 | 极低 |
| L1 | 文件元信息(文件名/摘要) | 进入相关目录时 | 低 |
| L2 | 文件全文 | 显式打开时 | 高 |

**这是和向量库/图谱完全不同的检索哲学** —— 它按**层级 + 主题**组织,不按"语义相似度"组织。更接近人类查文件的方式(我知道这个东西在哪个抽屉,而不是"和这个东西语义相似的东西")。

**意外地接近 [07](07-philosophy-deep-dive.md) §4 + [11](11-causal-state-store.md) 的"身份层"**:OpenViking 的 `viking://agent/coder-001/episodes/` 路径就是一个 agent 的"自传体记忆"—— 这是 Parfit 因果连续性所需要的"不可压缩的身份层"的工程化雏形,只是它按 episode(事件序列)组织,不是按因果关系组织。

对比向量库的优势(Red Hat 部署 OpenViking 的实测):

| 维度 | 经典向量 RAG | OpenViking |
|---|---|---|
| context 结构 | 扁平 chunks | 文件层级 |
| 检索策略 | 一次性语义相似 | 目录递归 |
| token 消耗 | 高(每次塞整 chunk) | 优化(分层加载) |
| 可观测性 | 黑盒 | 完整检索轨迹 |
| 持久记忆 | 弱(只有 chat history) | 原生(`viking://user/` + `viking://agent/`) |

### MemOS:记忆操作系统(记忆张量,2026 新增)

中国记忆赛道的头部公司,2024-11 成立,**近亿元天使轮**(孚腾资本 + 算丰信息 + 中金资本,国资 + 算力背景),CEO 熊飞宇(Drexel 博士)。

核心产品 **MemOS**(论文 arXiv:2507.03724,被引 88 次)的定位比 mem0/Zep 大一个量级 —— 不做记忆服务,做**记忆操作系统**:

| 维度 | Mem0 / Zep / Letta | MemOS |
|---|---|---|
| 定位 | 记忆**服务/库**(被应用调用) | 记忆**操作系统**(底层) |
| 跨模型 | 绑定单一 LLM | **Memory Interchange Protocol (MIP)** —— 跨 LLM 共享记忆 |
| 演化 | 记忆被读/写 | 记忆**可控、可塑、可演进** |
| 目标 | 给 agent 加记忆 | 给整个 LLM 生态加记忆层 |

**最值得注意的一点:MIP(Memory Interchange Protocol)**。这是一个**跨公司的记忆交换协议** —— 类似 Google A2A 协议(agent 间通信),但是给**记忆**用的。不同公司、不同架构的 LLM 通过 MIP 共享和复用记忆单元。

**这恰好对应 [09](09-stateless-function.md) 的一个隐含推论**:既然 LLM 是无状态函数,记忆必然在外部;那不同 LLM 之间迟早需要一个共享的记忆协议 —— 不然每个模型都自己存一份,记忆碎片化。MemOS 押注的就是这一层。详见 [11](11-causal-state-store.md) §8.5 对因果图跨 agent 共享的讨论。

**但 MemOS 仍然建立在 LLM 无状态的前提下**。它的"记忆可控/可塑/可演进"全部是通过 context 注入实现的,不是改 LLM 权重。换句话说:**MemOS 仍然走 [09](09-stateless-function.md) 说的"检索 + 注入"路线,只是把它做成了 OS 级基础设施。** 连国资背景、想做"记忆 OS"的中国头部公司,都不敢押注 LLM 变有状态 —— [09](09-stateless-function.md) 命题又一次被验证。

## 2. 把五家映射进 09 的召回策略表

09 §3 列了五种"记忆方案"。现在用真实公司填进去(原版三家 + OpenViking + MemOS):

| 09 §3 的策略 | 检索方式 | 有损程度 | **谁在做** |
|---|---|---|---|
| 完整 context(理想态) | 全部塞进去 | 无损 | 无人押注(长上下文撞 09 §4 三堵墙) |
| Compaction handoff | LLM 压缩后塞进去 | 高 | kimi-code、grok-build |
| 向量库 RAG | 相似度召回 | 低(召回不全) | **Mem0**(vector + graph + KV) |
| 知识图谱 | 结构化查询 | 低(建模不全) | **Zep**(+ 时间窗口) |
| 多尺度记忆 | 按时间尺度分层召回 | 各层不同 | **Letta**(main + archival + sleep-time) |
| **虚拟文件系统**(09 没列出) | 目录递归 + 分层加载 | 低 | **OpenViking**(L0/L1/L2) |
| **记忆 OS + 跨模型协议**(09 没列出) | OS 级调度 + 跨 LLM 共享 | 各模块不同 | **MemOS**(MemOS + MIP) |

### 三个 09 没列出的发现

**发现一(原版):09 §3 表里的"知识图谱(尚未普及)"这一格,被 Zep 填了**,而且填得比 09 预想的更好 —— 加了时间维度(validity window)。

**发现二(原版):Letta 超出了 09 的五种分类** —— 它不是任何一种"固定策略",而是**让 agent 自己选策略**。这接近 09 §5 说的"按当前任务动态召回",但代价是 LLM-in-the-loop 的延迟和 token 成本。

**发现三(2026-07 新增):OpenViking 和 MemOS 揭示了 09 §3 的分类本身不够**。09 把"记忆方案"等同于"召回策略",但 OpenViking 是**检索哲学**不同(层级而非相似度),MemOS 是**系统层级**不同(OS 而非库)。**完整的记忆架构分类需要三个维度:存储结构(向量/图/文件/…)、检索策略(相似/时序/层级/因果)、系统层级(库/服务/OS)。** 09 只覆盖了第一个维度。

## 3. LongMemEval 的硬数字:召回策略的精度差距

理论分析不够,看 benchmark。**LongMemEval**(arXiv:2410.10813)是这个赛道的 de facto 压力测试 —— 专门测"长对话里的事实召回",而且是**事实会随时间变化**的场景。

用 GPT-4o 跑:

| 记忆方案 | LongMemEval 分数 | Context Tokens | 中位延迟 |
|---|---|---|---|
| **Zep**(时序图谱) | **63.8%** | 1.6K | 2.58s |
| **Mem0**(混合存储) | 49.0% | - | - |
| Full-context(全塞) | 基准 | 115K | 28.9s |

**三个结论:**

### 结论一:召回策略的选择,造成 15 分的精度差距

Zep 比 Mem0 高 **15 个百分点**,差距完全来自架构(时序图谱 vs 向量检索),不是模型能力。**这是 09 §5"召回策略决定一切"的最干净实证。**

### 结论二:Zep 用 1/70 的 context 达到更高精度

Zep 只塞 1.6K token 进 context,Full-context 塞 115K —— Zep 用 **1/72 的 token 量**拿到了更高的分数。这证明:**精准检索碾压无脑全塞**。这是 09 §4"长上下文是逃生舱不是终点"的直接证据。

### 结论三:全塞 context 不只是贵,还更慢

Full-context 中位延迟 28.9s,Zep 是 2.58s —— **11 倍延迟差距**。长上下文的 O(n²) 注意力不只是理论问题,是用户能感知到的卡顿。

### benchmark 争议:这个赛道还不成熟

Mem0 曾发布对自己有利的 benchmark 结果,Zep 和 Letta 都公开反驳(Zep 发文称自己比 Mem0 高 24%,Letta 指出 Mem0 不公平地 benchmark 了竞品)。**三家在 benchmark 上互相打架,本身就说明:没有一家做出让另外两家服气的方案。** 这个赛道还在早期。

## 4. Letta 的研究 roadmap 是 05/09 的镜像

这不是泛泛的类比,是逐条对照。Letta(UC Berkeley Sky Computing Lab)过去一年的研究发表,几乎逐条对应 05/09 提出的概念:

| 我在 05/09 提出的 | Letta 已发表的论文 / 产品 |
|---|---|
| [05](05-agi-7x24.md) §3.2 "睡眠巩固"(回放 + 固化) | **Sleep-time Compute**(2025-04, arXiv:2504.13171)—— sleep-time agent 异步编辑 primary agent 的 core memory |
| [09](09-stateless-function.md) §5 "按当前任务动态召回" | **Context Constitution**(2026-04)—— context 组装的原则 |
| [05](05-agi-7x24.md) §3.1 "多尺度记忆" | **MemGPT 2.0**:primary + sleep-time 双 agent 架构 |
| [09](09-stateless-function.md) §9.2 "因果状态库结构化" | **Context Repositories: Git-based Memory**(2026-02)—— 程序化 context 管理 + git 版本控制 |
| [05](05-agi-7x24.md) §3.3 "自演化 prompt" | **Memory Models: memory-native RL**(2026-06)—— 比我提的更激进,直接训练 |
| [09](09-stateless-function.md) §8 "LLM 会变有状态吗" | **Continual Learning in Token Space**(2025-12)—— 押注 token 空间持续学习 |

### 最直接的对应:Sleep-time Compute = 05 §3.2

我 05 §3.2 提出 agent 需要"睡眠周期" —— 回放最近经验、固化短期到长期、丢弃冗余。Letta 的 Sleep-time Compute 论文做了**完全对应**的工程实现:

```mermaid
flowchart LR
    P["Primary Agent<br/>(有工具,无记忆编辑权)"]
    S["Sleep-time Agent<br/>(有记忆编辑权)"]
    M[("Core Memory<br/>+ Archival")]

    P -->|"读"| M
    S -->|"异步编辑"| M
    S -.->|"随时可读"| P
```

Primary agent 不能编辑自己的 core memory —— 这个权力交给 sleep-time agent。Sleep-time agent 在 idle 时段异步地整理、压缩、优化 core memory,primary agent 随时读取(不等 sleep-time 完成)。

**这正好对应 05 §3.2 的"工作 16 小时 + 睡眠巩固 8 小时"架构**,只是 Letta 把它做成了两个并行的 agent 而非两个时段。

### 但 Letta 比我多走了一步

我在 [05](05-agi-7x24.md) §3.3 说"自演化 prompt"是基于经验修改 system prompt。Letta 的 **Continual Learning in Token Space** 更激进 —— 他们押注:

> "Memories learned in token space become **more valuable than the model weights themselves**: agents run perpetually, gradually enriching learned context through trillions of tokens of experience data, **seamlessly transferring their memories across many generations of models**."

**权重是临时的,learned context 才是持久的。** 这是一个非常强的赌注:agent 的"自我"不在模型参数里,在 token 空间的累积记忆里。这和 [07-philosophy-deep-dive.md](07-philosophy-deep-dive.md) §4 的 Parfit 因果连续性是同一个方向 —— 身份不在"物质相同",在"信息链不断"。

## 5. 但没有一家做对了"按当前任务动态召回"

这是这篇的核心诊断。三家公司在 09 §5 的三个问题上,各自只回答了一个:

| 09 §5 的问题 | Mem0 | Zep | Letta |
|---|---|---|---|
| **该注入什么** | 相似度盲召回 | 图结构查询 | Agent 自己决定 |
| **该注入多少** | 固定 top-K | 固定图遍历深度 | Agent 自己决定 |
| **该以什么形态注入** | 抽取的事实片段 | 图的边 + 时间窗 | Agent 自己编辑的 memory block |

### 三家的盲区

**Mem0 的盲区:不理解任务。** 它的召回是 embedding 相似度 —— 不管你这一轮在做什么,只要语义相近就召回。一个 agent 在 debug 时,可能被召回一堆"用户喜欢简洁回答"的无关偏好。**召回和当前任务脱钩。**

**Zep 的盲区:不理解任务,只理解时间。** 时序图谱在"这件事什么时候是真的"上极强,但在"这件事和当前任务有没有关系"上仍然是盲召回。图遍历是结构性的,不是任务驱动的。

**Letta 的盲区:理解任务,但代价太高。** Letta 最接近"按任务召回"(agent 自己决定),但每次记忆编辑都是一次 LLM 调用 —— 延迟翻倍、token 成本翻倍。而且 agent 可能**编辑错** —— 把不该记的记下来,该记的丢了。LLM-in-the-loop 的可靠性是 Letta 的软肋。

### 09 §5 的真正难题没有被解决

> **"按当前任务动态决定召回什么"这件事,需要一个理解当前任务的检索器。**

三家都没做对:
- Mem0 / Zep 用**固定策略**(相似度 / 图遍历)绕开了"理解任务"
- Letta 用**agent 自己**绕开了"理解任务",但引入了 LLM-in-the-loop 的成本和不可靠性

**真正需要的**(09 §9.1)是一个**轻量的、任务感知的检索器** —— 它理解"这一轮 agent 在做什么",然后从外部状态库里精准拉取相关上下文。这个检索器本身可能是一个小模型(不一定需要全能力的 LLM),但当前没有任何一家公司在做这个。

## 6. 五家各自缺什么(映射到 09 §9 的诊断)

基于 [09](09-stateless-function.md) §9 的诊断框架,检查五家记忆公司:

| 09 §9 的研发方向 | Mem0 | Zep | Letta | OpenViking | MemOS |
|---|---|---|---|---|---|
| ① 任务感知的检索器 | ❌ 盲召回 | ❌ 盲遍历 | ⚠️ 有( agent 自管理),但太贵 | ⚠️ 目录递归是结构化的,但仍非任务感知 | ❌ OS 调度但不按任务 |
| ② 因果状态库结构化 | ❌ 扁平事实 | ⚠️ 有图,但是实体关系图不是因果图 | ❌ 文本块 | ⚠️ episodes 路径有事件序列雏形 | ❌ 模块化但非因果 |
| ③ 检索策略的元学习 | ❌ 无 | ❌ 无 | ⚠️ sleep-time 算雏形 | ❌ 无 | ⚠️ 记忆"可塑可演进"含糊提到 |
| ④ 分层压缩精度优化 | ❌ 单层 | ⚠️ 时间分层 | ✅ main + archival 两层 | ✅ L0/L1/L2 三层(本表最优) | ⚠️ OS 级分层但具体方案未明 |

**OpenViking 在 ④ 上是目前最优的**(三层加载比 Letta 的两层更精细),而且在"自传体记忆"上有接近 [11](11-causal-state-store.md) 身份层的雏形(`viking://agent/.../episodes/`)。但 ①②③ 全缺 —— 它的目录结构是静态的(开发者组织的),不是 agent 自动构建的,更不是因果的。

### 最关键的缺口:因果状态库(②)

**没有任何一家做了"因果图"。** Zep 的 Graphiti 是实体关系图("用户" —[在套餐]→ "Pro"),但不是**因果图**("决策 A 导致了结果 B")。

[09](09-stateless-function.md) §9.2 说 7×24 需要把 wire log / SQLite 从"事件流"升级成"因果图",让检索能按**因果关系**而非时间或相似度召回。这个方向三家都没碰。这是最大的空白,也是可能的创业 / 研究机会。

### Letta 的 sleep-time 是最接近元学习(③)的

Letta 的 sleep-time agent 在 idle 时段整理 core memory —— 这某种意义上是"检索策略的元学习"(从记忆编辑的成功/失败里学习怎么更好地编辑)。但它学的是**记忆编辑策略**,不是**召回策略**。而且学习信号很弱(没有明确的"这次召回失败导致了幻觉"的反馈)。

## 7. 这对 7×24 AGI 意味着什么

把 §5 和 §6 接起来:

> **7×24 AGI 的真正瓶颈,不在这些记忆公司现在卖的任何一种方案里。**

| 方案 | 能撑多久不崩溃 | 瓶颈 |
|---|---|---|
| Mem0 | 小时级(个性化场景) | 盲召回 + 无时序 |
| Zep | 天级(状态追踪场景) | 盲遍历 + 无任务感知 |
| Letta | 天级(stateful agent 场景) | LLM-in-the-loop 太贵 + 不可靠 |
| **7×24 AGI 需要** | 月级 | 任务感知检索 + 因果图 + 元学习 |

**当前没有任何一家公司的方案,能撑到月级 7×24。** 它们解决的是"小时到天级的记忆",离"月级"还有一个数量级。这个差距,对应的是 [05](05-agi-7x24.md) 说的"五种新能力"里还没人做对的那几种。

### 谁最接近?

基于 §4 的对照,**Letta 最接近 7×24** —— 它是唯一一家在做 sleep-time compute(睡眠巩固)、continual learning(持续学习)、memory-native RL(记忆原生强化学习)的。它的研究 roadmap 和 05/09 的预测最吻合。

但 Letta 也是**最重的**(agent 运行时,不是可插拔服务)。这暗示一个可能性:**7×24 AGI 的记忆方案,可能不是一个可插拔的 memory layer,而是一个完整的 stateful agent 运行时。** 这和 05 §4 的结论("AGI 最后一公里是反熵基础设施")一致 —— 基础设施不是一个插件,是一整套。

## 8. 回应 review R1-M1 的样本量质疑

[papers/01-review.md](../papers/01-review.md) R1-M1 批评"只分析了两个框架,样本量不够,没有 Claude Code"。

这篇给出了一个**不同维度的回应**:不用再拆一个 agent 框架,而是看**专门做记忆的整个赛道**。

- 6 个 agent 框架(kimi-code / grok-build / Pi / Codex / OpenAI Agents SDK / Google ADK)全部能归入 09 的反熵策略集 → [08](08-self-rebuttal.md) 反驳 5 已经覆盖
- **现在再加上 8 个记忆项目(Letta / Mem0 / Zep / Cognee / OpenViking / M3-Agent / MemOS / OpenMemory),全部默认 LLM 是无状态函数,全部在做检索 + 注入** → 09 核心命题的外部验证
- LongMemEval 的硬数字(召回策略造成 15 分差距)→ 09 §5"召回策略决定一切"的实证
- Mem0 MCP 形态 + OpenViking 虚拟文件系统 + MemOS 记忆 OS,三种完全不同的架构**都收敛到检索+注入** → 命题的鲁棒性验证

**14 个独立实现(6 框架 + 8 记忆项目),跨四种语言(TS / Rust / Python / Go)、四种形态(CLI / 库 SDK / 记忆服务 / 记忆 OS)、八个组织(美国 + 中国 + 欧洲),全部收敛到同一套设计空间。** 巧合的概率极低。

> R1-M1 想要的是"再加一个 Claude Code"。这篇给的是"加一整个赛道,而且是美国 + 中国双赛道"。**Claude Code 是一个数据点,记忆公司赛道是十四个数据点。**

## 9. 最终的一句话

> **专门做 AI 记忆的公司(Letta / Mem0 / Zep / OpenViking / MemOS)全部默认 LLM 是无状态函数,然后做检索 + 注入。这本身证明了 [09](09-stateless-function.md) 的核心命题。**
>
> 它们的架构覆盖了五种完全不同的存储范式(向量库 / 时序图谱 / agent 自管理 / 虚拟文件系统 / 记忆 OS),但**没有一个把记忆写进模型参数**。LongMemEval 上 Zep 比 Mem0 高 15 分,用 1/72 的 token 量碾压 Full-context —— 召回策略的精度差距是实打实的。
>
> 三个值得记录的发现:
> - **Mem0 现在主推 MCP 形态**,但本质仍然是给 agent 两个工具(`search` / `add`),不改变无状态函数接口
> - **字节的 OpenViking 用虚拟文件系统** —— 这是第五种架构,意外接近 [07](07-philosophy-deep-dive.md) 的身份层,但仍非因果结构
> - **中国的 MemOS 押注"记忆 OS + 跨 LLM 协议(MIP)"** —— 野心比美国玩家大一个量级,但仍然建立在 LLM 无状态的前提下
>
> Letta 的研究 roadmap(Sleep-time Compute / Continual Learning / Memory Models)是 [05](05-agi-7x24.md)/[09](09-stateless-function.md) 预测的镜像。MemOS 的 MIP 协议指向了 [11](11-causal-state-store.md) 还没覆盖的一个方向:因果图的跨 agent 共享(见 [11](11-causal-state-store.md) §8.5)。**最大的共同盲区仍然是:没有人做了因果状态库和任务感知检索器。这是 7×24 AGI 记忆架构的两个空白,也是可能的机会。**

---

## 参考资料

完整的参考文献（论文、博客、书籍）已集中维护在 [REFERENCES.md](REFERENCES.md)，所有链接均已验证。本篇涉及的核心参考：

- **Packer, C. et al.** (2023) · *MemGPT: Towards LLMs as Operating Systems* · arXiv:2310.08560 —— Letta 的起源论文,OS 范式的记忆管理
- **Lin, J. et al.** (2025) · *Sleep-time Compute: Beyond Inference Scaling at Test-time* · arXiv:2504.13171 —— Letta 的睡眠巩固工程实现,对应 05 §3.2
- **Wu, W. et al.** (2024) · *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory* · arXiv:2410.10813 —— 记忆赛道的 de facto benchmark,§3 硬数字来源
- **Maharana, A. et al.** (2024) · *LOCOMO: Long Context Multi-Turn Conversational Memory* · arXiv:2402.17753 —— 长对话记忆评测基准
- **ByteDance Volcengine** (2026) · *OpenViking: The Context Database for AI Agents* —— 虚拟文件系统架构,§1 的第五种存储范式
- **Li, Z. et al.** (2025) · *MemOS: A Memory OS for AI System* · arXiv:2507.03724 —— 记忆操作系统 + MIP 跨模型协议,§1 的记忆 OS 架构

> 完整链接见 [REFERENCES.md](REFERENCES.md)。
