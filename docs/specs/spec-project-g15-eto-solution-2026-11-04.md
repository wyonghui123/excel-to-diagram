# 实施方案：G15 ETO — Oracle 引用式 + SAP 任务轴

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：实施方案（待评审，**未实施**）
- 上游裁决：
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md`（§4 四条再评估条件、§7 14 项裁决）
  - `spec-project-g15-eto-infor-ifs-benchmark-2026-11-04.md`（§6 新增 `design_mode`）
  - `spec-project-g4-engineering-bom-2026-11-03.md`（D5 不建项目 BOM）
- 本文只回答一件事：**按"Oracle 骨架 + SAP 任务轴"把 ETO 落成可执行的对象改动与验收。**

---

## 0. 范围与结论

| # | 结论 |
|---|---|
| 1 | BOM / 工艺 / 变更 **全部保持产品级**，不加 `project_id`，不建项目 BOM 表、不建 WBS BOM、不建 Order BOM。 |
| 2 | ETO 项目差异化通过 **一项目一物料**（新建 item 承接定制结构）实现，这是 Oracle 的原生路线，不需要新对象。 |
| 3 | 唯一要新增的"项目层结构"是 P2 的 `project_structure_baseline`（**指针 + 快照哈希**，不是 BOM 副本）。 |
| 4 | **任务轴是本次真正的工程改动**：`project_task_id` 必须下钻到工单、库存事务、采购行。当前 `work_order` 只有 `project_id`，`inventory_transaction` **连 `project_id` 都没有**。 |
| 5 | 任务轴带来一个连带改动：`inventory_balances` 的唯一键必须纳入项目维度，否则项目库存与公共库存会被合并。这是本方案唯一"改既有投影"的地方。 |
| 6 | 项目成本只做**一个派生视图** `v_project_cost`，不建成本表；在财务模块落地前，视图先固定口径与形状，来源逐步填充。 |
| 7 | 全部改动收敛在 6 个对象 + 1 个视图；不做 PMMO、RA/Settlement、release key、DMS、CPQ、项目开票。 |

---

## 1. 裁决基线（一页）

| 对象 | 现状 | 目标 | 期次 |
|---|---|---|---|
| `project` | 有 `budget_amount`，无设计模式 | 加 `design_mode`（engineered / standard） | P1 |
| `project_task` | WBS 层级、状态机、无执行约束 | 不加字段；补索引 + 执行态守卫 | P1 |
| `work_order` | 有 `project_id`，无任务 | 加 `project_task_id` | P1 |
| `inventory_transaction` | **无项目字段** | 加 `project_id` + `project_task_id` | P1 |
| `inventory_balances` | 唯一键不含项目 | 唯一键纳入 `project_id` / `project_task_id`（0 哨兵） | P1 |
| `purchase_order_line` | 无任务 | 加 `project_task_id`（头已有 `project_id`） | P1 |
| `time_entry` | 已有 `project_task_id` | 不改字段，纳入成本来源 | P1 |
| `sales_order_line` | 无任务 | 加 `project_task_id`（可空） | P2 |
| `project_structure_baseline` | 不存在 | 新建（指针型） | P2 |
| `v_project_cost` | 不存在 | 新建视图 | P1（口径）/ P2（完整来源） |

---

## 2. P1 字段级设计

### 2.1 `project.design_mode`

```yaml
- id: design_mode
  name: 设计模式
  type: string
  db_column: design_mode
  required: true
  default: standard
  description: 项目设计模式；engineered = 按单设计（ETO），standard = 标准产品交付
  enum_values:
    - value: standard
      label: 标准
      color: info
      is_initial: true
    - value: engineered
      label: 按单设计
      color: warning
  semantics:
    meaning: 设计模式
    filterable: true
    filter_type: enum
    filter_label: 设计模式
```

用途：驱动校验与 UI，不改变对象结构。

- `engineered`：允许/要求走"一项目一物料"，工单与采购必须带 `project_task_id`（除非项目只有一个任务）。
- `standard`：不强制任务轴，行为与现状一致。

> 注意：这只是**行为开关**，不是新的事实字段。不要用它做成本口径或 BOM 归属。

### 2.2 `project_task`：不加字段，只加约束

现状已有 `project_id / parent_task_id / task_no / task_type(phase|work_package|activity) / status / percent_complete`，已足以承担 WBS 任务轴。

只做三件事：

1. 新增索引 `(project_id, status)`（任务轴过滤高频）。
2. 服务层守卫：被业务单据引用的任务，`status` 只能取 `planned` / `in_progress`；`cancelled` 任务禁止新引用。
3. 服务层守卫：`task_type = activity` 才允许被工单/采购/库存引用（phase 与 work_package 只做汇总）。若要放宽，用项目级配置，不新增字段。

**不新增**：预算、成本、计划金额——这些属于派生视图，不属于任务主数据。

### 2.3 `work_order.project_task_id`

```yaml
- id: project_task_id
  name: 项目任务
  type: integer
  db_column: project_task_id
  nullable: true
  description: 项目 WBS 任务；项目工单的归集粒度
  semantics:
    meaning: 项目任务
    display:
      type: association
      target_type: project_task
      display_field: name
  value_help:
    source:
      type: bo
      target_bo: project_task
      value_field: id
      display_field: name
      code_field: task_no
      apply_target_permissions: true
    behavior:
      multiple: false
      validation: true
      binding_strength: strict
```

守卫规则（服务层，非 DB 约束）：

| 规则 | 说明 |
|---|---|
| G1 | `project_task_id` 非空 ⇒ `project_id` 必须非空 |
| G2 | 任务必须属于同一 `project_id` |
| G3 | 任务 `status ∈ {planned, in_progress}`，且 `task_type = activity` |
| G4 | `project.design_mode = engineered` 且项目任务数 > 1 ⇒ `project_task_id` 必填 |
| G5 | 工单一旦 `released`，`project_id` / `project_task_id` 禁止修改 |

### 2.4 `inventory_transaction`：补项目维度（关键缺口）

当前该对象**完全没有项目字段**，导致"发料归项目"这件事在数据层无法成立。新增两个字段：

```yaml
- id: project_id
  name: 项目
  type: integer
  db_column: project_id
  nullable: true
  description: 库存事务归属项目；普通库存为空
  semantics:
    meaning: 项目
    filterable: true
    filter_type: number
    filter_label: 项目

- id: project_task_id
  name: 项目任务
  type: integer
  db_column: project_task_id
  nullable: true
  description: 库存事务归属的 WBS 任务
  semantics:
    meaning: 项目任务
    filterable: true
    filter_type: number
    filter_label: 项目任务
```

索引：`(project_id, project_task_id, item_id)`（项目发料查询）。

写入规则：

- 由项目工单产生的发料/退料：从工单带出 `project_id` + `project_task_id`。
- 由项目采购收货产生的事务：从采购行带出。
- 非项目业务：两字段为空，行为与现状一致（不需要 0 哨兵，因为事务表允许 NULL）。

### 2.5 `inventory_balances`：唯一键纳入项目（唯一改既有投影处）

现状唯一键 `(org_id, location_id, item_id, batch_id, stock_status)`，`batch_id` 用 0 哨兵。若不加项目维度，**A 项目的专用料会被合并进公共库存余额**，发料时无法区分"这堆料属于谁"。

改法：

```
uq_inv_balance_key = (org_id, location_id, item_id, batch_id, stock_status, project_id, project_task_id)
```

- `project_id` / `project_task_id` 使用 **0 哨兵**，与 `batch_id` 同构（SQLite 唯一约束不接受 NULL）。
- 投影重建逻辑同步：按事务的项目字段分组累加。
- 视图层：公共库存 = `project_id = 0`；项目库存 = `project_id > 0`。

不改的运行代价（必须写进风险）：项目专用库存与公共库存混算 → 可用量虚高 → 缺料/超发。

### 2.6 `purchase_order_line.project_task_id`

采购头已有 `project_id`。行级补任务，才能让"一批采购对应多个 WBS 任务"成立（ETO 常见：同一供应商同批到货，分属不同任务）。

新增字段与 `work_order.project_task_id` 同构。守卫：G1-G3 同上，另加：

- G6：`purchase_order_line.project_task_id` 非空 ⇒ 采购头 `project_id` 非空，且二者一致。
- G7：收货生成 `inventory_transaction` 时，项目字段**从采购行复制**，不允许手填。

### 2.7 `time_entry`：不改字段

已有 `project_task_id`。P1 只做一件事：把它纳入 `v_project_cost` 的人工来源。成本金额字段若尚未启用，视图该行返回 `amount = NULL` 并标记 `cost_status = 'pending_rate'`。

---

## 3. `v_project_cost`：单一口径的派生视图

### 3.1 形状（先固定，来源后填）

| 列 | 类型 | 说明 |
|---|---|---|
| `project_id` | int | 必填 |
| `task_id` | int | 0 = 未分配任务的项目级汇总 |
| `cost_type` | string | material / labor / subcontract / overhead / other |
| `qty` | number | 数量（材料/工时） |
| `amount` | number | 金额；无成本口径时为 NULL |
| `currency_id` | int | 币种 |
| `cost_status` | string | posted / pending_rate / estimated |
| `source_doc_type` | string | 来源对象（追溯用） |
| `source_doc_id` | int | 来源单据 |

### 3.2 来源矩阵（按可用性递进）

| `cost_type` | 来源 | P1 | P2 |
|---|---|---|---|
| material | `inventory_transactions` 出库类事务（qty）；金额待成本价 | qty 有、amount 空 | 接成本价后补 amount |
| labor | `time_entries`（qty = 工时） | qty 有、amount 空 | 接费率后补 amount |
| subcontract | `purchase_order_lines`（外协行） | amount 有 | — |
| overhead | 不派生 | — | 由财务事件回填 |
| other | 预留 | — | — |

### 3.3 硬规则

- 视图**只读**，不提供 CRUD，不允许人工写入。
- 任何"项目成本表"出现即视为违反单一事实，代码评审直接拒。
- 视图必须可按 `(project_id, task_id, cost_type)` 汇总，且与单据明细逐条可对。

---

## 4. P2：`project_structure_baseline`（指针型，非副本）

仅用于"标准物料 + 项目小幅差异"这一条路线，避免一项目一物料造成的料号爆炸。

| 字段 | 说明 |
|---|---|
| `project_id` | 项目 |
| `item_id` | 被引用的标准物料 |
| `structure_id` | 指向的 `item_structures` 版本（可为空 = 用当前生效版本） |
| `alternative_no` | 替代结构号 |
| `baseline_hash` | 该结构版本内容哈希（用于检测漂移） |
| `captured_at` | 快照时间 |
| `note` | 差异说明 |

**它不存 BOM 行。**这是与 SAP WBS BOM 的根本区别：SAP 存行，我们存指针 + 哈希。差异一旦需要"独立维护"，就必须改用"一项目一物料"，不允许在指针上加行。

---

## 5. 迁移与生成流程

| 迁移 | 内容 | 依赖 |
|---|---|---|
| `v204__project_design_mode.py` | `projects.design_mode` | 无 |
| `v205__eto_task_axis.py` | `work_orders.project_task_id`、`inventory_transactions.project_id/project_task_id`、`purchase_order_lines.project_task_id`、`sales_order_lines.project_task_id`（可一并） | v204 |
| `v206__project_stock_balance.py` | `inventory_balances` 唯一键重建 + 全量重算投影 | v205 |
| `v207__project_cost_view.py` | 建 `v_project_cost` 视图 | v205 |
| `v208__project_structure_baseline.py` | 建表（P2） | v207 |

要求：

1. 每次 schema 改动后重新生成 `generated_schema.sql` 与 `.schema_version.json`。
2. `v206` 属于"投影重建"，必须提供 `--rebuild` 幂等入口；重建前后用总量断言校验（∑事务 = ∑余额）。
3. 测试入口统一 `python d:\filework\test.py --single <path>`，禁止直接 pytest。

---

## 6. 守卫汇总（服务层，10 条）

| # | 规则 | 违反后果 |
|---|---|---|
| G1 | 任务字段非空 ⇒ 项目字段非空 | 400 |
| G2 | 任务必须属于同一项目 | 400 |
| G3 | 任务 `activity` + `planned/in_progress` | 400 |
| G4 | engineered 项目多任务 ⇒ 工单必填任务 | 400 |
| G5 | 工单 `released` 后项目字段不可改 | 400 |
| G6 | 采购行任务与采购头项目一致 | 400 |
| G7 | 收货事务项目字段只能从采购行复制 | 400（禁止手填） |
| G8 | 项目库存事务必须有项目；公共库存事务必须无项目 | 400 |
| G9 | 任务被引用时禁止删除/取消（先解绑） | 409 |
| G10 | 任何写入 `v_project_cost` / `inventory_balances` 的请求 | 405 |

---

## 7. 验收用例

| # | 用例 | 断言 |
|---|---|---|
| A1 | 新建 engineered 项目 → 2 个 activity 任务 → 建工单不带任务 | 400（G4） |
| A2 | 建工单带 B 项目任务 | 400（G2） |
| A3 | 项目工单发料 100 | 事务带 `project_id/project_task_id`；公共库存余额不变；项目库存余额 -100 |
| A4 | 项目采购 1 行挂任务 T1，收货 50 | 收货事务项目字段 = 采购行；项目库存余额 +50 |
| A5 | 同一物料同库位，A 项目 100、B 项目 50、公共 30 | 三行余额独立；`project_id=0` 行 = 30 |
| A6 | 清空 `inventory_balances` 后重建 | 行数与数量与重建前逐行一致 |
| A7 | `engineered` 项目，任务 T1 取消 | 409（G9，已被工单引用） |
| A8 | 查询 `v_project_cost` | 材料 qty 正确，`amount` 为 NULL 且 `cost_status='pending_rate'` |
| A9 | 手工 POST 一条项目成本 | 405（G10） |
| A10 | 标准项目（`standard`）建工单不带任务 | 201（不受 G4 约束） |

---

## 8. 任务清单（可直接排期）

**P1（必须）**

- [ ] P1-1 `projects.design_mode` 字段 + 枚举 + 迁移 v204
- [ ] P1-2 `work_orders.project_task_id` + 值帮助 + 迁移 v205
- [ ] P1-3 `inventory_transactions.project_id / project_task_id` + 索引
- [ ] P1-4 `inventory_balances` 唯一键纳入项目（0 哨兵）+ 投影重算 + 迁移 v206
- [ ] P1-5 `purchase_order_lines.project_task_id` + 收货复制链路
- [ ] P1-6 守卫 G1-G10 + 单测
- [ ] P1-7 `v_project_cost` 视图（材料/人工/外协三来源）+ 迁移 v207

**P2（可选）**

- [ ] P2-1 `sales_order_lines.project_task_id`
- [ ] P2-2 `project_structure_baseline` 指针表 + 漂移检测
- [ ] P2-3 `v_project_cost` 接成本价/费率，`amount` 补齐

**P3（暂不做）**

- WBS BOM / Order BOM / PMMO / RA / Settlement / release key / DMS / CPQ / 项目开票

---

## 9. 风险与回退

| # | 风险 | 处置 |
|---|---|---|
| R1 | `inventory_balances` 唯一键变更导致历史余额对不上 | 迁移内置投影全量重算；重建前后总量断言；失败即回滚迁移 |
| R2 | 项目库存与公共库存混算 | 0 哨兵 + G8 双向守卫 |
| R3 | 一项目一物料导致料号爆炸 | 用 `design_mode` 与四条再评估条件监控；超阈值切 P2 指针路线 |
| R4 | 任务轴变成"第二个项目预算表" | 明确拒绝：任务不加预算/成本字段 |
| R5 | 标准项目被强制任务轴 | `design_mode` 分流，A10 用例守 |
| R6 | 视图被当表改装 | G10 + 代码评审红线 |

---

## 10. 不做什么（写进评审口径）

1. 不给 `item_structures` 加 `project_id`。
2. 不建 BOM 副本表（任何名字都不行）。
3. 不在项目任务上放预算/成本字段。
4. 不建项目成本表。
5. 不为 ETO 新增"配置器"能力（CTO 已有 `configuration*`）。
6. 不在本期引入 WIP、收入确认、结算。

---

## 11. 执行记录与修正（2026-11-04）

对照仓库实际 schema 与并行设计稿（`spec-mto-eto-stock-segment-design-2026-11-04.md`、`docs/specs/inv2-reservation-atp/`）后，本文初稿有 4 处判断需要更正，**以本节为准**。

### 11.1 已实施

| 项 | 内容 | 验证 |
|---|---|---|
| `projects.design_mode` | 新增字段（`standard` / `engineered`），存量回填 `standard` | `test_project_p15` 21 passed |
| `meta/migrations/v206__project_design_mode.py` | 加列 + 幂等 skip + `verify` | 临时库探针：ADD → SKIP → PASS |
| `meta/schemas/generated_schema.sql` | 由 YAML 重新生成 | 顺带修复既有漂移（26 张表此前未写入） |

### 11.2 更正（初稿判断有误）

| 初稿主张 | 实际情况 | 结论 |
|---|---|---|
| `work_orders` 缺 `project_task_id`，需新增 | 已有 `source_demand_type` / `source_demand_id`，支持 `project_task`，并有 AC-09（同项目校验） | **不新增列**，任务轴已存在；查询走 `source_demand_*` |
| `purchase_order_lines` 需加 `project_task_id` | `purchase_order_line.yaml` 明确 T-D3 / D6：行不放单值项目或任务引用，归属由 `demand_allocation` 表达 | **禁止新增**；采购任务轴走 `demand_allocation` |
| `inventory_transactions` 补 `project_id` 并改余额唯一键 | 该改动已由 INV-2（`inv2-reservation-atp`，v205）以 stock segment 统一承接，尚未实现 | **不在本方案重复**；等 INV-2 落地 |
| 迁移用 v204 / v205 | v204 = 收货类型、v205 已被 INV-2 预留 | 本方案实际使用 **v206** |

### 11.3 修正后的 P1 状态

| 项 | 状态 |
|---|---|
| P1-1 `design_mode` | ✅ 已完成（v206） |
| P1-2 工单任务轴 | ✅ 已具备（`source_demand_type='project_task'`），无需开发 |
| P1-3 库存 / 采购任务轴 | ⏳ 由 INV-2 v205 + `demand_allocation` 承接 |
| P1-4 余额唯一键 | ⏳ 同上，由 INV-2 统一改 |
| P1-5 守卫 G1-G3 | ⏳ 改为作用在 `demand_allocation`（随 INV-2） |
| P1-6 `v_project_cost` | ⏳ 依赖成本价 / 费率，后置 |

### 11.4 结论

ETO 的"任务轴"在平台里**已经存在**，只是分散在 `demand_allocation` 与工单的需求来源字段上，而不是缺列。真正待建的只有三件：

1. 库存项目 / 段维度（INV-2）；
2. `v_project_cost` 派生视图（待成本口径）；
3. ETO 行为守卫（依赖前两项）。

若后续确有必要把 `project_task_id` 提升为工单/采购行的独立列，必须先修订 T-D3 与 AC-09，属于独立变更，不在本方案内。

