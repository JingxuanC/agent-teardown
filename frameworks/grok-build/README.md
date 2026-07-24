# Grok Build 拆解

Grok Build(`grok`)是 SpaceXAI 的终端 AI coding agent —— Rust 实现,134 万行,70+ crate。本目录是对其源码的逐模块拆解。

**仓库**:本地 `~/grok-build/`(从 SpaceXAI monorepo 同步)
**官方文档**:https://docs.x.ai/build/overview

## 拆解路线图

| # | 模块 | 状态 | 核心问题 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | crate 分层 + 和 kimi-code 对比 |
| 02 | [Doom Loop 检测](02-doom-loop.md) | ✅ | 服务端信号 + mid-stream abort + 预算化恢复 |
| 03 | [Skeptic Panel](03-skeptic-panel.md) | ✅ | goal 完成的对抗验证(majority-refute) |
| 04 | [Permission + Sandbox](04-permission-sandbox.md) | ✅ | shell 解析 + ML 分类器 + nono 物理隔离 |
| 05 | [Sampler](05-sampler.md) | ✅ | 三种 API + xAI 深度集成 + circuit breaker |
| 06 | [Loop + Persistence + Subagent + TUI](06-loop-persistence-subagent-tui.md) | ✅ | MvpAgent + JSONL/SQLite + 子 agent + ratatui |

## 关键发现速览

- **对抗性不信任是核心哲学**:skeptic panel 让 goal 完成要过 N 个独立 agent 的交叉验证。
- **Doom Loop 检测是独有创新**:服务端发信号 + 客户端 mid-stream abort。
- **双层安全**:permission(shell 解析 + ML 分类器)+ sandbox(nono Landlock/Seatbelt)。
- **Circuit Breaker**:滑动窗口熔断器,防止 provider 故障时疯狂重试。
- **SQLite + checkpoint**:比 wire.jsonl 全量重放更快,支持 SQL 查询。
- **xAI 深度集成**:x-grok-* headers 做追踪 + doom loop + 路由。
- **Rust 所有权系统**:编译时消除循环引用 / 数据竞争 / 空指针。
- **134 万行 vs kimi-code 的 10 万行**:功能更全(dashboard/图片/mermaid/sandbox),但复杂度也高一个量级。
