# Grok Build · 工具系统 + BM25 搜索 + Signals + Slash + 扩展系统 拆解

> 本篇合并五个中等模块(单独写太碎),覆盖 grok-build 剩余的所有核心子系统。

---

## ① 工具系统 + BM25 搜索(113K 行)

> 📁 `crates/codegen/xai-grok-tools/`(213 文件,113K 行) + `session/tool_index.rs`(2502 行)

### 工具规模

grok-build 的工具系统是**最大的 crate**(113K 行),包含:
- bash / terminal 执行
- 文件读写 / 搜索(grep/glob)
- 代码编辑(str-replace)
- computer use(控制鼠标键盘!)
- web fetch / search
- task(subagent)
- skills
- todo

### BM25 工具搜索

```rust
// tool_index.rs
//! Concrete ToolSearchIndex implementation using BM25.
//! Builds a BM25 index over registered MCP tools and searches it.
//! The index is rebuilt on each search call (sub-millisecond for tens
//! to low hundreds of tools).
```

**为什么需要搜索**:当 MCP server 很多(100+ 工具),LLM 的 tool 列表会爆炸。grok-build 建 **BM25 全文索引**让 LLM 能**搜索工具**(而不是看完整列表)。

**identifier 拆分**:支持 `__`(MCP 分隔符)、`_`(snake_case)、`-`(kebab-case)、camelCase 全部拆分成单词建索引。

**kimi-code 没有**:kimi-code 直接把所有工具发给 LLM(最多 100 个)。grok-build 用搜索引擎解决"工具太多"的问题。

---

## ② Signals 系统(3133 行,feedback 基础设施)

> 📁 `crates/codegen/xai-grok-shell/src/session/signals.rs`

### 作用

收集 **session 级运行信号**,用于决定"是否该问用户要 feedback"。

### 信号类型

```rust
pub struct ToolOutcome {
    // 每个工具的成功/失败统计
}

pub(crate) fn sample_rss_bytes() -> u64 {
    // 采样进程 RSS(getrusage)
}
```

- **推理延迟**:用 `TDigest` 做百分位统计(p50/p99)
- **工具成功率**:per-tool 的成功/失败 breakdown
- **内存使用**:`getrusage(RUSAGE_SELF)` 采样 RSS
- **token 消耗**:input/output 累计

### Actor 模式

```rust
//! Uses a channel-based actor pattern to avoid locks:
//! - SessionSignalsHandle is a cheap, cloneable sender
//! - SessionSignalsActor runs as a background task processing signal events
//! - Snapshots are requested via oneshot channels for async response
```

**无锁**:用 channel(actor 模式),不用 Mutex。多线程安全的信号收集。

### kimi-code 对比

kimi-code 有 telemetry(事件注册表 + track2),但没有这种"session 级 aggregate 信号用于 feedback 决策"的系统。grok-build 的 signals 更像是**运行时健康仪表盘**。

---

## ③ Slash Commands + Capability Gate(2649 行)

> 📁 `crates/codegen/xai-grok-shell/src/session/slash_commands.rs`

### Capability Gate

不是所有 slash 命令都可用,根据 session 的能力动态过滤:

```rust
pub(crate) enum BuiltinGate {
    AlwaysOn,        // 总是可用(compact / clear / help)
    Feedback,        // feedback 系统启用时
    Memory,          // memory backend 配置时
    MemoryConfigured, // memory 参数存在时(/memory 管理)
    Scheduler,       // scheduler_create 注册时
    Hooks,           // hook registry 加载时
    Plugins,         // plugin registry 加载时
    Goal,            // goal feature flag + update_goal 在工具集里
}
```

**kimi-code 的 slash 命令**是静态注册的,不根据能力过滤。grok-build 的设计更精细 —— 没有 memory backend 的 session 看不到 `/memory` 命令。

### 内置命令列表

包括:`/compact`、`/clear`、`/memory`、`/goal`、`/scheduler`、`/hooks`、`/plugins`、`/feedback` 等。

---

## ④ Interjection(中途插话)

> 📁 `crates/common/xai-interjection-core/`(320 行)

和 kimi-code 的 steer 对应。用户在 agent 工作中途发消息,被 buffer 起来,在 turn 边界注入。

```rust
pub use buffer::{FormattedInterjection, InterjectionBuffer, PendingInterjection, drain_formatted};
pub use format::{LARGE_PROMPT_THRESHOLD, format_interjection, user_query};
```

- **InterjectionBuffer**:缓存 pending 消息
- **FormattedInterjection**:格式化后的插话
- **LARGE_PROMPT_THRESHOLD**:大 prompt 的阈值(超过则特殊处理)

比 kimi-code 的 steer 简单(320 行 vs kimi-code 的几百行),但核心机制一样。

---

## ⑤ MCP + Hooks + Plugins + Memory 扩展系统

> 📁 `crates/codegen/xai-grok-mcp/`(10K 行) + `xai-grok-hooks/`(8.5K) + `xai-grok-plugin-marketplace/`(5.5K) + `xai-grok-memory/`(10K)

### MCP(和 kimi-code 类似)

```rust
// servers.rs(7538 行!)
```

支持 stdio / HTTP / SSE 三种 transport。和 kimi-code 的 MCP 系统结构类似(连接管理 + 工具注册 + OAuth)。

**差异**:grok-build 有 `mcp_dispatcher.rs`(1753 行)+ `mcp_restart.rs` + `managed_mcp.rs`,更精细的管理。

### Hooks(和 kimi-code 类似)

`xai-grok-hooks/`(8.5K 行):外部脚本扩展点。

### Plugin Marketplace

```rust
// xai-grok-plugin-marketplace(5502 行)
```

**kimi-code 没有 marketplace**!grok-build 有**插件市场** —— 可以从远程安装插件。

### Memory

```rust
// xai-grok-memory(9918 行)
```

**长期记忆系统** —— 跨 session 的知识存储。kimi-code 没有这个(每个 session 独立,不共享记忆)。grok-build 的 memory 让 agent 能**记住上次会话的结论**。

---

## ⑥ 其他模块速览

### Markdown + Mermaid(21K 行)

```
crates/codegen/xai-grok-markdown/
├── mermaid.rs(5237 行!)— 内置 Mermaid 图表渲染引擎
├── markdown-core/
```

**grok-build 在终端里渲染 Mermaid 图**!kimi-code 没有这个能力(只输出 mermaid 源码让 GitHub 渲染)。

### Voice(2802 行)

```
crates/codegen/xai-grok-voice/
```

**语音输入/输出**!kimi-code 没有语音支持。

### Auto Update(11K 行)

```
crates/codegen/xai-grok-update/src/auto_update.rs(4886 行)
```

**自动更新机制**(类似 VS Code 的后台更新)。kimi-code 靠 `uv tool upgrade` 手动更新。

### Computer Hub(4179 行)

```
crates/common/xai-computer-hub-core/
crates/common/xai-computer-hub-mcp-adapter/
crates/common/xai-computer-hub-sdk/
```

**Computer Use**(控制鼠标/键盘/屏幕)!让 agent 能操作 GUI 应用。kimi-code 没有这个。

### Crash Handler

```
crates/codegen/xai-crash-handler/
```

**崩溃处理 + 错误报告**。agent 崩溃时自动收集诊断信息。kimi-code 没有专门的 crash handler。

---

## 全面对比总结

| 模块 | kimi-code | grok-build | 谁更强 |
|---|---|---|---|
| **工具搜索** | 列表(≤100) | **BM25 全文搜索** | grok-build |
| **worktree** | 无 | **预创建池 + 原子 claim** | grok-build |
| **hunk 追踪** | 无 | **行级别** | grok-build |
| **signals** | telemetry | **session 级 aggregate + TDigest** | grok-build |
| **slash 命令** | 静态 | **Capability Gate 动态过滤** | grok-build |
| **插话** | steer(复杂) | interjection(简单) | kimi-code(更成熟) |
| **MCP** | 有 | 有(+ dispatcher + restart) | 持平 |
| **Hooks** | 有 | 有 | 持平 |
| **Plugin marketplace** | 无 | **有** | grok-build |
| **Memory(跨 session)** | 无 | **有** | grok-build |
| **Mermaid 渲染** | 无(只输出源码) | **终端渲染** | grok-build |
| **Voice** | 无 | **有** | grok-build |
| **Auto update** | 手动(uv) | **自动** | grok-build |
| **Computer Use** | 无 | **有** | grok-build |
| **Crash handler** | 无 | **有** | grok-build |
| **DI/Scope 架构** | **有(深度)** | 无(用 crate 分层) | kimi-code |
| **事件溯源(wire)** | **有** | JSONL + SQLite(混合) | kimi-code(更优雅) |
| **测试 harness** | **七层金字塔** | 有(但没拆到那么深) | kimi-code |
| **eval/benchmark** | **双轨道** | 未见(可能内部) | kimi-code |

**结论**:grok-build 在**功能广度**上碾压 kimi-code(voice/computer-use/marketplace/memory/mermaid/crash-handler/auto-update 都有)。kimi-code 在**架构深度**上更优雅(DI/wire/harness/eval)。两者代表了不同的工程哲学。

## 一句话总结

> Grok-build 在功能广度上远超 kimi-code:BM25 工具搜索、worktree 池、行级 hunk 追踪、TDigest 信号统计、Capability Gate slash 命令、plugin marketplace、跨 session memory、终端 Mermaid 渲染、语音输入、computer use、crash handler、自动更新 —— 这些 kimi-code 全都没有。但 kimi-code 在架构深度(DI×Scope / wire Op/Model / 七层 harness / 双轨道 eval)上更优雅。**grok-build 赢在广度,kimi-code 赢在深度**。

## 源码索引

| 概念 | 文件 |
|---|---|
| 工具系统 | `xai-grok-tools/src/`(113K 行) |
| BM25 搜索 | `session/tool_index.rs`(2502 行) |
| Signals | `session/signals.rs`(3133 行) |
| Slash 命令 | `session/slash_commands.rs`(2649 行) |
| Interjection | `xai-interjection-core/src/` |
| MCP | `xai-grok-mcp/src/`(10K 行) |
| Hooks | `xai-grok-hooks/src/`(8.5K 行) |
| Plugin marketplace | `xai-grok-plugin-marketplace/src/`(5.5K 行) |
| Memory | `xai-grok-memory/src/`(10K 行) |
| Markdown + Mermaid | `xai-grok-markdown/src/`(21K 行) |
| Voice | `xai-grok-voice/src/`(2.8K 行) |
| Auto update | `xai-grok-update/src/`(11K 行) |
| Computer hub | `xai-computer-hub-core/` + 适配器 + SDK |
| Crash handler | `xai-crash-handler/src/` |
| Config | `xai-grok-config/src/`(6.9K 行) |
| Auth | `xai-grok-auth/src/`(411 行) |
