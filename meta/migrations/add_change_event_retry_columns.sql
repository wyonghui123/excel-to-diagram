-- ============================================
-- Message Center: 事件重试补充列 + 索引 (P1-c)
-- 依据 docs/specs/spec-message-platform-change-event-2026-11-14.md §8
-- 幂等：ALTER 重复列由 migration_runner 的幂等错误容忍跳过；
--       索引全部 IF NOT EXISTS，可重复执行
-- ============================================

-- 1) 事件状态原因（投递集合聚合推导的补充语义，不新增 status 枚举）
ALTER TABLE change_events ADD COLUMN status_reason VARCHAR(30);

-- 2) 发布幂等键（同一业务事务重复发布只保留一条）
ALTER TABLE change_events ADD COLUMN idempotency_key VARCHAR(200);

CREATE UNIQUE INDEX IF NOT EXISTS uq_change_events_idem
    ON change_events(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_change_events_type_time
    ON change_events(object_type, created_at);

CREATE INDEX IF NOT EXISTS idx_change_events_status_time
    ON change_events(status, created_at);