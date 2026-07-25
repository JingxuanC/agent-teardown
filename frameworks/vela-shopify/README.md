# Vela Shopify Agent 拆解

Vela 是一个**生产级 7×24 电商 AI agent**。Go 实现，~30K 行 agent 代码。七个框架中唯一真正在生产环境运行的 agent（不是工具/框架/SDK）。

**仓库**:https://github.com/JingxuanC/vela-shopify
**本地路径**:`~/vela-shopify/`

## 拆解路线图

| # | 模块 | 状态 | 核心内容 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | DAG 编排 + 多策略 + 记忆衰减 + AutoGoal + K8s 沙箱 + 七框架对比 |
| 02 | [深度模块拆解](02-deep-modules.md) | ✅ | ReAct+DAG+Gate+Guard / 记忆12文件(reflect+decay+RRF) / AutoGoal+Verifier / 五策略+Circuit Breaker |

## 关键发现速览

- **唯一的生产 7×24 agent**:cron + event + autogoal 实现真正的连续自治运行。其他六个框架都是"工具"或"框架"。
- **DAG 任务编排**:不是线性 ReAct 循环,是有依赖关系的有向无环图。AutonomyGate 做 DAG 级权限过滤(阻止节点 → 依赖节点也被剪掉)。
- **记忆系统比 Codex 更丰富**:reflect(冷路径反思,从决策提取事实)+ decay(记忆衰减,过期清理)+ RRF(Reciprocal Rank Fusion,多路召回融合)。Codex 有 reflect 但没有 decay 和 RRF。
- **AutoGoal + Verifier**:自动目标系统 + LLM 验证器(类似 grok-build skeptic,但单 agent 版)。支持取消和实时 steering。
- **K8s Pod 沙箱**:容器级隔离,适合 SaaS 多租户。
- **多策略执行**:agent 根据场景自动选择策略(react/singlepass/goalloop/plan/chat)。
- **AutonomyGate**:DAG 级权限门,过滤 CONFIRM 工具 + 剪掉被阻止的依赖。
- **Vela 证明了论文方向**:7×24 能力不仅被 OpenAI(Codex)在实现,也被独立开发者在生产中实现。
