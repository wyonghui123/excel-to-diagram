-- ============================================================
-- SSOT migration: updated_at 从物理列改为从 audit_logs 虚拟计算
-- 
-- 变更内容:
-- 1. audit_logs 表加 created_at_epoch (Unix毫秒INTEGER) — 高效MAX聚合
-- 2. 建立复合索引加速 object_type + object_id + action 查询
-- 3. 所有业务表删除 updated_at 物理列 — 单一事实原则
-- ============================================================

-- 阶段1: 审计日志表升级
ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT;

-- 从现有的 TEXT created_at 填充 epoch 值
-- strftime('%s', ...) 返回 Unix 秒，* 1000 转为毫秒
UPDATE audit_logs 
SET created_at_epoch = (strftime('%s', created_at) * 1000)
WHERE created_at_epoch IS NULL AND created_at IS NOT NULL;

-- SSOT 查询索引: 覆盖 object_type + object_id + action + epoch 排序
CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated 
ON audit_logs(object_type, object_id, action, created_at_epoch DESC);

-- 阶段2: 业务表删除 updated_at 物理列
-- 每张表的删除操作独立执行，某张表失败不影响其他表

-- products 表
ALTER TABLE products DROP COLUMN updated_at;

-- versions 表
ALTER TABLE versions DROP COLUMN updated_at;

-- domains 表 (如果存在该列)
ALTER TABLE domains DROP COLUMN updated_at;

-- service_modules 表 (如果存在该列)
ALTER TABLE service_modules DROP COLUMN updated_at;
