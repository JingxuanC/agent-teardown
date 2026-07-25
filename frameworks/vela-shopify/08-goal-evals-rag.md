# 08 — GoalRunner + Verifier · evals 评估系统 · RAG 引擎

## A. GoalRunner:目标循环执行引擎(ADR 0004 核心)

**源码**:`internal/service/agent/goal/runner.go` + `verifier.go` + `spec.go`

之前 05 篇拆了 Scheduler(调度)和 Goal(模型),但没拆**真正跑一轮目标**的引擎。这是 ADR 0004 execute→verify→reflect 的实现。

### A1. GoalSpec — 目标规格

```go
// spec.go
type GoalSpec struct {
    Description string  // 目标描述
    Metric      string  // "seo_score"、"conversion_rate"
    Target      float64 // 80、0.02
    Operator    string  // ">=" | "<=" | "==" | "increase_by"
    MaxRounds   int     // 默认 5
}
```

### A2. GoalRunner.Run — 多轮 execute→verify 循环

`runner.go:49` 的核心循环:

```go
for state.Round = 1; state.Round <= goal.MaxRounds; state.Round++ {
    // 1. 上下文取消检查(steering interrupt)
    select { case <-ctx.Done(): state.DoneReason = "cancelled"; return }

    // 2. 构建本轮消息
    message := goal.Description
    if state.Round > 1 {
        message = state.BuildReflection()  // ★ 反思上轮结果,调整策略
    }

    // 3. 执行(注入的 AgentExecutor — 解耦于 agent 包)
    result, err := r.execute(ctx, shopID, message, nil)

    // 4. 提取节点结果文本
    nodeResults := resultsFn(result)  // 调用方提供的渲染函数

    // 5. ★ 验证
    verdict, err := r.verifier.Check(ctx, shopID, goal, nodeResults)
    state.CurrentValue = verdict.Score
    state.Suggestions = verdict.Suggestions

    // 6. 终止判定
    if verdict.Achieved {
        state.DoneReason = "achieved"; return
    }
    // ★ 停滞检测:分数没涨 + 没新建议
    if state.Round > 1 && prevRoundValue > 0 &&
       verdict.Score <= prevRoundValue && len(verdict.Suggestions) == 0 {
        state.DoneReason = "stalled"; return
    }
}
state.DoneReason = "max_rounds"
```

**三个终止条件**:
1. **achieved** — Verifier 判定目标达成
2. **stalled** — 分数没涨且没有新建议(连续无进展)
3. **max_rounds** — 跑满 MaxRounds 轮

**关键设计**:
- **AgentExecutor 是注入的函数类型**(`runner.go:21`),不是接口——`func(ctx, shopID, message, history) (*DAGResult, error)`。这让 goal 包完全解耦于 agent 包,测试时可以直接传 fake。
- **AutonomyGate 不在 Runner 里**——注释 `runner.go:24` 明确:"The AutonomyGate is NOT handled here — the injected AgentExecutor applies it internally per round." Gate 在每轮执行的 AgentExecutor 内部生效。
- **反思**——第 2 轮起用 `state.BuildReflection()` 替代原始描述,把上轮结果+建议编织进新消息,让 agent 换打法。
- **停滞检测**——不只看"没达成",还看"有没有在进步"。分数持平 + 没新建议 = 真的卡住了,不再浪费轮次。

### A3. Verifier — LLM 判定目标是否达成

`verifier.go:28`:

```go
type Verifier struct {
    llmCall func(ctx, prompt) (string, error)
}

func (v *Verifier) Check(ctx, shopID, goal GoalSpec, nodeResults string) (*Verdict, error) {
    prompt := buildVerificationPrompt(goal, nodeResults)
    resp, _ := v.llmCall(ctx, prompt)
    return parseVerdict(resp)  // {Achieved, Score, Reasoning, Suggestions}
}
```

`Verdict`:
```go
type Verdict struct {
    Achieved    bool
    Score       int      // 0-100
    Reasoning   string
    Suggestions []string // 下轮建议
}
```

**双模验证**(ADR 0004 §2):
- **可量化目标**(有 Metric + Target):Verifier 读 metric 数据对比 target
- **不可量化目标**(Metric 为空):LLM judge + 人工 review

### A4. GoalState — 状态追踪

```go
type GoalState struct {
    Goal          GoalSpec
    Round         int
    Achieved      bool
    Done          bool
    DoneReason    string   // "achieved" | "stalled" | "max_rounds" | "cancelled" | "error"
    CurrentValue  float64
    LastAction    string
    TriedActions  []string
    Suggestions   []string
}
```

`BuildReflection()`(`spec.go`)把上轮的 LastAction + Suggestions 编织成"反思消息",让下轮 agent 知道之前试了什么、结果如何、该换什么打法。

### A5. detector.go — 目标检测

`detector.go` 判断一条用户消息是否应该升级为长周期 Goal(ADR 0004 §4 的路由判定),检测时间跨度词、可测量目标值、多域 scope 等信号。

---

## B. evals/:agent 质量评估系统(3,048 行)

**源码**:`api-server-go/evals/`

这是 Vela 的**评估闭环**——怎么知道 agent 好不好。

### B1. 6 维度评分体系(scheme.go)

`EvalDimension` 定义 6 个评分维度:

| 维度 | 含义 | 权重示例 |
|---|---|---|
| `DimBrandVoice` | 品牌声音一致性 | 问候场景权重 2 |
| `DimCorrectness` | 正确性(事实/数据准确) | 分析场景权重 2 |
| `DimRobustness` | 鲁棒性(空消息/乱码不崩) | 边缘场景权重 2 |
| `DimPlanQuality` | 规划质量(步骤数/可执行性) | 目标场景权重 2 |
| `DimToolUsage` | 工具使用(选对工具) | SEO 场景权重 2 |
| `DimPersona` | 人格保真度(不说"I'm just an AI") | 商家场景权重 2 |

### B2. SchemeSpec — 测试方案(scheme.go:59)

```go
type SchemeSpec struct {
    Category        ConversationCategory
    Description     string
    Role            string         // "customer" | "merchant"
    ExpectPlanner   bool           // 是否期望进入规划器
    MinPlanSteps    int            // 最少规划步数
    ExpectedTools   []string      // 期望使用的工具
    ForbiddenTools  []string      // 禁止使用的工具
    PersonaMarkers  []string      // 人格标志词("Vela","运营","AI","伙伴")
    AntiMarkers     []string      // 反人格标志("I'm just a bot","I cannot")
    Tone            string
    Weights         SchemeDimensionWeights
    ExampleMessages []string
}
```

### B3. 11 个测试场景分类

`Scheme()`(`scheme.go:76`)定义 11 个场景的完整测试方案:

**顾客侧**(3 个):
- `CatCustomerGreeting` — 问候,友好回应,不进规划器
- `CatCustomerProductInquiry` — 产品咨询,准确有帮助
- `CatCustomerChitchat` — 闲聊,自然回应

**商家侧**(6 个):
- `CatMerchantGreeting` — Vela 自我介绍为"AI 合伙人"
- `CatMerchantGoalPlanning` — 设增长目标 → 进规划器(≥3 步)
- `CatMerchantAnalytics` — 数据分析 → 用分析工具
- `CatMerchantDiagnostic` — 完整店铺诊断
- `CatMerchantSEOAudit` — SEO 审计 → 用 SEO 工具
- `CatMerchantChitchat` — 商家闲聊,专业但有温度

**边缘场景**(3 个):
- `CatEdgeEmptyMessage` — 空消息,优雅处理不崩
- `CatEdgeGibberish` — 乱码,追问澄清不崩
- `CatEdgeGuardHallucination` — 要求不存在的能力,重定向到可用工具

**AntiMarkers 的设计哲学**:每个场景都列了**不该出现的词**。例如:
- 顾客闲聊:不能出现 "plan"、"step"、"agent_card_update"(不该触发工具)
- 商家问候:不能出现 "I'm just a bot"、"how can I assist"、"I cannot help"
- 边缘防护:不能出现 "Sure, I'll do that"(不能假装能做做不到的事)

### B4. LLMJudge — LLM 即裁判(judge.go)

```go
type DirectJudge struct {
    provider *dashScopeJudge
    model    string  // "deepseek-chat"(快便宜,不是被测模型)
}

func (j *DirectJudge) Score(ctx, c EvalCase, response, plannerEntered) ([]EvalScore, error) {
    userPrompt := buildJudgePrompt(c, response, plannerEntered)
    resp, _ := j.provider.ChatCompletion(ctx, req)
    // 解析 6 维度 JSON 评分
    // LLM 失败 → manualScore(规则兜底)
}
```

**关键**:Judge 用**不同于被测模型的模型**(`deepseek-chat` 评判,被测可能是 `gpt-4o`),避免同模型自评偏见。Judge 失败时降级到 `manualScore`(基于 AntiMarkers/MustContain 的规则匹配)。

### B5. 测试文件

| 文件 | 行数 | 测试内容 |
|---|---|---|
| `closed_loop_test.go` | 491 | 闭环测试:消息→agent→结果→judge |
| `full_scenario_test.go` | 587 | 11 场景完整跑通 |
| `oracle_scenario_test.go` | 217 | Oracle 路由准确率 |
| `eval_test.go` | 462 | eval 框架本身 |
| `agent_pure_compute_test.go` | 117 | 纯计算(无 LLM)路径 |
| `phase5_services_test.go` | 99 | Service 注入路径 |

---

## C. RAG 引擎(1,781 行)

**源码**:`internal/platform/rag/`

之前 03 篇(记忆)只提了 Qdrant 用法,没拆 RAG 内部流水线。

### C1. 架构(types.go 包注释)

```
EventBus → ChunkFactory(PII 脱敏) → Asynq → Ollama Embed → Qdrant
降级:Ollama 或 Qdrant 失败 → 回退到 SQL-only
```

**本地优先**(`types.go:4`):"All embeddings are computed locally via Ollama (nomic-embed-text). All vectors are stored in Qdrant with per-tenant collection isolation. No merchant data leaves the server during embedding or storage."

### C2. 核心组件

| 文件 | 作用 |
|---|---|
| `chunker.go` | 文本分块(200-800 字符),PII 脱敏 |
| `embedder.go` | OllamaEmbedder — 调本地 Ollama `/api/embed` |
| `indexer.go` | 异步批量索引(Asynq 任务队列,MaxBatchSize=50) |
| `retriever.go` | 语义检索 + embedding 缓存(Redis,TTL 30min) |
| `fetcher.go` | 数据获取(SQL + 向量混合) |
| `service.go` | RAGService 统一入口 |

### C3. Embedding 缓存(retriever.go)

```go
func embedCacheKey(shopID, query string) string {
    hash := md5.Sum([]byte(shopID + ":" + query))
    return fmt.Sprintf("rag:query_emb:%x", hash)
}
```

查询 embedding 按 `shopID:query` 缓存到 Redis(30min TTL)。序列化用 IEEE 754 二进制(`serializeEmbedding`),无损且紧凑(每个 float32 → 4 字节)。

### C4. 三种检索方式

```go
SearchWithText(ctx, shopID, query, opts)    // 文本 → embed → 搜索(per-shop collection)
SearchByVector(ctx, shopID, vector, opts)    // 预计算向量 → 搜索
SearchCollection(ctx, collectionName, query, opts)  // 搜索命名 collection(如 tool_semantic 全局索引)
```

### C5. Chunk + SearchOptions(支持 agent/goal 隔离)

```go
type ChunkMeta struct {
    AgentID string  // ★ Phase 2: 归属 Agent UUID
    GoalID  string  // ★ goal-scoped memory
    // ...
}

type SearchOptions struct {
    AgentID *uuid.UUID  // ★ scope to one Agent(nil = all)
    GoalID  *uuid.UUID  // ★ scope to one Goal
    Sources []string
    MinScore float64
}
```

这和 07 篇的 `RecallByAgentGoal` 对接——Qdrant 搜索时用 `should: agent_id=? OR is_empty` 过滤,实现子 agent 记忆隔离。

### C6. 混合检索 MergePrompt

```go
func MergePrompt(sqlResult any, vectorHits []ChunkHit) string {
    // [精确数据 — 来自数据库]
    // SQL 结果
    // [语义上下文 — 来自 AI 知识库]
    // 向量命中(截断 300 字符,带 source + relevance%)
}
```

SQL 精确数据 + 向量语义召回拼成 LLM 上下文——经典 RAG 模式。

### C7. Collection 隔离

```go
func CollectionName(shopID string) string {
    if len(shopID) > 12 { shopID = shopID[:12] }
    return CollectionPrefix + shopID  // "rag_" + shopID前12字符
}
```

每个 shop 一个 Qdrant collection,物理隔离。默认维度 768(nomic-embed-text),DefaultTopK=10,DefaultMinScore=0.5。

---

## D. 三系统如何协作

```
用户设目标:"转化率一周内 +2%"
  → Oracle 检测到长周期信号(detector.go)
  → GoalEngine.Create + 首轮

每轮(Scheduler tick 触发):
  GoalRunner.Run:
    1. BuildReflection(上轮结果→调整策略)
    2. execute(React / Coordinator DAG)
       └─ 工具调 RAG.SearchWithText 检索相关知识
       └─ DecisionStore.RecallByAgentGoal 召回该 goal 历史决策
    3. verifier.Check(LLM 判定是否达成 + 给建议)
    4. 停滞检测 / 达成检测
    5. 摘要 append 到 Goal.Conversation

评估(开发时):
  evals/ 跑 11 场景 → LLMJudge 6 维度打分
  → 确保 agent 质量 regression
```

---

## E. 与其他框架对比

| 维度 | Vela | kimi-code | grok-build | Codex |
|---|---|---|---|---|
| **目标循环** | GoalRunner(execute→verify→stall 检测) | Goal mode | goal complete 6 子系统 | — |
| **验证** | LLM Judge + metric 数据双模 | — | skeptic panel | — |
| **停滞检测** | 分数持平+无建议→stalled | — | doom loop 检测 | — |
| **评估系统** | 6 维度×11 场景×LLM judge | harness 7 层 | — | — |
| **RAG** | 本地 Ollama+Qdrant,per-shop 隔离 | — | — | Stage1+Stage2 |
| **embedding 缓存** | Redis MD5(shopID:query),30min | — | — | — |

**Vela 独有**:
1. **停滞检测**——不只检测 doom loop(循环),还检测"有在跑但没进步"(分数持平)。比 grok 的 doom loop 检测更细。
2. **6 维度×11 场景评估**——这是唯一有成体系 eval framework 的。AntiMarkers 设计(不能出现什么词)比正面评分更防"AI 味"。
3. **本地优先 RAG**——embedding 不出服务器(Ollama),对商户数据隐私是硬承诺。
