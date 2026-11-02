# G12 / G13 执行边界 —— 任务单（2026-11-01）

> 状态：**P1 / P2（G7）/ Phase 3 全部已落（2026-11-02）**。依据：
> `spec-project-type-object-model-research-2026-10-31.md` §3 G12 / G13、§4 D4 / D10 / D14、§8.2 四条硬规则；
> `spec-unified-resource-model-2026-11-01-v1.0.md` §9.3（`work_definition` 作业定义）；
> `docs/specs/task-two-generation-convergence/spec.md` §2.1 轨③。

## 1. 现状核对（2026-11-01，已读代码）

| 事实 | 证据 |
|---|---|
| `routing` 已落地，形式是 `work_definition`（`definition_kind=routing / service_template`） | `meta/schemas/work_definition.yaml`、`work_definition_operation.yaml`（v176） |
| 工单工序已有标准工时 / 资源组 / 技能 | `work_order_operation.yaml`：`setup_minutes` / `run_minutes` / `teardown_minutes` / `resource_group_id` / `required_skill_id` |
| 工单工序**曾缺**作业定义溯源 | 无 `work_definition_id` / `work_definition_operation_id`（本单 P1 已补，v184） |
| 六表「迁移兜底」**早已存在** | `meta/migrations/v154__provision_task_domain_tables.py`：复用代码 MetaObject 走 `sync_schema_from_meta`，幂等、回滚 no-op |
| G7 真正剩余 = 元模型化，不是建表 | `meta/core/task_schema.py` 注释明确「不注册进 BO registry，否则通用 BO API 可改 status 绕过状态机」 |
| 双通道仍未定界 | `work_order_operations.status` 与 `tasks.status` 并存；`tasks.line_refs` 为 JSON 弱引用，无创建 / 回填规则代码 |

**修正**：原计划把「G7 前半 = 六表 YAML + 迁移兜底」列为第一步，核对后迁移兜底已由 v154 完成；
真正卡点是 **YAML 注册语义**：`register_from_directory()` 会把对象注册进 BO registry，
与 `task_schema.py` 的「平台机制表不进 BO registry」纪律冲突，且与运行时 `ensure_task_tables()` 形成双 DDL 源。

## 2. 决策

| # | 决策 | 理由 |
|---|---|---|
| D18 | G12 溯源列用**软引用**（可空、无真外键），删除保护沿用 `work_definition_operation.deletion_policy` | SQLite 不支持对存量表 ALTER 加 FK；工序仍是参数表 |
| D19 | G7 元模型化需先引入「平台机制对象」注册豁免（`system_object` / 不注册），再迁 6 个 YAML | 绕过状态机风险不可接受；双 DDL 源会漂移 |
| D20 | G13 按 D10 方案 A 实现：工序只存参数，动作流转走 `tasks`，`tasks.line_refs` 指向工序 | 已有 `tasks.line_refs` 列，结构前提具备 |

## 3. 任务

### Phase 1 G12 溯源（已落）

- [x] **P1-1** `work_order_operation.yaml` 增 `work_definition_id` / `work_definition_operation_id`（可空、软引用、`value_help` 指向作业定义 / 标准工序）+ 2 条索引 + 表单「工艺溯源」段 + 详情字段。
- [x] **P1-2** 迁移 `v184__work_order_operation_definition_trace.py`：ALTER 补列 + 索引，幂等 `[SKIP]`；回滚只删索引、保留列。
- [x] **P1-3** `sync_schema --generate` 同步 `generated_schema.sql`。
- [x] **P1-4** 测试 `meta/tests/test_work_order_operation_trace.py` 8 passed：字段声明 / 无真外键 / 红线（无 `project_task_id`）/ UI 表单详情 / DDL / 迁移幂等 / 回滚。
- [x] **P1-5 定名**：统一为「作业步骤」（`work_order_operation.name` + 字段标签 / UI 标题 / 工单子表标题；保留旧别名「工单工序 / 作业工序」）；表名 / 对象 id / 列名不变。

### Phase 2 G7 元模型化（已落 2026-11-02）

- [x] **P2-1** 对象级开关 `skip_generic_api`（`MetaObject` 字段 + YAML 同名键，替代原设想的 `system_object` 专项豁免）：对象仍注册进统一 registry、仍进 DDL，但 ① `meta_api.list_objects` 不暴露；② agent `/tools`、`/schema` 不生成工具；③ `ensure_crud_actions()` 不补通用 CRUD 动作；④ `manage_api`（`/api/v1/<object_type>`）与 `bo_api`（`/api/v2/bo/<object_type>`）在 `before_request` 拦截，返回 404 `GENERIC_API_DISABLED`。
- [x] **P2-2** 六表 YAML：`meta/schemas/workflow.yaml` / `task_template.yaml` / `workflow_run.yaml` / `task.yaml` / `task_event.yaml` / `task_worklog.yaml`；`id` / `table_name` 与代码常量一致，字段 / 索引逐列平移，统一带 `skip_auto_menu: true` + `skip_generic_api: true`，`task.yaml` 另带 `requires_state_machine: true`。
- [x] **P2-3** 迁移切入口：`v154__provision_task_domain_tables.py` 改为从 `get_task_meta_objects()`（registry，YAML 兜底）取六对象建表，幂等 `[SKIP]`、编号未变；`sync_schema --generate` 重建 `generated_schema.sql`。DDL 等价已验收：六表列名 / 类型 / 可空 / 默认值 / 列序 / 索引名与改动前代码定义逐列逐索引一致（基线比对零差异）。
- [x] **P2-4** 删除 `task_schema.py` / `task_event_schema.py` 的 `_build_*_meta()` / `build_*_meta_objects()`；保留表名 / 对象 id 常量、状态机 import、`register_table_name` 白名单；新增 `get_task_meta_objects()` / `get_task_event_meta_objects()` 从 registry 按 id 取；`ensure_task_tables()` / `ensure_task_event_tables()` 改为 YAML 驱动，返回 SQL 列表签名与幂等性不变。
- [x] **P2-5** 测试：`meta/tests/test_g7_task_domain_meta_migration.py` 15 passed（YAML 加载 / `skip_generic_api` 生效 / v154 幂等 / 六表与 21 索引 / DDL 逐列等价 / 状态机合法与非法各一例）；回归任务域 195 passed、工作流 / 项目 / 工单域 284 passed。

### Phase 3 G13 双通道定界（已落 2026-11-02，设计见 §6）

- [x] **P3-1** 规则落地：`work_order_operations.status` 降为只读投影（`semantics.readonly_always` + UI 只读），唯一状态列 = `tasks.status`。证据：通用 `ManageService.update` 携带 `status` 不落库（库中仍 `pending`），随行可写字段正常更新；`test_single_point_trace.py::TestOperationStatusProjection` 4 passed。
- [x] **P3-2** 桥接逻辑：`meta/services/work_order_execution_service.py::create_operation_tasks` 只接受 `work_order_id`（project_task 不直接生成 tasks），校验 `source_demand_type='project_task'` + 项目一致（AC-09），按工序创建 tasks 并回填 `line_refs=[工序 id]`，重复调用幂等。接入点：`WorkOrderService.start_work_order`（New → In Progress，仅 project_task 来源调桥接）+ `POST /api/v1/work-orders/<id>/start`（事务包裹，桥接失败整体回滚）。测试 `test_work_order_execution_bridge.py` 11 passed。
- [x] **P3-3** 报工口径：实际工时只走 `time_entry`（v182）；工序不落 actual 列。证据：`work_order_operation.yaml` 字段无 `actual_*` / `reported_*` / `completed_qty` / `qty_done`；`generated_schema.sql` 的 `work_order_operations` 仅 `setup_minutes` / `run_minutes` / `teardown_minutes`，实际工时唯一落点是 `time_entries.minutes`。测试 `meta/tests/test_single_point_trace.py::TestReportingCaliber` 4 passed。
- [x] **P3-4** 「单点留痕」测试：同一动作只产生一条 `tasks` 状态流转 + 一条 `task_events`；工序状态不可手工推进。
  - 前半已落：一次 `record_transition` = 1 条 `status_changed` 事件 + 1 条 `transition` WORKLOG，事件与 WORKLOG 一一配对；任务迁移不改写 `work_order_operations.status`，`line_refs` 可反查工序（`TestSinglePointTrace` 3 passed）。
  - 后半已落：`TestOperationStatusProjection` 2 条通用更新用例证明工序 `status` 不可手工推进（4 passed）；整文件 11 passed。
- [x] **P3-5** 回归 `test_work_order_production.py` 15 passed / `test_work_order_service.py` 17 passed / `test_g7_task_domain_meta_migration.py` 15 passed / `test_task_state_machine.py` 33 passed。

## 4. 验收

- [x] G12：工序可按 `work_definition_id` / `work_definition_operation_id` 回溯；手填工序留空合法。
- [x] §8.2 红线 2 未破：`work_order_operation` 无 `project_task_id`（测试守护）。
- [x] G13：同一动作只在一处留痕；`tasks.line_refs` 能反查工序。（任务迁移不写工序状态、`line_refs` 可反查；工序 `status` 只读后不可手工推进）
- [x] G7：六表 DDL 单一真源（YAML）；`ensure_task_tables()` 仅保留 YAML 驱动的幂等兜底，启动期不再由代码 MetaObject 建表。

## 5. 风险

| 风险 | 处理 |
|---|---|
| YAML 与代码 MetaObject 字段漂移 | 已收敛：六表 DDL 列 / 索引基线比对零差异（`test_g7_task_domain_meta_migration`） |
| 对象进 BO registry 后绕过任务状态机 | `skip_generic_api` 关闭通用 CRUD / agent 工具；通用更新路径遇 `requires_state_machine` 调 `require_transition`，非法迁移返回 400 `STATE_MACHINE_VIOLATION` |
| 工序状态停写影响存量前端 / API 调用方 | P3-1 先投影只读，观察一轮再删写路径 |
| 工时口径被再次分裂 | 复用 `time_entry` + `v_resource_labor_daily`，不新增 actual 列 |

## 6. Phase 3 执行设计（2026-11-02，已批准并落地）

### 6.1 P3-1 工序 `status` 只读投影

**机制核对（已读代码）**

- `meta/core/yaml_loader.py` L367-374：字段级 `semantics.readonly_always` 会被解析进 `MetaField`；`work_order_operation.yaml` L363-368 已有 `semantics` 块，可直接加键。
- `meta/core/action_executor.py` L3339：`for_update` 时 `readonly_always` 字段被跳过（不落库、不报错）；`required_skill`（L244）已是同款写法。
- `meta/core/ui_config/field_extractor.py` L85：`readonly_always → readonly=True, editable=False`，列表 / 详情 / 表单三视图统一只读。
- 全仓无代码写 `work_order_operations.status`（`work_order_service` / `labor_service` / `resource_matching_service` 只读该校验），不会破坏存量链路。

**改动**

1. `meta/schemas/work_order_operation.yaml` 的 `status` 字段：
   - `semantics` 增 `readonly_always: true`；
   - `ui` 增 `editable: false` / `readonly: true`（与 `required_skill` 同款）；
   - `description` 改为「工序状态（只读投影；动作流转走 tasks，唯一状态列为 tasks.status）」。
2. 不改 DDL（无语义列变更），不重跑 `sync_schema --generate`。
3. `meta/tests/test_single_point_trace.py` 增 `TestOperationStatusProjection`（4 例）：
   - YAML `status.semantics.readonly_always is True`；
   - registry 加载后 `MetaField.semantics.readonly_always is True`；
   - `ManageService.update(object_type='work_order_operation', data={'status': 'completed'})` → 不落库，库中 `status` 仍为 `pending`（框架既定语义：只读字段跳过，不报错）；
   - 同一更新携带 `operation_name` 时：`operation_name` 落库、`status` 仍为 `pending`（证明「不可手工推进」且不误伤其它字段）。
4. 不改 `action_executor` / `manage_service` 全局行为（`readonly_always` 已被多处父键字段依赖，不能改成硬报错）。

### 6.2 P3-2 工序 → 任务桥接与 `line_refs` 回填

**边界**（延续 D10 / §8.2 硬规则 1）：`project_task` **不直接生成** `tasks`；只在工单已有工序后，由执行入口按工单创建 tasks。

**改动**

1. 新增 `meta/services/work_order_execution_service.py`：
   - `class BridgeError(Exception)`：带 `rule` 字段（`WORK_ORDER_NOT_FOUND` / `BRIDGE_SOURCE_NOT_PROJECT_TASK` / `PROJECT_MISMATCH` / `OPERATION_NOT_FOUND`）。
   - `create_operation_tasks(ds, work_order_id, *, created_by, executor_type='human') -> list[str]`：
     - 读 `work_orders`：空 → `WORK_ORDER_NOT_FOUND`；`source_demand_type != 'project_task'` → `BRIDGE_SOURCE_NOT_PROJECT_TASK`；
     - 读 `project_tasks(source_demand_id)` 校验 `project_id` 与工单一致（AC-09 口径），不一致 → `PROJECT_MISMATCH`；
     - 读 `work_order_operations`（按 `seq`，无工序 → `OPERATION_NOT_FOUND`），逐条 INSERT `tasks`：
       `id=uuid4().hex`、`title=operation_name`、`type='story'`、`status='pending'`、`executor_type`、`created_by`、`doc_ref=f'work_order:{work_order_id}'`、`line_refs=json.dumps([str(operation_id)])`、`created_at=updated_at=now`；
     - 幂等：先 `SELECT id, line_refs FROM tasks WHERE doc_ref = ?`，按 JSON 解析后匹配工序 id，已存在则跳过并返回已有 id；
     - 不自开事务（与 `work_order_service` 同构，事务边界由调用方控制）。
2. 新增 `meta/tests/test_work_order_execution_bridge.py`（5 例）：
   - 工单不存在 → `WORK_ORDER_NOT_FOUND`；
   - 来源非 `project_task` → `BRIDGE_SOURCE_NOT_PROJECT_TASK`；
   - 项目不一致 → `PROJECT_MISMATCH`；
   - 正常路径：2 条工序 → 2 条 tasks，`line_refs == ["<op_id>"]`、`doc_ref` 一致、`status='pending'`；
   - 幂等：重复调用不新增；且只给 `project_task`（无工单）时不会生成任何 task（硬规则 1）。
3. 接入点：`WorkOrderService.start_work_order`（New → In Progress；仅 project_task 来源调桥接）+ 专用端点 `POST /api/v1/work-orders/<id>/start`（显式事务，桥接失败整体回滚）；不改 `project_task` 现有路径；不改表结构。

### 6.3 P3-4 后半与 P3-5

- P3-4 后半：由 6.1 的两条 `ManageService` 用例直接收口，通过后勾选。
- P3-5 回归（worktree 内绝对路径 + 端口 3015）：
  - `python scripts/agent_test.py --file D:\filework\p2b1-worktree\meta\tests\test_work_order_production.py --port 3015 -q`
  - `test_work_order_service.py` / `test_g7_task_domain_meta_migration.py` / `test_task_state_machine.py` / `test_single_point_trace.py` / `test_work_order_execution_bridge.py`
- 全部通过后勾选 P3-1 / P3-2 / P3-4 / P3-5 与 §4 G13 验收，提交 `agent/labor-view`（不 merge）。

### 6.4 批准点

- 批准 = 同意按 §6.1 / §6.2 的文件与行为落地，并接受「只读字段跳过不报错」的既有框架语义。
- 不批准项可单独指定（例如要求 `status` 写入硬报错、或桥接不新增 service 文件）。

