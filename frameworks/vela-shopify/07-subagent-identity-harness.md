# 07 — 子 Agent 身份隔离:AgentNodeSpec + Harness + ServiceRegistry

> 这是之前完全漏掉的核心子系统。子 agent 在 DAG-of-Agents 里被执行时,怎么知道"我是谁"、能用哪些工具、读哪些记忆、受什么约束。

## A. 核心问题:子 agent 需要什么身份?

当一个 meta-goal 被 Coordinator 拆成多个子目标,每个子目标分配给一个 persona(如"SEO 专家"、"库存专家"),这个子 agent 跑起来时需要:

1. **身份** — 我是哪个 persona?持久 agentID 是什么?(影响计费和记忆归属)
2. **工具白名单** — SEO 专家只能用 SEO 工具,不能碰退款操作
3. **硬约束** — "折扣不超过 30%"、"不直接联系客户"
4. **记忆隔离** — SEO agent 召回的历史决策应该是 SEO 相关的,不能串到库存的
5. **上下文** — 元目标是什么、前序 agent 发现了什么(共享黑板)
6. **Skill** — 该 persona 能激活哪些 MerchantSkill

Vela 用一套精密的机制回答了这六个问题。

---

## B. AgentNodeSpec:Harness 五件套(身份+约束)

**源码**:`internal/service/orchestrator/orchestrator_agent.go:18`

```go
type AgentNodeSpec struct {
    ID       string     // DAG 节点 ID("step_0")
    Goal     string     // 子目标(喂给子 Agent.Run 作为 message)
    GoalID   *uuid.UUID // ★ goal-scoped memory:属于哪个长周期 Goal(nil = 非目标)
    Strategy string     // "auto"|"react"|"plan"|"goal_loop"|"chat"
    Persona  string     // 角色名("seo","content","inventory")

    // ── Harness:身份 + 约束(Phase 5 per 阿里 Harness 支柱①)──
    HarnessName        string   // 人可读 persona 名("退货分析师")
    HarnessExpertise   string   // 领域专长描述
    HarnessTools       []string // ★ 工具白名单(空 = 全部工具)
    HarnessConstraints []string // ★ 硬规则:"绝对不能做X"
    HarnessWorkflow    string   // 偏好执行模式
}
```

注释明确写了 **"Phase 5 per 阿里 Harness 支柱①"**——这说明设计参考了阿里在 agent harness 方面的实践。

**HarnessTools 是关键**:它是工具白名单。空数组 = 该子 agent 能用所有工具;非空 = 只能用列出的工具。配合 PersonaDef.Tools(见 [01-skill-prompt-persona.md](01-skill-prompt-persona.md) §C),实现了**双重工具限制**:Persona 声明 + 节点级 Harness 覆盖。

---

## C. AgentRunner.Run:身份注入的完整链路

**源码**:`internal/service/multiagent/runner.go:136`

这是子 agent 被执行的入口。完整流程:

### C1. 持久 agentID 解析(Phase 0)

```go
// runner.go:159
var agentID *uuid.UUID
if a.registry != nil && spec.Persona != "" {
    id, err := a.registry.ResolveAgentID(ctx, a.shopID, spec.Persona)
    // 把 persona 名解析成持久 agent UUID
    agentID = id
}
```

`AgentRegistry.ResolveAgentID`(`agentResolver` 接口,`runner.go:84`)把 persona 字符串映射到持久的 agent UUID。这意味着同一个 shop 的"SEO 专家"在不同 DAG run 里是**同一个 agent 身份**——它的记忆是累积的。

### C2. per-agent Service 解析(Phase 4)

```go
// runner.go:172
svcBundle := a.serviceBundle
if a.serviceReg != nil && agentID != nil {
    svcBundle = services.MergeBundles(a.serviceBundle, a.serviceReg.Resolve(a.shopID, agentID))
}
```

**`ServiceRegistry.Resolve` 三级解析**(`services/registry.go`):
```
解析顺序:agent-specific → shop-specific → global default
```

每个 agent 可以有**自己的 MemoryService / PromptService / MCPService**。`MergeBundles` 做 field-by-field 合并——agent-specific 的字段覆盖共享 bundle 的同名字段,其余继承。

这意味着:SEO agent 和库存 agent 可以挂载不同的记忆后端、不同的 prompt 模板、不同的 MCP 连接,完全隔离。

### C3. 沙箱边界(Phase 5)

```go
// runner.go:188
if req.Services.Sandbox != nil {
    s, err := req.Services.Sandbox.Acquire(ctx, services.SandboxSpec{
        AgentID:  spec.Persona,
        TaskID:   spec.ID,
        Timeout:  120 * time.Second,
        Tools:    spec.HarnessTools,   // 工具白名单传给沙箱
        Registry: a.toolRegistry,
    })
    sbox = s
    defer req.Services.Sandbox.Release(ctx, sbox.ID)
    if sbox.Deadline.After(time.Now()) {
        ctx, cancel = context.WithDeadline(ctx, sbox.Deadline)
    }
    granted = sandboxToolNames(sbox.Tools)  // 沙箱实际授予的工具
}
```

沙箱分两种路径(见 §D)。

### C4. ★ 工具白名单注入 context

```go
// runner.go:223
remote := sbox.IsRemote()
if !remote {
    if whitelist := effectiveToolWhitelist(spec.HarnessTools, granted); len(whitelist) > 0 {
        ctx = orchestrator.WithToolWhitelist(ctx, whitelist)
    }
}
```

`effectiveToolWhitelist`(`runner.go`)取 **HarnessTools 和沙箱授予工具的交集**——沙箱只会收窄,不会放宽。

这个白名单通过 `WithToolWhitelist` 注入 context,Oracle 在路由时通过 `ToolWhitelistFrom(ctx)` 读取并过滤(见 §E)。**子 agent 的 Oracle 只能看到白名单里的工具**,从源头防止越权。

### C5. 构建 AgentRequest

```go
// runner.go:178
req := strategy.AgentRequest{
    ShopID:   a.shopID,
    AgentID:  agentID,        // ★ 持久身份(计费+记忆)
    GoalID:   spec.GoalID,    // ★ goal-scoped memory
    Message:  message,        // workspace.BuildAgentContext() + Goal
    Mode:     mapStrategyMode(spec.Strategy),
    Persona:  spec.Persona,
    Services: svcBundle,      // ★ per-agent 服务集
}
```

### C6. 消息构建(workspace + goal)

```go
// runner.go:155
message := a.buildMessage(spec)
```

`buildMessage` 把 `MultiAgentWorkspace.BuildAgentContext()`(meta-goal + 前序 findings)和子目标拼接成子 agent 的消息。这让子 agent 知道大局 + 前序进展。

### C7. 结果捕获为 finding

```go
// runner.go:258
if a.workspace != nil {
    a.workspace.AddFinding(AgentFinding{
        Persona: spec.Persona,
        Goal:    spec.Goal,
        Summary: resp.Summary,
        Score:   resp.Succeeded * 25,  // 0-100 自评
    })
}
```

子 agent 跑完后,输出被写成 `AgentFinding` 加到共享黑板,供下游 agent 读取。

### C8. 持久化节点状态

```go
// runner.go:147 + 268
a.dagStore.StartNode(ctx, a.dagRunID, spec.ID)    // 开始
a.dagStore.CompleteNode(ctx, a.dagRunID, spec.ID, ...) // 完成
```

每个节点状态变化都持久化到 `DAGNodeState` 表——崩溃后另一个副本能恢复。

---

## D. 沙箱双路径:本地白名单 vs 远程子进程

**源码**:`runner.go:289`(`executeRemoteSandbox`)

### D1. 本地路径(白名单)

当沙箱是 `inproc` 或 `goroutine` 类型:
- `WithToolWhitelist` 注入 context
- Oracle 的 `filterToolsByWhitelist` 过滤工具列表
- 子 agent 在同进程跑,通过 context 传播白名单

### D2. 远程路径(子进程 + AgentGateway)

当沙箱是 `remote` 类型(`sbox.IsRemote() == true`):

```go
// runner.go:289
func executeRemoteSandbox(ctx, sbox, req) (*strategy.AgentResponse, error) {
    payload := services.SandboxRequest{
        ShopID:     req.ShopID.String(),
        Message:    req.Message,
        Persona:    req.Persona,
        GatewayURL: sbox.ServiceURL,  // ★ AgentGateway URL
    }
    if req.AgentID != nil {
        payload.AgentID = req.AgentID.String()
    }
    // 编码到子进程 stdin → 等待 stdout 响应
    json.NewEncoder(sbox.Writer).Encode(payload)
    sbox.Writer.Close()  // EOF
    json.NewDecoder(sbox.Reader).Decode(&sresp)
}
```

**远程子进程是自治的**——它通过 AgentGateway 挂载自己的 services + MCP 工具,执行自己的 AutonomyGate 策略。父进程**不传工具白名单**(注释 `runner.go:220`:"the child process is autonomous (MCP-only tools mounted via the gateway + its own AutonomyGate), so the parent-side whitelist constrains the local path only")。

**这就是"AgentGateway"的真正含义**:它是远程沙箱子进程挂载 Vela 服务(MCP 工具、记忆、prompt)的 HTTP 入口。子进程通过 Gateway URL 认证身份 + 获取该 agent 配置的服务。

---

## E. 工具白名单的 Oracle 消费

**源码**:`internal/service/orchestrator/tool_whitelist_context.go` · `oracle.go:246`

```go
// tool_whitelist_context.go — 零依赖的 context plumbing
func WithToolWhitelist(ctx context.Context, whitelist []string) context.Context {
    return context.WithValue(ctx, toolWhitelistKey{}, whitelist)
}
func ToolWhitelistFrom(ctx context.Context) []string {
    v, _ := ctx.Value(toolWhitelistKey{}).([]string)
    return v  // nil = "all tools"
}

// oracle.go:246 — Oracle 路由时消费
shopTools := o.registry.ListForShop(shopID)
shopTools = filterToolsByWhitelist(shopTools, ToolWhitelistFrom(ctx))
// ★ 子 agent 的 Oracle 只看到白名单工具,从源头防越权
```

`filterToolsByWhitelist`(`oracle_tool_filter.go:41`)逻辑简单但关键:白名单空 = 全部工具(主 agent 默认);白名单非空 = 只保留列出的工具。

---

## F. agentctx:零依赖的身份传播

**源码**:`internal/service/agent/agentctx/agentctx.go`

这是整个隔离系统的底层基础设施——一个**零依赖**的 context key 包。

```go
// agentctx.go:1 — 包注释
// Package agentctx carries the billing identity (agent ID, shop ID) through
// context so deep call sites — LLM providers, the MCP billing decorator — can
// attribute usage to the right agent without changing every signature along
// the way. Agent is pure compute; memory/context/prompt/MCP mount and bill
// by agentID.
//
// The package has zero internal dependencies on purpose: it sits at the
// bottom of the import graph so every layer (agent, llm, services, handler,
// server) can use it without import cycles.
```

**为什么零依赖**:`toolcontext` 包已经存在,但它 import 了 llm/memory/infra——如果 agentctx 放在那里,会形成 import cycle(agent → llm → agentctx → toolcontext → memory → agent)。所以 agentctx 独立出来,只依赖 `context` 和 `uuid`。

### F1. Agent.Run 注入身份

```go
// service/agent/run.go:113
func (a *Agent) Run(ctx, req strategy.AgentRequest, sse AgentSSEWriter) {
    if req.AgentID != nil {
        ctx = agentctx.WithAgentID(ctx, req.AgentID)  // ★ 注入持久身份
    }
    // 之后所有 LLM/MCP 调用都带着这个 agentID 计费
}
```

### F2. BillingMCPService 消费身份

**源码**:`internal/service/agent/services/billing_mcp.go:28`

```go
// 装饰器模式:包装真实 MCPService,加计费层
type BillingMCPService struct {
    inner    MCPService      // 真实 MCP 连接管理器
    recorder UsageRecorder   // 计费 sink
}

func (b *BillingMCPService) CallTool(ctx, shopID, fullToolName, args) (string, error) {
    result, err := b.inner.CallTool(ctx, shopID, fullToolName, args)
    if err != nil { return result, err }  // 失败不计费

    b.recorder.RecordAsync(ctx, infra.UsageRecord{
        ShopID:    shopID,
        AgentID:   agentctx.AgentIDFrom(ctx),  // ★ 按 agent 计费(nil = shop 级)
        Feature:   "mcp",
        Operation: fullToolName,
        Count:     1,
    })
    return result, nil
}
```

注释明确:"Agent is pure compute; MCP mounts bill by agentID"——**Agent 本身不持有资源,资源(MCP/记忆/prompt)按 agentID 挂载和计费**。

---

## G. 记忆隔离:三级 Recall

**源码**:`internal/service/agent/memory/store.go:411`

子 agent 的记忆通过 `agentID` 过滤实现隔离,有三个粒度:

### G1. RecallByAgent(按 agent)

```go
// store.go:413
func (s *DecisionStore) RecallByAgent(ctx, shopID, agentID *uuid.UUID, query, topK) {
    // Qdrant 路径:SearchOptions.AgentID 过滤
    //   should: agent_id=? OR is_empty
    //   (legacy 无 agentID 的决策仍被召回)
    // PG fallback:WHERE agent_id = ? OR agent_id IS NULL
}
```

### G2. RecallByAgentGoal(按 agent + goal)

```go
// store.go:481
func (s *DecisionStore) RecallByAgentGoal(ctx, shopID, agentID, goalID *uuid.UUID, query, topK) {
    // 在 RecallByAgent 基础上加 goal_id 过滤
    // 一个长周期 Goal 只召回自己的历史决策,不串到其他 Goal
}
```

### G3. RecallEnrichedByAgentGoal(增强版)

```go
// store.go:548
func (s *DecisionStore) RecallEnrichedByAgentGoal(ctx, shopID, agentID, goalID, query, topK) string {
    // RecallByAgentGoal + enrichment(额外上下文增强)
    // 返回拼好的字符串,直接注入 prompt
}
```

**隔离语义**:`agent_id = ? OR agent_id IS NULL`——该 agent 自己的决策 + 没归属的 legacy 决策都会被召回。这保证向后兼容(老数据没有 agentID 也能用),同时新数据按 agent 隔离。

### G4. RecallFacts 的 scope 优先级

```go
// store.go:385 — SQL 内联的半衰期衰减 + scope 排序
SELECT *, (confidence * POWER(0.5,
   EXTRACT(EPOCH FROM (NOW()-created_at)) / (3600.0 * GREATEST(halflife_hours,1))
)) AS decay_score
FROM agent_facts
WHERE status = 'active' AND (shop_id = ? OR scope = 'agent')
ORDER BY
  CASE scope WHEN 'shop' THEN 0 WHEN 'agent' THEN 1 ELSE 2 END,
  decay_score DESC
```

Facts 的召回:
- **scope=agent 的全局共享**(所有 shop 可见,跨 agent)
- **scope=shop 的本店专属**
- **scope=session 的临时**(优先级最低)
- 按 **实时半衰期衰减**排序(SQL 内联计算,不需要应用层)

---

## H. ServiceRegistry:三级服务解析

**源码**:`internal/service/agent/services/registry.go:47`

```go
type ServiceRegistry struct {
    memory  map[string]MemoryService  // key: "default" | agentID.String()
    mcp     MCPService                // 单实例(per-shop 过滤内建)
    skills  SkillService              // 单实例
    context ContextService            // 单实例
    prompt  map[string]PromptService  // key: "default" | agentID.String()
    sandbox map[string]SandboxService // key: "inproc"|"goroutine"|"remote"
}
```

**解析顺序**(注释 `registry.go:46`):`agent-specific → shop-specific → global default`

这意味着:
- 可以给"SEO agent"注册专属的 MemoryService(例如用不同的 Qdrant collection)
- 可以给"库存 agent"注册专属的 PromptService(不同的 prompt 模板)
- 没注册的 agent 走 "default" 全局服务

### H1. ServiceBundle(每次请求注入)

```go
// registry.go:17
type ServiceBundle struct {
    Memory  MemoryService
    MCP     MCPService
    Skills  SkillService
    Context ContextService
    Prompt  PromptService
    Sandbox SandboxService
}
```

Handler 层每次请求时从 ServiceRegistry 解析出 ServiceBundle,注入 `AgentRequest.Services`。Agent.Run 优先用注入的 Services,零值时降级到内置默认(`IsZero()` 判断)。

### H2. MergeBundles(field-by-field 合并)

`runner.go:174`:
```go
svcBundle = services.MergeBundles(a.serviceBundle, a.serviceReg.Resolve(a.shopID, agentID))
```

共享 bundle + agent-specific bundle 合并,agent-specific 的字段覆盖同名共享字段。这让"大部分服务共享,少数 per-agent 定制"变得简单。

---

## I. Skill 在子 agent 里怎么工作

子 agent 的 Skill 激活路径:

1. **MerchantSkill**(DB)→ 按 shop + 关键词匹配 → AgentSkill(运行时)
2. **skillsProvider 回调**(Oracle 路由时)→ 注入到 system prompt 的 skillsBlock
3. 子 agent 因为 `WithToolWhitelist` 只看到白名单工具,**如果某 skill 引用的工具不在白名单里,该 skill 实际无法执行**(虽然 prompt 里提到了它)

这是隐式约束——**Persona.HarnessTools 决定了哪些 skill 真正可用**。

---

## J. 完整身份注入链路(一图)

```
Coordinator 分解 meta-goal
  → LLMDecomposer 产出 []AgentStep{Goal, Persona, Strategy}
  → 每个 AgentStep → AgentNodeSpec{Harness* 字段从 PersonaDef 填充}

Orchestrator.Execute 遇到 DAGNode.Agent != nil
  → executeAgentNode(不重试,因为 agent 贵)
  → 调 AgentRunner.Run(ctx, spec)

AgentRunner.Run:
  1. ResolveAgentID(persona → 持久 agentID)
  2. MergeBundles(共享 + per-agent services)
  3. Sandbox.Acquire(HarnessTools)
  4. WithToolWhitelist(ctx, 交集白名单)
  5. buildMessage(workspace.BuildAgentContext + Goal)
  6. AgentRequest{AgentID, GoalID, Persona, Services, Message}
  7. Agent.Run(ctx, req)
     → agentctx.WithAgentID(ctx, agentID)  // 身份传播到最深层
     → Oracle.Route(filterToolsByWhitelist 消费白名单)
     → LLM 调用(带 agentID 计费)
     → MCP 调用(BillingMCPService 按 agentID 计费)
     → DecisionStore.RecallByAgentGoal(agentID + goalID 过滤记忆)
     → PromptContextProvider.Build(per-shop prompt)
  8. 输出 → AgentFinding → workspace.AddFinding
  9. dagStore.CompleteNode(持久化)
```

---

## K. 与 kimi-code / grok-build 的对比

| 维度 | Vela | kimi-code | grok-build |
|---|---|---|---|
| **子 agent 身份** | 持久 agentID(persona→UUID 映射) | 无持久身份 | subagent_id |
| **工具隔离** | HarnessTools 白名单 + Oracle 过滤 | DI Scope | worktree 物理隔离 |
| **记忆隔离** | agentID + goalID 双重过滤 | session metadata | wire Op scope |
| **服务隔离** | ServiceRegistry 三级解析 + MergeBundles | DI 容器 | — |
| **计费隔离** | agentctx 传播 → BillingMCPService | — | — |
| **沙箱** | 本地白名单 + 远程子进程双路径 | — | permission + sandbox |
| **设计参考** | 注释标注"阿里 Harness 支柱" | — | — |

**Vela 的独特设计**:
1. **持久 agentID**——同一个 persona 在不同 run 里是同一个身份,记忆累积。kimi/grok 的子 agent 都是一次性的。
2. **agentctx 零依赖包**——为了打破 import cycle 专门独立出来,这种工程细节体现了对"身份传播到每一层"的重视。
3. **远程沙箱自治**——远程子进程不靠父进程传白名单,而是通过 AgentGateway 自己挂载服务 + 自己跑 AutonomyGate。这是真正的"agent 自治",不是"父控制子"。

---

## L. 我为什么漏了这个

之前扒 `handler/agent_gateway.go` 时,我只看了 HTTP 入口(鉴权、SSE 流式),没追到"子 agent 在 DAG 里怎么获得身份"这条链。真正的"Agent Gateway"不是那个 HTTP handler,而是:

1. **`AgentNodeSpec.Harness*`** — 子 agent 的身份+约束声明
2. **`AgentRunner`** — 身份注入的执行器
3. **`WithToolWhitelist` + `agentctx`** — 身份的 context 传播
4. **`ServiceRegistry`** — per-agent 服务解析
5. **`BillingMCPService`** — 按 agentID 计费的装饰器
6. **远程沙箱的 AgentGateway URL** — 子进程挂载服务的入口

这六层合起来才是完整的"子 agent 身份网关"。我的错误是只看了第零层(HTTP),没追进去。
