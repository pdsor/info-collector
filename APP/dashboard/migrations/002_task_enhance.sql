-- 迁移 task_history 表，新增 trigger_type 和 rule_path 字段
ALTER TABLE task_history ADD COLUMN trigger_type TEXT DEFAULT 'manual';
ALTER TABLE task_history ADD COLUMN rule_path TEXT;
