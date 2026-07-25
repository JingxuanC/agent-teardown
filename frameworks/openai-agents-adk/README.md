# OpenAI Agents SDK + Google ADK 对比拆解

两个大厂的**库级 agent SDK**（不是 CLI agent）。用于构建 agent 应用，不是直接使用的 coding agent。

## 拆解路线图

| # | 模块 | 状态 | 核心内容 |
|---|---|---|---|
| 01 | [对比拆解](01-comparison.md) | ✅ | 六框架全面对比 + 两条路线差异 + 反熵验证 |

## 关键发现速览

- **OpenAI Agents SDK**：4 个原语（Agent/Handoff/Guardrail/Session）+ Python-first + 最小抽象。Handoff（控制权交接）和 Guardrail（并行校验中止）是独特贡献。
- **Google ADK**：企业级全栈 + 内置 Memory（跨 session）+ Evaluation + Web UI + A2A 原生支持。Sub-agent 树形结构和 MemoryService 是独特贡献。
- **六个框架全部能归入五种反熵策略**（kimi-code/grok-build/Pi/Codex/Agents SDK/ADK），进一步验证了反熵框架的普适性。
- **两条路线**：OpenAI "最小抽象" vs Google "企业级全栈"。前者学习曲线低，后者开箱即用。
