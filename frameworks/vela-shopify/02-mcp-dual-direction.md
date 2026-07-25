# 02 — MCP 双向集成:Server + Client + Apps + Codex Router

> 这是 Vela 最被低估的子系统。我之前完全没提 Vela 是 MCP **server**,只说了"调外部工具"。

## A. 核心认知:MCP 双向

Vela 与 MCP(Model Context Protocol)的关系是**双向**的:

```
┌─────────────────────────────────────────────────────┐
│  Vela 作为 MCP Server(platform/mcp/protocol.go)    │
│  把自己的 87+ 工具通过 stdio JSON-RPC 暴露给:        │
│  · OpenAI Codex CLI                                 │
│  · 其他 MCP 客户端                                  │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  Vela 作为 MCP Client(platform/mcp/manager.go)     │
│  按 shop 管理商户接入的外部 MCP server:              │
│  · 连接 / 发现工具 / 注册进 ToolRegistry             │
│  · 工具名格式 mcp:{conn}:{tool}                     │
│  · DB 持久化连接状态(MCPConnection 表)              │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  MCP Apps(ADR 0006)                                │
│  工具可声明前端渲染面板(_meta.ui.resourceUri)        │
│  → ReadResource 拉 ui:// bundle → iframe 渲染       │
└─────────────────────────────────────────────────────┘
```

---

## B. MCP Server:Vela 把工具暴露出去

**源码**:`internal/platform/mcp/protocol.go:279`

### B1. JSON-RPC 2.0 类型

```go
// protocol.go:24
type Request struct {
    JSONRPC string          `json:"jsonrpc"`
    ID      any             `json:"id,omitempty"` // nil = notification
    Method  string          `json:"method"`
    Params  json.RawMessage `json:"params,omitempty"`
}

type ServerInfo struct {
    Name    string `json:"name"`
    Version string `json:"version"`
}
```

### B2. Tool 定义(带 Vela 扩展)

```go
// protocol.go:132
type Tool struct {
    Name        string          `json:"name"`
    Description string          `json:"description"`
    InputSchema ToolInputSchema `json:"inputSchema"`
    Meta        *ToolMeta       `json:"_meta,omitempty"`  // 标准 MCP 元数据(MCP Apps 在此)
    UI          *ToolUI         `json:"ui,omitempty"`     // Vela 扩展(已废弃,见 ADR 0006)
    Scenes      []string        `json:"scenes,omitempty"` // Vela 扩展:工具所属场景
}
```

`UIResourceURI()` 方法(`protocol.go:157`)从 `_meta.ui.resourceUri` 取 MCP Apps 的面板资源 URI——这是 ADR 0006 的入口。

### B3. Server 结构

```go
// protocol.go:279
type Server struct {
    mu          sync.Mutex
    executor    ToolExecutor       // 工具执行器(调 Vela 内部工具)
    reqExecutor RequestToolExecutor
    provider    ToolProvider       // 工具列表提供者(ToolRegistry)
    initialized bool
}

func NewServer(executor ToolExecutor, provider ToolProvider) *Server
```

Server 通过 stdio 处理 JSON-RPC 消息,把 Vela 的 ToolRegistry 工具暴露成 MCP 工具。外部 MCP 客户端(如 Codex CLI)可以 `tools/list` 发现所有工具,`tools/call` 调用它们。

---

## C. MCP Client:Vela 接入外部 MCP Server

**源码**:`internal/platform/mcp/manager.go:27`

这是更复杂的部分——商户可以在自己的店里接入第三方 MCP server(例如一个邮件营销 MCP),Vela 负责管理这些连接。

### C1. MCPConnectionManager

```go
// manager.go:27
type MCPConnectionManager struct {
    db       *gorm.DB              // 持久化连接状态
    registry *tools.ToolRegistry   // 注册发现的工具

    mu      sync.RWMutex
    clients map[string]*clientEntry // key: "{shopID}:{name}"
}

type clientEntry struct {
    client *MCPClient
    shopID uuid.UUID
    name   string
    tools  []string // 注册的工具名(用于清理)
}
```

### C2. Connect:三阶段双重检查锁

`Connect`(`manager.go:95`)是生产级并发安全实现:

```
Phase 1: RLock 快速拒绝 — 已存在直接返回错误(不阻塞其他 shop)
Phase 2: 慢 HTTP 连接(在锁外,不阻塞其他 shop 的连接操作)
Phase 3: Lock + 双重检查 — 再查一次(防并发竞争)→ 原子插入
         + DB 持久化(失败则回滚工具注册)
```

**关键细节**:
- 工具注册在 DB 写入**之前**,这样 DB 失败可以 `Unregister` 回滚(`manager.go:147`)。
- 重复 key(DuplicateKey)不报错,而是走 `refreshExistingLocked`——把重装当作"刷新"(工具可能变了)。

### C3. 工具注册:格式转换

`registerMCPTool`(`manager.go:369`)把 MCP 的 `InputSchema` 转成 Vela 的 ToolRegistry 格式,并以 `mcp:{connName}:{originalName}` 命名注册:

```go
registeredName := mcpToolName(connName, t.Name) // "mcp:email_server:send_campaign"
m.registry.Register(&tools.AgentTool{
    Name:        registeredName,
    Description: fmt.Sprintf("[MCP:%s] %s", connName, t.Description),
    Schema:      velaSchema,
    Handle: func(ctx, args) {
        // 转发到外部 MCP server
        capturedClient.CallToolFull(ctx, capturedOriginalName, cleanArgs)
    },
})
```

### C4. 生命周期

- **启动**:`LoadAll`(`manager.go:55`)从 DB 加载所有 `connected`/`disconnected` 状态的连接并重连。
- **关闭**:`Shutdown`(`manager.go:79`)优雅断开所有客户端,注销工具。
- **工具分发**:`CallToolFull`(`manager.go:213`)解析 `mcp:{conn}:{tool}` 格式 → 找到对应 client → 转发调用(剥离 `shop_id` 参数)。
- **资源读取**:`ReadResource`(`manager.go:241`)代理 `resources/read`,供 workbench 拉 `ui://` MCP Apps bundle。

### C5. 持久化模型

```go
// internal/model/mcp_connection.go
type MCPConnection struct {
    ShopID    uuid.UUID
    Name      string
    URL       string
    Status    string  // connected | disconnected | error
    ToolCount int
    LastSeen  *time.Time
    LastError string
}
```

`updateStatus`(`manager.go:336`)有个有趣的修复注释:之前的 `Where().Assign().FirstOrCreate()` 在某 GORM 版本会插入缺 `shop_id`/`name` 的幽灵行,改成显式 `Updates` + 失败时 `Create`。

---

## D. MCP Apps:工具声明前端面板(ADR 0006)

**源码**:`platform/mcp/protocol.go:141` · `handler/mcp_ui_bundles.go`

MCP Apps 把 MCP 从"工具协议"升级成"应用协议"——工具不只返回数据,还能声明"我需要一个前端面板来渲染结果"。

### D1. 声明机制

工具在定义里通过标准 MCP 的 `_meta` 声明:

```go
// protocol.go:141
type ToolMeta struct {
    UI *ToolUI `json:"ui,omitempty"`
}

type ToolUI struct {
    ResourceURI string `json:"resourceUri"` // 指向 ui:// bundle
}
```

### D2. 渲染流程

```
1. 工具执行后,SSE 事件 agent_card_update 带 "card" payload
   (cardPayloadForTool 在 orchestrator.go:157 构建)
2. card 包含 resourceUri + data(结果数据随行,免二次 fetch)
3. 前端收到 → 通过 ReadResource 拉 ui:// bundle
4. bundle 在沙箱 iframe 里渲染,展示工具结果
```

这让第三方 MCP server(通过 Vela client 接入的)也能提供富 UI,而不只是文本结果。

---

## E. MCP Executor:计费 + 身份头

**源码**:`internal/server/mcp_executor.go:20`

```go
type mcpToolCaller struct { ... }

func newMCPToolExecutor(...) {
    // parseHeaderUUID — 从请求头解析身份
    // CallTool — 调用工具
    // RecordAsync — 记录计费(异步)
}
```

MCP 工具调用经过 `mcpToolCaller`,它会:
1. 从 identity headers 解析调用者身份
2. 调用工具
3. 异步记录用量(计费)——`RecordAsync`

测试(`mcp_executor_test.go`)验证了 `TestMCPToolExecutor_BillsWithIdentityHeaders`(带身份头要计费)和 `TestMCPToolExecutor_NoHeaders_StaysUnbilled`(无身份头不计费)。

---

## F. Codex Router:Vela ↔ Codex 集成

**源码**:`internal/service/codex/integration.go:28`

Codex 集成有两个 Phase:

### F1. Phase 1.5:两轮模式

```
Round 1: Codex 看工具目录 → 建议该用哪些工具
         (Vela 把 tool catalogue 字符串注入 Codex prompt)
Round 2: Vela 执行 Codex 建议的工具 → 把结果注入回 Codex
         → Codex 基于结果生成最终回答
```

```go
type CodexRouter struct {
    pool       *CodexPool
    bridge     *MemoryBridge
    toolRunner ToolRunner // Vela 工具执行器(两轮之间用)
    tools      string     // 预构建的工具目录文本
    useMCP     bool       // Phase 2 标志
}
```

### F2. Phase 2:MCP 单轮模式

```go
// integration.go:56
func (r *CodexRouter) WithMCP() *CodexRouter {
    r.useMCP = true
    return r
}
```

当 Codex 配置了 Vela 的 MCP server,`WithMCP()` 启用单轮模式——Codex 自己通过 MCP 协议直接调 Vela 工具,不需要两轮往返。这是更原生、更低延迟的集成。

### F3. Per-shop API Key

```go
// integration.go:66
type ShopKeyFunc func(shopID string) (apiKey string, model string)
```

`ShopKeyFunc` 让每个商户用自己的 Codex API key 和模型,实现多租户成本隔离。

---

## G. 与其他框架对比

| 框架 | MCP 角色 | 特色 |
|---|---|---|
| **Vela** | **Server + Client + Apps** | 唯一双向 + 富 UI 面板 + 多租户 |
| kimi-code | Client | 标准 MCP 客户端 |
| grok-build | 无 | 自有扩展系统(tools+signals+extensions) |
| Codex CLI | Client | 标准 MCP 客户端(Vela 的 Phase 2 对端) |

**Vela 的 MCP 设计哲学**:不只把 MCP 当"调外部工具的协议",而是当成"应用生态的底座"——商户可以接入任意 MCP server 扩展能力,第三方 MCP 工具能提供富 UI 面板,Vela 自己的工具也能被 Codex 等 MCP 客户端复用。这是 7 个框架里 MCP 用得最深、最双向的。
