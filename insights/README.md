# Insights · 跨框架洞察

这个目录收录**跨多个 agent 框架抽象出来的通用设计模式**。单篇拆解看的是"它怎么做",这里看的是"大家都怎么做 / 应该怎么做"。

## 计划中的对比主题

| 主题 | 涉及框架 | 状态 |
|---|---|---|
| [多 agent 调度策略对比](01-multi-agent-scheduling.md) | kimi-code(swarm)、AutoGen、CrewAI、LangGraph | ✅ |
| [CLI 渲染跨框架对比](02-cli-rendering.md) | kimi-code、Claude Code、Aider、Cursor | ✅ |
| [Agent 本质 —— 反熵增](03-agent-essence.md) | 六大厂 + kimi-code + grok-build 35 篇拆解 | ✅ |
| 子 agent 上下文隔离的三种方案 | kimi-code(scope)、Claude Code(worktree)、Cursor(?) | ⏳ |
| Rate limit 退避的工程实践 | kimi-code、Anthropic SDK、OpenAI SDK | ⏳ |
| Plan mode / 审批沙箱 | kimi-code、Claude Code、Cursor | ⏳ |
| Tool 系统的权限模型 | kimi-code、Claude Code、MCP | ⏳ |
| Agent 持久化的状态机设计 | kimi-code(wire+op)、Claude Code(session)、Devin | ⏳ |

每篇对比文档的结构:

1. **问题陈述**:这个设计选择要解决什么
2. **各方案速览**:每个框架怎么做的(链接到对应拆解)
3. **维度对比**:用表格列关键差异
4. **取舍分析**:什么场景适合什么方案
5. **通用模式抽象**:能不能抽出一个 reference design

## 写作触发条件

当某个模式在 **>=2 个框架**的拆解里都出现,且实现有明显差异时,就在这里立一个新主题。
