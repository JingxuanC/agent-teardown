# OpenAI Agents SDK + Google ADK · 对比拆解

> 📁 **源码** · [openai/openai-agents-python](https://github.com/openai/openai-agents-python)(Python) + [google/adk-python](https://github.com/google/adk-python)(Python)
>
> 🔌 **定位** · 两个都是**库级 SDK**（不是 CLI agent），用于**构建** agent 应用，不是直接使用的 coding agent

## 1. 它们和 kimi-code / grok-build / Codex / Pi 的区别

| 维度 | kimi-code/grok-build/Codex/Pi | **Agents SDK / ADK** |
|---|---|---|
| **形态** | CLI/TUI 应用（终端跑） | **Python 库**（`import` 使用） |
| **用户** | 开发者直接用 | 开发者**二次开发**用 |
| **自带 UI** | ✅ TUI | ❌ 纯 API（ADK 有 web UI 但独立） |
| **自带工具** | ✅ bash/file/edit | ❌ 用户自己定义 |
| **自带 session 管理** | ✅ | ⚠️ 部分（Agents SDK 有 sessions） |
| **目标** | 做好一个 coding agent | **让别人做任何 agent** |

**它们是"框架的框架"** —— 离终端用户更远，但抽象层次更高。

## 2. OpenAI Agents SDK

### 2.1 核心概念（4 个原语）

| 原语 | 作用 | 对比 |
|---|---|---|
| **Agent** | LLM + instructions + tools | 类似 kimi-code 的 profile |
| **Handoff** | agent 之间交接控制权 | kimi-code/grok-build 都没有 |
| **Guardrail** | 输入/输出校验（可中止 agent） | 类似 kimi-code 的 permission policy |
| **Session** | 对话历史管理 | 类似 wire.jsonl / SQLite |

### 2.2 设计哲学："Python-first, 最小抽象"

```python
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="You are a helpful assistant")
result = Runner.run_sync(agent, "Write a haiku about coding.")
print(result.final_output)
```

**没有 DSL，没有 YAML，没有图形编辑器**。纯 Python 代码定义 agent。

### 2.3 独特能力

**Handoff（交接）**：
```python
# Agent A 可以把控制权"交接"给 Agent B
agent_a = Agent(
    name="Triage",
    handoffs=[agent_b, agent_c],  # A 可以移交给 B 或 C
)
```
这不是 subagent（父→子→父），是**控制权的完全转移**（A 退出，B 接管）。

**Guardrail（并行校验）**：
```python
# 在 agent 跑之前或之后，并行运行校验
# 如果校验失败，agent 立即中止
```

**Tracing（内置可观测性）**：
```python
# 所有 agent 调用自动 trace
# 可在 OpenAI Dashboard 查看
```

**Sandboxed Code Execution**（2026 年 4 月加入）：
- Modal / E2B / Cloudflare / Vercel 沙箱
- agent 可以在隔离环境执行代码

### 2.4 和我们的反熵框架对照

| 反熵策略 | Agents SDK 怎么做 |
|---|---|
| **压缩** | Session 管理（但无自动 compaction） |
| **隔离** | Sandboxed code execution（Modal/E2B） |
| **验证** | Guardrail（输入/输出校验） |
| **恢复** | Session 持久化 |
| **约束** | Guardrail + sandbox |

## 3. Google ADK (Agent Development Kit)

### 3.1 核心概念

| 概念 | 作用 |
|---|---|
| **Agent** | LLM + instruction + tools（类似 Agents SDK） |
| **Sub-agent** | 父子 agent 关系（有内置多 agent 支持） |
| **Tool** | 函数工具 + MCP 工具 + Google Search 等内置工具 |
| **Session / State** | 跨 turn 状态管理 |
| **Memory** | 跨 session 记忆（✅ 和 Codex 类似！） |
| **Evaluation** | 内置 eval 框架 |
| **Code Executor** | 沙箱代码执行 |

### 3.2 设计哲学："Graph-based, enterprise-grade"

```python
from google.adk import Agent
from google.adk.tools import google_search

agent = Agent(
    name="researcher",
    model="gemini-flash-latest",
    instruction="You help users research topics thoroughly.",
    tools=[google_search],
    sub_agents=[summarizer, fact_checker],
)
```

**显式图结构**：ADK 的多 agent 是**树形/图形**的（类似 Codex 的 agent graph store），不像 Agents SDK 的 handoff（线性交接）。

### 3.3 独特能力

**内置 Memory（跨 session 记忆）**：
- ADK 有 `MemoryService`（类似 Codex 的双阶段记忆）
- 支持跨 session 知识共享
- 这是 kimi-code / grok-build / Pi 都没有的

**内置 Evaluation**：
- ADK 自带 eval 框架（类似 kimi-code 的 Terminal-Bench）
- 不需要额外集成

**Google 生态深度集成**：
- Google Search（内置工具）
- Vertex AI（模型部署）
- Cloud Run（部署 agent）
- BigQuery（数据分析）

**A2A 协议原生支持**：
- ADK 可以把 agent 暴露为 A2A server
- 其他框架的 agent 可以通过 A2A 协议调用

**Web UI（adk-web）**：
- 开发和调试用的可视化界面
- 类似 Codex 的 `codex app` 但独立开源

### 3.4 和我们的反熵框架对照

| 反熵策略 | ADK 怎么做 |
|---|---|
| **压缩** | Session 管理 + Memory（跨 session） |
| **隔离** | Code Executor（沙箱） |
| **验证** | Evaluation 框架 |
| **恢复** | Session + State 持久化 |
| **约束** | Agent 图结构约束 |

## 4. 六框架全面对比

| 维度 | kimi-code | grok-build | Pi | Codex | **Agents SDK** | **ADK** |
|---|---|---|---|---|---|---|
| **形态** | CLI | CLI | CLI | CLI | **库** | **库** |
| **语言** | TS | Rust | TS | Rust | **Python** | **Python** |
| **Agent 编排** | DI×Scope | Crate+Actor | Harness | Server/Client | **Python 代码** | **Python 代码** |
| **多 agent** | swarm(128) | skeptic | 无 | 树形+通信 | **Handoff** | **Sub-agent 树** |
| **跨 session 记忆** | ❌ | ❌ | ❌ | ✅ 双阶段 | ❌ | **✅ MemoryService** |
| **验证** | 3轮审计 | skeptic | 无 | 无 | **Guardrail** | **Evaluation** |
| **沙箱** | ❌ | nono | 容器 | 4平台原生 | **Modal/E2B** | **Code Executor** |
| **可观测** | telemetry | signals | 无 | rollout-trace | **Tracing** | **内置 eval** |
| **A2A 协议** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 原生** |
| **生态集成** | MCP | MCP | .pi/ | cloud-tasks | **OpenAI 平台** | **Google Cloud** |

## 5. 两条路线的根本差异

### OpenAI Agents SDK 的路线："最小抽象"

OpenAI 的哲学是 **"不要隐藏底层"**：

> We suggest that developers start by using LLM APIs directly: many patterns can be implemented in a few lines of code.
> —— [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)（Anthropic 的建议，OpenAI 也认同）

Agents SDK 只提供 4 个原语（Agent / Handoff / Guardrail / Session），其他全靠 Python 代码组合。**没有 DI，没有 wire，没有 goal 状态机**。

**优点**：学习曲线极低，几行代码就能跑。
**缺点**：复杂场景（goal 追踪、compaction、多 agent 拓扑）需要自己实现。

### Google ADK 的路线："企业级全栈"

ADK 的哲学是 **"开箱即用"**：

- 自带 Memory（跨 session）
- 自带 Evaluation
- 自带 Web UI
- 自带 A2A 协议
- 自带 Google Cloud 部署

**优点**：企业场景开箱即用，集成度高。
**缺点**：和 Google 生态绑定深，学习曲线比 Agents SDK 陡。

### 路线选择

```
简单 agent（1-3 个工具，单轮）     → OpenAI Agents SDK
复杂 agent（多工具，多轮，多 agent）→ Google ADK 或 kimi-code 级框架
生产 coding agent（CLI，完整工具链）→ Codex / grok-build / kimi-code
```

## 6. 对反熵增框架的验证

这两个 SDK 进一步验证了我们的五种反熵策略：

| 反熵策略 | Agents SDK | ADK |
|---|---|---|
| **压缩** | Session（基础） | Session + Memory（跨 session） |
| **隔离** | Sandbox（Modal/E2B） | Code Executor |
| **验证** | Guardrail | Evaluation |
| **恢复** | Session 持久化 | Session + State |
| **约束** | Guardrail + Sandbox | Agent 图结构 + Code Executor |

**六个框架（kimi-code / grok-build / Pi / Codex / Agents SDK / ADK）全部能归入五种反熵策略**。这进一步支持了"反熵策略是穷尽的"（虽然我们之前自我反驳说样本太小，但现在样本量到了 6）。

## 7. 一句话总结

> OpenAI Agents SDK 是**最小抽象路线**的代表（4 个原语 + Python 代码组合，几行代码跑起来），Google ADK 是**企业级全栈路线**的代表（内置 Memory + Eval + Web UI + A2A + Google Cloud 集成）。两者都不是 CLI agent（和 kimi-code/Codex 不同），是**构建 agent 的库**。Agents SDK 的 Handoff（控制权交接）和 Guardrail（并行校验中止）是独特贡献；ADK 的跨 session Memory 和 A2A 原生支持是独特贡献。**六个框架的设计全部能归入五种反熵策略，进一步验证了反熵框架的普适性。**
