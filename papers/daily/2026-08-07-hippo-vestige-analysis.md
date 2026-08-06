# Hippo + Vestige 深度分析 · 2026-08-07

> **一句话结论：Hippo 和 Vestige 是技术栈最接近 causal-memory 的两个竞品——Rust + MCP + spreading activation + active forgetting + sleep consolidation。但它们都没有因果关系类型、没有 prevented 负扩散、没有前向模拟。causal-memory 的"记忆工程"层面不再独特，所有独特性必须押在因果维度上。**

---

## 1. 为什么放在一起分析

Hippo（github.com/kitfunso/hippo-memory）和 Vestige（github.com/samvallad33/vestige）都是 2026 年出现的 Rust MCP 记忆 server，和 causal-memory 的技术选型几乎完全相同。放在一起分析更能看清 causal-memory 的定位变化。

---

## 2. Hippo 架构详解

### 2.1 三层记忆

```
Buffer (短期) → Episodic (情景) → Semantic (语义)
```

| 层 | 机制 | 参数 |
|----|------|------|
| Buffer | 临时缓冲 | — |
| Episodic | 带衰减的情景记忆 | half_life=14d, valence=good/bad/error |
| Semantic | 合并后的模式 | sleep 时 3+ episodic → 1 semantic |

### 2.2 Sleep Consolidation

```
hippo sleep
→ merge 3 related episodic → 1 semantic
→ original episodic decays
→ remove fully decayed memories
→ mark 30-day unretrieved as stale
```

### 2.3 Outcome Feedback

```python
hippo outcome --good  # reward_factor 1.0 → 1.15 (+15%)
hippo outcome --bad   # reward_factor 1.0 → 0.85 (-15%)
```

- 5 positive, 0 negative → factor ~1.42 → half-life 延长 42%
- 0 positive, 3 negative → factor ~0.63 → half-life 缩短 37%

---

## 3. Vestige 架构详解

### 3.1 核心机制

| 机制 | 实现 |
|------|------|
| **FSRS-6** | 间隔重复算法（Anki 同款），控制记忆衰减节奏 |
| **Prediction-error gating** | 只在预测和实际不符时写入 |
| **Active forgetting** | 主动遗忘不被使用的记忆 |
| **Spreading activation** | 图传播检索 |
| **3D dashboard** | 可视化记忆状态 |

### 3.2 技术栈

- Rust + MCP server（和 causal-memory 完全相同）
- 支持 Claude Code / Cursor / VS Code / Codex / Windsurf
- `npm install -g vestige-mcp-server`

---

## 4. 三方精确对比

| 维度 | causal-memory | Hippo | Vestige |
|------|---------------|-------|---------|
| **语言** | Rust ✅ | Rust ✅ | Rust ✅ |
| **MCP Server** | ✅ 13 tools | ✅ | ✅ |
| **海马体分层** | ✅ DG/CA3/CA1 | ✅ Buffer/Episodic/Semantic | ❌ 扁平 |
| **Sleep consolidation** | ✅ SWR (LTP/LTD/GC) | ✅ sleep 命令 | ❌ |
| **Spreading activation** | ✅ CSR typed edge | ❌ half-life 排序 | ✅ |
| **Active forgetting** | ✅ GC + LTD | ✅ decay + stale | ✅ FSRS-6 |
| **Outcome/reward** | ✅ Q-value Bellman | ✅ reward factor | ❌ |
| **Prediction gating** | ✅ novelty entropy | ❌ | ✅ prediction-error |
| **因果关系类型** | ✅ **caused/prevented** | ❌ valence (good/bad) | ❌ |
| **负扩散** | ✅ **prevented → -0.3** | ❌ | ❌ |
| **前向模拟** | ✅ **intervention_query** | ❌ | ❌ |
| **统一图** | ✅ 7种 typed edge | ❌ 独立层 | ✅ 但无类型 |
| **Benchmark** | LoCoMo 84.1% / LME 71.2% | ❌ | ❌ |

### 关键洞察

**causal-memory 的"记忆工程"层面（Rust + MCP + spreading + forgetting + consolidation）正在变成标配。** Hippo 和 Vestige 各做了子集：
- Hippo 做了分层 + consolidation + outcome
- Vestige 做了 spreading + FSRS-6 + prediction gating
- causal-memory 做了**全部 + 因果关系类型 + 负扩散 + 前向模拟**

**差异完全收窄到因果维度。** 如果 causal-memory 丢掉因果关系，它就是"Hippo + Vestige 的并集"——不再独特。

---

## 5. 行动项

| # | 行动 | 优先级 |
|---|------|--------|
| 1 | 在论文中明确区分"记忆工程"（标配）vs"因果推理"（独有） | 🔥 高 |
| 2 | 精确对比 Hippo（三层+consolidation+outcome）和 Vestige（spreading+FSRS-6） | ⭐ 中 |
| 3 | 考虑学习 FSRS-6（比 novelty entropy 更成熟） | ⭐ 中 |
| 4 | 考虑学习 Hippo 的 outcome reward factor（比 Q-value 更直观） | 📎 低 |
| 5 | 定位调整：从"海马体记忆引擎"→"因果记忆引擎" | 🔥 高 |

---

## 6. 和人脑的类比

Hippo 的 outcome feedback（positive → 衰减变慢）对应人脑的**多巴胺奖赏回路**——成功的经验被强化。Vestige 的 FSRS-6 对应人脑的**间隔重复效应**——间隔复习的记忆更持久。

causal-memory 的 prevented 负扩散对应人脑的**GABA 抑制性突触**——不仅强化好的（多巴胺），还主动抑制坏的（GABA）。**Hippo 和 Vestige 做了"多巴胺侧"，我们做了"多巴胺 + GABA 两侧"。**

---

## 7. 最终判断

**Hippo 和 Vestige 验证了 causal-memory 的工程方向（Rust + MCP + 海马体 + spreading + forgetting），但也证明这些不再是差异化。** 从今天起，causal-memory 的定位必须从"海马体记忆引擎"收窄到**"因果记忆引擎"**——"海马体"是标配，"因果"是独特。

在论文和 README 中，应该明确说：causal-memory 不是"又一个 Rust 记忆 MCP server"（Hippo 和 Vestige 已经做了），而是**唯一做因果关系的记忆系统**。
