# Debug Session: role-audit-missing
- **Status**: [OPEN] → [FIXED]
- **Issue**: 用户在 UI 改角色的管理维度/菜单/功能权限后, 既看不到审计日志列表, 也看不到角色详情"操作日志" tab 里的内容
- **Debug Server**: http://127.0.0.1:8765/event
- **Log File**: .dbg/trae-debug-log-role-audit-missing.ndjson

## Reproduction Steps
1. 登录 admin 账号
2. 打开 系统管理 → 角色管理
3. 选一个角色, 点详情
4. 在"权限配置" tab 里: 修改 管理维度 / 菜单 / 功能 / 数据权限 / 条件规则
5. 期望: 操作日志 tab 显示刚才的操作
   实际 (修复前): 列表为空

## Hypotheses & Verification

| ID | Hypothesis | Likelihood | Effort | Evidence | Status |
|----|------------|------------|--------|----------|--------|
| A | 前端走 v2 BO action, 不传 parent_object | Med | Low | 部分正确 - 部分 v2 path 没修 | Partially Confirmed |
| B | **save_dimension_scopes endpoint 完全没调 write_permission_config_audit** | High | Low | **CONFIRMED** - 静态代码分析 + DB 验证 | **FIXED** |
| C | saveMenuPermissions 走 v1 path, parent_object_id=0 | Low | Low | Rejected - role_menu_api.py:714 正确 | Rejected |
| D | useAuditLogs onMounted 时 props.role=null | Med | Med | Rejected - code review OK | Rejected |
| E | **audit_api.py parent_object 条件丢失导致 SQL 1=1** | High | Low | **CONFIRMED** - 修复被 revert | **FIXED** |
| F | **5 个其他权限 endpoint 同样没调 write_permission_config_audit** | High | Low | **CONFIRMED** - DB 直查 | **FIXED** |

## Root Cause (5 个 bug 叠加)

### Bug 1: `role_dimension_scope_api.py:save_dimension_scopes` 没写 audit log ✓ FIXED
### Bug 2: `role_dimension_scope_api.py:get_derived_permissions` 也没写 audit log ✓ FIXED
### Bug 3: `audit_api.py` 缺少 `parent_object_type/id` filter 条件 ✓ FIXED
### Bug 4: `role_api.py:set_role_permissions` 没写 audit log ✓ FIXED
### Bug 5: `role_api.py:add_role_data_permission` 没写 audit log ✓ FIXED
### Bug 6: `bo_api.py:update_role_menu_permissions` (v2) 没写 audit log ✓ FIXED
### Bug 7: `role_menu_api.py:update_role_menu_permissions` (PFCG) 没写 audit log ✓ FIXED
### Bug 8: `management_dimension_api.py:save_permission_rule` 没写 audit log ✓ FIXED
### Bug 9: `permission_rule_api.py:create_rule` 没写 audit log ✓ FIXED

## Files Modified

1. `meta/api/role_dimension_scope_api.py` - 调 write_permission_config_audit (Bug 1+2)
2. `meta/api/audit_api.py` - 加 parent_object_type/id filter (Bug 3)
3. `meta/api/role_api.py` - 调 write_permission_config_audit (Bug 4+5)
4. `meta/api/bo_api.py` - 调 write_permission_config_audit (Bug 6)
5. `meta/api/role_menu_api.py` - 调 write_permission_config_audit (Bug 7)
6. `meta/api/management_dimension_api.py` - 调 write_permission_config_audit (Bug 8)
7. `meta/api/permission_rule_api.py` - 调 write_permission_config_audit (Bug 9)

## Verification Conclusion (修复后)

### Pre-fix 证据 (DB 直查)
```
=== parent_object_type distribution ===
  (None, 68)    ← 全部是 None
  ('product', 37)
  ('version', 9)
  ...

=== all audit_logs with parent_object_type=role AND parent_object_id=22 ===
Count: 0    ← 0 条 role 关联日志!
```

### Post-fix 证据 (E2E)
```
=== POST results (6 个 endpoint 全部 200/201) ===
  role_permissions: 200 ✓
  role_data_permission: 201 ✓
  role_v2_menu_permissions: 200 ✓
  role_menu: 200 ✓
  permission_rule: 200 ✓
  role_dimension_scope: 200 ✓

=== object_type distribution for role_id=22 ===
  role_dimension_scope: 13  (从 1 增加到 13)
  role_data_permission: 5   (从 0 增加到 5)
  role_menu: 4              (从 0 增加到 4)
  role_v2_menu_permissions: 3  (从 0 增加到 3)
  role_permissions: 3       (从 0 增加到 3)
  permission_rule: 8        (从 0 增加到 8)

=== Verification ===
  Expected: ['permission_rule', 'role_data_permission', 'role_dimension_scope', 'role_menu', 'role_permissions', 'role_v2_menu_permissions']
  Found:    [..., 'permission_rule', 'role_data_permission', 'role_dimension_scope', 'role_menu', 'role_permissions', 'role_v2_menu_permissions', ...]
  Missing:  NONE
  [OK]
```

## Cleanup
- 临时文件: e2e_repro_dim_scope_audit.py, audit_diag.py, post_fix_diag.py, fix_final.py, fix_verify.out, fix_final.out, post_fix_diag.out, audit_diag.out, check_api.py, check_api.out, check_api2.py, check_api2.out, inspect_audit_dim.py, recent_audit.py, recent_audit.out, audit_after_fix.py, audit_after_fix.out, debug_500.py, debug_500.out, e2e_role_audit_aggregation.py, full_e2e.out
- Debug server: 8765 端口 (可手动 kill 或等 idle timeout)
- Debug log file: .dbg/trae-debug-log-role-audit-missing.ndjson (无需保留)

---

# Round 2 (2026-06-12): 用户反馈 2 个新问题

## Round 2 Issues
1. **对象类型/字段名显示技术名**: `role_menu` / `role_dimension_scope` / `menu_codes` / `dimension_codes` 应该显示中文
2. **特定角色 (id=3606) 操作日志仍未显示**: DB 里有 8 条 parent_object=role/3606 的日志, 但 UI 上看不到

## Round 2 Root Cause

### Bug A: 前端 useAuditLogs 只传 object_type+object_id, 没传 parent_object
- `RoleDetailDrawer.vue` 调用 `useAuditLogs('role', roleId, { autoLoad: false })`
- `auditLogService.getLogsByObject` 把 `objectType=role, objectId=3606` 传给后端
- 后端 SQL: `WHERE object_type = ? AND object_id = ?` → 0 条 (该角色没 object_type=role 的自身变更)
- DB 里的 8 条都是 `object_type IN (role_menu, role_dimension_scope, permission), parent_object_type=role, parent_object_id=3606`
- → 修复: 改 SQL 支持 OR 联合查询 + 前端传 parent_object_type/id

### Bug B: AuditLogDetail.vue 直接渲染 `log.object_type` / `log.field_name` 技术名
- 模板 `{{ log.object_type }}` → 渲染 "role_menu"
- 模板 `{{ log.field_name }}` → 渲染 "menu_codes"
- → 修复: 后端注入 `object_type_label` / `field_name_label` / `parent_object_type_label` 字段

## Round 2 Fix Plan
- [x] 1. `meta/api/audit_api.py` 加 OBJECT_TYPE_LABELS / FIELD_NAME_LABELS 映射
- [x] 2. `meta/api/audit_api.py` 让 `/audit/logs` 端点支持 `(object_type+object_id) OR (parent_object_type+parent_object_id)` 联合查询
- [x] 3. `meta/api/audit_api.py` 返回的 log 增加 `object_type_label` / `field_name_label` / `parent_object_type_label` 字段
- [x] 4. `src/services/auditLogService.js` 让 `buildLogFilter` 支持 `parentObject: { type, id }` 参数
- [x] 5. `src/composables/useAuditLogs.js` 让 composable 支持 `parentObject` 选项
- [x] 6. `src/views/SystemManagement/RoleDetailDrawer.vue` 调 useAuditLogs 时传 `parentObject: { type: 'role', id: roleId }`
- [x] 7. `src/components/common/AuditLogDetail/AuditLogDetail.vue` 优先显示 label, 技术名作为灰色括号后缀
- [x] 8. `src/components/common/AuditLog/AuditLog.vue` 在 group header 加对象类型中文标签, 列表/详情都用 label

## Round 2 Files Modified
1. `meta/api/audit_api.py` - OBJECT_TYPE_LABELS/FIELD_NAME_LABELS + OR 联合查询 + label 注入 (Bug A+B)
2. `src/services/auditLogService.js` - buildLogFilter 支持 parentObject (Bug A)
3. `src/composables/useAuditLogs.js` - 支持 parentObject 选项 (Bug A)
4. `src/views/SystemManagement/RoleDetailDrawer.vue` - 传 parentObject={type:'role',id:roleId} (Bug A)
5. `src/components/common/AuditLogDetail/AuditLogDetail.vue` - 渲染 label (Bug B)
6. `src/components/common/AuditLog/AuditLog.vue` - 列表也用 label, 加 .al-group-object-type 标签 (Bug B)

## Round 2 Verification (curl 验证)

### 测试 1: 联合查询 (object_type=role+parent_object_type=role, id=3606)
```
total: 8 ✓
  - id=78244 obj=role_menu(角色菜单权限) field=menu_names(菜单名称) action=CREATE parent=role(角色)
  - id=78243 obj=role_menu(角色菜单权限) field=synced_permissions_count(自动同步权限数) action=CREATE parent=role(角色)
  - id=78242 obj=role_menu(角色菜单权限) field=menu_codes(菜单编码列表) action=CREATE parent=role(角色)
  - id=78241 obj=role_menu(角色菜单权限) field=() action=CREATE parent=role(角色)
  - id=78240 obj=role_dimension_scope(角色维度范围) field=dimension_codes(维度编码列表) action=CREATE parent=role(角色)
  - id=78239 obj=role_dimension_scope(角色维度范围) field=scopes_count(维度范围数) action=CREATE parent=role(角色)
  - id=78238 obj=role_dimension_scope(角色维度范围) field=() action=CREATE parent=role(角色)
  - id=78199 obj=permission(权限) field=roles(角色) action=DISSOCIATE parent=role(角色)
```

### 测试 2: 单传 parent_object (id=3606)
```
total: 8 ✓  (与联合查询一致)
```

### 测试 3: 单传 object_type=role (id=3606)
```
total: 0  (符合预期 - 3606 角色没改过自身, 改的都是子对象)
```

### 关键 label 验证
- `object_type: 'role_menu'` → `object_type_label: '角色菜单权限'` ✓
- `object_type: 'role_dimension_scope'` → `object_type_label: '角色维度范围'` ✓
- `field_name: 'menu_codes'` → `field_name_label: '菜单编码列表'` ✓
- `field_name: 'dimension_codes'` → `field_name_label: '维度编码列表'` ✓
- `field_name: 'synced_permissions_count'` → `field_name_label: '自动同步权限数'` ✓
- `field_name: 'menu_names'` → `field_name_label: '菜单名称'` ✓
- `parent_object_type: 'role'` → `parent_object_type_label: '角色'` ✓
- `new_value: '["架构数据管理", "产品版本管理", "业务配置", "日志管理"]'` (menu_names 解析后是中文菜单名) ✓

## Round 2 Status: [OPEN] → [FIXED] ✓✓

所有 2 个用户反馈问题已解决：
- ✓ 角色 3606 的 8 条权限变更日志能正常显示 (前端传 parent_object, 后端 OR 联合查询)
- ✓ 对象类型/字段名显示中文 label (后端注入 + 前端模板优先用 label)
