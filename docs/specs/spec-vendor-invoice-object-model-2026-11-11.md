# 采购发票对象模型 Spec（Vendor Invoice Object Model）

> 版本：v1.0 草案 ｜ 日期：2026-11-11 ｜ 状态：待评审
> 上游契约：[spec-receipt-object-model-2026-11-01.md](./spec-receipt-object-model-2026-11-01.md) §10 / §11
> 样板：[sales-invoice-pricing-spec-2026-11-10.md](./sales-invoice-pricing-spec-2026-11-10.md)（FR/NFR/IF/TR 编号体系）
> 平台基线：`document_category / document_role / direction`（v243）、`doc_flow_rule`（v215）、`control_parameter_def`（容差）
> 证据等级：`C` = 代码已核实；`S` = SAP 对标；`F` = Oracle Fusion 对标；`D` = 本 Spec 决策

---

## 0. 结论先行

### 0.1 一句话结论

采购发票**不是新机制**，而是把销售发票已跑通的「单据骨架 + doc_flow 边 + 容差配置 + 声明式逆向」在采购侧做**一次对位复用**：新增 `vendor_invoice` 头 / `vendor_invoice_line` 行两张事实表，**零新增枚举物理列、零新增容差配置表、零物理缓存量列**，已开票量一律由 `doc_flow_edges` 视图推导。

### 0.2 对标采纳 / 不采纳

| # | 结论 | 采纳自 | 本 Spec 落点 | 证据 |
|---|---|---|---|---|
| A1 | 发票类型**不新建** `invoice_type` 字段，复用平台 `document_category` + `document_type.document_role` + `direction` | 平台 v243 + Fusion invoice types + SAP MIRO 四类 | §3.2 | C/F/S |
| A2 | 标准发票 / 贷项凭证 / 借项通知单 / 取消单据 = `document_category` 四值 | Fusion `AP_INVOICES_ALL.INVOICE_TYPE_LOOKUP_CODE`；SAP Credit Memo / Subsequent Debit | §3.2 | F/S |
| A3 | 匹配锚点 = **PO 计划行聚合**，发票行不直接持收货行 | Fusion `PO_LINE_LOCATIONS_ALL.quantity_billed` | §5.1 | F |
| A4 | 收货「不带 PO 单价」，发票价格比对 PO 单价快照 | 双向一致（Fusion 收货不含价 / SAP MSEG 不含价） | 维持 D-RC-9，不改 receipt_line | F/S |
| A5 | 已开票量**不落列**，由 doc_flow 边 + 视图推导（等价 SAP `EKBE` 采购历史） | SAP EKBE / Fusion quantity_billed | §11.2 | C/S |
| A6 | 匹配模式 `po_based / gr_based`，**分层解析**（组织 → 单据类型 → 行类型 → 物料组），对齐 SAP `EKPO-WEBRE` 且兼容 D365 / NetSuite 的多层覆盖 | SAP GR-based IV；D365 matching policy hierarchy；NetSuite 物料级 `Match Bill to Receipt` | §5.1 | S/F/N |
| A7 | 容差复用 `control_parameter_def`（已内置 `tolerance_direction / tolerance_basis`），不建新表 | SAP OMR6（PP/DQ/BD/BR/AN/AP）；Fusion tolerance | §5.3 | C/S/F |
| A8 | 数量容差**单向**（发票量 > 收货量才拦），对齐 SAP `DQ` | SAP OMR6 `DQ` 单向 | §5.3 | S |
| A9 | 状态机 `draft/submitted/posted/cancelled/reversed` + `match_status` 子状态；不引入 Park/Blocked 独立状态 | 平台 v236 骨架 + SAP Park/Blocked 折叠为子状态 | §6 | C/S |
| A10 | 退货 = **物流层 + 财务层两层配对**：`RETURN_PO + VENDOR_RETURN`（物流）+ 贷项发票（财务） | SAP Return PO + 122/161 + Credit Memo | §9 | S |
| A11 | 服务采购以 `schedule_kind='service'` 的计划行为锚，`gr_based` 下发票行 1:1 挂服务确认行 | SAP SES（服务录入单） | §10 | S |
| A12 | 自动结算预留 `settlement_mode ∈ {supplier_invoice, ers}`，本波只做 `supplier_invoice` | SAP ERS | §10.2 | S |

**不采纳（含理由）**

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N1 | 新建 `invoice_type` 枚举字段（Standard/Credit/Debit/Prepayment） | Fusion | 平台已有 `document_category + document_role + direction` 三元组，新增即并行机制（违反 NFR-001） |
| N2 | 新建发票-收货多对多匹配表 `invoice_line_match` | Fusion 分布表思路 | Fusion 实际锚点是计划行聚合；建匹配表会把可推导关系固化为物理事实（违反单一事实源） |
| N3 | `purchase_order_schedule.invoiced_qty` 缓存列 | 直觉设计 | 与 doc_flow 边冲突；SAP 用 EKBE 历史推导，我们已有 `v_doc_flow_consumed_qty` |
| N4 | `receipt_line` 补单价 / 金额快照 | 上轮曾提议 | Fusion/SAP 双侧证明收货不落价，撤回 |
| N5 | Prepayment 作为独立单据对象 | Fusion | 付款域对象（`payment_request` / `prepayment`）属付款波次，不在发票对象内；见 TBD-3 |
| N6 | 独立 `match_status` 物理枚举表 | — | 与 `status` 同表不同生命期，落 `vendor_invoices.match_status` 列即可（非枚举表） |
| N7 | 供应商级容差（`control_parameter_value.supplier_id`） | SAP LFM1 容差 | 当前维度无 supplier，扩展维度需全平台评审 → TBD-2 |

### 0.3 Decision Log

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| D-VI-1 | 头行两表 `vendor_invoices` / `vendor_invoice_lines` | 单表 + JSON 行 | 与 `customer_invoice` 对称；行需独立 doc_flow 目标 |
| D-VI-2 | 复用 `document_category`，seed 四类标的 `document_role` | 新建 invoice_type | 见 N1 |
| D-VI-3 | 匹配锚点 = `schedule_id`（计划行），`receipt_line_id` 仅作 trace | 锚点 = receipt_line | 见 A3；且兼容「先开票后收货」 |
| D-VI-4 | 已开票量走 doc_flow 推导 | 缓存列 | 见 N3 |
| D-VI-5 | 容差走 `control_parameter_def` | 新建 `invoice_tolerance` 表 | 见 A7 |
| D-VI-6 | 匹配模式可配（**已被 D-VI-9 细化**：配置参数多级解析，非类型硬列） | 全局开关 / 类型硬列 | SAP 按 PO 行 `WEBRE` 决定 ⇒ 需多层；D365/NetSuite 进一步证实 |
| D-VI-7 | 过账 = 仅状态 + 边 + 投影，**不产生 GL 凭证** | 生成会计凭证 | 本平台无 GL 域（§1 边界） |
| D-VI-8 | 红冲 = 新建红字发票（`reversal_of_invoice_id`），不原地改数 | 原地反向 | 与 `customer_invoice` 一致 |
| D-VI-9 | 匹配模式做成 `control_parameter_def` 枚举参数多级解析，**不给 `type_definitions` 加列** | 类型级硬列 / 全局常量 | D365 层级覆盖 + NetSuite 物料级 + Infor 全局设置（§18） |
| D-VI-10 | `billing` 与 `ap_match` **分池**，即「历史事实的记录类别判别符」 | 单池按 rule_id 过滤 | SAP `EKBE` 同一历史表内按记录类别（GR / IR / return / subsequent debit）区分（§18） |
| D-VI-11 | 退货与贷项为**软配对**（不强制），改用派生视图暴露敞口 | 强制「有退货单必开贷项」 | D365/SAP 均允许独立贷项（价格调整）；强制会阻断合法业务（§18） |
| D-VI-12 | 匹配规则**参数化**（一条 `vi_match_mode` + 未来可选匹配方案），**不建匹配单据** | 独立匹配单据 + 审批流 + 匹配工作台 | 本平台无匹配审批场景；金蝶把匹配做成带审批流的单据，是为承载审批与额度占用（§19） |
| D-VI-13 | 红字发票（`direction=-1`）**单独参与匹配**，不与蓝字同批净额；红冲蓝票时 `reversal_of_invoice_id` 必填 | 红蓝同批按净额匹配 | 金蝶 `对应蓝票` + 「红票非蓝票红冲时须单独发起匹配，不允许红蓝一起匹配」（§19） |
| D-VI-14 | 已匹配额**维持视图派生**，不反写源单额度；并发以事务 + `uq_doc_flow_idem` 兜底 | 源单头/行额度反写（占用 / 释放） | 反写即物理缓存（违反单一事实源，见 N3）；金蝶反写是为支持部分匹配占用与锁（§19） |
| D-VI-15 | 重复发票**硬拦**，查重键 = 供应商 + 规范化发票号（**不含金额**）；override 需专用权限 + 留痕 | 软校验可 override | Fusion / D365 均默认硬拦；软校验在应付侧是重复付款风险（§20.1 TBD-8） |
| D-VI-16 | 质检折抵按 `rejection_disposition`：`concession` / `rework` **仍可开票**，仅 `return_to_supplier` / `scrap` 折减 | 直接扣 `qty_rejected` 整量 | 旧口径会导致让步接收 / 返工被少开票（§20.1 TBD-7） |
| D-VI-17 | 付款冻结**不预埋字段**（删除 `payment_block`），延后付款波次以独立对象实现 | 头表留单值枚举字段 | 无码表即幽灵枚举（§11.5）；SAP `T008` / Fusion `AP_HOLDS_ALL` 均为独立对象（§20.1 TBD-3） |
| D-VI-18 | 行级多币种**永久关闭**，行币种必须为空或等于头币种 | 行币种 + 行汇率快照 | 6/6 家头部 ERP 均头级币种（§20.1 TBD-6） |
| D-VI-19 | 匹配提交统一以 **`BEGIN IMMEDIATE`** 开启事务，事务内重算剩余量 | 应用层锁 / 行级悲观锁 | SQLite 单写者，应用层锁只增死锁风险（§20.1 TBD-13） |
| D-VI-20 | **不建匹配方案对象**；参数维度扩展用 **0 哨兵值** + 新 `specificity_rank` 序 | 新建 `match_profile` 基础资料 | 金蝶方案对象是为审批流与单据级切换服务，本平台无此场景（§20.1 TBD-12 / TBD-2） |

---

## 1. 定位与边界

### 1.1 定位

`vendor_invoice` 是**采购侧的应付事实单据**：记录「供应商就某批采购承诺/收货向我方索取的金额」，是 PO → 收货 → 发票三单匹配的终点，也是付款波次的起点。

链条位置：

```
purchase_order
  └─ purchase_order_line
       └─ purchase_order_schedule        ← 匹配锚点（A3）
            ├─ receipt_line              ← 实物流水（qty，无价）
            └─ vendor_invoice_line       ← 财务流水（qty + price）★ 本 Spec
                 └─ vendor_invoice        ← 头
```

### 1.2 边界（明确不做）

| 不做 | 归属 | 理由 |
|---|---|---|
| GL 凭证 / 会计分录 / GR-IR 科目 | 会计域（未建） | 本平台无 GL 对象；`posted` 只表达业务已确认 |
| 付款 / 付款申请 / 预付冲销 | 付款波次（TBD-3） | 付款是独立事实（`payment_request`），发票只提供应付依据 |
| 供应商主数据 / 容差供应商级配置 | TBD-2 | `control_parameter_value` 无 supplier 维度 |
| 采购订单变更 / 价格修订联动 | PO Spec | 发票只对位当期快照，PO 变更走既有 PO 流程 |
| 税额计算引擎 / 税码推导 | 税务域 | 本波税额由行上 `tax_amount` 直录（TBD-4） |
| 三单匹配 UI 的差异工作台（差异池/批量处理） | 后续波次 | 本波只做行级 `match_status` + 例外原因落 `match_exception_reason` |

### 1.3 非目标

- 不重构 `customer_invoice`；仅**引用**其骨架作为对位模板。
- 不改 `receipt` / `purchase_order` 既有字段语义（除 §12.3 列出的新增可选列）。
- 不引入任何 `pytest` 之外的测试通道。

---

## 2. 与销售发票统一骨架对照

> 目的：证明采购发票是 **同一骨架的第二实例**，不是第二套机制。凡下表「复用」项，采购侧**不得**另造字段。

| # | 骨架元素 | 销售侧（`customer_invoice`，C） | 采购侧（`vendor_invoice`，本 Spec） | 处置 |
|---|---|---|---|---|
| M1 | 业务编号 | `invoice_no` + `numbering` + `type_definitions` | `invoice_no` + `numbering` | 复用 |
| M2 | 单据类型 | `document_type_id`（`scope_bo=customer_invoice`） | `document_type_id`（`scope_bo=vendor_invoice`） | 复用 |
| M3 | 单据类别 | `document_category ∈ {invoice, credit_memo, debit_memo, cancellation}` | 同四值 | 复用（A1/A2） |
| M4 | 方向 | `direction ∈ {1, -1}` | 同 | 复用 |
| M5 | 状态 | `draft / submitted / posted / cancelled / reversed` | 同 | 复用 |
| M6 | 行来源策略 | YAML `line_source_policy` | YAML `line_source_policy` | 复用（§4.3） |
| M7 | 行金额符号 | `direction × 行金额` | 同 | 复用 |
| M8 | 过账副作用 | `doc_effect.posting/faces/projections/reversal` | 同结构，边与投影不同 | 复用机制 |
| M9 | 红冲 | `reversal_of_invoice_id` + `customer_invoice_red_letter` | 同字段 + `vendor_invoice_red_letter` | 复用机制 |
| M10 | 舍入 | `rounding_diff` + `round_amount`（精度取 `currencies.decimal_places`） | 同 | 复用 |
| M11 | 定价模式 | `billing_pricing_mode` / `pricing_date` | `match_pricing_mode ∈ {po_price, receipt_price, manual}` | **不同名**（见 §5.4 理由） |

### 2.1 M11 为什么不能照抄 `billing_pricing_mode`

销售侧定价模式描述「价格从哪张价格单取」；采购侧价格来源是 **PO 快照**，业务问题是「是否允许偏离 PO 价、偏离多少由谁批」，本质是**匹配校验**而非定价。因此拆成两个正交字段：

- `match_pricing_mode`：价格取自何处（`po_price` / `receipt_price` / `manual`）
- `match_status` + `match_exception_reason`：是否通过校验

> 若强行复用 `billing_pricing_mode`，会把「校验结果」混进「定价来源」，属语义污染（D-VI-6 的反对案）。

---

## 3. `vendor_invoice`（头）

### 3.1 表与语义

| 项 | 值 |
|---|---|
| 对象 id | `vendor_invoice` |
| 表名 | `vendor_invoices` |
| 中文名 | 采购发票 |
| `aspects` | `[audit_aspect, document_type_aspect]` |
| `org_scope` | `direct` / 字段 `org_id` / `function: accounting` / `write_check: true` |
| `deletion_policy` | `restrict`，仅 `draft` 可删，级联 `vendor_invoice_lines` |
| `display_name_field` | `invoice_no` |
| `numbering` | `no_field: invoice_no`，`date_field: invoice_date`，`type_table: type_definitions` |

### 3.2 类型种子（`type_definitions`，`scope_bo=vendor_invoice`, `level=header`）

复用 v243 的 `document_role / direction / reversal_type_id / is_default` 四列，**不新增枚举**。

| code | 名称 | `document_category` | `document_role` | `direction` | `is_default` | 序列 |
|---|---|---|---|---|---|---|
| `VENDOR_INVOICE` | 采购发票 | `invoice` | `invoice` | `1` | `1` | `VI` |
| `VENDOR_CREDIT_MEMO` | 采购贷项凭证 | `credit_memo` | `credit_memo` | `-1` | `0` | `VCM` |
| `VENDOR_DEBIT_MEMO` | 采购借项通知单 | `debit_memo` | `debit_memo` | `1` | `0` | `VDM` |
| `VENDOR_INVOICE_CANCEL` | 采购发票取消单 | `cancellation` | `cancellation` | `-1` | `0` | `VIC` |

约束（复用 v243）：

- 唯一索引 `uq_type_default_role (scope_bo, level, document_role) WHERE is_default = 1` ⇒ 每 role 仅一个默认类型（C）。
- `reversal_type_id` 回指（TBD-5 已裁决）：`VENDOR_INVOICE → VENDOR_CREDIT_MEMO`、`VENDOR_CREDIT_MEMO → VENDOR_DEBIT_MEMO`、`VENDOR_DEBIT_MEMO → VENDOR_CREDIT_MEMO`、`VENDOR_INVOICE_CANCEL → VENDOR_INVOICE`；强不变量 = **反转类型 `direction` 必须与原类型相反**，默认发票类型该字段为空。
- `document_category / direction` **由类型派生**，字段 `semantics.immutable: true`，UI `editable: false`。

### 3.3 头字段表

> 类型标注沿用 YAML 的 `type`（`integer / string / date / number / text`）。`C` 列 = 与 `customer_invoice` 是否同构。

| 字段 | 类型 | 必填 | 说明 | 同构 |
|---|---|---|---|---|
| `id` | integer | 是 | 技术主键 | 同 |
| `invoice_no` | string(30) | 是 | 供应商发票号或内部号（编号序列取号）；`immutable`（R-VI-1） | 同 |
| `document_type_id` | integer | 是 | 单据类型（`scope_bo=vendor_invoice`） | 同 |
| `document_category` | string(20) | 是 | 由类型派生，`immutable` | 同 |
| `direction` | integer | 是 | 1 / -1，由类型派生，`immutable` | 同 |
| `invoice_date` | date | 是 | 供应商发票日期（编号日期段基准） | 同 |
| `received_date` | date | 否 | 我方收到日期（匹配基准日，SAP `RBKP-BLDAT` 对标） | 新增 |
| `posting_date` | date | 否 | 过账日期，空则取 `invoice_date` | 同 |
| `status` | string(20) | 是 | `draft/submitted/posted/cancelled/reversed` | 同 |
| `match_status` | string(20) | 是 | `unmatched / matched / exception / overridden`（§6.2） | 新增 |
| `match_mode` | string(20) | 是 | 冗余自类型配置的 `po_based / gr_based`，仅供查询与快照（§5.1） | 新增 |
| `supplier_account_id` | integer | 是 | 供应商（`vendor_account.id`，创建时快照） | 对称 `customer_account_id` |
| `supplier_party_id` | integer | 是 | 供应商主体（`party.id`，用于跨法人查询） | 对称 `party` |
| `supplier_site_text` | string(512) | 否 | 供应商开票地址快照 | 对称 `bill_to_address_text` |
| `supplier_tax_no` | string(64) | 否 | 供应商税号快照 | 对称 `tax_registration_no` |
| `currency_id` | integer | 是 | 币种，必须等于来源 PO 币种（R-VI-8） | 同 |
| `exchange_rate` | number(8) | 否 | 汇率快照 | 同 |
| `exchange_rate_type` | string(20) | 否 | 汇率类型快照 | 同 |
| `exchange_rate_date` | date | 否 | 汇率日期快照 | 同 |
| `purchase_org_id` | integer | 否 | 采购组织（来源 PO 快照） | 新增（采购域） |
| `org_id` | integer | 是 | 业务组织（`org_scope=direct` 的承载列，`function: accounting` / `write_check: true`，见 §3.1） | 同 |
| `supplier_invoice_no` | string(60) | 否 | **供应商方**发票号（外部业务键，用于重复发票检查） | 新增 |
| `net_amount` | number | 是 | 不含税金额合计（系统算，R-VI-7） | 同 |
| `tax_amount` | number | 是 | 税额合计 | 同 |
| `gross_amount` | number | 是 | 价税合计 | 同 |
| `rounding_diff` | number | 否 | 舍入差（`round_amount` 口径） | 同 |
| `match_pricing_mode` | string(20) | 是 | `po_price / receipt_price / manual`（§5.4） | 新增 |
| `match_exception_reason` | string(200) | 否 | 例外原因码：`price_over_tolerance / qty_over_receipt / qty_over_order / no_receipt / currency_mismatch / supplier_mismatch` | 新增 |
| `match_matched_at` | datetime | 否 | 匹配通过时间（审计用） | 新增 |
| `match_matched_by` | string(200) | 否 | 匹配通过人 | 新增 |
| `settlement_mode` | string(20) | 是 | `supplier_invoice / ers`，默认 `supplier_invoice`（§10.2） | 新增 |
| `reversal_of_invoice_id` | integer | 否 | 红冲来源发票 id（R-VI-9） | 同 |
| `remark` | text | 否 | 备注 | 同 |
| `created_at / updated_at / created_by / updated_by` | — | 审计 | `audit_aspect` 自动 | 同 |

**不建的头字段（显式否定）**：

| 不建 | 理由 |
|---|---|
| `total_invoiced_qty` | 可推导（Σ 行 `qty`），缓存列违反单一事实源 |
| `paid_amount` / `payment_status` | 付款域事实，不属发票对象 |
| `gl_voucher_no` | 无 GL 域（§1.2） |
| `invoice_type` | 见 N1 |
| `hold_flags` | SAP 多 hold 需独立表；本波用 `match_status=exception` 表达即可；付款冻结（payment block）归付款波次对象，发票头**不预埋**（TBD-3 已裁决） |

---

## 4. `vendor_invoice_line`（行）

### 4.1 表与语义

| 项 | 值 |
|---|---|
| 对象 id | `vendor_invoice_line` |
| 表名 | `vendor_invoice_lines` |
| 父对象 | `vendor_invoice`（`invoice_id`，1:N，`child_sections`） |
| `deletion_policy` | `restrict`，父 `draft` 时随父级联删除 |

### 4.2 行字段表

| 字段 | 类型 | 必填 | 说明 | 同构 |
|---|---|---|---|---|
| `id` | integer | 是 | 主键 | 同 |
| `invoice_id` | integer | 是 | 父头 | 同 |
| `line_no` | integer | 是 | 行号（头内唯一） | 同 |
| `schedule_id` | integer | 否 | **匹配锚点**：`purchase_order_schedule.id`（R-VI-2） | 新增 |
| `order_line_id` | integer | 否 | PO 行（随 `schedule_id` 快照，只读） | 新增 |
| `receipt_line_id` | integer | 否 | 收货行 trace（`gr_based` 下必填；`po_based` 可空） | 新增 |
| `invoice_line_id` | integer | 否 | 被核销的原发票行（`credit_memo / debit_memo / cancellation` 用，R-VI-2） | 新增 |
| `return_line_id` | integer | 否 | 退货收货行（`VENDOR_RETURN` 的收货行，§9.3） | 新增 |
| `item_id` | integer | 否 | 物料（随锚点快照；服务采购可空） | 新增 |
| `item_group_id` | integer | 否 | 物料组快照（容差解析维度之一） | 新增 |
| `line_type_id` | integer | 否 | 行类型（容差解析维度之一） | 同 |
| `description` | string(500) | 否 | 行描述 | 同 |
| `qty` | number | 是 | 开票数量（按 `uom_id`） | 同 |
| `uom_id` | integer | 否 | 单位 | 同 |
| `unit_price` | number | 是 | 单价（含税口径见 `price_includes_tax`） | 同 |
| `price_includes_tax` | integer(0/1) | 是 | 单价是否含税（默认 0） | 同 |
| `net_amount` | number | 是 | 行不含税金额（`round_amount` 口径） | 同 |
| `tax_amount` | number | 是 | 行税额（本波直录，TBD-4） | 同 |
| `gross_amount` | number | 是 | 行价税合计 | 同 |
| `po_unit_price` | number | 否 | **PO 单价快照**（匹配基准，不可变，A4） | 新增 |
| `price_diff_amount` | number | 否 | 价格差异额（`(unit_price - po_unit_price) × qty`，系统算） | 新增 |
| `price_diff_percent` | number | 否 | 价格差异百分比（容差判定用，系统算） | 新增 |
| `qty_over_receipt` | number | 否 | 超收量（`qty - 已净收量`，系统算；≤0 时置 0） | 新增 |
| `match_status` | string(20) | 是 | 行级匹配结果，聚合到头的判定依据 | 新增 |
| `match_exception_reason` | string(200) | 否 | 行级例外原因 | 新增 |
| `override_reason` | string(200) | 否 | 例外放行原因（`match_status=overridden` 时必填） | 新增 |
| `overridden_by` | string(200) | 否 | 放行人 | 新增 |
| `overridden_at` | datetime | 否 | 放行时间 | 新增 |
| `tax_code_id` | integer | 否 | 税码（TBD-4） | 新增 |
| `currency_id` | integer | 否 | 行币种：必须为空或等于头币种（多币种行**不采纳**，TBD-6 永久关闭） | 对称 |
| `created_at / updated_at` | — | 审计 | — | 同 |

**为什么行上要有 `po_unit_price` 快照**：价格校验必须对位「开票当时 PO 的价」，而 PO 价可能在其后被改。这不是缓存（R-VI-7 的派生量），而是一次**不可变事实快照**——与销售侧 `customer_invoice_lines.price_source / price_trace`（v244）同性质（C）。

### 4.3 `line_source_policy`（YAML 声明式，M6）

```yaml
line_source_policy:
  invoice:      [purchase_order_schedule, receipt_line, manual]
  credit_memo:  [invoice_line, return_line, manual]
  debit_memo:   [invoice_line, manual]
  cancellation: [invoice_line]
```

服务层不变量（YAML 表达不了的，由 `vendor_invoice_service` 强制）：

- **R-VI-2 行来源互斥**：`schedule_id` / `receipt_line_id` / 全空（manual）三选一；`credit_memo` 必须带 `invoice_line_id` 或 `return_line_id`。
- **R-VI-3 锚点一致性**：有 `schedule_id` 时，`order_line_id / item_id / uom_id` 必须等于计划行对应值（服务端覆写，不接受前端传值）。
- **R-VI-4 币种一致**：行 `currency_id` 空则取头；头 `currency_id` 必须等于来源 PO 币种。

---

## 5. 匹配契约（三单匹配）

### 5.1 匹配模式 `vi_match_mode`（参数 `control_parameter_def`）

| 模式 | 语义 | 对标 | 发票行要求 | 典型场景 |
|---|---|---|---|---|
| `po_based` | 2-way：发票 ↔ PO 计划行 | SAP PO-based IV（`WEBRE` 空）；Fusion 2-way | `schedule_id` 必填；`receipt_line_id` 可空 | 先开票后收货、服务类、低值免检 |
| `gr_based` | 3-way / 4-way：发票 ↔ PO ↔ 收货（↔ 质检） | SAP GR-based IV（`WEBRE='X'`）；Fusion 3/4-way | `schedule_id` + `receipt_line_id` 均必填，且**每张发票行对应一条收货行** | 常规物料采购 |

配置落点（D-VI-6 修订，**不新增物理列**）：

- **主配置**：新增 `control_parameter_def` 参数 `vi_match_mode`（`domain='procurement'`, `value_type='enum'`, `default_value='gr_based'`, 枚举 `{po_based, gr_based}`）。
- **覆盖**：`control_parameter_value` 按既有四维 + `specificity_rank` 解析（`org_id` → `document_type_id` → `line_type_id` → `item_group_id`），最具体优先。**「类型级」只是四维中的一层**，不是唯一层。
- **快照**：创建发票时把解析结果写入 `vendor_invoices.match_mode`，落盘后不随配置变更（审计可追溯）。
- 行级不设模式；行行为由头模式推导。
  > 依据：D365 的匹配策略是「法人默认 → 供应商/物料/供应商+物料」层级覆盖；NetSuite 开关落在**物料**记录；Infor M3 容差在 `APS900` 全局设置 + PO 行级匹配。三家均非「单据类型单层」，故本 Spec 把模式下沉为**配置参数的多级解析**（F/N/I）。
  > 金蝶（§19）把匹配规则做成 `匹配关系` + `匹配方案` 基础资料（支持自定义匹配条件 / 字段 / 公式），同样不是单据类型硬列；其「按总额 / 按明细」二选一在本 Spec **只采纳按明细**（N12）。

**聚合口径（A3，关键）**：

- `po_based` 校验量：`Σ invoice_line.qty (同 schedule_id) ≤ schedule.promised_qty - schedule.returned_qty + 容差`
- `gr_based` 校验量：`Σ invoice_line.qty (同 schedule_id) ≤ Σ qty_invoiceable(该 schedule 的收货行) + 容差`
  - `qty_invoiceable = qty_received − Σ qty_rejected(disposition ∈ {return_to_supplier, scrap})`（TBD-7 已裁决，§5.2）
  - 已匹配量来源：`v_doc_flow_consumed_qty` 在 `pool='ap_match'` 上按 `source_item='receipt_line.id'` 求和（§8）
- **不做**「发票行 ↔ 收货行多对多匹配表**（N2）**；`receipt_line_id` 是单值 trace，仅 `gr_based` 用于逐行对位。
- **匹配粒度只按明细**：每张发票行必须落到具体 `schedule_id`（`gr_based` 下再加 `receipt_line_id`）。**不采纳「按总额匹配」**——金蝶支持该模式，但会让 doc_flow 边失去行级锚点、无法做行级容差（N12 / §19）。

### 5.2 4-way（质检）说明

Fusion 4-way 把「质量检验」作为第四单。本平台质检结果是 `receipt_line.qty_rejected / rejection_disposition`（C），**不建质检单**；4-way 由处置类型折抵表达（TBD-7 已裁决）：

```
qty_invoiceable = qty_received − Σ qty_rejected(disposition ∈ {return_to_supplier, scrap})
```

- `return_to_supplier`（退回供应商）/ `scrap`（报废）：不可开票，必须折减。
- `concession`（让步接收）/ `rework`（返工后交付）：**仍计入可开票量**（可能带价格折让，走 `vi_price_tolerance`）。

> 旧口径「净收量 = `qty_received − qty_rejected`」会把让步接收与返工一并扣掉，导致供应商少开票、应付漏记 —— 属**缺陷**，本 Spec 已修正。若未来独立质检单建立，只需让 `qty_received` 取质检通过量，折抵公式不变。

### 5.3 容差契约（复用 `control_parameter_def`）

容差**一律不硬编码**（上游收货 Spec §10 已锁）。本 Spec 只用现有两类参数：

| `code` | `tolerance_direction` | `tolerance_basis` | `value_type` | 默认 | 语义 |
|---|---|---|---|---|---|
| `vi_price_tolerance` | `over` | `percent` | `decimal` | `0.00` | 发票单价高于 PO 单价的最大允许百分比 |
| `vi_qty_tolerance_receipt` | `over` | `percent` | `decimal` | `0.00` | 发票量高于**可开票量 `qty_invoiceable`**（§5.2）的最大允许百分比（单向，A8） |
| `vi_qty_tolerance_order` | `over` | `percent` | `decimal` | `0.00` | `po_based` 下发票量高于计划量的最大允许百分比 |
| `vi_amount_tolerance_abs` | `both` | `absolute` | `decimal` | `0.00` | 小额绝对差自动放过（SAP `BD` 对标） |
| `vi_rounding_tolerance_abs` | `both` | `absolute` | `decimal` | `0.01` | 舍入差容忍（SAP `BR` 对标） |

> 金蝶（§19）同样提供「匹配差异容差控制」，把容差方案作为**前置基础资料**（与匹配方案并列、匹配时可切换）⇒ 印证 A7「容差走配置」。但「多套容差方案并存 + 单据级选择」超出本波单值参数模型 —— **TBD-12 已裁决：不建方案对象**（§20.1），需要差异化时走 TBD-2 的参数维度扩展。

**解析顺序**（复用 `control_parameter_value.specificity_rank`，C）：

```
1. (org_id, document_type_id, line_type_id, item_group_id) 全匹配
2. 逐级放宽（最具体 → 最不具体）
3. 全不命中 → control_parameter_def.default_value
```

**单向性（A8，必须实现）**：

- 数量容差只在 `qty > reference_qty` 时判定；`qty ≤ reference_qty` 永不因数量触发例外。
- 价格容差是**双向语义上的单向**：仅 `unit_price > po_unit_price` 触发 `price_over_tolerance`；低于 PO 价**不拦**（供应商少开票是商业让步，SAP `PP` 同口径）。

**`overridden` 语义**：有权限用户可对 `exception` 行执行 `override_match`，写 `match_status=overridden` + `override_reason` + `overridden_by/at`；`overridden` 允许过账，但**永久留痕**，不进 `matched` 统计。

### 5.4 `match_pricing_mode` 三值

| 值 | 价格来自 | 校验行为 |
|---|---|---|
| `po_price`（默认） | `po_unit_price` 快照 | 与 PO 价比对，超容差 → `exception` |
| `receipt_price` | 无价可依 ⇒ 取 PO 价并**强制标记** `override_reason='receipt_price_mode'` | 仅校验数量，不校验价格 |
| `manual` | 用户录入 | 不自动校验价格；必须 `override_match` 才可过账 |

> `receipt_price` 存在的原因：SAP 允许「收货估价」场景；本平台 `receipt_line` 无价（D-RC-9），故该模式降级为「用 PO 价 + 留痕」，不引入收货价字段（N4）。

### 5.5 头级 `match_status` 聚合规则

```
行全 matched/overridden 且 头金额校验通过  → matched
任一行 exception                            → exception
全部行未校验（draft 未触发匹配）             → unmatched
```

头 `match_exception_reason` 取**首条**行级原因（完整列表见行）。

---

## 6. 状态机与不变量

### 6.1 主状态机（`status`，复用 M5）

```
draft ──submit──▶ submitted ──post──▶ posted ──reverse──▶ reversed
  │                   │                  │
  └────cancel─────────┴────cancel────────┘（posted 不可 cancel，只能 reverse）
```

| 转换 | 前置条件 | 副作用 |
|---|---|---|
| `draft → submitted` | 行 ≥ 1；头行金额自洽（R-VI-7） | **只计算** `match_status`（读已 `posted` 发票的边 + 本单内存行），**不写** doc_flow 边 |
| `submitted → posted` | `match_status ∈ {matched, overridden}`；重复发票硬拦通过（R-VI-14）；事务以 `BEGIN IMMEDIATE` 开启（R-VI-18） | 写 `billing` 池边 + `ap_match` trace 边（§8）；执行 `doc_effect.posting` |
| `submitted → cancelled` | 未过账 | 无（尚未写边） |
| `draft → cancelled` | 任意 | 无 |
| `posted → reversed` | 已存在有效红字发票 | 见 §7 |

### 6.2 匹配子状态（`match_status`，D-VI-5 补充说明）

| 值 | 含义 | 可否过账 |
|---|---|---|
| `unmatched` | 未执行匹配（`draft`） | 否 |
| `matched` | 全部行通过容差 | 是 |
| `exception` | 存在超容差行 | 否（须 override 或改数） |
| `overridden` | 例外已人工放行 | 是 |

> **不引入 SAP 的 Park / Blocked 独立状态**（A9）：Park ≈ `draft`（已录入未提交）；Blocked ≈ `submitted + match_status=exception`。用两字段正交表达，避免状态爆炸（`status` 5 × `match_status` 4 已覆盖 SAP 语义，C/S）。付款冻结不在此表达 —— 归付款波次对象（TBD-3）。

### 6.3 不变量清单

| ID | 不变量 | 强制层 |
|---|---|---|
| R-VI-1 | `invoice_no` 唯一且取号后不可改 | DB 唯一索引 + 服务 |
| R-VI-2 | 行来源互斥（§4.3） | 服务 |
| R-VI-3 | 有 `schedule_id` 时锚点字段由服务端覆写 | 服务 |
| R-VI-4 | 头币种 = 来源 PO 币种；行币种必须为空或等于头币种（多币种行不采纳，D-VI-18） | 服务 |
| R-VI-5 | 开票量 ≤ 参考量 + 容差（模式相关，§5.1） | 服务（查询时校验） |
| R-VI-6 | 行金额 = `round_amount(qty × unit_price × (含税折算))` | 服务 |
| R-VI-7 | 头 `net/tax/gross` = Σ 行对应值（含 `rounding_diff` 调整） | 服务 |
| R-VI-8 | 头币种 = PO 币种 | 服务 |
| R-VI-9 | `reversal_of_invoice_id` 仅 `document_category ∈ {credit_memo, cancellation}` 可非空，且源发票必须 `posted` | 服务 |
| R-VI-10 | 一次红冲只能有一个有效红字发票（`uq_vendor_invoice_reversal` 部分唯一索引） | DB |
| R-VI-11 | `posted` 后头行只读；`posting_date` 不可改 | 服务 |
| R-VI-12 | 红字 / 取消单写 `billing` 边时 `quantity_sign='red'`，净额由视图（active normal 求和 − red 求和）自动抵消，不新增「负数已开票量」字段 | 服务 + 视图 |
| R-VI-13 | `supplier_account_id` 必须与来源 PO 的供应商一致 | 服务 |
| R-VI-14 | 重复发票**硬拦**（`posted` 前）：查重键 = `supplier_account_id + normalized(supplier_invoice_no)`（去首尾/内部空格与连字符、全角转半角、统一大写；**不含金额**）；同键仅允许一张 `draft` 暂存；override 需 `vendor_invoice:override_duplicate` + 强制 `duplicate_override_reason` + 审计 | 服务（TBD-8 已裁决） |
| R-VI-15 | 红字发票不生成付款计划（付款域未建，仅记录约束） | 服务（占位） |
| R-VI-16 | 红冲蓝票（`reversal_of_invoice_id` 非空）必须指向 `posted` 且同供应商、同币种、同计划的蓝字发票；红字发票自身的 `direction=-1` 由类型派生，不可改 | 服务 |
| R-VI-17 | 一次匹配调用只能包含同一 `direction` 的发票；红字发票不得与蓝字发票同批匹配（金蝶「不允许红蓝一起匹配」，§19 / D-VI-13） | 服务 |
| R-VI-18 | 匹配提交以 **`BEGIN IMMEDIATE`** 开启事务，在同一事务内重算剩余量（计划量 / 可开票净收量 / 已匹配量）后才写边；`uq_doc_flow_idem` 冲突即整笔拒绝，不部分成功（TBD-13 已裁决） | 服务 + DB |

---

## 7. 过账副作用（`doc_effect`，M8）

YAML 声明式（与 `customer_invoice` 同结构，C）：

```yaml
doc_effect:
  posting:
    event_key: "vendor_invoice:{id}:post"
    direction_field: direction
  faces:
    - id: inv_consumption
      primitive: vendor_invoice_consumption_edges    # 写 billing + ap_match 边
    - id: po_invoiced_status
      primitive: recompute_schedule_invoiced_qty     # 只读投影，不落列
    - id: match_snapshot
      primitive: freeze_match_result                 # 冻结行 match_status 到行上
  projections:
    - id: po_billing_status
      primitive: recompute_purchase_billing_status   # PO 维度汇总（派生视图）
  reversal:
    from_states: [posted]
    to_state: reversed
    idempotent_states: [reversed]
    create_document:
      primitive: vendor_invoice_red_letter
```

**关键点**：

| 点 | 说明 |
|---|---|
| 无 GL | `posting` 只发领域事件 + 写边，不产生会计凭证（§1.2） |
| `recompute_schedule_invoiced_qty` 是**视图** | 不落 `purchase_order_schedules.invoiced_qty` 列（N3）；投影只是查询缓存键 |
| `freeze_match_result` | 过账时把当时行结果固化到 `vendor_invoice_lines.match_status`，后续 PO 价变更不影响历史判定 |
| 逆向声明式 | `reversal` 段由 `ReversalOrchestrator` 读取，不写 `if` 分支（与 v236 一致） |

---

## 8. doc_flow 边契约

### 8.1 规则清单（`doc_flow_rule`）

| `rule_id` | `source_bo` | `source_qty_field` | `target_bo` | `target_qty_field` | `pool` | 用途 |
|---|---|---|---|---|---|---|
| `po_schedule_to_vendor_invoice_line` | `purchase_order_schedule` | `promised_qty` | `vendor_invoice_line` | `qty` | `billing` | 已开票量（`po_based` 权威口径） |
| `receipt_line_to_vendor_invoice_line` | `receipt_line` | `qty_received` | `vendor_invoice_line` | `qty` | `ap_match` | 收货↔发票 trace（`gr_based` 逐行对位） |
| `vendor_invoice_line_to_credit_memo_line` | `vendor_invoice_line` | `qty` | `vendor_invoice_line` | `qty` | `billing` | 贷项核销原发票行 |

> 上表第二行**不是**新表：`vendor_invoice_line` 既是源也是目标（贷项行回指原发票行）。贷项规则沿用 `quantity_sign='red'` 语义（与 `customer_invoice_to_credit_memo` v240 对称，C）。

### 8.2 池语义（与上游收货 Spec §11 对齐）

| pool | 语义 | 消费视图 |
|---|---|---|
| `billing` | 已开票量（正式账面口径） | `v_doc_flow_consumed_qty`（active normal − red） |
| `ap_match` | 三单匹配 trace（不对账面负责） | `v_doc_flow_consumed_qty` 的独立切片，仅供 `gr_based` 匹配校验 |

**为什么 trace 要独立池**：`billing` 池是「已开票净额」，参与账面对账；若把收货 trace 也放 `billing`，同一张发票会被计两次（PO 计划行一次 + 收货行一次）。分池即隔离语义（D-VI-3 的推论）。

> 这不是「多造一个概念」：SAP 的 `EKBE` 就是**一张采购历史表内用记录类别**（收货 / 发票收据 / 退货 / 后续借项）区分同一 PO 行的不同事实（S）。`pool` 正是该判别符——复用 `billing` 等于丢掉判别符，口径必然被污染（D-VI-10）。
>
> 金蝶（§19）把 `收票单`（票据）/ `应付单`（业务应付）/ `财务应付单` / `匹配记录` 拆成四个独立对象，并用 `对应蓝票` 维持红蓝关系——方向一致：**票据事实与匹配历史必须可判别**，合并单池同样会抹掉判别符。

### 8.3 边字段约定（沿用 v215，C）

- `uq_doc_flow_idem` 保证幂等：同 `(rule_id, source_item, target_item)` 重复过账不新增边。
- `status ∈ {active, reversed}`；红冲时原边置 `reversed`，新红字边 `quantity_sign='red'`。
- **业务表上不放可写多态外键**（上游 §11 约束）；`vendor_invoice_lines` 只持具体 id（`schedule_id` / `receipt_line_id`），不持 `addressing` 表。
- `v_doc_flow_consumed_amount`（**本波新增视图**，与 `consumed_qty` 同构，按行金额求和）用于金额维度的「已开票金额」，服务 `po_based` 金额校验与 PO 维度汇总。

---

## 9. 退货：物流层 + 财务层两层（A10）

### 9.1 两层结构

| 层 | 对象 | 已有/新建 | 作用 |
|---|---|---|---|
| 物流层 | `RETURN_PO`（退货采购单）+ `VENDOR_RETURN`（退货出库） | **已建**（v227，C） | 实物退回供应商，库存减少（`receipt_line_to_return_out_txn`，v227） |
| 财务层 | `VENDOR_CREDIT_MEMO`（采购贷项凭证） | 本 Spec | 供应商退款 / 冲减应付 |

**两层配对关系**：贷项凭证行 `return_line_id` 指 `VENDOR_RETURN` 的收货行；不指 `RETURN_PO`（退货单本身不产生库存，只有退货出库产生）。这与 SAP「Return PO + MIGO 122/161 → MIRO Credit Memo」顺序一致（S）。

**配对强度 = 软约束（D-VI-11）**：

| 不做 | 做 |
|---|---|
| 不设「有退货单必须开贷项」的硬不变量（会阻断价格调整型贷项、供应商换货等合法场景） | 由退货动作**引导**：`receipt_create_vendor_return` 成功后提示「是否生成贷项」；贷项创建时若来自退货流程则 `return_line_id` 必填 |

**敞口可见性（替代强制）**：新增派生视图 `v_vendor_return_open_amount`——按 `schedule_id` 汇总「已退货数量/金额 − 已贷项数量/金额」，余额 > 0 即为「已退货未冲减」敞口，供列表页角标与对账查询使用。**视图派生、不落列**（§11.2 判别标准）。

> 依据：D365 的退货流程是「退货单 → 负向收货 → Invoice 按钮生成贷项」，贷项**由退货动作派生**但系统仍允许独立贷项（复制原发票行）；SAP 亦允许与退货无关的贷项（价格调整）。故软约束 + 敞口视图是两侧的共同做法（S/F）。
>
> 金蝶给出硬约束侧证：**所有出入库类单据不允许录入负数**，退货必须开退货类单据（正数），标准链路 `采购退料单 → 红字应付单 → 红字采购发票`；同时红字发票在「非红冲蓝票」场景可独立创建并单独匹配 ⇒ 与本 Spec 的「两层配对 + 软约束」一致（§19.1）。

### 9.2 为什么不是二选一（修正上轮结论）

早期判断「RETURN_PO 与贷项发票二选一」是错的：RETURN_PO 解决**货**，贷项发票解决**钱**。只做 RETURN_PO 会留下「已退货但应付未冲减」的敞口；只做贷项发票则实物没退、库存与账实不符。

### 9.3 行级退货字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `return_line_id` | integer | 指向 `VENDOR_RETURN` 对应的收货行（`receipt_line.id`，`document_category='return'`） |
| `return_reason_code` | string(30) | 退货原因（可空，随 `receipt_line.rejection_reason_code` 快照） |

路径：发票 `credit_memo` 行的 `line_source_policy.credit_memo` 含 `return_line`（§4.3），服务端校验该收货行属于 `VENDOR_RETURN` 且状态已过账。

---

## 10. 服务采购（SES）与自动结算（ERS）

### 10.1 服务采购

上游收货 Spec 的 `receipt.source_doc_type` 五值中**无** `service_entry`（C），而 §10 发票契约值域含 `service_entry` —— **契约漂移**，本 Spec 给出裁定：

| 裁定 | 内容 |
|---|---|
| 服务确认载体 | 复用 `receipt`，`source_doc_type='purchase_order'` + 计划行 `schedule_kind='service'`；不新增第 6 个 `source_doc_type`（避免扩 CHECK 枚举） |
| 发票侧 | `gr_based` 下服务发票行 1:1 挂「服务收货行」（SES 等价物）；`po_based` 下直接挂计划行 |
| 上游契约修订 | 收货 Spec §10 `source_doc_type` 值域中的 `service_entry` 应**删除**，改为「同 `purchase_order` + `schedule_kind=service`」；**TBD-1 已裁决**（§20.1），待回写收货 Spec |

> 这一裁定的收益：零新增枚举值、零表结构改造、服务与实物共享同一套匹配代码路径。

### 10.2 自动结算（ERS，预留）

- `settlement_mode='ers'`：由计划行 / 收货行按 PO 价自动生成 `draft` 发票，不经过供应商来票录入。
- 本波**只建字段与校验分支**（`settlement_mode` 默认 `supplier_invoice`），不实现 ERS 定时任务（TBD-9 已裁决，前置条件见 §20.1）。
- ERS 生成的发票仍需走 `match_status` 校验与 `post`，不复用特殊状态。

---

## 11. 单一事实源 / 元数据驱动审查

> 本章是本 Spec 的**架构合规声明**：每一行都对应一次「为什么不是我自造一个」的答辩。

### 11.1 枚举与身份

| 机制 | 真源 | 采购发票侧动作 |
|---|---|---|
| 单据类别 / 方向 / 角色 | `type_definitions.document_category / direction / document_role`（v243，C） | **只播种类型行**，不自造 `invoice_type` |
| 类型默认唯一 | `uq_type_default_role (scope_bo, level, document_role) WHERE is_default=1` | 直接受益，无需新索引 |
| 单据编号 | `number_sequences` + `type_definitions` 绑定 | 播种 `VI/VCM/VDM/VIC` 四条序列 |
| 状态枚举 | YAML `enum_values`（不发 DB CHECK） | 与 `customer_invoice` 同口径；**不写 SQLite CHECK** |

### 11.2 数量与金额的派生边界

| 量 | 真源 | 是否落列 |
|---|---|---|
| 已开票量（按计划行） | `doc_flow_edges` + `v_doc_flow_consumed_qty` | **否** |
| 已开票金额（按计划行） | `v_doc_flow_consumed_amount`（新增视图） | **否** |
| 已收货量 | `purchase_order_schedules.received_qty`（既有缓存列，v215 前已存在） | 是（历史既有，不改） |
| 超收量 | 发票行 `qty_over_receipt` | 是（**匹配判定快照**，非累计量） |
| 头金额合计 | 行求和 | 是（单据自身事实，非缓存） |

> 判别标准：**「跨单据累计」一律不落列**（防漂移），**「单张单据内可复算但需冻结」可落列**（防 PO 价/容差后续变更改写历史）。

**性能门槛（TBD-11 已裁决）**：维持视图派生，不落 `invoiced_qty`。仅当 `ap_match` 切片的 `doc_flow_edges` 边数 > 5 万，或 `v_doc_flow_consumed_qty` p95 > 200ms 时，才评估**物化视图**（`v_doc_flow_consumed_qty_mv` + 定时/触发器刷新），仍不落实体列。

### 11.3 容差与配置

- 复用 `control_parameter_def` 的 `tolerance_direction / tolerance_basis / default_value`（C），不新建容差表（A7）。
- 复用 `control_parameter_value.specificity_rank` 的四维解析（org / 单据类型 / 行类型 / 物料组，C）。
- 明确缺口：**无 supplier / item 维度** ⇒ 本波用物料组近似；**TBD-2 已裁决**为下一波扩 `supplier_account_id` + `item_id`（0 哨兵值 + 新 `specificity_rank` 序，§20.1），不在本波「偷偷加列」。

### 11.4 声明式而非代码分支

| 行为 | 声明位置 | 禁写位置 |
|---|---|---|
| 行来源可选集 | YAML `line_source_policy` | 前端下拉硬编码 |
| 过账副作用 / 投影 / 红冲 | YAML `doc_effect` | `if status == 'posted'` 散落分支 |
| 匹配模式 | `control_parameter_def` 参数 `vi_match_mode`（多级解析，D-VI-9） | 全局常量 / `type_definitions` 加列 |
| 动作与权限 | YAML `actions` + `bo_action_registrations` | 手写路由白名单 |
| 菜单 | YAML `ui.list/menu` + `skip_auto_menu` | `init_and_seed.py` 硬插行 |

### 11.5 必须清理的幽灵元数据（不属本 Spec 范围但需登记）

`AP_INVOICE` / `BO_AP_INV` / `BO_PAYMENT_REQ` 仅存在于 `meta/scripts/init_and_seed.py`（L300 / L342 / L345 / L377 / L380 / L425-427）与 `generate_test_data.py`，**无真实表**（C）。**TBD-10 已裁决：全量删除**（不接真对象 —— 真实对象是 `vendor_invoice`，`AP_PAYMENT` 属付款波次），删除清单见 §20.4，作为 W4 前置，不得留在库里造成「已支持」假象。

---

## 12. 页面、菜单、动作、权限

### 12.1 页面结构

| 项 | 内容 |
|---|---|
| 头列表列 | `invoice_no / invoice_date / supplier_account_id / supplier_invoice_no / currency_id / gross_amount / match_status / status / purchase_org_id / org_id` |
| 头列表筛选 | `document_category / status / match_status / supplier_account_id / invoice_date` |
| 头表单分区 | 基本信息（`invoice_no / document_type_id / invoice_date / received_date / status`）；供应商（`supplier_account_id / supplier_party_id / supplier_site_text / supplier_tax_no`）；匹配（`match_mode / match_pricing_mode / match_status / match_exception_reason / settlement_mode`）；金额（`currency_id / exchange_rate / net_amount / tax_amount / gross_amount / rounding_diff`）；组织（`org_id / purchase_org_id`）；其他（`supplier_invoice_no / remark`） |
| 详情子表 | `child_sections: [vendor_invoice_line]` |
| 行列表列 | `line_no / schedule_id / receipt_line_id / item_id / qty / uom_id / unit_price / po_unit_price / price_diff_amount / net_amount / tax_amount / match_status` |
| 行表单分区 | 锚点（`schedule_id` 只读派生 `order_line_id / item_id / uom_id`；`receipt_line_id` 仅 `gr_based` 可编辑）；数量金额（`qty / unit_price / price_includes_tax`）；税额（`tax_code_id / tax_amount`）；匹配（`match_status / match_exception_reason` 只读） |
| 详情动作 | 提交 / 过账 / 重新匹配 / 例外放行 / 取消 / 红冲（手工新建贷项 / 借项 / 取消单由守卫拦截） |

### 12.2 YAML `actions` 清单（复用 `bo_action_registrations`，禁手写路由）

| action id | type | method / path | 权限码（v249 单段式） |
|---|---|---|---|
| `vendor_invoice_create` | create | `POST /api/v1/vendor_invoices` | `vendor_invoice:create` |
| `vendor_invoice_read` | read | `GET /api/v1/vendor_invoices/{id}` | `vendor_invoice:read` |
| `vendor_invoice_update` | update | `PUT /api/v1/vendor_invoices/{id}` | `vendor_invoice:update` |
| `vendor_invoice_delete` | delete | `DELETE /api/v1/vendor_invoices/{id}` | `vendor_invoice:delete` |
| `vendor_invoice_list` | list | `GET /api/v1/vendor_invoices` | `vendor_invoice:read` |
| `vendor_invoice_submit` | custom | `POST /api/v1/vendor_invoices/{id}/submit` | `vendor_invoice:submit` |
| `vendor_invoice_post` | custom | `POST /api/v1/vendor_invoices/{id}/post` | `vendor_invoice:post` |
| `vendor_invoice_match` | custom | `POST /api/v1/vendor_invoices/{id}/match` | `vendor_invoice:match` |
| `vendor_invoice_override_match` | custom | `POST /api/v1/vendor_invoices/{id}/override-match` | `vendor_invoice:override_match` |
| `vendor_invoice_override_duplicate` | custom | `POST /api/v1/vendor_invoices/{id}/override-duplicate` | `vendor_invoice:override_duplicate` |
| `vendor_invoice_cancel` | custom | `POST /api/v1/vendor_invoices/{id}/cancel` | `vendor_invoice:cancel` |
| `vendor_invoice_reverse` | custom | `POST /api/v1/vendor_invoices/{id}/reverse` | `vendor_invoice:reverse` |
| `vendor_invoice_line_create / update / delete / list` | crud | `/api/v1/vendor_invoice_lines` | `vendor_invoice_line:*` |

### 12.3 菜单与路由

- 顶层分组 `procurement`（已存在，C），新增子菜单 `vendor-invoice-management` → `/vendor-invoices`；`skip_auto_menu: true`（与 receipt 同范式）。
- `src/router/detailRouteGuard.js`：`SUPPORTED_OBJECT_TYPES` 补 `vendor_invoice`，`typeLabels` 补「采购发票」。

### 12.4 对既有对象的改动（最小集）

| 对象 | 改动 | 原因 |
|---|---|---|
| `type_definitions` | **不改**（匹配模式走 `control_parameter_def`，见 §5.1） | 零物理列变更；D365/NetSuite 均非类型级单层 |
| `purchase_order_schedule` | **不加列**（复用 `received_qty / returned_qty` + doc_flow 视图） | N3 |
| `receipt` | **不改**（`source_doc_type` 不扩值，见 §10.1） | TBD-1 |
| `control_parameter_def` | 只插 **6** 条参数行（§5.3 五条容差 + §5.1 一条 `vi_match_mode`），不改表结构 | A7 / D-VI-6 |
| `doc_flow_rule` | 插 3 条规则（§8.1） | — |
| `bo_action_registrations` | 插 §12.2 动作注册 | — |

---

## 13. 迁移与实施顺序

> 磁盘实际最大迁移为 `v256__align_status_check.py`（已被他人占用，C）；本 Spec 落盘 **v252–v255 + v258**（W1–W4 / W6），W5 无迁移。

| 波次 | 迁移 | 内容 | 验证 |
|---|---|---|---|
| W1 | `v252__vendor_invoice_object.py` | `vendor_invoices` / `vendor_invoice_lines` 建表 + 索引（`uq_vendor_invoice_no`、`uq_vendor_invoice_reversal`、`uq_line_no`）；含 `org_id`、`settlement_mode`，**不含** `payment_block`（TBD-3） | `python d:\filework\test.py --file meta/tests/migrations/test_vendor_invoice_migrations.py` |
| W2 | `v253__vendor_invoice_type_seed.py` | 四类类型种子（§3.2）+ 四条序列绑定 + **6 条参数**（`vi_match_mode` + 5 条容差，§5.3；`control_parameter_def` 种子，非 `type_definitions` 列） | 同上 `--file meta/tests/migrations/test_vendor_invoice_migrations.py` |
| W3 | `v254__vendor_invoice_doc_flow.py` | 3 条 `doc_flow_rule`（§8.1）+ `v_doc_flow_consumed_amount` 视图 | 同上 `--file meta/tests/migrations/test_vendor_invoice_migrations.py` |
| W4 | `v255__vendor_invoice_actions.py` | 17 权限码 + 菜单 + 退役旧自动菜单 / 幽灵元数据（动作注册在 `bo_action_registrations` 静态块，不建表）；**已退役手工 `create_credit_memo` / `create_debit_memo` 动作与权限** | 同上 `--file meta/tests/migrations/test_vendor_invoice_migrations.py` |
| W5 | **无迁移**（无表变更） | 匹配服务 `vendor_invoice_match_service.py` + 动作层 `vendor_invoice_actions.py` | `--file meta/tests/services/test_vendor_invoice_match.py` |
| W6 | `v258__vendor_invoice_reversal.py` | 补 `reversal_reason` 列；回填 `VENDOR_INVOICE.reversal_type_id → VENDOR_CREDIT_MEMO`；清理死权限 `create_credit_memo` / `create_debit_memo` | 同上 `--file meta/tests/migrations/test_vendor_invoice_migrations.py` |

**W3 之后才能做 W5**：匹配服务依赖 `v_doc_flow_consumed_qty` 的 `ap_match` 切片与 `consumed_amount`。

**风险门（每波必过）**：

1. `python d:\filework\test.py --failed`（串行确认，禁 `pytest`）。
2. `generated_schema.sql` 与 YAML 一致性检查（`declaration_guard`）。
3. `v_doc_flow_consumed_qty` 列数不因新视图变化（保 17 列语义，C）。

---

## 14. 出口判据（Definition of Done）

| # | 判据 | 验证方式 |
|---|---|---|
| D1 | 两张表 + 全部索引存在，`sqlite_master` 可见 | `table_schema` 工具 / 迁移 `verify()` |
| D2 | 四类类型 + 四序列 + **6 条参数**（`vi_match_mode` + 5 容差）已播种，且 `uq_type_default_role` 不冲突 | 迁移 `verify()` 断言 |
| D3 | 3 条 doc_flow 规则存在，`uq_doc_flow_idem` 幂等生效（同单重复过账不增边） | 集成测试 |
| D4 | `po_based` 超计划量 → `exception`；`gr_based` 超 `qty_invoiceable` → `exception`；反向（少开）不拦 | 单测 4 例 |
| D5 | `matched → post` 写边；`exception → post` 被拒；`override → post` 成功且留痕 | 单测 3 例 |
| D6 | 贷项凭证核销原发票行后，`billing` 池净额回到过账前 | 集成测试（对账断言） |
| D7 | 红冲后原边 `reversed`、红字边 `quantity_sign='red'`，`v_doc_flow_consumed_qty` 净额为 0 | 集成测试 |
| D8 | 前端列表/详情/行子表可新建—提交—匹配—过账—红冲（3006 端口人工验证） | Playwright / 人工 |
| D9 | 无 GL 凭证、无付款单据被创建（越界断言） | 单测负向断言 |
| D10 | `test.py --failed` 全绿 | 命令输出 |

---

## 15. TBD（未决项 — 已裁决，详见 §20）

> 下表「现状 / 本波处置」为**裁决前**记录；最终裁决、依据、落点与签字人见 §20.1。凡与本节不一致处，以 §20 为准。

| ID | 议题 | 现状 / 本波处置 | 决策人 |
|---|---|---|---|
| TBD-1 | 收货 Spec §10 的 `source_doc_type='service_entry'` 与 `receipt.yaml` 五值不一致 | 本波裁定用 `purchase_order + schedule_kind=service`；需回写收货 Spec | PM |
| TBD-2 | 参数解析维度缺 `supplier_account_id` / `item_id`（现仅 org / 单据类型 / 行类型 / 物料组） | 本波用**物料组近似物料级**、供应商级不做；但 D365（供应商/物料/物料+供应商）与 NetSuite（物料级）均把开关放在这两层 ⇒ 建议下一波扩展 `control_parameter_value` 维度，需全平台评审 | 架构 |
| TBD-3 | 付款 / 预付 / `payment_block` 码表 | 本波只留字段，不实现；预付不作为发票类型（N5） | PM（付款波次） |
| TBD-4 | 税额计算与税码推导 | 本波行税额直录；若接税务引擎需新增 `tax_code_id` 校验链 | 税务域负责人 |
| TBD-5 | `reversal_type_id` 链：贷项是否回指发票、取消单是否回指发票 | 暂定 发票↔贷项 双向，取消单 → 发票 | PM |
| TBD-6 | 多币种行（行币种 ≠ 头币种） | 本波禁止（R-VI-4）；如需支持，需汇率按行快照 | 架构 |
| TBD-7 | 独立质检单（Fusion 4-way 第四单） | 本波用 `qty_rejected` 折抵；独立质检单建后调整净收量口径 | PM |
| TBD-8 | 重复发票检查（`supplier_invoice_no` + 金额 + 供应商） | 本波软校验可 override；是否硬拦待定 | PM |
| TBD-9 | ERS 定时自动结算 | 本波只留 `settlement_mode` 字段 | PM |
| TBD-10 | 幽灵元数据 `AP_INVOICE / BO_AP_INV / BO_PAYMENT_REQ` | 落地时删除或接真对象（二选一） | 本波实施者 |
| TBD-11 | 是否新增 `purchase_order_schedule.invoiced_qty` 只读缓存列（性能） | **不加**（N3）；若查询成为瓶颈，以物化视图另行评估 | 架构 |
| TBD-12 | 多套匹配方案 / 容差方案并存 + 单据级选择 | 金蝶把「匹配关系 / 匹配方案 / 容差方案」做成可切换的基础资料；本波只有单值 `vi_match_mode` + 单套容差参数，未建模「方案选择」（§19.1） | 架构 |
| TBD-13 | 并发匹配的 TOCTOU 锁策略 | 视图派生无锁：两个匹配动作可能同时读到同一剩余量。本波用事务内重算 + `uq_doc_flow_idem` 兜底（R-VI-18）；是否需要 `BEGIN IMMEDIATE` / 悲观锁待评审 | 架构 |

---

## 16. 参考来源

| 来源 | 用途 |
|---|---|
| `docs/specs/spec-receipt-object-model-2026-11-01.md` §10 / §11 | 上游发票接口契约与 doc_flow 边契约 |
| `docs/specs/spec-purchase-order-object-model-2026-11-01.md` | PO / 计划行字段与状态基线 |
| `docs/specs/sales-invoice-pricing-spec-2026-11-10.md` | Spec 结构与 FR/NFR 范式 |
| `meta/schemas/customer_invoice.yaml` | 头行骨架、`doc_effect`、`line_source_policy` 模板 |
| `meta/schemas/control_parameter_def.yaml` / `control_parameter_value.yaml` | 容差元数据与解析维度 |
| `meta/migrations/v243__customer_invoice_document_role.py` | `document_role / direction / is_default` 平台身份模型 |
| `meta/migrations/v215__doc_flow_stage2_rules.py` | `doc_flow_rule / doc_flow_edges / v_doc_flow_consumed_qty` |
| `meta/migrations/v227__purchase_return_object.py` | 退货物流层（`RETURN_PO` / `VENDOR_RETURN` / `receipt_line_to_return_out_txn`） |
| Oracle Fusion `AP_INVOICES_ALL / AP_INVOICE_LINES_ALL / PO_LINE_LOCATIONS_ALL` | 发票头行、计划行聚合口径、2/3/4-way |
| SAP `RBKP / RSEG / EKBE / EKPO-WEBRE / OMR6` | GR-based IV、容差键、Park/Blocked/Posted、ERS |

---

## 17. 审批要求

| 角色 | 关注点 |
|---|---|
| PM | §0.2 采纳表、§1.2 边界（无 GL / 无付款）、§13 波次切分、**§20.2 签字项（TBD-1/3/5/7/8/9）** |
| 架构 | §8 池语义、§11 单一事实源审查（尤其「不落列」清单）、**§20.3 签字项（TBD-2/6/11/12/13）** |
| 后端 | §5 匹配口径、§6 状态机与不变量、§8.3 边幂等 |
| 前端 | §12 页面结构与行子表只读/可编辑边界 |
| 测试 | §14 出口判据可测性（D3–D7 必须有自动化） |

---

## 18. 其他头部 ERP 交叉验证（2026-11-11 追加）

> 触发：评审提出「三个待确认点，再看其他头部 ERP 怎么设计」。本节只补对标，不推翻 §0–§17；凡与前三节冲突处以本节修订为准（已在正文同步改毕）。

### 18.1 产品矩阵

| 维度 | D365 F&O | NetSuite | Infor M3 / LN | SAP | 本 Spec 结论 |
|---|---|---|---|---|---|
| 2-way / 3-way 开关层级 | 法人默认（AP parameters `Line matching policy`）+ **供应商 / 物料 / 物料+供应商**三级覆盖（`Allow matching policy override`） | **物料**主数据 `Match Bill to Receipt` 复选框 | `APS900` 用户定义容差（公司级）+ PO 头/行级匹配；LN `ACP Parameters` 自动匹配开关 | **PO 行** `EKPO-WEBRE` | `control_parameter_def` 枚举参数 + 四维解析（D-VI-9） |
| 容差粒度 | 默认容差 + 供应商级覆盖 | 规则 + 容差 | `APS900` 用户定义（价格/数量差异） | `OMR6` 容差键（PP/DQ/BD/BR/AN/AP） | `control_parameter_def` 五条容差 + `specificity_rank`（A7/A8） |
| 收货 vs 发票事实的组织方式 | **分表**：`VendPackingSlipTrans`（收货）/ `VendInvoiceInfoLine`（发票行），收货行带 `Remain` 可匹配量 | 分事务：Item Receipt / Vendor Bill | 分表：收货单 / 供应商发票 | **同表不同记录类别**：`EKBE` 一行一条后续单据（收货 / 发票收据 / 退货 / 后续借项） | `doc_flow_edges.pool` 作判别符（`billing` / `ap_match`），D-VI-10 |
| 退货与贷项 | 退货单 → 负向收货 → `Invoice` 按钮生成贷项；也支持复制原发票行独立开贷项 | 退货授权 → 贷项 | 退货单 → 贷项 | Return PO + 122/161 → MIRO Credit Memo；贷项亦可独立（价格调整） | 物流层 + 财务层**软配对** + 敞口视图（D-VI-11） |

### 18.2 三点结论与修订

| 待确认点 | 原方案 | 交叉验证结论 | 修订 |
|---|---|---|---|
| 匹配模式粒度 | 单据类型级硬列 | 三家头部产品**没有一家**把开关钉死在单据类型：D365 是「法人默认 + 供应商/物料/物料+供应商」覆盖，NetSuite 在物料主数据，SAP 在 PO 行。类型级过粗，且给 `type_definitions` 加列是「为配置项加物理列」的反模式 | 改为 `control_parameter_def` 参数 `vi_match_mode`，走既有四维解析 + 头快照；`type_definitions` **零改动**（D-VI-9） |
| `ap_match` 独立池 | 独立池 | D365 用**独立表**承载收货与发票匹配量；SAP 用**同一历史表的记录类别**区分。二者都要求「收货事实」与「发票事实」可判别。我们的 `pool` 列正是该判别符，复用 `billing` 等于抹掉判别符 | **维持独立池**，并在文档中把它定义为「记录类别判别符」而非第二个概念（D-VI-10） |
| 退货是否强制两层 | 强制二选一 → 修正为两层，但未定强度 | D365 退货流程中贷项由退货动作派生，但系统仍允许独立贷项（复制原发票）；SAP 贷项可完全独立于退货（价格调整）。**强制会阻断合法业务** | 软约束 + 派生视图 `v_vendor_return_open_amount` 暴露「已退货未冲减」敞口（D-VI-11） |

### 18.3 新增反例（继续不采纳）

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N8 | 「退货负向收货直接开负发票」的单据形态（负数量收货单即财务凭证） | D365 退货收货的 `Invoice` 动作 | 会让 `receipt` 承载金额，破坏 D-RC-9（收货不落价）；本平台用 `document_category=credit_memo + direction=-1` 等价表达，且保留单据类型语义 |
| N9 | 把匹配模式做成公司级单值开关 | Infor `ACP Parameters` / D365 法人默认 | 头部产品都允许下级覆盖；单值开关会导致「同一法人下服务类与物料类被迫同模式」 |

### 18.4 对前文的影响清单

| 位置 | 变更 |
|---|---|
| §0.2 A6 | 「对齐 SAP」→「对齐 SAP + D365/NetSuite 多层覆盖」 |
| §0.3 D-VI-6 | 标注被 D-VI-9 细化；新增 D-VI-9 / D-VI-10 / D-VI-11 |
| §5.1 配置落点 | 类型硬列 → `control_parameter_def` 多级解析（无物理列） |
| §8.2 | 补「pool = 记录类别判别符」论证 |
| §9.1 | 补软配对强度表 + 敞口视图 |
| §12.4 | `type_definitions` 行改为「不改」；参数行 5 → 6 |
| §15 TBD-2 | 维度缺口扩写为「供应商 / 物料」并升级优先级 |
| §18 | 本节 |

### 18.5 来源

- [Set up Accounts payable invoice matching validation — Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/tasks/set-up-accounts-payable-invoice-matching-validation)
- [Accounts payable invoice matching overview — Microsoft Learn](https://learn.microsoft.com/en-US/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching)
- [Create a purchase return order — Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/tasks/create-purchase-return-order)
- [Describe the purchase order creation and purchase return processes — Microsoft Learn](https://learn.microsoft.com/en-us/training/modules/describe-sales-procurement-processes-dynamics-365/7-describe-purchase-order-creation-process)
- [NetSuite 3-Way Matching: How It Works and How to Configure It — Tim Dietrich](https://timdietrich.me/blog/netsuite-3way-matching/)
- [NetSuite Advanced Procurement（Three-Way Match）— Oracle NetSuite](https://www.netsuite.com.sg/portal/assets/pdf/ds-advanced-procurement.pdf)
- [Matching Supplier Invoices to Purchase Orders（APS360）— Infor M3 文档](https://docs.infor.com/m3udi/16.x/en-us/m3beud/finaccths/vzq1567534411182.html)
- [Define Basic Accounts Payable Settings（APS905）— Infor M3 文档](https://docs.infor.com/m3udi/16.x/en-us/m3beud/finaccths/aps905.html)
- [Purchase Invoice Entry（tfacp2600m000）— Infor LN 文档](https://docs.infor.com/ln/10.4/en-us/lnolh/help/tf/acp/tfacp2600m000.html)
- [Purchase Order History Table in SAP with EKBE and ME23N](https://purchaseorders.io/blog/purchase-order-history-in-sap)
- [EKBE - History per Purchasing Document — LeanX](https://leanx.eu/en/sap/table/ekbe.html)

---

## 19. 金蝶（Kingdee Cloud）交叉验证（2026-11-11 追加）

> 触发：在第 5 家（金蝶云·星空 V7.0.4）上复核 §18.2 的三个待确认点。本节只补对标与修订，凡与 §0–§18 冲突处以本节为准（冲突项已在正文同步标注）。
> 金蝶的核心差异：**把「业务应付（应付单）」与「发票」彻底分离**，并把「发票匹配」做成**独立单据 + 审批流 + 匹配工作台**。

### 19.1 产品矩阵

| 维度 | 金蝶云·星空（V7.0.4） | 本 Spec | 判定 |
|---|---|---|---|
| 匹配规则载体 | **基础资料**：`匹配关系` + `匹配方案`（可自定义匹配条件 / 匹配字段 / 多匹配对象公式）；预制 2 套（方案1 按物料并校验物料、方案2 按金额且不校验物料）；匹配时可选方案，默认取「默认=是」 | `control_parameter_def` 枚举参数 `vi_match_mode`（未来再加匹配方案） | **一致**：都不是钉在单据类型上的硬列（D-VI-9 / D-VI-12） |
| 匹配对象与粒度 | 匹配对象可为 **采购入库单 / 采购订单 / 采购验收单 / 采购收货单**（可自定义）；支持**按总额**或**按明细**；业务控制基准可选**数量 / 金额** | 锚点固定为「计划行 + 行」，**只支持按明细**（D-VI-3） | **差异**：不采纳「按总额」与「可换匹配对象」（N12） |
| 事实组织方式 | 四对象拆分：`收票单`（票据） / `应付单`（业务应付） / `财务应付单` / `匹配记录`（独立单据） | `vendor_invoice` 单对象 + `doc_flow_edges.pool` 判别符 | **方向一致**：都要求「票据事实」与「业务事实」可判别（D-VI-10） |
| 红蓝票 | `对应蓝票` 字段；红冲蓝票须维护对应蓝票；**红票若非蓝票红冲，则单独发起匹配，不允许红蓝一起匹配** | `reversal_of_invoice_id` + 红字发票独立匹配 | **一致**（D-VI-13） |
| 退货 / 负数 | **所有出入库类单据禁止录负数**，必须开退货类单据（正数）：`采购退料单 → 红字应付单 → 红字采购发票`；「不要手工直接开红字」属实践引导，非系统硬约束 | 物流层 + 财务层两层配对；`document_category=credit_memo + direction=-1`；N8 已拒绝负向收货 | **一致**：印证 N8 与 D-VI-11 |
| 未匹配额度存储 | **反写到源单**：收票单头 `已匹配(是/否)` / `匹配状态(未匹配/部分匹配/全部匹配)`，行 `未匹配价税合计 / 未匹配数量`；保存占用、删除释放 | **视图派生**（`v_doc_flow_consumed_qty` 等），零物理缓存列 | **差异**：不采纳反写（N11 / D-VI-14） |
| 匹配动作形态 | 独立单据 + 审批流 + **发票匹配工作台**（未匹配 / 匹配中 / 已匹配 / 匹配异常） | doc_flow 边 + 服务动作 + 行级 `match_status` | **差异**：不建匹配单据（N10） |
| 应付确认时点 | **立账模式**参数：`暂估应付`（按发票确认应付，未到票记暂估，到票红冲暂估）/ `业务应付`（物权转移即确认应付，到票差异生成差异应付单） | 无 AP / GL 台账，`posted` 只表达业务已确认 | **正交维度**：与匹配模式无关，明确不在本 Spec 范围（§1.2） |

### 19.2 三点结论与修订

| 待确认点 | §18 结论 | 金蝶证据 | 本轮裁定 |
|---|---|---|---|
| ① 匹配模式粒度 | `control_parameter_def` 多级解析 | 匹配规则是**可配置基础资料**（匹配关系 / 匹配方案，含自定义匹配条件与字段），并有系统参数「收票单匹配应付，自动生成采购发票状态」控制结果状态；**从未钉在单据类型上** | **维持 D-VI-9**，并新增 D-VI-12：规则参数化、**不建匹配单据** |
| ② `ap_match` 独立池 | 独立池 = 记录类别判别符 | 金蝶把 `收票单` / `应付单` / `财务应付单` / `匹配记录` 拆成四个对象，用 `对应蓝票` 维护红蓝关系；单池会让「票据」与「匹配历史」再次混同 | **维持 D-VI-10**：拆分方向一致，不分池会抹掉判别符 |
| ③ 退货是否强制两层 | 软配对 + 敞口视图 | 金蝶要求退货走 `退料单 → 红字应付单 → 红字发票`，但红字发票仍可独立创建并按「非红冲蓝票」单独匹配 ⇒ 系统层面**不强制**「退料必有红票」 | **维持 D-VI-11**（软配对）；新增 D-VI-13 红蓝票匹配规则、D-VI-14 不反写额度 |

### 19.3 新增反例（继续不采纳）

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N10 | **匹配做成独立单据**（带审批流、匹配工作台、保存占用 / 删除释放） | 金蝶「发票匹配」 | 本平台无匹配审批场景；把「匹配」升格为单据会引入第二种业务编号、第二套状态机与第二套权限，与 NFR-001（不建并行机制）冲突。匹配是**关系事实**，落 `doc_flow_edges` 即可 |
| N11 | **把已匹配额度反写到源单**（`已匹配` / `匹配状态` / `未匹配价税合计` / `未匹配数量`） | 金蝶收票单头 / 行额度字段 | 反写即物理缓存（同 N3 的推理），且存在并发写竞争；本平台用视图派生 + 提交时重算校验，避免「缓存与边不一致」 |
| N12 | **按总额匹配**（不落到行）与**可自由更换匹配对象**（入库单 / 订单 / 验收单 / 收货单） | 金蝶「按总额 / 按明细」「可自定义匹配对象」 | 按总额会让 `doc_flow` 边失去行级锚点，与 A3 / D-VI-3 冲突，且无法支撑行级容差；更换匹配对象会引入多态锚点，超出本波边界（§1.3） |
| N13 | 用「立账模式」决定发票是否产生应付 | 金蝶 `暂估应付` / `业务应付` | 本平台无 AP 台账与 GL，`posted` 只表达业务确认；若将来引入 AP 域，应在 AP 波次建模，不塞进 `vendor_invoice`（§1.2） |

### 19.4 对前文的影响清单

| 位置 | 变更 |
|---|---|
| §0.3 | 新增 D-VI-12 / D-VI-13 / D-VI-14 |
| §5.1 | 明确匹配**只按明细**，不采纳「按总额」（N12）；匹配对象固定为计划行，不允许多态切换 |
| §5.3 | 金蝶亦有「匹配差异容差控制」且容差方案为前置基础资料 ⇒ 印证 A7；但「多套方案并存 + 单据级选择」记为 TBD-12 |
| §8.2 | 补金蝶四对象拆分（收票单 / 应付单 / 财务应付单 / 匹配记录）作为 D-VI-10 的第二组证据 |
| §9.1 | 补「禁止出入库单据录负数」证据，强化 N8；退货标准链路与本 Spec 两层配对同构 |
| §6.3 | 新增不变量：红冲蓝票必须带 `reversal_of_invoice_id`（R-VI-16）；红字发票不得与蓝字发票共用一次匹配调用（R-VI-17）；并发匹配事务内重算剩余量（R-VI-18） |
| §13 | 迁移内容不变（v252–v255；W5 无迁移），无新增表 / 列 |
| §15 | 新增 TBD-12（匹配方案多套并存 + 单据级选择）、TBD-13（并发匹配 TOCTOU 的锁策略） |

### 19.5 来源

- [发票匹配 — 金蝶云社区](https://club.kdcloud.com/knowledge/611983863967082752)
- [发票匹配场景指引 — 金蝶云社区](https://club.kdcloud.com/knowledge/659751519922992384)
- [收票单匹配应付，支持自定义匹配方案 — 金蝶开发者社区](https://developer.kingdee.com/knowledge/256119163692275712)
- [应付款管理（暂估应付 / 业务应付立账模式、核销方式）— 金蝶云·星空在线帮助](https://help.open.kingdee.com/)
- [采购入库核算应用（入库 / 退料下推应付单、到票核销）— 金蝶云·星空在线帮助](https://help.open.kingdee.com/)
- [采购退料单 → 红字应付单 → 红字采购发票（退货链路）— 金蝶云社区问答](https://vip.kingdee.com/questions/903946036103154688)
- [出入库单及退货单能不能录负数? — 金蝶云社区](https://vip.kingdee.com/knowledge/637456347524514048)
- [应付会计智能体（多级精准匹配 / 三单智能匹配）— 金蝶官网](https://www.kingdee.com/resources/ai-agent/1534503207326479713)

---

## 20. TBD 决策建议（2026-11-11）

> 裁决依据 = §18（SAP / Fusion / D365 / NetSuite / Infor 交叉验证）+ §19（金蝶）+ 本平台现状（C 级代码证据）。
> 本节为**决策结论**；§15 保留裁决前的原始记录，以本节为准。

### 20.0 裁决原则（五条，供后续争议时回溯）

| # | 原则 | 说明 |
|---|---|---|
| P1 | 单一事实源优先 | 能由边/视图派生的累计量一律不落列（§11.2）；落列只在「单张单据内可复算但需冻结」时成立 |
| P2 | 主流默认优先 | ≥ 4/6 家一致的做法直接采纳为默认；仅 1–2 家采用的（如匹配独立单据、额度反写）不引入 |
| P3 | 无下游域则不预埋字段 | 下游对象未建（付款 / GL / 税务引擎）时，不提前造半个枚举字段，避免幽灵枚举（§11.5 同源） |
| P4 | 财务风险项硬约束优先 | 重复付款类风险（重复发票）默认硬拦，override 需专用权限 + 强制留痕，不接受「软校验」 |
| P5 | 语义按处置而非按数量 | 质检/退货的折抵路径取决于**处置**（disposition），不取决于「拒收总量」 |

### 20.1 裁决总表

优先级：**P0** = 阻塞建表 / 匹配服务正确性；**P1** = 本波内必须定稿；**P2** = 后续波次。

| TBD | 议题 | 建议裁决 | 依据（产品 / 本平台） | 落点 | 优先级 | 签字人 |
|---|---|---|---|---|---|---|
| TBD-1 | 收货 `source_doc_type` 是否加 `service_entry` | **不加**。维持 `receipt.yaml` 五值；服务采购走 `purchase_order + schedule_kind='service'`，回写收货 Spec §10 删除 `service_entry` 表述 | SAP 服务确认（SES）最终仍落 PO 行；本平台 `receipt_line` 已挂计划行且 `schedule_kind` 已区分 service / physical（C）⇒ 新增来源值需同步 YAML / DB / 前端三处，违反单一事实源 | §10、§12.3、收货 Spec §10 | P1 | PM |
| TBD-2 | 参数维度缺 `supplier_account_id` / `item_id` | 本波**不扩**（物料组近似物料级、供应商级不启用）；下一波给 `control_parameter_value` 加 `supplier_account_id` + `item_id` 两列，用 **0 哨兵值**表示「不限」（SQLite 唯一索引对 NULL 不去重）；`specificity_rank` 排序扩为 **item+supplier > item > supplier > item_group > line_type > document_type > org** | D365 四级覆盖（法人 / 供应商 / 物料 / 物料+供应商）；NetSuite 物料级 `Match Bill to Receipt`；SAP `LFM1` 供应商级容差组；本平台已有 `specificity_rank` ⇒ 扩列为纯加法，但影响全平台所有参数解析 ⇒ 必须架构评审 | §5.3、§11.3、下一波迁移（不占 v250–v254） | P2 | 架构 |
| TBD-3 | 付款 / 预付 / `payment_block` 码表 | **本波删除 `payment_block` 字段**（「只留字段、不建码表」= 幽灵枚举，与 §11.5 自相矛盾）；付款波次统一建付款对象 + 冻结码对象，届期以 `payment_block_code` 回加；预付**不作为**发票类型（维持 N5） | Fusion 冻结在 `AP_HOLDS_ALL` 独立表；SAP 冻结码为独立码表（`T008`）且多字段并存；金蝶付款申请为独立单据。6/6 证明冻结属付款域对象，非发票头单值枚举 | §3.3（删行）、§3.3 不建字段表、§6.1、§6.2、§15 | P0 | PM（确认可延后） |
| TBD-4 | 税额计算与税码推导 | 本波 **manual**（行 `tax_amount` 直录）；接税务引擎时新增 nullable `tax_code_id` + **行级 `tax_rate` 快照**（不反查当前税率），`tax_amount` 保持快照语义；税码生效日校验链列下一波 | SAP 税由税码 `MWSKZ` 实时推导；Fusion 有独立税引擎；本平台无税域对象 ⇒ 快照符合 §11.2「单张单据内需冻结可落列」 | §4.2、§15 | P2 | 税务域负责人 |
| TBD-5 | `reversal_type_id` 链 | 定链：`VENDOR_INVOICE → VENDOR_CREDIT_MEMO`；`VENDOR_CREDIT_MEMO → VENDOR_DEBIT_MEMO`；`VENDOR_DEBIT_MEMO → VENDOR_CREDIT_MEMO`；`VENDOR_INVOICE_CANCEL → VENDOR_INVOICE`。强不变量：**反转类型 `direction` 必须与原类型相反**；默认发票类型 `reversal_type_id` 为空 | SAP 有 reversal reason + 反向凭证类型；Fusion credit/debit 互转；金蝶「对应蓝票」单向。v243 已有 `reversal_type_id` 列（C）⇒ 只需定链，无需新列 | §3.2、§15 | P1 | PM |
| TBD-6 | 多币种行（行币种 ≠ 头币种） | **不采纳，永久关闭**。行 `currency_id` 留空且必须等于头币种；若未来确需，必须整单按行币种 + 行汇率快照 + 行级容差重算，成本极高 | SAP（币种在 `BKPF-WAERS` 头级）、Fusion（`INVOICE_CURRENCY_CODE` 头级）、D365、NetSuite、金蝶 —— **6/6 家均头级** | §4.2（L261 改写）、§15 | P1 | 架构（确认关闭） |
| TBD-7 | 质检折抵口径（Fusion 4-way 第四单） | **当前口径有缺陷，修正**：`qty_invoiceable = qty_received − Σ qty_rejected(disposition ∈ {return_to_supplier, scrap})`；`concession`（让步接收）与 `rework`（返工后交付）**计入可开票**。独立质检单仍不建 | SAP 让步接收仍按收货计量可开票；Fusion 4-way 按 inspection accept/reject 分流；金蝶不建质检单、以入库量为准。本平台 `rejection_disposition` 四值已区分处置（C）⇒ 折抵必须按处置而非按 `qty_rejected` 整量 | §5.2、§10、§11.2；回写收货 Spec disposition 语义 | P0 | PM（业务口径） |
| TBD-8 | 重复发票检查 | **改为硬拦**（`posted` 前）。查重键 = `supplier_account_id + 规范化(supplier_invoice_no)`，**不含金额**（含金额则改金额即可绕过）；同一键允许一张 `draft` 暂存，`posted` 层唯一；override 需专用权限 `vendor_invoice:override_duplicate` + 强制 `duplicate_override_reason` + 审计。规范化 = 去首尾/内部空格与连字符、全角转半角、统一大写 | Fusion Duplicate Invoice 校验（Supplier + Invoice Num，硬拦 + 可配 allow）；D365 发票号唯一校验；SAP 参考码重复检查。软校验在应付侧是重复付款高风险 | §6.3 R-VI-14 改写、§12.2 权限、§15 | P0 | PM（硬拦 + override 归属） |
| TBD-9 | ERS 定时自动结算 | 本波只留 `settlement_mode ∈ {supplier_invoice, ers}`，**不实现**。下一波前置条件：① 计划行价格快照稳定；② 自动取号；③ 无供应商票号；④ 具备定时任务；⑤ 幂等键（`schedule_id + period`）防重复结算；⑥ 与收货 `posted` 事件解耦（按周期聚合） | SAP ERS 以「收货过账 + 信息记录价稳定」为前提自动结算；Fusion Self-Service Invoice 仍非全自动 | §10.2、§15 | P2 | PM |
| TBD-10 | 幽灵元数据 `AP_INVOICE / BO_AP_INV / BO_PAYMENT_REQ` | **全量删除**（不接真对象：真实对象是 `vendor_invoice`；`AP_PAYMENT` 属付款波次，不在本波）。删除清单见 §20.4 | §11.5；假对象会让权限矩阵 / 菜单出现「已支持」错觉；本波真实对象由 §3.2 单独种子 | W4 前置清理（v253 之前） | P0 | 本波实施者 |
| TBD-11 | `purchase_order_schedule.invoiced_qty` 缓存列 | **不加**（N3）。设性能门槛：`ap_match` 切片的 `doc_flow_edges` 边数 > 5 万或 `v_doc_flow_consumed_qty` p95 > 200ms 时才评估**物化视图**，仍不落实体列 | Fusion `quantity_billed` / D365 已开票数量确实落列，但依赖严格过账引擎与批量重算；本平台已有视图层 ⇒ 先测后优 | §11.2（补门槛）、§15 | P2 | 架构 |
| TBD-12 | 多套匹配 / 容差方案并存 + 单据级选择 | **不建「方案」对象**。用 `vi_match_mode` 参数多级解析 + TBD-2 维度扩展表达「按组织/类型/物料组/物料/供应商不同策略」；若未来确有单据级切换需求，再建 `match_profile` 头引用参数集，不预埋字段 | 金蝶把匹配关系/匹配方案/容差方案做成基础资料，是为承载**审批流 + 匹配单据**；本平台无匹配审批场景（D-VI-12）⇒ 方案对象是空壳 | §5.1、§15 | P2 | 架构 |
| TBD-13 | 并发匹配 TOCTOU 锁策略 | 匹配提交用 **`BEGIN IMMEDIATE`**（写前取 RESERVED 锁）→ 事务内重算剩余量 → 写边；**不加行级悲观锁**；`uq_doc_flow_idem` 冲突即整笔拒绝。视图仅展示，不承担锁语义。未来迁 PG 时等价替换为 `SELECT … FOR UPDATE`（按 `schedule_id`） | SQLite 单写者 + Waitress 多线程单文件库（C）⇒ 应用层锁只会引入死锁；SAP/Fusion 用 DB 行锁，语义等价 | §6.3 R-VI-18、§8、§15 | P0 | 架构 |

### 20.2 需业务（PM）签字项

| TBD | 签字内容 | 不签的后果 |
|---|---|---|
| TBD-3 | 确认本波**不建** `payment_block`，冻结能力延后到付款波次 | 发票头留幽灵枚举；付款波次还得再迁移一次 |
| TBD-5 | 确认 `reversal_type_id` 四条链 | 红冲方向错误（贷项冲成借项）无法在类型层拦住 |
| TBD-7 | 确认「让步接收 / 返工仍可开票」的业务口径 | 供应商少开票 → 应付漏记 → 后续补票对不上账 |
| TBD-8 | 确认硬拦 + `vendor_invoice:override_duplicate` 权限归属（财务主管？） | 重复发票进入付款；或过度拦截阻断正常红冲后重开 |
| TBD-1 / TBD-9 | 确认服务采购不新增来源类型；ERS 延后 | 收货 Spec 与实现分叉；ERS 半成品 |

### 20.3 需架构签字项

| TBD | 签字内容 | 影响面 |
|---|---|---|
| TBD-2 | `control_parameter_value` 扩 `supplier_account_id` + `item_id`（0 哨兵值）+ `specificity_rank` 新序 | **全平台**参数解析；需回归所有已用 `control_parameter_value` 的模块 |
| TBD-6 | 永久关闭多币种行 | 行字段语义冻结；未来若反悔需行级汇率快照迁移 |
| TBD-11 | 维持视图派生 + 性能门槛（5 万边 / p95 200ms） | 大客户场景性能需实测兜底 |
| TBD-12 | 不建 `match_profile` 对象 | 若后续接入匹配工作台，需另立波次 |
| TBD-13 | `BEGIN IMMEDIATE` 作为匹配事务起点 | 所有写 `ap_match` 边的事务必须统一走该入口 |

### 20.4 技术实施直接修正（无需签字，随 W1–W5 落地）

1. **TBD-7 派生口径**：匹配服务计算参考量时改用 `qty_invoiceable`（`qty_received − (return_to_supplier + scrap)`），不得直接用 `qty_received − qty_rejected`；§5.1 `gr_based` 校验量同步改口径。
2. **TBD-8 查重实现**：头表加**表达式唯一索引**或服务层查重（推荐服务层 + 规范化函数，便于 draft 暂存）；`posted` 转换处硬拦；`override_duplicate` 独立权限码进 W4。
3. **TBD-10 删除清单**（逐行核对后删，删完跑 `python scripts/lint_tests.py` + `test.py --failed`）：
   - `meta/scripts/init_and_seed.py`：`L300`（`AP_INVOICE` 菜单）、`L342`（`BO_AP_INV` 对象）、`L345`（`BO_PAYMENT_REQ`）、`L377`（`BO_AP_INV → AP_INVOICE` 映射）、`L380`（`BO_PAYMENT_REQ → AP_PAYMENT`）、`L425–427`（`BO_SUPPLIER → BO_AP_INV → BO_PAYMENT_REQ → BO_PAYMENT_VOUCHER` 链路）
   - `meta/scripts/generate_test_data.py`：`L242 / L275 / L278 / L304 / L307 / L358–360`
   - 同步全库检索 `AP_INVOICE|BO_AP_INV|BO_PAYMENT_REQ`，残留即失败（纳入 W4 验收）
4. **TBD-13 事务入口**：匹配服务统一以 `BEGIN IMMEDIATE` 开启事务；`uq_doc_flow_idem` 冲突 → 整笔回滚并返回可重试错误码，不做部分成功。
5. **TBD-4 预留**：行 YAML 保留 `tax_code_id`（nullable）+ `tax_rate`（nullable 快照），本波不启用校验链。

### 20.5 本平台裁决 vs 主流 ERP 的差异性质

| 议题 | 主流做法 | 本平台裁决 | 差异性质 / 理由 |
|---|---|---|---|
| 已开票量 | Fusion `quantity_billed`、D365 已开票数量**落列** | 视图派生（`doc_flow_edges`） | **有意差异**：落列依赖严格过账引擎；本平台以边为唯一事实，设性能门槛（TBD-11） |
| 匹配载体 | 金蝶「匹配单据 + 审批流 + 额度反写」 | 规则参数 + 服务事务 | **有意差异**：无匹配审批场景；反写即缓存（D-VI-14） |
| 匹配方案 | 金蝶基础资料可切换 | 不建对象，参数多级解析 | **有意差异**：方案对象是为审批与单据级切换服务（TBD-12） |
| 多币种行 | 6/6 家头级币种 | 禁止行级多币种 | **一致**（TBD-6 永久关闭） |
| 重复发票 | Fusion / D365 硬拦 + 可配放行 | 硬拦 + 专用 override 权限 | **一致**（TBD-8 由软改硬） |
| 质检第四单 | Fusion 独立 inspection | 不建单，按 disposition 折抵 | **有意差异 + 口径修正**（TBD-7：让步/返工可开票） |
| 付款冻结 | SAP 独立码表 + 多 hold；Fusion 独立表 | 本波不建，延后付款波次 | **方向一致**（TBD-3），仅时点不同 |
| 参数维度 | D365 供应商/物料四级；NetSuite 物料级 | 本波物料组近似，下一波扩展 | **暂时差异**（TBD-2） |
| 反向类型链 | SAP 反向凭证类型 + reason；金蝶对应蓝票 | `reversal_type_id` 四条链 + direction 相反不变量 | **一致**（TBD-5） |
| 并发控制 | DB 行锁（SAP/Fusion） | `BEGIN IMMEDIATE` + 幂等索引 | **语义等价**（TBD-13） |

### 20.6 本轮正文回写清单（已执行）

| 章节 | 修改 |
|---|---|
| §3.2 | `reversal_type_id` 四条链定稿 + direction 相反不变量（TBD-5） |
| §3.3 | 删除 `payment_block` 行；`hold_flags` 注记改为「冻结归付款波次」（TBD-3） |
| §4.2 | 行 `currency_id` 标注「多币种行不采纳，TBD-6 永久关闭」 |
| §5.1 | `gr_based` 校验量改为 `qty_invoiceable` 汇总（TBD-7） |
| §5.2 | 净收量口径改为按 `rejection_disposition` 折减（TBD-7） |
| §6.1 | `submitted → posted` 去掉 `payment_block` 条件，补重复票硬拦与 `BEGIN IMMEDIATE` |
| §6.2 | Park / Blocked 注记去掉 `payment_block` |
| §6.3 | R-VI-14 改硬拦 + 规范化 + override 权限；R-VI-18 补 `BEGIN IMMEDIATE` |
| §11.2 | 补性能门槛（5 万边 / p95 200ms → 物化视图） |
| §11.4 | 匹配模式声明位置修正为 `control_parameter_def` 的 `vi_match_mode`（原误写 `type_definitions` 列） |
| §12.2 | 新增 `vendor_invoice_override_duplicate` 动作 + 权限码（TBD-8） |
| §13 | W1 去掉 `type_definitions.invoice_match_mode` 列；W2 参数由 5 条改 6 条（`vi_match_mode` + 5 容差） |
| §14 | D2 改为「6 条参数」；D4 改为判 `qty_invoiceable` |
| §15 | 标题标注「已裁决，详见 §20」+ 指向 §20.1 的注记 |

### 20.7 签字通过后的实施入口

- W1 `v252` 建表（**不含** `payment_block`，含 `org_id` / `settlement_mode`）。
- W2 `v253` 种子：4 类型 + 4 序列 + **6 条参数**（`vi_match_mode`（`domain='procurement'`）+ `vi_price_tolerance` / `vi_qty_tolerance_receipt` / `vi_qty_tolerance_order` / `vi_amount_tolerance_abs` / `vi_rounding_tolerance_abs`）。
- W3 `v254` doc_flow 规则 + `v_doc_flow_consumed_amount`。
- W4 `v255` 动作 / 权限 / 菜单（**前置：TBD-10 幽灵元数据清理**；新增 `vendor_invoice:override_duplicate`；**不含**手工贷项 / 借项动作）。
- W5 **无迁移**：匹配服务（`qty_invoiceable` 口径 + `BEGIN IMMEDIATE` + 重复票硬拦）。
- W6 `v258` 红冲链（`reversal_reason` 列 + 类型反转指针回填 + 死权限清理）。

### 20.8 实施落地口径（W1–W6 已落盘）

| 项 | 落地口径 |
|---|---|
| 重复发票 override | 头表**不加** `duplicate_of_id` / `duplicate_override_reason` 列；override 写 `audit_logs`（`action='override_duplicate'`），过账时查询放行 |
| `doc_flow_edges.source_item` | attach 模式实际为空串 ⇒ 已开票量一律按 `(source_bo, source_id, pool)` 聚合，不按行精确匹配 |
| 冲销类单据（credit / debit / cancellation） | **禁止手工新建**：守卫拦截器在 create 阶段拒绝非草稿状态与 `credit_memo` / `debit_memo` / `cancellation`（`VI_MANUAL_ADJUSTMENT_FORBIDDEN`）；调整单改走正向调整单（Phase 2，未授权） |
| 贷项净额归零 | 不建 `vendor_invoice_line_to_credit_memo_line` 规则；对原发票行的 billing / ap_match 边写 `red_ink_edge`（`derive_key='red:{orig}:{ref}'`），`_red_available` 防超冲 |
| 红冲链（posted → reversed） | YAML `doc_effect.reversal` + `faces` 声明；`VendorInvoiceMatchService.reverse()` 事务外预取号 → `ReversalOrchestrator.execute` 自持事务 7 步；红字单类型由 `VENDOR_INVOICE.reversal_type_id`（v258 回填 → `VENDOR_CREDIT_MEMO`）派生，方向必须为 `-1` |
| 红冲守卫 | `_assert_reversible`：正向角色 + `direction=1` + 类型已声明反转 + `status='posted'` + 无有效红字单；原因必填（`VI_REVERSAL_REASON_REQUIRED`） |
| 容差超派生 | 写边时 `edge_qty = min(qty, open_qty)`，金额按比例缩放 |
| 双池双写 | post 同时写 billing（PO 计划行）+ ap_match（收货行）两条边，属设计意图（D-VI-10） |
| 事务 | 匹配提交 / 过账统一 `with ds.transaction()`（SQLite `BEGIN IMMEDIATE`）内重算剩余量；红冲由 ReversalOrchestrator 自持事务 |

> 本轮**不提交**（git commit 未授权）。

---

## 21. Phase 2：正向调整单（增减调整流程）

> 决策来源：§20.8「调整单改走正向调整单」。核心结论：**调整单是正向链上的新事实，不是对原票的行级负向冲减**。
> 逆向三档中，`cancel` / `reverse` 走 Orchestrator（负向补偿）；`return` / 调整 走正向链。本节只定义正向链。

### 21.1 语义定位

| 维度 | 红冲（credit_memo，Phase 1） | 调整单（Phase 2） |
|---|---|---|
| 事实性质 | 对原票的**负向补偿**（原票置 reversed） | **正向新单据**（原票保持 posted 不变） |
| 生命周期 | 引擎派生（red_letter creator），一步到 posted | 正常单据链 draft → submitted → posted |
| 状态归属 | 原票承担 `reversed` 终态 | 调整单自带状态；原票只读 |
| 数量口径 | 红字边 `quantity_sign='red'` 全额/部分冲减 | increase 写 normal 边追加；decrease 写 red 边冲减 |
| 撤销方式 | 无（终态） | 新建**方向相反**的反向调整单 |

不变量：
- **R-VI-20** 调整单必须回指一张 `status='posted'` 的原票（或已过账的调整单），原票任何字段不被修改。
- **R-VI-21** `adjustment_direction` ∈ {increase, decrease}，创建后不可变。
- **R-VI-22** 调整单**不声明** `doc_effect.reversal`；`posted` 后禁止 `status='reversed'`。
- **R-VI-23** increase 的行数量不得超过目标池 `open_qty`（严格拒绝，不截断）；decrease 不得超过原行边的 `_red_available`。

### 21.2 类型与编号

`v259` 新增（不动 v253 的历史 4 类型）：

| code | document_role | document_category | direction | is_default | sequence | reversal_type_id |
|---|---|---|---|---|---|---|
| `VENDOR_INVOICE_ADJUSTMENT` | `adjustment` | `adjustment` | `1` | `0` | `VIA` | **NULL** |

序列：`VIA`，`pattern='VIA-{DATE:yyyymm}-{SEQ:5}'`，`date_field='invoice_date'`。
`reversal_type_id` 为 NULL 是**设计意图**：调整单不能进入红冲引擎（§21.4）。

### 21.3 头字段（`vendor_invoices` 扩列）

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `adjustment_of_invoice_id` | integer | 是 | 回指原票 / 原调整单（`vendor_invoice.id`）；调整单必填 |
| `adjustment_direction` | string(10) | 是 | `increase` / `decrease`；调整单必填且不可变 |
| `adjustment_reason` | string(256) | 是 | 调整原因；调整单创建必填 |

金额口径：
- increase：行金额为**正数**，头金额 = Σ 行金额。
- decrease：行数量存**正数幅值**，行金额存**负数**（`-abs(amount)`），头金额 = Σ 行金额（负数）。
- `direction` 仍由类型派生为 `1`（文档方向），**不**用 `direction` 表达增减；增减只由 `adjustment_direction` 表达。

### 21.4 状态机与 `doc_effect`

- 复用 `draft → submitted → posted`，`draft|submitted → cancelled`。
- **不声明** `doc_effect.reversal`，因此 `ReversalOrchestrator` 无法对调整单执行红冲。
- 守卫拦截器：`category='adjustment'` 且 `status='posted'` 时，`status=reversed` 请求抛 `VI_ADJUSTMENT_NOT_REVERSIBLE`（提示新建反向调整单）。
- `vendor_invoice.yaml` 的 `doc_effect.faces` / `reversal` 保持 Phase 1 声明不变（仅对 invoice 角色生效）。

### 21.5 过账边语义（`post`）

| 场景 | 边类型 | 目标 | 数量校验 | 金额 |
|---|---|---|---|---|
| increase | **normal**（`attach_edge`） | 原行的 `purchase_order_schedule` / `receipt_line` 锚点 | `qty <= open_qty`，超出 → `VI_ADJUSTMENT_EXCEEDED` | 边 `amount` = 调整行 `net_amount`（边数量 = 行数量，无需再分摊） |
| decrease | **red**（`red_ink_edge`） | 原行该规则的**全部** active normal 边 | 先按 `Σ_red_available` 校验，超出 → `VI_ADJUSTMENT_EXCEEDED`；无 active 边 → `VI_ADJUSTMENT_ANCHOR_MISSING` | 同上（负数金额写正数 quantity + `quantity_sign='red'`） |
| qty=0 | 不写边 | — | 纯金额调整（如价格差异） | 仅头/行金额变化 |

- 行金额口径：`lines[]` 只给 `qty` 未给 `net_amount` / `tax_amount` 时，按**原行数量比例**折算金额（`net × qty/qty_原行`），避免「数量是部分、金额是全额」的口径失衡。
- decrease 分摊：同一原行可能因 increase 产生多条 normal 边（分属多条计划行），按 `rowid` FIFO 依次冲减直至满足本次冲减量；校验用累计可用量而非单边可用量。
- 原票边**永不**被 update/delete；decrease 通过新增红字边使 `_red_available` 归零，语义与 Phase 1 红冲一致。
- increase 的 open 量按 `(source_bo, source_id, pool)` 聚合后减去该行的已开票量（含红字抵扣），复用 `v_doc_flow_consumed_amount`。

### 21.6 行模型与 `line_source_policy`

- 调整行**必须**携带 `invoice_line_id` 回指原行；锚点（schedule / receipt）在 `_normalize_line_anchors` 中从**原行**解析，不重复落库到调整行。
- `line_source_policy.adjustment` = `[invoice_line]`（仅允许回指原行；不允许 `manual`，也不允许直接挂 PO/收货锚点）。
- 行 create/update 守卫：父单为 adjustment 且 `invoice_line_id` 为空 → `VI_ADJUSTMENT_ANCHOR_REQUIRED`。
- 调整行不参与数量/价格容差匹配（`_match_line` 与 credit_memo 同组直接置 matched）。

### 21.7 权限与动作

| 动作 | 权限 | 治理 | 幂等 | 说明 |
|---|---|---|---|---|
| `vendor_invoice.create_adjustment` | **复用** `vendor_invoice:create` | audit | 否 | 入参 `invoice_id` / `direction` / `reason` / `invoice_date?` / `lines?` |

- 不新增 DB 权限码：调整单属于发票创建能力的变体，避免 `permission_set_permissions` / 菜单绑定迁移风险。
- 无独立「调整单列表」菜单；通过 `document_category=adjustment` 过滤查看（list filters 已含 `document_category`）。
- UI 入口（2026-11-12 修复）：`ui_view_config.detail.actions` 已全链路透传
  （`UIDetailViewConfig.actions` → `parse_ui_detail_view_config` → `/api/v2/meta/<obj>/ui-config`；
  form 不可渲染时 `UIConfigBuilder` 的整体替换分支也保留声明的 `detail.actions`）；
  详情页按 `permission` / `visible_when` 门控，声明 `input_fields` 的动作先弹 `AppModal` 收集参数再派发 BO Action。
  通用派发默认只带 `source_doc_id`，handler `_invoice_id` 已兼容。
- 已声明动作：`match` / `override_match` / `override_duplicate` / `create_adjustment`；
  四个动作**均**带 `visible_when`（`override_duplicate` 此前缺失，已补 `status in ['draft','submitted']`）；
  `create_adjustment` 仅 `status == 'posted'` 可见，入参 `direction`（increase / decrease，必填）+ `reason`（必填）。
- 平台通用编辑入口（2026-11-12 修复）：`DetailPage` 默认「编辑」按钮不再无条件渲染，
  改为 `authStore` 权限（`{bo}:edit` / `{bo}:update`，管理员直通）+ 单据状态双门控；
  状态枚举含 `draft` 的对象仅草稿可编辑，已提交/已过账只能走业务动作。
- 单据流追溯面板（2026-11-12 修复）：规则只声明到行级（`vendor_invoice_line`），
  头级详情页的 `docFlowMatched` 改为「等于或 `<bo>_` 前缀命中」判定；
  `DocFlowTracePanel` 按 `/doc-flow/edges` 实际响应 `{items,total}` 读取（此前读不存在的 `.edges`，恒空）。
- 新建表单不再可选调整单类型：`document_type_id` 的 `value_filter` 增加
  `code__notin: [VENDOR_INVOICE_ADJUSTMENT]`（调整单只能由 `create_adjustment` 生成，
  其必填字段在表单中 `hidden_in_form`，直选必保存失败）；服务层创建调整单走直插，不受该过滤影响。
- `direction` 补齐静态 `enum_values`（1 正向 / -1 负向），详情页与列表按标签显示；
  列表列补 `document_type_id` / `direction`。

### 21.8 明确不做（边界）

- 不做行级红冲（不写 `reversal_of_line_id`，不对原行做负向冲减）。
- 不做调整单自身的红冲（撤销 = 新建反向调整单，即对调整单建 `decrease` 调整单，红字冲减其入边）。
- 不支持对调整单再 `increase`（调整行不落锚点列，过账无法解析订单/收货锚点；需要继续加量请对原发票行做 `increase`）。服务层与守卫均在创建期拒绝，规则码 `VI_ADJUSTMENT_INCREASE_UNSUPPORTED`。
- 不支持调整单跨供应商 / 跨币种 / 跨 org（头字段全部从原票复制）。
- 不支持调整单修改数量以外的价格模型重算（价格差异用 qty=0 的纯金额调整表达）。

### 21.9 迁移与测试（W7 = v259）

| 项 | 内容 |
|---|---|
| 迁移 | `v259__vendor_invoice_adjustment.py`：三列 ALTER（PRAGMA 幂等）+ 索引 `idx_vendor_invoice_adjustment_of`（旧库升级不执行 generated_schema，索引须在迁移内建）+ 类型 `VENDOR_INVOICE_ADJUSTMENT` + 序列 `VIA` |
| `verify` | 列存在；索引存在；类型 code/category/role/direction 正确且 `reversal_type_id IS NULL`；序列存在且 pattern 正确 |
| `rollback` | 删索引 → 删序列 → 删类型 → 清三列值（不 DROP COLUMN） |
| 服务 | `create_adjustment()` / `_write_adjustment_increase_edges()` / `_write_adjustment_decrease_edges()`；`_insert_lines(..., negate=False)` |
| 守卫 | create 校验原票 posted / 方向 / 原因；posted 拒绝 reversed；行必须回指原行 |
| 平台修复 | `UIDetailViewConfig.actions`（此前缺字段，YAML `detail.actions` 加载即丢弃）+ `parse_ui_detail_view_config` 解析；`UIConfigBuilder` 兜底替换时保留声明动作（此前只保留 `hub`）；`DetailPage` 映射 `confirm_message` / `input_fields` 并用 `AppModal` 收集入参；`vendor_invoice_actions._invoice_id` 兼容 `source_doc_id` |
| 平台测试 | `test_yaml_loader.py::TestDetailViewActionsParsing`（解析 + 真实 YAML 声明）、`test_bo_api.py::TestBoAPIV2Meta::test_ui_config_exposes_detail_actions`（接口下发）、`test_ui_config_enhanced.py::TestUIConfigBuilderDeclaredDetailActions`（兜底分支保留 / 不误加）、`test_vendor_invoice_match.py::test_match_handler_accepts_source_doc_id`（派发定位）、`test_bo_api.py::TestBoAPIV2Meta::test_vendor_invoice_ui_fixes_exposed`（2026-11-12：`direction` 枚举 / `override_duplicate.visible_when` / 调整单排除 / 列表列 随 ui-config 下发） |
| 测试 | `meta/tests/test_vendor_invoice_adjustment.py`（创建 / increase 边 / decrease 红边 / 超额拒绝 / 无锚点 / 原票只读 / 状态机 / 不可红冲 / 仅数量覆盖按比例折算金额 / 多边 FIFO 分摊） |

### 21.10 与逆向三档的最终对照

| 档 | 触发 | 原票状态 | 补偿载体 | 落地方案 |
|---|---|---|---|---|
| `cancel` | 草稿/已提交撤销 | → cancelled | 无（未过账） | 既有状态迁移 |
| `reverse` | 已过账全额红冲 | → reversed | 红字单（引擎派生） | Phase 1，`doc_effect.reversal` |
| `return` / 调整 | 已过账部分增减 | **保持 posted** | **调整单（正向新事实）** | Phase 2，本节 |