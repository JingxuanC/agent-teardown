# Grok Build 拆解

Grok Build(`grok`)是 SpaceXAI 的终端 AI coding agent —— Rust 实现。本目录是对其源码的逐模块拆解。

**仓库**:本地 `~/grok-build/`(从 SpaceXAI monorepo 同步)
**官方文档**:https://docs.x.ai/build/overview
**拆解基线**:`SOURCE_REV` 记录的 monorepo commit(2026-07)

## 拆解路线图

| # | 模块 | 状态 | 核心问题 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | crate 分层 + 和 kimi-code 对比 |
| 02 | [Doom Loop 检测](02-doom-loop.md) | ✅ | 服务端信号 + mid-stream abort + 预算化恢复 |
| 03 | Skeptic Panel | ⏳ | goal 完成的对抗验证 |
| 04 | Permission + Sandbox | ⏳ | shell parser + 双层防护 |
| 05 | Sampler(LLM 调用) | ⏳ | SSE 解析 + circuit breaker |
| 06 | Agent Loop | ⏳ | MvpAgent + LocalSet + CancellationToken |
| 07 | Persistence(SQLite) | ⏳ | journal + checkpoint + WAL |
| 08 | Worktree + VCS | ⏳ | fast worktree + git 集成 |
| 09 | TUI(ratatui) | ⏳ | scrollback + dashboard + 流式渲染 |
| 10 | Subagent | ⏳ | coordinator + spawn + isolation |

## 关键发现速览

(拆解过程中沉淀的"啊哈"时刻)

- **对抗性不信任是核心哲学**:skeptic panel 让 goal 完成要过 N 个独立 agent 的交叉验证,不是"信任 LLM 自报"。
- **Doom Loop 检测是独有创新**:服务端发信号 + 客户端 mid-stream abort,grok-build 能实时检测并中断 agent 的重复死循环。kimi-code 只有事后 max_steps。
- **双层安全**:permission(逻辑层)+ sandbox(物理层),比 kimi-code 单层更安全。
- **Circuit Breaker 应用到 agent**:HTTP 熔断器保护 agent 不在 provider 故障时疯狂重试。
- **SQLite + checkpoint 替代事件溯源**:比 wire.jsonl 全量重放更快,支持 SQL 查询。
- **Rust 的所有权系统 = 编译时正确性保证**:循环引用、数据竞争、空指针在编译时消除,不靠运行时检查。
