# Pi Agent 拆解

Pi 是一个"自扩展"（self-extensible）的 agent harness，由 earendil-works 开发。TypeScript 实现，~10 万行，7 个包。

**仓库**:https://github.com/earendil-works/pi
**官网**:https://pi.dev
**本地路径**:`~/pi/`

## 拆解路线图

| # | 模块 | 状态 | 核心内容 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | 7 包分层 + Session Tree + Branch Summarization + 三框架对比 |

## 关键发现速览

- **Session Tree 是最大创新**:不是线性时间线,是树形结构,允许回溯和保留探索历史。Branch summarization 把旧分支摘要(不删除),让 agent 能"回到过去重新尝试"。
- **走"最信任 LLM"路线**:无内置权限、无 skeptic panel、无 doom loop 检测。靠容器化(Docker/Gondolin/OpenShell)保障安全。和 grok-build 的"对抗性不信任"形成光谱两端。
- **pi-ai 是最强的 provider 抽象**:8+ provider(含 Bedrock/Vertex/Mistral/Codex WebSocket),自动 model catalog,全 OAuth credential store。
- **自扩展系统最灵活**:.pi/extensions/ 加载 TypeScript 文件(不是纯文本),能动态添加 UI 组件和工具。
- **无内置验证**:没有 goal 状态机、没有 skeptic、没有 plan mode。agent 做完就做完,系统不二次验证。这是"信任 LLM"的极致体现。
