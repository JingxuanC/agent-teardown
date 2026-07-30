# Insights · 从因果层到完整记忆系统 —— One Graph, One Engine, One Loop

> 本篇是 [11](11-causal-state-store.md)（因果状态库概念）→ [16](16-spike-results.md)（工程验证）之后的**架构收口**。
>
> 11 提出了因果状态库的概念（存"为什么"），16 用真实 benchmark 证明了它的工程价值（压缩生存 +20.8pp）。但它们都把因果记忆定位成一个**补充层**——要和 Mem0（事实召回）配合使用。本篇记录这个定位被推翻的过程：**因果层不是终点，是滩头阵地。**
>
> 触发这次推翻的是 2026-07-30 的三篇深度分析：HeLa-Mem（ACL'26，做了 Hebbian 兴奋侧，和我们 prevented 抑制侧高度重叠）、OpenViking（VLDB'26，LoCoMo 80-83%，事实召回碾压我们 65%）、Dreams API（Anthropic 的巩固工业化标准）。它们一起逼出了一个结论：**要么自给自足成为完整系统，要么永远当配件。** causal-memory 选择了前者。

## 0. 起点：因果层的两个致命短板

[16](16-spike-results.md) 落地后，causal-memory 的 benchmark 格局是这样的：

| Benchmark | causal-memory | 行业最强 | 差距来源 |
|---|---|---|---|
| LoCoMo（事实召回） | 65% | OpenViking 80-83% | **不会存事实** |
| LongMemEval（多 session） | 61.8% | Zep/Mem0 ~90%+ | **不会存事实** |
| Compaction survival | +20.8pp ✅ | 无人做过 | 独家优势 |
| Agent 学习 | 67%→33% ✅ | 无人做过 | 独家优势 |

**诊断很清楚**：所有 benchmark 差距都来自同一个瓶颈——不会存事实。而所有独家优势都在因果侧。如果继续只做因果层，就会永远困在"65% 的因果增强配件"这个位置。

更严峻的是竞争侧的压力：

- **HeLa-Mem**（ACL 2026）做了 Hebbian 学习 + spreading activation + 巩固——和我们的海马体架构高度重叠。它消融实验证明 spreading activation 贡献 -2.55pp、巩固贡献 -4.87pp。**它验证了我们的方向，但也缩小了我们的独特性。**
- **OpenViking**（VLDB 2026，27.7k★）用虚拟文件系统 + 三层加载把 token 效率做到 34-91% 节省。**在检索工程上，我们打不过它。**

这两个发现合在一起提出了一个真实的战略选择：

| 选择 | 含义 | 风险 |
|---|---|---|
| **A. 留在因果层** | 和 Mem0/OpenViking 配合使用 | 65% 永远追不上；HeLa-Mem 把海马体叙事也抢走 |
| **B. 扩成完整系统** | 事实+时序+因果统一，自给自足 | 工程量大；但差异化不缩反扩 |

causal-memory 选了 B。本篇记录这个选择的**理论根据**——不只是"我们要做更大"，是有一套可论证的统一架构。

---

## 1. 统一命题：一切记忆都是 typed edge

[13](13-reconstructive-memory.md) §0 列了四种记忆架构选项（外部检索 / Agent 自管理 / 自检索+目录 / 重构式）。本篇提出第五种，它不是新发明，是前四种的**收敛点**：

> **所有记忆类型——事实、时序、因果、共现、元模式——都是同一张图上的 typed edge。用一个类型加权激活扩散引擎检索，用一个不可变巩固循环演化。不是多个存储拼在一起，是一个系统。**

### 1.1 边类型分类学（edge taxonomy）

| 边类型 | 语义 | 例子 | 扩散系数 | 生物学对应 |
|---|---|---|---|---|
| `caused` | A 导致 B | mutex →caused→ deadlock | +1.0 | 谷氨酸强兴奋 |
| `fact` | 主语-谓语-宾语 | user →prefers→ TypeScript | +0.8 | 语义关联 |
| `meta` | 跨情景统计模式 | "分布式系统避免 mutex" | +0.6 | 皮层自上而下 |
| `enabled` | A 使 B 成为可能 | index →enabled→ fast query | +0.5 | 弱兴奋 |
| `co_occurrence` | A 和 B 反复共现 | redis ⇄ cache_config | +0.2×w(t) | **Hebbian LTP（动态）** |
| `prevented` | A 阻止 B | cache →prevented→ stale data | **−0.3** | **GABA 抑制（独家）** |
| `no_effect` | A 对 B 无影响 | rename →no_effect→ perf | 0.0 | 无连接 |

**三个关键设计决策**：

1. **事实不是一张新表，是一类新边。** `fact` 边和 `caused` 边在同一个图里，参与激活扩散、参与巩固、参与 GC。这是和"三层独立存储"的根本区别——那里事实层是外挂，这里事实层是图的一等公民。

2. **时序不是层，是所有边的有效期元数据。** `valid_from / valid_to / event_time` 是所有边携带的字段。一条 `caused` 边可以过时（valid_to 非空），一条 `fact` 边也可以。时序是横切关注点，不是存储维度。

3. **静态因果语义 + 动态统计强度叠加。** 因果边权重是类型决定的静态扩散系数（caused=+1.0，prevented=-0.3）；共现边权重是运行时按 Hebbian 规则 `w(t+1)=(1-λ)·w(t)+η·𝕀(共激活)` 演化的。**前者是"为什么"，后者是"多频繁"。两者在同一条边上叠加。**

### 1.2 为什么这是四种架构的收敛点

| [13](13-reconstructive-memory.md) 的选项 | 在统一图里的位置 |
|---|---|
| ① 外部检索器（Mem0/Zep） | `fact` 边的 BM25/embedding 检索 |
| ② Agent 自管理（Letta） | Agent 显式调用 `record_decision` / `record_fact` 写边 |
| ③ 自检索+目录（13 §1） | `search_memory` RRF 融合 + L0 目录常驻 |
| ④ 重构式（13 §2） | `reconstruct_lesson`：从 Markov-blanket 子图 LLM 重构叙述 |

**四种架构不是互斥的，是同一张图上的四种检索/写入模式。** 一个统一系统可以同时提供所有四种——这正是 [13](13-reconstructive-memory.md) §3.7 说的"四层叠加终局"，只是本篇把它从"四层"压缩成了"一张图四种模式"。

---

## 2. 核心洞察：兴奋/抑制二元性

这是本篇最重要的跨框架抽象，也是 causal-memory 最硬核的差异化论点。

### 2.1 问题：所有竞品只做了一半

人脑海马体同时有两类突触：

| 突触类型 | 神经递质 | 功能 | 作用 |
|---|---|---|---|
| 兴奋性 | 谷氨酸（Glutamate） | LTP 长时程增强 | "共同激活的连接增强"——Hebbian |
| 抑制性 | GABA | LTD 长时程抑制 | 抑制过度激活，防止全脑扩散 |

**当前所有 agent 记忆系统都只做了兴奋侧**：

| 系统 | 兴奋侧 | 抑制侧 |
|---|---|---|
| HeLa-Mem (ACL'26) | ✅ Hebbian 正向增强 w≥0 | ❌ spreading 只传播正值 |
| Mem0 / Zep | ✅ 语义相似度（隐式兴奋） | ❌ |
| OpenViking | ✅ 向量相似度 | ❌ |
| Dreams API | ✅ 巩固增强 | ❌（只删过时，不传播抑制） |
| **causal-memory** | ✅ caused/enabled 正扩散 | ✅ **prevented −0.3 负扩散** |

**没有任何系统实现了抑制侧。** HeLa-Mem 是最接近的竞争者——它做了 Hebbian 兴奋侧，但它的 spreading activation 公式 `S(v_j) = S_base(v_j) + β·Σ S_base(v_i)·w_ij` 里 w_ij ≥ 0，激活只会增强不会抑制。

### 2.2 prevented 负扩散为什么重要

考虑一个 agent 学习场景：

```
决策 A: 用缓存 → 结果: 数据陈旧（坏结果）
决策 B: 用缓存 + TTL 刷新 → 结果: 数据新鲜（好结果）
```

在只有兴奋侧的系统里，"缓存"会激活"数据陈旧"（caused，正向传播）。但它**无法表达**"加了 TTL 刷新之后，缓存阻止了数据陈旧"。

在 causal-memory 里：

```
缓存 →caused(+1.0)→ 数据陈旧      （兴奋性：缓存导致陈旧）
TTL刷新 →prevented(−0.3)→ 数据陈旧 （抑制性：TTL 阻止陈旧）
```

当 agent 查询"数据陈旧怎么办"时，spreading activation 从"数据陈旧"出发：
- 顺着 `caused` 边找到"缓存"（+1.0，兴奋）
- 顺着 `prevented` 边找到"TTL 刷新"（−0.3，抑制）

**负扩散让 agent 能回答"什么阻止了这个坏结果"——这是纯兴奋系统做不到的。** 这是因果推理（Pearl 的 do-calculus 中 intervention 的工程近似）在记忆层的直接体现。

### 2.3 完整系统需要两者

> **HeLa-Mem 做了兴奋侧（谷氨酸 LTP），causal-memory 做了抑制侧（GABA LTD）。完整的生物记忆系统需要两者。这不是"谁对谁错"，是"谁先补齐另一半"。**

如果 HeLa-Mem 加了 prevented 负扩散，它就追平了。但它的边是 Hebbian 共现权重（统计共现频率），没有因果语义——"A 和 B 经常一起出现"不等于"A 阻止了 B"。要加负扩散，必须从底层重新设计 spreading activation 算法，让边类型决定扩散符号。**这是架构层面的护城河，不是调参数能复制的。**

---

## 3. 竞争全景：一张表定位所有系统

[10](10-memory-frameworks.md) §6 诊断出"因果状态库是最大空白"。本篇把那个诊断更新为一张完整的竞争矩阵——**没有任何系统占据了所有行，causal-memory 的组合是独有的**：

| 能力 | causal-memory | HeLa-Mem | OpenViking | Mem0 | Zep | Letta | Dreams |
|---|---|---|---|---|---|---|---|
| 类型化因果语义 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **prevented 负扩散（抑制侧）** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Hebbian 共现边（兴奋侧） | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 巩固不可变（delta+clone） | ✅ | ❌ | ❌ | n/a | n/a | ❌ | ✅ |
| 情景/语义共存 | ✅ | ⚠️ | ❌ | ❌ | ⚠️ | ❌ | ✅ |
| 检索激活轨迹 | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| 分层加载 L0/L1/L2 | ✅ | ❌ | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| Compaction survival 实证 | ✅ +20.8pp | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Q-value 动态效用 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 一张图统一所有记忆类型 | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ | ❌ |

**读法**：没有任何单行是 causal-memory 独有的——HeLa-Mem 有 Hebbian，OpenViking 有分层加载，Dreams 有不可变巩固。但**没有任何系统同时拥有两行以上**。causal-memory 的护城河不是单项第一，是**组合唯一**。

关键组合是：**prevented 负扩散 + Hebbian 共现边 = 兴奋/抑制二元完整**。HeLa-Mem 有后者没前者，Dreams 两者概念都不同。这个组合来自生物学完整性原则——人脑两者都有，缺一是残缺系统。

---

## 4. 三个被吸收的机制

完整系统不是从零重写，是把竞品的机制吸收进统一图。2026-07-30 三篇深度分析的每个行动项都被精确映射：

### 4.1 吸收 HeLa-Mem：Hebbian 共现边

| HeLa-Mem 机制 | 统一图里的实现 |
|---|---|
| Hebbian 更新 w=(1-λ)·w+η·𝕀(共激活) | `co_occurrence` 边，λ=0.995，η=0.02，运行时演化 |
| Hub 检测 D(v)>δ_hub | SWR 巩固时检测，LLM 蒸馏成 `meta` 边 |
| 三重复合遗忘（弱+老+零访问） | GC 判据升级 |
| 双路检索 Top-k ∪ Top-m | 检索加"翻转路径"标记 |

**吸收逻辑**：HeLa-Mem 的边是纯 Hebbian 共现权重（统计），causal-memory 的因果边是类型语义（caused/prevented）。两者叠加——**静态因果语义（这条边是什么关系）+ 动态统计强度（这条边多频繁）在同一条边上共存。** HeLa-Mem 只有一半，我们两半都有。

### 4.2 吸收 Dreams API：不可变巩固

| Dreams 设计 | 统一图里的实现 |
|---|---|
| 输入永不被修改 | SWR 2.0：计算 delta → 应用到 clone → 原图只读 |
| `instructions` 引导 | `causal-memory sleep --instructions "focus on causal lessons"` |
| session_id 可观察 | ConsolidationResult 带 delta_log 审计日志 |
| 候选→确认流程 | 产出 new_graph，上层审查后原子切换 |

**吸收逻辑**：Dreams 的"不可变"是安全底线。causal-memory 原来的 SWR 直接改图（LTP 增强、LTD 减弱、GC 删除），一旦巩固出错不可逆。改成 delta+clone 后，巩固变成"生成性操作"而非"破坏性操作"——出错可丢弃，敢大规模高频巩固。这把 causal-memory 从"能跑的原型"推到"能生产的系统"。

### 4.3 吸收 OpenViking：分层加载 + 可观察检索

| OpenViking 机制 | 统一图里的实现 |
|---|---|
| L0/L1/L2 三层 | 检索结果分层返回（L0 摘要50tok → L1 概览500tok → L2 全文） |
| 目录递归检索 | 激活轨迹记录（seed → 边 → 浮出节点） |
| token budget | `max_tokens` 参数严格控制 |

**吸收逻辑**：OpenViking 在事实召回上碾压我们（80-83% vs 65%），但它是**数据库视角**（怎么高效存储检索），不是**认知科学视角**（怎么从经验学习因果）。吸收它的工程手段（分层加载），但不和它在事实召回赛道正面竞争——我们的定位是"因果记忆层"，事实层轻量自建对标 Letta 74%，不预设追平 80-83%。

---

## 5. 五条不可协商原则

从全部研究（insights 04-16 + 2026-07 深度分析）中蒸馏出的硬约束。任何实现细节都不能违反：

| # | 原则 | 来源 | 含义 |
|---|---|---|---|
| P1 | **生物学完整性** | HeLa-Mem 分析 §6 | 兴奋侧（Hebbian LTP）和抑制侧（prevented GABA）必须共存；只做一半是残缺的系统 |
| P2 | **情景与语义共存，不是替代** | Dreams 分析 §8 | 巩固产出语义知识（meta 边），但原始情景边（caused/prevented）永远保留可查 |
| P3 | **巩固不可变** | Dreams 分析 §3 | 巩固 = 计算 delta + 应用到 clone，原图永不被直接修改；出错可丢弃 |
| P4 | **检索可观察** | OpenViking 分析 §2.3 | 每次检索保留激活轨迹，能回答"为什么返回这条" |
| P5 | **压缩免疫是一等公民** | [16](16-spike-results.md) | 关键结构活在 agent 上下文窗口之外，benchmark 必须持续证明（+20.8pp） |

**P1 是最硬的**——它不是工程选择，是生物学约束。人脑没有"只有兴奋没有抑制"的记忆系统，那会导致癫痫式全脑激活。任何声称模拟海马体的系统，如果只做正向 spreading activation，在生物学上是不完整的。

---

## 6. 双系统映射（不变）

[11](11-causal-state-store.md) §3 的双系统映射在本架构里仍然成立：

```
海马体（情景记忆） = caused/enabled/prevented/fact/co_occurrence 边
                     具体、一次性、快速写入
新皮层（语义记忆） = meta 边（巩固时从情景边蒸馏）
                     抽象、统计、慢速形成

巩固 = 情景边"毕业"产出 meta 边，情景边本身保留（P2）
```

**和 [13](13-reconstructive-memory.md) 重构式记忆的关系**：`reconstruct_lesson` 工具做的是"从情景子图（Markov blanket）用 LLM 重构叙述"——这正是 [13](13-reconstructive-memory.md) §2 说的重构式。所以重构式不是一种独立架构，而是统一图上的一种检索模式（从碎片生成叙述）。

---

## 7. 实施路线（17 天，和 causal-memory roadmap 对齐）

| Phase | 内容 | 依赖 | 天数 |
|---|---|---|---|
| 1 | 事实边：`agent_facts` 表 + `record_fact`/`search_facts` | 无 | 2 |
| 2 | 统一检索：`search_memory` RRF 三层融合 | P1 | 1 |
| 3 | LLM distill ingest：一次调用三种产出 | P1 | 1 |
| 4 | 边类型泛化：扩散引擎支持 fact/meta/co_occurrence + 激活轨迹 | P2 | 3 |
| 5 | Hebbian 运行时权重：共现边建边 + 更新规则 | P4 | 2 |
| 6 | SWR 2.0：不可变 delta+clone + instructions + 巩固日志 + 三重 GC | 无（可并行） | 3 |
| 7 | Q-value 动力学：替代静态 confidence | P6 | 2 |
| 8 | Benchmark 战役：distill 重跑 + 正式消融 + token 效率 | P1–P7 | 3 |

**Phase 6（不可变巩固）可以提前并行**——它不依赖事实层，而且是从"原型"到"生产"的安全底线，应该最先做。

**Phase 8 的正式消融最关键**：HeLa-Mem 有消融数据（spreading -2.55pp，巩固 -4.87pp），causal-memory 目前没有。需要把 SWR / spreading / prevented 各砍一次，量化每个的贡献。**没有消融数据的系统，论文里站不住脚。**

---

## 8. 开放问题（诚实）

本篇是架构收口，不是问题终结。诚实地列出未解：

1. **prevented 负扩散的实证价值有多大？** §2 论证了它的理论价值（生物学完整性 + 因果推理），但**没有 benchmark 单独证明"加了 prevented 之后，agent 表现提升多少"**。Phase 8 的消融要回答这个。
2. **统一图的规模瓶颈。** 10 万+ 节点时 CSR 重建成本。对策是增量 CSR（已有 rev_to_fwd_idx 的教训），但还没测。
3. **工具数量膨胀。** 13 个 MCP 工具 vs [14](14-on-deep-digging.md) "complete-looking is the enemy of depth"。对策是 `search_memory` 作为默认入口，其他退化为专家模式。
4. **LLM distill 的 ingest 成本。** 每 session 一次 LLM 调用。对策是 distill 可选，未配置时退化为规则提取。
5. **事实层能否达到 75-80%？** 目标对标 Letta 74%，不预设追平 OpenViking 83%。如果 Phase 8 小规模（200 题）验证 distill 收益不够，需要调整预期。
6. **HeLa-Mem 如果加了 prevented 怎么办？** §2.3 说这是"谁先补齐另一半"的竞争。护城河是架构层面的（边类型决定扩散符号），但不是永久的。需要持续在 benchmark + 生物学完整性论证上领先。

---

## 9. 和前面 insights 的关系

```
04 反熵增（信息论）  →  P5 压缩免疫是反熵的工程实现
     ↓
09 无状态函数        →  记忆 = 外部状态，统一图是那个外部状态
     ↓
10 记忆赛道诊断      →  §6 "因果是最大空白" → 本篇 §3 把它更新为完整竞争矩阵
     ↓
11 因果状态库（概念）→  本篇 §1 把它从"一张表"升级为"一张 typed-edge 图"
     ↓
12 生成性            →  Q-value 动态效用（Phase 7）是"记忆的生成性"
     ↓
13 重构式记忆        →  §1.2 指出重构式是统一图上的一种检索模式，不是独立架构
     ↓
16 工程验证          →  P5 的 +20.8pp 实证基础
     ↓
17 完整系统（本篇）  →  统一命题 + 兴奋/抑制二元 + 竞争矩阵 + 五原则
```

**本篇的增量**：不是新发现一个空白（那是 11/13 做的），是把已有发现**收敛成一个可实施的统一架构**，并给出竞争护城河的精确定位（兴奋/抑制二元完整）。

---

## 10. 最终的一句话

> **causal-memory 从"因果补充层"演化为"完整记忆系统"，不是膨胀，是收敛。**
>
> 统一命题是：所有记忆类型（事实、时序、因果、共现、元模式）都是同一张 typed-edge 图上的边，用一个类型加权激活扩散引擎检索，用一个不可变巩固循环演化。四种记忆架构（外部检索 / 自管理 / 自检索 / 重构式）不是互斥的，是这张图上的四种模式。
>
> 核心护城河是**兴奋/抑制二元性**：HeLa-Mem 做了兴奋侧（Hebbian LTP），causal-memory 做了抑制侧（prevented GABA 负扩散）。完整的生物记忆系统需要两者——没有任何竞品实现了抑制侧，而要加它必须从底层重设计 spreading activation 算法。这是架构层面的护城河。
>
> 五条不可协商原则（生物学完整性 / 情景语义共存 / 巩固不可变 / 检索可观察 / 压缩免疫）把"能跑的原型"推到"能生产的系统"。**17 天实施路线里，Phase 6（不可变巩固）应该最先做——它是安全底线。**

---

## 参考资料

- **causal-memory 架构文档**：[docs/complete-memory-system.md](../causal-memory-mcp/../docs/complete-memory-system.md)（One Graph, One Engine, One Loop）
- **causal-memory roadmap**：定位重写记录（slice → system）
- **HeLa-Mem 深度分析**：[papers/daily/2026-07-30-helamem-analysis.md](../papers/daily/2026-07-30-helamem-analysis.md)（消融数据 + Hebbian 规则 + 五个行动项）
- **Dreams API 深度分析**：[papers/daily/2026-07-30-dreams-api-analysis.md](../papers/daily/2026-07-30-dreams-api-analysis.md)（不可变巩固 + instructions + 伪代码）
- **OpenViking 深度分析**：[papers/daily/2026-07-30-openviking-analysis.md](../papers/daily/2026-07-30-openviking-analysis.md)（分层加载 + 定位张力）
- **MemRL 深度分析**：[papers/daily/2026-07-29-memrl-analysis.md](../papers/daily/2026-07-29-memrl-analysis.md)（Q-value 记忆动力学）
- [11](11-causal-state-store.md) — 因果状态库概念（本篇的起点）
- [16](16-spike-results.md) — 工程验证（+20.8pp 实证）
- [13](13-reconstructive-memory.md) — 重构式记忆（本篇 §1.2 指出它是统一图的一种模式）
- [10](10-memory-frameworks.md) §6 — "因果是最大空白"诊断（本篇 §3 更新为完整矩阵）
