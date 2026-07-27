# Anthropic Dreaming 深度分析 —— sleep-time compute 的工业化落地

> 来源: Code with Claude 2026 开发者大会 + claudefa.st 完整技术拆解 + GitHub 泄露的 system prompt
>
> 本篇是 [papers/daily/2026-07-27.md](daily/2026-07-27.md) 🔥-1 的深度展开。Anthropic 的 Dreaming 是 sleep-time compute 的工业化落地,直接验证 [insights/05](../../insights/05-agi-7x24.md) §3.2 的"睡眠巩固"路线。但它也暴露了 causal-memory 的一个定位问题。

## 1. Dreaming 是什么(一句话版)

> **Dreaming 是 Claude Code 的后台记忆整理进程** —— 在 session 之间定期运行,用 Claude 自己(配合 sub-agents)扫描最近的会话记录 + 现有记忆文件,合并重复、删除过时、验证事实、提取新模式、重组索引。

类比:人脑在 REM 睡眠时重放白天的经历,巩固重要的、丢弃不重要的。Anthropic 直接用了这个类比 —— "Auto Dream is the REM sleep cycle"。

## 2. 技术架构:四阶段

Anthropic 的 system prompt(从 GitHub 泄露的 [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) 拿到完整版)描述了四个阶段:

| 阶段 | 名称 | 做什么 |
|---|---|---|
| 1 | **Orient** | `ls` 记忆目录,读 `MEMORY.md` 索引,扫描已有 topic 文件 |
| 2 | **Gather Signal** | 从 daily logs + session transcripts(JSONL)里 grep 新信息,**不全量读,只 grep narrow terms** |
| 3 | **Consolidate** | 合并新信息到 topic 文件,转换相对日期为绝对日期,**删除被推翻的事实** |
| 4 | **Prune & Index** | 更新 `MEMORY.md` 索引(<200 行),删除过时指针,降级冗长条目 |

### 关键设计决策

**a) 文件系统即记忆**
> Claude 把记忆看作一个熟悉的文件系统,用 bash + editor 工具读写。

这不是 Mem0 的 vector store,不是 Zep 的知识图谱,不是 causal-memory 的 SQLite —— **就是普通的文件目录**。利用了 Claude Opus 4.7 对文件系统的强理解能力。

**b) grep,不全量读**
> "Don't exhaustively read transcripts. Look only for things you already suspect matter."

Phase 2 的 system prompt 明确要求 **grep narrow terms**,不全量读 JSONL。这是对 [09](../../insights/09-stateless-function.md) §4 "lost in the middle" 的工程回应 —— 不全量塞进 context,只精准检索。

**c) 删除被推翻的事实**
> "Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source"

这和 Mem0g 的 invalid marking 类似,但 Dreaming **直接删除**(不是标记失效)。这是比 Mem0g 和 causal-memory 的 valid_to 更激进的做法。

**d) 安全沙箱**
> "During a dream cycle, Claude can only write to memory files. It cannot modify your source code, configuration, tests, or any other project file."

Dreaming 运行时是 **read-only on project code, write-only on memory directory**。这是一个重要的安全约束 —— 防止 Dreaming 意外修改代码。

**e) 触发机制**
- 每 24 小时自动触发
- 或每 5 个 session 后触发
- 或手动触发(用户说"dream"/"consolidate memory")

## 3. Claude Code 的四层记忆系统

Dreaming 不是单独存在的,它是 Claude Code 四层记忆里的一层:

| 层 | 名称 | 谁写 | 何时跑 | 存什么 | 人类类比 |
|---|---|---|---|---|---|
| 1 | **CLAUDE.md** | 用户手动 | 启动时加载 | 规则、架构、命令 | 指令手册 |
| 2 | **Auto Memory** | Claude 每轮 | session 中(~5K tokens) | 项目模式、debugging 经验、偏好 | 白天笔记 |
| 3 | **Session Memory** | Claude 自动 | 后台每 ~5K tokens | 对话摘要 | 短期对话回忆 |
| 4 | **Auto Dream** | Claude 定期 | session 之间(24h/5sessions) | 记忆整理 | REM 睡眠巩固 |

**causal-memory 的定位**:
- Layer 2(Auto Memory)对应 causal-memory 的 `record_decision`(实时记录)
- Layer 4(Auto Dream)对应 causal-memory 的 `chain_linker` + 未来的 `consolidate` 命令(离线整理)
- **causal-memory 不是替代任何一层,而是补上它们缺的因果维度**

## 4. Dreaming vs causal-memory 的精确对比

| 维度 | Dreaming | causal-memory |
|---|---|---|
| **存什么** | Markdown 文件(文本记忆) | SQLite 因果边(结构化) |
| **整理方式** | LLM 全文分析 + 文件重写 | 规则 + CTE(自动桥接边) |
| **删除策略** | 直接删除被推翻的事实 | 标记 valid_to(保留历史) |
| **检索** | grep(关键词) | task_tag + keyword + trace_cause_chain |
| **因果关系** | ❌ 不显式存储 | ✅ causal_edges 表 |
| **多跳追溯** | ❌ 无(grep 是单跳) | ✅ recursive CTE |
| **安全** | ✅ 沙箱(只写 memory 目录) | ✅ 独立进程(MCP server) |
| **状态** | research preview(部分用户可用) | v0.6 alpha |

### Dreaming 没做但 causal-memory 做了的

1. **因果边类型**(`caused`/`enabled`/`prevented`) —— Dreaming 的 Markdown 不区分关系类型
2. **置信度分级**(temporal/rule/llm_inferred/user_feedback) —— Dreaming 没有置信度概念
3. **多跳因果链追溯**(trace_cause_chain) —— Dreaming 的 grep 只能单跳
4. **时序窗口**(valid_to 保留历史) —— Dreaming 直接删除,不留时序快照

### Dreaming 做了但 causal-memory 没做的

1. **全自动整理** —— Dreaming 自动合并/删除/重组,causal-memory 只有 chain_linker 做桥接
2. **LLM 驱动的整理** —— Dreaming 用 Claude 自己分析哪些记忆重要,causal-memory 用规则
3. **跨 session 模式提取** —— Dreaming 扫描多个 session transcripts 找模式
4. **文件系统原生** —— Dreaming 用 Markdown 文件(人类可读),causal-memory 用 SQLite(程序友好但人类不可读)

## 5. 对 causal-memory 的影响

### 好消息:Dreaming 验证了 sleep-time compute 路线

[insights/05](../../insights/05-agi-7x24.md) §3.2 预测的"Agent 需要睡眠巩固" —— Anthropic 自己做了。这说明方向是对的。

而且 Dreaming 的四阶段(Orient → Gather → Consolidate → Prune)正好对应 [05](../../insights/05-agi-7x24.md) §3.2 的"回放 → 固化 → 丢弃 → 更新"。

### 坏消息:Dreaming 是文本整理,不是因果整理

Dreaming 整理的是 **Markdown 文本记忆**,不是因果图。它不提取"决策 A 导致了结果 B"这种因果关系 —— 它只做"合并重复、删除过时、重组索引"。

这意味着:
- **Dreaming 不能回答"什么导致了这个失败"** —— 它没有因果边
- **Dreaming 不能做多跳因果追溯** —— 它的 grep 只能找关键词,不能走图
- **Dreaming 不会自动发现"这个决策和过去的某个决策相似"** —— 它不做 MetaCausalEdge

### causal-memory 的定位(再次修正)

> **Dreaming 是文本记忆的整理器,causal-memory 是因果记忆的存储器。**
>
| 需求 | 用 Dreaming | 用 causal-memory |
|---|---|---|
| 合并重复的项目偏好 | ✅ | ❌ |
| 删除过时的事实 | ✅ | ✅(valid_to) |
| 追溯"什么导致了这个 bug" | ❌ | ✅(trace_cause_chain) |
| 查"过去类似任务的教训" | ❌ | ✅(search_causal) |
| 自动整理记忆 | ✅(全自动) | ⚠️(chain_linker 只做桥接) |
| 跨 session 模式提取 | ✅ | ❌(meta_causal_edges 未激活) |

**理想的组合**:Claude Code 的 Dreaming 做文本记忆整理 + causal-memory 做因果记忆存储/追溯。两者互补。

### causal-memory 可以学 Dreaming 的什么

1. **四阶段整理流程** —— causal-memory 的 `consolidate` 命令(路线图)可以借鉴 Dreaming 的 Orient → Gather → Consolidate → Prune
2. **自动触发** —— Dreaming 每 24h 自动跑。causal-memory 的 consolidate 也应该自动触发
3. **安全沙箱** —— Dreaming 运行时只写 memory 目录。causal-memory 的 consolidate 应该只写 SQLite,不碰 agent 的代码
4. **文件系统记忆作为 L0 目录** —— Dreaming 用 `MEMORY.md` 做索引(<200 行)。这正好对应 [13](../../insights/13-reconstructive-memory.md) §1.2 的"系统提示词作为身份层"

## 6. 最终判断

> **Anthropic 的 Dreaming 是 sleep-time compute 的工业化落地,但它整的是文本记忆,不是因果记忆。**
>
> 验证了 [insights/05](../../insights/05-agi-7x24.md) §3.2 的睡眠巩固路线(方向对了)。
>
> 没有削弱 causal-memory 的核心差异化 —— Dreaming 不存因果边,不做多跳因果追溯。但它在"自动整理"和"LLM 驱动整理"上比 causal-memory 成熟很多。
>
> **causal-memory 应该定位为 Dreaming 的因果补充层**:Dreaming 管文本记忆的整理,causal-memory 管因果记忆的存储和追溯。两者可以共存于同一个 agent。
>
> causal-memory 的 `consolidate` 命令(路线图)应该借鉴 Dreaming 的四阶段设计,但聚焦于因果边的整理(合并相似因果边、删除低置信度边、激活 meta_causal_edges)。

---

## 参考资料

- **Dreaming 官方**:Code with Claude 2026 开发者大会(YouTube: "Memory and dreaming for self learning agents")
- **完整技术拆解**:claudefa.st/blog/guide/mechanics/auto-dream
- **泄露的 system prompt**:github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/agent-prompt-dream-memory-consolidation.md
- **Ars Technica 报道**:arstechnica.com/ai/2026/05/anthropics-claude-can-now-dream-sort-of/
- **insights 对应**:[05-agi-7x24.md](../../insights/05-agi-7x24.md) §3.2(睡眠巩固)+ [13-reconstructive-memory.md](../../insights/13-reconstructive-memory.md) §1.2(系统提示词作为身份层)
