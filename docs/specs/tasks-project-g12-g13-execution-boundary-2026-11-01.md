# G12 / G13 执行边界 —— 任务单（2026-11-01）

> 状态：**P1 已落，P2–P4 待评审**。依据：
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
- [ ] **P1-5 定名**（`工序` vs `上门步骤`）：等 `order_type` 文案统一时一起改，本阶段不动。

### Phase 2 G7 元模型化（阻塞，待评审）

- [ ] **P2-1** 设计「平台机制对象」注册豁免：YAML 标记（如 `system_object: true`）→ loader 只解析、不注册进 BO registry / 不生成菜单 / 不暴露 BO API；或反向：把 `build_task_meta_objects()` 迁为 YAML 并删除代码定义。
- [ ] **P2-2** 六表 YAML（`tasks` / `task_templates` / `workflows` / `workflow_runs` / `task_events` / `task_worklogs`），字段与代码 MetaObject 逐列对齐。
- [ ] **P2-3** 迁移切入口：v154 继续兜底；新增迁移校验 YAML 与代码 DDL 一致性（列差集为空）。
- [ ] **P2-4** 切换后删除 `ensure_task_tables()` / `ensure_task_event_tables()` 的 DDL 职责（保留表名白名单登记）。
- 阻断原因：P2-1 属平台启动路径改动，需单独评审；未决前不动，避免双 DDL 源。

### Phase 3 G13 双通道定界（待 G7 元模型化）

- [ ] **P3-1** 规则落地：`work_order_operations.status` 降为只读投影（或停写），唯一状态列 = `tasks.status`。
- [ ] **P3-2** 桥接逻辑：`project_task → source_demand(project_task) → work_order → work_order_operation → tasks`，创建 tasks 时回填 `line_refs`（指向工序 id）。
- [ ] **P3-3** 报工口径：实际工时只走 `time_entry`（v182）；工序不落 actual 列。
- [ ] **P3-4** 「单点留痕」测试：同一动作只产生一条 `tasks` 状态流转 + 一条 `task_events`；工序状态不可手工推进。
- [ ] **P3-5** 回归 `test_work_order_production.py` / `test_work_order_service.py` / 任务域六表测试。

## 4. 验收

- [x] G12：工序可按 `work_definition_id` / `work_definition_operation_id` 回溯；手填工序留空合法。
- [x] §8.2 红线 2 未破：`work_order_operation` 无 `project_task_id`（测试守护）。
- [ ] G13：同一动作只在一处留痕；`tasks.line_refs` 能反查工序。
- [ ] G7：六表 DDL 单一真源（YAML），启动期不再懒建表。

## 5. 风险

| 风险 | 处理 |
|---|---|
| YAML 与代码 MetaObject 字段漂移 | P2-3 一致性迁移（列差集为空才通过） |
| 对象进 BO registry 后绕过任务状态机 | P2-1 注册豁免，默认禁止 |
| 工序状态停写影响存量前端 / API 调用方 | P3-1 先投影只读，观察一轮再删写路径 |
| 工时口径被再次分裂 | 复用 `time_entry` + `v_resource_labor_daily`，不新增 actual 列 |
