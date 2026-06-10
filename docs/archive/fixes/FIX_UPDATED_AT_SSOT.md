# updated_at 派生规则 — SSOT 修复（2026-06-05）

> 修复用户组表查询 500 错误，统一所有 object 的 `updated_at` 计算逻辑

## 背景

### 问题
- `meta/architecture.db` 的 `user_groups` 表**缺失 `updated_at` 列**
- `meta/services/user_group_service.py` 直接 `SELECT g.updated_at` → 500 错误
- 影响所有 `/api/v1/user-groups` 调用

### 根因
`user_group_service.py` 试图**直接读写** `updated_at` 列：
```sql
SELECT g.updated_at FROM user_groups g  -- 列不存在 → 500
INSERT INTO user_groups (... updated_at) VALUES (...)
UPDATE user_groups SET updated_at = ?  -- 也会失败
```

### 设计原则（用户要求）
- `updated_at` 是**计算字段**，不应在 DB 中存储
- 所有 object 统一计算规则
- 数据源：`audit_logs` 表

## SSOT 现有实现

项目内已存在 2 处 `_enrich_audit_virtual_fields` 实现：

### 1. query_service.py
```python
def _enrich_audit_virtual_fields(self, meta_obj, records):
    """SSOT: 从 audit_logs 批量计算 virtual updated_at
    
    单一事实原则。与 persistence_interceptor._enrich_audit_virtual_fields 逻辑一致。
    
    更新时间逻辑：
    1. 只查询 UPDATE 操作的审计日志时间
    2. 如果没有 UPDATE 日志，则使用记录本身的 created_at
    """
```

### 2. persistence_interceptor.py
```python
def _enrich_audit_virtual_fields(self, meta_object, records, data_source):
    """[Virtual] 计算 virtual updated_at 从 audit_logs"""
```

> 两处实现逻辑一致但**未抽取为共享 helper**（未来应合并为 `meta/core/audit_derived_fields.py`）。

## 修复方案

### user_group_service.py 重构

#### 1. 派生 SQL（计算 updated_at）
```python
_VIRTUAL_UPDATED_AT_SQL = (
    "COALESCE("
    "(SELECT MAX(created_at) FROM audit_logs "
    "WHERE object_type='user_group' AND object_id=g.id AND action='UPDATE'), "
    "g.created_at) AS updated_at"
)
```

#### 2. SELECT 改派生
```sql
-- 修复前
SELECT g.id, g.name, ..., g.created_at, g.updated_at, ...

-- 修复后
SELECT g.id, g.name, ..., g.created_at, ..., 
    COALESCE(
        (SELECT MAX(created_at) FROM audit_logs 
         WHERE object_type='user_group' AND object_id=g.id AND action='UPDATE'),
        g.created_at
    ) AS updated_at,
    ...
```

#### 3. INSERT 移除 updated_at 列
```sql
-- 修复前
INSERT INTO user_groups (name, code, ..., created_at, updated_at)
VALUES (?, ?, ..., ?, ?)

-- 修复后
INSERT INTO user_groups (name, code, ..., created_at)
VALUES (?, ?, ..., ?)
```

#### 4. UPDATE 移除 updated_at 写入
```python
# 修复前
updates['updated_at'] = now

# 修复后
# 不再写 updated_at 列
```

#### 5. ORDER BY 修复
```python
# 修复后：updated_at 是别名，不是 g.updated_at 列
elif field == 'updated_at':
    sql = f"{base_sql} ORDER BY updated_at {direction}"
```

## 验证

### API
| 端点 | 修复前 | 修复后 |
|------|--------|--------|
| `GET /api/v1/user-groups` | **500** | **200** (3 个用户组) |
| `GET /api/v2/bo/user_group/3` | 500 (SQL 错) | 200 (含 updated_at) |

### 响应字段
```json
{
  "code": "TEST001",
  "created_at": "2026-06-04T20:21:27.632030",
  "updated_at": "2026-06-04T20:21:27.632030",  ← 派生（无 UPDATE 记录时 = created_at）
  "updated_by": "",
  "member_count": 0
}
```

### E2E
- `user-group-detail.spec.js` → 1/1 passed ✅
- `user-group-filter.spec.js` → 2 failed（页面选择器问题，与 API 无关）

## 关键设计点

### 为什么 user_groups 表**不**添加 updated_at 列？
按用户要求：
- `updated_at` 是计算字段，DB 中不应有
- 所有 object 共用同一计算规则
- 避免在多张表上重复维护 `updated_at` 字段 + 触发器
- 避免 UPDATE 操作的双写（DB + 审计）

### BO 框架如何处理其他 object？
- `products`, `business_objects`, `domains` 等已有 `updated_at` 列 → 已用 `persistence_interceptor._enrich_audit_virtual_fields` 派生
- 这些列可以保留（兼容性）或后续清理
- 未来统一方向：移除所有表的 `updated_at` 列，全部派生

### 何时 audit_logs 中才会有 UPDATE 记录？
- **BO 框架 object**：通过 `AuditInterceptor.after_action()` 自动写入（已实现）
- **非 BO 框架 object**（user_group, role）：需要 `update_group` 等 service 方法显式调用 audit 写入
  - 当前 user_group_service 未应用 `@audit_log` 装饰器（待 P3 任务）
  - 当前现状：新创建的 user_group 不会有 UPDATE 审计记录，`updated_at` 总是 = `created_at`

## 后续任务

### P3: 应用 @audit_log 装饰器 ✅ 完成
- `user_group_service.create_group` / `update_group` / `delete_group` 全部已装饰
- 同步增强了 `audit_interceptor`：
  - 支持位置参数 `args[0]` 作为 `object_id`（兼容 `update_group(self, group_id, ...)`）
  - `request` 访问容错（service 上下文外仍可运行）
- 验证：PUT → audit_logs 自动写入 (id=727, action=UPDATE) → /api/v1/user-groups updated_at 派生

### P3: 抽取 SSOT 共享 helper ✅ 完成
- 创建 `meta/core/audit_derived_fields.py`（约 180 行）
- `query_service._enrich_audit_virtual_fields` 委托给 helper
- `persistence_interceptor._enrich_audit_virtual_fields` 委托给 helper
- 统一签名：`enrich_audit_virtual_fields(ds, object_type, records, field_ids=None)`

### P4: 清理其他表的 updated_at 列
- products, business_objects, domains 等
- 移除 `updated_at` 列
- 依赖 BO 框架的 `_enrich_audit_virtual_fields` 派生
- 需要 migration 脚本

## 影响面

### 受影响文件
- ✅ `meta/services/user_group_service.py`（已修复）
- ⏳ `meta/services/role_service.py`（如存在同样问题，待查）
- ⏳ 其他 service（如有类似模式）

### 不受影响
- BO 框架 object 走 `persistence_interceptor`，已有派生逻辑
- 16 张已存在的 `updated_at` 列的表（products, business_objects 等），由 BO 框架统一处理

## 测试覆盖

### 后端单元测试
- `test_user_group_service.py`（如存在）— 需验证 `updated_at` 字段返回
- 新增测试：派生规则验证（无 UPDATE 时 = created_at，有 UPDATE 时 = MAX(audit_logs.created_at)）

### E2E
- `user-group-detail.spec.js` → 1/1 passed（updated_at 字段返回）
- `user-group-filter.spec.js` → 2 failed（页面选择器问题，需单独修复）
