-- ============================================================================
-- Migration: BUG-V031 service_module.domain_id / BO domain_id / rel 6列 冗余列自动维护
-- 创建时间: 2026-06-28
-- 背景:
--   service_module.domain_id, business_object.domain_id/sub_domain_id,
--   relationships.source_*/target_* 等冗余列 (从子表 FK 推导) 从未自动维护,
--   直接影响关系范围树分类 (用户选 domain 时 0 in-scope 关系) 和 BO list 显示
--
-- 方案: E - DB 层 trigger 自动同步
--   0. 添加冗余列 (ALTER TABLE)
--   1. 一次性回填当前 NULL 数据
--   2. SM INSERT/UPDATE trigger: 自动从 sub_domain_id 推 domain_id
--   3. BO INSERT/UPDATE trigger: 自动从 service_module_id 推 domain_id/sub_domain_id
--   4. rel 4 个 trigger: 自动从 source_bo_id/target_bo_id 推 6 列
--   5. 所有 trigger 都是"总是覆盖" (不依赖 IS NULL 条件), 防止任何错误值
--
-- 回退:
--   DROP TRIGGER trg_sm_domain_id_insert;
--   DROP TRIGGER trg_sm_domain_id_update;
--   DROP TRIGGER trg_bo_domain_id_insert;
--   DROP TRIGGER trg_bo_domain_id_update;
--   DROP TRIGGER trg_rel_src_domain_insert;
--   DROP TRIGGER trg_rel_src_domain_update;
--   DROP TRIGGER trg_rel_tgt_domain_insert;
--   DROP TRIGGER trg_rel_tgt_domain_update;
-- ============================================================================

-- ========== Step 0: ALTER TABLE 添加冗余列 ==========

-- service_modules: 添加 domain_id
ALTER TABLE service_modules ADD COLUMN domain_id INTEGER;

-- business_objects: 添加 domain_id 和 sub_domain_id
ALTER TABLE business_objects ADD COLUMN domain_id INTEGER;
ALTER TABLE business_objects ADD COLUMN sub_domain_id INTEGER;

-- relationships: 添加 6 列
ALTER TABLE relationships ADD COLUMN source_domain_id INTEGER;
ALTER TABLE relationships ADD COLUMN source_sub_domain_id INTEGER;
ALTER TABLE relationships ADD COLUMN source_service_module_id INTEGER;
ALTER TABLE relationships ADD COLUMN target_domain_id INTEGER;
ALTER TABLE relationships ADD COLUMN target_sub_domain_id INTEGER;
ALTER TABLE relationships ADD COLUMN target_service_module_id INTEGER;

-- 创建索引以加速回填和后续查询
CREATE INDEX IF NOT EXISTS idx_sm_domain_id ON service_modules(domain_id);
CREATE INDEX IF NOT EXISTS idx_bo_domain_id ON business_objects(domain_id);
CREATE INDEX IF NOT EXISTS idx_bo_sub_domain_id ON business_objects(sub_domain_id);
CREATE INDEX IF NOT EXISTS idx_rel_src_domain_id ON relationships(source_domain_id);
CREATE INDEX IF NOT EXISTS idx_rel_tgt_domain_id ON relationships(target_domain_id);

-- ========== Step 1: 一次性回填 SM ==========
UPDATE service_modules
SET domain_id = (
    SELECT sd.domain_id FROM sub_domains sd WHERE sd.id = service_modules.sub_domain_id
)
WHERE service_modules.sub_domain_id IS NOT NULL;

-- ========== Step 2: 一次性回填 BO ==========
UPDATE business_objects
SET domain_id = (
    SELECT sm.domain_id FROM service_modules sm WHERE sm.id = business_objects.service_module_id
),
sub_domain_id = (
    SELECT sm.sub_domain_id FROM service_modules sm WHERE sm.id = business_objects.service_module_id
)
WHERE service_module_id IS NOT NULL;

-- ========== Step 3: 一次性回填 rel 6 列 ==========
UPDATE relationships
SET source_domain_id = (
    SELECT bo.domain_id FROM business_objects bo WHERE bo.id = relationships.source_bo_id
),
source_sub_domain_id = (
    SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = relationships.source_bo_id
),
source_service_module_id = (
    SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = relationships.source_bo_id
),
target_domain_id = (
    SELECT bo.domain_id FROM business_objects bo WHERE bo.id = relationships.target_bo_id
),
target_sub_domain_id = (
    SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = relationships.target_bo_id
),
target_service_module_id = (
    SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = relationships.target_bo_id
)
WHERE source_bo_id IS NOT NULL AND target_bo_id IS NOT NULL;

-- ========== Step 4: Triggers (总是覆盖, 防止任何错误值) ==========

-- service_modules
DROP TRIGGER IF EXISTS trg_sm_domain_id_insert;
CREATE TRIGGER trg_sm_domain_id_insert
AFTER INSERT ON service_modules
FOR EACH ROW
WHEN NEW.sub_domain_id IS NOT NULL
BEGIN
    UPDATE service_modules
    SET domain_id = (SELECT sd.domain_id FROM sub_domains sd WHERE sd.id = NEW.sub_domain_id)
    WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_sm_domain_id_update;
CREATE TRIGGER trg_sm_domain_id_update
AFTER UPDATE OF sub_domain_id ON service_modules
FOR EACH ROW
WHEN NEW.sub_domain_id IS NOT NULL
BEGIN
    UPDATE service_modules
    SET domain_id = (SELECT sd.domain_id FROM sub_domains sd WHERE sd.id = NEW.sub_domain_id)
    WHERE id = NEW.id;
END;

-- business_objects
DROP TRIGGER IF EXISTS trg_bo_domain_id_insert;
CREATE TRIGGER trg_bo_domain_id_insert
AFTER INSERT ON business_objects
FOR EACH ROW
WHEN NEW.service_module_id IS NOT NULL
BEGIN
    UPDATE business_objects
    SET domain_id = (SELECT sm.domain_id FROM service_modules sm WHERE sm.id = NEW.service_module_id),
        sub_domain_id = (SELECT sm.sub_domain_id FROM service_modules sm WHERE sm.id = NEW.service_module_id)
    WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_bo_domain_id_update;
CREATE TRIGGER trg_bo_domain_id_update
AFTER UPDATE OF service_module_id ON business_objects
FOR EACH ROW
WHEN NEW.service_module_id IS NOT NULL
BEGIN
    UPDATE business_objects
    SET domain_id = (SELECT sm.domain_id FROM service_modules sm WHERE sm.id = NEW.service_module_id),
        sub_domain_id = (SELECT sm.sub_domain_id FROM service_modules sm WHERE sm.id = NEW.service_module_id)
    WHERE id = NEW.id;
END;

-- relationships source
DROP TRIGGER IF EXISTS trg_rel_src_domain_insert;
CREATE TRIGGER trg_rel_src_domain_insert
AFTER INSERT ON relationships
FOR EACH ROW
WHEN NEW.source_bo_id IS NOT NULL
BEGIN
    UPDATE relationships
    SET source_domain_id = (SELECT bo.domain_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id),
        source_sub_domain_id = (SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id),
        source_service_module_id = (SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id)
    WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_rel_src_domain_update;
CREATE TRIGGER trg_rel_src_domain_update
AFTER UPDATE OF source_bo_id ON relationships
FOR EACH ROW
WHEN NEW.source_bo_id IS NOT NULL
BEGIN
    UPDATE relationships
    SET source_domain_id = (SELECT bo.domain_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id),
        source_sub_domain_id = (SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id),
        source_service_module_id = (SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = NEW.source_bo_id)
    WHERE id = NEW.id;
END;

-- relationships target
DROP TRIGGER IF EXISTS trg_rel_tgt_domain_insert;
CREATE TRIGGER trg_rel_tgt_domain_insert
AFTER INSERT ON relationships
FOR EACH ROW
WHEN NEW.target_bo_id IS NOT NULL
BEGIN
    UPDATE relationships
    SET target_domain_id = (SELECT bo.domain_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id),
        target_sub_domain_id = (SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id),
        target_service_module_id = (SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id)
    WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS trg_rel_tgt_domain_update;
CREATE TRIGGER trg_rel_tgt_domain_update
AFTER UPDATE OF target_bo_id ON relationships
FOR EACH ROW
WHEN NEW.target_bo_id IS NOT NULL
BEGIN
    UPDATE relationships
    SET target_domain_id = (SELECT bo.domain_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id),
        target_sub_domain_id = (SELECT bo.sub_domain_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id),
        target_service_module_id = (SELECT bo.service_module_id FROM business_objects bo WHERE bo.id = NEW.target_bo_id)
    WHERE id = NEW.id;
END;
