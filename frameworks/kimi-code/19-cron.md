# Kimi Code · Cron / 定时任务系统拆解

**源码位置**:`packages/agent-core-v2/src/agent/cron/`(legacy) + `packages/agent-core-v2/src/session/cron/`(v2)
**核心文件**:`manager.ts`(400+ 行,CronManager)、`sessionCronStore.ts`(持久化)、`createCronScheduler.ts`

## 1. 为什么 Agent 需要 Cron?

Agent 不只是被动响应,还能**主动**工作:
- "每天早上 9 点检查 CI 状态"
- "每小时同步上游数据"
- "工作日下班前提醒我提交代码"

这让 agent 从"工具"变成"工作者"。

## 2. 核心抽象:CronTask

```typescript
interface CronTask {
  readonly id: string;
  readonly cron: string;                    // cron 表达式(5 字段)
  readonly prompt: string;                  // 触发时发给 agent 的 prompt
  readonly recurring: boolean;              // true = 循环,false = 一次性
  readonly createdAt: number;
  lastFiredAt?: number;                     // 最后触发时间
  fireCount: number;                        // 总触发次数
  stale: boolean;                           // 是否过期
}
```

## 3. CronManager 的核心职责

### 3.1 调度循环

```typescript
// manager.ts(简化)
constructor(agent: Agent, opts: CronManagerOptions = {}) {
  this.scheduler = createCronScheduler({
    clocks: opts.clocks ?? SYSTEM_CLOCKS,
    source: () => this.store.list(),                 // 任务来源
    isIdle: () => !agent.turn.hasActiveTurn,         // ★ 只在 agent 空闲时触发
    isKilled: () => process.env['KIMI_DISABLE_CRON'] === '1',
    onFire: (task, ctx) => this.handleFire(task, ctx),
    removeOneShot: (id) => this.removeTasks([id]),   // 一次性任务触发后删除
    onAdvanceCursor: (id, lastFiredAt) => this.advanceCursor(id, lastFiredAt),
    pollIntervalMs: process.env['KIMI_CRON_MANUAL_TICK'] === '1'
      ? null                                         // ★ 手动驱动(测试用)
      : opts.pollIntervalMs,
  });
  this.start();
}
```

### 3.2 三个关键设计

**1. `isIdle` 检查**:

```typescript
isIdle: () => !agent.turn.hasActiveTurn
```

**Agent 忙时不触发 cron**。防止"用户正在和 agent 对话,cron 突然插进来打断"。

**2. 全局 killswitch**:

```typescript
isKilled: () => process.env['KIMI_DISABLE_CRON'] === '1'
```

环境变量一行关掉所有 cron(应急用)。

**3. 手动 tick(测试)**:

```typescript
KIMI_CRON_MANUAL_TICK=1
```

关闭 setInterval,让测试用 `tick()` 显式推进时间。这让 cron 测试不依赖真实时间流逝。

### 3.3 触发处理

```typescript
private async handleFire(task: CronTask, ctx: CronFireContext): Promise<void> {
  const coalescedCount = ctx.coalescedCount;          // 错过的触发次数
  const prompt = task.prompt;

  // 发 telemetry
  this.emitScheduled(task);

  // 触发 agent(steer 模式,不抢当前 turn)
  await this.agent.records.logRecord({
    type: 'cron.fire',
    taskId: task.id,
    cron: task.cron,
    prompt,
    coalescedCount,
    recurring: task.recurring,
    stale: this.isStale(task),
  });

  // 通过 steer 把 prompt 注入 agent
  this.agent.turn.steer([{
    type: 'text',
    text: this.formatFirePrompt(task, coalescedCount),
  }], { kind: 'cron_job', jobId: task.id, ... });
}
```

**用 steer 而不是 prompt**:steer 是软插入(见 [09-loop.md](09-loop.md) §5.2),如果 agent 正在跑,cron 的 prompt 进队列等。这避免了 cron 抢占用户对话。

## 4. 持久化

### 4.1 文件镜像

```typescript
// manager.ts:166-170
private readonly persistStore: PerIdJsonStore<CronTask> | undefined;

// addTask 时
this.persistEnqueue(task.id, () =>
  this.persistStore!.write(task.id, task),
);
```

每个 task 一个 JSON 文件:`<agentDir>/cron/<taskId>.json`。session resume 时 `loadFromDisk` 重建。

### 4.2 串行化写入

```typescript
private readonly persistQueues: Map<string, Promise<void>> = new Map();

private persistEnqueue(id: string, fn: () => Promise<void>): void {
  const prev = this.persistQueues.get(id) ?? Promise.resolve();
  const next = prev.then(fn, fn);
  this.persistQueues.set(id, next);
  next.finally(() => {
    if (this.persistQueues.get(id) === next) {
      this.persistQueues.delete(id);
    }
  });
}
```

**per-id 串行队列**:同一个 task 的写操作串行(防止 rename race),不同 task 可以并行。Map 在完成后清理,不会无限增长。

## 5. Stale 检测

```typescript
private static readonly STALE_THRESHOLD_MS = 30 * 24 * 60 * 60 * 1000;  // 30 天

isStale(task: CronTask): boolean {
  if (process.env['KIMI_CRON_NO_STALE'] === '1') return false;
  if (task.recurring === false) return false;
  const age = this.clocks.wallNow() - task.createdAt;
  return Number.isFinite(age) && age >= STALE_THRESHOLD_MS;
}
```

**超过 30 天的循环任务标记为 stale**。触发时 prompt 会带 stale 标记,提醒 agent"这个任务可能过时了,问用户是否还要继续"。

## 6. 一次性任务的"rolled to next year"防护

```typescript
// tools/cron/cron-create.ts:218-232(来自 06-tool-system.md)
if (!recurring) {
  const firstFire = computeNextCronRun(parsed, nowAtPrepare);
  if (firstFire - nowAtPrepare > ONE_SHOT_MAX_FUTURE_MS) {  // ~1 年
    return {
      isError: true,
      output: `One-shot cron would not fire until ${firstFire} (more than a year out). If you meant "today", the pinned date has already passed this year.`,
    };
  }
}
```

防止"用户说'今天 9 点提醒我',但已经过了 9 点,实际会明年才触发"。

## 7. 边界条件

| 触发 | 行为 |
|---|---|
| Agent 正在 turn | cron 进 steer 队列,等 turn 结束 |
| 多个 cron 同时到期 | 按 fire 时间顺序触发 |
| Agent 关闭时 cron 到期 | coalescedCount 累加,resume 后一次性触发 |
| Cron 表达式无解(2月30日) | 创建时拒绝 |
| 5 年内不触发 | 创建时拒绝 |
| Session prompt 字节超 8KB | 创建时拒绝 |
| 同 session 超过 MAX_CRON_JOBS | 创建时拒绝 |
| Stale 任务 | 触发但带 stale 标记 |
| KIMI_DISABLE_CRON=1 | 调度器立即返回不触发 |
| Cron task 被删除 | 不再触发 |

## 8. 一句话总结

> Cron 系统让 agent **主动工作**:声明 cron 表达式 + prompt,到点自动触发。核心是 `isIdle` 检查(只在 agent 空闲时触发)+ steer 注入(不抢用户对话)+ 文件持久化(resume 后恢复,coalesce 错过的触发)+ stale 检测(30 天警告)+ 手动 tick(测试注入时间)。一次性任务有"明年才触发"防护。

## 9. 源码索引

| 概念 | 文件 |
|---|---|
| `CronManager` | `src/agent/cron/manager.ts` |
| `SessionCronStore` | `src/agent/cron/` |
| `createCronScheduler` | `src/agent/cron/` |
| CronCreate 工具 | `src/tools/cron/cron-create.ts`(v1)/ 对应 v2 |
| CronDelete 工具 | `src/tools/cron/cron-delete.ts` |
| 持久化 | `PerIdJsonStore<CronTask>` |

## 参考资料

- [09-loop.md](09-loop.md) —— steer 机制
- [08-context-memory.md](08-context-memory.md) —— CronJobOrigin 在 context
- [06-tool-system.md](06-tool-system.md) —— CronCreate 的 resolveExecution 范例
