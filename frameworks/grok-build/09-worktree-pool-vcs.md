# Grok Build · Worktree Pool + VCS + Hunk Tracker 拆解

> 📁 **源码位置** · `crates/codegen/xai-fast-worktree/`(19K 行) + `crates/codegen/xai-grok-shell/src/session/worktree_pool.rs`(2439 行) + `crates/codegen/xai-hunk-tracker/`(13K 行) + `crates/codegen/xai-gix-status/`

## 1. Worktree Pool(预创建 git worktree 池)

**kimi-code 没有**。grok-build 有**专用的 worktree 池**。

### 1.1 问题

macOS/APFS 上创建 git worktree 是 **O(file_count)**(慢,大项目可能几秒到几十秒)。如果每次 subagent spawn 都等 worktree 创建,用户体验很差。

### 1.2 解法:预创建 + 池化

```rust
//! On startup the pool spawns a background fill task that pre-creates linked
//! worktrees up to `pool_size`. When `acquire()` takes a worktree and the
//! pool drops below capacity, it kicks the fill task to create replacements.
//! `release()` returns used worktrees (cleaned in background) so they can
//! be reused without a full O(N) creation.
```

**流程**:
1. 启动时:**后台预创建** `pool_size` 个 worktree
2. 需要 worktree 时:`acquire()` 从池里取
3. 池低于容量:**后台填充**(创建新 worktree 补位)
4. 用完后:`release()` 归还(后台清理,可复用)

### 1.3 原子 Claim(防竞争)

```rust
const READY_SUFFIX: &str = ".ready";
const CLAIMED_SUFFIX: &str = ".claimed";
const CLAIMING_SUFFIX: &str = ".claiming";
```

**三阶段原子 claim**:
1. worktree 创建完成 → 写 `.ready` 文件
2. `acquire()` → rename `.ready` → `.claimed`(原子操作)
3. 如果有人正在 claim(rename `.ready` → `.claiming` → `.claimed`)

**为什么用文件而不是 Mutex**:多个 grok 进程可能共享同一个池,跨进程 Mutex 复杂,文件 rename 是原子的。

### 1.4 多实例安全

```rust
//! Each pool instance gets a unique subdirectory under
//! `~/.grok/worktree_pool/<instance_id>/` with a `.pid` liveness file.
//! Startup cleanup only removes directories for dead processes.
```

每个 grok 实例有自己的子目录(`~/.grok/worktree_pool/<instance_id>/`),带 PID 存活文件。启动时**清理死进程的残留 worktree**。

### 1.5 macOS only

```rust
//! macOS only: Linux has O(1) BTRFS snapshots; the pool adds value
//! only on macOS/APFS where worktree creation is O(file_count).
```

**Linux 上不需要**(BTRFS 快照是 O(1))。这个池**专门为 macOS 优化**(xAI 的开发者主要用 Mac)。

## 2. Hunk Tracker(变更追踪)

> `crates/codegen/xai-hunk-tracker/`(13K 行)

### 2.1 作用

追踪 agent 做了**哪些具体的代码变更**(hunk 级别),用于:
- **Skeptic panel**:显示 diff 给验证 agent 看
- **Undo/rewind**:精确回退某个变更
- **UI 展示**:高亮 agent 改了哪些行

### 2.2 和 kimi-code 的对比

kimi-code 没有独立的 hunk tracker。变更追踪靠 wire log(但那是消息级别,不是代码行级别)。grok-build 的 hunk tracker 能精确到**哪一行改了什么**,这让 skeptic panel 的 diff 更精准。

## 3. Git Status(xai-gix-status)

用 `gix`(纯 Rust 的 git 实现)替代 `git2-rs`。不用 shell `git status`,直接用 Rust 库读 git index。更快、更安全(不依赖 shell)。

## 4. 和 kimi-code 对比

| 维度 | kimi-code | grok-build |
|---|---|---|
| **worktree** | 无(靠 git 原生命令) | **预创建池 + 原子 claim + 后台填充** |
| **变更追踪** | wire log(消息级别) | **hunk tracker(行级别)** |
| **git 操作** | shell `git` | **gix(纯 Rust)** |
| **多实例** | 不支持 | **PID 存活文件 + 自动清理** |
| **平台优化** | 无 | **macOS 专用 worktree 池** |

## 5. 一句话总结

> Worktree Pool 是 grok-build 独有的 **macOS 性能优化**:预创建 git worktree 池 + 原子文件 claim + 后台填充,让 subagent spawn 不等 worktree 创建。Hunk Tracker 做**行级别变更追踪**(用于 skeptic panel + undo + UI)。Git 操作用 **gix(纯 Rust)**,不依赖 shell。整体让 git 集成比 kimi-code **深一个量级**(从"调 shell git"到"纯 Rust git 库 + worktree 池 + 行级 diff")。

## 6. 源码索引

| 概念 | 文件 |
|---|---|
| Worktree pool | `session/worktree_pool.rs`(2439 行) |
| Fast worktree crate | `xai-fast-worktree/src/`(19K 行) |
| Hunk tracker | `xai-hunk-tracker/src/`(13K 行) |
| Git status(gix) | `xai-gix-status/src/` |
| Session worktree | `session/worktree.rs` |
