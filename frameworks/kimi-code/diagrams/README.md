# kimi-code 架构图

6 张架构图,**两种格式**都提供:

| 用途 | 格式 | 怎么看 |
|---|---|---|
| **快速浏览**(GitHub 直接渲染) | Mermaid(本文件内嵌) | 往下滚就能看到 |
| **编辑/美化/导出 PNG** | Excalidraw(`.excalidraw` 文件) | 在 [excalidraw.com](https://excalidraw.com) 里 Open |

---

## ① 整体分层架构

```mermaid
flowchart TB
    subgraph Apps["📱 User-facing apps"]
        TUI["TUI<br/>(terminal)"]
        WEB["Web UI"]
        IDE["IDE<br/>(ACP: Zed/JetBrains)"]
    end

    SDK["🔗 @moonshot-ai/klient<br/>(SDK facade)"]
    SERVER["🔗 kap-server<br/>(REST + WebSocket)"]

    subgraph Engine["🤖 agent-core-v2 — the engine"]
        LOOP["Loop"]
        GOAL["Goal"]
        SWARM["Swarm"]
        SUB["Subagent"]
        TOOLS["Tools"]
        CTX["Context"]
        PLAN["Plan"]
        SKILL["Skill"]
        MCP["MCP"]
    end

    subgraph Found["🏗️ Foundation"]
        KOSONG["kosong<br/>(LLM 抽象)"]
        WIRE["Wire<br/>(Op/Model)"]
        DISCOPE["DI × Scope"]
    end

    subgraph Persist["💾 Persistence"]
        WLOG["wire.jsonl<br/>(append log)"]
        STATE["state.json<br/>(atomic doc)"]
        BLOBS["blobs/&lt;sha256&gt;"]
    end

    Apps --> SDK --> SERVER --> Engine --> Found --> Persist
```

**对应拆解**:[01-architecture.md](../01-architecture.md)

---

## ② Agent Loop(Prompt → Turn → Step)

```mermaid
flowchart TB
    subgraph Prompt["1️⃣ Prompt layer"]
        U["User message"]
        GC["Goal continuation"]
        CRON["Cron fire"]
        BG["Background task"]
    end

    subgraph Turn["2️⃣ Turn layer (单线程,排队)"]
        Q["queued"] --> R["running"]
        R -->|"done"| C["completed"]
        R -->|"abort"| X["cancelled"]
        R -->|"error"| F["failed"]
    end

    subgraph Step["3️⃣ Step layer (LLM + 工具循环)"]
        BC["Build context"] --> CL["Call LLM<br/>(kosong)"]
        CL --> TC{"Tool calls?"}
        TC -->|"yes"| ET["Execute tools<br/>(parallel)"]
        ET --> BC
        TC -->|"no"| END["turn ends"]
    end

    Prompt --> Turn --> Step

    %% sidebar
    STEER["↩️ Steer<br/>(user mid-turn)<br/>buffer → flush at step"]
    RETRY["🔁 StepRetry<br/>429/5xx → backoff<br/>max 5 attempts"]
    STEER -.-> Step
    RETRY -.-> CL
```

**对应拆解**:[09-loop.md](../09-loop.md)

---

## ③ 三种多 Agent 模式对比

```mermaid
flowchart TB
    subgraph Swarm["① Swarm mode (并行批处理,最多 128)"]
        direction LR
        SP["Main agent"] -->|"dispatch"| S1["Subagent 1"]
        SP --> S2["Subagent 2"]
        SP --> SN["Subagent N"]
        S1 & S2 & SN -->|"summary XML"| SP
        SCHED["⚡ AgentRunBatch<br/>3-stage: 5 立即 → 700ms → maxConcurrency<br/>+ 自适应 rate limit 退避"]
    end

    subgraph Goal["② Goal mode (串行自治,单 agent)"]
        direction LR
        GP["Main agent"]
        GA["active"] -->|"自治多轮"| GP
        GP --> PAUSED["paused"]
        GP --> BLOCKED["blocked"]
        GP --> COMPLETE["complete"]
        DRIVER["🔄 continuation driver<br/>auto-drives next turn"]
        GA -.-> DRIVER -.-> GP
    end

    subgraph OneOff["③ One-off Subagent (隔离委派)"]
        direction LR
        OP["Main agent"] -->|"spawn"| OS["Subagent<br/>(coder/explore/plan)"]
        OS -->|"summary"| OP
        PROFILES["📋 3 profiles<br/>no Agent tool (no nested spawn)"]
    end
```

**对应拆解**:[02-swarm](../02-swarm.md) + [03-goal-mode](../03-goal-mode.md) + [04-subagent](../04-subagent.md)

---

## ④ Wire Op/Model(事件溯源)

```mermaid
flowchart LR
    subgraph Dispatch["dispatch(op) — 原子四步"]
        direction TB
        D1["1. zod schema validate"] --> D2["2. apply state + payload<br/>→ new state (frozen)"]
        D2 --> D3["3. append to wire.jsonl"]
        D3 --> D4["4. publish toEvent → IEventBus"]
    end

    subgraph Models["Model state (per-agent)"]
        M1["SwarmModel"]
        M2["GoalModel"]
        M3["PlanModel"]
        M4["ContextSizeModel"]
    end

    subgraph Persist["持久化"]
        P1["📁 wire.jsonl<br/>(append-only)"]
        P2["🍴 fork = copy log<br/>+ insert forked marker"]
        P3["🔄 restore = replay apply<br/>(no events, no writes)"]
        P1 --> P2 --> P3
    end

    Dispatch -->|"updates"| Models
    D3 --> P1
```

**对应拆解**:[07-wire-protocol.md](../07-wire-protocol.md)

---

## ⑤ 工具调用全链路

```mermaid
flowchart LR
    LLM["🤖 LLM returns<br/>tool_call"] --> RE["① resolveExecution<br/>→ ToolExecution"]

    RE --> PERM["② Permission chain<br/>(19 policies, first wins)"]

    PERM -->|"allow"| EX["③ execute<br/>via toolScheduler"]
    PERM -->|"ask"| ASK["🙋 ask user"]
    PERM -->|"deny"| DENY["🚫 deny"]

    ASK -->|"approved"| EX
    ASK -->|"rejected"| DENY

    RE -.->|"carries"| ACC["accesses<br/>(file read/write)"]
    RE -.->|"carries"| RULE["approvalRule<br/>(with payload)"]
    RE -.->|"carries"| DISP["display (UI hint)"]

    subgraph Conflict["冲突检测(并行安全)"]
        RR["Read + Read → ok"]
        RW["Read + Write → serialise"]
        ALL["kind:'all' → blocks all"]
    end

    EX -.-> Conflict
```

**对应拆解**:[06-tool-system.md](../06-tool-system.md)

---

## ⑥ kosong · 五大 LLM Provider 统一

```mermaid
flowchart TB
    CP["🔗 ChatProvider.generate()<br/>→ StreamedMessage (async iterator)"]

    subgraph Providers["5 provider adapters"]
        direction LR
        OAI["OpenAI Chat<br/>(legacy)"]
        RES["OpenAI Responses<br/>(reasoning)"]
        ANT["Anthropic<br/>(thinking, tool_use)"]
        GEN["Google GenAI<br/>(functionCall)"]
        KIMI["Kimi (KFC)<br/>+ Ollama compat"]
    end

    Providers --> CP

    CP --> LOOP["generate() — pure function<br/>for await part of stream:<br/>  merge same-type parts<br/>  streamIndex Map routes parallel tool delta<br/>  onToolCall fires AFTER stream ends"]

    LOOP --> OUT1["FinishReason<br/>(completed/tool_calls/truncated/...)"]
    LOOP --> OUT2["ModelCapability<br/>(max_context, vision)"]
    LOOP --> OUT3["TokenUsage<br/>(input/output/cache)"]
    LOOP --> OUT4["Errors<br/>(RateLimitError, ...)"]
```

**对应拆解**:[14-provider-llm.md](../14-provider-llm.md)

---

## Excalidraw 版本(可编辑)

同目录下的 `.excalidraw` 文件是手绘风格的源文件,适合:

- **二次编辑**:改字、调位置、换色
- **导出 PNG/SVG**:做 PPT 或博客配图
- **自由布局**:不受 Mermaid 语法约束

**打开方式**:
1. 访问 https://excalidraw.com
2. 左上角菜单 → **Open** → 选择 `.excalidraw` 文件
3. 即可看到手绘风格渲染

## 重新生成 Excalidraw 版本

```bash
cd frameworks/kimi-code/diagrams
python3 gen_excalidraw.py .
```

纯 Python 标准库,无第三方依赖。
