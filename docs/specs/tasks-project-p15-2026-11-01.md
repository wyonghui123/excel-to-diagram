# P1.5 任务清单：计划层 `project_task` + 依赖边（2026-11-01）

> 依据：`spec-project-type-object-model-research-2026-10-31.md` §2.5 / §5 Phase 1.5 / AC-09；
> `spec-unified-demand-execution-milestone-2026-10-31.md` §0.1 P1.5（G11 / Q3）。
> 本文件只记录实施步骤与验收口径，不替代上述 spec。

## 范围

做：`project_task`、`project_task_dependency` 两个元模型对象；`work_order.source_demand_type`
扩 `project_task`；工单服务对 `project_task` 需求来源的必填与同项目校验；v179 迁移（建表 +
索引 + 权限 + 菜单）；`generated_schema.sql` 同步；测试与 spec 变更记录。

不做：`project_task` 生成 `tasks`、挂 `work_order_operation`；关键路径落表；
`project_milestone` 独立表；工时回聚派生视图（依赖 G7「Gen2 任务六表进元模型」，本阶段只留 TODO）。
项目 360 不加计划层 tab（AC-03 只列五段，避免改动既有 360 断言）。

## 步骤

- [x] Task 1: 新建 `meta/schemas/project_task.yaml`
  - `id: project_task`，`table_name: project_tasks`，`display_name_field: task_no`，
    `aspects: [audit_aspect]`，`ui_view_config.skip_auto_menu: true`（菜单由 v179 手工声明）。
  - 字段：`id`（integer 主键）；`project_id`（integer / required / 展示 `project` /
    value_help `project_no + name`）；`parent_task_id`（integer / nullable /
    `semantics.hierarchy_field: parent` / 自引用 max_depth 10）；`task_no`（string / required /
    max_length 30 / `data_category: code`）；`name`（string / required / max_length 200）；
    `task_type`（phase / work_package / activity，default `activity`）；`status`
    （draft / planned / in_progress / done / cancelled）；`planned_start` / `planned_end`（date）；
    `percent_complete`（number / default 0 / gte 0 lte 100 decimal 2）；`owner_user_id`；
    `description`（max_length 500）；`created_at` / `updated_at`。
  - 状态机（声明式 `rules: state_transition`，`state_field: status`）：
    `plan_task(draft→planned)`、`start_task(planned→in_progress)`、
    `complete_task(in_progress→done)`、`cancel_task(draft/planned/in_progress→cancelled)`。
  - 索引：`uidx_project_task_no(project_id, task_no) unique`、
    `idx_project_task_project_status(project_id, status)`、`idx_project_task_parent(parent_task_id)`、
    `idx_project_task_owner(owner_user_id)`。
  - 关系：`project_task_to_project`（reference → project，真外键；新表无存量漂移问题）。

- [x] Task 2: 新建 `meta/schemas/project_task_dependency.yaml`
  - `id: project_task_dependency`，`table_name: project_task_dependencies`，
    `aspects: [audit_aspect]`，`skip_auto_menu: true`。
  - 字段：`predecessor_task_id` / `successor_task_id`（integer / required / 展示
    `project_task.task_no`）；`dependency_type`（FS / SS / FF / SF，default FS）；
    `lag_minutes`（integer / required / default 0 / `numeric_range gte -525600 lte 525600
    decimal_places 0`，允许负数）；`created_at` / `updated_at`。
  - 索引：`uidx_ptd_edge(predecessor_task_id, successor_task_id, dependency_type) unique`、
    `idx_ptd_successor(successor_task_id)`。
  - 关系：两条 reference（→ project_task，真外键）。

- [x] Task 3: `meta/schemas/work_order.yaml`
  - `source_demand_type.enum_values` 增 `project_task`（label「项目任务」，category active）。
  - 同步文件头注释：production 需求来源集合改为
    `{sales_order_schedule, sales_order_line, project_task}`。

- [x] Task 4: `meta/services/work_order_service.py`
  - 常量：`SOURCE_DEMAND_PROJECT_TASK = 'project_task'`，并纳入 `SOURCE_DEMAND_TYPES`。
  - `_resolve_demand` 增 `project_task` 分支：查 `project_tasks(id, project_id)`，
    缺行抛 `ST_SOURCE_DEMAND_INVALID`；返回 `order_id/order_line_id/customer_account_id/
    item_id/qty = None`，附 `project_id`。
  - `_create_production`：解析需求后校验项目归属——payload `project_id` 与任务 `project_id`
    同时存在且不等 ⇒ `WorkOrderError(field_name='project_id', rule='ST_PROJECT_MISMATCH')`；
    工单 `project_id` 缺省时从任务回填。

- [x] Task 5: 新建 `meta/migrations/v179__project_task_p15.py`
  - 五件套结构照 v178：`migrate / verify / rollback / downgrade = rollback / __main__`。
  - `CREATE TABLE IF NOT EXISTS project_tasks / project_task_dependencies`（与生成 DDL 一致）。
  - 索引同上（`CREATE INDEX IF NOT EXISTS`）。
  - 权限：`project:project_task_{create,read,update,delete,list}`（`resource_type=project`）。
  - 菜单：`menu_code=project-task`，`parent_menu=sales`，`menu_path=/project-tasks`，
    同步写 `menus` 与 `menu_permissions`；并在 `meta/scripts/init_menu_permissions.py`
    声明该手工菜单，避免步骤 7.6 当冗余删除。
  - 幂等：表 / 索引 / 权限 / 菜单先查后用，重复执行打印 `[SKIP]`。
  - 回滚：删菜单 + 删索引 + 删两张表；权限行保留。

- [x] Task 6: 生成 DDL 与 schema 版本
  - cwd=worktree：`python -m meta.tools.sync_schema --generate`
  - `meta/schemas/generated_schema.sql` 已含两张新表与六条索引。

- [x] Task 7: 新建 `meta/tests/test_project_p15.py`
  - AC-09 四点：任务独立创建/关闭 + 状态机、依赖 FS/SS/FF/SF + lag、需求必填、同项目校验。
  - 迁移：建表 / 幂等 / verify / rollback（回滚后表消失、权限保留）。
  - `generated_schema.sql` 与 registry 生成的 DDL 一致（无 FK 漂移）。
  - 执行结果：21 passed（`python scripts/agent_test.py --file ... --port 3014 -q`）。

- [x] Task 8: 文档
  - 项目 spec 变更记录增 v1.7；Phase 1.5 行标注「已落，v179 / 视图待 G7」。
  - 统一里程碑 spec §0.1 P1.5 行标注状态，变更记录增 v0.7。

- [x] Task 9: 验证与提交
  - 回归：`test_project_p1.py`（35 passed）、`test_project_p2b1.py`（25 passed）、
    `test_work_order_production.py`（15 passed）、`test_work_order_service.py`（17 passed）。
  - 仅在 worktree 提交：`feat(project): P1.5 落地 project_task 与依赖边（G11）`。
  - 不 merge（主工作树仍有另一 Agent 未提交的 resource schema 与 v175）。

## 验证

- [x] `python scripts/agent_test.py --file D:/filework/p2b1-worktree/meta/tests/test_project_p15.py --port 3014 -q`
- [x] `python scripts/agent_test.py --file D:/filework/p2b1-worktree/meta/tests/test_project_p1.py --port 3014 -q`
- [x] `python scripts/agent_test.py --file D:/filework/p2b1-worktree/meta/tests/test_project_p2b1.py --port 3014 -q`
- [x] `python scripts/agent_test.py --file D:/filework/p2b1-worktree/meta/tests/test_work_order_production.py --port 3014 -q`
- [x] `python scripts/agent_test.py --file D:/filework/p2b1-worktree/meta/tests/test_work_order_service.py --port 3014 -q`

（cwd = worktree；测试入口只用 `agent_test.py`，禁 pytest。）

## 验收出口

- [x] 上述 5 个测试文件全绿（21 / 35 / 25 / 15 / 17）；
- [x] `generated_schema.sql` 含两张新表与六条索引；
- [x] 旧链路无回归（work_order service / production 测试不变）；
- [x] spec v1.7 变更记录落地；
- [x] worktree 单次提交（c4723446），未动主工作树。
