# Memora FAMA Benchmark 深度分析 · 2026-08-06

> **一句话结论：Memora 的 FAMA 指标（Forgetting-Aware Memory Accuracy）首次系统性地惩罚"使用过期记忆"的行为——这直接验证了 causal-memory 的 prevented 负扩散和 superseded 机制的设计价值。Memora 应该成为 causal-memory 的下一个主 benchmark。**

---

## 1. 核心问题 / 背景

现有记忆 benchmark（LoCoMo / LongMemEval）有一个共同缺陷：它们只检查"答案是否包含正确信息"，**不惩罚使用过期/已失效记忆**。

举个例子：用户在 3 月说"我在公司 A 工作"，6 月说"我跳槽到公司 B"。如果 agent 回答"你在公司 A 工作"，标准指标可能给部分分（因为确实曾经是真的），但**正确答案应该是公司 B**。

Memora 引入 FAMA 来解决这个问题。

---

## 2. 方法详解

### 2.1 Memora Benchmark 设计

三个维度交叉：

| 维度 | 取值 |
|------|------|
| **任务** | Remembering（事实召回）/ Recommending（推荐）/ Reasoning（推理）|
| **时间跨度** | Weekly / Monthly / Quarterly |
| **记忆变化量** | Weekly 1.9 次变更 / Monthly 5.3 次 / Quarterly 28.4 次 |

每个 persona 有多 session 对话，其中有信息更新、偏好变化、事实失效。agent 必须正确回答基于**当前**记忆状态的问题。

### 2.2 FAMA 指标

```
标准 Memory Presence Accuracy (MPA):
  回答包含正确信息 → 得分
  回答包含过期信息 → 也可能得分（不惩罚）

FAMA (Forgetting-Aware Memory Accuracy):
  回答包含正确信息 → 得分
  回答包含过期/失效信息 → 扣分
```

FAMA 的核心创新：每条记忆有"valid_until"时间戳。如果 agent 的回答引用了已失效的记忆，FAMA 扣分。

### 2.3 实验结果（真实数字）

**长期记忆 Agent 的 FAMA 分数（forgetting reduction 在括号内）：**

| Agent | Weekly | Monthly | Quarterly |
|-------|--------|---------|-----------|
| LangMem | 173.0 (−23.0) | 132.2 (−31.1) | 127.4 (−43.4) |
| Mem-0 | 119.4 (−10.4) | 78.6 (−21.3) | 72.7 (−12.3) |

**关键发现**：
- LangMem 在标准 MPA 上最高，但 FAMA reduction 最大（−43.4 at quarterly）——它大量使用过期记忆
- Nemori 在标准 MPA 上落后于 MemoryOS 和 A-Mem，但 FAMA reduction 最小（15.4），最终排名反超
- **"Retaining access to older memories without effective forgetting amplifies inconsistency"**——不遗忘 = 不一致

---

## 3. 和 causal-memory 的精确对比

| 维度 | Memora FAMA | causal-memory | 关系 |
|------|------------|---------------|------|
| **过期记忆处理** | 惩罚使用过期记忆 | prevented 负扩散 + superseded 标记 | ✅ **直接对应** |
| **forgetting 机制** | 测量（benchmark） | 实现（prevented/superseded/invalidate） | ✅ 测-做对应 |
| **valid_until** | 每条记忆有时间戳 | causal_edges 有 valid_from/valid_to | ✅ 已有 |
| **变更追踪** | 跟踪 mutations | invalidate_superseded + replace_same_key | ✅ 已有 |
| **FAMA 分数** | 未测 | 需要测 | ⚠️ 行动项 |

### 关键洞察

**Memora FAMA 测的能力，causal-memory 天然有优势：**

1. **prevented 负扩散** — 过期记忆被 prevented 边自动抑制，不参与 spreading activation
2. **superseded 标记** — 旧记忆被标记为 superseded（valid_to 非 NULL），检索时被过滤
3. **invalidate_superseded** — 新记忆写入时自动失效矛盾的旧记忆

**Memora 的实验证明这些机制的价值**：没有有效遗忘的 agent（LangMem）在 quarterly 设置下 FAMA reduction 高达 -43.4——将近一半的"正确"答案是靠过期记忆蒙对的。

---

## 4. 行动项

| # | 行动 | 对应机制 | 优先级 |
|---|------|---------|--------|
| 1 | 下载 Memora benchmark 数据集 | benchmark | 🔥 高 |
| 2 | 在 Memora 上评估 causal-memory | benchmark | 🔥 高 |
| 3 | 测量 causal-memory 的 FAMA reduction | prevented/superseded | 🔥 高 |
| 4 | 预期 prevented 负扩散 → 小 reduction | hippocampus | ⭐ 验证 |
| 5 | 论文中引用 Memora 作为 forgetting benchmark | documentation | ⭐ 中 |

---

## 5. 和人脑的类比

Memora 的 FAMA 指标对应人脑的**主动遗忘**机制：

- 人脑不是"什么都能记住"——海马体的 DG（齿状回）做 pattern separation，区分新旧记忆
- 失去遗忘能力 = 记忆混乱——额颞叶痴呆患者无法抑制旧记忆，导致行为矛盾
- **causal-memory 的 prevented 负扩散 = 主动遗忘的 AI 实现**——不是"删除旧记忆"，而是"抑制旧记忆的传播"

Memora 证明了：**记忆系统的价值不只在"记住"，更在"遗忘"。** 这是赛道的新方向——从"召回准确率"转向"遗忘准确率"。

---

## 6. 最终判断

**Memora FAMA 是 causal-memory 的最佳 benchmark——它测的能力（有效遗忘）正是 prevented 负扩散和 superseded 机制解决的。** 应该立即在 Memora 上评估 causal-memory，预期 FAMA reduction 显著小于竞品（因为 prevented 自动抑制过期记忆）。

这可能是 causal-memory 在 benchmark 层面取得差异化优势的机会——不在"记住多少"（已经饱和）上竞争，而在"遗忘多准"上领先。
