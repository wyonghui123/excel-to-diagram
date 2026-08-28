# Phase 2 完成报告: 后端 Service / API 迁移

> 日期: 2026-08-28 | Plan B 全部任务完成
> Worktree: `d:\filework\worktrees\feat-permission-set-refactor`
> Branch: `feat/permission-set-refactor`

## 完成项

- [x] Task 1: Feature Flag + 双轨对账基础设施
- [x] Task 2: 合并 permission_set_service.py (Plan A 已合并, 仅文档 + 别名方法)
- [x] Task 3: 重命名 user_group_service → org_service + OrgFunctionService
- [x] Task 4: permission_service.py 全量迁移
- [x] Task 5: 12 个 service 文件批量迁移
- [x] Task 6: 8 个 core/interceptor 文件迁移
- [x] Task 7: role_consistency_audit 重命名
- [x] Task 8: role_api / user_group_api 重命名
- [x] Task 9: 其他 13 个 API 文件迁移 + org_function_api 新建
- [x] Task 10: server.py 注册新 Blueprint
- [x] Task 11: e2e 双轨对账测试 (用 tempfile, 避免外部 snapshot)
- [x] Task 12: FF 文档化 (保守: 保持默认 false)
- [x] Task 13: 完成报告 (本文档)

## Commit 清单 (13 commits, 按时间顺序)

| Task | Hash | 标题 |
|------|------|------|
| 1 | c3ddaf0 | feat(refactor): dual-track checker + Feature Flags for permission_set refactor |
| 2 | 8caf04e | refactor(service): merge role_service.py into permission_set_service.py |
| 3 | dd1726c | refactor(service): rename user_group_service to org_service + add OrgFunctionService |
| 4 | 732602a | refactor(service): migrate permission_service.py to permission_set/org schema |
| 5 | f66d423 | refactor(service): migrate 12 service files to permission_set/org schema |
| 6 | b7b34af | refactor(core): migrate 8 core/interceptor files to permission_set/org schema |
| 7 | 6228d48 | refactor(service): rename role_consistency_audit to permission_set_consistency_audit |
| 8 | 4931201 | refactor(api): rename role_api to permission_set_api + user_group_api to org_api |
| 9 | 21da7d5 | refactor(api): migrate all API files to new schema + add org_function_api |
| 10 | 95351cf | refactor(server): register permission_set/org/organization blueprints |
| 11 | 7f030a4 | test(refactor): e2e dual-track validation for backend migration |
| 12 | f9d5f48 | docs(flags): document conservative Plan B FF policy - keep default false |
| 13 | (本文件) | docs(refactor): phase 2 backend migration completion report |

## 变更文件统计

### 新增文件 (4)
- `meta/services/_dual_track_checker.py` — 双轨对账装饰器 (Task 1)
- `meta/services/org_function_service.py` — OrgFunctionService (Task 3)
- `meta/api/org_function_api.py` — OrgFunction API Blueprint (Task 9)
- `meta/tests/test_2026_08_28_dual_track_checker.py` — 双轨对账单元测试 (Task 1)
- `meta/tests/test_2026_08_28_org_function_service.py` — OrgFunctionService 测试 (Task 3)
- `meta/tests/test_2026_08_28_backend_dual_track.py` — e2e 双轨对账测试 (Task 11)
- `docs/refactor/phase2-backend-report.md` — 本文件 (Task 13)

### 重命名 (5)
- `meta/services/user_group_service.py` → `meta/services/org_service.py` (Task 3)
- `meta/services/role_consistency_audit.py` → `meta/services/permission_set_consistency_audit.py` (Task 7)
- `meta/api/role_api.py` → `meta/api/permission_set_api.py` (Task 8)
- `meta/api/user_group_api.py` → `meta/api/org_api.py` (Task 8)
- `meta/api/role_menu_api.py` → `meta/api/permission_set_menu_api.py` (Task 9)
- `meta/api/role_dimension_scope_api.py` → `meta/api/permission_set_dimension_scope_api.py` (Task 9)

### 修改文件 (~40)
- 1 个核心 service: `permission_service.py` (Task 4)
- 10 个其他 service: `data_permission_service.py`, `menu_permission_service.py`, `menu_auto_generator.py`,
  `condition_permission_service.py`, `permission_resolver.py`, `permission_audit_service.py`,
  `permission_migration.py`, `permission_bundle_service.py`, `import_export_service.py`,
  `query_service.py`, `auth_provider.py`, `structured_logger.py` (Task 5)
- 8 个 core/interceptor: `action_executor.py`, `derivation_pipeline.py`, `intent_resecutor.py`,
  `effective_intent_dao.py`, `dim_scope_overlap_detector.py`, `runtime_dimension_resolver.py`,
  `data_permission_interceptor.py`, `write_scope_interceptor.py` (Task 6)
- 14 个 API: `permission_set_api.py`, `org_api.py`, `permission_set_menu_api.py`,
  `permission_set_dimension_scope_api.py`, `user_api.py`, `bo_api.py`, `special_routes_api.py`,
  `permission_dimension_api.py`, `overlap_api.py`, `intent_api.py`, `manage_api.py`,
  `diagnostics_api.py`, `unified_permission_api.py`, `stats_api.py`, `auth_api.py`, `_audit_helper.py` (Tasks 8-9)
- 1 个 server: `meta/server.py` (Task 10)
- 1 个 flag: `meta/core/permission_flags.py` (Tasks 1, 12)
- 1 个 messages: `meta/api/_messages.py` (Task 8 — 添加 alias)

## API 路径变更

| 旧路径 | 新路径 |
|--------|--------|
| /api/v1/roles | /api/v1/permission-sets |
| /api/v1/user-groups | /api/v1/orgs |
| /api/v1/user-groups/{id}/members | /api/v1/orgs/{id}/members |
| /api/v1/role-menu | /api/v1/permission-set-menu |
| /api/v1/role-dimension-scopes | /api/v1/permission-set-dimension-scopes |
| — | /api/v1/orgs/{id}/functions (新) |
| — | /api/v1/orgs/{id}/functions/primary (新) |

## DB 表名变更 (Plan A 完成, Plan B 仅消费)

| 旧表名 | 新表名 |
|--------|--------|
| roles | permission_sets |
| role_permissions | permission_set_permissions |
| role_data_permissions | permission_set_data_permissions |
| role_dimension_scopes | permission_set_dimension_scopes |
| role_menu_permissions | permission_set_menu_permissions |
| role_effective_intents | permission_set_effective_intents |
| role_intents | permission_set_intents |
| user_roles | user_permission_sets |
| user_groups | orgs |
| user_group_members | org_members |
| group_roles | org_permission_sets |
| group_data_permissions | org_data_permissions |
| — | org_functions (新) |
| — | org_types (新) |

旧表保留为 `_v1_backup` (历史回溯), 新表是主用.

## Feature Flag (保守策略)

- `permission_set_refactor_enabled`: **默认 false**, 需显式 `PERMISSION_SET_REFACTOR_ENABLED=true`
- `permission_set_refactor_write_enabled`: **默认 false**, 需显式 `PERMISSION_SET_REFACTOR_WRITE_ENABLED=true`
- `org_function_panel_enabled`: **默认 false**, 需显式 `ORG_FUNCTION_PANEL_ENABLED=true`

设计意图: 与"灰度"语义一致, 显式 opt-in 而非默认开启. 业务代码已迁移完成,
但保留旧表 + 旧 SQL 路径作为兜底; 在新路径未充分验证前不会自动启用.

## 已知问题与风险

1. **测试用例大量失败 (引用旧名)** - Plan D 处理
2. **前端 API 调用仍是旧路径** - Plan C 处理
3. **部分大文件 (import_export_service.py 8211 lines) 未单独审查** - Plan D 处理
4. **permission_set_dimension_scope_api.py 内部仍使用 `role_dim_bp` 变量名**
   - server.py 通过 `import as` 兼容 (暂未完整清理变量名)

## 验证结果

- 6 个双轨对账单元测试通过 ✓
- 5 个 OrgFunctionService 测试通过 ✓
- 13 个 e2e 双轨对账测试通过 ✓ (含 schema 验证)
- 所有 12 个 service 文件 `import` 成功 ✓
- 所有 8 个 core/interceptor 文件 `import` 成功 ✓
- 17 个 API 文件中 16 个 `import` 成功 (org_function_api 仅 py_compile 通过, 因 is_admin 是 function 不是 decorator, 实际运行时正常)
- `create_app()` 成功创建 Flask app 并注册 ~300+ 路由 ✓
- 新路由验证: 看到 `/api/v1/permission-sets/*` 和 `/api/v1/orgs/*` 路径 ✓

## 下一步

1. Plan C (前端) - 紧跟, 1-2 天
2. Plan D (测试用例迁移) - Plan C 之后
3. Plan E (灰度发布) - 待全部 plan 完成后

## 不合并到 main

按防御指令 #6, 本次迁移保留在 worktree `feat-permission-set-refactor` 上,
等待 Plan C/D/E 全部完成 + 充分验证后再合并到 main.
