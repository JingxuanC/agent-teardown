# 01 — Skill 三层 · Prompt 7 层 · 9 Persona 协作图

> 全部基于 codegraph 读取的真实源码。引用格式 `文件:行号`。

## A. Skill 系统:三层并存的设计

Vela 的"skill"不是单一概念,而是三个不同层次的抽象,服务于不同场景:

### A1. MerchantSkill — 商户自定义可复用工作流(DB 持久化)

**源码**:`internal/model/skill.go:14` · `internal/service/skills/store.go:29` · `internal/handler/skill_api.go`

这是一个完整的 CRUD 工作流系统,商户可以在对话里让 agent 帮自己把重复操作沉淀成"技能":

```go
// internal/model/skill.go:14
type MerchantSkill struct {
    ID           uuid.UUID      // 主键
    ShopID       uuid.UUID      // 归属店铺
    Name         string         // "退货深度分析" — LLM 生成或商户编辑
    Description  string         // 注入到 Oracle prompt 的描述
    Trigger      string         // 自然语言触发关键词,| 分隔
    Stages       datatypes.JSON // []SkillStage — 与 orchestrator.Stage 同构
    Parameters   datatypes.JSON // [{name, type, description, required, default}]
    Priority     int            // 1-5,数字越小优先级越高
    Status       string         // active | deprecated | superseded
    SupersededBy *uuid.UUID     // 指向新版本(版本化!)
    UsageCount   int            // 使用次数(IncrementUsage 更新)
    LastUsedAt   *time.Time
}

type SkillStage struct {
    Parallel bool     `json:"parallel"` // 同 stage 内工具是否并行
    Tools    []string `json:"tools"`    // 工具名列表
}
```

**关键设计**:
- **版本化**:`Status` + `SupersededBy` 实现技能演进,旧版 deprecated 而非删除,新版 supersede 旧版。
- **优先级排序**:`SkillStore.GetByShop` 按 `priority ASC, usage_count DESC` 排序——优先级高的先用,同优先级用得多的先用。
- **校验**:`SkillStore.Create` 调 `validateStages` 校验 Stages 里引用的工具都存在于 ToolRegistry。
- **使用统计**:`IncrementUsage` 用 `gorm.Expr("usage_count + 1")` 原子自增,记录 `last_used_at`。
- **软删除**:`DeprecateWithoutSuperseder` 只改 status,不物理删除(避免历史决策记录悬空)。

**CRUD 端点**(`handler/skill_api.go`):
```
GET    /api/skills          ListSkills(列出当前 shop 的 active 技能)
POST   /api/skills          SaveSkill(从 preview 确认保存)
DELETE /api/skills/{id}     DeleteSkill(软删除 → deprecated)
```

### A2. AgentSkill — 运行时按关键词注入 prompt 的技能模块

**源码**:`internal/service/agent/storefront/types.go:72`

这是运行时层——当用户消息命中某个 MerchantSkill 的 Trigger 关键词,该技能被实例化成 `AgentSkill` 注入 system prompt:

```go
// internal/service/agent/storefront/types.go:72
type AgentSkill struct {
    Name     string   `json:"name"`
    Content  string   `json:"content"`   // 注入 system prompt 的实际文本
    Priority int      `json:"priority"`
    Triggers []string `json:"triggers"`  // 激活关键词
    Roles    []string `json:"roles"`     // ["customer"] / ["merchant"] 角色限定
}
```

它挂在 `TurnContext.ActiveSkills` 上(`types.go:61`),由 `BuildTurnContext` 在每轮开始时根据用户消息匹配触发词填充。

### A3. Codex Skill Catalogue — 外部技能注册表

**源码**:`internal/server/codex_catalogue.go` · `internal/service/codex/`

这是 Vela 与 OpenAI Codex 集成的技能目录(`CodexRouter.WithToolCatalogue` 注入)。Phase 1.5 是两轮模式(Codex 建议工具 → Vela 执行 → 注入结果);Phase 2 MCP 模式下 Codex 直接通过 MCP server 调 Vela 工具,单轮完成(见 `service/codex/integration.go:28` 的 `CodexRouter`)。

### A4. Oracle 如何消费 Skill

**源码**:`internal/service/orchestrator/oracle.go:239-242`

```go
var skillsBlock string
if o.skillsProvider != nil {
    skillsBlock = o.skillsProvider(ctx, shopUUID, message)
}
// ... 之后 skillsBlock 拼进 BuildOracleSystemPrompt
```

Oracle 在路由前调用 `skillsProvider` 回调,把匹配到的技能描述拼成 `skillsBlock`,作为 system prompt 的一部分。这让商户自定义的技能能影响 LLM 的工具选择。

---

## B. Prompt 7 层组装(ADR 0001)

**源码**:`internal/service/agent/prompt/provider.go` · ADR `docs/adr/0001-unified-prompt-context-provider.md`

### B1. 为什么有这层

ADR 0001 的背景:Vela 有两套 agent 系统(V1 顾客侧 SalesAgent + V3 商家侧 Agent),prompt 构建完全独立,品牌声音有 **4 条独立加载路径**,同一个商家在顾客端和工作台看到不同人格。`PromptContextProvider` 是为了**标准化(不是统一)** prompt 上下文的数据来源和结构。

### B2. PromptContext 结构

```go
// internal/service/agent/prompt/provider.go:35
type PromptContext struct {
    Role            string   // "customer" | "merchant"
    BrandVoice      string   // 展开后的 tone 指令文本(toneRules 映射在 Provider 内部完成)
    StoreIdentity   string   // 店铺卖什么的自然语言描述
    StorePolicy     string   // 退货/发货政策
    ActiveSkills    []string // 匹配当前消息的技能名
    CustomerProfile string   // 仅 role=customer
    LongTermMemory  string   // 历史摘要 + Qdrant 召回,仅 role=customer
    SessionContext  string   // 当前会话轮次/购买阶段,仅 role=customer
}
```

### B3. 两层加载 + 缓存策略

`Build` 方法(`provider.go:92`)分两层:

```
1. 静态层(BrandVoice + StoreIdentity + StorePolicy)
   → 先查 Redis(key: promptctx:{shopID},TTL 5min)
   → miss 则查 PG(sales_agent_configs 表)
   → 查到后回填 Redis

2. 动态层(仅 customerID 非空时)
   → loadCustomerProfile(PG customer_chat_profiles)
   → loadLongTermMemory(历史会话摘要 + Qdrant 向量召回)
   → loadSessionContext(当前轮次 + 购买阶段)
```

**降级路径**:任何一层失败都返回空字段 + warn log,**绝不因为 Provider 故障让 LLM 收到空 system prompt**——调用方保留硬编码静态 fallback。

### B4. 三个方法,三个用途

| 方法 | 用途 | 注入内容 |
|---|---|---|
| `Build` | V3 热路径(fallbackLLM / Execute 主路径) | 全 7 层(merchant 角色跳过动态层) |
| `BuildForRouter` | Oracle 路由器 | **仅 BrandVoice**——Router 的核心是工具调度规则,注入 StoreIdentity/Policy 会膨胀 prompt 干扰工具选择 |
| `BuildSystemText` | V1 SalesAgent(Phase 1b 替代内联拼接) | 消费已构建的 TurnContext,拼接 7 层文本 |

### B5. 7 层结构(BuildSystemText)

`provider.go:440` 的 `BuildSystemText` 按固定顺序拼接:

| Layer | 内容 | 来源 |
|---|---|---|
| 1 | Base role block | 调用方提供(V1 自己的角色前导) |
| 2 | BrandVoice | 静态层 |
| 3 | StoreIdentity("## ABOUT THIS STORE") | 静态层 + 强约束"只推荐这些品类" |
| 4 | StorePolicy("## STORE POLICY") | 静态层 |
| 5 | CustomerProfile | 动态层 |
| 6 | LongTermMemory("## PREVIOUS CONTEXT") | 动态层 |
| 7 | CustomerMemories("## CUSTOMER MEMORIES") | 语义搜索结果 |
| + | SessionContext("## CURRENT SESSION") | 近因信号 |

> Layer 3 后跟一句强约束:`"IMPORTANT: Only recommend products from these categories. Do NOT mention products the store does not sell."` —— 这是防止 LLM 幻觉推荐店铺不卖的品类。

---

## C. 9 Persona 专家系统 + 协作图

**源码**:`internal/service/agent/plan/personas.go:1`

### C1. 为什么有 Persona

Persona 是多 agent 编排(ADR 0003)的角色抽象。每个 persona 代表一个领域专家,绑定特定的工具集、工作流、约束、优先级,以及可以交接给哪些其他 persona。这让 `LLMDecomposer` 拆解 meta-goal 时能给每个子目标分配合适的专家。

### C2. 9 个 Persona 一览

| PersonaID | 中文名 | 工具数 | 优先级 | 可交接给 |
|---|---|---|---|---|
| `inventory_manager` | 库存管理专家 | 5 | 1(最高) | 退货分析师、定价策略 |
| `returns_analyst` | 退货分析师 | 3 | 2 | 库存管理、客户洞察 |
| `pricing_strategist` | 定价策略专家 | 4 | 2 | 营销策略、库存管理 |
| `customer_insights` | 客户洞察专家 | 6 | 2 | 营销策略、退货分析师 |
| `marketing_strategist` | 营销策略专家 | 8 | 2 | 定价、内容、客户洞察 |
| `review_operator` | 评价运营专家 | 3 | 3 | 内容编辑、客户洞察 |
| `seo_specialist` | SEO 优化专家 | 15 | 3 | 内容编辑、营销策略 |
| `content_editor` | 内容创作专家 | 5 | 4 | SEO、营销策略 |
| `data_analyst` | 数据分析师 | — | — | 默认 persona |

### C3. PersonaDef 结构

```go
// internal/service/agent/plan/personas.go:48
type PersonaDef struct {
    ID           PersonaID
    Name         string      // 中文名
    Expertise    string      // 领域描述
    Tools        []string    // 授权工具(白名单)
    Workflow     string      // 偏好工作流
    Constraints  []string    // 运营约束/规则
    Priority     int         // 调度优先级(1=最高,5=最低)
    Collaborates []PersonaID // 可交接的 persona
}
```

**约束示例**(每个 persona 都有业务红线):
- 定价策略:`"折扣幅度不超过 30%"`、`"不损害品牌定位的前提下促销"`
- 客户洞察:`"不直接联系客户"`、`"分析结果需脱敏后展示"`
- 营销策略:`"营销频次不过度骚扰客户"`、`"营销预算不超月营收 15%"`
- 内容编辑:`"内容需符合品牌调性"`、`"不夸大产品功效"`、`"遵守广告法"`
- 退货分析师:`"不处理退货政策咨询(仅分析数据)"`、`"不直接发起退款或换货操作"`

### C4. 协作图(Collaborates)

```
inventory ─┬─→ returns
           └─→ pricing
returns ───┬─→ inventory
           └─→ customer_insights
pricing ───┬─→ marketing
           └─→ inventory
customer_insights ─┬─→ marketing
                   └─→ returns
marketing ─┬─→ pricing ──→ ...(形成网状)
           ├─→ content
           └─→ customer_insights
review ────┬─→ content
           └─→ customer_insights
seo ───────┬─→ content
           └─→ marketing
content ───┬─→ seo
           └─→ marketing
```

这不是硬编码的 DAG,而是 persona 的"可交接"声明——`Coordinator`/`LLMDecomposer` 在拆解 meta-goal 时参考这些关系决定子目标分配给哪个 persona。

### C5. Validate 校验

`personas.go:209` 的 `Validate(toolNames)` 遍历所有 persona,检查每个引用的工具是否在传入的 toolNames 集合里。如果有 persona 引用了未注册的工具,返回错误列出第一个缺失项。这保证了 persona 声明不会引用幽灵工具。

---

## D. 与 kimi-code 的对比

| 维度 | Vela | kimi-code |
|---|---|---|
| Skill 持久化 | MerchantSkill(DB,版本化,优先级,使用统计) | Skills(文件系统,SKILL.md) |
| Skill 激活 | 关键词触发 → 注入 prompt | 显式 /skill 调用或自动加载 |
| Prompt 组装 | 7 层 + Redis/PG 两级缓存 + 降级 | 系统模板 + 上下文注入 |
| 角色系统 | 9 Persona + 工具白名单 + 协作图 | 无独立 persona 概念 |
| Prompt 单一真相源 | PromptContextProvider(ADR 0001) | 各 provider 自己组装 |

**Vela 的独特之处**:Persona 不只是角色标签,而是**工具权限边界**——每个 persona 的 `Tools` 是白名单,多 agent 编排时子 agent 只能用所属 persona 授权的工具。这比 kimi 的"所有工具共享"更细粒度。
