# Nemori 深度分析 · 2026-08-03

> **一句话结论：Nemori 的 Predict-Calibrate 原则（Free Energy Principle 驱动的 surprise-gated 记忆准入）在概念上与 causal-memory 的 novelty entropy trigger 直接竞争，但两者的实现路径、计算成本和理论深度有本质差异 —— Nemori 用 LLM 预测做语义层面的惊讶检测（更强但更贵），causal-memory 用 Shannon entropy 做词频层面的惊讶检测（更轻但更浅）。**

---

## 1. 核心问题 / 背景

causal-memory 的写入门控使用 **novelty entropy trigger** —— 当一段对话的 Shannon entropy 超过阈值时才写入记忆，跳过低信息量的寒暄和重复。这个机制的设计灵感来自海马体的 novelty detection。

但一个关键问题始终悬而未决：**Shannon entropy 是词频层面的度量，它无法检测语义层面的惊讶。** 例如，用户说"我决定把所有仓位清零"—— 词频上不罕见（每个词都很常见），但语义上极其重要（决策反转）。纯 entropy trigger 可能会错过这条。

Nemori（arXiv:2508.03341）用 **Free Energy Principle** 的 prediction gap 解决了这个问题—— 它让 LLM 先预测用户会说什么，然后比较预测和实际消息的差距，只在差距大时才提取记忆。这是**语义层面**的惊讶检测。

---

## 2. 方法 / 架构详解

### 2.1 两个核心原则

#### 原则 1：Configurable Granularity（可配置粒度）

```
f_θ = configurable confidence threshold ∈ [0, 1]
```

每个用户消息 `m_i` 是一个元组 `(ρ_i, c_i, τ_i)`（role, content, timestamp）。当消息进入 buffer 时，系统用 `f_θ` 决定是否提取知识。`f_θ` 可调：
- `f_θ` 高（如 0.9）→ 只提取非常确定的记忆 → 记忆少但精确
- `f_θ` 低（如 0.3）→ 提取大量记忆 → 记忆多但有噪声

对应人脑：注意力的集中程度决定了什么进入工作记忆。

#### 原则 2：Predict-Calibrate Principle（预测-校准原则）

这是 Nemori 的核心创新，基于 Karl Friston 的 **Free Energy Principle (FEP)**：

```
1. Predict:   对每个新消息 m_{t+1}, 先用 LLM 基于 buffer M 预测: f_θ(M) → predicted message
2. Compare:   计算 predicted 和 actual message 的 gap: e = (ξ, ζ) = g_ϕ(M)
               其中 ξ = knowledge gap (新知识), ζ = confidence
3. Calibrate: 如果 gap 超过 boundary threshold σ_boundary:
               → 从 gap 中提取 semantic memory K_new
               → 更新知识库: K ← K ∪ K_new
```

**关键参数**（从论文实验部分提取）：
- `σ_s = 0.0`（similarity threshold，低于此值认为有 gap）
- `σ_boundary = 0.7`（boundary threshold，gap 超过此值才触发记忆提取）
- `β_max = 25`（buffer 最大消息数）
- 检索：top-k=`k=10`, top-m=`m=2k=20`

### 2.2 三阶段管道

```
用户消息 → [Message Buffer] → [Predict-Calibrate Gate] → [Semantic Memory DB]
              ↑                      ↑                         ↑
           原始缓冲            surprise detection          知识存储
           (β_max=25)         (σ_boundary=0.7)           (K memories)
```

1. **Message Buffer**：缓存最近 β_max 条消息
2. **Predict-Calibrate Gate**：LLM 预测 → gap 计算 → 阈值判断
3. **Semantic Memory DB**：只存通过 gate 的知识

### 2.3 和 Free Energy Principle 的对应

| FEP 概念 | 人脑 | Nemori |
|---------|------|--------|
| Free Energy | 预测误差 | prediction gap (ξ) |
| Active Inference | 主动更新内部模型 | 从 gap 提取新知识 K_new |
| Surprise | 预期之外的输入 | σ > σ_boundary |
| Prior | 已有知识库 K | DB 中的 K memories |
| Posterior | 更新后的知识 | K ∪ K_new |

---

## 3. 实验结果（真实数字）

### 3.1 LoCoMo Benchmark

| 系统 | Overall | Short-term | Long-term |
|------|---------|------------|-----------|
| RAG (baseline) | 0.237-0.326 | 0.157-0.222 | 0.117-0.186 |
| **Nemori** | **0.710-0.821** | **0.466-0.588** | **0.385-0.515** |

Nemori 在不同 session 数量下的表现：
- 5 sessions: Overall 0.710
- 15 sessions: Overall 0.744
- 更多 sessions: 接近 0.821

### 3.2 LongMemEval Benchmark

| 系统 | Overall | Short-term | Long-term |
|------|---------|------------|-----------|
| RAG | 0.274-0.359 | 0.191-0.258 | 0.139-0.220 |
| **Nemori** | **0.776-0.849** | **0.502-0.588** | **0.456-0.515** |

### 3.3 效率对比

| 系统 | Score | Latency (ms) | Extract Time (ms) | Total (ms) |
|------|-------|-------------|-------------------|------------|
| LangMem | 0.513 | 1,251 | 9,829 | 22,082 |
| Zep | 0.585 | 2,247 | 522 | 23,255 |
| **Nemori** | **0.744** | **2,745** | **787** | **3,053** |

Nemori 的总延迟 3,053ms，比 LangMem (22,082ms) 和 Zep (23,255ms) **快 7 倍**。

---

## 4. 消融实验（最有价值的部分）

### 4.1 去掉每个组件的影响

**LoCoMo benchmark:**

| 配置 | Overall | Short | Long | 变化 |
|------|---------|-------|------|------|
| w/o Nemori (baseline RAG) | 0.006 | 0.005 | 0.009 | — |
| w/o ξ (去掉 prediction gap) | 0.615 | 0.434 | 0.340 | -0.129 |
| w/o σ (去掉 surprise threshold) | 0.705 | 0.470 | 0.370 | -0.039 |
| **Full Nemori** | **0.744** | **0.495** | **0.385** | — |

**LongMemEval benchmark:**

| 配置 | Overall | Short | Long | 变化 |
|------|---------|-------|------|------|
| w/o Nemori | 0.012 | 0.016 | 0.015 | — |
| w/o ξ | 0.696 | 0.461 | 0.396 | -0.098 |
| w/o σ | 0.756 | 0.501 | 0.435 | +0.038 |
| **Full Nemori** | **0.794** | **0.534** | **0.456** | — |

### 4.2 消融结论

1. **prediction gap (ξ) 是核心组件** —— 去掉它 Overall 掉 9.8-12.9pp。这是 surprise detection 的核心
2. **surprise threshold (σ) 的作用不稳定** —— 在 LoCoMo 上去掉它掉 3.9pp，在 LongMemEval 上反而涨 3.8pp（可能 LongMemEval 的任务需要更多记忆）
3. **两个原则有协同效应** —— Full Nemori > w/o ξ > w/o σ > baseline

---

## 5. 精确对比 causal-memory

| 维度 | Nemori | causal-memory | 重叠/独有 |
|------|--------|---------------|----------|
| **写入门控** | prediction gap (FEP) | novelty entropy (Shannon) | ✅ 概念重叠（surprise-gated），❌ 实现不同 |
| **门控理论** | Free Energy Principle | Shannon information theory | ❌ 不同理论框架 |
| **门控成本** | 每条消息需要 LLM 预测调用 | entropy 计算（O(n)，无需 LLM） | ⭐ causal-memory 更轻量 |
| **门控深度** | 语义层面（LLM 预测 vs 实际） | 词频层面（entropy） | ⭐ Nemori 更深 |
| **记忆类型** | semantic memory (fact) | causal + fact + meta + co_occurrence | ⭐ causal-memory 类型更丰富 |
| **因果关系** | 无 | caused/enabled/prevented | ✅ causal-memory 独有 |
| **负扩散** | 无 | prevented → -0.3 spreading | ✅ causal-memory 独有 |
| **巩固** | 实时（gap 出现就写） | SWR offline consolidation | ❌ 不同时机 |
| **图传播** | 无 | CSR sparse matrix spreading activation | ✅ causal-memory 独有 |
| **LoCoMo** | 71-82% | 67.4% | ⭐ Nemori 高 4-15pp |
| **延迟** | 3,053ms total | — | 不同 benchmark，不可直接比 |

### 关键差异分析

**Nemori 强在**：
1. **语义层面的惊讶检测** —— prediction gap 能捕捉"词频不罕见但语义重要"的消息
2. **理论框架** —— FEP 是人脑 predictive coding 的核心理论，比 Shannon entropy 更接近神经科学
3. **benchmark 数字** —— LoCoMo 71-82% vs 我们 67.4%

**causal-memory 强在**：
1. **轻量门控** —— entropy 计算不需要额外 LLM 调用，适合高频写入场景
2. **因果关系类型** —— prevented 负扩散是 Nemori 完全没有的
3. **SWR 巩固** —— offline consolidation 能做跨 session 的模式发现（meta-edge mining）
4. **图传播** —— spreading activation 能发现间接关联

---

## 6. 对 causal-memory 的具体行动项

| # | 行动 | 对应机制 | 优先级 |
|---|------|---------|--------|
| 1 | 评估 prediction gap 作为 entropy trigger 的增强 | write-time gatekeeping | 🔥 高 |
| 2 | 实现"entropy 粗筛 + prediction gap 精筛"混合门控 | distill pipeline | ⭐ 中 |
| 3 | 在论文/README 中精确对比 Nemori | documentation | 🔥 高 |
| 4 | 测量 entropy trigger vs prediction gap 的 token 成本 | benchmark | ⭐ 中 |
| 5 | 考虑 FEP 作为 causal-memory 的理论框架 | positioning | 📎 低 |

### 行动 1 详解：混合门控方案

```
当前:   message → entropy check → write/discard
混合:   message → entropy check (cheap) → if borderline → prediction gap (expensive) → write/discard
```

- entropy 做粗筛（O(n)，无 LLM 调用）→ 过滤掉明显低信息量的消息
- 对 borderline 消息（entropy 在阈值附近），再用 prediction gap 做精筛（需要 LLM 预测）
- 预期效果：比纯 entropy 更准确，比纯 prediction gap 更省 token

### 行动 3 详解：论文对比要点

在 README/论文中需要说清楚：
- **causal-memory 的 entropy trigger 是 O(n) 的**，Nemori 的 prediction gap 需要 O(1) 次额外 LLM 调用
- **causal-memory 的 prevented 负扩散是 Nemori 没有的** —— Nemori 只做了"写入门控"，没有"因果传播"
- **causal-memory 的 SWR 巩固能做跨 session 模式发现**，Nemori 是实时写入没有跨 session 分析

---

## 7. 和人脑的类比（跨域类比）

### Free Energy Principle 在人脑中的对应

Friston 的 Free Energy Principle 认为：**大脑是一个预测机器，它不断生成对世界的预测，只在预测错误时才更新内部模型。** 这是人脑的 predictive coding。

具体到海马体：
- **CA3 做预测（pattern completion）** —— CA3 的递归 collateral 网络能从部分输入"补全"完整的模式（预测）
- **CA1 做 mismatch detection** —— CA1 比较 CA3 的预测和来自 entorhinal cortex 的实际输入，当不匹配时发出 novelty signal
- **这个 novelty signal 就是 prediction error** —— 驱动记忆写入（LTP）和探索行为

### causal-memory vs Nemori vs 人脑

| 功能 | 人脑海马体 | Nemori | causal-memory |
|------|-----------|--------|---------------|
| 预测 | CA3 pattern completion | LLM 预测 | ❌ 无 |
| 惊讶检测 | CA1 mismatch detection | prediction gap (FEP) | Shannon entropy |
| 检测层面 | 语义/模式 | 语义 | 词频 |
| 检测成本 | 神经元放电（~20ms） | LLM 调用（~1s） | 统计计算（~0.1ms） |
| 记忆类型 | episodic + semantic | semantic | causal + fact + meta |
| 巩固 | SWR (sleep) | 实时 | SWR (offline) |
| 抑制 | GABA 抑制性突触 | ❌ 无 | prevented 负扩散 |

**完整的人脑需要三个层次**：
1. **快速惊讶检测**（CA1 mismatch → causal-memory 的 entropy trigger）
2. **语义惊讶检测**（predictive coding → Nemori 的 prediction gap）
3. **因果抑制**（GABA → causal-memory 的 prevented 负扩散）

causal-memory 做了 1 和 3，Nemori 做了 2。**一个完整的系统需要三者结合。**

---

## 8. 连接 insights

- **[11](../../insights/11-causal-state-store.md) novelty entropy trigger** —— 被 Nemori **挑战**。entropy trigger 的概念被验证（surprise-gated admission 是对的），但 Nemori 用更强的 FEP 框架实现了类似功能，且 benchmark 数字更高。需要：
  1. 明确 entropy trigger 的轻量优势
  2. 考虑吸收 prediction gap 思想做混合方案

- **[13](../../insights/13-reconstructive-memory.md) 重构式检索** —— **间接验证**。Nemori 的 message buffer 保留原始消息（可逆），只在 gap 出现时提取 semantic memory（压缩）。这符合 rate-distortion 理论的"可逆性优先"。

- **[05](../../insights/05-agi-7x24.md) 7×24 记忆** —— **间接验证**。Nemori 的 surprise-gated admission 正是 7×24 agent 需要的：不是记住所有东西，而是只记住"值得记住的"。

---

## 9. 最终判断

**Nemori 是 causal-memory 在写入门控方向上最直接的学术竞争者。** 它的 Predict-Calibrate 原则和我们的 novelty entropy trigger 本质相同（surprise-gated admission），但：

1. **Nemori 的理论框架更强**（FEP > Shannon entropy）
2. **Nemori 的 benchmark 更高**（71-82% vs 67.4%）
3. **但 Nemori 的成本更高**（每条消息需要 LLM 预测调用）
4. **Nemori 没有因果关系类型、负扩散、SWR 巩固**

**causal-memory 的应对策略应该是"吸收而非对抗"**：
- 承认 prediction gap 比 entropy 更强（语义层面 vs 词频层面）
- 但强调 entropy 的轻量优势（无 LLM 调用）
- 提出**混合门控**（entropy 粗筛 + prediction gap 精筛）作为 future work
- 强调 causal-memory 独有的 prevented 负扩散和 SWR 巩固是 Nemori 完全没有的维度

**causal-memory 不应该假装没看见 Nemori。** 在论文/README 中需要精确对比，说清楚差异化收窄到哪些点。
