# 采购订单对象模型细化（独立 spec）

> 依据：`spec-procurement-task-object-model-2026-10-31.md`（v1.13 §3 / §5 决策）、`spec-unified-demand-execution-milestone-2026-10-31.md`（M3）、`meta/schemas/sales_order.yaml`、`meta/schemas/sales_order_line.yaml`、`meta/schemas/sales_order_schedule.yaml`、`meta/schemas/shipment.yaml`、`meta/schemas/shipment_line.yaml`、`meta/schemas/requisition.yaml`、`meta/schemas/requisition_line.yaml`
> 状态：草案 v2，待评审；**评审通过前不实施、不提交**
> 范围：M3 第一阶段 —— `purchase_order` 头 / 行 + `demand_allocation` + `purchase_order_schedule`（到货计划行）；收货 / 发票只锁接口契约，字段细化另立 spec
> 日期：2026-11-01

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| M3 能否先做 | **能**。`document_type` 平台（v170 / v171）、需求层审批（M1）已就位；`supplier_party_id` 在 M2 未接线前允许人工填写，M2 接线后由 sourcing 回填，**结构不改** |
| 采购订单与销售订单是否应统一 | **应统一到同一副骨架**：单据类型、编号、状态机、金额快照、行结构、计划行、审计、子表挂载、派生缓存纪律全部对齐 |
| 统一到什么程度 | 头 / 行字段 **80% 同名同义**；差异只保留采购语义必需项（供应商、采购组织、收货地点、供应商单号、供应商物料号） |
| 最关键的统一点 | ① 编号列统一叫 `order_no`；② 状态机统一为 `draft → submitted → confirmed → closed`，任意态可 `cancelled`；③ 行金额字段与取值顺序完全一致；④ 头 / 行只存快照，汇总由服务层回写；⑤ **补上计划行层**，与 `sales_order_schedule` 同构 |
| `demand_allocation` 对标谁 | 头部产品**没有同名通用对象**。结构最接近 **Oracle `PO_DISTRIBUTIONS_ALL`**（PO 行/计划 → requisition distribution 的分配行，带数量与金额），语义最接近 **Oracle / PeopleSoft 的 pegging**（供需数量挂钩），可写性最接近 **Coupa invoice line allocation**。本对象是「事务型 pegging + distribution」的综合，不是抄某一家 |
| PO 层要不要审批 | **要，但可配置，不是硬编码**。SAP 用 release strategy，Oracle 用审批规则引擎，D365 用 change management，Coupa 用审批链。共同点：**单据类型是策略挂载点/维度，金额、组织、品类、供应商才是条件**；审批状态与单据状态分离 |
| 审不审批是否由 document type 定 | **document type 决定「用哪套策略」，不决定「是否审批」**。平台层应以 `document_type_id` 作为策略选择维度，再叠加金额 / 组织 / 品类条件；无匹配策略 = 免审批。**条件因子由独立审批规则模型（策略 / 条件 / 步骤，见 §6.2）承载，不是控制参数表的列** |
| 采购业务类型（委外 / 资产 / 服务 / 费用） | **放行级 `line_type`，不放头级**。一张 PO 可混合物料与服务（SAP item category、Oracle line type + 分配行 expense destination 均为行级）；委外不新建单据对象 |
| 成本中心 / distribution | distribution 在 Oracle 就是「记账到谁头上」（`ChargeAccountId` = 公司 + 成本中心 + 科目 + 项目），与 pegging 同表。所以成本维度（成本中心 / 费用科目 / 资产类别）**长在分配行**，并加 `charge_basis` 决定记账走向 |
| 收货 / 发票 | 收货已另立并细化：`spec-receipt-object-model-2026-11-01.md`（头 / 行 / 过账 / 红冲 / 分配拆分）；本 spec 仍只定对象关系：`purchase_order_schedule`（到货计划行）→ `receipt_line`（收货行）→ `vendor_invoice_line`（发票行）；**发票仍待立** |
| 本 spec 明确不做的 | PO 头 `from_org / to_org`（T-D8）、供应商主数据新表（T-D4）、`doc_flow` 写边（M6）、ASN 对象（列为未决） |

---

## 1. 定位与边界

### 1.1 四层关系（采购侧）

```
requisition（需求，审批在此，M1）
    │  sourcing 求值（M2 给出 supplier_party_id / 内部来源）
    ▼
purchase_order（采购订单，本 spec）
    └── purchase_order_line（订单行）
          └── purchase_order_schedule（到货计划行，本 spec）
                └── receipt_line（收货行，M3 第二阶段）
                      └── vendor_invoice_line（发票行，M3 第二阶段）
```

### 1.2 边界

| 属于 PO | 不属于 PO |
|---|---|
| 与外部供应商的成交事实（数量、单价、币种、交期、条款） | 需求审批（在 `requisition`，T-D2） |
| 采购方组织与财务归属（`org_id` / `purchase_org_id`） | 内部交易方向（`from_org` / `to_org`，T-D8；跨法人走 ISO，同法人异库存组织走 `transfer_order`） |
| 合并采购的分配归集（`demand_allocation`） | 供应商主数据（走 `party` + `party_relation(role='vendor')` + `vendor_account`，T-D4） |
| 到货计划与部分收货追溯（`purchase_order_schedule`） | 生产 / 外协工序（走 `work_order`，不是 PO） |
| 收货 / 发票的追溯锚点（PO 行 / 计划行 id） | 发票校验策略（M3 第二阶段） |

### 1.3 为什么 M3 可以先做

| 前置 | 状态 | 影响 |
|---|---|---|
| 单据类型平台 | v170 / v171 已落，`type_definitions` 可挂 `scope_bo='purchase_order'` | 无阻塞 |
| 需求层审批 | M1 已落 `tasks(type=approval)` + 控制参数 | PO 审批可复用同一底座 |
| sourcing 求值 | M2 代码齐备但全仓无调用方 | `supplier_party_id` 先人工填；`sourcing_rule_line_id` 先留空 |
| 收货 / 发票 | 收货已细化（`spec-receipt-object-model-2026-11-01.md`）；发票仍待立 | 收货字段 / 过账 / 红冲已独立成 spec；本 spec 保留 `source_doc_type` 契约与计划行层 |
| `doc_flow` | 内核已存在，app 未声明 | M3 不写边；数量闭合用 `demand_allocation` + 收货行引用 |

风险：M2 未接线时，合并采购的「同物料同供应商」只能人工判断；M3 出口判据中的 sourcing 相关项降级为「结构可回填，不阻塞验收」。

---

## 2. 与销售订单的统一骨架（强约束）

以下 13 项 PO 与 SO **必须一致**，实施时逐条对照，测试逐条断言。

| # | 维度 | 统一口径 |
|---|---|---|
| U1 | 表命名 | 头 `purchase_orders` / 行 `purchase_order_lines` / 计划 `purchase_order_schedules`；行与计划均为 `parent_object: purchase_order` |
| U2 | 业务键 | 头唯一业务键列名 **`order_no`**（与 SO 同名，不复用 `po_no`）；行 `line_no` 字符串、`^[0-9]{1,6}$`、同一单内唯一；计划行 `schedule_no` 整数、行内唯一 |
| U3 | 单据类型 | 头 `document_type_id`（`type_definitions.scope_bo='purchase_order'` + `level='header'`），行 `line_type_id`（同 `scope_bo` + `level='line'`）；创建时必填、离开草稿不可改（T-D20） |
| U4 | 状态机 | 头 5 态 `draft / submitted / confirmed / closed / cancelled`；行 3 态 `open / closed / cancelled`；计划行 4 态 `planned / confirmed / completed / cancelled`；规则命名 `submit_* / confirm_* / close_* / cancel_*` |
| U5 | 金额快照 | 行：`qty × unit_price = net_amount`；`tax_amount` 按 `tax_code`；`gross_amount = net_amount + tax_amount`；头三项恒等于行汇总；**界面只读，服务层回写** |
| U6 | 币种与汇率 | `currency_id` 必填；`exchange_rate` 默认 1；`exchange_rate != 1` 时 `exchange_rate_date` 必填 |
| U7 | 审计切面 | `aspects: [audit_aspect]`；`create: all` / `update: changed_only` / `delete: business_only`；派生缓存列与 PII 列排除 |
| U8 | 删除策略 | `mode: restrict`，`cascade_delete: [purchase_order_lines]`；非草稿禁删行（守卫强制度） |
| U9 | 版本号 | `revision_no` 整数、默认 1、平台写入、界面不可编辑 |
| U10 | 派生缓存 | `fulfillment_status` / `fulfillment_derived_at` 为**只读缓存**（T-D19），唯一写入方 `PurchaseOrderFulfillmentService`，禁止人工改；计划行 `received_qty` / `rejected_qty` 为只读缓存列（真源是 `receipt_line` 过账流水，R-RC-16 对账） |
| U11 | 子表挂载 | 行与计划行不建顶层菜单；头 `ui_view_config` 用 `child_sections` 内联行、分配、计划；`skip_auto_menu: true`，菜单由迁移落库 |
| U12 | 编号 | 头创建时经 `type_definitions.number_sequence_id` 取号（平台通用路径 `meta/api/bo_api.py` L482-500），生成后不可改，允许跳号 |
| U13 | 计划层 | SO 有 `sales_order_schedule`；PO 必须有同构的 `purchase_order_schedule`，下游单据（SO→shipment / PO→receipt）都挂在计划行上，不直接挂订单行 |

### 2.1 与 SO 的差异清单（仅 8 项，均有语义理由）

| # | 差异 | SO | PO | 理由 |
|---|---|---|---|---|
| D1 | 交易对手 | `customer_account_id` + `ship_to_party_id` | `supplier_party_id`（必填）+ `supplier_account_id`（可空） | M2 sourcing 直接输出 `supplier_party_id`；账户只承载商务默认值 |
| D2 | 组织维度 | `sales_org_id`（须 sales 职能） | `purchase_org_id`（须 purchasing 职能） | 同名机制，职能不同 |
| D3 | 收货地点 | `ship_to_party_id` / `ship_to_address_id` / 行 `plant_location_id` | 头 / 行 / 计划行 `deliver_to_location_id` | 采购收货是我方内部地点，与需求层同名，不再引入第三个名字 |
| D4 | 外部单号 | `customer_po_no` | `supplier_reference_no` | 方向相反 |
| D5 | 物料代号 | `customer_item_code` | `supplier_item_code` | 方向相反 |
| D6 | 行项目归属 | 行 `project_id` | **行不设 `project_id`** | 合并采购后单行可服务多个需求行，归属由 `demand_allocation` 表达（T-D3） |
| D7 | 配置展开 | `configuration_id` / `parent_line_id` / `pricing_mode` / `component_no` | **设 `pricing_mode` / `parent_line_id` / `component_no`**（成套计价需要）；`configuration_id` 只读追溯 | 修正见 §5.5：采购有成套整包价，但**不触发选配求解**；`reference_line_id` 仍不设 |
| D8 | 服务计费 | `billing_method` / `required_resource_type` / `service_duration` / `duration_type` | 不设；仅保留 `service_start_date` / `service_end_date` | 采购服务的结算由发票 / 验收处理，PO 不表达「如何向客户计费」 |

> 单据类型挂载机制：本 spec 采用平台切面 `document_type_aspect`（requisition / service_request 已用）；SO 目前是手写字段，字段 id 与语义完全一致。**SO 迁到切面属遗留治理（L-PO-1），不在 M3 范围。**

---

## 3. `purchase_order` 头字段表

表：`purchase_orders`；`display_name_field: order_no`；`aspects: [audit_aspect, document_type_aspect]`；`semantics.category: business_document`；`business_key: [order_no]`。

| # | 字段 id | 中文 | 类型 | 必填 | SO 对应 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | `id` | 自增主键 |
| 2 | `order_no` | 采购订单号 | string(30) | 是 | `order_no` | 唯一、不可改；创建时取号，`ui.editable: false` |
| 3 | `document_type_id` | 单据类型 | integer | 是（创建） | `document_type_id` | 切面提供；`scope_bo='purchase_order'` + `level='header'`；离开草稿不可改 |
| 4 | `order_date` | 订单日期 | date | 是 | `order_date` | 取号日期段与汇率快照基准 |
| 5 | `project_id` | 项目 | integer | 否 | `project_id` | 整单归集用；空 = 未归集。行级归集走分配表 |
| 6 | `status` | 状态 | string(20) | 是 | `status` | 默认 `draft`，5 态枚举同 SO |
| 7 | `supplier_party_id` | 供应商 | integer | 是 | （无） | `party.id`；M2 前人工填，M2 后 sourcing 回填 |
| 8 | `supplier_account_id` | 供应商档案 | integer | 否 | `customer_account_id` | `vendor_account.id`；空 = 用该 party 默认 vendor 档案；承载币种 / 付款条件 / Incoterm 默认值 |
| 9 | `supplier_reference_no` | 供应商单号 | string(40) | 否 | `customer_po_no` | 供应商侧的订单号 |
| 10 | `contact_party_id` | 联系人 | integer | 否 | `contact_party_id` | 供应商联系人；PII 相关列不进审计 |
| 11 | `contact_name_text` | 联系人姓名 | string(80) | 否 | `contact_name_text` | 快照，PII，审计排除 |
| 12 | `contact_phone_text` | 联系电话 | string(40) | 否 | `contact_phone_text` | 快照，PII，审计排除 |
| 13 | `org_id` | 业务实体 | integer | 是 | `org_id` | 采购方法人 / 财务归属；默认取送达组织所属法人 |
| 14 | `purchase_org_id` | 采购组织 | integer | 是 | `sales_org_id` | 须具备 purchasing 职能；数据范围与报表主过滤维度 |
| 15 | `division_code` | 产品分部 | string(20) | 否 | `division_code` | 与 SO 同义 |
| 16 | `deliver_to_location_id` | 收货地点 | integer | 否 | `ship_to_*` + `plant_location_id` | 空 = 采购组织默认地点；行 / 计划行可覆盖 |
| 17 | `currency_id` | 币种 | integer | 是 | `currency_id` | 订单币种 |
| 18 | `exchange_rate` | 汇率 | number | 是 | `exchange_rate` | 默认 1 |
| 19 | `exchange_rate_type` | 汇率类型 | string(20) | 否 | `exchange_rate_type` | 确认时冻结 |
| 20 | `exchange_rate_date` | 汇率日期 | date | 否 | `exchange_rate_date` | `exchange_rate != 1` 时必填 |
| 21 | `payment_term_id` | 付款条件 | integer | 否 | `payment_term_id` | 空 = 供应商档案默认 |
| 22 | `incoterm_code` | 贸易条款 | string(10) | 否 | `incoterm_code` | 与 SO 同义 |
| 23 | `requested_date` | 需求交付日 | date | 否 | `requested_date` | 整单口径；计划行可覆盖 |
| 24 | `confirmed_date` | 供应商确认日 | date | 否 | `confirmed_date` | 确认时填 |
| 25 | `price_date` | 定价日期 | date | 否 | `price_date` | 单价快照基准日 |
| 26 | `header_discount_percent` | 头折扣率 | number | 是 | 同名 | 默认 0；与 SO 金额聚合口径一致 |
| 27 | `header_surcharge_percent` | 头附加率 | number | 是 | 同名 | 默认 0 |
| 28 | `header_discount_amount` | 头折扣额 | number | 是 | 同名 | 默认 0，快照 |
| 29 | `header_surcharge_amount` | 头附加额 | number | 是 | 同名 | 默认 0，快照 |
| 30 | `net_amount` | 净额 | number | 是 | `net_amount` | 默认 0，行汇总回写 |
| 31 | `tax_amount` | 税额 | number | 是 | `tax_amount` | 默认 0 |
| 32 | `gross_amount` | 含税额 | number | 是 | `gross_amount` | 默认 0 |
| 33 | `description` | 订单说明 | text(2000) | 否 | `description` | 与 SO 同义 |
| 34 | `revision_no` | 版本号 | integer | 是 | `revision_no` | 默认 1，平台写入 |
| 35 | `approval_status` | 审批状态 | string(20) | 是 | （SO 无） | **只读缓存**：`not_required / pending / approved / rejected`；默认 `not_required`，由审批任务派生，见 §6 |
| 36 | `fulfillment_status` | 履约状态 | string(20) | 否 | `fulfillment_status` | **只读缓存**：`open / partially_received / received / closed`；唯一写入方 `PurchaseOrderFulfillmentService` |
| 37 | `fulfillment_derived_at` | 履约派生时间 | datetime | 否 | 同名 | **只读缓存**；随派生刷新，作为巡检水位 |
| 38 | `created_at` | 创建时间 | datetime | 否 | `created_at` | — |
| 39 | `updated_at` | 更新时间 | datetime | 否 | `updated_at` | — |

### 3.1 `status` 枚举（与 SO 完全一致）

| 值 | 标签 | 色 | 类别 | 初态 |
|---|---|---|---|---|
| `draft` | 草稿 | info | draft | 是 |
| `submitted` | 已提交 | primary | active | — |
| `confirmed` | 已确认 | success | active | — |
| `closed` | 已关闭 | info | inactive | — |
| `cancelled` | 已取消 | danger | inactive | — |

### 3.2 `approval_status` 枚举（与单据状态正交）

| 值 | 标签 | 色 | 含义 |
|---|---|---|---|
| `not_required` | 免审批 | info | 无匹配审批策略；提交后可直接确认 |
| `pending` | 审批中 | warning | 已建审批任务，状态停在 `submitted` |
| `approved` | 审批通过 | success | 可执行确认 |
| `rejected` | 审批驳回 | danger | 单据退回 `draft`，修改后可重提 |

### 3.3 头级索引

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uidx_purchase_order_no` | `order_no` | 是 |
| `idx_purchase_order_supplier_date` | `supplier_party_id, order_date` | 否 |
| `idx_purchase_order_purchase_org_date` | `purchase_org_id, order_date` | 否 |
| `idx_purchase_order_status` | `status` | 否 |
| `idx_purchase_order_approval_status` | `approval_status` | 否 |
| `idx_purchase_order_document_type` | `document_type_id` | 否 |
| `idx_purchase_order_project` | `project_id` | 否 |

### 3.4 头级关系

`purchase_order_to_type_definition`、`purchase_order_to_supplier`（→ `party`，真外键）、`purchase_order_to_supplier_account`（→ `vendor_account`，可空）、`purchase_order_to_org`、`purchase_order_to_purchase_org`（→ `org`，可空校验在守卫）、`purchase_order_to_location`、`purchase_order_to_currency`、`purchase_order_to_payment_term`、`purchase_order_to_project`。

---

## 4. `purchase_order_line` 行字段表

表：`purchase_order_lines`；`parent_object: purchase_order`；`hierarchy: {enabled: true, parent_field: order_id}`；`aspects: [audit_aspect]`；`deletion_policy.mode: cascade`（父单草稿删除时级联；非草稿由守卫禁删）。

| # | 字段 id | 中文 | 类型 | 必填 | SO 对应 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | `id` | 主键 |
| 2 | `order_id` | 所属订单 | integer | 是 | `order_id` | 父键；`ui.relation: purchase_order` |
| 3 | `line_no` | 行号 | string(6) | 是 | `line_no` | 同单唯一，`^[0-9]{1,6}$` |
| 4 | `line_type_id` | 行类型 | integer | 是 | `line_type_id` | `scope_bo='purchase_order'` + `level='line'` |
| 5 | `item_id` | 物料 | integer | 否 | `item_id` | `goods` 行必填；`service` 行可空 |
| 6 | `supplier_item_code` | 供应商物料号 | string(40) | 否 | `customer_item_code` | 方向相反 |
| 7 | `description` | 行描述 / 服务规格 | string(300) | 否 | `description` | `item_id` 为空时必填 |
| 8 | `qty` | 数量 | number(6) | 是 | `qty` | `> 0`；退货单由单据类型方向决定，行内不带方向 |
| 9 | `uom_id` | 单位 | integer | 否 | `uom_id` | `goods` 行必填；`service` 行可空 |
| 10 | `unit_price` | 单价 | number(6) | 否 | `unit_price` | 默认 0；确认时冻结 |
| 11 | `net_amount` | 净额 | number(2) | 是 | `net_amount` | 默认 0，服务层计算 |
| 12 | `header_discount_amount` | 分摊头折扣 | number(2) | 是 | 同名 | 默认 0 |
| 13 | `header_surcharge_amount` | 分摊头附加 | number(2) | 是 | 同名 | 默认 0 |
| 14 | `tax_code_id` | 税码 | integer | 否 | `tax_code_id` | 空 = 免税 |
| 15 | `tax_base_amount` | 计税基数 | number(2) | 是 | `tax_base_amount` | 默认 0 |
| 16 | `tax_rate_percent` | 税率 | number(4) | 否 | `tax_rate_percent` | 确认时冻结 |
| 17 | `tax_amount` | 税额 | number(2) | 是 | `tax_amount` | 默认 0 |
| 18 | `gross_amount` | 含税额 | number(2) | 是 | `gross_amount` | 默认 0 |
| 19 | `requested_date` | 行需求日期 | date | 否 | `requested_date` | 空 = 取头；计划行可覆盖 |
| 20 | `deliver_to_location_id` | 行收货地点 | integer | 否 | `plant_location_id` | 空 = 取头；计划行可覆盖 |
| 21 | `service_start_date` | 服务开始日 | date | 否 | 同名 | 仅 `service` 行 |
| 22 | `service_end_date` | 服务结束日 | date | 否 | 同名 | 仅 `service` 行 |
| 23 | `price_source` | 价格来源 | string(20) | 否 | `price_source` | `manual / contract / quotation / price_list` |
| 24 | `price_trace` | 价格轨迹 | text | 否 | `price_trace` | JSON 快照；M3 允许为空 |
| 25 | `sourcing_rule_line_id` | 命中寻源规则行 | integer | 否 | （无） | M2 接线后回填，用于回答「为什么这个供应商」；不改结构 |
| 26 | `status` | 行状态 | string(20) | 是 | `status` | 默认 `open`；`open / closed / cancelled` |
| 27 | `fulfillment_status` | 行履约状态 | string(20) | 否 | `fulfillment_status` | **只读缓存**，由收货分配派生 |
| 28 | `fulfillment_derived_at` | 行派生时间 | datetime | 否 | 同名 | **只读缓存** |
| 29 | `created_at` | 创建时间 | datetime | 否 | `created_at` | — |
| 30 | `updated_at` | 更新时间 | datetime | 否 | `updated_at` | — |

### 4.1 行级索引

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uidx_purchase_order_line_no` | `order_id, line_no` | 是 |
| `idx_purchase_order_line_item` | `item_id` | 否 |
| `idx_purchase_order_line_order_status` | `order_id, status` | 否 |
| `idx_purchase_order_line_sourcing` | `sourcing_rule_line_id` | 否 |

### 4.2 行级规则

`close_purchase_order_line`：`open → closed`；`cancel_purchase_order_line`：`open, closed → cancelled`；命名与 SO 行规则同构。

---

### 4.3 定价与采购金额计算（与销售订单复用）

#### 4.3.1 销售侧现状（读代码确认的事实）

| 环节 | 实现位置 | 内容 |
|---|---|---|
| 行 / 头金额算术 | [sales_order_amount_service.py](file:///d:/filework/excel-to-diagram/meta/services/sales_order_amount_service.py#L101-L167) | 行 `net = qty × unit_price + 头折扣分摊 + 头附加分摊`，再算 `tax_amount / gross_amount`；头按行求和回写。**与对象无关，可直接复用** |
| 取价执行 | [sales_order_pricing_service.py](file:///d:/filework/excel-to-diagram/meta/services/sales_order_pricing_service.py#L102-L188) | 校验草稿态 → 调 `PricingDeterminationService` → 写 `unit_price / price_source / price_trace`，头写 `price_list_id / pricing_procedure_id` |
| 定价规则 | `pricing_determination`（`pricing_determinations`） | 键 = `sales_org_id + order_type_id + 生效日`，输出 `rate_table_id + 定价过程 + 查找序列`；`rate_table_id` 可空 = 按组织 + 币种自动选最新 approved 表 |
| 价目表 | `rate_table`（`rate_tables`） | `status ∈ draft / approved / inactive`，**仅 approved 参与取价**；`owner_org_id` 空 = 全局、非空 = 限定组织；币种必填 |
| 取价优先级 | `customer_account.default_rate_table_id` → `customer_sales_org.rate_table_id` → 定价规则 → 价目表最新 | 销售侧已有完整回退链 |

#### 4.3.2 采购侧复用裁决

| 环节 | 是否复用 | 口径 |
|---|---|---|
| 金额算术 | **完全复用** | 抽 `DocumentAmountService`（纯函数：行金额 → 税 → gross；头汇总），SO 现有服务改为薄包装；PO 调同一函数，字段名与取值顺序不变 |
| 取价执行骨架 | **复用** | `PricingDeterminationService` + `PricingService` 同一套；PO 只是把「解析规则来源」换成采购规则 |
| 价目表 `rate_table` | **复用同一张表** | 采购侧按 `owner_org_id = purchase_org_id` 过滤；供应商价目表用同一容器，不新建 `supplier_price_list` |
| 定价规则表 | **不复用，新建 `purchase_pricing_determination`** | 销售规则键是「销售组织 + 订单类型」，采购规则键是「采购组织 + 单据类型 + 供应商」，合并会让一半列恒空；原理同 D-PO-13 |
| 取价优先级 | **不复用顺序** | 采购侧新序（对齐 Oracle 寻源默认顺序）：本地协议 > 全局协议 > 供应商报价 > 价目表 > 最近采购价 > 标准成本 > 人工，详见 §4.4.2 |

`purchase_pricing_determination`（v178）字段：`id, code, name, purchase_org_id, document_type_id, supplier_party_id, base_date_from, base_date_to, seq, rate_table_id, status`；匹配次序 = 供应商精确 > 组织精确 > 序列号小者（沿用销售侧 `score` 口径，避免出现第二套默认语义）。

#### 4.3.3 采购侧的取价来源与金额差异

| `price_source` 值 | 含义 | M3 |
|---|---|---|
| `manual` | 人工录入 | 启用 |
| `agreement` | 一揽子协议（本地 / 全局），价格来自数量阶梯 | 启用 |
| `rate_table` | 命中价目表 | 启用 |
| `quotation` | 供应商报价（catalog / standard quotation） | 启用（可只读引用） |
| `last_po` | 最近一次已确认 PO 的单价（按 `supplier_party_id + item_id` 取最新） | 启用（只读派生，采购特有，SO 没有） |
| `standard_cost` | 物料标准成本 | 留枚举位 |

金额口径差异（其余全部同 SO）：

| 项 | SO | PO | 处理 |
|---|---|---|---|
| 税方向 | 销项 | 进项 | 同一 `tax_code` 计算，方向由单据类型决定，**不新增字段** |
| 不可抵扣税 | — | 部分费用票需计入成本 | 行加 `tax_recoverable`（默认 true）；false 时税额单列 `non_recoverable_tax_amount`，**不并入 `net_amount`**，避免破坏「net 未税」口径 |
| 运费 / 关税 | — | 常见 | M3 先由 `header_surcharge_amount` 承接；多费用行另立 spec |
| 整单折扣 / 附加 | 有 | 供应商整单折扣，同构 | 完全复用头四字段与分摊算法 |

#### 4.3.4 需并入 §3 / §4 字段表的追加项

| 位置 | 字段 | 说明 |
|---|---|---|
| 头 | `price_list_id` | 取价命中的价目表快照（同 SO `price_list_id`） |
| 头 | `pricing_procedure_id` | 定价过程快照（同 SO） |
| 行 | `tax_recoverable` | 布尔，默认 true；进项税是否可抵扣 |

M3 范围：金额算术复用 + `manual / rate_table / last_po` 三源 + 头两个快照；合同价、标准成本、费用行、税不可抵扣只留字段位。Oracle 核对结论见 §4.4。

### 4.4 Oracle 二次确认（四项核对）

| # | 本 spec 的方案 | Oracle 实际做法 | 结论 |
|---|---|---|---|
| V1 | 金额算术复用 SO | 采购与销售共用同一套价目 / 价格调整机制（价格阶梯、附加费、调整） | 一致，可复用 |
| V2 | 定价规则表不共用 | Oracle 里销售用 Advanced Pricing 价目表，采购用供应商 catalog / quotation + 一揽子协议价格阶梯，**本来就是两套** | 一致，且反向印证「不共用」 |
| V3 | 取价优先级「协议 > 价目表 > 最近采购价 > 标准成本 > 人工」 | 寻源默认顺序：**本地 BPA > 全局 BPA > 本地合同 > 全局合同 > 报价（quotation）**；价格来自命中协议的价格阶梯；多条同时命中**取最低价**；阶梯可选累计 / 非累计 | 需细化：区分本 / 全局，且必须落地价格阶梯 |
| V4 | 委外 = 成品行 + 我方组件发料清单 | Oracle OSP：PO 行是**外协工序服务**，组件按 Push / Pull 供应类型发到 WIP 工单，收货进 WIP 而非库存 | **模型不同**，需明确选型（见下） |

#### 4.4.1 V4 委外模型选型

Oracle 的 OSP 有三条硬前提：WIP 工单、工艺路线、outside resource。PO 只是外协工序的采购载体，组件从不落到 PO 上。

我们目前**没有 WIP 与工艺路线**，照搬会把委外绑死在未建对象上。所以：

- M3 采用 **SAP 式委外整单**：PO 行 = 加工后物料 + 组件发料清单（`subcontract_component`）；
- 等 `work_order` 落地后，再评估切到 OSP 式「工序服务行」；
- 迁移点只有一个：`line_type='subcontract'` 的行拆成「成品行（可选）+ 工序服务行」，组件发料改挂 `work_order`。结构上已由 `component_issue_required` 与 `subcontract_component` 预留，不需要改 PO 主表。

#### 4.4.2 V3 的落地修正

| 项 | 修正后口径 |
|---|---|
| `price_source` | `agreement`（一揽子协议）/ `quotation`（供应商报价）/ `rate_table`（价目表）/ `last_po`（最近采购价）/ `standard_cost`（标准成本）/ `manual`。原 `contract` 归并进 `agreement` |
| 价格阶梯 | 协议与报价都必须有 `qty_from / qty_to` 阶梯，并可带 `ship_to_location_id` 匹配；**同条件多档命中取最低价**（与 Oracle 一致） |
| 阶梯口径 | 加参数 `price_break_cumulative`（true = 按累计数量选档，false = 按本次数量）；**必须显式配置**，不设隐式默认 |
| 寻源优先级 | 本地协议 > 全局协议 > 供应商报价 > 价目表 > 最近采购价 > 标准成本 > 人工；表结构用 `agreement_scope ∈ local / global` 表达，不靠排序猜 |

Oracle 依据：[Purchase Order Pricing（价格阶梯匹配与取最低价）](https://docs.oracle.com/en/cloud/saas/procurement/25d/oaprc/purchase-order-pricing.html)、[Defaulting Sourcing Information（本地 / 全局协议优先级）](http://docs.oracle.com/cd/E18727_01/doc.121/e13410/T446883T443954.htm)、[OSP 物理流（Push / Pull 发料）](http://docs.oracle.com/cd/A60725_05/html/comnls/us/po/osp03.htm)、[AutoCreate Requisitions（需求由销售订单 / 计划订单生成）](https://docs.oracle.com/cd/E18727_01/doc.121/e13406/T373258T374217.htm)。

---

## 5. 单据类型与编号

| 项 | 口径 |
|---|---|
| 头类型 | `type_definitions.scope_bo='purchase_order'` + `level='header'` + `document_category ∈ {order, return}`（退货单金额为负） |
| 行类型 | `level='line'`；M3 种子至少三条：`PO_GOODS`（物料行）、`PO_SERVICE`（服务行）、`PO_TEXT`（文本行） |
| 默认行类型 | 头类型 `default_type_id` 指向 `PO_GOODS` |
| 编号 | 创建时按 `document_type.number_sequence_id` 取号；前缀 `PO-`，日期段 `%Y%m%d`，序号 6 位；取号失败不回退（允许跳号） |
| 不可变性 | `order_no` 生成后不可改；`document_type_id` 离开草稿不可改（T-D20） |
| 方向 | 单据类型不得编码 `purchase / internal` 载体方向（T-D13a）；内外由 sourcing 派生，退货只由 `document_category='return'` 表达 |
| 审批策略 | 单据类型是**审批策略的选择维度**；是否审批由策略条件（对象字段）决定，见 §6 |

### 5.1 采购业务类型矩阵（行级，与 SO 的 `line_type` 同构）

| 业务类型 | 语义 | 行类型种子 | 与 SO 的对应 | 关键差异 |
|---|---|---|---|---|
| `standard` | 标准物料（外购件 / 原辅料），入库 | `PO_GOODS` | 实物行 | 无额外字段 |
| `subcontract` | 委外加工：我方提供原材料，供应商加工后回货 | `PO_SUBCONTRACT` | 无（SO 侧外协走 `work_order`） | 需组件发料清单 + 加工费计价口径 |
| `asset` | 资产采购，资本化进固定资产 | `PO_ASSET` | 无 | 需资产类别 + 资本化标记 |
| `service` | 服务采购，按验收结算 | `PO_SERVICE` | 服务行（同构） | 与 SO 一致：服务起止日 + 验收驱动 |
| `expense` | 费用采购，不建库存直接费用化 | `PO_EXPENSE` | 无 | 收货即费用，走成本中心 / 费用科目 |

**为什么放行级**：SAP 的行项目类别（item category：标准 / L 委外 / A 资产 / D 服务 / 非库存）就是行级，一张 PO 可混合；Oracle 用 `PO_LINE_TYPES`（Goods / Services）加上分配行的 `Expense Destination`（Inventory / Expense / Asset）。把业务类型放头级，会让「物料 + 服务同单」无法表达，也会让取号体系被迫按业务类型拆碎。头级 `document_type` 只负责编号体系与默认值，**不得编码行级差异**。

### 5.2 各类型的追加行字段与流程差异

| 类型 | 追加行字段（实施时并入 §4 行字段表） | 流程差异 | 下游 |
|---|---|---|---|
| `standard` | 无 | 正常收货入库 | `receipt_line` → 库存 |
| `subcontract` | `subcontract_fee_basis`（`per_unit` / `per_batch`）、`component_issue_required`（布尔） | 下单后需发料给供应商；收货时冲减供应商处组件 | 组件发料走 `subcontract_components`（另立 spec）/ 与 `work_order` 联动 |
| `asset` | `asset_category_code`、`capitalization_flag`、`capitalization_date` | 收货即转固 | `receipt_line` → 资产卡片（FA 波次） |
| `service` | `service_acceptance_required`（默认 true） | 验收单驱动付款 | 复用 `receipt`（`source_doc_type='service_entry'` 前先复用） |
| `expense` | `expense_account_code`、`cost_center_id` | 收货即费用，不入库存 | `receipt` → 总账 |

**M3 范围**：只落 `line_type` 枚举与字段位；委外组件发料、资产转固、服务验收单**只留挂载位**，未接线时字段只读或隐藏，守卫拒绝非法组合。三条流程闭环放 M4 / M5。

### 5.3 委外是否算「一种类型」：结论

**是，但是行级类型，不是独立单据对象。** 头部产品一致：

- SAP：item category `L` + BOM 展开 + 组件发料（541），仍在同一张 PO；
- Oracle：outside processing 通过 line type + WIP 关联，仍是同一张 PO；
- 因此不新建 `subcontract_order` 对象，只加 `line_type='subcontract'` + 组件发料清单（后续波次）。新建独立单据会把「同一供应商同一次下单」拆成两张单，收货与发票对账立刻分裂。

### 5.4 BOM / 超级 BOM 相关采购

#### 5.4.1 仓库现有事实

| 对象 | 文件名 / 表 | 关键口径 |
|---|---|---|
| BOM 头 | `item_structure` / `item_structures` | 业务键 `(item_id, usage, alternative_no, revision)`；`usage ∈ production / engineering / sales / costing`，**一期只有 `production` 参与展开**；同一 `(item_id, usage, alternative_no)` 任一日期只允许一个 `status='active'` 版本 |
| BOM 行 | `item_structure_line` / `item_structure_lines` | `parent_object: item_structure`，承载组件、用量、可选性 |
| 选配 | `configuration / configuration_component / configuration_value` + `config_rule / config_rule_term` | 销售侧配置求解体系，与 BOM 结构分开 |
| 超级 BOM | **没有该对象** | 「超级 BOM」是多层 BOM：组件 item 再挂自己的 `item_structure`，靠递归表达，不另建结构表 |

#### 5.4.2 采购侧的四种 BOM 场景与落法

| 场景 | 语义 | 落法 | M3 |
|---|---|---|---|
| 按组件采购（BOM 展开下单） | 工程 / 生产 BOM 展开成采购件，按 make/buy 过滤 | 展开在**需求侧**完成（`requisition_line` 展开为多条需求行）；每条 PO 行挂 `source_structure_id / source_structure_line_id` 追溯 | 不展开，只留追溯字段 |
| 成套采购（整包） | 供应商按整套报价，收货按套 | 父行 `pricing_mode='bundle_price'`；子行 `parent_line_id` + `component_no`，子行单价可为 0 或组件价 | 结构留位，UI 后置 |
| 委外加工 | 我方供料，供应商加工回货 | `line_type='subcontract'` + 行 `component_issue_required` + 组件发料清单（另立 spec） | 只落行类型与字段位 |
| 多层 / 超级 BOM | 多层递归、含虚拟件（phantom） | 展开引擎按 `max_level` + `usage='production'` + make/buy 过滤；虚拟件穿透不建行 | 后续波次 |

#### 5.4.3 三条硬口径

1. **PO 存结果，不存结构**。PO 行只保留追溯锚点 `source_structure_id / source_structure_line_id`，绝不复制 BOM 行；否则 BOM 改版后订单数据悄悄漂移，且收货对不上组件。
2. **展开必须在需求侧**。`requisition_line` 展开成多条需求行后，sourcing 才能按组件分别找供应商；PO 只是执行结果。若在 PO 上展开，就绕过了寻源与比价。
3. **委外组件发料是独立一层**。`subcontract_component`（`id, po_line_id, structure_line_id, item_id, qty_required, qty_issued, issue_status`）挂 PO 行，不挂 BOM 结构；它管理的是「我方发出的物权」，与 BOM 的「理论用量」不是一回事。
4. **委外模型与 Oracle 有差异，是选型而非遗漏**。Oracle OSP 的 PO 行是「外协工序服务」，组件发到 WIP；我们没有 WIP 与工艺路线，故 M3 走 SAP 式整单委外，等 `work_order` 落地再评估切换，迁移点见 §4.4.1。

#### 5.4.4 需并入 §4 字段表的追加项（BOM / 成套相关）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pricing_mode` | string(30) | 是 | 与 SO 同 4 值：`standalone / bundle_price / component_price / base_plus_option`；默认 `standalone` |
| `parent_line_id` | integer | 否 | 成套 / 组件父子行；只允许同单内、且父行 `pricing_mode='bundle_price'` |
| `component_no` | string(20) | 否 | 成套内组件序号，与 SO 同名同义 |
| `configuration_id` | integer | 否 | **只读追溯**：需求 / 销售订单已确定的配置；PO 不触发选配求解 |
| `source_structure_id` | integer | 否 | 来源 BOM 头（`item_structure.id`） |
| `source_structure_line_id` | integer | 否 | 来源 BOM 行（`item_structure_line.id`）；有值时必须与 `item_id / uom_id` 一致 |
| `component_issue_required` | boolean | 是 | 仅 `line_type='subcontract'` 可为 true；默认 false |

### 5.5 对 §2.1 D7 的修正

原 D7 写「PO 不设 `configuration_id / parent_line_id / pricing_mode / component_no`」，过于一刀切。修正为：

| 字段 | 是否设 | 理由 |
|---|---|---|
| `pricing_mode` | **设** | 成套采购（整包价）在采购侧真实存在，且与 SO 同一枚举 |
| `parent_line_id` / `component_no` | **设** | 成套的父子行结构，复用 SO 口径 |
| `configuration_id` | **设，但只读追溯** | 配置由需求 / 销售订单确定，采购只引用，不求解 |
| `reference_line_id` | 不设 | 那是销售侧退货引用，采购侧对应 `demand_allocation.reversed_at` 与退货单 |

---

## 6. 审批：头部产品对标与平台口径

### 6.1 头部产品审批矩阵

| 产品 | 审批触发载体 | 条件维度 | 状态模型 |
|---|---|---|---|
| SAP MM | Release strategy（PO 头级、PR 行级） | 分类特性（class + characteristics）：单据类型、金额、供应商、工厂等；无 release 则单据被冻结，不可打印 / 发送 | 未释放 → 已释放；逐级 release code |
| Oracle Fusion Procurement | 审批规则引擎 | 规则 = 条件 + 动作；条件含申请金额、功能币种、单据类型等 | 审批动作单独记录；PO 路由给审批人 |
| Dynamics 365 SCM | Change management（可按供应商开关） | 审批工作流；金额 / 供应商 / 单据类型等条件 | **审批状态与单据状态分离**：Draft → In review → Approved → Finalized 等六态 |
| Coupa | 审批链 | 条件含科目、品类、物料、申请人等；供应商级可配置「发票一律送审」 | 审批链 / 层级 |
| 共性 | 单据类型是策略挂载点 | 金额、组织、品类、供应商是条件 | 审批状态独立于业务单据生命周期 |

结论：**「是否审批」不是 document type 的布尔值，而是「document type 选择策略 + 条件求值」的结果。** 只按单据类型写死审批，会导致同一类型下小额单据也被卡住，或大额单据漏审。

### 6.2 平台口径（v2 修正）：独立审批规则模型

v1 把审批条件塞进 `control_parameter_values`（org / document_type / line_type / item_group，再加金额区间），有两个根本问题：

1. **条件因子天然是「该对象的字段」**。不同对象的字段集不同，控制参数表用固定列枚举，永远加不完；Oracle 的条件就是「任意字段 + 操作符 + 值」。
2. **控制参数回答「开关 / 默认值」，审批规则回答「条件 → 审批链」**。混在一张表后，多级审批、会签、金额分段无处表达。

结论：**审批规则模型独立于控制参数，并完全按对象生效**（与 Oracle approval rule 的「条件组 + 条件 + 动作」、SAP release strategy 的「特性 → 分组 → 策略」同构）。

#### 6.2.1 三张表（平台级，v177）

| 表 | 关键字段 | 作用 |
|---|---|---|
| `approval_policies` | `id, code, name, scope_bo, trigger_action, priority, effective_from, effective_to, status` | 策略头。`scope_bo` 决定适用对象；`trigger_action ∈ submit / confirm / release`；`priority` 越大越优先 |
| `approval_policy_conditions` | `id, policy_id, group_no, logic, field_id, operator, value_text, value_number, value_json` | 条件因子。`field_id` 引用**该对象**在 registry 中的字段 id，运行时从记录行取值；`operator ∈ = / in / between / >= / <= / is_null` |
| `approval_policy_steps` | `id, policy_id, step_no, approver_type, approver_ref, min_amount, max_amount, approve_mode, sla_hours` | 审批链。`approver_type ∈ role / user / org_head / superior`；`approve_mode ∈ any / all`（会签） |

#### 6.2.2 求值口径

| # | 口径 |
|---|---|
| R1 | 只有 `scope_bo` 等于当前对象的策略参与求值。**不同对象各用各的字段**，「按单据类型共享一套条件」不成立 |
| R2 | 同一策略内多条件 = AND；`group_no` 预留 OR 分组，M3 只做单层 AND |
| R3 | 多策略命中时取 `priority` 最大者；同优先级取 `effective_from` 最新 |
| R4 | **无命中策略 = 免审批**（`approval_status='not_required'`），提交后可直接确认 |
| R5 | `min_amount / max_amount` 挂在**步骤**上（同策略内按金额分段给不同审批人），不是挂在策略条件上 |
| R6 | 解析器 `DocumentApprovalResolver.resolve(object_type, record_id)`：读记录 → 求值 → 输出 `{required, policy_code, steps}`；PO / requisition / service_request / 未来 SO 共用 |
| R7 | 审批任务沿用 `ApprovalTaskService`：`tasks.type='approval'`、`doc_ref=<record_id>`、`app_id` 按域 |
| R8 | `approval_status` 为只读缓存，事实源是 `tasks`；驳回回 `draft`，单据状态机不受影响 |
| R9 | 策略变更不回溯已提交单据：提交时把命中的策略与步骤**快照**进 `tasks.inputs.policy_snapshot` |

#### 6.2.3 控制参数的边界（收窄）

| 项 | 口径 |
|---|---|
| 保留 | `control_parameter_defs / values` 只承载**开关与默认值**，例如组织级 `approval_enabled`（紧急旁路，默认 true） |
| 撤回 | **撤回 v1 的 `amount_min / amount_max` 列方案**。金额是审批条件，不是控制参数 |
| 兼容 | 旧 `demand_approval_required / demand_approval_policy` 标 `deprecated`，M3 期间继续生效；迁移到新模型列为 L-PO-2（M3 之后，须保证 requisition 在途单据不受影响） |
| 迁移 | v177 = 建上述三表 + 种子（PO 默认无策略 = 免审批） |

M3 实现范围：4 个 operator（`= / in / between / >=`）、单层 AND、两级 steps、三类审批人来源。更复杂的规则（OR 分组、动态审批人、代理审批）留后续波次，表结构已能承载。

### 6.3 PO 审批状态机

| 规则 id | 名称 | from | to | 触发 |
|---|---|---|---|---|
| `submit_purchase_order` | 提交 | `draft` | `submitted` | 提交时解析审批策略：免审批 → `approval_status=not_required`；需审批 → 建任务、`approval_status=pending` |
| `approve_purchase_order` | 审批通过 | `submitted` | `confirmed` | 审批任务动作 `purchase_order.approve` 调用；`approval_status=approved`；冻结价格 / 汇率 / 税率 |
| `reject_purchase_order` | 审批驳回 | `submitted` | `draft` | 审批任务动作 `purchase_order.reject` 调用；`approval_status=rejected`，修改后可重提 |
| `confirm_purchase_order` | 确认 | `submitted` | `confirmed` | 仅当 `approval_status ∈ {not_required, approved}` 时允许；免审批路径的人工确认 |
| `close_purchase_order` | 关闭 | `confirmed` | `closed` | 关闭后只读；未收数量不再执行 |
| `cancel_purchase_order` | 取消 | `draft, submitted, confirmed` | `cancelled` | 不回滚已收货 / 已开票事实 |

> 与 SO 的差异：SO 没有 `approve_purchase_order` / `reject_purchase_order`。这是**审批策略驱动**的差异，不是骨架差异；`approval_status` 与 SO 的 `status` 正交，未来 SO 若接入审批可复用同一套。

### 6.4 审批任务字段

| 项 | 值 |
|---|---|
| `type` | `approval` |
| `doc_ref` | PO 头 id（字符串） |
| `app_id` | `procurement` |
| `executor_type` | `human` |
| `assign_policy` | `claim` |
| `inputs` | `{id, purchase_order_id}` |
| `executor_config.decision_actions` | `{approve: 'purchase_order.approve', reject: 'purchase_order.reject'}` |
| 标题 | `采购订单审批 #<order_no>` |

---

## 7. 供应商字段口径

| 字段 | 规则 |
|---|---|
| `supplier_party_id` | 必填，指向 `party.id`；草稿允许任意启用 party，**提交 / 确认时**必须有 `party_relation(role='vendor', internal_mark='外部')` 的有效行 |
| `supplier_account_id` | 可空，指向 `vendor_account.id`；用于带出币种 / 付款条件 / Incoterm；空则按 party 的有效 vendor relation 取默认档案 |
| 内部来源不落 PO | 若 sourcing 判定为内部（`source_org_id`），不得建 PO；跨法人走 ISO（M4），同法人异库存组织走 `transfer_order`（M4） |
| M2 未接线 | 允许人工填 `supplier_party_id` + `supplier_account_id`；`sourcing_rule_line_id` 留空。M2 接线后仅在**草稿态**回填，已提交单据不回写 |

> 不建 `supplier` 表（T-D4）；供应商准入 / 绩效 / 结算条件随 `vendor_account` 的后续波次，不在 M3。

---

## 8. requisition → purchase_order 字段映射

### 8.1 头级

| requisition 字段 | PO 字段 | 处理 |
|---|---|---|
| `requisition_no` | — | 不落 PO；关系由分配表 + （M6）边表表达 |
| `document_type_id` | `document_type_id` | **不复制**；PO 选自己的类型 |
| `requester_org_id` | — | 不落；需求侧事实 |
| `deliver_to_org_id` | `org_id`（默认） | 默认取送达组织所属法人；集中采购可人工改 |
| `deliver_to_location_id` | `deliver_to_location_id` | 直接带过 |
| `need_date` | `requested_date` | 直接带过 |
| `priority` | — | 不落；留在需求行，经分配表追溯 |
| `requested_by_party_id` | — | 不落 |
| `description` | `description` | 可带过（合并采购时人工整理） |
| `status` | `status` | 不复制；PO 从 `draft` 起 |

### 8.2 行级

| requisition_line 字段 | PO 行字段 | 处理 |
|---|---|---|
| `line_no` | — | 不落；分配表记录来源行 |
| `line_type`（goods / service） | `line_type_id` | 按类型字典 code 映射 `PO_GOODS` / `PO_SERVICE` |
| `item_id` | `item_id` | 直接带过 |
| `description` | `description` | 直接带过 |
| `qty` | `qty` + 分配数量 | 可部分转单；未转数量留在需求行 |
| `uom_id` | `uom_id` | 直接带过 |
| `need_date` | `requested_date` | 直接带过 |
| `deliver_to_location_id` | `deliver_to_location_id` | 直接带过 |
| `requested_source_org_id` | — | 不落；sourcing 输入 |
| `resolved_source_org_id` | — | 不落；sourcing 结果用于决定载体，不写 PO |
| `fulfilled_qty`（派生） | — | 不落；由分配 / 收货派生 |

### 8.3 合并采购规则

- 一张 PO 行可服务 **N 条需求行**，前提：`item_id + uom_id + unit_price + 交期窗口` 兼容。
- **禁止**在 PO 行放 `requisition_line_id` / `project_task_id` 单一引用（T-D3）。
- 每条「需求行 → PO 计划行」写一行 `demand_allocation`，数量为分配量；`sum(分配量) <= 计划行 promised_qty`，且 `<= PO 行 qty`。
- 同一需求行可分裂到多张 PO / 其他载体（ISO / 调拨 / 工单），分配表统一归集（T-D14）。

---

## 9. `demand_allocation`（统一分配表）

### 9.1 对标结论：头部产品没有同名对象

| 产品 | 需求 → 执行的关系载体 | 数量分配 | 计划层 | 可写性 / 局限 |
|---|---|---|---|---|
| SAP MM | `EKPO` 上的 `BANFN / BNFPO`（PO 行引用 PR 行） | 同一 PO 单可合并多张 PR（须同供应商 / 采购组织 / 币种），但 **PO 行通常只回指一条 PR 行**；同物料合并后若只留一行，另一条 PR 的追溯会丢失 | `EKET` 计划行（`EBELN / EBELP / ETENR`，`EINDT` 交期，`MENGE` 数量） | 单值引用，无 N:M 分配行 |
| Oracle Fusion Procurement | `PO_DISTRIBUTIONS_ALL`：分配行挂 `PoLineId` + `ReqDistributionId`；`REQ_LINE_REFERENCE_NUM / REQ_HEADER_REFERENCE_NUM` 仅纸面申请参考号，不是外键 | 分配行承载数量 / 金额 / 费用科目 | `PO_LINE_LOCATIONS_ALL`：schedule / location / qty / need-by / requested ship date，支持 split | 可写；但语义是「采购分配 + 费用分配」，不是需求 pegging |
| Oracle SCM Planning | Pegging（supply ↔ demand 数量挂钩） | 有数量关系 | 计划层 | 计划期只读，不是事务单据 |
| PeopleSoft | Pegging Workbench：MSR / 内部调拨可被 peg | 有数量关系 | 调拨 / 需求行 | 计划 / 执行交叉 |
| Coupa | PO 行 ↔ 申请行；ASN / receipt 行；invoice line allocation | 部分收货、部分开票可按行分配 | Buyer-generated delivery schedules（`Schedules Planned` 属性，供应商承诺量可小于订单行量） | 可写；allocation 主要服务发票匹配 |

结论：**没有一个头部产品提供「需求行 ↔ 执行行」的通用 N:M 数量分配对象**。SAP 靠单值引用，Oracle 靠 PO distribution + planning pegging，Coupa 靠发票行 allocation。我们的 `demand_allocation` 是三类对象的综合：

1. **结构骨架取 Oracle `PO_DISTRIBUTIONS_ALL`**：一行分配同时挂「执行行 / 执行计划行」与「需求行」，带数量、金额、归属。
2. **语义取 Oracle / PeopleSoft pegging**：回答「这 10 件到货是给哪条需求」，支持多源、分批、红冲。
3. **可写性取 Coupa allocation**：由业务 / 服务层维护，不是计划引擎的只读缓存。

命名保留 T-D14 的 `demand_allocation`；别名：pegging / distribution / allocation。

### 9.2 结构

表：`demand_allocations`；`semantics.category: business_document`（分配事实，不是主数据）；`aspects: [audit_aspect]`。

| # | 字段 id | 中文 | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | 主键 |
| 2 | `demand_bo` | 需求对象 | string(40) | 是 | `requisition / service_request / sales_order_schedule / project_task` |
| 3 | `demand_id` | 需求单 id | integer | 是 | 头级 id |
| 4 | `demand_line_id` | 需求行 id | integer | 是 | 行级 id（`requisition_lines.id` 等） |
| 5 | `demand_line_no` | 需求行号 | string(10) | 否 | **只读缓存**，便于列表展示 |
| 6 | `demand_need_date` | 需求日期 | date | 否 | **只读缓存**，来自需求行，用于排序 / 齐套检查 |
| 7 | `project_id` | 项目 | integer | 否 | 需求归属项目；合并采购时逐分配行落项目 |
| 8 | `project_task_id` | 项目任务 | integer | 否 | 需求归属任务；**只允许落在分配行，不允许落在 PO 行**（T-D3） |
| 9 | `target_bo` | 执行对象 | string(40) | 是 | `purchase_order / receipt / transfer_order / work_order / sales_order` |
| 10 | `target_id` | 执行单 id | integer | 是 | 头级 id |
| 11 | `target_line_id` | 执行行 id | integer | 是 | 行级 id |
| 12 | `target_schedule_id` | 执行计划行 id | integer | 否 | PO 场景指向 `purchase_order_schedules.id`；无计划层的载体为空 |
| 13 | `qty` | 分配数量 | number(6) | 是 | `> 0` |
| 14 | `uom_id` | 单位 | integer | 否 | 空 = 取需求行单位 |
| 15 | `allocated_amount` | 分配金额 | number(2) | 否 | **只读缓存列（实现修正）**：口径 `qty × 执行行单价`，币种取执行单；`target_bo` 多态无法用 YAML 公式跨表派生，故落 nullable 列由服务层计算回写，界面不可编辑 |
| 16 | `status` | 状态 | string(20) | 是 | 默认 `active`；`active / reversed` |
| 17 | `reversed_at` | 冲销时间 | datetime | 否 | 红冲 / 取消时写 |
| 18 | `created_at` | 创建时间 | datetime | 否 | — |
| 19 | `updated_at` | 更新时间 | datetime | 否 | — |

索引：

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uidx_demand_alloc_target` | `demand_bo, demand_line_id, target_bo, target_line_id, target_schedule_id`（`target_schedule_id` 无计划层时按 0） | 是（同需求行对同一执行计划行只有一条分配） |
| `idx_demand_alloc_target_line` | `target_bo, target_line_id` | 否 |
| `idx_demand_alloc_target_schedule` | `target_bo, target_schedule_id` | 否 |
| `idx_demand_alloc_demand` | `demand_bo, demand_id` | 否 |
| `idx_demand_alloc_project` | `project_id, project_task_id` | 否 |
| `idx_demand_alloc_cost` | `cost_center_id, expense_account_code` | 否 |

### 9.2.1 成本归属维度：distribution 就是「demand 的来源 + 记到谁头上」

Oracle 的 `PO_DISTRIBUTIONS_ALL.ChargeAccountId` 是**完整会计组合**（公司段 + 成本中心 + 科目 + 项目），也就是说 Oracle 的 distribution 一行同时回答两件事：

1. 这笔到货冲的是哪条需求（`ReqDistributionId`）→ pegging；
2. 这笔支出记到哪个成本对象（`ChargeAccountId`）→ 成本归属。

我们合并成一张 `demand_allocation`，因此成本维度**必须长在分配行**：同一 PO 行可能同时服务「研发项目」和「生产费用」，PO 行放单值成本中心必然错账。

追加字段（M3 建列，UI 后置只读）：

| # | 字段 id | 中文 | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 7a | `cost_center_id` | 成本中心 | integer | 否 | 从 `requisition_line.cost_center_id` 带过；同一分配行不允许改写成本归属 |
| 7b | `expense_account_code` | 费用科目 | string(32) | 否 | 费用 / 服务 / 资产类采购使用 |
| 7c | `asset_category_code` | 资产类别 | string(20) | 否 | 资产采购时与 §5.2 行字段对齐，收货后转固依据 |
| 7d | `charge_basis` | 记账口径 | string(20) | 是 | `inventory / project / expense / asset`；决定下游记账走向，默认 `inventory` |

**前置小改**：`requisition_line` 需补 `cost_center_id`（M1 已有项目 / 任务，成本中心缺失），否则分配行无处继承；这条列为 M3 前置，不改则成本中心在转单时永久丢链。

M3 只建列 + 继承 + 守卫校验，不做凭证与科目映射；费用化 / 资本化的记账闭环随财务波次。

### 9.3 与对标对象的字段映射

| 对标 | 我们的字段 | 说明 |
|---|---|---|
| Oracle `ReqDistributionId` | `demand_line_id` | 需求侧分配锚 |
| Oracle `PoLineId` | `target_line_id` | 执行行 |
| Oracle schedule / location | `target_schedule_id` | 执行计划行（到货计划） |
| Oracle distribution amount | `allocated_amount` | 只读派生，不手工改 |
| Oracle 费用科目 / 项目（`ChargeAccountId`） | `project_id` / `project_task_id` / `cost_center_id` / `expense_account_code` / `asset_category_code` + `charge_basis` | 成本归属已在本 spec 落地（§9.2.1）；`charge_basis` 对应 `Expense Destination` 的 Inventory / Expense / Asset |
| SAP `BANFN / BNFPO` | `demand_bo / demand_id / demand_line_id` | 把单值引用升级为可拆分的分配行 |
| SAP `EKET-ETENR` | `target_schedule_id` | 对应到货计划行 |
| Coupa invoice line allocation | `status` + `target_bo='receipt'` | 收货 / 发票阶段复用同一分配表 |

### 9.4 边界与不变量

- `demand_allocation` 是**可人工调整的业务分配事实**；`doc_flow_edges` 是 M6 由分配 / 收货派生的**只读消耗账**。M3 不写边；M6 对账要求「分配汇总 = 边表汇总」零差异。
- 守卫不变量：
  - `qty > 0`；`status='active'` 的分配合计不得超过执行行 / 计划行的数量。
  - 同一需求行的 `active` 分配合计不得超过需求行 `qty`（跨载体合计）。
  - 执行行或计划行 `cancelled` 时，其分配必须置 `reversed` 并写 `reversed_at`（服务层联动）。
  - `project_task_id` 非空时，`project_id` 必须与任务所属项目一致。
- 分配行不允许改 `demand_bo / demand_line_id / target_bo / target_line_id`（只能作废重开），避免追溯链断裂。
- `charge_basis` 与成本字段联动：`project` → `project_id` 必填；`expense` → `expense_account_code` 必填；`asset` → `asset_category_code` 必填；`inventory` → 三者可空。
- `cost_center_id` 必须与需求行一致；分配环节不允许改写成本归属（要改只能回需求行改后重新分配）。

---

## 10. `purchase_order_schedule`（到货计划行）

### 10.1 定位

PO 的第三层，挂在 PO 行上，回答「这批货什么时候到、到多少」。它是收货行的**唯一挂载点**，与销售侧 `sales_order_schedule`（交货计划行）同构。采购侧叫「到货计划行」，不叫「收货单」；收货单是实际事件，计划行是承诺。

### 10.2 字段表

表：`purchase_order_schedules`；`parent_object: purchase_order`；`hierarchy: {enabled: true, parent_field: order_id}`；`aspects: [audit_aspect]`；`display_name_field: schedule_no`。

| # | 字段 id | 中文 | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 1 | `id` | ID | integer | 是 | 主键 |
| 2 | `order_id` | 所属订单 | integer | 是 | 由 `line_id` 反查填充；一致性由守卫保证 |
| 3 | `line_id` | 订单行 | integer | 是 | `purchase_order_lines.id`，真外键 |
| 4 | `schedule_no` | 序号 | integer | 是 | 行内唯一，从 1 递增；作废后仍占号 |
| 5 | `schedule_kind` | 计划类型 | string(20) | 是 | `delivery`（到货）/ `service`（服务）；默认 `delivery` |
| 6 | `deliver_to_location_id` | 收货地点 | integer | 否 | 空 = 取行 / 头；`delivery` 建议必填 |
| 7 | `promised_date` | 承诺到货日 | date | 是 | 供应商承诺日；可与「需求日」不同 |
| 8 | `promised_qty` | 承诺数量 | number(6) | 是 | `> 0`；单位 = 订单行 `uom_id` |
| 9 | `status` | 计划状态 | string(20) | 是 | `planned / confirmed / completed / cancelled`，默认 `planned` |
| 10 | `received_qty` | 已收数量 | number(6) | 否 | **只读缓存（净收口径）**：`sum(posted 标准单 qty_received − qty_rejected) − sum(posted 红字单净量)`，≈ Oracle `QUANTITY_ACCEPTED`；仅收货服务过账 / 红冲回写；不回填 0（区分「未收货」与「零收货」）；R-RC-16 对账以 `receipt_line` 流水为准 |
| 11 | `rejected_qty` | 累计拒收量 | number(6) | 否 | **只读缓存**：`sum(posted qty_rejected)`；与 `received_qty` 独立累加，不得混算（R-RC-18） |
| 12 | `completion_source` | 完成来源 | string(20) | 否 | `manual / receipt / short_close`；仅 `status='completed'` 时有值，红冲只回退 `receipt` 来源 |
| 13 | `completion_prev_status` | 完成前状态 | string(20) | 否 | `planned / confirmed`；红冲时据此回退（避免把原 `planned` 错写成 `confirmed`） |
| 14 | `created_at` | 创建时间 | datetime | 否 | — |
| 15 | `updated_at` | 更新时间 | datetime | 否 | — |

### 10.3 索引与关系

| 索引 | 字段 | 唯一 |
|---|---|---|
| `uidx_po_schedule_line_kind_no` | `line_id, schedule_kind, schedule_no` | 是 |
| `idx_po_schedule_order` | `order_id` | 否 |
| `idx_po_schedule_line` | `line_id` | 否 |
| `idx_po_schedule_promised_date` | `promised_date` | 否 |
| `idx_po_schedule_location` | `deliver_to_location_id` | 否 |

关系：`purchase_order_schedule_to_order`、`purchase_order_schedule_to_line`、`purchase_order_schedule_to_location`。

### 10.4 状态机与不变量

| 规则 id | 名称 | from | to | 说明 |
|---|---|---|---|---|
| `confirm_po_schedule` | 确认到货计划 | `planned` | `confirmed` | 供应商承诺后确认 |
| `complete_po_schedule` | 完成到货 | `confirmed` | `completed` | 累计净收 ≥ 承诺量时由收货服务自动置位，写 `completion_source='receipt'` + `completion_prev_status` |
| `close_po_schedule` | 短收结案 | `planned, confirmed` | `completed` | `completion_source='short_close'`，记 `closed_short_qty = promised_qty − received_qty`；结案后禁止再收货 |
| `cancel_po_schedule` | 作废 | `planned, confirmed` | `cancelled` | 已有 `posted` 收货时禁止作废；`completed` 不可作废 |

不变量：

- R-SCH-0：`order_id` 必须等于 `line_id` 所属订单；`schedule_no` 在同 `line_id + schedule_kind` 内唯一。
- R-SCH-1：`promised_qty > 0`；`delivery` 行必填；`service` 行可用。
- R-SCH-2：同一 PO 行的计划行 `promised_qty` 合计不得超过行 `qty`（允许后续追加计划行，不允许超计划）。
- R-SCH-3：收货累计量 > `promised_qty` 时拒绝（容差默认 0，未来由控制参数 `receipt_over_tolerance_percent` 放开）。
- R-SCH-4：计划行作废后不可重开；新增计划行顺延 `schedule_no`。
- R-SCH-5：`completion_source='short_close'` 的计划行禁止再收货（`RC_SCHEDULE_CLOSED`）；`completed` 计划行不可回退，只能由红字收货单按 `completion_prev_status` 回退 `completion_source='receipt'` 的完成。
- R-SCH-6：`received_qty`（净收）与 `rejected_qty`（拒收）独立累加；两者以 `receipt_line` 流水为准，计划行列只作缓存（R-RC-16 对账）。

### 10.5 与销售侧镜像

| 销售侧 | 采购侧 | 说明 |
|---|---|---|
| `sales_order` | `purchase_order` | 头 |
| `sales_order_line` | `purchase_order_line` | 行 |
| `sales_order_schedule`（`delivery`） | `purchase_order_schedule`（`delivery`） | 计划行；SO 是发货承诺，PO 是到货承诺 |
| `sales_order_schedule`（`billing` / `service`） | `purchase_order_schedule`（`service`） | 开票计划采购侧由发票 spec 处理；服务计划保留 |
| `shipment`（交货单头） | `receipt`（收货单头） | 出库 vs 入库；均带 `source_doc_type / source_doc_id` |
| `shipment_line.schedule_id` | `receipt_line.schedule_id` | **唯一挂载点**，都指向计划行 |
| `shipment_line.order_line_id` / `item_id` / `uom_id` | `receipt_line.order_line_id` / `item_id` / `uom_id` | 冗余列，由计划行反查；不一致拒绝 |
| `shipment.actual_arrival_date` | `receipt.actual_arrival_date` | 实际到达日 |
| `shipment` 状态 `release / stage / ship / receive / close / cancel` | `receipt` 状态 `draft / posted / reversed / cancelled` | 方向相反；采购收货以「过账」为核心事件 |

> 这一组镜像把「计划层」补进采购链，避免收货行直接挂 PO 行后无法表达分批到货；同时让销售 / 采购两侧的 UI、守卫、追溯逻辑可以复用同一套推导。

---

## 11. 收货 / 发票接口契约（T-D12）；收货字段细化见 `spec-receipt-object-model-2026-11-01.md`，发票后置

| 约定 | 内容 |
|---|---|
| 复用对象 | 收货单、发票各**只建一个对象**，按 `source_doc_type` 区分来源，不为 PO / ISO / 退货分别建表 |
| 收货单 `source_doc_type` | `purchase_order / transfer_order / work_order / sales_return / intercompany` |
| 发票 `source_doc_type` | `purchase_order / receipt / intercompany / service_entry` |
| 收货头字段（最小集） | `receipt_no`、`source_doc_type`、`source_doc_id`、`supplier_party_id`、`org_id`、`deliver_to_location_id`、`receipt_date`、`actual_arrival_date`、`status`（`draft / posted / reversed / cancelled`） |
| 收货行字段（最小集） | `receipt_id`、`schedule_id`（指向 `purchase_order_schedules.id`，必填）、`order_line_id`（冗余）、`item_id`（冗余）、`uom_id`（冗余）、`qty_received`、`qty_rejected`、`lot_no`、`serial_no`、`status` |
| 收货挂载 | 收货行**只挂计划行**，不直接挂 PO 行；一张收货单可含多条计划行；同一计划行可分多次收货 |
| 部分收货 | 收货行数量回写 `demand_allocation`（`target_bo='receipt'`, `target_schedule_id=schedule_id`），按分配比例 / 人工拆分到需求行，实现需求级追溯 |
| 超收 | 守卫拦截：累计收货 > 计划行 `promised_qty`（容差另配，默认 0） |
| 三单匹配 | PO / 收货 / 发票按计划行 + 行匹配；容差放 `control_parameter_defs`（`invoice_match_tolerance_*`），不硬编码 |
| 退货 / 红冲 | 方向由单据类型 `document_category='return'` 决定；红冲在 M6 由 `doc_flow` 的 `quantity_sign='red'` 处理 |
| 到货计划 vs ASN | 计划行是**买方计划 / 供应商承诺**；ASN（供应商预先发货通知）是外部事件，M3 不建，列为未决 Q1 |

本 spec 只要求：M3 第一阶段落 PO + 计划行后，收货 / 发票 spec 必须遵守以上契约，不得另起字段名。

> 收货 spec §18 提出 7 项对本 spec 的修订，**已于 2026-11-01 评审通过并回写**：R-PO-9 分段计数（§14.1）、`close_po_schedule` 与 `completion_source`（§10.4）、计划行新增 `rejected_qty` / `completion_source` / `completion_prev_status`（§10.2）、`schedule_id` 改为「PO 来源必填」、收货头字段扩展、分配拆分算法（收货 spec §6.1）。履约派生唯一写入方为 `PurchaseOrderFulfillmentService`（§3 字段 36/37）。

---

## 12. doc_flow 边契约（M6 使用，M3 不写）

| 边 | `source_bo` | `source_item` | `target_bo` | `target_item` | `rule_id` | `quantity` | `pool` |
|---|---|---|---|---|---|---|---|
| 需求 → PO | `requisition` | 需求行号 | `purchase_order` | PO 行号 | `req_to_po` | 分配数量 | `procurement` |
| PO → 收货 | `purchase_order` | PO 计划行号 | `receipt` | 收货行号 | `po_to_receipt` | 收货数量 | `procurement` |
| 收货 → 发票 | `receipt` | 收货行号 | `vendor_invoice` | 发票行号 | `receipt_to_invoice` | 开票数量 | `billing` |
| 红冲 | 同上 | 同上 | 同上 | 同上 | 同上 | 原数量 | 同上，`quantity_sign='red'`、`status='reversed'` |

约束：边由派生引擎写；业务对象上不得放可写多态外键；缓存列（`fulfillment_status`、`approval_status` 等）只读（T-D19）。

---

## 13. 页面、菜单、权限

| 项 | 内容 |
|---|---|
| 头列表列 | `order_no`、`document_type_id`、`order_date`、`supplier_party_id`、`purchase_org_id`、`org_id`、`currency_id`、`net_amount`、`status`、`approval_status`、`fulfillment_status` |
| 头表单分区 | 基本信息（`order_no / document_type_id / order_date / status`）；供应商与组织（`supplier_party_id / supplier_account_id / supplier_reference_no / purchase_org_id / org_id / division_code`）；交付与条款（`deliver_to_location_id / requested_date / confirmed_date / payment_term_id / incoterm_code / currency_id / exchange_rate / exchange_rate_type / exchange_rate_date`）；金额（4 个头折扣 / 附加字段 + `net / tax / gross`）；说明（`description`） |
| 详情子表 | `child_sections`：`purchase_order_line`（行）、`purchase_order_schedule`（到货计划）。**落库后回写（D-PO-23）**：`demand_allocation` 是多态分配表（`target_bo` + `target_id` 可指向任意载体，没有单一父字段），M3 不放进 `child_sections`，由服务 / API 维护；等 M6 派生只读视图就位后再做「需求分配」tab，不为单载体写前端特例 |
| 行列表列 | `line_no / line_type_id / item_id / supplier_item_code / description / qty / uom_id / unit_price / net_amount / tax_amount / gross_amount / requested_date / deliver_to_location_id / status / fulfillment_status` |
| 计划行列表列 | `schedule_no / line_id / schedule_kind / deliver_to_location_id / promised_date / promised_qty / received_qty / rejected_qty / status` |
| 行表单分区 | 基本信息（`line_no / line_type_id`）；物料（`item_id / supplier_item_code / description`）；数量与价格（`qty / uom_id / unit_price / net_amount`）；税（`tax_code_id / tax_rate_percent / tax_amount / gross_amount`）；交付（`requested_date / deliver_to_location_id`）；服务（`service_start_date / service_end_date`，仅服务行）；价格来源（`price_source`，只读 `price_trace`） |
| 菜单 | 顶层分组 `procurement`（无页面 / 无路径），子菜单 `purchase-order-management` → `/purchase-orders`；`skip_auto_menu: true` |
| 权限码 | 双段式：`purchase_order:purchase_order_create/read/update/delete/list`、`purchase_order_line:*`、`purchase_order_schedule:*`、`demand_allocation:*`；与 `v121` 同款写法 |

---

## 14. 实施步骤（decision-complete）

> 迁移序号：当前最大为 `v176__resource_domain_p2b.py`（2026-11-01 已落地），本批用 **`v177__purchase_order_object.py`**、**`v178__approval_rule_model.py`**、**`v179__purchase_pricing.py`**；若期间有新迁移先落地，按实际序号顺延。执行顺序 = v177 → v178 → v179（v177 的表是其余两步的前置）。
>
> 落库后追加 **`v181__purchase_order_menu_reconcile.py`**（幂等菜单对账）：v177 的「授权 + 菜单 + 孤儿清理」段是在首次执行**之后**才补进文件的，checksum 变化使框架拒绝重跑，DB 只剩 `show_in_sidebar=0` 的 `purchase_order-list` 等自动生成孤儿菜单，`/purchase-orders` 无动态路由。v181 只补这一段，不改表结构。

| 步 | 文件（新建 / 修改） | 内容 | 验证 |
|---|---|---|---|
| 1 | `meta/schemas/purchase_order.yaml`（新建） | §3 头字段（含 `approval_status`）、§2 统一骨架、状态机、索引、关系、`ui_view_config`（含 `child_sections`） | YAML 加载无报错；`metadata_validator` 通过 |
| 2 | `meta/schemas/purchase_order_line.yaml`（新建） | §4 行字段、行规则、索引、关系 | 同上 |
| 3 | `meta/schemas/purchase_order_schedule.yaml`（新建） | §10 计划行字段、状态机、索引、`received_qty` / `rejected_qty` / `completion_source` / `completion_prev_status` 只读缓存列、UI 配置 | 同上 |
| 4 | `meta/schemas/demand_allocation.yaml`（新建） | §9 字段、唯一索引、审计、UI 三态 | 同上 |
| 5 | `meta/migrations/v177__purchase_order_object.py`（新建） | 建四张表 + 索引；补 `requisition_line.cost_center_id`（§9.2.1 前置小改）；seed `type_definitions`（`PO_STD` / `PO_GOODS` / `PO_SUBCONTRACT` / `PO_ASSET` / `PO_SERVICE` / `PO_EXPENSE` / `PO_TEXT`）；seed `number_sequences`（`PO-`）；回填 `number_sequence_id` / `default_type_id`；permissions（双段式）；menus（`procurement` + `purchase-order-management`）；幂等；`verify()` 断言表 / 类型 / 序列 / 权限 / 菜单 | 迁移连跑两次，DB 终态一致 |
| 6 | `meta/migrations/v178__approval_rule_model.py`（新建） | 建 `approval_policies` / `approval_policy_conditions` / `approval_policy_steps` 三表 + 索引；seed 组织级 `approval_enabled` 控制参数；旧 `demand_approval_*` 标 deprecated；PO 默认无策略 = 免审批 | 迁移幂等；`DocumentApprovalResolver` 能按对象字段求值 |
| 6A | `meta/migrations/v179__purchase_pricing.py`（新建） | 建 `purchase_pricing_determinations`（`purchase_org_id / document_type_id / supplier_party_id / seq / rate_table_id / agreement_scope`）；`rate_tables` 加 `scope_bo`（默认 `sales_order`）；价格阶梯字段 `qty_from / qty_to / ship_to_location_id`；seed 控制参数 `price_break_cumulative`（显式配置，无隐式默认）；幂等 | 迁移连跑两次终态一致；销售取价零回归 |
| 6B | `meta/services/purchase_pricing_service.py`（新建） | 解析顺序：本地协议 > 全局协议 > 报价 > 价目表 > `last_po` > 标准成本 > 人工；价格阶梯同条件多档**取最低价**；写 `unit_price / price_source / price_trace` 与头 `price_list_id / pricing_procedure_id` | 取价用例全绿；`last_po` 为只读派生，不落表 |
| 7 | `meta/services/purchase_order_guard_service.py`（新建） | §15.1 不变量；金额汇总；供应商 vendor relation 校验；分配数量上限；确认冻结 | 单元测试全绿 |
| 8 | `meta/core/interceptors/purchase_order_guard_interceptor.py`（新建） | 拦截 `purchase_order` / `purchase_order_line` / `purchase_order_schedule` / `demand_allocation` 的 create / update / delete / status | 拦截器用例全绿 |
| 9 | `meta/server.py` L549-550 附近；`meta/core/app_builder.py` L291-292 附近（修改） | 注册 `PurchaseOrderGuardInterceptor()` | 启动后守卫生效 |
| 10 | `meta/services/document_approval_service.py`（新建） | `DocumentApprovalResolver.resolve(object_type, record_id)`：按 `scope_bo` 取策略 → 逐条求值 `approval_policy_conditions`（`field_id` 取值于记录）→ 命中后按 `approval_policy_steps` 生成链路；返回 `required / policy_code / steps / snapshot`；无命中 = 免审批 | 审批解析用例全绿 |
| 11 | `meta/services/approval_task_service.py`（新建） | 从 `DemandEntryService.create_approval_task` 抽通用建任务；PO / requisition / service_request 共用 | 同 M1 行为零回归 |
| 12 | `meta/services/document_approval_decision.py`（新建） | `purchase_order_approve_handler` / `purchase_order_reject_handler`；走 BO actions `purchase_order.approve / .reject`；落库复核 | 用例全绿 |
| 13 | BO Action 注册点（按 `demand_entry_decision.py` 同款位置，修改） | 挂 `purchase_order.approve / .reject` | 审批任务可执行 |
| 14 | `meta/tests/test_purchase_order_schema.py`（新建） | YAML 字段 / 切面 / 状态机 / 索引 / 关系断言 | `python d:\filework\test.py --single meta/tests/test_purchase_order_schema.py` |
| 15 | `meta/tests/test_purchase_order_guard.py`（新建） | §15.1 每条不变量一用例；合并采购分配上限；确认冻结；取消不可逆 | 同上 `--single` |
| 16 | `meta/tests/test_purchase_order_schedule.py`（新建） | 计划行序号 / 状态机 / 超计划拦截 / 与收货的挂载契约 | 同上 `--single` |
| 17 | `meta/tests/test_demand_allocation_schema.py`（新建） | 字段 / 唯一索引 / 多载体 `target_bo` 值域 / 项目任务归属 | 同上 `--single` |
| 18 | `meta/tests/test_document_approval.py`（新建） | 免审批 / 金额命中 / 单据类型命中 / 驳回回草稿 | 同上 `--single` |
| 19 | 回归 | SO 链路、requisition 链路、work_order 链路 | `python d:\filework\test.py --failed`；必要时 `--all` 后再 `--failed` 串行确认 |
| 20 | `meta/migrations/v181__purchase_order_menu_reconcile.py`（新建） | 幂等补 `procurement`（顶层分组，`menu_path=''`）+ `purchase-order-management`（`/purchase-orders`）+ `menu_permissions` + 授权 `admin`（`default` 集不存在则跳过）+ 清理 `purchase_order-list` 等自动生成孤儿 | 迁移 `verify OK`；`/purchase-orders` 路由可渲染 |
| 21 | `src/router/detailRouteGuard.js`（修改） | `SUPPORTED_OBJECT_TYPES` 补 `purchase_order`、`typeLabels` 补「采购订单」 | 手拼 `/detail/purchase_order/<id>` 不再 `reason=unsupported_object_type` |
| 22 | `meta/tests/test_purchase_pricing_service.py`（新建） | 协议阶梯（1-99 ¥10 / 100+ ¥9）、边界 100 件、本地未命中回落全局、多档覆盖报错、无来源落 manual | `python d:\filework\test.py --single meta/tests/test_purchase_pricing_service.py` |
| 23 | `meta/services/requisition_po_conversion.py`（新建）+ `meta/services/bo_action_registrations.py`（修改） | approved 申请 → 草稿 PO（头 + 行 + 分配，单事务）；行类型 `goods→PO_GOODS` / `service→PO_SERVICE`；剩余量 = 行 `qty` − active 分配合计，超量直接拒绝；注册 `purchase_order.create_from_requisition` | `--single meta/tests/test_requisition_po_conversion.py`；action 契约校验无告警 |

### 14.1 守卫不变量（R-PO-0 ~ R-PO-18）

| 编号 | 规则 |
|---|---|
| R-PO-0 | 创建时 `document_type_id` 必填；`scope_bo='purchase_order'` + `level='header'` |
| R-PO-1 | `order_no` 生成后不可改；取号失败不回退 |
| R-PO-2 | `document_type_id` / `currency_id` / `supplier_party_id` 离开草稿不可改 |
| R-PO-3 | 行 `qty > 0`；`goods` 行 `item_id` 与 `uom_id` 必填；`item_id` 为空时 `description` 必填 |
| R-PO-4 | 行 `line_type_id` 必须 `scope_bo='purchase_order'` + `level='line'`，且与头类型 `default_type_id` 同域 |
| R-PO-5 | 头 `net/tax/gross` 恒等于行汇总；任一行变更后服务层重算回写（界面不可编辑） |
| R-PO-6 | 非草稿禁删行；禁改 `order_no` / `document_type_id` / `currency_id` / `supplier_party_id` |
| R-PO-7 | 确认时冻结 `exchange_rate / exchange_rate_type / exchange_rate_date / tax_rate_percent / unit_price` |
| R-PO-8 | 提交 / 确认时 `supplier_party_id` 必须有有效 `party_relation(role='vendor', internal_mark='外部')`；`purchase_org_id` 必须有 purchasing 职能 |
| R-PO-9 | 分配分段计数（按 `target_bo`，两段不相加）：① `target_bo='purchase_order'`：`sum(active.qty) <= 计划行 promised_qty`、`<= 行 qty`、同需求行 `<= 需求行 qty`；② `target_bo='receipt'`：单条 `<=` 对应 PO 分配剩余量，同需求行在本计划行累计 `<=` 对应 PO 分配 `qty × (1 + receipt_over_tolerance_percent)`（与 R-SCH-3 共用容差） |
| R-PO-10 | 行 / 计划行 `cancelled` ⇒ 其 `active` 分配置 `reversed` 并写 `reversed_at` |
| R-PO-11 | 计划行 `order_id` 必须与 `line_id` 所属订单一致；`schedule_no` 行内唯一 |
| R-PO-12 | 确认动作仅当 `approval_status ∈ {not_required, approved}`；`approval_status=pending` 时禁止 `confirm_purchase_order` |
| R-PO-13 | 成套：`parent_line_id` 必须同单且父行 `pricing_mode='bundle_price'`；父行不得再有父；子行 `qty` 不得超父行 `qty` |
| R-PO-14 | `source_structure_line_id` 有值时，其 `item_id / uom_id` 必须与 PO 行一致，且 `source_structure_id` 必须等于该结构行的 `structure_id` |
| R-PO-15 | `component_issue_required=true` 仅允许 `line_type='subcontract'`；其它行类型置 true 拒绝 |
| R-PO-16 | `tax_recoverable=false` 时必须填 `tax_code_id`；`non_recoverable_tax_amount` 不得并入 `net_amount`（保持 net 未税口径） |
| R-PO-17 | 分配行 `charge_basis` 与成本字段联动：`project` → `project_id` 必填；`expense` → `expense_account_code` 必填；`asset` → `asset_category_code` 必填 |
| R-PO-18 | `price_source != 'manual'` 时必须带 `price_trace`（命中键快照）；无任何来源命中时只允许落 `manual` 且 `price_trace` 为空 |

### 14.2 冒烟步骤

1. `python scripts/service_manager.py doctor` → 无孤儿进程 / 端口正常。
2. 执行迁移：按项目现有迁移入口按序跑 `v177` → `v178` → `v179` → `v181`（先快照 DB）。
3. `python scripts/service_manager.py restart`。
4. API 冒烟（`curl.exe` + dev-login cookie）：
   - 建 `PO_STD` 草稿单 → 断言 `order_no` 已生成且只读；
   - 加两条行（`PO_GOODS`）→ 断言头金额 = 行汇总；
   - 加两条到货计划行 → 断言 `promised_qty` 合计不超行 qty；
   - 建 `demand_allocation` 两行挂同一计划行（来自两条 requisition 行）→ 断言合计不超计划量；
   - `draft → submitted → confirmed`（免审批路径）→ 断言冻结字段不可改；
   - 另一单配置金额策略 → `submitted` 建审批任务 → approve → `confirmed`；reject → 回 `draft`；
   - 取价：建一条协议阶梯（1-99 件 ¥10 / 100 件以上 ¥9）→ 下 100 件断言命中 ¥9 且 `price_source='agreement'`；同物料再下一单断言 `last_po` 命中上一单价格；
   - `confirmed → closed`；另一单 `→ cancelled` 并断言不可回退。
5. 列表 / 菜单：`/purchase-orders` 可见；行、计划行、分配子表可渲染。
6. 回归：`sales_order` 列表 / 状态动作 / 计划行 / 交货单零异常。

### 14.2.1 执行结果（2026-11-01 落库）

| 项 | 证据 |
|---|---|
| 迁移 | v177 / v178 / v179 `SUCCESS`；v181 `[NEW] procurement` / `[NEW] purchase-order-management` / `[SKIP] 权限集 default 不存在` / `[DROP] 4 个孤儿` / `verify OK` |
| 列表页 | `/purchase-orders` 20 行；表头 12 列（采购订单号 / 单据类型 / 订单日期 / 供应商 / 采购组织 / 业务实体 / 订单币种 / 不含税合计 / 状态 / 审批状态 / 履约状态）；侧栏「采购 / 采购订单」可见 |
| 明细页 | `/detail/purchase_order/2` 7 个表单分区（单据信息 / 供应商与组织 / 交付与条款 / 抬头折扣与附加费 / 定价信息 / 金额合计 / 其他信息）+ 2 个子表各 2 行（订单行 / 到货计划） |
| API 冒烟 | `.trae/debug/po_smoke.py` 46/46 全绿（含 `last_po` 取价、手工改价、审批通过 / 驳回、分配上限、确认冻结、关闭 / 取消不可逆） |
| 取价单测 | `test_purchase_pricing_service.py` 6 passed（50 件→¥10 / 150 件→¥9 / 边界 100 件→¥9、本地未命中回落全局、多档覆盖报错、无来源落 manual） |
| 需求转单（单测） | `test_requisition_po_conversion.py` 10 passed（全量 / 分批 / 剩余量扣减 / 超量拒绝 / 未审批拒绝 / 关闭行拒绝 / 缺参 / 行创建失败整单回滚）；`purchase_order.create_from_requisition` 注册成功（契约校验通过，共 32 个 action） |
| 需求转单（真实 DB + BO 框架） | `.trae/debug/po_convert_smoke.py` 7/7 全绿：approved 申请 7 的开放行 → PO 23（`PO-202611-000024`，draft，`approval_status=not_required`，供应商 8 / 币种 8 / 组织 315）→ 行 22（qty 10，单价 0，金额 0）→ 分配 9（`demand_line_id=2` ↔ `target_line_id=22`，`status=active`）；再请求 5 件被 `QTY_EXCEEDS_REMAINING` 拒绝且 PO 计数不变（23） |
| 需求转单（本轮修复） | 冒烟暴露并修复 3 处：① `RequisitionToPoService.ds` 懒加载未带 `sqlite` 参数（真实进程直接 `TypeError`）；② 转单走 BO Action 不经 `bo_api`，`order_no` 未取号（落库后回执为空）→ 改为 `_build_header` 在开事务前用 `NumberSequenceEngine` 独立取号；③ 回执不含 `order_no` → 取入参兜底 |
| 销售轴回归 | `sales_order` / `sales_order_line` / `sales_order_schedule` 列表可读（19 / 20 / 1 行）；视图配置、明细、动作接口均 200 |
| 测试基线 | 本模块 5 个测试文件 93 passed + 新增取价 6 passed；`--failed` 余量为既有环境失败，本模块零新增 |
| 已知缺口 | ① 环境无 `default` 权限集（v177 授权段跳过），E10「非 admin 可见按钮」未取证，未擅自动 `editor / viewer` 授权；② 转单 action 的 HTTP 暴露已确认（后端重启后 `GET /api/v2/action/` 返回 32 个 action，含 `purchase_order.create_from_requisition`），未做写调用 API 冒烟（需先有新的开放需求行）；写路径由真实 DB + BO 框架进程内端到端冒烟覆盖（取号 / 守卫 / 金额回写 / 整单回滚） |

脚本统一落在 `.trae/debug/`：`po_smoke.py`（API 冒烟）、`po_convert_smoke.py`（转单端到端，结果 `po_convert_smoke.json`）、`po_ui_check.py`（UI 冒烟，结果 `po_ui_check_result.json`，截图由 `PlaywrightCLI` 落到 `test_output/.trae/debug/po_ui_list.png` / `po_ui_detail.png`）、`po_sales_regression.py`（销售轴回归）、`po_env_probe.py`（环境探测）。

---

## 15. 出口判据

| # | 判据 | 验证方式 |
|---|---|---|
| E1 | 头 / 行 CRUD 与 `draft → submitted → confirmed → closed`、任意态 `cancelled` 全部可用 | 冒烟 + 守卫用例 |
| E2 | 编号创建时生成、唯一、不可改；单据类型离开草稿不可改 | 用例 |
| E3 | 头金额恒等于行汇总；确认后冻结字段不可改 | 用例 |
| E4 | 一张 PO 行可分配 2 条以上 requisition 行，且分配合计不超行 / 计划行 qty | 用例 + 冒烟 |
| E5 | PO 行不出现 `requisition_line_id` / `project_task_id` 单值引用；项目任务只落在分配行 | schema 断言 |
| E6 | 到货计划行与 `sales_order_schedule` 同构；收货行以 `schedule_id` 为唯一挂载点 | schema 断言 + 计划行用例 |
| E7 | 审批：无策略免审批；单据类型 + 金额命中则建任务；驳回回草稿；审批状态与单据状态正交 | 审批用例 |
| E8 | 收货 / 发票接口契约以 `source_doc_type` 表达，未新建供应商表 / 未给 PO 加 `from_org/to_org` | schema 断言 |
| E9 | 新测试全绿；`--failed` 无本模块新增失败；SO / requisition / work_order 链路零回归 | `python d:\filework\test.py` |
| E10 | 菜单 / 权限双段式落库，非 admin 可见按钮 | DB 直查 + 前端冒烟 |
| E11 | 取价：协议价格阶梯按数量取对档、多档命中取最低价；`last_po` 命中上一张已确认 PO；无来源时允许人工价 | 取价用例 + 冒烟 |
| E12 | 行类型 5 种均可建档；`component_issue_required` / `pricing_mode` 非法组合被守卫拒绝 | 守卫用例 |
| E13 | 审批策略按对象字段求值：同字段不同对象互不干扰；策略变更不回溯在途单据（快照生效） | 审批用例 |
| E14 | 需求转采购订单：approved 申请的开放行按剩余量转成草稿 PO 并写 `demand_allocation` 锚点；超量 / 未审批 / 已关闭行一律拒绝；任一行写失败整单回滚 | 转单用例 + 真实 DB / BO 框架冒烟 |

---

## 16. 与销售订单统一性对照总表

| 维度 | sales_order | purchase_order | 统一 | 备注 |
|---|---|---|---|---|
| 表 / 行表 | `sales_orders` / `sales_order_lines` | `purchase_orders` / `purchase_order_lines` | 是 | 同构后缀 |
| 计划层 | `sales_order_schedules` | `purchase_order_schedules` | 是 | SO 交货计划 / PO 到货计划 |
| 下游单据 | `shipment` + `shipment_line.schedule_id` | `receipt` + `receipt_line.schedule_id` | 镜像 | 出库 vs 入库 |
| 编号列 | `order_no` | `order_no` | 是 | 唯一业务键同名 |
| 单据类型 | `document_type_id` | `document_type_id` | 是 | PO 走切面，SO 手写字段 |
| 状态机 | draft/submitted/confirmed/closed/cancelled | 同 + 审批规则 | 骨架是 | PO 多 `approve/reject` 规则，审批状态正交 |
| 行状态 | open/closed/cancelled | 同 | 是 | — |
| 计划状态 | planned/confirmed/completed/cancelled | 同 | 是 | 语义替换为到货 |
| 金额模型 | net/tax/gross + 头折扣附加 | 同 | 是 | 行级舍入再汇总 |
| 币种 / 汇率 | 有 | 有 | 是 | 冻结时点同 |
| 组织 | `org_id` + `sales_org_id` | `org_id` + `purchase_org_id` | 结构是 | 职能不同 |
| 交易对手 | `customer_account_id` + `ship_to_party_id` | `supplier_party_id` + `supplier_account_id` | 结构近似 | 供应商由 sourcing 直接给 party |
| 收货地点 | 客户地址 / `plant_location_id` | `deliver_to_location_id` | 否 | 采购是我方地点，统一到需求层命名 |
| 行项目归属 | 行 `project_id` | 无行 `project_id` | 否（有理由） | 合并采购走分配表 |
| 配置展开 | 支持 | 不支持 | 否（有理由） | PO 不做选配 |
| 服务字段 | 计费 / 资源 / 工期 | 仅服务起止日 | 否（有理由） | 采购服务结算由发票处理 |
| 审计 / 版本 / 派生缓存 | 有 | 有 | 是 | 派生只读 |
| 子表 / 菜单 | `child_sections` | 同 | 是 | 迁移落库 |

---

## 17. 未决问题（需评审拍板）

| # | 问题 | 本 spec 建议 | 影响 |
|---|---|---|---|
| Q1 | 是否建 ASN（供应商预先发货通知） | M3 不建；到货计划行先覆盖「买方计划 + 供应商承诺」，ASN 留 M5 / 收货 spec | 若建，需 `asn` + `asn_line`，收货行可挂 ASN |
| Q2 | 收货 / 发票是否与本 spec 合并 | 不合并；另立 `spec-receipt-invoice-object-model` | 本 spec 只锁契约与计划行 |
| Q3 | 供应商价格来源（合同价 / 报价 / 价目表）是否 M3 内建 | M3 人工单价 + `price_source`；价格表随采购定价波次 | 影响 `price_trace` 是否有内容 |
| Q4 | 审批规则用什么承载 | **独立三表**（`approval_policies / approval_policy_conditions / approval_policy_steps`），条件因子引用对象字段；**撤回**给控制参数加金额列的方案 | 影响 v177 迁移内容与 M1 审批兼容 |
| Q5 | PO 审批驳回后回 `draft` 还是 `cancelled` | 回 `draft`，保留修改重提 | 与 D365「Request change」同向 |
| Q6 | 到货计划是否允许超计划收货 | 默认不允许；容差由 `receipt_over_tolerance_percent` 控制 | 影响 R-SCH-3 |
| Q7 | `demand_allocation.allocated_amount` 是否保留 | 保留为只读派生（`qty × 单价`），用于成本回聚 | 若不要，可删除 |
| Q8 | `schedule_kind` 是否只做 `delivery` | 做 `delivery + service`；开票计划由发票 spec 处理 | 影响计划行 UI |
| Q9 | 服务采购验收是否复用收货单 | 是，`source_doc_type` 扩 `service_entry` 前先复用 `receipt` | M5 前定 |
| Q10 | 多税率 / 多税行 | 沿用 SO 单 `tax_code` 口径 | 与 SO 一致，暂不扩 |
| Q11 | `demand_allocation` 的成本维度做到什么程度 | **建列 + 从需求行继承 + 守卫校验**（`cost_center_id / expense_account_code / asset_category_code / charge_basis`）；不做凭证与科目映射 | 需要 `requisition_line.cost_center_id` 前置补列 |
| Q12 | 委外是否独立单据对象 | **不独立**，`line_type='subcontract'` + 组件发料清单；独立对象会让同一次下单的收货 / 发票对账分裂 | 影响 §5.1 行类型种子与 M4 排期 |
| Q13 | 采购业务类型放头级还是行级 | **行级** `line_type`；一张 PO 可混合物料 + 服务 | 若放头级，混合单据无法建模 |
| Q14 | 审批规则何时替换旧 `demand_approval_*` | M3 期间旧口径继续生效（标 deprecated）；迁移列 L-PO-2，需保证 requisition 在途单据不受影响 | 影响 v177 与 M1 存量数据 |
| Q15 | BOM 展开放在 PO 还是需求侧 | **需求侧**（`requisition_line` 展开）；PO 只存追溯锚点 `source_structure_id / source_structure_line_id` | 若放 PO 会绕过寻源与比价，且 BOM 改版后订单漂移 |
| Q16 | 采购定价规则是否与销售共用 `pricing_determination` | **不共用**，新建 `purchase_pricing_determination`（键含 `purchase_org_id` + `supplier_party_id`）；`rate_table` + 取价服务共用 | 合并会让一半列恒空，且供应商维度无处放 |
| Q17 | `last_po`（最近采购价）是否作为取价来源 | **作为只读派生来源**，按 `supplier_party_id + item_id` 取最近一次 `confirmed` PO 行；SO 无对应概念 | 需要 PO / 行状态可查询，不改结构 |

---

## 18. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| D-PO-1 | PO 与 SO 共用骨架，差异只保留采购语义项 | 单系统、单订单实体；减少两套守卫 / 两套 UI 推导 |
| D-PO-2 | 编号列统一 `order_no` | 通用取号、列表、守卫可复用；前缀由序列区分 |
| D-PO-3 | 单据类型走切面 | 平台规范 T-D20；与 requisition / service_request 一致；SO 迁移列为遗留 |
| D-PO-4 | PO 审批**可配置**：document_type 选策略，金额 / 组织 / 品类为条件；默认免审批 | 对标 SAP / Oracle / D365 / Coupa；只按类型写死会误伤小额或漏审大额；审批状态与单据状态正交 |
| D-PO-5 | 供应商用 `supplier_party_id` + `supplier_account_id` | T-D4 不建 supplier 表；sourcing 输出 party；账户只带默认值 |
| D-PO-6 | 行不设 `project_id` / `requisition_line_id` | T-D3 合并采购禁止单值引用；归属走 `demand_allocation` |
| D-PO-7 | `demand_allocation` 为唯一分配表，挂到**计划行**粒度 | T-D14；对标 Oracle PO distributions + pegging；支持分批收货追溯 |
| D-PO-8 | M3 不写 `doc_flow` 边 | M6 统一启用；M3 用分配表闭合，避免双写 |
| D-PO-9 | 收货 / 发票按 `source_doc_type` 复用 | T-D12；本 spec 只锁契约 |
| D-PO-10 | 补 `purchase_order_schedule` 计划层 | SO 已有 `sales_order_schedule`；没有计划层就无法表达分批到货与部分收货 |
| D-PO-11 | ~~审批金额维度进入平台控制参数~~ **已被 D-PO-17 取代** | 原方案复用 M1 控制参数底座加 `amount_min / amount_max`；v2 评估后认为条件因子应引用对象字段，改用独立审批规则模型 |
| D-PO-12 | 分配行承载项目 / 项目任务 | 合并采购后成本回聚到需求方；避免在 PO 行放单值 `project_task_id` |
| D-PO-13 | **审批规则独立成模型**：策略 / 条件 / 步骤三表，条件引用对象字段 | 条件因子天然按对象不同；Oracle = 条件组 + 条件 + 动作，SAP = 特性 → 分组 → 策略；控制参数只留开关 |
| D-PO-14 | **采购业务类型放行级 `line_type`**，不放头级 document_type | 一张 PO 可混合物料 + 服务 + 资产；SAP item category、Oracle line type 均为行级 |
| D-PO-15 | **成本归属维度长在分配行**，`charge_basis` 决定记账走向 | Oracle `ChargeAccountId` = 公司 + 成本中心 + 科目 + 项目；distribution 同时是 pegging 行与成本归属行 |
| D-PO-16 | **委外不新建单据对象**，同一张 PO + 行类型 + 组件发料清单 | 拆单会让收货 / 发票对账分裂；SAP / Oracle 都在同单内处理委外 |
| D-PO-17 | 撤回 `control_parameter_values` 加金额列方案，v177 改为建审批规则三表 | 金额区间是策略条件，不是控制参数；避免平台留下两套审批口径 |
| D-PO-18 | **BOM 展开在需求侧，PO 只存追溯锚点**；委外发料独立成层 | BOM 改版不应让订单数据漂移；需求侧展开后 sourcing 才能按组件寻源 |
| D-PO-19 | **金额算术完全复用，定价规则表不复用** | `sales_order_amount_service` 与对象无关；而销售 / 采购的规则键语义不同（组织 + 客户 vs 组织 + 供应商），合并即产生恒空列 |
| D-PO-20 | **成套计价复用 SO 的 `pricing_mode` / `parent_line_id` / `component_no`**；`configuration_id` 只读追溯 | 供应商整包报价是真实场景；选配求解仍只在销售侧 |
| D-PO-21 | **委外采用 SAP 式整单模型，不用 Oracle OSP 式工序服务行** | OSP 依赖 WIP 工单 / 工艺路线 / outside resource，本系统均未建；结构已预留迁移点（§4.4.1） |
| D-PO-22 | **价格阶梯必须显式配置累计 / 非累计口径**，同条件多档命中取最低价 | 对齐 Oracle BPA 价格阶梯行为；不设隐式默认，避免「为什么取这一档」说不清 |
| D-PO-23 | **`demand_allocation` 不进 PO 详情 `child_sections`（M3）**，由服务 / API 维护 | 该表多态（`target_bo` + `target_id`），无单一父字段，子表组件按单父字段过滤；为一家载体写特例会让 UI 出现第二套父字段口径，留给 M6 派生只读视图 |

---

## 19. 参考来源

| # | 来源 | 用途 |
|---|---|---|
| 1 | [SAP PR → PO 合并条件（Guru99）](https://www.guru99.com/es/how-to-convert-purchase-requistion-to-purchase-order.html) | 同供应商 / 采购组织 / 币种可合并多张 PR |
| 2 | [SAP MM 数据流 PR → PO → GR](https://croma-campus.weebly.com/blog/how-sap-mm-actually-moves-data-from-purchase-requisition-to-payment) | `BANFN` 存入 PO |
| 3 | [SAP EKET 计划行字段](https://www.sapdatasheet.org/abap/tabl/EKET.html) / [EKET vs I_ScheduleLine](https://btpstacks.com/post/559c0e54-01ea-4f89-84d0-14e190f90875) | 计划行键与交期 / 数量字段 |
| 4 | [Oracle Purchasing：订单计划页签](http://docs.oracle.com/cd/E18727-01/doc.121/e13410/T446883T443956.htm) | schedule / location / qty / need-by；split schedule |
| 5 | [Oracle PO_LINE_LOCATIONS_ALL](http://docs.oracle.com/en/cloud/saas/procurement/24c/oedmp/polinelocationsall-9221.html) | `REQUESTED_SHIP_DATE` 等计划字段 |
| 6 | [Oracle PO_DISTRIBUTIONS_ALL](https://docs.oracle.com/en/cloud/saas/procurement/25c/oedmp/podistributionsall-31530.html) | `REQ_LINE_REFERENCE_NUM` / `REQ_HEADER_REFERENCE_NUM`；distribution 与 requisition 关系 |
| 7 | [Oracle Draft Purchasing Document Distributions](http://docs.oracle.com/en/cloud/saas/procurement/24c/oadpr/DraftPurchasingDocumentDistributionExtractPVO.html) | `PoLineId` + `ReqDistributionId` |
| 8 | [Oracle 项目 pegging](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24a/fausp/review-supplies-and-demands-with-project-pegging.html) / [PeopleSoft MSR pegging](http://docs.oracle.com/en/applications/peoplesoft/financials-and-supply-chain-management/9.2.057/peoplesoft-supply-chain-management-common-information/pegging-material-stock-request.html) | 供需 pegging 语义 |
| 9 | [SAP Release Procedure for PO](https://www.sapdatasheet.org/abap/cus0/olmeomgs_2.html) / [Release Strategy vs Fiori Workflow](https://www.corepath.es/blog/sap-release-strategy-vs-fiori-workflow_fr.html) | PO 头级 release、PR 行级 release、分类特性 |
| 10 | [Oracle Approval Rules](https://docs.oracle.com/en/cloud/saas/procurement/25b/oapro/various-aspects-of-approval-rules.html) / [PO Approval Processed](https://docs.oracle.com/en/cloud/saas/procurement/25b/oaprc/how-purchase-order-approval-is-processed.html) | 规则 = 条件 + 动作；金额 / 币种条件 |
| 11 | [D365 Approve and confirm POs](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-approval-confirmation) | Change management；审批状态与单据状态分离 |
| 12 | [Coupa Approval Chain Import](https://docs.coupa.com/en/developer-documentation/coupa-core-flat-files-csv/flat-file-csv-import/approval-chain-import) | 审批链条件：科目 / 品类 / 物料 / 申请人 |
| 13 | [Coupa Delivery Schedules for External POs](https://docs.coupa.com/en/supplier-documentation/coupa-for-suppliers/the-coupa-supplier-portal-or-csp/features-and-processes-in-the-coupa-supplier-portal/purchase-orders/purchase-order-collaboration-with-buyers/manage-buyer-generated-delivery-schedules-for-external-pos) | `Schedules Planned`、承诺量小于订单行量 |
| 14 | [Coupa Invoices Export](https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/coupa-core-flat-files-(csv)/flat-file-(csv)-export/invoices-export) | Invoice Line Allocation 行类型 |

---

## 20. 审批要求

本 spec 需用户确认以下 8 项后才进入实施：

1. 是否接受 §2 的统一骨架与 §2.1 的 8 项差异（特别是 D6「PO 行不设 `project_id`」）。
2. 是否接受 §7 的供应商字段口径（`supplier_party_id` 必填 + `supplier_account_id` 可空）。
3. 是否接受 §6.2 的**独立审批规则模型**：策略 / 条件 / 步骤三表，条件因子引用对象字段（按对象各自生效），`document_type` 只是策略选择维度，无命中策略 = 免审批；并确认**撤回**给 `control_parameter_values` 加金额列的方案，v177 改为建三表。
4. 是否接受 §5 的**采购业务类型放行级**：`standard / subcontract / asset / service / expense`，委外不新建单据对象；M3 只落类型与字段位，发料 / 转固 / 验收闭环放 M4 / M5。
5. 是否接受 §9.2.1 的**成本归属维度**：`cost_center_id / expense_account_code / asset_category_code / charge_basis` 长在分配行，并同意 M3 前置给 `requisition_line` 补 `cost_center_id`。
6. 是否接受 §9 / §10 的对象关系：`demand_allocation` 挂到**到货计划行**粒度，并新增 `purchase_order_schedule` 作为收货行唯一挂载点。
7. 是否接受 §5.4 / §5.5 的 BOM 口径：**展开在需求侧完成**，PO 只存 `source_structure_id / source_structure_line_id` 追溯锚点；成套计价复用 SO 的 `pricing_mode` / `parent_line_id` / `component_no`，`configuration_id` 只读追溯；委外发料另立一层。
8. 是否接受 §4.3 / §4.4 的定价口径：**金额算术完全复用**（抽 `DocumentAmountService`），**定价规则表不共用**（新建 `purchase_pricing_determination`，含 `purchase_org_id` + `supplier_party_id`），`rate_table` 与取价服务共用；并按 Oracle 核对结论落地**价格阶梯（同条件取最低价）**与**本地 / 全局协议优先级**，`last_po` 作为只读派生来源。

确认后按 §14 步骤执行，用 TodoWrite 跟踪，不提交 git（除非另行指示）。
