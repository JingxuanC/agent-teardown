# Kimi Code CLI 拆解

Kimi Code CLI 是 Moonshot AI 开源的终端 AI agent(`MoonshotAI/kimi-code`,TypeScript),由 Python 版的 `kimi-cli` 演化而来。本目录是对其架构的逐模块拆解。

**仓库**:https://github.com/MoonshotAI/kimi-code
**拆解基线**:`main` 分支(2026-07)
**本地路径**:`~/kimi-code`

## 拆解路线图

| # | 模块 | 状态 | 核心问题 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | DI × Scope 分层、wire 协议、agent lifecycle |
| 02 | [Swarm 群体智能](02-swarm.md) | ✅ | 如何启动 128 个并行 subagent,如何应对 rate limit |
| 03 | [Goal Mode 自治状态机](03-goal-mode.md) | ✅ | 四状态机 + continuation driver + 预算 + 错误停车 |
| 04 | [Subagent 系统](04-subagent.md) | ✅ | 扁平 lifecycle registry + 纯函数运行层 + 镜像事件层 |
| 05 | [Plan Mode 与权限沙箱](05-plan-mode.md) | ✅ | 规划/执行隔离 + 四种动态 reminder + 文件级 plan 产物 |
| 06 | [工具系统与权限责任链](06-tool-system.md) | ✅ | resolveExecution 两阶段 + 19 policy 责任链 + 资源冲突检测 |
| 07 | [Wire 协议与 Op/Model](07-wire-protocol.md) | ✅ | 事件溯源架构 + 持久化 + restore + migration 链 |
| 08 | [Context Memory 与 Compaction](08-context-memory.md) | ✅ | Full Compaction 第一人称 handoff + 窗口算法 + blob offload |
| 09 | [Agent Loop 主循环](09-loop.md) | ✅ | Prompt → Turn → Step 三层 + steer + step retry |
| 10 | [Skills 系统](10-skills.md) | ✅ | 四层来源 + frontmatter 解析 + flow 流程图 + 双向激活 |
| 11 | [MCP 集成](11-mcp.md) | ✅ | 三种 transport + 六状态机 + OAuth + attemptId 竞态保护 |
| 12 | [记忆管理与上下文注入](12-memory-and-injection.md) | ✅ | 四种存储接口 + system.md 模板 + 运行时 reminder |
| 13 | [CLI/TUI 渲染系统](13-tui-rendering.md) | ✅ | 脏标记节流 + 流式合并 + 折叠 + pi-tui 自研框架 |
| 14 | [Provider/kosong LLM 抽象](14-provider-llm.md) | ✅ | 5 provider 统一 + 流式归一 + 工具调用多路复用 |
| 15 | [错误系统](15-errors.md) | ✅ | Error2 + 去中心化 code 注册 + 边界翻译 + 序列化 |
| 16 | [ACP/IDE 集成](16-acp-ide.md) | ✅ | JSON-RPC over stdio + 图片压缩 + slash 拦截 |
| 17 | [插件系统](17-plugin.md) | ✅ | 标准 register API + 同进程无 sandbox |
| 18 | [Hook 系统](18-hooks.md) | ✅ | 外部脚本扩展点 + JSON in/out + 安全失败 |
| 19 | [Cron/定时任务](19-cron.md) | ✅ | isIdle 检查 + steer 注入 + stale 检测 + 持久化 |
| 20 | [Workspace/Session 生命周期](20-workspace-session.md) | ✅ | 三层组织 + fork + archive + workspaceId 派生 |
| 21 | [后台 Task 系统](21-task-background.md) | ✅ | shell/agent 两类 + 自动通知 + lost 状态 |
| 22 | [媒体/图片处理](22-media-image.md) | ✅ | 三层存储 + 1568px 压缩 + blob 去重 + 格式检测 |
| 23 | [Telemetry 与隐私](23-telemetry.md) | ✅ | 事件注册表 + 三层脱敏 + AsyncEventQueue |
| 24 | [测试 Harness 七层架构](24-harness-testing.md) | ✅ | 纯函数→时间注入→DI→scripted LLM→fake provider→ACP→E2E |
| 25 | [Agent 评测与基准测试](25-eval-benchmark.md) | ✅ | 双轨道:Terminal-Bench-2 标准 benchmark + LLM 自评(swarm 编排) |
| 03 | Goal Mode | ⏳ | 自治多轮驱动的状态机 |
| 04 | Subagent 系统 | ⏳ | spawn / resume / retry / scope 隔离 |
| 05 | Plan Mode | ⏳ | EnterPlanMode → ExitPlanMode 的权限沙箱 |
| 06 | 工具系统 | ⏳ | toolContract、权限规则、toolRegistry |
| 07 | MCP 集成 | ⏳ | 加载、权限、oauth |
| 08 | Cron / 定时任务 | ⏳ | session 级别持久化的 cron 调度器 |

## 关键发现速览

(拆解过程中沉淀的"啊哈"时刻,按发现时间倒序)

- **Loop 三层抽象**:Prompt(入队策略)→ Turn(生命周期)→ Step(LLM + 工具)。单 turn 串行,多 agent 并行(swarm)。详见 [09-loop.md](09-loop.md)。
- **Context Memory 的核心是 Full Compaction**:不是算法裁剪,而是让 LLM 给"未来的自己"写第一人称 handoff note。
- **架构地基 = DI × Scope 树 + Op/Model wire 协议**。三层 Scope(App/Session/Agent)+ "子可见父、父不可见子"的铁律,把几百个 service 组织成 DAG。详见 [01-architecture.md](01-architecture.md)。
- **循环依赖是硬约束**:容器主动抛 `CyclicDependencyError`,逼你重构,而不是用 Proxy 软化。这是非常强的设计立场。
- **Swarm 不是协作,是批处理**:128 个子 agent 各自独立工作,通过模板 + items 切片,不互相通信。真正的协作在 goal mode(单 agent 自治多轮)。
- **三层并发控制**:`INITIAL_LAUNCH_LIMIT=5`(启动期)→ `maxConcurrency`(整体)→ `rateLimitCapacity`(退避后的自愈容量)。
- **Rate limit 退避是独立的调度模式**:一旦 provider 返回 429,调度器切到完全不同的代码路径(`scheduleRateLimitLaunch` vs `scheduleNormalLaunch`),带容量自适应恢复。
- **Wire 协议 + Op/Model 架构**:所有状态变更都是可持久化、可重放的 Op,这让 session resume 天然 work。
- **Goal mode 四状态机极简**:active/paused/blocked/complete,但用"连续 3 轮才能 blocked"的审计阈值防止模型偷懒。
- **Plan mode 三层防护**:工具层(profile 不注册写工具)+ 运行层(运行时拒绝)+ 提示层(reminder)。
- **工具系统是 resolveExecution 两阶段**:让权限系统在执行前看到工具意图,而不是事后追责。
- **权限责任链 19 个 policy**:首个命中赢,但 approvalRule 带完整 payload 防止"批准一次永久授权"。

## 术语对照

| 中文 | 英文 | 说明 |
|---|---|---|
| 群体智能 | swarm mode | 一次启动多个并行 subagent 的模式 |
| 子代理 | subagent | 由主 agent spawn 出来的子 agent |
| 调度器 | scheduler / batch | 决定何时启动哪个 task 的组件 |
| 速率限制 | rate limit / 429 | provider 返回的请求频率限制 |
