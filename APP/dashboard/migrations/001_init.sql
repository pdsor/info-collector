-- Dashboard Database Schema
-- Version: 001

-- Cron Jobs Table
CREATE TABLE IF NOT EXISTS cron_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    second       TEXT DEFAULT '0',
    minute       TEXT NOT NULL DEFAULT '*',
    hour         TEXT NOT NULL DEFAULT '*',
    day          TEXT NOT NULL DEFAULT '*',
    month        TEXT NOT NULL DEFAULT '*',
    day_of_week  TEXT NOT NULL DEFAULT '*',
    rule_path    TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Task History Table
CREATE TABLE IF NOT EXISTS task_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    message     TEXT NOT NULL DEFAULT '',
    new_count   INTEGER NOT NULL DEFAULT 0,
    duration    REAL NOT NULL DEFAULT 0.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cron_jobs_enabled ON cron_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_task_history_created_at ON task_history(created_at DESC);
