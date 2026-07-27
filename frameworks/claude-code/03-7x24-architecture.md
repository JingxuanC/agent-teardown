# Claude Code 7×24 长时运行架构拆解

> 本篇拆解 Claude Code 的**长时运行 / 7×24 能力** —— background sessions、managed agents、scheduled tasks、remote triggers、 dreaming。
>
> 数据来源:CHANGELOG.md(v2.0 → v2.1.214)+ sdk-tools.d.ts + 二进制 strings + Code with Claude 2026 大会信息。
>
> 对应 insights: [05-agi-7x24.md](../../insights/05-agi-7x24.md)(7×24 的五种死法 + 五种新能力)

## 0. Anthropic 的 7×24 架构全景

```
┌───────────────────────────────────────────────────────────┐
│                  Claude Code 7×24 架构                     │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Foreground  │  │ Background   │  │ Managed Agents  │   │
│  │ Session     │←→│ Daemon       │  │ (Claude Platform)│  │
│  │ (TUI)       │  │ (local)      │  │ (cloud)         │   │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘   │
│         │                │                    │            │
│         │    ┌───────────┼────────────┐       │            │
│         │    │           │            │       │            │
│         ▼    ▼           ▼            ▼       ▼            │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐    │
│  │ Worktree │ │ Cron /   │ │ Scheduled  │ │ Remote   │    │
│  │ Pool     │ │ Loop     │ │ Wakeup     │ │ Trigger  │    │
│  │ (隔离)   │ │ (定时)   │ │ (自调度)   │ │ (外部触发)│    │
│  └──────────┘ └──────────┘ └────────────┘ └──────────┘    │
│                                                           │
│  ┌──────────────────────────────────────────────────┐     │
│  │              Auto Dream (离线巩固)                 │     │
│  │  每 24h / 5 sessions → 整理 memory + 提议 skill   │     │
│  └──────────────────────────────────────────────────┘     │
│                                                           │
│  ┌──────────────────────────────────────────────────┐     │
│  │              安全约束层                           │     │
│  │  • 预算上限 (--max-budget-usd)                   │     │
│  │  • 并发子 agent 上限 (20)                        │     │
│  │  • 每 session 子 agent 上限 (200)                │     │
│  │  • WebSearch 上限 (200/session)                  │     │
│  │  • 子 agent 嵌套深度 (默认禁止)                   │     │
│  │  • Dream 沙箱 (只写 memory 目录)                 │     │
│  └──────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────┘
```

## 1. Background Sessions —— 本地 7×24

### 架构:Daemon + Worker

从 CHANGELOG 提取的关键信息:

```
"background daemon"
"daemon.lock"
"daemon handover"
"background worker"
"background sessions parked with ← or /background"
```

Claude Code 的 background session 是一个 **daemon + worker** 架构:
- **Daemon**:常驻进程,管理所有 background session 的生命周期
- **Worker**:每个 background session 是一个独立 worker 进程
- **Daemon lock**:防止多个 daemon 同时运行(`daemon.lock` 文件)
- **Daemon handover**:版本升级时的 daemon 切换(按 build timestamp 判断新旧)

### 关键工程问题(CHANGELOG 里大量修复)

| 问题 | 修复 | 对应 insights |
|---|---|---|
| sleep/wake 后 session 卡死 | "detects clock jumps instead of treating them as elapsed idle time" | [05](../../insights/05-agi-7x24.md) 死法③(状态日志无限增长) |
| App Nap 导致 false-positive stall | "Fixed false-positive worker-stall detection storm after host sleep or macOS App Nap" | [05](../../insights/05-agi-7x24.md) 死法⑤(doom loop) |
| OAuth token 过期 | "Fixed sessions going stale in long-running sessions after the OAuth token rotates" | [05](../../insights/05-agi-7x24.md) 死法②(成本) |
| cloud session container 重启 | "cloud sessions dropping the in-flight message when the session's container restarts mid-turn — the interrupted turn now re-runs on resume" | [05](../../insights/05-agi-7x24.md) 死法①(compaction 传话游戏) |
| daemon 被替换后 worker 崩溃 | "Fixed displaced background daemon deleting its successor's control socket" | [04](../../insights/04-anti-entropy.md) §2 恢复策略 |

**这些全是 7×24 的真实工程挑战** —— Anthropic 不是在做"概念验证",是在解决生产环境的真实问题。对应 [05](../../insights/05-agi-7x24.md) 说的"五种死法",每一种 Anthropic 都在 CHANGELOG 里修过。

### /background 和 /fork

```
"/background or ←" → park session to background
"/fork" → copy conversation into a new background session
```

用户可以把当前 session 推到后台(`←` 或 `/background`),然后继续做别的事。`/fork` 创建一个当前对话的分叉,分叉自动成为 background session。

## 2. Managed Agents —— 云端 7×24

### Claude Platform

从 CHANGELOG + 大会信息:

```
"Managed Agents"
"Claude Platform"
"cloud session"
"remote session"
"remote worker"
```

Managed Agents 是 Anthropic **云端的 7×24 agent 运行环境**:
- Agent 跑在 Anthropic 的云上(Claude Platform)
- 不依赖用户的本地机器 —— 用户关机了 agent 继续跑
- 支持容器重启恢复("container restarts mid-turn — re-runs on resume")
- 支持 AWS 集成("Claude Platform on AWS")

### Remote Control

```
"Remote Control sessions"
"Remote Control clients"
"session ready push notification"
```

Remote Control 允许从手机/网页**远程控制** agent session —— 连接后可以看到 pending permission prompt、发送消息。

### 对 [05](../../insights/05-agi-7x24.md) 的影响

Managed Agents 是 [05](../../insights/05-agi-7x24.md) §4 预测的"OpenAI Codex 已经实现了部分能力"的 **Anthropic 回应**。Anthropic 也在做云端 7×24 agent 运行环境。

## 3. 定时任务:Cron + Loop + ScheduleWakeup

这是 Claude Code 最有意思的 7×24 工具链。从 sdk-tools.d.ts 提取的三个工具:

### 3.1 CronCreate —— 标准 cron 表达式定时

```typescript
interface CronCreateInput {
  cron: string;          // 标准 5 字段 cron 表达式
  prompt: string;        // 每次触发时执行的 prompt
  recurring?: boolean;   // true=循环(默认), false=一次性
  durable?: boolean;     // true=持久化到 .claude/scheduled_tasks.json
}
```

Agent 可以**自己创建 cron 任务** —— 设定时间表,到点了自动跑一个 prompt。而且 `durable: true` 可以让任务**跨 session 存活**(持久化到文件)。

### 3.2 ScheduleWakeup —— 动态自调度

```typescript
interface ScheduleWakeupInput {
  delaySeconds?: number;  // 60-3600 秒后唤醒
  reason?: string;        // 给用户看的解释
  prompt?: string;        // 唤醒时执行的 /loop 输入
  stop?: boolean;         // true=停止循环
}
```

这是**动态自调度** —— agent 不用预设 cron 表达式,而是说"60 秒后再跑一次"。每次唤醒时 agent 重新决定下一次的 delay。这比 cron 更灵活 —— agent 可以根据当前状态调整节奏。

`<<autonomous-loop-dynamic>>` 是一个特殊 sentinel —— 表示"这是自主循环,没有用户 prompt"。

### 3.3 Monitor —— 持续监控

```typescript
interface MonitorInput {
  description: string;      // 给用户看的监控描述
  timeout_ms: number;       // 超时(默认 5 分钟,最大 1 小时)
  persistent: boolean;      // true=session 生命周期内持续运行
  command: string;          // shell 命令,每行 stdout 是一个事件
}
```

Monitor 是一个**持续监控工具** —— 运行一个 shell 命令,每行 stdout 触发一个事件。`persistent: true` 让它跑整个 session 生命周期。这就是 grok-build 的 `monitor` 工具的 Claude Code 版本。

### 对 [05](../../insights/05-agi-7x24.md) 的影响

这三个工具合在一起,构成了 [05](../../insights/05-agi-7x24.md) §3.4 说的"自适应验证"的雏形:
- Cron = 固定时间表(低频)
- ScheduleWakeup = 动态自调度(中频)
- Monitor = 持续事件流(高频)

而且 ScheduleWakeup 的 `reason` 字段 + `<<autonomous-loop-dynamic>>` sentinel 说明 Anthropic 在认真地做**agent 自主循环** —— 不是简单的 cron,是 agent 自己决定"什么时候再跑"。

## 4. Auto Dream —— 离线巩固

已在 [01-memory-context.md](01-memory-context.md) 详细拆解。这里补充 7×24 视角:

```
"every 24h + 5 sessions"
"Triggered on schedule (cron), after task completion, or via API"
"Reviews recent session transcripts + existing memory store"
"Produces a diff of updates: merges duplicates, removes stale/outdated entries,
 verifies facts, surfaces new insights"
```

Dream 是 7×24 架构的**离线巩固层** —— 对应人脑的睡眠。它的触发是双条件的(24h 或 5 sessions),先到先触发。

### Dream 的 7×24 含义

Dream 解决了 [05](../../insights/05-agi-7x24.md) 死法④(身份漂移)—— 通过定期整理 memory,防止记忆随时间退化成噪音。这是 [05](../../insights/05-agi-7x24.md) §3.2 预测的"Agent 需要睡眠巩固"的工业化实现。

## 5. 安全约束层 —— 防止 7×24 失控

7×24 agent 最大的风险是**失控** —— 无限循环、无限花费、无限 fan-out。Claude Code 的约束:

| 约束 | 默认值 | 环境变量 | 作用 |
|---|---|---|---|
| 并发子 agent 上限 | 20 | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | 防止 fan-out 爆炸 |
| 每 session 子 agent 上限 | 200 | `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` | 防止 delegation 循环 |
| WebSearch 上限 | 200 | `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` | 防止搜索循环 |
| 子 agent 嵌套 | 禁止 | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | 防止递归爆炸 |
| 预算上限 | 可配置 | `--max-budget-usd` | 防止花费失控 |
| Dream 沙箱 | 只写 memory | 硬编码 | 防止 Dream 修改代码 |
| Cron 自动过期 | 7 天 | 硬编码 | 防止僵尸任务 |
| ScheduleWakeup 范围 | 60-3600s | 硬编码 | 防止过快或过慢循环 |
| MCP 自动后台 | 2 分钟 | `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` | 防止 MCP 阻塞 |
| Auto-compact 熔断 | 3 次失败 | 硬编码 | 防止压缩死循环 |

**这对应 [04](../../insights/04-anti-entropy.md) §2 的"约束"策略** —— 在系统开始退化前就限制行为空间。而且 Anthropic 做得比 grok-build 更细致 —— grok-build 只有 `max_steps` 和 `budget`,Claude Code 有 10 个不同维度的约束。

### autocompact 熔断器的详细实现

CHANGELOG:
> "Fixed autocompact thrash loop — now detects when context refills to the limit immediately after compacting three times in a row and stops with an actionable error instead of burning API calls"
> "Fixed auto-compaction retrying indefinitely after consecutive failures — a circuit breaker now stops after 3 attempts"

这正是 [05](../../insights/05-agi-7x24.md) 死法⑤(doom loop)的防护:
- **Thrash 检测**:compact 后 context 立刻又满 → 连续 3 次 → 停止 + 报错
- **熔断器**:连续 3 次失败 → 停止重试

## 6. 对 [05-agi-7x24.md](../../insights/05-agi-7x24.md) 的系统性对照

[05](../../insights/05-agi-7x24.md) 预测的五种 7×24 死法 vs Anthropic 的实际解决:

| 死法 | [05] 预测 | Claude Code 的实际解决 | 状态 |
|---|---|---|---|
| ① Compaction 传话游戏 | k 次有损压缩累积失真 | API 级 compact-2026-01-12 + Dream 整理 | ⚠️ 部分解决(API 压缩质量更高,但仍然有损) |
| ② Token 成本爆炸 | 反熵操作花钱 | `--max-budget-usd` + prompt cache(1h TTL) | ✅ 有预算控制 |
| ③ 状态日志无限增长 | wire log / SQLite 爆 | Dream 定期 prune + memory 文件整理 | ⚠️ 部分解决(Dream 清理 memory,但不清理 transcript) |
| ④ 身份漂移 | compaction 断裂因果链 | CLAUDE.md(恒定)+ MEMORY.md(索引)+ Dream(整理) | ⚠️ 文本层面有缓解,但没有因果链 |
| ⑤ Doom loop | 行为锁定 | autocompact 熔断 + 并发上限 + 搜索上限 | ✅ 有多维度防护 |

[05](../../insights/05-agi-7x24.md) 预测的五种新能力 vs Anthropic 的实际实现:

| 新能力 | [05] 预测 | Claude Code 的实际实现 | 状态 |
|---|---|---|---|
| ① 多尺度记忆层级 | 秒/分/时/天/周/月 6 层 | CLAUDE.md + Auto Memory + Session Memory + Dream = 4 层 | ⚠️ 4 层,没有周/月级 |
| ② 离线巩固(Sleep) | 16h 工作 + 4h 睡眠 + 4h 深度 | Dream(每 24h/5sessions) | ⚠️ 有基础版,没有分阶段 |
| ③ 自演化 Prompt | 基于经验修改 system prompt | CLAUDE.md additions(Dream 提议)+ skill 提议 | ✅ 有(但不是修改 system prompt,是提议新规则) |
| ④ 自适应验证 | 按风险分级验证 | auto mode + permission policy + safety classifier | ⚠️ 有基础版 |
| ⑤ 成本意识 | 预算管理 + 成本归因 | `--max-budget-usd` + `/context` token 分解 | ✅ 有 |

## 7. causal-memory 在 Anthropic 7×24 架构里的位置

```
Anthropic 7×24 架构
├── 记忆层: CLAUDE.md + Auto Memory + Session Memory + Dream
├── 上下文层: Compaction + /context + /rewind + prompt cache
├── 调度层: Background Daemon + Cron + ScheduleWakeup + Monitor
├── 云端层: Managed Agents + Remote Control
├── 安全层: 10 个维度的约束 + 熔断器
└── ❌ 缺失: 因果记忆层 ← causal-memory 的位置
```

**Anthropic 的 7×24 架构缺的恰好是 causal-memory 做的事**:
- Dream 整理的是**文本记忆**(Markdown),不是**因果边**
- /rewind 是**时间旅行**(回到之前的状态),不是**因果追溯**(找到导致问题的决策)
- CLAUDE.md additions 是**规则提议**,不是**因果教训**

causal-memory 可以作为 Anthropic 7×24 架构的**因果补充层**:
- Dream 整理完文本记忆后,causal-memory 从中提取因果边
- /rewind 回到某个点时,causal-memory 提供那个点的因果上下文
- Background session 完成后,causal-memory 记录"这个 session 的决策导致了什么结果"

## 8. 最终判断

> **Anthropic 的 7×24 不是概念,是产品。**
>
> Background sessions + Managed Agents + Cron/ScheduleWakeup/Monitor + Dream + 10 维安全约束 —— 这是一个完整的、经过大量 bug 修复(CHANGELOG 477KB)的工业级 7×24 系统。
>
> [05](../../insights/05-agi-7x24.md) 预测的五种死法,Anthropic 每一种都遇到过并且修过(从 CHANGELOG 的 bug fix 可以看出)。五种新能力,Anthropic 实现了大部分(虽然不如预测的那么完整)。
>
> **causal-memory 的机会**:Anthropic 的 7×24 缺因果层。Dream 管文本记忆,不管因果。causal-memory 可以成为 Dream 的因果补充 —— 在 Dream 整理完文本后,提取因果边存入 SQLite,提供 trace_cause_chain 能力。

---

## 参考资料

- Claude Code CHANGELOG.md v2.0 → v2.1.214(477KB 完整版本历史)
- sdk-tools.d.ts(CronCreate / ScheduleWakeup / Monitor 类型定义)
- Code with Claude 2026: "Memory and dreaming for self learning agents"
- [01-memory-context.md](01-memory-context.md)(四层记忆 + Dream)
- [02-context-system.md](02-context-system.md)(上下文管理五子系统)
- [05-agi-7x24.md](../../insights/05-agi-7x24.md)(7×24 的五种死法 + 五种新能力)
