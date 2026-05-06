-- Migration: 002_task_logs
-- Creates task_logs table for persisting JSONL events from task runs

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES task_history(id)
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);