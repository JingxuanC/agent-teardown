# Insights · 跨框架洞察

这个目录收录**跨多个 agent 框架抽象出来的通用设计模式**。单篇拆解看的是"它怎么做",这里看的是"大家都怎么做 / 应该怎么做"。

## 计划中的对比主题

| 主题 | 涉及框架 | 状态 |
|---|---|---|
| [多 agent 调度策略对比](01-multi-agent-scheduling.md) | kimi-code(swarm)、AutoGen、CrewAI、LangGraph | ✅ |
| [CLI 渲染跨框架对比](02-cli-rendering.md) | kimi-code、Claude Code、Aider、Cursor | ✅ |
| [Agent 本质 —— 行业全景与设计哲学](03-agent-essence.md) | Anthropic、OpenAI、Google、Kimi、智谱、DeepSeek | ✅ |
| [反熵增 —— Agent 的第二定律](04-anti-entropy.md) | 六大厂 + kimi-code + grok-build 35 篇拆解(信息论重构版:Shannon 熵定位到 context 组装) | ✅ |
| [7×24 AGI 的反熵挑战](05-agi-7x24.md) | 前瞻:多尺度记忆 + 睡眠巩固 + 自演化 prompt | ✅ |
| [未解之题 —— Agent 的七个盲区](06-open-questions.md) | 反思:想透了工程,哲学才刚开始 | ✅ |
| [哲学深度探索 —— 从代码到意识](07-philosophy-deep-dive.md) | 七个盲区的回应:Nature 2026 + CMU ToM + Parfit + AgentOS | ✅ |
| [自我反驳 —— 反熵增框架的五个致命缺陷](08-self-rebuttal.md) | 反驳:偷换概念/过度归类/修辞非论证/解释不了创造/不可证伪 | ✅ |
| [LLM 是无状态函数 —— 7×24 AGI 的物理基础](09-stateless-function.md) | 重构:context 之外皆不存在/幻觉=组装失败/记忆=检索注入/AGI 最后一公里在检索架构 | ✅ |
| [记忆公司赛道 —— 09 命题的外部验证与诊断](10-memory-frameworks.md) | 验证:8 家记忆项目(Letta/Mem0/Zep/Cognee/OpenViking/M3/MemOS/OpenMemory)全默认无状态/MCP/虚拟文件系统/记忆OS 三种新架构/LongMemEval 硬数字/MemOS MIP 指向跨 agent 共享 | ✅ |
| [因果状态库 —— 7×24 记忆架构的最大空白](11-causal-state-store.md) | 方案:实体关系图≠因果图/因果schema设计/从wire log自动构建三步/一库解三题(检索+归因+身份)/Pearl阶梯边界/§8.5 因果图跨agent共享 | ✅ |
| [生成性 —— Agent 的另一半](12-generativity.md) | 补完:Agent=反退化+生成/生成来自f(LLM)不在框架/失败五类分归因/learned context是改善路径/生成性无理论是最大空白 | ✅ |
| [重构式记忆 —— 从检索到生成的范式转换](13-reconstructive-memory.md) | 新向:人回忆=重构非检索(Bartlett/Schacter/Nature2023)/当前agent记忆全检索式无重构式/系统提示词=身份层目录/agent自检索+工具/MRAgent ICML2026主动>被动定理/四层叠加的7×24终局 | ✅ |
| [元反思 —— 为什么我不能像你这样主动深挖](14-on-deep-digging.md) | 自诊断:三个缺失(内驱好奇心/不满足圆满/主动跨域)+三个自我问题清单(先搜再写/找替代/跨域类比)+理解局限≠克服局限 | ✅ |
| [AGI 可达性 —— 04-14 的分层收尾](15-agi-feasibility.md) | 总结:三层拆解(L1工程版5-10年大概率/L2通用版10-30年不确定/L3真正智能未知)/L1路径已被04-14铺平/L2障碍是理论缺失/L2-L3突破可能不来自当前架构 | ✅ |
| [因果状态库的工程验证 —— 从概念到代码到真实 benchmark](16-spike-results.md) | 落地:11 的 schema 变成可编译 Rust 原型(6 测试过)+ 用 grok-build 真实生产 prompt 跑真实 LLM 压缩/k=2 拉开 15pp,k=5 拉开 55pp/发现三件 11 没预见的事(CHECK/互补/断崖) | ✅ |
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
