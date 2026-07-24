# Kimi Code · Provider/kosong LLM 抽象层拆解

> 📁 **源码位置** · `packages/kosong/`(独立包,8000+ 行)+ `packages/agent-core-v2/src/app/llmProtocol/`(集成层)
>
> 📄 **核心文件** · `provider.ts`(274 行,核心接口)、`generate.ts`(365 行,流式生成)、`providers/anthropic.ts`(1297 行)、`providers/openai-responses.ts`(1199 行)、`providers/google-genai.ts`(988 行)、`providers/kimi.ts`(659 行)


## 1. 这个模块要解决什么问题

**场景**:Agent 框架要支持**多个 LLM 提供商**,但它们之间差异巨大:

| Provider | API 风格 | 流式协议 | 工具调用格式 | 思考过程 |
|---|---|---|---|---|
| **OpenAI Chat Completions** | `/v1/chat/completions` | SSE delta | `tool_calls[]` | 无原生 |
| **OpenAI Responses** | `/v1/responses` | SSE event | `function_call` item | reasoning items |
| **Anthropic Messages** | `/v1/messages` | SSE event | `tool_use` block | `thinking` block |
| **Google GenAI** | `generateContent` | SSE | `functionCall` | `thought` |
| **Kimi(KFC)** | OpenAI 兼容 | SSE | OpenAI 风格 | 部分模型支持 |
| **本地 Ollama** | OpenAI 兼容 | SSE | OpenAI 风格 | 无 |

如果不抽象,业务代码要写 5 套适配逻辑,而且**换 provider 要改业务**。

**kosong 的目标**:统一这些差异,让 agent 框架只看到一套接口。

**为什么叫 kosong**?(马来语/印尼语"空")—— 寓意"空白抽象层"。

## 2. 核心抽象:ChatProvider

```typescript
// provider.ts(简化)
export interface ChatProvider {
  // 模型信息
  readonly providerName: string;
  readonly modelName: string;

  // 流式生成
  generate(
    systemPrompt: string,
    tools: Tool[],
    history: Message[],
    options?: GenerateOptions,
  ): Promise<StreamedMessage>;

  // 配置链式 API
  withApiKey(key: string): ChatProvider;
  withBaseUrl(url: string): ChatProvider;
  withModel(model: string): ChatProvider;
  withThinking(effort: ThinkingEffort): ChatProvider;
  withMaxCompletionTokens(tokens: number, options?: MaxCompletionTokensOptions): ChatProvider;
  withResponseFormat(format: ResponseFormat): ChatProvider;
}
```

**链式 API**(`withXxx`)是不可变配置:每次返回新实例,不修改原对象。这让 provider 实例可以安全共享。

## 3. StreamedMessage:统一流式协议

这是整个抽象最关键的部分 —— 把五种完全不同的 SSE 协议**归一**成一个 async iterator。

```typescript
export interface StreamedMessage {
  [Symbol.asyncIterator](): AsyncIterator<StreamedMessagePart>;

  readonly id: string | null;                    // 响应 ID
  readonly usage: TokenUsage | null;             // token 统计
  readonly finishReason: FinishReason | null;    // 归一化的停止原因
  readonly rawFinishReason: string | null;       // 原始字符串(escape hatch)
  readonly traceId?: string | null;              // x-trace-id(Kimi 专用)
}
```

### 3.1 StreamedMessagePart:统一的 chunk 类型

```typescript
type StreamedMessagePart =
  | TextPart                           // 文本 delta
  | ToolCallPart                       // 工具调用 delta
  | ThinkingPart                       // 思考过程 delta
  | VideoURLPart;                      // 视频引用
```

不管原始协议是 OpenAI 的 `delta.content` 还是 Anthropic 的 `content_block_delta`,都被翻译成 `TextPart`。这让上层代码不用关心"现在用的是哪家 API"。

### 3.2 FinishReason 归一化

```typescript
export type FinishReason =
  | 'completed'    // 正常完成
  | 'tool_calls'   // 暂停以执行工具调用
  | 'truncated'    // token 预算用尽
  | 'filtered'     // 安全过滤
  | 'paused'       // Anthropic 的 pause_turn
  | 'other';
```

不同 provider 的命名规约:

| 统一值 | OpenAI | Anthropic | Gemini |
|---|---|---|---|
| `completed` | `stop` | `end_turn` / `stop_sequence` | `STOP` |
| `tool_calls` | `tool_calls` | `tool_use` | (归到 completed) |
| `truncated` | `length` | `max_tokens` | `MAX_TOKENS` |
| `filtered` | `content_filter` | — | `SAFETY` |
| `paused` | — | `pause_turn` | — |

**保留 `rawFinishReason`**:如果出现新的、未映射的原因,上层还能拿到原始字符串做特殊处理。

## 4. generate:核心流式循环

`generate.ts` 是一个**纯函数**,把 provider 的 stream 累积成完整 message。

### 4.1 主循环

```typescript
// generate.ts(简化)
export async function generate(
  provider: ChatProvider,
  systemPrompt: string,
  tools: Tool[],
  history: Message[],
  callbacks?: GenerateCallbacks,
  options?: GenerateOptions,
): Promise<GenerateResult> {
  const message: Message = { role: 'assistant', content: [], toolCalls: [] };
  let pendingPart: StreamedMessagePart | null = null;
  const streamIndexToToolCallIndex = new Map<number, number>();

  const stream = await provider.generate(systemPrompt, tools, history, options);

  for await (const part of stream) {
    if (options?.signal?.aborted) throw new AbortError('Aborted');

    // 合并连续的同类 part
    if (pendingPart !== null && canMerge(pendingPart, part)) {
      mergeInPlace(pendingPart, part);
    } else {
      if (pendingPart !== null) flushPart(message, pendingPart);
      pendingPart = part;
    }

    // 流式回调(用于 UI 实时显示)
    await callbacks?.onMessagePart?.(part);
  }

  if (pendingPart !== null) flushPart(message, pendingPart);

  // 工具调用回调(整个 stream 结束后才触发)
  for (const toolCall of message.toolCalls) {
    await callbacks?.onToolCall?.(toolCall);
  }

  // 检查空响应
  if (message.content.length === 0 && message.toolCalls.length === 0) {
    throw new APIEmptyResponseError();
  }

  return {
    id: stream.id,
    message,
    usage: stream.usage,
    finishReason: stream.finishReason,
    rawFinishReason: stream.rawFinishReason,
    traceId: stream.traceId,
  };
}
```

### 4.2 三个精妙设计

**1. 流式合并**:

```typescript
if (pendingPart !== null && canMerge(pendingPart, part)) {
  mergeInPlace(pendingPart, part);     // 累积文本
}
```

文本 delta 来时是碎片("Hello" → " world" → "!"),合并成 "Hello world!"。避免存 100 个小 TextPart。

**2. 工具调用延迟触发**:

```typescript
// 工具调用回调(整个 stream 结束后才触发)
for (const toolCall of message.toolCalls) {
  await callbacks?.onToolCall?.(toolCall);
}
```

**为什么不流式触发 onToolCall**?因为 OpenAI 的并行工具调用会**交错**:

```
tc0-header → tc1-header → tc0-args → tc1-args → tc0-done → tc1-done
```

如果中途触发,会拿到**半个参数**的工具调用。延迟到 stream 结束后统一触发,保证参数完整。

**3. AbortSignal 检查**:

```typescript
for await (const part of stream) {
  if (options?.signal?.aborted) throw new AbortError('Aborted');
  ...
}
```

每个 chunk 之间检查 abort。这让用户 Ctrl+C 能在**毫秒级**生效,不用等整个响应完成。

## 5. 工具调用的多路复用

OpenAI 并行工具调用的流式协议是**交错的**:`tc0-header → tc1-header → tc0-args → tc1-args`。kosong 怎么路由?

### 5.1 streamIndex 路由

```typescript
// generate.ts
const streamIndexToToolCallIndex = new Map<number, number>();

// 收到 ToolCallPart 时
const streamIdx = part._streamIndex;       // provider 提供的流索引
let toolCallIdx = streamIndexToToolCallIndex.get(streamIdx);
if (toolCallIdx === undefined) {
  toolCallIdx = message.toolCalls.length;
  message.toolCalls.push({ id: '', name: '', arguments: '' });
  streamIndexToToolCallIndex.set(streamIdx, toolCallIdx);
}
// 把 delta 累积到 message.toolCalls[toolCallIdx]
```

**Map 路由**:streamIndex(provider 的流索引,例如 OpenAI 的 `index`)→ message 里的 toolCalls 数组索引。这让交错的 delta 能正确累积到对应的 toolCall。

### 5.2 id 分配

不同 provider 的 toolCall id 时机不同:
- OpenAI:header 阶段就有 id
- Anthropic:可能延后到 content_block_start

kosong 在 stream 结束时统一规整 id,保证业务看到的 id 都是非空字符串。

## 6. Provider 适配器:五朵金花

### 6.1 Anthropic(1297 行,最大)

特点:
- `thinking` block 是原生支持的(reasoning models)
- `tool_use` block 独立于文本
- `cache_control` 字段支持 prompt cache
- 需要 `max_tokens` 强制指定

挑战:
- anthropic 的 SSE 事件类型多(`message_start`、`content_block_start`、`content_block_delta`、`content_block_stop`、`message_delta`、`message_stop`)
- thinking 和 text 在不同 content block,要正确路由

### 6.2 OpenAI Responses(1199 行)

特点:
- 新的 Responses API(`/v1/responses`)
- 原生支持 reasoning items(`reasoning.encrypted_content`)
- 工具调用是 `function_call` item,独立于文本
- `previous_response_id` 支持 server-side state(但 kosong 没用,保持无状态)

挑战:
- Responses API 的事件语义和 Chat Completions 完全不同
- reasoning content 是加密的,不能直接读

### 6.3 OpenAI Legacy(693 行)

老的 `/v1/chat/completions`,兼容大量第三方 OpenAI 兼容服务(ollama、vllm、deepseek 等)。这是**用户最多的 provider**。

### 6.4 Google GenAI(988 行)

特点:
- `functionCall` 而不是 `tool_calls`
- `thought` 是 Gemini 2.5+ 的思考过程
- 协议是 Google 自家的(SSE 但事件格式不同)

### 6.5 Kimi(659 行)

Moonshot 自家的 KFC 平台。基本兼容 OpenAI,但有自己的增强:
- `x-trace-id` 响应头
- 部分模型支持 thinking
- `kimi-files.ts` 支持文件引用

## 7. Thinking 支持

不同 provider 暴露思考过程的方式不同。kosong 用 `ThinkingEffort` 统一:

```typescript
export type ThinkingEffort = 'off' | 'on' | (string & {});
```

- `'off'`:关闭思考
- `'on'`:开启(对布尔型模型,例如 Claude 3.5)
- 其他字符串:模型声明的 effort 等级(`'low'`、`'high'`、`'max'`)

**provider 适配器把 ThinkingEffort 翻译成各自 API 的格式**:
- Anthropic:`thinking: { type: 'enabled', budget_tokens: N }`
- OpenAI Responses:`reasoning: { effort: 'high' }`
- Kimi:某些模型支持 `reasoning_effort`

## 8. Token 使用统计

```typescript
export interface TokenUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly cachedInputTokens?: number;        // prompt cache 命中
  readonly reasoningTokens?: number;           // 思考 token
}
```

不同 provider 报告的字段不同:
- OpenAI:`prompt_tokens`、`completion_tokens`、`prompt_tokens_details.cached_tokens`
- Anthropic:`input_tokens`、`output_tokens`、`cache_creation_input_tokens`、`cache_read_input_tokens`

kosong 统一成 `TokenUsage`,业务代码不用关心字段名差异。

## 9. 错误归一化

kosong 有专门的 `errors.ts`(534 行)归一化错误:

```typescript
// errors.ts(简化)
export class APIStatusError extends Error {
  constructor(
    message: string,
    readonly statusCode: number,
    readonly requestId?: string | null,
  ) { ... }
}

export class APIProviderRateLimitError extends APIStatusError { }   // 429
export class APIConnectionError extends Error { }                    // 网络问题
export class APITimeoutError extends APIConnectionError { }          // 超时
export class APIEmptyResponseError extends Error { }                 // 空响应
```

**所有 provider 的原始错误都翻译成这些类型**。这让上层的 retry 逻辑(见 [09-loop.md](09-loop.md) §7)可以用 `isRetryableGenerateError(error)` 统一判断,不用 switch provider。

## 10. Capability Registry

不同模型能力差异巨大(最大 context、是否支持思考、是否支持 vision)。kosong 有 `capability-registry.ts`:

```typescript
export interface ModelCapability {
  readonly max_context_tokens: number;
  readonly max_output_tokens?: number;
  readonly supports_thinking?: boolean;
  readonly supports_vision?: boolean;
  readonly supports_audio?: boolean;
  readonly supports_video?: boolean;
  readonly supports_response_format?: boolean;
  // ...
}
```

每个 provider 提供自己的 capability 查询函数:

```typescript
getAnthropicModelCapability(modelName: string): ModelCapability
getOpenAIResponsesModelCapability(modelName: string, opts): ModelCapability
getOpenAILegacyModelCapability(modelName: string, opts): ModelCapability
getGoogleGenAIModelCapability(modelName: string): ModelCapability
```

**业务代码只看 `ModelCapability`**,不用知道"这个模型是 OpenAI 的还是 Anthropic 的"。

## 11. 边界条件与失败模式

| 触发条件 | 行为 |
|---|---|
| API 返回 429 | 抛 `APIProviderRateLimitError`(上层 retry) |
| API 返回 5xx | 抛 `APIStatusError`(上层 retry) |
| 网络断开 | 抛 `APIConnectionError` |
| 请求超时 | 抛 `APITimeoutError` |
| 空响应 | 抛 `APIEmptyResponseError` |
| 中途 abort | 抛 `AbortError`(DOMException) |
| 工具参数 JSON 解析失败 | 累积成 toolCall.arguments 字符串,业务层 try parse |
| 工具调用 id 重复 | 保留最后一个(provider 的 bug) |
| 流式响应中断(没 finishReason) | `finishReason = null`,业务决定怎么处理 |
| Thinking 模型不支持 | 静默忽略 ThinkingEffort(降级到无 thinking) |
| Cache 命中 | usage.cachedInputTokens 有值 |
| Reasoning tokens 计费 | usage.reasoningTokens 单独计 |
| Model 不存在 | provider.generate 时 404,抛 APIStatusError |
| API key 无效 | 401,抛 APIStatusError |
| 并行工具调用交错 | streamIndex Map 路由 |
| provider 配置 baseURL 无效 | 第一次请求时失败 |
| 响应里既有 text 又有 thinking | 分别累积到 content 和 thinkingParts |

## 12. 设计权衡

### 12.1 为什么 kosong 是独立包?

- **复用性**:其他项目(不只是 kimi-code)可以直接用
- **测试隔离**:kosong 有自己的 vitest 配置,可以独立跑
- **API 稳定性**:独立版本号,语义化版本,破坏性变更显式

### 12.2 为什么用 async iterator 而不是 callback?

```typescript
// kosong 的方式
for await (const part of stream) { ... }

// 替代方案
provider.generate({ onData, onToolCall, onEnd })
```

- async iterator 支持 `break`(自然取消)
- 可以用 `Promise.race` 和其他异步操作组合
- 更容易做 backpressure
- 是 ECMAScript 标准

### 12.3 为什么 generate 是纯函数?

```typescript
generate(provider, systemPrompt, tools, history, callbacks, options): Promise<GenerateResult>
```

- 可测试:传 mock provider 就能测
- 无状态:同样的输入产生同样的输出
- 易组合:可以 pipe 多个 generate

### 12.4 为什么不直接用 Vercel AI SDK / LangChain?

- **轻量**:kosong 8000 行,Vercel AI SDK 数万行
- **控制权**:可以针对 agent 场景优化(例如工具调用延迟触发)
- **无运行时依赖**:不引入 LangChain 那套庞大生态
- **agent 场景定制**:thinking part、reasoning tokens 这些是 agent 特有的

### 12.5 遗憾与可改进点

- **没有 streaming tool result**:工具结果必须等整段 JSON 完整才能用,不能流式解析(虽然有 `tool.call.delta` 给 UI,但业务层还是等完整)
- **没有 provider fallback**:不能配置"OpenAI 失败自动切到 Anthropic"
- **没有请求级 budget**:`max_completion_tokens` 是全局的,不能"这次请求最多 1000 token"
- **capability 是硬编码**:新模型出来要改代码。应该从 API 自描述加载
- **没有 batch API**:Anthropic/OpenAI 都支持 batch,kosong 没抽象
- **错误信息泄漏**:有时会把 API key 的一部分包含在错误信息里

## 13. 一句话总结

> kosong 是一个**统一 5 大 LLM provider(OpenAI Chat/Responses、Anthropic、Google、Kimi)的抽象层**,通过 `ChatProvider` 接口 + `StreamedMessage` async iterator 把不同 API 的 SSE 协议、工具调用格式、思考过程、token 统计、错误码全部归一。核心 `generate()` 纯函数把流式 chunk 合并成完整 message,用 `streamIndex` Map 路由并行工具调用的交错 delta,工具调用回调延迟到 stream 结束后触发(防止半参数)。`FinishReason` 和 `ModelCapability` 让业务代码完全感知不到"现在用的是哪家 API"。

## 14. 本篇用到的核心源码索引

| 概念 | 文件 | 关键行 |
|---|---|---|
| `ChatProvider` 接口 | `packages/kosong/src/provider.ts` | — |
| `ThinkingEffort` | `packages/kosong/src/provider.ts` | 25-32 |
| `FinishReason` 归一化 | `packages/kosong/src/provider.ts` | 55-85 |
| `StreamedMessage` | `packages/kosong/src/provider.ts` | 85-127 |
| `GenerateOptions` | `packages/kosong/src/provider.ts` | 128+ |
| `generate` 纯函数 | `packages/kosong/src/generate.ts` | 85-150 |
| 工具调用延迟触发 | `packages/kosong/src/generate.ts` | 注释 55-60 |
| `streamIndex` 路由 | `packages/kosong/src/generate.ts` | 99-110 |
| `Message` 类型 | `packages/kosong/src/message.ts` | — |
| `StreamedMessagePart` | `packages/kosong/src/message.ts` | — |
| `TokenUsage` | `packages/kosong/src/usage.ts` | — |
| 错误类型 | `packages/kosong/src/errors.ts` | 全文 534 行 |
| `ModelCapability` | `packages/kosong/src/capability.ts` | — |
| Capability registry | `packages/kosong/src/providers/capability-registry.ts` | — |
| Anthropic 适配器 | `packages/kosong/src/providers/anthropic.ts` | 全文 1297 行 |
| OpenAI Responses 适配器 | `packages/kosong/src/providers/openai-responses.ts` | 全文 1199 行 |
| OpenAI Legacy 适配器 | `packages/kosong/src/providers/openai-legacy.ts` | 全文 693 行 |
| Google GenAI 适配器 | `packages/kosong/src/providers/google-genai.ts` | 全文 988 行 |
| Kimi 适配器 | `packages/kosong/src/providers/kimi.ts` | 全文 659 行 |
| Provider catalog | `packages/kosong/src/catalog.ts` | — |

## 参考资料

- [01-architecture.md](01-architecture.md) —— kosong 是 L0 层(最底层)
- [08-context-memory.md](08-context-memory.md) —— token usage 来自 kosong
- [09-loop.md](09-loop.md) —— StepRetry 消费 kosong 的错误类型
- [12-memory-and-injection.md](12-memory-and-injection.md) —— ProfileModelContext 用 ModelCapability
- OpenAI API:https://platform.openai.com/docs/api-reference
- Anthropic API:https://docs.anthropic.com/en/api/messages
- Google GenAI:https://ai.google.dev/api/rest/v1beta/models/generateContent
