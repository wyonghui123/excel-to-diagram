# Tasks：编排调度（schedule）与平台运维作业视图

> 依赖 spec：`2026-10-14-workflow-schedule-and-platform-ops-jobs.md` | 状态：待批准

## A. 选项2 —— Workflow schedule 调度器（后端核心）

- [x] A1 扩展 `meta/core/workflow_trigger.py`：`TRIGGER_SCHEDULE` 常量、`TriggerSpec.cron`、
      `parse_trigger_expr` 分派 + `_parse_schedule_expr`（findings 见 spec §2）。
- [x] A2 修订 `meta/tests/test_workflow_trigger.py`：TC-WFT-001 循环去掉 schedule；补 schedule
      合法/缺 expr/非 JSON/非对象/缺 cron/坏 cron 用例。
- [x] A3 修订 `meta/tests/test_workflow_store.py`：TC-WFS-010 补 schedule 合法 expr；
      TC-WFS-014 循环去掉 schedule；补 schedule 缺 expr → `TRIGGER_EXPR_MISSING`。
- [x] A4 跑 A2/A3 相关既有测试（test_workflow_trigger 47 passed；test_workflow_store 25 passed）。
- [x] A5 新建 `meta/core/workflow_schedule_scheduler.py`：`WorkflowScheduleScheduler`（spec §3.1）。
- [x] A6 新建 `meta/tests/test_workflow_schedule_scheduler.py`（先红）：派生作业、refresh 增量、
      tick 到点触发、run_now 唤起 Run、is_registered、坏定义跳过。
- [x] A7 `meta/server.py` 接线（spec §3.3）：`if _cron_enabled` 内建 + start + atexit + 注入；
      `else` 记 paused。

## B. 选项1 —— 只读聚合端点（后端）

- [x] B1 新建 `meta/api/workflow_api.py`：`workflow_bp` + `set_workflow_scheduler` +
      `GET /api/v2/workflows/schedules` + `GET /api/v2/workflows/scheduler/status`（spec §3.4）。
- [x] B2 新建 `meta/tests/test_workflow_api.py`（先红）：聚合三段 / node_count / runs 状态 /
      status 三态（503 / 暂停 / 正常）。
- [x] B3 `meta/server.py`：`if is_module_enabled('tasks'):` 内注册 `workflow_bp`。

## C. 前端视图

- [x] C1 `src/services/taskService.js` 加 `fetchWorkflowSchedules()`。
- [x] C2 `src/views/TaskCenter/TaskCenter.vue` 加「调度」tab + 只读表；`menuConfig.js`
      `tabGroupConfigs['task-management']` 同步。
- [x] C3 新建 `src/services/schedulerService.js`：`fetchSchedulerStatus()` / `runSchedulerJob(code)`。
- [x] C4 新建 `src/views/SystemManagement/PlatformOpsJobs.vue`（custom_page，两组表 + 行内立即执行）。
- [x] C5 `src/router/modules/system.js` 加路由 `/system/platform-ops-jobs`；
      `src/router/dynamicRoutes.js` 两个 Set 登记 name/path。
- [x] C6 `meta/scripts/init_menu_permissions.py` 的 `system_menus` 增「平台运维作业」菜单
      （parent_menu='system'、page_type='custom_page'）。
- [x] C7 前端单测：TaskCenter schedule tab、PlatformOpsJobs 渲染 + 立即执行、两个 service。

## D. 文档与提交

- [x] D1 回填 `meta/docs/SCHED_CRONTAB_RULES.md`、`docs/superpowers/specs/2026-09-07-task-model-design.md`
      §7.4/§9.5/§12.1、`docs/superpowers/specs/…-task-scheduler.md` §13。
- [x] D2 全量回归（spec §4 清单）+ 前端 spec。
- [x] D3 按协议提交（`[pm-authorized]`，`excel-to-diagram/docs` 与 `meta/docs` 一并提交；
      `d:\filework\docs` 只改不提交）。
