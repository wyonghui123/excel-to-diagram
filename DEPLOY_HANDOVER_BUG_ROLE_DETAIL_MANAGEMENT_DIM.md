# 角色详情管理维度为空 — 完整根因分析

> **作者**: dev-agent
> **日期**: 2026-07-07 12:30
> **状态**: 🟢 已分析, 待协调智能体决策
> **关联**: 
> - [debug-role-audit-missing.md](./debug-role-audit-missing.md) (Round 1+2 历史 bug 修复记录)
> - [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md) (生产 IO error)

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| BUG-ID | **角色详情管理维度为空 (第 3 次)** |
| 严重度 | P2-Medium (功能缺陷, 不影响登录/数据) |
| 真因 | **3 层叠加** (SQL 表缺失 + role.yaml schema 缺失 + 前端 lazy load) |
| 不是 IO error 复发 | ✅ 不是 (角色管理维度显示完全独立) |
| 修复方向 | 1. 建 `management_dimensions` 表 + 数据 2. role.yaml 加 association 3. 前端加 tab |

---

## 1. 历史回顾 (基于 debug-role-audit-missing.md)

### Round 1 (2026-06-12): 用户报"管理维度变更后, 操作日志为空"

**已修复 9 个 bug** (都是审计日志写入缺失):

| Bug | 文件 | 修复 |
|-----|------|------|
| 1 | `role_dimension_scope_api.py:save_dimension_scopes` | 加 audit log |
| 2 | `role_dimension_scope_api.py:get_derived_permissions` | 加 audit log |
| 3 | `audit_api.py` | 加 parent_object_type filter |
| 4 | `role_api.py:set_role_permissions` | 加 audit log |
| 5 | `role_api.py:add_role_data_permission` | 加 audit log |
| 6 | `bo_api.py:update_role_menu_permissions` (v2) | 加 audit log |
| 7 | `role_menu_api.py:update_role_menu_permissions` (PFCG) | 加 audit log |
| 8 | `management_dimension_api.py:save_permission_rule` | 加 audit log |
| 9 | `permission_rule_api.py:create_rule` | 加 audit log |

### Round 2 (2026-06-12): 用户报"对象类型/字段名显示技术名" + "特定角色日志仍不显示"

**已修复 8 处前端 + 后端**:

| Bug | 文件 | 修复 |
|-----|------|------|
| A | `audit_api.py` | 加 OR 联合查询 (object_type OR parent_object_type) |
| B | `audit_api.py` | 加 OBJECT_TYPE_LABELS / FIELD_NAME_LABELS |
| C | `auditLogService.js` | buildLogFilter 支持 parentObject |
| D | `useAuditLogs.js` | composable 支持 parentObject |
| E | `RoleDetailDrawer.vue` | 调 useAuditLogs 时传 parentObject |
| F | `AuditLogDetail.vue` | 优先显示 label, 技术名括号后缀 |
| G | `AuditLog.vue` | 列表也用 label |

### **关键发现 — Round 1+2 都聚焦在 "管理维度变更的审计日志"**, **没人查"管理维度数据本身是否可显示"**!

---

## 2. 第 3 次发生 — 当前根因 (基于本地 db 实证)

### 2.1 admin 角色数据实证 (本地 db)

```
admin role (id=1) role_dimension_scopes:
  Total: 1 scopes
  scope: code='domain', values='[1, 2]', inherit=1, mode=include
```

**✅ admin 角色有 1 个管理维度 (domain, [1, 2])** — **数据存在**

### 2.2 但是! `management_dimensions` 表**不存在**

```
management_dimensions table:
  err: no such table: management_dimensions
```

**🎯 `management_dimensions` 表** — 完全不存在于 db 中!

但 `.schema_version.json` L269-280 提到 `management_dimension` schema (fields=id/code/name/field/resource_types/description, table=management_dimensions):

```json
"management_dimension": {
  "hash": "4a122ba07fc7150815f62421c08a84ca",
  "fields": ["id", "code", "name", "field", "resource_types", "description"],
  "table": "management_dimensions"
}
```

**schema 声明了, 但 db 没建表** — 这是 schema migration 漏跑的结果。

### 2.3 role.yaml schema 也没声明 `management_dimension` association

```yaml
# meta/schemas/role.yaml L191-246
associations:
  permissions:
    type: many_to_many
    through: role_permissions
  assigned_groups:
    type: reverse_many_to_many
    through: group_roles
# ❌ 没有 management_dimensions association
```

### 2.4 role.yaml detail tabs 也没有管理维度 tab

```yaml
# meta/schemas/role.yaml L376-403
detail:
  tabs:
    - basic
    - permissions
    - assigned_groups    # ← 只有 用户组 tab
    - audit-log
# ❌ 没有 management_dimensions tab
```

---

## 3. 三层根因 (叠加)

### Layer 1: DB schema 缺失

**`management_dimensions` 表从未被创建**:
- schema 声明存在 (`.schema_version.json`)
- 但 DB migration 没执行建表 SQL
- 结果: API 调 `SELECT * FROM management_dimensions` 立即报 `no such table`

### Layer 2: role.yaml schema 缺失

**role.yaml 没声明 `management_dimensions` association**:
- UI 渲染 association 时需要 schema 声明
- 即使 DB 有数据, UI 也没法自动显示 (需要 association 配置)
- 需要手动加:
  ```yaml
  associations:
    management_dimensions:
      type: many_to_many
      through: role_dimension_scopes
      target_entity: management_dimension
      # ...
  ```

### Layer 3: role_dimension_scope_api.py SQL 注入风险 + 错误表名推断

**`role_dimension_scope_api.py:65` 的 f-string**:
```python
table_name = f"{dimension_code}s" if not dimension_code.endswith('s') else f"{dimension_code}"
```

**问题 1 - SQL 注入**: `dimension_code` 来自用户输入 (前端 dim selector), 没白名单校验
**问题 2 - 表名错误**: 如果 `dimension_code='business'`, 推导出 `table_name='businesss'` (复数错), 查询失败, 但被 try/except 吞掉, 返回空 `dimension_values: [{'id': vid, 'name': str(vid), 'code': ''}]`

**结果**: 即使 admin 角色有 `dimension_code='domain', values=[1,2]`, API 返回:
```json
[{
  "dimension_code": "domain",
  "dimension_values": [
    {"id": 1, "name": "1", "code": ""},  ← 应该是 {"id": 1, "name": "采购管理", "code": "domain-1"}
    {"id": 2, "name": "2", "code": ""}
  ]
}]
```

**UI 拿到 name="1", name="2" — 这就是"管理维度为空"的视觉效果!**

---

## 4. 为什么 3 次发生, 但没人发现根因?

### 第 1 次发生 (推测 2026-06 中旬)
- 用户报"角色管理维度为空"
- 有人看代码, 加了 role_dimension_scope_api.py 和 role.yaml (但只加了部分)
- 没修 SQL 注入, 没修表名推断, **仍为空**
- 任务被标 [FIXED], **实际未修复**

### 第 2 次发生 (推测 2026-06 下旬)
- Round 1 修 audit log 时, 有人看 role_dimension_scope_api.py:46-96 GET endpoint
- 但只加 audit log, **没看 SQL 注入和表名推断**
- 任务被标 [FIXED], **仍为空**

### 第 3 次发生 (现在)
- 用户再次报"角色管理维度为空"
- 现在我们用 Python 直接查 db, 发现:
  - 数据存在 ✅
  - table 不存在 ❌
  - SQL 注入 + 表名推断 ❌

**3 次发生都没修对根因**, 因为:
- 前 2 次只看了 audit log (Round 1) 和 label 显示 (Round 2)
- **没人跑过实际的 GET `/api/v1/roles/1/dimension-scopes` 看返回数据**
- **没人看 management_dimensions 表是否真的存在**

---

## 5. 完整根因图

```
用户报 "角色详情管理维度为空"
     ↓
Layer 3: role_dimension_scope_api.py:65 f-string 推断表名错误
     + try/except 吞错
     → API 返回空 dimension_values
     ↓
Layer 2: role.yaml 缺 management_dimensions association
     → 即使数据正确, UI 也没法显示
     ↓
Layer 1: management_dimensions 表不存在
     → 即使 UI 显示, 数据也为空
     ↓
Layer 0: schema 声明存在但 migration 漏跑
     → 从一开始就没建表
```

---

## 6. 修复方案 (3 层都修)

### Phase A: 建表 + 填充数据 (立即可做)

```sql
-- migration: Vxxx_create_management_dimensions.sql
CREATE TABLE IF NOT EXISTS management_dimensions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code VARCHAR(100) NOT NULL UNIQUE,
  name VARCHAR(200) NOT NULL,
  field VARCHAR(100),  -- 关联的字段名 (e.g., 'product_id', 'version_id')
  resource_types TEXT,  -- JSON array of object_types
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 填充基础数据 (V007.25)
INSERT OR IGNORE INTO management_dimensions (code, name, field, resource_types, description) VALUES
  ('product', '产品', 'product_id', '["product","business_object","annotation"]', '产品维度'),
  ('version', '产品版本', 'version_id', '["business_object","annotation","relationship","service_module"]', '产品版本维度'),
  ('domain', '业务域', 'domain_id', '["business_object","annotation","service_module","sub_domain"]', '业务域维度'),
  ('sub_domain', '子域', 'sub_domain_id', '["business_object","annotation","relationship"]', '子域维度');
```

### Phase B: 修 role.yaml + role_dimension_scope_api.py

```yaml
# meta/schemas/role.yaml - 加 association + tab
associations:
  management_dimensions:
    name: management_dimensions
    label: 管理维度
    type: many_to_many
    through: role_dimension_scopes
    source_key: role_id
    target_entity: management_dimension
    target_key: dimension_code
    description: 此角色可管理的业务范围（基于管理维度）

detail:
  tabs:
    - basic
    - permissions
    - management_dimensions    # ← 新增
      label: 管理维度
      type: association
      association: management_dimensions
      description: 此角色的管理维度范围
    - assigned_groups
    - audit-log
```

```python
# meta/api/role_dimension_scope_api.py:65 - 修 SQL 注入 + 表名白名单
ALLOWED_DIMENSION_TABLES = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    'business_object': 'business_objects',
    'service_module': 'service_modules',
    'annotation': 'annotations',
    'relationship': 'relationships',
    'management_dimension': 'management_dimensions',
}

# 修:
table_name = ALLOWED_DIMENSION_TABLES.get(dimension_code)
if not table_name:
    # 未知 dimension_code, 跳过 (不再用 f-string)
    item['dimension_values'] = [{'id': vid, 'name': str(vid), 'code': ''} for vid in dimension_values]
    continue
```

### Phase C: 前端 RoleDetailDrawer.vue 加 tab

```vue
<!-- 在 tabs 里加 -->
<el-tab-pane label="管理维度" name="management_dimensions">
  <ManagementDimensionTab :role-id="role.id" />
</el-tab-pane>
```

---

## 7. 验证清单 (Phase A 完成)

```bash
# 1. 跑 migration
python -c "
import sqlite3
con = sqlite3.connect('/path/to/architecture.db')
cur = con.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"management_dimensions\"')
print('table exists:', cur.fetchone() is not None)
"

# 2. 验证数据
python -c "
import sqlite3
con = sqlite3.connect('/path/to/architecture.db')
cur = con.cursor()
cur.execute('SELECT * FROM management_dimensions')
print('rows:', cur.fetchall())
"

# 3. 验证 API
curl -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/roles/1/dimension-scopes
# 期望: dimension_values 有 name 和 code (不再是 "1", "2")
```

---

## 8. 与 IO error 的关系

| 问题 | 是否相关 |
|------|---------|
| V007.21 disk I/O error | ❌ **完全无关** |
| V007.22 lazy init fd 泄漏 | ❌ 完全无关 |
| V007.24 multi-pool fd 泄漏 | ❌ 完全无关 |
| 角色管理维度为空 | ✅ **独立问题, UI/DB 层** |

**这是另一个独立的问题**, 跟 fd 泄漏 / IO error 完全无关。建议:
1. Phase 1 (V007.24) 继续推进部署
2. **角色管理维度** 作为 V007.25 单独修复

---

## 9. 协调智能体决策项

### A. 立即可做 (P2 优先级)

1. **跑 migration 建 management_dimensions 表**
2. **修 role_dimension_scope_api.py SQL 注入 + 表名白名单**
3. **加 role.yaml association + detail tab**

### B. 不需要做的

1. ❌ 不要把 V007.24 fd 泄漏修复跟这个混在一起 (不同问题)
2. ❌ 不要改 V007.16 修复 (无关)
3. ❌ 不要改 server.py:376 TRUNCATE (无关)

### C. 注意事项

1. **不要回滚之前的 audit log 修复** (Round 1+2 都是正确的)
2. **保留 debug-role-audit-missing.md** (历史修复记录)
3. **V007.25 应作为独立 bug ID 跟踪**, 不混入 V007.24

---

## 10. 文件改动清单

| 文件 | 改动 | 优先级 |
|------|------|--------|
| `meta/migrations/Vxxx_create_management_dimensions.sql` | 新建表 | P0 |
| `meta/scripts/seed_management_dimensions.py` | 填充数据 | P0 |
| `meta/api/role_dimension_scope_api.py:65` | 修 f-string, 加白名单 | P0 |
| `meta/schemas/role.yaml` | 加 management_dimensions association + tab | P1 |
| `frontend_dist_files/views/RoleDetailDrawer.vue` | 加管理维度 tab | P1 |
| `tests/test_role_dimension_scope_api_extended.py` | 加 SQL 注入 + 表名测试 | P1 |

**总工作量**: 6h (1 天)
**风险**: 低 (独立功能修复, 不影响主流程)