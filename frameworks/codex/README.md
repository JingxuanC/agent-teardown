# OpenAI Codex CLI 拆解

OpenAI 官方的终端 coding agent。Rust 实现，100 个 crate，~116 万行。四个框架中功能最全、工程最成熟。

**仓库**:https://github.com/openai/codex
**本地路径**:`~/codex/`

## 拆解路线图

| # | 模块 | 状态 | 核心内容 |
|---|---|---|---|
| 01 | [架构总览](01-architecture.md) | ✅ | 100 crate 分层 + 10 个独有设计 + 四框架对比 |
| 02 | [双阶段记忆系统](02-dual-stage-memory.md) | ✅ | Stage1 提取 + Stage2 合并 + SQLite 作业队列 + 用量追踪 |
| 03 | [Multi-Agent + ExecPolicy](03-multi-agent-execpolicy.md) | ✅ | 拓扑追踪 + agent 间通信 + fork + DSL 策略 + 网络协议级控制 |
| 04 | [Compaction 系统](04-compaction.md) | ✅ | 服务端压缩 + AutoCompactWindow + token 预算感知 + trace |

## 关键发现速览

- **Codex 是离 7×24 AGI 最近的框架**:已有双阶段记忆巩固、agent 身份持久化(ed25519+JWT)、云任务卸载、agent 拓扑图。这些正是我们论文里提出的能力。
- **Agent Identity 是独家**:用 ed25519 密钥对 + JWT 管理身份。每个 agent 可以签名和验证自己的操作。其他三个框架完全没这个概念。
- **双阶段记忆(memory_stage1 + memory_consolidate_global)**:Stage1 从对话提取记忆,Global 合并成跨 session 知识。这是生产级实现了我们论文里提的"多尺度记忆 + 离线巩固"。
- **四平台原生沙箱**:Linux(BubbleWrap+Landlock) / macOS(Seatbelt) / Windows(Restricted Token)。唯一支持 Windows 的框架。
- **ExecPolicy DSL**:不是简单 allow/deny,是可编程的命令策略语言(有 parser、rule matching、network protocol 级控制)。
- **Cloud Tasks**:能把任务卸载到 OpenAI 云端执行。其他三个框架完全本地。
- **Agent Graph Store**:追踪多 agent 的父子拓扑关系(谁 spawn 了谁)。
- **反熵路线**:不做"结果验证"(skeptic),做"结构性约束"(沙箱+策略+身份)。和 grok-build 的对抗性不信任完全不同。
