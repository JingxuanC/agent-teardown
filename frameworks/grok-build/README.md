# Grok Build 拆解

Grok Build(`grok`)是 SpaceXAI 的终端 AI coding agent —— Rust 实现,134 万行,70+ crate。本目录是对其源码的逐模块拆解。

**仓库**:本地 `~/grok-build/`(从 SpaceXAI monorepo 同步)
**官方文档**:https://docs.x.ai/build/overview

## 拆解路线图(10 篇,全部完成)

| # | 模块 | 状态 | 核心内容 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | 70+ crate 分层 + 和 kimi-code 对比 |
| 02 | [Doom Loop 检测](02-doom-loop.md) | ✅ | 服务端信号 + mid-stream abort + 预算化恢复 |
| 03 | [Skeptic Panel](03-skeptic-panel.md) | ✅ | goal 完成的对抗验证(majority-refute) |
| 04 | [Permission + Sandbox](04-permission-sandbox.md) | ✅ | shell 解析 + ML 分类器 + nono 物理隔离 |
| 05 | [Sampler](05-sampler.md) | ✅ | 三种 API + xAI 深度集成 + circuit breaker |
| 06 | [Loop + Persistence + Subagent + TUI](06-loop-persistence-subagent-tui.md) | ✅ | MvpAgent + JSONL/SQLite + ratatui |
| 07 | [Goal 完整系统](07-goal-complete.md) | ✅ | 6 子系统 + 7 prompt + 7 状态 + stop detector |
| 08 | [两遍压缩](08-compaction-two-pass.md) | ✅ | pass1(95%)→NOTE₁,pass2(NOTE₁+5%tail)→NOTE₂ |
| 09 | [Worktree Pool + VCS](09-worktree-pool-vcs.md) | ✅ | 预创建池 + 原子 claim + hunk tracker + gix |
| 10 | [工具+信号+扩展系统](10-tools-signals-extensions.md) | ✅ | BM25搜索+TDigest信号+marketplace+memory+voice+computer-use+mermaid |

## 关键发现速览

(从拆解中沉淀的洞察)

### vs kimi-code:广度 vs 深度

**grok-build 赢在广度**(kimi-code 没有的):
- Doom loop 检测(服务端 + mid-stream abort)
- Skeptic panel(对抗验证 goal 完成)
- 双层安全(permission + sandbox)
- Circuit breaker(熔断器)
- 两遍压缩(pass1 95% → pass2 + tail)
- Worktree pool(预创建 + 原子 claim,macOS 优化)
- BM25 工具搜索(100+ 工具时全文检索)
- Goal stop detector(regex 检测过早放弃)
- Goal strategist(stall 时主动重组策略)
- Goal summarizer(完成后独立 subagent 写总结)
- Plugin marketplace(插件市场)
- 跨 session memory(长期记忆)
- 终端 Mermaid 渲染(不依赖 GitHub)
- Voice(语音输入/输出)
- Computer Use(控制鼠标键盘)
- Auto update(自动更新)
- Crash handler(崩溃报告)
- TDigest 信号统计(百分位 + RSS 采样)
- Slash 命令 Capability Gate(动态过滤)

**kimi-code 赢在深度**(grok-build 没有的):
- DI × Scope 架构(App/Session/Agent 三层生命周期)
- Wire Op/Model 事件溯源(可重放 + 可 diff)
- 七层测试 harness(scripted generate + assertedCallCount)
- 双轨道 eval(Terminal-Bench + LLM 自评)
- 手写 compaction handoff instruction(第一人称笔记)
- resolveExecution 两阶段工具执行(声明意图 → 权限 → 执行)
- 19 policy 权限责任链(可组合微内核)
- Flow skill(Mermaid 流程图驱动多轮)

### 工程哲学差异

| 维度 | kimi-code(Moonshot) | grok-build(SpaceXAI) |
|---|---|---|
| **信任模型** | 信任但验证 | **对抗性不信任** |
| **设计原则** | 优雅抽象 | **多重冗余** |
| **语言哲学** | TS 灵活快速 | Rust 编译时保证 |
| **工程文化** | 互联网产品 | **航天工程** |
| **代码量** | ~10 万行 | **~134 万行** |
| **功能策略** | 够用就好 | **大而全** |
