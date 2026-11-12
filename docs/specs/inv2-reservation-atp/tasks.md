# INV-2 任务分解：库存段、预留与 ATP

- 规格：`docs/specs/inv2-reservation-atp/spec.md`
- 迁移：v205
- 状态：**已实施**（2026-11-04，阶段 A→I 完成；未 commit）
- 测试入口：`python d:\filework\test.py --single <path>`

---

## 阶段 A：S1 段铺底（迁移 v205）

- [x] A1 新建 `meta/migrations/v205__inventory_segment_reservation.py`
  - `MIGRATION_NAME = 'v205__inventory_segment_reservation'`
  - `inventory_transactions` / `inventory_balances` 各加 5 列
  - 建 `inventory_reservations` / `demand_trace_links`
  - 注册枚举：`stock_segment_type` / `inventory_reservation_status` / `inventory_peg_type` / `demand_object_type` / `demand_trace_type`
  - 5 条权限 + 2 个菜单（`inventory-reservation-list` / `demand-trace-link-list`）
  - `items` 加 `so_segment_enabled` / `consignment_enabled` / `hard_peg_default` / `valuation_relevant`（boolean，默认 false/false/false/true）
  - 验收：重复执行 `[SKIP]`；`migration_lint` 无重复版本；`migration_runner --dry-run` 顺序为 v204 → v205
- [x] A2 余额唯一键重建
  - 新键：`(org_id, location_id, item_id, batch_id, stock_status, stock_segment_type, project_id, project_task_id, sales_order_line_id, owner_party_id)`
  - 先建新索引 → 回填 `owned` + 0 哨兵 → 删旧索引
  - 验收：存量行数不变；`rebuild_balances` 结果与 INV-1 一致
- [x] A3 存量回填
  - 事务/余额全部置 `stock_segment_type='owned'`，伙伴列 0
  - 不猜测历史项目；输出待清洗计数
  - 验收：`SELECT count(*) WHERE stock_segment_type IS NULL` 为 0

## 阶段 B：Schema 与对象

- [x] B1 `meta/schemas/inventory_transaction.yaml` / `inventory_balance.yaml` 加 5 段字段，余额 `business_key` 同步
- [x] B2 `meta/schemas/items.yaml` 加 4 个字段（`fieldGroup: 库存段`，位置 240+）
- [x] B3 新建 `meta/schemas/inventory_reservation.yaml`（列表字段：预留号/物料/组织/需求节点/段/数量/状态/钉类型）
- [x] B4 新建 `meta/schemas/demand_trace_link.yaml`（列表字段：供应节点/需求节点/类型/分配量/计划版本）
- [x] B5 单据行补 `project_task_id`（仅 `receipt_line` / `shipment_line`，若已有则跳过）
  - **不含 `purchase_order_line`**：该对象按 T-D3 / D6 明确禁止行级单值项目/任务引用，采购归属只走 `demand_allocation`
  - **不含 `work_order_line`**：仓库无此对象（工单任务轴走 `work_orders.source_demand_type='project_task'`）
  - 验收：`sync_schema_from_meta` 后 `PRAGMA table_info` 可见

## 阶段 C：段解析与过账

- [x] C1 新建 `meta/services/stock_segment_service.py`
  - `resolve_segment` / `validate_segment` / `segment_key` / `transfer_segment` / `assert_cross_segment_allowed`
  - 优先级：寄售 > 项目任务 > SO 段 > owned
  - `ensure_root_task(project_id)`：项目无任务时自动建根任务（D5），有任务则复用
  - 验收：单测覆盖 5 类段与非法组合；`customer_owned` 一律拒绝
- [x] C2 扩展 `meta/services/inventory_posting_service.py`
  - `_insert_transaction` / `_apply_balance` 写 5 列
  - `on_hand` 支持段过滤；`rebuild_balances` 按新键
  - 出库按段校验可用量
  - 验收：现有 INV-1 测试全绿
- [x] C3 段转移事务
  - 成对出入、`transfer_group_id`、原因/审批字段
  - 禁止普通收发模拟
  - 验收：数量守恒；跨段未授权报 `INV_CROSS_SEGMENT_DENIED`
  - 实现：`StockSegmentService.transfer_segment` / `consume_consignment`；单测 `test_inventory_segment_posting.py` 覆盖

## 阶段 D：S2 预留与 ATP

- [x] D1 新建 `meta/services/inventory_reservation_service.py`
  - `create_reservation`（`reservation_key` 幂等）/ `release_reservation` / `fulfill_reservation` / `expire_reservations` / `atp`
  - 状态机：open → partially_fulfilled → fulfilled / cancelled / expired
  - 验收：超量报 `INV_RESERVATION_QTY_EXCEEDED`；硬钉冲突报 `INV_HARD_PEG_CONFLICT`
- [x] D2 可用量口径
  - v1 只实现 `available_on_hand(segment) = on_hand(segment) - open/partially_fulfilled reservations(segment)`
  - `atp(segment, include_inbound=false)` 保留接口；`expected_receipts` 恒为 0，接入计划后另行开启
  - soft 在公共池扣减；hard 在目标段扣减
  - 验收：跨段不串池；非估值段同样扣减；`include_inbound=false` 时不得返回在途量
- [x] D3 销售订单接入
  - MTO：创建预留（`hard_peg_default` 决定 hard/soft）
  - `so_segment_enabled=1`：创建 SO 段预留
  - 取消订单/行：释放预留
  - 验收：MTO 标准不建段；SO 段只对该行可用

## 阶段 E：S3 需求线索

- [x] E1 新建 `meta/services/demand_trace_service.py`
  - `link_supply_demand` / `unlink` / `inherit_from_document` / `trace_end_demand`
  - 校验数量上限与节点类型
  - 验收：多对多、部分分配、超量报 `INV_TRACE_QTY_EXCEEDED`
- [x] E2 单据继承
  - 收货/发运/工单/调拨从即时来源与预留推导 trace
  - 发运核销预留并关闭 trace
  - 验收：PO → 库存 → 发运 → SO 行可端到端追溯
  - 实现：发运已接入（`shipment_service.ship_confirm`）；收货/工单/调拨本期只提供 `inherit_from_document` 服务 API，未接入单据流程

## 阶段 F：S4 SO 专用段

- [x] F1 物料策略开关生效
  - `so_segment_enabled=1` 且 SO 行存在时建 SO 段
  - 未开启时传 SO 段报 `INV_SO_SEGMENT_DISABLED`
  - 验收：MTS/MTO 标准不受影响
- [x] F2 SO 段生命周期
  - 取消/余料：显式转移至 `owned`
  - 退货：优先回原 SO 段
  - 验收：段转移留原因与快照
  - 实现：统一走 `transfer_segment`（原因/备注写入事务 remark）；退货由调用方显式传原 SO 段

## 阶段 G：S5 供应商寄售

- [x] G1 寄售收货
  - `consignment_enabled=1` + `owner_party_id` → `supplier_consignment`
  - 收货不产生库存金额（只留 `valuation_relevant=0`）
  - 验收：缺供应商报 `INV_CONSIGNMENT_OWNER_REQUIRED`
- [x] G2 寄售消耗
  - 所有权转移事务：`supplier_consignment → owned`
  - 生成计价标记（金额交 INV-5）
  - 验收：数量守恒；原寄售段余额归零
- [x] G3 客供料
  - 仅建枚举与字段，不实现；`customer_owned` 任何写入一律报 `INV_SEGMENT_INVALID`（负向测试）

## 阶段 H：拦截器、权限与菜单

- [x] H1 段不可变守卫：拦截直接改余额段/事务段
  - 实现：`inventory_balance` / `inventory_transaction` schema 仅声明 read/list（无 create/update/delete 路由），无 BO 写入路径，无需新增拦截器
- [x] H2 预留与线索动作权限接入（`action_ref` 用完整权限码）
  - 实现：`inventory_reservation_guard_interceptor.py`（priority=60）委托服务；create 回填、update 仅允许 cancel、delete 仅允许终态
- [x] H3 菜单/列表可见性验证（只读列表 + 释放动作）
  - 实现：v205 注册 2 菜单 + 5 权限，`required_permissions` 自动生效

## 阶段 I：测试与文档

- [x] I1 `meta/tests/test_inventory_segment_migration.py`（v205 + 幂等 + 回填）
- [x] I2 `meta/tests/test_inventory_segment_posting.py`（4 类段过账 + 重建 + 负库存）
- [x] I3 `meta/tests/test_inventory_reservation_service.py`（幂等/释放/核销/状态机/硬钉）
- [x] I4 `meta/tests/test_inventory_atp.py`（按段 ATP + 跨段隔离）
- [x] I5 `meta/tests/test_demand_trace_service.py`（多对多/部分分配/上限/端到端）
- [x] I6 `meta/tests/test_mto_consignment_flow.py`（MTO/SO 段/ETO/寄售）
- [x] I7 回归：`test_inventory_schema.py` / `test_inventory_posting.py` / `test_inventory_receipt_bridge.py` / `test_inventory_transfer_bridge.py` / P6b 序列号测试
  - 结果：schema 12/12、posting 23/23、receipt bridge 通过、transfer bridge 9/9、序列号 9/9 + 5/5 + 7/7
- [x] I8 同步 `spec.md` 状态、决策记录与验收结果
- [x] I9 `qty_reserved` 投影一致性：建/释放/核销预留后 `rebuild_reserved_qty` 结果 = 预留表汇总；余额手动写该列被拒
  - 实现：`InventoryPostingService.rebuild_reserved_qty` 由 `inventory_reservations` 回写；预留服务每次状态变更后触发
- [x] I10 `ensure_root_task`：无任务项目自动建根任务；有任务复用；跨项目借用被拒
- [x] I11 `demand_trace` 与 `demand_allocation` 边界：采购行项目任务仍只出现在 `demand_allocation`，trace 表不重复写入
  - 实现：`test_demand_trace_service.py::test_trace_does_not_duplicate_demand_allocation_project_task`

## 实施细化（决策完成版）

> 本节锁定实现细节；改动范围仅限下列文件，不新增单据框架、不改 v201–v204。

### R1 迁移 `meta/migrations/v205__inventory_segment_reservation.py`

结构（与 v201/v202 风格一致：`sqlite3` + `Path`，幂等打印 `[SKIP]`）：

| 常量/函数 | 内容 |
|---|---|
| `MIGRATION_NAME` | `'v205__inventory_segment_reservation'` |
| `SEGMENT_COLUMNS` | `(stock_segment_type VARCHAR(20) NOT NULL DEFAULT 'owned', project_id/project_task_id/sales_order_line_id/owner_party_id INTEGER NOT NULL DEFAULT 0)` |
| `NEW_BALANCE_INDEX` | `uq_inv_balance_segment`，10 列（规格 §3.2） |
| `OLD_BALANCE_INDEX` | `uq_inv_balance_key`（5 列，迁移末尾 DROP） |
| `RESERVATION_TABLE` / `TRACE_TABLE` | `inventory_reservations` / `demand_trace_links`（DDL 见规格 §3.3/§3.4；**不建表级 CHECK**，段合法性由 `validate_segment` 校验） |
| `ENUM_SEEDS` | 5 个类型：`stock_segment_type` / `inventory_reservation_status` / `inventory_peg_type` / `demand_object_type` / `demand_trace_type`（`enum_types` + `enum_values`，与 v202 `_do_enums` 同构） |
| `apply_segment_schema(conn)` | 公开函数：列、新表、新索引、回填、删旧索引、items 4 列；`migrate()` 与测试替身都调用它 |
| `migrate(db_path, skip_backup=True)` | 顺序：`apply_segment_schema` → 枚举 → 权限 → 授权 → 菜单 → 参数 |
| `verify(db_path)` | 断言 10 列/2 新表/新索引存在+旧索引不存在/枚举/权限/菜单/参数/`items` 4 列 |
| `rollback(db_path)` | 删新表、新索引、枚举值、权限、菜单、参数；恢复 `uq_inv_balance_key`；段列保留（SQLite 不支持安全 DROP COLUMN，注释说明） |

要点：
- 先 `ALTER TABLE ... ADD COLUMN`（默认值即完成 A3 回填，无需 UPDATE）；再建新唯一索引；最后 `DROP INDEX IF EXISTS uq_inv_balance_key`（新键为旧键超集，建索引不会冲突）。
- 余额表若不存在则跳过（`[SKIP]`），保证空库可迁移。
- `items` 4 列：`so_segment_enabled` / `consignment_enabled` / `hard_peg_default` / `valuation_relevant`，默认 `false/false/false/true`（统一 boolean，不用 0/1）。
- 权限 5 条按规格 §5；授权 `admin` + `default`；菜单 2 个挂 `procurement`（`sort_order` 7/8，`show_in_sidebar=0`，`page_type=object_list`，primary 分别 `inventory_reservation` / `demand_trace_link`）。
- 参数 5 个按规格 §5，`domain='procurement'`，`target_bo` 分别 `inventory_reservation` / `inventory_balance`。

### R2 Schema 与测试替身

| 文件 | 改动 |
|---|---|
| `meta/schemas/inventory_transaction.yaml` / `inventory_balance.yaml` | 加 5 字段；余额 `business_key` 改 10 列 |
| `meta/schemas/items.yaml` | 加 4 字段（`fieldGroup: 库存段`，position 240+） |
| `meta/schemas/inventory_reservation.yaml` / `demand_trace_link.yaml` | 新建，字段/权限与规格一致 |
| `meta/schemas/{receipt_line,shipment_line}.yaml` | 补 `project_task_id`（已存在则跳过）；`purchase_order_line` / `work_order_line` 不动（前者 T-D3，后者不存在） |
| `meta/tests/inventory_test_doubles.py` | `_install_tables` 末尾调用 `v205.apply_segment_schema(conn)`；`install_inventory` 同 |
| `meta/tests/test_inventory_schema.py` | 唯一索引断言由 `uq_inv_balance_key` 改为 `uq_inv_balance_segment`（规格要求重建键，属预期变更） |

### R3 服务 API（签名锁定）

`meta/services/stock_segment_service.py`：

```python
class StockSegmentService:
    def resolve_segment(self, doc_ctx: dict) -> dict
    def validate_segment(self, segment: dict) -> dict
    def segment_key(self, segment: dict) -> dict
    def transfer_segment(self, payload: dict) -> dict   # 成对出/入 + transfer_group_id
    def assert_cross_segment_allowed(self, from_seg: dict, to_seg: dict, ctx: dict) -> None
```

- `resolve_segment` 返回 `{'stock_segment_type','project_id','project_task_id','sales_order_line_id','owner_party_id'}`，优先级寄售 > 项目任务 > SO 段 > owned。
- 错误码严格用规格 §6；段不可变仅由守卫（R6）拦截。

`meta/services/inventory_reservation_service.py`：

```python
class InventoryReservationService:
    def create_reservation(self, payload: dict) -> dict
    def release_reservation(self, reservation_id: int, reason: str = '') -> dict
    def fulfill_reservation(self, reservation_id: int, qty: float, tx_id: int = 0) -> dict
    def expire_reservations(self, now: str | None = None) -> int
    def atp(self, query: dict, include_inbound: bool = False) -> dict
        # {'on_hand','reserved','available_on_hand'}；include_inbound=false 时 expected_receipts 恒 0
```

- `available_on_hand = on_hand - sum(open/partially_fulfilled reservations)`，按 `segment_key` 精确匹配。
- `inventory_reservations` 是预留量唯一事实源；`inventory_balances.qty_reserved` 只是投影（见 `rebuild_reserved_qty`）。
- `qty_reserved`/`qty_fulfilled` 用 REAL，累加校验 ≤ `qty_reserved`。

`meta/services/demand_trace_service.py`：

```python
class DemandTraceService:
    def link_supply_demand(self, payload: dict) -> dict
    def unlink(self, link_id: int, reason: str = '') -> None
    def inherit_from_document(self, doc: dict) -> list
    def trace_end_demand(self, supply_node: dict) -> list
```

`meta/services/inventory_posting_service.py`（改，不重写）：

- `_insert_transaction(normalized, ...)` 增加 5 列绑定；
- `_apply_balance(normalized)` 的 `ON CONFLICT` 与 INSERT 用 10 列键；
- `_current_qty(normalized)` 与 `on_hand(...)` 增加 `segment` 过滤参数（默认 `owned` 全 0）；
- `rebuild_balances(org_id=None)` 按含段键重建；随后调用 `rebuild_reserved_qty(org_id=None)`；
- `rebuild_reserved_qty(org_id=None)`：由 `inventory_reservations` 汇总 `open/partially_fulfilled` 回写余额 `qty_reserved`（唯一写入口，禁止其他代码写该列）；
- `reverse()` 反冲分录继承原段（从 `_load_transaction` 读取 5 列）。

`meta/services/inventory_guard_service.py`：`normalize_entry` 透传 5 个段字段（默认 owned/0）。

### R4 单据接入（只改既有函数，不加新框架）

| 文件 | 接入点 |
|---|---|
| `meta/services/receipt_service.py` | 收货过账前 `resolve_segment`，按 PO 行/项目任务/寄售供应商写段；收货行继承 |
| `meta/services/transfer_order_service.py` | 调拨段随行；跨段默认拒绝（参数 `inventory.allow_cross_project_issue`） |
| `meta/services/inventory_adjustment_service.py` / `inventory_count_service.py` | 按段调整/盘点，不改段类型 |
| `meta/services/sales_order_fulfillment_service.py` | 发运核销预留 + 写 trace；SO 段只允许所属行 |
| `meta/services/sales_order_service.py`（若存在）或 `sales_order_guard_service.py` | 建/改/取消订单行时 `create_reservation` / `release_reservation`；`so_segment_enabled=1` 才建 SO 段 |

- 接入前先 Grep 定位实际函数名，禁止编造；找不到对应钩子则该单据只保留服务 API，并在 tasks 勾选处标注“未接入”。
- 所有段解析只能走 `StockSegmentService.resolve_segment`。

### R5 测试与验证（逐文件串行）

```powershell
python d:\filework\test.py --single meta/tests/test_inventory_segment_migration.py
python d:\filework\test.py --single meta/tests/test_inventory_segment_posting.py
python d:\filework\test.py --single meta/tests/test_inventory_reservation_service.py
python d:\filework\test.py --single meta/tests/test_inventory_atp.py
python d:\filework\test.py --single meta/tests/test_demand_trace_service.py
python d:\filework\test.py --single meta/tests/test_mto_consignment_flow.py
python d:\filework\test.py --single meta/tests/test_inventory_schema.py
python d:\filework\test.py --single meta/tests/test_inventory_posting.py
```

- 迁移验收 `python -m ... migration_runner --dry-run` 若存在；否则用 test 内直接 `migrate()` + 重复执行断言 `[SKIP]`。
- 全部完成前不 commit（用户未授权）。

### R6 守卫与权限（阶段 H）

`meta/core/interceptors/` 增加最小只读校验（不建新拦截器框架）：余额/事务 UPDATE 语句含段列时抛 `INV_SEGMENT_IMMUTABLE`；动作 `action_ref` 使用规格 §5 完整权限码。菜单可见性靠 `required_permissions` 自动生效，不做前端改动。

## 依赖顺序

```text
A → B → C → D → E → F → G → H → I
```

- C 完成前不做 D；E 依赖 D 的预留；F/G 依赖 C/E；I 按阶段逐文件跑，不集中到最后。

## 验收命令

```powershell
python d:\filework\test.py --single meta/tests/test_inventory_segment_migration.py
python d:\filework\test.py --single meta/tests/test_inventory_segment_posting.py
python d:\filework\test.py --single meta/tests/test_inventory_reservation_service.py
python d:\filework\test.py --single meta/tests/test_inventory_atp.py
python d:\filework\test.py --single meta/tests/test_demand_trace_service.py
python d:\filework\test.py --single meta/tests/test_mto_consignment_flow.py
```
