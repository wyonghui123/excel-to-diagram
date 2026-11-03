# G14 工时回聚派生视图 —— 细化任务（2026-11-01）

> 状态：**计划（未实施）**。依据：
> `spec-project-type-object-model-research-2026-10-31.md` §3 G14 / §4 D11 / §8.2 第 4 条；
> `spec-unified-resource-model-2026-11-01-v1.0.md` FR-001 / FR-004 / FR-005 / FR-008 / FR-014 / FR-015；
> 主工作树最新资源域提交：`01458f61`、`05a9c5e2`、`e137db0a`、`16037c1a`（main tip `154dcaf5`，迁移至 `v181`）。

## 1. 现状核对（已读代码，不是推测）

| 事实 | 证据 |
|---|---|
| 资源 / 资源组 / 能力 / 费率 / 分配 / 多口径产能 / 可用性例外 / 班次 / 日历班次均已落库 | `meta/schemas/resource.yaml`、`resource_group.yaml`、`resource_capacity.yaml`、`resource_rate.yaml`、`resource_assignment.yaml`、`shift.yaml`、`calendar_shift.yaml`；迁移 `v175__resource_domain_foundation.py`、`v176__resource_domain_p2b.py`、`v180__resource_availability.py` |
| 产能可按日历 + 班次 + 例外算出「某资源某日可用分钟」 | `meta/services/resource_matching_service.py`：`resolve_resource_calendar()` / `shift_windows_for_date()` / `available_minutes()` / `availability_overrides()` |
| 资源分配只有**计划**时间窗与计划量，没有实际工时 | `resource_assignments` 字段止于 `planned_start` / `planned_end` / `planned_qty` / `status` / `source` |
| 工单工序只有**标准**分钟，没有实际分钟 | `work_order_operation`：`setup_minutes` / `run_minutes` / `teardown_minutes` / `resource_group_id`，无 actual 列 |
| Gen2 的 `task_worklogs` 是执行审计账，**不含工时与资源** | `meta/core/task_event_schema.py` `_build_worklog_meta()`：`entry_type` / `actor` / `detail` / `doc_ref`，无 `minutes`、无 `resource_id` |
| 项目任务已可用 | `meta/schemas/project_task.yaml`（v179，P1.5） |

**结论**：工时回聚真正的缺口是「**实际工时记录对象**」缺失，不是 G7。
G7（Gen2 六表进元模型）只影响任务六表的治理口径；本视图只要不依赖 `tasks` / `task_worklogs` 即可先落地。
另一个智能体交付的资源 / 班次主数据已经能把「可用分钟」算出来，正好补上视图的产能侧。

## 2. 设计决策（实施前请先确认）

| # | 决策 | 理由 |
|---|---|---|
| **D13** | 新建 `time_entry`（表 `time_entries`）作为唯一实际工时载体 | `task_worklogs` 是 append-only 审计账，加 `minutes`/`resource_id` 会污染账本语义；`resource_assignment` 只有计划量；没有第三个现成落点 |
| **D14** | 桥只落行级：`project_task_id` / `work_order_id` / `work_order_operation_id` / `resource_assignment_id`；`work_order_operation` **不加** `project_task_id` | 延续 §8.2 红线（桥只两键、只落单据头/行）；工时行属于「行」，工序只存参数 |
| **D15** | 回聚用视图 `v_project_task_labor` / `v_project_labor` / `v_resource_labor_daily`，不落汇总表 | 延续 D11；视图列只做 SUM / COUNT / MIN / MAX，不复制金额 |
| **D16** | 产能利用率不写 SQL 视图，由服务层复用 `available_minutes()` 计算 | 日历继承（资源 > 组 > 地点 > 默认）+ 例外日 + 班次跨天是 Python 逻辑；视图重写会造成第二套口径 |
| **D17** | 成本归集放阶段二：`time_entry` 写入时解析 `resource_rate`（`rate_purpose=cost` / `per_hour` / 生效日 + `priority`）并快照 `rate_id` / `cost_amount`；首期只做工时 | 避免视图在 SQL 里做多行费率择优；快照不是汇总表，符合 D11 |

## 3. 任务

### Phase 0 前置（阻断，必须先做）

- [x] **P0-1 合并完成**（merge commit `5d63d94d`，main 已并入本分支）
  - 决策：**保留 v175–v179 号段，不重编号**。`migration_runner.schema_migrations` 以**完整文件名**为唯一键，同号不同名的文件都会执行并各自记录；与 main 的 v175–v181 无同名文件、无依赖冲突。
  - 原因：PO 智能体正在主工作树开发（未提交 `requisition_po_conversion.py` 等），把项目侧迁移改号到 v182 反而会占用它下一个号段；保留原号段，后续新迁移从 **v182** 起。
  - 合并结果：`meta/scripts/init_menu_permissions.py` 自动合并成功（项目菜单与资源/采购菜单并存）；`generated_schema.sql` 保持「只含 project_tasks、不含资源/采购表」的既有状态（main 侧本来也未生成）。
  - 回归已验证：项目 P1.5 21、P1 35、P2b1 25、work_order production 15 / service 17、resource_matching 22、资源迁移 4 + 6，全部通过。
- [x] **P0-2 资源域可用**：v175 / v176 / v180 已随 main 合并，`resource_matching_service.available_minutes()` 测试 22 项通过。
- [x] **P0-3 项目侧可用**：`project_tasks` / `project_task_dependencies` 已存在，P1.5 测试 21 项通过。

### Phase 1 实际工时对象 `time_entry`

- [x] **P1-1 新建 `meta/schemas/time_entry.yaml`**
  - `id: time_entry`，`table_name: time_entries`，`display_name_field: id`，`aspects: [audit_aspect]`，`skip_auto_menu: true`（菜单由迁移手工声明）。
  - 字段：
    - `work_date`（date / required）
    - `resource_id`（integer / required / 展示 `resource.code - name` / value_help `resource`，`is_active=true`）
    - `minutes`（integer / required / `numeric_range gt 0 lte 1440 decimal_places 0`）
    - `project_task_id`（integer / nullable / 展示 `project_task.task_no`）
    - `work_order_id`（integer / nullable / 展示 `work_order.work_order_no`）
    - `work_order_operation_id`（integer / nullable / 展示 `work_order_operation.operation_name`）
    - `resource_assignment_id`（integer / nullable）
    - `entry_type`（string / required / default `manual` / enum `manual / timer / import`）
    - `billable`（boolean / required / default true）
    - `note`（string / max_length 500）
    - `created_at` / `updated_at`
  - 索引：`idx_time_entry_task_date(project_task_id, work_date)`、`idx_time_entry_resource_date(resource_id, work_date)`、`idx_time_entry_wo(work_order_id)`、`idx_time_entry_operation(work_order_operation_id)`、`idx_time_entry_assignment(resource_assignment_id)`。
  - 关系（真外键）：→ `resource`、`project_task`、`work_order`、`work_order_operation`、`resource_assignment`；均 `nullable`，删除 restrict。
- [x] **P1-2 服务层校验 `meta/services/labor_service.py`**（新建）
  - `R-TE-1` `project_task_id` 与 `work_order_operation_id` 至少填一个，否则 `ST_TIME_ENTRY_ANCHOR_REQUIRED`。
  - `R-TE-2` 两者都填时，任务 `project_id` 必须等于工单 `project_id`（工单为空时以任务为准），否则 `ST_PROJECT_MISMATCH`。
  - `R-TE-3` 传 `work_order_operation_id` 时，`work_order_id` 由工序反查并回填；显式值不一致抛 `ST_WORK_ORDER_MISMATCH`。
  - `R-TE-4` 传 `resource_assignment_id` 时，必须与 `work_order_operation_id`、`resource_id` 一致，否则 `ST_ASSIGNMENT_MISMATCH`。
  - `R-TE-5` `minutes` 必须 1–1440 的整数；`work_date` 不得晚于今天（补录允许过去）。
  - `R-TE-6` 资源必须 `is_active=1`；不限制 `resource_kind`（人 / 外协班组都可记工时），UI 默认筛 `person`。
- [x] **P1-3 迁移 `v182__time_entry_labor_view.py`**（实际落地号）
  - 建表 + 索引 + 权限 `project:time_entry_{create,read,update,delete,list}`（`resource_type=project`，不新增资源类型）。
  - 手工菜单 `time-entry`：`menu_path=/time-entries`，`parent_menu=sales`，`sort_order=4`，`skip_auto_menu` 配套声明写入 `meta/scripts/init_menu_permissions.py`。
  - 幂等 `[SKIP]`；`verify` 校验表 / 索引 / 权限 / 菜单 / **视图可 SELECT**；`rollback` 删视图 → 删表 → 删菜单，权限保留。
- [x] **P1-4 `python -m meta.tools.sync_schema --generate`**，确认 `generated_schema.sql` 含 `time_entries` 与 5 条索引。

### Phase 2 派生视图（工时回聚本体）

- [x] **P2-1 `v_project_task_labor`**（任务级）
  - 列：`project_id, project_task_id, task_no, task_name, status, actual_minutes, actual_hours, billable_minutes, entry_count, resource_count, first_work_date, last_work_date`。
  - 来源：`time_entries te JOIN project_tasks pt ON pt.id = te.project_task_id`；`GROUP BY pt.project_id, pt.id`。
  - `actual_hours = ROUND(SUM(minutes)/60.0, 2)`；`billable_minutes = SUM(CASE WHEN billable=1 THEN minutes ELSE 0 END)`。
- [x] **P2-2 `v_project_labor`**（项目级）
  - 列：`project_id, project_no, project_name, actual_minutes, actual_hours, billable_minutes, task_count, resource_count, entry_count, last_work_date`。
  - 归属解析：`COALESCE(pt.project_id, wo.project_id)`；`LEFT JOIN work_orders wo ON wo.id = te.work_order_id`。
  - 防重：一条工时即使同时挂任务与工序，也只按 `COALESCE` 的一个项目计一次；`task_count = COUNT(DISTINCT te.project_task_id)`。
- [x] **P2-3 `v_resource_labor_daily`**（资源 × 日，纯实际）
  - 列：`resource_id, work_date, actual_minutes, billable_minutes, entry_count, project_count`。
  - 只做实际分钟，不塞产能；产能利用率由服务层算（D16）。
- [x] **P2-4 视图守卫**
  - 迁移内 `DROP VIEW IF EXISTS` → `CREATE VIEW`；`verify` 对三个视图各做一次 `SELECT ... LIMIT 1`（SQLite 视图延迟解析，不 SELECT 等于没建）。
  - 回滚只删视图与表，不碰任何既有表。
  - 新增测试：空库建视图成功、插入种子后聚合值正确、回滚后视图消失。

### Phase 3 查询服务与入口

- [x] **P3-1 `labor_service.py` 聚合查询**
  - `project_task_labor(project_id=None, task_id=None)` → 读 `v_project_task_labor`。
  - `project_labor(project_id)` → 读 `v_project_labor`。
  - `resource_utilization(resource_id, start_date, end_date)`：
    - 逐日读 `v_resource_labor_daily`，逐日调 `available_minutes(conn, resource_id, date)`；
    - 返回 `actual_minutes / available_minutes / utilization_pct / overtime_minutes`；
    - 当日 `available_minutes=0` 且 `actual>0` 时记 `capacity_missing`，不抛错。
- [x] **P3-2 API**（实际：`/api/v1/labor` + `/api/labor` 别名）
  - 工时录入走通用 BO CRUD（`time_entry` 对象）+ 服务层校验；聚合查询新增只读端点（`GET /api/labor/...`），走 `_response_contract`，禁 `jsonify(`。
  - 权限：录入/修改沿用 `project:time_entry_*`；聚合读沿用 `project:time_entry_read`。
- [x] **P3-3 UI（最小，通用页承载）**
  - 菜单「工时记录」：`page_type=object_list` + `primary_object_type=time_entry`，由 `GenericObjectList` / `MetaListPage` 自动渲染列表与抽屉表单（资源 / 日期 / 分钟 / 项目任务 / 工单工序均来自 YAML 元模型），未新增前端文件。
  - 项目任务详情「工时」分区暂不新增：本工作树尚无项目任务详情页 / 项目 360 前端，随项目 360 前端一并落地；后端 `GET /api/labor/project-tasks` 已就绪。

### Phase 4 测试

- [x] **P4-1 `meta/tests/test_time_entry.py`**（15 passed）
  - 元模型：字段 / 必填 / 索引 / 5 条真外键。
  - 每条校验规则各 1 用例（R-TE-1 … R-TE-6）。
- [x] **P4-2 `meta/tests/test_project_labor_view.py`**（9 passed）
  - 种子：项目 A 两个任务 + 项目 B 一个任务 + 一条只挂工单的工时；
  - 断言任务级 / 项目级 / 资源日级数字一致，且只挂工单的工时归到工单项目；
  - 断言「任务 + 同项目工序」的工时只计一次。
- [x] **P4-3 `meta/tests/test_labor_queries.py`**（15 passed；任务单原写 `test_labor_utilization.py`，实际落地改名）
  - 班次 480 分钟、实际 600 → `overtime_minutes=120`；
  - `resource_availability` 请假扣减后 `available_minutes` 下降；
  - 无日历资源 → `available_minutes=0` + `capacity_missing`。
  - 另覆盖三个只读 API 端点。
- [x] **P4-4 回归**：`test_project_p15.py`（21）、`test_project_p1.py`（35）、`test_project_p2b1.py`（25）、`test_work_order_production.py`（15）、`test_work_order_service.py`（17）、`test_resource_matching.py`（22），全部通过。

### Phase 5 文档

- [x] **P5-1** project spec 升 v1.8：G14 关闭；D11 补「工时视图载体 = `time_entries`」；补 D13–D17；§2.5 红线 3 改写、§8.2 红线 1 / 2 确认未破。
- [x] **P5-2** 统一里程碑 spec 升 v0.8：P1.5 的「工时回聚视图（待 G7）」改为「已落，v182；G7 仅治理项」。
- [x] **P5-3** 本文件勾选完成项，提交（仅分支，不 merge）。

## 4. 视图 SQL 草案

```sql
CREATE VIEW v_project_task_labor AS
SELECT pt.project_id,
       pt.id AS project_task_id,
       pt.task_no,
       pt.name AS task_name,
       pt.status,
       SUM(te.minutes) AS actual_minutes,
       ROUND(SUM(te.minutes) / 60.0, 2) AS actual_hours,
       SUM(CASE WHEN te.billable = 1 THEN te.minutes ELSE 0 END) AS billable_minutes,
       COUNT(te.id) AS entry_count,
       COUNT(DISTINCT te.resource_id) AS resource_count,
       MIN(te.work_date) AS first_work_date,
       MAX(te.work_date) AS last_work_date
FROM time_entries te
JOIN project_tasks pt ON pt.id = te.project_task_id
GROUP BY pt.project_id, pt.id;

CREATE VIEW v_project_labor AS
WITH resolved AS (
    SELECT te.id,
           te.minutes,
           te.billable,
           te.resource_id,
           te.work_date,
           te.project_task_id,
           COALESCE(pt.project_id, wo.project_id) AS project_id
    FROM time_entries te
    LEFT JOIN project_tasks pt ON pt.id = te.project_task_id
    LEFT JOIN work_orders wo ON wo.id = te.work_order_id
)
SELECT r.project_id,
       p.project_no,
       p.name AS project_name,
       SUM(r.minutes) AS actual_minutes,
       ROUND(SUM(r.minutes) / 60.0, 2) AS actual_hours,
       SUM(CASE WHEN r.billable = 1 THEN r.minutes ELSE 0 END) AS billable_minutes,
       COUNT(DISTINCT r.project_task_id) AS task_count,
       COUNT(DISTINCT r.resource_id) AS resource_count,
       COUNT(r.id) AS entry_count,
       MAX(r.work_date) AS last_work_date
FROM resolved r
JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL
GROUP BY r.project_id;

CREATE VIEW v_resource_labor_daily AS
SELECT te.resource_id,
       te.work_date,
       SUM(te.minutes) AS actual_minutes,
       SUM(CASE WHEN te.billable = 1 THEN te.minutes ELSE 0 END) AS billable_minutes,
       COUNT(te.id) AS entry_count,
       COUNT(DISTINCT COALESCE(pt.project_id, wo.project_id)) AS project_count
FROM time_entries te
LEFT JOIN project_tasks pt ON pt.id = te.project_task_id
LEFT JOIN work_orders wo ON wo.id = te.work_order_id
GROUP BY te.resource_id, te.work_date;
```

## 5. 验收出口

- [x] 三张视图在空库可建、可 SELECT；回滚后消失（`test_project_labor_view.py` 覆盖）。
- [x] 任务级 / 项目级 / 资源日级数字与种子数据逐项一致；无重复计数。
- [x] `work_order_operation` 未新增 `project_task_id`；工时桥只落 `time_entries` 行。
- [x] `resource_utilization` 复用 `available_minutes()`，不出现第二套班次 / 日历口径。
- [x] 所有新增测试 + 6 个回归文件全绿；`check_architecture.py` 计数不上升。
      —— 测试全绿已确认；`scripts/check_architecture.py` 全部计数持平基线（jsonify_total 372→371，系文档注释误计，已改文案）。
- [x] spec v1.8 / 里程碑 v0.8 变更记录落地。

## 6. 风险与暂不做

| 风险 | 处理 |
|---|---|
| 迁移号重叠（v175–v181） | Phase 0 重编号到 v182+，同步测试导入与文档 |
| SQLite 视图延迟解析 | `verify` 强制 `SELECT ... LIMIT 1` |
| 成本多币种 / 费率择优 | 阶段二做，写入时快照 `rate_id` / `cost_amount`；首期不聚合金额 |
| 跨天班 / 调休 / 请假 | 只用 `available_minutes()`，不在视图重算 |
| 结账后补录工时 | 首期允许；锁定 / 期间控制留到对账需求出现 |
| 无日历资源 | `available_minutes=0` + `capacity_missing` 标记，不阻断记工时 |

暂不做：`tasks` / `task_worklogs` 入元模型（G7）；工时审批流；计费工时开票；按项目预算的工时控制；
工时与 `resource_assignment` 的自动回填（首期只做一致性校验，不回写计划量）。
