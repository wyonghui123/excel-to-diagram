# 规格：端到端转单统一接入 DOC_FLOW（Copy Control）

- 文档版本：v0.1
- 日期：2026-11-05
- 状态：**阶段 0/1/2/3/4/5 已实施**，阶段 5.1「已发运数据错误冲销」已实施（AC-01~AC-28 已验证通过）（2026-11-05）
- 上游依据：
  - 本次端到端流程检查结论（销售→发货→出库、采购→到货→入库、需求→采购/调拨、销售→服务确认）
  - `docs/specs/spec-project-g15-eto-solution-2026-11-04.md` §4（P2 任务轴）
  - 代码契约：`meta/core/doc_flow_rule_store.py`、`doc_flow_schema.py`、`doc_flow_derive_engine.py`、`doc_flow_reversal.py`、`doc_flow_reconcile.py`
- 术语：本文中「转单」= 源单到目标单的派生（SAP Copy Control 语义）；「过账」= 库存事务与余额变更（InventoryPostingService）。

---

## 0. 结论摘要

1. 通用转单规则模型 **DOC_FLOW 已实现**（规则表 + 边表 + 单行/批量派生引擎 + 红字冲销 + 三域对账 + 消耗视图），但**零启用**：`apps/*/app.yaml` 没有任何 `doc_flow` 声明，业务服务中只有 `SalesOrderGuardService` 读边表做防删校验，无任何转单服务写边。
2. 当前实际存在**三套并存模型**：`doc_flow_edges`（转单事实，未启用）、`demand_allocations`（需求分配计划）、`demand_trace_links`（计划/钉住追溯）。
3. 统一原则：
   - **边表 = 唯一转单事实层**（VBFA）：所有产生下游单据/库存事实的转单都写边；
   - **过账服务 = 唯一账实写入口**：库存余额与事务只由 `InventoryPostingService.post()` 写，DOC_FLOW 不直插事务表；
   - **`demand_allocations` 保留「计划」语义**（需求怎么分），不作为转单事实；
   - **`demand_trace_links` 保留「计划/钉住」语义**（含 `forecast`、`inventory_balance` 等非单据节点、`plan_version` 与有效期），**不降级为边表派生视图**；
   - **两表之上新增只读统一追溯面**（view 元模型 `v_demand_trace_graph`：执行层取边表、计划层取线索表），读统一、写边界不变。
4. 接入范围不是"全部"：单据→单据必须接；单据→库存事务应当接（attach 模式）；纯状态动作与派生视图不必接。
5. 退货执行缺口按**方案 A** 处理：复用交货单 + 单据类别 `return` 反向入库，不新建独立退货单/退货收货单对象（与 SAP Returns Delivery、Oracle RMA 一致）；阶段 5 实施，验收 AC-19~AC-23。

---

## 1. 现状审计

| 链路 | 现有实现 | 是否写 `doc_flow_edges` |
|---|---|---|
| 请购 → 采购订单 | `requisition_po_conversion.convert()`（[L73](file:///d:/filework/excel-to-diagram/meta/services/requisition_po_conversion.py#L73)）+ `demand_allocations` | ❌ |
| 采购订单 → 收货单 | BO Action `receipt.create_from_schedule`（[注册](file:///d:/filework/excel-to-diagram/meta/services/bo_action_registrations.py#L837)） | ❌ |
| 收货 → 入库事务 | `receipt_service.post()`（[L420](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L420)）→ `_post_receipt_inventory`（[L1003](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L1003-L1075)）→ `InventoryPostingService.post()` | ❌ |
| 销售订单 → 交货单 | `ShipmentService.create_shipment()`（[L93](file:///d:/filework/excel-to-diagram/meta/services/shipment_service.py#L93)） | ❌ |
| 交货确认 → 出库事务 | **无**（[ship_confirm](file:///d:/filework/excel-to-diagram/meta/services/shipment_service.py#L157-L224) 只回写状态/核销预留） | ❌ |
| 需求分配 → 调拨单 | BO Action `transfer_order.create_from_allocation`（[注册](file:///d:/filework/excel-to-diagram/meta/services/bo_action_registrations.py#L1152)；服务 [L80](file:///d:/filework/excel-to-diagram/meta/services/transfer_order_from_allocation.py#L80-L164)） | ❌ |
| 调拨发运 → 库存事务 | `transfer_shipment_service.post()`（[L241](file:///d:/filework/excel-to-diagram/meta/services/transfer_shipment_service.py#L241)）；`transfer_order_service`（[L526-L568](file:///d:/filework/excel-to-diagram/meta/services/transfer_order_service.py#L526-L568)）调用过账 | ❌ |
| 销售 → 服务确认 | 无服务层（`service_request`/`service_event` 仅 schema） | ❌ |
| 服务确认 → 开票/收入 | 无对象 | ❌ |

审计证据：

- 全仓引用 `doc_flow_edges/doc_flow_rule` 的 19 个文件中，业务服务仅 `sales_order_guard_service.py`（[L1791-1797](file:///d:/filework/excel-to-diagram/meta/services/sales_order_guard_service.py#L1791-L1797)），且查询 fail-open。
- `apps/warehouse|tms|hello_world/app.yaml` 均无 `doc_flow:` 节点；`_prepare_doc_flow`（[app_registry.py L863-928](file:///d:/filework/excel-to-diagram/meta/core/app_registry.py#L863-L928)）因此从未执行。
- `meta/schemas/requisition.yaml:16` 已写明设计口径：「下游单据关系由 doc_flow_edges 记录」——**设计已定、实现未接**。

---

## 2. 目标与非目标

### 2.1 目标

| # | 目标 |
|---|---|
| G1 | 所有「单据→单据」转单统一写 `doc_flow_edges`，形成可审计的端到端转单事实链 |
| G2 | 「单据→库存事务」转单以 attach 模式补边，支持红字冲销与数量核对 |
| G3 | `ship_confirm` 补齐出库过账，消除"已发货、库存未扣"的账实不符（P0） |
| G4 | 数量幂等与池隔离：重复派生不重复记数、Σ 派生量不超过源数量 |
| G5 | 对账可发现「有事务无边」「有边无事务」「源目标数量不一致」 |
| G6 | 追溯查询由统一只读追溯面驱动（执行层 `doc_flow_edges` / 计划层 `demand_trace_links`），不再出现两套查询口径 |
| G7 | 退货执行可表达：交货单按单据类别反向入库（退货交货），退货事实与数据错误冲销可区分 |

### 2.2 非目标

- 不新建 BOM/项目 BOM/Order BOM；
- 不把审批、预留创建、核销、状态推进接入 DOC_FLOW（不产生下游单据）；
- 不用 DOC_FLOW 替代 `InventoryPostingService`（禁止直插库存事务）；
- 不改成本口径，不实现 `v_project_cost`（P2-3 后置）；
- 不实现服务确认/开票对象本身，只预留规则位。
- 不删除、不改写 `demand_trace_links` 的计划语义，也不把它替换为边表（计划节点与钉住口径无法由边表表达）。
- 不把统一追溯视图做成可写入口（写仍走各自权威服务）。
- 不新建独立退货单/退货收货单对象：退货复用既有单据 + 单据类别（方案 A）；退货检验/维修/报废分支（ARM）不在本规格实现。

---

## 3. 模型契约（以现有代码为准）

### 3.1 规则表 `doc_flow_rule`（平台库）

| 列 | 含义 |
|---|---|
| `rule_id` | 规则唯一标识 |
| `source_bo` / `target_bo` | 源/目标业务对象 |
| `source_qty_field` | 从源行取数量的字段（默认 `quantity`） |
| `pool` | 数量池；同池内 Σ 派生量受源数量约束 |
| `status` | `active` / `deprecated`（声明 upsert 不覆盖运行态） |
| `field_map` | 源字段 → 目标字段映射 |
| `split_key` | 批量派生分单键 |
| `target_line_bo` / `head_fk_field` | 头行模式下的目标行对象与头外键 |
| `check_hook` / `map_hook` / `create_hook` | **Phase 1 留空，不执行** |

来源：[doc_flow_rule_store.py L26-64](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_rule_store.py#L26-L64)、upsert [L110-140](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_rule_store.py#L110-L140)。

### 3.2 边表 `doc_flow_edges`（应用库）

记录「已转单事实」：源/目标对象与行、`quantity`、`amount`、`currency`、`unit`、`quantity_sign`、`rule_id`、`derived_at/by`、`status`（`active` / `reversed`）、`pool`、`derive_key`。

- 幂等键为 7 元组（源对象/源 id/源行/目标对象/目标 id/目标行/规则）；
- 唯一写入口为派生引擎，禁止业务代码直接 INSERT。

来源：[doc_flow_schema.py L44-121](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_schema.py#L44-L121)。

### 3.3 派生引擎

- 单行：[doc_flow_derive_engine.py L371-437](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_derive_engine.py#L371-L437)
- 批量：`doc_flow_batch_engine.py`
- 两种模式：
  - `create`：按规则 + `target_data` 新建目标行，同时写边；
  - `attach`：目标行已存在（如过账生成的事务），只写边；
- Σ 校验：同 `(source, pool)` 的派生量之和不得超过源数量，超额抛错并回滚；
- 事务：派生与写边同事务。

### 3.4 冲销

`doc_flow_reversal.py`：红字边（`quantity_sign=-1` 或负数量）+ 原边置 `reversed`；对应业务服务做反向过账。

### 3.5 对账

`meta/tools/doc_flow_reconcile.py`（三域：结构 / 边域 / 视图）：
- 结构：规则引用的 BO/字段是否存在；
- 边域：边是否悬空、幂等冲突、Σ 超额；
- 视图：`v_doc_flow_consumed_qty` 与边表汇总一致。

P0/P1 新增检查项：`inventory_transactions.source_doc_type IN ('shipment','receipt','transfer_order')` 无对应边 → `ORPHAN_TXN`；边指向不存在事务 → `DANGLING_EDGE`。

P2（B+）新增检查项（`_SOURCE_DOC_REGISTRY` 为唯一来源类型注册表）：

| code | 级别 | 含义 |
|---|---|---|
| `UNKNOWN_SOURCE_DOC_TYPE` | warn | 事务来源类型未注册（防新入口绕开 B+ 口径） |
| `MISSING_SOURCE_DOC` | error | 调整/盘点事务的 `source_doc_id` 在来源表不存在（删除策略 restrict，正常不应出现） |
| `UNEXPECTED_ADJUSTMENT_EDGE` | warn | 调整/盘点事务被转单边引用（违反「不接入 DOC_FLOW」，会把调整量带进需求追溯执行层） |

未注册类型：`shipment` / `receipt` / `transfer_order`（过账，必须有边）、`inventory_adjustment` / `inventory_count`（C 类，只保留事实引用）、`opening`（批次号 CRC32，无来源表）、`inventory_segment_transfer`（事件键来源）。

---

## 4. 接入分类矩阵

| 类别 | 链路 | 判定 | 派生模式 |
|---|---|---|---|
| A. 单据→单据 | 请购→采购订单 | 必须接 | create / attach |
| A | 采购订单→收货单 | 必须接 | attach |
| A | 销售订单→交货单 | 必须接 | attach |
| A | 需求分配→调拨单 | 必须接 | attach |
| A | 调拨单→调拨发货单（调拨行 → 发货行） | 必须接（v231 补齐） | attach |
| A | 调拨单→调拨收货单（调拨行 → 收货行） | 必须接（v231 补齐） | attach |
| A | 销售退货 → 退货交货（退货订单计划行 → 退货交货行） | 必须接（方案 A） | attach |
| A | 数据错误冲销（货物未真实离库） | 必须接 | reversal（`reverse_edge` + 反向过账，与退货路径分开） |
| A | 服务确认→开票（未来） | 必须接 | create |
| B. 单据→库存事务 | 收货→入库事务 | 应当接 | attach |
| B | 交货→出库事务 | 应当接（P0） | attach |
| B | 调拨发运→事务 | 应当接 | attach |
| C. 调整/盘点→库存事务 | 库存调整→调整事务 | 不接入（B+：保留 `source_doc_type`/`source_doc_id` 事实引用） | — |
| C | 库存盘点→盘盈盘亏事务 | 不接入（B+：盘点差异由盘点单承载，不做 Copy Control） | — |
| C | 期初导入→期初事务 | 不接入（批次号即来源，无单据对象） | — |
| D. 纯状态/派生 | 审批、预留创建/核销、履约状态回写、`v_project_cost` | 不必接 | — |

> C 类判定依据（Oracle Fusion / SAP 对照）：库存调整、盘点差异是**事务源头**，其 `source_doc_type/source_doc_id` 只作为事实引用（等价 Oracle `SourceCode/SourceHeaderId/SourceLineId`），不进入单据派生（Copy Control 仅用于销售/采购等凭证派生，盘点差异走差异凭证 + 调整科目）。只有「调整单/盘点单」升级为受控单据（审批 + 行 + 状态机）后，才按受限 A 形态接入：`edge_kind='adjustment'`、带符号 delta、独立 pool 不参与 Σ、排除需求追溯。

---

## 5. 逐链路设计

### 5.1 交货确认 → 库存事务（正向出库 / 退货入库，P0 + P0.5）

**触发点**：`ShipmentService.ship_confirm()`（[L157-224](file:///d:/filework/excel-to-diagram/meta/services/shipment_service.py#L157-L224)）

**方向决议（方案 A）**：读交货单 `document_type_id` → `type_definitions.document_category`（`scope_bo='shipment'`、`level='header'`）：

- `document_category='return'` → **退货入库**分支；
- 其他值或缺失 → **正向出库**分支（存量类型兼容，按 `sales` 解释）。

**行不带方向**：沿用 `sales_order` 口径，方向只在抬头类型上。

**顺序**（两分支相同，外层事务）：

```
① 校验 staged / 序列号 / HU
② 类型一致性守卫（见下）
③ InventoryPostingService.post(entries, source)      # 唯一写库存
④ doc_flow derive(attach)                            # 只写边
⑤ 回写 schedule delivered_qty / 行/头状态
⑥ 核销预留 + demand_trace（仅正向分支）
```

**过账参数（按分支）**：

| 项 | 正向出库 | 退货入库（P0.5） |
|---|---|---|
| `direction` | `out` | `in` |
| `transaction_type_id` | `ISSUE_TO_SHIP` | `RETURN_IN`（`category='receipt'`、`direction='in'`，按 v204 模式 seed） |
| `source_event_key` | `shipment:{id}:ship` | `shipment:{id}:return` |
| 边规则 `rule_id` | `shipment_line_to_issue_txn` | `shipment_line_to_return_in_txn` |
| `pool` | `inventory_issue` | `inventory_return` |
| 核销预留 / `demand_trace` | 是 | 否（退货不回写履约预留） |

共同字段：`source={source_doc_type:'shipment', source_doc_id:delivery_id, transaction_date, created_by}`；每行 entry 带 `qty`（保持正数）、`item_id/location_id/batch_id/serial_no/hu_id`、`project_id`（抬头）、`project_task_id`（行）、`source_line_id`。

**规则（阶段 5 新增退货规则）**：

| 字段 | 值 |
|---|---|
| `rule_id` | `shipment_line_to_return_in_txn` |
| `source_bo` → `target_bo` | `shipment_line` → `inventory_transaction` |
| `source_qty_field` | `qty` |
| `pool` | `inventory_return` |
| `status` | `active` |

attach 模式：`target_data={'id': txn_id, 'item': line_id, 'amount': 0, 'unit': uom_id}`。

**类型一致性守卫**：

1. 交货单类别与来源订单类别必须一致：`shipment.document_type_id → category` 对比 `shipment.order_id → sales_orders.document_type_id → category`；不一致 → `DN_CATEGORY_MISMATCH`，零事务、零边。
2. 行 `schedule_id` 所属订单必须等于 `shipment.order_id`（现状由 `order_line_id` 冗余校验，缺时以 schedule 反查）。
3. 退货单行合法性由 R-RET-1~9 在订单侧保证；发运侧复用 R-DN-1（`qty > 0` 且不超过计划剩余量）。

**幂等**：`source_event_key` 去重 + 边 7 元组幂等；状态机保证 `staged→shipped` 单次。

**过账开关**：`inventory_posting_enabled=0`（迁移默认值）时两分支均**跳过过账与转单边，不阻断发运**——与收货同口径的过渡期行为；开关开启后才校验负库存/批次/段，失败即拒绝并整体回滚。

**退货 ≠ 冲销（关键语义）**：

- **业务退货** = 新事实：生成退货交货 + `RETURN_IN` 入库 + 新边；原正向 `shipment_line_to_issue_txn` 边保持 `active`，不置 `reversed`。
- **数据错误冲销** = 货物未真实离库：调用 `reverse_edges_by_source` + 反向过账（`InventoryPostingService.reverse_by_source`），不得用退货单掩盖数据错误。入口见下「5.1.1 已发运数据错误冲销（阶段 5.1）」。
- P0 仍禁止已 `shipped` 单据取消（R-DN-2 不变）；数据错误改走 `reversed` 终态，`cancelled` 语义不变。

**5.1.1 已发运数据错误冲销（阶段 5.1，全量回滚版）**

评审结论：`shipped` / `delivered` 后无冲销入口是真实缺口；序列号、装箱（HU）、预留三处的「不回滚」并**不是不支持**——前两者已有现成反向原语，仅预留缺反向核销，故本阶段一次做全量回滚，不保留已知边界。

| 项 | 落地 |
|---|---|
| 状态机 | `shipped` / `delivered` → `reversed`（新增终态，行状态同步）；`draft`/`released`/`staged` 拒绝（`DN_STATE_INVALID`）；`reversed` 幂等重入 |
| 库存 | `InventoryPostingService.reverse_by_source`：`source_event_key = shipment:{id}:{ship\|return}_reverse`，原事件键 `shipment:{id}:{ship\|return}`；生成 `REVERSAL` 分录并回指 `reversal_of_transaction_id` |
| 单据边 | `reverse_edges_by_source(rule_id, 'shipment_line', line_id, ref_id=delivery_id)`：红字边 `quantity_sign='red'`（`derive_key='red:<原边id>:<交货单id>'`、`rule_id` 带 `#red:<交货单id>`）+ 原边 `reversed` |
| 序列号 | `SerialNumberService.reverse_serial_event(txn_id)`：按原出库事务逐条反冲（退货方向未登记，自动 no-op） |
| 装箱 HU | `HandlingUnitService.reverse_document('shipment', delivery_id)`（退货方向未装箱，自动 no-op） |
| 预留 | `InventoryReservationService.unfulfill_by_demand('sales_order_line', line_id, qty, reason)`：`fulfilled`/`partially_fulfilled` → `open`，`qty_fulfilled` 回退（新增原语） |
| 计划行 | `delivered_qty = MAX(delivered_qty − 行数量, 0)`，归零时清 `delivery_id`；`completed` 回落 `confirmed`；随后 `SalesOrderFulfillmentService.recompute_order` |
| 审计 | 抬头写 `reversed_at` / `reversal_reason`（v223 迁移新增两列）+ 新权限 `shipment:shipment_reverse` |
| 权限 / UI | `shipment.yaml` 新增 `reverse_shipment` 规则（`shipped`/`delivered` → `reversed`，二次确认文案明确「数据错误」）与 `reversed` 状态枚举；拦截器 `ShipmentGuardInterceptor` 委托 `service.reverse()` |

**边界（本阶段不做）**：调拨发运已发运行的冲销入口仍为 P1——现状不是缺冲销，而是 `TransferShipmentService.post()` 正向过账/边未接（R3 范围内仅委托记账），待正向接入后复用同一套 `reverse_by_source`。退货检验/维修/报废分支仍不在本规格。

**追溯口径**：`v_demand_trace_graph.signed_qty` 定义「对源单履约量的净贡献」——出库 `+qty`、退货入库 `-qty`；由阶段 5 迁移刷新视图 SQL（仍 17 列，`relation` 区分 `shipment_line_to_issue_txn` / `shipment_line_to_return_in_txn`）。

**对账**：`ORPHAN_TXN` 判定纳入 `RETURN_IN` 事务；退货边与事务数量互检沿用 `DANGLING_EDGE` / 数量一致规则。

### 5.2 请购 → 采购订单

**触发点**：`requisition_po_conversion.convert()`（[L73](file:///d:/filework/excel-to-diagram/meta/services/requisition_po_conversion.py#L73)）

- 规则：`requisition_line_to_po_line`，`source_bo=requisition_line`，`target_bo=purchase_order_line`，`source_qty_field=qty`，`pool=purchasing`。
- 现有 `demand_allocations` 继续记录"需求分配到 PO 行"（计划层），派生后 **attach 写边**，数量取实际转单量。
- 幂等：重复转换不重复建 PO（现有状态机）+ 边 7 元组。

### 5.3 采购订单 → 收货单

- 规则：`po_schedule_to_receipt_line`，`source_bo=purchase_order_schedule`，`target_bo=receipt_line`，`source_qty_field=promised_qty`（实际以收货行数量为准，`quantity` 取实收），`pool=purchasing`。
- 触发点：`receipt.create_from_schedule` handler 内，创建收货行后 attach。

### 5.4 收货 → 入库事务

- 规则：`receipt_line_to_inventory_txn`，`source_bo=receipt_line`，`target_bo=inventory_transaction`，`source_qty_field=qty_received`（`receipt_line` 无 `qty` 列；`quantity` 取净收 = `qty_received - qty_rejected`），`pool=inventory_receipt`。
- 触发点：`_post_receipt_inventory`（[L1003](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L1003-L1075)）过账成功后 attach；项目/任务维度按 active `demand_allocation` 带出（既有 G7）。
- 冲销：收货 reverse 时红字边 + 反向过账。

### 5.5 销售订单 → 交货单

- 规则：`so_schedule_to_shipment_line`，`source_bo=sales_order_schedule`，`target_bo=shipment_line`，`source_qty_field=promised_qty`（`sales_order_schedule` 无 `qty` 列；`quantity` 取交货行实际数量），`pool=sales_delivery`。
- 触发点：`ShipmentService.create_shipment()` 写行后 attach。
- 继承维度：`project_id`（抬头）、`project_task_id`（行），与 P2 实现一致。

### 5.6 需求分配 → 调拨单

- 规则：`allocation_to_transfer_line`，`source_bo=demand_allocation`，`target_bo=transfer_order_line`，`source_qty_field=qty`，`pool=transfer`。
- 触发点：`transfer_order_from_allocation.create_from_allocation()`（[L80-164](file:///d:/filework/excel-to-diagram/meta/services/transfer_order_from_allocation.py#L80-L164)）。
- 当前仅支持 `demand_bo='requisition'`；扩大来源需单独评审。

### 5.7 调拨发运 → 库存事务

- 规则：`transfer_order_line_to_issue_txn`，`source_bo=transfer_order_line`，`target_bo=inventory_transaction`，`source_qty_field=qty`，`pool=transfer_move`。
- 触发点：`transfer_shipment_service.post()`（[L241](file:///d:/filework/excel-to-diagram/meta/services/transfer_shipment_service.py#L241)）委托 `transfer_order_service` 过账（[L526-L568](file:///d:/filework/excel-to-diagram/meta/services/transfer_order_service.py#L526-L568)），记账只发生一次；源行是 `transfer_order_line`（不存在独立的 transfer_shipment 事务行）。

### 5.8 销售 → 服务确认（预留）

- 前置：先落地服务行识别与服务确认单据（见 P2 断点 3），不在本规格实现。
- 规则位：`sales_order_line_to_service_confirmation`，`pool=service_delivery`。

### 5.9 服务确认 → 开票（预留）

- 规则位：`service_confirmation_to_invoice_line`，`pool=billing`；依赖开票对象先落地。

### 5.10 统一追溯读面（view 元模型，阶段 4 方案）

**结论**：适合，但只作为**只读读面**。`object_type: view` + `view_definition` 能把执行层 `doc_flow_edges` 与计划层 `demand_trace_links` 投影成同一列族，直接获得通用 read/list API 与只读护栏；**不适合**替代两张权威表，也不适合把 `demand_trace_links` 改成边表派生视图。

**为什么不能替代存储**：

| 语义 | `doc_flow_edges` | `demand_trace_links` | 能否映射 |
|---|---|---|---|
| 关系性质 | 转单事实（Copy Control） | 计划/钉住（reservation / pegging / allocation） | 不同维度 |
| 节点域 | 单据/单据行、库存事务 | 含 `forecast`、`inventory_balance` 等非单据节点 | 边表无对应节点 |
| 数量语义 | 源行被消耗量（append-only） | 分配量（可原地改量、`valid_to` 失效） | 不可逆映射 |
| 有效期 | 无（事实不可变） | `plan_version` + `valid_from/to` | 边表无 |
| ATP | 不参与 | `_sum_inbound_pegged` 依赖 `peg_type='hard'` | 边表无 peg 维度 |
| 写路径 | derive / attach / reversal 引擎 | `DemandTraceService` | 不同服务 |

**视图元数据**（`meta/schemas/demand_trace_graph.yaml`）：

- `object_type: view`、`table_name: v_demand_trace_graph`；
- 无 `write_anchor` ⇒ `manage_service._reject_if_readonly_view` 拒绝写（`READ_ONLY_VIEW`）；
- `import_export.auto_crud: false`，仅声明 read / list 动作；
- `ui_view_config.skip_auto_menu: true`（只读追溯面，不单独挂菜单）；
- `relations: []`，**不挂 `dimension_bindings`**（两表均无 org 列，挂绑定会静默注入过滤得空集）。

```yaml
id: demand_trace_graph
name: 统一追溯图谱
table_name: v_demand_trace_graph
description: 只读统一追溯面：执行层取 doc_flow_edges，计划层取 demand_trace_links
display_name_field: id
object_type: view
view_definition: |
  SELECT
    'execution' AS layer,
    'E:' || e.id AS id,
    e.rule_id AS relation,
    e.source_bo AS source_object_type,
    e.source_id AS source_object_id,
    COALESCE(e.source_item, '') AS source_line_id,
    e.target_bo AS target_object_type,
    e.target_id AS target_object_id,
    COALESCE(e.target_item, '') AS target_line_id,
    e.quantity AS qty,
    CASE WHEN e.quantity_sign = 'red' THEN -e.quantity ELSE e.quantity END AS signed_qty,
    e.status AS status,
    NULL AS peg_type,
    NULL AS plan_version,
    NULL AS valid_from,
    NULL AS valid_to,
    e.derived_at AS occurred_at
  FROM doc_flow_edges e
  UNION ALL
  SELECT
    'plan' AS layer,
    'T:' || CAST(t.id AS TEXT) AS id,
    t.trace_type AS relation,
    t.supply_object_type AS source_object_type,
    CAST(t.supply_object_id AS TEXT) AS source_object_id,
    COALESCE(NULLIF(CAST(t.supply_line_id AS TEXT), '0'), '') AS source_line_id,
    t.demand_object_type AS target_object_type,
    CAST(t.demand_object_id AS TEXT) AS target_object_id,
    COALESCE(NULLIF(CAST(t.demand_line_id AS TEXT), '0'), '') AS target_line_id,
    t.allocated_qty AS qty,
    CASE WHEN t.valid_to IS NULL THEN t.allocated_qty ELSE 0 END AS signed_qty,
    CASE WHEN t.valid_to IS NULL THEN 'active' ELSE 'expired' END AS status,
    t.peg_type AS peg_type,
    t.plan_version AS plan_version,
    t.valid_from AS valid_from,
    t.valid_to AS valid_to,
    t.computed_at AS occurred_at
  FROM demand_trace_links t
import_export:
  auto_crud: false
actions:
  - id: demand_trace_graph_read
    name: 查询追溯关系
    type: crud
    method: GET
    path: "/api/v1/demand_trace_graphs/{id}"
  - id: demand_trace_graph_list
    name: 查询追溯关系列表
    type: crud
    method: GET
    path: "/api/v1/demand_trace_graphs"
```

`fields` 按下列列映射逐一声明（`layer` / `id` 必填）：

| 列 | 类型 | 执行层来源 | 计划层来源 | 说明 |
|---|---|---|---|---|
| `layer` | string | 常量 `execution` | 常量 `plan` | 分层标识 |
| `id` | string | `'E:' || id` | `'T:' || id` | 跨层稳定主键 |
| `relation` | string | `rule_id` | `trace_type` | 关系类型 |
| `source_object_type` | string | `source_bo` | `supply_object_type` | 源（供应）对象 |
| `source_object_id` | string | `source_id` | `supply_object_id` | 统一转字符串 |
| `source_line_id` | string | `source_item` | `supply_line_id`（0→空） | 行级标识 |
| `target_object_type` | string | `target_bo` | `demand_object_type` | 目标（需求）对象 |
| `target_object_id` | string | `target_id` | `demand_object_id` | 统一转字符串 |
| `target_line_id` | string | `target_item` | `demand_line_id`（0→空） | 行级标识 |
| `qty` | number | `quantity` | `allocated_qty` | 原始数量 |
| `signed_qty` | number | 红字取负 | 失效取 0 | 可直接求和 |
| `status` | string | `active/reversed` | `active/expired` | 统一状态 |
| `peg_type` | string | NULL | `hard/soft` | 钉住强度（仅计划层） |
| `plan_version` | string | NULL | `plan_version` | 计划版本（仅计划层） |
| `valid_from` | datetime | NULL | `valid_from` | 有效期（仅计划层） |
| `valid_to` | datetime | NULL | `valid_to` | 有效期（仅计划层） |
| `occurred_at` | datetime | `derived_at` | `computed_at` | 发生/计算时间 |

**创建与刷新**：

- 迁移 `v219__demand_trace_graph_view.py` 负责：两基表同库 → `DROP VIEW IF EXISTS` + `CREATE VIEW`；任一缺失 → `[SKIP]` 并记录原因。
- 不用 `schema_generator` 自动建：它只发 `CREATE VIEW IF NOT EXISTS`（`schema_generator.py` L86-98），**定义变更不会生效**；定义真源仍是 YAML，刷新由迁移负责。
- **同库前提**：SQLite 视图不能跨库 UNION。当前 `v205`（trace）与 `v214/v215`（edges）均落平台库，满足；若未来应用库启用 doc_flow 而 trace 留在平台库，则该库 `[SKIP]`，不得用 `ATTACH` 跨库。
- **全局 sync 兜底**：SQLite 的 `CREATE VIEW` 不校验基表存在（缺表时建视图成功、查询期才报 `no such table`），因此 `TraceGraphService` 对查询失败按空读处理；同时 `SchemaMigrator`（`schema_generator.py` L399-415）已把 VIEW 建表失败纳入降级告警，兼容未来会校验的方言，避免中断整轮 sync。

**遍历不在视图里做**：视图只做列投影与分层，不做方向/深度参数化。`TraceGraphService` 在视图上做逐跳查询（深链用递归 CTE，限制深度与节点数），避免把运行时条件写进 `view_definition`。

---

## 6. 统一改造路径

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| **0 启用** | 规则声明 + 边表初始化 + 对账命令 | `doc_flow_rule` 有 active 规则；`doc_flow_edges` 存在；reconcile 可运行 |
| **1 P0** | 5.1 交货→出库（post + attach） | 发运后余额扣减、事务与边一致 |
| **2 存量补边** | 5.2~5.6 各加 1 处 attach | 6 条主链路均有边，测试通过 |
| **3 冲销统一** | 取消/退货/红字 | 已实施（收货链路）：边 `reversed` + 红字边 + 余额回补一致 |
| **4 追溯统一** | 只读统一追溯面 `v_demand_trace_graph`（view 元模型）+ 写边界治理 + 跨层对账 | 追溯查询走单一读面；两表保持权威；无越层直写 |
| **5 P0.5 退货执行** | 5.1 退货入库分支（类型决议 + `RETURN_IN` 过账 + 独立规则/池）+ 退货≠冲销语义 | AC-19~AC-23 通过；正向链路零回归 |
| **5.1 冲销入口** | 5.1.1 已发运数据错误冲销（全量回滚：库存/边/序列号/HU/预留/计划行/履约） | AC-24~AC-28 通过；调拨发运 P1 |

**阶段 0/1 实施记录（2026-11-05）**：

| 项 | 落地 |
|---|---|
| 迁移 | `meta/migrations/v214__doc_flow_shipment_issue_rule.py`（建边表/索引/消耗视图 + upsert 规则，幂等，不覆盖运行态 `status`） |
| 服务 | `ShipmentService.ship_confirm` → `_post_issue_inventory`（过账）→ `_write_issue_edges`（attach 边） |
| 段解析 | 任务行走 `project_task` 段；非任务行仅在物料 `so_segment_enabled=1` 时走 SO 专用段；寄售仅在 `consignment_enabled=1` 时带所有权方 |
| 测试 | `meta/tests/test_shipment_issue_doc_flow.py`（6 例：开关关闭/正向过账+边/规则缺失降级/负库存回滚/重放幂等/迁移幂等） |
| 回归 | `test_shipment_service`(32) · `test_inventory_posting`(23) · `test_mto_consignment_flow`(3) · `test_doc_flow`(28) 全绿 |

**阶段 2 实施记录（2026-11-05）**：

| 项 | 落地 |
|---|---|
| 迁移 | `meta/migrations/v215__doc_flow_stage2_rules.py`（6 条规则幂等 upsert + 建表/索引/视图兜底） |
| 工具 | `meta/core/doc_flow_attach.py` `attach_edge()`：规则缺失 / 未启用 / 派生失败 → 告警并返回 False，不阻断存量链路 |
| 请购→PO | `requisition_po_conversion.convert()` 创建 PO 行与分配后 attach |
| PO→收货 | `receipt_actions.create_from_schedule_handler` 建单后按 `receipt_lines.schedule_id` attach |
| 收货→入库 | `receipt_service._post_receipt_inventory` 返回 `{收货行: 事务}`，`_write_receipt_inbound_edges` attach（RCV_PO/RCV_TO/RCV_WO 同口径） |
| SO→交货 | `shipment_service.create_shipment` 写行后 attach；`_insert_line` 返回行 id |
| 分配→调拨 | `transfer_order_from_allocation._write_back` 回写分配时 attach |
| 调拨发运→事务 | `transfer_order_service._post_ship_inventory` 过账后 attach；`transfer_shipment.post` 委托记账，仅一次（R3 已确认） |
| 测试 | `meta/tests/test_doc_flow_stage2_edges.py`（3 例：迁移幂等 / attach 写边与降级 / SO→交货接线）；相关服务与 DOC_FLOW 回归全绿 |

### 阶段 3 实施记录（2026-11-05，已实施）

**现状核查结论（2026-11-05）**：

| 链路 | 是否存在「已过账冲销」业务入口 | 结论 |
|---|---|---|
| 收货 → 入库事务 | 有：`ReceiptService.reverse()` 覆盖 PO / TO / WO 三支；`_reverse_receipt_inventory()` 已做反向过账 | **本阶段接入红字边** |
| 发运 → 出库事务 | 无：`ShipmentService.cancel()` 仅 draft/released；`shipped` 之后按 R-DN-2 禁止取消，且无 reverse 方法 | **阶段 5.1 已补**：`ShipmentService.reverse()` + `reversed` 终态（AC-24~AC-28） |
| 调拨发运 → 事务 | 无：`TransferOrderService.cancel()` 要求总发货量 = 0；`create_reversal()` 只建反向**草稿**，其发运走正常正向规则 | 反向调拨单发运已由阶段 2 正向规则产生正常边；已发运行无冲销入口（P1） |

**实现方案（仅收货链路，不改 schema、不新增迁移）**：

| 文件 | 变更 |
|---|---|
| `meta/core/doc_flow_attach.py` | 新增 `reverse_edges_by_source(app_ds, rule_id, source_bo, source_id, *, ref_id, derived_by='') -> int`：查询该源行 `status='active' AND quantity_sign='normal'` 的边；逐条先 `red_ink_edge(quantity=边数量, ref_id=红字单)` 再 `reverse_edge`（级联红字子边，聚合归零）；单条失败仅告警并继续，返回成功条数 |
| `meta/services/receipt_service.py` | 新增 `ReceiptService._reverse_receipt_inbound_edges(line_ids, red_receipt_id)`：对每行调用上述 helper，规则 `receipt_line_to_inventory_txn`、`source_bo='receipt_line'`；模块/边表缺失降级为告警 |
| 同上 `reverse()`（PO 支） | `_reverse_receipt_inventory()` 之后调用：`[item['line']['id'] for item in source_items]` + `red_id` |
| 同上 `_reverse_transfer_order()` | `_reverse_receipt_inventory()` 之后调用：`[line['id'] for line, _ in source_items]` + `red_id` |
| 同上 `_reverse_work_order()` | 同上 |
| `meta/tests/test_doc_flow_stage3_reversal.py`（新增） | 3 例：① 红冲后原边 `reversed`、红字边落库（`quantity_sign='red'`、`rule_id` 带 `#red:<红字单id>`、`derive_key='red:<原边id>:<红字单id>'`）、重复红冲被状态守卫 `RC_STATE_INVALID` 拒绝；② 边表缺失时红冲仍成功（降级）；③ helper 直测：全部冲销后消耗视图归零、二次调用 0 新增（幂等） |

**验收与回归**：

1. `python d:\filework\test.py --single meta/tests/test_doc_flow_stage3_reversal.py`
2. `python d:\filework\test.py --single meta/tests/test_receipt_reversal.py`
3. `python d:\filework\test.py --single meta/tests/test_receipt_service.py`
4. `python d:\filework\test.py --single meta/tests/test_doc_flow_reversal.py`
5. `python d:\filework\test.py --single meta/tests/test_doc_flow_stage2_edges.py`

**执行结果（2026-11-05）**：新增 3 例通过；收货红冲、收货服务、DOC_FLOW 冲销引擎、阶段 2 补边套件回归全绿。无新迁移（边表列已由 v214/v215 提供）。发运已发运行的冲销入口已由**阶段 5.1** 补齐（`ShipmentService.reverse()`，复用 `reverse_edges_by_source`）；调拨发运仍为 P1（正向过账/边未接）。

**对账增强（AC-14 / AC-15，2026-11-05）**：

| 项 | 落地 |
|---|---|
| 巡检域 | `doc_flow_reconcile.scan` 新增④库存事务互检：`ORPHAN_TXN`（发运/收货/调拨事务无任何边引用，REVERSAL 豁免）、`DANGLING_EDGE`（边指向不存在事务）；库无 `inventory_transactions` 表时跳过本域 |
| AC-14 测试 | `test_doc_flow_reconcile.py` 新增 6 例：边事务匹配 / 孤儿事务 / 调拨类型纳入 / REVERSAL 豁免且原边 reversed 仍计数 / 悬空边 / 无事务表跳过 |
| AC-15 测试 | `test_doc_flow_stage2_edges.py` 新增端到端链路例：销售计划行 → 交货行 → 出库事务，相邻两跳消耗量一致 |
| 回归 | 对账 29 例、阶段 2 4 例全绿 |

### 阶段 4 方案与实施（view 元模型，2026-11-05）

**判定**：`demand_trace_links` **不改为边表派生视图**（语义不可映射，见 §5.10）；新增只读统一追溯面 `v_demand_trace_graph`，两表各自保持权威。

| 工作项 | 落地 | 验收 |
|---|---|---|
| 视图元数据 | `meta/schemas/demand_trace_graph.yaml`：`object_type: view` + `view_definition`（§5.10）+ 仅 read/list + `auto_crud: false` | AC-16 |
| 视图创建/刷新 | `meta/migrations/v219__demand_trace_graph_view.py`：两基表同库 → `DROP VIEW` + `CREATE VIEW`；缺表 `[SKIP]` | AC-16 |
| 只读护栏 | 不设 `write_anchor` ⇒ `manage_service` 返回 `READ_ONLY_VIEW`；写仍走 `DemandTraceService` / derive 引擎 | AC-18 |
| 写边界治理 | `doc_flow_edges` 唯一写入口 = derive/attach/reversal；`demand_trace_links` 唯一写入口 = `DemandTraceService`（`shipment_service._fulfill_reservations` 已委写，保持，不新增直插） | AC-18 |
| 跨层对账 | `doc_flow_reconcile.scan` 增⑤：`TRACE_EDGE_QTY_MISMATCH`（仅 `trace_type='reservation'` 且映射可确定：按 SO 行比较 active trace Σ 与 `shipment_line_to_issue_txn` 边 Σ；缺 `shipment_lines`/任一基表则跳过本域） | AC-17 |
| 遍历服务 | 新增 `TraceGraphService`（方向/深度由服务层实现，视图不含动态条件） | AC-16 |

**边界（不做）**：

- 不把 `demand_trace_links` 的表改成视图，不迁数据；
- 不在视图上挂 `dimension_bindings`（两表均无 org 列）；
- 不用视图承接消耗量聚合（`v_doc_flow_consumed_qty` 继续独立）；
- 不做跨库 `ATTACH`。

**跨层对账口径（防假阳性）**：

- 仅比较**同一 SO 行**内 `trace_type='reservation'`（发运核销写入，`peg_type='soft'`）的计划量与执行量；`trace_type='pegging'`（硬钉住/ATP）不参与对比；
- 两层任一侧为空不报（可能是历史缺失，不是漂移）；
- 容差 `1e-4`。

**阶段 4 实施记录（2026-11-05）**：

| 项 | 落地 |
|---|---|
| 视图元数据 | `meta/schemas/demand_trace_graph.yaml`（`object_type: view`，仅 read/list，17 列统一映射） |
| 迁移 | `meta/migrations/v219__demand_trace_graph_view.py`（同库两基表 → `DROP VIEW` + `CREATE VIEW`；缺表 `[SKIP]`；`VIEW_SQL` 与 YAML 逐字一致） |
| 遍历服务 | `meta/services/trace_graph_service.py`（`list_links` 端点过滤；`trace` 双向 BFS，限制深度/节点数） |
| 跨层对账 | `meta/core/doc_flow_reconcile.py` `_trace_edge_findings`（`TRACE_EDGE_QTY_MISMATCH`；缺 `demand_trace_links`/`shipment_lines`/边表或半迁移时跳过） |
| 降级 | `meta/core/schema_generator.py`：VIEW 建表失败仅告警不中断 sync；`TraceGraphService` 查询失败按空读 |
| 测试 | `meta/tests/test_demand_trace_graph.py`（12 例：双层投影 / YAML-SQL 一致 / 双向遍历 / 缺视图空读 / 迁移跳过 / sync 降级 / 跨层对账 4 例 / 只读护栏 / 无直插 SQL） |
| 回归 | `test_doc_flow_reconcile.py`(29) · `test_doc_flow_stage3_reversal.py`(3) · `test_doc_flow_stage2_edges.py`(4) 全绿 |

### 阶段 5 实施计划（方案 A，已实施 2026-11-05）

**决策依据**：SAP 的退货交货（Returns Delivery）复用 delivery 对象并带退货标识；Oracle 的 RMA 是订单类型而非并列对象。两家都不做独立退货单对象，且本仓库红字收货已采用「复用单据 + `document_category='return'`」模式。因此销售退货复用 `shipment`（方案 A），不新建退货收货单（方案 B）。

| 工作项 | 内容 | 验收 |
|---|---|---|
| 类型决议 | `ShipmentService` 读 `document_type_id` → `document_category`；缺失按 `sales` 解释 | AC-20 |
| 类型守卫 | `shipment` 类别 vs `order_id` 所属订单类别不一致 → `DN_CATEGORY_MISMATCH`（零事务/零边） | AC-20 |
| 事务类型 | 迁移 seed `RETURN_IN`（`category='receipt'`、`direction='in'`，按 v204 模式）；缺 `inventory_transaction_types` 表 `[SKIP]` | AC-19 |
| 过账分支 | `_post_issue_inventory` 按类别选 `ISSUE_TO_SHIP`/`RETURN_IN`、`out`/`in`、`shipment:{id}:ship`/`shipment:{id}:return`；退货分支跳过预留核销 | AC-19 |
| 规则 | 迁移 upsert `shipment_line_to_return_in_txn`（`pool=inventory_return`），不覆盖运行态 `status` | AC-21 |
| 边 | `_write_issue_edges` 按分支选规则；两池互不合并计数 | AC-21 |
| 追溯视图 | 同一迁移 `DROP VIEW` + `CREATE VIEW`：`signed_qty` 按规则映射（出库 +、退货 −），列数不变 | AC-22 |
| 对账 | `ORPHAN_TXN` 纳入 `RETURN_IN`；退货边事务互检 | AC-23 |
| 冲销入口 | P0.5 只接「业务退货」；「数据错误冲销」另立阶段 5.1（已实施，全量回滚），不复用退货路径 | AC-22 / AC-24~AC-28 |
| 测试 | 新增 `meta/tests/test_shipment_return_doc_flow.py`（覆盖 AC-19~AC-23） | 全绿 |

**阶段 5 实施记录（2026-11-05）**：

| 项 | 落地 |
|---|---|
| 服务分支 | `meta/services/shipment_service.py`：`_is_return_shipment`（读交货单/来源订单 `document_type_id` 的 `document_category`，缺失继承订单类别）；不一致抛 `DN_CATEGORY_MISMATCH`；退货跳过序列号校验/HU/预留核销 |
| 过账 | `_post_issue_inventory(..., is_return)`：`RETURN_IN` / `direction='in'` / 事件键 `shipment:{id}:return`（与 `:ship` 互不覆盖） |
| 边 | `_write_issue_edges(..., is_return)`：退货走 `shipment_line_to_return_in_txn`（`pool=inventory_return`），正向仍 `shipment_line_to_issue_txn`（`inventory_issue`） |
| 迁移 | `meta/migrations/v222__doc_flow_return_shipment_rule.py`：seed `RETURN_IN` + 退货交货类型（`shipment`/`header`/`RETURN`/`return`）+ upsert 退货规则 + 刷新视图（四分支 `signed_qty`，仍 17 列）；缺表 `[SKIP]` |
| 视图元数据 | `meta/schemas/demand_trace_graph.yaml` `view_definition` 与 v222 逐字一致（出库 +、退货 −、红字取反） |
| 测试 | `meta/tests/test_shipment_return_doc_flow.py`（8 例：退货过账/继承类别/类别不一致/池隔离/退货≠冲销/对账/迁移幂等）；`test_demand_trace_graph.py` 改以 v222 为视图真源（12 例） |
| 回归 | `test_shipment_issue_doc_flow.py`(6) · `test_shipment_service.py`(32) · `test_shipment_schema_rules.py`(5) · `test_doc_flow_reconcile.py`(29) 全绿 |

**阶段 5.1 实施记录（已发运数据错误冲销，2026-11-05）**：

| 项 | 落地 |
|---|---|
| 服务 | `meta/services/shipment_service.py`：新增 `reverse(delivery_id, reason)` + 6 个私有 helper；`STATUS_REVERSED` 纳入 LOCKED / UNDELETABLE |
| 预留原语 | `meta/services/inventory_reservation_service.py`：新增 `unfulfill_by_demand()`（`fulfilled`/`partially_fulfilled` → `open`，重建投影） |
| 拦截器 | `meta/core/interceptors/shipment_guard_interceptor.py`：`reversed` 目标委托 `service.reverse()` |
| 元数据 | `meta/schemas/shipment.yaml` / `shipment_line.yaml`：新增 `reversed` 状态 + `reversed_at` / `reversal_reason` + `reverse_shipment` 规则（`shipped`/`delivered` → `reversed`） |
| 迁移 | `meta/migrations/v223__shipment_reverse.py`：加两列（缺表 `[SKIP]`）+ 权限 `shipment:shipment_reverse`（`INSERT OR IGNORE`）并授权 admin/default |
| 测试 | `meta/tests/test_shipment_reverse.py`（5 例：正向全量回滚+幂等 / 退货方向反冲 / draft 拒绝 / 预留反向核销 / 冲销后禁签收重发） |
| 回归 | `test_shipment_issue_doc_flow.py`(6) · `test_shipment_service.py`(32) · `test_shipment_schema_rules.py`(5→7 条规则) · `test_demand_trace_graph.py`(12) · `test_doc_flow_reconcile.py`(29) · `test_shipment_reverse.py`(5) 全绿 |
| 已知边界 | 调拨发运已发运行的冲销入口 = P1（正向过账/边未接，非冲销缺口） |

**不做（阶段 5 边界）**：

- 不新建退货收货单对象、不动 `shipment_line` 行模型；
- 不实现退货检验/维修/报废分支（留给 ARM 式扩展）；
- 不把退货入库写进 `demand_trace_links`（避免污染履约钉住口径）。

**阶段 0 的两种实现方式（待决策 D1）**：

- **方式 A（声明式）**：新建 app 清单声明 `doc_flow.enabled` + 规则。要求规则引用的 BO 都在该 app 声明；但 `shipment_line`/`inventory_transaction` 当前属于核心 schema，不在 `apps/*`，需要先建 app 清单。
- **方式 B（最小侵入，推荐 P0）**：迁移中调用 `ensure_doc_flow_edge_tables(app_ds)` + `upsert_rules(platform_ds, ...)` 直接落规则。后续再补声明式清单。

---

## 7. 数据迁移与历史回填

| 项 | 规则 |
|---|---|
| 新表 | 无新业务表；边表由 `doc_flow_schema.ensure_doc_flow_edge_tables` 幂等创建 |
| 视图 | 阶段 4 由 `v219` 建/刷 `v_demand_trace_graph`；缺任一基表跳过；不重建基表、不迁数据 |
| 规则 | 新迁移幂等 upsert；重复执行 `[SKIP]`；不覆盖运行态 `status` |
| 移动类型（阶段 5） | `RETURN_IN` 按 v204 模式幂等 seed（`category='receipt'`、`direction='in'`）；`inventory_transaction_types` 缺表 `[SKIP]` |
| 退货规则/视图（阶段 5） | `v222` 幂等 upsert `shipment_line_to_return_in_txn` + `DROP VIEW`/`CREATE VIEW` 刷新符号映射；不迁数据、不改列数 |
| 单据类别（阶段 5） | 不改写存量 `type_definitions.document_category`；缺失按 `sales` 解释，退货类型由业务配置建档 |
| 历史回填 | 按现有外键关系（`source_doc_type/source_doc_id`、`demand_allocations`）扫描生成边；只处理可确定数量的记录；必须 dry-run + 计数报告 |
| 回填顺序 | 先阶段 2 的存量链路，再阶段 1 的事务类；回填脚本可重跑（7 元组幂等） |
| 备份 | 迁移前自动备份应用库（沿用迁移框架） |

---

## 8. 验收用例

| # | 场景 | 期望 |
|---|---|---|
| AC-01 | 规则启用 | `doc_flow_rule` 中 `shipment_line_to_issue_txn` 为 `active`；reconcile 结构域通过 |
| AC-02 | 发运确认（正向） | `inventory_transactions` +1（out）、`inventory_balances` 减 qty、`doc_flow_edges` +1 且 quantity=实发量 |
| AC-03 | 重复发运确认 | 状态机拒绝；无重复事务、无重复边 |
| AC-04 | 超发 | 第二次发运超出源数量 → 拒绝，余额与事务回滚 |
| AC-05 | 任务行发运 | 扣 `project_task` 段；自有段不变；边 source 指向任务行（维度随行） |
| AC-06 | 过账开关关闭 | 发运成功但零事务、零边（过渡期不阻断） |
| AC-07 | 收货→入库 | 过账 + 边各 1 条，数量一致 |
| AC-08 | 请购→PO | 边记录 requisition_line → po_line，重复转换不重复 |
| AC-09 | PO→收货 | 边记录 schedule → receipt_line |
| AC-10 | SO→交货 | 边记录 schedule → shipment_line（含项目任务维度） |
| AC-11 | 分配→调拨 | 边记录 allocation → transfer_line |
| AC-12 | 调拨发运→事务 | 记账一次；边 1 条 |
| AC-13 | 冲销 | 原边 `reversed`、红字边生成、余额回补 |
| AC-14 | 对账 | 构造孤儿事务/悬空边 → 报告 `ORPHAN_TXN` / `DANGLING_EDGE` |
| AC-15 | 端到端追溯 | SO 行 → 交货行 → 出库事务数量可加总一致 |
| AC-16 | 统一追溯读面 | `v_demand_trace_graph` 同时返回 execution 与 plan 行；`layer/id/relation/signed_qty` 正确；通用 list API 可分页过滤 |
| AC-17 | 跨层对账 | 同一 SO 行 trace=10、出库边=12 → 报告 `TRACE_EDGE_QTY_MISMATCH`；两侧为空不报 |
| AC-18 | 只读与写边界 | 对视图发 create/update/delete → `READ_ONLY_VIEW`；发运核销仍经 `DemandTraceService` 写入，无直插 SQL |
| AC-19 | 退货交货入库 | 退货类型交货单 `ship_confirm` → `RETURN_IN` 事务 1 条（`direction='in'`）、余额增加、边 `shipment_line_to_return_in_txn`（`pool=inventory_return`）；重复确认无重复事务/边 |
| AC-20 | 方向分支与类型一致性 | 正向类型 → `ISSUE_TO_SHIP`/`out`；退货类型 → `RETURN_IN`/`in`；交货单类别与来源订单类别不一致 → `DN_CATEGORY_MISMATCH`，零事务零边 |
| AC-21 | 规则与池隔离 | 正向边只落 `inventory_issue`、退货边只落 `inventory_return`；同池内 Σ 派生量 ≤ 源数量，跨池不合并计数 |
| AC-22 | 退货 ≠ 冲销 | 业务退货后原出库边仍 `active`；只有数据错误冲销才 `reversed` + 红字边；`v_demand_trace_graph` 同时返回两条 relation，且 `signed_qty` 出库为正、退货为负 |
| AC-23 | 退货对账 | 无边 `RETURN_IN` 事务 → `ORPHAN_TXN`；退货边指向不存在事务 → `DANGLING_EDGE`；正向单据不误报；缺表降级为空 |
| AC-24 | 已发运数据错误冲销（正向） | `shipped` → `reversed`：库存回补、`REVERSAL` 事务回指原事务、原边 `reversed` + 红字边、计划行 `delivered_qty` 归零、抬头/行 `reversed` 并记录原因；重复冲销零新增（`idempotent`） |
| AC-25 | 退货交货冲销 | 退货类型 `shipped` → `reversed`：`RETURN_IN` 反冲为 `direction='out'` 的 `REVERSAL`，红字边按退货规则（`shipment_line_to_return_in_txn`），计划行按实际回写对称回滚，跳过序列号/HU/预留 |
| AC-26 | 冲销状态守卫 | 仅 `shipped` / `delivered` 可冲销；`draft` / `released` / `staged` → `DN_STATE_INVALID` 且零副作用；`reversed` 重入幂等 |
| AC-27 | 预留反向核销 | 发运时 `fulfilled` 的预留，冲销后 `status='open'`、`qty_fulfilled=0`，投影重建 |
| AC-28 | 冲销后终态 | `reversed` 禁止再签收 / 再发运 / 取消（`LOCKED` + `UNDELETABLE`），行状态同步 `reversed` |

**验收状态（2026-11-05）**：AC-01~AC-18 已验证通过（AC-13 由 `test_doc_flow_stage3_reversal.py` 覆盖；AC-14 由 `test_doc_flow_reconcile.py` 新增库存事务互检例覆盖；AC-15 由阶段 2 端到端链路例覆盖；AC-16~AC-18 由 `test_demand_trace_graph.py` 12 例覆盖）；AC-19~AC-23 已验证通过（`test_shipment_return_doc_flow.py` 8 例）；AC-24~AC-28 已验证通过（`test_shipment_reverse.py` 5 例）。

---

## 9. 风险与决策点

| # | 风险 / 决策 | 处置建议 |
|---|---|---|
| D1 | 规则声明方式：app.yaml vs 迁移 upsert | P0 用迁移 upsert；后续补声明式清单 |
| D2 | `post` 与 `derive` 事务边界 | 若 posting 自带事务，则先 Σ 预检，derive 失败抛错；对账兜底孤儿事务 |
| D3 | 事务类是否建边 | 建（attach），用于冲销与追溯；不建则无法回答"这笔事务来自哪条发运行" |
| D4 | `demand_trace_links` 与边表的关系 | **不做派生视图替换**：计划层（peg / plan_version / 有效期 / 非单据节点）与执行层语义不可映射；阶段 4 改为「只读统一追溯面 + 写边界 + 跨层对账」 |
| D5 | 历史数据回填范围 | 只回填数量可确定的记录；不可确定的留空并在报告中列示 |
| D6 | 已发运取消 / 冲销 | P0 禁止取消；P0.5 走方案 A（退货交货入库）；**阶段 5.1 已实施数据错误冲销**（`reversed` 终态，全量回滚），两条路径不得混用 |
| D6.1 | 序列号 / HU / 预留是否随冲销回滚 | **全量回滚**：前两者复用 `reverse_serial_event` / `reverse_document`，预留新增 `unfulfill_by_demand`；不留「不回滚」已知边界 |
| D7 | 统一追溯视图定义的生效方式 | `schema_generator` 仅 `CREATE VIEW IF NOT EXISTS`，定义变更由迁移 `DROP VIEW` + `CREATE VIEW` 负责；YAML 仍是元数据真源 |
| D8 | 退货执行单据形态：复用 `shipment`（A）vs 独立退货收货单（B） | 采用 A：与 SAP Returns Delivery / Oracle RMA 一致，且与仓库红字收货「复用单据 + 类别」模式一致；B 仅在需要 ARM 式检验/维修分支时作为上层子流程引入 |
| R1 | `inventory_transaction` 无 `quantity` 字段 | attach 模式不受影响；未来 create 模式需 `target_data` 显式写 `qty` |
| R2 | 三套并存（trace + allocation + edge） | 不合并存储；阶段 4 以统一读面 + 跨层对账防止口径漂移 |
| R3 | 调拨双记账 | 阶段 2 已确认 `transfer_shipment.post` 委托 `transfer_order_service` 记账，仅一次；边由后者写 |
| R4 | 性能 | 边表按 7 元组唯一索引；追溯查询走 `v_doc_flow_consumed_qty`，不逐行实时重算 |
| R5 | 统一追溯面依赖两基表同库 | 视图只能 UNION 同库表；缺任一表迁移 `[SKIP]`，不做空表 stub，不跨库 `ATTACH` |
| R6 | 视图无 `org_id` | 边与线索均不带 org 维度；不挂 `dimension_bindings`（避免静默过滤/空集），需要组织范围时由消费方 join 源单 |
| R7 | 视图为虚拟表，深度遍历成本 | 仅做索引可覆盖的逐跳查询；深链用递归 CTE 并限制深度/节点数；不在视图内做聚合重算 |
| R8 | `shipment` 存量类型可能无 `document_category` | 缺失按 `sales` 解释，不回填业务配置；退货类型须由业务建档后才能发运 |
| R9 | `RETURN_IN` 移动类型缺失导致过账失败 | 迁移幂等 seed；类型缺失时过账明确失败并回滚，不静默降级为正向 |
| R10 | 调拨发运已发运行无冲销入口（P1） | 现状是正向未接（`TransferShipmentService.post()` 无过账/边），不是冲销缺口；正向补齐后复用 `reverse_by_source`，不伪造红字调拨单 |
| R11 | `reversed` 为终态、冲销不可逆 | 误冲销只能人工新建正向交货修复；审计保留红字边 + `REVERSAL` 事务 + `reversal_reason`，不提供二次撤销 |

---

## 10. 代码锚点（评审用）

| 主题 | 位置 |
|---|---|
| 规则存储 | `meta/core/doc_flow_rule_store.py` |
| 边表 DDL | `meta/core/doc_flow_schema.py` |
| 单行派生 | `meta/core/doc_flow_derive_engine.py` |
| 批量派生 | `meta/core/doc_flow_batch_engine.py` |
| 冲销 | `meta/core/doc_flow_reversal.py` |
| 对账 | `meta/core/doc_flow_reconcile.py`、`meta/tools/doc_flow_reconcile.py` |
| 启动期准备 | `meta/core/app_registry.py` `_prepare_doc_flow` |
| 声明解析 | `meta/core/app_loader.py` `DocFlowRuleDecl` |
| 当前唯一业务读边 | `meta/services/sales_order_guard_service.py` |
| 交货发运服务 | `meta/services/shipment_service.py`（`ship_confirm` / `_post_issue_inventory` / `_write_issue_edges`） |
| 交货单模型 | `meta/schemas/shipment.yaml`（`order_id` / `document_type_id`）、`shipment_line.yaml`（`schedule_id`） |
| 单据类别 | `meta/schemas/type_definition.yaml`（`document_category`）、`meta/migrations/v201__inventory_foundation.py`（移动类型字典） |
| 退货阶段 5 | `meta/migrations/v222__doc_flow_return_shipment_rule.py`、`meta/tests/test_shipment_return_doc_flow.py`、`meta/services/shipment_service.py`（退货分支） |
| 冲销阶段 5.1 | `meta/services/shipment_service.py`（`reverse` / `_reverse_inventory` / `_reverse_serial_tracking` / `_reverse_hus` / `_unfulfill_reservations` / `_rollback_schedule_delivery`）、`meta/services/inventory_reservation_service.py`（`unfulfill_by_demand`）、`meta/migrations/v223__shipment_reverse.py`、`meta/tests/test_shipment_reverse.py` |
| 收货过账 | `meta/services/receipt_service.py` `_post_receipt_inventory` |
| 库存过账 | `meta/services/inventory_posting_service.py` `post` |
| 请购转 PO | `meta/services/requisition_po_conversion.py` |
| 分配转调拨 | `meta/services/transfer_order_from_allocation.py` |
| 调拨过账 | `meta/services/transfer_shipment_service.py`、`transfer_order_service.py` |
| BO Action 注册 | `meta/services/bo_action_registrations.py` |
| 既有设计口径 | `meta/schemas/requisition.yaml:16` |
| 统一追溯视图（阶段 4 新增） | `meta/schemas/demand_trace_graph.yaml` |
| 统一追溯视图迁移 | `meta/migrations/v219__demand_trace_graph_view.py` |
| 追溯遍历服务 | `meta/services/trace_graph_service.py` |
| 跨层对账规则 | `meta/core/doc_flow_reconcile.py` `_trace_edge_findings` |
| 阶段 4 测试 | `meta/tests/test_demand_trace_graph.py` |
| VIEW 建表机制 | `meta/core/schema_generator.py` `_generate_create_view`（仅 `IF NOT EXISTS`） |
| 只读视图护栏 | `meta/services/manage_service.py` `_reject_if_readonly_view` |
| VIEW 元模型先例 | `meta/core/doc_flow_schema.py` `_build_consumed_view_meta`、`meta/schemas/party_internal.yaml` |
