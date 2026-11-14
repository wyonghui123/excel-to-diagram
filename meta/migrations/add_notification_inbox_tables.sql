-- ============================================
-- Message Center: 投递记录 + 站内收件箱 (P1-b)
-- 依据 docs/specs/spec-message-platform-change-event-2026-11-14.md §8
-- 幂等：全部 IF NOT EXISTS，可重复执行
-- ============================================

-- 1) 投递记录（每个 事件 × 订阅 × 通道 一行，重试状态机的事实载体）
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    subscription_id INTEGER NOT NULL,
    user_id INTEGER,
    channel VARCHAR(20) NOT NULL
        CHECK (channel IN ('in_app','webhook','im','email','sms')),
    target VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sending','delivered','failed','skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, subscription_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_delivery_status_retry
    ON notification_deliveries(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_delivery_event
    ON notification_deliveries(event_id);

-- 2) 站内收件箱（唯一收件箱；task_id 为可执行附件弱引用，无 FK）
CREATE TABLE IF NOT EXISTS notification_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delivery_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(250) NOT NULL,
    body VARCHAR(2000),
    link VARCHAR(500),
    task_id VARCHAR(64),
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retention_until TIMESTAMP,
    UNIQUE(user_id, delivery_id)
);
CREATE INDEX IF NOT EXISTS idx_inbox_user_unread
    ON notification_inbox(user_id, read_at, created_at);
CREATE INDEX IF NOT EXISTS idx_inbox_task
    ON notification_inbox(task_id) WHERE task_id IS NOT NULL;