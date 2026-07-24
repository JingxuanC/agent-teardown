# Grok Build · Sampler(LLM 调用)拆解

> 📁 **源码位置** · `crates/codegen/xai-grok-sampler/`(10K 行)+ `crates/codegen/xai-grok-sampling-types/`(9K 行)
>
> 📄 **核心文件** · `client.rs`(HTTP 客户端) · `stream/responses.rs`(Responses API SSE) · `stream/messages.rs`(Anthropic SSE) · `stream/chat_completions.rs`(OpenAI 兼容) · `doom_loop.rs` · `shared_http.rs`

## 1. 三种 API 后端

```rust
//! Talks to three backend shapes:
//! * Chat Completions (/chat/completions)
//! * Responses API (/responses)
//! * Anthropic Messages API (/messages)
```

和 kimi-code 的 kosong 一样,grok-build 也统一了**三种 API**。但 grok-build 额外有 **xAI 自家 API** 的深度集成(通过 `x-grok-*` headers)。

## 2. xAI 深度集成

### 2.1 x-grok 请求头

```rust
struct GrokRequestHeaders<'a> {
    conv_id: &'a str,        // 会话 ID
    req_id: &'a str,         // 请求 ID
    model_id: &'a str,       // 模型
    session_id: &'a str,     // session
    turn_idx: Option<&'a str>,  // turn 序号
    agent_id: &'a str,       // agent ID
    deployment_id: Option<&a str>,
    user_id: Option<&'a str>,
}
```

这些 headers 让 xAI 服务端能做:
- **请求追踪**(通过 conv_id + req_id 关联)
- **doom loop 检测**(服务端分析重复模式)
- **负载均衡**(session affinity)
- **按 deployment 路由**

**kimi-code 没有这种深度集成** —— 它只用标准 HTTP headers。

### 2.2 Doom Loop 请求头

```rust
pub const DOOM_LOOP_CHECK_HEADER: &str = "x-grok-doom-loop-check";
```

opt-in doom loop 检测(见 [02-doom-loop.md](02-doom-loop.md))。

### 2.3 Retry-After 解析

```rust
/// Parse the Retry-After response header as delta-seconds.
/// Capped at 120s to prevent absurdly long sleeps.
```

provider 返回 429 + `Retry-After` 时,grok-build 会听 provider 的(但上限 120s,防止恶意值)。

## 3. SSE 流解析

三个 stream 模块分别处理三种 API 的 SSE:

| 模块 | API | 流式格式 |
|---|---|---|
| `stream/responses.rs` | xAI / OpenAI Responses | `response.output_text.delta` 等 |
| `stream/messages.rs` | Anthropic Messages | `content_block_delta` 等 |
| `stream/chat_completions.rs` | OpenAI 兼容 | `choices[0].delta.content` 等 |

每个模块做两件事:
1. **Layer 1**:原始 SSE 字节流 → 事件(含 doom loop 拦截)
2. **Layer 2**:事件 → 统一的 `ConversationResponse`

## 4. Circuit Breaker

```rust
// xai-circuit-breaker
//! Sliding-window-with-min-samples: trips when
//! sample_count >= min_samples AND error_rate >= error_rate_threshold
```

**和 retry 的区别**:
- retry:单次请求失败就重试
- circuit breaker:**窗口内错误率超阈值**就熔断(停止所有请求)

**对 agent 的意义**:如果 xAI API 连续返回 500,retry 会无限循环浪费 token。circuit breaker **熔断后等待一段时间**,避免雪崩。

## 5. 和 kimi-code kosong 对比

| 维度 | kosong(kimi-code) | sampler(grok-build) |
|---|---|---|
| **支持的 API** | 5 种(OpenAI×2/Anthropic/Google/Kimi) | 3 种(Responses/Messages/ChatCompletions) |
| **xAI 集成** | 无 | **深度(x-grok headers)** |
| **doom loop** | 无 | **有(服务端 + 客户端)** |
| **circuit breaker** | 无 | **有(sliding window)** |
| **工具调用多路复用** | streamIndex Map | 类似 |
| **流式合并** | generate() 纯函数 | stream transform |

## 6. 一句话总结

> Sampler 是 grok-build 的 LLM 调用层,统一三种 API(Responses/Messages/Chat Completions),深度集成 xAI 自家 API(x-grok headers 做追踪 + doom loop + 路由)。配合 **circuit breaker**(滑动窗口熔断)和 **doom loop 检测**(服务端信号 + 客户端 abort),比 kimi-code 的 kosong 多了两层**实时故障保护**。

## 7. 源码索引

| 概念 | 文件 |
|---|---|
| HTTP 客户端 | `sampler/src/client.rs` |
| Responses stream | `sampler/src/stream/responses.rs` |
| Messages stream | `sampler/src/stream/messages.rs` |
| Chat Completions stream | `sampler/src/stream/chat_completions.rs` |
| Doom loop transport | `sampler/src/doom_loop.rs` |
| Shared HTTP(circuit breaker) | `sampler/src/shared_http.rs` |
| Sampling types | `xai-grok-sampling-types/src/conversation.rs`(9481 行) |
| Sampler config | `sampler/src/config.rs` |
| Circuit breaker | `xai-circuit-breaker/src/` |
