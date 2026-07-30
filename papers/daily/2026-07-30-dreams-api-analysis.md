# Anthropic Dreams API 深度分析 —— 睡眠时间计算的工业化标准

> 来源: [platform.claude.com/docs/en/managed-agents/dreams](https://platform.claude.com/docs/en/managed-agents/dreams) · Anthropic 官方文档 · Beta header `dreaming-2026-04-21` · 配套视频 "Memory and dreaming for self-learning agents"
>
> 本篇是 [papers/daily/2026-07-30.md](2026-07-30.md) 🔥-2 的深度展开。Dreams 是 Anthropic 把"睡眠巩固"做成 **托管 API** 的产品化尝试 —— 它定义了 sleep-time compute 的工业标准。causal-memory 的 SWR consolidate 需要对齐这个设计。

## 0. 一句话结论

> **Dreams 的核心设计是"只产出新记忆，永不修改输入"——这让记忆巩固变成一个可审查、可回滚、可丢弃的安全操作。causal-memory 的 SWR consolidate 必须学这个不可变性原则，否则一旦巩固出错，就再也回不去了。**

---

## 1. 背景：记忆为什么需要"做梦"

[insights/05](../../insights/05-agi-7x24.md) §3.2 和 [frameworks/claude-code/01-memory-context.md](../../frameworks/claude-code/01-memory-context.md) 都讨论过 sleep-time compute。Dreams 是这个概念的官方落地。

Anthropic 的产品经理 Mahesh 在配套视频中把记忆定位为 **"继 MCP、skills 之后的下一个原语"**：

```
MCP（2025）→ 让 agent 访问外部工具和数据
Skills（2025-10）→ 让 agent 获得新能力
Memory（2026）→ 让 agent 从经验中自学习  ← 我们在这里
Dreams（2026）→ 让记忆在离线时自我整理  ← 本篇主题
```

**问题陈述**：agent 在工作时往 memory store 写记忆，但这些写入是**局部和增量的** —— 经过很多 session 后，memory store 会积累重复、矛盾、过时的条目。Dreams 让 Claude 清理这些。

> **对比 causal-memory 的痛点**：causal-memory 的因果边也会积累噪音 —— 过时的决策、被推翻的结论、重复的因果链。我们目前没有自动清理机制，靠 SWR consolidate 手动触发。Dreams 给出了"怎么自动清理才安全"的标准答案。

---

## 2. API 全貌：一个异步巩固任务

Dreams 的本质是一个**异步批处理任务（asynchronous job）**：

### 2.1 数据流

```
┌─────────────────────────────────────────────────────┐
│  输入                                                │
│  ┌──────────────┐   ┌──────────────────────────┐    │
│  │ memory_store │ + │ sessions (1~100 个会话)   │    │
│  │ (已有记忆库)  │   │ (历史对话转录)            │    │
│  └──────────────┘   └──────────────────────────┘    │
│                        ↓                             │
│              [Dream 异步流水线]                       │
│              · 读 memory store                       │
│              · 挖掘 session 转录中的模式              │
│              · 合并重复 / 替换过时 / 验证事实         │
│              · 提取新洞察（recurring mistakes 等）    │
│                        ↓                             │
│  输出                                                │
│  ┌──────────────────────────────┐                   │
│  │ 新的 memory_store（独立的）   │ ← 输入永不被修改   │
│  └──────────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

### 2.2 核心 API 调用

```python
dream = client.beta.dreams.create(
    inputs=[
        {"type": "memory_store", "memory_store_id": store_id},
        {"type": "sessions", "session_ids": [session_a, session_b]},
    ],
    model="claude-opus-4-8",
    instructions="Focus on coding-style preferences; ignore one-off debugging notes.",
)
print(dream.id)  # drm_01...
```

**参数详解**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `inputs` | array | 一个 memory_store + 1~100 个 sessions |
| `model` | string | 执行流水线的模型 |
| `instructions` | string (≤4096 字符) | 可选，引导整理方向 |

**支持的模型**：`claude-fable-5`, `claude-opus-4-8`, `claude-opus-4-7`, `claude-sonnet-5`, `claude-sonnet-4-6`。注意有 `claude-fable-5` —— 这是 Anthropic 专门为长 horizon agent 设计的模型。

### 2.3 instructions 字段 —— 最关键的设计

`instructions` 不是对记忆文本的编辑指令，而是**对整个综合流水线的引导**。文档明确区分：

```
✅ 正确用法（高层综合引导）：
   "focus on coding-style preferences"     → 聚焦提取方向
   "preserve project structure unchanged"  → 保留哪些不变
   "structure output by topic"             → 输出组织方式

❌ 错误用法（对具体行的命令式编辑）：
   "change sentence X to Y"    → 不会生效
   "fix the count in section Z" → 不会生效
```

> **设计哲学**：Dreams 是"综合 pass"，不是"编辑器"。它读输入、理解模式、产出新组织，而不是逐行修改文本。如果要做针对性编辑，应该对输出 store 直接用 Memory Stores API。
>
> **对 causal-memory 的启示**：causal-memory 的 SWR consolidate 应该加一个类似 `instructions` 的参数。例如 `"focus on causal lessons; ignore routine operations"` —— 让巩固只提取因果教训，忽略日常操作噪音。这比现在"无差别回放所有链"精确得多。

---

## 3. 最重要的设计决策：输入不可变

> **"The input store is never modified, so you can review the output and discard it if you don't like the result."**

这是整份文档最重要的一句话。它定义了记忆巩固的**安全模型**：

### 3.1 为什么不可变很重要

| 如果巩固直接改原图（causal-memory 当前做法） | 如果巩固产出新图（Dreams 做法） |
|---|---|
| 巩固出错 → 原始记忆被破坏 → 不可逆 | 巩固出错 → 丢弃输出 → 原图完好 |
| 无法 A/B 对比新旧 | 可以对比两个 memory store |
| 无法回滚 | 随时切回旧 store |
| 信任边界模糊（LLM 直接改了你的数据） | 信任边界清晰（LLM 只产出一个候选） |

**这就是"可审查性"** —— Dreams 把巩固从"破坏性写操作"变成了"只读分析 + 生成新候选"。这在生产环境是必须的，因为 LLM 巩固会出错（幻觉、错误合并、误删）。

### 3.2 生命周期管理

Dreams 的状态机：

```
pending → running → completed → (archived)
                 ↘ failed → (archived)
                 ↘ canceled → (archived)
```

| 状态 | 含义 | 输出 store 状态 |
|---|---|---|
| `pending` | 已创建，排队中 | 空 |
| `running` | 流水线处理中 | 已克隆输入 store，持续更新 |
| `completed` | 成功完成 | 完整的新 memory store |
| `failed` | 出错终止 | 保留失败前的部分内容 |
| `canceled` | 被取消 | 保留取消前的部分内容 |

**亮点**：即使 `failed` 或 `canceled`，输出 store 也保留部分内容（不删除），让你检查崩溃前产出了什么。这是"可调试性"的体现。

> **对 causal-memory 的启示**：causal-memory 的 `swr_consolidate` 目前直接修改 `CausalGraph`（LTP 增强边、LTD 减弱边、GC 删除边）。**这是破坏性的**。应该改成产出一个新的 graph snapshot，让上层决定是否替换。具体做法：
> - SWR 产出 `CausalGraph` 的 delta（哪些边增强、哪些删除）
> - 把 delta 应用到一个 clone 上
> - 返回 clone，原始 graph 不变
> - 上层验证后用 clone 替换原图

---

## 4. 可观测性：能"观看"巩固过程

Dreams 有一个很巧妙的设计：`session_id` 字段。

```python
# dream.running 时, session_id 指向执行流水线的底层 session
# 可以 stream 这个 session 的事件, 实时观察 dream 在读什么、写什么
```

```
while dream.status in ("pending", "running"):
    time.sleep(10)
    dream = client.beta.dreams.retrieve(dream.id)
    print(f"status={dream.status} input_tokens={dream.usage.input_tokens}")
```

**意义**：巩固过程不再是黑盒。你可以实时看到 Claude 在读哪条记忆、在做什么合并决策。session 在 dream 终止后会被 **archive（不是 delete）**，所以转录保留下来，事后可审计。

> **对 causal-memory 的启示**：causal-memory 的 SWR consolidate 目前是静默的。应该加一个"巩固日志" —— 记录 LTP 增强了哪些边、LTD 减弱了哪些边、GC 删除了哪些边、replay 重放了哪些链。这对调试和审计至关重要。

---

## 5. 错误处理与限制

### 5.1 错误类型

| `error.type` | 触发场景 |
|---|---|
| `timeout` | 流水线超出运行时间预算 |
| `internal_error` | 未分类的流水线失败 |
| `memory_store_org_limit_exceeded` | 组织的 memory store 数量超上限 |
| `input_memory_store_too_large` | 输入 store 超出大小限制 |
| `input_memory_store_unavailable` | 输入 store 在 dream 运行中被 archive/delete |
| `input_session_unavailable` | 输入 session 在 dream 运行中被删除 |

**注意**：如果在 dream 运行时删除输入 store 或 session，dream 会失败。这强化了"输入不可变"的契约 —— 不仅产出不改输入，**输入在消费期间也不能被动**。

### 5.2 限制

| 限制 | 值 |
|---|---|
| 每 dream 的 sessions 数 | 100 |
| `instructions` 长度 | 4,096 字符 |
| 支持的模型 | 5 个（fable-5, opus-4-8/4-7, sonnet-5/4-6） |

### 5.3 计费

按标准 API token 费率计费，成本随输入 session 的数量和长度**大致线性增长**。文档建议"从小批量 session 开始，满意后再扩大"。

---

## 6. Dreams 做了什么、没做什么

Dreams 的四个功能：

1. **合并重复**（deduplicate）—— 多个 session 写了同一条事实
2. **替换过时**（replace stale）—— 新 session 推翻了旧事实
3. **验证事实**（verify）—— 检查记忆是否自洽
4. **提取新洞察**（surface insights）—— recurring mistakes（反复犯的错）、successful strategies（成功策略）

**Dreams 没做的（causal-memory 的机会）**：

| 能力 | Dreams | causal-memory |
|---|---|---|
| 因果关系巩固 | ❌ 不区分因果 | ✅ 保留 caused/prevented 语义 |
| 负面教训保留 | ❌ 模糊 | ✅ prevented 边显式保留 |
| 图结构（spreading） | ❌ memory store 是条目列表 | ✅ CSR 图 + spreading activation |
| compaction survival | ❌ 不涉及 | ✅ +20.8pp 实证 |
| 多 agent 记忆共享 | ⭐ 视频提到（未来方向） | ⭐ 待做 |

---

## 7. 对 causal-memory 的四个具体行动

| # | 行动 | 对应 Dreams 设计 | 优先级 |
|---|---|---|---|
| 1 | **SWR consolidate 改为不可变** —— 产出 graph delta + clone，不直接改原图 | 输入永不被修改 | 🔥 高 |
| 2 | **加 `instructions` 参数** —— 引导巩固方向（"focus on causal lessons"） | instructions 字段 | 🔥 高 |
| 3 | **加巩固日志** —— 记录 LTP/LTD/GC 的每一步操作 | session_id 可观测 | ⭐ 中 |
| 4 | **加巩固的"候选→确认"流程** —— 产出候选 graph，人工/自动确认后替换 | review output → leverage/discard | ⭐ 中 |

### 7.1 不可变 consolidate 的伪代码

```rust
// 当前（破坏性）：
pub fn swr_consolidate(&mut self, graph: &mut CausalGraph) {
    // 直接修改 graph: LTP 增强, LTD 减弱, GC 删除
}

// 改造后（不可变）：
pub fn swr_consolidate(
    &self,
    graph: &CausalGraph,
    instructions: Option<&str>,   // ← 新增：引导方向
) -> ConsolidationResult {
    let delta = self.compute_delta(graph, instructions);  // 计算 LTP/LTD/GC 的变更
    let new_graph = graph.apply_delta(&delta);             // 应用到 clone，原图不变
    ConsolidationResult {
        new_graph,              // 候选新图
        delta_log: delta,       // 变更日志（可审计）
        instructions_used: instructions,
    }
}
// 上层验证后: self.graph = result.new_graph
```

---

## 8. 和人脑的类比

Dreams 的命名直接来自**人类睡眠中的梦境**。人脑的睡眠巩固分两个阶段（[insights/05](../../insights/05-agi-7x24.md) §3.2）：

| 人脑阶段 | 功能 | Dreams 对应 |
|---|---|---|
| NREM 慢波睡眠（SWS） | 重放白天经验，巩固情景记忆 | ✅ 读 session 转录，重放经验 |
| REM 快速眼动睡眠 | 整合关联，提取抽象知识 | ✅ 合并重复，提取 insights |
| 海马体→皮层转移 | 情景记忆转成语义记忆 | ✅ memory store 重新组织 |

**关键类比**：人脑的睡眠巩固也是"不破坏原始记忆"的 —— 新皮层慢慢形成稳定的语义表征，但海马体的情景记忆在相当长时间内仍然保留（这是为什么你能记起昨晚做的梦的具体情景，也能记起它的抽象意义）。Dreams 的"输入不变 + 产出新 store"完美对应了这个生物学机制。

> **causal-memory 的对应**：我们的 SWR（Sharp Wave Ripple）回放对应 NREM，但应该确保情景记忆（原始因果链）在巩固后仍然可查，而不是被语义知识完全替代。**情景和语义应该共存，不是替代**。

---

## 9. 最终判断

> **Dreams API 是 sleep-time compute 的工业化标准。它最大的贡献不是技术（合并重复、提取洞察这些大家都知道怎么做），而是设计原则 —— "输入不可变"。**
>
> 这个原则把记忆巩固从"危险的破坏性操作"变成了"安全的生成性操作"。一旦巩固出错可以丢弃重来，记忆系统就敢大规模、高频率地做巩固。
>
> **对 causal-memory 的核心影响**：SWR consolidate 必须从"直接改图"改成"产出候选图"。这是生产级记忆系统的安全底线。同时加 `instructions` 参数让巩固方向可控，加巩固日志让过程可审计。
>
> **跨域类比**：人脑的睡眠巩固也是"不破坏原始记忆"的 —— 海马体情景记忆和新皮层语义记忆长期共存。Dreams 的不可变设计完美对应了这个生物学事实。causal-memory 的 SWR 应该同样保留情景记忆（原始因果链）的可查性。

---

## 参考资料

- **官方文档**: [platform.claude.com/docs/en/managed-agents/dreams](https://platform.claude.com/docs/en/managed-agents/dreams)
- **配套视频**: [Memory and dreaming for self-learning agents](https://www.youtube.com/watch?v=RtywqDFBYnQ) · Anthropic · 2026-05-08
- **Beta header**: `dreaming-2026-04-21`
- **支持模型**: claude-fable-5, claude-opus-4-8, claude-opus-4-7, claude-sonnet-5, claude-sonnet-4-6
- **限制**: 100 sessions/dream, 4096 字符 instructions
- **insights 对应**: [05](../../insights/05-agi-7x24.md) §3.2（睡眠巩固）+ [09](../../insights/09-stateless-function.md)（无状态函数）+ [frameworks/claude-code/01-memory-context.md](../../frameworks/claude-code/01-memory-context.md)
