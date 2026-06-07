-- ============================================
-- Change Notification Tables Migration
-- 说明: 变更通知数据表，支持事件驱动架构
-- 创建时间: 2026-05-01
-- ============================================

-- ============================================
-- 表: change_events
-- 说明: 存储变更事件记录，用于事件溯源和通知分发
-- ============================================

CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    channels TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    audit_log_id INTEGER,
    
    CONSTRAINT chk_status CHECK (status IN ('pending', 'processing', 'delivered', 'failed'))
);

-- change_events 索引
CREATE INDEX IF NOT EXISTS idx_change_events_object_type ON change_events(object_type);
CREATE INDEX IF NOT EXISTS idx_change_events_object_id ON change_events(object_id);
CREATE INDEX IF NOT EXISTS idx_change_events_status ON change_events(status);
CREATE INDEX IF NOT EXISTS idx_change_events_created_at ON change_events(created_at);
CREATE INDEX IF NOT EXISTS idx_change_events_audit_log ON change_events(audit_log_id);

-- ============================================
-- 表: change_subscriptions
-- 说明: 存储用户订阅配置，支持灵活的事件订阅
-- ============================================

CREATE TABLE IF NOT EXISTS change_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    event_types TEXT,
    channel VARCHAR(50) NOT NULL DEFAULT 'in_app',
    filter_condition TEXT,
    webhook_url VARCHAR(500),
    webhook_secret VARCHAR(200),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_channel CHECK (channel IN ('in_app', 'email', 'webhook', 'sms'))
);

-- change_subscriptions 索引
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_user_id ON change_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_object_type ON change_subscriptions(object_type);
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_enabled ON change_subscriptions(enabled);

-- ============================================
-- 外键约束 (SQLite 需要启用 PRAGMA foreign_keys = ON)
-- ============================================

-- 注意: SQLite 的外键约束在表创建时定义
-- 以下 ALTER TABLE 语句在 SQLite 中可能不被支持
-- 外键约束已在表创建时通过 REFERENCES 子句定义

-- ============================================
-- 数据字典说明
-- ============================================

-- change_events 表字段说明:
-- id: 自增主键
-- object_type: 对象类型 (如 'product', 'domain', 'business_object' 等)
-- object_id: 对象ID
-- event_type: 事件类型 ('create', 'update', 'delete', 'state_change')
-- changed_fields: JSON 数组，记录变更的字段名列表
-- old_values: JSON 对象，变更前的值
-- new_values: JSON 对象，变更后的值
-- payload: JSON 对象，事件的附加数据
-- channels: JSON 数组，通知渠道列表 ['in_app', 'email', 'webhook']
-- status: 事件状态 ('pending', 'processing', 'delivered', 'failed')
-- retry_count: 重试次数
-- created_at: 事件创建时间
-- delivered_at: 事件投递时间
-- audit_log_id: 关联的审计日志ID

-- change_subscriptions 表字段说明:
-- id: 自增主键
-- user_id: 订阅用户ID
-- object_type: 订阅的对象类型
-- event_types: JSON 数组，订阅的事件类型 ['create', 'update', 'delete']
-- channel: 通知渠道 ('in_app', 'email', 'webhook', 'sms')
-- filter_condition: JSON 对象，过滤条件
-- webhook_url: Webhook 回调地址 (channel=webhook 时使用)
-- webhook_secret: Webhook 签名密钥
-- enabled: 是否启用 (1=启用, 0=禁用)
-- created_at: 订阅创建时间

-- ============================================
-- 示例数据 (可选)
-- ============================================

-- INSERT INTO change_subscriptions (user_id, object_type, event_types, channel, enabled)
-- VALUES (1, 'product', '["create", "update", "delete"]', 'in_app', 1);

-- INSERT INTO change_subscriptions (user_id, object_type, event_types, channel, webhook_url, enabled)
-- VALUES (1, 'domain', '["create", "update"]', 'webhook', 'https://example.com/webhook', 1);
