-- ========================================================================
-- v2_001_audit_log_v2.sql
-- 【2026-06-05 Spec v1.0 实施】FR-LOG-005: AuditRecord 新增 5 字段
-- ========================================================================
-- 兼容 SQLite + PostgreSQL

-- 🆕 v2 新增 5 字段
ALTER TABLE audit_logs ADD COLUMN action_kind TEXT;          -- 'instance' | 'static'
ALTER TABLE audit_logs ADD COLUMN outcome TEXT;              -- 'success' | 'failure' | 'denied' | 'retry'
ALTER TABLE audit_logs ADD COLUMN parent_action_id INTEGER;  -- FK to audit_logs.id（批量聚合）
ALTER TABLE audit_logs ADD COLUMN error_message TEXT;        -- 失败/拒绝时记录原因
ALTER TABLE audit_logs ADD COLUMN retention_until TEXT;      -- ISO 8601 截止时间（6 月）

-- 🆕 v2 索引（4 个）
CREATE INDEX IF NOT EXISTS idx_audit_parent ON audit_logs(parent_action_id);
CREATE INDEX IF NOT EXISTS idx_audit_outcome ON audit_logs(outcome);
CREATE INDEX IF NOT EXISTS idx_audit_action_kind ON audit_logs(action_kind);
CREATE INDEX IF NOT EXISTS idx_audit_retention ON audit_logs(retention_until);

-- 🆕 v2 归档表（FR-LOG-008 6 月归档）
CREATE TABLE IF NOT EXISTS audit_logs_archive (
    id INTEGER PRIMARY KEY,
    archived_at TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    action TEXT,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    user_name TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT,
    trace_id TEXT,
    transaction_id TEXT,
    status TEXT,
    agent_id TEXT,
    agent_session_id TEXT,
    tool_call_id TEXT,
    agent_reasoning TEXT,
    log_category TEXT,
    log_level TEXT,
    -- v2 字段
    action_kind TEXT,
    outcome TEXT,
    parent_action_id INTEGER,
    error_message TEXT,
    retention_until TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_archive_retention ON audit_logs_archive(retention_until);
CREATE INDEX IF NOT EXISTS idx_audit_archive_object ON audit_logs_archive(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_archive_user ON audit_logs_archive(user_id, created_at);

-- 回滚 SQL（手动执行）
-- ALTER TABLE audit_logs DROP COLUMN action_kind;
-- ALTER TABLE audit_logs DROP COLUMN outcome;
-- ALTER TABLE audit_logs DROP COLUMN parent_action_id;
-- ALTER TABLE audit_logs DROP COLUMN error_message;
-- ALTER TABLE audit_logs DROP COLUMN retention_until;
-- DROP INDEX IF EXISTS idx_audit_parent;
-- DROP INDEX IF EXISTS idx_audit_outcome;
-- DROP INDEX IF EXISTS idx_audit_action_kind;
-- DROP INDEX IF EXISTS idx_audit_retention;
-- DROP TABLE IF EXISTS audit_logs_archive;
