# 05 — 多 Agent(DAG-of-Agents)+ 分布式 AutoGoal + Steering

> 这是 ADR 0003 + ADR 0004 的落点,也是我之前最严重的错误判断。

## A. 多 Agent:DAG-of-Agents(ADR 0003)

### A1. 核心抽象:节点既可是 tool 也可是 agent

**源码**:`internal/service/orchestrator/orchestrator.go:24`

```go
type DAGNode struct {
    ID       string
    Tool     string         // 工具节点:注册的工具名
    Args     map[string]any
    Deps     []string       // 依赖的节点 ID
    Required bool
    Retry    int            // 默认 3
    Timeout  time.Duration  // 默认 60s
    Fallback string         // "skip" | "cache" | "abort"
    Agent    *AgentNodeSpec // ★ 非 nil = agent 节点(跑子 agent 而非工具)
}
```

`Agent *AgentNodeSpec` 是 ADR 0003 Phase 2.1 的扩展——`nil` 时是传统工具节点(向后兼容),非 nil 时 Orchestrator 跑一个子 `Agent.Run` 而非工具 handler。

### A2. Orchestrator.Execute:拓扑并行执行

**源码**:`orchestrator.go:105`

```go
func (o *Orchestrator) Execute(ctx, dag DAG, sse SSEWriter) *DAGResult {
    results := make(map[string]*NodeResult)
    for {
        // 上下文取消检查(商户发了新消息 → 立即停)
        select { case <-ctx.Done(): return &DAGResult{Cancelled: true} ... }

        batch := dag.ReadyNodes(results)  // 依赖都完成的节点
        if len(batch) == 0 { break }

        // 并行执行 batch
        var wg sync.WaitGroup
        for _, node := range batch {
            sse.WriteEvent("agent_card_update", {status: "loading"...})
            wg.Add(1)
            go func(n *DAGNode) {
                defer wg.Done()
                res := o.executeWithRetry(ctx, n)  // 3 次重试 + 可恢复错误判定
                results[n.ID] = res
                // MCP Apps: 如果工具声明了 card,附带 data
                sse.WriteEvent("agent_card_update", {status, score, card?, data?})
            }(node)
        }
        wg.Wait()
    }
}
```

`executeWithRetry`(`orchestrator.go`)对可恢复错误(timeout/connection refused/rate limit/429/503)重试 3 次,用 `isRecoverable`(`orchestrator.go:301`)判定。

### A3. ReadyNodes:拓扑排序

`ReadyNodes`(`orchestrator.go:321`)返回依赖全部完成的节点:

```go
func (d *DAG) ReadyNodes(results map[string]*NodeResult) []*DAGNode {
    var ready []*DAGNode
    for _, node := range d.Nodes {
        if _, processed := results[node.ID]; processed { continue }
        allDepsReady := true
        for _, dep := range node.Deps {
            r, ok := results[dep]
            if !ok || r.Status == "error" {  // 依赖失败也不 ready
                allDepsReady = false
                break
            }
        }
        if allDepsReady { ready = append(ready, node) }
    }
    return ready
}
```

### A4. Score 语义

`NodeResult.Score`(`orchestrator.go:49`)是 0-100 的健康度,工具自己设置——发现很多问题的工具给低分,一切健康的给高分。有命名常量(`ScoreActionable` 等)统一阈值,替代了之前散落在 wakeup/cron.go、synthesizer.go、coordinator.go 的魔法数字。

---

## B. MultiAgentWorkspace:共享黑板

**源码**:`internal/service/multiagent/workspace.go:36`

ADR 0003 Phase 2.2 的核心——所有 agent 节点读写同一个工作区。

### B1. 结构

```go
type MultiAgentWorkspace struct {
    mu       sync.RWMutex
    metaGoal string              // 协调者追求的顶层目标
    context  map[string]any      // 共享上下文(店铺快照 + 累积状态)
    findings []AgentFinding      // 各 agent 的关键产出
}

type AgentFinding struct {
    AgentID   string         // 产出此 finding 的 DAGNode.ID
    Persona   string         // 角色("seo"/"content"/"inventory")
    Goal      string         // 该 agent 追求的子目标
    Summary   string         // 人可读摘要
    Data      map[string]any // 结构化关键输出
    Score     int            // 0-100 自评置信度
    Timestamp time.Time
}
```

### B2. 线程安全设计

所有 accessor 用 `sync.RWMutex`。**读取返回拷贝**(`Context()`、`Findings()`)——这样 agent 读取工作区后,在漫长的执行期间不需要持锁:

```go
// workspace.go:76
func (w *MultiAgentWorkspace) Context() map[string]any {
    w.mu.RLock()
    defer w.mu.RUnlock()
    out := make(map[string]any, len(w.context))
    for k, v := range w.context { out[k] = v }  // 拷贝
    return out
}
```

### B3. BuildAgentContext:注入子 agent

`BuildAgentContext`(`workspace.go:124`)把工作区渲染成字符串,在子 agent 跑之前注入它的消息:

```
META-GOAL: 做大促准备

PRIOR AGENT FINDINGS:
- [seo] 发现 12 个商品标题缺关键词 (score=85)
- [content] 已生成 5 篇博客草稿 (score=90)
```

这让下游 agent 能看到跨切面的状态,不只依赖 DAG 边的直接前驱数据。**双通道数据流**:DAG 边(直接前驱结果) + 黑板(跨切面共享)。

---

## C. Coordinator + LLMDecomposer

**源码**:`internal/service/multiagent/coordinator.go` · `internal/service/autogoal/decomposer.go`

### C1. AgentStep

```go
// multiagent/coordinator.go:23
type AgentStep struct {
    Goal     string // 子目标
    Persona  string // 分配的专家
    Strategy string // "react" 等
}
```

### C2. LLMDecomposer:拆 meta-goal

**源码**:`autogoal/decomposer.go:49`

```go
func (d *LLMDecomposer) Decompose(ctx, goal *model.Goal) ([]multiagent.AgentStep, error) {
    // LLM prompt: "把目标拆成 2-4 个子目标,分配给不同专家 agent"
    // 回复格式: [{"goal":"...","persona":"seo|content|inventory|..."}]
    // ★ clampSubAgents: 硬上限 maxSteps(默认 50),防 LLM 拆太细
    // 任何错误 → singleStep(退化为单 agent 跑整个目标)
}
```

默认模型 `deepseek-chat`,温度 0.3(要稳定可预测的拆解),maxTokens 300。

---

## D. 持久化:DAGRun + DAGNodeState(崩溃恢复)

**源码**:`internal/model/dag_run.go` · `internal/service/multiagent/dag_store.go`

这是生产级的关键——多 agent 运行可能很长,进程重启要能恢复。

```go
// model/dag_run.go:18
type DAGRun struct {
    ID        uuid.UUID
    ShopID    uuid.UUID
    MetaGoal  string
    Status    string        // pending | running | completed | failed
    Steps     datatypes.JSON // []AgentStep 快照
    Findings  datatypes.JSON // []AgentFinding 累积
}

// model/dag_run.go:30
type DAGNodeState struct {
    RunID     uuid.UUID
    NodeID    string  // "step_0", "step_1"
    Persona   string
    Goal      string
    Status    string  // pending | running | done | error | skipped
    Summary   string
    Score     int
    StartedAt *time.Time
    DoneAt    *time.Time
}
```

`DAGRunStore`(`dag_store.go:21`)的 `RecoverPendingRuns` 在启动时重建状态——pending/running 节点重新入队,completed 节点跳过,workspace findings 从 completed 节点结果重建。

---

## E. Autonomous Goal Loop(ADR 0004)

### E1. Goal:持久状态机 + 对话线程 + 进度

**源码**:`internal/model/autogoal.go:48`

```go
type Goal struct {
    ID, ShopID    uuid.UUID
    MetaGoal      string
    // 可测量目标契约
    Metric        string  // "conversion_rate"
    Target        float64 // 0.02 表示 "+2%"
    Operator      string  // ">=" | "<=" | "==" | "increase_by"
    Baseline      float64 // 创建时的 metric 值
    // 生命周期 + 进度
    Status        string  // active|paused|completed|failed|stalled|awaiting_review
    CurrentValue  float64
    Cycle         int
    MaxCycles     int
    Deadline      *time.Time
    ExecuteMode   string  // "single_agent" | "multi_agent"
    Persona       string  // 归属 persona(记忆隔离 + 自我意识)
    // 跨轮状态(JSONB)
    MetricHistory datatypes.JSON // []MetricPoint(进度曲线)
    Findings      datatypes.JSON // []AgentFinding
    Conversation  datatypes.JSON // []GoalMessage(per-goal 会话!)
}
```

**三位一体**:Goal = 自治 Loop(GoalEngine 驱动)+ per-goal 对话线程(用户交互入口)+ 进度视图(MetricHistory)。

### E2. GoalMessage:对话 + Steering

```go
type GoalMessage struct {
    Role     string // "user" | "assistant" | "system"
    Content  string
    Cycle    int    // assistant 轮次摘要所属轮次
    Severity string // user 消息:"advisory" | "interrupt"
}
```

- **user**:商户的 steering 消息。`advisory`(默认)= 下一轮读入注入;`interrupt`("停止"/"重定向")= 取消当前轮。
- **assistant**:GoalEngine 的每轮摘要("Cycle 3: 改了 5 个 SEO 标题,转化 1.2%→1.4%")——这就是阶段性结果可视化。
- **system**:生命周期事件(状态变更、HITL 检查点、错误)。

### E3. GoalEngine.Advance:一轮的完整流程

```
1. 读会话里新的 user 消息(steering)
   → advisory:注入 "USER UPDATE: ..." 到下一轮
   → interrupt:已通过 ctx cancel 中断(见 Scheduler)

2. execute(按 ExecuteMode):
   → single_agent:跑 React(单 agent)
   → multi_agent:跑 Coordinator DAG(多 agent 并行)

3. verify:
   → 有 metric:读转化率等数据对比 target
   → 无 metric:LLM judge + 人工 review

4. reflect:未达标→换打法;达标→completed;无进展→stalled→awaiting_review

5. 把本轮摘要作为 assistant 消息 append 到 Conversation

6. persist(状态 + findings + CurrentValue + Conversation)
```

---

## F. 分布式 Scheduler(水平扩展就绪)

**源码**:`internal/service/autogoal/scheduler.go:24`

这是 7 个框架里唯一考虑了水平扩展的调度器。

### F1. Scheduler 结构

```go
type Scheduler struct {
    engine         *GoalEngine
    store          *DBGoalStore
    interval       time.Duration
    cancels        sync.Map          // goalID → context.CancelFunc(实时中断)
    maxConcurrency int               // 默认 5(信号量限流)
    locker         GoalLocker        // ★ PG advisory lock(多副本去重)
    broadcaster    cancelBroadcaster // ★ 跨副本 cancel 广播
}
```

### F2. tick:并发推进

```go
// scheduler.go:174
func (s *Scheduler) tick(ctx) {
    goals := s.store.ListActive(ctx)
    sem := make(chan struct{}, s.maxConcurrency)  // 信号量
    var wg sync.WaitGroup
    for i := range goals {
        g := &goals[i]
        wg.Add(1)
        go func() {
            defer wg.Done()
            sem <- struct{}{}        // 获取令牌
            defer func() { <-sem }() // 释放令牌
            s.advanceOne(ctx, g)
        }()
    }
    wg.Wait()
}
```

### F3. ★ 分布式去重(GoalLocker)

```go
// scheduler.go:203
func (s *Scheduler) advanceOne(ctx, g *model.Goal) {
    if s.locker != nil {
        unlock, ok, err := s.locker.TryLockGoal(ctx, g.ID)
        if !ok {
            // 另一个副本正在推进这个 goal → 跳过
            slog.Info("autogoal: goal already advancing on another replica, skipping")
            return
        }
        defer unlock()
    }
    goalCtx, cancel := context.WithCancel(ctx)
    s.cancels.Store(g.ID, cancel)  // 存 cancel func 供实时中断
    defer s.cancels.Delete(g.ID)
    s.engine.Advance(goalCtx, g)
}
```

`DBGoalStore` 实现 `GoalLocker` 用 Postgres advisory lock。多副本部署时,同一 goal 在同一 tick 只被一个副本推进。

### F4. ★ 跨副本 Cancel 广播

```go
// scheduler.go:147
func (s *Scheduler) Cancel(goalID uuid.UUID) {
    s.cancelLocal(goalID)  // 本副本中断
    if s.broadcaster != nil {
        s.broadcaster.PublishCancel(ctx, goalID)  // 广播给所有副本
    }
}

// scheduler.go:101 — 订阅其他副本的 cancel 信号
func (s *Scheduler) subscribeCancels(ctx) {
    ch, stop := s.broadcaster.CancelEvents(ctx)
    for {
        select {
        case goalID := <-ch:
            s.cancelLocal(goalID)  // 收到信号 → 中断本副本正在跑的该 goal
        }
    }
}
```

**场景**:Goal A 在副本 1 跑。用户在副本 2 发了"停止目标 A"。副本 2 的 `Cancel` 广播 → 副本 1 的 `subscribeCancels` 收到 → `cancelLocal` 调存好的 `CancelFunc` → goalCtx.Done() → GoalEngine.Advance 中断。

这是真正的分布式实时 steering,不是单机的 ctx cancel。

### F5. GoalLoop Strategy(交互式)

**源码**:`internal/service/agent/strategy/goalloop.go:25`

ADR 0004 把 GoalLoop 从 wakeup-only 提升为交互式策略,可在主对话里 `Mode=GoalLoop` 触发:

```go
type GoalLoop struct {
    runner goalRunner // goal.GoalRunner(wakeup 路径已用)
}

func (g *GoalLoop) Run(ctx, req AgentRequest, out AgentOutput) (*AgentResponse, error) {
    state, err := g.runner.Run(ctx, req.ShopID, *req.GoalSpec, summarizeDAGForVerifier, out)
    // state.Achieved / state.Round / state.DoneReason
}
```

`summarizeDAGForVerifier`(`goalloop.go:72`)把 DAGResult 渲染成 Verifier 读取的文本——无论从 wakeup 还是交互触发,验证行为一致。

---

## G. 人在回路(HITL)

ADR 0004 Phase C 的 HITL 复用 AutonomyGate:
- 轮内拦高危动作 → Goal 进 `awaiting_review`
- 商户**在 goal 会话里**批 → resume
- 默认轮末批量 checkpoint(不逐动作中断,减少打扰)

---

## H. 与其他框架对比

| 维度 | Vela | grok-build | kimi-code |
|---|---|---|---|
| **多 agent 模型** | DAG-of-Agents + 共享黑板 | Subagent + worktree | Swarm + Subagent |
| **目标持久化** | Goal 状态机 + 对话线程 | Goal complete(6 子系统) | Goal mode(会话级) |
| **分布式** | PG advisory lock + 跨副本 cancel | 单机 | 单机 |
| **Steering** | advisory(下轮)+ interrupt(秒级) | 无 | 无 |
| **崩溃恢复** | DAGRun + DAGNodeState | wire 持久化 | session metadata |
| **HITL** | AutonomyGate 复用(轮末批量) | 无独立 HITL | 无 |

**Vela 多 agent 系统的独特价值**:它是唯一为**多副本水平扩展**设计的——PG advisory lock 防双跑,cancel 广播实现跨副本实时 steering。这意味着 Vela 可以部署多个实例分摊 goal 负载,而 kimi/grok/codex 都是单机假设。配合 DAGRun 持久化,即使实例崩溃,另一个实例能在下一个 tick 接管未完成的 goal。
