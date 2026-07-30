# OpenViking 深度分析 —— 用"虚拟文件系统"重新定义 agent 上下文数据库

> 项目: [github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking) · 字节跳动火山引擎 · 27.7k★ · 论文: VikingMem (arXiv:2605.29640, **VLDB 2026**)
>
> 本篇是 [papers/daily/2026-07-30.md](2026-07-30.md) 🔥-3 的深度展开。OpenViking 把"记忆库"重新构想为**虚拟文件系统** —— agent 用 `ls`/`tree`/`find` 浏览自己的上下文，而不是查黑盒向量库。它的 LoCoMo 80-83% 和 token 节省 34-91% 是目前最强的工程实现。

## 0. 一句话结论

> **OpenViking 的核心创新不是检索算法，是数据组织范式 —— 把记忆、资源、技能统一成一个可分层加载的虚拟文件系统（L0/L1/L2）。causal-memory 应该借鉴它的"目录递归检索 + 分层加载"，但我们的差异化仍在因果图 spreading activation，不在事实召回。**

---

## 1. 背景：为什么需要"上下文数据库"

[insights/13](../../insights/13-reconstructive-memory.md) 和 [papers/daily/2026-07-28.md](2026-07-28.md) 讨论过当前 agent 记忆的格局：Mem0（事实抽取）、Letta（74% LoCoMo）、MemGPT（OS 式分层）。OpenViking 提出了第四种范式：**把上下文当作文件系统来管理**。

传统向量库的问题：

| 问题 | 传统向量库 | OpenViking |
|---|---|---|
| 检索是黑盒 | 给个 query，返回一堆 chunk，不知道为什么 | 每次查询保留"目录浏览轨迹"，可追溯 |
| 结果脱离上下文 | 返回孤立的片段 | 先定位最高分目录，再逐层下钻，结果自带上下文 |
| token 浪费 | 全量加载匹配的 chunk | 分层加载（L0 摘要→L1 概览→L2 全文），按需深入 |
| 无确定性操作 | 只能模糊查询 | 支持 `ls`/`tree`/`find` 等确定性文件操作 |

**OpenViking 的命题**：agent 浏览自己的上下文，应该像开发者浏览文件系统一样 —— 确定性、可观察、按需加载。

---

## 2. 架构：viking:// 虚拟文件系统

### 2.1 统一 URI 协议

OpenViking 把三类上下文统一在 `viking://` 协议下：

```
viking://
├── resources/              # 资源：项目文档、代码库、网页等
│   └── my_project/
│       ├── docs/
│       │   ├── api/
│       │   └── tutorials/
│       └── src/
└── user/
    └── {user_id}/
        ├── memories/       # 记忆
        │   └── preferences/
        │       ├── writing_style
        │       └── coding_habits
        ├── resources/      # 私有资源
        │   └── private_project/
        └── skills/         # 技能
            ├── search_code
            └── analyze_data
```

**关键洞察**：记忆、资源、技能**不再是三种不同的存储**，而是同一个文件系统的不同子目录。这意味着：
- agent 可以用同一套 API（`ls`/`find`/`tree`）操作所有上下文
- 上下文之间可以建立目录层级关系
- 和 [docs/unified-memory-design.md](../../project/causal-memory-hippocampus/docs/unified-memory-design.md) 的"三层统一记忆"（facts + temporal + causal）理念相通

> **对比 causal-memory**：causal-memory 目前把记忆存在 SQLite 表里（causal_facts, causal_edges），靠 SQL 查询。OpenViking 的"虚拟文件系统 + 目录层级"是一种更自然的组织方式 —— 尤其对 agent 来说，"浏览文件"比"写 SQL"更直观。

### 2.2 三层加载（核心创新）

每个条目在写入时被处理成三层：

```
viking://resources/my_project/
├── .abstract               # L0: ~100 tokens - 快速相关性判断
├── .overview               # L1: ~2k tokens - 结构和关键点
└── docs/
    ├── .abstract
    ├── .overview
    └── api/
        ├── auth.md         # L2: 全文内容，按需加载
        └── endpoints.md
```

| 层级 | 大小 | 用途 | 加载时机 |
|---|---|---|---|
| **L0 (Abstract)** | ~100 tokens | 一句话摘要，快速判断相关性 | 检索时先加载所有候选的 L0 |
| **L1 (Overview)** | ~2k tokens | 核心信息 + 使用场景，用于规划 | L0 判断相关后加载 |
| **L2 (Details)** | 全文 | 原始完整数据 | 任务明确需要时才加载 |

**每个目录也带自己的 L0/L1** —— 所以可以在不读任何全文的情况下，判断一个目录是否相关：

```
检索流程:
1. 向量搜索定位"最高分目录"（只读 L0 摘要）
2. 逐层下钻：L0 → L1 → L2
3. 结果自带周围的上下文（不孤立）
```

> **这就是 token 节省 34-91% 的秘密**。传统向量库一查就返回一堆 L2 全文，OpenViking 只在最后一步才加载 L2。
>
> **对 causal-memory 的启示**：causal-memory 的 `hippocampus_search` 目前返回完整的因果边（decision + outcome 全文）。可以学 OpenViking 的分层 —— 检索时先返回因果边的"摘要版"（L0: "决策X导致了结果Y"），用户/agent 觉得相关后再展开全文（L2）。这能大幅降低 token 消耗。

### 2.3 目录递归检索

这是 OpenViking 检索算法的核心，和传统向量搜索有本质区别：

```
传统向量检索:
  query embedding → 和所有 chunk embedding 算相似度 → 返回 top-k chunk
  问题: 返回孤立片段，脱离上下文

OpenViking 目录递归检索:
  Step 1: 向量搜索定位"最高分目录"（不是最高分 chunk）
  Step 2: 在该目录内，按 L0→L1→L2 逐层下钻
  Step 3: 结果自带目录上下文（不孤立）
```

**"可观察的检索"**：每次查询都保留"目录浏览轨迹"。当结果看起来不对时，你能看到是哪条路径产生的。这是传统向量库做不到的 —— 向量库返回 top-k 后，你不知道它为什么返回这些。

> **对 causal-memory 的启示**：causal-memory 的 spreading activation 有类似潜力 —— 我们可以记录"激活轨迹"（seed → 哪些边传播 → 激活了哪些节点），让检索过程可追溯。这比纯 BM25 或向量搜索更透明。

---

## 3. Benchmark：碾压级的表现

### 3.1 LoCoMo（长对话记忆）

OpenViking 集成了三个 agent（OpenClaw、Hermes、Claude Code），效果惊人：

| Agent | 原生准确率 | +OpenViking | 提升 |
|---|---|---|---|
| OpenClaw | 24.20% | **82.08%** | +57.88pp |
| Hermes | 33.38% | **82.86%** | +49.48pp |
| Claude Code | 57.21% | **80.32%** | +23.11pp |

**三个 agent 全部拉到 80-83% 区间** —— 无论原生起点多低，OpenViking 都能把它们拉到同一个高水平。

**对比 causal-memory 的 LoCoMo 65%**：差距 15-18pp。但需要注意：
- causal-memory 的 65% 是 LLM judge 评测，OpenViking 的 80-83% 可能也是 LLM judge（需确认）
- causal-memory 的差异化在**因果召回 + compaction survival**，不在纯事实召回
- OpenViking 是纯检索系统，没有因果推理能力

### 3.2 tau2-bench（多轮 agent 任务）

| 任务类型 | 原生成功率 | +OpenViking | 提升 |
|---|---|---|---|
| Retail | 70.94% | **77.81%** | +6.87pp |
| Airline | 54.38% | **66.25%** | +11.87pp |

tau2-bench 是真实多轮 agent 任务（不是纯 QA），提升 7-12pp 说明 OpenViking 的记忆系统在实际 agent 工作流中有效。

### 3.3 效率指标

| 指标 | 范围 | 意义 |
|---|---|---|
| Token 节省 | **34.3-91.0%** | 分层加载的威力 |
| 延迟降低 | **58.45-66.10%** | 检索更快 |

**对比 causal-memory**：causal-memory 没有公开 token 效率数据。OpenViking 的 34-91% token 节省主要来自 L0/L1/L2 分层加载。如果 causal-memory 加分层（§2.2），理论上也能获得类似的 token 节省。

### 3.4 和其他系统的对比

| 系统 | LoCoMo | Token 效率 | 因果能力 | 数据范式 |
|---|---|---|---|---|
| OpenViking | **80-83%** | **34-91% 节省** | ❌ | 虚拟文件系统 |
| Letta | 74% | 中 | ❌ | 数据库 |
| Mem0 | ~55% | 中 | ❌ | 事实抽取 |
| HeLa-Mem | ~35% (F1) | 1,010 tokens | ❌ | Hebbian 图 |
| **causal-memory** | 65% | 待测 | ✅ | **CSR 因果图** |

**结论**：OpenViking 在纯检索效率上是当前最强。但 causal-memory 在因果推理上是唯一的。两者不是替代关系，是互补关系。

---

## 4. 工程实现亮点

### 4.1 Rust + 大规模工程

OpenViking 是 **Rust 项目**（有 `crates/` 目录），和 causal-memory 同语言。这意味着：
- 性能是第一优先级（Rust 的零成本抽象）
- CSR 格式、SIMD 向量化搜索等底层优化可行
- 1862 commits, 215 contributors, 63 releases, 182 branches —— 这是**生产级规模**的工程

**工程细节亮点**：
- cuVS GPU 向量搜索微批处理（commit `perf(vectordb): micro-batch compatible cuVS searches`）
- 插件系统（支持 Claude Code、Codex、Cursor/Trae、OpenCode）
- 批量 add-message 写入优化
- recall API 的 token budget 控制（`max_chars` 严格限制）

### 4.2 Session → Memory 自动提取

> "After a session commits, OpenViking asynchronously extracts user preferences and agent experience into long-term memory."

这和 Anthropic Dreams 的理念一致 —— session 结束后，异步把经验提取成长期记忆。OpenViking 把这个做成了内置功能。

> **对比 causal-memory**：causal-memory 目前靠 agent 显式调用 `record_decision` 写记忆。OpenViking 的"session commit 后自动提取"更自动化。不过 causal-memory 的因果关系需要显式的 outcome 反馈，不能纯从 session 转录推断 —— 这是因果记忆的固有复杂度。

### 4.3 插件生态

OpenViking 已经集成了主流 agent 框架：
- Claude Code（memory plugin harness）
- Codex（marketplace install）
- Cursor/Trae
- OpenCode

合作伙伴包括：deer-flow（字节的长 horizon SuperAgent）、NoKV（AI 原生分布式文件系统）、loopx、Hermes Agent。

> **对 causal-memory 的启示**：causal-memory 作为 MCP server，天然和这些 agent 框架兼容。但 OpenViking 的"插件化深度集成"（不只 MCP，还有 hooks、statusline 等）值得学习。我们的 MCP 集成是"工具调用"层面的，OpenViking 是"工作流嵌入"层面的。

---

## 5. VikingMem 论文（VLDB 2026）

OpenViking 是 VikingMem 论文的开源子集：

> **VikingMem: A Memory Base Management System for Stateful LLM-based Applications**
> Jiajie Fu, Junwen Chen, Mengzhao Wang, Aoxiang He, Maojia Sheng, Xiangyu Ke, Yifan Zhu, Yunjun Gao.
> arXiv:2605.29640 · **VLDB 2026**

VLDB 是数据库领域的顶会。这说明 OpenViking 的定位是**数据库研究**，不是 NLP/AI 研究。它的核心贡献在数据管理（分层存储、目录索引、检索效率），不在记忆的认知模型。

> **定位差异**：VikingMem 是"数据库"视角（怎么高效存储和检索），causal-memory 是"认知科学"视角（怎么模拟海马体的因果学习）。两者解决的是不同层面的问题。causal-memory 的 CSR 因果图可以看作 VikingMem 文件系统之上的一层"语义索引"。

---

## 6. 对 causal-memory 的五个行动

| # | 行动 | 对应 OpenViking 机制 | 优先级 |
|---|---|---|---|
| 1 | **因果边分层加载** —— 检索返回摘要版，展开才加载全文 | L0/L1/L2 三层 | 🔥 高 |
| 2 | **记录激活轨迹** —— spreading 的传播路径可追溯 | 可观察检索 | ⭐ 中 |
| 3 | **token budget 控制** —— 检索结果严格限制 token 总量 | max_chars budget | ⭐ 中 |
| 4 | **session 自动提取** —— session 结束后异步提取因果教训 | session→memory | ⭐ 中 |
| 5 | **正式测 token 效率** —— 量化 causal-memory 的 token 消耗，和 OpenViking 对比 | 34-91% 节省基准 | 🔥 高 |

### 6.1 因果边分层加载的设计

```rust
// 当前: search_causal 返回完整因果边
pub fn hippocampus_search(&self, query: &str) -> Vec<CausalEdge> {
    // 返回 decision + outcome 全文
}

// 改造: 分层返回
pub struct SearchResult {
    edges_l0: Vec<EdgeSummary>,   // L0: "决策X →caused→ 结果Y" 一句话
    edges_l1: Vec<EdgeOverview>,  // L1: 核心信息 + context
    edges_l2: Vec<CausalEdge>,    // L2: 全文（按需）
    activation_path: Vec<Path>,   // 激活轨迹（可追溯）
}
```

---

## 7. causal-memory 的差异化定位（重新校准）

面对 OpenViking 80-83% 的碾压级数据，causal-memory 需要重新校准定位：

| 维度 | OpenViking | causal-memory | 谁强 |
|---|---|---|---|
| 纯事实召回 (LoCoMo) | 80-83% | 65% | **OpenViking** |
| Token 效率 | 34-91% 节省 | 待测 | **OpenViking** |
| 因果推理 | ❌ | ✅ caused/prevented | **causal-memory** |
| Spreading activation | ❌ | ✅ CSR 图传播 | **causal-memory** |
| 负面教训 (prevented) | ❌ | ✅ GABA 抑制 | **causal-memory** |
| Compaction survival | ❌ | ✅ +20.8pp | **causal-memory** |
| 生产成熟度 | 27.7k★, 1862 commits | v0.9.0 | **OpenViking** |

**重新校准的定位**：
- causal-memory **不应该和 OpenViking 在事实召回上竞争** —— 那是用数据库工程打认知科学，打不过
- causal-memory 的价值在**因果记忆层** —— 它应该作为 OpenViking 这类检索系统**之上**的语义增强
- 理想架构：OpenViking 做底层存储 + 分层检索，causal-memory 做上层的因果图 + spreading activation

> **这和 [docs/unified-memory-design.md](../../project/causal-memory-hippocampus/docs/unified-memory-design.md) 的三层统一设计一致** —— facts 层（像 Mem0/OpenViking）+ temporal 层 + causal 层。causal-memory 不需要重造事实召回的轮子，应该专注因果层，并在统一检索中调用底层的事实召回。

---

## 8. 最终判断

> **OpenViking 是目前最强的 agent 上下文数据库工程实现。它的"虚拟文件系统 + 三层加载 + 目录递归检索"把 token 效率推到了 34-91% 节省，LoCoMo 拉到 80-83%。**
>
> 但它是**数据库视角**的胜利 —— 解决"怎么高效存储和检索上下文"，不解决"怎么从经验中学习因果关系"。causal-memory 不应该在这个赛道上和它正面竞争。
>
> **对 causal-memory 的核心影响**：学它的分层加载（L0/L1/L2）和可观察检索，但把定位重新校准为"因果记忆层" —— 作为 OpenViking 这类检索系统的上层语义增强，而不是替代品。causal-memory 的差异化在 caused/prevented 因果语义 + spreading activation + compaction survival，这些 OpenViking 完全没有。
>
> **跨域类比**：OpenViking 像人脑的**新皮层** —— 高效存储、分层组织、快速检索。causal-memory 像人脑的**海马体** —— 因果关联、spreading activation、从经验中学习。人脑两者都有。理想系统是 OpenViking 做存储层 + causal-memory 做因果层。

---

## 参考资料

- **项目**: [github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking) · 27.7k★ · 字节跳动火山引擎
- **论文**: VikingMem · arXiv:2605.29640 · VLDB 2026 · Fu et al.
- **架构文档**: [docs.openviking.ai/en/concepts](https://docs.openviking.ai/en/concepts/01-architecture)
- **设计博客**: [The Database Paradigm for Context Engineering](https://blog.openviking.ai/post/openviking-context-database/)
- **Benchmark 报告**: [openviking-benchmark-results](https://blog.openviking.ai/post/openviking-benchmark-results/)
- **核心概念**: viking:// 协议 + L0/L1/L2 三层加载 + 目录递归检索 + 可观察检索
- **insights 对应**: [13](../../insights/13-reconstructive-memory.md)（重构式检索）+ [09](../../insights/09-stateless-function.md)（无状态函数）+ [docs/unified-memory-design.md](../../project/causal-memory-hippocampus/docs/unified-memory-design.md)（三层统一记忆）
