# Checklist：编排调度（schedule）与平台运维作业视图

> 依赖 spec：`2026-10-14-workflow-schedule-and-platform-ops-jobs.md`
> 验证日期：2026-10-14

## 选项2 —— Workflow schedule 调度器（后端核心）

- [x] `trigger_kind='schedule'` 的 `trigger_expr` 契约：须为 JSON 对象且含非空 `cron`，发布即校验
      （`parse_trigger_expr` 分派 `_parse_schedule_expr`）；错误码 `TRIGGER_EXPR_MISSING` /
      `TRIGGER_EXPR_NOT_JSON` / `TRIGGER_EXPR_NOT_OBJECT` / `TRIGGER_CRON_MISSING` / `TRIGGER_CRON_INVALID` 齐备。
- [x] `meta/core/workflow_schedule_scheduler.py`：作业集从已发布 schedule 定义派生（code=workflow_key、
      handler=`workflow_schedule`）；`refresh_jobs` 增量维护 `_next_run`；`tick` 先 refresh 再 `super().tick`；
      `run_now` 调 `start_run(...)`；`is_registered` / `codes`；调度状态**仅在内存**、不落表。
- [x] `meta/server.py`：`_cron_enabled` 时建 `WorkflowScheduleScheduler` 并 `start()` + `atexit` 注册 +
      注入 `set_workflow_scheduler`；`else` 分支记 paused。

## 选项1 —— 只读聚合端点（后端）

- [x] `meta/api/workflow_api.py`：`GET /api/v2/workflows/schedules` 只读聚合（定义 + cron/next_run +
      最近 runs）；`GET /api/v2/workflows/scheduler/status` 三态（未接线 503 / 暂停 200+paused / 正常 200）。
- [x] `meta/server.py`：`workflow_bp` 仅在 `is_module_enabled('tasks')` 时注册。

## 前端视图

- [x] `src/services/taskService.js` 增 `fetchWorkflowSchedules()`（→ `apiV2.get('/workflows/schedules')`）。
- [x] `src/views/TaskCenter/TaskCenter.vue` 增只读「调度」tab；`src/config/menuConfig.js` 同步该 tab。
- [x] `src/services/schedulerService.js`：`fetchSchedulerStatus()` / `runSchedulerJob(code)`（code 走
      `encodeURIComponent`）。
- [x] `src/views/SystemManagement/PlatformOpsJobs.vue`（custom_page）：读 `GET /api/v2/schedulers/status`，
      maintenance / platform 两组表 + 行内「立即执行」→ `POST /api/v2/schedulers/<code>/run-now`；
      用标准组件（PageShell/AppCard/AppButton/EmptyState）。
- [x] 路由：`src/router/modules/system.js` 加 `/system/platform-ops-jobs`；
      `src/router/dynamicRoutes.js` 的 `STATIC_ROUTE_NAMES` / `STATIC_ROUTE_PATHS` 均登记。
- [x] 菜单种子：`meta/scripts/init_menu_permissions.py` 的 `system_menus` 增「平台运维作业」
      （`parent_menu='system'`、`page_type='custom_page'`、path=`/system/platform-ops-jobs`），
      且**未**放入 `init_task_menus.py`。

## 菜单可见性修正（交付菜单的必经修复）

- [x] `meta/api/menu_permission_api.py` 的 `_prune_empty_groups`：原判定把「任意无 children 的
      `custom_page`」一律当空分组容器裁掉，导致真页面叶子（`custom_page` + 静态路由 + 无子菜单）不可见。
      改为按「是否设权限门槛」区分：`required_permissions` 为空 → 仍视为分组容器（无可见子菜单则隐藏，
      保住 H2/H3 契约）；显式设权限门槛 → 视为独立页面，保留。
- [x] 种子 `platform-ops-jobs.required_permissions` 由 `[]` 改为 `["*"]`（管理员门槛，与 `audit-log`
      同口径、与路由 `meta.requiresAdmin` 一致）。
- [x] 新增 `meta/tests/test_menu_platform_ops_jobs.py`（先红后绿，4 用例）：super_admin 在 `system`
      下可见该菜单；business_user 不可见；且 business_user 仍看不到空的 `system` 分组（H3 未破）。
- [x] 附带数据清理：本地库残留的 `aa-diagram` 旧菜单行（其移除迁移因表名过时从未生效）随修正显形，
      已按迁移意图删除 `menus` / `menu_permissions` 残留行（仅数据，不改代码）。

## 任务管理菜单可见性修正（同口径收口）

- [x] `meta/scripts/init_task_menus.py`：`task-management` 的 `required_permissions` 由 `[]` 改为
      `['*']`。该菜单同为「`custom_page` + 有 `menu_path` + 无子菜单」的真页面叶子，门槛为空时会被
      `_prune_empty_groups` 误当空分组容器裁掉，导致管理员侧栏看不到「任务管理」；设 `['*']`
      即声明其为独立页面，并与路由 `meta.requiresAdmin` 保持一致（业务用户不可见）。
- [x] 重跑 `init_task_menus` 应用于 `architecture.db`：`menus` / `menu_permissions` 两表该行
      `required_permissions` 均落为 `["*"]`。
- [x] 扩展 `meta/tests/test_menu_platform_ops_jobs.py`（先红后绿，新增 3 用例）：super_admin 在
      `system` 下可见 `task-management` 且路径为 `/system/task-management`；business_user 不可见。
      该文件合计 7 用例全绿。

## 测试

- [x] 后端：`test_workflow_schedule_scheduler.py`（12）、`test_workflow_api.py`（7）、`test_scheduler_api.py`（13）、
      `test_workflow_trigger.py`（47）、`test_workflow_store.py`（25）、`test_maintenance_scheduler.py`（10）、
      `test_platform_scheduler.py`（13）、`test_task_api.py`（8）全绿。
- [x] 受菜单种子影响的测试：`test_menu_platform_ops_jobs.py`（4）、`test_platform_modules_20261013.py`（27）、
      `test_task_menu_entry_convergence.py`（5）、`test_server_app_integration.py`（10）、
      `test_merged_two_apps_menu.py`（9）、`test_warehouse_app_poc2.py`（17）全绿。
- [x] 前端：`schedulerService.spec.js`（3）、`PlatformOpsJobs.spec.js`（5）、`TaskCenter.schedule.spec.js`（2）、
      `taskService.spec.js`（19）全绿（4 files / 29 tests）。

## 文档

- [x] `meta/docs/SCHED_CRONTAB_RULES.md` 回填 schedule 触发契约 + 调度器位置 + 只读端点。
- [x] `docs/specs/spec-task-scheduler.md` §13 回填菜单现状（含 `required_permissions=["*"]` 与剪枝约束说明）。
- [x] `d:\filework\docs\superpowers\specs\2026-09-07-task-model-design.md` §7.4/§9.5/§12.1 推进 C 组状态
      （该文件**只改不提交**）。

## 边界（明确不做）

- [x] 未新增 BO、未走 MetaTable；未调整 `/api/v2/schedulers/status` 暂停态语义；
      未改 `MaintenanceScheduler` / `PlatformScheduler` 既有行为与作业集；未引入第二套事件通道/表达式语言。

## 菜单可见性测试陈旧断言修正（本次一并收口）

- [x] `meta/tests/test_menu_visibility_h2_h3.py` 3 条陈旧断言已按现状更新（`user-permission` 自
      2026-06-20 顶栏重构后为顶级节点，不再挂在 `system` 下）：
      - `test_admin_sees_system_with_children`：`system` 子菜单改为断言
        `task-management` / `business-config` / `audit-log` / `platform-ops-jobs`，去掉 `user-permission`。
      - `test_super_admin_sees_full_tree`：改为断言 `user-permission` 节点存在且其子叶子
        `user-management` 可见。
      - `test_business_user_no_system_no_audit_log`：去掉 `user-permission` 断言（顶级自助菜单，
        业务用户可见属正常），补齐 `task-management` / `platform-ops-jobs` 的隐藏断言。
      该文件 14 用例全绿。

## 已知遗留（非本次引入，未处理）

- [ ] `meta/migrations/remove_aa_diagram_menu_2026.py` 引用的 `role_menu_permissions` 表已不存在
      （更名为 `permission_set_menu_permissions`），脚本运行即报错；本次改用等价 SQL 直接清理数据。
