
## Phase H14: 导入导出权限一致性 (2026-06-25)

**问题背景**: 在角色权限配置页的"菜单与功能权限"矩阵下，BO 独立动作（export/import）的可见性由 menus.bo_bindings[*].include_actions 决定，而 init_menu_permissions.py 是硬编码初始化的——没有自动从 yaml import_export: 段派生。结果：sub_domain / service_module / business_object / relationship 在 yaml 中支持导入导出，但权限矩阵 UI 中根本没有 sub_domain:import/export 这些独立权限可勾；同时权限矩阵也没有从 yaml 派生 ssign/unassign (user_group) 等动作。出现"列表页能点导入导出按钮（页面级全局开关），但角色配置里没有对应权限条目"的认知错位。

**根因**:
- yaml import_export 段: 业务能力声明（ImportExportService 能否工作）
- menu o_bindings.include_actions: 权限矩阵 UI 推导源（_derive_bo_permission_groups 的 ctions_map）
- 页面 ctionsConfig: 前端按钮可见性（页面级默认 enabled）
- 三层独立维护，无联动机制

### H14.1: 步骤 6.5 自动化对齐脚本（修复 2 — 推荐）

- [ ] SubTask: 在 meta/scripts/init_menu_permissions.py 步骤 6 之后增加"步骤 6.5: yaml → menu bo_bindings 自动对齐"
- [ ] SubTask: 扫描 meta/schemas/*.yaml，对每个有 import_export: 段的 BO：
  - import_enabled: true → 在对应 menu 的 o_bindings 该 BO 条目中追加 import 到 include_actions
  - export_enabled: true → 同上追加 export
  - 已存在的不重复添加（保持现有 source/role 字段不变）
- [ ] SubTask: 对 user_group 等 yaml 未配 import_export 但 bo_bindings 显式声明了 ssign/unassign/grant/revoke 的情况，反向保留（不删除人工显式声明）
- [ ] SubTask: 输出对齐 diff 日志：[ALIGN] domain: +export +import / [ALIGN] sub_domain: +export +import / [KEEP] user_group: assign/unassign (yaml 未配但 menu 显式声明)
- [ ] SubTask: 在 init_menu_permissions.py 顶部 docstring 增加"yaml 是单一事实源"的注释

### H14.2: 架构修复（修复 3 — 长期）

- [ ] SubTask: 把 _derive_bo_permission_groups 中的 _STANDALONE_ACTIONS_DEF 硬编码列表改为从 yaml import_export 段 + _action_groups.yaml.standalone_actions 动态推导
- [ ] SubTask: 后端新增 endpoint GET /api/v1/meta/bo-standalone-actions 返回所有 BO 的可用独立动作
- [ ] SubTask: MenuPermissionMatrix.vue 改为调用此 endpoint 渲染独立动作按钮（不再依赖 bo_bindings.include_actions 中的 export/import 存在与否）
- [ ] SubTask: 启动时校验：若 menu 的 bo_bindings 显式声明 export/import 但 yaml 不支持，记录 warning（反向检查）

### H14.1 完成确认 (2026-06-25)

- [OK] init_menu_permissions.py 步骤 6.5 实现，幂等跑通 (第二次打印 "无需对齐 (yaml ↔ menu 已一致)")
- [OK] seed_perms_direct.py 写入 195 条 permission 到 DB (来自 yaml schema 派生)
- [OK] 7 个 menu 的 bo_bindings 全部对齐：
  - arch-data: sub_domain/service_module/business_object 从 0 standalone 补到 2 (export+import)
  - arch-data: relationship 从 1 (export) 补到 2 (+import)
  - product-management: product/version 从 0 补到 2
  - user-permission: user/role 从 0 补到 2
  - enum_type: 仅 export (yaml import_enabled=false) ✓
  - audit_log: 仅 export (yaml import_enabled=false) ✓
- [OK] API /api/v1/roles/1/unified-permissions 验证: 所有 13 个 BO 的 bo_permission_groups 完整返回

## Phase H15: 用户反馈的 3 个具体问题 (2026-06-25)

**问题 1: 业务关系 (relationship) 矩阵中"管理"按钮缺失**

- 现象: arch-data 菜单下 relationship 只有 view+export+import 三组，没有 edit 和 manage 组
- 根因: **不是 bug，是用户角色 TEST888 没被分配 relationship:create/update/delete**。relationship yaml 有 relationship_create/update/delete 三个 actions。
  - API 返回 `[arch-data] relationship: grp=[view], std=2` — 只有 view 组说明只有 view 权限被勾
  - yaml 中 `relationship_delete` 等存在
- 解决方案:
  - 短期: 在角色 TEST888 权限页手动勾选 relationship 的 create/update/delete
  - 中期: 考虑给 admin 角色默认勾选所有 BO 的全部 action (现在 admin 也需要手动)

**问题 2: user_group:unassign / user_group:grant 等独立动作 label 显示英文**

- 现象: "详细权限"列表中 `user_group:unassign` 和 `user_group:grant` 显示为英文 "unassign" "grant"
- 根因链 (双重缺失):
  - [user_group.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/user_group.yaml) 没有 `actions:` 段声明 `user_group_assign` / `user_group_unassign` / `user_group_grant` / `user_group_revoke`
  - [_standard_actions.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/_standard_actions.yaml) 只有 `assign` (分配) 和 `revoke` (撤销)，缺 `unassign` / `grant` / `associate` / `dissociate` 的中文 name
  - 后端 `_get_permission_label()` 三层 fallback 全部 miss → 直接返回 perm_code 原值
- 解决方案:
  - [H15.2.1] 在 _standard_actions.yaml 补充 4 个独立动作的中文 name (unassign=取消分配, grant=授权, associate=关联, dissociate=取消关联) — 1 分钟
  - [H15.2.2] 在 user_group.yaml 显式声明 user_group_assign/unassign/grant/revoke 四个 actions (让 BO-specific label 优先于标准) — 可选，更准确
  - [H15.2.3] 验证: 重启后端 → API 返回 user_group:unassign label 应为 "用户组:取消分配"

**问题 3: TEST888 角色无 service_module:export 权限但 list 页面仍能导出 (前端 bypass)**

- 现象: 用户角色 TEST888 角色配置中没有服务模块的"导入/导出"独立权限勾选，但进入 arch-data 切换到"服务模块" tab 仍可点"导出"按钮
- 根因 (双层):
  - 前端 [useMultiObjectPage.js:519-530](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js) `canExport`/`canImport` computed 只看 `actionsConfig.enabled` 和 `versionContext`，**完全没接角色权限/RBAC**
  - 后端 [export_import_api.py:129 export_data / 444 import_data](file:///d:/filework/excel-to-diagram/meta/api/export_import_api.py#L129) **没有权限检查** — 任何登录用户都能调用导出导入 API
- 安全等级: **高危** — 这是个 bypass 漏洞，普通用户能导出未授权数据
- 解决方案:
  - [H15.3.1] (必须，P0 安全) 后端 export_data/import_data 加上 `check_permission("{bo_id}:export" / "{bo_id}:import")`，无权限返回 403
  - [H15.3.2] (必须) 前端 useMultiObjectPage 的 canExport/canImport 增加 roleHasPerm 短路判断 (从 permission store 读已分配权限)
  - [H15.3.3] (测试) 写 test_h15_rbac_bypass.py: 用户 A 角色无 service_module:export → 调 /api/v1/export 期望 403

### 验证
- test_h14_alignment.py:
  - 跑 init_menu_permissions 后检查 menus.bo_bindings：domain/sub_domain/service_module/business_object/relationship 都包含 export+import
  - role-permission UI 切换到 arch-data 菜单，应能看到所有 BO 的 export/import 独立权限按钮
  - 给子领域角色勾上 import/export，导出子领域应该 200 通过
- 回归：
  - user_group 的 assign/unassign/grant/revoke 不受 H14.1 影响（无 yaml 但 menu 显式声明）
  - enum_type 的 import_enabled=false → menu 中 enum_type 不会出现 import 按钮
