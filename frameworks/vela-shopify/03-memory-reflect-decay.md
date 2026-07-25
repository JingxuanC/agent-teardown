# 03 — 记忆系统:Mem0 式 Reflect + 半衰期衰减 + Qdrant 去重 + RRF 召回

> 我之前说"reflect+decay+RRF"是对的,但严重低估了复杂度。这是 7 个框架里最丰富的记忆系统。

## A. 三层记忆架构

```
┌─────────────────────────────────────────────────────┐
│  热路径(每轮)                                       │
│  DecisionStore.Recall → RRF 融合                    │
│   ├─ RecallByVector(Qdrant 语义召回)                │
│   └─ RecentDecisions(PG 近因召回)                   │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  冷路径(定时 Reflect)                               │
│  Reflector.Reflect(5 步,PG advisory lock 保护)      │
│   → LLM 抽取 Facts + Insights + L0 摘要              │
│   → 三级去重(hash → Qdrant 0.95 → PG ILIKE)         │
│   → UPSERT Facts(带 halflife)                       │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  持久层                                              │
│  agent_facts(半衰期衰减 · 3 级 scope · entity_tags) │
│  agent_insights(分类 · 置信度 · 来源引用)            │
│  agent_decision_records(决策记录 · reflected_at)    │
└─────────────────────────────────────────────────────┘
```

---

## B. Reflector:Mem0 式加性抽取

**源码**:`internal/service/agent/memory/reflect.go`

### B1. 触发判定:ShouldReflect

`ShouldReflect`(`reflect.go:45`)决定一个 shop 是否该跑 Reflect:

```go
// 四个触发条件(任一满足)
1. unreflected_count >= 10                          // 数据够多
2. 最老未反思决策 > 7 天                              // 数据太旧
3. 距上次反思 > 7 天                                  // 定期反思
4. noveltyEntropy > 2.5 || unreflected_count < 5    // 新颖度高(或数据很少也反思)
```

`noveltyEntropy` 是一个信息熵计算——衡量近期决策的多样性。熵高说明出现了新模式,值得反思;熵低说明重复,暂不反思。

### B2. 5 步 Reflect 循环(ADVISORY LOCK 保护)

`Reflect`(`reflect.go:112`)是核心,用 PG advisory lock 防并发:

```go
// reflect.go:115 — 把 shop UUID 前 8 字节哈希成 int64 锁 ID
lockID := int64(b[0])<<56 | int64(b[1])<<48 | ...
pg_try_advisory_lock(lockID)  // 拿不到锁 = 另一个 goroutine 在反思同个 shop → 返回错误
defer pg_advisory_unlock(lockID)
```

**5 步**:

```
Step 1: SELECT 未反思决策(shop_id + reflected_at IS NULL,限 100 条,按时间正序)
Step 2: LLM 单次调用 → 同时抽取 Facts + Insights + L0 摘要(一个 prompt 三种产出)
Step 3: 三级去重(见下节)
Step 4: UPSERT Facts(ON CONFLICT content_hash)
Step 5: UPSERT Insights + 标记决策已反思(reflected_at + l0_summary)
```

### B3. LLM Prompt(Mem0 加性模式)

`callLLM`(`reflect.go:181`)的 prompt 设计是 Mem0 式的——**给 LLM 看已有的 facts,明确告诉它"不要重复抽取"**:

```go
// reflect.go:204
prompt := fmt.Sprintf(`You are an AI operations analyst. Analyze these Agent decisions and extract:

1. FACTS: 具体持久观察。每条必须有:
   - scope: "shop"(全店) | "agent"(全 agent) | "session"(临时)
   - halflife_hours: 2160(90d) | 720(30d) | 168(7d) | 24(1d)
   - entity_tags: ["product:123","template:seo_audit"]
   - confidence: 0-1

2. INSIGHTS: 跨决策合成的结论
   - category: retention | pricing | content | seo | operations
   - source_refs: 支撑这个 insight 的决策编号

3. L0_SUMMARIES: 每条决策一句话摘要

Existing facts (JSON with integer ids — do NOT re-extract these):
%s  ← 已有 facts 带 id,LLM 可引用而非重抽

Respond ONLY with JSON: {"facts":[...],"insights":[...],"l0_summaries":{...}}`)
```

### B4. 三级去重

`dedupFacts`(`reflect.go:252`)按顺序检查每个 LLM 抽出的 fact:

```
Level 1: content_hash 精确去重
  → HashContent(f.Content) 哈希,DB 查重
  → 命中则跳过

Level 2: Qdrant 语义去重(阈值 0.95)
  → store.SearchFactsSemantic(shopID, content, 1, 0.95)
  → 语义近似命中则跳过
  → Qdrant 不可用时降级到 Level 3

Level 3: PG ILIKE 子串去重(兜底)
  → LOWER(content) LIKE LOWER("%新内容%")
  → 粗粒度,防 Qdrant 宕机时重复
```

这是**渐进降级**设计:精确 → 语义 → 粗子串,任一可用就保证不重复。

### B5. UPSERT Facts(带半衰期)

`upsertFacts`(`reflect.go:287`)用 `ON CONFLICT (content_hash) DO UPDATE`:

```sql
INSERT INTO agent_facts (shop_id, scope, content, content_hash, halflife_hours, entity_tags, status, confidence, created_at)
VALUES (...)
ON CONFLICT (content_hash) DO UPDATE SET
  entity_tags = EXCLUDED.entity_tags,
  confidence = EXCLUDED.confidence,
  status = CASE WHEN agent_facts.status = 'superseded' THEN agent_facts.status ELSE 'active' END
RETURNING id
```

**关键**:
- 冲突时更新 entity_tags 和 confidence,但**不复活已 superseded 的 fact**(`CASE` 保护)。
- `RETURNING id` 拿到稳定 UUID,异步索引到 Qdrant(`go r.store.indexFact(...)`,reflect.go:316)。

---

## C. Fact 模型:半衰期 + 三级 Scope

**源码**:`internal/model/agent_fact.go`

```go
type AgentFact struct {
    ID            uuid.UUID
    ShopID        *uuid.UUID
    Scope         string        // "agent" | "shop" | "session"
    Content       string
    ContentHash   string        // 去重用
    HalflifeHours int           // 2160(90d) | 720(30d) | 168(7d) | 24(1d)
    EntityTags    []string      // ["product:123", "template:seo_audit"]
    Status        string        // active | superseded
    Confidence    float64       // 0-1
    CreatedAt     time.Time
}
```

### C1. 半衰期衰减(不是 TTL 删除)

`PurgeExpiredFactsForShop`(`reflect.go:37` 调用)按半衰期清理过期 facts。这不是简单的"到期删除",而是:
- **session scope**:会话结束后清理
- **shop/agent scope**:按 halflife 衰减——越久没被"强化"(重新抽取/引用),越早被清理
- 半衰期四档对应业务语义:运营策略(90d)、月度模式(30d)、周度趋势(7d)、临时观察(1d)

### C2. 三级 Scope

| Scope | 含义 | 示例 |
|---|---|---|
| `agent` | 适用于所有 shop 的 agent 行为 | "SKU 缺货时优先推荐替代品而非劝退" |
| `shop` | 单个店铺的运营事实 | "该店主卖溜冰鞋(24 SKU)+护具(8 SKU)" |
| `session` | 单次会话临时观察 | "客户这轮在比较 A 和 B 两款" |

这比 kimi-code(只有 session/cross-session 两级)和 Codex(Stage1 短期 + Stage2 长期两级)都更细粒度。

---

## D. 热路径:RRF 召回融合

**源码**:`internal/service/agent/memory/recall.go:117`

### D1. Recall 方法

`Recall` 融合两路召回结果(Reciprocal Rank Fusion):

```go
func (s *DecisionStore) Recall(ctx, shopID, query, agentID, topK) []MemoryRecallResult {
    // 路径 A:语义召回(Qdrant 向量)
    semantic := s.RecallByVector(ctx, queryEmbedding, topK)
    // 路径 B:近因召回(PG 最近决策)
    recent := s.RecentDecisions(ctx, shopID, agentID, topK)
    // RRF 融合:1/(60+rank),合并同源,按融合分数排序
    return rrfFuse(semantic, recent)
}
```

**RRF(Reciprocal Rank Fusion)** 是信息检索经典算法:对每个结果,分数 = Σ 1/(k + rank_in_each_list),k 通常 60。它不需要校准分数,天然融合多路召回。

### D2. 调用方

- `agent_gateway.go` — agent 执行前召回相关记忆
- `prompt/provider.go` — `loadLongTermMemory` 注入 prompt Layer 6
- `service/agent/core.go` — agent 核心循环使用
- `service/agent/memory/conflict.go` — 冲突检测时查历史决策

### D3. RecallEnrichedByAgent

`react_default.go:164` 显示还有按 agent 过滤的增强召回:
```go
decisionCtx = r.decisionStore.RecallEnrichedByAgent(ctx, r.shopID, nil, r.message, 5)
```
这让不同 persona 的 agent 只看到与自己相关的历史决策,避免上下文串扰。

---

## E. Insight 模型:跨决策合成

**源码**:`internal/model/agent_insight.go`

```go
type AgentInsight struct {
    ShopID     uuid.UUID
    Content    string     // 合成的结论
    Category   string     // retention | pricing | content | seo | operations
    Confidence float64
    SourceRefs []string   // 支撑此 insight 的 decision ID 列表(可追溯)
}
```

Insight 是 Reflector 从多条决策中合成的"高阶认知"——不是单个事实,而是模式。`source_refs` 让每个 insight 都可追溯到支撑它的原始决策,这是可解释性的关键。

---

## F. CircuitBreaker:执行保护

**源码**:`internal/service/agent/execute/retry.go:20`

虽然不是记忆专属,但记忆工具调用受 CircuitBreaker 保护:

```go
type CircuitBreaker struct {
    consecutiveFailures int
    state               int    // 0=CLOSED, 1=OPEN, 2=HALF_OPEN
    Threshold           int    // 默认 5 次连续失败跳闸
    Timeout             time.Duration // 默认 30s 后允许单次 HALF_OPEN 探测
    Decay               time.Duration // 默认 2min 无失败则重置计数
}
```

三态机:CLOSED(正常)→ 连续失败达阈值 → OPEN(拒绝所有)→ 超时后 → HALF_OPEN(允许一次探测)→ 成功则 CLOSED / 失败则回 OPEN。`Decay` 是"冷却"机制——长时间无失败自动恢复。

---

## G. 与其他框架对比

| 维度 | Vela | kimi-code | Codex | grok-build |
|---|---|---|---|---|
| **抽取模式** | Mem0 式加性(LLM 看 old facts 不重抽) | 无自动抽取 | Stage2 离线抽取 | 无 |
| **去重** | 三级(hash → 语义 0.95 → ILIKE) | 无 | 无 | 无 |
| **衰减** | 半衰期四档(90d/30d/7d/1d) | 无 | Stage1/Stage2 分离 | wire Op 事件源 |
| **Scope** | 三级(agent/shop/session) | 两级(session/cross) | 两级(短/长) | — |
| **召回** | RRF(语义 + 近因) | blob 加载 | 向量 | 重放 |
| **并发保护** | PG advisory lock | 无 | 无 | 无 |
| **可追溯** | Insight.source_refs → decision | 无 | 无 | wire Op ID |

**Vela 记忆系统的独特价值**:
1. **半衰期衰减**是业务语义驱动的,不是技术 TTL——运营策略 90 天有效,临时观察 1 天就过期,符合电商节奏。
2. **三级去重渐进降级**保证 Qdrant 宕机也能工作。
3. **PG advisory lock** 让 Reflect 在多副本部署下不重复跑——这是生产级考虑,kimi/grok/codex 都没有。
4. **Insight + source_refs** 让合成的结论可追溯,这是可解释 AI 的基础。
