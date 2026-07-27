# Claude Code 上下文系统拆解

> 本篇聚焦 Claude Code 的**上下文管理系统** —— context window 是怎么组装、监控、压缩、回退的。
> 记忆系统(四层架构)已在 [01-memory-context.md](01-memory-context.md) 覆盖,本篇不重复。
>
> 数据来源:CHANGELOG.md(477KB,完整版本历史)+ sdk-tools.d.ts + 二进制 strings 提取。
>
> 拆解版本: v2.1.214

## 0. 上下文管理的五个子系统

```
┌──────────────────────────────────────────────────────────┐
│                    上下文生命周期                          │
│                                                          │
│  ① 上下文组装(Context Assembly)                         │
│     ↓                                                    │
│  ② 上下文监控(Context Monitoring / /context)             │
│     ↓                                                    │
│  ③ 自动压缩(Auto-Compact)                                │
│     ↓                                                    │
│  ④ 手动压缩(/compact)                                    │
│     ↓                                                    │
│  ⑤ 上下文回退(/rewind + /fork)                           │
└──────────────────────────────────────────────────────────┘
```

## 1. 上下文组装(Context Assembly)

### 每次推理时,context 是这样组装的

从 CHANGELOG 和 binary strings 推断的组装顺序(后面的覆盖前面的优先级):

```
┌───────────────────────────────────────────────┐
│ System Prompt(恒定,不随轮次变化)               │
│  ├── 基础系统提示词(Claude Code 的核心行为)     │
│  ├── CLAUDE.md(全量加载,项目级规则)            │
│  ├── MEMORY.md 索引(前 200 行 / 25KB)          │
│  ├── 工具定义(Bash, Read, Write, Edit, ...)    │
│  ├── MCP 工具定义(动态加载)                     │
│  ├── Skill 定义(动态加载)                       │
│  └── Agent 定义(子 agent 的角色和工具)           │
├───────────────────────────────────────────────┤
│ 消息历史(Conversation History)                 │
│  ├── User messages                             │
│  ├── Assistant messages(含 thinking + text)    │
│  ├── Tool calls + Tool results                 │
│  └── Session memory 摘要(每 ~5K tokens 自动)    │
├───────────────────────────────────────────────┤
│ 当前用户输入                                    │
└───────────────────────────────────────────────┘
```

### 关键发现:CLAUDE.md 是"too long"感知的

CHANGELOG:
> "The 'CLAUDE.md is too long' warning threshold now scales with the model's context window"

CLAUDE.md 的长度警告**随模型的 context window 动态调整** —— 200K 模型和 1M 模型的阈值不同。这意味着 Anthropic 在**系统提示词层面就做了 context budget 管理**。

### 关键发现:MEMORY.md 有双重限制

CHANGELOG:
> "MEMORY.md index now truncates at 25KB as well as 200 lines"

MEMORY.md 索引有**两个限制**:200 行 AND 25KB。先到哪个就截断。这防止了"每行超长导致单文件过大"的问题。

### 关键发现:工具定义也消耗 context

CHANGELOG:
> "Reduced UI stutter when compaction triggers on large sessions"
> "Fixed prompt cache bust when an MCP server with instructions connects after the first turn"
> "Improved prompt cache hit rate ... by removing dynamic content from tool descriptions"

工具定义(MCP tools + skills + agents)的 schema **计入 context 消耗**。而且 MCP server 连接时如果带了 `instructions` 字段,会**打破 prompt cache**(因为 system prompt 变了)。Claude Code 专门优化了这一点 —— 从工具描述里移除动态内容来提高缓存命中率。

## 2. 上下文监控(/context 命令)

### /context 做什么

CHANGELOG 揭示了 `/context` 命令的功能演进:

| 版本 | 功能 |
|---|---|
| 早期 | 显示 token 使用量 |
| 2.1.74 | "Added actionable suggestions to `/context` — identifies context-heavy tools, memory bloat, and capacity warnings with specific optimization tips" |
| 后续 | "per-skill token estimates now account for the model's tokenizer" |
| 后续 | "shows the providing plugin's name for plugin-sourced skills" |
| 修复 | "Fixed `/context` dumping its rendered ASCII visualization grid into the conversation, wasting ~1.6k tokens per call" |

`/context` 是一个**上下文诊断工具** —— 它不只显示"用了多少 token",还:
- 按工具/skill 分解 token 消耗
- 识别"哪些工具最吃 context"
- 识别"memory 是否膨胀"
- 给出具体的优化建议

### 对 grok-build / causal-memory 的启示

grok-build 和 causal-memory 都没有 `/context` 这样的诊断工具。**causal-memory 应该加一个 `causal-memory stats` 命令**,显示:
- 因果边总数 + 按 task_tag 分布
- 搜索返回的平均 token 量
- 占用 context 的比例

## 3. 自动压缩(Auto-Compact)

### 触发机制

CHANGELOG:
> "Auto-compact in auto mode now displays `auto`"
> "Fixed auto-compact never triggering for Claude Opus 4.8 on Bedrock"
> "Fixed autocompact thrash loop — now detects when context refills to the limit immediately after compacting three times in a row and stops with an actionable error"

Auto-compact 是**自动触发**的 —— 当 context 接近模型的 context window 上限时。关键细节:

1. **阈值随模型动态调整** —— 200K 模型和 1M 模型的触发点不同
2. **有防抖机制** —— 如果 compact 后 context 立刻又满了(连续 3 次),停止 compact 并报错,不无限循环
3. **有熔断器** —— 连续失败 3 次后停止(circuit breaker)

### Compaction 的 API 级实现

从二进制提取:
```
"compact-2026-01-12"
"betas=[compact-2026-01-12]"
```

Claude Code 的 compaction **不是纯客户端实现** —— 它用 Anthropic API 的 `compact-2026-01-12` beta。这意味着:
- 压缩逻辑有一部分在 Anthropic 的服务器上
- 不是简单的"客户端发一个 summarize 请求"
- 可能利用了服务端对 context 的直接访问(效率更高)

对比 grok-build:**grok-build 的两遍压缩是纯客户端的**([04](../../insights/04-anti-entropy.md) §2)。Claude Code 的方案更底层。

### Compaction 和 Prompt Cache 的关系

CHANGELOG 揭示了大量关于 prompt cache 和 compaction 交互的细节:

| 发现 | 来源 |
|---|---|
| "Improved compaction to preserve images in the summarizer request, allowing prompt cache reuse" | 压缩时保留图片 → 缓存可复用 |
| "Fixed prompt cache misses in long sessions caused by tool schema bytes changing mid-session" | 工具 schema 变化 → 缓存失效 |
| "Reduced input token costs up to 12x" (SDK query 的缓存修复) | 缓存修复后 12x 降本 |
| "ENABLE_PROMPT_CACHING_1H env var to opt into 1-hour prompt cache TTL" | 可选 1 小时缓存(默认 5 分钟) |
| "Pro users now see a footer hint when returning to a session after the prompt cache has expired" | 缓存过期提示 |

**Prompt cache 是 Claude Code 上下文管理的隐藏维度** —— 它不是直接管理 context 大小,而是通过缓存减少重复 context 的计算成本。这是一个 grok-build 没有的优化层。

## 4. 手动压缩(/compact)

CHANGELOG:
> "/compact" 命令存在(多处引用)
> "Fixed `/context` reporting stale pre-compact token usage after compacting from the message picker"
> "a failed `/compact` displays as an error"

用户可以手动触发压缩(`/compact`)。关键细节:
- 压缩后 `/context` 显示的 token 使用量会更新
- 压缩可能失败(API 错误),会显示为 error
- 压缩可以在 message picker(消息选择器)中触发

## 5. 上下文回退(/rewind + /fork)

### /rewind —— 上下文时间旅行

CHANGELOG:
> "Esc-Esc at an idle prompt opening the rewind picker"
> "`/rewind` no longer restores or deletes files through symlinks or hard links"
> "[VSCode] Esc-twice (or `/rewind`) to open a keyboard-navigable rewind picker"

`/rewind` 是**上下文级的时间旅行** —— 可以回到之前某个对话点。Esc-Esc 快捷键打开一个可导航的 picker。

### /fork —— 上下文分叉

CHANGELOG:
> "Improved the `/fork` confirmation to one line with the new session's name"
> "SessionStart hooks to report source `\"fork\"` when a session begins as a fork"
> "Fixed fork-session lineage being lost after compaction in headless and SDK sessions"

`/fork` 创建当前对话的一个**分叉副本** —— 从当前点开始新的 session,不影响原 session。

### 对 insights 的影响

`/rewind` 和 `/fork` 对应 [04](../../insights/04-anti-entropy.md) §2 的**恢复策略** —— "回到已知好的状态"。但 Claude Code 的实现比 grok-build 的 wire restore 更轻量:
- grok-build: 重放 Op 序列重建状态(重计算)
- Claude Code: 直接截断消息历史到某个点(O(1))

## 6. 1M Context 模型的特殊处理

CHANGELOG 揭示了大量 1M context 模型(Sonnet 5, Opus 5)的特殊逻辑:

| 发现 | 含义 |
|---|---|
| "Fixed Opus 4.7 sessions showing inflated `/context` percentages and autocompacting too early — Claude Code was computing against a 200K context window instead of Opus 4.7's native 1M" | context window 大小是**模型感知**的 |
| "Fixed sessions on 1M-context models with a smaller autocompact window being falsely blocked with 'Prompt is too long'" | 1M 模型有自己的 autocompact 窗口 |
| "The 'CLAUDE.md is too long' warning threshold now scales with the model's context window" | 系统提示词预算也随模型缩放 |

**对 [09](../../insights/09-stateless-function.md) §4 三堵墙的影响**:

之前说长上下文撞三堵墙(O(n²) 注意力、lost in the middle、经济性)。但 Claude Code 的 1M context 支持 + 模型感知的 autocompact 窗口说明:**Anthropic 正在系统性地解决长上下文的工程问题**。[09](../../insights/09-stateless-function.md) §4 的"墙"可能在移动,不是在消失。

## 7. 完整的上下文 budget 分配(推断)

基于以上发现,Claude Code 的 context window budget 大致是:

```
1M token context window (Opus 5 / Sonnet 5)
├── System Prompt (~10-30K tokens)
│   ├── 基础 system prompt (~5K)
│   ├── CLAUDE.md (~2-10K, 动态阈值)
│   ├── MEMORY.md 索引 (~5K, 200行/25KB)
│   ├── 工具定义 (~5-15K, 含 MCP + skills)
│   └── Agent 定义 (~1-5K)
├── Prompt Cache 前缀 (~95%+ 命中时几乎免费)
├── 消息历史 (剩余空间, ~950K+)
│   ├── User + Assistant 消息
│   ├── Tool calls + results (最耗 token)
│   └── Session memory 摘要
├── Auto-compact 触发阈值 (~80-90% context window)
└── 当前用户输入
```

**关键洞察**:System prompt + 工具定义可能占 10-30K tokens —— 这不是小数目。在 200K 模型上是 5-15%,在 1M 模型上是 1-3%。**这也是为什么 MEMORY.md 有 200 行限制** —— 它是 system prompt 的一部分,直接吃 context。

## 8. 和 grok-build / causal-memory 的对比

| 维度 | Claude Code | grok-build | causal-memory |
|---|---|---|---|
| **压缩** | API 纆 beta(compact-2026-01-12) | 客户端两遍 | 不压缩(因果表不被压) |
| **压缩防抖** | ✅ 3次循环检测 + 熔断 | ❌ | N/A |
| **上下文诊断** | ✅ /context(分工具分解) | ❌ | ❌ |
| **上下文回退** | ✅ /rewind(O(1)截断) | ✅ wire restore(重计算) | ❌ |
| **上下文分叉** | ✅ /fork | ❌ | ❌ |
| **Prompt Cache** | ✅ 1h TTL + 缓存感知压缩 | ❌ | N/A |
| **模型感知** | ✅ 200K vs 1M 动态阈值 | ❌ | ❌ |
| **系统提示词预算** | ✅ CLAUDE.md 动态阈值 | ❌ | ❌ |

### Claude Code 的上下文管理比 grok-build 成熟很多

grok-build 的 compaction 是纯客户端的([04](../../insights/04-anti-entropy.md) §2),没有:
- API 级压缩支持
- Prompt cache 优化
- 模型感知的阈值
- 压缩防抖 / 熔断器
- 上下文诊断工具

Claude Code 的上下文管理是一个**工业级的系统**,不只是"压一下 context"。

## 9. 对 causal-memory 的启示

### 9.1 causal-memory 的输出必须考虑 context budget

causal-memory 的 `search_causal` 返回结果会**占用 agent 的 context window**。如果返回 10 条因果边 × 100 tokens = 1000 tokens,在 200K 模型上占 0.5%,但在有其他工具定义的情况下可能更紧。

**建议**:search_causal 加一个 `max_tokens` 参数,限制返回内容的总 token 量(类似 Claude Code 的 MEMORY.md 200 行限制)。

### 9.2 causal-memory 应该加 stats 命令

类似 `/context`,causal-memory 应该有 `causal-memory stats` 显示:
- 因果边总数
- 按 task_tag 分布
- 搜索返回的平均 token 量
- 占用 context 的估算比例

### 9.3 因果表是 prompt cache 友好的

causal-memory 的 SQLite 因果表**不随轮次变化**(只有 extract/link 时才写)。这意味着因果边的查询结果可以被 prompt cache 命中 —— 如果 agent 在多轮里搜同样的 task_tag,缓存会让第二次几乎免费。

---

## 参考资料

- Claude Code CHANGELOG.md(477KB,v2.0 → v2.1.214 完整版本历史)
- sdk-tools.d.ts(v2.1.214 类型定义)
- 二进制 strings 提取(compact-2026-01-12 beta API)
- [01-memory-context.md](01-memory-context.md)(四层记忆架构)
- insights/04 §2(反退化策略:压缩/隔离/验证/恢复/约束)
- insights/09 §4(长上下文三堵墙)
