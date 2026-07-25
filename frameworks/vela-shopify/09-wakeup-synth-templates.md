# 09 — Wakeup/Cron/EventWatcher · Synthesizer · TaskTemplates · ToolRegistry

## A. Wakeup 系统:三种触发方式

**源码**:`internal/service/agent/wakeup/` + `internal/server/event_watcher*.go`

agent 不是只靠用户消息触发,还有三种自动唤醒机制。

### A1. Cron 定时触发(wakeup/cron.go)

```go
// cron.go:53
type Scheduler struct {
    cron CronEngine  // robfig/cron 注入
}

func (s *Scheduler) RegisterFromTemplates(onExecute func(template string, signal Signal)) {
    for name, tmpl := range orchestrator.Templates {
        if tmpl.CronDefault == "" { continue }
        sig := templateToSignal(template)
        s.cron.AddFunc(tmpl.CronDefault, func() {
            onExecute(template, sig)
        })
    }
}
```

**语义 Signal 系统**(`cron.go:13`):不是模糊的"weekly/daily",而是带业务意图的信号:

```go
SignalMondayMorning  // 周一晨检(store_health/seo_audit/geo_audit/weekly_report)
SignalLowStock        // 库存不足 → 补货工作流
SignalChurnRisk       // 流失风险 → 留存活动
SignalReturnSpike     // 退货激增 → 根因分析
```

**templateSignalMap**(`cron.go:71`):数据驱动的 template→Signal 映射。注释说明为什么改数据驱动:"prior switch statement was incomplete — only 3 of 6 scheduled templates were explicitly mapped"。现在缺失映射会**启动时 panic**,不会静默误分类。

### A2. 条件信号(DetectConditionalSignals)

`cron.go:171` — cron 跑完后,**检查结果分数**决定是否触发后续行动:

```go
var watchedTools = map[string]struct {
    signal Signal
    below  int  // 分数低于此值 → 触发信号
}{
    "predict_churn_risk": {signal: SignalChurnRisk, below: ScoreActionable}, // <50
    "detect_dead_stock":  {signal: SignalLowStock, below: ScoreActionable},  // <50
    "check_inventory":    {signal: SignalLowStock, below: 40},               // 更严格
    "analyze_returns":    {signal: SignalReturnSpike, below: 45},            // 更敏感
}

func DetectConditionalSignals(toolScores map[string]int) []Signal {
    // 纯函数(无 I/O),可内联在 cron 回调里
    // 返回排序去重的信号列表
}
```

这是**主动式 agent**——不只定时跑,还根据结果**二次触发**。例如周一晨检发现流失风险高(<50 分),自动触发 `SignalChurnRisk` → 留存工作流,不用等下次定时。

### A3. 事件驱动(EventWatcher)

**源码**:`internal/service/agent/wakeup/event.go` + `internal/server/event_watcher.go`

EventWatcher 订阅 EventBus,业务事件触发 agent:

```go
// event.go:18
type EventWatcher struct {
    wakeUpFunc func(ctx, shopID, signal, message) error
    limits     *rate.Limiter     // 全局 10/sec
    running    map[string]bool   // per-shop 互斥
    mu         sync.Mutex
}

func (w *EventWatcher) Subscribe(bus eventbus.EventBus) {
    bus.Subscribe(EventReturnSynced, w.onEvent("return_spike",
        "退货率超过15%,分析退货模式和根因"))
    bus.Subscribe(EventReviewSynced, w.onEvent("review_trend",
        "出现连续差评趋势,分析评价数据并建议回复策略"))
    bus.Subscribe(EventOrderFulfilled, w.onEvent("low_stock",
        "订单完成,检查库存是否低于安全阈值"))
}
```

**三重保护**:
1. **panic recovery** — 单个 handler panic 不崩消费端
2. **全局限流** — `rate.Limiter(10/sec, burst 10)`,过载丢事件(不阻塞)
3. **per-shop 互斥** — 同一 shop 的 agent 正在跑时,新事件跳过(防重复并发)

### A4. EventWatcher Guard + Lock(server 层)

**源码**:`internal/server/event_watcher_guard.go` + `event_watcher_lock.go`

`server/` 层有额外的守护和锁机制(581 行),防止事件风暴导致 agent 过载。

---

## B. TaskTemplates:15+ 预设工作流

**源码**:`internal/service/orchestrator/task_templates.go`(381 行)

这是 Vela 的**领域知识库**——15+ 个预设的 DAG 工作流模板,覆盖电商运营全场景。

### B1. 模板结构

```go
type TaskTemplate struct {
    Name        string
    Description string  // 何时使用的自然语言描述
    Stages      []Stage // DAG 阶段(并行/串行工具组)
    CronDefault string  // cron 表达式(空 = 不定时)
    Attribution bool    // 是否做归因追踪
}
```

### B2. 模板全景

| 分类 | 模板 | 工具数 | 定时 | 场景 |
|---|---|---|---|---|
| **店铺运营** | store_health | 5 | 周一8点 | 概览+滞销+退货+流失→周报 |
| | quick_diagnostic | 3 | — | 快速快照 |
| **退货质量** | returns_analysis | 5 | — | 退货模式+取消+欺诈 |
| **库存** | dead_stock | 4 | 周三8点 | 滞销→折扣+营销→告警 |
| | inventory_health | 4 | — | 滞销+周转+目录健康 |
| **SEO/GEO** | seo_audit | 8 | 周一3点 | 全站SEO审计 |
| | geo_audit | 6 | 周一2点 | AI搜索可见性 |
| | seo_quick_fix | 2 | — | 单商品快速优化 |
| **客户** | customer_insights | 6 | — | 流失+LTV+RFM+队列 |
| | churn_prevention | 4 | — | 流失检测→留存计划 |
| **收入定价** | revenue_analysis | 5 | — | 收入+AOV+周期对比 |
| | pricing_optimization | 5 | — | 折扣ROI+定价建议 |
| **营销** | marketing_audit | 4 | — | 流程+ROI+趋势 |
| | cart_recovery | 3 | 周一10点 | 弃购→折扣→告警 |

### B3. 典型模板:store_health

```go
"store_health": {
    Stages: []Stage{
        {Parallel: true, Tools: []string{
            "get_store_overview",    // 概览
            "detect_dead_stock",     // 滞销
            "analyze_return_patterns", // 退货
            "predict_churn_risk",    // 流失
        }},
        {Parallel: false, Tools: []string{"generate_weekly_report"}}, // 汇总
    },
    CronDefault: "0 8 * * 1",  // 每周一8点
    Attribution: true,
}
```

第一轮 4 个诊断工具**并行**,第二轮汇总报告**串行**——经典的 fan-out → fan-in 模式。

### B4. templateToGoalSpec(可测量模板)

`agent_wakeup.go:396` 把某些模板转成 GoalSpec(支持多轮 GoalRunner):

```go
var measurableGoalTemplates = map[string]GoalSpec{
    "store_health": {Metric: "health_score", Target: 80, Operator: ">="},
    "seo_audit":    {Metric: "seo_score", Target: 80, Operator: ">="},
    "geo_audit":    {Metric: "geo_score", Target: 80, Operator: ">="},
    "dead_stock":   {Metric: "dead_stock_count", Target: 10, Operator: "<="},
}
```

这些模板的 cron 触发不是"跑一次就完",而是 GoalRunner 多轮执行直到 metric 达标。

---

## C. Synthesizer:结果汇总(防 AI slop)

**源码**:`internal/service/orchestrator/synthesizer.go`

### C1. 为什么需要 Synthesizer

DAG 执行后有一堆 NodeResult(每个工具的状态/分数/数据),需要 LLM 把它们汇总成商户可读的摘要。但有个风险——**"AI slop"**(千篇一律的模板化废话)。

### C2. 三层质量保障

```go
type Synthesizer struct {
    llmClient       *agentllm.Client
    promptProvider  *agentprompt.PromptContextProvider  // ★ 品牌声音注入
    maxSummaryWords int                                 // ★ 硬上限(默认 120)
}
```

**WithPromptProvider**(`synthesizer.go:48`)注释说明为什么:

> "V3 architecture review flagged the prior synthesizer prompt as an 'AI slop' risk — the same generic 3-section English summary for every store. Injecting the merchant's brand voice + a strict length/structure cap raises the floor on output quality and removes the most-visible 'this is clearly a chatbot' tell."

三层保障:
1. **品牌声音注入** — 用商户配置的 BrandVoice,不是通用英文
2. **长度硬上限** — 120 词,防止 LLM 输出 500 词废话
3. **结构约束** — 严格格式,不允许"AI 味"模板

---

## D. Queue:审批队列

**源码**:`internal/service/orchestrator/queue.go`(114 行)

AutonomyGate 过滤出的 CONFIRM 节点进入审批队列,等商户确认。

```go
type Queue struct {
    // pending confirmations
}
```

商户在 UI 里确认/拒绝(见 04 篇 §C6 的 GateConfirm handler),confirmed 的节点从队列移除,下一轮/cron 拾取执行。

---

## E. ConflictDetector:冲突检测

**源码**:`internal/service/agent/memory/conflict.go`

```go
type ConflictResult struct {
    // 检测当前决策是否与历史冲突
}

func Detect(ctx, shopID, query) (*ConflictResult, error) {
    decisions := s.Recall(ctx, shopID, query, topK)  // 召回历史
    // 对比当前决策与历史
}
```

`BuildConflictPrompt` 把冲突检测结果编织成 prompt,通过 `WithConflictCtx` 注入 Oracle 的 context(见 04 篇 §A2 的冲突注入)。这让 agent **不重复之前冲突/被拒的决策**。

---

## F. ToolRegistry:87+ 工具的全貌

**源码**:`internal/service/agent/tools/`(55 文件)

### F1. 工具分类(按文件)

| 文件 | 工具类别 |
|---|---|
| `customer_tools.go` | 顾客侧(产品搜索/FAQ/购物车) |
| `merchant_tools.go` | 商家侧(运营管理) |
| `seo_tools.go` | SEO(15 个工具) |
| `geo_tools.go` | GEO/AI 搜索可见性 |
| `content_tools.go` | 内容生成 |
| `marketing_ops.go` | 营销操作 |
| `returns_ops.go` | 退货管理 |
| `review_ops.go` | 评价管理 |
| `fulfillment_ops.go` | 履约 |
| `memory_tools.go` | 记忆工具(remember/search/forget) |
| `skill_tools.go` | 技能工具(save_skill) |
| `mcp_management_ops.go` | MCP 连接管理 |
| `email_marketing_ops.go` | 邮件营销 |
| `cart_recovery_ops.go` | 购物车恢复 |
| `shop_ops.go` | 店铺操作 |
| `tools_analytics.go` | 分析工具 |
| `tools_discount.go` | 折扣工具 |

### F2. 工具注册:registry.go(397 行)

```go
type ToolRegistry struct {
    tools map[string]*AgentTool
    // per-shop 工具(MCP 动态注册的)
}

func (r *ToolRegistry) Register(tool *AgentTool)
func (r *ToolRegistry) ListForShop(shopID uuid.UUID) []*AgentTool  // 含 MCP 工具
func (r *ToolRegistry) ListByRole(role string) []*AgentTool         // 按角色过滤
```

### F3. AutonomyLevel 声明(registry_autonomy_test.go)

每个工具可声明自己的 `AutonomyLevel`(Auto/Suggest/Confirm),`AutonomyGate.classify` 优先读声明(见 04 篇 §C2 规则 2)。

### F4. scenes.go — 场景过滤

工具可声明属于哪些 Scenes(`Tool.Scenes`),按场景过滤可见工具。

### F5. signals.go — 信号系统(275 行)

工具执行后可发出**信号**(Signals),这是工具向 agent 框架反馈"发现了什么"的机制——与 `DetectConditionalSignals` 联动。

### F6. tool_search.go — 工具搜索恢复(58 行)

当 Oracle 选的工具全被 validateStages 过滤掉,`attemptToolSearchRecovery`(`oracle.go`)用语义搜索在工具目录里找最相关的,作为路由失败的最后恢复手段。

---

## G. 完整自动触发链路

```
                 ┌─ Cron 定时 ──────────────────────┐
                 │  Scheduler.RegisterFromTemplates  │
                 │  → cron 触发 → onExecute(template)│
                 │  → DetectConditionalSignals       │
                 │    (分数低 → 二次信号)            │
                 └───────────────────────────────────┘
                                ↓
                    WakeUpHandle(agent_wakeup.go)
                                ↓
                 ┌─ EventWatcher 事件驱动 ──────────┐
                 │  EventBus → Subscribe             │
    商家消息 →    │  (退货同步/评价同步/订单完成)     │
                 │  → 限流 + 互斥 + panic 恢复       │
                 │  → wakeUpFunc                     │
                 └───────────────────────────────────┘
                                ↓
                    templateToGoalSpec(可测量?)
                       ↓              ↓
                    是               否
                       ↓              ↓
                 GoalRunner        单次 React
                 (多轮)            ↓
                   ↓            Synthesizer(汇总)
              Verifier.Check       ↓
                   ↓            ConflictDetector(冲突检测)
              achieved?            ↓
              ├─是→ done      SaveDecision(记录)
              └─否→ reflect   PublishAgentEvent(广播)
                   ↓
              下一轮
```

---

## H. 与其他框架对比

| 维度 | Vela | kimi-code | grok-build |
|---|---|---|---|
| **触发方式** | Cron + 条件信号 + 事件驱动(三合一) | cron 任务 | signals |
| **条件触发** | DetectConditionalSignals(分数→信号) | — | — |
| **事件保护** | 限流 + 互斥 + panic 恢复 | — | — |
| **预设工作流** | 15+ TaskTemplate(DAG 化) | — | — |
| **结果汇总** | Synthesizer(品牌声音+长度限制) | — | — |
| **冲突检测** | ConflictDetector + context 注入 | — | — |
| **工具规模** | 87+ 内置 + MCP 动态 + 商户自定义 | ~50 | ~30 |

**Vela 的独特价值**:
1. **三合一触发**(cron + 条件 + 事件)形成完整的自动运营闭环,不只是"被动等用户消息"
2. **条件信号**是真正"主动式 agent"的体现——跑完检查结果,不好就自动追击
3. **15+ 预设模板**是领域知识沉淀——不是通用 agent 框架,而是电商运营专家系统
4. **Synthesizer 防 AI slop**——品牌声音 + 长度硬限,从工程上消灭"一眼就是机器人"的输出
