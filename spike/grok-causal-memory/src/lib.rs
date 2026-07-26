//! Causal memory layer for grok-build — implements insights/11 §2.
//!
//! 这是 grok-build memory crate 的因果扩展原型。
//! 真实 grok-build 的 `xai-grok-memory/src/schema.rs` 只有 `chunks` 表
//! (chunk + vector + FTS5),没有因果关系的一等公民。
//!
//! 本 crate 加两张表(对应 insights/11 §2 的 schema):
//! - `causal_edges` — 决策 → 结果
//! - `meta_causal_edges` — 决策 → 决策(跨任务模式)
//!
//! 和一个 `search_causal` 方法 —— 返回的不是语义相似 chunk,
//! 而是"过去类似决策导致了什么结果"。这是 insights/11 §5 解决问题一
//! (任务感知检索)的具体实现。
//!
//! 设计目标:
//! - schema 跟真实 grok-build 兼容(同样的 SQLite + 同样的 rowid 主键风格)
//! - 是叠加,不是替代 —— chunks 表保持原样,因果表是新增的索引层
//! - 可被真实 grok-build 的 memory crate 引用(只需要 copy 这个文件 + bump SCHEMA_VERSION)

use rusqlite::{params, Connection};

// ──────────────────────────────────────────────────────────────────────────
// 因果表的 schema(对应 insights/11 §2)
// ──────────────────────────────────────────────────────────────────────────

/// Schema version bump:grok-build 当前是 1,加因果表后是 2。
/// 真实接入时需要写 migration(从 1 升到 2 时 CREATE 因果表)。
pub const CAUSAL_SCHEMA_VERSION: u32 = 2;

pub const CAUSAL_SCHEMA_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS causal_edges (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,           -- 决策 ID(指向 chunks.id 或专门的 decisions 表)
    to_id TEXT NOT NULL,             -- 结果 ID
    relation TEXT NOT NULL CHECK(relation IN ('caused','enabled','prevented','no_effect')),
    confidence REAL NOT NULL,        -- 0.0-1.0,对应 insights/11 §3 步骤三
    discovered_by TEXT NOT NULL CHECK(discovered_by IN ('temporal','rule','llm_inferred','user_feedback')),
    discovered_at INTEGER NOT NULL,
    task_tag TEXT,                   -- 任务标签(用于 task-aware retrieval,insights/11 §5)
    FOREIGN KEY (from_id) REFERENCES chunks(id),
    FOREIGN KEY (to_id) REFERENCES chunks(id)
);
CREATE INDEX IF NOT EXISTS idx_causal_from ON causal_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_causal_to ON causal_edges(to_id);
CREATE INDEX IF NOT EXISTS idx_causal_task ON causal_edges(task_tag);

CREATE TABLE IF NOT EXISTS meta_causal_edges (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,           -- 决策 ID
    to_id TEXT NOT NULL,             -- 另一个决策 ID
    relation TEXT NOT NULL CHECK(relation IN ('similar_to','repeated','contradicts','refines')),
    pattern TEXT,                    -- 共性模式(如"都是并发问题的修复尝试")
    confidence REAL NOT NULL,
    FOREIGN KEY (from_id) REFERENCES chunks(id),
    FOREIGN KEY (to_id) REFERENCES chunks(id)
);
CREATE INDEX IF NOT EXISTS idx_meta_causal_from ON meta_causal_edges(from_id);
"#;

// ──────────────────────────────────────────────────────────────────────────
// 类型
// ──────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum CausalRelation {
    Caused,
    Enabled,
    Prevented,
    NoEffect,
}

impl CausalRelation {
    pub fn as_str(&self) -> &'static str {
        match self {
            CausalRelation::Caused => "caused",
            CausalRelation::Enabled => "enabled",
            CausalRelation::Prevented => "prevented",
            CausalRelation::NoEffect => "no_effect",
        }
    }
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "caused" => Some(CausalRelation::Caused),
            "enabled" => Some(CausalRelation::Enabled),
            "prevented" => Some(CausalRelation::Prevented),
            "no_effect" => Some(CausalRelation::NoEffect),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Confidence {
    /// 时间邻近 —— 0.3-0.5(insights/11 §3 步骤三:只是相关性)
    Temporal,
    /// 规则匹配 —— 0.6-0.8
    Rule,
    /// LLM 推断 —— 0.5-0.7(规模化的主力)
    LlmInferred,
    /// 用户反馈 —— 0.9-1.0(金标准)
    UserFeedback,
}

impl Confidence {
    pub fn as_str(&self) -> &'static str {
        match self {
            Confidence::Temporal => "temporal",
            Confidence::Rule => "rule",
            Confidence::LlmInferred => "llm_inferred",
            Confidence::UserFeedback => "user_feedback",
        }
    }
    pub fn default_value(&self) -> f64 {
        match self {
            Confidence::Temporal => 0.4,
            Confidence::Rule => 0.7,
            Confidence::LlmInferred => 0.6,
            Confidence::UserFeedback => 0.95,
        }
    }
}

/// 一条因果边:决策 from_id 导致了结果 to_id。
#[derive(Debug, Clone)]
pub struct CausalEdge {
    pub from_id: String,
    pub to_id: String,
    pub relation: CausalRelation,
    pub confidence: f64,
    pub discovered_by: Confidence,
    pub discovered_at: i64,
    pub task_tag: Option<String>,
}

/// 因果检索的结果。
#[derive(Debug, Clone)]
pub struct CausalRetrieval {
    pub decision_id: String,
    pub decision_text: String,
    pub outcome_id: String,
    pub outcome_text: String,
    pub relation: CausalRelation,
    pub confidence: f64,
}

// ──────────────────────────────────────────────────────────────────────────
// CausalStore —— 因果记忆的核心 API
// ──────────────────────────────────────────────────────────────────────────

pub struct CausalStore {
    conn: Connection,
}

impl CausalStore {
    /// 打开一个 in-memory 或 file-backed 的因果存储。
    /// 会自动建表(schema 不可变,所以重复调用安全)。
    pub fn open_in_memory() -> rusqlite::Result<Self> {
        let conn = Connection::open_in_memory()?;
        // 先建一个最小 chunks 表(真实 grok-build 里早就有了,这里只为测试)
        conn.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL
            );
        "#)?;
        conn.execute_batch(CAUSAL_SCHEMA_SQL)?;
        Ok(Self { conn })
    }

    /// 插入一个 chunk(真实 grok-build 用 blake3 hash + 行号,这里简化)。
    pub fn add_chunk(&self, id: &str, text: &str) -> rusqlite::Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO chunks(id, text) VALUES (?1, ?2)",
            params![id, text],
        )?;
        Ok(())
    }

    /// 插入一条因果边。
    pub fn add_causal_edge(&self, edge: &CausalEdge) -> rusqlite::Result<()> {
        self.conn.execute(
            "INSERT INTO causal_edges
                (from_id, to_id, relation, confidence, discovered_by, discovered_at, task_tag)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                edge.from_id,
                edge.to_id,
                edge.relation.as_str(),
                edge.confidence,
                edge.discovered_by.as_str(),
                edge.discovered_at,
                edge.task_tag,
            ],
        )?;
        Ok(())
    }

    /// 因果检索:给定一个决策 ID,返回它导致了什么结果。
    /// 对应 insights/11 §5 解决问题一(任务感知检索)的基础版。
    pub fn search_outcomes(&self, decision_id: &str) -> rusqlite::Result<Vec<CausalRetrieval>> {
        let mut stmt = self.conn.prepare(
            "SELECT c_from.text, c_to.id, c_to.text, ce.relation, ce.confidence
             FROM causal_edges ce
             JOIN chunks c_from ON c_from.id = ce.from_id
             JOIN chunks c_to ON c_to.id = ce.to_id
             WHERE ce.from_id = ?1
             ORDER BY ce.confidence DESC",
        )?;
        let rows = stmt.query_map(params![decision_id], |row| {
            Ok(CausalRetrieval {
                decision_id: decision_id.to_string(),
                decision_text: row.get(0)?,
                outcome_id: row.get(1)?,
                outcome_text: row.get(2)?,
                relation: CausalRelation::from_str(&row.get::<_, String>(3)?).unwrap(),
                confidence: row.get(4)?,
            })
        })?;
        rows.collect()
    }

    /// 任务感知检索:给定一个 task_tag,返回该任务下所有因果关系。
    /// 这是 insights/11 §5 的核心 —— 不是语义相似度,是任务 + 因果。
    pub fn search_by_task(&self, task_tag: &str) -> rusqlite::Result<Vec<CausalRetrieval>> {
        let mut stmt = self.conn.prepare(
            "SELECT c_from.id, c_from.text, c_to.id, c_to.text, ce.relation, ce.confidence
             FROM causal_edges ce
             JOIN chunks c_from ON c_from.id = ce.from_id
             JOIN chunks c_to ON c_to.id = ce.to_id
             WHERE ce.task_tag = ?1
             ORDER BY ce.confidence DESC",
        )?;
        let rows = stmt.query_map(params![task_tag], |row| {
            Ok(CausalRetrieval {
                decision_id: row.get(0)?,
                decision_text: row.get(1)?,
                outcome_id: row.get(2)?,
                outcome_text: row.get(3)?,
                relation: CausalRelation::from_str(&row.get::<_, String>(4)?).unwrap(),
                confidence: row.get(5)?,
            })
        })?;
        rows.collect()
    }

    /// 反向查询:给定一个结果,回溯它被哪个决策导致。
    /// 对应 insights/11 §5 解决问题二(失败归因)。
    pub fn trace_cause(&self, outcome_id: &str) -> rusqlite::Result<Vec<CausalRetrieval>> {
        let mut stmt = self.conn.prepare(
            "SELECT c_from.id, c_from.text, ce.relation, ce.confidence
             FROM causal_edges ce
             JOIN chunks c_from ON c_from.id = ce.from_id
             WHERE ce.to_id = ?1
             ORDER BY ce.confidence DESC",
        )?;
        let rows = stmt.query_map(params![outcome_id], |row| {
            Ok(CausalRetrieval {
                decision_id: row.get(0)?,
                decision_text: row.get(1)?,
                outcome_id: outcome_id.to_string(),
                outcome_text: String::new(), // 不查
                relation: CausalRelation::from_str(&row.get::<_, String>(2)?).unwrap(),
                confidence: row.get(3)?,
            })
        })?;
        rows.collect()
    }

    /// 统计:用于 benchmark 和可观测性。
    pub fn count_causal_edges(&self) -> rusqlite::Result<i64> {
        self.conn.query_row("SELECT COUNT(*) FROM causal_edges", [], |row| row.get(0))
    }

    pub fn count_chunks(&self) -> rusqlite::Result<i64> {
        self.conn.query_row("SELECT COUNT(*) FROM chunks", [], |row| row.get(0))
    }
}

// ──────────────────────────────────────────────────────────────────────────
// 单元测试 —— 验证 schema 和基础检索工作
// ──────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn seed_redis_story(store: &CausalStore) {
        // 复刻 papers/02 的源 session:Redis 缓存击穿 → mutex 死锁 → channel 修复
        store.add_chunk("d1", "决策:用 Redis 做缓存(选 Redis 不选 Memcached)").unwrap();
        store.add_chunk("o1", "结果:缓存击穿,DB 被打爆").unwrap();
        store.add_chunk("d2", "决策:用 redlock 实现 mutex 加锁").unwrap();
        store.add_chunk("o2", "结果:死锁 —— 某请求 acquire 后崩溃不释放").unwrap();
        store.add_chunk("d3", "决策:用 channel/single-flight 方案").unwrap();
        store.add_chunk("o3", "结果:成功修复 race condition").unwrap();

        // 因果边:每条决策 → 结果
        store.add_causal_edge(&CausalEdge {
            from_id: "d1".into(), to_id: "o1".into(),
            relation: CausalRelation::Caused, confidence: 0.9,
            discovered_by: Confidence::UserFeedback, discovered_at: 1000,
            task_tag: Some("caching".into()),
        }).unwrap();
        store.add_causal_edge(&CausalEdge {
            from_id: "d2".into(), to_id: "o2".into(),
            relation: CausalRelation::Caused, confidence: 0.85,
            discovered_by: Confidence::Rule, discovered_at: 1100,
            task_tag: Some("concurrency".into()),
        }).unwrap();
        store.add_causal_edge(&CausalEdge {
            from_id: "d3".into(), to_id: "o3".into(),
            relation: CausalRelation::Caused, confidence: 0.95,
            discovered_by: Confidence::UserFeedback, discovered_at: 1200,
            task_tag: Some("concurrency".into()),
        }).unwrap();
    }

    #[test]
    fn test_schema_creates_tables() {
        let store = CausalStore::open_in_memory().unwrap();
        // 表存在
        let n: i64 = store.conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('causal_edges','meta_causal_edges')",
            [], |row| row.get(0)
        ).unwrap();
        assert_eq!(n, 2);
    }

    #[test]
    fn test_insert_and_search_outcomes() {
        let store = CausalStore::open_in_memory().unwrap();
        seed_redis_story(&store);

        // 查 d2(mutex 决策)导致了什么
        let results = store.search_outcomes("d2").unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].outcome_text, "结果:死锁 —— 某请求 acquire 后崩溃不释放");
        assert_eq!(results[0].relation, CausalRelation::Caused);
        assert!((results[0].confidence - 0.85).abs() < 1e-6);
    }

    #[test]
    fn test_task_aware_retrieval() {
        // 对应 insights/11 §5 解决问题一
        let store = CausalStore::open_in_memory().unwrap();
        seed_redis_story(&store);

        // 任务感知:concurrency 任务下有哪些因果关系
        let results = store.search_by_task("concurrency").unwrap();
        assert_eq!(results.len(), 2); // d2→o2 + d3→o3

        // 按 confidence 排序,d3 (0.95) 应该在前
        assert!(results[0].confidence >= results[1].confidence);
    }

    #[test]
    fn test_failure_attribution() {
        // 对应 insights/11 §5 解决问题二 —— 失败归因
        let store = CausalStore::open_in_memory().unwrap();
        seed_redis_story(&store);

        // o2(死锁)是被哪个决策导致的?
        let causes = store.trace_cause("o2").unwrap();
        assert_eq!(causes.len(), 1);
        assert_eq!(causes[0].decision_text, "决策:用 redlock 实现 mutex 加锁");
    }

    #[test]
    fn test_relation_constraints() {
        // 验证 CHECK 约束 —— 无效的 relation 应该被拒绝
        let store = CausalStore::open_in_memory().unwrap();
        store.add_chunk("a", "a").unwrap();
        store.add_chunk("b", "b").unwrap();
        let result = store.conn.execute(
            "INSERT INTO causal_edges (from_id,to_id,relation,confidence,discovered_by,discovered_at)
             VALUES ('a','b','invalid_relation',0.5,'temporal',0)",
            [],
        );
        assert!(result.is_err(), "无效的 relation 应该被 CHECK 拒绝");
    }

    #[test]
    fn test_schema_version_bump() {
        // 真实 grok-build 的 schema.rs SCHEMA_VERSION 是 1
        // 加因果表后应该是 2
        assert_eq!(CAUSAL_SCHEMA_VERSION, 2);
    }
}
