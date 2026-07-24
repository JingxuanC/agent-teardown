# kimi-code 架构图

6 张手绘风格架构图,Excalidraw 格式(可在 [excalidraw.com](https://excalidraw.com) 打开、编辑、导出 PNG/SVG)。

## 怎么看

### 方式 1:在线(最简单)

1. 打开 https://excalidraw.com
2. 左上角菜单 → **Open** → 选择 `.excalidraw` 文件
3. 即可看到手绘风格渲染,可继续编辑

### 方式 2:VSCode

装 Excalidraw 插件(`pomdtr.excalidraw-editor`),直接在编辑器里打开 `.excalidraw` 文件。

### 方式 3:导出 PNG/SVG

在 Excalidraw 里 Menu → **Export** → 选 PNG(含透明背景)或 SVG(矢量)。

## 图表清单

| # | 文件 | 对应拆解 | 内容 |
|---|---|---|---|
| 1 | `01-overall.excalidraw` | [01-architecture.md](../01-architecture.md) | 整体分层架构(apps → engine → foundation → persistence) |
| 2 | `02-loop.excalidraw` | [09-loop.md](../09-loop.md) | Agent Loop 三层(Prompt → Turn → Step)+ steer + retry |
| 3 | `03-multi-agent.excalidraw` | [02-swarm](../02-swarm.md) + [03-goal-mode](../03-goal-mode.md) + [04-subagent](../04-subagent.md) | Swarm / Goal / Subagent 三种多 agent 模式对比 |
| 4 | `04-wire.excalidraw` | [07-wire-protocol.md](../07-wire-protocol.md) | Wire Op/Model 事件溯源 + 持久化 + restore |
| 5 | `05-tools.excalidraw` | [06-tool-system.md](../06-tool-system.md) | 工具调用全链路(resolveExecution → 权限 → 执行) |
| 6 | `06-providers.excalidraw` | [14-provider-llm.md](../14-provider-llm.md) | kosong 五大 LLM provider 统一抽象 |

## 重新生成

所有图由 `gen_excalidraw.py` 生成。改完源码后重跑:

```bash
cd frameworks/kimi-code/diagrams
python3 gen_excalidraw.py .
```

脚本不依赖任何第三方包,只用 Python 标准库(`json` + `uuid`)。

## 为什么用 Excalidraw 格式?

- **天然手绘风格**:`roughness: 1` 让所有线条带 wobble,正是我们要的"卡通感"
- **可二次编辑**:不是死图,改字、调位置、换色都行
- **开放格式**:JSON,可 diff,可版本控制
- **零依赖**:不需要 image_gen API 或渲染服务

## 配色

| 颜色 | 含义 |
|---|---|
| 🔵 蓝 | 用户接触面 / 输入 |
| 🟡 黄 | 中间层 / SDK / 调度 |
| 🟢 绿 | 正常路径 / 成功 |
| 🟠 橙 | 警告 / 等待 |
| 🔴 粉 | Agent 核心 / 错误 |
| 🟣 紫 | 基础设施 / 持久化 |
| 🟦 青(TEAL) | 扩展点 / 调度 |
| ⚪ 灰 | 兜底 / 终态 |
