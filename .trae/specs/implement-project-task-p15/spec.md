# 项目计划层 P1.5（`project_task` + 依赖边）Spec

## Why

项目类型四层对象模型（P1 / P2 / P3 已落）缺计划层：项目无法独立表达「任务」与「任务间依赖」，
`work_order.source_demand_type` 也没有 `project_task` 取值，导致 G11（项目产生执行需求）无落点。

## What Changes

- 新增元模型对象 `project_task`（表 `project_tasks`）：项目内唯一 `task_no`、自引用父子层级、
  声明式状态机（draft → planned → in_progress → done / cancelled）。
- 新增元模型对象 `project_task_dependency`（表 `project_task_dependencies`）：
  只表达 FS / SS / FF / SF + `lag_minutes`（允许负数），三列复合唯一。
- `work_order.source_demand_type` 枚举扩 `project_task`（G11）。
- `WorkOrderService` 生产路径支持 `project_task` 需求来源：`source_demand_id` 必填、
  任务必须存在、工单与任务归属同一 `project_id`（缺省回填任务项目）。
- 迁移 `v179__project_task_p15.py`（建表 / 索引 / 权限 / 手工菜单），同步 `generated_schema.sql`。
- 不做：生成 `tasks`、挂 `work_order_operation`、关键路径落表、`project_milestone` 独立表、
  工时回聚派生视图（待 G7）、项目 360 计划层 tab。

## Impact

- Affected specs：[spec-project-type-object-model-research-2026-10-31.md](../../../docs/specs/spec-project-type-object-model-research-2026-10-31.md)（v1.7）、
  [spec-unified-demand-execution-milestone-2026-10-31.md](../../../docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md)（v0.7）
- Affected code：`meta/schemas/project_task.yaml`、`meta/schemas/project_task_dependency.yaml`、
  `meta/schemas/work_order.yaml`、`meta/services/work_order_service.py`、
  `meta/migrations/v179__project_task_p15.py`、`meta/scripts/init_menu_permissions.py`、
  `meta/tests/test_project_p15.py`

## ADDED Requirements

### Requirement: 项目任务可独立创建与关闭

系统 SHALL 提供 `project_task` 对象，任务归属单一项目，`task_no` 在项目内唯一，
并通过声明式状态机完成「计划 → 开始 → 完成 / 取消」。

#### Scenario: 创建并关闭任务

- **WHEN** 在项目下创建任务并依次执行 `plan_task` / `start_task` / `complete_task`
- **THEN** 任务状态依次为 `planned` / `in_progress` / `done`，且不产生任何工单操作行

### Requirement: 依赖边只表达四种类型与 lag

系统 SHALL 用 `project_task_dependency` 表达任务依赖，`dependency_type` 只能是
`FS / SS / FF / SF`，`lag_minutes` 为整数且允许负数。

#### Scenario: 重复边被拒绝

- **WHEN** 同一 `predecessor_task_id` + `successor_task_id` + `dependency_type` 再次写入
- **THEN** 唯一索引 `uidx_ptd_edge` 拒绝写入

### Requirement: 项目任务作为工单需求来源

系统 SHALL 允许 `work_order.source_demand_type='project_task'`；
此时 `source_demand_id` 必填、任务必须存在，且工单 `project_id` 与任务归属一致。

#### Scenario: 跨项目引用被拒绝

- **WHEN** 工单 `project_id` 与任务 `project_id` 不一致
- **THEN** 抛出 `ST_PROJECT_MISMATCH`

#### Scenario: 工单缺省项目时回填

- **WHEN** 工单未传 `project_id` 而来源任务有项目
- **THEN** 工单项目回填为该任务的项目
