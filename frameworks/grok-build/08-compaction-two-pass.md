# Grok Build · 两遍压缩(Compaction)拆解

> 📁 **源码位置** · `crates/codegen/xai-grok-shell/src/session/compaction.rs`(3321 行) + `compaction_config.rs` + `compaction_segments.rs` + `two_pass.rs` + `crates/common/xai-grok-compaction/src/code_compaction/`
>
> 📄 **核心文件** · `two_pass.rs`(两遍分割纯函数) · `compaction.rs`(压缩主逻辑) · `code_compaction/prompt.rs` · `code_compaction/templates/full_replace_summary_prompt.txt`

## 1. 核心创新:两遍压缩(Two-Pass)

**kimi-code 是单遍压缩**:把旧消息 → LLM 总结 → handoff note。

**grok-build 是两遍压缩**:

```
Pass 1: 压缩 95% 的历史 → NOTE₁
Pass 2: 把 NOTE₁ + 剩余 5% 尾部 → NOTE₂(最终 handoff)
```

### 1.1 为什么两遍?

```rust
//! Pass1 summarizes ~95% of history (by estimated-token weight) → NOTE₁.
//! Pass2 rewrites NOTE₁ + the ~5% tail into the successor-visible NOTE₂.
//! Sampling lives in compaction; this module has no I/O.
```

**单遍的问题**:如果直接压 100% 的历史,LLM 需要同时理解旧 context + 最近消息,容易丢失最近的细节(最重要的部分)。

**两遍的解法**:
1. **Pass 1**:先压前面的 95%(不太新的部分)→ NOTE₁(中间产物)
2. **Pass 2**:把 NOTE₁ + 最后 5%(最近最重要的消息)一起再压一遍 → NOTE₂(最终)

这让 pass 2 能**同时看到总结和最近的细节**,产出的 NOTE₂ 比单遍更完整。

### 1.2 关键常量

```rust
pub(crate) const TWO_PASS_DEFAULT_SPLIT_FRACTION: f64 = 0.95;        // 95% 给 pass 1
const TWO_PASS_MIN_SUMMARY_BLOCK_CHARS: usize = 1000;                 // NOTE₁ 最少 1000 字符
const TWO_PASS_MAX_NOTE1_CHARS: usize = 12_000;                       // NOTE₁ 最多 12K 字符
```

### 1.3 按 token 权重分割

```rust
fn split_index_by_token_fraction(weights: &[u64], fraction: f64) -> usize {
    // 不是按消息条数分,而是按 token 权重分
    // 确保前面 95% 的 token 给 pass 1
}
```

**按 token 而不是消息条数分割** —— 因为一条消息可能是 10 token 也可能是 5000 token。按 token 分割更精确。

## 2. Compaction 配置

```rust
// compaction_config.rs
// 触发比例、保留窗口、最大压缩次数等
```

和 kimi-code 类似(85% 触发、保留最近 N 条等),但有更多可配项。

## 3. Compaction Segments

```rust
// compaction_segments.rs
// 把对话分成段,决定哪些保留、哪些压缩
```

**Segment 概念**:不是按"消息条数"分,而是按**语义段落**分(例如一个 tool-call + tool-result 是一个 segment)。这让压缩不会切断"调用 + 结果"这种关联。

## 4. 和 kimi-code 对比

| 维度 | kimi-code | grok-build |
|---|---|---|
| **压缩遍数** | 1 遍 | **2 遍**(pass1: 95% → NOTE₁,pass2: NOTE₁ + 5% tail → NOTE₂) |
| **分割方式** | 按消息条数(maxRecentMessages=4) | **按 token 权重 + 语义 segment** |
| **handoff 质量** | 好(但可能丢最近细节) | **更好**(pass2 同时看到总结 + 最近消息) |
| **成本** | 1 次 LLM 调用 | **2 次 LLM 调用**(更贵,但质量更高) |
| **prompt** | compaction-instruction.md | **full_replace_summary_prompt.txt** + 两遍逻辑 |

## 5. 一句话总结

> Grok-build 的 compaction 是**两遍压缩**:Pass1 压前 95% 历史 → NOTE₁,Pass2 把 NOTE₁ + 最近 5% → NOTE₂(最终 handoff)。按 token 权重而非消息条数分割,确保最近的细节不被丢失。成本是 kimi-code 的 2 倍(2 次 LLM 调用),但 handoff 质量更高。

## 6. 源码索引

| 概念 | 文件 |
|---|---|
| 两遍分割(纯函数) | `session/two_pass.rs` |
| 压缩主逻辑 | `session/compaction.rs`(3321 行) |
| 配置 | `session/compaction_config.rs` |
| 语义分段 | `session/compaction_segments.rs` |
| code compaction | `xai-grok-compaction/src/code_compaction/` |
| prompt 模板 | `code_compaction/templates/full_replace_summary_prompt.txt` |
