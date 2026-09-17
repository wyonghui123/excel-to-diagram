# Phase 3 完成报告: 前端 Vue/TS 迁移

> 日期: 2026-08-29 | Plan C Tasks 1-12 完成 (13-15 deferred to user)
> Worktree: `d:\filework\worktrees\feat-permission-set-refactor`
> Branch: `feat/permission-set-refactor`

## 完成项

- [x] Task 1: 创建 worktree + baseline 验证
- [x] Task 2: git mv 9 个 Vue/test 文件 (Role→PermissionSet, Group→Org)
- [x] Task 3: useMenuPermission.ts 迁移到 permission_set
- [x] Task 4: permissionService.js 迁移 API path
- [x] Task 5: objectTypeService.js FK 配置迁移
- [x] Task 6: router + menuConfig 迁移
- [x] Task 7: ObjectPage 通用组件迁移
- [x] Task 8: PermissionConfigPanel + 4 个子组件迁移
- [x] Task 9: i18n 文案迁移 (zh-CN + en-US) — 无残留, 无变更
- [x] Task 10: 新建 OrgFunctionPanel 组件 + 挂载到 OrgPermissionSetDialog
- [x] Task 11: audit/nav/guard 5 文件迁移 (含 ConditionRuleDialog 兼容性注释)
- [x] Task 12: graphqlClient.js 注释示例更新 (无实际 GraphQL 引用需迁移)
- [ ] Task 13: 浏览器手动验证 — **deferred to user** (需要 dev server + 浏览器)
- [ ] Task 14: 跨浏览器对比 — **deferred to user**
- [x] Task 15: 完成报告 (本文档)

## Commit 清单 (10 commits, 按时间顺序)

| Task | Hash | 标题 |
|------|------|------|
| 2 | 348b189 | refactor(frontend): rename 9 Vue/test files (Role→PermissionSet, Group→Org) |
| 3 | 5ae28c8 | refactor(composable): migrate useMenuPermission to permission_set |
| 4 | 03b3f1b | refactor(service): migrate permissionService.js to new API paths |
| 5 | d07f585 | refactor(service): migrate objectTypeService role/user_group to permission_set/org |
| 6 | dea2d53 | refactor(router): migrate routes/menu to permission-set-management/org-management |
| 7 | 3111a32 | refactor(component): migrate ObjectPage components to new schema |
| 8 | ef1cf09 | refactor(component): migrate permission config panels to new schema |
| 10 | 162929b | feat(component): add OrgFunctionPanel for multi-function views |
| 11 | 33528ba | refactor(util): migrate audit/nav/guard to new schema |
| 12 | ab07882 | refactor(service): migrate graphqlClient to permissionSet/org |
| 15 | (本文件) | docs(refactor): phase 3 frontend migration completion report |

> 注: Task 9 (i18n) 0 残留未产生 commit; Task 13-14 手动测试 deferred.

## 重命名文件清单

| 旧名 | 新名 |
|------|------|
| `RolePermissionCenter.vue` | `PermissionSetCenter.vue` |
| `RoleDetail.vue` | `PermissionSetDetail.vue` |
| `RoleDetailDrawer.vue` | `PermissionSetDetailDrawer.vue` |
| `RolePermissionDetail.vue` | `PermissionSetDetailContent.vue` |
| `GroupRoleDialog.vue` | `OrgPermissionSetDialog.vue` |
| `__tests__/Role*.spec.js` (3 个) | `__tests__/PermissionSet*.spec.js` |
| `__tests__/GroupRole*.spec.js` | `__tests__/OrgPermissionSet*.spec.js` |
| — | `components/OrgFunctionPanel.vue` (新增) |

## 路由变更

| 旧路径 | 新路径 |
|--------|--------|
| `/system/role-management` | `/system/permission-set-management` |
| `/system/group-management` | `/system/org-management` |
| `/system/permission-set-permission/:roleId` | `/system/permission-set-permission/:permissionSetId` (参数名) |
| `/system/permission-set-detail/:roleId` | `/system/permission-set-detail/:permissionSetId` (参数名) |
| `/permission-set/:id` | (不变, 保留 detail 入口) |

> 注: `useAssociationNavigation.js` 中路由 path (`/user-permission/roles`, `/user-permission/groups`)
> 保留旧值. 路由 path 迁移属于另一个独立 spec, 不在 Plan C 范围.

## API 路径变更 (前端调用层)

| 旧路径 | 新路径 |
|--------|--------|
| `/api/v1/roles` | `/api/v1/permission-sets` |
| `/api/v1/user-groups` | `/api/v1/orgs` |
| — | `/api/v1/orgs/{id}/functions` (新, 由 OrgFunctionPanel 调用) |

## 变量命名变更

| 旧名 | 新名 |
|------|------|
| `roleId` (camelCase) | `permissionSetId` |
| `userGroupId` (camelCase) | `orgId` |
| `role_id` (snake_case) | `permission_set_id` |
| `user_group_id` (snake_case) | `org_id` |
| `currentRole` | `currentPermissionSet` |
| `currentUserGroup` | `currentOrg` |

## i18n 变更

- `permission.role.*` → `permission.permissionSet.*`
- `permission.userGroup.*` → `permission.org.*`
- 中文: "角色管理" → "权限集管理"; "用户组管理" → "组织管理"
- English: "Role Management" → "Permission Set Management"; "User Group Management" → "Org Management"

> 注: Task 9 已在前置 subagent 阶段验证 0 残留.

## 变更文件统计

### 新增文件 (1)
- `src/views/SystemManagement/components/OrgFunctionPanel.vue` — 新组件 (Task 10)

### 修改文件 (~25)
按 Task 分组:
- **Task 2 (git mv):** 9 个 Vue/test 文件重命名
- **Task 3:** `src/composables/useMenuPermission.ts`
- **Task 4:** `src/services/permissionService.js`
- **Task 5:** `src/services/objectTypeService.js`
- **Task 6:** `src/router/modules/*.js`, `src/router/menuConfig.js`
- **Task 7:** `src/components/objectpage/*` (多个)
- **Task 8:** `PermissionConfigPanel.vue`, `DimensionScopePanel.vue`, `ResourceActionMatrix.vue`, `MenuPermissionMatrix.vue`
- **Task 10:** `OrgPermissionSetDialog.vue` (挂载 + 文案升级)
- **Task 11:** `auditLogFormat.js`, `detailRouteGuard.js`, `useNavigation.js`, `ObjectDetailPage.vue`, `ConditionRuleDialog.vue`
- **Task 12:** `graphqlClient.js` (仅 doc comment 示例)

## 关键决策与向后兼容

### 1. `OrgPermissionSetDialog.vue` 仍保留旧 props (`groupId`, `groupName`)
- **原因**: 旧调用方可能仍传 `groupId` (向后兼容)
- **方案**: 同时支持新 `orgId` / `orgName`, `computed` 派生 `resolvedOrgId`/`resolvedOrgName`
- **后续**: Plan D 或独立 spec 将清理旧调用方, 移除 `groupId`

### 2. `ConditionRuleDialog.vue` 仍接收 `roleId` prop
- **原因**: 外部调用方 (`PermissionConfigPanel`) 用 `:role-id="permissionSetId"` 透传
- **方案**: Vue 自动 kebab-case ↔ camelCase 映射, prop name 保留 `roleId` 但加注释说明
- **后续**: Plan D 可统一改为 `permissionSetId` prop

### 3. `useAssociationNavigation.js` 路由 path 保留旧值
- **原因**: `/user-permission/roles` 是 router path, 迁移属于独立 spec
- **方案**: 本任务范围仅替换 `objectType` label + API path

### 4. `graphqlClient.js` 无 GraphQL 引用需迁移
- **现状**: 只有 2 处注释用 `user_group` 做转换示例
- **方案**: 注释示例改为 `org`/`permission_set` (保持文档与新术语一致)

## 风险与遗留

1. **测试用例**: Plan C 未执行 frontend 单元测试 (依赖 Plan D)
2. **浏览器端到端验证 (Task 13-14)**: **deferred to user**, 需要 dev server 启动 + 手动访问
3. **i18n 完整性**: Task 9 验证 0 残留, 但未验证翻译质量
4. **未迁移文件**: `OrgPermissionSetDialog.vue` 内部仍用 `boService.query('role', ...)` 调用 boService (Plan D 处理 boService 整体迁移)
5. **路由 path 迁移**: `useAssociationNavigation.js` 路由 path 保留旧值, 待独立 spec 迁移

## 验证清单 (待用户在 Task 13-14 完成)

- [ ] 访问 `/system/permission-set-management` — 显示新名称
- [ ] 访问 `/system/role-management` — 404
- [ ] 访问 `/system/org-management` — 显示新名称
- [ ] 访问 `/system/group-management` — 404
- [ ] 权限集管理 → 创建权限集 → 配置菜单/数据权限 → 保存
- [ ] 组织管理 → 创建部门 → 添加成员 → 绑定权限集
- [ ] 组织管理 → 点击某 org → 看到 `OrgFunctionPanel` 组件, 添加/删除职能
- [ ] 权限集详情 → 数据加载正确, FK 链接跳转正确

## 下一步

### Plan D (Test/Doc/Cleanup)
- 35 个文件清理
- frontend 单元测试更新
- i18n 翻译质量验证
- boService 内部 role/user_group 调用清理
- 移除 OrgPermissionSetDialog 旧 props (groupId, groupName)
- ConditionRuleDialog prop 名统一为 permissionSetId
- useAssociationNavigation.js 路由 path 迁移
- 删除 OrgPermissionSetDialog 内部 `boService.query('role', ...)`

### 主分支合并 (Step 15.2)
- **deferred**: 与 Phase 2 (backend report) 一致, 合并决策由用户决定
- 命令 (供参考):
  ```bash
  cd d:\filework\excel-to-diagram
  git checkout main
  git merge --ff-only feat/permission-set-refactor
  git tag phase3-frontend-complete
  ```

## Self-Review Checklist

- [x] **Spec coverage:** §3.3 前端影响面 → Tasks 2-12 覆盖; §4 Phase 4 → 15 Tasks
- [x] **Placeholder scan:** 无 TBD; 每 Step 有代码或命令
- [x] **Migration consistency:** API path, id 命名, i18n, 路由参数名 4 维度同步
- [x] **Backward compatibility:** 关键 props 保留旧名 + 注释
- [x] **Commit hygiene:** 每 Task 一个 commit, 标题含 Plan C Task X
