# Vela Shopify Agent — 深度拆解总览(v2,源码级)

> 本文档替换之前 `_archive-shallow/` 里太浅的版本。之前的拆解主要看了 HTTP handler 骨架,
> 错误地结论"Vela 没有多 agent 系统"——实际上 `service/multiagent/`(15 文件)、
> `service/autogoal/`(24 文件)、`service/orchestrator/`(28 文件)、`service/agent/`(169 文件)
> 构成了一个完整的生产级多 agent + 自治目标平台。本次重写全部基于 codegraph 读取的真实源码 +
> 4 份正式 ADR 设计文档(`docs/adr/0001-0004`)。

## 0. 先纠正我之前的三个错误判断

| 之前说的 | 真实情况(源码验证) |
|---|---|
| "Vela 没有多 agent,只是单 agent + DAG 工具编排" | 错。`service/multiagent/`(ADR 0003)实现了 **DAG-of-Agents**:DAG 节点既可以是 tool 也可以是 **agent**(`DAGNode.Agent *AgentNodeSpec`),有共享黑板 `MultiAgentWorkspace`、`Coordinator` 分解 meta-goal、`LLMDecomposer` 拆 2-4 子目标、`DAGRun`+`DAGNodeState` 持久化支持崩溃恢复 |
| "记忆是简单的 reflect+decay" | 严重低估。真实是 **Mem0 式加性抽取**:5 步 Reflect 循环(PG advisory lock 保护)、半衰期衰减(90d/30d/7d/1d 四档)、三级 scope(agent/shop/session)、entity_tags、content_hash 去重 → Qdrant 语义去重(0.95 阈值)→ PG ILIKE 兜底、novelty entropy 触发判定 |
| "MCP 就是调外部工具" | 错。Vela 是 **MCP 双向**:既是 MCP **server**(`platform/mcp/protocol.go` 的 stdio `Server`,把自己的 87+ 工具暴露给 Codex 等),又是 MCP **client**(`MCPConnectionManager` 按 shop 管理外部 MCP 连接,工具名 `mcp:{conn}:{tool}`),还实现了 **MCP Apps**(ADR 0006,`_meta.ui.resourceUri` + `ReadResource` 渲染 iframe 面板) |

## 1. 系统全景:四层 ADR 驱动的架构

Vela 不是"写出来的",是"设计出来的"——`docs/adr/` 有 4 份正式架构决策记录,代码里反复引用:

| ADR | 标题 | 核心决策 | 代码落点 |
|---|---|---|---|
| **0001** | Unified Prompt Context Provider | 提取 `PromptContextProvider` 作为 V1/V3 共享的 prompt 上下文单一真相源(7 层组装,Redis 静态层缓存 + 动态层实时加载) | `service/agent/prompt/provider.go` |
| **0002** | Agent Execution Unification | 引入 `ExecutionStrategy` 抽象,5 条独立执行路径 → 6 个可切换策略,`Agent.Run` 成为唯一入口,控制流下沉 service 层 | `service/agent/strategy/{chat,singlepass,react,plan,goalloop}.go` |
| **0003** | Multi-Agent Architecture | DAG-of-Agents + 共享黑板 + eventbus 混合模型。复用 DAG 引擎,把"节点=工具"扩展成"节点=工具**或**agent" | `service/multiagent/`, `service/orchestrator/orchestrator_agent.go` |
| **0004** | Autonomous Goal Loop + Steering | Goal = 持久状态机 + per-goal 对话线程 + 进度视图三位一体。前台 React + 后台 Loop + 在线 steering | `service/autogoal/`, `model/autogoal.go` |
| (0006) | MCP Apps | 代码引用但 ADR 文档未见,工具可通过 `_meta.ui.resourceUri` 声明前端渲染面板 | `platform/mcp/protocol.go`, `handler/mcp_ui_bundles.go` |

## 2. 分层地图

```
┌─────────────────────────────────────────────────────────────────┐
│  HTTP Gateway(middleware/gateway.go)                            │
│  多 auth(Shopify JWT / Merchant JWT / Internal token)            │
│  跨租户隔离 · feature flag · 配额 · 分级限流                       │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Handler 层(薄壳,ADR 0002 Phase 0.6)                            │
│  agent_execute*.go(14 文件)· agent_gateway.go · autogoal_handler │
│  → 解析请求 → 组 AgentRequest → 流式 SSE                         │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Agent.Run 唯一入口(ADR 0002)                                    │
│  ┌─────────── 6 个 ExecutionStrategy ───────────┐               │
│  │ Chat · SinglePass · ReAct · Plan · GoalLoop   │               │
│  │ (+ v3Agent 备选实现)                           │               │
│  └────────────────────────────────────────────────┘               │
│  共享横切:Guard · AutonomyGate · ConflictDetector ·               │
│           CircuitBreaker · Synthesizer · MemoryRecall ·           │
│           PromptContextProvider                                   │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Oracle 意图路由(orchestrator/oracle.go)                         │
│  intent: chat | tool_call | plan                                 │
│  + domain classification(>20 工具时收窄到 10-15 个)               │
│  + tool budget filter(防 prompt 膨胀)                            │
│  + conflict context injection · tool_search 恢复                  │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Multi-Agent 编排层(ADR 0003)                                    │
│  Coordinator → LLMDecomposer(拆 2-4 子目标)                      │
│  → DAG-of-Agents(节点 = tool 或 agent)                           │
│  → MultiAgentWorkspace(共享黑板:metaGoal + findings)             │
│  → DAGRun + DAGNodeState(持久化,崩溃恢复)                        │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Autonomous Goal Loop(ADR 0004)                                  │
│  Scheduler(tick 调度 · 并发上限 · PG advisory lock 多副本去重      │
│           · cancelBroadcaster 跨副本中断)                         │
│  → GoalEngine.Advance(读 steering → execute → verify →            │
│                       reflect → 摘要入会话 → persist)             │
│  → Goal 状态机(active/paused/completed/failed/stalled/review)    │
│  → per-goal 对话线程(advisory / interrupt steering)               │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  DAG 引擎(orchestrator/orchestrator.go)                         │
│  BuildDAG · ReadyNodes(拓扑)· executeWithRetry(3次+退避)         │
│  · AutonomyGate.Filter(Auto/Suggest/Confirm 三队列)              │
│  · BuildExecutableDAG(剪除 CONFIRM 依赖)                         │
│  · SSE 事件流(agent_card_update · MCP Apps 面板)                 │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  ToolRegistry(87+ 工具)· MCP 双向(server+client)                │
│  Skill 三层:MerchantSkill(DB)· AgentSkill(运行时注入)            │
│             · Codex catalogue(外部)                              │
│  9 Persona(退货/库存/评价/SEO/定价/内容/客户洞察/营销/数据)       │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  Memory:Reflector(Mem0 式)· DecisionStore · Qdrant · RRF          │
│  Facts(halflife 衰减 · 3 级 scope · entity_tags)                 │
│  Insights(category · confidence · source_refs)                   │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  LLM Provider:LLMRouter(per-shop 模型解析)                       │
│  DashScopeProvider 基类 ← DeepSeek/Grok/Kimi/OpenAI(embed)       │
│  CircuitBreaker · Usage 计费 · Metrics                            │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 与其他 6 个框架的关键差异

| 维度 | Vela | kimi-code | grok-build | Codex |
|---|---|---|---|---|
| **语言** | Go | TypeScript | Rust | Rust |
| **多 agent** | DAG-of-Agents + 共享黑板(ADR 0003) | Swarm + Subagent + Goal mode | Subagent + worktree | ExecPolicy + 多 agent |
| **目标持久化** | Goal 状态机 + per-goal 会话(ADR 0004) | Goal mode(会话级) | Goal complete(6 子系统) | 无独立目标层 |
| **记忆** | Mem0 式 Reflect + halflife 衰减 | Session metadata + blob | wire Op 事件源 | Stage1+Stage2 双阶段 |
| **权限** | AutonomyGate(4 规则分级) | DI × Scope | Permission + sandbox | ExecPolicy DSL |
| **MCP** | **双向**(server + client + Apps) | MCP 客户端 | 扩展系统 | 无 |
| **分布式** | PG advisory lock + 跨副本 cancel 广播 | 单机 | 单机 | 单机 |
| **loop 中断** | ctx.Cancel + 跨副本 pub/sub | — | doom loop 检测 | — |

**Vela 独有的亮点**:
1. **分布式自治目标调度**——多副本部署下,PG advisory lock 防止同一 goal 被双跑,cancelBroadcaster 让一个副本的 Cancel 信号秒级传到真正在跑的副本。这是 7 个框架里唯一考虑了水平扩展的。
2. **MCP Apps**——不只是调工具,还能让 MCP 工具声明前端渲染面板(`_meta.ui.resourceUri`),通过 `ReadResource` 拉 `ui://` bundle 在 iframe 里渲染。把 MCP 从"工具协议"升级成"应用协议"。
3. **domain classification + tool budget**——当工具目录膨胀到 130+(MCP + 商户自定义),Oracle 先做一次 ~20 token 的领域分类把工具收窄到 10-15 个,再做路由。用一次便宜调用省掉多轮错误工具的 React。
4. **半衰期记忆衰减**——Facts 带 `halflife_hours`(90d/30d/7d/1d 四档),不是简单的 TTL 删除,而是按业务语义分级衰减。

## 4. 后续深度文档索引

| 文档 | 主题 |
|---|---|
| [01-skill-prompt-persona.md](01-skill-prompt-persona.md) | Skill 三层 + Prompt 7 层 + 9 Persona 协作图 |
| [02-mcp-dual-direction.md](02-mcp-dual-direction.md) | MCP server + client + Apps + Codex Router |
| [03-memory-reflect-decay.md](03-memory-reflect-decay.md) | Reflector 5 步 + halflive 衰减 + Qdrant 去重 + RRF |
| [04-react-oracle-gate.md](04-react-oracle-gate.md) | Oracle 路由 + ReAct 双实现 + AutonomyGate 4 规则 |
| [05-multiagent-autogoal.md](05-multiagent-autogoal.md) | DAG-of-Agents + 分布式 Scheduler + Steering |
| [06-gateway-context-llm.md](06-gateway-context-llm.md) | HTTP Gateway + UnifiedContext + LLM Provider |

## 5. 验证方法

本文档集所有结论均通过以下方式验证:
- **codegraph**(`~/vela-shopify/.codegraph`,1391 Go 文件,索引 7/21)读取真实源码,引用均为 `文件:行号`
- **4 份 ADR**(`docs/adr/0001-0004`)对照设计意图
- **代码注释**——Vela 代码注释质量极高,大量"Phase X.Y"、"ADR 000N §M"标注,可直接追溯设计决策

> 源码位置:`~/vela-shopify/api-server-go/`(主代码)· module `github.com/JingxuanC/vela-ai-api` · Go 1.26
