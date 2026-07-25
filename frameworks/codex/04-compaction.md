# OpenAI Codex CLI · Compaction 系统深度拆解

> 📁 **源码位置** · `codex-rs/core/src/compact.rs` + `compact_remote*.rs`(4 个文件) + `state/auto_compact_window.rs` + `codex-api/src/endpoint/compact.rs`
>
> 🔬 **codegraph 验证** · 精确追踪 CompactionTraceContext / AutoCompactWindow / CompactClient

## 1. Codex Compaction 的独特之处

四个框架的 compaction 策略：

| 框架 | 策略 | 压缩在哪 |
|---|---|---|
| kimi-code | 单遍 LLM 压缩 | **客户端**（kosong） |
| grok-build | 两遍(pass1+pass2) | **客户端**（sampler） |
| Pi | 单遍 + branch summary | **客户端** |
| **Codex** | **服务端压缩 + 客户端压缩 + auto-compact + window 追踪** | **客户端 + 服务端** |

**Codex 是唯一支持服务端压缩的**。

## 2. 三种压缩模式

### 2.1 手动压缩（用户 `/compact`）

用户主动触发，调用 `compact` 函数。

### 2.2 自动压缩（auto-compact）

当 token 用量接近 context window 上限时自动触发。

```rust
// codex-rs/core/src/state/auto_compact_window.rs (verbatim from codegraph)
pub(crate) struct AutoCompactWindow {
    window_number: u64,           // 第几个压缩窗口
    ids: AutoCompactWindowIds,    // UUID v7 时间戳 ID
    new_context_window_requested: bool,
    prefill_input_tokens: Option<AutoCompactWindowPrefill>,  // 压缩后的基线 token 数
    token_budget_reminder_delivered: bool,                    // 是否提醒过 token 预算
    auto_compact_fallback_delivered: bool,                    // 是否回退过
}
```

**Auto-compact window 是一个状态机**：
- 每次压缩创建一个新 window（UUID v7）
- 追踪 `window_number`（第几次压缩）
- 记录 `prefill_input_tokens`（压缩后的基线，用于判断下次何时触发）
- 有两种 prefill：**ServerObserved**（服务端报告的真实值）和 **Estimated**（客户端估算）

**advance 操作**（进入下一个窗口）：
```rust
pub(super) fn advance(&mut self) -> (u64, AutoCompactWindowIds) {
    self.window_number = self.window_number.saturating_add(1);
    self.ids.previous_window_id = Some(self.ids.window_id);
    self.ids.window_id = Uuid::now_v7();
    // ...
}
```

### 2.3 远程压缩（server-side compaction）★ 独有

```rust
// codex-rs/core/src/compact_remote_request.rs (verbatim from codegraph)
pub(super) async fn run_remote_compact_attempt(
    sess: &Arc<Session>,
    step_context: &Arc<StepContext>,
    turn_state: Option<Arc<OnceLock<String>>>,
    compaction_trace: &CompactionTraceContext,
    compaction_metadata: CompactionTurnMetadata,
    analytics_details: &mut CompactionAnalyticsDetails,
) -> CodexResult<RemoteCompactAttempt> {
    let mut history = sess.clone_history().await;
    let base_instructions = sess.get_base_instructions().await;
    
    // 先在客户端裁剪 function call history
    let (rewritten_outputs, estimated_deleted_tokens) =
        trim_function_call_history_to_fit_context_window(
            &mut history, turn_context, &base_instructions,
        );
    // 然后发送到服务端压缩
    // ...
}
```

**两步压缩**：
1. **客户端预处理**：`trim_function_call_history_to_fit_context_window`（裁剪旧的 function call 历史，节省发送量）
2. **服务端压缩**：发送到 OpenAI 的 `responses/compact` 端点

```rust
// codex-rs/codex-api/src/endpoint/compact.rs (verbatim from codegraph)
fn path() -> &'static str {
    "responses/compact"
}

pub async fn compact(
    &self,
    body: serde_json::Value,
    extra_headers: HeaderMap,
    request_timeout: Duration,
    turn_state: Option<&OnceLock<String>>,
) -> Result<Vec<ResponseItem>, ApiError> {
    let resp = self.session.execute_with(
        Method::POST, Self::path(), extra_headers, Some(body), ...
    ).await?;
    // 解析 CompactHistoryResponse
    Ok(parsed.output)
}
```

**服务端压缩 API**：POST `responses/compact`，返回压缩后的消息列表。

**为什么服务端压缩更强**：
- 服务端有**完整的 prompt cache**（客户端发送的历史不需要重新编码）
- 服务端可以用**更大的模型**做压缩（客户端只能用当前模型）
- 服务端可以**跨 session 复用**压缩结果（未来可能的优化）

## 3. Compaction Trace（压缩追踪）

```rust
// codex-rs/rollout-trace/src/compaction.rs (from codegraph)
pub struct CompactionTraceContext {
    state: CompactionTraceContextState,
}

// 追踪的事件：
// - start_attempt    开始一次压缩尝试
// - record_installed  记录已安装
// - record_started    记录已开始
// - record_completed  记录已完成
// - record_failed     记录失败
```

**每次压缩都被完整追踪**：尝试次数、成功/失败、token 变化。这让 OpenAI 能分析压缩的质量和成本。

## 4. Token Budget Context（预算通知）

```rust
// codex-rs/core/src/context/token_budget_context.rs (verbatim from codegraph)
pub(crate) struct TokenBudgetContext {
    thread_id: ThreadId,
    first_window_id: Uuid,
    previous_window_id: Option<Uuid>,
    window_id: Uuid,
    mcp_result: Option<String>,
}

impl ContextualUserFragment for TokenBudgetContext {
    fn role(&self) -> &'static str { "developer" }
    fn markers(&self) -> (&'static str, &'static str) {
        (CONTEXT_WINDOW_OPEN_TAG, CONTEXT_WINDOW_CLOSE_TAG)
    }
}
```

**agent 能感知到自己的 token 预算**！通过 `developer` 角色消息注入：
- 当前在哪个 compaction window
- 第几次压缩
- 剩余预算

这让 agent 能**自我调节**（"我快没预算了，应该更简洁"）。

## 5. 压缩后能 Fork

从测试文件 `compact_resume_fork.rs` 确认：

```rust
//! Integration tests that cover compacting, resuming, and forking conversations.
```

**压缩 → resume → fork** 的完整链路是测试覆盖的。这意味着：
- 压缩后可以恢复
- 恢复后可以 fork
- fork 可以 rollback 到压缩前的状态

## 6. 和其他框架对比

| 维度 | kimi-code | grok-build | Pi | **Codex** |
|---|---|---|---|---|
| **压缩位置** | 客户端 | 客户端 | 客户端 | **客户端 + 服务端** |
| **压缩次数** | 单遍 | 两遍 | 单遍 | **单遍（但服务端有 cache）** |
| **自动触发** | 85% 阈值 | 85% 阈值 | 有 | **有（AutoCompactWindow）** |
| **window 追踪** | ❌ | ❌ | ❌ | **✅ UUID v7 + window_number** |
| **token 预算感知** | ❌ | ❌ | ❌ | **✅ developer 消息注入** |
| **function call 裁剪** | ❌ | ❌ | ❌ | **✅ trim_function_call_history** |
| **压缩追踪** | ❌ | ❌ | ❌ | **✅ CompactionTraceContext** |
| **压缩后 fork** | ❌ | checkpoint | session tree | **✅ compact → resume → fork** |
| **prompt cache 利用** | ❌ | ❌ | ❌ | **✅ 服务端有 cache** |

## 7. 设计权衡

### 7.1 为什么用服务端压缩？

**Prompt cache** 是关键。客户端压缩需要把整个历史发给 LLM，但服务端压缩时：
- 历史已经在服务端的 cache 里
- 只需要告诉服务端"压缩哪些部分"
- 返回压缩后的消息

**成本差异**：客户端压缩 = 全量 input token。服务端压缩 = cache hit（可能只付 10% 的 input 成本）。

### 7.2 为什么追踪 window_number？

每次压缩创建一个新 window。这让系统能知道"这个 agent 已经被压缩了多少次" —— 直接关联到我们在论文里提的"cumulative compaction degradation"。Codex 通过 window_number 追踪这个数据，但**目前没有基于它的退化检测**（未来方向）。

### 7.3 为什么让 agent 感知 token 预算？

传统 agent 不知道自己还剩多少 token。Codex 通过 `developer` 消息注入预算信息，让 agent 能：
- 自我调节输出长度
- 主动建议用户 compact
- 在低预算时更谨慎地选择工具调用

## 8. 一句话总结

> Codex 的 compaction 是四个框架中最成熟的：(1) **服务端压缩**（利用 prompt cache，成本低）+ 客户端预处理（function call 裁剪）；(2) **AutoCompactWindow** 状态机（UUID v7 追踪每次压缩，记录 prefill token baseline）；(3) **CompactionTraceContext**（完整追踪压缩尝试/成功/失败）；(4) **Token Budget Context**（通过 developer 消息让 agent 感知自己的预算）；(5) **压缩后 fork**（compact → resume → fork 完整链路）。**唯一利用服务端 prompt cache 做压缩的框架**，成本比纯客户端压缩低一个数量级。

## 9. 源码索引

| 概念 | 文件 |
|---|---|
| 客户端压缩 | `core/src/compact.rs` |
| 服务端压缩请求 | `core/src/compact_remote_request.rs` |
| 服务端压缩 v2 | `core/src/compact_remote_v2.rs` + `compact_remote_v2_attempt.rs` |
| 压缩 API 客户端 | `codex-api/src/endpoint/compact.rs` |
| AutoCompactWindow | `core/src/state/auto_compact_window.rs` |
| 压缩追踪 | `rollout-trace/src/compaction.rs` |
| Token 预算上下文 | `core/src/context/token_budget_context.rs` |
| function call 裁剪 | `core/src/compact_remote_request.rs`(trim_function_call_history) |
| 测试(compact) | `core/tests/suite/compact.rs`(5,444 行!) |
| 测试(compact+resume+fork) | `core/tests/suite/compact_resume_fork.rs` |
