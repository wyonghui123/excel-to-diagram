# Spec: Transfer Order（调拨单）对象模型

> 状态：已实施（v190 迁移已执行，schema / 服务 / 守卫 / 动作 / 收货桥接 / 测试全部落地）
> 日期：2026-11-02（实施完成日）
> 关联规格：
> - `docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md`（M4 载体决策 / A3 命名边界）
> - `docs/specs/spec-purchase-order-object-model-2026-11-01.md`（PO 类型范式 / 组织语义）
> - `docs/specs/spec-receipt-object-model-2026-11-01.md`（收货复用 / 来源单据多态）
> 实施任务：`docs/specs/tasks-transfer-order-object-model-2026-11-02.md`
> 语言：中文

---

## 0. 二次检查结论（本 Spec 的事实基础）

本节是对 `transfer_order` 的 document type、line type 以及与其他对象关系的二次核对结果。核对对象包括 `type_definition`、`document_type`、`line_type`、`line_type_assignment`、`purchase_order`、`receipt`、`demand_allocation`、`location`、`items`、`shipment`、`org_legal_entity`。

### 0.1 类型体系核对

平台类型字典是单表 `type_definitions`，用 `level`（header / line）与 `scope_bo`（消费方 BO 的 YAML id）判别归属；`document_type` / `line_type` 只是 `level` 切片只读视图；复合唯一键 `(scope_bo, level, code)`。

| 单据 | scope_bo | header 类型 | line 类型 | 编号序列 |
|---|---|---|---|---|
| 销售订单 | `sales_order` | 销售单据类型（多类别） | 销售行类型（多类） | 销售序列 |
| 采购订单 | `purchase_order` | `PO_STD`（standard） | 6 个：`PO_GOODS` / `PO_SUBCONTRACT` / `PO_ASSET` / `PO_SERVICE` / `PO_EXPENSE` / `PO_TEXT`，带 `line_category` 与 `delivery_relevant` | `PO_STD` |
| 收货单 | `receipt` | `RCV_STD`（standard）/ `RCV_RETURN`（return） | **无行类型** | `RCV` |
| 调拨单（本 Spec） | `transfer_order` | `TRF_STD`（standard） | **1 个**：`TRF_GOODS`（material，delivery_relevant=1） | `TRF` |

核对发现：

1. **TO 不能照抄收货的“无行类型”做法。** 收货单没有行类型，是因为收货行只记录“收多少”，不决定执行逻辑；调拨行要驱动发货、收货与后续库存过账，必须保留行身份。本波只建 1 个物料行类型，`line_type_id` 仍落在行上。
2. **`document_category` 没有 `transfer` 取值。** 现有枚举是 standard / rush / return / credit_memo / debit_memo / consignment / loan。TO 头类型必须用 `standard`，不能自造 `transfer` 类别。
3. **不需要 `TRF_RETURN`。** 已发货调拨不能取消，只能开一张反向调拨单（from/to 互换、数量仍为正）。反向调拨是新的标准调拨单，方向由组织字段表达，不是负向单据；本波不建 return 头类型。
4. **`line_category` 枚举与 PO 种子已存在漂移。** `type_definition.yaml` 的 `line_category` 只列 material / service / return / free_of_charge / text，但 `v177` 已写入 `subcontract` / `asset` / `expense`。说明该枚举不是强约束、且 UI 选项已落后。TO 只用 `material`，不碰这处漂移；修复枚举不在本波范围。
5. **`line_type` / `document_type` 视图未暴露 `scope_bo`。** 因此行类型下拉无法按归属对象过滤。TO 本波只有 1 个行类型，采用“头类型 `default_type_id` 自动带出、行上只读”的方式绕开；不扩平台视图。
6. **`line_type_assignment` 的父对象是 `document_type`，规则是“单据类型 + 物料组 → 行类型”。** TO 只有 1 个行类型，不需要确定表；本波不建 assignment，避免空配置。

### 0.2 对象关系核对（关键结论）

1. **收货单已预留 TO 来源。** `receipt.source_doc_type` 值域已包含 `transfer_order`；`receipt_line.source_line_id` 是“非 PO 来源的挂载点”（与 `schedule_id` 至少一个必填）；`supplier_party_id` 可空。结构上无需为 TO 改收货表。
2. **收货单没有“收货库存组织”字段。** 收货头只有 `org_id`（收货方法人）与 `purchase_org_id`（采购组织快照），PO 头也只有法人/采购组织，平台当前不存在“收货库存组织”事实。TO 来源收货的 `to_org` 只能通过 `source_doc_id` 回查 TO 头派生，本波不新增收货字段。
3. **`location` 没有 `org_id`。** `location` 只是 site / warehouse / zone / bin 的树，不挂组织。因此无法校验“库位属于组织”，TO 只能校验 from/to 库位不同，不能把组织归属写成不变量。这是平台缺口。
4. **`items` 没有成本字段。** `items` 只有 `item_type`（goods / service），没有 standard_cost / cost_price。TO 的“成本价”在本平台没有取数来源；本波不建金额字段，成本事实留给库存/成本域（后续 TODO）。
5. **`demand_allocation` 已预留 TO 载体。** `target_bo` 枚举已包含 `transfer_order`；`target_id` / `target_line_id` 必填。TO 行天然是需求分配的执行目标，不新建追溯表。
6. **`shipment` 是销售专用，不可直接复用。** `shipment.order_id` 必填且指向 `sales_order`，行挂 `sales_order_schedules`。把 shipment 泛化会破坏销售侧，本波 TO 发货不建 shipment。
7. **`party` 与 TO 无关。** TO 是内部调拨，不挂 supplier / customer；TO 来源收货的 `supplier_party_id` 为空。
8. **`org_legal_entity` 是只读视图，不能做外键。** 法人判定取 `org_functions.function_type='legal_entity'` 职能，不写死 `org_type=company`。TO 头存 `legal_entity_id` 快照（指向 `org`，语义为法人组织），守卫按 sourcing 同口径判定同一法人。
9. **`work_order` / `sales_order` / 发票与 TO 无直接关系。** 跨法人走 ISO（复用 `sales_order` + 接收方收货 + 内部发票），不建 TO；生产需求走工单；TO 不产生发票。
10. **库存域全系统缺失。** 无 inventory / on-hand / in-transit / lot / serial 对象。TO 行的 `qty_shipped` / `qty_received` 是单据缓存，不是库存台账；发货不校验可用量，收货不生成库存事务。

---

## 1. 背景与目标

M4 已确定内部供应载体边界：

- 跨法人（无需审批）：走 ISO，复用 `sales_order` + 接收方收货 + 内部发票；
- 同法人、不同库存组织：走 `transfer_order`（无售价、有成本价）；
- 生产工序：走工单。

本 Spec 的目标是把 `transfer_order` 落成平台可实现的头 + 行对象，并明确它与类型字典、组织、物料、库位、需求分配、收货、发货、库存域的关系。**库存域明确为后续 TODO，本波不做。**

---

## 2. 范围

### 2.1 本波范围（In Scope）

1. `transfer_order` 头对象与 `transfer_order_line` 行对象（schema + 表 + 索引）。
2. 头类型 `TRF_STD` 与行类型 `TRF_GOODS`；编号序列 `TRF`。
3. TO 生命周期动作：release / ship / receive / cancel / close。
4. TO 与 `receipt` 的桥接：TO 来源收货单的创建、过账回写、红冲回退。
5. TO 与 `demand_allocation` 的载体关系（表结构已支持；自动转换不在本波）。
6. 权限、菜单、动作注册、守卫、单测与迁移验证。

### 2.2 非范围（Out of Scope）

1. 库存台账：inventory transaction / on-hand / in-transit / lot / serial / bin stock / 库存过账。
2. 成本与估值：unit_cost、金额合计、币种、成本核算。
3. 跨法人内部交易：intercompany TO、内部发票、内部结算价；跨法人一律走 ISO。
4. 发货单对象：多包裹、多承运商、装箱单；本波发货事实落在 TO 头/行。
5. 收货检验、质检路由、退货入库。
6. 请购 → 调拨的自动转换（`create_from_allocation`）。
7. 审批流（TO 本波不接审批）。
8. 同一组织内的库位间移库（本波要求 from_org != to_org）。

---

## 3. 对象模型

### 3.1 transfer_order（头）

表名：`transfer_orders`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | INTEGER PK | 是 | 技术主键 |
| `transfer_order_no` | VARCHAR(30) | 是 | 业务键；创建时按 `document_type.number_sequence_id` 取号，生成后不可改，允许跳号 |
| `document_type_id` | INTEGER | 是 | 单据类型（`document_type_aspect` 提供；`scope_bo='transfer_order'` + `level='header'`；离开草稿不可改） |
| `transfer_date` | DATE | 是 | 调拨日期；取号日期段基准；草稿后可改，release 后冻结 |
| `status` | VARCHAR(20) | 是 | 单据状态：`draft` / `released` / `closed` / `cancelled`，默认 `draft` |
| `fulfillment_status` | VARCHAR(30) | 否 | 履约状态只读缓存：`open` / `partially_shipped` / `shipped` / `partially_received` / `received`，由服务层派生 |
| `from_org_id` | INTEGER | 是 | 调出组织（库存组织）；须存在、启用、具备 `inventory` 职能 |
| `to_org_id` | INTEGER | 是 | 调入组织（库存组织）；须存在、启用、具备 `inventory` 职能 |
| `legal_entity_id` | INTEGER | 是 | 法人快照（只读派生）；`from_org_id` / `to_org_id` 上溯到的同一法人组织 id；指向 `org`，语义为 `legal_entity` 职能组织 |
| `from_location_id` | INTEGER | 否 | 调出库位 / 仓库；可空，表示组织级调拨 |
| `to_location_id` | INTEGER | 否 | 调入库位 / 仓库；可空 |
| `project_id` | INTEGER | 否 | 项目；可空 |
| `actual_ship_date` | DATE | 否 | 首次发货日期（ship 动作写入） |
| `carrier_name` | VARCHAR(100) | 否 | 承运商（ship 动作写入，可空） |
| `waybill_no` | VARCHAR(50) | 否 | 运单号（ship 动作写入，可空） |
| `remark` | TEXT | 否 | 备注 |
| `created_at` / `updated_at` / `created_by` / `updated_by` | 审计字段 | 是 | 平台审计切面 |

设计说明：

- 头不存金额、币种、供应商、客户、发票信息。
- 头存 `reversal_of_transfer_id`（v191 起）：反向调拨仍是独立标准 TO，只做原单链接与 from/to 互换校验（TBD-2 已关闭）。
- 头不存 `inventory_org` 之外的执行组织；调出/调入组织本身就是库存组织。

### 3.2 transfer_order_line（行）

表名：`transfer_order_lines`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | INTEGER PK | 是 | 技术主键 |
| `transfer_order_id` | INTEGER | 是 | 所属调拨单；真外键（逻辑约束） |
| `line_no` | INTEGER | 是 | 行号；同单内唯一，服务层按 10/20/30 递增 |
| `line_type_id` | INTEGER | 是 | 行类型；指向 `type_definitions` 的 `scope_bo='transfer_order'` + `level='line'` 行；本波由头类型 `default_type_id` 自动带出，UI 只读 |
| `item_id` | INTEGER | 是 | 物料；须存在、启用、`item_type='goods'` |
| `uom_id` | INTEGER | 是 | 计量单位 |
| `qty` | DECIMAL(20,6) | 是 | 计划调拨量；恒为正；草稿可改，release 后冻结 |
| `qty_shipped` | DECIMAL(20,6) | 是 | 已发货累计；默认 0；只读缓存，仅 ship 动作累加 |
| `qty_received` | DECIMAL(20,6) | 是 | 已收货累计（净收）；默认 0；只读缓存，仅收货过账/红冲回写 |
| `status` | VARCHAR(20) | 是 | 行状态：`open` / `closed` / `cancelled`，默认 `open` |
| `fulfillment_status` | VARCHAR(30) | 否 | 行履约状态只读缓存，取值同头 |
| `remark` | TEXT | 否 | 备注 |
| `created_at` / `updated_at` / `created_by` / `updated_by` | 审计字段 | 是 | 平台审计切面 |

约束：

- `UNIQUE (transfer_order_id, line_no)`。
- `qty > 0`；`0 <= qty_shipped <= qty`；`0 <= qty_received <= qty_shipped`。
- 行不存单价、金额、税率、成本价。
- 行不建 schedule 子表；发货/收货事实直接累计在行上。

### 3.3 索引

`transfer_orders`：

- `idx_transfer_order_type (document_type_id)`
- `idx_transfer_order_date (transfer_date)`
- `idx_transfer_order_from_org (from_org_id)`
- `idx_transfer_order_to_org (to_org_id)`
- `idx_transfer_order_project (project_id)`
- `idx_transfer_order_status (status)`

`transfer_order_lines`：

- `idx_transfer_order_line_order (transfer_order_id)`
- `idx_transfer_order_line_item (item_id)`
- `idx_transfer_order_line_type (line_type_id)`

---

## 4. 类型与编号

### 4.1 头类型

| 项 | 值 |
|---|---|
| `code` | `TRF_STD` |
| `name` | 标准调拨单 |
| `scope_bo` | `transfer_order` |
| `level` | `header` |
| `document_category` | `standard` |
| `default_type_id` | `TRF_GOODS`（同 scope、level=line） |
| `number_sequence_id` | `TRF` |
| `status` | `active` |
| `description` | 同法人不同库存组织之间的内部调拨单据类型 |

### 4.2 行类型

| 项 | 值 |
|---|---|
| `code` | `TRF_GOODS` |
| `name` | 标准物料行 |
| `scope_bo` | `transfer_order` |
| `level` | `line` |
| `line_category` | `material` |
| `delivery_relevant` | `1` |
| `status` | `active` |
| `description` | 可发货、可收货的实物物料行 |

v191 起建 `TRF_SERVICE` / `TRF_ASSET` / `TRF_TEXT`（`delivery_relevant=0`，release 时自动关闭行，不参与发货 / 收货 / 履约收满判定）。

### 4.3 编号序列

| 项 | 值 |
|---|---|
| `code` | `TRF` |
| `name` | 调拨单编号 |
| `pattern` | `TRF-{DATE:yyyymm}-{SEQ:6}` |
| `date_field` | `transfer_date` |
| 重置 | 按年度（与 PO / RCV 同口径） |
| 溢出 | `error`（不回退、不静默扩位） |

取号时机：创建草稿时取号（与 PO / RCV 一致），生成后不可改。

### 4.4 行类型确定

本波不建 `line_type_assignment`。TO 行 `line_type_id` 由头类型 `default_type_id` 带出；UI 只读，守卫强制校验 scope / level / status。

---

## 5. 全量对象关系

| 关系对象 | 挂载字段 | 基数 | 引用方式 | 约束 / 说明 | 本波 |
|---|---|---|---|---|---|
| `type_definitions`（header） | `transfer_orders.document_type_id` | N:1 | 真外键（逻辑） | `scope_bo='transfer_order'` + `level='header'`；离开草稿不可改 | 是 |
| `type_definitions`（line） | `transfer_order_lines.line_type_id` | N:1 | 真外键（逻辑） | `scope_bo='transfer_order'` + `level='line'` + `status='active'`；由头类型默认带出 | 是 |
| `number_sequence` | 经 `document_type.number_sequence_id` 间接 | N:1 | 间接 | 创建时取号；生成后不可改 | 是 |
| `org`（调出） | `from_org_id` | N:1 | 真外键（逻辑） | 存在、启用、具备 `inventory` 职能 | 是 |
| `org`（调入） | `to_org_id` | N:1 | 真外键（逻辑） | 存在、启用、具备 `inventory` 职能；必须与 from 不同 | 是 |
| `org`（法人快照） | `legal_entity_id` | N:1 | 真外键（逻辑） | from/to 上溯到的同一法人组织；只读；解析失败拒绝创建 | 是 |
| `location`（调出） | `from_location_id` | N:1 | 真外键（逻辑） | 可空；`location` 无 `org_id`，不能校验组织归属 | 是 |
| `location`（调入） | `to_location_id` | N:1 | 真外键（逻辑） | 可空；与 from 同时存在时必须不同 | 是 |
| `project` | `project_id` | N:1 | 真外键（逻辑） | 可空 | 是 |
| `item` | `transfer_order_lines.item_id` | N:1 | 真外键（逻辑） | 存在、启用、`item_type='goods'` | 是 |
| `uom` | `transfer_order_lines.uom_id` | N:1 | 真外键（逻辑） | 必填 | 是 |
| `demand_allocation` | 分配表的 `target_id` / `target_line_id` | 1:N | 多态（无外键） | `target_bo='transfer_order'`；`target_line_id` 必填；`target_schedule_id` 为空 | 表结构已支持；自动转换 TBD-4 |
| `receipt` | 收货头 `source_doc_type` / `source_doc_id` / `source_doc_no` | 1:N | 多态（无外键） | `source_doc_type='transfer_order'`；`source_doc_id=transfer_order.id` | 是 |
| `receipt_line` | `source_line_id` | 1:N | 多态（无外键） | 指向 TO 行；`schedule_id` / `order_id` 为空 | 是 |
| `party`（供应商 / 客户） | 无 | - | - | TO 是内部调拨，不挂往来单位 | 否 |
| `shipment` / `shipment_line` | 无 | - | - | `shipment.order_id` 必填指向 `sales_order`，不复用 | 否 |
| `sales_order` / ISO | 无 | - | - | 跨法人走 ISO，不建 TO | 否 |
| `work_order` | 无 | - | - | 生产需求走工单；后续可经 `demand_allocation` 指向 TO | 否 |
| `currency` / 发票 | 无 | - | - | TO 无金额、无发票 | 否 |
| `line_type_assignment` | 无 | - | - | 本波只有 1 个行类型，不建确定表 | 否 |
| `location` 的组织归属 | 无 | - | - | `location` 无 `org_id`，平台缺口（TBD-7） | 否 |

---

## 6. 状态机与动作

### 6.1 头状态

`status`：

| 状态 | 含义 | 进入方式 | 允许动作 |
|---|---|---|---|
| `draft` | 草稿 | 创建 | update / delete / release |
| `released` | 已下达 | release | ship / receive / close / cancel（仅未发货） |
| `closed` | 已关闭 | 全部收货自动关闭；或手工 close | 只读；反向调拨另开新单 |
| `cancelled` | 已取消 | cancel | 只读 |

`fulfillment_status`（只读派生）：

- `open`：总发货量 = 0；
- `partially_shipped`：0 < 总发货量 < 总量，且总收货量 = 0；
- `shipped`：总发货量 = 总量，且总收货量 = 0；
- `partially_received`：总收货量 > 0，且未全部收货；
- `received`：全部行 `qty_received >= qty`。

在途量不单独建表，报表口径为 `sum(qty_shipped - qty_received)`。

### 6.2 行状态

`status`：`open` / `closed` / `cancelled`。

- `open`：默认；
- `closed`：行全部收货时自动关闭；头 close 时全部行关闭；
- `cancelled`：头 cancel 时全部行取消。

`fulfillment_status`：与头同公式，按行计算。

### 6.3 动作

| 动作 | 前置状态 | 结果 | 关键校验 |
|---|---|---|---|
| `release` | draft | released | 至少 1 行；头/行/组织/法人/物料/单位全部合法；冻结业务字段 |
| `ship` | released | 仍 released；履约状态变化 | 行 quantity > 0；`qty_shipped + qty <= qty`；首次发货写 `actual_ship_date` |
| `receive` | released | 生成一张 draft 收货单 | 只允许发运余量 > 0 的行；收货单走 receipt 自身 post / reverse |
| `cancel` | draft / released | cancelled | 仅当总发货量 = 0；已发货只能反向调拨 |
| `close` | released | closed | 在途量 = 0 且总收货量 > 0（短收结案）；全部收货自动 close |

动作实现通过 `bo_action_registrations` 注册，沿用 receipt 的动作调用通道，不新开 REST 路由。

---

## 7. 发货、收货与库存边界

### 7.1 发货段（不建 shipment）

| 发货事实 | 承载 |
|---|---|
| 发货动作 | TO 头 `ship` |
| 发货日期 | `transfer_orders.actual_ship_date`（首次发货） |
| 承运商 / 运单号 | `transfer_orders.carrier_name` / `waybill_no` |
| 行发货量 | `transfer_order_lines.qty_shipped` |
| 在途量 | `qty_shipped - qty_received`（派生，不建表） |
| 发货单 | 不建；`shipment` 销售专用，不复用、不泛化 |

### 7.2 收货段（复用 receipt）

TO 来源收货单的字段映射：

| receipt 字段 | TO 来源取值 |
|---|---|
| `source_doc_type` | `transfer_order` |
| `source_doc_id` | `transfer_order.id` |
| `source_doc_no` | `transfer_order.transfer_order_no` |
| `org_id` | `transfer_order.legal_entity_id`（收货方法人） |
| `purchase_org_id` | 空 |
| `supplier_party_id` | 空 |
| `deliver_to_location_id` | `transfer_order.to_location_id`（可空） |
| `receipt_line.source_line_id` | `transfer_order_line.id` |
| `receipt_line.schedule_id` | 空 |
| `receipt_line.order_id` | 空 |

收货过账回写：

- TO 行 `qty_received += (receipt_line.qty_received - receipt_line.qty_rejected)`（净收）；
- 累计净收不得超过 `qty_shipped`；本波不设超收容差；
- 全部行收满时，TO 头 `status` 自动置 `closed`、`fulfillment_status` 置 `received`；
- 收货红冲：反向扣减 `qty_received`；若 TO 头因收满而 closed，回退为 released 并重算履约状态；
- 草稿收货单删除 / 取消：不影响 TO 数量。

TO 来源收货不写 `purchase_order_schedules`、不调 `PurchaseOrderFulfillmentService`。

### 7.3 库存边界（后续 TODO）

本波明确不做：

1. `inventory_transaction` / on-hand 余额 / in-transit 台账；
2. lot / serial / bin 级库存；
3. 发货时的可用量校验与预留；
4. 收货时的库存过账；
5. 成本价、估值、币种、金额；
6. 同一组织内的库位间移库；
7. 盘点 / 循环盘点；
8. 收货头的“库存组织”字段（TBD-6）。

因此，TO 行 `qty_shipped` / `qty_received` 是**单据缓存**，不是库存派生量；系统允许发货量超过实际库存。

---

## 8. 需求分配与追溯

- `demand_allocation.target_bo='transfer_order'`，`target_id=transfer_order.id`，`target_line_id=transfer_order_line.id`，`target_schedule_id` 为空。
- `demand_allocation` 是多态表，无外键；TO 删除草稿时由服务层同步清理对应分配行（或按平台既有口径 restrict）。
- TO 头不存 `requisition_id` / `source_doc_id`；需求追溯统一走 `demand_allocation`。
- sourcing 的 `requested_source_org_id` / `resolved_source_org_id` 不落库，只用于决定载体（TO / ISO / PO / 工单）。
- 请购 → TO 的自动创建不在本波（TBD-4）。

---

## 9. 权限、菜单与 API

### 9.1 权限

CRUD：

- `transfer_order:transfer_order_create`
- `transfer_order:transfer_order_read`
- `transfer_order:transfer_order_update`
- `transfer_order:transfer_order_delete`
- `transfer_order:transfer_order_list`

单据动作：

- `transfer_order:transfer_order_release`
- `transfer_order:transfer_order_ship`
- `transfer_order:transfer_order_receive`
- `transfer_order:transfer_order_cancel`
- `transfer_order:transfer_order_close`

### 9.2 菜单

| 项 | 值 |
|---|---|
| `menu_code` | `transfer-order-management` |
| `menu_name` | 调拨单 |
| `parent_menu` | `procurement` |
| `page_type` | `object_list` |
| `primary_object_type` | `transfer_order` |
| `bo_bindings` | `transfer_order` / role=primary / include_actions=CRUD |
| `sort_order` | 3 |
| 数据权限建议 | 按 `from_org_id` 主过滤，`to_org_id` 作为附加过滤 |

菜单加入 `meta/scripts/init_menu_permissions.py` 的 `MIGRATION_OWNED_MENUS` 白名单，避免初始化脚本误删。

### 9.3 数据权限

TO 涉及两个组织。若平台数据权限只支持单字段，以 `from_org_id` 为主过滤；`to_org_id` 在列表提供显式过滤条件。

---

## 10. 服务层不变量（R-TO）

| 编号 | 不变量 |
|---|---|
| R-TO-0 | 创建时 `document_type_id` 必填，且属于 `scope_bo='transfer_order'` + `level='header'`；离开 draft 不可改 |
| R-TO-1 | `from_org_id != to_org_id`；两组织存在、启用、具备 `inventory` 职能 |
| R-TO-2 | `from_org_id` / `to_org_id` 上溯到同一法人；`legal_entity_id` 为只读快照；法人解析失败拒绝创建，不降级放行 |
| R-TO-3 | release 时至少 1 行；`line_type_id` 属于 `scope_bo='transfer_order'` + `level='line'` + active；`item_type='goods'` 且物料启用 |
| R-TO-4 | `qty > 0`；`0 <= qty_shipped <= qty`；`0 <= qty_received <= qty_shipped` |
| R-TO-5 | release 后冻结 `document_type_id` / `transfer_date` / `from_org_id` / `to_org_id` / `legal_entity_id` / 行的 `line_type_id` / `item_id` / `uom_id` / `qty` / `line_no` |
| R-TO-6 | cancel 仅允许总发货量 = 0；已发货只能反向调拨 |
| R-TO-7 | ship 原子累加 `qty_shipped`，单行不得超发；允许部分行发货；首次发货写 `actual_ship_date` |
| R-TO-8 | receive 只允许 `status='released'` 且发运余量 > 0；生成 draft 收货单，不直接过账 |
| R-TO-9 | TO 来源收货过账按净收回写 `qty_received`，不得超过 `qty_shipped`；红冲反向扣减并重算头状态 |
| R-TO-10 | TO 不写金额、币种、发票、库存事务；不调 PO 计划行与 PO 履约服务 |
| R-TO-11 | `from_location_id` / `to_location_id` 可空；同时存在时必须不同；不校验组织归属（平台缺口） |
| R-TO-12 | 仅 draft 可删除；released / closed / cancelled 禁止删除 |
| R-TO-13 | closed / cancelled 为终态，禁止 ship / receive / update；纠正走反向调拨 |

---

## 11. 实施任务与验收

完整任务见 `docs/specs/tasks-transfer-order-object-model-2026-11-02.md`。概要：

1. schema：`transfer_order.yaml` / `transfer_order_line.yaml`；
2. 迁移 `v190__transfer_order_object.py`：表、索引、类型、序列、权限、菜单；
3. 服务：`transfer_order_service.py` / `transfer_order_guard_service.py`；
4. 守卫拦截器：`transfer_order_guard_interceptor.py`，双处注册（`app_builder.py` / `server.py`）；
5. 动作：`transfer_order_actions.py` + `bo_action_registrations.py`；
6. 收货桥接：`receipt_service.py` / `receipt_guard_service.py`；
7. 测试：schema / service / guard / receipt bridge 四个文件；
8. 迁移验证、回归、冒烟。

验收标准：

- `meta/schemas` 注册加载通过，无 schema 校验错误；
- v190 verify PASS（表、索引、类型、序列、权限、菜单、动作）；
- 单测全绿；
- TO 创建 → release → ship → receive → post → 全部收满自动 close 全链路可跑；
- 收货红冲后 TO 行数量回退、状态重算；
- 既有 PO / receipt 回归不受影响；
- 代码中无库存域依赖、无金额字段。

---

## 12. 决策记录

| 编号 | 决策 | 理由 |
|---|---|---|
| D-TO-1 | 库存域本波不做，TO 数量为单据缓存 | 用户明确库存为后续 TODO；平台无库存对象 |
| D-TO-2 | 不建 shipment，不泛化销售发货单 | `shipment.order_id` 必填指向 `sales_order`，泛化会破坏销售侧 |
| D-TO-3 | 不建金额 / 成本 / 币种字段 | `items` 无成本字段；成本事实应由后续库存/成本域承载 |
| D-TO-4 | 只建 1 个行类型 `TRF_GOODS` | 本波 TO 只调实物物料；避免空配置与过度设计 |
| D-TO-5 | 行类型由头类型默认带出，UI 只读，不建 assignment | `line_type` 视图未暴露 `scope_bo`，下拉无法按 BO 过滤；单类型场景直接带出 |
| D-TO-6 | 头类型只用 `TRF_STD`（standard），不建 `TRF_RETURN` | `document_category` 无 transfer；反向调拨是新的标准 TO |
| D-TO-7 | 收货复用 receipt，不新增“收货库存组织”字段 | 收货头本无库存组织事实；TO 来源 `to_org` 由 `source_doc_id` 回查 |
| D-TO-8 | `legal_entity_id` 必填且解析失败拒绝创建 | 保证同一法人，且收货头 `org_id` 有值；不降级 |
| D-TO-9 | 发货后才允许收货（`qty_received <= qty_shipped`） | 内部调拨以发货为起点；避免先收后发的口径混乱 |
| D-TO-10 | 已发货不可取消，只能反向调拨 | 与 M4 一致；保留业务可追溯性 |
| D-TO-11 | 不建 schedule 子表 | TO 是单次发货 + 多次收货，不需要销售/采购的计划行层 |
| D-TO-12 | 库位可空，且不校验组织归属 | `location` 无 `org_id`，平台缺口不能写成不变量 |

---

## 13. TBD List

| 编号 | 待定项 | 触发条件 / 说明 |
|---|---|---|
| TBD-1 | 库存域：inventory transaction / on-hand / in-transit / lot / serial / bin stock / 库存过账 | 用户明确后续 TODO；落地后 TO 发货/收货改为库存事实源 |
| TBD-2 | `reversal_of_transfer_id` 原单链接与反向调拨校验 | **已关闭（v191）**：头加列 + 守卫校验 from/to、库位互换 + `create_reversal` |
| TBD-3 | 多包裹 / 多承运商发货单（独立 `transfer_shipment`） | **已关闭（v192）**：`transfer_shipment` + `transfer_shipment_line`，post 原子累加 TO `qty_shipped` |
| TBD-4 | 请购 → 调拨自动转换（`create_from_allocation`）与 `line_type_assignment` | **已关闭（v191 + v193）**：`LineTypeResolver` 支持 scope；`transfer_order.create_from_allocation` 按分配建单 |
| TBD-5 | `TRF_SERVICE` / `TRF_ASSET` / `TRF_TEXT` 行类型 | **已关闭（v191）**：三种行类型种子，`delivery_relevant=0` |
| TBD-6 | 收货头 `inventory_org_id`（收货库存组织） | 库存域落地或跨来源报表需要收货库存组织维度时；本波由 `source_doc_id` 回查 |
| TBD-7 | `location` 增加 `org_id` 与组织归属校验 | 需要库位级库存与组织隔离时 |
| TBD-8 | 超发 / 超收容差参数 | **已关闭（v191）**：`transfer_over_ship_percent` / `transfer_over_receive_percent`，默认 0 |
| TBD-9 | TO 审批流 | **已关闭（v194）**：`approval_status` + submit / withdraw / approve / reject + release 闸门 |
| TBD-10 | 跨法人场景的 PO / receipt 法人一致性守卫 | **已关闭（v195）**：`purchase_orders.purchase_legal_entity_id` 快照 + 收货法人一致性守卫（R-RC-19） |
| TBD-11 | `line_type` / `document_type` 视图暴露 `scope_bo` | **已关闭（v191）**：两个只读视图增加 `scope_bo` 列并重建 |

---

## 14. 附：与 PO / Receipt / ISO 的边界一句话总结

- **采购订单**：对外采购，有供应商、价格、计划行、收货回写；跨法人采购走 ISO，不落 PO。
- **收货单**：通用收货事实，来源多态；TO 来源复用同一对象，但 `org_id` 取 TO 法人、`supplier` 为空、回写 TO 行而非 PO 计划行。
- **调拨单**：同法人、不同库存组织之间的内部移动；无供应商、无售价、无金额、无发货单、无库存台账；发货走 TO 头/行，收货走 receipt。
- **ISO**：跨法人的内部交易载体，复用 `sales_order` + 接收方收货 + 内部发票；TO 不承担跨法人。
