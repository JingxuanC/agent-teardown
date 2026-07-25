# 06 — HTTP Gateway + UnifiedContext + LLM Provider

## A. Agent Gateway:多层防护

### A1. Gateway 中间件(鉴权 + 租户隔离)

**源码**:`internal/middleware/gateway.go:38`

`Gateway` 是所有 `/api/` 路径的守门人,实现三级认证 + 多重安全检查:

```
请求进入
  ↓
1. 公开端点放行(/api/contact, /api/auth/*, /api/analytics/*)

2. ★ 三级认证(任一成功):
   a. Shopify App Bridge JWT(Bearer token)
      → verifyShopifySessionToken 解析 shopDomain
      → resolver 把 domain 解析成 UUID,透明改写 query param
   b. Merchant JWT(X-Vela-Auth: Bearer)
      → parseMerchantJWT 解析 merchantID
      → ★ merchantOwnerCheck 验证 merchant 拥有该 shop(防越权)
   c. Internal API token(legacy,跳过若有 X-Internal-Secret)

3. Feature flag 检查(Redis,失败放行)
   → disabled 则返回 {success:false, disabled:true}

4. ★ 跨租户防护
   → X-Shop-ID header 与 shop_id query 不一致 → 403
   → "Cross-tenant access denied"

5. Domain → UUID 解析(透明改写 query)

6. ★ 每日配额检查(开发环境跳过,Redis 失败放行)
```

**关键安全细节**:
- `merchantOwnerCheck`(`gateway.go:94`)——商户 JWT 认证后,还要验证该商户确实拥有请求的 shop_id。这防止一个商户访问另一个商户的店铺数据。
- Header/Query 不一致检测(`gateway.go:165`)——如果 `X-Shop-ID` header 和 `shop_id` 参数都有但不一致,直接 403。这防 CSRF 式的租户混淆攻击。
- 所有 Redis 检查**失败放行**(fail-open)——可用性优先于安全性,但有 warn log。

### A2. 分级限流

**源码**:`internal/middleware/ratelimit.go:24`

```go
func DefaultRateLimits() []RateLimitConfig {
    return []RateLimitConfig{
        {PathPrefix: "/api/contact",        Window: 60s, Max: 5,  PerIP: true},
        {PathPrefix: "/api/auth/signup",    Window: 60s, Max: 5,  PerIP: true},
        {PathPrefix: "/api/auth/login",     Window: 60s, Max: 10, PerIP: true},
        {PathPrefix: "/api/llm",            Window: 60s, Max: 10, PerShop: true},
        {PathPrefix: "/api/admin/observability", Window: 60s, Max: 10, PerShop: true},
        {PathPrefix: "/api",                Window: 60s, Max: 60, PerShop: true}, // 兜底
    }
}
```

**设计**:
- **前缀匹配,具体优先**——`/api/contact` 比 `/api` 更具体,先匹配。
- **固定窗口**(INCR + EXPIRE)——简单有效,Redis 原子操作。
- **key 格式**:`ratelimit:{prefix}:{shop_id}:{ip}:{window_bucket}`——PerShop 和 PerIP 可组合。
- **失败放行**——Redis 错误时放行(可用性优先),但有 warn log。
- **响应头**:`X-RateLimit-Limit`、`X-RateLimit-Remaining`、`Retry-After`。

### A3. Agent Gateway Handler

**源码**:`internal/handler/agent_gateway.go`

这是 agent 执行的 SSE 入口。它:
- 鉴权后从 context 取 shopID
- 召回相关记忆(`DecisionStore.Recall`)
- 构建 TurnContext / AgentRequest
- 通过 SSE 流式返回 agent 执行过程

### A4. AgentRollout 中间件(灰度)

**源码**:`internal/middleware/agent_rollout.go`

`AgentRollout` 做 A/B 灰度——`DecideVariant` 决定请求走 V1 还是 V3 agent 路径,支持按 shop 百分比灰度发布。

---

## B. UnifiedContext:上下文组装

### B1. UnifiedContext

**源码**:`internal/service/orchestrator/context_builder.go:24`

```go
type UnifiedContext struct {
    // 量化指标(ContextBuilder 负责,与 PromptContextProvider 不重叠)
    Snapshot    map[string]any  // 店铺快照(库存/订单/客户统计)
    // ... 其他经营数据字段
}
```

`ContextBuilder.Build`(`context_builder.go:90`)聚合多个 Fetcher 的数据——这是**定量**层(经营指标),与 PromptContextProvider 的**定性**层(品牌人格)分工明确(ADR 0001 §被否决方案明确两者不重叠)。

### B2. ToolContext:工具执行上下文(134 个调用点!)

**源码**:`internal/service/agent/toolcontext/tool_context.go:21`

`ToolContext` 是每个工具执行时能访问的所有依赖的接口。`Infra`(`service/agent/infra.go:32`)实现了它:

```go
type Infra struct {
    db            *gorm.DB
    cache         *infra.CacheService
    llmRouter     *llm.LLMRouter
    httpClient    *http.Client
    rag           *ragpkg.RAGService
    eventBus      eventbus.EventBus
    pageGEO       *visibility.PageGEOEngine
    sessionStore  tctx.SessionStore
    skillStore    *skills.SkillStore
    registry      *platform.Registry
    decisionStore *agentmemory.DecisionStore
}
```

工具通过 `ToolContext` 访问 DB/Cache/LLM/RAG/EventBus/SkillStore/Platform,不依赖具体 Agent 实现。这是**依赖倒置**——Infra 在 server.go 初始化一次,共享给 SalesAgent、Agent V3、Orchestrator。

### B3. Context 注入到 DAG

`injectContextIntoDAG` / `injectStoreContext`(`react_loop.go` / `react.go`)把 UnifiedContext 和 store URL 注入到每个 DAG 节点的 Args,让工具能读到店铺上下文。

### B4. MultiAgentWorkspace.BuildAgentContext(多 agent 上下文)

见 [05-multiagent-autogoal.md](05-multiagent-autogoal.md) §B3——多 agent 场景下,子 agent 的上下文由共享黑板渲染。

---

## C. LLM Provider 层

### C1. DashScopeProvider:基类

**源码**:`internal/service/llm/dashscope.go`

```go
type DashScopeProvider struct {
    apiKey   string
    endpoint string  // 默认 dashscopeChatURL,可被 LLM_ENDPOINT 覆盖
    http     *http.Client
    model    string  // 默认 qwen-plus,可被 LLM_MODEL 覆盖
    name     string
    metrics  LLMMetricsCollector  // 可选:延迟/tokens/错误率
    usage    LLMUsageRecorder     // 可选:计费
}
```

`ChatCompletion`(`dashscope.go:217`)是核心:
- normalizeMessages 预处理消息
- HTTP POST → 解析 `choices[0].message.content`
- `recordMetrics`(模型、延迟、tokens、是否错误)
- `recordUsage`(计费——但**流式调用不计费**,注释明确"stream usage is not parsed, so stream token consumption is deliberately not billed")

### C2. 四个 Provider embed DashScope

```
DashScopeProvider(基类)
  ├─ deepSeekProvider    (DeepSeek,支持 function calling)
  ├─ grokProvider        (xAI Grok)
  ├─ kimiProvider        (Moonshot Kimi)
  └─ openaiProvider      (OpenAI)
```

只有 DeepSeek 实现了完整的 `ChatCompletionWithTools`(function calling),其他都降级到文本 completion(`dashscope.go:186` 的 stub)。

### C3. LLMRouter:per-shop 模型解析

**源码**:`internal/service/llm/llm_router.go:25` · `internal/service/agent/llm/client.go:41`

```go
// ResolveModel 的解析顺序(client.go:41,9 个调用点)
func ResolveModel(ctx, shopID) string {
    // 1. shop 配置(llm_configs 表,per-shop 模型偏好)
    // 2. LLM_DEFAULT_MODEL 环境变量
    // 3. 默认值(各场景不同:execute=defaultExecuteLLMModel, decompose="deepseek-chat")
}
```

`GetProvider` 根据 shop 配置返回对应的 Provider 实例。这让每个商户能用不同的模型(例如 A 商户用 DeepSeek,B 商户用 Kimi)。

### C4. CallContentLLM:工具侧封装

**源码**:`internal/service/agent/infra.go:145`

```go
func (inf *Infra) CallContentLLM(ctx, shopID, toolName, userPrompt, fallback) (map[string]any, error) {
    provider, _, err := inf.llmRouter.GetProvider(ctx, shopUUID)
    model := inf.llmRouter.ResolveModel(ctx, shopUUID)
    if model == "" { model = "deepseek-chat" }
    // 调用 → ExtractJSON → Unmarshal → 合并到 fallback
    // 任何失败 → FallbackToResult(返回兜底结果,不阻断工具)
}
```

这是工具生成内容的统一入口——所有失败都优雅降级到 fallback map,绝不因为 LLM 故障让工具报错。

---

## D. 完整请求生命周期(串联所有层)

```
1. HTTP 请求到达
   → Gateway(三级认证 + 租户隔离 + feature flag + 配额)
   → RateLimit(分级限流)
   → AgentRollout(灰度 V1/V3)

2. Agent Gateway Handler
   → DecisionStore.Recall(RRF 召回相关记忆)
   → PromptContextProvider.Build(7 层 prompt 上下文)
   → ContextBuilder.Build(量化指标 UnifiedContext)
   → 组装 AgentRequest

3. Agent.Run(唯一入口,ADR 0002)
   → Oracle.Route(领域分类 + 工具预算 + 冲突注入 → Intent)
   → 选 ExecutionStrategy(chat/single/react/plan/goalloop)
   → 策略执行(含 AutonomyGate 过滤、DAG 并行、taskReview 复核)

4. 工具执行(每个工具)
   → ToolContext(Infra 提供 DB/Cache/LLM/RAG/EventBus)
   → 可能调 CallContentLLM(per-shop 模型 + 降级)
   → 可能调 MCP 外部工具(mcp:{conn}:{tool})
   → 可能触发 MCP Apps 面板(ReadResource ui://)

5. 结果处理
   → Synthesizer 汇总
   → DecisionStore.SaveAgentDecision(供 Reflect)
   → PublishAgentEvent(eventbus)
   → SSE 流式返回(agent_card_update / token / done)
```

---

## E. 与其他框架对比

| 维度 | Vela | kimi-code | grok-build |
|---|---|---|---|
| **鉴权** | 三级(Shopify JWT + Merchant JWT + Internal) | DI Scope | Permission + sandbox |
| **租户隔离** | Header/Query 一致性 + ownership check | — | worktree 隔离 |
| **限流** | 分级前缀匹配 + 固定窗口 | — | — |
| **上下文** | UnifiedContext(定量)+ PromptContext(定性) | Session metadata | wire Op |
| **LLM 多模型** | per-shop 配置 + 4 provider | provider 抽象 | sampler |
| **降级策略** | 全链路 fail-open + fallback | — | circuit breaker |

**Vela Gateway 的工程成熟度**:三级认证 + 跨租户防护 + 灰度发布 + 分级限流 + 配额,这是真正的 SaaS 多租户网关设计。其他几个框架要么单机、要么不考虑多租户,Vela 的 Gateway 是为"成千上万个 Shopify 商户同时使用"设计的。

---

## F. 总结:Vela 是被低估的生产级 Agent 平台

经过这次源码级拆解,Vela 的真实水平远超我最初的判断:

1. **架构驱动**:4 份正式 ADR,代码注释里处处标注"Phase X.Y"、"ADR 000N §M",是有规划、有阶段的工程演进。
2. **生产级深度**:分布式调度、崩溃恢复、多租户隔离、计费、灰度——这些是"真在跑"的系统才需要的。
3. **独特创新**:MCP 双向 + Apps、半衰期记忆、置信度降级、领域分类路由、跨副本 cancel 广播——多个点在其他 6 个框架里找不到对应。
4. **诚实的设计**:ADR 明确记录"被否决的方案"、"已知限制"、"不做的事",代码注释诚实标注"legacy"、"deprecated"、"🔴 fix"。

如果要把 7 个框架排个工程成熟度,Vela 在**生产就绪性**和**多租户 SaaS 适配**上排第一,kimi-code 在**架构优雅(DI×Scope)**上排第一,grok-build 在**安全沙箱**上排第一。三者各有不可替代的长板。
