# DATA_PERMISSION_INHERITANCE.md

> **Data Permission 继承规则文档**
> 版本: v1.0
> 创建: 2026-06-14
> BMRD DEFER ID: DATA-PERM-INHERIT

## 1. 概述

Data Permission (数据权限) 在三层实体间继承:
- **Role** (角色)
- **Group** (用户组)
- **Employee/User** (员工/用户)

继承规则: **子继承父** + **更高权限优先**。

## 2. 实体层级 (HIERARCHY_ORDER)

```python
HIERARCHY_ORDER = ['company', 'sub_company', 'department', 'sub_department', 'employee']
```

| 层级 | 索引 | 说明 |
|------|------|------|
| `company` | 0 | 顶级公司 |
| `sub_company` | 1 | 子公司 |
| `department` | 2 | 部门 |
| `sub_department` | 3 | 子部门 |
| `employee` | 4 | 员工/个人 |

## 3. 权限级别 (Permission Level)

| 级别 | 数值 | 说明 |
|------|------|------|
| `read` | 1 | 只读 |
| `write` | 2 | 读写 |
| `admin` | 3 | 完全控制 |

**数值越大权限越高**。多个父继承时取**最大权限**。

## 4. 继承流程

### 4.1 顺序
```
1. 查询用户直接授权 (employee 级)
2. 查询 group 继承授权
3. 查询 role 继承授权
4. 查询 parent_visibility 继承授权
```

### 4.2 关键代码 (`data_permission_service.py:409`)
```python
def _get_inherited_permission_level(self, user_id, resource_type, resource_id):
    level_idx = self._get_level_index(resource_type)
    if level_idx <= 0:
        return None

    parent_types = self.HIERARCHY_ORDER[:level_idx]  # 所有父层级
    best_level = None
    level_order = {'read': 1, 'write': 2, 'admin': 3}

    for parent_type in parent_types:
        parent_id = self._find_parent_id(resource_type, resource_id, parent_type)
        if parent_id is None:
            continue
        # 查询父级的权限
        row = ... (SELECT permission_level FROM data_permissions WHERE ...)
        if row and row[1]:  # inherit_to_children = True
            perm_level = row[0]
            if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                best_level = perm_level  # 取最大

    return best_level
```

### 4.3 inherit_to_children 标志
- 数据库列: `inherit_to_children` (BOOLEAN, 1/0)
- 默认 1 (true) - 子实体自动继承
- 可设为 0 (false) - 不继承, 仅当前实体

## 5. Role → Group → Employee 继承

### 5.1 Role 优先级
- 表 `roles.priority` (INTEGER)
- 默认 0, 可设置 0-100
- **数值越大优先级越高**

### 5.2 用户的最大 Role 优先级
```sql
SELECT MAX(r.priority) FROM roles r
INNER JOIN group_roles gr ON r.id = gr.role_id
INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
WHERE ugm.user_id = ?
```

### 5.3 权限分配规则
- 用户的有效权限 = max(直接授权, group 继承, role 继承)
- 例: 用户有 role A (priority 50) + role B (priority 80) → 有效 role = B
- 例: 用户是 group_X 成员, group_X 有 role A (priority 50) → 用户有 role A

## 6. 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/bo/role_data_permission` | GET | 列出 role 数据权限 |
| `/api/v2/bo/role_data_permission` | POST | 创建 role 数据权限 |
| `/api/v2/bo/group_data_permission` | GET | 列出 group 数据权限 |
| `/api/v2/bo/employee_data_scope` | GET | 列出 employee 数据范围 |

## 7. 数据库 Schema

### 7.1 data_permissions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 主键 |
| `user_id` | int | 授权给的 user |
| `resource_type` | str | 资源类型 (company/department/...) |
| `resource_id` | int | 资源 ID |
| `permission_level` | str | read/write/admin |
| `inherit_to_children` | bool | 是否继承给子实体 |
| `created_at` | timestamp | 创建时间 |

## 8. 示例场景

### 场景 1: 用户读部门 A 的所有数据
```
1. 给 role "部门经理" 添加数据权限:
   resource_type = "department", resource_id = 10 (部门A)
   permission_level = "read"
   inherit_to_children = true
2. 用户属于 role "部门经理"
3. 用户可读 部门A 及其所有子部门的资源
```

### 场景 2: 用户的写权限只限本部门
```
1. 给 user 添加数据权限:
   resource_type = "department", resource_id = 10 (本部门)
   permission_level = "write"
   inherit_to_children = false  ← 关键: 不继承子部门
2. 用户可写本部门, 但不能写子部门
```

### 场景 3: 多个 role 冲突
```
1. user 有 role A (priority 30) 读权限
2. user 有 role B (priority 80) 写权限
3. 有效权限 = max(read, write) = write
```

## 9. BMRD 规则

| 规则 ID | 状态 | 说明 |
|---------|------|------|
| DATA-PERM-DIM-1 | ACTIVE | role_data_permission 列表 |
| DATA-PERM-DIM-2 | ACTIVE | employee_data_scope 列表 |
| DATA-PERM-DIM-3 | ACTIVE | group_data_permission 列表 |
| DATA-PERM-DIM-4 | ACTIVE | data_scope 多端点 |
| DATA-PERM-INHERIT | 🟡 DEFER (文档化完成) | 等后端继承规则上线后改 ACTIVE |

## 10. 测试覆盖

- `meta/tests/test_data_permission_service.py` - 核心服务
- `meta/tests/test_data_permission_generator.py` - 生成器
- `meta/tests/test_role_data_permission.py` - role 端点
- `meta/tests/test_group_data_permission.py` - group 端点

## 11. 已知限制

| 限制 | 原因 | 解决方案 |
|------|------|----------|
| 跨域继承未文档化 | 业务侧兜底 | P2: 添加跨域继承规则 |
| 权限审计不完整 | 设计中 | P2: 完整审计 trail |
| 性能优化中 | 多 role 查询慢 | P2: 缓存机制 |

## 12. 解锁条件

DATA-PERM-INHERIT DEFER → ACTIVE:
- [ ] 文档化完成 ✅
- [ ] 关键代码确认 ✅ (`_get_inherited_permission_level`)
- [ ] 端点确认 ✅ (role/group/employee 端点 200)
- [ ] BMRD 规则引用 ✅
- [ ] 完整测试覆盖 ✅
- [ ] 解锁: 改 `_data_permission_dimension_rules.yaml` 中 `DATA-PERM-INHERIT` 为 ACTIVE

## 13. 参考

- 后端核心: `meta/services/data_permission_service.py`
- 角色继承: `meta/services/role_data_permission_api.py`
- 维度集成: `meta/services/dimension_scope_engine.py`
- BMRD 规则: `.trae/specs/_business_rules/_data_permission_dimension_rules.yaml`
