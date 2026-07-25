# Vela Shopify Agent — 深度拆解(v2,源码级)

> 基于 codegraph 读取真实源码 + 4 份 ADR 设计文档。替换 `_archive-shallow/` 里的浅版本。

## 文档索引

| # | 文档 | 主题 |
|---|---|---|
| 00 | [deep-overview.md](00-deep-overview.md) | 全景地图 + 纠正之前的错误判断 + 与 6 框架对比 |
| 01 | [skill-prompt-persona.md](01-skill-prompt-persona.md) | Skill 三层(MerchantSkill/AgentSkill/Codex)+ Prompt 7 层 + 9 Persona 协作图 |
| 02 | [mcp-dual-direction.md](02-mcp-dual-direction.md) | MCP 双向(Server+Client)+ MCP Apps(ADR 0006)+ Codex Router |
| 03 | [memory-reflect-decay.md](03-memory-reflect-decay.md) | Mem0 式 Reflect + 半衰期衰减 + 三级去重 + RRF 召回 |
| 04 | [react-oracle-gate.md](04-react-oracle-gate.md) | Oracle 路由(领域分类+预算)+ ReAct 双实现 + AutonomyGate 四规则 |
| 05 | [multiagent-autogoal.md](05-multiagent-autogoal.md) | DAG-of-Agents + 共享黑板 + 持久化恢复 + 分布式 Scheduler + Steering |
| 06 | [gateway-context-llm.md](06-gateway-context-llm.md) | HTTP Gateway(三级认证+租户隔离)+ UnifiedContext + LLM Provider |
| 07 | [subagent-identity-harness.md](07-subagent-identity-harness.md) | 子 Agent 身份隔离:AgentNodeSpec Harness + ServiceRegistry + agentctx + 沙箱双路径 |

## 被纠正的关键错误

之前的浅版本(已归档到 `_archive-shallow/`)有三个严重误判:

1. ~~"Vela 没有多 agent"~~ → 实际有完整的 DAG-of-Agents(ADR 0003)
2. ~~"记忆是简单的 reflect+decay"~~ → 实际是 Mem0 式加性抽取 + 三级去重 + 半衰期四档
3. ~~"MCP 就是调外部工具"~~ → 实际是双向(Server+Client)+ MCP Apps 富 UI

## 技术栈

- **语言**:Go 1.26(module `github.com/JingxuanC/vela-ai-api`)
- **代码量**:1,391 个 Go 文件
- **核心包**:`service/agent/`(169 文件)、`service/multiagent/`(15)、`service/autogoal/`(24)、`service/orchestrator/`(28)
- **设计文档**:`docs/adr/0001-0004` 四份正式 ADR
- **codegraph 索引**:1391 文件,7/21 建索引
