CREATE TABLE IF NOT EXISTS cron_jobs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    rule_path   TEXT NOT NULL,
    schedule    TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_history (
    id          TEXT PRIMARY KEY,
    job_id      TEXT,
    rule_path   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'stopped')),
    new_count   INTEGER DEFAULT 0,
    error_msg   TEXT,
    duration    REAL,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_task_history_job_id ON task_history(job_id);
CREATE INDEX IF NOT EXISTS idx_task_history_started_at ON task_history(started_at);
