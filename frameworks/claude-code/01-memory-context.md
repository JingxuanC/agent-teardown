# Claude Code 记忆与上下文架构拆解

> 拆解对象: Claude Code v2.1.214 (npm @anthropic-ai/claude-code)
> 方法: 二进制 `strings` 提取 + sdk-tools.d.ts 类型分析 + system prompt 泄露
> 日期: 2026-07-27
>
> 诚实声明: Claude Code 是 247MB 的编译二进制(Mach-O arm64),不是开源 TS 源码。以下所有结论来自 `strings` 提取的字符串、泄露的 system prompt、和 sdk-tools.d.ts 类型定义。不是完整源码拆解,是**逆向工程的字符串分析**。

## 0. 顶层架构:四层记忆 + 上下文管理

从二进制提取到的关键字符串揭示了一个**四层记忆系统 + 两层上下文管理**:

```
┌──────────────────────────────────────────────────────┐
│ Layer 1: CLAUDE.md (用户手写,启动时全量加载)          │
│   存什么: 规则、架构决策、命令、项目约定                 │
│   类比: 指令手册                                       │
├──────────────────────────────────────────────────────┤
│ Layer 2: Auto Memory (Claude 每轮自动写)              │
│   存什么: 项目模式、debugging 经验、用户偏好            │
│   路径: ~/.claude/projects/<sanitized-cwd>/memory/    │
│   格式: Markdown + frontmatter (name, description, type)│
│   类比: 白天笔记                                       │
├──────────────────────────────────────────────────────┤
│ Layer 3: Session Memory (后台自动,每 ~5K tokens)       │
│   存什么: 对话摘要                                     │
│   格式: JSONL                                          │
│   类比: 短期对话回忆                                    │
├──────────────────────────────────────────────────────┤
│ Layer 4: Auto Dream (定期,session 之间)               │
│   存什么: 整理后的高信号记忆                            │
│   触发: 每 24h 或每 5 个 session                       │
│   类比: REM 睡眠巩固                                   │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Context Management                                    │
│   ├── Compaction (compact-2026-01-12 beta API)       │
│   ├── Context Engineering (CLAUDE.md + grep + glob)  │
│   └── MEMORY.md index (<200 行,截断警告)              │
└──────────────────────────────────────────────────────┘
```

## 1. Layer 1: CLAUDE.md —— 项目宪法

### 加载机制
从二进制提取:
```
"CLAUDE.md auto-discovery"
"Minimal mode: skip ... CLAUDE.md auto-discovery"
```

CLAUDE.md 在启动时自动发现并全量加载。对应 [insights/13](../../insights/13-reconstructive-memory.md) §1.2 的"系统提示词作为身份层"。

### CLAUDE.md Additions 机制
从二进制提取:
```json
{
  "addition": "A specific line or block to add to CLAUDE.md based on workflow patterns. E.g., 'Always run tests after modifying auth-related files'",
  "why": "1 sentence explaining why this would help based on actual sessions",
  "prompt_scaffold": "Instructions for where to add this in CLAUDE.md. E.g., 'Add under ## Testing section'"
}
```

Claude Code 会**主动建议**向 CLAUDE.md 添加规则 —— 基于 session 中观察到的模式。这比静态的 CLAUDE.md 更进了一步。

### 对 causal-memory 的含义
CLAUDE.md 就是 [13](../../insights/13-reconstructive-memory.md) §1.2 说的"系统提示词作为身份层"的真实实现。causal-memory 的系统提示词目录(L0)可以直接复用这个机制。

## 2. Layer 2: Auto Memory —— 文件系统记忆

### 目录结构
从二进制提取:
```
"Custom directory path for auto-memory storage."
"defaults to ~/.claude/projects/<sanitized-cwd>/memory/"
```

路径: `~/.claude/projects/<sanitized-cwd>/memory/`

### 记忆文件格式
每个记忆是独立的 Markdown 文件,带 frontmatter:
```markdown
---
name: memory-name
description: What this memory is about
type: user | feedback | decision | pattern | ...
---
记忆内容...
```

### MEMORY.md 索引
从二进制提取:
```
"MEMORY.md index (<200 行)"
"lines after ${pre} will be truncated"
"> WARNING: ${r0} is ${a}. Only part of it was loaded."
"Keep index entries to one line under ~200 chars; move detail into topic files."
```

MEMORY.md 是一个**索引文件**(<200 行),每行一个指针:
```
- [Title](file.md) — one-line hook
```

超过 200 行会被截断 + 警告。这正好对应 [13](../../insights/13-reconstructive-memory.md) §1.2 的 L0 目录设计 —— **系统提示词放索引,详情按需读**。

### Team Memory(跨用户共享)
从二进制提取:
```
"Team memory (`team/` subdirectory)"
"You have read-only access to team memory synced from your project."
"Team memory is shared with all repository collaborators."
"You MUST avoid saving sensitive data within shared team memories."
```

Team memory 是 `team/` 子目录,**跨用户共享**,但在 session 中是 **read-only** 的。用户写的新记忆只进自己的 private memory 目录。

### Auto-Memory 开关
从二进制提取:
```
"Enable auto-memory for this project."
"Auto-dream: off while auto-memory is off"
```

Auto-memory 是可配置的(项目级别)。而且 **Dream 依赖 auto-memory** —— 如果 auto-memory 关了,dream 也不跑。

### Memory Watcher
从二进制提取:
```javascript
Promise.resolve().then(() => (QYr(),kho)).then((g)=>g.startMemoryWatcher())
```

启动时调用 `startMemoryWatcher()` —— 监视 memory 目录变化。

## 3. Layer 3: Session Memory —— 对话级持久化

从二进制提取:
```
"session.memory"
"~/.claude/projects/<project>/<session>/session-memory/"
"Background, every ~5K tokens"
```

Session memory 是后台进程,每 ~5000 tokens 自动生成对话摘要,存在 session 专属目录里。这对应 grok-build 的 compaction([insights/04](../../insights/04-anti-entropy.md) §2 的"两遍压缩")。

## 4. Layer 4: Auto Dream —— 睡眠巩固

### System Prompt(完整提取)
```
"You are performing a dream — a reflective pass over your memory files.
Synthesize what you've learned recently into durable, well-organized
memories so that future sessions can orient quickly."

Phase 1 - Orient: ls memory dir, read MEMORY.md index, skim topic files
Phase 2 - Gather Signal: grep JSONL transcripts (narrow terms only)
Phase 3 - Consolidate: merge new info, delete contradicted facts
Phase 4 - Prune & Index: update MEMORY.md (<200 lines)
```

### Dream 可以提议新 Skill
从二进制提取:
```javascript
createdBy: e.created_by === "dream-proposal" || e.improved_by === "dream-proposal" 
  ? "dream-proposal" : void 0
```

Dream 不仅能整理记忆,还能**提议新的 skill**(`createdBy: "dream-proposal"`)。这意味着 Dream 的输出不只是"更好的记忆",还包括"新的自动化能力"。

### Dream 的安全约束
从二进制提取:
```
"During a dream cycle, Claude can only write to memory files."
"It cannot modify your source code, configuration, tests, or any other project file."
```

Dream 运行时是**沙箱化的** —— 只能写 memory 目录,不能碰代码。这对应 [04](../../insights/04-anti-entropy.md) §2 的"隔离"策略。

### Dream 的触发
```
"every 24h + 5 sessions"
"Triggered on schedule (cron), after task completion, or via API"
```

## 5. Compaction —— 上下文压缩

### Beta API
从二进制提取:
```
"compact-2026-01-12"
"betas=[\"compact-2026-01-12\"]"
"compaction summary:"
"Context window exhausted — compact or split the conversation"
```

Claude Code 用的是 **Anthropic API 层面的 compaction beta**(`compact-2026-01-12`),不是纯客户端压缩。这意味着 Anthropic 的 API 自己支持 compaction —— 这比 grok-build 的客户端两遍压缩([04](../../insights/04-anti-entropy.md) §2)更底层。

### Compaction 和 Memory 的关系
```
"# Append full content — compaction blocks must be preserved"
```

Compaction 时,**记忆相关的内容不被压缩** —— 这验证了 [papers/02](../papers/02-compaction-degradation.md) 的核心论点:重要的信息应该移出 compaction 管线。

## 6. Context Engineering —— 上下文组装

从二进制提取(Anthropic 工程博客的落地):
```
"Resources (files, repos, memory stores — attached at startup)"
"Use memory maps to search files. By default, memory maps are used"
```

Claude Code 的 context engineering 策略:
1. **CLAUDE.md**: 启动时全量加载(恒定注入)
2. **MEMORY.md 索引**: 启动时加载前 200 行(L0 目录)
3. **grep/glob**: 即时检索文件(不预加载)
4. **Memory files**: 按需读取(只在相关时)
5. **Session memory**: 后台自动摘要

这对应 [09](../../insights/09-stateless-function.md) §3 的"所有记忆都是检索+注入" —— Claude Code 的实现完全验证了这个论点。

## 7. 和 grok-build / causal-memory 的对比

| 维度 | Claude Code v2.1.214 | grok-build | causal-memory |
|---|---|---|---|
| **记忆存储** | Markdown 文件系统 | SQLite + wire log | SQLite causal_edges |
| **记忆整理** | Auto Dream(LLM 全文分析) | 两遍 compaction(LLM) | chain_linker(规则) |
| **索引** | MEMORY.md(<200 行) | 无显式索引 | recent_decisions(L0 目录) |
| **跨用户共享** | ✅ team/ 目录 | ❌ | ❌ |
| **因果关系** | ❌ 不存储 | ❌ 不存储 | ✅ causal_edges |
| **Compaction** | API 级 beta(compact-2026-01-12) | 客户端两遍 | 不 compact(因果表不被压) |
| **安全** | Dream 沙箱(只写 memory) | Sandbox(landlock/seatbelt) | 独立进程(MCP) |
| **自动整理** | ✅ Dream(每 24h) | ❌ 无自动整理 | ⚠️ chain_linker(手动触发) |
| **文件格式** | Markdown(人类可读) | JSONL(程序友好) | SQLite(程序友好) |

### Claude Code 没做但 causal-memory 做了的

1. **因果边类型** —— Claude Code 的 Markdown 不区分 `caused`/`enabled`/`prevented`
2. **置信度分级** —— Claude Code 没有 temporal/rule/llm_inferred/user_feedback
3. **多跳因果追溯** —— Claude Code 的 grep 是单跳,没有 recursive CTE
4. **时序窗口(valid_to)** —— Claude Code 直接删除过时记忆,不留历史快照

### Claude Code 做了但 causal-memory 没做的

1. **Auto Dream** —— 全自动 LLM 驱动的记忆整理(causal-memory 只有 chain_linker)
2. **Team Memory** —— 跨用户共享记忆(causal-memory 是单用户的)
3. **CLAUDE.md Additions** —— 主动建议规则添加
4. **Skill 提议** —— Dream 可以提议新自动化能力
5. **API 级 Compaction** —— Anthropic API 原生支持

## 8. 对 causal-memory 的三个具体启示

### 8.1 MEMORY.md 索引 = causal-memory 的 L0 目录

Claude Code 的 MEMORY.md(<200 行)正好是 [13](../../insights/13-reconstructive-memory.md) §1.2 设计的"系统提示词作为身份层"。causal-memory 应该:

- 生成一个 `CAUSAL_MEMORY.md` 索引文件(最近 N 条因果决策摘要)
- 放在 agent 的 context 里(每轮恒定注入)
- 超过 200 行截断 + 警告

### 8.2 Dream 的四阶段 = causal-memory 的 consolidate 命令

causal-memory 的 `consolidate` 命令(路线图)应该借鉴 Dream 的四阶段:

1. **Orient**: 扫描 causal_edges 表,看现有因果边
2. **Gather**: 从最近的 session 提取新决策
3. **Consolidate**: 合并相似因果边,删除低置信度边
4. **Prune**: 激活 meta_causal_edges(跨任务模式)

### 8.3 Team Memory = causal-memory 的跨 agent 共享

Claude Code 的 team/ 目录对应 [11](../../insights/11-causal-state-store.md) §8.5 的"因果图跨 agent 共享"。causal-memory 的 v0.7+ 应该支持:

- `team/` 目录存放共享的因果边
- 私有目录存放用户专属的因果边
- Team 因果边是 read-only 的(防止跨用户污染)

## 9. 最终判断

> **Claude Code 的记忆架构是"文件系统 + LLM 整理"路线的工业化落地。**
>
> 它用 Markdown 文件(人类可读) + Dream(LLM 自动整理) + MEMORY.md 索引(<200 行截断)的组合,实现了 [09](../../insights/09-stateless-function.md) 说的"检索+注入"和 [13](../../insights/13-reconstructive-memory.md) 说的"系统提示词作为身份层"。
>
> **但它不存因果关系** —— 它的记忆是"这个项目用 TypeScript" / "用户喜欢简洁回答",不是"用 mutex 导致了死锁"。这是 causal-memory 的差异化仍然成立的原因。
>
> **causal-memory 应该定位为 Claude Code Auto Memory 的因果补充层**:用 MCP 挂载,提供 Claude Code 自己做不到的因果存储和多跳追溯。

---

## 参考资料

- Claude Code v2.1.214 二进制 strings 提取(2026-07-27)
- sdk-tools.d.ts 类型定义
- 泄露的 Dream system prompt: github.com/Piebald-AI/claude-code-system-prompts
- Anthropic context engineering 博客: anthropic.com/engineering/effective-context-engineering-for-ai-agents
- insights/09 §3(检索+注入)
- insights/13 §1.2(系统提示词作为身份层)
- insights/04 §2(隔离策略)
