# Agent Teardown

各种 AI Agent 框架的深度拆解文档。每篇文档聚焦一个具体的子系统(调度器、子 agent 编排、工具系统、权限模型等),读源码、画流程、抽模式。

不是教程,不是 README 翻译,是**逆向工程的拆解笔记**。

## 仓库结构

```
frameworks/       # 按框架组织,每个框架一个目录
  <framework>/
    README.md            # 框架总览:技术栈、核心概念、模块地图
    NN-<module>.md       # 具体模块拆解(两位数前缀排序)
templates/        # 拆解文档模板
insights/         # 跨框架对比与抽象出的设计模式
```

## 收录范围(进行中/已完成)

| 框架 | 语言 | 状态 | 关注点 |
|---|---|---|---|
| [kimi-code](frameworks/kimi-code/) | TypeScript | 🔄 拆解中 | 群体智能、goal mode、DI × Scope 架构 |

未来可能加入:Claude Code、Cursor、Aider、OpenAI Codex、Devin、Goose 等。

## 写作规范

- **基于真实源码**:所有结论必须能在源码里指到具体文件、行号或符号。不写"我觉得"、"可能是"。
- **代码块带出处**:引用源码时,在代码块上方标注路径与关键行号,如 `agentRunBatch.ts:195-220`。
- **图优于文字**:架构、状态机、调用流都用 mermaid 画图,再配文字解释。
- **先整体后细节**:每篇拆解按「目标 → 架构 → 关键流程 → 边界条件 → 设计权衡」的顺序展开。
- **对比而非孤立**:能在 `insights/` 里抽象成通用模式的,就抽出来,便于跨框架对比。
- **中文为主,术语保留英文**:例如"调度器"、"并发限制"用中文,`rate limit`、`backoff` 这类保留英文。

## 工作流

1. 选定框架 + 模块(例如 kimi-code 的 swarm)
2. 用 codegraph / ripgrep 通读相关源码
3. 按模板写拆解文档,放到对应 `frameworks/<framework>/` 目录
4. 发现跨框架通用模式时,在 `insights/` 单独立项
5. PR 自审后合并到 main

## 文件命名

- 目录用框架的官方名(小写,连字符):`kimi-code`、`claude-code`
- 文件用 `NN-kebab-case.md`,两位数前缀控制阅读顺序:`01-architecture.md`、`02-swarm.md`
- 不要用日期前缀,拆解是按逻辑顺序排,不是按时间
