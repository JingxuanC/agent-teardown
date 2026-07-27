# Vela vs Claude Code —— 记忆与 7×24 架构的深层对比

> 本篇对比 Shopify Vela(Go,生产 7×24)和 Anthropic Claude Code(编译二进制,编码 agent)的记忆与长时运行架构。
>
> 两者语言不同、场景不同,但在记忆和 7×24 架构上有**深层同构** —— 这不是巧合,是 [04](../../insights/04-anti-entropy.md) 说的"物理约束决定论"的又一次验证。
>
> 但 Vela 有两个 Claude Code 没有的独特能力,值得 causal-memory 学习。

## 1. 同构部分(收敛到相同策略)

### 1.1 热路径(每轮推理时的记忆召回)

| 维度 | Vela | Claude Code |
|---|---|---|
| 机制 | DecisionStore.Recall → RRF 融合(向量召回 + 近因召回) | MEMORY.md 索引(前 200 行)+ grep 即时检索 |
| 存储 | PostgreSQL(agent_facts + agent_insights) | Markdown 文件(~/.claude/projects/<cwd>/memory/) |
| 检索方式 | Qdrant 向量 + PG 近因,RRF 排序融合 | 文件系统 grep + 索引加载 |
| 对应 insights | [09](../../insights/09-stateless-function.md) §3:所有记忆都是检索+注入 | 同上 |

**同构**:两者都是"每轮推理前,从外部存储检索相关记忆,注入 context"。LLM 本身无状态([09](../../insights/09-stateless-function.md) §1)。

**差异**:Vela 用向量+近因 RRF 融合(更精准),Claude Code 用文件 grep(更简单)。Vela 的 RRF 融合是 [10](../../insights/10-memory-frameworks.md) §1 里 Mem0 的路线,Claude Code 的 grep 更接近 OpenViking 的"文件系统即记忆"。

### 1.2 冷路径(定时离线巩固)

| 维度 | Vela | Claude Code |
|---|---|---|
| 名称 | Reflector(5 步循环) | Auto Dream(4 阶段) |
| 做什么 | LLM 抽取 Facts + Insights + L0 摘要 | LLM 合并/删除/重组 Markdown 记忆 |
| 去重 | 三级(hash → Qdrant 0.95 → PG ILIKE) | 合并重复 |
| 衰减 | 半衰期(halflife_hours 四档:24h/168h/720h/2160h) | 直接删除过时记忆 |
| 持久化 | PG 表(agent_facts 带 halflife) | Markdown 文件 |
| 触发 | 4 条件(数据量/旧度/定期/新颖度熵) | 2 条件(24h/5 sessions) |
| 并发保护 | PG advisory lock | 文件锁(lock file) |
| 对应 insights | [05](../../insights/05-agi-7x24.md) §3.2:睡眠巩固 | 同上 |

**同构**:两者都有"定时用 LLM 整理记忆"的离线巩固机制。对应 [05](../../insights/05-agi-7x24.md) §3.2 预测的"Agent 需要睡眠巩固"。

**差异**:Vela 的 Reflector 比 Claude Code 的 Dream **更系统化**:
- 三级去重(vs Dream 的"合并重复",没有多级)
- 半衰期衰减(vs Dream 的"直接删除",没有衰减曲线)
- noveltyEntropy 触发(vs Dream 的固定 24h)

### 1.3 调度系统

| 维度 | Vela | Claude Code |
|---|---|---|
| Cron | robfig/cron + 语义 Signal 系统 | CronCreate(标准 cron 表达式) |
| 监控 | EventWatcher(事件流) | Monitor(shell stdout 事件流) |
| 对应 insights | [05](../../insights/05-agi-7x24.md) §3.4:自适应验证 | 同上 |

**同构**:两者都有 cron 定时 + 事件流监控。

### 1.4 安全约束

| 维度 | Vela | Claude Code |
|---|---|---|
| 并发 | AutonomyGate 四规则 + DAG scheduler | 并发子 agent 上限(20) |
| 预算 | Oracle 路由(领域分类 + 预算分配) | --max-budget-usd |
| 防失控 | Steering + stall 检测 | autocompact 熔断 + 搜索上限 |
| 对应 insights | [04](../../insights/04-anti-entropy.md) §2:约束策略 | 同上 |

**同构**:两者都在多个维度限制 agent 行为空间,防止 7×24 失控。

## 2. Vela 独有(Claude Code 没有的)

### 2.1 noveltyEntropy —— 基于信息熵的反思触发

Vela 的 Reflector 用一个叫 `noveltyEntropy` 的指标决定"是否该反思":

```go
// 四个触发条件(任一满足)
1. unreflected_count >= 10         // 数据够多
2. 最老未反思决策 > 7 天            // 数据太旧
3. 距上次反思 > 7 天                // 定期
4. noveltyEntropy > 2.5 || unreflected_count < 5  // 新颖度高
```

`noveltyEntropy` 是**信息熵计算** —— 衡量近期决策的多样性。熵高 = 出现了新模式 = 值得反思;熵低 = 重复模式 = 暂不反思。

**为什么这比 Claude Code 的"每 24h 固定触发"更好**:
- 人脑不是每 24h 固定反思 —— 是在遇到新情况时才反思
- 固定 24h 会在"没新东西"时浪费 LLM 调用,在"大量新东西"时反应太慢
- noveltyEntropy 让反思**按内容多样性触发**,不按时间触发

**对人脑的类比**:这对应海马体的"模式分离"(pattern separation) —— 大脑检测到新模式时触发记忆巩固,不是固定时间触发。

### 2.2 DetectConditionalSignals —— 结果驱动的二次触发

Vela 的 cron 跑完后,**检查结果分数**决定是否触发后续行动:

```go
var watchedTools = map[string]struct {
    signal Signal
    below  int  // 分数低于此值 → 触发
}{
    "predict_churn_risk": {signal: SignalChurnRisk, below: 50},
    "detect_dead_stock":  {signal: SignalLowStock, below: 50},
    "check_inventory":    {signal: SignalLowStock, below: 40},
    "analyze_returns":    {signal: SignalReturnSpike, below: 45},
}
```

例如:周一晨检跑 `predict_churn_risk`,结果 < 50 分 → 自动触发 `SignalChurnRisk` → 留存工作流。**不用等下次定时,不用人工干预**。

**为什么 Claude Code 没有这个**:Claude Code 的 cron 只在到点时跑一个 prompt,**不根据结果二次触发**。这是一个反馈闭环的缺失。

**对 causal-memory 的含义**:这是"因果反馈闭环"的雏形 —— cron 的结果触发了后续行动,形成了一条因果链(晨检 → 发现风险 → 触发留存)。causal-memory 应该能捕获这种"条件触发的因果链"。

## 3. Claude Code 独有(Vela 没有的)

### 3.1 ScheduleWakeup —— 动态自调度

```typescript
interface ScheduleWakeupInput {
  delaySeconds?: number;  // 60-3600 秒后唤醒
  reason?: string;        // 给用户看的解释
  prompt?: string;        // 唤醒时执行的 /loop 输入
  stop?: boolean;         // true=停止循环
}
```

Agent 可以**自己决定什么时候再跑** —— 不是预设 cron,是动态自调度。Vela 没有这个 —— Vela 的 cron 是预设的,agent 不能自己改时间表。

**对 causal-memory 的含义**:ScheduleWakeup 创造了一种新的因果链 —— "agent 决定 60 秒后再检查" 这个决策本身可以被 causal-memory 记录。这对应 [11](../../insights/11-causal-state-store.md) §2 的"决策点":`type='plan_step'`。

### 3.2 Auto Dream 能提议新 Skill

```javascript
createdBy: e.created_by === "dream-proposal" ? "dream-proposal" : void 0
```

Dream 不仅能整理记忆,还能**提议新的自动化能力**(skill)。Vela 的 Reflector 不做这个 —— 它只抽取 facts 和 insights,不生成新的可执行能力。

**对应 insights**:这是 [05](../../insights/05-agi-7x24.md) §3.3 "自演化 Prompt" 的一种形态 —— 不是修改 system prompt,而是**提议新 skill**(新的自动化模式)。

## 4. 完整对比矩阵

| 能力 | Vela | Claude Code | 差异方向 |
|---|---|---|---|
| 热路径检索 | RRF(向量+近因) | grep + 索引 | Vela 更精准 |
| 冷路径巩固 | Reflector(5步) | Dream(4阶段) | 同构 |
| 去重 | 三级(hash/Qdrant/ILIKE) | 合并 | Vela 更系统化 |
| 衰减 | **半衰期(四档)** | 直接删除 | **Vela 更精细** |
| 反思触发 | **noveltyEntropy(信息熵)** | 固定 24h | **Vela 更智能** |
| 条件触发 | **DetectConditionalSignals** | 无 | **Vela 独有** |
| Cron 定时 | robfig/cron + Signal | CronCreate | 同构 |
| 动态自调度 | 无 | **ScheduleWakeup** | **Claude Code 独有** |
| 持续监控 | EventWatcher | Monitor | 同构 |
| Dream 提议 skill | 无 | **dream-proposal** | **Claude Code 独有** |
| 运行环境 | K8s(唯一生产) | 本地 daemon + 云端 | 不同形态 |
| 持久化 | PostgreSQL | Markdown 文件 | 不同选择 |

## 5. 对 causal-memory 的三个具体启示

### 5.1 加半衰期(学 Vela)

Vela 的 `halflife_hours`(24h/168h/720h/2160h)比 causal-memory 的 `valid_to`(手工失效)**好得多**。causal-memory 应该加:

```sql
ALTER TABLE causal_edges ADD COLUMN halflife_hours INTEGER DEFAULT 720; -- 30天
-- effective_confidence = confidence * 0.5 ^ (age_hours / halflife_hours)
```

这让因果边的置信度**随时间自动衰减**,不需要手工标记失效。`valid_to` 保留给"被明确推翻"的情况。

### 5.2 加去重(学 Vela)

Vela 的第一级去重(content hash)很简单但有效。causal-memory 应该加:

```sql
-- 插入前检查:同样的 (from_id, to_id, relation) 是否已存在
-- 如果存在,只更新 confidence(取更高值),不创建重复边
```

### 5.3 加条件触发的因果链捕获(学 Vela)

Vela 的 `DetectConditionalSignals` 创造了一种因果链:"cron 结果分数低 → 触发后续行动"。causal-memory 应该能捕获这种链:

```
[决策:cron 跑 predict_churn_risk] → [结果:分数 45 (< 50)] → [触发:SignalChurnRisk] → [行动:留存工作流]
```

这比当前 causal-memory 的扁平因果边更丰富 —— 它有**条件触发**(分数 < 阈值)。future 的 `meta_causal_edges` 可以存这种"条件 → 触发"的模式。

---

## 参考资料

- Vela 拆解:[03-memory-reflect-decay.md](../vela-shopify/03-memory-reflect-decay.md) + [09-wakeup-synth-templates.md](../vela-shopify/09-wakeup-synth-templates.md)
- Claude Code 拆解:[01-memory-context.md](../claude-code/01-memory-context.md) + [02-context-system.md](../claude-code/02-context-system.md) + [03-7x24-architecture.md](../claude-code/03-7x24-architecture.md)
- insights/04(反退化策略)+ insights/05(7×24)+ insights/09(无状态函数)
