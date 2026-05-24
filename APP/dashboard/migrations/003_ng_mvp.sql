-- Info Collector NG MVP metadata
-- 本地 SQLite 版本，用于承载 Source / Rule / Task / Governance 摘要。

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'website',
    category TEXT NOT NULL DEFAULT '',
    trust_score REAL NOT NULL DEFAULT 0.5,
    update_frequency INTEGER NOT NULL DEFAULT 3600,
    anti_crawl_level TEXT NOT NULL DEFAULT 'low',
    parser_strategy TEXT NOT NULL DEFAULT '',
    auth_required INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'zh-CN',
    tags TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE',
    rule_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS governance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL DEFAULT '',
    item_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    injection_risk_count INTEGER NOT NULL DEFAULT 0,
    field_completeness REAL NOT NULL DEFAULT 1.0,
    quality_score REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'SUCCESS',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled);
CREATE INDEX IF NOT EXISTS idx_governance_subject_platform ON governance_records(subject, platform);
