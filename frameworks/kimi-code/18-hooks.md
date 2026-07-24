# Kimi Code · Hook 系统拆解

> 📁 **源码位置** · `packages/agent-core-v2/src/agent/externalHooks/`
>
> 📄 **核心文件** · `externalHooksService.ts` + `src/session/externalHooks/`(session 级适配)


## 1. Hook 是什么?

Hook 让用户在 agent 的**关键事件**上挂**外部脚本**。这是**用户级编程接口**,比插件轻量得多 —— 不用写 TS 代码,写个 shell/python 脚本就行。

**典型用途**:
- `PreToolUse`:工具调用前跑 lint 检查
- `SubagentStart`:子 agent 启动时发通知
- `TurnEnd`:turn 结束时跑测试
- `SessionStart`:session 启动时加载环境

## 2. Hook vs Loop Hooks 的区别

| 维度 | Loop Hooks(onWillBeginStep 等) | External Hooks |
|---|---|---|
| 形态 | TS 函数 | 外部脚本(shell/python) |
| 注册 | 代码里 `register(...)` | 配置文件声明 |
| 通信 | 同进程函数调用 | JSON in / JSON out |
| 用途 | 内部扩展 | 用户自定义 |
| 性能 | 微秒级 | 毫秒级(进程启动) |

**External Hooks 是 Loop Hooks 的"用户友好包装"**:底层是 loop hook 订阅,但把回调转成"跑外部脚本"。

## 3. 配置

```toml
# ~/.kimi-code/config.toml 或 .kimi-code/config.toml
[[hooks]]
event = "PreToolUse"
command = "python3 .kimi-code/hooks/pre-tool-check.py"

[[hooks]]
event = "SubagentStop"
command = "notify-send 'Subagent finished'"
```

## 4. 执行协议

```mermaid
sequenceDiagram
    participant Loop as Agent Loop
    participant Hook as ExternalHookService
    participant Script as 用户脚本

    Loop->>Hook: 触发 hook event
    Hook->>Hook: 序列化 input 成 JSON
    Hook->>Script: spawn(command),stdin = JSON
    Script->>Script: 处理
    Script-->>Hook: stdout = JSON output
    Hook->>Loop: 解析 output,决定 allow/deny/modify
```

**输入**(stdin JSON):

```json
{
  "event": "PreToolUse",
  "toolName": "Bash",
  "toolInput": { "command": "rm -rf /" },
  "cwd": "/Users/me/project",
  "sessionId": "sess-xxx"
}
```

**输出**(stdout JSON):

```json
{
  "decision": "block",                    // allow / block / modify
  "reason": "Destructive command blocked",
  "modifiedInput": null
}
```

## 5. 关键 hook 事件

| 事件 | 时机 | 能做什么 |
|---|---|---|
| `PreToolUse` | 工具执行前 | allow/block/modify 参数 |
| `PostToolUse` | 工具执行后 | 检查结果、记录 |
| `SubagentStart` | 子 agent 启动 | 发通知 |
| `SubagentStop` | 子 agent 结束 | 记录 |
| `SessionStart` | session 启动 | 加载环境 |
| `TurnEnd` | turn 结束 | 跑测试 |

## 6. 失败处理

- **脚本不存在**:log warning,继续(hook 不阻塞主流程)
- **脚本超时**:默认 30s,超时 kill,hook 视为 no-op
- **脚本输出非 JSON**:视为 no-op
- **脚本 exit code != 0**:视为 block(安全失败)

**安全失败原则**:hook 系统的问题**不能让 agent 停摆**。所有异常都被捕获,降级为 no-op。

## 7. 一句话总结

> Hook 系统让用户通过**配置声明 + 外部脚本(JSON in/out)**在关键事件(PreToolUse/SubagentStart/TurnEnd)上挂自定义逻辑。底层是 loop hooks 的包装,把 TS 回调转成"spawn 脚本 + JSON 通信"。安全失败原则:hook 异常降级为 no-op,不阻塞 agent。

## 8. 源码索引

| 概念 | 文件 |
|---|---|
| Agent 级 hook | `src/agent/externalHooks/externalHooksService.ts` |
| Session 级适配 | `src/session/externalHooks/` |
| Hook 配置 | config.toml 的 `[[hooks]]` |

## 参考资料

- [04-subagent.md](04-subagent.md) —— SubagentStart/Stop hook
- [06-tool-system.md](06-tool-system.md) —— PreToolUse hook 是 policy 之一
- [09-loop.md](09-loop.md) —— Loop hooks 机制
