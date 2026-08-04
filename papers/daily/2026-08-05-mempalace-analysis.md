# MemPalace 深度分析 · 2026-08-05

> **一句话结论：MemPalace 的 96.6% R@5 被"打假"了——这个分数来自 ChromaDB 默认 embedding + verbatim 全文存储，MemPalace 的"宫殿"结构没有参与。但 verbatim-first 的哲学被验证是对的——它验证了 causal-memory 的 session_logs 设计，同时挑战了我们的 eager distill 管道。**

---

## 1. 核心问题 / 背景

MemPalace（github.com/MemPalace/mempalace）在 2026 年 4 月开源后两周冲到 47K stars，声称 LongMemEval 96.6% R@5，零 LLM 调用。这是记忆赛道前所未有的数字——Mem0 只有 ~49%，Zep ~85%。

但独立审计（arXiv:2604.21284 "Spatial Metaphors for LLM Memory: A Critical Analysis" + GitHub issue #27 + lhl/agentic-memory 分析）发现了一个尴尬的事实。

---

## 2. 审计发现

### 2.1 96.6% 来自什么

| 组件 | 是否参与 96.6% |
|------|--------------|
| ChromaDB 默认 embedding (all-MiniLM-L6-v2) | ✅ 这就是全部 |
| Verbatim 全文存储（不压缩不提取） | ✅ 这就是全部 |
| MemPalace 的宫殿结构（wings/rooms/halls） | ❌ 没有参与 |
| LLM 调用 | ❌ 零调用 |
| 分层加载（L0/L1/L2） | ❌ raw mode 不用 |

GitHub issue #27 的原话：
> "Real score, but measured in 'raw mode' — uncompressed verbatim text stored in ChromaDB, standard nearest-neighbor retrieval. **The palace structure (wings/rooms/halls) is not involved.** This measures ChromaDB's default embedding model performance, not MemPalace."

### 2.2 R@5 vs Accuracy 的区别

| 指标 | 衡量什么 | MemPalace | causal-memory |
|------|---------|-----------|---------------|
| R@5 (Recall@5) | 能不能找到包含答案的 chunk | 96.6% | 88.6% (evidence hit rate) |
| LLM-Judge Accuracy | 能不能正确回答问题 | 未报告 | 71.2% |

**R@5 和 Accuracy 差一个"LLM 能不能用检索到的证据回答问题"的环节。** 我们之前分析过：88.6% evidence hit 但只有 71.2% accuracy——差的就是回答环节。

### 2.3 竞争格局变化

审计报告提到一个重要事实：**Mem0 追上来了**。

| 系统 | LongMemEval | 时间 |
|------|------------|------|
| MemPalace (raw) | 96.6% R@5 | 2026-04 |
| Mem0 (token-efficient algorithm) | 93.4% R@5 | 2026-04 |
| Zep | ~85% R@5 | 2026-03 |

Mem0 的"token-efficient memory algorithm"大幅提升了检索 recall。

---

## 3. Verbatim-First 哲学的验证

虽然 MemPalace 的宫殿结构被"打假"，但它的核心哲学——**verbatim-first**——被验证是对的：

> "Store everything, never summarize, solve retrieval separately."

这直接反驳了 Mem0/Zep/LangMem 的"extract-and-summarize"共识。

### 和 causal-memory 的对比

| 维度 | MemPalace (raw) | causal-memory |
|------|----------------|---------------|
| 写入策略 | verbatim 全文 | session_logs（verbatim）+ distill（提取） |
| 写入成本 | 零 LLM 调用 | distill 每session调 LLM |
| 检索 | ChromaDB embedding NN | BM25 + semantic RRF + spreading activation |
| R@5 | 96.6% | 88.6% |
| 因果关系 | ❌ | ✅ caused/prevented edges |

**causal-memory 已经有 verbatim 存储（session_logs）**。问题是我们在 verbatim 之上还做了一层 eager distill——而 MemPalace/LazyMem 证明这可能是不必要的。

---

## 4. 行动项

| # | 行动 | 优先级 |
|---|------|--------|
| 1 | 测量 session_logs（verbatim）单独的 R@5 | 🔥 高 |
| 2 | 评估 distill 的额外价值（是否提升 R@5？） | 🔥 高 |
| 3 | 考虑默认 raw mode + 可选 distill | ⭐ 中 |
| 4 | 用更好的 embedding 模型提升 R@5 | ⭐ 中 |

---

## 5. 最终判断

**MemPalace 的"宫殿"被审计"打假"了，但它的 verbatim-first 哲学是对的。** causal-memory 应该：
1. 保持 session_logs（verbatim 存储）作为主存储
2. 把 distill 改为可选/懒触发（参考 LazyMem + RecMem）
3. 用更好的 embedding 模型提升检索 recall
4. 因果关系是我们独有的——MemPalace 完全没有
