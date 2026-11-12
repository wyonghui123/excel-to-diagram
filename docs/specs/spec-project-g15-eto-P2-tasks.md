# G15 P2 任务分解：销售订单任务轴 + 结构基线

- 规格：`docs/specs/spec-project-g15-eto-solution-2026-11-04.md` §4
- 迁移：`v210`（SO 行任务字段）、`v209`（结构基线）；`v211`（成本视图）后置
  - 编号让位：`v208` 已被并发会话的 `work_order_project_task` 占用
- 状态：**已实施**（2026-11-04；阶段 A/B/C 完成，P2-3 后置；验收结果见文末）
- 测试入口：`python d:\filework\test.py --single <path>`

---

## 阶段 A：SO 行任务字段与守卫（v210）

- [x] A1 新建 `meta/migrations/v210__sales_order_line_project_task.py`
  - `sales_order_lines` 加 `project_task_id INTEGER NOT NULL DEFAULT 0`
  - 建索引 `idx_sales_order_line_project_task(project_task_id)`
  - 幂等 `[SKIP]`；`verify` 断言列/索引；`rollback` 仅删索引（SQLite 不删列，注释说明）
  - 验收：重复执行 `[SKIP]`；`migration_lint` 无重复版本；`--dry-run` 顺序 v209 → v210

- [x] A2 `meta/schemas/sales_order_line.yaml` 加字段
  - `project_task_id`，association → `project_task`，display `task_no`，filterable
  - 位置紧跟 `project_id` 之后

- [x] A3 守卫接入 `meta/services/sales_order_guard_service.py`
  - 行写入（create/update）调用共享 `project_task_guard`（strict）：G1 任务 ⇒ 项目；G2 同项目；G3 `activity` + `planned/in_progress`
  - 行 `project_id` 为空时用抬头 `project_id` 归一化；归一化后仍为空 → `SO_LINE_TASK_PROJECT_REQUIRED`
  - 行/抬头项目非空不一致 → `SO_LINE_PROJECT_MISMATCH`
  - 物料 `so_segment_enabled=1` 且行挂任务 → `SO_LINE_SEGMENT_TASK_CONFLICT`
  - 错误码统一映射为 400，`field_name` 指向 `project_task_id`

- [x] A4 单测 `meta/tests/test_sales_order_line_project_task.py`
  - R1-R5 正反例；MTS 标准行不受影响；抬头无项目但行有任务时拒绝

- [x] A5 验收
  - `python d:\filework\test.py --single meta/tests/test_sales_order_line_project_task.py`
  - 回归 `test_sales_order_guard.py` / `test_sales_order_fulfillment_status.py`

---

## 阶段 B：预留与发运维度

- [x] B1 `InventoryReservationService._load_sales_order_line` 增查 `l.project_id, l.project_task_id`
  - `sync_sales_order_line` 的 `segment_ctx` 增传两者
  - 任务行按 INV-2 优先级落 `project_task` 段；SO 段物料已在 A3 拒绝组合，不产生歧义

- [x] B2 释放清理
  - 取消行/订单沿用 `release_by_source`；释放后 `prune_empty_balances(project_task 段)`
  - `qty_reserved` 投影回写后任务段空余额可删

- [x] B3 交货单复制
  - 创建 `shipment_lines` 时从 SO 行复制 `project_id/project_task_id`
  - 明确：当前无发运自动过账；后续接入出库过账必须带这两个维度（文档注释 + `tasks.md` 标注）

- [x] B4 单测
  - `test_inventory_reservation_service.py` 增：任务行预留落 `project_task` 段、取消释放清空
  - `test_mto_consignment_flow.py` 增：任务行端到端（预留 → 收货 → 核销）
  - 验收：跨段不串池；trace 表不写任务字段（I11 边界不变）

---

## 阶段 C：结构基线（v209）

- [x] C1 新建 `meta/migrations/v209__project_structure_baseline.py`
  - `project_structure_baselines`（DDL 见规格 §4.2）
  - 唯一索引 `uq_project_structure_baseline(project_id, item_id, usage, alternative_no)`
  - 幂等 / verify / rollback（删表 + 索引）

- [x] C2 `meta/schemas/project_structure_baseline.yaml`
  - 字段：项目/物料/usage/替代号/结构版本/基线哈希/快照时间/备注
  - 只读 hash 展示；`baseline_hash` 禁止手工编辑（`readonly`）
  - 权限 2 条（read/list）+ create/update/delete 动作；菜单挂项目任务同级父菜单（待确认 menu parent code）
  - 验收：`sync_schema_from_meta` 后 `PRAGMA table_info` 可见

- [x] C3 新建 `meta/services/project_structure_baseline_service.py`
  - `resolve_structure(item_id, usage, alternative_no, structure_id, at)`：0 → 时点 active 版本；非 0 → 钉住版本
  - `compute_hash(structure)`：`revision|base_qty|uom` + 按 `line_no` 排序行，数值去尾零、布尔 1/0
  - `create_or_update(payload)`：同键 upsert，写入 hash/captured_at
  - `check_drift(baseline_id)` → `OK / DRIFT / STRUCTURE_MISSING`
  - `refresh(baseline_id, note)`：重钉当前版本并更新 hash/captured_at

- [x] C4 读写接入
  - create/update 守卫：项目 `design_mode='standard'`；`structure_id` 属同一 `item_id/usage/alternative_no`；键唯一
  - `check_drift` 动作（`action_ref` 完整权限码）；列表只展示存储 hash，不逐行实时算

- [x] C5 单测 `meta/tests/test_project_structure_baseline.py`
  - 哈希稳定性（行顺序/数值格式/布尔）
  - 版本切换 → DRIFT；显式钉住版本内容改动 → DRIFT；结构缺失 → STRUCTURE_MISSING
  - 非法 `structure_id` / 非 standard 项目 / 同键重复 → 400
  - `refresh` 后 drift 归 OK

- [x] C6 验收
  - `python d:\filework\test.py --single meta/tests/test_project_structure_baseline.py`
  - `test_inventory_schema.py` / `test_schema_sync` 回归

---

## 阶段 D：回归与文档

- [ ] D1 P2-3 `v211__project_cost_view.py` 后置
  - 待成本价/费率口径确认；`amount` 未就绪时 `cost_status='pending_rate'`

- [x] D2 回归
  - `test_sales_order_guard.py` / `test_sales_order_fulfillment_status.py`
  - `test_inventory_reservation_service.py` / `test_inventory_atp.py` / `test_demand_trace_service.py`
  - `test_purchase_order_guard.py` / `test_demand_allocation_schema.py`
  - `test_inventory_schema.py` / `test_inventory_segment_migration.py`

- [x] D3 文档同步
  - 规格 §4 状态改为「已实施」；§5 迁移状态更新
  - 记录验收结果与偏差

---

## 验收用例

| # | 场景 | 期望 |
|---|---|---|
| P2-AC1 | SO 行仅填任务不填项目 | 400 `SO_LINE_TASK_PROJECT_REQUIRED` |
| P2-AC2 | 任务属项目 A，行/抬头项目 B | 400 `PROJECT_TASK_PROJECT_MISMATCH` |
| P2-AC3 | 任务状态 `done` 或类型 `phase` | 400 `PROJECT_TASK_NOT_EXECUTABLE` |
| P2-AC4 | 行项目与抬头项目不一致 | 400 `SO_LINE_PROJECT_MISMATCH` |
| P2-AC5 | `so_segment_enabled=1` 物料行挂任务 | 400 `SO_LINE_SEGMENT_TASK_CONFLICT` |
| P2-AC6 | 任务行创建 MTO 预留 | 预留落 `project_task` 段；`available_on_hand` 按该段计算 |
| P2-AC7 | 取消任务行 / 取消订单 | 预留释放；任务段空余额被清理；`qty_reserved` 投影一致 |
| P2-AC8 | 基线：结构换版后查询 | `DRIFT`；`refresh` 后 `OK` |
| P2-AC9 | 基线：`structure_id` 指向他物料结构 | 400 |
| P2-AC10 | 基线：engineered 项目创建 | 400（仅 standard 允许） |

---

## 实施顺序与依赖

1. A（v208 + 守卫）→ B（预留/发运维度）
2. C（v209 基线，可与 B 并行）
3. D（P2-3 后置；回归与文档）

依赖：INV-2 `v205` 段/预留已就绪；共享 `project_task_guard` 已就绪（v207 任务轴索引）。

---

## 风险

| # | 风险 | 处置 |
|---|---|---|
| R1 | SO 段与任务段静默降级 | A3 直接拒绝组合，不做优先级兜底 |
| R2 | 发运出库维度缺失导致扣错段 | B3 复制维度 + 文档标注；过账接入时强制校验 |
| R3 | 结构基线 hash 逐行实时算导致列表慢 | 列表只展示存储 hash，detail / 动作实时算 |
| R4 | `item_structures` 原地改行无法审计 | hash 可检测；要求结构行编辑留审计，或只允许换 revision |

---

## 验收结果（2026-11-04）

| 用例 / 套件 | 结果 |
|---|---|
| `test_sales_order_line_project_task.py`（A4 新增 14 例，R1-R5 正反例） | 14 passed |
| `test_sales_order_guard.py` 回归 | 34 passed |
| `test_sales_order_fulfillment_status.py` 回归 | 34 passed，1 failed（既有失败：INV-1 单写者扫描误判 fulfillment writer，与 P2 无关） |
| `test_inventory_reservation_service.py`（含任务段预留 / 取消释放 2 例） | 全通过 |
| `test_mto_consignment_flow.py`（含任务行端到端 1 例） | 全通过 |
| `test_shipment_service.py`（含 `project_task_id` 继承 1 例） | 全通过 |
| `test_project_structure_baseline.py`（15 例） | 15 passed |
| `test_inventory_schema.py` / `test_schema_generator.py` / `test_bo_action_contract.py` | 全通过 |
| `test_inventory_atp.py` / `test_demand_trace_service.py` | 3 / 6 passed |
| `test_purchase_order_guard.py` / `test_demand_allocation_schema.py` | 29 / 20 passed |
| `test_inventory_segment_migration.py` / `test_app_builder.py` | 7 / 22 passed |
| `tools/migration_lint.py`（仅新增 v209 / v210） | 0 FAIL / 0 WARN |

偏差记录：

1. **迁移编号**：`v208` 在实施期间被并发会话的 `v208__work_order_project_task.py` 占用，SO 行字段顺延为 `v210`，结构基线为 `v209`；成本视图顺延 `v211`。
2. **P2-2 结构基线**：迁移 / schema / 服务 / BO Action / 单测由并发会话同步落地，本会话复核其接口并通过全部用例；权限码采用 `project_structure_baseline:{check_drift,refresh}`。
3. **B3 发运维度**：`shipment_lines` 只有 `project_task_id` 列（`project_id` 在抬头，G6）；发运当前无自动库存过账，接入出库过账时必须携带抬头 `project_id` + 行 `project_task_id`。
4. **A3 归一化**：行 `project_id` 为空时仅用抬头项目做校验归一化，不回写行字段；抬头也无项目时拒绝挂任务（P2-AC1）。
