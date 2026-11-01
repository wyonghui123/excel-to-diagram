# 收货对象模型细化（独立 spec）

> 依据：`spec-purchase-order-object-model-2026-11-01.md` §10 / §11（到货计划行与收货契约）、`spec-procurement-task-object-model-2026-10-31.md`（T-D12 / T-D19 / 证据表 `RCV_*`）、`meta/schemas/shipment.yaml` / `shipment_line.yaml`（销售侧镜像）、`meta/schemas/purchase_order_schedule.yaml`、`meta/services/shipment_service.py`
> 状态：草案 v1，待评审；**评审通过前不实施、不提交**
> 范围：M3 第二阶段 —— `receipt` 头 / 行（收货单 / 收货行）+ 与 PO 计划行、需求分配、库存 / 质检 / 财务的关系；**发票只留接口契约，字段细化后置**
> 日期：2026-11-01

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 收货单是否独立对象 | **是**，且全系统只建一个 `receipt`，按 `source_doc_type` 区分来源（T-D12）；不为 PO / 调拨 / 工单 / 退货分别建表 |
| 收货行挂在哪 | **挂到货计划行**（`purchase_order_schedules.id`），不直接挂 PO 行；同一计划行可分多次收货（与销售侧 `shipment_line.schedule_id` 完全镜像） |
| 收货的核心事件是什么 | **过账（posted）**。草稿可改；过账即成事实，不得改数量，只能开红字单冲销 |
| 过账改什么 | ① 回写计划行 `received_qty` / `rejected_qty` 与状态 `completed`（带来源标记）；② **调用** `PurchaseOrderFulfillmentService.recompute_order` 派生 PO 行 / 头 `fulfillment_status`（禁止直写）；③ 写 `demand_allocation`（`target_bo='receipt'`）实现需求级追溯；④ **不动 PO 金额 / 单价 / 税率** |
| 部分收货如何追溯 | 收货行净收量按「PO 分配的剩余量」比例拆到 `demand_allocation`；同一需求行的「PO 分配」与「收货分配」**分段计数、不相加**（修正 PO spec R-PO-9 的口径） |
| 超收怎么办 | 默认拒绝（`receipt_over_tolerance_percent` 默认 0）；容差只由控制参数放开，不硬编码 |
| 短收怎么办 | 允许；计划行不会自动完成，需要显式 `close_po_schedule`（短收结案）——本 spec 对 PO spec 的一处**增量修订** |
| 退货 / 冲销怎么做 | 本波只做**整单红冲**（红字收货单，`document_category='return'`）；供应商退货出库（RTV）、部分红冲列为后续 |
| 库存怎么落 | **本波不建库存台账**。收货 `posted` 只表达业务事实与过账契约；`stock_transaction` 另立 spec（M4），UI 文案统一用「已过账」而非「已入库」 |
| 质检怎么做 | 不建质检对象；行上 `qty_rejected` + `rejection_reason_code` + `rejection_disposition` 三件套表达判定与处置 |
| 服务采购怎么收 | 复用同一对象，`schedule_kind='service'` 的计划行收货即「验收确认」，数量仍走 `qty_received` |
| 发票 | **本 spec 只锁契约**：`vendor_invoice` 头 / 行的匹配键、`source_doc_type` 值域与「按计划行 + 行匹配」口径；字段与流程后置 |
| 本 spec 明确不做的 | 库存台账、质检对象、ASN、供应商退货出库、部分红冲、序列号明细子表、发票实现 |

---

## 1. 定位与边界

### 1.1 在链条中的位置

```
purchase_order
    └── purchase_order_line
          └── purchase_order_schedule（到货计划行，承诺）
                └── receipt_line（收货行，实际事件，本 spec）   ← 唯一挂载点
                      └── vendor_invoice_line（发票行，后置 spec，只留契约）
```

### 1.2 边界

| 属于收货 | 不属于收货 |
|---|---|
| 实际到货事实（时间、地点、数量、批次 / 序列、拒收） | 采购承诺（`purchase_order_schedule`） |
| 过账副作用（计划行已收量、PO 履约状态、需求分配） | PO 金额 / 单价 / 税率（PO 快照，收货不改） |
| 收货差异的判定与处置（拒收 / 让步接收 / 退回供应商） | 质检方案、检验项、抽样规则（后置） |
| 库存 / 资产 / 费用的**过账契约** | 库存台账、资产卡片、GL 凭证（M4 / 财务波次） |
| 冲销（红字单）事实与追溯 | 供应商退货出库（RTV，需库存，后置） |
| 三单匹配的**锚点**（计划行 + 行） | 发票校验、容差、付款（后置 spec） |

### 1.3 为什么收货可以先于库存台账落地

| 前置 | 状态 | 影响 |
|---|---|---|
| PO + 到货计划行 | 已落（v177 / v181） | `receipt_line.schedule_id` 有真外键 |
| `demand_allocation` | 已落（v177） | 收货分配复用同一张表，`target_bo='receipt'` |
| `type_definitions` 平台 | 已落（v170 / v171） | 收货单据类型 + 编号序列直接挂载 |
| 库存台账 | **全缺** | `posted` 不写库存；只留 `inventory_transaction` 契约（D-RC-8） |
| 质检对象 | **全缺** | 用行级拒收三件套替代（D-RC-7） |
| 发票 | **全缺** | 只留匹配键契约（§10） |

结论：收货的**事实层**（数量、计划行闭合、需求追溯、履约回写）不依赖库存台账；库存与财务是**下游过账**，可以后续补。

---

## 2. 与销售侧 `shipment` 的统一骨架

收货单与交货单是同一副骨架的两个方向，实施时逐条对照。

| # | 维度 | 销售侧 `shipment` | 采购侧 `receipt` | 统一口径 |
|---|---|---|---|---|
| M1 | 表命名 | `shipments` / `shipment_lines` | `receipts` / `receipt_lines` | 头 + 行两表，行不单独成菜单 |
| M2 | 父字段 | `delivery_id` | `receipt_id` | 行用 `{父对象}_id` |
| M3 | 业务键 | `delivery_no` | `receipt_no` | 头业务键 + 唯一索引；生成后不可改 |
| M4 | 单据类型 | `type_definitions(scope_bo='shipment')` | `type_definitions(scope_bo='receipt')` | 切面 `document_type_aspect`；方向由 `document_category` |
| M5 | 行唯一挂载点 | `schedule_id → sales_order_schedules` | `schedule_id → purchase_order_schedules` | **都只挂计划行**，不挂订单行 |
| M6 | 冗余列 | `order_line_id / item_id / uom_id` | `order_id / order_line_id / item_id / uom_id` | 由计划行反查；不一致拒绝 |
| M7 | 批次 / 序列 | `lot_no` / `serial_no` 单字段 | 同左 | 本波与销售侧同构；序列明细后置（Q5） |
| M8 | 实际时间 | `actual_ship_date` / `actual_arrival_date` | `actual_arrival_date` | 采购侧只有到达，没有发运 |
| M9 | 状态机 | `draft → released → staged → shipped → delivered → closed / cancelled` | `draft → posted → reversed / cancelled` | 采购以「过账」为核心事件，不需要拣货段 |
| M10 | 回写 | `delivered_qty`（计划行）+ 订单履约状态（服务派生） | `received_qty` / `rejected_qty`（计划行）+ PO 履约状态（服务派生） | 唯一写入口在服务层，禁止散写 |
| M11 | 分配追溯 | 无（销售不写 `demand_allocation`） | `target_bo='receipt'` | 采购独有（需求侧追溯） |

> 与销售侧的唯一结构性差异是 M11：采购收货要回到需求行（合并采购后一张单服务多个需求），销售不需要。

---

## 3. `receipt` 头字段表

表：`receipts`；`display_name_field: receipt_no`；`aspects: [audit_aspect, document_type_aspect]`；`semantics.category: business_document`；`business_key: [receipt_no]`。

| # | 字段 id | 中文 | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | 自增主键 |
| 2 | `receipt_no` | 收货单号 | string(30) | 是 | 唯一、不可改；由 `type_definitions.number_sequence_id` 取号 |
| 3 | `document_type_id` | 单据类型 | integer | 是 | `scope_bo='receipt'` + `level='header'`；`document_category` ∈ `standard / return` |
| 4 | `receipt_date` | 收货日期 | date | 是 | 业务日期；取号日期段基准 |
| 5 | `actual_arrival_date` | 实际到达时间 | datetime | 否 | 过账时可补；与 `receipt_date` 不同口径 |
| 6 | `source_doc_type` | 来源单据类型 | string(30) | 是 | `purchase_order / transfer_order / work_order / sales_return / intercompany` |
| 7 | `source_doc_id` | 来源单据 | integer | 是 | 多态头 id，按 `source_doc_type` 解释 |
| 8 | `source_doc_no` | 来源单号快照 | string(40) | 否 | 展示 / 打印用；不参与校验 |
| 9 | `supplier_party_id` | 供应商 | integer | 否 | PO 来源创建时必填，过账时校验 vendor 关系（同 R-PO-8）；非 PO 来源可空 |
| 10 | `supplier_delivery_no` | 供应商送货单号 | string(40) | 否 | 对账 / 三单匹配辅助键 |
| 11 | `org_id` | 收货方法人 | integer | 是 | 取 PO 头 `org_id`；非 PO 来源按来源推导 |
| 12 | `purchase_org_id` | 采购组织快照 | integer | 否 | 取 PO 头；报表维度（**契约扩展字段**，PO spec §11 最小集未列） |
| 13 | `deliver_to_location_id` | 收货地点 | integer | 否 | 默认计划行 → 行 → 头；过账时行级可覆盖 |
| 14 | `project_id` | 项目 | integer | 否 | 取 PO 头；整单归集用 |
| 15 | `received_by` | 收货人 | string(80) | 否 | 姓名文本快照；PII，审计排除 |
| 16 | `status` | 状态 | string(20) | 是 | `draft / posted / reversed / cancelled`，默认 `draft` |
| 17 | `reversal_of_receipt_id` | 冲销原单 | integer | 否 | 红字单必填；`document_category='return'` 时必填 |
| 18 | `reversed_at` | 被冲销时间 | datetime | 否 | 原单全部冲销后回写 |
| 19 | `remark` | 备注 | string(500) | 否 | — |
| 20 | `created_at` | 创建时间 | datetime | 否 | — |
| 21 | `updated_at` | 更新时间 | datetime | 否 | — |

### 3.1 索引

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uq_receipt_no` | `receipt_no` | 是 |
| `idx_receipt_source` | `source_doc_type, source_doc_id` | 否 |
| `idx_receipt_status_date` | `status, receipt_date` | 否 |
| `idx_receipt_supplier` | `supplier_party_id` | 否 |
| `idx_receipt_reversal` | `reversal_of_receipt_id` | 否 |
| `idx_receipt_project` | `project_id` | 否 |

### 3.2 关系

| 关系 id | 目标 | 字段 | 基数 | 说明 |
|---|---|---|---|---|
| `receipt_to_document_type` | `type_definition` | `document_type_id` | N:1 | 真外键 |
| `receipt_to_supplier` | `party` | `supplier_party_id` | N:1 | 可空 |
| `receipt_to_org` | `org` | `org_id` | N:1 | 真外键 |
| `receipt_to_location` | `location` | `deliver_to_location_id` | N:1 | 可空 |
| `receipt_to_project` | `project` | `project_id` | N:1 | 可空 |
| `receipt_to_reversal` | `receipt` | `reversal_of_receipt_id` | N:1 | 自引用；红字单 → 原单 |

---

## 4. `receipt_line` 字段表

表：`receipt_lines`；`parent_object: receipt`；`hierarchy: {parent_field: receipt_id}`；`display_name_field: line_no`；`deletion_policy.mode: cascade`。

| # | 字段 id | 中文 | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | 主键 |
| 2 | `receipt_id` | 收货单 | integer | 是 | 父字段 |
| 3 | `line_no` | 行号 | string(6) | 是 | `^[0-9]{1,6}$`，单内唯一 |
| 4 | `schedule_id` | 计划行 | integer | 条件必填 | PO 来源**必填**；指向 `purchase_order_schedules.id` |
| 5 | `source_line_id` | 来源行 | integer | 条件必填 | 非 PO 来源的多态行锚点（本波只留字段与守卫分支，不实现来源） |
| 6 | `order_id` | 采购订单 | integer | 条件必填 | 冗余：由 `schedule_id` 反查；PO 来源必填 |
| 7 | `order_line_id` | 订单行 | integer | 条件必填 | 冗余：由 `schedule_id` 反查 |
| 8 | `item_id` | 物料 | integer | 是 | 冗余：由计划行 → 订单行带出；不一致拒绝 |
| 9 | `uom_id` | 计量单位 | integer | 是 | 冗余：同上；本波不允许收货换算（Q6） |
| 10 | `qty_received` | 收货数量 | number(6) | 是 | `> 0`；单位 = 计划行 `uom_id` |
| 11 | `qty_rejected` | 拒收数量 | number(6) | 否 | 默认 0；`>= 0` 且 `<= qty_received` |
| 12 | `rejection_reason_code` | 拒收原因 | string(30) | 否 | `qty_rejected > 0` 时必填 |
| 13 | `rejection_disposition` | 拒收处置 | string(20) | 否 | `return_to_supplier / concession / scrap / rework`；`qty_rejected > 0` 时必填 |
| 14 | `lot_no` | 批次号 | string(64) | 否 | 文本；物料主数据当前未声明批次管理（Q5） |
| 15 | `serial_no` | 序列号 | string(64) | 否 | 文本；本波每行一个序列号 |
| 16 | `putaway_location_id` | 入库库位 | integer | 否 | 空 = 头 `deliver_to_location_id`；只作过账契约锚点 |
| 17 | `status` | 行状态 | string(20) | 是 | `draft / posted / reversed / cancelled`，随头联动 |
| 18 | `reversal_of_line_id` | 被冲销行 | integer | 否 | 红字行必填；指向原单行 |
| 19 | `created_at` | 创建时间 | datetime | 否 | — |
| 20 | `updated_at` | 更新时间 | datetime | 否 | — |

### 4.1 索引

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uq_receipt_line_no` | `receipt_id, line_no` | 是 |
| `idx_receipt_line_schedule` | `schedule_id` | 否 |
| `idx_receipt_line_order_line` | `order_line_id` | 否 |
| `idx_receipt_line_item` | `item_id` | 否 |
| `idx_receipt_line_lot` | `lot_no` | 否 |

> `schedule_id` **不唯一**：同一计划行可分多次收货（与 `shipment_line` 的 R-DN-5 同口径）。

### 4.2 关系

| 关系 id | 目标 | 字段 | 基数 | 说明 |
|---|---|---|---|---|
| `receipt_line_to_receipt` | `receipt` | `receipt_id` | N:1 | 真外键 |
| `receipt_line_to_schedule` | `purchase_order_schedule` | `schedule_id` | N:1 | 唯一挂载点（PO 来源） |
| `receipt_line_to_order` | `purchase_order` | `order_id` | N:1 | 冗余，查询用 |
| `receipt_line_to_order_line` | `purchase_order_line` | `order_line_id` | N:1 | 冗余 |
| `receipt_line_to_item` | `item` | `item_id` | N:1 | 冗余 |
| `receipt_line_to_uom` | `uom` | `uom_id` | N:1 | 冗余 |
| `receipt_line_to_putaway` | `location` | `putaway_location_id` | N:1 | 可空 |
| `receipt_line_to_reversal` | `receipt_line` | `reversal_of_line_id` | N:1 | 自引用（红字） |

---

## 5. 状态机与不变量

### 5.1 头状态机

| 规则 id | 名称 | from | to | 说明 |
|---|---|---|---|---|
| `post_receipt` | 过账 | `draft` | `posted` | 校验行、计划行、超收、拒收三件套；触发全部回写（§6） |
| `cancel_receipt` | 取消 | `draft` | `cancelled` | 仅草稿可取消；行一并置 `cancelled` |
| `reverse_receipt` | 冲销 | `posted` | `reversed` | 仅红字单过账后由原单被冲销时置位（§7） |

### 5.2 行状态机

| 规则 | from | to | 说明 |
|---|---|---|---|
| 随头过账 | `draft` | `posted` | 头 `post_receipt` 时批量置位 |
| 随头取消 | `draft` | `cancelled` | 头 `cancel_receipt` 时批量置位 |
| 随头被冲销 | `posted` | `reversed` | 原单被红字单全额冲销时批量置位 |

### 5.3 不变量（R-RC-0 ~ R-RC-15）

| 编号 | 规则 |
|---|---|
| R-RC-0 | 头 `document_type_id` 必须 `scope_bo='receipt'` + `level='header'`；`document_category ∈ {standard, return}`；`return` 必须带 `reversal_of_receipt_id` |
| R-RC-1 | `source_doc_type='purchase_order'` 时，行 `schedule_id` 必填，且计划行 `schedule_kind ∈ {delivery, service}`、状态 ∈ `{planned, confirmed}`；否则 `RC_SCHEDULE_INVALID` |
| R-RC-2 | 行 `order_id / order_line_id / item_id / uom_id` 必须与 `schedule_id` 反查结果一致；不一致 `RC_LINE_MISMATCH` |
| R-RC-3 | `qty_received > 0`；`qty_rejected >= 0` 且 `<= qty_received`；否则 `RC_QTY_INVALID` |
| R-RC-4 | `qty_rejected > 0` 时 `rejection_reason_code` 与 `rejection_disposition` 必填；否则 `RC_REJECTION_INCOMPLETE` |
| R-RC-5 | 计划行净收累计（标准单净量 − 红字单净量）> `promised_qty × (1 + receipt_over_tolerance_percent)` 时拒绝，报 `RC_OVER_RECEIPT` |
| R-RC-6 | 头 `posted` 后行数量 / 计划行 / 行号 / 批次序列禁止修改；仅红字单可产生反向事实；否则 `RC_POSTED_IMMUTABLE` |
| R-RC-7 | 红字单必须引用原单全部有效行，数量取原单每行净量，不得超过；否则 `RC_REVERSAL_INVALID` |
| R-RC-8 | 取号必须在开事务之前（序列引擎要求独立事务）；取号失败不回退 |
| R-RC-9 | 收货分配（`target_bo='receipt'`）：单条 ≤ 对应 PO 分配的剩余量；同一需求行在本计划行上的收货分配累计 ≤ 对应 PO 分配 `qty × (1 + receipt_over_tolerance_percent)`（**分段上限**，不与 PO 分配相加，与 R-RC-5 共用同一容差）；否则 `RC_ALLOC_OVER` |
| R-RC-10 | 计划行净收累计 ≥ `promised_qty` 时自动置 `completed`，同时写 `completion_source='receipt'` 与 `completion_prev_status`（原 `planned / confirmed`）；仅 `planned / confirmed` 可被自动完成。红冲只回退 `completion_source='receipt'` 的计划行到 `completion_prev_status`；`manual` 与 `short_close` 不回退 |
| R-RC-11 | 收货不修改 PO 头 / 行的金额、单价、税率、汇率；收货服务禁止写这些字段 |
| R-RC-12 | `posted` 不可改 `actual_arrival_date` 之外的业务字段；时间类字段允许补齐 |
| R-RC-13 | 草稿删除级联行；`posted / reversed` 禁止删除 |
| R-RC-14 | 服务计划行（`schedule_kind='service'`）按 `qty_received` 视为验收量；不额外建验收单 |
| R-RC-15 | `putaway_location_id` 有值时必须 `location.status='active'`；空时过账取头 `deliver_to_location_id` |
| R-RC-16 | 计划行 `received_qty` 缓存必须等于 `SUM(posted 标准单净量) − SUM(posted 红字单净量)`；不一致以流水为准并修复缓存（对账脚本 / 巡检入口） |
| R-RC-17 | `completion_source='short_close'` 的计划行（已结案）禁止再收货；新收货行引用即 `RC_SCHEDULE_CLOSED` |
| R-RC-18 | `received_qty` 语义 = **净收**（≈ Oracle `QUANTITY_ACCEPTED`）；`rejected_qty` 为独立缓存（`SUM(posted qty_rejected)`），两者不得混算 |

---

## 6. 过账副作用（唯一写入口：`receipt_service.post`）

一次过账在**单事务**内完成下列 6 步；任一步失败整单回滚（含取号已消耗——跳号允许）。

| 步 | 动作 | 细节 |
|---|---|---|
| 1 | 校验 | §5.3 全部不变量 + 空单据禁止过账（`RC_EMPTY`） |
| 2 | 写需求分配 | 按 §6.1 算法拆 `demand_allocation`（`target_bo='receipt'`，`target_id=receipt_id`，`target_line_id=receipt_line_id`，`target_schedule_id=schedule_id`，`demand_*` 与成本字段**整行复制** PO 分配，不改写） |
| 3 | 回写计划行 | **条件 UPDATE 原子累加**：`received_qty = received_qty + 净量`、`rejected_qty = rejected_qty + 拒收量`；`WHERE` 带「未结案 + 累加后 ≤ `promised_qty × (1 + 容差)`」，`rowcount=0` 即拒绝 `RC_OVER_RECEIPT`（禁止先查后写）。净量 ≥ `promised_qty` 且原状态 ∈ `{planned, confirmed}` 时置 `completed`，写 `completion_source='receipt'` + `completion_prev_status` |
| 4 | 回写 PO 履约 | **调用** `PurchaseOrderFulfillmentService.recompute_order(order_id)`（内部行先、抬头后）；`receipt_service` 禁止直写 `fulfillment_status` / `fulfillment_derived_at` |
| 5 | 状态置位 | 头 → `posted`，行 → `posted` |
| 6 | 审计 | 过账动作写 `audit_aspect`；不写 `doc_flow`（M6 统一启用） |

### 6.1 收货分配拆分算法（可测试口径）

1. 取该计划行的 PO 分配：`target_bo='purchase_order' AND target_schedule_id=schedule_id AND status='active'`，合计 `planned_i`。
2. 取该计划行已收货分配净量：`target_bo='receipt' AND target_schedule_id=schedule_id`，按 `demand_line_id` 汇总（标准单为正、红字单为负）。
3. `remaining_i = planned_i - received_net_i`。
4. 本次净量 `qty = qty_received - qty_rejected`，按 `remaining_i` 占比拆分；单一分配全归；舍入余数归**最后一条**。
5. 若 `qty > Σ remaining_i + 容差`（容差 = 计划行 `promised_qty × receipt_over_tolerance_percent`，与 R-RC-5 / R-RC-9 同一参数）：拒绝 `RC_ALLOC_OVER`；若 `Σ remaining_i = 0`：拒绝 `RC_ALLOC_EXHAUSTED`。

> 例：计划行承诺 10，PO 分配给需求行 A=6、B=4。第一次收 4 → A 2.4 / B 1.6；第二次收 6 → A 3.6 / B 2.4（余数归尾）。A、B 各累计 6 / 4，不再可收。

### 6.2 为什么「PO 分配」与「收货分配」不相加

`demand_allocation` 是阶段性事实，不是同一阶段的两种记录：

- PO 分配回答「这 10 件计划给谁」；
- 收货分配回答「这 4 件实际到货归谁」。

把两者相加会立刻违反 PO spec 的 R-PO-9（同一需求行 `sum(active.qty) <= 需求行 qty`）——因为同一批货被数了两遍。因此 R-PO-9 的口径需按 `target_bo` 分段：

| 阶段 | 上限 |
|---|---|
| `target_bo='purchase_order'` | ≤ 需求行 `qty`（原 R-PO-9 不变） |
| `target_bo='receipt'` | ≤ 对应 PO 分配 `qty`（新增，本 spec 定义） |

---

## 7. 冲销（本波只做整单红冲）

| 项 | 口径 |
|---|---|
| 触发 | `posted` 单调用 `reverse_receipt`，系统生成一张红字收货单并自动过账 |
| 红字单 | 独立 `receipt`，`document_category='return'`，`reversal_of_receipt_id=原单 id`，行 `reversal_of_line_id=原行 id`，数量 = 原行净量 |
| 副作用 | 计划行 `received_qty` 减回；由过账置位的 `completed` 回退为 `confirmed`（计划行自身的确认事实不因收货 / 冲销而改变）；PO 履约状态重算；收货分配写负向行（`target_bo='receipt'`，`qty` 取负） |
| 原单 | 全部行冲销后置 `reversed` + `reversed_at`；行置 `reversed` |
| 不可做 | 部分行红冲（Q4）、真实退货出库（需库存，Q7） |

> 红字单之所以仍走 `posted`，是为了让「净收量 = 标准单 − 红字单」在同一个事实表里可算，不引入第二套负数量口径。

---

## 8. 与其他对象的关系细化

### 8.1 关系总表

| 关系 | 方向 | 基数 | 实现方式 | 回写 / 约束 |
|---|---|---|---|---|
| receipt → purchase_order | 追溯 | N:1 | `source_doc_type + source_doc_id`（多态引用） | 不写 PO 金额；PO 履约状态由收货派生 |
| receipt_line → purchase_order_schedule | **唯一挂载** | N:1 | `schedule_id` 真外键 | 过账回写 `received_qty` / `rejected_qty` / `completed`（带 `completion_source` + `completion_prev_status`）；R-RC-16 对账 |
| receipt → purchase_order（履约） | 派生 | N:1 | 服务调用，非字段写入 | `PurchaseOrderFulfillmentService.recompute_order` 唯一写 `fulfillment_status` |
| receipt_line → purchase_order_line | 冗余 | N:1 | `order_line_id` | 一致性校验 R-RC-2 |
| receipt_line → purchase_order | 冗余 | N:1 | `order_id` | 一致性校验 |
| receipt → demand_allocation | 分配事实 | 1:N | 多态 `target_bo='receipt'` | 按 §6.1 拆分；不改成本归属 |
| receipt → reversal receipt | 自引用 | 1:N | `reversal_of_receipt_id` | 整单红冲 |
| receipt_line → location | 地点 | N:1 | `deliver_to_location_id` / `putaway_location_id` | 过账取默认；必须 active |
| receipt → party | 供应商 | N:1 | `supplier_party_id` | PO 来源过账校验 vendor 关系（R-RC-0 扩展：同 R-PO-8） |
| receipt → org / project | 组织 / 项目 | N:1 | `org_id` / `project_id` | 取 PO 快照 |
| receipt → inventory_transaction | 过账契约 | 1:N（后置） | **不建表** | 契约见 §9 |
| receipt → vendor_invoice | 匹配锚点 | 1:N（后置） | `receipt_line_id` | 契约见 §10 |
| receipt → doc_flow | 只读消耗账 | — | M6 派生 | 本波不写边（§11） |

### 8.2 非 PO 来源的挂载契约（本波不实现，只定字段）

| `source_doc_type` | 头锚点 | 行锚点 | 本波状态 |
|---|---|---|---|
| `purchase_order` | `source_doc_id=PO id` | `schedule_id` | **实现** |
| `transfer_order` | 转移单头 | `source_line_id`（转移单计划行，后置） | 契约占位 |
| `work_order` | 工单头 | `source_line_id`（工单产出 / 组件行，后置） | 契约占位 |
| `sales_return` | 销售退货单 | `source_line_id`（退货行） | 契约占位 |
| `intercompany` | ISO 头 | `source_line_id`（ISO 行） | 契约占位 |

> 这解释了为什么行上同时保留 `schedule_id` 与 `source_line_id`：前者是 PO 的强类型挂载点（真外键），后者是其他来源的多态占位。二者**至少一个必填**，由 `source_doc_type` 决定哪一个是强约束。PO spec §11「`schedule_id` 必填」按本表修订为「PO 来源必填」。

---

## 9. 库存 / 资产 / 费用：过账契约（不建表）

当前全仓无库存对象。本波收货 `posted` 的语义是**业务事实已确认**，不是库存已增加。

| 行类型（PO `line_type`） | 收货后的下游去向 | 本波实现 | 后续波次 |
|---|---|---|---|
| `PO_GOODS` | 库存事务（入库） | 行上 `putaway_location_id` + `lot_no` / `serial_no` 已备齐 | `inventory_transaction`（M4）：`source='receipt_line'`、`direction='in'`、`qty=净量`、`location=putaway` |
| `PO_ASSET` | 资产卡片 | `asset_category_code` 由分配行快照 | FA 波次以收货行为来源建卡片 |
| `PO_EXPENSE` | 费用 / GL | `expense_account_code` / `cost_center_id` 由分配行快照 | GL 波次 |
| `PO_SUBCONTRACT` | 供应商处组件冲减 | 仅记事实 | 组件发料清单另立 spec |
| `PO_SERVICE` | 验收确认 | `qty_received` 即验收量（R-RC-14） | 发票按验收量开票 |

**措辞纪律**：前端状态标签用「已过账 / 已冲销」，不得写「已入库」；库存页面出现前不得暗示库存已变更。

---

## 10. 发票接口契约（后置 spec，本波只锁键）

| 项 | 契约 |
|---|---|
| 对象 | `vendor_invoice` 头 + `vendor_invoice_line` 行，一个对象按 `source_doc_type` 复用（T-D12） |
| `source_doc_type` 值域 | `purchase_order / receipt / intercompany / service_entry` |
| 匹配键 | 以 `purchase_order_schedule.id` + PO 行 id 为粒度；发票行引用 `receipt_line_id`（可空 = 未收货先开票，需容差策略） |
| 金额口径 | 发票数量 ≤ 净收量 + `invoice_qty_tolerance_percent`；金额比对 PO 单价快照 |
| 容差 | 一律放 `control_parameter_defs`（`invoice_match_tolerance_*`），不硬编码 |
| 本波不做 | 发票对象、校验流程、三单匹配界面、付款 |

> 收货侧只承诺**锚点稳定**：`receipt_line.id` 与 `schedule_id` 一经过账不再变化，发票可安全引用。

---

## 11. doc_flow 边契约（M6 使用，本波不写）

| 边 | `source_bo` | `source_item` | `target_bo` | `target_item` | `rule_id` | `quantity` | `pool` |
|---|---|---|---|---|---|---|---|
| PO → 收货 | `purchase_order` | 计划行号 | `receipt` | 收货行号 | `po_to_receipt` | 净收量 | `procurement` |
| 收货 → 发票 | `receipt` | 收货行号 | `vendor_invoice` | 发票行号 | `receipt_to_invoice` | 开票量 | `billing` |
| 红冲 | 同上 | 同上 | 同上 | 同上 | 同上 | 原量 | 同上，`quantity_sign='red'`、`status='reversed'` |

约束不变：边由派生引擎写；业务对象上不放可写多态外键；缓存列只读（T-D19）。

---

## 12. 页面、菜单、权限

| 项 | 内容 |
|---|---|
| 头列表列 | `receipt_no / receipt_date / source_doc_no / supplier_party_id / org_id / purchase_org_id / deliver_to_location_id / status / actual_arrival_date` |
| 头表单分区 | 基本信息（`receipt_no / document_type_id / receipt_date / status`）；来源（`source_doc_type / source_doc_id / source_doc_no / supplier_party_id / supplier_delivery_no`）；组织与地点（`org_id / purchase_org_id / deliver_to_location_id / project_id`）；其他（`actual_arrival_date / received_by / remark`） |
| 详情子表 | `child_sections`：`receipt_line`。**`demand_allocation` 不放进 `child_sections`**（沿用 D-PO-23：多态表无单一父字段） |
| 行列表列 | `line_no / schedule_id / order_line_id / item_id / qty_received / qty_rejected / uom_id / lot_no / serial_no / putaway_location_id / status` |
| 行表单分区 | 挂载（`schedule_id`，只读 `order_line_id / item_id / uom_id`）；数量（`qty_received / qty_rejected / rejection_reason_code / rejection_disposition`）；批次（`lot_no / serial_no / putaway_location_id`） |
| 列表动作 | 新建 / 过账 / 冲销 / 取消 / 导出 / 打印 |
| 菜单 | 顶层分组 `procurement`（已存在），新增子菜单 `goods-receipt-management` → `/receipts`；`skip_auto_menu: true` |
| 权限码 | 双段式：`receipt:receipt_create/read/update/delete/list`、`receipt:receipt_post/reverse/cancel`；行：`receipt_line:*` |
| 路由 | `src/router/detailRouteGuard.js` 的 `SUPPORTED_OBJECT_TYPES` 补 `receipt`，`typeLabels` 补「收货单」 |

---

## 13. 实施步骤

> 迁移序号：当前最大 `v185__employee_master.py`（另一会话在途），本批用 **`v186__receipt_object.py`** + **`v187__receipt_menu_reconcile.py`**；若有新迁移先落地，按实际顺延。

| 步 | 文件（新建 / 修改） | 内容 | 验证 |
|---|---|---|---|
| 1 | `meta/schemas/receipt.yaml`（新建） | §3 头字段、状态机、索引、关系、UI 三态、`child_sections: [receipt_line]` | YAML 加载 / metadata_validator 通过 |
| 2 | `meta/schemas/receipt_line.yaml`（新建） | §4 行字段、规则、索引、关系、`skip_auto_menu: true` | 同上 |
| 3 | `meta/migrations/v186__receipt_object.py`（新建） | 建两表 + 索引；seed 头类型 `RCV_STD`（standard）/ `RCV_RETURN`（return）；seed 序列 `RCV-{DATE:yyyymm}-{SEQ:6}`；回填 `number_sequence_id`；**`ALTER purchase_order_schedules` 补 `rejected_qty` / `completion_source` / `completion_prev_status` 三列（先查后用，幂等）**；permissions（双段式）；menus；幂等；`verify()` 断言 | 连跑两次 DB 终态一致 |
| 4 | `meta/services/receipt_service.py`（新建） | `create` / `post` / `reverse` / `cancel`；取号在开事务前（R-RC-8）；§6 过账 6 步；§6.1 拆分；§7 红冲 | 服务用例全绿 |
| 5 | `meta/services/receipt_guard_service.py` + `meta/core/interceptors/receipt_guard_interceptor.py`（新建） | §5.3 不变量；posted 不可变；行一致性；超收拦截 | 守卫用例全绿 |
| 6 | `meta/server.py` / `meta/core/app_builder.py`（修改） | 注册 `ReceiptGuardInterceptor()` | 启动后守卫生效 |
| 7 | `meta/services/bo_action_registrations.py`（修改） | 注册 `receipt.create_from_schedule`（由 PO 计划行批量生成收货行）、`receipt.post`、`receipt.reverse`、`receipt.cancel` | action 契约校验通过；`GET /api/v2/action/` 可见 |
| 8 | `meta/services/purchase_order_fulfillment_service.py`（**已建**） | PO 头 / 行 `fulfillment_status` + `fulfillment_derived_at` 派生（过账 / 冲销双向）；`recompute_line / recompute_order / recompute_all`；口径见 `spec §6 步 4` | `test_purchase_order_fulfillment_service.py` 9 passed |
| 9 | PO spec 增量修订（**已回写**） | ① R-PO-9 按 `target_bo` 分段并共用容差；② 新增 `close_po_schedule`（`planned/confirmed → completed`，`completion_source='short_close'`，记 `closed_short_qty`）；③ 计划行新增 `rejected_qty` / `completion_source` / `completion_prev_status`；④ 明确 `received_qty` = 净收；⑤ `complete_po_schedule` 仅 `confirmed→completed` 且带来源 | PO spec §14.1 / §10.2 / §10.4 / §11 已同步 |
| 10 | `meta/tests/test_receipt_schema.py`（新建） | 字段 / 切面 / 状态机 / 索引 / 关系 / child_sections 断言 | `python d:\filework\test.py --single ...` |
| 11 | `meta/tests/test_receipt_service.py`（新建） | 过账回写 / 分批 / 超收拒绝 / 拒收三件套 / 空单拒绝 / 取消 | 同上 |
| 12 | `meta/tests/test_receipt_allocation.py`（新建） | §6.1 拆分（单分配 / 多分配 / 余数 / 耗尽 / 红字负向） | 同上 |
| 13 | `meta/tests/test_receipt_reversal.py`（新建） | 整单红冲 / 计划行回退 / PO 履约重算 / 原单置 reversed | 同上 |
| 14 | `meta/migrations/v187__receipt_menu_reconcile.py`（新建） | v186 首次执行后补菜单 / 授权 / 孤儿清理（照 v181 幂等模式） | `verify OK`；`/receipts` 路由可渲染 |
| 15 | `src/router/detailRouteGuard.js`（修改） | 补 `receipt` 与「收货单」标签 | 手拼 `/detail/receipt/<id>` 可渲染 |
| 16 | `.trae/debug/receipt_smoke.py`（调试脚本，不入库） | 真实 DB + BO 框架：转单 → 计划行 → 收货过账 → 断言计划行 / 履约 / 分配 → 超收拒绝 → 整单红冲 | 7 步全绿，结果写 `receipt_smoke.json` |
| 17 | 回归 | PO / SO / requisition 链路 | `python d:\filework\test.py --failed`；必要时 `--all` 后 `--failed` 串行确认 |

---

## 14. 冒烟步骤（真实验收）

| 步 | 动作 | 断言 |
|---|---|---|
| 1 | 用需求转单服务建 PO（或复用上一波 PO 23） | 计划行存在、`received_qty` 为空 |
| 2 | 由计划行生成收货行（`create_from_schedule`） | 行 `item_id / uom_id / order_line_id` 与计划行一致 |
| 3 | 过账 | 头 / 行 `posted`；计划行 `received_qty` = 净量；PO 行 `partially_received` |
| 4 | 再收余量 | 计划行 `completed`；PO 行 / 头 `received` |
| 5 | 超收请求 | `RC_OVER_RECEIPT`；计划行与 PO 状态不变 |
| 6 | 整单红冲 | 红字单 `posted`；原单 `reversed`；计划行 `received_qty` 归零并回退 `confirmed`；分配负向行 |
| 7 | 无库存断言 | 全库无 `stock_*` / `inventory_*` 新表（契约未落地属预期） |

---

## 15. 出口判据（E-RC-1 ~ E-RC-12）

| 编号 | 判据 | 验证方式 |
|---|---|---|
| E-RC-1 | `receipt` / `receipt_line` 与 `shipment` / `shipment_line` 骨架同构（M1-M10） | schema 断言 |
| E-RC-2 | 收货行只挂计划行；`schedule_id` 非 PO 来源走 `source_line_id` | schema + 守卫用例 |
| E-RC-3 | 过账 6 步全部生效且单事务 | 服务用例 + 冒烟 |
| E-RC-4 | 超收默认拒绝、容差由控制参数放开 | 用例（0 / 5% 两组） |
| E-RC-5 | 分批收货时分配按剩余量拆分、余数归尾 | 分配用例（§6.1 例子） |
| E-RC-6 | PO 分配与收货分配分段上限，不相加 | 分配用例 + 上限拒绝 |
| E-RC-7 | 整单红冲可逆，计划行 / 履约 / 分配三处回滚 | 冲销用例 |
| E-RC-8 | `posted` 后不可改数量；只能红冲 | 守卫用例 |
| E-RC-9 | 不建库存 / 质检 / ASN 对象，措辞不出现「已入库」 | schema 断言 + 页面文案检查 |
| E-RC-10 | 发票契约中的键（`receipt_line_id` / `schedule_id`）过账后稳定 | schema 断言 |
| E-RC-11 | 计划行 `received_qty` / `rejected_qty` 与 `receipt_line` 流水对账零差异（R-RC-16） | 对账脚本连跑两次均为 0 差异 |
| E-RC-12 | 收货过账 / 红冲后 PO 履约状态与 `recompute_all` 重算结果一致（重算写入 0 条） | 幂等重算断言 |

---

## 16. 开放问题

| # | 问题 | 当前结论 | 影响 |
|---|---|---|---|
| Q1 | 是否建 ASN（供应商预先发货通知） | 本波不建；到货计划行已表达承诺 | 建则需 `asn` / `asn_line`，收货行可挂 ASN |
| Q2 | 收货是否需要审批 | **不需要**：收货是事实确认，审批在 PO；差异处置走拒收 / 红冲 | 若客户要求「收货复核」，可加 `receipt_approval_required` 控制参数（不默认） |
| Q3 | 拒收是否要独立质检单 | 本波不建；三件套够用 | 后续质检波次可把 `qty_rejected` 升级为检验单 |
| Q4 | 是否支持部分红冲 / 按行红冲 | 本波只整单红冲 | 部分红冲需逐行负向正确性，后置 |
| Q5 | 序列号是否要明细子表（一行多序列） | 本波单字段；物料主数据未声明批次 / 序列管理 | 建 `receipt_line_serial` 需先有物料管理标记 |
| Q6 | 收货单位与订单单位不同时是否换算 | 本波不换算（`uom_id` 必须等于计划行） | 换算需 `item_uom_conversion` 接线与舍入口径 |
| Q7 | 供应商退货出库（RTV）何时做 | 依赖库存台账，M4 后 | 需 `direction='out'` 与库存扣减 |
| Q8 | 短收结案用 `close_po_schedule` 还是 `cancel_po_schedule` | **新增 `close_po_schedule`**（`completed`），保留 `cancelled` 给「整行作废」 | 需 PO spec 同步 |
| Q9 | 库存台账归属哪个波次 | M4；本波只留 `inventory_transaction` 契约 | 决定「已过账 ≠ 已入库」期限 |
| Q10 | `received_by` 是否走人员主数据 | 本波文本快照（与 PO 联系人同口径） | 人员主数据就绪后可改引用 |

---

## 17. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| D-RC-1 | 收货单全系统**只建一个**，按 `source_doc_type` 复用 | T-D12；按内部 / 外部 / 来源分表会让对账与权限分裂 |
| D-RC-2 | 收货行**唯一挂计划行**（PO 来源强约束 `schedule_id`），非 PO 来源用 `source_line_id` 多态占位 | 与销售侧 `shipment_line` 完全镜像；没有计划层就无法表达分批到货 |
| D-RC-3 | 以**过账**为核心事件，`posted` 即不可改 | 收货是事实，修正只能红冲；避免「改历史数量」导致计划行与分配漂移 |
| D-RC-4 | 本波只做**整单红冲**，部分红冲 / RTV 后置 | 整单红冲的负向副作用可一次回滚，验证闭环；部分红冲需要逐行净量账 |
| D-RC-5 | 收货**不设审批** | 审批发生在 PO；对收货再审批会拖慢仓库且与红冲机制重复 |
| D-RC-6 | `demand_allocation` 的 PO 阶段与收货阶段**分段计数**，不相加 | 同一批货被数两遍会违反原 R-PO-9；Oracle 的 PO distribution 与 receipt distribution 也是两套事实 |
| D-RC-7 | 不建质检对象，用 `qty_rejected` + 原因 + 处置 | 质检方案 / 抽样 / 检验项是独立领域，强塞进收货会拖垮单据模型 |
| D-RC-8 | **不建库存台账**；收货只表达事实与 `inventory_transaction` 契约 | 全仓无库存对象；贸然建半成品库存表会锁死 M4 的批次 / 序列 / 成本层设计 |
| D-RC-9 | 收货不落金额（单价 / 税额 / 金额） | 金额以 PO 快照 + 发票为准；收货落金额会造成三份金额来源 |
| D-RC-10 | 收货地点与入库库位分离（`deliver_to_location_id` vs `putaway_location_id`） | 送达地址 ≠ 实际上架库位；合并会让库位统计失真 |
| D-RC-11 | 批次 / 序列与销售侧同构（单字段） | 复用 UI 与守卫；序列明细待物料主数据声明后再拆表 |
| D-RC-12 | PO 计划行新增 `close_po_schedule`（短收结案） | 短收在现实中常见；只靠 `cancelled` 无法区分「剩余作废」与「按实结案」 |
| D-RC-13 | 服务计划行收货即验收确认 | 复用同一对象与同一状态机；不建第二套验收单 |
| D-RC-14 | 红字单 `document_category='return'`，数量保持正数、净量为负向贡献 | 保持 `qty_received > 0` 的单一正数口径；避免负数量污染 UI / 报表 |

---

## 18. 对 PO spec 的修订点（评审时一并确认）

| # | 原口径（PO spec） | 修订 |
|---|---|---|
| 1 | R-PO-9：`sum(active.qty) <= 需求行 qty`（不分阶段） | 按 `target_bo` 分段：PO 分配 ≤ 需求行 qty；收货分配 ≤ 对应 PO 分配 `qty × (1 + receipt_over_tolerance_percent)`（§6.2 / R-RC-9） |
| 2 | §10.4 计划行只有 `confirm / complete / cancel` | 新增 `close_po_schedule`（`planned/confirmed → completed`，`completion_source='short_close'`，记 `closed_short_qty`） |
| 3 | §11「收货行 `schedule_id` 必填」 | 修订为「**PO 来源必填**；非 PO 来源用 `source_line_id`」（§8.2） |
| 4 | §11「收货头最小集」 | 扩展 `supplier_delivery_no / source_doc_no / purchase_org_id / project_id / reversal_of_receipt_id / reversed_at / received_by`（§3） |
| 5 | §11「部分收货回写 `demand_allocation`」 | 明确拆分算法、舍入与耗尽拒绝口径（§6.1） |
| 6 | §10.2 计划行字段 1-12 | 新增 `rejected_qty` / `completion_source` / `completion_prev_status`；`received_qty` 语义改为**净收**（≈ Oracle `QUANTITY_ACCEPTED`）（R-RC-18） |
| 7 | §3 字段 36/37（`fulfillment_status` / `fulfillment_derived_at`） | 明确唯一写入方 `PurchaseOrderFulfillmentService`；收货服务只调用、不直写（R-RC-16 同源纪律） |

---

## 19. 参考来源

| # | 来源 | 用途 |
|---|---|---|
| 1 | `spec-purchase-order-object-model-2026-11-01.md` §10 / §11 / §12 | 计划行、收货契约、doc_flow 边 |
| 2 | `spec-procurement-task-object-model-2026-10-31.md`（T-D12 / T-D19，§6 证据表） | Oracle `RCV_SHIPMENT_LINES`（`PO_HEADER_ID / PO_LINE_ID / PO_LINE_LOCATION_ID / PO_DISTRIBUTION_ID`）、`RCV_TRANSACTIONS`（`TRANSACTION_TYPE / QUANTITY / PARENT_TRANSACTION_ID`，只增不改，净量入 `RCV_SUPPLY`） |
| 3 | `meta/schemas/shipment.yaml` / `shipment_line.yaml`；`meta/services/shipment_service.py` | 交货单骨架、计划行挂载、`delivered_qty` 回写、守卫规则 R-DN-0~8 |
| 4 | `meta/schemas/purchase_order_schedule.yaml`（R-SCH-0~4） | 计划行状态机与超计划拦截 |
| 5 | SAP MM `MIGO` / `EKBE`（收货历史） | 「收货是独立事实单据、可冲销不可改」的行业依据 |
| 6 | Oracle `RCV_TRANSACTIONS` 只增不改 + corrective transaction | 红字冲销而非回滚原行（D-RC-4 / D-RC-14） |
| 7 | D365「Product receipt」与 Coupa「Receipt / Receipt Line」 | 收货与发票分离、三单匹配以计划行 + 行为锚点 |

> 说明：以上行业依据按对象名引用，未附外部链接；实施评审如需出处，再补一次检索。

---

## 20. 审批要求

评审结论（2026-11-01 已确认，按以下变体实施）：

| # | 评审项 | 结论 | 落地位置 |
|---|---|---|---|
| 1 | §2 的 11 项镜像与唯一差异 M11 | 采纳；M10 的履约回写改为「服务派生」，M11（收货写需求分配）不变 | §2 / §6 步 4 |
| 2 | §6.2 分段计数 | 采纳；收货分配上限加容差，与 R-RC-5 共用 `receipt_over_tolerance_percent` | R-RC-9 / §6.1 / PO spec R-PO-9 |
| 3 | §7 整单红冲 + 红字单正数 | 采纳；补 `completion_source` / `completion_prev_status`，红冲只回退 `receipt` 来源 | R-RC-10 |
| 4 | §9 不建库存台账、不写「已入库」 | 采纳 | §9 / E-RC-9 |
| 5 | §13 步 9 `close_po_schedule` | 采纳；与 `complete_po_schedule` 用 `completion_source` 区分（`manual / receipt / short_close`） | PO spec §10.4 |
| 6 | §8.2 非 PO 来源挂载契约 | 采纳；`schedule_id` 与 `source_line_id` 均 nullable，服务层互斥校验，不用 NOT NULL | `receipt_line` schema |
| 7 | §10 发票边界（只锁键） | 采纳；`received_qty` 明确为净收（≈ Oracle `ACCEPTED`），`qty_rejected` 持久化供三单匹配 | §10 / R-RC-18 |

> 实施中若发现新口径差，回到本表增补并同步修订 PO spec，不静默改规则。
