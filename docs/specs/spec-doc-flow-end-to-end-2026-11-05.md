# 规格：端到端转单统一接入 DOC_FLOW（Copy Control）

- 文档版本：v0.1
- 日期：2026-11-05
- 状态：**阶段 0/1/2/3/4 已实施**，AC-01~AC-18 已验证通过（2026-11-05）
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

### 2.2 非目标

- 不新建 BOM/项目 BOM/Order BOM；
- 不把审批、预留创建、核销、状态推进接入 DOC_FLOW（不产生下游单据）；
- 不用 DOC_FLOW 替代 `InventoryPostingService`（禁止直插库存事务）；
- 不改成本口径，不实现 `v_project_cost`（P2-3 后置）；
- 不实现服务确认/开票对象本身，只预留规则位。
- 不删除、不改写 `demand_trace_links` 的计划语义，也不把它替换为边表（计划节点与钉住口径无法由边表表达）。
- 不把统一追溯视图做成可写入口（写仍走各自权威服务）。

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

P0/P1 新增检查项：`inventory_transactions.source_doc_type IN ('shipment','receipt','transfer_shipment')` 无对应边 → `ORPHAN_TXN`；边指向不存在事务 → `DANGLING_EDGE`。

---

## 4. 接入分类矩阵

| 类别 | 链路 | 判定 | 派生模式 |
|---|---|---|---|
| A. 单据→单据 | 请购→采购订单 | 必须接 | create / attach |
| A | 采购订单→收货单 | 必须接 | attach |
| A | 销售订单→交货单 | 必须接 | attach |
| A | 需求分配→调拨单 | 必须接 | attach |
| A | 退货/冲销（反向单据） | 必须接 | reversal |
| A | 服务确认→开票（未来） | 必须接 | create |
| B. 单据→库存事务 | 收货→入库事务 | 应当接 | attach |
| B | 交货→出库事务 | 应当接（P0） | attach |
| B | 调拨发运→事务 | 应当接 | attach |
| C. 纯状态/派生 | 审批、预留创建/核销、履约状态回写、`v_project_cost` | 不必接 | — |

---

## 5. 逐链路设计

### 5.1 交货确认 → 出库事务（P0，最高优先）

**触发点**：`ShipmentService.ship_confirm()`（[L157-224](file:///d:/filework/excel-to-diagram/meta/services/shipment_service.py#L157-L224)）

**顺序**（外层事务）：

```
① 校验 staged / 序列号 / HU
② InventoryPostingService.post(entries, source)      # 唯一写库存
③ doc_flow derive(attach)                            # 只写边
④ 回写 schedule delivered_qty / 行/头状态
⑤ 核销预留 + demand_trace
```

**过账参数**：

- `source = {source_doc_type:'shipment', source_doc_id:delivery_id, source_event_key:'shipment:{id}:ship', transaction_date, created_by}`
- 每交货行 entry：`direction='out'`、`transaction_type_id=ISSUE_TO_SHIP`、`qty`、`item_id/location_id/batch_id/serial_no/hu_id`、`project_id`（抬头）、`project_task_id`（行）、`source_line_id`

**规则**：

| 字段 | 值 |
|---|---|
| `rule_id` | `shipment_line_to_issue_txn` |
| `source_bo` → `target_bo` | `shipment_line` → `inventory_transaction` |
| `source_qty_field` | `qty` |
| `pool` | `inventory_issue` |
| `status` | `active` |

attach 模式：`target_data={'id': txn_id, 'item': line_id, 'amount': 0, 'unit': uom_id}`。

**幂等**：`source_event_key` 去重 + 边 7 元组幂等；状态机保证 `staged→shipped` 单次。

**过账开关**：`inventory_posting_enabled=0`（迁移默认值）时**跳过过账与转单边，不阻断发运**——与收货同口径的过渡期行为；开关开启后才校验负库存/批次/段，失败即拒绝并整体回滚。

**冲销**：P0 禁止已 `shipped` 取消；P0.5 走退货单/红字。

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
| 发运 → 出库事务 | 无：`ShipmentService.cancel()` 仅 draft/released；`shipped` 之后按 R-DN-2 禁止取消，且无 reverse 方法 | 无可冲销对象；P0.5 退货单落地后才接入 |
| 调拨发运 → 事务 | 无：`TransferOrderService.cancel()` 要求总发货量 = 0；`create_reversal()` 只建反向**草稿**，其发运走正常正向规则 | 反向调拨单发运已由阶段 2 正向规则产生正常边；已发运行无冲销入口 |

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

**执行结果（2026-11-05）**：新增 3 例通过；收货红冲、收货服务、DOC_FLOW 冲销引擎、阶段 2 补边套件回归全绿。无新迁移（边表列已由 v214/v215 提供）。发运 / 调拨发运已发运行的冲销入口仍按 D6 留给 P0.5（退货单 / 红字单），届时复用 `reverse_edges_by_source` 接线。

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

**验收状态（2026-11-05）**：AC-01~AC-18 已验证通过（AC-13 由 `test_doc_flow_stage3_reversal.py` 覆盖；AC-14 由 `test_doc_flow_reconcile.py` 新增库存事务互检例覆盖；AC-15 由阶段 2 端到端链路例覆盖；AC-16~AC-18 由 `test_demand_trace_graph.py` 12 例覆盖）。

---

## 9. 风险与决策点

| # | 风险 / 决策 | 处置建议 |
|---|---|---|
| D1 | 规则声明方式：app.yaml vs 迁移 upsert | P0 用迁移 upsert；后续补声明式清单 |
| D2 | `post` 与 `derive` 事务边界 | 若 posting 自带事务，则先 Σ 预检，derive 失败抛错；对账兜底孤儿事务 |
| D3 | 事务类是否建边 | 建（attach），用于冲销与追溯；不建则无法回答"这笔事务来自哪条发运行" |
| D4 | `demand_trace_links` 与边表的关系 | **不做派生视图替换**：计划层（peg / plan_version / 有效期 / 非单据节点）与执行层语义不可映射；阶段 4 改为「只读统一追溯面 + 写边界 + 跨层对账」 |
| D5 | 历史数据回填范围 | 只回填数量可确定的记录；不可确定的留空并在报告中列示 |
| D6 | 已发运取消 | P0 禁止；P0.5 做红字冲销 |
| D7 | 统一追溯视图定义的生效方式 | `schema_generator` 仅 `CREATE VIEW IF NOT EXISTS`，定义变更由迁移 `DROP VIEW` + `CREATE VIEW` 负责；YAML 仍是元数据真源 |
| R1 | `inventory_transaction` 无 `quantity` 字段 | attach 模式不受影响；未来 create 模式需 `target_data` 显式写 `qty` |
| R2 | 三套并存（trace + allocation + edge） | 不合并存储；阶段 4 以统一读面 + 跨层对账防止口径漂移 |
| R3 | 调拨双记账 | 阶段 2 已确认 `transfer_shipment.post` 委托 `transfer_order_service` 记账，仅一次；边由后者写 |
| R4 | 性能 | 边表按 7 元组唯一索引；追溯查询走 `v_doc_flow_consumed_qty`，不逐行实时重算 |
| R5 | 统一追溯面依赖两基表同库 | 视图只能 UNION 同库表；缺任一表迁移 `[SKIP]`，不做空表 stub，不跨库 `ATTACH` |
| R6 | 视图无 `org_id` | 边与线索均不带 org 维度；不挂 `dimension_bindings`（避免静默过滤/空集），需要组织范围时由消费方 join 源单 |
| R7 | 视图为虚拟表，深度遍历成本 | 仅做索引可覆盖的逐跳查询；深链用递归 CTE 并限制深度/节点数；不在视图内做聚合重算 |

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
| 发运确认 | `meta/services/shipment_service.py` `ship_confirm` |
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
