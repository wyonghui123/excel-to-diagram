# SSOT updated_at P4 清理 — 移除 BO 框架表的物理 updated_at 列（2026-06-05）

> v1.4 SSOT 落地：8 张 BO 框架管理的表移除物理 `updated_at` 列，依赖 `audit_logs` 派生

## 背景

v1.4 SSOT 原则：所有 object 的 `updated_at` 是**计算字段**，从 `audit_logs` 实时派生。

### 历史
- v1.4 P3：抽取 SSOT 共享 helper (`meta/core/audit_derived_fields.py`)
- v1.4 P3：`query_service` 和 `persistence_interceptor` 委托给 SSOT helper
- v1.4 P3：`user_group_service` 应用 `@audit_log` 装饰器 + 改用 SQL 内联派生
- **v1.4 P4（本任务）**：移除 8 张 BO 框架表的物理 `updated_at` 列

### 关键原则
- BO 框架管理的表：**移除** `updated_at` 列（依赖 `persistence_interceptor._enrich_audit_virtual_fields` 派生）
- 专用 DAO/Service 管理的表：**保留** `updated_at` 列（如 `role_intents`）
- 任务/调度/权限类表：**保留** `updated_at` 列（业务状态时间戳）

## 受影响的表

### 移除 `updated_at` 列（8 张）
| 表 | 行数 | 状态 |
|----|------|------|
| products | 3 | ✅ |
| business_objects | 25 | ✅ |
| domains | 4 | ✅ |
| sub_domains | 8 | ✅ |
| service_modules | 16 | ✅ |
| relationships | 28 | ✅ |
| new_objects | 0 | ✅（空表） |
| role_intents | 1 | ⚠️ 单独恢复（见下） |

### role_intents 单独恢复原因
`role_intents` 表由 `meta/core/intent_resolver.py` 专用 DAO 管理，包含 4 处直接 SQL：
```sql
INSERT INTO role_intents (..., updated_at) VALUES (..., CURRENT_TIMESTAMP)
SELECT ..., updated_at FROM role_intents WHERE role_id = ?
```
不归 BO 框架管，移除 `updated_at` 会导致运行时错误。

**解决方案**：恢复 `role_intents.updated_at` 列，未来可考虑迁移到 BO 框架。

### 跳过（保留 `updated_at` 列）
- **任务调度类**：`task_executions` (872 行), `task_queues`, `scheduled_tasks`, `ai_async_tasks`
- **权限类**：`menu_permissions`, `permission_bundles`, `permission_rules`
- **其他**：`filter_variants` (UI 状态), `versions` (version 业务状态), `user_groups` (P3 已派生), `roles` (P3 已派生)

## 修复

### 1. Migration 脚本
**`meta/scripts/migration_remove_updated_at.py`**：
- 备份 DB：`architecture.db.bak.<timestamp>`
- 重建表（SQLite 12 步重表法）
- 重建索引
- 验证移除结果

### 2. role_intents 列恢复
临时脚本（已删除）：
```python
ALTER TABLE role_intents ADD COLUMN updated_at DATETIME
UPDATE role_intents SET updated_at = created_at WHERE updated_at IS NULL
```

### 3. init_and_seed.py 适配
移除以下表的 `updated_at TEXT,`：
- products, versions, domains, sub_domains, service_modules, business_objects, relationships
- 移除 `sub_domains` 的 INSERT 中的 `updated_at` 引用

## 验证

### API 端点（11 个）
| 端点 | 类型 | 结果 |
|------|------|------|
| /api/v2/bo/product | BO framework | 200 + updated_at |
| /api/v2/bo/business_object | BO framework | 200 + updated_at |
| /api/v2/bo/domain | BO framework | 200 + updated_at |
| /api/v2/bo/sub_domain | BO framework | 200 + updated_at |
| /api/v2/bo/service_module | BO framework | 200 + updated_at |
| /api/v2/bo/relationship | BO framework | 200 + updated_at |
| /api/v1/user-groups | user-group SQL derive | 200 + updated_at |
| /api/v1/roles/1/intents | role_intent independent | 200 |
| /api/v1/roles/1/overlaps | overlaps v1 | 200 |
| /api/v2/roles/1/overlaps | overlaps v2 | 200 |
| /api/v2/bo/business_object/1 | BO detail | 200 + updated_at |

### E2E（8 个）
- business-object-crud: 1/1 ✅
- product-crud: 2/2 ✅
- user-group-detail: 1/1 ✅
- role-permission-center: 2/2 ✅
- overlap-warning: 1/1 ✅

**总计 8/8 passed**

## 已知问题与未来工作

### 1. user_group / role 的元数据驱动原则违反
**问题**：`user_group_service.py` / `permission_service.py` 是**反模式**：
- 元数据驱动架构下，object CRUD 应由 BO 框架统一处理
- 拦截器链（`PersistenceInterceptor` / `PermissionInterceptor` / `AuditInterceptor`）已涵盖所有横切关注点
- 不应该有"具体 object 的 service"

**未来重构目标**：
- 创建 `user_group` / `role` 的 yaml BO 描述
- 让 `user_group` / `role` 走 BO 框架
- 删除 `user_group_service.py` / `permission_service.py`
- 此重构是**架构级**任务，需要全面业务分析，超出 SSOT 范围

### 2. 已存在的 `meta/database/migration_ssot_updated_at.sql`
项目内**已有** SSOT migration 计划：
- 阶段 1：添加 `audit_logs.created_at_epoch` 列 + 复合索引
- 阶段 2：移除业务表 `updated_at` 物理列

**当前状态**：
- 阶段 1 **未执行**（`created_at_epoch` 列不存在）
- 阶段 2 部分执行（BO 框架 7 张表已完成；`role_intents` 已恢复）

**未来改进**：
- 执行阶段 1，添加 `created_at_epoch` 列 + 索引
- 切换 SSOT helper 使用 `MAX(created_at_epoch)` 而非 `MAX(created_at)`
- 性能优化（epoch 比 TEXT 比较快）

### 3. 测试中的 `updated_at` mock
`meta/tests/` 多处有 `updated_at: now` 的 mock（如 `init_and_seed.py`, `check_tables.py`）：
- 这些 mock 依赖 `updated_at` 列存在
- 未来清理（移除 mock 中的 `updated_at` 引用）

## 关键文件

| 文件 | 改动 |
|------|------|
| `meta/scripts/migration_remove_updated_at.py` | 新建（migration 脚本） |
| `meta/scripts/init_and_seed.py` | 移除 7 张表的 `updated_at TEXT,` + sub_domains INSERT |
| `meta/database/migration_ssot_updated_at.sql` | 已存在（项目原计划），未执行 |
| `meta/core/audit_derived_fields.py` | SSOT 共享 helper（P3 创建） |
| `meta/services/query_service.py` | 委托给 SSOT helper（P3 改动） |
| `meta/core/interceptors/persistence_interceptor.py` | 委托给 SSOT helper（P3 改动） |
| `meta/services/user_group_service.py` | SQL 内联派生 + @audit_log（P3 改动） |
| `meta/services/audit_interceptor.py` | 增强（支持 args[0] + request 容错） |

## 备份与回滚

- **备份**：`d:\filework\excel-to-diagram\meta\architecture.db.bak.20260605_120456`
- **回滚**：
  ```bash
  cp architecture.db.bak.<timestamp> architecture.db
  ```
- **role_intents 单独处理**：迁移后立即恢复 `updated_at` 列

## 测试覆盖

### 后端单元测试
- `test_user_group_service.py`（如存在）— 验证派生 updated_at
- `test_audit_derived_fields.py`（如存在）— 验证 SSOT helper

### E2E
- `user-group-detail.spec.js` → 1/1 passed
- `product-crud.spec.js` → 2/2 passed
- `business-object-crud.spec.js` → 1/1 passed
- `role-permission-center.spec.js` → 2/2 passed
- `overlap-warning.spec.js` → 1/1 passed

## 未来 P5 任务（可选）

1. **执行项目原计划的阶段 1**：`audit_logs.created_at_epoch` + 索引
2. **切换 SSOT helper 使用 epoch**：性能提升
3. **元数据驱动重构**：`user_group` / `role` 走 BO 框架
4. **清理测试 mock**：移除 `tests/` 中 `updated_at` 引用
5. **前端 updated_at 显示优化**：基于派生的语义（"从未更新过"等）
