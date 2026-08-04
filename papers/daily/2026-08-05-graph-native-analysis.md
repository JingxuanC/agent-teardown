# Graph-Native Cognitive Memory 深度分析 · 2026-08-05

> **一句话结论：这篇论文（arXiv:2603.17244）是 causal-memory 统一图设计的学术同盟——它明确论证了"统一图 vs 分图"的优势，站在我们这边。它的 belief revision semantics 和 URI addressing 是我们可以学习的两个具体设计。**

---

## 1. 核心问题 / 背景

Graph-Native Cognitive Memory 解决的问题是：agent 如何在一个统一的图结构中同时管理记忆和资产（工作产出）。

核心创新：
1. **单图统一**——所有关系在一张 property graph 里，用 typed edges 区分
2. **Belief revision**——形式化的 AGM 信念修正公理
3. **URI addressing**——记忆节点有确定性 URI
4. **Immutable revisions + mutable tag pointers**——版本控制式管理

---

## 2. 架构详解

### 2.1 单图统一

```
Neo4j (长期图) + Redis (工作记忆)
  所有关系在一张 property graph 里：
  - 记忆边（remembered, learned, decided）
  - 资产边（produced, version-of, current-tag）
  - 因果边（caused-by, derived-from）
```

### 2.2 Belief Revision (AGM 公理)

AGM（Alchourrón-Gärdenfors-Makinson）是信念修正的形式化理论：
- **Expansion**：加入新信念（如果和旧信念不矛盾）
- **Contraction**：移除一个信念（不加入新信息）
- **Revision**：加入新信念 + 移除矛盾的旧信念

Graph-Native 把这映射到图操作：
- Expansion = 加新边
- Contraction = 删边（保留历史）
- Revision = 加新边 + 标记旧边为 superseded

### 2.3 URI Addressing

每个记忆节点有一个确定性 URI（类似 `mem://agent/decision/2026-08-05/redis-cache`）。这让其他系统可以精确引用一个记忆节点。

---

## 3. 和 causal-memory 的精确对比

| 维度 | Graph-Native | causal-memory | 关系 |
|------|-------------|---------------|------|
| **图架构** | 统一图（property graph） | 统一图（CSR sparse matrix） | ✅ 同一阵营 |
| **边类型** | typed edges（未明确类型列表） | 7 种 typed edge | ⭐ causal-memory 更明确 |
| **信念修正** | AGM 形式化公理 | invalidate_superseded | ⭐ Graph-Native 更理论化 |
| **URI** | ✅ 有 | ❌ 无 | ⭐ 可以学 |
| **版本控制** | immutable revisions + tag pointers | swr_consolidate_immutable | ✅ 类似 |
| **负扩散** | ❌ 无 | prevented → -0.3 | ⭐ causal-memory 独有 |
| **前向模拟** | ❌ 无 | intervention_query | ⭐ causal-memory 独有 |
| **存储** | Neo4j + Redis | SQLite | 不同选择 |

### 关键洞察

**Graph-Native 在论文中明确批评了 MAGMA 的分图设计：**

> "MAGMA disentangles memory dimensions into separate graphs for cleaner retrieval routing, whereas our architecture unifies all relationships in a single property graph with typed edges, enabling cross-dimensional traversal (e.g., ANALYZEIMPACT propagating across all edge types simultaneously)."

这几乎是在说 causal-memory 的设计哲学。**我们是统一图阵营，Graph-Native 是我们的学术同盟。**

---

## 4. 行动项

| # | 行动 | 优先级 |
|---|------|--------|
| 1 | 引用 Graph-Native 作为统一图的学术支持 | 🔥 高 |
| 2 | 学习 AGM belief revision 公理 | ⭐ 中 |
| 3 | 考虑加 URI addressing | ⭐ 中 |
| 4 | 对比 Neo4j+Redis vs SQLite 的 tradeoff | 📎 低 |

---

## 5. 最终判断

**Graph-Native 是 causal-memory 在"统一图 vs 分图"辩论中的学术同盟。** 它的 belief revision semantics 和 URI addressing 是我们可以学习的具体设计。但在 prevented 负扩散和 intervention_query 上，causal-memory 仍然独有。
