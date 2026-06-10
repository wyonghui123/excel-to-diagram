# SSOT v1.4 阶段 1 — audit_logs epoch 性能优化（2026-06-05）

> v1.4 SSOT P5：执行项目原计划的阶段 1 migration，添加 `created_at_epoch` 列 + 复合索引

## 背景

v1.4 SSOT helper（`meta/core/audit_derived_fields.py`）当前用 `MAX(created_at)` (TEXT) 聚合，性能不佳。

项目内**已存在**的 `meta/database/migration_ssot_updated_at.sql` 计划分两阶段：
- **阶段 1**（本次执行）：添加 `audit_logs.created_at_epoch` (BIGINT) + 复合索引
- **阶段 2**（P4 部分完成）：移除业务表 `updated_at` 物理列

阶段 2 之前**没有**执行 — 因为如果阶段 1 没执行，SSOT helper 的 epoch 路径会失败，触发 fallback。P5 阶段 1 让 helper 真正使用高性能 epoch 路径。

## 执行内容

### 1. 添加 `created_at_epoch` 列（BIGINT）
```sql
ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT;
```

### 2. Backfill 现有数据（89 行）
```sql
UPDATE audit_logs
SET created_at_epoch = (strftime('%s', created_at) * 1000)
WHERE created_at_epoch IS NULL AND created_at IS NOT NULL;
```

### 3. 复合索引（覆盖 SSOT 查询模式）
```sql
CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated
ON audit_logs(object_type, object_id, action, created_at_epoch DESC);
```

## SSOT Helper 行为

`audit_derived_fields.py` 的查询策略：

```python
# 优先使用 epoch（高性能）
SELECT object_id, MAX(created_at_epoch), MAX(created_at)
FROM audit_logs
WHERE object_type = ? AND object_id IN (...) AND action = 'UPDATE'
GROUP BY object_id

# Fallback（audit_logs 缺 epoch 列时）
SELECT object_id, NULL, MAX(created_at)
FROM audit_logs
...
```

阶段 1 执行后，**默认走 epoch 路径**。如果以后遇到缺 epoch 的环境，自动 fallback。

## 验证

### 阶段 1 migration 输出
- ✓ Added created_at_epoch column
- ✓ Backfilled 89 rows
- ✓ Created idx_audit_ssot_updated index

### API 验证
| 端点 | 结果 | updated_at 派生 |
|------|------|------------------|
| /api/v2/bo/user_group/3 | 200 | `2026-06-05T19:40:10` (epoch 路径) |
| /api/v2/bo/product | 200 | epoch 派生 |
| /api/v1/user-groups | 200 | SQL 内联 COALESCE (不依赖 epoch) |
| /api/v1/roles/1/intents | 200 | role_intents 独立表（未迁移） |

### E2E 回归
- business-object-crud: 1/1 ✅
- product-crud: 2/2 ✅
- user-group-detail: 1/1 ✅
- role-permission-center: 2/2 ✅
- overlap-warning: 1/1 ✅
- user-permission: 3/3 ✅

**总计 10/10 passed**

## 关键文件

| 文件 | 改动 |
|------|------|
| `meta/scripts/migration_ssot_stage1.py` | 新建（阶段 1 migration 脚本） |
| `meta/core/audit_derived_fields.py` | 无改动（已支持 epoch，fallback 兼容） |
| `meta/database/migration_ssot_updated_at.sql` | 已存在（项目原计划），现可部分执行 |

## 备份

- `d:\filework\excel-to-diagram\meta\architecture.db.bak.stage1.20260605_123530`
- 回滚：直接 cp 覆盖

## 性能提升（预期）

### 阶段 1 前
```sql
SELECT MAX(created_at) FROM audit_logs WHERE ...
-- TEXT 比较，按字符串排序 '2026-06-05' vs '2026-06-04'
-- 需要 strftime 转换才能得到 ISO 时间
```

### 阶段 1 后
```sql
SELECT MAX(created_at_epoch) FROM audit_logs WHERE ...
-- BIGINT 比较，单条指令即可
-- 复合索引 (object_type, object_id, action, created_at_epoch DESC) 直接覆盖
```

**预期性能**：派生查询从 O(n) 全表扫描 → O(log n) 索引扫描。

## SSOT P5 总结

### 已完成
- ✅ **P3**：SSOT 共享 helper 抽取 + query_service / persistence_interceptor 委托
- ✅ **P3**：user_group_service 改用 SQL 内联派生 + @audit_log 装饰器
- ✅ **P4**：移除 7 张 BO 框架表的物理 `updated_at` 列
- ✅ **P4**：role_intents 单独恢复 `updated_at` 列
- ✅ **P5**：执行阶段 1 migration（`created_at_epoch` + 索引）
- ✅ **P5**：E2E 10/10 回归通过

### 关键认识
1. **元数据驱动原则 vs 业务服务**：
   - `user_group` / `role` / `user` / `permission` **已经**走 BO 框架
   - `user_group_service` 的主表 CRUD 方法是**冗余**的（v2/bo 端点覆盖）
   - `user_group_service` 的**业务关系方法**（成员/角色/委托/迁移）**应该保留**
   - 这是合理的领域服务分层

2. **SSOT 列设计**：
   - BO 框架表（products/business_objects/...）：**移除**物理 updated_at，依赖派生
   - 任务/调度/权限类：**保留** updated_at（业务状态时间戳）
   - 专用 DAO 表（role_intents）：**保留** updated_at（直接 SQL 写入）

3. **阶段 1 性能优化**：
   - `created_at_epoch` + 复合索引
   - SSOT helper 优先 epoch 路径
   - 自动 fallback 兼容旧环境

### 备份状态
- `architecture.db.bak.20260605_120456` (P4)
- `architecture.db.bak.stage1.20260605_123530` (P5 阶段 1)

## 未来 P6 任务（可选）

1. **统一 user_group_service 主表 CRUD**：
   - 标记 `create_group` / `update_group` / `delete_group` 为 deprecated
   - 前端迁移到 v2/bo/user_group 端点
   - 移除冗余方法

2. **执行项目原计划阶段 2 余下表**：
   - versions, task_executions 等
   - 视具体业务需求决定

3. **性能基准测试**：
   - 对比 epoch vs TEXT 路径的 query time
   - 验证索引有效使用

4. **前端 updated_at 显示优化**：
   - 基于派生的语义
   - "从未更新过" vs "刚刚更新"
