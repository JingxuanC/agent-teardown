# 04 — Oracle 路由 + ReAct 双实现 + AutonomyGate 四规则

## A. Oracle:意图路由器(带领域分类 + 工具预算)

**源码**:`internal/service/orchestrator/oracle.go`

Oracle 是所有 agent 执行的入口——它决定一条消息是纯聊天、需要调工具、还是需要多步规划。

### A1. OracleResult 结构

```go
// oracle.go:38
type OracleResult struct {
    Intent     string   `json:"intent"`     // "chat" | "tool_call" | "plan"
    Reasoning  string   `json:"reasoning"`  // LLM 的决策解释
    Text       string   `json:"text"`       // chat 时的回复文本
    Stages     []Stage  `json:"stages"`     // tool_call 时的并行/串行工具组
    Steps      []string `json:"steps"`      // plan 时的多步目标字符串
    Confidence float64  `json:"confidence"` // LLM 自评置信度(0-1)
}
```

### A2. Route 方法的完整流程

`Route`(`oracle.go:206`)是核心路由逻辑,经过精心设计的多层过滤:

```
1. 构建 brand context(PromptContextProvider.Build)
   → BrandVoice + StoreIdentity + StorePolicy

2. 构建 skills block(skillsProvider 回调)
   → 匹配到的 MerchantSkill 描述

3. 列出 shop 工具(registry.ListForShop)
   → 应用白名单(子 agent HarnessTools 限制)

4. ★ 领域分类(当工具 >20 时)
   → domainClassifier.Classify(message) → domain
   → FilterByDomain(shopTools, domain) 收窄到 10-15 个
   → 一次 ~20 token 的便宜调用,省掉多轮错误工具的 React

5. ★ 工具预算过滤
   → filterToolsByBudget(shopTools, message, toolBudget)
   → 核心工具总是包含,非核心按关键词相关性排序
   → 防 MCP + 商户自定义工具让目录膨胀到 130+

6. 构建 system prompt
   BuildOracleSystemPrompt(tools, storeCtx, personaCtx, brandCtx, skillsBlock)

7. ★ 冲突上下文注入
   → ConflictCtxFrom(ctx) 附加 "PRIOR CONFLICTS / CAUTIONS"
   → 让 Oracle 不重复之前冲突/被拒的决策

8. LLM 调用 → parseOracleResponse → OracleResult

9. ★ 工具名校验 + 恢复
   → validateStages 校验工具存在
   → 全部被过滤掉时 attemptToolSearchRecovery
   → 恢复失败才降级为 chat
```

**两个容易被忽略的亮点**:

**领域分类**(`oracle.go:256`):当工具目录大(>20),LLM 经常选错但相关的工具(例如该选 `approve_return` 却选了 `get_product_detail`)。先做一次领域分类把工具收窄到该领域的 10-15 个,再让 LLM 在小集合里选。注释说:"Costs one ~20-token LLM call; saves multiple wrong-tool React rounds."

**冲突上下文**(`oracle.go:279`):之前有一个 `TwoLayerRouter` 会读冲突上下文,它被移除后冲突检测就"瞎了"。P3 修复:通过 `WithConflictCtx` 把之前的冲突/拒绝决策附到 context,Oracle 读到后避免重复。

### A3. Intent 分发

| Intent | 去向 | 说明 |
|---|---|---|
| `chat` | ChatStrategy | 纯对话,不调工具 |
| `tool_call` | SinglePass 或 ReAct | 简单走 SinglePass,复杂走 ReAct |
| `plan` | PlanStrategy | 多步规划(ADR 0002 接通了原 core.go:185 的死分支) |

---

## B. ReAct 循环:双实现

Vela 有两套 ReAct 实现——V1 内联版和 Phase 0.6 重构的 strategy 版。

### B1. V1 内联版:handleToolCallLoop

**源码**:`internal/handler/agent/react_loop.go:26`

```go
const maxRounds = 3

for round := 0; round < maxRounds; round++ {
    dag := orchestrator.BuildDAG(shopID, oracleResult.Stages)
    h.injectContextIntoDAG(dag, uctx, ...)

    // AutonomyGate 过滤
    gateResult := h.gate.Filter(dag)
    if gateResult.ExecutableCount() == 0 {
        sse.WriteEvent("agent_gate_held", ...)
        return ...
    }
    gatedDAG := h.gate.BuildExecutableDAG(dag, gateResult)

    // 执行
    results := h.executeOracleStages(ctx, gatedDAG, oracleResult.Stages, sse, shopUUID)
    // 累积结果...

    // LLM 复核
    review := h.taskReviewCheckpoint(ctx, shopUUID, message, accumulatedResults, round+1)
    switch review {
    case "done":   return ...
    case "more":   // 扩展上下文,重新 Route
    case "ask":    // 需要商户澄清
    case "abort":  // 放弃
    }
}
```

### B2. Strategy 重构版:strategy.React

**源码**:`internal/service/agent/strategy/react.go:24`

ADR 0002 Phase 0.6 把循环逻辑从 handler 下沉到 service 层,核心循环完全相同,但依赖通过接口注入:

```go
type React struct {
    gate      autonomyGate   // AutonomyGate
    executor  roundExecutor  // executeOracleStages 的接口
    oracle    reRouter       // 重新路由的接口
    reviewer  taskReviewer   // taskReviewCheckpoint 的接口
    maxRounds int            // 默认 DefaultReactMaxRounds(budgets.go)
}
```

`Run`(`react.go:73`)的逻辑与 V1 一致,但解耦了 `net/http`——strategy 只面向 `AgentOutput` 接口写流,不依赖 `*httputil.SSEWriter`。

**两版并存的原因**(`agent_execute_strategy.go:20` 注释):`handleToolCallLoop` 保留是因为 plan-step 路径(`executePlanStepsReact`)还在用它,PlanStrategy 迁移时会一起改。

### B3. taskReviewCheckpoint:LLM 复核

**源码**:`react_loop.go:120`

每轮执行后,LLM 判断结果是否充分:

```
决策规则(注入 prompt):
- "done": 结果足以回答商户,停。
- "more": 结果有缺口,需要更多工具。
- "ask": 任务歧义,需要商户澄清。
- "abort": 工具完全失败,无法继续。

输入:任务 + 每轮结果(status/score/error)+ 统计(错误数/有意义数据/完成工具数)
输出:EXACTLY ONE WORD
```

reviewer 看 `Score`(0-100,越高越健康)和错误数做判断。这是"自我评估"机制——agent 不盲目跑满 3 轮,而是每轮后判断是否够了。

---

## C. AutonomyGate:四规则分级

**源码**:`internal/service/orchestrator/autonomy.go:20`

AutonomyGate 是安全护栏——把 DAG 节点按风险分三级,高风险的要人工确认。

### C1. 三级 AutonomyLevel

| 级别 | 含义 | 行为 |
|---|---|---|
| `Auto` | 安全只读 | 自动执行 |
| `Suggest` | 建议级 | 执行但提示商户 |
| `Confirm` | 高风险 | **必须人工确认** |

### C2. 四条分类规则(classify)

`classify`(`autonomy.go:125`)按优先级判断:

```
规则 1: HARD CONFIRM — 永远赢,不可放宽
  → 客户可见沟通(发邮件/通知)或资金变动(退款/折扣)
  → 无论工具怎么声明,都是 Confirm

规则 2: 显式声明 — 工具自己的 AutonomyLevel
  → registry.Get(toolName).AutonomyLevel
  → 可被商户偏好(applyMerchantPrefs)调整

规则 3: 遗留前缀兜底
  → classifyByPrefix(toolName)
  → 按工具名前缀分类(legacy,未迁移工具走这里)
```

**规则 4: 置信度升级**(`ClassifyWithConfidence`,`autonomy.go:72`):
```go
// 如果 Oracle 置信度 < confThreshold(默认 0.7),AUTO → SUGGEST
// "Agent 可以质疑自己的决策"——不确定时降一档,多一层提示
```

### C3. FirstUseChecker

`WithFirstUseChecker`(`autonomy.go:55`):商户第一次用某个模板时,所有节点强制 CONFIRM。这是"新功能谨慎上线"的保护——第一次都要人工看过一遍,之后才放行。

### C4. Filter + BuildExecutableDAG

`Filter`(`autonomy.go:92`)把 DAG 节点分到三个队列:

```go
type GateResult struct {
    AutoNodes    map[string]*DAGNode
    SuggestNodes map[string]*DAGNode
    ConfirmNodes map[string]*DAGNode
}
```

`BuildExecutableDAG`(`autonomy.go:243`)做**两遍剪枝**——移除 CONFIRM 节点,并递归移除依赖它们的下游节点:

```
Pass 1: 收集可执行(Auto + Suggest)节点 ID
        → 移除依赖了非可执行节点的节点(递归标记)

Pass 2: 再扫一遍,移除依赖了刚被剪掉的节点的节点
        (两遍保证传递性剪枝完整)
```

**为什么两遍**:第一遍剪掉依赖 CONFIRM 的节点后,原本依赖这些被剪节点的节点也该剪——单遍循环做不到完整传递性,两遍是简单且正确的方案(虽然理论上可能需要多遍直到不动点,但 DAG 深度有限,两遍覆盖绝大多数场景)。

### C5. 全部被拦时

`react.go:96`:`if gateResult.ExecutableCount() == 0` → 发 `agent_gate_held` SSE 事件,带 `actions` 数量(多少个要确认),agent 停下来等人工。

### C6. 人工确认端点

**源码**:`handler/agent/agent_execute.go:806`

```go
type gateConfirmReq struct {
    GateID string `json:"gate_id"`
    Choice string `json:"choice"` // "confirmed" | "rejected"
}
```

`GateConfirm` handler:商户在 UI 里点确认/拒绝 → confirmed 则从队列移除(下一轮/cron 拾取执行),rejected 则丢弃。

---

## D. 完整执行流(串联)

```
用户消息
  → Gateway(鉴权 + 限流 + 租户隔离)
  → AgentExecuteHandler(薄壳,组 AgentRequest)
  → Oracle.Route(领域分类 + 工具预算 + 冲突注入 → Intent)
  → 按 Intent 选 Strategy:
     ├─ chat → ChatStrategy(fallbackLLM)
     ├─ tool_call(简单) → SinglePassStrategy(一轮 DAG)
     └─ tool_call(复杂) → ReActStrategy(多轮)
        └─ 每轮:
           BuildDAG → AutonomyGate.Filter → BuildExecutableDAG
           → Orchestrator.Execute(并行 + 重试 + SSE)
           → taskReviewCheckpoint(done/more/ask/abort)
           → "more" 则扩展上下文重新 Route
  → Synthesizer(汇总结果)
  → DecisionStore.SaveAgentDecision(记录决策供 Reflect)
  → PublishAgentEvent(eventbus 广播)
```

---

## E. 与其他框架对比

| 维度 | Vela | grok-build | kimi-code |
|---|---|---|---|
| **意图路由** | Oracle(领域分类 + 预算 + 冲突) | 单层 LLM 路由 | provider 抽象 |
| **安全分级** | AutonomyGate 4 规则(Auto/Suggest/Confirm) | Permission + sandbox | DI × Scope |
| **循环复核** | taskReviewCheckpoint(LLM judge) | doom loop 检测 | step/retry |
| **置信度降级** | AUTO→SUGGEST(置信 <0.7) | 无 | 无 |

**Vela 的独特设计**:AutonomyGate 的"置信度升级"——agent 不确定时主动降一档权限,这是"AI 自我质疑"的工程化体现。配合 FirstUseChecker(首次强制确认),既保证安全又不牺牲效率。
