# Kimi Code · 错误系统拆解

**源码位置**:`packages/agent-core-v2/src/_base/errors/` + 各域的 `errors.ts` + `src/errors.ts`(facade)
**核心文件**:`errors.ts`(75 行,base 类)、`codes.ts`、`serialize.ts`(107 行)、`docs/errors.md`(必读)
**设计哲学**:**编码化错误 + 域归属 + 边界翻译 + 序列化友好**

## 1. 为什么 agent 框架需要专门的错误系统?

普通 web 应用的错误处理:`throw new Error('x')` + 全局 catch + 日志。够用。

**Agent 框架不能这样**,因为:
- 错误要**跨 RPC 传播**(kap-server ↔ klient ↔ TUI),`instanceof` 失效
- 错误要**可重试判断**(429 要 retry,400 不要)
- 错误要**国际化和本地化**(显示给用户)
- 错误要**携带结构化元数据**(errno、syscall、statusCode、requestId)
- 错误要**可观测**(telemetry 报告)

裸 `Error` 字符串解决不了这些。所以 kimi-code 设计了 `Error2` + `ErrorCodes` 体系。

## 2. 五种错误基类

```typescript
// errors.ts(简化)
export class Error2 extends Error {
  constructor(
    code: ErrorCode,                        // ★ 必须的 code
    message: string,                        // 短的人类可读消息
    options?: { details?: Record<string, unknown>; cause?: unknown },
  );
  readonly code: ErrorCode;
  readonly details?: Record<string, unknown>;
}

export class ExpectedError extends Error2 { }       // 预期错误(不算 bug)
export class ErrorNoTelemetry extends Error2 { }   // 不上报 telemetry(隐私)
export class BugIndicatingError extends Error2 { } // 调用者写错了(应该 fix)
export class NotImplementedError extends Error2 { } // 占位实现
```

**为什么五种?**因为它们语义不同,处理方式不同:
- `ExpectedError`:用户操作引发,正常显示即可
- `ErrorNoTelemetry`:可能含敏感信息,不上报
- `BugIndicatingError`:程序员 bug,应该断言而不是 catch
- `NotImplementedError`:feature 未完成

## 3. ErrorCodes:去中心化注册

错误码不在中心文件,而是**每个域一个 `errors.ts`**:

```typescript
// tool/errors.ts
export const ToolErrors = {
  codes: {
    UNKNOWN_TOOL: 'tool.unknown_tool',
    EXECUTION_FAILED: 'tool.execution_failed',
  },
  retryable: ['tool.execution_failed'],          // ★ 可重试的 code 列表
  info: {
    'tool.unknown_tool': {
      title: 'Unknown tool',
      retryable: false,
      public: true,                              // 给用户看
      action: 'Check the tool name passed by the model.',
    },
  },
} as const satisfies ErrorDomain;

registerErrorDomain(ToolErrors);                 // 自注册
```

`src/errors.ts` 是**facade**,import 所有域的 errors.ts(触发注册),汇成统一的 `ErrorCodes`:

```typescript
import './tool/errors';
import './goal/errors';
import './session/errors';
// ...

export const ErrorCodes = {
  ...ToolErrors.codes,
  ...GoalErrors.codes,
  ...SessionErrors.codes,
  // ...
};
```

**命名约定**:`domain.reason`(例如 `tool.unknown_tool`、`goal.already_exists`)。这让错误码**自带溯源** —— 看到码就知道是哪个域的。

## 4. 序列化:跨 RPC 边界

RPC 边界上 `instanceof` 失效(不同进程)。所以有 `toErrorPayload` / `fromErrorPayload`:

```typescript
// serialize.ts
export interface ErrorPayload {
  readonly code: string;
  readonly message: string;
  readonly details?: Record<string, unknown>;
  readonly retryable?: boolean;
}

export function toErrorPayload(error: unknown): ErrorPayload;
export function fromErrorPayload(payload: ErrorPayload): Error2;
```

**关键规则**:**跨 wire 永远按 `code` 分支,不按 `instanceof`**。因为类身份不跨序列化。

## 5. 外部错误的边界翻译

Provider/HTTP/fs/MCP 的错误格式各不相同。在**域边界**翻译:

```typescript
// 域的入口处
try {
  await fs.readFile(path);
} catch (error) {
  throw toHostFsError(error, path);              // 翻译成 FileErrors.READ_FAILED
}
```

**翻译是幂等的**:`toHostFsError` 检测输入是否已经是 `FileErrors`,是就原样返回。这让多层边界不会双重包装。

**Cancellation 不翻译**:`AbortError` 直接穿透,因为取消不是错误(见 [09-loop.md](09-loop.md) §9.3)。

## 6. 边界条件与设计权衡

| 规则 | 原因 |
|---|---|
| `throw new Error('x')` 只用于 unreachable guards | 业务错误必须 coded |
| 错误码属于域,不属于 `_base` | 解耦,易扩展 |
| 添加新 code 要先改 protocol(`KimiErrorCode`)| wire 兼容性 |
| 重命名/删除 code 是 major break | SDK 客户端会炸 |
| `details` 必须 JSON-serializable | 跨 wire 传输 |
| `message` 是短的人类句子 | UI 展示 |
| 路径/errno/syscall 进 `details` | 不污染 message |
| 跨 wire 按 code 分支 | instanceof 失效 |
| 翻译用 `unwrapErrorCause` | 拿到原始错误判断 |
| 取消错误穿透 | 不是错误 |

**遗憾**:
- protocol 强约束让加 code 很重(要改 protocol 包)
- `ErrorCodes.X` 字符串是魔法值,IDE 跳转不友好

## 7. 一句话总结

> 错误系统是**Error2 + ErrorCodes(去中心化注册)+ 边界翻译 + 序列化 payload** 的组合。每个错误必须带 `domain.reason` 格式的 code,在域边界翻译外部错误,跨 RPC 按 code 而非 instanceof 分支。五种基类(Error2/ExpectedError/ErrorNoTelemetry/BugIndicatingError/NotImplementedError)区分错误语义,retryable 元数据让 retry 逻辑不用硬编码。

## 8. 源码索引

| 概念 | 文件 |
|---|---|
| 基类(Error2 等) | `src/_base/errors/errors.ts` |
| `ErrorDomain` + `registerErrorDomain` | `src/_base/errors/codes.ts` |
| 序列化 | `src/_base/errors/serialize.ts` |
| Facade(汇总所有域) | `src/errors.ts` |
| 各域 errors | `src/<domain>/errors.ts` |
| 设计文档 | `docs/errors.md`(必读) |

## 参考资料

- [09-loop.md](09-loop.md) §7 —— StepRetry 用 `isRetryableGenerateError`
- [14-provider-llm.md](14-provider-llm.md) —— kosong 错误归一化后,域边界再翻译
