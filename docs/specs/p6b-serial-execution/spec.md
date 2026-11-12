# P6b 序列号执行层（INV-3 细化）Spec

> 版本：v1.1（2026-11-04）
> 状态：已确认（用户 2026-11-04 批准方案 1A / 2A / 3A，按本版实施）
> 前置：P6a 序列号对象模型（`docs/specs/p6-serial-number-model/spec.md`，迁移 `v202__serial_number_model.py`）已实施；INV-4 库存调整/盘点（`v203__inventory_adjustment.py`）已实施
> 定位：P6a 只回答「序列号是什么、怎么建档、怎么录/发」；P6b 回答「调拨 / 调整 / 盘点 / 退货 / 发货时建档 在各单据的哪个时点、由谁、按什么规则写序列号事件」

---

## 1. 背景与目标

P6a 已把收货、发运两条链路的序列号登记打通（`register_receipt` / `register_shipment`），但其余单据仍只动数量账，序列号主档与事件账不会跟随，导致：

- 调拨发货后，序列号仍显示「在库」，实际已在途；
- 调整单做 `status_transfer` / 报废 / 盘亏时，序列号质量状态与库存桶不一致；
- 盘点差异无法定位到具体是哪几个号盘亏/盘盈；
- 仅发货管理模式（`require_on_issue=1` 且 `require_on_receipt=0`）的物料发货时无法建档。

**目标**：在 P6a 的模型与 `SerialNumberService` 之上补齐执行层，做到「数量账动、序列号事件同步动；数量账反冲、序列号事件同步反冲」。

**非目标（本阶段不做）**：

- 退货单据本体（RMA）：当前仓库无退货单据，P6b 只提供 `return_serial`（`issued→returned→in_stores`）与事件，不新建单据、不建表；
- 调拨收货单据本体：不新建收货单据，复用「TO 来源收货单过账」链路；P6b 在该链路内实现 `register_transfer_receipt`（`in_transit→in_stores`）；
- P6c 谱系落地（完工成品号、组件单父谱系、`relation_type=assembly`）；
- P7 全局唯一 / UII 合规；
- 序列号级预留、拣货拆号（与 P5 D12 同口径）。

---

## 2. Oracle / SAP 对标结论（用于定口径，不照搬）

| 议题 | Oracle EBS | SAP EWM/MM | 本系统口径 |
|---|---|---|---|
| 序列号归属 | 组织/子库存/库位维度 | 设备号 + 库存地点 | 沿用 P6a：`org_id` + `current_location_id`（不引入子库存） |
| 调拨 | 发货即转出子库存，序列号随行 | 转储单两步（转出/转入），序列号随物料凭证 | 发货写 `transfer_out`（`in_stores→in_transit`），收货落地后再写 `transfer_in` |
| 调整 / 状态变更 | 序列号状态与库存桶可分别调整 | 序列号状态随库存状态（`EQBS`） | 序列号是质量状态权威载体：`status_transfer` 必须同步 `quality_status`；批次仍不随调（INV-4 TBD-5） |
| 报废 | 序列号置报废终态 | 报废为终态 | `scrapped` 终态；写 `scrap` 事件 |
| 盘点 | 按号盘点，一號一数量 | 序列号库存盘点逐号核对 | 数量账仍按桶；差异行在提交时强制登记号（盘亏选号 / 盘盈录号） |
| 仅发货建号 | 发货时校验已存在号，不建号 | 按序列号参数决定是否发货建档 | 支持 `issue_created`（P6a 已预留枚举） |
| 红冲 | 反向事务自动反向序列号事件 | 冲销凭证反向对象清单 | 统一走 `reverse_serial_event(inventory_transaction_id)` |

**关键结论**：序列号与批次在「质量状态是否随库存桶变化」上不同——批次是聚合维度，TBD-5 已定不同步；序列号是单件实体，必须同步，否则单件状态失去意义。

---

## 3. 关键决策（本 Spec 已定）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 序列号 `quality_status` 是单件质量状态的唯一真源；库存调整 `status_transfer` 必须同步 | 单件可追溯是序列号存在的目的；与批次「聚合不同步」不矛盾 |
| D2 | 单据-序列号关系统一写 `document_serial_links`，`doc_type` 扩为 `transfer_order` / `inventory_adjustment` / `inventory_count` | 沿用 P6a D6，避免 N 张单据子表 |
| D3 | 调拨发货写 `transfer_out`（`in_stores→in_transit`）；TO 来源收货单过账时写 `transfer_in`（`in_transit→in_stores`，同时迁移 `org_id` / 库位） | 已批准的 1A：收货走既有 TO 收货桥接，不新建单据 |
| D4 | 调整减少 / 报废必须逐号：`qty_decrease → scrapped`，`scrap → scrapped`；增加 / 期初按号激活 `defined` 或按 `source_type=opening` 建档后置 `in_stores`；`status_transfer` 只切 `quality_status` | 已批准口径：减少与报废统一终态，状态转移走质量轴 |
| D5 | 盘点不新增 `serial_id` 列：差异号的登记存 `document_serial_links`（`doc_type=inventory_count`），盘点过账生成调整单时不复制链接 | 已批准 3A：单据行只加 `serial_no` 快捷列，qty>1 走链接；盘点过账直接写序列号事件 |
| D6 | `issue_created` 在发货登记时先建主档（`source_type=issue_created`）再写 `ship` 事件；建档数量必须等于本行数量 | P6a 已预留该枚举，仅补执行 |
| D7 | 所有 P6b 事件都回填 `serial_transactions.inventory_transaction_id`，用来源事件键定位数量事务 | 落实 P6a D5 的桥接契约 |
| D8 | 单据取消/草稿作废只解除链接，不写事件；已过账单据红冲走 `reverse_serial_event` | 与 INV-4 单据生命周期一致 |
| D9 | 幂等键 = `(serial_id, txn_type, doc_type, doc_id, line_id)`；重复登记直接跳过 | P6a 现有查重口径，扩展到新单据 |
| D10 | `change_status` 作为 `serial_number` 的独立动作暴露，权限复用 `serial_number:serial_number_update`；若后续要求独立权限再追加迁移 | 与 INV-4 行删除复用 `_update` 同口径，本阶段零迁移 |
| D11 | 三张单据行（调拨 / 调整 / 盘点）新增 `serial_no`（可空，max_length=200），仅 `qty=1` 快捷录入；`qty>1` 必须走 `document_serial_links` | 已批准 3A：不改数量账、不建单据子表，保持与 P6a D7 一致 |
| D12 | 质量状态白名单三值自由流转（`unrestricted↔inspection↔blocked`），只改 `quality_status` 并写 `status_change` 事件 | 已批准：用途轴与质量轴解耦；`scrapped` 号禁止变更 |

**迁移结论**：`serial_numbers` / `serial_transactions` / `document_serial_links` 三表已由 v202 建好，`txn_type` CHECK 已包含 `transfer_out / transfer_in / return / adjust / status_change / scrap`，`source_type` 已包含 `issue_created`。**P6b 不需要新迁移**。

D11 的单据行 `serial_no` 亦无需新迁移：`inventory_adjustment_line.yaml` / `inventory_count_line.yaml` / `transfer_order_line.yaml` 三份 YAML **均已声明** `serial_no`（`max_length: 200`），生产库由平台 `sync_schema_from_meta`（`meta/core/app_registry.py::sync_schema_from_meta` / `meta/tools/sync_schema.py`）在启动/初始化时补列。**测试替身例外**：内存 SQLite 不会跑 sync_schema，测试建表时必须显式带 `serial_no VARCHAR(200)` 列，否则相关断言会失败（这是测试夹具责任，不是产品代码分支）。

---

## 4. 数据与关系

### 4.1 复用（不改）

- `serial_numbers`：主档，投影字段 `usage_status` / `quality_status` / `current_location_id` / `batch_id`。
- `serial_transactions`：事件账；`txn_type` 取值 `transfer_out` / `transfer_in` / `adjust` / `status_change` / `scrap` / `ship` / `return`；新增使用 `inventory_transaction_id` 桥接。
- `document_serial_links`：`(doc_type, doc_id, line_id, serial_id, direction)`，`direction ∈ {in, out}`。

### 4.2 `doc_type` 与 `direction` 约定

| 单据 | `doc_type` | `doc_id` | `line_id` | `direction` | 事件类型 |
|---|---|---|---|---|---|
| 调拨发货 | `transfer_order` | 调拨单头 ID | 调拨行 ID | `out` | `transfer_out` |
| 调拨收货（未来） | `transfer_order` | 调拨单头 ID | 调拨行 ID | `in` | `transfer_in` |
| 调整-增加/期初 | `inventory_adjustment` | 调整单头 ID | 调整行 ID | `in` | `adjust` |
| 调整-减少/报废 | `inventory_adjustment` | 调整单头 ID | 调整行 ID | `out` | `adjust` / `scrap` |
| 调整-状态转移 | `inventory_adjustment` | 调整单头 ID | 调整行 ID | 不写链接 | `status_change` |
| 盘点-盘盈 | `inventory_count` | 盘点单头 ID | 盘点行 ID | `in` | `adjust` |
| 盘点-盘亏 | `inventory_count` | 盘点单头 ID | 盘点行 ID | `out` | `adjust` |
| 盘点差异生成的调整单 | `inventory_adjustment` | 调整单头 ID | 调整行 ID | 继承盘点行链接方向 | `adjust` |
| 发货时建档 | `shipment` | 交货单头 ID | 交货行 ID | `out` | `ship` |
| 退货（未来） | `return` | 退货单头 ID | 退货行 ID | `in` | `return` |

> 盘点差异调整单的链接按「盘点行 → 调整行」转移：`doc_type` 改为 `inventory_adjustment`、`line_id` 改为调整行 ID、`doc_id` 改为调整单 ID；原 `inventory_count` 链接保留只读追溯，不删除。

---

## 5. 功能需求

### FR-001 调拨发货（transfer_order ship）

- **WHEN** 调拨单执行 `ship`，且 `items.serial_tracked=1`
- **THEN**
  1. 每个本次发运行必须通过 `document_serial_links(doc_type=transfer_order, line_id=调拨行)` 或行内 `serial_no`（qty=1）选定序列号；
  2. 号数量必须等于本次发货数量（否则 `SERIAL_TRANSFER_COUNT_MISMATCH`）；
  3. 号必须属于调出组织且当前 `usage_status=in_stores`（否则 `SERIAL_NOT_AVAILABLE`）；
  4. 写 `transfer_out` 事件：`usage in_stores→in_transit`、`org/location from=调出方`、`to` 为空、`inventory_transaction_id` = 对应 `ISSUE_TO_SHIP` 事务；
  5. 主档更新 `usage_status=in_transit`、`current_location_id=NULL`；
  6. 与调拨发货数量事务同一 `ds.transaction()`，失败整体回滚。

### FR-002 调整-状态转移（inventory_adjustment status_transfer）

- **WHEN** 调整单 `adjustment_type=status_transfer` 过账，且物料启用序列号
- **THEN**
  1. 调整行必须选定号（数量=行数量），每个号的 `quality_status` 必须等于行 `from_stock_status`（否则 `SERIAL_STATUS_PAIR_INVALID`）；
  2. 逐号 `quality_status: from→to`，写 `status_change` 事件（`quality_from/quality_to`）；
  3. **不同步** `batches.quality_status`（与 INV-4 TBD-5 一致）；
  4. 不写 `document_serial_links` 的 `direction` 链接（内部状态变化，不是出入库）；
  5. 序列号 `usage_status` 不变（仍在库）。

### FR-003 调整-减少 / 报废

- **WHEN** `qty_decrease` 或 `scrap` 过账
- **THEN**
  1. 必须逐号选定（`SERIAL_ADJUST_COUNT_MISMATCH` 否则）；
  2. 号的当前状态必须 `in_stores` 且 `quality_status` 等于行 `from_stock_status`；
  3. `qty_decrease`：`usage in_stores→scrapped`，写 `scrap` 事件并置 `scrapped_at`；
  4. `scrap`：`usage in_stores→scrapped`，写 `scrap` 事件并置 `scrapped_at`；`scrapped` 为终态；
  5. 两种类型都写 `document_serial_links(direction='out')`；
  6. 行的 `reason_code/reason_text` 必填校验沿用 INV-4。

### FR-004 调整-增加 / 期初

- **WHEN** `qty_increase` / `opening` 过账
- **THEN**
  1. 可按行内 `serial_no` 快捷录入（qty=1）或链接既有 `defined` 号；
  2. 号不存在时按 `source_type=opening` 自动建档，`usage_status` 置 `in_stores`、`quality_status` 取行 `to_stock_status`、`current_location_id` 取行库位；
  3. 序列号数量必须等于行数量（否则 `SERIAL_ADJUST_COUNT_MISMATCH`）；
  4. 写 `adjust` 事件与 `direction='in'` 链接。

### FR-005 盘点差异号登记（inventory_count）

- **WHEN** 盘点单 `post`（审批后过账）且物料启用序列号
- **THEN**
  1. `variance_qty ≠ 0` 的行必须登记差异号：
     - 盘亏（`variance<0`）：选号数量 = `|variance|`，号必须当前 `in_stores`、质量状态 = 行 `stock_status`；
     - 盘盈（`variance>0`）：录入数量 = `variance`，号不得与现有主档重复；
  2. 盘亏选号存 `document_serial_links(doc_type=inventory_count, direction='out')`；盘盈录号存 `direction='in'`；
  3. 未登记齐 → `SERIAL_COUNT_SERIAL_REQUIRED`（过账前置校验）；
  4. 无差异行不要求登记号；
  5. `cancel` 只删除 `document_serial_links`，不写事件。

### FR-006 盘点差异过账

- **WHEN** 盘点单 `post`
- **THEN**
  1. 生成本次数量事务（`source_doc_type=inventory_count`）后，逐行写序列号事件：
     - 盘亏：`in_stores→scrapped`，写 `scrap` 事件；
     - 盘盈：按 `source_type=opening` 建档后置 `in_stores`，写 `adjust` 事件；
  2. 事件回填 `inventory_transaction_id` = 对应盘点数量事务；
  3. 由 `inventory_count` 生成调整单的链接不复制、不改写，盘点链接保留追溯。

### FR-007 发货时建档（issue_created）

- **WHEN** 交货单 `register_shipment` 且物料 `serial_tracked=1`、`require_on_receipt=0`、`require_on_issue=1`
- **THEN**
  1. 行未提供号时，按数量自动建号：`source_type=issue_created`、`source_doc_type=shipment`、`source_doc_id=交货单 ID`；
  2. 建号后立即写 `ship` 事件并置 `shipped`；
  3. 行已提供号时仍走校验路径（号必须存在）；
  4. 其它组合保持 P6a 行为不变。

### FR-008 质量状态流转

- **WHEN** 用户或质量单据需要改变序列号 `quality_status`
- **THEN**
  1. 只允许 `unrestricted↔inspection`、`inspection↔blocked`、`blocked↔unrestricted`；
  2. `scrapped` 号禁止任何质量状态变更（`SERIAL_STATUS_TRANSITION_INVALID`）；
  3. 必须写 `status_change` 事件（含 `reason`、单据号）；
  4. 不允许通过 CRUD 直接改 `quality_status`（沿用 P6a 拦截器）。

### FR-009 红冲与反冲

- **WHEN** 调整单 `reverse` / 调拨发货红冲（未来）/ 收货红冲
- **THEN**
  1. 按 `inventory_transaction_id` 找到对应序列号事件；
  2. 逆序恢复 `usage_status` / `quality_status` / `current_location_id` / `batch_id`；
  3. 写一条反向事件（`remark='反冲 <原事件 ID>'`）；
  4. 已存在反冲事件 → 幂等返回，不重复写；
  5. 找不到原事件 → 跳过并记 WARNING（不阻断数量账红冲，避免历史数据缺桥接时卡死）。

### FR-010 幂等

- **WHEN** 同一单据同一行同一号重复登记
- **THEN** 按 `(serial_id, txn_type, doc_type, doc_id, line_id)` 查重，已存在则直接返回，不重复写事件或链接。

---

## 6. 服务接口契约（`SerialNumberService` 扩展）

| 方法 | 入参 | 返回 | 说明 |
|---|---|---|---|
| `register_transfer_ship` | `transfer_order_id` | `{registered, lines}` | FR-001 |
| `precheck_transfer_receipt` | `transfer_order_id, receipt_id` | `None`（抛错） | FR-002 前置 |
| `register_transfer_receipt` | `transfer_order_id, receipt_id` | `{registered}` | FR-002，TO 来源收货过账 |
| `precheck_adjustment` | `adjustment_id` | `None`（抛错） | FR-002~FR-004 前置 |
| `register_adjustment` | `adjustment_id` | `{registered, skipped}` | FR-002~FR-004 |
| `precheck_count` | `count_id` | `None`（抛错） | FR-005 校验差异号登记完整性 |
| `register_count` | `count_id` | `{registered}` | FR-006 过账时写事件 |
| `return_serial` | `serial_id, location_id=None, to_stores=False` | `{id, from_status, to_status}` | 退货预留：`issued→returned→in_stores` |
| `change_quality_status` | `serial_id, to_quality, reason='', doc=None` | `{id, from, to}` | FR-008 |
| `link_serials` | `doc_type, doc_id, line_id, serial_nos, direction` | `{linked}` | 统一链接登记入口 |
| `change_status` | 已有签名 | 已有 | FR-008，扩展 `doc` 参数支持单据号 |
| `reverse_serial_event` | `inventory_transaction_id` | `{reversed}` | FR-009，扩展支持 `doc_type` 批量 |

**调用归属**：

- 调拨发货：`TransferOrderService._post_ship_inventory()` 同事务调用 `register_transfer_ship`；
- 调整：`InventoryAdjustmentService.post()/reverse()` 同事务调用 `register_adjustment`；
- 盘点：`InventoryCountService.submit()` 调 `precheck_count`，`post()` 调 `register_count`；
- 交货：`ShipmentService` 现有 `register_shipment` 内扩展 FR-007。

---

## 7. 拦截器与权限

| 对象 | 动作 | 处理 |
|---|---|---|
| `serial_number` | `crud_create` | 沿用 P6a：只允许注册表内物料/组织与开关校验 |
| `serial_number` | 自定义 `change_status` | 委托 `SerialNumberService.change_status`，权限复用 `serial_number:serial_number_update` |
| `serial_number` | `crud_update` | 禁止直接改 `usage_status` / `quality_status` / `current_location_id`（沿用 P6a） |
| `transfer_order` | `crud_update(status=shipped)` | 沿用现有调拨守卫；序列号校验在 service 内，错误转 `ValidationFailedError` |
| `inventory_adjustment` | `crud_update(status=posted/reversed)` | 沿用 P58；序列号错误在 service 内转 `INV_*`/`SERIAL_*` |
| `inventory_count` | `crud_update(status=submitted/approved/posted)` | 沿用 P59；`submit` 前必须完成差异号登记 |

**权限码**：P6b 不新增权限码。单据动作沿用 INV-4 的 `release/post/reverse/cancel`、`start/submit/approve/post/cancel`；序列号状态动作复用 `serial_number:serial_number_update`。

---

## 8. 错误码

| 错误码 | 触发场景 |
|---|---|
| `SERIAL_TRANSFER_COUNT_MISMATCH` | 调拨发货号数 ≠ 发货数量 |
| `SERIAL_ADJUST_COUNT_MISMATCH` | 调整减少/报废号数 ≠ 行数量 |
| `SERIAL_ADJUST_SERIAL_REQUIRED` | 调整行未选号 |
| `SERIAL_STATUS_PAIR_INVALID` | 号质量状态 ≠ 行 `from_stock_status`，或转移前后相同 |
| `SERIAL_COUNT_SERIAL_REQUIRED` | 盘点差异行未登记号 |
| `SERIAL_COUNT_SERIAL_OUT_OF_SCOPE` | 盘亏号不在盘点范围（组织/库位/桶） |
| `SERIAL_COUNT_DUPLICATE` | 盘盈录入号重复 |
| `SERIAL_ISSUE_CREATE_FAILED` | 发货建档失败（号重复/超长等） |
| `SERIAL_REVERSE_SOURCE_MISSING` | 红冲找不到原事件（WARNING 级，不阻断） |
| `SERIAL_ITEM_NOT_TRACKED` / `SERIAL_NOT_FOUND` / `SERIAL_NOT_AVAILABLE` / `SERIAL_STATUS_TRANSITION_INVALID` / `SERIAL_DUPLICATE` / `SERIAL_ORG_MISMATCH` | 沿用 P6a |

---

## 9. 测试计划

| 文件 | 覆盖 |
|---|---|
| `meta/tests/test_serial_transfer_posting.py` | FR-001/FR-002：发货号数/组织/状态校验、`transfer_out` 事件与桥接、收货 `transfer_in` 与组织迁移、失败回滚 |
| `meta/tests/test_serial_adjustment_count_posting.py` | FR-002/003/004/005/006：状态转移切质量轴、减少/报废终态、增加建档、盘盈建档、盘亏报废、数量不符 |
| `meta/tests/test_serial_number_service.py`（扩展） | FR-008 质量状态白名单；`return_serial`；`issue_created` 发货建档 |
| 回归 | P6a 既有 `test_serial_number_service.py` / `test_serial_tracking_posting.py` 不回归；INV-4 四个测试文件不回归 |

所有测试走 `python d:\filework\test.py --single <path>`，禁止直接 pytest。

---

## 10. 里程碑与依赖

| 阶段 | 内容 | 依赖 |
|---|---|---|
| P6b-1 | FR-001 调拨发货 + FR-007 发货建档 | P6a `register_shipment` |
| P6b-2 | FR-002/003/004 调整 + FR-009 红冲 | INV-4 `InventoryAdjustmentService` |
| P6b-3 | FR-005/006 盘点差异号 | INV-4 `InventoryCountService` |
| P6b-4 | FR-008 质量状态动作 + 拦截器收口 + 全量回归 | P6b-1~3 |

**并行性**：P6b-1 与 P6b-2/3 可并行（互不共享文件）；P6b-4 最后收口。

---

## 11. 风险与待确认

| # | 风险/待确认 | 建议口径 |
|---|---|---|
| TBD-1 | 盘亏号最终状态：`defined` 还是 `scrapped` | 采用 `defined`（盘亏不等于报废，号可后续找回/重收）；报废必须显式走 `scrap` |
| TBD-2 | 调整增加允许激活 `defined` 号，是否限制来源 | 允许，但必须同组织同物料；来源单据记 `inventory_adjustment` |
| TBD-3 | 调拨收货落地时点（未来单据） | 由 `register_transfer_receipt` 统一处理，P6b 只留契约 |
| TBD-4 | 盘盈录号在主档的建档时点：`submit` 还是 `post` | `post`（避免草稿盘点提前占用号） |
| TBD-5 | 红冲找不到原事件是否阻断 | 不阻断数量账，记 WARNING（FR-009.5） |
| TBD-6 | 是否需要独立 `serial_number:change_status` 权限 | 本期复用 `_update`；若质量部门要求职责分离，追加 v204 迁移 |

---

## 12. 实施落点（文件 / 函数 / 验证）

### 12.1 唯一服务扩展：`meta/services/serial_number_service.py`

新增常量：`DOC_TRANSFER='transfer_order'`、`DOC_ADJUSTMENT='inventory_adjustment'`、`DOC_COUNT='inventory_count'`、`DOC_RETURN='return'`；`QUALITY_TRANSITIONS`（三值两两互通，自反禁止）。

新增 / 修改方法（全部只走 `self.ds.transaction()`，失败整体回滚）：

| 方法 | 落点 | 说明 |
|---|---|---|
| `link_serials(doc_type, doc_id, line_id, serial_nos, direction, item_id, org_id, create_missing=False, quality_status='unrestricted')` | 新方法，复用 `_find_serial` / `_ensure_link` | 统一链接入口；`direction='in'` 且号不存在时可建 `defined` 壳号（盘盈用），已存在则直接复用 |
| `precheck_transfer_ship(transfer_order_id, lines)` | 新方法，复用 `_precheck_line` 思路 | 号数 = 本次发货量；号 ∈ 调出组织且 `in_stores` |
| `register_transfer_ship(transfer_order_id, lines, event_key, txn_date=None)` | 新方法；`lines={line_id: qty}` | 写 `transfer_out`（`in_stores→in_transit`），`inventory_transaction_id = _find_inv_tx(event_key, line_id)`；主档置 `in_transit`、`current_location_id=NULL` |
| `precheck_transfer_receipt(transfer_order_id, lines)` | 新方法（契约） | 校验 `in_transit` 号数 = 收货量 |
| `register_transfer_receipt(transfer_order_id, lines, event_key, txn_date=None)` | 新方法（契约） | 写 `transfer_in`（`in_transit→in_stores`），主档迁 `org_id` / `current_location_id`；`lines` 项含 `to_org_id` / `to_location_id` |
| `precheck_adjustment(adjustment_id)` | 新方法，复用 `_load` 逻辑（直接 SQL） | 按 `adjustment_type` 逐行校验：减少/报废/状态转移/增加/期初 |
| `register_adjustment(adjustment_id, event_key='adjustment:{no}')` | 新方法 | 见 FR-002/003/004；`source_line_id=str(line_id)` 定位数量事务 |
| `precheck_count(count_id)` | 新方法 | 差异行号数 = `|variance|`；盘亏号须在库、质量 = 行 `stock_status`、组织/库位在范围内 |
| `register_count(count_id, event_key='count:{no}')` | 新方法 | 盘亏写 `scrap` 并置 `scrapped`；盘盈建 `opening` 号并写 `adjust`；回填 `inventory_transaction_id` |
| `return_serial(serial_id, location_id=None, to_stores=False)` | 新方法 | `issued→returned`；`to_stores=True` 时再 `returned→in_stores` 并落库位 |
| `change_quality_status(serial_id, to_quality, reason='', doc=None)` | 新方法 | 三值白名单；`scrapped` 拒绝；写 `status_change` 事件 |
| `_register_shipment_line` | **修改**（FR-007） | `require_on_issue=1 & require_on_receipt=0` 且无 link / 无 `serial_no` 时，按数量建 `source_type='issue_created'` 号后走 `ship` |
| `_precheck_line` | **修改**（FR-007） | 上述组合跳过 `SERIAL_ISSUE_COUNT_MISMATCH` 前置数量校验，允许过账时建档 |
| `reverse_serial_event` | **修改**（FR-009） | 同时回退 `quality_from/quality_to`；已存在反向事件（`remark LIKE '反冲%'`）则幂等跳过 |

### 12.2 调用接线（同事务；`serial_schema_ready(self.ds)` 为真才启用）

| 文件 | 函数 | 改动 |
|---|---|---|
| `meta/services/transfer_order_service.py` | `_post_ship_inventory` | `InventoryPostingService.post()` 成功后调用 `register_transfer_ship(header, items, event_key, ship_date)`；`SerialNumberError → TransferOrderError(rule)` |
| `meta/services/inventory_adjustment_service.py` | `post` | `posting.post()` 成功后、状态回写前调用 `register_adjustment(header['id'], 'adjustment:{no}')`；`SerialNumberError → InventoryError(rule)` |
| 同上 | `reverse` | `posting.reverse()` 后逐个 `tx_id` 调 `reverse_serial_event(tx_id)` |
| `meta/services/inventory_count_service.py` | `submit` | 状态写入前 `precheck_count(count_id)` |
| 同上 | `post` | `posting.post()` 成功后调用 `register_count(count_id, 'count:{no}')` |
| `meta/services/shipment_service.py` | `register_shipment` | 不改接线；FR-007 全部落在序列号服务内部 |

### 12.3 拦截器收口

| 文件 | 改动 |
|---|---|
| `meta/core/interceptors/serial_number_guard_interceptor.py` | `crud_update` 携带变更后的 `quality_status` 时，委托 `SerialNumberService.change_quality_status`（写事件后放行持久化）；仍禁止直接改 `usage_status`；`scrapped` 号拒绝任何修改 |

权限：不新增权限码；`change_quality_status` 走 `serial_number:serial_number_update`（D10）。无需注册新拦截器、无需改 `app_builder.py` / `server.py`。

### 12.4 测试与验证

| 文件 | 覆盖 |
|---|---|
| `meta/tests/test_serial_transfer_posting.py`（新建） | FR-001/FR-002：号数/组织/状态校验、`transfer_out` 事件与 `inventory_transaction_id` 桥接、`transfer_in` 迁组织、失败回滚 |
| `meta/tests/test_serial_adjustment_count_posting.py`（新建） | FR-002/003/004/005/006：状态转移只切质量轴、减少/报废终态、增加/期初建档、盘盈建档、盘亏报废、数量不符、幂等 |
| `meta/tests/test_serial_number_service.py`（扩展） | FR-008 质量白名单、`scrapped` 拒绝、`return_serial`、`link_serials` |
| `meta/tests/test_serial_tracking_posting.py`（扩展） | FR-007 发货建档（`issue_created`）、数量不符拒绝 |
| 回归 | P6a 两个测试文件 + INV-4 四个测试文件 |

验证命令（逐文件，禁止 pytest）：

```
python d:\filework\test.py --single meta/tests/test_serial_transfer_posting.py
python d:\filework\test.py --single meta/tests/test_serial_adjustment_count_posting.py
python d:\filework\test.py --single meta/tests/test_serial_number_service.py
python d:\filework\test.py --single meta/tests/test_serial_tracking_posting.py
python d:\filework\test.py --single meta/tests/test_inventory_adjustment_service.py
python d:\filework\test.py --single meta/tests/test_inventory_count_service.py
```

验收口径：新增测试全绿；P6a + INV-4 回归无新增失败；`serial_transactions` 每条 P6b 事件都能用 `inventory_transaction_id` 反查到数量事务（纯状态变更除外）；重复过账/重复登记不产生重复事件。
