# 销售开票对象模型细化（Sales Order Billing）

> 状态：**研究草案 v1（待评审，评审通过前不实施）**
> 日期：2026-11-07
> 范围：销售订单（sales_order）→ 开票计划 → 销售发票（customer_invoice）→ 应收发生额（L2 会计事件）
> 依据（均为当前 HEAD 代码/文档实证）：
> - `meta/schemas/sales_order.yaml`、`sales_order_line.yaml`、`sales_order_schedule.yaml`、`shipment.yaml`、`type_definition.yaml`、`number_sequence.yaml`
> - `meta/services/sales_order_guard_service.py`（R-SCH-11..15 开票计划守卫）
> - `docs/specs/spec-doc-flow-end-to-end-2026-11-05.md`（billing 池、service_confirmation 预留边）
> - `docs/specs/spec-project-g15-finance-boundary-2026-11-04.md`（L1/L2/L3 财务边界）
> - `docs/specs/spec-receipt-object-model-2026-11-01.md` §10（采购侧发票契约，销售侧须对称）
> - `docs/specs/bo-metadata-gap-2026-11-06/spec.md`（S7 六件套、S1 状态矩阵、编号外部校验）

---

## 0. 结论先行

| # | 问题 | 结论 |
|---|---|---|
| 0.1 | billing 是否做成 SO 的子对象 | **否**。建独立事实单据 `customer_invoice` + `customer_invoice_line` |
| 0.2 | 现有 `sales_order_schedules(schedule_kind='billing')` 算什么 | 是**开票计划（billing plan）**，不是发票；保留在原对象，不升级为单据 |
| 0.3 | 是否新建「开票到期清单 / billing request」表 | **不建表**。到期清单是投影，用查询/视图实现 |
| 0.4 | 开票触发源 | Wave A：发货（shipment shipped/delivered）+ 手工；Wave B：里程碑计划；Wave C：服务确认（T&M） |
| 0.5 | 过账点 | `posted`。过账后不可改，只能整单红冲（red invoice） |
| 0.6 | 金额/税/汇率 | 全部由服务层计算并**落快照**，前端只读（沿用 SO 的 R11/R12 口径） |
| 0.7 | 版本跟踪 | **不启用** `revision_policy`（事务单据：字段级审计 + 过账快照即可，对齐 SAP/Oracle 主数据才做版本） |
| 0.8 | 财务边界 | 只做 L1 发票 + L2 会计事件；**不做** AR 台账/账龄/收入确认/税务申报 |
| 0.9 | 编号 | `type_definitions(scope_bo='customer_invoice')` + `number_sequences`，拦截器取号，外部号走 S6 校验 |
| 0.10 | 迁移号 | `v232__customer_invoice.py`（当前最大为 v231） |
| 0.11 | 发票聚合键 | Wave A：**一发货单一张票**；允许手工勾选多张发货单合并。聚合键 `(customer_account_id, currency_id, bill_to_account_id, org_id)`，自动合并留 Wave C（D7） |
| 0.12 | 更正手段分层 | Wave A：整单红冲；Wave C：`credit_memo` 行级部分冲销（对齐 Oracle UNIT 口径）。**不做** AR 侧 adjustment（D8） |
| 0.13 | 计划与发货的关系 | **二选一**（D10 已定）：订单行 `billing_relevance`（`delivery` 默认 / `plan` / `none`），**不做**双口径主从。详见 §20 |

**一句话**：开票计划已经有了（计划行），缺的是「计划/发货 → 发票」这一段事实单据；补齐后销售链路才闭环，且不会把 AR 台账拖进平台。

---

## 1. 现状审计（已有什么 / 缺什么）

| 能力 | 现有实现 | 证据 | 缺口 |
|---|---|---|---|
| 开票计划 | `sales_order_schedules.schedule_kind='billing'`，含 `billing_percent` / `billing_amount`(派生) / `milestone_code` / `promised_date` / `status` | `sales_order_schedule.yaml`；`sales_order_guard_service.py` R-SCH-11..15 | 无「已开票量/额」回写；状态无 `partial`；无发票引用 |
| 订单行计价 | `unit_price` / `net_amount` / `tax_amount` / `gross_amount` / `tax_code_id` / `tax_rate_percent` 快照；`billing_method`（fixed_price / time_and_material / milestone） | `sales_order_line.yaml` | 无 `billed_*` 进度列 |
| 发货事实 | `shipment` + `shipment_line`（`schedule_id` / `order_line_id` / 数量），状态含 `shipped` / `delivered` / `reversed` | `shipment.yaml` | 行无金额（开票按订单行价格快照取）；出库过账仍是 doc-flow G3 缺口 |
| 单据平台能力 | 六件套 `document:`、S1 状态矩阵、S6 编号/外部号、过账快照、doc_flow 边 | S7 已合并 | 发票对象未声明 |
| 采购侧对称 | `vendor_invoice` / `vendor_invoice_line` 契约已锁定，`receipt_to_invoice` 边池 = billing | 采购发票 spec §10 | 销售侧无对应对象 |
| 财务出口 | g15 定「平台只到开票申请（L1）+ 会计事件（L2）」 | g15 spec | 无会计事件出口 |

**结论**：不是「从零建 billing」，而是**把计划层的半成品接到一张新的事实单据上**，并补三处进度缓存。

---

## 2. 行业对标与我方取舍

| 维度 | SAP | Oracle Fusion | 我方取舍 |
|---|---|---|---|
| 计划 | Billing Plan（FPLT）挂在 SO item，里程碑/日期/比例 | 订单行 Recurring Billing（期次 + 每期覆盖）/ Project Billing Bill Plan | 复用 `sales_order_schedules(kind='billing')`，不新建计划对象 |
| 到期清单 | VF04 Billing Due List（**程序**，不落表） | 无独立对象：AutoInvoice 批处理 + 工作区列表 | 用查询/视图，**不建表** |
| 发票单据 | Billing Document VBRK/VBRP，独立事实 | **无 billing 单据层**：AutoInvoice 直接从 OM/Project 生成 AR 发票（`RA_CUSTOMER_TRX_ALL`） | 建 `customer_invoice` 头+行，独立事实 |
| 不可修改 | 已开票只能 VF11 冲销或贷项凭证 | Credit Memo（引原发票行）/ Adjustment / Void | `posted` 后只读，整单红冲；贷项凭证列 Wave C |
| 开票来源 | 交货开票（以 delivery 为源）或计划/订单 | 订单（按发货）/ 项目 / 订阅 / 外部导入 | Wave A 以 shipment 为源，Wave B 接计划，Wave C 接服务确认 |
| 应收 | FI-AR 台账（独立模块） | AR 子账 + SLA 凭证 | **不做**，只出 L2 会计事件 |

> Oracle Fusion 的细节拆解见 **§16**（含源链接）；SAP 的细节拆解见 **§18**（含源链接）；其他头部 ERP（D365 / NetSuite / Workday / Infor / Odoo / 用友 / 金蝶）的横向对比见 **§19**；下表只保留取舍结论。

**关键判断**：三方都把「计划 ≠ 单据 ≠ 应收」分成三层。当前项目把前两层混在了 `sales_order_schedules` 里（字段命名甚至写成「收款比例/收款金额/收款日」，实际是开票里程碑），这是本次要澄清的核心语义债。

---

## 3. 目标对象链

```
sales_order
 └─ sales_order_line   ← billing_relevance（delivery | plan | none）决定唯一开票锚
     ├─[plan]     sales_order_schedules(kind=billing) ───────────────┐
     └─[delivery] sales_order_schedules(kind=delivery) → shipment    │
                                                          └ shipment_line
                                                                     ├─┘
                                                                     ▼
                                              customer_invoice (1..N) └─ customer_invoice_line
                                              doc_flow_edges (pool=billing)
```

| 来源 | 目标 | 适用 `billing_relevance` | 基数 | 锚点 | 写入口 |
|---|---|---|---|---|---|
| shipment_line | customer_invoice_line | **仅 `delivery`** | N : 1（可多次部分开票） | `shipment_line_id` + 数量 | `CustomerInvoiceService.create_from_shipment` |
| sales_order_schedule(kind=billing) | customer_invoice_line | **仅 `plan`** | 1 : N（可分期/部分） | `schedule_id` + 比例/金额 | `create_from_schedule`（Wave B） |
| sales_order_line | customer_invoice_line | 仅 `delivery`（手工挑量） | N : 1 | `order_line_id` | `create_manual` |
| service_confirmation | customer_invoice_line | — | N : 1 | 预留（doc-flow 已有 rule 位） | Wave C |
| customer_invoice（红冲） | customer_invoice（红字） | 任意 | 1 : 1 | `reversal_of_invoice_id` | `reverse` |

> 头不带 `order_id`：合并开票会跨多张 SO，来源信息落在行级；抬头汇总只用于展示。
> **互斥不变量**：同一订单行的发票行，永远只允许一种来源类型（`delivery` ↔ `shipment_line_id`，`plan` ↔ `schedule_id`），跨发票亦然（R-INV-3）。

---

## 4. `customer_invoice`（头）字段

| 分组 | 字段 | db_column | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 标识 | id | id | integer | 是 | 主键 |
| | invoice_no | invoice_no | string(30) | 是 | 业务键，取号后不可改（外部号走 S6 四道校验） |
| | document_type_id | document_type_id | integer | 是 | `type_definitions`，`scope_bo=customer_invoice` + `level=header` |
| 日期 | invoice_date | invoice_date | date | 是 | `business_date_field`；编号日期段基准 |
| | posting_date | posting_date | date | 否 | 会计日期；过账时必填（Wave A 可等于 invoice_date） |
| 状态 | status | status | string | 是 | draft / submitted / posted / cancelled / reversed |
| 往来方 | customer_account_id | customer_account_id | integer | 是 | 售达方（快照自 order） |
| | bill_to_account_id | bill_to_account_id | integer | 否 | 收票方；空 = 同售达方 |
| | payer_account_id | payer_account_id | integer | 否 | 付款方；空 = 同售达方 |
| | bill_to_address_text | bill_to_address_text | string(512) | 否 | 开票地址快照（税务要素） |
| | tax_registration_no | tax_registration_no | string(64) | 否 | 购方税号快照（来源 party_tax_registration） |
| 金额 | currency_id | currency_id | integer | 是 | 必须等于订单币种（Wave A） |
| | exchange_rate | exchange_rate | number(18,8) | 否 | 本币折算，rate=1 可空 |
| | exchange_rate_type / exchange_rate_date | 同名 | string / date | 否 | 汇率快照；rate≠1 时日期必填 |
| | payment_term_id | payment_term_id | integer | 否 | 付款条件快照（收款计划模板，不生成收款计划） |
| | incoterm_code | incoterm_code | string(16) | 否 | 贸易术语快照 |
| | net_amount / tax_amount / gross_amount | 同名 | number(18,4) | 是 | 服务层汇总快照，前端只读 |
| 组织 | org_id | org_id | integer | 是 | 财务归属（法人主体由 `org_legal_entity` 视图推导，不新增列） |
| | sales_org_id | sales_org_id | integer | 否 | 数据范围用，不参与取价 |
| 项目 | project_id | project_id | integer | 否 | 单项目时填；多项目以行级为准 |
| 冲销 | reversal_of_invoice_id | reversal_of_invoice_id | integer | 否 | 红字单指向原单 |
| | reversal_reason | reversal_reason | string(256) | 否 | 红冲/作废原因（posted 后红冲必填） |
| 其他 | remark | remark | text | 否 | 备注 |
| 审计 | created_by / created_at / updated_at | 同名 | — | — | 由 audit_aspect 管理 |

YAML 声明（示意）：

```yaml
document:
  number_field: invoice_no
  business_date_field: invoice_date
  state_field: status
  posting_state: posted
  document_type_field: document_type_id
  line_object: customer_invoice_line
  line_parent_field: invoice_id
  line_sequence_field: line_no
deletion_policy:
  mode: restrict
  cascade_delete: [customer_invoice_lines]   # 仅 draft 可删，守卫强制
audit: {enabled: true}                        # 全量审计，update 用 changed_only
# 不声明 revision_policy
```

---

## 5. `customer_invoice_line`（行）字段

| 分组 | 字段 | db_column | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 标识 | id / invoice_id / line_no | 同名 | integer | 是 | 行主键 / 父键 / 行号（唯一键 `invoice_id + line_no`） |
| | line_type_id | line_type_id | integer | 是 | `scope_bo=customer_invoice` + `level=line` |
| 来源 | source_doc_type | source_doc_type | string(32) | 是 | shipment / billing_schedule / sales_order / service_confirmation / manual |
| | source_doc_id | source_doc_id | integer | 否 | 来源单据头 id（只读副本） |
| | source_line_id | source_line_id | integer | 否 | 来源行 id（只读副本） |
| | shipment_line_id / schedule_id / order_line_id | 同名 | integer | 否 | 语义化快照键（便于查询与回写，均只读） |
| 物料 | item_id | item_id | integer | 否 | 服务行可空；空时 description 必填（沿用 SO R6） |
| | description | description | string(512) | 是 | 开票描述（快照） |
| | uom_id | uom_id | integer | 是 | 计量单位（纯金额行仍取「EA/项」类 uom） |
| 数量 | qty | qty | number(18,4) | 是 | 开票数量；纯金额行填 1 |
| | billing_basis | billing_basis | string(16) | 是 | quantity（按量）/ percent（按比例）/ amount（按金额） |
| 金额 | unit_price | unit_price | number(18,6) | 是 | 单价快照（percent/amount 行由服务层反算） |
| | net_amount | net_amount | number(18,4) | 是 | = ROUND(qty × unit_price) |
| | tax_code_id | tax_code_id | integer | 是 | 税码快照（来源行） |
| | tax_rate_percent | tax_rate_percent | number(9,4) | 是 | 税率快照 |
| | tax_amount | tax_amount | number(18,4) | 是 | = ROUND(net × rate/100) |
| | gross_amount | gross_amount | number(18,4) | 是 | = net + tax |
| 项目 | project_id / project_task_id | 同名 | integer | 否 | 来源行透传（会计事件维度） |
| 审计 | created_at / updated_at | 同名 | — | — | 行不设状态字段，生命周期随头 |

> 不写 `warehouse_id` / 成本字段 / 科目字段：成本与科目属会计映射，不进业务单据。

---

## 6. 状态机与不变量

### 6.1 状态机

```
draft ──submit──► submitted ──post──► posted ──reverse──► reversed
  │                   │                  │
  └──cancel───────────┴──cancel──────────┘（posted 不可 cancel，只能 reverse）
```

- `posted` 为 `posting_state`：跨入时写**过账快照**（不推进 revision）。
- `reversed`：原单只读标记；红字单自身走 draft → submitted → posted。

### 6.2 状态 × 字段矩阵（S1）

| 状态 | 策略 |
|---|---|
| submitted | 冻结 `invoice_no` / `document_type_id` / `customer_account_id` / `currency_id` / `exchange_rate*` |
| posted / reversed | 整单只读（全部业务字段 hidden/readonly） |
| cancelled | 整单只读 + `cancelled_reason`（若加字段） |

### 6.3 服务层不变量（YAML 表达不了的）

| 编号 | 规则 |
|---|---|
| R-INV-0 | `invoice_no` 取号后不可改；取号失败不回退（允许跳号），对外部号执行 S6 四道校验 |
| R-INV-1 | 币种必须等于来源订单币种（Wave A；跨币种 Wave C） |
| R-INV-2 | `exchange_rate ≠ 1` 时 `exchange_rate_date` 必填；`posted` 后冻结 |
| R-INV-3 | 行级来源必须与所属订单行的 `billing_relevance` 一致：`delivery` → `shipment_line_id` 必填、`schedule_id` 必空；`plan` → `schedule_id` 必填、`shipment_line_id` 必空；`manual` → 全部来源键为空。**同一订单行的发票行不得同时出现两种来源（含跨发票）** |
| R-INV-4 | 按量开票：Σ(本行有效发票行 qty) ≤ 来源可开票量（`shipment_line.qty` 或 `order_line.qty` − 已开票量） |
| R-INV-5 | 按比例开票：金额 = ROUND(`billing_percent`/100 × 订单行净额)；同一计划行累计开票 ≤ 行净额 |
| R-INV-6 | 行金额重算：net = ROUND(qty × unit_price)；tax = ROUND(net × rate/100)；gross = net + tax |
| R-INV-7 | 抬头合计 = Σ 行（先按币种精度舍入，再汇总，沿用 SO R11） |
| R-INV-8 | 非红字单金额/数量不得为负；红字单必须全负（对齐 SO R3） |
| R-INV-9 | 非 draft 禁删；`posted` 禁改（守卫拦截器强制） |
| R-INV-10 | 红冲：整单红冲，红字单数量/金额取负并引用 `reversal_of_invoice_id`；原单 → `reversed`；同一原单只能红冲一次 |
| R-INV-11 | 过账前置：来源 shipment 必须 `shipped`/`delivered` 且未 `reversed`；来源计划行必须属于 `confirmed` 订单且计划行未 `cancelled` |
| R-INV-12 | 订单 `closed` 允许对历史发货开票，`cancelled` 禁止开票 |
| R-INV-13 | 回写只由服务层执行：`billed_qty` / `billed_amount` 与计划行状态，红冲时回滚 |
| R-INV-14 | 红字单 `posting_date` 不得早于原单 `posting_date`（对齐 Oracle 贷项会计日期约束，见 §16.4） |
| R-INV-15 | 行级部分冲销（Wave C）：同一原行冲销数量合计 ≤ 原行 `qty`（对齐 Oracle UNIT 口径） |
| R-INV-16 | **`delivery` 分支**：进度回写必须与 `posted` 同一事务，并以条件更新保证「Σ 已开票 ≤ 来源可开量」——`UPDATE shipment_lines SET billed_qty = billed_qty + :q WHERE id = :id AND billed_qty + :q <= qty`；受影响行数 ≠ 1 即整体回滚（防并发超开） |
| R-INV-17 | **`plan` 分支**：`billing_basis='percent'` 行必须以「计划行金额 × 比例」反算净额，且该计划行累计比例 ≤ 100%；**不得**用单价 × 数量口径 |
| R-INV-18 | `billing_relevance` 默认由 `billing_method` 带出（`milestone` → `plan`，其余 → `delivery`），draft 可改，**订单确认后只读**；该行一旦存在非作废发票行，禁止切换取值（错误码 `BILLING_RELEVANCE_LOCKED`） |
| R-INV-19 | 可开量按范式分流、互不折算：`delivery` 行 = `shipment_line.qty − billed_qty`（或 `order_line.qty − billed_qty`）；`plan` 行 = `schedule.billing_amount − schedule.billed_amount` |
| R-INV-20 | 回写分流：`delivery` 只写 `shipment_line.billed_qty` + `sales_order_line.billed_qty`；`plan` 只写 `sales_order_schedule.billed_amount` / `billing_status`。同一订单行不得两路同时回写（红冲时同一路回滚） |

---

## 7. 过账与冲销副作用（唯一写入口）

`CustomerInvoiceService.post(invoice_id)`：

1. 校验 R-INV-11 / R-INV-4 / R-INV-7；
2. 写 `doc_flow_edges`（source → customer_invoice，pool=billing）；
3. 回写来源行 `billed_qty` / `billed_amount`；计划行累计达 100% → `completed`，部分 → `partial`；
4. 触发 `sales_order.billing_status` 重算（none / partial / full，派生字段，不进状态机）；
5. 发 `accounting_event(invoice_issued)`（若 g15 L2 未落地则只留 hook，不建表）；
6. **不改**订单状态、订单金额、库存、发运状态。

`CustomerInvoiceService.reverse(invoice_id, reason)`：生成红字单并过账 → 回滚 3/4 → 原单 `reversed`。

`cancel(invoice_id)`：仅 draft/submitted；释放已占用的「在途开票量」（若有锁定）。

---

## 8. 需新增的派生列（随发票回写）

| 对象 | 新增字段 | 类型 | 说明 |
|---|---|---|---|
| shipment_lines | `billed_qty` | number(18,4) | 该发货行已开票数量（**仅 `delivery` 路径**；防同一发货行重复开票） |
| sales_order_lines | `billed_qty` | number(18,4) | 已开票数量（**仅 `delivery` 路径**，只读缓存，服务层维护） |
| sales_order_lines | `billed_amount` | number(18,4) | 已开票净额（**仅 `delivery` 路径**） |
| sales_order_schedules | `billed_amount` | number(18,4) | 计划行已开票金额（**仅 `plan` 路径**，里程碑口径） |
| sales_order_schedules | `billing_status` | enum none/partial/full | 计划行开票进度（派生，不进 state_transition） |
| sales_orders | `billing_status` | enum none/partial/full | 整单开票进度（派生，对齐 `fulfillment_status` 做法） |
| sales_orders | `billing_derived_at` | datetime | 派生时间戳（不参与审计 diff） |

> 这些都是**只读派生缓存**，不是新的真相源；真相源永远是已过账发票行。`schema` 里标注 `ui.editable: false` 且不进 `state_field_policies` 的可写集合。
>
> **两套回写列互斥（R-INV-20）**：`delivery` 路径只写 `shipment_lines` / `sales_order_lines` 的列；`plan` 路径只写 `sales_order_schedules` 的列。同一订单行两路不会同时非 0，巡检断言见 §20.4。`sales_orders.billing_status` 是唯一同时读两路的汇聚点（只读投影）。

---

## 9. 编号 / 类型 / 六件套 / 权限

| 项 | 设计 |
|---|---|
| 类型 | `type_definitions` seed：`SINV`（标准发票）/ `SCR`（贷项凭证）/ `SDN`（借项凭证），`scope_bo=customer_invoice`、`level=header`、`document_category` 分别 standard / credit_memo / debit_memo；行类型 `ITEM` / `SERVICE` / `DISCOUNT` |
| 编号 | `number_sequences` 例：`SINV-{YYYY}-{SEQ:5}`、`SCR-{YYYY}-{SEQ:5}`；`code` 由类型绑定 |
| 六件套 | 见 §4 YAML 示意；`posting_state=posted` |
| 删除 | `restrict` + draft 级联删行；守卫拦截非 draft 删除 |
| 审计 | create=all；update=changed_only（排除派生列与审计列）；delete=business_only |
| 版本 | 不启用 |
| 权限 | 独立资源 `customer_invoice.*`（view/create/edit/delete/post/reverse/print）；到期清单只读资源 `customer_invoice_due.*` |
| 菜单 | 销售 → 开票 → {销售发票, 开票到期清单}；不在订单详情内嵌可编辑发票 |

---

## 10. doc_flow 契约（与 doc-flow spec 对齐）

| rule id | source_bo | target_bo | 池 | 计量 | 状态约束 | 方向 |
|---|---|---|---|---|---|---|
| `shipment_to_customer_invoice` | shipment | customer_invoice | billing | 数量 | source ∈ shipped/delivered，未 reversed；target 非 cancelled；**来源订单行 `billing_relevance` 必须 = `delivery`** | 正向 |
| `billing_schedule_to_customer_invoice` | sales_order_schedule | customer_invoice | billing | 金额 | source `schedule_kind='billing'` 且未 cancelled；**来源订单行 `billing_relevance` 必须 = `plan`** | 正向 |
| `sales_order_to_customer_invoice` | sales_order | customer_invoice | billing | 否 | 仅手工开票；**仅 `delivery` 行可按 `order_line` 挑量** | 正向 |
| `customer_invoice_reversal` | customer_invoice | customer_invoice | billing | 金额（负） | source = posted 且未被红冲 | 红字 |
| `service_confirmation_to_invoice_line` | service_confirmation | customer_invoice_line | billing | 数量 | **预留**，Wave C 接线 | 正向 |

**两条开票边互斥**：`shipment_to_customer_invoice` 与 `billing_schedule_to_customer_invoice` 不得对同一订单行同时生效；`delivery_schedule_to_customer_invoice` **禁止建边**（`kind='delivery'` 的计划行只作发货来源）。该互斥由 `CustomerInvoiceService.create_*` 在建行时校验（R-INV-3），**不依赖 doc_flow 规则表达**——doc_flow 只记录已发生的边，不具备「按订单行分叉」的准入语义。详见 §20.6。

---

## 11. 财务边界（对齐 g15）

| 层 | 由谁负责 | 本期是否落地 |
|---|---|---|
| L1 业务事实：开票申请/发票 | 平台（本 spec） | ✅ Wave A |
| L2 会计事件：`invoice_issued`（借 AR / 贷收入+销项税） | 平台出事件，规则映射后置 | ⏳ hook 位（Wave C 或 g15 Phase 2） |
| L3 总账凭证、AR 台账、账龄、税务申报、收入确认 | 外部财务系统 / 后续项目 | ❌ 明确不做 |

**红线**：不在 `customer_invoice` 上放科目、成本、已收金额、账龄字段；不建 `ar_invoice` / `ar_ledger` 表。

---

## 12. 实施波次与任务

### Wave A（最小闭环，建议先做）

| 任务 | 内容 | 规模 |
|---|---|---|
| S8-A1 | `customer_invoice.yaml` / `customer_invoice_line.yaml`；六件套、状态矩阵、删除策略、审计；**`customer_invoice_line` 的 `ck_cil_source_xor` 行级互斥约束** | M |
| S8-A2 | 类型/编号 seed（SINV）+ 行类型 | S |
| S8-A3 | `meta/services/customer_invoice_service.py`：`create_from_shipment` / `create_manual` / `recalc` / `submit` / `post` / `cancel`；`_available()` 按 `billing_relevance` 分支；`plan` 取值入口 fail-closed | L |
| S8-A4 | 守卫拦截器：R-INV-0..9 + R-INV-14 + **R-INV-18/19/20**、过账/红冲入口校验（fail-closed） | M |
| S8-A5 | 回写分流：**`delivery` 路径**写 `shipment_line.billed_qty` / `order_line.billed_qty` / `billed_amount`；`plan` 路径列建而不写（R-INV-20）；`billing_status` 两路汇聚 | M |
| S8-A6 | doc_flow 边 `shipment_to_customer_invoice` + 状态约束 + 准入校验（§20.6） | S |
| S8-A7 | `v232__customer_invoice.py`：建表/加列（含 `sales_order_lines.billing_relevance`、`shipment_lines.billed_qty`）、索引、`billing_relevance` 回填（§20.8）、断言、verify | M |
| S8-A8 | 测试：`test_customer_invoice_service.py`（≥14，含两种取值的可用量分支）、`test_customer_invoice_guard.py`（≥8，含 `BILLING_SOURCE_MISMATCH` / `BILLING_RELEVANCE_LOCKED`）、`test_migration_v232.py`（4，含回填断言） | M |
| S8-A9 | 数据质量巡检：§20.4 两条互斥 SQL，落 `meta/tools/`，作为 S8 出口门禁 | S |

出口：一张已发货的 shipment 能开出 `posted` 发票，重复开票被拒，订单行 `billed_qty` 正确回写；**`plan` 行被 fail-closed 拒绝**；互斥巡检返回 0 行；测试全绿。

### Wave B（计划开票 + 到期清单）

- 打开 `plan` 分支：`create_from_schedule`（期次金额/比例 → 发票行，`qty=1`、`billing_basis='percent'|'amount'`）；
- 计划行回写：`sales_order_schedule.billed_amount` / `billing_status`（`none → partial → full`），**不写 `shipment_line.billed_qty`**（R-INV-20）；
- 里程碑开票（`billing_percent` / `billing_amount`），计划行 `partial` / `completed`；
- 开票到期清单：查询/视图（按 `promised_date ≤ 今天` 且 `billing_status <> full`），**不建表**；
- 部分开票与「在途锁量」；一期累计 ≤ 该期金额（R-INV-17）。

### Wave C（后置）

- 贷项/借项凭证、整单红冲、合并开票（跨 SO）、跨币种、服务确认 T&M 开票、L2 会计事件。

### 明确不做

- AR 台账 / 账龄 / 收款核销；收入确认；税务申报；电子发票平台对接（可留 adapter）；发票 OCR/影像。

---

## 13. 决策记录（D1-D11）

| 编号 | 决策点 | 结论 / 推荐 | 备选 | 状态 |
|---|---|---|---|---|
| D1 | 发票是否独立事实单据 | **独立**（1 SO : N 发票、可合并开票、可红冲） | 作为 SO 子对象（会锁死 1:1，不推荐） | ✅ 已定 |
| D2 | 是否建 `billing_request` 表 | **不建**（到期清单用查询/视图） | 建表（多一套状态机与一致性负担） | ✅ 已定 |
| D3 | `billing_percent` / `billing_amount` 到底是开票计划还是收款计划 | **需重新确认**：§19.3 发现用友/金蝶的「收款计划」是独立对象且不控开票。若我方这两列实为收款口径，应另立 `collection_schedule`，不得与开票计划混用 | 维持现状并只改文案为「开票比例/开票金额」（仅在确认它们确实只控开票时成立） | ⏳ 待确认 |
| D4 | Wave A 开票触发源 | **shipment（shipped/delivered）** | 以计划为准（依赖计划行状态早于发货） | ✅ 已定 |
| D5 | 是否启用 `revision_policy` | **不启用** | 启用（与「事务单据只有字段级审计」结论冲突） | ✅ 已定 |
| D6 | L2 会计事件是否本期落地 | **本 spec 只留 hook，按 g15 排期** | 本期一并做（范围外溢） | ⏳ 待确认 |
| D7 | 多发货单是否自动合并成一张发票 | **Wave A 不自动合并**（一发货单一张票 + 手工多选），聚合键固定 4 元组 | 自动按客户/币种合并（需分组规则配置，Wave C） | ✅ 已定 |
| D8 | 部分冲销用贷项凭证还是拆红冲 | **Wave A 整单红冲**；Wave C 增 `document_category='credit_memo'` 行级引用原发票行 | 只做整单红冲（无法部分冲销，长期受限） | ✅ 已定 |
| D9 | 报价域（Oracle CPQ 对标）是否进本期 | **不进**，仅保留 `quote → sales_order` 的衔接结论（详见 §17.5） | 本期接入报价域（范围外溢） | ✅ 已定 |
| D10 | 开票主锚：里程碑计划与发货是二选一还是主从 | **二选一**：`sales_order_line.billing_relevance`（`delivery` 默认 / `plan` / `none`），行级单值、互斥链路。落地设计见 **§20** | 双口径主从 / NetSuite 式「计划定金额 + 发货作闸门」 | ✅ 已定（用户拍板） |
| D11 | 一期能否分次开票 | **允许**，但一期累计 ≤ 该期比例/金额（R-INV-17），到 100% 后该期关闭 | 一期必须一次开完 | ⏳ 待确认 |
| D12 | 是否按「出库批次」动态生成收款计划组 | **不做**。计划分组键固定在订单行级静态维度（`group_no` 由订单行拆批决定），不随每次发货新增组 | 动态批次组（§24.6 原提案；§24.9 曾称其为差异化） | ✅ 已定（用户拍板：无人做则不做） |
| D13 | 开票时能否改价 | **允许受控改价**：行上落 `order_unit_price` / `invoice_unit_price` / `price_diff_amount` / `price_override_reason`，差额单独入「价差」会计维度 | 禁止改价（原 §5 口径，已作废） | ✅ 已定（SAP / Oracle 均支持） |
| D14 | 收（付）款单与计划期次的颗粒度关系 | **事实层整单 + 核销层到期次**：`payment_receipt` 不带 `schedule_id` 外键；期次归属由 `payment_allocation` 表达（N:M） | 收款单直接挂期次（1:1，锁死部分付款与跨期付款） | ⏳ 建议（见 §25） |
| D15 | 预付款在开票前没有「应付/应收」，如何挂账 | **不造假应收**：以 `reserved_amount` + 核销锚点（`order_id` / `group_no`）承载承诺，开票后再转 `applied` | SAP 式统计性 FAZ 请求 / Oracle 式 Prepayment 发票 | ⏳ 建议（见 §25.7） |
| D16 | 「已结算金额」与「已核销金额」是否同一口径 | **两个口径分离**：发票侧 `receipt_settled_amount`（现金已收）+ `prepaid_offset_amount`（预收抵扣）；付款侧 `applied_amount`（已核销） | 单列混算（金蝶口径，客户无法区分现金与抵扣） | ⏳ 建议（见 §25.5） |

> **编号说明**：D9 在 §17.5（报价域）已被占用，因此「开票主锚」使用 D10，「一期分次开票」使用 D11——§18.4.1 与 §18.10 的引用口径一致，不再调整。
> D10 的结论推翻了 §2 早期「数量看发货、金额看计划」的双口径假设：那是自研扩展，行业无先例（§19.3 结论 1）。
> **D12–D16 为本轮（2026-11-08）新增**：D12/D13 为用户当面拍板；D14–D16 为 §25 对象模型研究的结论，状态标为「建议」，待评审确认后转「已定」。
> D12 与本文件 §24.9 的「动态批次组是唯一差异化」表述冲突，以 D12 为准（§24.9 该句作废，见 §25.10 注）。

---

## 14. 出口判据（Definition of Done）

- E-INV-1 发货单可开票；同一 shipment_line 重复开票被拒（R-INV-4）；
- E-INV-2 `posted` 后任一字段修改被守卫拦截；只能红冲；
- E-INV-3 红冲后 `billed_qty` / `billing_status` 正确回滚；
- E-INV-4 发票金额 = Σ 行，行金额按 R-INV-6 舍入；
- E-INV-5 编号取号唯一，外部号非法被拒（S6 错误码）；
- E-INV-6 doc_flow 边可追溯（source → invoice），状态约束生效；
- E-INV-7 存量对象零影响（新增对象 + 新增派生列，默认值向后兼容）；
- E-INV-8 `python d:\filework\test.py --all` 全绿（新测试 + SO/发货回归）。
- E-INV-9 二选一生效：`delivery` 行可开票；Wave A 下 `plan` 行被 `BILLING_RELEVANCE_NOT_SUPPORTED` 拒绝；同一订单行在**任意发票**中不得同时出现 `shipment_line_id` 与 `schedule_id`（§20.4 巡检 0 行）。
- E-INV-10 回写分流：`delivery` 路径 `schedule.billed_amount` 恒 0；`plan` 路径 `shipment_line.billed_qty` 与 `order_line.billed_qty` 恒 0；`sales_order.billing_status` 两路汇聚正确。

---

## 15. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `sales_order_schedules` 语义混淆（开票计划 vs 收款计划） | 认知混淆、字段误用；D3 悬而未决 | YAML description 明确「开票里程碑，非收款计划」；D3 确认前不改列名，也不在其上叠加收款逻辑 |
| `billing_relevance` 被误用（同一订单行混用两口径） | 双口径并行、金额与数量对不上 | 行级单值 + `ck_cil_source_xor` 物理互斥 + 跨发票巡检 + 订单确认后锁定（R-INV-18/20，§20.4） |
| 出库过账仍未闭环（doc-flow G3） | 「发货开票」与实物账不同步 | Wave A 以 `shipped/delivered` 状态为业务事实，不依赖库存过账；库存过账按 doc-flow 单独排期 |
| 税率/金额舍入口径不一致 | 与订单金额对不上 | 复用 SO R11：先按行+币种精度舍入，再汇总 |
| 合并开票跨多 SO 的币种/汇率 | 金额失真 | Wave A 限单订单单币种；Wave C 再放开 |
| 派生列被手工改 | 真相源污染 | `ui.editable: false` + 守卫白名单，仅服务层可写 |

---

## 16. Oracle Fusion 深度拆解（对标依据）

> 依据：Oracle Fusion Cloud 26C 官方文档（Order Management / Receivables / SCM 三本手册），
> 源链接见 §16.8。本节只写「文档可证实」的事实，推断处明确标注「口径推断」。

### 16.1 模块地图：Fusion 没有 billing 单据层

```
Order Management (DOO)          Receivables (AR)                 Subledger / GL
─────────────────────           ─────────────────                ────────────────
sales order / fulfillment  ──►  AutoInvoice (ESS 并发程序)  ──►  SLA 会计事件 ──► GL
project / subscription     ──►        │
external interface tables  ──►        ▼
                               AR 发票（RA_CUSTOMER_TRX_ALL）
                               ├─ 发票行 RA_CUSTOMER_TRX_LINES_ALL
                               ├─ 行会计分配 RA_CUST_TRX_LINE_GL_DIST_ALL
                               ├─ 收款计划 AR_PAYMENT_SCHEDULES_ALL
                               └─ 核销/调整 AR_RECEIVABLE_APPLICATIONS_ALL / AR_ADJUSTMENTS_ALL
```

**核心事实**：OM 只负责接单与履单，**不产出任何 billing document**；开票由 AutoInvoice 跨越式完成——它直接把 OM 的履单数据（以及 Project / Subscription / 外部接口表）转成 AR 发票。因此 Fusion 里「业务单据 + 应收事务」是**同一行记录**（`RA_CUSTOMER_TRX_ALL`），不存在 SAP VBRK 那种「先出 billing document，再传 FI-AR」的两段式。

| 层 | SAP | Oracle Fusion | 我方 |
|---|---|---|---|
| 履单 | Delivery (LIKP/LIPS) | Shipment（DOO） | `shipment` / `shipment_line` ✅ 已有 |
| 开票单据 | Billing Document (VBRK/VBRP) | **不存在** | `customer_invoice`（Wave A 新建） |
| 应收事务 | FI-AR（BKPF/BSEG + 台账） | AR 发票本身（`RA_CUSTOMER_TRX_ALL`） | 不做（只出 L2） |
| 会计 | FI-GL | SLA → GL | 不做（L3） |

**对我方的意义**：Fusion 的「省掉中间单据」是**因为它把 OM 与 AR 做成同库同事务**；我方平台不做 AR 子账，若不补 `customer_invoice`，就等于把开票事实挂到发货单上——发货单一改，已开票事实就失去独立性。故 0.1 的结论（建独立 `customer_invoice`）在「不建 AR」的前提下**必须成立**，不能照搬 Fusion 的「无单据层」。

### 16.2 AutoInvoice 三阶段与发票粒度

AutoInvoice 一次运行分三段，**发票粒度由配置决定，不是 1:1**：

| 阶段 | 做什么 | 失败落点 |
|---|---|---|
| 1. Validation（校验） | 逐行校验必填、客户、地点、币种、税、会计日期、重复引用等 | 拒绝行写入 `RA_INTERFACE_ERRORS_ALL`，不出票 |
| 2. Grouping（分组） | 按 **grouping rule** 把行归并成「一张发票」；按 **line ordering rule** 定行号 | 分组键缺失时走回退链 |
| 3. Transfer（转输） | 生成 `RA_BATCHES_ALL` → `RA_CUSTOMER_TRX_ALL` / `RA_CUSTOMER_TRX_LINES_ALL` / GL 分配 / 收款计划 | 成功即产生正式发票 |

**grouping rule 决定「哪些行会合并成同一张票」**，常用分组属性：事务来源、事务类型、客户账户、开票地点（bill-to）、币种、付款条件、会计日期等。**line ordering rule** 决定同一张票内的行序（影响行号稳定性）。

**未显式绑定分组规则时的回退层级**（配置继承链，由近及远）：

```
事务来源（Transaction Source）
  → 客户地点（Customer / Site profile）
    → 客户档案（Customer profile）
      → 系统选项（System Options）
```

**对我方的映射**：

| Fusion 概念 | 我方对应 | 结论 |
|---|---|---|
| grouping rule | 无（Wave A 固定聚合键） | 用 4 元组 `(customer_account_id, currency_id, bill_to_account_id, org_id)` 硬编码（D7），不引入可配置分组规则 |
| line ordering rule | `customer_invoice_line.line_no` | 按来源类型 + 来源 id + 时间排序，服务层生成 |
| 回退层级 | 无层级配置 | **不做**。我方是「配置少、语义硬」路线，分层继承会带来隐性行为 |
| 校验拒绝行 → 错误表 | 无独立错误表 | 校验失败直接抛业务错误码，不落「待处理池」（Wave A）；批量导入场景 Wave C 再评估 |

### 16.3 类型 / 来源 / 编号 / 完成控制

Fusion 的发票由**两个配置维度**共同决定行为：

| 维度 | 关键选项 | 作用 |
|---|---|---|
| Transaction Type（事务类型） | Open Receivable / Post to GL / Natural Application / Overapplication | 是否产生应收余额、是否过总账、是否允许超额核销 |
| Transaction Source（事务来源） | 手工 / 导入（AutoInvoice 专用）；Receipt Handling for Credits；校验集合；分组规则；是否允许 Incomplete | 控制入口与校验强度 |

**编号**：Fusion 的发票号由来源（transaction source）上配置的**编号规则**决定，AutoInvoice 段内连续取号；外部系统导入可带自己的号，但需通过来源的「允许外部编号」配置。

**完成控制（Control of Transaction Completion）**——这是 Fusion 一个值得注意的机制：

- 未完成的发票状态为 **Incomplete + Pending Approval**，不参与过账；
- 三种控制方式：**External**（外部系统回调确认）/ **Role-Based**（按角色放行）/ **User-Based**（指定人放行）；
- **只对第三方导入（外部接口表）生效**；Fusion 内部上游（OM / Project / Subscription）**不允许**开启，因为它们本身就是可信源。

**对我方的映射与取舍**：

| Fusion | 我方 | 取舍理由 |
|---|---|---|
| Transaction Type 四选项 | `type_definitions(scope_bo='customer_invoice')` | 只保留「是否过账 / 是否红冲单」两类语义，不做 Natural Application 这类 AR 核销策略（属 L3） |
| Transaction Source 校验集合 | 无 | 我方只有「服务层校验 + S6 四道编号校验」，不引入来源级校验配置 |
| 外部编号 | S6 `NUMBER_FORMAT_INVALID` 等四码 | 机制等价，能力更强（格式/范围/重复/序列可用性） |
| Incomplete + Pending Approval | **不做** | 该机制存在的前提是「跨系统异步回调确认」；我方单体内同步事务，引入只会增加状态机复杂度。若未来接外部开票系统，再按 external 模式补 |

### 16.4 冲销与更正三件套

Fusion 提供三种更正手段，粒度不同：

| 手段 | 粒度 | 会计后果 | 适用 |
|---|---|---|---|
| **Credit Memo**（贷项凭证） | 行级或整单 | 冲减应收 + 冲减收入 | 部分退货、价格折让、错开金额 |
| **Adjustment** | Invoice / Line / Charges / Tax / Freight 五种 | 视 adjustment 类型 | 少收/多收、税差、运费差 |
| **Void**（作废） | 整单 | 直接抹掉，无会计痕迹 | 当天开票当天发现错误 |

**Credit Memo 的关键细节**（对 Wave C 设计有直接约束）：

- **on-account 类型**：不引用原发票，只产生「客户有余额」，不对应原票 → 我方不需要；
- **against transaction 类型**：通过 `REFERENCE_LINE_ID` 引用原发票行；若来源行没有 Fusion 的内部 id（外部导入），则用 `REFERENCE_LINE_ATTRIBUTE1-15` + `REFERENCE_LINE_CONTEXT` 做**外部行键**匹配。→ **我方 Wave C 的 `credit_memo` 应把 `source_line_id` + `line_type` 落成显式列**，不要走「15 个自由属性」那条老路。
- **有 invoicing rule 的发票**，贷项按 `CREDIT_METHOD_FOR_ACCT_RULE` 三选一冲收入：
  - **LIFO**：从最近一期开始冲；
  - **PRORATE**：按期比例摊；
  - **UNIT**：按数量冲，**贷记量不得超过原行数量**。
- 贷项的**会计日期不得早于原发票会计日期**（硬约束）。

**对我方的映射**：

| Fusion | 我方 | 决策 |
|---|---|---|
| Credit Memo（行级部分冲销） | `document_category='credit_memo'` + 行级引用 | Wave C（D8）。Wave A 只做整单红冲 |
| Adjustment 五粒度 | 不做 | 属 AR 侧核销调整，落在 L3 边界外 |
| Void | `cancelled` 只对未过账生效 | 等价：过账前 cancel 即「作废」，过账后只能 red invoice |
| LIFO / PRORATE / UNIT | 不适用 | 我方不做收入确认（无 invoicing rule），无「按期冲收入」问题 |
| 会计日期不早于原票 | `posted` 后红冲日期校验 | 需在 Wave A 服务层加一条不变量（见下） |

> **已并入 §6.3**：`R-INV-14` 红字单的 `posting_date` 不得早于原单 `posting_date`；`R-INV-15` 红字单行引用原行时，冲销数量合计 ≤ 原行数量（Wave C 启用）。

### 16.5 分期、收入确认、会计——都在 AR，不在 OM

| 能力 | Fusion 落在哪 | 关键表 / 概念 | 我方 |
|---|---|---|---|
| 分期（付款计划） | AR | `AR_PAYMENT_SCHEDULES_ALL`，**独立于发票行** | **不做**。`payment_term_id` 只作快照 |
| 收入确认排程 | AR | Invoicing rule（in advance / in arrears）+ Accounting rule / Revenue Scheduling Rule（Fixed / Variable / Daily Revenue Rate-All Periods / Daily Revenue Rate-Partial Periods） | **不做**（g15 L3） |
| 子账会计 | SLA | `RA_CUST_TRX_LINE_GL_DIST_ALL` 等分配行 → SLA 事件 → GL | 只出 L2 事件 |

**Installments 的三个可证实细节**：

1. 收款计划**不是发票行的派生**，是独立记录，可单独改到期日、未付额、增删期数；
2. 期数金额**合计必须等于发票总额**（否则校验失败）；
3. **balance forward billing** 的付款条件**不允许修改期数**（结构性锁定）。

**对我方的意义**：这条边界说明得很干净——「发票 → 收款计划 → 核销」整条链在 Fusion 里属于 AR 子账。我方不做 AR，因此：
- 不在 `customer_invoice` 上派生收款计划；
- `payment_term_id` 仅为快照（供下游 AR 系统读取），不生成期数记录；
- 收入确认完全不做（Wave A/B/C 均不碰）。

### 16.6 计划侧：Recurring Billing 与 Project Billing

**Recurring Billing（OM 订单行参数，不是单据）**：

| 参数 | 作用 |
|---|---|
| Number of Billing Periods | 期数 |
| Recurring Billing Start Date | 首期起始日 |
| Billing Frequency | 周期（月/季…） |
| Billing Plan Overrides | 每期覆盖：数量/金额，**最多覆盖 5 期**（超出需改结构） |

订单上可直接查看**每期的 Invoice Date / Invoice Number / Amount**——即「计划行 → 已生成发票」的回写视图。

**Project Billing（PPM）**：

| 概念 | 作用 |
|---|---|
| Bill Plan（计费计划） | 项目级计费策略 |
| Bill Set | 带同一 bill set 号的发票行 → **合并到同一张发票**；不同 → 拆票 |

**对我方的映射**：

| Fusion | 我方 | 结论 |
|---|---|---|
| Number of Billing Periods + Frequency | 多条 `sales_order_schedules(kind='billing')` | 语义已等价（每个计划行 = 一期），**不新建计划对象** |
| Billing Plan Overrides（≤5 期） | 计划行上可直接改 `billing_percent` / `billing_amount` | 天然支持任意期覆盖，**无需 5 期限制** |
| 订单查看每期 Invoice No / Amount | `sales_order_schedules.billed_amount` + `invoice_id` 回写 | 已在 §8 派生列设计中覆盖 |
| Bill Set 合并 | 聚合键 4 元组（D7） | Wave A 无 bill set 概念；Wave C 若需「按项目合并」再加 `billing_group_code` |

> **补充建议（并入 Wave B）**：计划行需补 `sequence_no`，避免「同一天多期」时排序不稳定（Fusion 用 line ordering rule 解决的正是这个问题）。

### 16.7 对我方既有结论的确认与修订

| # | 原结论 | Oracle 证据 | 处理 |
|---|---|---|---|
| 0.1 | 建独立 `customer_invoice` | Fusion 无 billing 层，但因其无独立 AR 边界 | **确认**（我方无 AR，必须独立） |
| 0.2 | 计划行不升级为单据 | Recurring Billing 是订单行参数 | **确认** |
| 0.3 | 不建 billing request 表 | 无对应对象（AutoInvoice 批 + 工作区） | **确认** |
| 0.5 | `posted` 后整单只读 | Void / Credit Memo 均不改原单 | **确认**，并补 R-INV-14（红冲日期不早于原票） |
| 0.8 | 不做 AR / 收入确认 / 税务 | 全在 AR 与 SLA | **确认** |
| 0.9 | 编号机制 | Transaction Source 编号规则 + 外部号 | **确认**（S6 能力更强） |
| §6.3 | 未定义红冲日期约束 | 贷项会计日期 ≥ 原票会计日期 | **新增 R-INV-14 / R-INV-15** |
| 新 | 发票聚合 | grouping rule / bill set 决定合并 | **新增 D7**（Wave A 固定 4 元组，不自动合并） |
| 新 | 部分冲销 | Credit Memo 行级 + UNIT 口径 | **新增 D8**（Wave C 做 credit_memo） |
| 不做 | Incomplete / Pending Approval | 仅第三方导入生效 | **明确排除**，写入 §16.3 |

### 16.8 源链接（Oracle 26C 官方文档）

Order Management（SCM 26C / fauom）：

- Shipment and Billing Details — https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fauom/shipment-and-billing-details.html
- Edit Recurring Billing — https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fauom/edit-recurring-billing.html

Receivables（Financials 26C / faofc）：

- AutoInvoice Import and External Data — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/autoinvoice-import-and-external-data.html
- How AutoInvoice Processes Data During Import — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/how-autoinvoice-processes-data-during-import.html
- AutoInvoice and Control of Transaction Completion — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/autoinvoice-and-control-of-transaction-completion.html
- AutoInvoice Import and Credit Memos — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/autoinvoice-import-and-credit-memos.html
- How Adjustments to Transactions Are Calculated — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/how-adjustments-to-transactions-are-calculated.html
- Guidelines for Updating Installments on Transactions — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/guidelines-for-updating-installments-on-transactions.html
- How Revenue Scheduling Rules Are Used — https://docs.oracle.com/en/cloud/saas/financials/26c/faofc/how-revenue-scheduling-rules-are-used.html

> 抓取内容本地留存于 `c:\Users\Administrator\.trae-cn\work\.trae\toolcall-output\`（三份 TOC：fauom / faofc / SCM All Books），后续如需复核可直接 grep，不必重抓。

---

## 17. Oracle CPQ（报价侧）与开票链路的衔接

> 说明：本节把用户所说的「CP」按 **CPQ（Configure, Price, Quote）** 理解；SAP 侧同类产品（SAP CPQ，原 CallidusCloud）见 **§18.9**，两者结论一致。
> 依据：Oracle CPQ 26C 在线帮助（`help-cxsales.oraclecloud.com/cpq`，静态镜像 `help.bigmachines.com/cpq/Content/`）。
> 目的：确认「报价 → 订单 → 开票」三段里，报价段是否会把结构反向拖进开票对象模型。

### 17.1 定位：CPQ 是独立云服务，不在 Fusion ERP 核心里

- Oracle CPQ（原 BigMachines）是 **独立的 Oracle Cloud 服务**，有自己的 26C 版本与帮助站点；
- 它通过 **Oracle Integration Cloud（OIC）** 或预置集成包与 OM / ERP / EBS / Subscription Management 对接；
- **CPQ 不含任何开票/应收能力**——报价确认后交给 Order Management 建单，之后的开票仍在 AR 侧（见 §16.1）。

对我方：**CPQ 不是参照对象，而是「上游缺的那一段」**。我方的 `sales_order` 目前既是下单入口也是价格快照来源，没有报价层；但这不构成本 spec 的缺口，开票对象不依赖报价存在。

### 17.2 CPQ 的单据对象：Commerce Transaction + Stage

| 概念 | 含义 |
|---|---|
| Commerce Process | 可部署的**流程模板**，定义报价/下单/审批的工作流；未 deploy 前对生产不可见 |
| Standard Process（23B+） | 默认流程，提供标准化 quote 对象并预置组件与系统逻辑 |
| Stage | 事务生命周期的阶段：**Quote**（默认）/ **Order** / **Agreement**，可裁剪 |
| 编辑模式 | Collaborative（多人同时）/ Transaction Locking（单人锁定）/ Single User（后者可覆盖前者） |

**关键结论**：CPQ 用「stage」表达**流程推进**，而不是业务状态机；它没有 `posted` 这类会计时点，也没有开票状态。因此：

- 我方 `customer_invoice` 的 `status`（draft/submitted/posted/…）**不需要对齐 CPQ 的 stage**；
- 也不要为了「像 CPQ」给 SO 增加 Agreement 阶段——合同属独立对象，不在本期范围。

### 17.3 配置与定价：能力很重，但与本 spec 无关

| 维度 | CPQ 的做法 |
|---|---|
| 产品层次 | 四级：All Product Families → Product Family → Product Line → Model；属性/规则/动作/流程**向下继承**，尽量定义在高层级 |
| 配置 | Configurable Attributes + Configuration Rules + Configuration Flows + Configuration Actions；`product definition` 与 `catalog` 需显式 deploy |
| 定价 | 多 Price Book；价格模型三类：Price List / Discount List / Markup List；Attribute-based Matrix Pricing；Rate Card **仅用于 usage 价型**（Price List 模型） |
| 费用类型 | 区分**一次性费用**与**经常性费用**，报价页实时联动 |

**对我方的取舍**：这些都是「报价侧」能力。我方按 SO 行价格快照开票（R-INV-6），**不引入价目表/矩阵/折扣引擎**；若未来要做 CPQ，应单独立项，不能塞进开票 spec。

### 17.4 接缝：报价怎么变成订单与周期账单

```
CPQ transaction(stage=Order) ──integration action──► Order Management sales order
                                                        │
                                     Subscription Mgmt（OIC）──► 周期性/用量价格项
                                                        │
                                                        ▼
                                              开票（AR / 我方 customer_invoice）
```

- 集成以 **integration action** 为触发点：`order_start`（创建订单）、`order_update`（更新）、`order_reject`（拒单）等；
- **Subscription Management 集成**（经 OIC）把报价里的订阅型产品转成**周期性 / 用量型价格项**，这是 CPQ 与账单周期唯一的结构性联系；
- CPQ 到 EBS 还额外提供 Inventory On Hand / Material Reservation 可选集成（与开票无关）。

**对我方的意义（确认 §16.6）**：Oracle 的「周期账单」源头是**报价行的经常性费用 → 订阅价格项 → 周期开票**，Fusion 内部同样不产生 billing 单据层。这与我方「`sales_order_schedules(kind='billing')` 每期一条」是同一抽象，只是我方把期次直接放在计划行上，省掉了订阅对象。

### 17.5 对既有结论的影响

| # | 结论 | CPQ 证据 | 处理 |
|---|---|---|---|
| 0.1 | 建独立 `customer_invoice` | CPQ 不含开票，确认开票是独立下游 | **确认** |
| 0.2 | 计划行不升级为单据 | 经常性费用是报价行属性，非单据 | **确认** |
| 0.4 | 开票触发源 | CPQ 只触发建单，不触发开票 | **确认**（开票源头仍是发货/计划/服务确认） |
| §16.6 | 计划侧只需期次 + 覆盖 | 订阅价格项 → 周期开票 | **确认** |
| 新 | 是否引入报价对象 | CPQ 是独立产品，能力极重 | **本期不做**；若要做另立 spec（D9：报价域不进本期） |
| 新 | 是否引入 stage 概念 | stage 是流程推进，不是业务状态 | **不引入**，保持 S1 状态矩阵 |

> **D9（建议）**：报价（Quote/CPQ）域**不纳入**本次销售开票对象模型；`sales_order` 仍是最上游入口，开票链路从 SO 开始建模。

### 17.6 源链接（Oracle CPQ 26C）

- CPQ 26C 帮助首页 — https://help-cxsales.oraclecloud.com/cpq/
- Commerce Process 概览 — https://help.bigmachines.com/cpq/Content/Commerce_Process/Commerce_Process_Overview.htm
- Product Configuration 概览 — https://help.bigmachines.com/cpq/Content/Configurations/ProductConfiguration.htm
- Integration 概览（含 Subscription / EBS） — https://help.bigmachines.com/cpq/Content/Integrating_With_BigMachines/Integration_Guides/Integration_Guide.htm
- Manage Pricing — https://help.bigmachines.com/cpq/Content/Products/ManagePricing.htm
- Pricing Matrix Templates（动态矩阵定价） — https://help.bigmachines.com/cpq/Content/Manage_Pricing/pricingMatrixTemplates.htm
- CPQ 产品页（中文，含「直接连接 ERP 与 Order Management」表述） — https://www.oracle.com/cn/cx/sales/cpq/

---

## 18. SAP S/4HANA 销售开票（SD Billing）深度拆解

> 依据：SAP 官方件（SAP Note 400000《FAQ: VF11 Cancellation of SD Billing Documents》及关联 Note 978098 / 147149、SAP Fiori Apps Library F0798、SAP 2018 Q1 财报）+ 权威字段字典镜像（leanx.eu / summit-bi.com）+ SAP 学习资料。
> 取证限制：`help.sap.com` / `api.sap.com` 正文为 JS 渲染，直接抓取返回空；故**字段级事实用字段字典镜像交叉确认，官方流程事实用 SAP Note / Fiori 库确认**。未能逐字确认的条目以 ⚠️ 标注。
> 与 §16（Oracle Fusion）、§17（Oracle CPQ）结构对齐，便于三方对照。

### 18.1 模块地图：SAP 有独立开票单据，且「保存即过账」

```
VBAK/VBAP (销售订单) ──► LIKP/LIPS (交货) ──┐
        │                                    ├──► VBRK/VBRP (开票单据)
        └──────── billing plan (FPLA/FPLT) ──┘            │
                                                          │ 保存时同步过账
                                                          ▼
                                            BKPF/BSEG ──► ACDOCA (Universal Journal)
                                                          │
                                                          ▼
                                                   FI-AR (客户/总账)
```

| 层 | SAP | Oracle Fusion | 我方 |
|---|---|---|---|
| 计划 | Billing Plan `FPLA/FPLT`（挂订单行） | 订单行 Recurring Billing / PPM Bill Plan | `sales_order_schedules(kind='billing')` |
| 开票单据 | **有**：`VBRK/VBRP`，独立号码段 + 独立状态 | **无**：AutoInvoice 直接生成 AR 发票 | **有**：`customer_invoice` + `_line`（本 spec） |
| 应收 | FI-AR（独立模块） | AR 子账 + SLA | 只出 L2 会计事件 |

**三点关键差异（决定我方设计）**：

1. **SAP 的「开票单据」是独立事实单据**——有自己的 `VBELN` 号码、`FKSTO` 已冲销标志、`RFBSK` 过账状态，可独立冲销并生成取消单据 [1]。这印证 §0.1：我方建 `customer_invoice` 是对的，不是过度设计。
2. **SAP 保存开票即生成 FI 凭证**（`BELNR/GJAHR` 回写 `VBRK`），没有「草稿」阶段；单据有错误时以 `RFBSK` 冻结、不产生会计凭证 [1][6]。我方 `draft → submitted → posted` 比 SAP 多一个草稿态，但**语义等价于 SAP 的 error/incomplete**，且更适合「先建单、后审核」的业务。
3. **FI 不会反向生成开票**——单向派生。我方同理：会计事件只能由 `posted` 触发，不能由 L2 回写业务单据。

### 18.2 `VBRK` / `VBRP` 关键字段与映射

| SAP 字段 | 表 | 含义 | 我方对应 |
|---|---|---|---|
| `VBELN` | VBRK | 开票单据号（按开票类型号码段） | `invoice_no` |
| `FKART` | VBRK | 开票类型（4 位，控制键） | `document_type_id` |
| `FKTYP` | VBRK | 开票类别（1 位，业务归类） | 由 `type_definitions` 的 `scope_bo` + 类型属性承载 |
| `FKDAT` | VBRK | 开票日期 | `invoice_date`（business_date_field） |
| `KUNAG` | VBRK | 售达方 | `customer_account_id` |
| `KUNRG` | VBRK | 付款方 | `payer_account_id` |
| `NETWR` / `WAERK` | VBRK | 净额 / 单据货币 | `net_amount` / `currency_id` |
| `KURRF` | VBRK | FI 过账汇率 | `exchange_rate` |
| `BELNR` / `GJAHR` | VBRK | 会计凭证号 / 年度 | 不落业务表（L2 事件回执） |
| `SFAKN` / `FKSTO` | VBRK | 被冲销单据号 / 已冲销标志 | `reversal_of_invoice_id` / 原单 `status='reversed'` |
| `VGBEL` / `VGPOS` / `VGTYP` | VBRP | 来源单据 / 行 / 类别 | `source_doc_id` / `source_line_id` / `source_doc_type` |
| `AUBEL` / `AUPOS` | VBRP | 来源销售订单 / 行 | `order_line_id` |
| `FKIMG` / `MWSBP` | VBRP | 开票数量 / 行税额 | `qty` / `tax_amount` |

**两处结构性差异**：

- SAP **收票方（bill-to）不是 VBRK 字段**，而是伙伴角色 `RE` 存在 `VBPA`（多伙伴角色：AG 售达、WE 送达、RE 收票、RG 付款）⚠️。我方采用**扁平化**（`customer_account_id` / `bill_to_account_id` / `payer_account_id` 三列），是有意的简化，本期不建伙伴角色表；代价是「一单多伙伴」场景不支持，属可接受范围。
- SAP 行级**不存单价快照**，定价条件（KONV）在订单/开票条件表里；我方按 R-INV-6 落 `unit_price` 快照，比 SAP 更利于单据自证，但需承担「改价不回写」的一致性约束。

### 18.3 开票类型（FKART）与开票类别（FKTYP）

`FKART` 是**控制键**，在 `TVFK` 中决定：号码段（`NUMKI/NUMKE`）、科目确定过程（`KALSMC`）、定价过程（`KALSM`）、取消类型（`FKARTS`）、过账/冻结控制 [3]。
`FKTYP`（1 位）只是**业务归类**，由类型带出：A 订单相关、L 交货相关、D 周期开票、R 发票清单、U 开票请求、P 预付款请求、I/S CRM 相关 [1][3]。

标准交付件示例（项目配置可能不同）[6]：

| `FKART` | 业务含义 | 是否过账 | 我方对应（Wave） |
|---|---|---|---|
| `F2` | 标准发票 | 是 | `customer_invoice`（Wave A） |
| `G2` | 贷项凭证（credit memo） | 是（冲应收） | Wave C `document_category='credit_memo'` |
| `L2` | 借项凭证（debit memo） | 是（增应收） | 本期不做 |
| `RE` | 退货贷项 | 是 | 不做（退货走采购/库存侧） |
| `S1` / `S2` | 取消单据（F2 / G2 的取消类型） | 是（冲销原凭证） | Wave A 整单红冲，红字单独立取号 |
| `F5` / `F8` | 形式发票（pro forma） | **否** | 不做 |
| `LR` / `LG` | 发票清单（invoice list） | 是 | 不做（对应「合并开票」，Wave C） |
| `FAZ` | 预付款请求（advance payment） | 是 | 不做 |

**对我方最重要的两条**：

1. **「形式发票」与「正式发票」是不同开票类型，且形式发票不过账**——我方不需要形式发票类型，但 UI 上若要「预览/暂存」，正确做法是用 `draft` 状态，而不是新增单据类型。
2. **取消单据本身有独立号码和独立类型**（`FKARTS` 指定）——这印证 R-INV-0：红字单必须独立取号，不能复用原单号加后缀。

### 18.4 开票计划：`FPLA` 头 + `FPLT` 日期行

| 层级 | 字段 | 含义 |
|---|---|---|
| `FPLA`（头） | `FPLNR` | 计划号 |
| | `FPART` | 计划类型（决定日期规则与用途） |
| | `BEDAT` / `ENDAT` | 计划起 / 止日 |
| | `HORIZ` | Horizon（只展开未来一段日期） |
| | `AUTTE` | 提前开票规则 |
| | `AUTKOR` | 自动更正日期 |
| `FPLT`（行） | `FPLTR` | 日期行号 |
| | `FPTTP` | 日期类别 |
| | `FKDAT` | 期限日期（deadline，数据元素 `BFDAT`） |
| | `AFDAT` | **实际开票日期**（数据元素为 `FKDAT`） |
| | `FAREG` | 开票规则 |
| | `FPROZ` | 百分比 |
| | `FAKWR` | 应开票值（固定金额规则用） |
| | `FKSAF` | 计划行开票状态：A 未处理 / B 部分 / C 已开票 / D 拒绝 / E 已请求 |
| | `FPFIX` | 里程碑取日方式 |

开票规则（`FAREG`）标准取值 [5]：1 百分比、2 固定金额、3 结算/尾票（final settlement）、4/5 预付款、6 周期计费。期间指向（`UEVOR`）：0001 提前周期、0002 追溯周期、0003 里程碑 [5]。

**一张订单行挂一个计划，多个日期行分别开票 → 一张订单可产生多张发票**——但这条只在行项目开票相关性 `VBAP-FKREL = I`（订单相关 + billing plan）时成立，详见 §18.4.1。

### 18.4.1 场景推演：3 批发货 × 2 期里程碑（50% / 50%）

**结论：SAP 是「行项目级二选一」，不是主从叠加。** 计划与发货谁做锚，由行项目的 `VBAP-FKREL`（开票相关性，由项目类别 `TVAP-FKREL` 带出）唯一决定，一行只能取一个值。

| `FKREL` | 开票数量来源 | 时点 / 金额来源 | 3 批发货 + 2 期里程碑的实际结果 |
|---|---|---|---|
| **`I`**（订单相关 + billing plan，挂计划的标准取值） | 订单行数量，**不看 `LIPS-LFIMG`** | `FPLT` 日期行：到期日 + `FAREG` 规则 | **2 张票**，各 50% 订单净值；3 张交货**不产生发票**，交货开票状态也不更新 |
| **`A`**（交货相关） | 已交未开票量（`LIPS-LFIMG`） | 交货单 `LIKP-FKDAT` | 2 期比例**不生效**；按 3 批交货出 **1~3 张票**（抬头字段一致可合并为 1 张） |
| **`G`**（订单相关、按累计交货数量） | 累计已交货量，可合并多批 partial delivery | 订单 / 交货 | 可把 3 批合并成 1 张票，但**不带 billing plan** |
| **`K`**（交货相关、部分数量开票） | 手工挑选交货 / 部分数量 | 交货 | 可做「按里程碑挑数量」（如 70/30），是常见的变通做法 |

**三条机制要点**：

1. **二选一发生在「开票相关性」，不是「计划 vs 发货」本身**：`FKREL` 是行项目单一值，不能一行同时 A 和 I。
2. **计划行状态字段是 `FPLT-FKSAF`**（A/B/C/D/E），不是常被误传的 `FAKST`；状态到 C 后该日期行**不能再开票**（SAP 原文：prevents a billed date from being billed again）。
3. **到期清单有两条独立来源**：订单相关（含计划日期）与交货相关，VF04 **不取交集**；开票阻塞优先级为「日期行 > 行项目 > 抬头」。

**要做到「3 批发货 + 2 期票」怎么办**（SAP 标准无直连机制）：

| 方案 | 做法 | 代价 |
|---|---|---|
| a. `I` + 里程碑阻塞 | 按计划开票，发货/验收只作为里程碑的阻塞条件 | 金额仍按比例，**不与交货量互校**；少发/超发不会自动修正发票 |
| b. `A` + `K` | 交货相关，按里程碑手工挑交货数量（如 70/30） | 计划比例靠人守，容易漏开 / 超开 |
| c. 自开发 | 把 `FPLT` 带入交货开票校验 | 非标，升级与回归成本高 |

**对我方 D10 / D11 的直接含义**（D10 = 开票主锚，D11 = 一期能否分次开票；D9 已被 §17.5 占用为「报价域不进本期」）：

- 上一轮建议的「主从模式」（数量以发货为准、金额以计划比例为准）**不是 SAP 标准做法**，而是自研扩展。SAP 的选择是：要么**计划主**（`I`，数量看订单）、要么**交货主**（`A` / `K`，金额看交货）。
- 主从模式已被放弃（**D10 ✅ 二选一**）：SAP 用 `FKREL` 规避的两个问题——同一行不能有两个数量口径、计划行与交货行进度不能互相覆盖——我方改用行级单值枚举 + 互斥回写解决。
- 枚举落在**销售订单行** `billing_relevance`（`delivery` / `plan` / `none`），不等发票行再决定；R-INV-3 已由「发票行级二选一」升级为「必须与订单行取值一致，且跨发票不得混用」，粒度问题已消除。落地设计见 **§20**。

与我方 `sales_order_schedules` 对照：

| SAP 能力 | 我方现状 | 差距处理 |
|---|---|---|
| 日期行 + 百分比 / 金额 / 尾票 | `schedule_kind='billing'` + `billing_percent` / `billing_amount` / `milestone_code` | **已覆盖** |
| 周期计费（规则 6） | 无「周期模板」概念，靠多行手工铺 | Wave B 再评估，不在 Wave A 做递归展开 |
| Horizon | 无 | **不做**（我方计划行有限且人工维护） |
| 自动更正日期 | 无 | **不做** |
| 提前 / 追溯周期 | 无 | **不做** |

**结论**：SAP 的 `FPLT` 与我们的计划行是同一抽象；差异集中在「无限期周期计划」的自动展开，这属于 Wave B（订阅/租赁）范畴，不污染 Wave A。

### 18.5 到期清单（Billing Due List）：程序，不是表

- `VF04` 是**事务码**，执行选择程序后**即时生成工作清单**；后台批处理为 `VF06`；**不存在持久化的「到期清单」表**（行业通识 + 依赖程序 `SDBILLDL`，⚠️）[6]；
- 到期判定：开票日期（含计划日期）已到 + 开票冻结已释放 + 前序单据开票状态未完成 [6]；
- S/4HANA 的 Fiori 应用 **Create Billing Documents（F0798）** 可直接从到期清单建单，并支持先生成**临时开票单据**校验、再转正式；经典 VF04 仍保留 [6]。

**对我方的印证**：§0.3「不建到期清单表，用查询/视图」与 SAP 完全一致。Fiori 的「临时单据」也可用我方 `draft` 状态承载，无需新增对象。

### 18.6 更正与冲销：SAP 有两套手段，语义不同

| 手段 | 产生什么 | 关键字段 / 约束 | 我方对应 |
|---|---|---|---|
| `VF11` 取消 | **取消单据**（类型由 `TVFK-FKARTS` 指定，F2→S1、G2→S2），不重新定价、不重跑科目确定 | 取消单 `SFAKN` 指回原单；原单 `FKSTO=X`、`RFBSK='E'`；FI 生成冲销凭证 [1][3][7] | Wave A 整单红冲（`reversal_of_invoice_id` + 原单 `reversed`） |
| 贷项凭证申请 `CR` → 开票类型 `G2` | 贷项凭证（**独立业务单据**，减少应收） | 申请单本身不是会计凭证，须再开票 [6] | Wave C `credit_memo` + 引用原发票行 |
| 借项凭证申请 `DR` → `L2` | 借项凭证（增加应收） | 同上 | 不做 |
| 发票更正申请 `RK` | 更正类发票 | 同上 | 不做 |

**两条硬约束（支撑我方 D8）**：

1. **SAP 允许行项目取消，但 FI 凭证会被整张冲销**（SAP Note 978098 / 147149），因此**同一张发票不能被多次部分冲销** [7]。这说明「部分冲销」在 SAP 也要靠 `G2` 贷项凭证，而不是反复 `VF11`。我方 D8「Wave A 整单红冲、Wave C 才做行级贷项」的分层与 SAP 一致。
2. **保存后关键字段（开票日期、客户、物料、数量、金额）不可改，仅文本/分配类可改**；错误只能冲销重建 ⚠️（培训/社区共识，无单一官方条目）。这印证 §6.2 的 S1 矩阵：`posted` 后整单只读，且 `submitted` 起冻结关键字段。

**命名建议（重要）**：SAP 把「取消单据」和「贷项凭证」分得很清。我方 §0.12 目前统一叫「整单红冲 / red invoice」，落地时应明确：**Wave A 的红字单是「取消单据（cancellation）」，不是「贷项凭证（credit memo）」**。二者差异：

- 取消单据：**全额、一对一、原单标记 `reversed`**，目的是「这张票作废」；
- 贷项凭证：**可部分、可不对应原单**（on-account），目的是「少收钱」，原单仍有效。

建议 `customer_invoice` 增加 `document_category` 枚举（`invoice` / `cancellation` / `credit_memo`），Wave A 只实现前两个值，Wave C 补第三个——避免用同一个「红冲」词表达两种业务。

### 18.7 收入确认：S/4HANA 已把开票与收入确认解耦

- 经典 SD 收入确认（组件 `SD-BIL-RR`，事务 `VF44/VF45`）在 **S/4HANA 不再提供**，改用 **RAR（Revenue Accounting and Reporting，IFRS 15）** [8]；
- 财务侧另有 **Event-Based Revenue Recognition（EBRR）**，按业务事件在总账/CO-PA 确认 ⚠️（第三方文章）；
- 因此开票只把应收 / 税 / 收入过账进 `ACDOCA`，**履约义务的确认时点由 RAR / EBRR 决定**，与开票日期解耦 [6][8]；
- S/4HANA 的分析真源是 `ACDOCA`（Universal Journal）；`BKPF/BSEG` 仍存在，但不再是对外的分析口径 ⚠️。

**对我方的印证**：§0.8「只做 L1 发票 + L2 会计事件，不做收入确认」与 SAP 的分层完全一致。同时说明：**不要**在 `customer_invoice_line` 上加「收入确认日期 / 履约义务」字段——那是 RAR 域的职责。

### 18.8 订阅与用量计费：BRIM 在 SD 之外

- **BRIM** = SOM（Subscription Order Management）+ Convergent Charging（批价）+ **Convergent Invoicing（CI）** + FI-CA（合同应收），运行于 S/4HANA [9]；
- **SAP Subscription Billing** 是公有云形态的订阅管理 / 计价 / 计费 [9]；
- 周期与用量计费对象落在 SOM / CI（billable item → invoicing document → FI-CA）或 Subscription Billing，**不经 SD 的 `VBRK`** ⚠️（分层为官方，具体对象归属为通识推断）[9]。

**对我方的取舍**：我方不引入 BRIM 的「billable item → invoicing document」两级对象。理由与 §16.6 / §17.4 相同——**期次直接挂在计划行上**已能表达「第 N 期、多少钱、什么时候开」。若未来做用量计费，应单独立项，不在 `customer_invoice` 上叠用量明细。

### 18.9 SAP CPQ：与 Oracle CPQ 同构，同样不含开票

- SAP 于 **2018-04-05** 完成 CallidusCloud 收购（US$36/股，约 24 亿美元），CPQ 并入 SAP CX 产品线 [10]；
- 职责：产品配置、定价规则、报价与合同生成；
- 接缝在「**报价 → 订单**」：报价确认后进 S/4 销售订单，再由 SD / BRIM 开票；**CPQ 自身不开票** ⚠️（官方仅述其覆盖配置/定价/报价/合同）[10]。

**结论**：无论「CP」指 Oracle CPQ 还是 SAP CPQ，结论一致——**报价域是上游独立产品，不改变开票对象模型**。§17.5 的 D9（报价域不纳入本期）对 SAP 侧同样成立。

### 18.10 对既有结论的影响

| # | 结论 | SAP 证据 | 处理 |
|---|---|---|---|
| 0.1 | 建独立 `customer_invoice` | `VBRK/VBRP` 是独立事实单据，独立取号/冲销 | **强确认** |
| 0.2 | 计划行不升级为单据 | `FPLA/FPLT` 是计划，不是发票 | **确认** |
| 0.3 | 不建到期清单表 | VF04/VF06 是程序，无持久化表 | **确认** |
| 0.4 | 开票触发源（发货/计划/手工） | SD 以 delivery 为主源，计划日期行为次源 | **确认** |
| 0.5 | `posted` 过账点 | SAP「保存即过账」+ `RFBSK` 冻结；我方多一个 draft | **确认**（差异合理） |
| 0.8 | 不做收入确认 | S/4 已把 RR 移到 RAR/EBRR | **确认** |
| 0.11 | Wave A 一发货单一张票 | SAP 默认按 delivery 开票，`LR` 才合并 | **确认** |
| D7 | 不自动合并 | 合并需发票清单 `LR`（独立类型） | **确认** |
| D8 | Wave A 整单红冲 / Wave C 贷项 | `VF11` 整单冲销 vs `G2` 贷项凭证，SAP 也分层 | **确认**，并补命名区分（见 §18.6） |
| **D10** | **开票主锚（计划主 / 交货主 / 自研主从）** | **`VBAP-FKREL` 行项目单一值，只能二选一**：`I` = 计划主（数量看订单）、`A`/`K` = 交货主（比例失效） | **✅ 已定：二选一**，放弃自研主从；行级枚举 `billing_relevance`，落地设计见 §20 |
| **D11** | **一期计划能否分次开票（部分开票）** | `FPLT-FKSAF` 有 `B`（部分），说明允许部分处理；但到 `C`（已开票）后同一日期行**不可再开**，累计不得超该期比例 | **建议允许**（`partial` 状态），但受 R-INV-17 比例上限约束 |
| 新 | 伙伴角色表 | SAP 用 `VBPA` 存 4 种伙伴角色 | **本期不建**，维持三列扁平化 |
| 新 | 已开票量回写 | SAP 靠 `VBFA` 关系 + 行开票状态推算 | **需补列**（见下） |

### 18.11 两条不变量（已并入 §6.3 的 R-INV-16/17）

| 编号 | 规则 | 依据 |
|---|---|---|
| R-INV-16 | 开票过账时必须**原子回写**来源进度：`shipment_line.billed_qty`（或计划行 `billed_amount`）在 `posted` 同一事务内递增；回写以「已开票合计 ≤ 来源可开量」为条件更新，防并发超开 | SAP 用 `VBFA` + 开票状态保证不超开；我方缺进度列，靠反查 Σ 在并发下不可靠（呼应上一轮「2 期 vs 3 批发货」结论） |
| R-INV-17 | `billing_basis='percent'` 行必须以**计划行金额 × 比例**反算净额，且该计划行累计比例 ≤ 100%；不得用单价 × 数量口径 | SAP `FPLT-FPROZ` 是百分比语义，金额由计划金额派生，不是数量 × 单价 |

> **D10 已定 = 二选一**，因此这两条不再「同时生效」，而是**按分支各管一路**：
> - `delivery` 行：R-INV-16 生效（防并发超开）；R-INV-17 不适用。
> - `plan` 行：R-INV-17 生效（比例反算 + 累计 ≤ 100%）；R-INV-16 不适用，`shipment_line.billed_qty` 恒 0。
>
> **前提订正**：SAP 是**行级二选一**（`VBAP-FKREL`）；「主从」（数量以发货为准、金额以计划比例为准）属于**自研扩展**，不是 SAP 标准做法，本 spec 已放弃（§19.3 结论 1）。

### 18.12 源链接

- VBRK 字段字典（FKTYP / SFAKN / FKSTO / KURRF / BELNR） — https://leanx.eu/sap/table/vbrk/
- VBRP 字段字典（VGBEL / VGPOS / AUBEL / FKIMG） — https://www.summit-bi.com/resources/sap-reference/tables/VBRP
- TVFK 开票类型控制字段（NUMKI / NUMKE / KALSMC / FKARTS） — https://leanx.eu/sap/table/tvfk/
- FPLA 开票计划头（FPLNR / HORIZ / AUTTE / AUTKOR） — https://leanx.eu/sap/table/fpla/
- TFPLA 计划类型与开票规则（FAREG / UEVOR / FPTYP） — https://leanx.eu/sap/table/tfpla/
- 开票类型 / 类别 / 到期清单 / 过账与 ACDOCA — https://open-exam-prep.com/study-guides/sap-s4hana-sd/billing-financial-integration/billing-types-due-list
- SAP Note 400000《FAQ: VF11 Cancellation of SD Billing Documents》（含 978098 / 147149） — https://www.stechno.net/repository/sap-notes.html?id=400000
- Eursap：S/4HANA 不再提供 SD Revenue Recognition、迁移 RAR — https://eursap.eu/blog/migration-to-sap-revenue-accounting-and-reporting-sap-rar
- SAP BRIM 组成与 Subscription Billing 对比 — https://www.bpc.ag/dienstleistungen/sap-billing/sap-brim/
- SAP 2018 Q1 报表（CallidusCloud 收购完成） — https://cdn.pressebox.de/a/eb862edbb17d6fdb/attachments/0968336.attachment/filename/sap-2018-q1-statement.pdf

> 说明：`help.sap.com` 正文抓取返回空（JS 渲染）；上述字段字典镜像与 SAP Note 为本轮可验证的一级/二级证据，未逐字确认项已标 ⚠️。

---

## 19. 其他头部 ERP 对标（第二轮：D365 / NetSuite / Workday / Infor / Odoo / 用友 / 金蝶）

> 目的：验证「里程碑计划与发货，到底是二选一还是主从结合」这个判断在行业里是否普遍。本节只做结论级对比。

### 19.1 一张总表

| 产品 | 单据链 | 独立开票单据 | 计划挂在哪 | 计划 vs 发货 | 3 批发货 × 2 期 50/50 的结果 |
|---|---|---|---|---|---|
| SAP S/4HANA | VBAK/VBAP → LIKP/LIPS → VBRK/VBRP → ACDOCA | 有，保存即过账 | `FPLA/FPLT` 挂订单行 | **行级二选一**（`VBAP-FKREL`） | `I` → 2 张各 50%；`A` → 1~3 张、比例失效（§18.4.1） |
| MS Dynamics 365 F&SCM | SalesTable/SalesLine → CustPackingSlipJour → CustInvoiceJour → Voucher | **无**开票申请层；`Posting=Yes` 才落 `CustInvoiceJour` | 核心订单无计划；计划在 Subscription billing / 项目计费旁路 | 过账参数 `Quantity`：`Packing slip`（按发货）/ `All`（按订单，可早于发货） | 3 张 30/30/40；要 2 张 50 需两次订单直开改数量，或走订阅/里程碑模板 |
| NetSuite | salesorder → itemfulfillment → invoice / creditmemo | Invoice 独立，保存即入 GL（无 posting 动作） | `billingschedule` 挂订单头或行 | **默认「计划定金额 + 发货作闸门」**：可履约品须先履约、首期开完才推进；开 `Invoice in Advance of Fulfillment` 才可先于发货 | 默认 3 张 30/30/40；开偏好 + 50/50 计划 → 2 张各 50 |
| Workday Financials | Customer Contract → Billing Schedule → Installment → Customer Invoice | **有**：Installment 即开票申请，发票审批后入账 | Billing Schedule 挂**合同**，不挂订单 | **二选一**：`Billing Type` = `Installment`（只认金额/日期）/ `Transaction`（认履约交易） | Installment 型 → 2 张各 50，发货不参与 |
| Infor LN | Sales Order → Delivery → Sales Invoice（Invoicing） | 有：`Release to Invoicing` → `Post` | Installment Plan 挂 Invoice-to BP | **二选一**：`Invoicing by Installments` 开/关 + 订单类型 `Invoice by` | 开分期 → 2 张各 50；关分期 → 3 张 30/30/40；混用须拆单 |
| Infor M3 | Customer Order → Delivery → Invoice（OIS180） | 无正式申请层，开票即记账 | 无里程碑分期，仅预付款 OIS105 | 固定按交货（`auto level` 控制） | 3 张 30/30/40；带预付款 = 1 张预付 + 尾款 |
| Odoo | sale.order → stock.picking → account.move | 无；须 `Post` 才入账 | 核心无计划；里程碑用 `project.milestone` | **行级三选一**（`product.invoice_policy`）：`order` / `delivery` / `delivered_milestone` | order → 1 张 100；delivery → 3 张 30/30/40；milestone → 2 张 50/50 |
| 用友 YonBIP / U9 | 销售订单 → 发货单 → 销售出库 → 销售发票 → 应收单 | 有；发票审核转应收/应收事务 | **无开票计划**；只有「收款计划」（收款协议） | **单级可配置**：开票依据 = 订单 / 发货单 / 出库单 | 按发货 → 3 张 30/30/40；按订单（预开票）→ 2 张 50/50，发货不参与 |
| 金蝶 云·星空 | 销售订单 → 发货通知 → 销售出库 → 应收单 → 销售发票 | 有，但**方向相反**：应收先立账，发票只做「开票核销」 | 「收款计划」挂订单头，**控收款/控发货，不控开票** | **两级串联**：计划 → 发货 → 开票（每级单一口径） | 按出库 → 3 张 30/30/40；要 2×50 只能预开票再核销应收 |

### 19.2 五种范式（本节核心）

| 范式 | 控制点 | 代表产品 | 特征 |
|---|---|---|---|
| **A 行/单级二选一** | 订单行或订单头一个枚举 | SAP `FKREL`、Odoo `invoice_policy`、Infor `Invoicing by Installments`、用友「开票依据」、Workday `Billing Type` | 一行/一单只能有一种数量口径；换口径要改建单参数 |
| **B 计划定金额 + 发货作闸门** | 计划为主，发货是布尔前置条件 | **NetSuite**（唯一） | 最接近「主从」的实现，但金额只有**一个**口径（计划）；发货只回答「能不能开」 |
| **C 计划管发货、发货管开票（两级串联）** | 两级各自单口径 | **金蝶**、用友「收款计划」 | 看起来"都参与"，实为串行，不是并行双口径 |
| **D 无计划，纯按发货** | 过账参数 / 交货状态 | D365 核心、Infor M3、Odoo `delivery` | 计划能力在旁路产品（订阅计费 / 项目计费） |
| **E 计划在合同/订阅层，订单不参与** | 合同 + 期次 | Workday Installment、SAP BRIM、D365 Subscription billing | 订单只是履约凭证，开票锚上移到合同 |

### 19.3 关键结论：行业里不存在「双口径并行主从」

1. **没有任何一个产品同时用「发货数量」和「计划比例」两个独立口径去算同一张发票，更不会互校。** 7 个产品中 6 个是单口径；唯一像主从的 NetSuite 也只是「金额口径唯一（计划）+ 发货作布尔闸门」。
   **例外修正（2026-11-08 补）**：Infor LN 的 `Direct Settlement` / `Indirect Settlement` 确实实现了「金额看分期计划、数量看交货」并行，但**载体是两张发票流 + 结算对冲**（分期发票只记金额、货票只记数量，打印货票时冲减分期余额），不是一张发票两个口径。详见 §22.5。该修正**不影响** D10 二选一结论：一张发票仍然只有一个口径。
2. 「主从」在行业里有三种**互不相同**的含义，容易混淆：
   - **B 型**：计划定金额、发货定「可否开」（NetSuite）；
   - **C 型**：计划定发货、发货定开票，两级串联（金蝶 / 用友收款计划）；
   - **E 型**：计划上移到合同、订单不参与（Workday / 订阅计费）。
3. **「收款计划」≠「开票计划」**：用友、金蝶标准的「收款计划 / 收款协议」控制的是**收款与发货**，不控制开票。这印证 §2 的判断——我方当前字段名（收款比例/收款金额/收款日）确实是语义债，且 D3「只改文案」需重新确认：**它到底是收款计划还是开票计划**，在国产 ERP 里这是两个对象。
4. **业务发票 ≠ 税务发票（国内特有）**：用友/金蝶均为「业务发票（或应收单）→ 开票申请 → 金税/数电票 → 回写发票号与开票金额」；红字必须与原蓝字绑定，专票要先申请红字信息表。我方 `customer_invoice` 目前只有一个 `invoice_no`，需明确它是**业务单号**，税务票号另行存放。

### 19.4 对我方 D10 / D11 的影响

| 决策 | 行业证据 | 结论 |
|---|---|---|
| **D10 开票主锚** | 6/7 产品单口径；唯一「主从」是 B 型（金额单口径 + 发货闸门） | ✅ **已采纳二选一**：枚举落 `sales_order_line.billing_relevance`（`delivery` / `plan` / `none`），默认 `delivery`，`plan` 留 Wave B。双口径主从不做。落地设计见 §20 |
| **D10 备选（若一定要「计划 + 发货」）** | NetSuite 是唯一可行范式 | 已否决。若未来业务强制要求，改用 **B 型**（金额只按计划、发货只作闸门），**不做数量互校**，且不需要 `shipment_line.billed_qty` |
| **Wave A 裁剪** | 多数产品核心订单无开票计划（D365 / Infor M3 / Odoo `delivery`） | `delivery` / `none` 支持；`plan` 建列但入口 fail-closed（§20.9），Wave B 打开 |
| **D11 一期能否分次开票** | SAP `FKSAF=B` 部分处理；金蝶「发票受应收未开票金额约束」；NetSuite 首期未开完不推进 | **允许**，但一期累计 ≤ 该期比例/金额（R-INV-17），到 100% 后该期关闭 |
| D3 计划字段语义 | 用友/金蝶的「收款计划」是独立对象，且不控开票 | **需澄清**：若我方 `billing_percent/billing_amount` 实为收款计划，应单列 `collection_schedule`，不得与开票计划混用 |
| 税务发票对接 | 用友/金蝶均「业务票 → 税务票回写」 | Wave A 不加字段，但 §4 需注明 `invoice_no` 是**业务单号**；税务票号 Wave C 走外部号机制 |

### 19.5 源链接

- D365 销售订单开票 — https://learn.microsoft.com/en-us/dynamics365/finance/accounts-receivable/tasks/create-sales-order-invoices
- D365 订阅计费计划 — https://learn.microsoft.com/en-us/dynamics365/finance/accounts-receivable/sb-billing-schedules
- NetSuite Billing Schedules — https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1251398.html
- NetSuite 订单管理会计偏好（先于履约开票） — https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1388149.html
- NetSuite BillingSchedule 记录类型 — https://system.netsuite.com/help/helpcenter/en_US/srbrowser/Browser2019_2/script/record/billingschedule.html
- Workday Billing Schedules — https://doc.workday.com/workday-education/en-us/course-manuals/customer-accounts-and-contracts-for-administrators/billing-schedules.html
- Workday 分期开票计划 — https://doc.workday.com/admin-guide/en-us/financial-management/revenue/customer-contracts-billing/kat1372349443205.html
- Infor LN 分期开票 — https://docs.infor.com/ln/10.5/en-us/lnolh/help/td/onlinemanual/000069.html
- Infor M3 客户订单开票 — https://docs.infor.com/m3udi/16.x/en-us/m3beud/slsmgmths/ois360.html
- Odoo 开票策略（按订单/按交付/按里程碑） — https://www.odoo.com/documentation/19.0/applications/sales/sales/invoicing/invoicing_policy.html
- 用友 U8C 应收单申请开票与税务云回调 — https://u8chelpcenter.yonyoucloud.com/help/simpchn/ar2006030102.html
- 用友税务云销项发票 OpenAPI — https://fapiao.yonyoucloud.com/apidoc/appendix/%E9%94%80%E9%A1%B9%E5%8F%91%E7%A5%A8%E7%AE%A1%E7%90%86.html
- 金蝶标准销售业务 — https://help.open.kingdee.com/dokuwiki_std/doku.php?id=%E6%A0%87%E5%87%86%E9%94%80%E5%94%AE%E4%B8%9A%E5%8A%A1
- 金蝶应收开票核销 — https://help.open.kingdee.com/dokuwiki/doku.php?id=%E5%BA%94%E6%94%B6%E5%BC%80%E7%A5%A8%E6%A0%B8%E9%94%80
- 金蝶财务应收单下推开票申请单 — https://club.kdcloud.com/knowledge/322439898978883072

> 取证限制：Workday 的 Sales Order 与 Fulfillment 公开资料较少（主路径是 Customer Contract + Billing Schedule）；Infor LN 订单类型 `Invoice by`（Order/Delivery）未取到官方字段原文；NetSuite `Memorized` 属「记忆交易」而非 Billing Schedule 类型。以上未逐字确认项标 ⚠️。

---

## 20. 二选一范式的对象模型与关系模型（D10 已定）

> 决策：**D10 = 二选一**。一条订单行只能有一个开票锚，由 `sales_order_line.billing_relevance` 决定，取值 `delivery` / `plan` / `none`。
> 本节的「二选一」含义与 SAP `VBAP-FKREL`、Odoo `invoice_policy`、Infor `Invoicing by Installments`、Workday `Billing Type` 同构（§19.2 范式 A），**不是** NetSuite 的「计划定金额 + 发货作闸门」（范式 B）。
> 一句话：**数量口径与金额口径不再互校，而是按行走两条互斥的链路；唯一的汇聚点是订单头只读派生列 `billing_status`。**

### 20.1 对象清单（新增 / 改动 / 明确不建）

| 类别 | 对象 | 变更 | 说明 |
|---|---|---|---|
| 新建 | `customer_invoice`（表 `customer_invoices`） | 头字段见 §4 | 独立事实单据，六件套 + `posting_state=posted` |
| 新建 | `customer_invoice_line`（表 `customer_invoice_lines`） | 行字段见 §5 | 来源键三选一：`shipment_line_id` / `schedule_id` / 全空（`manual`） |
| 改动 | `sales_order_line` | + `billing_relevance`（enum，默认 `delivery`） | **二选一的载体**，本节的唯一新开关 |
| 改动 | `sales_order_line` | + `billed_qty` / `billed_amount` | 仅 `delivery` 路径回写（`plan` 路径恒 0） |
| 改动 | `sales_order_schedule` | + `billed_amount` / `billing_status` | 仅 `plan` 路径回写（`delivery` 路径恒 0） |
| 改动 | `shipment_line` | + `billed_qty` | 防同一发货行重复开票；仅 `delivery` 路径使用 |
| 改动 | `sales_order` | + `billing_status` / `billing_derived_at` | 两路汇聚的只读派生（唯一允许同时读两路的地方） |
| **不建** | `billing_request` / `billing_due_list` | — | 到期清单是查询/视图（D2） |
| **不建** | `billing_plan`（新对象） | — | 复用 `sales_order_schedules(kind='billing')` |
| **不建** | `ar_invoice` / `ar_ledger` / 收入确认 | — | g15 边界（§11） |
| **不改** | `shipment` / `shipment_line` 的状态机 | — | 发货状态与开票状态解耦 |

> 关键点：**没有新增任何「计划对象」或「申请对象」**。二选一只加了一个枚举列 + 两套互斥的回写列，对象数量不变。

### 20.2 关系矩阵（基数 / 键 / 索引 / 约束）

```
sales_order (1)
 └─(1:N) sales_order_line            ← billing_relevance 在此分叉
     ├─(1:N) sales_order_schedule   （kind = delivery | billing | service）
     │        ├─[delivery] →(1:N) shipment_line →(1:N, 仅 delivery 行) customer_invoice_line
     │        └─[billing]  →(1:N, 仅 plan 行)     customer_invoice_line
     └─(1:N, 仅 manual 挑量)                      customer_invoice_line
customer_invoice (1) ──(1:N) customer_invoice_line
customer_invoice (1) ──(1:1) customer_invoice（红字，reversal_of_invoice_id）
```

| # | 主 → 从 | 基数 | 连接键 | 唯一键 / 索引 | 约束 |
|---|---|---|---|---|---|
| R1 | `sales_orders` → `sales_order_lines` | 1 : N | `order_id` | 现有 | 沿用 |
| R2 | `sales_order_lines` → `sales_order_schedules` | 1 : N | `order_line_id` | `idx_sos_order_line` + `(order_line_id, schedule_kind, sequence_no)` | `kind=billing` 时 `billing_percent`/`billing_amount` 至少一个非空 |
| R3 | `sales_order_schedules(kind=delivery)` → `shipment_lines` | 1 : N | `shipment_lines.schedule_id` | 现有 `idx_shipment_line_schedule`（**非唯一**，R-DN-5） | 只允许挂 `kind='delivery'`（R-DN-0） |
| R4 | `shipment_lines` → `customer_invoice_lines` | 1 : N | `shipment_line_id` | **新增非唯一索引** `idx_cil_shipment_line` | 仅当所属订单行 `billing_relevance='delivery'` |
| R5 | `sales_order_schedules(kind=billing)` → `customer_invoice_lines` | 1 : N | `schedule_id` | **新增非唯一索引** `idx_cil_schedule` | 仅当所属订单行 `billing_relevance='plan'`；`schedule_kind` 必须 `='billing'` |
| R6 | `sales_order_lines` → `customer_invoice_lines` | 1 : N | `order_line_id` | **新增非唯一索引** `idx_cil_order_line` | 所有发票行必填（用于互斥巡检与汇聚） |
| R7 | `customer_invoices` → `customer_invoice_lines` | 1 : N | `invoice_id` | `UNIQUE(invoice_id, line_no)` | 行随头，仅 draft 可增删 |
| R8 | `customer_invoices` → `customer_invoices` | 1 : 1 | `reversal_of_invoice_id` | `UNIQUE(reversal_of_invoice_id)` | 同一原单只能红冲一次（R-INV-10） |
| R9 | `customer_invoices` ↔ `shipments` | N : M | 经 R4 行级 + `doc_flow_edges(pool=billing)` | `idx_ci_customer_status(customer_account_id, status)`、`idx_ci_invoice_no(invoice_no)` | 合并开票只体现在行级，头不带 `order_id` |

**行级三选一的物理约束**（新表可写进 DDL，SQLite 支持）：

```sql
CONSTRAINT ck_cil_source_xor CHECK (
     (shipment_line_id IS NULL OR schedule_id IS NULL)
 AND (source_doc_type IN ('shipment','billing_schedule','sales_order','service_confirmation','manual'))
 AND (source_doc_type <> 'shipment'           OR shipment_line_id IS NOT NULL)
 AND (source_doc_type <> 'billing_schedule'   OR schedule_id      IS NOT NULL)
 AND (source_doc_type NOT IN ('sales_order','service_confirmation','manual')
      OR (shipment_line_id IS NULL AND schedule_id IS NULL))
)
```

> `order_line_id` 在所有分支都必填——它是互斥巡检与订单头汇聚的唯一公共键，不能用 `shipment_line_id → schedule_id` 反推（`manual` 行没有来源行）。

### 20.3 `billing_relevance` 字段规格

| 取值 | 语义 | 开票来源 | 数量口径 | 金额口径 | 可开量上限 | 回写目标 | 谁驱动状态 |
|---|---|---|---|---|---|---|---|
| `delivery`（默认） | 以**履约数量**为唯一锚 | `shipment_line`；手工挑量时可 `order_line` | 数量（`qty`） | 订单行单价 × 数量（快照） | `shipment_line.qty − billed_qty`；或 `order_line.qty − billed_qty` | `shipment_line.billed_qty` + `sales_order_line.billed_qty` / `billed_amount` | 发货（`shipped` / `delivered`） |
| `plan` | 以**期次金额**为唯一锚 | `sales_order_schedule(kind='billing')` | 不取发货数量（`qty` 恒 1，或按期次反算） | `schedule.billing_amount` 或 `percent × 行净额` | `schedule.billing_amount − schedule.billed_amount` | `sales_order_schedule.billed_amount` + `billing_status` | 里程碑达成 / 期次到期 |
| `none` | 不开票（赠品 / 样机 / 内部转移） | 无 | — | — | 0 | 无 | 无 |

**派生与锁定**（R-INV-18）：

| 场景 | 规则 |
|---|---|
| 新建订单行 | 由 `billing_method` 带出：`milestone` + 存在 `kind='billing'` 计划行 → `plan`；其余 → `delivery` |
| draft 阶段 | 可手工改；改为 `plan` 时必须已存在 `kind='billing'` 计划行（否则 `BILLING_PLAN_REQUIRED`） |
| 订单确认后 | 只读；写接口返回 `BILLING_RELEVANCE_LOCKED` |
| 已有非作废发票行 | 任何情况下禁改（含 draft 改） |
| `none` | 只能手工设置（不自动派生），用于免开票行 |

> **为什么不用订单头开关**：合并开票会跨多张 SO，且一张订单里可能既有「按发货」的物料行、又有「按里程碑」的服务行（SAP `FKREL` 同样是 item 级）。头级开关无法表达，且与合并开票冲突。

### 20.4 不变量落地（§6.3 的执行层映射）

| 不变量 | 落地位置 | 校验时机 | 错误码 |
|---|---|---|---|
| R-INV-3 来源与订单行取值一致 + 跨发票互斥 | `CustomerInvoiceService.create_*` + 守卫 | 建行、改行、submit、post 四次 | `BILLING_SOURCE_MISMATCH` |
| R-INV-4 按量不超 | 同上 | 建行、submit、post | `BILLING_QTY_EXCEEDED` |
| R-INV-5 按比例不超 | 同上 | 建行、submit、post | `BILLING_PLAN_AMOUNT_EXCEEDED` |
| R-INV-18 枚举派生与锁定 | `SalesOrderGuard` 字段守卫 | 改 `billing_relevance` 时 | `BILLING_RELEVANCE_LOCKED` / `BILLING_PLAN_REQUIRED` |
| R-INV-19 可开量分流 | `CustomerInvoiceService._available()`，单一函数、按取值分支 | 建行、submit、post | 复用上面两个 |
| R-INV-20 回写分流 | `_apply_billed()` / `_revert_billed()`，按 `billing_relevance` 二分支 | post / reverse | 内部断言（不面向用户） |
| Wave A 未支持的取值 | `CustomerInvoiceService.create_*` 入口 fail-closed | 建单 | `BILLING_RELEVANCE_NOT_SUPPORTED` |

**互斥巡检 SQL**（放 `meta/tools/` 下的数据质量巡检，不在业务事务里跑）：

```sql
-- 期望返回 0 行：同一订单行不得同时出现 delivery 与 plan 两种来源（含跨发票）
SELECT l.order_line_id,
       SUM(CASE WHEN l.shipment_line_id IS NOT NULL THEN 1 ELSE 0 END) AS delivery_lines,
       SUM(CASE WHEN l.schedule_id      IS NOT NULL THEN 1 ELSE 0 END) AS plan_lines
FROM customer_invoice_lines l
JOIN customer_invoices i ON i.id = l.invoice_id
WHERE i.status NOT IN ('cancelled')
GROUP BY l.order_line_id
HAVING delivery_lines > 0 AND plan_lines > 0;
```

```sql
-- 期望返回 0 行：来源合法但订单行取值不匹配
SELECT l.id, ol.billing_relevance, l.source_doc_type
FROM customer_invoice_lines l
JOIN sales_order_lines ol ON ol.id = l.order_line_id
JOIN customer_invoices  i  ON i.id = l.invoice_id
WHERE i.status NOT IN ('cancelled')
  AND (   (l.shipment_line_id IS NOT NULL AND ol.billing_relevance <> 'delivery')
       OR (l.schedule_id      IS NOT NULL AND ol.billing_relevance <> 'plan') );
```

### 20.5 状态联动：两条互不交叉的状态流

**Delivery 路径**

```
sales_order_line.billing_relevance = 'delivery'
  shipment: draft → … → shipped → delivered
  shipment_line.billed_qty: 0 ──(invoice posted)──► qty ──(reverse)──► 0
  customer_invoice: draft → submitted → posted → reversed
  sales_order_line: billed_qty / billed_amount 累加；billing_status = none / partial / full
```

| 触发 | 动作 | 不动的字段 |
|---|---|---|
| invoice `posted` | `shipment_line.billed_qty += qty`；`order_line.billed_qty/billed_amount +=`；`order.billing_status` 重算 | `schedule.billed_amount`（恒 0）、`shipment.status` |
| invoice `reversed` | 同上取负回滚 | `shipment.status` |
| shipment `delivered` | 只更新 `fulfillment_status` / 发货完成度 | `billed_qty`、发票状态 |

**Plan 路径**

```
sales_order_line.billing_relevance = 'plan'
  sales_order_schedule(kind='billing'): pending ──(invoice posted)──► partial ──► completed
  customer_invoice: draft → submitted → posted → reversed
  sales_order_line.billed_qty: 恒 0（发货不影响开票进度）
```

| 触发 | 动作 | 不动的字段 |
|---|---|---|
| invoice `posted` | `schedule.billed_amount +=`；`schedule.billing_status = partial/full`；`order.billing_status` 重算 | `shipment_line.billed_qty`（恒 0）、`order_line.billed_qty`（恒 0）、履约状态 |
| 期次到期 | 进入「开票到期清单」视图（`promised_date ≤ today` 且 `billing_status <> full`），**不落表** | — |
| 发货完成 | 只更新 `fulfillment_status`；**不产生发票、不推进期次** | `schedule.billed_amount`、`billing_status` |

**汇聚点（唯一例外）**：`sales_order.billing_status` 由两路汇总：

```
full     ⟺ 所有 delivery 行 billed_qty = qty  且  所有 plan 行 billing_status = full
partial  ⟺ 任一已开票 > 0（任一路径）且未达 full
none     ⟺ 两路均为 0
```

它是**只读投影**，可随时从行级重算；不参与任何守卫判断，也不作为第二口径回写行级。

### 20.6 doc_flow 边（与 §10 一致，此处补准入规则）

| rule id | 适用 `billing_relevance` | 准入校验（建行时执行，不依赖 doc_flow 规则） |
|---|---|---|
| `shipment_to_customer_invoice` | **仅 `delivery`** | 来源订单行 `billing_relevance='delivery'`；shipment 行 `schedule.kind='delivery'`；shipment 状态 ∈ `shipped/delivered` 且未 `reversed` |
| `billing_schedule_to_customer_invoice` | **仅 `plan`** | 来源订单行 `billing_relevance='plan'`；`schedule_kind='billing'`；计划行未 `cancelled`；订单 `confirmed` 以上 |
| `sales_order_to_customer_invoice` | `delivery`（手工挑量） | 手工单允许按 `order_line` 挑量，仍受 `order_line.qty − billed_qty` 上限 |
| `customer_invoice_reversal` | 任意 | 原单 `posted` 且未被红冲 |
| `service_confirmation_to_invoice_line` | Wave C | 预留 |
| `delivery_schedule_to_customer_invoice` | **禁止建边** | `kind='delivery'` 的计划行不作为开票来源（只作为发货来源） |

两条正向开票边**互斥**：任一行在一张发票内只能命中一条；跨发票由 R-INV-3 + 20.4 巡检兜底。

### 20.7 数值推演：同一订单，两种取值

前提：1 条订单行，净额 100 万元，税率 13%，3 批发货（30% / 30% / 40%），计划为 2 期（50% / 50%）。

**取值 `delivery`（Wave A 默认）**

| 事件 | 来源 | qty | net | tax | gross | `shipment_line.billed_qty` | `order_line.billed_qty` |
|---|---|---|---|---|---|---|---|
| 交货 1 | `shipment_line` #1 | 30% | 30.0000 万 | 3.9000 万 | 33.9000 万 | 30% | 30% |
| 交货 2 | `shipment_line` #2 | 30% | 30.0000 万 | 3.9000 万 | 33.9000 万 | 30% | 60% |
| 交货 3 | `shipment_line` #3 | 40% | 40.0000 万 | 5.2000 万 | 45.2000 万 | 40% | 100% |

- 结果：**3 张发票 30 / 30 / 40 万**（税 3.9 / 3.9 / 5.2）。
- `sales_order_schedules(kind='billing')` 的 2 期 50/50 **完全不参与**，`billed_amount` 恒 0、`billing_status` 恒 `none`。
- `sales_order.billing_status`：`partial` → `partial` → `full`。

**取值 `plan`（Wave B）**

| 事件 | 来源 | qty | net | tax | gross | `shipment_line.billed_qty` |
|---|---|---|---|---|---|---|
| 交货 1（30%） | — | — | 0 | 0 | 0 | **0** |
| 交货 2（60%） | — | — | 0 | 0 | 0 | **0** |
| 交货 3（100%） | — | — | 0 | 0 | 0 | **0** |
| 里程碑 1 达成 | `schedule` #1 | 1 | 50.0000 万 | 6.5000 万 | 56.5000 万 | 0 |
| 里程碑 2 达成 | `schedule` #2 | 1 | 50.0000 万 | 6.5000 万 | 56.5000 万 | 0 |

- 结果：**2 张发票 50 / 50 万**（税 6.5 / 6.5），可在 3 批发货全部完成前开出（§18.4.1 SAP `FKREL=I` 同构）。
- `shipment_line.billed_qty` 与 `order_line.billed_qty` 恒 0；`fulfillment_status` 仍按 30/60/100 正常推进。
- `sales_order.billing_status` 走计划口径：`none` → `partial`（第 1 期）→ `full`。

> 对照结论：**同样的业务事实，选 `delivery` 得 3 张按量票，选 `plan` 得 2 张按期票，系统不会同时产出两套。** 若业务确实需要「3 批发货 + 2 期里程碑」，正确做法是**把该行设为 `plan`**，而不是让两个口径并存（§19.3 结论 1）。

### 20.8 迁移与回填（`v232__customer_invoice.py`）

| 步骤 | 内容 |
|---|---|
| 1 | 建表 `customer_invoices` / `customer_invoice_lines`（含 `ck_cil_source_xor`、`UNIQUE(invoice_id, line_no)`、`UNIQUE(reversal_of_invoice_id)`） |
| 2 | 新增列：`sales_order_lines.billing_relevance`（默认 `'delivery'`）、`billed_qty`、`billed_amount`；`sales_order_schedules.billed_amount`、`billing_status`（默认 `'none'`）；`shipment_lines.billed_qty`；`sales_orders.billing_status`（默认 `'none'`）、`billing_derived_at` |
| 3 | 索引：`idx_cil_shipment_line` / `idx_cil_schedule` / `idx_cil_order_line` / `idx_ci_customer_status` / `idx_ci_invoice_no` |
| 4 | 回填 `billing_relevance`：`billing_method='milestone'` **且** 存在 `schedule_kind='billing'` 的计划行 → `'plan'`；其余（含 milestone 但无计划行）→ `'delivery'` |
| 5 | 断言：非 milestone 行 100% 为 `'delivery'`；所有 `'plan'` 行均至少有一条 `kind='billing'` 计划行；所有派生活塞列 = 0 |
| 6 | 数据质量告警（不阻塞迁移）：`billing_method='milestone'` 但无 billing 计划行的订单行，输出清单供业务确认是补计划还是降级 `delivery` |
| 7 | `skip_backup=True` 签名、事务提交后**直接查 DB 复验**（SESSION_REMINDER：脚本报「已清理 N 条」不等于生效） |

### 20.9 对 Wave A / Wave B 的裁剪

| 波次 | `billing_relevance` 支持范围 | 落地的分支 | 守卫行为 |
|---|---|---|---|
| **Wave A** | `delivery` ✅ / `none` ✅ / `plan` ❌ | `create_from_shipment` / `create_manual` / `reverse`；`shipment_line.billed_qty` 全量回写 | 命中 `plan` 行直接 `BILLING_RELEVANCE_NOT_SUPPORTED`（fail-closed，不静默降级） |
| **Wave B** | 三值全开 | 新增 `create_from_schedule`；期次 `partial`/`full`；到期清单视图；`plan` 回写 | 提交换 `plan` 分支守卫 |
| **Wave C** | 不变 | 服务确认 T&M、贷项/借项、合并开票、跨币种 | 不变 |

> Wave A 建列但不建分支的好处：迁移一次到位、`billing_relevance` 从第一天就是唯一开关，Wave B 只需加服务方法与守卫分支，**不需要二次改表**。

---

## 21. 「收款计划」是否存在于销售模块（D3 的行业取证）

> 问题：其他头部 ERP 的销售模块里，到底有没有「收款计划 / 分期收款」这个对象？它和开票计划是不是同一个东西？
> 结论先行：**有，但绝大多数不是第一类业务对象，而是「付款条件（payment terms）的多期展开」**；且**没有任何一个产品用同一个对象同时控开票和收款**。

### 21.1 十个产品横向对照

| 产品 | 收款计划载体 | 挂载层级 | 与开票计划的关系 | 取证 |
|---|---|---|---|---|
| **SAP S/4HANA** | 付款条件多期：`VBAK-ZTERM` + `T052`（净到期 + 3 档折扣）不足以表达分期，需 OBB8「分期标识」主条件 + **OBB9** 把每期 % 映射到各自付款条件 | 订单头（单值） | **独立**。开票计划是 `FPLA/FPLT`，预付请求 `FAZ` 是其下游 | 字段字典 + 学习站（⚠️ OBB9 未取到 help.sap.com 原文） |
| **D365 F&SCM** | `Payment schedule` 是 **AR 付款设置里的配置对象**（按总额/固定额/固定期数/指定行分配），付款条件可挂它；开票时落为 `CustPaymSched` / `CustPaymSchedLine`（**单据级**）。销售订单头 Price and discount 卡可见 | 订单头 + 配置模板 | **独立**（开票按 packing slip：`CustPackingSlipTrans` → `CustInvoiceTrans`） | 官方 Learn |
| **Oracle Fusion** | **无独立对象**。Payment Terms 本身支持多期（split terms：% + Days/固定日），订单头 Billing and Payment 页签带出，开票后在 AR 展开为 payment schedule（`AR_PAYMENT_SCHEDULES_ALL`） | 订单头 | **独立**（AutoInvoice 生成 AR 发票） | 书籍入口 + 镜像（⚠️ 字段名未逐字确认） |
| **NetSuite** | Term 记录有 `Installment` 勾选 + 百分比子表 + Recurrence（Frequency/Count/Split Evenly），**不支逐期任意天数** | 订单头（行可覆盖 ⚠️） | **独立**。`Billing Schedule` 是 Advanced Billing 的独立对象，其 `Recurrence Payment Terms` 反向引用付款条件 | 官方 help |
| **Workday** | 付款条件**只管到期日/折扣**；多期收款在**发票**上（Payment Schedule 页签，% 或固定额），需开 `Enable Multiple Due Dates on Customer Invoices` | 发票 | **独立**。`Billing Schedule` / `Billing Installment` 属客户合同开票维度 | 官方 admin guide |
| **Infor LN** | **唯一的第一类对象**：`Payment Schedule` 头（`tcmcs2120m000` / `tcmcs2620m000`，表 `tcmcs220`）+ 行（`tcmcs2121m000`，表 `tcmcs221`）；AR 侧称 `Receipt Schedule`（`tfacr1103m000`）；可独立定义、被多条付款条件复用 | **付款条件**（`tcmcs0113s000` 上的 `Payment Schedule Header` 字段）；**订单上没有该字段**，订单只带 `Terms of Payment` | **独立**。开票分期是 `Invoicing by Installments` + `Installment Plan`（`tdsls4100m000`，运行期 `cisli8620m000`） | 官方 docs.infor.com（字段级见 §22） |
| **Odoo 17/18** | `account.payment.term` + `account.payment.term.line`（`value`=percent/fixed、`nb_days`、`delay_type`）；`sale.order` 只有 `payment_term_id` | 条件头 + 条件行 | **独立**。开票由 `product.invoice_policy` + 开票向导决定 | 官方文档 + 源码 |
| **IFS Cloud** | Payment Term 下的 **Installment Plan**（每期含付款日、占总额 %、付款方式） | 付款条件头 + 分期行 | **独立**。`Staged Billing` 挂订单行管开票阶段 | 官方帮助 |
| **Sage X3** | 付款条件 `PTE`（`GESTPT`）定义 payment schedule（一张发票多条 open item） | 条件级（SO 头只带 PTE） | **独立**。开票节奏由 `Invoicing terms`（`GESINVCND`）控 | 官方帮助 |
| **用友 / 金蝶** | 销售订单上的**独立「收款计划」子对象**（用友：`收款协议` 基础资料 → 订单带入；金蝶：`收款条件` → 订单「收款计划」页签） | 订单头（计划行以页签/子表呈现） | **独立**。两者都**不控开票**：用友控制环节枚举只有「不控制 / 发货单 / 订单 / 出库单」，无「开票」；金蝶控制环节枚举为「订购 / 发货 / 出库 / 生产」，同样无「开票」 | 见 §23.1（含三处 ⚠️） |

### 21.2 两派实现（都能表达「30% 预付 + 70% 货到 30 天」）

**A 派 · 付款条件多期（主流，7/10）**：付款条件头 + 分期行（`%` + 天数/固定日）。销售订单只存一个 `payment_term_id`，**开票时**才在应收侧展开成多条到期行（Oracle `AR_PAYMENT_SCHEDULES_ALL`、Odoo 发票 journal items 300/700、D365 `CustPaymSchedLine`、SAP 分期付款条件）。
- 优点：一个字段、零新对象；改付款条件不动订单。
- 缺点：**订单上看不到「哪天收多少钱」**；到期行是开票后的产物，不是业务事实。

**B 派 · 独立收款计划对象（Infor LN / 用友 / 金蝶，3/10）**：
- Infor LN：`Payment Schedule` 可独立建、可复用、可被多条付款条件引用；AR 侧再生成 `Receipt Schedule` 逐行催收/计息。
- 用友/金蝶：销售订单上直接挂收款计划行（用友：期号 + 比例/金额 + 起算时点/延迟 + 结算方式；金蝶：应收比例/金额 + 到期日 + 是否预收），**并且只控发货/出库、不控开票**——这是关键证据（字段级取证见 §23.1）。

### 21.3 三条结论

1. **收款计划 ≠ 开票计划，全行业无一例外。** 开票计划回答「什么时候开多少票」（收入/应收确认节奏）；收款计划回答「什么时候该收多少钱」（现金回笼节奏）。两者可以同比例，也可以完全不同（如「2 期开票 50/50，但收款是 30% 预付 + 70% 货到 60 天」）。
2. **同一个对象同时控开票和收款，10 个产品里 0 个这么做。** 因此我方若让 `sales_order_schedules(kind='billing')` 的 `billing_percent/billing_amount` 既被当作开票里程碑、又被业务解读为收款计划，是**语义债**，必须拆。
3. **「订单上看得见收款计划」只在部分 B 派成立**：B1（用友/金蝶）订单上直接可见；B2（Infor LN，见 §22.1）订单上只有一个付款条件代码，计划要到发票才展开；A 派把可见性整体放在开票后的 AR 侧。所以「订单级可见」不是 B 派的必要条件，而是用友/金蝶的**主动设计选择**——动因见 §23.2。是否需要订单上可见，取决于财务是否要在接单时锁定回款节奏，这是 D3 的真正决策点，不是技术问题。

### 21.4 对 D3 的三个方案

| 方案 | 做法 | 对象成本 | 适合 |
|---|---|---|---|
| **D3-a 付款条件多期（推荐 Wave A）** | 复用现有 `payment_term_id`，在 `payment_term` 下加分期行（`percent` / `amount` / `days` / `fixed_date`）；发票 `posted` 时展开为 L2 会计事件的到期日 | 0 新单据，1 张子表 | 收款节奏由商务条款决定、财务无需在订单上逐期跟踪 |
| **D3-b 独立 `collection_schedule`（对齐 Infor/用友/金蝶）** | 新对象挂订单头/行：期次、比例/金额、计划收款日、状态（`pending/partial/collected`）；**明确不控开票**（与 billing schedule 平行） | 1 个新对象 + 1 张表 + 回款核销联动 | 需要在接单时锁定回款计划、按计划催收、与信用/账龄联动 |
| **D3-c 合并（当前隐含做法）** | 一个计划行同时被当开票与收款 | 0 | ❌ **不建议**：10 个产品无一先例，且拆账时必然对不上 |

> 建议：**Wave A 走 D3-a**（我方已有 `payment_term_id`，改动最小），把 `sales_order_schedules` 的文案彻底锁死为「开票计划」；若 Wave C 出现「按计划催收 + 逾期计息」需求，再按 D3-b 建独立对象，并保证它与 `billing_relevance='plan'` **正交**（一个控开票、一个控回款，互不写对方字段）。

### 21.5 源链接

- D365 Payment schedule（AR 配置） — https://learn.microsoft.com/en-us/training/modules/configure-accounts-receivable-dyn365-finance/2-payment-schedule
- D365 Terms of payment 与 schedule 的关系 — https://learn.microsoft.com/en-us/training/modules/configure-accounts-receivable-dyn365-finance/3-terms-payment-days
- D365 `CustPaymSchedLine` 表 — https://learn.microsoft.com/en-us/previous-versions/dynamics/ax-2012/reference/gg924515(v=ax.60)
- NetSuite Term 记录（Installment / 百分比子表） — https://system.netsuite.com/help/helpcenter/en_US/srbrowser/Browser2026_1/script/record/term.html
- NetSuite 应用 Billing Schedules — https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1253848.html
- Workday 创建客户发票（多到期日） — https://doc.workday.com/admin-guide/en-us/financial-management/customer-accounts/customer-invoices/invoicing/dan1370796996367.html
- Workday Billing Schedules — https://doc.workday.com/workday-education/en-us/course-manuals/customer-accounts-and-contracts-for-administrators/billing-schedules.html
- Odoo 18 付款条件与分期计划 — https://www.odoo.com/documentation/18.0/applications/finance/accounting/customer_invoices/payment_terms.html
- Odoo 18 开票策略 — https://www.odoo.com/documentation/18.0/applications/sales/sales/invoicing/invoicing_policy.html
- Infor LN 销售订单（`tdsls4100m000`） — https://docs.infor.com/ln/10.7/en-us/lnolh/help/td/sls/tdsls4100m000.html
- Infor LN 付款计划总览 — https://docs.infor.com/ln/10.7/en-us/lnolh/help/tf/onlinemanual/000474.html
- Infor LN 收款计划（`tfacr1103m000`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/tf/acr/tfacr1103m000.html
- IFS Cloud 分期计划 — https://docs.ifs.com/ifsclouddocs/25r2/lang/en/DefineFinancialsBasics/ActivityEnterInstallmentPlan.htm
- IFS Cloud Staged Billing — https://docs.ifs.com/ifsclouddocs/24r1/Sales/AboutStagedBilling.htm
- Sage X3 付款条件 `GESTPT` — https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESTPT.htm
- Sage X3 开票条件 `GESINVCND` — https://online-help.sagex3.com/erp/11/en-US/FCT/GESINVCND.htm
- SAP `T052` 付款条件字段 — https://www.sapdatasheet.org/abap/tabl/t052.html ⚠️ 镜像
- SAP OBB8/OBB9 分期付款条件 — https://sapficolearns.wordpress.com/2020/10/16/payment-terms-fico/ ⚠️ 学习站

> 取证限制：help.sap.com 与 Oracle Fusion 文档为 JS 渲染，正文未直接抓取；OBB9 与 `AR_PAYMENT_SCHEDULES_ALL` 的字段级细节来自学习站/镜像，标 ⚠️。Infor LN `000474` 页面末尾被截断，"payment schedules 与 sales 的区别"后半句未取到原文，但「收款计划=独立头行对象」的判定由 `tcmcs2620m000`/`tcmcs2121m000`/`tfacr1103m000` 三个官方表单页支撑。

---

## 22. Infor LN Payment Schedule 深度拆解（D3-b 的唯一完整样板）

> 目的：Infor LN 是 10 个产品里**唯一**把「收款计划」做成可复用主数据头行对象的产品。要判断我方是否照抄 D3-b，必须看它到底长什么样、挂在哪、字段能表达什么。
> 取证：全部来自 `docs.infor.com` 在线手册（10.3/10.4/10.5/10.7 各版本），每条附 URL；未取到原文的显式标 ⚠️。

### 22.1 三层结构：主数据 → 付款条件 → 发票

```
Payment Schedule（主数据头/行，可复用）
        ▲ 被引用
Payment Terms（付款条件，字段 Payment Schedule Header）
        ▲ 被引用
Sales Order / Invoice（订单只带付款条件，不带计划）
        ▼ 开票时展开
Receipt Schedule（AR 逐期应收，tfacr1103m000）
```

| 层 | 对象 | 表单 | 表 | 说明 |
|---|---|---|---|---|
| 主数据 | Payment Schedule 头 | `tcmcs2120m000`（Payment Schedule Headers）/ `tcmcs2620m000`（Payment Schedules） | `tcmcs220` | 两个入口在 10.x 不同版本文档中同时出现，视为同族会话 |
| 主数据 | Payment Schedule 行 | `tcmcs2121m000` | `tcmcs221` | 期次定义 |
| 引用 | Payment Terms | `tcmcs0113s000` | `tcmcs0113` | 头上有 `Payment Schedule Header` 字段 |
| 事实 | Receipt Schedule | `tfacr1103m000` | `tfacr201` ⚠️ | 发票创建时按计划自动生成 |

**最容易误判的一点**：Payment Schedule **不挂在销售订单上，也不挂在业务伙伴上**。订单表单（`tdsls4100m000` / `tdsls4100m900`）只有 `Terms of Payment`，没有 Payment Schedule 字段；业务伙伴（`tccom4512m000` / `tccom4112s000`）只有默认付款条件。

> 对比：用友/金蝶的「收款计划」是**挂在订单上、接单时可见**的；Infor LN 的收款计划**要到发票才展开**，订单上只看得见一个付款条件代码。所以 B 派内部还有两小派：**B1 订单级可见（用友/金蝶）** vs **B2 条件级隐藏（Infor LN）**。

### 22.2 字段级（这是 D3-b 的真实表达力上限）

**头（`tcmcs220`）**

| 字段 | 取值 | 说明 |
|---|---|---|
| Payment Schedule | 编码 | 主键，可复用 |
| Schedule Definition | `By Percentage` / `By Factor` | 决定行上按百分比还是按系数分摊 |
| Payment Period Type | `Days` / `Months` / `Fiscal Periods` | 期数偏移的计量单位；`Fiscal Periods` 可表达「按会计期（月末）收款」 |

> 头**没有币种字段、也没有固定金额字段**（官方字段清单未列）。推论 ⚠️：计划以发票币种表达，因此同一计划可被多币种付款条件复用，不需按币种复制。

**行（`tcmcs221`）**

| 字段 | 说明 |
|---|---|
| Sequence Number | 期次序号 |
| Number of Payment Periods | 相对**发票日**的偏移量（天数/月数/会计期数），**可为负**（负数 = 预付，早于发票日） |
| Percentage of Invoice Amount | 占发票金额百分比，各行**合计必须 = 100** |
| Factor of Invoice Amount | 与 Percentage **二选一**（系数分摊） |
| Payment Method / Receipt Method | 逐行独立（同一计划内不同期可用不同方式） |
| 三档折扣天数 + 百分比 | 每期独立折扣（如 10 天内 2%、30 天内净额） |

**到期日算法（关键）**：`发票 document date + Number of Payment Periods` → 再套用所挂付款条件的到期日计算（付款日历、固定付款日、附加天数）。

三条硬约束：
1. **没有「固定日期」**，一律相对发票日 → 计划天然随发票日期平移，不需要逐期维护日历。
2. **没有「固定金额」** → 无法表达「第 1 期固定收 5 万、余额分两期」；要固定金额只能用 `By Factor` 近似，或改建付款条件。（对比 D365：支持按固定金额分配）
3. **没有里程碑/事件** → 收款计划与「发货完成」「验收通过」这类业务事件**无关联**，纯时间驱动。

### 22.3 与开票分期的正交性（两套机制互不写字段）

| 维度 | 收款侧 Payment Schedule | 开票侧 Installment Plan |
|---|---|---|
| 主数据 | `tcmcs2120m000` / `tcmcs2121m000`（`tcmcs220/221`） | `tcmcs2645m000` 计划；`tcmcs2140/2141` 分期行 |
| 挂载点 | **付款条件** `tcmcs0113s000` | **销售订单** `tdsls4100m000` 的 `Plan` 字段 |
| 运行期载体 | 每张发票 → `tfacr1103m000` | 每张订单 → `cisli8620m000` 分期行 |
| 时间基准 | 相对**发票日** + N | 相对**订单日/交付日**（`Invoice Day`） |
| 关键字段 | %/Factor、Payment/Receipt Method、折扣 | %、`Invoice Day`、`Installment Type`（Advance / Normal / Guarantee） |
| 交叉字段 | **无** | **无** |

**反证（互不写字段）**：
- `tccom4112s000` 上 `Installment Plan` 与 `Payment Terms` 是两个独立字段；
- `tcmcs2645m000` / `tcmcs2141m000` 无付款条件字段；
- `tcmcs2120m000` / `tcmcs2121m000` 无开票分期字段；
- `cisli8620m000` 无 `Receipt Method` / 付款条件 / 收款行字段。

> 唯一耦合点是**发票**这个中立对象，以及 Settlement 的单向冲减（见 §22.5）。这坐实了 §21.3 结论 2：**没有任何产品用同一对象同时控开票和收款**。

### 22.4 `Invoicing by Installments` 五个取值（修正 §19.2 A 行的笼统表述）

| 值 | 含义 |
|---|---|
| `No` | 非分期订单，纯按交货开票 |
| `Installment Plan` | 按 installment plan 开票；**唯一启用分段会计（segment accounting）的取值** |
| `Direct Settlement` | 未开完全部期也可对已交货货物开票；货票上**冲减**已开票分期金额，收入/周转立即可见 |
| `Indirect Settlement` | 分期未关闭前不得对交货开票；关闭时才冲减，周转暂挂 installment item |
| `Closed` | 所有非 guarantee 期已开票（系统推进态） |

禁用条件：成本/托收/寄售/退货/retro-billed 订单，或行间 `Tax Code` / `Project` / `Sales Type` 不一致（视参数）。

**注意**：`Installment Plan` 字段指向 `tcmcs2645m000`，默认值取自 Invoice-to BP；`cisli8620m000` **不是维护入口**，而是订单生成后的运行期分期行（含 `Percentage/Amount`、`Invoice Day`、`Installment Type`、累计 `Invoiced / Paid / To be Settled / Settled`）。

### 22.5 「3 批发货 + 2 期开票」在 Infor LN 里怎么跑

这是用户最关心的对照实验。结论：**不是二选一，也不是一张发票双口径，而是「两张发票流 + 结算对冲」**。

| 流 | 内容 | 数量 | 金额 |
|---|---|---|---|
| 分期发票流 | 按 `Installment Plan` 每期开一张（默认「每期一张」，`Invoicing Method` 的 `Installments` 勾选才合并多期） | **空**（行上 `Quantity`/`Price` 不填） | 按期百分比 |
| 货物流发票 | 按每批发货开（Packing slip → 货票） | 按发货数量 | 已开票分期金额在货票打印时按订单行 **prorate 冲减**（settlement） |
| 结算 | `Direct`：已交货即可开货票并立即冲减；`Indirect`：分期关闭后才冲减 | — | 冲减 `To be Settled`，最终为 0 |

推演（订单净额 100 万、3 批 30/30/40、2 期 50/50）：
1. 第 1 期 50 万可在**任何发货前**开出（Advance 期甚至要求先收款才 release 到仓储）。
2. 三批发货各开一张货票，数量 30/30/40，金额为订单行价 × 数量。
3. 但已开出的 50 万要在货票上冲减，否则重复计收入 → `Direct Settlement` 在打印货票时按行 prorate 冲减，`To be Settled` 递减到 0。
4. 第 2 期 50 万 按期次日期开出。

**因此**：Infor LN 「金额看计划、数量看交货」是成立的，但代价是**引入了 settlement 这个额外机制和两套发票流**。这正是我方 §20 刻意回避的复杂度 —— 我们选择行级 `billing_relevance` 二选一，一张发票只承载一个口径。

> 对本 spec 的修正：§19.3 结论 1 已补「例外修正」。D10 二选一**不变**；若未来 Wave C 真的需要「预付按金额、发货按数量」，正确路径是新增 **settlement 机制**（分期发票只记金额 + 货票冲减 `settled_amount`），而不是放宽 `billing_relevance`。

### 22.6 收款分期与开票分期的期次是否必须一一对应

**不必须，但也不能真正「全订单 3 期收款」**。机制是：收款计划在**每张发票**创建时展开 → 2 张发票 × 3 行计划 = 6 条 `Receipt Schedule`。

推论 ⚠️（文档无逐字表述，由机制推得）：
- 「每张发票内部分 N 期」→ 原生支持；
- 「整张订单跨多张发票、总共只收 3 次」→ **不原生支持**，除非用 `Receipts against shipments`（按发货生成收款行，此时**忽略**付款条件上的 payment schedule）。

这条限制对我的 D3 判断很重要：**A 派（付款条件多期）表达的是「单张发票的收款节奏」，不是「订单的收款节奏」**。如果业务真的要「订单收款计划」（接单时锁定 30/40/30、按订单总额算），那 A 派本身就不够，必须 D3-b。

### 22.7 AR 侧 `tfacr1103m000`（Receipt Schedule）

| 项 | 事实 |
|---|---|
| 生成时机 | 发票创建时，按付款条件的 payment schedule 定义**自动生成** |
| 行号规则 | 发票号 + schedule line |
| 可改性 | 付款过账前可手工增删 |
| 强制参数 | `Schedules Mandatory` 开启且无计划时，强制弹出该会话；不需要计划则建单行 = 全额 |
| 存什么 | `Schedule Amount`、`Amount Received`、`Balance`、`Due Date`、`Receipt Method`、三档折扣日期/金额、`Letter Number`（催款信）、`Problem/Date`、Shipment 关联 |
| 不存什么 | **利息不在该表**；逾期由 LN 另生成利息发票 + 催款信 |
| 基数 | 发票 1 : N 收款行；`Receipts against shipments` 时每 shipment 一行 |

### 22.8 我方结论

| 问题 | 结论 |
|---|---|
| Infor LN 的收款计划是「付款条件附属行」还是「第一类对象」 | **第一类对象**，但业务上只经付款条件被引用，**订单上不可见** |
| 能否照抄 D3-b | 可以，但要先决定「订单上要不要看得见」：要看见 → 学用友/金蝶（B1）；只要条件级复用 → 学 Infor（B2） |
| 对我方现有 `payment_term_id` 的影响 | Infor 证明「条件 + 分期头行」能覆盖 90% 场景；但**无固定金额**是硬伤，若我方要支持「首期固定 5 万」需在分期行上加 `amount` 字段（D365 路线） |
| 对 D10 的影响 | 无。二选一仍成立；Infor 的双流是通过 **settlement** 实现的第二种单据流，不是放宽枚举 |
| 对 Wave C 的启发 | 若要做「预付 + 发货」并用，最小增量是 `customer_invoice_line.settled_amount` + `settled_by_invoice_id`，**不新增对象** |

### 22.9 源链接

- Payment Schedules 总览/使用 — https://docs.infor.com/ln/10.3/en-us/lnolh/help/tf/onlinemanual/000474.html
- Payment Schedule Headers（`tcmcs2120m000`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/mcs/tcmcs2120m000.html
- Payment Schedules（`tcmcs2620m000`） — https://docs.infor.com/ln/10.3/en-us/lnolh/help/tc/mcs/tcmcs2620m000.html
- Payment Schedule Lines（`tcmcs2121m000`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/mcs/tcmcs2121m000.html
- 使用付款计划（`000477`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/tf/onlinemanual/000477.html
- Receipt Schedules（`tfacr1103m000`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/tf/acr/tfacr1103m000.html
- Payment Terms（`tcmcs0113s000`） — https://docs.infor.com/ln/10.3/en-us/lnolh/help/tc/mcs/tcmcs0113s000.html
- 收款行生成/发货冲销（`000490`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/tf/onlinemanual/000490.html
- Installment 域（`futo`，五值） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/domains/futo.html
- Sales Orders（`tdsls4100m000`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/td/sls/tdsls4100m000.html
- Installments 总览（`000069`） — https://docs.infor.com/ln/10.3/en-us/lnolh/help/td/onlinemanual/000069.html
- Prorate-based installments（`000611`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/td/onlinemanual/000611.html
- Installments（`cisli8620m000`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/ci/sli/cisli8620m000.html
- Installment Plan（`tcmcs2645m000`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/mcs/tcmcs2645m000.html
- Installment Lines（`tcmcs2141m000`） — https://docs.infor.com/ln/10.7/en-us/lnolh/help/tc/mcs/tcmcs2141m000.html
- Invoicing Methods（`tcmcs0155s000`） — https://docs.infor.com/ln/10.4/en-us/lnolh/help/tc/mcs/tcmcs0155s000.html
- Invoice-to BP（`tccom4112s000`） — https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/com/tccom4112s000.html
- 归档表清单（`tcmcs220/221`） — https://docs.infor.com/ln/10.3/en-us/lnolh/help/archiving/MasterData.html

> ⚠️ 未验证项：① `tfacr201`（Receipt Schedule 物理表）仅有社区表字典与旧版归档佐证，在线手册无映射，需登录 Infor Support Table Definitions；② 2023.x 站点为 JS 渲染，`Installment Plan` 默认值原文仅由检索快照取得；③ 「最后一期取余额」在 `tcmcs2141m000` 无对应字段或说明，**不要按此假设设计**。

---

## 23. 为什么用友/金蝶把收款计划放在订单上（中国业务约束推演）

> 问题：§21 已证明「收款计划」在 10 个产品里只有 3 个是独立对象，其中只有 2 个（用友/金蝶）把它**放在订单上、接单时可见**。这是产品历史包袱，还是中国 B2B 业务的必然？对 D3 的选型有无决定性影响？
> 取证方式：官方帮助文档字段级 + 法规/统计口径数据；凡无原文支撑的一律标 ⚠️，不给出「行业共识」当作事实。

### 23.1 事实还原（先把两家的机制说准）

#### 23.1.1 用友（NC / U8C / YonBIP）

**结构**：`收款协议` 是**基础资料**（支持租户级/组织级分级管控、可共享），销售订单表头参照带入；订单明细的收款计划行**可改比例、改起算时点、改账期、可增行**。NC 术语表定义原文：

> 「销售订单整单按照收款协议制定的不同收款时点，拆分计算的收款计划表。」

NC `收款协议` 节点说明原文：

> 「通过收款协议编制分期收款的时点、比例、结算方式和折扣等重要交易因素，对销售合同、销售订单、销售发票的销售收款计划跟踪，实现客户应收账龄分析、收款预测、信用管控等管理工作。」

**订单收款计划行字段**

| 字段 | 取值 / 规则 |
|---|---|
| 期号 | 行序号 |
| 收款比例 | 各期之和必须 = 100 |
| 收款金额 | **订单收款限额** = 比例 × 表头价税合计；可手工改 |
| 日期 | **不存静态日期**。存「起算时点 + 延迟天数 + 延迟月数 + 账期/信用期限 + 固定出账日」，出账日 = 起算日 + 延迟天数 + 延迟月数 |
| 结算方式 | 现金 / 现金支票 / 转账支票 / 网银 / 电汇 / 信汇 / **银行承兑汇票** |
| 质保金 / 保证金 | NC 仅一行可设质保金；U8C 为保证金 |
| 预收款标志 | 协议行可勾，另有「预售折算方式」（先到先用 / 比例折算） |
| 收款状态 | 未收款 / 部分收款 / 部分收款待确认 / 收款待确认 / 收款完成；**下游回写，不可手工改** |

**控制点（这是最关键的一列）**

| 控制项 | 枚举 |
|---|---|
| 控制环节 | 不控制 / **发货单** / **订单** / **出库单** —— **无「开票」** |
| 控制时机 | 保存 / 提交 / 审核 |
| 控制方式 | 提示 / 无控制 / 拒绝使用 |

订单上的业务开关：「款到发货」= 必须整单收款后才能出库；「按款发货」= 严格按该笔订单收款放行。

> ⚠️ 取证限制：① U8+ 有「收付款协议档案」+ 账期/信用期限 → 发货控制，但 **U8 订单级收款计划子表的官方字段原文未取到**；② U9 cloud 无公开帮助文档可抓。上表字段以 NC/U8C 帮助为准。

#### 23.1.2 金蝶云·星空

**结构**：销售订单表头有「收款计划」页签，由**收付款条件**基础资料单向带出（收款条件 → 收款计划），订单可改比例或金额；**控制环节带入后不允许手工维护**；到期日仅在「到期日计算日期 = 订单日期」且「收款方式 = 按到期日收款」时可改；要改建议走「订单新变更单」。

**收款计划行字段**

| 字段 | 说明 |
|---|---|
| 应收比例(%) | 与应收金额互算：**新增时算，修改时不重算** |
| 应收金额 | 同上 |
| 到期日 | **默认 = 单据日期**，可改（受上面条件限制） |
| 是否预收 | 布尔 |
| 控制环节 | 订购 / 发货 / 出库 / 生产 —— **无「开票」** |
| 关联单号 / 实收金额 | 下游回写 |
| ~~期次~~ / ~~收款状态~~ | ⚠️ **官方字段表未列，不要假设存在** |
| 结算方式 | **不在计划行**，在表头「财务信息」页签 |

**收付款条件基础资料**：预设「货到收款 / 30 天后收款 / 月结 30 天 / 多到期日（按金额）」四种；可设预收比例、到期日计算日期（订单日期 / 出库日期 / 应收单业务日期）、收款方式（按到期日 / 按订单 / 按物料明细）、标准（比例或金额）、确认方式（交易日 / 月结 / X 天后 / 固定日）。

**预收控发货：存在，但默认关闭**

- 官方原文：「预收是指在销售业务执行过程中，先向客户收取一定比例的款项，再进行交易。」
- 官方原文：「支持按收款计划控制商品订购、发货、出库和生产。」
- 官方原文（控制效果）：「只有达到预收金额，业务单据才能通过审核。」
- 但生效需要三重条件同时成立：收款条件勾「是否预收」+ 设控制环节 + 勾「按实际预收控制发货」，再加销售系统参数的控制时点。**未设置时，100% 预收仍可正常出库**。

**应收单与发票彻底分离**

- 官方原文：「应收账款通过应收单确认，应收单是债权成立的标志。」
- 主流程：订单 → 发货通知 → 销售出库 → **应收单** → 销售发票；收款单与应收单核销。
- 可设「出库单审核自动生成应收单」；立账模式有「业务应收 / 暂估应收」，后者开票后转财务应收并红冲。

> ⚠️ 「**收款计划管发货、发货管开票**」这个两级串联说法，**未找到任何官方原文**支撑。官方只证明「收款计划可控制发货/出库」，开票环节再未出现在任何控制枚举里。该说法属顾问总结，**不要写进我方设计依据**。

### 23.2 动因拆解：不是历史包袱，是四层约束叠加

用友/金蝶把收款计划做成订单级独立对象，是四个**互相独立、且都指向订单层**的约束共同挤压的结果。任一约束单独存在都不足以逼出这个设计。

**约束 1 · 发货前置的资金风控（业务动因）**

中国 B2B 大量行业是「先款后货」或「款到发货」：家电（格力 2008 年公告「内销全部先收款后发货」，2026 年中报合同负债 84.74 亿元）、工程、大宗贸易。这类业务的风险点不在「开票后收不到钱」，而在**「发货前没收到钱」**。所以控制点必须落在**发货/出库**，而发货发生在开票之前（金蝶流程里应收单甚至在发票之前）。⇒ 计划必须存在于**订单层**，因为它是发货的前置校验条件，不是开票的产物。这也解释了为什么两家的「控制环节」枚举都止于出库、都不含开票。

**约束 2 · 票据结算（金融动因）**

中国 B2B 结算高度票据化：央行数据，2025 年商业汇票承兑 42.7 万亿元、贴现 33.9 万亿元（2024 年 38.3 / 30.5 万亿；2020 年签发 22.1 万亿，五年翻倍）；2026 年上半年承兑额/GDP 达 33.2%（2017 年为 20.71%）；2025 年 1–11 月商票承兑同比 +26.43%、银票 +12.04%。上市公司层面，华锐精密招股书披露银行承兑回款占回款额约 29%–44%。

票据不是一条「银行流水」，它有自己的生命周期（出票 → 背书 → 贴现 → 到期托收 → 追索），并且**到期日与付款条件到期日不是一回事**。所以用友把「结算方式（含银行承兑汇票）」直接放进收款计划行，且期数/金额/方式逐行独立。A 派（付款条件多期）里付款条件只表达「多少天」，**表达不了「这一期收银承、下一期收电汇」**——这是把计划提到订单层的第二个硬理由。

**约束 3 · 增值税三时点解耦（税制动因）**

《发票管理办法》把发票定义为「收付款凭证」；《增值税法》第 28 条规定纳税义务发生时间为「收到销售款项或取得索取销售款项凭据的当天」，**先开具发票的，为开具发票的当天**。⇒ 开票即纳税。于是中国 B2B 天然存在三个**不同步**的时点：**发货 / 开票（纳税）/ 收款**。

当三个时点解耦，且都可能相隔数月（规上工业企业应收账款平均回收期 2022 年 52.8 天 → 2025 年末 67.9 天），财务必须在订单这一个业务事实上，同时挂住「已发多少 / 已开多少 / 应开未开 / 已收多少 / 应收未收」，才能对齐申报与账龄。⇒ 订单成为统一台账，收款计划是其中的现金维度。司法实践也印证这种解耦：「开票属从给付义务，除非合同明确『先票后款』，买方不得以未收票拒付」——即**开票与收款在法律上是可分离的两个义务**。

**约束 4 · 集团司库的月度资金计划（治理动因）**

国资委《关于中央企业加快建设世界一流财务管理体系的指导意见》要求司库体系覆盖资金预算与票据管理；地方国资（如江苏省国资委 2024 年通知）要求「年度预算定总盘、月度计划滚动调整」；云南能投等企业披露「销售订单—应收账款—银行流水」三单匹配实践。央企/国企客户的**回款预测必须落到订单级、月份级**，并可与票据到期日勾稽。A 派的到期行在开票后才产生，**接单时无法进入月度资金计划**。⇒ 计划必须在订单上。

**小结**：约束 1（发货前置）决定「挂在订单」，约束 2（票据）决定「计划行必须有结算方式与逐行独立」，约束 3（税制）决定「订单要当统一台账」，约束 4（司库）决定「接单即锁定、可按月汇总」。四条同时作用，就是用友/金蝶现在的形态。

### 23.3 中国特有 vs 被夸大（三条判断）

| # | 判断 | 证据 |
|---|---|---|
| 1 | **真正中国特有的是「票」和「税」，不是「分期」** | 分期/预付款/质保金全球普遍：英国建筑业 retention 通常 3–5%；SAP 早就有 billing plan 与 down payment；欧盟 2011/7/EU 指令企业间默认 30 天、最长 60 天。四段式（30% 预付 → 发货付至 60% → 验收付至 95% → 5% 质保金）在国内政府采购/上市公司合同中普遍，但**非中国独有** |
| 2 | **票据化 + 先开票即纳税 + 长账期，是中国的量级差异** | 商业汇票年承兑 42.7 万亿（2025）、占 GDP 33.2%；DSO 67.9 天（2025 末，规上工业）vs 欧洲中位数 48.5 天（Hackett 2025，二手引用）；A 股账期中位数约 75 天（Wind 二手引用）。增值税法第 28 条使开票行为本身产生纳税义务 |
| 3 | **工程预付款/质保金的比例是被法规锚定的** | 财政部《建设工程价款结算暂行办法》第十二条：工程预付款原则上**不低于合同额 10%、不高于 30%**；国办 2016 年通知：工程质量保证金**上限 5%**。所以「质保金单独一行、只允许一行」在国产 ERP 里是法规映射，不是随意设计 |

**反过来，「必须挂到销售订单行」这一层，多为实施做法而非统一强制** —— 用友/金蝶的官方文档只证明「订单上有收款计划页签」，未证明「所有业务都必须逐行挂」。这一点不要对客户宣称。

### 23.4 对我方 D3 的最终影响

| 问题 | 结论 |
|---|---|
| 用友/金蝶的设计是「中国业务特点」吗 | **部分是**。分期本身不是中国特有；把计划做成订单级独立对象，是**票据 + 税制三时点解耦 + 发货前置融资 + 集团司库**四条约束的叠加产物，其中票据与税制是量级上的中国特征 |
| 我方 Wave A 是否必须建 `payment_schedule` | **不必须**（命名裁决见 §23.6）。我方 Wave A 场景（`delivery` / `none`）不涉及预收控发货、不接票据、不做司库，D3-a（付款条件多期）足够 |
| 若未来做 D3-b，最小必备项 | ① 挂**订单头/行**（不是只挂付款条件）；② 计划行必须有 `settlement_method`（含银行承兑/商业承兑）；③ 必须有 `retention_amount`（质保金）与 `deposit_amount`（保证金）语义，且质保金建议限一行；④ 支持「起算时点 + 延迟」而非纯静态日期（用友做法）；⑤ **控制环节枚举到出库为止，不含开票** |
| 是否照抄「两级串联（计划控发货、发货控开票）」 | **不照抄**。该串联无官方原文（⚠️ §23.1.2），且与我方 D10 二选一冲突。正确关系是：`payment_schedule`（回款）与 `sales_order_schedules(kind='billing')`（开票）**正交**，互不写字段（命名裁决见 §23.6） |
| 对 D10 的影响 | **无**。收款计划只控「钱」，开票锚仍由 `billing_relevance` 决定 |
| 对我方字段命名的影响 | 加强 §2 判断：`sales_order_schedules` 现有的 `billing_percent/billing_amount` 若被业务读成「收款比例/收款金额」，必须改名或加注释，**明确它是开票里程碑** |

### 23.5 源链接与取证限制

用友：
- NC 收款协议/收款计划（术语与节点说明） — https://www.yonyou.com/ ⚠️ 帮助站为登录态 JS 渲染，原文经搜索快照取得
- U8+ 收付款协议档案 — https://www.yonyou.com/ ⚠️ 同上
- U8C 质保金/保证金 — https://www.yonyou.com/ ⚠️ 同上

金蝶：
- 金蝶云·星空 销售订单（收款计划页签、字段与控制环节） — https://vip.kingdee.com/ ⚠️ 需登录
- 金蝶云·星空 收付款条件 — https://vip.kingdee.com/ ⚠️ 需登录
- 金蝶云·星空 应收单与发票、立账模式 — https://vip.kingdee.com/ ⚠️ 需登录

法规与统计：
- 财政部《建设工程价款结算暂行办法》第十二条（预付款 10%–30%） — https://www.gov.cn/
- 国办 2016 年清理规范工程建设领域保证金通知（质保金上限 5%） — https://www.gov.cn/
- 《中华人民共和国增值税法》第二十八条（纳税义务发生时间） — https://www.gov.cn/
- 《中华人民共和国发票管理办法》（发票定义） — https://www.gov.cn/
- 国资委《关于中央企业加快建设世界一流财务管理体系的指导意见》 — http://www.sasac.gov.cn/
- 中国人民银行《2025 年支付体系运行总体情况》（商业汇票承兑/贴现） — http://www.pbc.gov.cn/
- 国家统计局 规上工业企业应收账款平均回收期 — https://www.stats.gov.cn/

> ⚠️ 取证限制：① 用友/金蝶官方帮助站需登录且有 JS 渲染，字段表与控制环节枚举来自检索快照与实施文档交叉，**未取得可公开链接的逐字原文**；② 国际对比数据（欧洲 DSO 48.5 天、A 股账期中位数 75 天）为二手引用，口径可能与我方统计不同，仅用于量级判断；③ 「四段式比例区间」为行业共识，无全国性调查支撑，**不作为设计输入**；④ 「收款计划必须挂订单行」无官方强制原文。

---

### 23.6 命名裁决：`collection_schedule` → `payment_schedule`

**结论：改。** 统一为 `payment_schedule`（表 `payment_schedules`），中文显示名固定为「**收付款计划**」；订单上的互斥枚举同步改名 `payment_relevance`（值 `invoice_term` / `order_plan` / `none`）。§23.4 及之前出现的 `collection_schedule` / `collection_relevance` 一律按此替换。

| # | 理由 | 依据（当前 HEAD 实证） |
|---|---|---|
| 1 | **平台既有命名已经是双侧共用** | `meta/schemas/payment_term.yaml` 头注释原文「销售 / 采购共用的收付款账期规则（头）」，且被 `sales_order.payment_term_id` 与 `purchase_order.payment_term_id` 同时引用。再新造一个 `collection_*` 会与 `payment_term` 割裂成两套词族 |
| 2 | **采购侧确实需要一个同类对象** | `purchase_order.payment_term_id` 已存在（`purchase_order.yaml` L747–L786）；但采购侧计划层目前**只有到货/服务**——`purchase_order_schedule.yaml` 头注释原文「采购侧开票计划由发票 spec 处理，不在本对象承载」，`schedule_kind` 枚举只有 `delivery` / `service`。应付分期当前无处落地 |
| 3 | **行业同名词可直接对标** | 微软 D365 `Payment schedule`（表 `CustPaymSched` / `CustPaymSchedLine`）；Infor LN `Payment Schedule` 主数据（头 `tcmcs220`、行 `tcmcs221`）；Oracle `AP_TERMS` 家族。§21 取样的 10 个产品里没有一个叫 `collection schedule` |
| 4 | **`collection` 语义单向、偏催收** | 英文 collection = 催收 / 回款归集，天然是应收视角；应付侧的反向词就是 payment。硬用 `collection` 会读成「向供应商催收」 |
| 5 | **中文名一次消歧** | 显示名用「收付款计划」，比「收款计划」覆盖更全，且与「付款条件」同词族，UI 上并列出现不突兀 |

**反对意见与处理**：中文语境下 `payment` 常被直译成「付款」，有被读成「只做应付侧」的风险。处理方式不是换名，而是三重兜底——① 表内 `direction`（`receivable` / `payable`）做硬侧别；② UI 按来源单据类型默认过滤（销售订单详情只显示 `receivable`）；③ 中文显示名固定「收付款计划」，不得简写为「付款计划」。

**不选 `settlement_schedule` 的原因**：「结算」在中文 ERP 语境已被 `settlement_method`（结算方式）占用，「结算计划」又易与「结算中心 / 汇算」混淆；且与已有 `payment_term` 词族不一致。

---

### 23.7 对象模型：`payment_schedule` + `payment_schedule_line`

**定位**：订单级**回款/付款节奏的实例**。既不是模板（模板是 `payment_term`），也不是事实（事实是 `receipt` / 付款单）。头 = 一张计划，行 = 一期。

沿用本平台已验证的「一头多行 + `child_sections`」形态（同 `payment_term` → `payment_term_line`、`purchase_order` → `purchase_order_schedule`）。

#### 23.7.1 头：`payment_schedule` / `payment_schedules`

| 分组 | 字段 | db_column | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 标识 | id | id | integer | 是 | 主键 |
| | schedule_no | schedule_no | string(30) | 是 | 业务编号；**同一来源单据内唯一**，不走全局号码段（不启用六件套取号） |
| 侧别 | direction | direction | string(10) | 是 | `receivable` 应收 / `payable` 应付；决定 `settled_amount` 是「已收」还是「已付」 |
| | party_account_id | party_account_id | integer | 是 | 往来方（应收 = 客户；应付 = 供应商）⚠️ 见 §23.11 遗漏项 6 |
| | currency_id | currency_id | integer | 是 | 与来源单据币种一致；**只存原币，不落本币**（避免与发票汇率二次折算打架） |
| 来源 | source_doc_type | source_doc_type | string(32) | 是 | `sales_order` / `purchase_order` / `customer_invoice` / `vendor_invoice` / `manual` |
| | source_doc_id | source_doc_id | integer | 是 | 来源单据头 id |
| | source_line_id | source_line_id | integer | 否 | 空 = 整单级计划；非空 = 订单行级计划 |
| 模板 | payment_term_id | payment_term_id | integer | 否 | 实例化来源，**只读追溯**；空 = 手工建的计划 |
| | basis_date_rule | basis_date_rule | string(20) | 是 | 实例化时**快照**头上的口径（不进 `payment_term_line`）；模板后续改动不回写 |
| | cutoff_day | cutoff_day | integer | 否 | 同上快照 |
| 金额 | total_amount | total_amount | number(18,4) | 是 | Σ 行 `plan_amount`，服务层汇总，前端只读 |
| 状态 | status | status | string(20) | 是 | `draft` / `active` / `closed` / `cancelled` |
| 组织 | org_id | org_id | integer | 是 | 财务归属 |
| 其他 | remark | remark | text | 否 | 备注 |
| 审计 | created_by / created_at / updated_at | 同名 | — | — | `audit_aspect` |

**不声明**：`document:` 六件套（无独立号码段、无 `business_date_field`、无过账）、`revision_policy`、`display_name_field`（用 `schedule_no` 即可）。

#### 23.7.2 行：`payment_schedule_line` / `payment_schedule_lines`

| 分组 | 字段 | db_column | 类型 | 必填 | 说明 |
|---|---|---|---|---|---|
| 标识 | id / schedule_id / seq | 同名 | integer | 是 | 行主键 / 父键 / 期次（`schedule_id + seq` 唯一） |
| 起算 | basis_point | basis_point | string(20) | 是 | `order_date` / `delivery_date` / `invoice_date` / `month_end`；**逐行独立**（修掉 `payment_term.basis_date_rule` 头级单值的缺陷） |
| | offset_months | offset_months | integer | 是 | 0–60，默认 0 |
| | fixed_day_of_month | fixed_day_of_month | integer | 否 | 1–31；空 = 保持基准日的日 |
| | offset_days | offset_days | integer | 是 | 0–999，默认 0 |
| | due_date | due_date | date | 否 | **计算后落库的只读快照**；`basis_point=invoice_date` 且发票未生成时为空 |
| 金额 | percentage | percentage | float | 是 | 0 < p ≤ 100；Σ=100 由 `assert_schedule_complete` 使用前校验（对齐 `payment_term_guard` 的 G1 口径：写时只拦 >100） |
| | plan_amount | plan_amount | number(18,4) | 是 | = percentage × 头基数；**允许手工覆盖**（对齐用友「收款金额可手工」） |
| | retention_amount | retention_amount | number(18,4) | 否 | 质保金；**建议全表限一行**（对齐用友 NC「只一行可设质保金」、国办 2016 质保金上限 5%） |
| | deposit_amount | deposit_amount | number(18,4) | 否 | 保证金（应收 = 预收保证金 / 应付 = 预付保证金） |
| 结算 | settlement_method | settlement_method | string(20) | 否 | `cash` / `bank_transfer` / `cheque` / `cashier_cheque` / `bank_acceptance` / `commercial_acceptance` / `letter_of_credit` / `other`。**必须落在计划行，不能放进 `payment_term_line`**（见 §23.9） |
| | is_prepayment | is_prepayment | boolean | 是 | 默认 false；true 时 `basis_point` 通常为 `order_date` |
| 事实回写 | settled_amount | settled_amount | number(18,4) | 否 | **只读缓存**，由 `receipt` / 付款单核销时回写 |
| | related_doc_no | related_doc_no | string(64) | 否 | 关联单号（下游回写、只读；轻量方案，见 §23.10） |
| | settled_at | settled_at | date | 否 | 最后核销日 |
| 状态 | status | status | string(20) | 是 | `planned` / `partial` / `settled` / `cancelled` |
| 说明 | description | description | text | 否 | 期次说明（首付款 / 发货款 / 验收款 / 质保金） |
| 审计 | created_at / updated_at | 同名 | — | — | 派生列从 `audit.update.exclude` 排除（对齐 `purchase_order_schedule` 对 `received_qty` 的处理） |

**到期日计算口径**（与 `meta/services/payment_term_schedule_service.py::compute_schedule` 同构，消费方不得自行解释）：
1. 基准日 = `basis_point` 指向的单据日期；若头 `cutoff_day` 非空且单据日 > cutoff_day ⇒ 基准月顺延一月；
2. 先加 `offset_months`；`fixed_day_of_month` 非空 ⇒ 落到该月第 N 天（超过当月天数取月末）；
3. 再加 `offset_days` ⇒ 到期日（写 `due_date`）。

---

### 23.8 关系模型

```
payment_term ──(模板/实例化一次, 单向)──▶ payment_schedule ──┬─▶ payment_schedule_line
   (头+行, 无金额无状态)                    (头, 有侧别/来源)   │       │
                                                              │       ├─(核销回写 settled_amount)─▶ receipt / 付款单
sales_order.payment_term_id ─────────────────────────────────┘       │
purchase_order.payment_term_id ──────────────────────────────┘       ├─(轻量) related_doc_no ─▶ customer_invoice / vendor_invoice
                                                                      └─(严谨) payment_schedule_allocation ─▶ customer_invoice_line
```

| 边 | 基数 | 关系性质 | 约束 / 写入口 |
|---|---|---|---|
| `payment_term` → `payment_schedule` | 1 : N | **模板 → 实例**，单向 | 实例化只在建单/审核时发生一次；模板后续改动**不回写**实例（快照 `basis_date_rule` / `cutoff_day` / 各期参数） |
| `sales_order` / `purchase_order` → `payment_schedule` | 1 : 1（默认） | 来源挂载 | 由 `payment_relevance`（订单侧枚举）决定是否生成；`order_plan` 才建，`invoice_term` / `none` 不建 |
| `payment_schedule_line` → `receipt`（应收）/ 付款单（应付） | 1 : N | **事实核销** | `receipt` 过账时按行核销，回写 `settled_amount` / `settled_at` / `related_doc_no` + 行状态；红冲按流水重算 |
| `payment_schedule_line` → `customer_invoice` / `vendor_invoice` | N : M | 轻量：`related_doc_no` 单列；严谨：分配表 | 见 §23.10 |
| `payment_schedule` ↔ `sales_order_schedules(kind='billing')` | **正交** | 互不写字段 | 一个管「钱」，一个管「开票里程碑」；禁止互相回写（§23.4） |
| `payment_schedule` ↔ `purchase_order_schedule` | **无关系** | 分属不同层 | 后者只承载到货/服务（本文件头注释已排除开票与付款） |

**订单侧枚举 `payment_relevance`**（三值互斥，默认 `invoice_term`）：

| 值 | 含义 | 计划来源 | 收款口径 |
|---|---|---|---|
| `invoice_term` | A 派，默认 | **不建** `payment_schedule` | 每张发票按 `payment_term` 各自展开账期（D3-a） |
| `order_plan` | B1 派（用友/金蝶形态） | 建 `payment_schedule` | 计划为唯一权威；发票只做占用对象，不再按 `payment_term` 二次展开（D3-b） |
| `none` | 全额预付 / 不计收款 | 不建 | 无账期语义（Wave A 可支持） |

> 互斥的意义：**同一批钱不能双算**。`invoice_term` 与 `order_plan` 同时生效就是「两层收款并存」，是 §23.1 用友/金蝶用「起算时点 + 延迟」字段极力避免的重复计算。

---

### 23.9 与既有对象的边界（防重复建对象）

| 既有对象 | 处置 | 理由 |
|---|---|---|
| `payment_term` / `payment_term_line` | **复用，结构不改** | 模板层已完整：`basis_date_rule`（头）+ `offset_months` / `fixed_day_of_month` / `offset_days` / `discount_*`（行），恰好就是「起算时点 + 延迟」的表达 |
| `payment_term_line.settlement_method` | **不加** | `payment_term.yaml` 头注释已明写「不建模付款方式（银行转账 / 票据 / 信用证）—— 属支付域」。且模板一行会被多张订单共用，塞结算方式必然污染 |
| `sales_order_schedules(kind='billing')` | **禁止新增 `kind='payment'`** | 四条：① 履约计划是数量/金额里程碑，payment 计划是纯金额；② payment 计划跨发票、生命周期长于订单；③ payment 计划有结算方式 / 质保金 / 保证金，billing 计划没有；④ 采购侧没有对称的 billing 计划，塞进 `sales_order_schedules` 采购侧无处安放 |
| `purchase_order_schedule` | **不复用** | 头注释已限定 `delivery` / `service`；语义是「到货承诺」不是「付款承诺」 |
| `customer_invoice.payment_term_id`（§4 已定） | **保留** | 发票上的 `payment_term` 是 A 派口径的起点；与订单级 `payment_schedule` 由 `payment_relevance` 二选一，互斥 |
| `receipt` / 付款单（`spec-receipt-object-model-2026-11-01.md`） | **事实层，不反向建计划** | 只回写 `settled_amount` / `settled_at` / `related_doc_no` |
| `payment_due_list`（到期清单） | **不建表** | 投影：`WHERE due_date <= today AND status IN ('planned','partial')`。对齐 SAP `VF04` 为程序不落表、g15 L1/L2 边界 |

---

### 23.10 计划与发票的分配：轻量 vs 严谨（二选一）

| 方案 | 做法 | 优点 | 缺点 | 采用时机 |
|---|---|---|---|---|
| **轻量**（推荐 Wave B） | 行上单列 `related_doc_no` + `settled_amount` 回写 | 零新表；对齐用友「关联单号 / 实收金额下游回写」与金蝶同名字段 | 一期覆盖多张发票时明细丢失，无法按发票对账 | 订单级计划 + 发票数量少的场景 |
| 严谨 | 新增 `payment_schedule_allocation(id, schedule_line_id, invoice_id, invoice_line_id, allocated_amount)` | 可对账、可按发票核销、可做账龄 | 一张新表 + 金额不超限校验 | 出现「一期覆盖多张发票」或需要按发票对账时再升 |

> 判断口径：**Wave B 不建分配表**。理由：Wave B 的订单通常是「一张订单 → 一张或少数几张发票」，FIFO 分配结果不需要持久化；一旦引入分配表，就同时要引入「反分配 / 重分配」事务，复杂度不成比例。

---

### 23.11 补充与遗漏清单（对照 §23.4 最小必备项逐条核）

**本轮补上的（原模型里缺的）**：

| # | 补上的点 | 原缺口 |
|---|---|---|
| 1 | 侧别中立 `direction`（`receivable` / `payable`） | 原 `collection_schedule` 是单侧命名，采购应付无处落地 |
| 2 | `settlement_method` 落在**计划行** | §23.4 最小必备项②只有「要有」，没有落点；且 `payment_term` 已声明不建模票据 |
| 3 | `retention_amount` / `deposit_amount` | 最小必备项③缺字段；质保金「限一行」靠守卫而非字段 |
| 4 | **逐行** `basis_point` | 现有 `payment_term.basis_date_rule` 是头级单值，无法表达「预付按订单日、尾款按发票日」 |
| 5 | `payment_relevance` 三值互斥 | 前次仅口头结论；不落枚举就会出现两层收款并存 |
| 6 | 与 `purchase_order_schedule` 的边界 | 两者都叫 schedule，极易被误合并 |
| 7 | 到期清单明确「不建表」 | 防止照抄金蝶/用友做成实体清单 |

**仍是遗漏 / 落地前必须决策**：

| # | 问题 | 现状 | 建议 |
|---|---|---|---|
| 1 | 是否启用六件套 `document:` | 计划不是单据 | **不启用**；保留 `status` + `rules: state_transition`（对齐 `purchase_order_schedule`） |
| 2 | 是否进 doc_flow | 计划不产生单据流 | **不进**；只有 `receipt` / 付款单进 |
| 3 | 订单审核后能否改计划 | 用友「收款状态下游回写不可改」、金蝶「带入后不允许手工维护」 | 订单 `submitted` 起冻结行编辑，`draft` 期可调 |
| 4 | 预收控发货 | 我方无控制参数 | Wave B **不实现**；若做，加控制参数 `prepayment_control_level`，枚举**只到发货/出库、不含开票** |
| 5 | 本币金额 | — | 不做；头只存原币，本币在发票/凭证侧算 |
| 6 | **采购侧往来方对象** | `customer_account` 与供应商账户是否同表**未取证** | ⚠️ 落地前必须先确认；若不同表，`party_account_id` 要么拆两列，要么改多态键（`party_type` + `party_id`） |
| 7 | 迁移号 | v231 为当前最大，v232 已分配给 `customer_invoice` | `payment_schedule` 用 **v233**，与 v232 解耦（D3-a 时不建表，v233 不产出） |
| 8 | 权限 | — | `payment_schedule:create/update/delete`，`owner_auto_permission: false` |
| 9 | UI 入口 | `purchase_order.yaml` L1530 已有 `child_object: purchase_order_schedule` 先例 | 销售/采购订单详情各加一个 `child_sections` tab「收付款计划」；`skip_auto_menu: true` |
| 10 | 行级 vs 单级计划并存 | 头有 `source_line_id` | 默认整单级（`source_line_id` 空）；只有按行约定付款时才落行（避免与 `payment_term` 逐行分裂叠加） |

---

### 23.12 D3 决策（命名更新版，待拍板）

| 选项 | 含义 | 建表 | 适用 |
|---|---|---|---|
| **D3-a**（Wave A 采用） | 只保留 `payment_term` 多期，发票按账期展开；订单上不建计划 | 不建 | 我方 Wave A（`delivery` / `none`）、不接票据、不做司库 |
| **D3-b** | 建 `payment_schedule` + `payment_schedule_line`，订单上 `payment_relevance='order_plan'` | v233 | 需要预收控发货、票据结算、集团月度资金计划 |
| **D3-c** | 只做单期预付（订单上存一个 `prepaid_percent`），不做多期 | 不建 | 极简场景，不建议（无法覆盖质保金） |

> **建议**：Wave A 走 D3-a，不建表；`payment_schedule` 的设计冻结在 §23.7–§23.10，留给 D3-b 时直接落地，避免二次返工。

---

### 23.13 「起算时点」的语义与可选值域（本轮确认）

**你的理解方向正确，但需要拆成三件事**，否则会把「起算点」和「期数结构」混成一件事。

#### 23.13.1 先给结论

| 问题 | 结论 |
|---|---|
| 起算时点 = payment term 的起算时点？ | **是**。四个体系用的是同一个概念：账期公式的自变量（起点） |
| 它是否"决定了 payment 计划"？ | **决定两件**：① 日期分布（`due_date` 落在哪天）；② **计划组的粒度**（以哪一批事实为一组、这一组多少钱）。**不决定**期数与每期比例——那是 `seq` / `percentage` / `offset_months` / `offset_days`。详见 **§23.14** |
| 起算时点是否只能是 billing（开票日）？ | **不是**。开票日只是最常见的默认值 |
| 会不会是出库 / 发货 / 订单？ | **会，三种都真实存在**，均有官方字段级证据 |
| 还有我方没有的类型吗？ | **有 4 类**：合同生效日、收票日、独立出库日、系统日 |

> 一句话：**X 轴是"分几期、每期多少"（payment_term_line），Y 轴是"从哪天开始算 + 以哪批事实为一组"（起算点）**。起算点不改变期数与比例，但会改变**组的个数与每组的钱**（§23.14）。

#### 23.13.2 行业取证（起算点的官方可选值）

| 体系 | 官方术语 | 可选值 | 出处 / 备注 |
|---|---|---|---|
| Oracle Payables | **Terms Date Basis** | System Date / Goods Received Date / Invoice Date / Invoice Received Date | 原文："Terms Date is the **beginning date** from which Payment Terms start"；即"起算日"逐字对应 |
| SAP FI | **Baseline Date**（`BSEG-ZFBDT`） | Entry Date / Document Date / Posting Date（部分场景 Goods Receipt Date） | SAP 认证题「default baseline date 可从哪些日期派生」答案为 Entry / Document / Posting |
| SAP SD | **Billing Date** | 实际由 goods issue（实际发货）决定 | 说明"以开票日起算"与"以发货日起算"**并不总是两个独立选项**：开票日本身可能是发货派生的 |
| 用友 NC / U8C | **起效日期**（参照档案「收款时点-集团」） | **出库日期 / 出库单签字日期 / 销售开票日期 / 销售发票审核日期 / 销售订单日期 / 销售合同生效日期** | 档案化预置，可扩展；这是覆盖面最广的一套 |
| 金蝶 | **到期日计算日期** | 系统预设 订单日期 / 入库日期 / 收料日期 / 应付单业务日期，用户可增补单据上的其它日期 | 采购侧预设；与"设置标准（比例/金额）+ 确认方式（交易日/月结/X 天后/固定日）"组合使用 |

**读这张表最关键的一点**：把可选值按**语义层**归并后，只有三类起点，且每类都是"在哪一层事实发生"：

| 层 | 起点 | 谁在用 |
|---|---|---|
| ① 业务承诺 | 订单日、合同生效日 | 预收款（钱先到、履约未发生） |
| ② 履约事实 | 发货日、出库日、出库单签字日、到货日、收货日 | 发货后收款（中国主流，控发货场景） |
| ③ 结算事实 | 开票日、发票审核日、收票日 | 开票后收款（Oracle AR 默认、我方默认） |
| ④ 控制/技术日 | 系统日、录入日 | Oracle AP 的 System Date；**不建议业务使用**（不可审计、跨时区漂移） |

因此"起算时点是不是 billing"的正确回答是：**billing 属于第 ③ 层，是可选值之一，不是唯一值；而第 ①②③ 层之间可以按行混用**（用友正是靠"头定起效日期 + 行定延迟"实现这一点）。

#### 23.13.3 我方现状（已支持什么）

```
payment_term.basis_date_rule      # 头级单值，模板默认；default = invoice_date
  ├ invoice_date   开票日          # 第 ③ 层
  ├ delivery_date  发货日          # 第 ② 层
  ├ order_date     订单日          # 第 ① 层
  └ month_end      月末            # 口径修饰（把起点对齐到月末）

payment_term_schedule_service.resolve_base_date(term, trigger_date)
  # 关键实现细节：先按 basis_date_rule 选定"用哪个口径"，
  # 再由调用方传入 trigger_date（该口径对应的实际单据日期），
  # month_end 复用 invoice_date 字段作为 trigger（BASE_DATE_FIELD 已声明）
```

**结论**：你提的"出库 / 发货 / 订单"里，`delivery_date` 与 `order_date` **已经在支持范围内**，不是新需求。真正缺的是更细的粒度。

#### 23.13.4 还缺什么（按缺口排序）

| 起算点 | 语义层 | 我方能否表达 | 差什么 |
|---|---|---|---|
| 出库日（goods issue） | ② 履约事实 | 只能用 `delivery_date` **近似** | `shipment` 只有 `actual_ship_date` / `actual_arrival_date`，**没有独立的出库过账日**（即 §1 已记的 doc-flow G3 缺口）；出库 ≠ 发货，混用会让起算日提前 |
| 出库单签字日 | ② 履约事实 | 不能 | 用友独有粒度；我方无签字动作 |
| 到货日 | ② 履约事实 | 不能（未入枚举） | `shipment.actual_arrival_date` **已存在**，只需加一个枚举值，零结构改动 |
| 发货日 | ② 履约事实 | **能** | — |
| 订单日 | ① 业务承诺 | **能** | — |
| 合同生效日 | ① 业务承诺 | 不能 | 我方无独立合同对象，只能用 `sales_order.order_date` 近似；若后续上合同对象须补枚举 |
| 开票日 | ③ 结算事实 | **能（默认）** | — |
| 发票审核日 | ③ 结算事实 | 不能 | 用友粒度；我方开票即过账，无"审核"独立事件 |
| 收票日（invoice received） | ③ 结算事实 | 不能 | 仅采购侧有意义，需 `vendor_invoice.received_date`；销售侧无此概念 |
| 系统日 / 录入日 | ④ 控制日 | 不能 | **建议不做**（Oracle AP 有，但业务与审计上都是坑） |

**建议**：Wave A 不新增枚举值（现有四值已覆盖 Wave A 的 `delivery` / `none`）；补 `actual_arrival_date`（到货日）成本最低、收益明确，可列入 Wave B 的枚举扩展；`goods_issue_date` 必须**等 doc-flow G3 出库过账落地后**再加，否则枚举名与数据语义不符。

#### 23.13.5 头级 vs 行级：这不是矛盾

| 落点 | 字段 | 性质 | 能表达什么 |
|---|---|---|---|
| `payment_term`（模板） | `basis_date_rule` | **头级单值**，所有行共用 | "这个账期条件一律从开票日起算" |
| `payment_schedule_line`（实例，§23.7） | `basis_point` | **行级独立** | "预付款按订单日、尾款按发票日" |

两者是**模板默认值 → 实例可覆盖**的关系，不冲突。**需精确订正上轮表述**：

> 准确说法是「**`payment_term` 模板层**表达不了不同期不同起算点」，**不是**「整个方案表达不了」。`payment_schedule_line.basis_point` 逐行独立，就是用来承接这种场景的（§23.14.1）。
> 更关键的是：**预付款本来就不该由 `payment_term` 表达** —— 账期的语义是「开票后多少天付款」，而预付款发生在开票之前，它没有账期。所以这不是"模板字段不够"的缺陷，而是对象分工。

**因此不建议**给 `payment_term_line` 加行级 `basis_date_rule`：会与 `payment_term_line` 的既有定位（只描述"什么时候付多少"，见其头注释）冲突，且与 §23.9 的边界表矛盾。差异一律留在 `payment_schedule_line`。

#### 23.13.6 术语订正

不需要改名字：`basis_date_rule`（口径）与 `trigger_date`（实际传入的单据日期）已经是两个不同的东西，命名正确。用户口语里的"起算时点"= **口径**（rule），"起算日"= **取到的那个日期**（date）——建议后续文档统一按此二分，避免再把"口径"和"日期"说成一个词。

---

### 23.14 起算点的第二个作用：它同时是「计划组的分组键」

> 本节回答两个具体追问：①「每个阶段各自设计算时点」为什么不是模板层的事；② 起算点选的那批事实，是否同时提供「起算日」和「金额基数」。

#### 23.14.1 问题 A：三个层次，只有中间那层能逐期不同

| 层 | 对象 | 能否「第 1 期用订单日、第 2 期用发票日」 | 原因 |
|---|---|---|---|
| ① 模板层 | `payment_term` + `payment_term_line` | **不能** | 头级 `basis_date_rule` 单值；行级只有正向 `offset_months` / `offset_days`，无法表达"第 1 期早于基准日" |
| ② 计划实例层 | `payment_schedule` + `payment_schedule_line` | **能（已如此设计）** | §23.7.2 的 `basis_point` **逐行独立**，第 1 行填 `order_date`、第 2 行填 `invoice_date` 即可 |
| ③ 事实层 | 发票 / 发货 / 订单本身 | 不适用 | 日期是既成事实 |

**所以你的理解在 ② 层是对的**：预付款阶段、尾款阶段各自设自己的计算时点，`payment_schedule_line.basis_point` 就是干这个的。上轮说的"表达不了"**只针对 ① 模板层**，且真正的理由不是"字段不够"，而是：

> **预付款不属于账期语义。** `payment_term` 描述的是"**开票后**多少天付款"；预付款发生在开票**之前**，它根本没有账期。所以预付款由计划实例（或订单上的预付比例）承载，尾款由 `payment_term` 承载 —— 这是对象分工，不是缺陷。

行业佐证：Oracle AR 里预收款（Prepayment）是**独立事务类型**、先收款后核销发票，**不走 Payment Terms**；`AR_PAYMENT_SCHEDULES_ALL` 的每一行是挂在发票上的 installment（`DUE_DATE` + `AMOUNT_DUE_ORIGINAL`）。

#### 23.14.2 问题 B：起算点 = 事实粒度选择器（不只是日期规则）

**你的第二点理解基本正确，但漏了一环**：起算点选的是"**以哪一批事实为单位**"，这批事实同时提供 **起始日期 + 金额基数**。所以它实际是一个**分组键（granularity key）**，而不是单纯的日期口径。

| 起算口径 | 一个计划组 = | 组的起始日 | 组的金额基数 | 开 2 次票（20 / 50）的结果 |
|---|---|---|---|---|
| `invoice_date` | **一张发票** | 该发票开票日 | **该发票净额** | **2 个计划组**，20 与 50 各按自己的开票日展开期次——**与你描述完全一致** |
| `delivery_date` | **一次发货** | 该次发货日 | 该发货对应的**已定价金额**（通常 = 其开票额） | 若 2 次发货分别开票 ⇒ 2 组；若合并成 1 张票 ⇒ 仍是 2 个日期锚但金额按开票拆分 |
| `order_date` | **整张订单** | 订单日 | **订单净额** | 只有 **1 个计划组**（基数 = 70），2 次开票不改变组的数量，只影响核销 |

> 一句话：**改起算点 = 改"以哪批事实为一组" = 改组的个数与每组的钱**。期数比例（X 轴）不变，但组数（Y 轴的分组粒度）会变。

#### 23.14.3 关键修正：日期来自事实，金额基数通常来自「带价单据」

你的"设出库就以出库实际数量为基数"在**数量**意义上成立，在**金额**意义上要加一条前提：

| 事实 | 有日期 | 有价格/金额 | 能否直接当金额基数 |
|---|---|---|---|
| 订单 `sales_order` | 有（`order_date`） | **有**（净额/税额/总额） | **能**（预收款场景直接用） |
| 发货 `shipment` | 有（`actual_ship_date`） | **无**（`shipment_line` 无单价、无金额） | **不能直接当**，须先经开票定价，取"该发货对应的开票金额" |
| 发票 `customer_invoice` | 有（`invoice_date`） | **有**（行净额/税/总额） | **能**（默认口径） |

> 所以标准链路是：**履约事实（发货/出库）→ 定价固化（开票）→ 收款计划**。日期可以取履约事实的日期（第 ② 层），但**金额基数必须取带价单据**。
> 唯一例外是"发货即确认收入 / 无票销售"——需要出库单自带价，我方当前不具备（`shipment_line` 无价、doc-flow G3 出库过账也未落地）。**不建议为这个例外改结构。**

行业取证：
- **Oracle AR**：`AR_PAYMENT_SCHEDULES_ALL` 按**发票（`TRX_DATE`）**生成 installment 行，每行 `DUE_DATE`（到期日）+ `AMOUNT_DUE_ORIGINAL`（金额基数）；Payment Terms 只负责算 `DUE_DATE`，**不收钱、不定额**。
- **SAP FI**：Baseline Date（`BSEG-ZFBDT`）只是"到期日计算的基础"，金额始终来自凭证（发票）本身；付款条件只决定到期日与现金折扣。
- **Oracle AP 的一个补充事实**：应付侧起算日并非简单单选，而是 `Greatest(Goods_Received_Date + Receipt_Acceptance_Days, Invoice_Date, Terms_Date)` —— **取多个候选日中最晚的一个**。这说明"起算日"在行业里也可以是**复合口径**，但应收侧（我方主战场）仍是单口径。

#### 23.14.4 对我方模型的映射（无结构改动，只补口径）

§23.7.1 已经有承载分组键的字段，无需新增列：

| 分组粒度 | `payment_schedule.source_doc_type` | `source_doc_id` | 基数取值 | 对应 `payment_relevance` |
|---|---|---|---|---|
| 每张发票一组 | `customer_invoice` | 该发票 id | 发票 `net_amount`（或 `gross_amount`，按价税口径定） | `invoice_term`（默认） |
| 整张订单一组 | `sales_order` | 订单 id | 订单 `net_amount` | `order_plan` |
| 手工 | `manual` | 空 | 手填 `plan_amount` | `none` |

- **`invoice_term`（默认）**：订单上**不建**计划；每张发票过账时按 `payment_term` 展开，生成 `source_doc_type=customer_invoice` 的计划 —— 天然做到"开 2 次票 = 2 组"。
- **`order_plan`**：订单上建 1 组，行可按不同 `basis_point`（预付 `order_date`、尾款 `invoice_date`），但**基数始终是订单净额**。
- 两者互斥（§20 的 D10 二选一），正好对应用户描述的两种模式。

**待补的一条口径（写进实施清单，不改结构）**：`payment_schedule` 头应显式记录**基数金额**（建议名 `base_amount`，与 `total_amount = Σ plan_amount` 区分），否则"手工覆盖 `plan_amount`"之后无法追溯"百分比是按谁的百分比"。当前 §23.7.1 只有 `total_amount`，属遗漏。

#### 23.14.5 对 §23.13 的三处订正

1. §23.13.1 「只决定日期分布」→ 已改为「决定日期分布 **+ 计划组粒度**」。
2. §23.13.5 「模板层表达不了」→ 已限定为「**`payment_term` 模板层**」，并补充"预付款不属于账期语义"的对象分工理由。
3. 新增本条结论：**起算点不只是 Y 轴，它还是"组的划分方式"**；因此"选 invoice_date 还是 delivery_date"在业务上等价于问"**按票收款还是按发货收款**"。

---

### 23.15 预付款与账期的判据：不是「有没有 billing」，而是「基数来自哪一层事实」

#### 23.15.1 问题 1：「有 billing 才算非预付款」——当前实现下成立，业务判据上不成立

| 判断口径 | 结论 |
|---|---|
| 作为我方 Wave A 的实现约束 | **成立**：`shipment_line` 无 `amount` / `price` 字段（已核实），发货事实不带价 ⇒ 非预付款的金额基数只能来自发票 |
| 作为一般业务判据 | **不成立**：真正的判据是「**金额基数取自承诺层还是结算层**」，billing 只是当前唯一稳定可用的结算层带价单据 |

| 基数来源 | 收款性质 | 是否有 billing |
|---|---|---|
| 承诺层：订单 / 合同金额 | **预收**（钱先到，履约与结算均未发生） | 无 |
| 结算层：带价单据金额 | **后收**（账期） | 通常是发票；若履约单据自带价（发货即确认收入 / 寄售结算 / 服务按期确认），也可不带 billing |

> 所以准确的表述不是"非预付款必须有 billing"，而是"**非预付款的基数必须来自一张带价单据；在我方当前模型里，发票是唯一带价的结算单据**"。

**中国场景必须注意的例外**：预收款也常常开票（不征税发票 / 收据）。因此"**有没有票**"不能当判据 —— 要区分「业务开票（确认收入的事实）」与「票据（税务凭证）」。我方 `customer_invoice` 只承载前者，后者属票据域，不进 L1 业务事实。

#### 23.15.2 问题 2：预付款基数 = 订单金额 —— 成立，且我方字段齐备

| 需要的基数 | 我方字段 | 位置 | 结论 |
|---|---|---|---|
| 订单净额 | `sales_order.net_amount` | `sales_order.yaml` L1279 | 有 |
| 订单税额 | `sales_order.tax_amount` | L1295 | 有 |
| 订单含税合计 | `sales_order.gross_amount` | L1311 | 有 |

`sales_order.yaml` L1781 注释已明确：`total_amount -> gross_amount（含税合计，订单总额口径）`。

**建议**：预付款基数默认取 **`gross_amount`（含税合计）** —— 客户实付的是含税金额；税额在后续正式开票时冲抵，预付阶段不拆分。这也与订单"总额口径"保持一致，避免同一张订单出现两个总额定义。

#### 23.15.3 三个必须定的落地口径（列入 Wave B 清单）

| # | 口径 | 建议 | 理由 |
|---|---|---|---|
| 1 | 基数含税与否 | 默认 `gross_amount`；全局统一，不允许按单据自选 | 与实际收款一致，避免预付/开票两套总额 |
| 2 | 订单变更时预付款是否重算 | **不自动重算**；差额在后续发票体现；订单金额改动时校验并提示「预付款比例已偏离」 | 预款是已发生事实，不得被主数据变更回写篡改 |
| 3 | 预付款核销 | 必须在正式发票上冲抵；落在 `payment_schedule_line.settled_amount` + `related_doc_no` | 对齐 Oracle AR：Prepayment 先收款、后核销到 invoice |

#### 23.15.4 一句话收口

- **预付款**：基数 = 订单 `gross_amount`（承诺层），起算日 = `order_date`，**无 billing**。
- **账期**：基数 = 发票金额（结算层），起算日 = `invoice_date`（或由其派生的发货日），**有 billing**。
- 二者的分野不是"有没有票"，而是「**基数取自承诺还是取自结算**」；票只是结算层最常见的那张带价单据。

---

### 23.16 场景推演：订单 100 件 / 1000 元，发货 60 件、未开票、按出库日分期收款

#### 23.16.1 三个判断，两个成立、一个不成立

| 你的判断 | 结论 |
|---|---|
| 金额基数应该是 **600** | **成立**，但它是「按订单价**推算**的发货金额」，不是结算金额；必须定分摊规则 |
| 这 600 再分两个阶段（里程碑）付 | **成立**，且这两期很可能分属**两个不同的起算层**（② 履约 + ③ 结算） |
| 「这都算预付款」 | **不成立**。判据是**控制权转移时点**，不是收款时点；按你描述的"签收之后付"，控制权已转移 ⇒ 属**应收**，不是预收 |

#### 23.16.2 600 从哪来：推算金额 ≠ 结算金额

| 算法 | 结果 | 前提 / 风险 |
|---|---|---|
| 数量比例：60/100 × 1000 | 600 | 要求订单内单价一致；有阶梯价 / 行级折扣 / 运费 / 税差时**偏差** |
| 金额比例：Σ(60 件所属订单行金额) | 更准 | 按**订单行**分摊，不按整单分摊；跨行折扣需先摊到行 |
| 单价直算：60 × 单价 | 等价 | 同上，需处理行折扣与含税口径 |

**建议**：以**订单行**为单位按 `qty` 比例分摊该行 `gross_amount`，再按行汇总；尾差落在最后一期。**最终以发票金额为准回补差额**（见 23.16.5）。

#### 23.16.3 为什么"不是预付款"：看控制权，不看收款时点

| 收款时点 | 控制权是否转移 | 会计性质 | 我方是否有载体 |
|---|---|---|---|
| 下单后、发货前 | 未转移 | **预收**（合同负债 / 预收账款） | 无（订单不是会计事实） |
| 已发货、签收前（在途） | 未转移（发出商品） | **预收**（若此时已收） | 无 |
| **签收后、开票前** | **已转移** | **应收（已履约未结算）** ← **你的场景** | **无（缺口，见 23.16.5）** |
| 开票后 | 已转移 | 应收（已结算） | 有（`customer_invoice` 过账） |

> 所以"发货 60 件后按出库日分期收款"在业务上是「**货到/签收付款**」，不是预收款。把它记成预收会挂错科目（该确认收入的做成合同负债）。
> 附加提醒：先收款未开票还牵动**增值税纳税义务发生时间**（收款或合同约定收款日，先到者），属税务域，不在本 spec 展开。

#### 23.16.4 600 分两期 → 正好验证 `basis_point` 逐行独立

| 期次 | 金额 | 起算层 | `basis_point` | 触发 |
|---|---|---|---|---|
| 第 1 期（签收款 20%） | 600 × 20% = **120** | ② 履约事实 | `delivery_date`（更精确是签收日，我方暂缺） | 签收 |
| 第 2 期（尾款 80%） | 600 × 80% = **480** | ③ 结算事实 | `invoice_date` | 开票 |

一个计划组内两期用不同起算口径 —— **这就是 §23.7.2 把 `basis_point` 放在行上、而不是放在头上的理由**，也是 §23.14.1「模板层做不到、实例层做得到」的实例。

#### 23.16.5 真实缺口：签收后、开票前的收款，我方没有应收载体

- 我方 L2 会计事件**只从 `customer_invoice` 过账产生**；发货 / 签收不产生任何会计事件（g15 边界）。
- 因此"签收后收的 120"在当前模型里**既不能挂预收（性质错），也没有应收科目可挂**。
- 行业对照：
  - SAP 用 **提前开票 / 形式发票（pro forma invoice）** 让这笔钱有单据落脚；
  - Oracle 不允许"未开票直接建应收"，实务上仍是**先开票**再按账期收。
- **建议**：Wave A 明确"**先开票、后收款**"，避免无载体；若要支持"签收即收"，须先补「待开票 / 暂估应收」中间态，属 Wave B 或更后，且要同步定义它与发票的冲抵规则（对齐 §23.15.3 第 3 条）。

#### 23.16.6 一句话

**600 是对的（推算值），分两期也是对的（且跨两个起算层），但它不是预付款** —— 它是「已履约、未结算」的应收。真正的预付款只有一种：**钱在履约之前到**。

---

### 23.17 从 600 场景收回设计：四处补口与取舍

> §23.16 是业务推演，本节把它落成字段级 / 波次级的可执行条目。原则：**不为这个场景新增对象**，只补字段与口径。

#### 23.17.1 缺口清单

| # | 缺口 | 现状实证 | 处理 | 波次 |
|---|---|---|---|---|
| 1 | 计划头只有 `total_amount`（Σ 行 `plan_amount`），**没有基数金额** | §23.7.1 头字段表；§23.14.4 已标 | 补 `base_amount`（`number(18,4)`，只读快照）。实例化时从来源单据取；`plan_amount = percentage × base_amount`。手工改 `plan_amount` **不回写** `base_amount`，差额即"手工调整"，可追溯 | Wave A（表结构一次到位，避免二次迁移） |
| 2 | 没有"签收日"，只有到货日 | `shipment.yaml` L340 `planned_ship_date` / L355 `actual_ship_date` / L370 `actual_arrival_date`；无 `pod_date` | 口径取舍见 23.17.2 | Wave A 用 `actual_arrival_date`；Wave B 视需要补 `pod_date` |
| 3 | 签收后、开票前的收款无应收载体 | g15：L2 会计事件**只从 `customer_invoice` 过账产生** | Wave A 明确"先开票、后收款"；暂估应收属 Wave B | 边界声明 |
| 4 | `basis_point` 枚举无"签收" | §23.7.2：`order_date` / `delivery_date` / `invoice_date` / `month_end` | **不加**，理由见 23.17.3 | 无需变更 |

#### 23.17.2 "签收日"的三条路与选择

| 方案 | 成本 | 准确性 | 问题 |
|---|---|---|---|
| 用 `actual_arrival_date`（到货日） | 零（字段已有） | 近似 | "到货" ≠ "签收确认"；争议时无客户签收凭证 |
| `actual_ship_date` + 固定在途天数 | 零 | 推算 | 不是事实，与 §23.13「起算点优先取事实」相悖 |
| 新增 `pod_date`（proof of delivery） | 需先有"签收确认"动作与单据流 | 最准 | doc-flow G3（出库过账）本身仍是缺口，不能在本波同时补两层 |

**选择**：Wave A 用 `actual_arrival_date`，并在 `delivery_date` 的取值定义里写清「**优先取客户签收日，无签收日取到货日**」——这样字段先不扩，未来补 `pod_date` 时只是填充优先级更高的一档，不改口径语义。

#### 23.17.3 为什么不给 `basis_point` 加 `receipt_date`

- `delivery_date` 已代表 **② 履约事实** 这一层；签收是这一层内的**精度**问题，不是新的一层（§23.13 四层语义里，② 已包含 发货 / 出库 / 出库单签字 / 到货 / 收货）。
- 加枚举的成本是双侧的：`payment_term.basis_date_rule`（模板层）与 `payment_schedule_line.basis_point`（实例层）必须同步扩，且**历史实例的快照语义要重新解释**（已实例化的行快照的是旧枚举含义）。
- 判定标准：**只有当同一层内两个口径会给出不同到期日结果时才加枚举**。签收日与到货日通常同日或相差 1–3 天，属精度容忍范围。
- 反之，`month_end` 能留下来，是因为它跨越了"按事实"与"按日历"两类语义，会给出结构性不同的到期日。

#### 23.17.4 600 场景逐层落地对照

| 层 | 承载对象 | 本例落值 |
|---|---|---|
| ① 承诺 | `sales_order` / `sales_order_line` | 100 件 / `gross_amount` 1000 |
| ② 履约 | `shipment` / `shipment_line` | 60 件；**无价无金额**（`shipment_line` 无 amount/price 字段，已核实） |
| 推算 | **服务层计算，不落库** | 600 = Σ(60 × 行单价) 或按行 `qty` 比例分摊后汇总；尾差落末期 |
| ③ 计划 | `payment_schedule` + `payment_schedule_line` | 头：`base_amount=600`、`total_amount=600`；行 1：`percentage=20` → 120、`basis_point=delivery_date`；行 2：`percentage=80` → 480、`basis_point=invoice_date` |
| ④ 结算 | `customer_invoice` | 待开票（Wave A 要求先开票）；开票后以票额回补 600 与实际差额 |
| ⑤ 会计 | L2 会计事件 | 由 `customer_invoice` 过账产生；**120 在 Wave A 里等发票，不提前挂账** |

#### 23.17.5 一句话

方案不需要为此新增"预付款对象"或"发货结算对象"；需要的是三处填平 —— **计划头补基数金额、签收日定口径、暂估应收划入 Wave B**。

---

### 23.18 金蝶专题：预收款不是"提前的到期日"，而是"流程闸门"

> 本节为补充取证，来源为金蝶云产品手册（收款条件 / 收款计划及预收 / 销售订单）、金蝶云社区与星空知识库，见 23.18.9 引用清单。
> 结论先行：金蝶把「预收款」与「账期」做成了**两套机制**——预收靠"控制环节"卡流程，账期靠"到期日"算日期。这比"用起算时点区分预付与后付"更彻底，也直接印证 §23.13.5 的判断。

#### 23.18.1 三个对象，各管一段

| 对象 | 层级 | 管什么 |
|---|---|---|
| 收款条件（模板） | 主数据 | 预收比例、到期日计算日期、收款方式、到期日确认方式、控制环节 |
| 收款计划（页签） | 单据表头子页签 | 每行的 `是否预收` / `应收比例` / `应收金额` / `到期日` / `实收金额` / `控制环节` |
| 收款单 / 预收款单 | 事实单据 | 实际到账；预收类型收款单可与订单关联 |

- 系统预设 4 种收款条件：货到收款、30 天后收款、月结 30 天、多到期日（按金额）。
- **收款计划挂在单据表头，行级没有独立的起算口径字段** —— 起算口径是头的单值。

#### 23.18.2 起算时点：三个预设值，头级单值

> 原文：「到期日计算日期系统预设为**订单日期、出库日期和应收单业务日期**。用户可以根据企业的实际业务增加单据上的其它日期为到期日计算日期。」

| 金蝶取值 | 对应 §23.13 四层 | 说明 |
|---|---|---|
| 订单日期 | ① 业务承诺 | 下单即起算 |
| 出库日期 | ② 履约事实 | 中国主流 |
| 应收单业务日期 | ③ 结算事实 | 等价于我方 `invoice_date`（应收单 = 应收载体） |
| （可增补）单据上的其它日期 | ②/③ | 按企业口径扩展 |

两点值得注意：

1. **没有"发票/开票日期"这个预置值**。因为金蝶的应收载体的「应收单」，发票只是票据（开票单）——这正是 §23.15.1「业务开票 vs 票据」的中国式体现。
2. **到期日计算日期是收款条件的属性，不是计划行的属性**。一个收款条件下的所有期次共用同一口径。

> 「当收款条件的到期日计算方式是"订单日期"，并且收款方式是"按到期日收款"时，销售订单收款计划的到期日才能手工维护，其他情况下为系统自动计算。」

⇒ 金蝶的把关很实在：**要么你选一个自动口径，要么你切到"订单日期"口径后全手工**。它不提供"第 1 行用订单日、第 2 行用发票日"这种逐行口径。

#### 23.18.3 收款方式三值 = 计划组粒度（对 §23.14 的行业印证）

> 原文：「收款方式包括：**按到期日收款、按订单收款、按物料明细收款**三种。」

| 金蝶收款方式 | 分组粒度 | 对应我方 |
|---|---|---|
| 按到期日收款 | 按期次一组；不记订单信息 | `source_line_id` 为空 + `source_doc_type=manual`（默认） |
| 按订单收款 | 整单一组；收款单记订单号，核销按「客户 + 订单号」 | `source_doc_type=sales_order`、`source_line_id` 为空 |
| 按物料明细收款 | 订单行一组；可显示物料、可显示订单号 | `source_doc_type=sales_order`、`source_line_id` 非空 |

差异不只在显示，还在**核销归属**：按到期日收款时「收款单上没有记录订单信息，所以不能按订单找到对应的收款信息，不能支持显示订单已收款金额、未收款金额」，核销按客户应收先后顺序；按订单/按物料明细收款则记订单号，可精确核销。

**这是 §23.14 的强证据**：起算口径的第二个作用「决定计划组粒度」不是我方推演出来的抽象概念，金蝶把它做成了显式枚举，并公开承认它影响核销归属。我方 `source_doc_type` + `source_line_id` 的组合已经覆盖这三档，不必新增字段，但**要在设计说明里写明它与金蝶三值的映射**，避免使用者误以为"按订单收款"是另一种到期日规则。

同时，金蝶在「按物料明细收款」下支持**按物料维度控制发货**（「收款条件是按物料明细收款时，暂不支持按收款计划控制发货」是旧限制，新版已放开为「按物料+项目维度统计应收/已收/累计发货金额，发货通知单或销售出库单提交时自动校验」），这属于 Wave C 的执行控制，不在 Wave A 范围。

#### 23.18.4 核心：预收款走的是「控制环节」，不是「到期日」

这是本节最重要的发现。金蝶销售订单表头收款计划页签的字段：

| 字段 | 规则（原文要点） |
|---|---|
| 是否预收 | 勾选指是预收，不勾选指不是预收 |
| 应收比例（%） | 根据收款条件自动带出，或手工维护 |
| 应收金额 | `应收金额 = 价税合计 × 应收比例`；输入金额可反算比例；应收金额合计 = 价税合计时，最后一行比例 = 1 − 前面合计 |
| 实收金额 | 选收款单时默认取关联预收单的 Σ未关联金额，锁定 |
| **控制环节** | **仅当「是否预收」勾选时可维护；下拉 4 值：订购、发货、出库、生产；表示只有达到预收金额，业务单据才能通过审核** |

对照预售实践案例（芯片代工）：「投产阶段校验 30% 预付款到账，未达标无法生成生产工单；发货前校验剩余 40% 预付款才生成发货通知单」。

⇒ 金蝶的预收款语义是：**"钱到账才能推进到下一个环节"的闸门（gate）**，不是"某天到期该收多少"。

| 机制 | 回答的问题 | 金蝶承载字段 |
|---|---|---|
| 到期日 | 这笔钱**什么日期**该收 | `到期日`（由收款条件算出） |
| 控制环节 | 这笔钱**没到账时，业务能走到哪里** | `控制环节`（订购/发货/出库/生产） |

**这解答了你之前的两个追问**：

- 「预付款按订单日、尾款按发票日，为什么模板层表达不了？」—— 金蝶的回答是：**预付款根本不需要一个起算日期**。它需要的是一个"到账门槛"；它的"日期"就是下单那天（因为下单即要求付款）。而尾款才需要起算日期。两件事用两个机制，自然不需要同一张表里放两个起算口径。
- 「预付款的金额基数是基于订单吗？」—— 金蝶明确：`应收金额 = 价税合计 × 应收比例`，`价税合计` 即订单含税总额。**预收基数 = 订单含税总额**，与 §23.15.2 我方 `gross_amount` 完全一致。

#### 23.18.5 暂估应收：我方 §23.16.5 缺口的现成答案

> 落地路径：【财务云】-【应收】-【往来处理】-【应收处理】-【暂估应收处理】

金蝶的流程（原文要点）：

1. **销售出库完成、当月不开票** ⇒ 月末由**销售出库单下推生成暂估应收单**（业务应收）；
2. 下月开票时两条路径：
   - 一次性开票：暂估应收单 → 开票单；
   - 需部分开票/控开票额度：暂估应收单 → 财务应收单 → 开票单。
3. 立账模式二选一：**业务应收**（由业务应收单生成"应收账款"凭证）/ **暂估应收**（由财务应收单生成凭证）。
4. 配套报表：应收未开票明细表、已出库未应收明细表。
5. 会计处理有两种实务：对暂估应收单**生成凭证、下月初冲回**；或**不生成凭证**，只进应收报表用于对账。

⇒ 这正好落在我方 §23.16.5 的空档上：**「签收后、开票前」的应收需要一个"暂估应收"载体**，来源是发货/出库单、金额按订单价推算（即 §23.16.2 的 600），下游被发票冲抵。

**与 SAP 对照**：SAP 用提前开票/形式发票（pro forma）让这笔钱有单据；金蝶用暂估应收单（业务应收）。两者都承认"未开票也可以有应收"，区别是金蝶把它做成了**独立单据 + 双重立账模式**，比形式发票更轻。

**对我方的建议调整**：原 §23.16.5 写"Wave B 或更后"，现在可以收窄为 —— **Wave B 建 `provisional_receivable`（暂估应收）**，`source_doc_type=shipment`、`source_line_id=shipment_line.id`、金额按订单行价推算、无税票；下游 `customer_invoice` 过账时按 `(order_line_id, qty)` 冲抵。这比"只声明先开票后收款"更能覆盖中国实务（月底出库、次月开票是常态）。

#### 23.18.6 对我方对象模型的三条修正

| # | 现状 | 金蝶证据 | 建议 |
|---|---|---|---|
| 1 | `payment_schedule_line.is_prepayment` 只是布尔标记，无下游动作 | 「控制环节」：订购/发货/出库/生产，达不到预收金额则单据不能审核 | 补 `control_stage`（`none` / `order_confirm` / `ship` / `issue` / `produce`），仅在 `is_prepayment=true` 时可填；由业务单据提交时校验。**否则 `is_prepayment` 只是一句备注，没有执行力** |
| 2 | 计划头只有 `total_amount`，缺基数 | `应收金额 = 价税合计 × 应收比例` | 维持 §23.17.1 的 `base_amount` 补充，语义与金蝶"价税合计"对齐 |
| 3 | 签收后开票前无应收载体 | 暂估应收单（业务应收/暂估应收双模式） | Wave B 建 `provisional_receivable`，来源 `shipment_line` |

#### 23.18.7 金蝶 vs Oracle：两种"起算"哲学

| 维度 | Oracle AR | 金蝶云·星空 |
|---|---|---|
| 起算基准 | 发票 `TRX_DATE`（可达 100% 归一到票） | 订单日 / 出库日 / 应收单业务日期（三选一） |
| 起算粒度 | 每张发票一组（`AR_PAYMENT_SCHEDULES_ALL` 按发票生成 installment） | 到期日 / 订单 / 物料明细（显式三档） |
| 预付款 | **独立事务类型**，先收款后核销，不走 Payment Terms | **收款计划里的一行** + 控制环节闸门 |
| 未开票应收 | 不允许，必须开票 | **暂估应收单**（业务应收/暂估应收） |

一句话差异：**Oracle 把"票"作为一切起算的原点；金蝶把"流程推进"作为预收的判据、把"出库/应收单"作为账期的原点**。我方作为中国业务平台，`basis_point` 取值集合（`order_date` / `delivery_date` / `invoice_date` / `month_end`）与金蝶三预设 + 月结实质重合，**说明取值集合已经对齐本土主流**；差异只剩下"行级独立"这一点，而这是我方更灵活的地方，应保留。

#### 23.18.8 一句话

金蝶的答案是：**预收看闸门（控制环节：订购/发货/出库/生产），后收看日历（起算日：订单/出库/应收单）；未开票但有货权的应收，用暂估应收单兜住**。三段各用各的机制，比我方原设计"用一个 `is_prepayment` 布尔区分"更完整。

#### 23.18.9 引用清单

- 金蝶云产品手册《收款条件》：`help.open.kingdee.com/dokuwiki/doku.php?id=收款条件`
- 金蝶云产品手册《收款计划及预收》：`help.open.kingdee.com/dokuwiki/doku.php?id=收款计划及预收`
- 金蝶云产品手册《销售订单》（表头收款计划页签：是否预收 / 应收比例 / 应收金额 / 实收金额 / 控制环节）
- 金蝶云产品手册《应收单》：`help.open.kingdee.com/dokuwiki_std/doku.php?id=应收单`
- 金蝶云产品手册《应收款管理》（立账模式：业务应收 / 暂估应收）
- 金蝶云社区《应收业务介绍——暂估应收下推开票流程介绍》（2025-09-06）
- 金蝶云社区《销售订单收款条件按"订单收款"或"按物料明细收款"支持显示订单已收款/未收款金额》
- 金蝶云社区《收付款计划支持按物料明细管控，实现全链路精准追溯》

---

### 23.19 用友专题：行级起算时点 + 签收暂估应收

> 取证口径：NC 的「收款协议」取自用友 NC 手册镜像（字段级逐条原文）；U8C / YonBIP 的「起算日」「按协议行收款」「签收暂估应收 SO091」取自 yonyoucloud 官方帮助页（控制逻辑级原文）；畅捷通分期收款计划作为同族旁证。凡"手册未写、由相邻字段推断"的地方均显式标注 `[推断]`。

#### 23.19.1 三个对象各管一段（与金蝶同构，粒度不同）

| 对象 | 管什么 | 粒度 |
|---|---|---|
| 收款时点档案（收款时点-集团 / 起算时点档案） | 定义"哪一天算起算日"的**可选值清单** | 全局档案，供引用 |
| 收款协议（NC 集团/业务单元；U8C 按客户/按协议） | 期数、比例、**每期自己的起算时点**、延迟、账期/固定结账日、结算方式、质保金、现金折扣 | **一行一期**，行级独立 |
| 收款计划（销售订单 / 应收单上的执行明细） | 按协议行展开出的到期日与金额，供收款、账龄、信用使用 | 单行一条 |

三家（SAP / 金蝶 / 用友）都是"模板 → 展开 → 执行"三段，差别只在**展开时起算时点挂在头还是挂在行**。

#### 23.19.2 NC 收款协议字段表（手册原文口径）

| 字段 | 手册原文要点 | 对我方的意义 |
|---|---|---|
| 分期收款的期数 | 共分 3 期则三行分别维护 1/2/3 | 与我方 `payment_term_line.seq` 同构 |
| 收款比例 | 本收款期内要收到总应收款的比例，**各期比率之和必须等于 100** | 与我方 G1（Σ = 100，写时只拦 >100）一致 |
| **预收款** | **确认"本收款期"是否是预收款**；销售订单业务**根据此标志进行预收款控制** | 判据是"期"，不是"协议" ⇒ `is_prepayment` 放在**行**上正确 |
| **起效日期** | 参照【收款时点-集团】档案预置的 6 个值，即**本期的起算时点** | **行级独立起算**，见 §23.19.3 |
| 起效日期延迟天数 | 在起效日期后延期推后的天数 | 我方分解为 `offset_months` + `offset_days`，语义可覆盖 |
| 账期天数 | 允许延迟结算的天数，超期成为账期外应收；系统据此算账龄与信用到期日 | 我方 `offset_days` 的等价物 |
| **固定结账日 / 生效月 / 附加月** | 三者是一组信息；**每一期只能"账期天数"与"固定结账日"二选一** | 我方用 `fixed_day_of_month` + `offset_months` 表达，同样互斥 |
| 结算方式 | 本期用什么方式收（转账/票据等） | 我方线条级尚无，见 §23.19.8 第 4 条 |
| 质保金 | 只有一行可设该属性，允许全为非质保金行 | 我方用 `line_type` 可承载（如 `retention`） |
| 现金折扣 | 与账期并行 | 我方 `discount_percent` / `discount_days` 已覆盖 |

#### 23.19.3 与金蝶最大的差异：起效日期在**行**上，不是头级单值

| 维度 | 金蝶云·星空 | 用友 NC |
|---|---|---|
| 起算时点挂在哪 | 收款条件（模板）**头级单值**，一个条件里所有期次共用 | 收款协议**每一行各自一个起效日期** |
| 结果 | 「预付按订单日、尾款按发票日」在**一个模板**里表达不了，只能拆成两张收款条件 | **一个协议内逐期不同起算点**，原生支持 |

这正是用户最早质疑的那句「模板层表达不了预付款按订单日、尾款按发票日」的**行业正解**：金蝶的答案是"拆模板"，用友的答案是"把起算点下沉到行"。

⇒ **我方 `payment_schedule_line.basis_point`（行级独立）有直接行业先例，不是我方自创的灵活性。**

#### 23.19.4 收款时点档案：6 个预置值（含开票与发票审核）

| 预置值 | 归层（§23.13） | 我方 `basis_point` 是否有 |
|---|---|---|
| 出库日期 | ② 履约事实 | 有（`delivery_date`） |
| 出库单签字日期 | ② 履约事实 | 无（更细的签收口径，见 §23.17.2） |
| **销售开票日期** | ③ 结算事实 | 有（`invoice_date`） |
| **销售发票审核日期** | ③ 结算事实 | **无** |
| 销售订单日期 | ① 业务承诺 | 有（`order_date`） |
| **销售合同生效日期** | ① 业务承诺 | **无** |

**与金蝶的对照**：金蝶三预设（订单日 / 出库日 / 应收单业务日期）**没有开票日期**，因为其应收载体是应收单、发票只是票据；用友**有开票日期与发票审核日期**，因为 NC 的应收载体包含销售发票本身。⇒ 「有没有开票起算点」取决于**把发票当不当应收载体**，不取决于国别。

**对我方**：`basis_point` 现有 4 值（`order_date` / `delivery_date` / `invoice_date` / `month_end`）覆盖了两家预设的公共交集，**Wave A 不需要扩枚举**。
- `invoice_review_date` **不加**：我方 `customer_invoice` 只有 `invoice_date`，没有"审核"这一独立动作，加了就是空枚举值。
- `contract_effective_date` **暂缓**：Wave A 订单即承诺载体，无独立合同对象；待合同对象立项时再议（记入 §23.19.8 第 5 条）。

#### 23.19.5 到期日双算法（NC 原文，两种情况互斥）

```
无固定结账日：到期日 = 起效日期 + 起效日期延迟天数 + 账期天数
有固定结账日：到期日 = 起效日期 + 延迟天数，再落 固定结账日 + 生效月 + 附加月
U8C / YonBIP：出账日 = 起算日 + 延迟天数 + 延迟月数（未设固定日时）
```

手册给出的对照例：固定结账日 10 号、生效月"当月/下月"、附加月 0/1 ⇒ 1 月 5 日与 1 月 25 日两笔业务的到期日落在不同月份，差异完全由"生效月 + 附加月"决定。

**与 `payment_term_line` 计算口径的对照**（§文件头写死的四步）：

| 步骤 | 用友 | 我方 |
|---|---|---|
| 基准日 | 起效日期（行级） | 头 `basis_date_rule`（头级）+ 行 `basis_point`（实例层覆盖） |
| 顺延 | 起效日期延迟天数 | `cutoff_day` 顺延 + `offset_days` |
| 月偏移 | 生效月（当月/下月）+ 附加月 | `offset_months` |
| 固定日 | 固定结账日 | `fixed_day_of_month` |

⇒ 两者的**能力集合等价**，用友用"生效月/附加月"两个枚举+整数表达，我方用 `offset_months` 一个整数表达，表达力更强（可 0..60），**不需要改我方算法**。

#### 23.19.6 签收暂估应收（SO091）：以"签收"为触发点

U8C / YonBIP 新架构原文要点：

1. 销售订单**预置交易类型**：编码 **SO091**，名称「签收结转成本 / 签收暂估应收」，并带**对应业务流**；
2. **支持签收确认进行暂估应收和发出商品成本结转**；
3. 业务流设计中，销售出库配置**保存动作前规则**「签收暂估应收」，规则名为 `出库立账方式_签收暂估`；
4. 配套：`出库立账方式` 可切换，即"出库即立账"与"签收才立账"是**同一位置的两个选项**。

**与金蝶暂估应收的对照**：

| 维度 | 金蝶云·星空 | 用友 U8C / YonBIP |
|---|---|---|
| 触发点 | 月末未开票的销售出库单 → 下推暂估应收单 | **签收确认**（也可切到出库） |
| 载体 | 独立单据（业务应收 / 暂估应收双立账模式） | 交易类型 SO091 + 业务流 + 立账方式规则 |
| 后续 | 暂估应收单 → 开票单 / → 财务应收单 → 开票单 | 签收暂估 → 发票 → 冲回 |

⇒ **用户 600 场景的"签收后、开票前"应收，用友给的答案是明确的：把它做成一种"立账方式"，而不是让业务手工补单。**

**对我方 §23.18.6 第 3 条的收窄**：Wave B 的 `provisional_receivable` 应补一个 `accrual_trigger` 枚举（`ship` / `receipt`），默认 `ship`（对齐金蝶与中国"月末出库未开票"高频场景），可配 `receipt`（对齐用友 SO091）。**不做**成两套对象——两家都只是同一对象的不同触发点。

#### 23.19.7 四家横向对照

| 维度 | Oracle AR | 金蝶云·星空 | 用友 NC | 用友 U8C / YonBIP |
|---|---|---|---|---|
| 起算基准 | 发票 `TRX_DATE` | 订单日 / 出库日 / 应收单业务日期（**无开票日**） | 6 值含**开票日 + 发票审核日 + 合同生效日** | 起算日档案 + **可自定义起算时间**（含**签收单据日期/审核日期**） |
| 起算粒度 | 每张发票一组 | 模板**头级单值** | 协议**行级独立** | 协议行 + 应收单**可手工改起算日** |
| 预收机制 | 独立事务类型（先收款后核销） | 收款计划一行 + **控制环节**闸门（订购/发货/出库/生产） | 协议行「预收款」标志 + **销售订单预收款控制** | 同 NC（收款协议行 + 预收款标志） |
| 未开票应收 | 不允许，必须开票 | 暂估应收单（月末出库下推） | 走发票/应收单 | **签收暂估应收 SO091**（签收或出库立账） |
| 到期清单 | 无独立对象，批处理 | 收款计划页签 | 收款计划跟踪 + 账龄/信用 | 收款执行明细 + 出账日/到期日 |

一句话：**Oracle 归一到票；金蝶归一到"模板 + 闸门"；用友归一到"行 + 立账方式"。用友在"起算点行级独立"和"签收即立账"两件事上，比我方原设计更靠前。**

#### 23.19.8 对我方的五条修正

| # | 现状 | 用友证据 | 结论 |
|---|---|---|---|
| 1 | `payment_schedule_line.basis_point` 行级独立，曾担心"过度设计" | NC 协议**每行一个起效日期** | **保留，且升级为卖点**：行级起算有行业先例，不是自创 |
| 2 | `is_prepayment` 无执行力（§23.18.6 已提 `control_stage`） | NC「本收款期是否预收款」+ 销售订单预收款控制 | `control_stage` 建议**保留枚举但 Wave A 只实现 `none` / `order_confirm` 两值**，与金蝶 4 值、用友布尔闸门三者兼容；不实现完整 4 值不算缺口 |
| 3 | `provisional_receivable` 计划 Wave B 建，粒度未定 | 金蝶=月末出库下推；用友=签收立账（可切出库） | 补 `accrual_trigger`（`ship` / `receipt`），**一个对象两种触发**，不建两套 |
| 4 | 计划行无"结算方式" | NC 协议行有结算方式 | **不加**。结算方式是收款执行侧属性（收款单/付款单），不应污染计划；金蝶亦未放在收款条件上 |
| 5 | 无"合同生效日"起算 | NC 预置"销售合同生效日期"；YonBIP 支持自定义起算时间 | **Wave A 不加**（无独立合同对象）。Wave B 接合同对象时，`basis_point` 扩 `contract_effective_date` 一个值即可，不改表结构 |

金额基数再获第三次印证：畅捷通分期收款计划「各阶段之和 = 销售订单**整单含税金额**」「先填比例则 `计划收款金额 = 整单含税金额 × 应收比例`」。⇒ §23.17.1 的 `base_amount` 语义 = 订单 `gross_amount`，与金蝶"价税合计"、用友"整单含税金额"**三家口径完全一致**。

#### 23.19.9 一句话

**用友的答案是"把起算点下沉到每一期、把有没有货权下沉到立账方式"**：起算行级独立解决了"预付按订单日、尾款按开票日"；「预收款标志 + 销售订单预收款控制」解决了预收的执行力；「签收暂估应收 SO091」解决了签收后开票前的应收载体。三条都落在我方已有的字段/波次上，**不需要新增对象，只需要两处枚举补值（`accrual_trigger`、Wave B 的 `contract_effective_date`）**。

#### 23.19.10 引用清单

- 用友 NC《收款协议》手册（分期收款协议字段与到期日算式原文，含期数/比例/预收款/起效日期/延迟天数/账期天数/固定结账日/生效月/附加月/结算方式/质保金/现金折扣）
- 用友 U8C / YonBIP《收款协议》：起算时点参照收款起算时点档案，`出账日 = 起算日 + 延迟天数 + 延迟月数`
- 用友 YonBIP《应收单》：「起算日」定义与可手工修改的控制逻辑
- 用友 YonBIP《销售订单》：「按协议行收款」支持导入协议行、自定义起算时间、以签收确认单据日期/审核日期为起算时点、按订单收款情况变更协议行
- 用友 YonBIP《销售订单交易类型》：预置 SO091「签收结转成本 / 签收暂估应收」+ 业务流 + 出库保存前规则 `出库立账方式_签收暂估`
- 畅捷通《分期收款计划》：计划收款金额必填、各阶段之和 = 订单整单含税金额、按应收比例反算
- 用友 U8《期初发货单》与存货核算「期初分期收款发出商品」取数口径

#### 23.19.11 二次核验：「每次出库自动复制一套期次」不成立，且有三条反向证据

用户要求复核"用友 BIP / NC 是否会自动按出库批次复制收款期次"。复核结论：**没有正向证据，并新增三条反向证据。**

| # | 证据原文 | 出处 | 证明了什么 |
|---|---|---|---|
| 1 | 应收单「期号」：取数逻辑为**上游单据携带、不可修改**；控制逻辑为**有来源且上游有付款协议的，自动携带付款协议行的期号，不可修改** | YonBIP 应收单字段说明 | 期次结构由**上游（合同/订单）一次性确定**，应收单只继承，不复制 |
| 2 | 销售合同「收款协议」子表：选档案后自动带出协议明细行，可改**各期比例、起算时点、账期、账期单位、账期类型、起算延迟月、起算延迟日**；可增行 | U8C 销售合同帮助 | 期次的增删改发生在**合同层**，不是出库时 |
| 3 | 收款协议档案「分期收款」：支持灵活设置**期数、各期比例或金额、各期的收款出账日依据和收款到期日计算依据** | U8C 收款协议档案帮助 | 起算点是**档案行级**属性（第三次确认）；亦修正 §23.19.3 的对比强度 |

**分界结论：**

- [OK] 可证：起算点可以是出库日期、出库单签字日期、签收确认单据日期/审核日期，且**逐期可配**。
- [X] 不可证：不存在任何"出库单保存 → 自动生成或复制 N 期收款计划"的描述；证据方向相反。
- [WARNING] 文档空白：当起算点 = 出库日期且分批出库时，到期日取**首次 / 末次 / 逐次**出库日，公开文档均未写明。这正是我方可以自定规则的地方，但也意味着不能对外声称"行业标准做法"。

**顺带发现的两处能力差距（低优先，记入待补项）：**

| # | 用友能力 | 我方现状 | 建议 |
|---|---|---|---|
| 1 | 固定日支持 **1 至 4 个**："设置固定日后，在 1~4 个固定日中向后取最近的固定日期" | `payment_term_line.fixed_day_of_month` 为单值 | Wave A 不改；若出现"每月 5 日 / 15 日 / 25 日三档付款日"客户，再扩为多值 |
| 2 | 账期天数可选"信用期限"，**取客户档案信用天数** | `offset_days` 只能填死数字 | 不引入。这是信用主数据耦合，Wave C 接信用模块时再议 |

**对 §23.19.9 一句话的修正**：用友解决的是"起算点逐期可配 + 签收即立账"，**不是**"按出库批次自动复制期次"。因此"每批两个阶段"的组模型（§23.7 方案甲/乙）**仍须我方自建**，行业方案只提供了起算点这一半。

---

### 23.20 金蝶产品线二次核验：星瀚（Cosmic）vs 星空（Galaxy）

用户追问"我说的是经典的星瀚或者星空"——§23.18 只写了"金蝶云·星空"，未区分产品线。本节做二次确认：**两条产品线的收款条件机制不同源，且星瀚（大型企业线）比星空（中型企业线）更接近我方的组模型。**

#### 23.20.1 两条线不是同一个产品

| 维度 | 金蝶云·星空（Galaxy） | 金蝶云·星瀚（Cosmic） |
|---|---|---|
| 客群 | 高成长型 / 中型企业 | 大型、跨国集团 |
| 技术底座 | 企业版为传统架构 + .NET；旗舰版起上苍穹 PaaS | 苍穹 PaaS + Java，云原生 |
| 手册域名 | `help.open.kingdee.com/dokuwiki`（产品手册） | `vip.kingdee.com` 知识库 + 星瀚专题 |
| 我方 §23.18 证据归属 | **全部来自这一条线** | 本节新增 |

⇒ 此前"金蝶"的结论只在星空上成立，不能直接外推到星瀚。

#### 23.20.2 收款条件字段对照（同一功能，两套设计）

| 星瀚字段 | 星瀚可选项 | 星空对应物 | 差异性质 |
|---|---|---|---|
| 收款设置依据 | **按比率（%）/ 按金额** | 只有比例（`预收比例`） | **能力差**：星瀚支持"某期固定收 X 元" |
| 到期日计算日期 | 销售订单日期 / **销售收货日期** / **销售入库日期** / 应付单日期 | 订单日期 / **出库日期** / 应收单业务日期 | 基准日集合不同：星瀚有收货、无出库；星空有出库、无收货 |
| 条件使用范围 | 销售订单 / 财务应付单 | 未设（应收侧独立配置） | 星瀚一个条件同时服务应收应付 |
| 款项名称 | 到货收款 / 接收收款 / 验收收款 | 无独立款项分类 | 星瀚把"款项性质"做成主数据 |
| 预付标志 | 是 / 否（**行级**） | 是否预收（头级预收比例 + 控制环节） | 星瀚行级；星空头级 + 闸门 |
| 到期日确定方式 | **交易日 / 某天后 / 月结** | 到期日确认方式 + 提前/延后天数 + 固定日 | 星瀚三档语义更显式 |
| 收款方式（计划粒度） | 无此字段，改由 **V8.0.15 收付款维度**承担 | 按到期日收款 / 按订单收款 / 按物料明细收款 | 演进路径不同 |
| 控制环节 | 有（履约控制微服务按"收款维度+控制环节+预收标识"分组校验） | 订购 / 发货 / 出库 / 生产 | 都有，星瀚多了维度参数 |

星瀚"月结"算法的原文规则（用于和我方四步对齐）：

- 账单结算日：1–31，填 **31 = 取到期月月末**
- 若 `到期日计算日期 + 天数 > 账单结算日` ⇒ 到期日 = **1 + 月数** 个月后的账单结算日
- 若 `到期日计算日期 + 天数 ≤ 账单结算日` ⇒ 到期日 = **月数** 个月后的账单结算日
- 特别说明：星瀚"某天后"的**月数固定按 30 天折算**（非自然月）

#### 23.20.3 星瀚 V8.0.15「收付款维度」= 我方组模型的行业实证

星瀚 V8.0.15 及以上版本新增"收付款维度"（基础服务云：收付款维度成员 / 收付款维度），机制原文：

1. 选了绑定付款维度的付款条件后，触发"拆分收付款计划"微服务，**按维度对物料明细分组汇总，并逐行计算计划金额**
2. 预置三种维度组合：按物料明细 / 按物料 / 按项目；可自定义（WBS、成本中心等）
3. 原文示例：付款条件"预付 20% + 货款 80%"，维度 = 物料编码 + 项目编号；物料A（项目1，100 万）、物料B（项目2，80 万）⇒ 自动生成 **4 条**计划：A-项目1 预付 20 万、A-项目1 货款 80 万、B-项目2 预付 16 万、B-项目2 货款 64 万
4. "比例加总、金额加总均通过合法性校验，**确保与合同总金额完全一致**"
5. 财务应收单按收款维度**分单生成**；维度成员值从上游携带、不可修改
6. 结算分摊按维度行应收金额比例分摊，**尾差统一归集至最后一行**
7. 限制：由"开票申请单下推财务应收单"的流程**不能启用**该特性（未与发票云打通，维度会丢失）

**这与 §23.7 的「组 / 期」两层完全同构**：

| 星瀚概念 | 作用 | 我方对应 |
|---|---|---|
| 维度成员组合（物料+项目） | 决定分成几组 | 组（`source_doc_type` + `source_doc_id` / `group_no`） |
| 付款条件的期次行 | 决定每组怎么切 | 期（`percentage` + `basis_point` + `offset_*`） |
| 组内金额 = 组基数 × 期比例 | 计算 | `group_base_amount` × `percentage` |
| 加总校验 = 合同总额 | 防重复收款 | 待补不变量：各组 `base_amount` 之和 ≤ 订单 `gross_amount` 且互斥 |
| 尾差归最后一行 | 四舍五入 | 尾差落该组最后一期 |

⇒ 结论修正：**"组/期"两层不是我方发明**，星瀚已经商品化；我方 §23.7 方案甲（头 1:1 + 行上 `group_no`）在数据上等价于"组 = 维度成员组合"。这让方案甲从"设计推断"升级为"有行业先例"。

#### 23.20.4 对 §23.18 / §23.19 结论的影响（三条）

| # | 影响 | 处理 |
|---|---|---|
| 1 | §23.18 的"头级单值"只在**星空**成立；星瀚是**行级**（每款项一行，各自带比率/预付标志/到期日确定方式） | §23.18 保留但加限定：其结论适用星空；星瀚与我方 `payment_schedule_line` 的行级设计同构 |
| 2 | 星瀚证明"**按金额** 收款"是一等公民（质保金、固定尾款场景） | 记入待补项：`payment_term_line.percentage` 应扩为 `settle_basis`（`percent` / `amount`），二选一，`amount` 时不参与 100% 校验 |
| 3 | 星瀚把"**收货日 / 入库日**"列为到期日基准，星空只有出库日 | `basis_point` 枚举 Wave A 不扩；Wave B 若接签收/收货确认，补 `receipt_date`（与 §23.19.6 的 `accrual_trigger=receipt` 同一节点） |

同时**再次证伪**"出库自动复制期次"：星瀚在出库/发货环节做的是"**校验预收款是否达标**"（不达标拦截提交），以及在应收单生成时"**按维度分单**"，两者都不是"新增一期计划"。三处证据方向一致（用友期号不可改、星瀚维度分单、星空控制环节闸门）。

#### 23.20.5 一句话

金蝶两条线都没有"按出库批次自动复制期次"；但**星瀚的"收付款维度"已经把"一个订单拆成多组、每组按付款条件展开多期"做成了标准能力**——这正是我方 §23.7 要建的东西，差别只在星瀚的分组键是"物料/项目"，我方的分组键是"出库/发货批次"。

#### 23.20.6 引用清单

- 金蝶云·星瀚《基础资料-收款条件介绍》（收款设置依据 / 到期日计算日期四值 / 条件使用范围 / 款项名称 / 预付标志 / 到期日确定方式三档 + 月结算法原文）
- 金蝶云·星瀚《收付款计划支持按物料明细管控，实现全链路精准追溯》（V8.0.15+，收付款维度、拆分微服务、4 条计划示例、加总校验、尾差归最后一行、按维度分单、开票申请单下推不支持）
- 金蝶云·星空《收款条件》《收款计划及预收》《销售订单》（预收比例、到期日计算日期三值、收款方式三值、控制环节四值、预设四种收款条件）
- 金蝶国际 2024 年报（星瀚=大型企业 SaaS 管理云、星空=高成长型企业 SaaS 管理云的产品线定义）
- 金蝶云社区问答《星空跟星瀚具体有什么区别》（客群 + 技术架构差异）

---

### 24 跨产品线综合：三轴坐标、三条物理定律、三条分叉、一个我方增量

> 综合 §16（Oracle Fusion）、§18（SAP）、§19（其他头部 ERP）、§21（收款计划取证）、§22（Infor LN）、§23.18（金蝶星空）、§23.19（用友 NC/U8C/YonBIP）、§23.20（星瀚）。
> 本节只写"跨产品才能看清"的结论，不复述单产品细节。

#### 24.1 七家的真实坐标：三个正交轴

任何"收款计划"方案都可以被三个轴完全定位，产品差异全部落在这三轴上，而不在 UI 或字段命名上。

| 轴 | 取值 | 说明 |
|---|---|---|
| **A 锚定层** | 承诺层（订单/合同）/ 结算层（发票/应收单）/ 履约层（发货/出库/签收） | 决定"计划在什么时候出生" |
| **B 分组键** | 整单 / 订单行 / 物料 / 项目 / **批次事实** | 决定"分成几组" |
| **C 起算粒度** | 头级单值（全组共用一套） / 行级独立（每期各自一个基准日） | 决定"每组怎么切、从哪天算" |

各产品定位（A 档 = 已做字段级取证；B 档 = 只做机制级取证）：

| 产品 | A 锚定层 | B 分组键 | C 起算粒度 | 档 |
|---|---|---|---|---|
| Oracle Fusion AR | 结算层（AR 发票，无 billing 单据层） | 整单（trx 头） | 头级（Payment Terms 模板 + 行） | A |
| Oracle Fusion OM / Project | 承诺层（订单行 / 项目 Bill Plan） | 订单行 | 行级（每期覆盖） | A |
| SAP SD + FI-AR | 结算层（FI 发票为应收锚） | 整单 | 头级（T052 条件） | A |
| SAP Billing Plan（FPLT） | 承诺层（SO item） | 订单行 | 行级（每期 FKDAT，FKDAT = 开票日不是结算日） | A |
| 金蝶·星空 | 承诺层（订单表头收款计划页签）+ 结算层（应收单） | 整单，粒度由"收款方式"三值切换 | 头级 | A |
| 金蝶·星瀚 | 承诺层 + 结算层 | **维度成员组合**（物料/项目/WBS/成本中心） | 行级（每款项一行） | A |
| 用友 NC / U8C / YonBIP | 承诺层（合同收款协议）+ 结算层（应收单继承期号） | 整单 / 协议行 | **行级**（每行独立起效日期） | A |
| Infor LN | 承诺层（订单/合同分期付款计划） | 整单 / 行 | 行级 | A |
| D365 F&O / NetSuite / Odoo | 承诺层（订单 payment schedule）/ 结算层（发票 installment） | 整单为主 | 头级为主 | B |

**读这张表的方法**：A 轴决定"预收款存不存在"；B 轴决定"多批次能不能表达"；C 轴决定"一期一个起算点能不能配"。三者互相独立，所以"某产品有 A 但没 B"不是缺陷，是定位不同。

#### 24.2 三条物理定律（七家无一例外）

| 定律 | 内容 | 七家表现 |
|---|---|---|
| 定律 1 | **计划 ≠ 单据 ≠ 应收**，三层必须分离 | Oracle 用 AR 发票当结算层；SAP 用 FI 发票；金蝶/用友用应收单；没有一家把"计划行"当发票 |
| 定律 2 | **到期日 = 基准日 + 编排**，编排能力集合等价 | 全部可归约为四步：定基准日 → 顺延（cutoff）→ 月偏移 → 固定日 / 天偏移。差异只在"月"是自然月还是 30 天近似（星瀚用 30 天） |
| 定律 3 | **基数 = 订单/合同含税总额**，且分期合计必须闭合 | 金蝶"价税合计"；用友"整单含税金额"；畅捷通"各阶段之和 = 订单整单含税金额"；星瀚"加总校验 = 合同总金额"；Oracle 按 trx 总额；SAP 按发票总额 |

**最强的负向收敛**：七家在"出库/发货"环节做的都是**校验（闸门）**或**分单**，没有一家"每发生一次出库就自动复制一套期次"。三条独立证据链（用友应收单期号不可改、星瀚按维度分单、星空控制环节拦截提交）方向完全一致。

⇒ 这条负向结论可以写进设计约束：**"按批次动态生成组"必须我方自建，任何"行业标准做法"的引用都不成立。**

#### 24.3 三条分叉：不是能力差，是会计制度与法律环境决定

| 分叉 | 西方路径（Oracle / SAP） | 中国路径（金蝶 / 用友） | 根因 |
|---|---|---|---|
| **分叉 1：应收载体** | 发票是唯一应收载体 ⇒ 起算点默认 `invoice_date` | 出库/签收即产生应收事项 ⇒ 起算点含 `delivery` / `receipt` | 中国以票控税，但收入确认与风险转移按合同多在出库；两者必然错位 |
| **分叉 2：暂估应收** | ASC 606 / IFRS 15 按履约义务确认收入，发票只是账单 ⇒ **不需要**"暂估应收"这个对象 | 未开票但已出库 ⇒ 月末必须"暂估应收"（金蝶销售出库单下推暂估应收单、用友 SO091 签收暂估） | 法定凭证（增值税专用发票）与会计收入确认时点不一致 |
| **分叉 3：预收款** | 预收款只是 AR 的收款类型 = 财务科目问题；控制靠 Credit Check / Order Holds | 预收款是**流程闸门**：未达预收比例不许审核/发货/出库（金蝶控制环节四值、用友布尔闸门） | 中国 B2B 坏账风险与"先款后货"商业惯例；ERP 承担业务管控职责 |

**关键推论**：分叉 1、2 决定我方必须支持 `delivery` / `receipt` 起算点与 Wave B 的 `provisional_receivable`；分叉 3 决定 `control_stage` 必须存在，哪怕 Wave A 只实现 `none` / `order_confirm`。**这三条不是我方"多做的功能"，是中国市场的准入条件。**

#### 24.4 三个真正的设计自由度

排除掉行业一致项与制度决定项后，只剩三处需要我方拍板：

| # | 自由度 | 选项 | 谁有先例 |
|---|---|---|---|
| F1 | **分组键** | 整单 / 物料·项目（静态主数据）/ **出库批次（动态事实）** | 星瀚做了静态维度；**动态批次无人做** |
| F2 | **组基数口径** | 实际货值法 / **分配法** | 三家都隐含"总额分配"，但没人显式声明 |
| F3 | **预收款形态** | 闸门（gate）/ 标记（flag） | 金蝶、用友都做闸门 |

#### 24.5 我方的独特增量：动态分组键

星瀚的"收付款维度"与本方的组模型只在 B 轴上同构、在**生成时机**上根本不同：

| | 星瀚维度 | 我方批次组 |
|---|---|---|
| 分组键来源 | 静态主数据（创建时一次性算好） | **动态事实**（每张出库单过账后才新增一组） |
| 组数量 | 订单确认时确定 | 随发货次数增长，**事前未知** |
| 组基数 | 订单金额可直接按维度分摊 | 必须等该批实际出库量确定才能分摊 |
| 失败模式 | 维度成员选错（可改） | 发货红冲/退货 ⇒ 组必须作废且已收金额需重挂（不可简单回滚） |

⇒ **我方的增量不是"组/期"两层，而是"组的事件驱动追加 + 基数事实化 + 跨组不重复校验"三件套。** 这三件在七家产品文档中都没有对应机制，必须自研，且必须写清失败模式。

#### 24.6 核心洞察：组基数必须用「分配法」，不能用「实际货值法」

这是本次综合最重要的一条结论，直接决定"会不会重复收款"。

**实际货值法**（直觉写法）：

```
group_base_i = Σ(该批出库数量 × 订单单价) + 税额
```

**分配法**（正确写法）：

```
group_base_i = order.gross_amount × (该批数量 / 订单数量)
             （或按金额摊：order.gross_amount × 该批金额 / 订单行金额）
Σ_i group_base_i = order.gross_amount      ← 恒等，尾差归最后一批
```

| 比较项 | 实际货值法 | 分配法 |
|---|---|---|
| Σ 各组基数 = 订单总额？ | **不一定**：订单有整单折扣、含税四舍五入、价格变更时，`Σ 数量×单价` ≠ `gross_amount` | **恒等成立** |
| 与"600 = 1000×60%"的直觉一致？ | 否（是"60 件 × 单价"） | **是** |
| 与三家行业口径一致？ | 否 | **是**（价税合计 / 整单含税金额 / 合同总金额） |
| 尾差处理 | 无法定位 | 归最后一批，可审计 |

⇒ **定稿：`group_base_amount` 一律由分配法算出并落库**，同时把口径落成枚举 `group_allocation_basis`（`by_qty` / `by_amount`），禁止运行时重算（重算会出现"同一组昨天的基数与今天不同"）。

分配法的前提：出库行必须能归到订单行。若出库行跨订单行，先按"订单行金额占比"二次分摊。

#### 24.7 由此推出的四条不变量 + 组状态机

| 编号 | 不变量 | 违反后果 | 校验点 |
|---|---|---|---|
| I1 组内闭合 | 组内各期 `planned_amount` 之和 = `group_base_amount`（尾差归组内最后一期） | 组内漏收/多收 | 保存期次时 |
| I2 跨组互斥且封顶 | `Σ group_base_amount ≤ order.gross_amount`；同一 `group_source_doc_id` 不得进两组 | 重复收款（600+400+200=1200 型错误） | 新增组时 |
| I3 基数可追溯 | `group_base_amount` 与 `group_allocation_basis` 必须落库，不得运行时重算 | 基数漂移、对账无据 | 组激活时 |
| I4 组状态门禁 | 组只能由**已过账**的发货单创建；发货红冲 ⇒ 组必须作废，已收金额需转挂或退款 | 组挂在未过账事实之上 | 发货过账/红冲事件 |

**组状态机**（§23.7 当前缺）：

```
planned ──(发货单过账)──► activated ──(组内各期结清)──► closed
   │                          │
   └──(订单取消)──► cancelled ◄──(发货红冲/退货)──┘
```

- `planned`：订单确认时按计划量预建（可选，用于展示未来资金流）
- `activated`：基数落定，期次正式生效，可出现在到期清单
- `closed`：组内全部结算，不再出现在清单
- `cancelled`：组失效，但**不物理删除**（审计要求），期次同步作废

#### 24.8 对三个待拍板问题的最终建议

| # | 问题 | 建议 | 依据 |
|---|---|---|---|
| 1 | 尾款并入每组期 2（4 行 2 组）还是独立第三组（5 行 3 组、余额法） | **并入每组期 2** | 独立第三组必须用余额法（base = 已开票 − 已计划），余额法在第 1 批发货后、第 2 批未发时无法确定基数，会破坏 I2 的"可审计封顶"；并入后 4 行天然满足 Σ = 1000 |
| 2 | 组结构：方案甲（头 1:1 + 行上 `group_no`）还是方案乙（头 1:N） | **方案甲** | 组是动态追加的，方案乙会造成"每发一次货多一个头"，头的生命周期与订单 1:1 的语义被打散；方案甲只需在行上加 `group_no` / `group_base_amount` / `group_status` / `group_allocation_basis` 四列 |
| 3 | D3：Wave A 是否建 `payment_schedule` | **Wave A 走 D3-a（不建表，只挂 `payment_term`）；Wave B 建** | Wave A 没有出库过账（doc-flow G3 缺口），组只能全部停在 `planned`，建表即空表；且七家中"订单级计划"都依附已有单据，独立计划表是大型产品线（星瀚/用友）才有的形态 |

#### 24.9 一句话

七家产品告诉我们三件事：**计划/单据/应收必须三层分离（照做）、到期日就是四步编排（照做）、预收款在中国是闸门（照做）**；同时告诉我们一件不能被抄的事：**没有任何一家按"出库批次"动态生成计划组**——因为西方没有"出库即应收 + 以票控税"的双节点，中国两家有双节点却把分组键选在了静态主数据上。**"动态批次组 + 分配法基数 + 跨组封顶"是我方唯一需要自研、也唯一可能形成差异化的部分。**

> **注（2026-11-08）**：本句已被 **D12** 推翻——用户明确「没有任何一家做的，我们也不一定要做」。动态批次组改为默认不做，分组键固定在订单行拆批上。本节正文仅作历史研究记录保留，不作为实施依据。

---

## 25. 收款与核销对象模型（Payment Receipt & Allocation）

> 状态：**研究结论 v1（待评审）**，对应决策 **D14 / D15 / D16**。
> 术语约定：本节「付款/收款」在销售侧统一指**客户付款（receipt）**；采购侧（payment）为对称结构，字段命名以 `receipt` ↔ `payment` 互换即可。

### 25.1 缺口确认（先排除重复建模）

| 检查项 | 结论 | 证据 |
|---|---|---|
| `docs/specs/` 内是否已有收款单对象 | **没有** | `spec-receipt-object-model-2026-11-01.md` 全文围绕 `demand_allocation` / `target_bo='receipt'` / `R-PO-9`，是**采购收货（goods receipt）**模型，不是客户收款 |
| §24 是否已覆盖 | **只覆盖计划层** | §24 产出的是 `payment_schedule` + `payment_schedule_line`（计划），不含「钱实际到账」的事实单据与核销关系 |
| 采购侧是否有可复用契约 | **有，需对称** | `vendor_invoice` 契约（§10）已锁定，销售侧发票契约与之对称；收付款单无对应契约 |

**结论**：收款单 + 核销关系是**真实缺口**，本次需新增，不能复用收货模型。

### 25.2 三层对象链

```
sales_order ─ sales_order_line
   └─ payment_schedule（头，与订单 1:1，§24.8 方案甲）
        └─ payment_schedule_line
             group_no / group_base_amount / group_status / planned_amount
             line_type ∈ {normal, prepayment, retention}
             settled_amount          ← 只读缓存（现金 + 预收抵扣）
             control_stage            ← 本期控款/控票阶段
                    ▲
                    │ settlement（核销回写，只读派生）
                    │
payment_receipt（事实单据，**整单**）
   amount | applied_amount | reserved_amount | unapplied_amount
   └─ payment_allocation（关系层，N:M）
        ├─ prepay_to_schedule      → payment_schedule_line.settled_amount
        ├─ receipt_to_invoice      → customer_invoice.receipt_settled_amount
        ├─ prepay_offset_invoice   → customer_invoice.prepaid_offset_amount
        └─ on_account              → 客户挂账户（未指定订单/发票）
```

**三条结构性判断**：

1. 收款单**不带** `schedule_id` / `invoice_id` 外键（D14）。一笔款可跨期、跨票、跨订单，也可能暂时不指定任何对象（`on_account`）。
2. 期次归属由 `payment_allocation` 表达，N:M。收款单 1 : N 核销行，计划行 1 : N 核销行。
3. 累计类字段**全部是派生缓存**，真源是 `payment_allocation`；任何重算都必须能从核销行还原。

### 25.3 `payment_receipt`（头）字段

| 分组 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 标识 | `id` | integer | 是 | 主键 |
| | `receipt_no` | string(30) | 是 | 业务键，取号后不可改（外部流水号走 S6 校验） |
| | `document_type_id` | integer | 是 | `scope_bo='payment_receipt'` + `level=header` |
| 日期 | `receipt_date` | date | 是 | `business_date_field`；到账日 |
| | `posting_date` | date | 否 | 会计日期 |
| 状态 | `status` | string | 是 | `draft / submitted / posted / cancelled` |
| 往来方 | `customer_account_id` | integer | 是 | 付款方主体 |
| | `payer_account_id` | integer | 否 | 代付方；空 = 同客户 |
| 币种 | `currency_id` | integer | 是 | 到账币种（**允许与发票币种不同**，汇率在核销行折算） |
| | `exchange_rate` / `exchange_rate_type` / `exchange_rate_date` | 同 SO | 否 | 本币折算快照 |
| 金额 | `amount` | number(18,4) | 是 | 到账总额（原币） |
| | `applied_amount` | number(18,4) | 是 | 已核销（缓存，= Σ 有效 allocation） |
| | `reserved_amount` | number(18,4) | 是 | 预占用（已指定订单/组但未核销） |
| | `unapplied_amount` | number(18,4) | 是 | 未核销（挂账户） |
| 结算 | `payment_method_id` | integer | 否 | 银行转账 / 承兑汇票 / 现金 / 第三方 |
| | `bank_account_id` | integer | 否 | 收款账户（组织维度） |
| | `reference_no` | string(64) | 否 | 银行流水号 |
| | `remark` | text | 否 | 备注 |
| 审计 | `created_by` / `created_at` / `updated_at` | — | — | audit_aspect，`changed_only` |

**YAML 要点**：

```yaml
document:
  number_field: receipt_no
  business_date_field: receipt_date
  state_field: status
  posting_state: posted
  document_type_field: document_type_id
  line_object: payment_allocation
  line_parent_field: receipt_id
deletion_policy: {mode: restrict, cascade_delete: [payment_allocations]}
audit: {enabled: true}
```

- `posted` 后整单只读；纠正只能 `cancel` 或做反向核销（见 V5），**不允许修改 amount**。
- 不做 `revision_policy`（同 D5 口径）。

### 25.4 `payment_allocation`（核销行）字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | 是 | 主键 |
| `receipt_id` | integer | 是 | 父键 |
| `line_no` | integer | 是 | 唯一键 `receipt_id + line_no` |
| `allocation_type` | string(24) | 是 | `prepay_to_schedule` / `receipt_to_invoice` / `prepay_offset_invoice` / `on_account` |
| `target_bo` | string(32) | 是 | `sales_order` / `payment_schedule_line` / `customer_invoice` / `customer_account` |
| `target_id` | integer | 否 | 目标头 id |
| `target_line_id` | integer | 否 | 目标行 id（期次核销必填） |
| `amount` | number(18,4) | 是 | 核销金额（收款币种） |
| `amount_local` | number(18,4) | 是 | 本币金额（汇率折算快照） |
| `allocation_date` | date | 是 | 核销日 |
| `status` | string(16) | 是 | `active` / `reversed` |
| `reversal_of_allocation_id` | integer | 否 | 反向记录指向原核销行 |
| `reason` | string(256) | 否 | 核销/反核销原因 |

**为什么核销要独立成表而不是在收款单上存 JSON**：拆表才能满足 V2/V3 的封顶校验（Σ 核销 ≤ 目标可核销额），也才能在计划行上做「已核销金额 + 核销状态」的稳定查询。

### 25.5 三层累计口径（D16）

| 层 | 对象.字段 | 回答的问题 | 口径说明 |
|---|---|---|---|
| 事实层 | `payment_receipt.amount` | 这笔钱到了多少 | 银行到账原币 |
| | `payment_receipt.applied_amount` | 已经用掉多少 | Σ `allocation(status=active)`，**不含** `on_account` |
| | `payment_receipt.reserved_amount` | 被哪张单预占了 | 只能指向 `order_id` / `group_no`（V1b） |
| | `payment_receipt.unapplied_amount` | 还有多少可分配 | 客户多付、暂未指定 |
| 发票层 | `customer_invoice.receipt_settled_amount` | 这张票**收到现金**多少 | 只由 `receipt_to_invoice` 累加 |
| | `customer_invoice.prepaid_offset_amount` | 这张票被**预收款抵扣**多少 | 只由 `prepay_offset_invoice` 累加 |
| 计划层 | `payment_schedule_line.settled_amount` | 这一期的钱**到位没有** | 现金 + 预收抵扣合并（对客户只问"这期清了没"） |
| 订单层 | `order_settlement_summary`（**视图，不落表**） | 这单整体收了多少、还差多少 | 由上述三层聚合 |

**必须分离的理由**：金蝶把两者合并为「已结算金额」，导致客户无法区分"这 10 万是汇进来的"还是"用预收款抵掉的"，退款时基数不可判。SAP 侧用**开票状态（`VBUP-FKSTA` / `FKSAA`）+ 清账凭证（clearing document）**把「开票进度」与「收款清账」分成两个独立事实，因此我方拆两列（D16）。

### 25.6 不变量 V1–V6

| 编号 | 内容 | 触发时点 |
|---|---|---|
| **V1** | `applied_amount + reserved_amount + unapplied_amount = amount` | 收款单每次核销/反核销后 |
| **V1b** | `reserved_amount` 只能指向 `order_id` / `group_no`，**不得指向发票**（发票是既成事实，无需预占） | 建 `allocation` 时 |
| **V2** | 单计划行 Σ `active` 核销 ≤ `planned_amount`（跨收款单汇总） | 核销提交时 |
| **V3** | `receipt_settled_amount + prepaid_offset_amount ≤ gross_amount` | 发票核销时 |
| **V4** | 预收抵扣限同一 `order_id` / `group_no`，跨单抵扣需显式授权标记 | 核销时 |
| **V5** | 取消核销 = 新增 `reversed` 反向记录 + 原行置 `reversed`；反向行金额 **≤** 原行金额（**允许部分反核销**），不改原金额 | 反核销时 |
| **V6** | 结算口径（settled）与付款核销口径（applied）分开统计，任何报表不得混算 | 报表/视图 |

> **V5 已于 2026-11-08 放宽（原稿为「整额反冲」）**：原稿依据 Oracle AR `unapply`（不允许部分反核销）。但 SAP 的 **partial payment**（保留原未清项）与 **residual payment**（按未付额生成新未清项）两种模式都支持部分金额清账，说明「整额」只是 Oracle 该动作的实现限制，不是行业共识。因此 Wave A 即允许部分反核销（反向行 ≤ 原行），业务不必靠"拆两笔原核销"绕过。详见 §26.5。

### 25.7 预付款链路（D15：开票前无应收，如何处理）

三种行业解法与我方取舍：

| 方案 | 代表 | 机制 | 代价 |
|---|---|---|---|
| A. 统计性请求单 | SAP | 开票类型 `FAZ`（billing category = P 请求）→ 生成开票凭证 → FI 记 **noted item** + 特殊总账标识 **F**；客户付款用标识 **A**；最终发票 `F2` 由条件类型 **AZWR** 抵扣；取消用 **FAS** | 需要独立的总账标识体系与 FI 集成 |
| B. 假应收（预付发票） | Oracle AR | Prepayment 是**发票类型**，付款后 apply 到标准发票，可部分核销 | 会污染应收台账，账龄/DSO 失真 |
| C. 不造假，只走核销锚点 | 金蝶 / 用友 | 预收单/预收款 + 核销单（业务类型「预付冲应付」），不生成应收 | 需要承诺层锚点，否则预收无处可挂 |

**我方选 C，但补一个承诺锚点（D15）**：

```
预付款到账
  └─ payment_receipt(status=posted, amount=10万, reserved=10万, applied=0, unapplied=0)
        └─ payment_allocation(type=prepay_to_schedule, target=sales_order / group_no)
              └─ payment_schedule_line(line_type=prepayment).settled_amount += 10万
发货 / 开票
  └─ customer_invoice(posted, gross=10万)
        └─ payment_allocation(type=prepay_offset_invoice, amount=10万)
              └─ customer_invoice.prepaid_offset_amount = 10万
              └─ 同时把原 reserved 行置 applied（资金用途落定）
```

关键：**开票前不进 `applied`**。理由是没有应收对象可核销，若强行 `applied` 会出现「已核销但无对方单据」的悬空行，V3 无处校验。

### 25.8 与 §24 组模型的衔接

| §24 概念 | §25 落点 |
|---|---|
| `group_no` | `payment_allocation` 的 `reserved` 锚点；计划行 `settled_amount` 按组汇总 |
| `group_status = planned` | 只允许 `reserved`，不允许 `applied`（组基数未定，核销会破坏 I2） |
| `group_status = activated` | 允许 `applied`，且受 V2 封顶 |
| `group_status = closed` | 拒绝对该组的任何新核销 |
| `group_status = cancelled` | 已核销金额必须转挂（新组）或退款，不允许直接作废 |

### 25.9 订单级汇总视图 `order_settlement_summary`

```sql
-- 视图，不建表（沿用 D2「到期清单不建表」原则）
order_id, group_no,
planned_total,            -- Σ payment_schedule_line.planned_amount
invoiced_total,           -- Σ customer_invoice_line.gross_amount
receipt_settled_total,    -- Σ 现金核销
prepaid_offset_total,     -- Σ 预收抵扣
outstanding_total,        -- planned_total - settled 合计
overdue_total             -- 逾期未结（按 term line 到期日 + 宽限）
```

### 25.10 与 §24.9 的冲突处理

§24.9 结论「动态批次组 + 分配法基数 + 跨组封顶是我方唯一需要自研」**作废**（D12）。本节的三层链路不依赖动态批次组，只依赖：
1. 计划行上的 `group_no`（订单行拆批时静态写入）
2. `payment_allocation` 的 N:M 核销
3. 三层累计缓存 + V1–V6 校验

### 25.11 行业证据等级

| 事实 | 来源 | 等级 |
|---|---|---|
| SAP `FAZ` = 请求类开票类型，FI 记 noted item + 特殊总账标识 `F`；付款用 `A`；`F2` 用 `AZWR` 抵扣；取消用 `FAS` | SAP Help / 官方手册 | **A** |
| SAP 计划行开票状态字段是 **`FPLT-FKSAF`**（A 未处理 / B 部分 / C 已开票 / D 拒绝 / E 已请求），`STATV` 只是其数据域、**不是字段名**；订单行侧为 `VBUP-FKSTA`（交货相关开票状态）/ `VBUP-FKSAA`（订单相关开票状态） | SAP 表结构文档 + 官方 Help 衍生 | **B**（原稿写「`FPLT-STATV`」，2026-11-08 已订正） |
| Oracle AR 收款状态 APP / UNID / UNAPP / REV；支持 On Account、Unapplied、部分收款 | Oracle AR 用户指南 | **A** |
| Oracle AP Prepayment 为发票类型，付款后 apply 到标准发票，`unapply` 必须整额 | Oracle AP 用户指南 | **A** |
| 金蝶应付单「付款计划」页签含「已核销金额」+ 核销状态；「已结算/未结算/锁定金额」 | 金蝶云·星空产品手册 | **A** |
| 用友 U8C「预占用金额」：余额 − 预占用 才参与核销；「即时核销-按单据/按表体」 | 用友 U8C 手册 | **A** |
| 畅捷通收付款单列「累计核销金额 / 未核销金额」；核销依据「按单据/按明细」 | 畅捷通产品文档 | **A** |

### 25.12 待拍板（3 条已提建议）

| # | 问题 | 建议 |
|---|---|---|
| 1 | 预付款开票前只进 `reserved`，不进 `applied` | 采纳（D15） |
| 2 | 客户多付进 `unapplied`（挂账户）而非 `reserved`（指定订单） | 采纳：`unapplied` 是客户级，`reserved` 是订单级，不可混用 |
| 3 | 反核销是否允许部分 | Wave A 整额（V5），Wave C 再放宽 |

### 25.13 配套字段改动清单（与 §24 联动）

| 对象 | 改动 | 状态 |
|---|---|---|
| `payment_schedule`（头） | 补 `gross_amount`（含税计划总额） | 待评审 |
| `payment_schedule_line` | 补 `line_type`（`normal`/`prepayment`/`retention`）、`settled_amount`、`control_stage` | 待评审 |
| `customer_invoice` | 补 `receipt_settled_amount`、`prepaid_offset_amount` | 待评审 |
| `customer_invoice_line` | 补 `order_unit_price` / `price_diff_amount` / `price_override_reason`（D13） | 待评审 |
| `payment_term_line` | 扩 `settle_basis`（`invoice`/`delivery`/`receipt`） | Wave B |

---

## 26. SAP 预付款与应收清账（补充研究，2026-11-08）

> 定位：§18 已拆解 SAP 的**开票侧**（VBRK/VBRP、FKART/FKTYP、FPLA/FPLT、VF04、VF11）。本节只补**钱侧**——预付款如何挂账、发票如何抵扣、收款如何清账、分期如何落到应收。
> 证据说明见 §26.9：本轮复核**未取到 SAP Help 正文**，最高 B 级。

### 26.1 结论速览

| # | 结论 | 对我方 |
|---|---|---|
| 1 | 预付款请求（`FAZ`）是**请求单**，产生 noted item（Merkposten），不产生借貸、不更新应收余额 | D15 选 C 正确；我方用 `payment_schedule_line(line_type=prepayment)` 承担同一角色，比 SAP 更轻 |
| 2 | 真预收款用**特殊总账标识 A**（Anzahlung），请求用 **F**（Anzahlungsanforderung）；靠「替代对账科目 + 统计型 + 报表默认过滤」实现"挂账但不进账龄" | 我方 `reserved_amount` 是同一语义的业务层实现，但**必须在报表层显式过滤**，否则账龄会虚高 |
| 3 | 抵扣链三步：`F-29` 收预付（标识 A）→ 最终发票用条件类型 **`AZWR`** 抵扣（不得超过发票金额，位于销项税之前）→ 欠抵扣余额用 **`F-39`** 清掉 | 我方 `prepay_offset_invoice` + V3 封顶与之等价 |
| 4 | **分期不是"一个未清项带 3 个到期日"，而是拆成 3 个独立应收行项目，各自算到期日** | 我方"计划行 + `payment_allocation.target_line_id`"达到同样效果，且**开票前就存在**（可做预收闸门），SAP 必须等发票 |
| 5 | `partial payment`（留原未清项）与 `residual payment`（按未付额生成新未清项）都支持部分金额 | **推翻 V5 的「整额反冲」**（已放宽，见 §25.6） |

### 26.2 开票类型：FAZ / FAS

| 类型 | 语义 | FI 侧效果 |
|---|---|---|
| `FAZ` | 预付款请求（down payment request），开票类别 **P** | 只生成 **noted item / Merkposten**：有凭证号、单行、**无借貸、不动应收余额**；仍可在行项目显示中被引用，也能被付款程序/催款程序处理 |
| `FAS` | `FAZ` 的标准取消类型（VF11 冲销时生成） | 冲销该请求凭证 |
| `FAY` | — | **未证实**（标准清单未检到，疑为客户自有命名，不要引用） |

> 关键点：SAP 把"我要收预付"这件事建模成**一张不产生应收的请求单**。这与我方 `payment_schedule_line(line_type=prepayment)` 的定位完全一致——**请求是计划层对象，不是应收对象**（印证 D15）。

### 26.3 特殊总账标识（Special G/L Indicator）

| 标识 | 英文 | 德文 | 用途 | 典型事务码 |
|---|---|---|---|---|
| **A** | Down Payment | Anzahlung | 真实预收款 | `F-29`（Enjoy: `FBA2`） |
| **F** | Down Payment Request | Anzahlungsanforderung | 预付款请求（统计型） | `F-37`（Enjoy: `FBA1`） |

"挂账但不进正常应收/账龄"靠三件事：
1. `OBXR` / `OBYR`（或 `FBKP`）为该标识配置**替代对账科目**，不走正常应收对账科目；
2. `F` 是统计型，根本不产生借貸；
3. 标准客户行项目报表与账龄默认**过滤**特殊总账项（`FBL5N` 需显式勾选才显示）。

**对我方的直接启示**：`reserved_amount` 若不在报表层过滤，客户账龄/DSO 会被预收款虚假压低——必须像 SAP 一样把"预占"与"已开票应收"分成两个报表口径（呼应 V6）。

### 26.4 预付款 → 发票抵扣 → 清零

```
① 收预付      F-29（标识 A）      借 银行 / 贷 客户（预收款科目）  → 真实特殊总账未清项
② 最终发票    条件类型 AZWR       条件类 E、计算式 48，上限 = 发票金额，置于销项税之前
                                  → 发票净额只开剩余部分；允许手工改 AZWR 做部分抵扣
③ 清零        F-39（Enjoy: FBA3） 未被抵扣的预付余额 → 转回正常应收 / 清账
```

我方映射：

| SAP | 我方 |
|---|---|
| `FAZ` 预付款请求（noted item） | `payment_schedule_line(line_type=prepayment)` |
| `F-29` 收预付（标识 A） | `payment_receipt` + `payment_allocation(prepay_to_schedule)`，钱进 `reserved` |
| `AZWR` 抵扣 | `payment_allocation(prepay_offset_invoice)` → `customer_invoice.prepaid_offset_amount` |
| `F-39` 清余额 | 计划行 `settled_amount` 结转 + 剩余 `unapplied` 退回/挂账 |

### 26.5 清账机制（关键的三个更正）

| 事务 / 对象 | 作用 |
|---|---|
| `F-28` | 收款过账，可同时勾选发票完成清账 |
| `F-32` | 只清客户未清项（不涉及银行过账） |
| `F.13`（程序 `SAPF124`） | 自动清账：按 `OB74` 配置的匹配字段分组，净额为 0 即清 |
| `BSID` → `BSAD` | 未清项 → 已清项；清账后写入 `AUGDT`（清账日）、`AUGBL`（清账凭证号） |
| clearing document | 清账动作产生的 FI 凭证，把被清项目与差额记在一起——**这才是"反核销"应该还原的对象** |

| 付款方式 | 原发票未清项 | 结果 |
|---|---|---|
| **Partial payment** | **保持未清** | 付款单独成一条贷方未清项，需二次清账（两笔未清项并存） |
| **Residual payment** | **被清掉** | 同一张清账凭证内按未付额生成**新未清项**（带新到期日） |

> **更正 1（V5）**：SAP 两种模式都支持部分金额，`整额反冲`只是 Oracle AR `unapply` 的实现限制 → V5 已放宽为"反向行 ≤ 原行"。
> **更正 2（字段名）**：`FPLT` 没有 `STATV` 字段；计划行开票状态字段是 **`FPLT-FKSAF`**，`STATV` 只是其数据域（数据元素 `FKSAF` → 域 `STATV`）。原稿 §25.11 已订正。
> **更正 3（状态分层）**：订单行侧是 `VBUP-FKSTA`（交货相关开票状态）与 `VBUP-FKSAA`（订单相关开票状态），二者与 `FPLT-FKSAF` 不是同一个对象，引用时不可混用。

### 26.6 分期付款条件：OBB8 / OBB9（T052S）

| 配置 | 内容 |
|---|---|
| `OBB8` | 付款条件（表 `T052`）：基准日规则、账期、现金折扣 |
| `OBB9` | **分期条件**（表 `T052S` 的维护界面）：`ZTERM`（组）、`RATNR`（期号）、`RATPZ`（百分比）、`RATZT`（该期自己的付款条件） |

**核心事实**：发票**只开一次**；FI 过账时按各期**拆成多条应收行项目，每行独立算基准日与到期日** → 因此能按"期"核销。

与我方对比：

| 维度 | SAP | 我方 |
|---|---|---|
| 期次的宿主 | **发票行 / 应收未清项** | **`payment_schedule_line`（开票前就存在）** |
| 分期模板 | 付款条件（`T052` + `T052S`） | `payment_term` + `payment_term_line`（四步到期日，见 `payment_term_line.yaml`） |
| 能否开票前控款 | 不能（必须等发票生成未清项） | **能**（`control_stage` + `settled_amount`） |
| 按"期"核销的键 | 未清项 `BELNR + BUZEI` | `payment_allocation.target_line_id` |

> 结论：我方把"期"从发票行**上移**到计划行，是比 SAP 更利于预收闸门的结构；代价是必须自己维护期次与实际核销的一致性（V2 封顶即为此）。

### 26.7 现金核销（cash application）自动化

| 手段 | 解决什么 | 事务码 |
|---|---|---|
| Lockbox | 银行代收箱 + BAI/BAI2 文件带发票号，自动匹配；未识别转人工 | `FLB2` 导入（`RFEBLB00`）、`FLB1` 后处理 |
| 电子银行对账单（EBS） | 整份对账单按 posting rule + search string 自动清账 | `FF.5` / `FF_5` 导入，`FEBAN` 后处理 |
| Payment advice | 客户汇款通知作为匹配依据；S/4 的 SAP Cash Application 用 ML 给匹配建议（事务码未证实） | — |
| `F.13` | 无外部信息时按规则批量清 | `SAPF124` |
| **Payment on account** | 多付/未指定发票 → 客户账户上一条**贷方未清项**，后续 `F-32` 核销 | 与 `F-29`（标识 A 预收款）**不同，勿混用** |

我方映射：`on_account` 对应 "payment on account"（客户级 `unapplied`）；`prepay_to_schedule` 对应 "down payment（标识 A）"（订单级 `reserved`）。**两者不可合并**，正是 V1b 的理由。

### 26.8 对我方模型的 5 条影响

| # | 影响 | 落点 |
|---|---|---|
| 1 | 预付款请求不应生成应收（noted item 语义） | D15 维持，不需造假应收 |
| 2 | 特殊总账"挂账但不进账龄"必须靠报表口径过滤 | V6 + §25.9 视图需区分 `reserved` 与应收 |
| 3 | 分期 = 多个可独立核销的到期单元 | §25.4 `target_line_id` 设计成立 |
| 4 | 部分反核销是行业通行能力 | V5 已放宽（§25.6） |
| 5 | 多付/未指定必须独立于预占 | V1b 维持 |

### 26.9 证据等级说明

本轮为独立复核，**SAP Help 官网正文未取回**（页面返回空），因此：
- §26 全部结论最高为 **B**（SAP 表结构字典 leanx、OpenExamPrep 学习指南、SAPinsider、WU 术语表、SAP TCodes 站点、Guru99、第三方顾问博客）；
- §25.11 中 SAP 相关条目（`FAZ` / `AZWR` / 特殊总账标识）的 **A** 级来自早期取自 SAP Help 的结论，本轮未能二次证实——建议评审时用官方 Help 再核一遍再定「已定」；
- 凡标 **C** 或「未证实」的（如 `FAY`、S/4 Cash Application 事务码），不得直接写进实现。

### 26.10 Sources

1. FPLT 表结构（`FKSAF` 取值 A/B/C/D/E） — https://leanx.eu/sap/table/fplt/
2. VBUP 表结构（`FKSTA` / `FKSAA`） — https://leanx.eu/sap/table/vbup/
3. T052S 分期付款条件结构（`ZTERM` / `RATNR` / `RATPZ` / `RATZT`） — https://leanx.eu/sap/table/t052s/
4. Credit/Debit Memos, Down Payments（`FAZ` → noted item、标识 `F`/`A`、`AZWR`） — https://open-exam-prep.com/study-guides/sap-s4hana-sd/billing-financial-integration/credit-memos-cancellations
5. Billing Plans & Installments（每期一条应收行） — https://open-exam-prep.com/study-guides/sap-s4hana-sd/billing-financial-integration/billing-plans-installments
6. SAP 分期付款条件配置（OBB8 / OBB9，拆三行示例） — https://cloud.tencent.com/developer/news/881357
7. SAPinsider：Customer Down Payment Process（`FAZ`/`FAS`、`AZWR`） — https://sapinsider.org/improve-your-companys-revenues-with-saps-customer-down-payment-process/
8. WU Vienna SAP Glossary：Noted Item（Merkposten） — https://www.wu.ac.at/erp/glossary/n/10
9. SAP TCode `F-39`：Clear Customer Down Payment — https://www.sap-tcodes.org/tcode/f-39.html
10. Guru99：Residual Payment vs Partial Payment — https://www.guru99.com/how-to-post-incoming-partial-payments-by-residual-method.html
11. `F.13` / `SAPF124` / `OB74` 自动清账规则 — https://bestsapcbi.com/sap-cross-company-code-clearing/
12. SAP TCode `FLB2`：Import Lockbox File — https://www.sap-tcodes.org/tcode/flb2.html

---

## 27. 收付款对象模型总纲（收敛版，2026-11-09）

> 定位：§20–§26 是**研究过程**（含已作废的中间结论），本节是**收敛结果**。评审只需读本节 + §13 决策记录。
> 状态：**研究草案，待评审**。以下「已定」指用户拍板，「建议」指待拍板。
> 与旧文冲突时以本节为准；已知冲突见 §27.9。

### 27.1 全局对象地图

```
【计划层】
sales_order
 └─ sales_order_line
     ├─ billing_relevance          delivery | plan | none（D10）
     ├─ sales_order_schedules      kind = delivery | billing
     └─ payment_schedule           与订单 1:1（Wave B，D3-a）
          └─ payment_schedule_line
               group_no / group_base_amount / group_status
               line_type / planned_amount / settled_amount / control_stage

【事实层】—— 只写一次，过账后只读
shipment ─ shipment_line                    出库事实
customer_invoice ─ customer_invoice_line    开票事实
payment_receipt                             收款事实（整单，无期间外键）

【关系层】—— 表达"谁来自谁""谁抵了谁"
payment_allocation                          核销关系（N:M，四类 target）
doc_flow_edges                              单据流转（池 billing）

【视图层】—— 不落表
order_settlement_summary                    订单/组级汇总
```

**分层铁律**：计划层可改、事实层过账后不可改、关系层只能新增不能修改、视图层永不落表。

### 27.2 对象清单与职责边界

| # | 对象 | 层 | 职责一句话 | 生命周期 | 唯一写入口 | 可物理删 |
|---|---|---|---|---|---|---|
| 1 | `sales_order_line` | 计划 | 承载合同行的量、价、税与开票方式 | 已有 | SO 服务 | 否 |
| 2 | `sales_order_schedules` | 计划 | 承载发货计划 / 开票计划（`kind`） | 已有 | SO 服务 | draft 可 |
| 3 | `payment_schedule` | 计划 | 订单级收付款计划头，与订单 1:1 | 新建（Wave B） | 计划服务 | 否（restrict） |
| 4 | `payment_schedule_line` | 计划 | 一个到期单元（期次），含组归属 | 新建 | 计划服务 | 否 |
| 5 | `shipment_line` | 事实 | 出库数量事实 | 已有 | 出库服务 | 否（红冲代替） |
| 6 | `customer_invoice` | 事实 | 开票单据头 | 新建 | `CustomerInvoiceService` | draft 可 |
| 7 | `customer_invoice_line` | 事实 | 开票行（含价差快照 D13） | 新建 | 同上 | 随头 |
| 8 | `payment_receipt` | 事实 | 客户付款到账事实（整单） | 新建 | `PaymentReceiptService` | 否 |
| 9 | `payment_allocation` | 关系 | 把一笔钱对到计划/发票/订单/客户账户 | 新建 | `AllocationService` | 否（只能反核销） |

**边界判断三问**（新增对象前必答）：
1. 它有没有独立的业务编号与业务日期？→ 决定是不是"单据"
2. 它过账后是否必须不可改？→ 决定是不是"事实层"
3. 它能否被多次引用、且引用方与被引用方都可独立存在？→ 决定是不是"关系层"

### 27.3 关系模型

#### 27.3.1 三类关系

| 类型 | 定义 | 实例 | 基数 | 写入规则 |
|---|---|---|---|---|
| **归属** | 子对象不能脱离父对象存在 | order → order_line；order → payment_schedule；schedule → line；invoice → line；receipt → allocation | 1:N / 1:1 | 父删除时 restrict；子随父级联仅限 draft |
| **追溯** | 事实之间的来源快照，只读 | invoice_line → shipment_line；invoice_line → schedule_line；allocation → target | N:1 | 只在创建时写一次，此后只读 |
| **核销** | 双向的多对多抵消关系 | receipt ↔ schedule_line；receipt ↔ invoice；receipt ↔ order/group | N:M | 只能新增；撤销靠反向记录 |

#### 27.3.2 `payment_allocation` 多态 target 设计

三种写法对比：

| 方案 | 结构 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| 甲 | 每类 target 一列外键（`schedule_line_id` / `invoice_id` / `order_id`），用 `CHECK` 保证互斥 | 强约束、可建外键 | 加一类 target 就要改表 | 备选 |
| **乙** | `target_bo` + `target_id` + `target_line_id` | 扩展零成本 | 无法建数据库外键，靠服务层保证 | **采用** |
| 丙 | 每种 target 一张中间表 | 约束最强 | 四张表、查询要 UNION | 否决（过度设计） |

采用乙的理由：Wave A 只有 4 类 target，但 Wave C 可能加"服务确认单"，甲会触发表结构变更。

```yaml
payment_allocation:
  target_bo: enum(order, group, customer_invoice, customer_account)
  target_id: integer          # 头 id
  target_line_id: integer     # 行 id（发票行为 invoice_line，计划行为 schedule_line）
```

约束：`target_bo` 与 `target_line_id` 的可用组合由服务层白名单校验（R1-3）。

#### 27.3.3 基数总表

| 从 | 到 | 基数 | 说明 |
|---|---|---|---|
| sales_order | sales_order_line | 1:N | |
| sales_order | payment_schedule | **1:1** | §24.8 方案甲 |
| payment_schedule | payment_schedule_line | 1:N | 按 `group_no` 分组 |
| sales_order_line | payment_schedule_line | 1:N | 一行可拆多批 ∏ 多期 |
| shipment | shipment_line | 1:N | |
| customer_invoice | customer_invoice_line | 1:N | |
| payment_receipt | payment_allocation | 1:N | 一笔款可多次核销 |
| payment_schedule_line | payment_allocation | 1:N | 一期可被多笔款核销 |
| customer_invoice | payment_allocation | 1:N | 一张票可多次收款 |

### 27.4 规则模型

规则分四类，编号前缀区分：`R1` 结构、`V` 不变量、`ST` 状态、`B` 业务。

#### 27.4.1 R1 结构性规则（建表/建对象时校验）

| 编号 | 规则 | 违反后果 |
|---|---|---|
| R1-1 | `payment_receipt` **不得**带 `schedule_id` / `invoice_id` / `order_id` 外键（D14） | 设计评审否决 |
| R1-2 | `customer_invoice_line` 的来源互斥：`shipment_line_id` 与 `schedule_id` 只能有一个非空（R-INV-3） | 落库拒绝 |
| R1-3 | `payment_allocation.target_bo` 只能是 `order` / `group` / `customer_invoice` / `customer_account`；`target_line_id` 仅前两者与 `customer_invoice` 允许非空 | 落库拒绝 |
| R1-4 | 所有累计字段（`settled_amount` / `receipt_settled_amount` / `prepaid_offset_amount` / `applied_amount` / `reserved_amount` / `unapplied_amount`）**只读**，只能由服务层通过 `payment_allocation` 重算写入 | 直接 UPDATE 视为缺陷 |
| R1-5 | 事实层对象过账后不可 UPDATE 金额字段，只能整单红冲或反向记录 | 落库拒绝 |

#### 27.4.2 V 不变量（提交时校验）

| 编号 | 内容 | 触发时点 | 新增/沿用 |
|---|---|---|---|
| **V1** | `applied_amount + reserved_amount + unapplied_amount = amount` | 每次核销/反核销后 | 沿用 |
| **V1b** | `reserved` 只能指向 `order_id` / `group_no`，**不得指向发票** | 建 allocation 时 | 沿用 |
| **V2** | 单计划行 Σ `active` 核销 ≤ `planned_amount` | 核销提交时 | 沿用 |
| **V3** | `receipt_settled_amount + prepaid_offset_amount ≤ gross_amount` | 发票核销时 | 沿用 |
| **V4** | 预收抵扣限同一 `order_id` / `group_no`，跨单需显式授权标记 | 核销时 | 沿用 |
| **V5** | 反核销 = 新增 `reversed` 反向行 + 原行置 `reversed`；反向行金额 **≤** 原行金额 | 反核销时 | 沿用（已放宽） |
| **V6** | 结算口径（settled）与核销口径（applied）不得混算 | 报表/视图 | 沿用 |
| **V7** | `allocation.amount ≤ min(资金侧可用, 目标侧可核销余额)` | 核销提交时 | **新增** |
| **V8** | 同一 allocation 只能有一条有效反向记录（唯一索引） | 反核销时 | **新增** |
| **V9** | allocation 落库与余额更新必须同事务，且余额更新影响行数 = 1 | 核销提交时 | **新增** |

**V7 展开**：

```
资金侧可用 = receipt.amount
           − Σ allocation(status=active, type∈{receipt_to_invoice, prepay_offset_invoice})
           − Σ allocation(status=active, type=prepay_to_schedule)

目标侧可用（按 target_bo 三选一）：
  schedule_line : planned_amount − Σ active 核销到该行
  invoice       : gross_amount − receipt_settled_amount − prepaid_offset_amount
  order/group   : contract_limit_amount × (1 + over_tolerance_percent/100)
                  − Σ active 已核销 − Σ active 已预占
```

> **波次注记（见 §28.2 断点 F）**：Wave A 只实现 `invoice` + `customer_account` 两个分支；`schedule_line` 随 `payment_schedule` 在 Wave B 落地；`order/group` 分支依赖合同额字段，Wave C 再开。`contract_limit_amount` 在 Wave A/B **不存在**，不得提前引用（见 §28.2 断点 B）。

**V8 展开**：`reversal_of_allocation_id` 建唯一索引（`WHERE status = 'active'`），保证一笔核销只能被反冲一次；多次反冲必须走"反冲的反冲"（新增正向记录）。

**V9 的意义**：这是把 SAP 的 `EFBKPF` 锁 + `F1805` 更新终止翻译成 SQLite 的最小等价物。见 §27.6。

#### 27.4.3 ST 状态规则

**`payment_receipt`**：

| 状态 | 允许动作 | 允许改金额 | 允许核销 |
|---|---|---|---|
| `draft` | 编辑 / 提交 / 删除 | 是 | 否 |
| `posted` | 核销 / 反核销 / 红冲 | 否 | 是 |
| `reversed` | 只读 | 否 | 否 |

**`payment_schedule_line.group_status`**：

| 状态 | 允许新核销类型 | 说明 |
|---|---|---|
| `planned` | 只允许 `prepay_to_schedule`（reserved） | 组基数未定，`applied` 会破坏 I2 |
| `activated` | `prepay_to_schedule` + `receipt_to_invoice` | 受 V2 封顶 |
| `closed` | 拒绝 | 已结清 |
| `cancelled` | 拒绝，已核销金额必须转挂或退款 | 不物理删除 |

**`customer_invoice`**：沿用 §6.1（draft → submitted → posted → reversed / cancelled），`posted` 后只读。

#### 27.4.4 B 业务规则

| 编号 | 规则 | 默认值 | 可配 | 依据 |
|---|---|---|---|---|
| B1 | 核销不得超计划期次 | 硬拦 | 容差三字段 | §24 |
| B2 | 核销不得超发票应收 | 硬拦 | 容差三字段 | V3 |
| B3 | 预收抵扣限同订单/组 | 硬拦 | 跨单需授权标记 | V4 |
| B4 | 超容差默认动作 | `block` | `block` / `warn` / `approve_once` | 金蝶硬拦 + SAP 消息分级 |
| B5 | 重复付款硬唯一键 | 三键唯一 | 不可关 | 见 §27.6.3 |
| B6 | 疑似重复分级 | 预警 | 预警 / 落地确认 / 禁止 | §25 三道防线 |
| B7 | 已过账不可改 | 硬拦 | 不可关 | R1-5 |
| B8 | 组关闭后拒绝新核销 | 硬拦 | 不可关 | ST 矩阵 |
| B9 | 同一订单同币种 | 硬拦（Wave A） | Wave C 放开 | §4 |

**容差三字段**（落在 `payment_schedule` 头与 `customer_invoice` 头）：

```
over_tolerance_percent   number(9,4)   默认 0
over_tolerance_amount    number(18,4)  默认 0
over_tolerance_action    enum          block | warn | approve_once
```

判定：`实际值 ≤ 上限 × (1 + percent/100) + amount` 才放行；超出按 `action` 处理。

### 27.5 业务逻辑（五条主时序）

#### S1 订单确认 → 计划生成（Wave B）

```
触发：sales_order.status → confirmed
前置：payment_term_id 非空；订单行金额已算定
动作：
  ① 建 payment_schedule（1:1），gross_amount = Σ 行含税额
  ② 按 payment_term_line 展开 payment_schedule_line
     - 每行落 planned_amount = gross × ratio
     - group_no 由订单行拆批决定（静态，不随发货新增组）
     - line_type: normal / prepayment / retention
  ③ group_status = planned
事件：PaymentScheduleCreated
异常：Σ planned ≠ gross → 断言失败，整单回滚
```

#### S2 发货过账 → 组激活

```
触发：shipment.status → posted
前置：shipment_line 数量 ≤ 订单行未发量 ×(1 + 过量容差)
动作：
  ① 回写 sales_order_line 已发量
  ② 对应 group_no 的 group_status: planned → activated
  ③ 重算 group_base_amount（该组实际发货基数）
事件：ScheduleGroupActivated
异常：组已 cancelled → 拒绝发货
```

#### S3 开票过账 → 应收发生

```
触发：customer_invoice.status → posted
前置：来源行合法（R1-2）；数量 ≤ 可开票量；价格在容差内（D13 受控改价）
动作：
  ① 写 customer_invoice + line（金额快照）
  ② 回写 sales_order_line 已开票量
  ③ 回写 sales_order_schedules(kind=billing) 状态
  ④ 生成 L2 会计事件（D6 待定）
事件：InvoicePosted
异常：超容差 → 按 B4 动作处理
```

#### S4 收款登记 → 核销

```
触发：payment_receipt.status → posted，且提交核销清单
前置校验（顺序不可换）：
  ① 幂等键校验（B5）→ 重复直接返回原单
  ② V7 资金侧可用 ≥ 本次核销合计
  ③ 逐目标校验 V2 / V3 / V7 目标侧可用
  ④ 组状态校验（ST 矩阵）
  ⑤ V4 预收抵扣归属校验
动作（同一事务）：
  ① INSERT payment_receipt
  ② INSERT payment_allocation × N
  ③ UPDATE 各目标余额缓存（V9：影响行数断言 = 1）
  ④ 更新计划行 settled_amount / 发票双列
  ⑤ 若全部结清 → 组状态 → closed
事件：ReceiptPosted、AllocationCreated
异常：任一步失败 → 全回滚，返回具体不变量编号
```

#### S5 预收抵扣 / 反核销

```
S5a 预收抵扣：
  触发：invoice.posted 且存在同订单 reserved
  动作：
    ① INSERT allocation(type=prepay_offset_invoice)
    ② 原 prepay_to_schedule 行：reserved 部分转 applied
    ③ 发票 prepaid_offset_amount += 金额
  约束：V4（同订单/组）+ V3（不超发票）

S5b 反核销：
  触发：手工反核销 / 收款红冲
  动作：
    ① 校验 V8（该行未被反冲过）
    ② INSERT allocation(status=reversed, reversal_of_allocation_id=原行, amount ≤ 原行)
    ③ 原行 status → reversed
    ④ 回退目标余额缓存
  约束：反向行金额 ≤ 原行金额（V5）；不允许修改原行金额
```

### 27.6 并发与幂等（SAP 教训的直接翻译）

#### 27.6.1 对照

| 机制 | SAP | 我方 | 为什么不同 |
|---|---|---|---|
| 加锁 | `EFBKPF`（表 `BKPF`，键 `BUKRS`+`BELNR`+`GJAHR`，mode E） | `BEGIN IMMEDIATE`（库级写锁） | SQLite 无行锁，库级锁更简单且足够（单机） |
| 冲突检测 | 更新任务内校验 → **`F1 805`（F1805）** 更新终止 + 回滚 | `rowcount` 断言 = 1，否则抛异常回滚 | SQLite 条件更新影响 0 行不报错，必须显式断言 |
| 已清标记 | `AUGDT` / `AUGBL` | `allocation.status = 'reversed'` | 我方用关系表状态，不迁表 |
| 余额来源 | `BSIK` 按 `SHKZG` 借贷汇总 | `Σ allocation(status=active)` | **同样不能读单行缓存** |
| 两阶段 | F110 proposal → run（有间隙，间隙内被清触发 F1805） | **不引入两阶段** | 我方单阶段提交，避免间隙 |

#### 27.6.2 关键认知（来自 SAP 复核）

> **部分收款不会改小原单金额。** SAP 的 partial payment 让原发票保持全额未清，付款另生成一笔未清项，两者靠 `REBZG` 关联。所以「查余额」永远不能读单行金额，必须按方向汇总。
> 我方对应：`settled_amount` / `receipt_settled_amount` 是**缓存**，真源永远是 `payment_allocation`；任何对账都必须能从核销行重算并比对缓存。

#### 27.6.3 幂等三键

| 键 | 作用域 | 用途 |
|---|---|---|
| `(bank_account_id, reference_no)` | 收款单 | 防同一笔银行流水重复导入 |
| `(source_batch_id, source_line_no)` | 收款单（导入批次） | 防批次重跑 |
| `idempotency_key` | 核销提交 | 防前端重复点击 / 网络重试 |

三个键都必须建**唯一索引**，冲突时返回原单而非报错（幂等语义）。

### 27.7 三层闸门与三余额模型

| 层 | 闸门 | 比较对象 | 我方落点 |
|---|---|---|---|
| L0 | 合同/协议累计额 | 累计应付+付款申请 vs 合同价税合计 | `sales_order.contract_limit_amount` + B4 |
| L1 | 订单行金额（含容差） | 开票/发货额 vs 订单行额 ×(1+容差) | S3 前置校验 + 容差三字段 |
| L2 | 已确认应收/应付 | 核销额 vs 发票 gross | V3 |
| L3 | 发票/期次 | 单票单期不超收 | V2 / V3 |

三余额（与 V7 对应，建议物化到 `order_settlement_summary` 供高频查询）：

```
① committed_available = order_total ×(1 + over_tolerance%) − 已下单/已开票额
② settle_available    = Σ posted 发票 gross − Σ active 现金核销
③ reserve_available   = 订单预收上限 − Σ active reserved
```

**并发写法**（V9 的具体实现）：

```sql
UPDATE payment_schedule_line
   SET settled_amount = settled_amount + :amt
 WHERE id = :line_id
   AND settled_amount + :amt <= planned_amount
   AND group_status = 'activated';
-- 断言 rowcount = 1，否则抛 InvariantViolation('V2')
```

> 不采用「先 SELECT 再判断再 UPDATE」，因为那会产生竞态。条件写进 `WHERE` 是唯一可靠做法。

### 27.8 实施波次影响

| 波次 | 对象 | 规则 | 说明 |
|---|---|---|---|
| **Wave A** | `customer_invoice` + line；`payment_receipt`（仅登记，不做计划核销）；`payment_allocation`（仅 `receipt_to_invoice` / `on_account`） | R1、V1、V3、V5、V7、V8、V9；B2、B5、B7 | 不建 `payment_schedule`（D3-a），收款只能核到发票 |
| **Wave B** | `payment_schedule` + line；`prepay_to_schedule` / `prepay_offset_invoice` | 加 V2、V4；B1、B3、B8 | 引入计划层与预收抵扣 |
| **Wave C** | 自动核销（对齐 SAP `F.13` + `TF123`）、贷项凭证、跨订单抵扣 | 加 B6、B9 放开 | 自动匹配规则参考「科目维度 + 最多 5 个用户准则字段」的结构 |

### 27.9 已知冲突与订正

| # | 冲突 | 处理 |
|---|---|---|
| 1 | §25.12 第 3 条「反核销 Wave A 整额」与 §25.6 V5「允许部分反核销」矛盾 | **以 V5 为准**，Wave A 即允许部分反核销；§25.12 该条作废 |
| 2 | §24.9「动态批次组是差异化」 | 已由 D12 推翻，见 §24.9 注 |
| 3 | §5「开票不改价」 | 已由 D13 推翻，改为受控改价 |
| 4 | §25.11 中 SAP 条目原标 A 级 | 本轮复核后降为 **B**（SAP Help 正文未取回），见 §26.9 |
| 5 | §25.9 视图口径未区分现金与预收 | 已由 D16 + V6 分离，视图需输出两列 |

### 27.10 本节结论（三句话）

1. **对象只有九个，层只有四层**（计划 / 事实 / 关系 / 视图），新增对象前必须过「边界判断三问」。
2. **规则只有四类，硬不变量只有九条**（V1–V9），其余都是可配业务规则；实现时先落 V 系列，再落 B 系列。
3. **并发只有一招**：余额条件写进 `WHERE` + 影响行数断言 + 失败回滚。这是 SAP「加锁 + 更新终止」在 SQLite 下的最小等价物，不需要更复杂。

### 27.11 待拍板（收敛）

| # | 问题 | 所在节 | 建议 | 阻塞什么 |
|---|---|---|---|---|
| 1 | D14 / D15 / D16 由「建议」转「已定」 | §13 | 采纳 | 收款单字段定稿 |
| 2 | §24.8 三项（尾款并入期 2 / 方案甲 / D3-a） | §24.8 | 采纳 | 计划表结构 |
| 3 | D6（L2 会计事件） | §13 | 一期只出事件、不建台账 | S3 的④ |
| 4 | D11（一期分次开票） | §13 | 允许 | 开票回写逻辑 |
| 5 | 超容差默认动作 | B4 | `block` | 校验行为 |
| 6 | 订单级余额用物化表还是视图 | §25.9 / §27.7 | **视图 + 缓存列**，不建独立物化表 | 性能方案 |

---

## 28. 跨层对齐：开票 / 应收 / 收付款三条链的整体校核（2026-11-09）

> 本节回答一个问题：**§3–§11 的开票模型、g15 的财务边界、§25 的收付款模型，三者能不能拼成一个闭环？**
> 结论：**不能直接拼，有 6 处断点，其中 1 处是硬冲突。** 逐条给证据与修复方案。

### 28.1 三条链的现状

| 链 | 核心对象 | 定义在哪 | 落地波次 | 完成度 |
|---|---|---|---|---|
| **开票链** | `customer_invoice` + line | §3–§10 | Wave A | 字段、状态机、规则 R-INV-0..20 齐全 |
| **应收链** | **无独立对象**，由 `customer_invoice` 代替 | §11（明确不建 AR 台账） | — | **缺位** |
| **收款链** | `payment_receipt` + `payment_allocation` | §25 | Wave A（部分）/ B | 字段齐全，但与开票链有冲突 |
| **计划链** | `payment_schedule` + line | §24 | Wave B | 字段齐全，Wave A 不建 |
| **财务出口** | L2 会计事件（hook） | §11 / g15 | Wave C | 未落地 |

### 28.2 六个断点

#### 断点 A（硬冲突）：发票头能不能放「已收金额」

| 项 | 内容 |
|---|---|
| 冲突双方 | §11 红线（L296）：「不在 `customer_invoice` 上放科目、成本、**已收金额**、账龄字段」<br>§25.13（L2846）：「`customer_invoice` 补 `receipt_settled_amount`、`prepaid_offset_amount`」 |
| 性质 | **直接矛盾**。评审时一定被问「到底能不能放」 |
| 影响 | 不放 → V3「已收+预收 ≤ 发票额」无法高效校验，每次核销都要全表扫 allocation；放 → 违反既定红线 |

**三个选项**：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A1 | **修订红线**：允许「核销累计列」，仍禁止科目/成本/账龄 | 简单、查询快；累计列是派生缓存不是第二套账 | 需要重新解释「红线」 |
| A2 | 两列挪到独立表 `invoice_settlement_status(invoice_id, settled, prepaid)` | 不动发票表 | 多一张一对一表，JOIN 成本更高 |
| A3 | 纯视图计算，不落列 | 最纯粹 | 每次核销都要聚合 allocation，量上来会慢 |

**建议 A1**。理由：这两列的性质与 §8 的 `billed_qty` / `billed_amount` 完全相同——都是「只读派生缓存，真源是关系表」。§11 红线真正要防的是「科目、成本、账龄」这类会计属性侵入业务单据，而不是核销进度。建议把红线原文改成：

> 不在 `customer_invoice` 上放科目、成本、账龄字段；**允许存放核销进度缓存列（`receipt_settled_amount` / `prepaid_offset_amount`），但必须满足：① 只读；② 可由 `payment_allocation` 全量重算；③ 巡检能比对出差异**。

#### 断点 B（悬空引用）：`contract_limit_amount` 从未定义

| 项 | 内容 |
|---|---|
| 现象 | §27.4 V7 与 §27.7 L0 闸门都引用了 `sales_order.contract_limit_amount` |
| 证据 | 全文检索该字段，除 §27 两处引用外**没有任何字段定义**；`sales_order.yaml` 现有字段也没有 |
| 影响 | V7 的 order/group 分支无法实现；L0 闸门无落点 |

**三个选项**：

| 方案 | 做法 | 适用 |
|---|---|---|
| B1 | `sales_order` 头新增 `contract_limit_amount` / `contract_limit_percent` | 订单即合同口径（我方多数场景） |
| B2 | 新建独立 `sales_contract` 对象，订单挂合同 | 一合同多订单 |
| B3 | Wave A 不落字段，用 `sales_order.gross_amount ×(1+容差)` 代替 | 最小改动 |

**建议 B3 + B1**：Wave A 用 B3（订单额即上限），Wave C 若出现「一合同多订单」再引入 B2。**不要**在 Wave A 造合同对象——目前没有合同主数据。

#### 断点 C（对象缺位）：应收没有独立载体

| 项 | 内容 |
|---|---|
| 现象 | g15 与 §11 都明确「不做 AR 台账」，但 §25 的核销目标写的是「发票」 |
| 后果 1 | **预收无载体**：开票前没有应收，`reserved_amount` 只能挂在 order/group 上（§25.7 方案 C 已处理，但语义上是"绕过应收"） |
| 后果 2 | **发票 ≠ 应收**：发票红冲后应收消失，但真实业务中可能仍有收款待退；红字单与蓝字单的应收净额没有独立对象表达 |
| 后果 3 | **暂估缺失**：已发货未开票的部分（`billed_qty < shipped_qty`）在财务上是应收，但系统里完全看不到 |

**三个选项**：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| C1 | **发票即应收**，只建视图 `v_receivable`（= posted 发票 − 已核销） | 零新表，符合 g15 | 无法表达暂估；红冲后退款场景靠人工 |
| C2 | 建轻量 `receivable_item`（发票过账生成、红冲反向） | 语义纯正，可挂暂估 | 与发票高度重复，等于建了 AR 台账，违反 g15 |
| C3 | 只建 `v_receivable` + `v_unbilled_receivable`（暂估视图） | 覆盖暂估，仍不落表 | 视图复杂度上升 |

**建议 C3**。两个视图即可，不建表：

```
v_receivable            = posted 发票 gross − Σ active 现金核销 − Σ active 预收抵扣
v_unbilled_receivable   = Σ(shipment_line.qty − billed_qty) × 订单行单价（仅 delivery 行）
```

这样「应收」是一个**口径**而不是一个**对象**，与 g15「L3 是投影」的原则一致。

#### 断点 D（越界）：`payment_receipt` 触碰 g15「资金/银行/支付不建」红线

| 项 | 内容 |
|---|---|
| 现象 | §25.3 的 `payment_receipt` 含 `bank_account_id` / `payment_method_id` / `reference_no` |
| g15 原文 | §3.1：「资金 / 银行 / 支付」列为**不建** |
| 辨析 | g15 要防的是「支付执行通道」（发起付款、对接银企直连、回单解析），不是「到账事实登记」 |
| 影响 | 若按字面执行，收款单不能有任何银行字段，模型退化成「记一笔金额」，无法对账 |

**建议**：修订 g15 表述，区分两个概念：

| 概念 | 归属 | 我方是否做 |
|---|---|---|
| **支付执行**（发起付款指令、银企直连、回单自动解析） | 外部 | 不做 |
| **到账登记**（人工/导入登记一笔钱到了哪个账户） | 平台 | **做** |

即：`payment_receipt` 保留银行字段，但**不建** `payment_instruction` / `bank_connection` / `bank_statement_import` 这类执行侧对象。

#### 断点 E（不对称）：采购侧没有对应的发票与付款对象

| 项 | 内容 |
|---|---|
| 现象 | `spec-purchase-order-object-model-2026-11-01.md` §0 明写「发票仍待立」；采购侧无 `vendor_payment` / 预付款对象 |
| 影响 1 | §25 的 `payment_receipt` 若只在销售侧用，采购侧要重做一遍，两套逻辑会漂移 |
| 影响 2 | 采购侧「三单匹配 → 应付 → 付款」是更刚需的场景，却比销售侧落后 |
| 影响 3 | §26 研究的 SAP 机制（`MIRO` / `F110` / `ZLSPR`）全部是采购侧，研究成果没有落点 |

**两个选项**：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| E1 | `payment_receipt` 改为**收付款通用对象**，加 `direction ∈ {inbound, outbound}` | 一套模型两侧复用；核销逻辑同构 | 字段要兼容两侧（往来方、账户类型） |
| E2 | 销售 `payment_receipt` / 采购 `vendor_payment` 两张表 | 语义清晰 | 两套代码，长期漂移 |

**建议 E1**。理由：收付款的机制（余额封顶、核销、反核销、幂等）在两侧完全同构，差异只在「往来方是谁」和「方向」。用 `direction` + `party_account_id` 即可统一。

对应调整：

```
payment_receipt:
  direction            enum(inbound, outbound)   ← 新增
  party_account_id     integer                   ← 统一取代 customer_account_id / vendor_account_id
  counterparty_type    enum(customer, vendor)    ← 配合 party_account_id
```

> 若采用 E1，§25.3 的 `customer_account_id` / `payer_account_id` 需合并为 `party_account_id` + `counterparty_type`。这是**对 §25 的实质修订**，需要拍板。

#### 断点 F（波次错配）：V7 的三个 target 跨了两个波次

| 项 | 内容 |
|---|---|
| 现象 | V7 写了三种 target（`schedule_line` / `invoice` / `order,group`），但 `payment_schedule` 是 **Wave B** |
| 影响 | Wave A 实现 V7 时，`schedule_line` 分支不存在，`order/group` 也依赖 B1 的合同额字段 |
| 修复 | Wave A 的 V7 **降级为两分支**：`invoice` + `customer_account`；Wave B 再补 `schedule_line` / `order/group` |

建议在 §27.4.2 的 V7 下补一行波次注记。

### 28.3 修复后的整体对象地图

```
【开票链】                        【应收链（视图，不落表）】
sales_order_line                      v_receivable
  └ customer_invoice ──line ──────────┘（posted 发票 − 核销）
       │                              v_unbilled_receivable
       │                                （已发货未开票，暂估）
       │
【收付款链】                          【计划链（Wave B）】
payment_receipt（direction）           payment_schedule
  └ payment_allocation ────────────────└ payment_schedule_line
       ├ receipt_to_invoice
       ├ prepay_offset_invoice
       ├ prepay_to_schedule
       └ on_account

【财务出口】
accounting_event(hook) → 外部总账
```

**关键变化**（相对 §27 的地图）：

| 变化 | 原因 |
|---|---|
| 新增 `v_receivable` / `v_unbilled_receivable` 两个视图 | 断点 C |
| `payment_receipt` 加 `direction` / `party_account_id` | 断点 E |
| `contract_limit_amount` 降级为 Wave C | 断点 B |
| 发票头明确允许两列核销缓存 | 断点 A |

### 28.4 规则冲突矩阵

| 规则/字段 | 出处 | 与谁冲突 | 处理 |
|---|---|---|---|
| 「不放已收金额」红线 | §11 L296 | D16 / §25.13 | **修订红线**（方案 A1） |
| `contract_limit_amount` | §27.4 / §27.7 | 全文无定义 | **Wave C 再引入**（方案 B3） |
| `customer_account_id` / `payer_account_id` | §25.3 | 断点 E 的统一方向 | **合并为 `party_account_id`**（需拍板） |
| 不建 AR 台账 | §11 L296 / g15 §3.1 | §25 需要应收余额 | **建视图不建表**（方案 C3） |
| 不建资金/银行/支付 | g15 §3.1 | `payment_receipt` 有银行字段 | **修订 g15 表述**（方案 D） |
| R-INV-10「整单红冲」 | §6 | Wave C 行级部分冲销 | 已在 §13 D8 说明分期 |

### 28.5 对 §13 决策记录的补充建议（D17–D20）

| # | 问题 | 建议 | 候选 | 状态 |
|---|---|---|---|---|
| **D17** | 发票头能否放核销累计列 | **允许**，但限定「只读 + 可重算 + 可巡检」，修订 §11 红线 | 完全禁止（挪独立表） | ⏳ 建议 |
| **D18** | 应收用什么承载 | **视图即应收**（`v_receivable` + `v_unbilled_receivable`），不建 `receivable_item` | 轻量 `receivable_item` 表 | ⏳ 建议 |
| **D19** | 收付款对象是否统一 | **统一**：`payment_receipt` 加 `direction`，`party_account_id` 取代客户/供应商双字段 | 销售/采购两张表 | ⏳ 建议 |
| **D20** | 合同额上限怎么落 | Wave A 用订单总额 ×(1+容差)，Wave C 再建 `contract_limit_amount` | Wave A 即建独立合同对象 | ⏳ 建议 |

### 28.6 三条链的完整性检查清单（评审用）

| # | 检查项 | 当前是否通过 | 阻塞点 |
|---|---|---|---|
| 1 | 每个事实单据都有唯一写入口 | 是 | — |
| 2 | 每个累计字段都能从关系表重算 | 是（V6 / V9） | — |
| 3 | 开票 → 应收的口径闭合 | **否** | 断点 C |
| 4 | 应收 → 核销的口径闭合 | 部分 | 断点 A（无缓存则低效） |
| 5 | 预收 → 应收的转换闭合 | 是（方案 C，V4） | — |
| 6 | 销售侧 ↔ 采购侧同构 | **否** | 断点 E |
| 7 | 财务边界（g15）无越界 | **否** | 断点 D |
| 8 | 所有引用字段都已定义 | **否** | 断点 B |
| 9 | 每个不变量都有明确波次 | **否** | 断点 F |
| 10 | 红冲/反核销路径闭环 | 是 | — |

**结论**：10 项中 6 项通过、1 项部分、3 项不通过。**断点 A / C / E 必须在评审前解决**，B / D / F 可以带条件通过。

### 28.7 本节小结

1. 三条链**不是同一天设计的**：开票链（§3–§10）早于财务边界（g15）早于收付款模型（§25）。所以出现「红线禁止已收金额」与「收款模型要求已收金额」并存，是时序造成的，不是谁写错了。
2. **修复原则只有一条**：能算出来的，不要存；必须存的，必须能重算。按这条原则，A1（允许缓存列）、C3（视图即应收）、D（区分执行与登记）都是自然结论。
3. **D19 影响面最大**：把 `payment_receipt` 改成收付款通用对象，会改动 §25.3 的字段表。这是本轮唯一一处「改已有定义」而不只是「补新定义」的建议，建议优先拍板。