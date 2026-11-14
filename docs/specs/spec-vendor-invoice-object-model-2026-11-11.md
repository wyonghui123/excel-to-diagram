# 采购发票对象模型 Spec（Vendor Invoice Object Model）

> 版本：v1.10 草案（2026-11-14 W11-2 已实施：R-VI-51 / R-VI-52 / R-VI-53 + v273 `v_vendor_return_open_amount`；v1.9 追加 §25.11 规则模型落位与 SSOT 收敛；2026-11-14 追加 §25 端到端 / 逆向 / 异常一致性补强：R-VI-48 ~ R-VI-59，并修订 R-VI-36；v1.7 于 2026-11-14 W10-1 已实施：R-VI-38 ~ R-VI-47 + 枚举收敛；v1.6 于 2026-11-14 追加 §24 三单匹配补强；v1.5 于 2026-11-14 落实施 §23.9 方案 A；v1.4 于 2026-11-13 追加 22.6.2 费用变更与单一事实源约束 / R-1~R-4 / 变更矩阵 A~D；v1.3 同日追加 22.6.1 费用分摊方案 / D-CH-01~12；v1.2 于 2026-11-12 §22 细化，金额计算改为复用统一内核 `SalesOrderAmountService`，D-VI-27）｜ 日期：2026-11-11 ｜ 状态：待评审（§23 已实施，2026-11-14；§24 W10-1 已实施，2026-11-14；§25 W11-1 已实施，2026-11-14；§25 W11-2 已实施，2026-11-14；§25.11 SSOT 收敛已实施，2026-11-14；其余待评审）
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

> 金额计算（行 / 头公式、舍入、税、运费）、价格变更矩阵与新增不变量 **R-VI-24 ~ R-VI-33** 见 **§22**（2026-11-12 细化追加）；R-VI-6 / R-VI-7 以 §22.2 / §22.3 为准；金额算术统一复用 `SalesOrderAmountService`（D-VI-27）。

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
| TBD-14 | 是否与 PO 行税额比对 | 本波**不比对**，仅预留 `vi_po_tax_compare`（默认 `false`）；开启后按行 `tax_amount` 与 PO 行税额差 > `vi_tax_tolerance_abs` 置 `exception` | 税额差异多数来自税率快照时点不同，先积累数据再定口径 | §22.7、§22.10 | P3 | PM |
| TBD-15 | `customer_invoice_service` 金额逻辑未复用统一内核 | **本波不改**；登记为已知不一致，后续独立波次收敛到 `SalesOrderAmountService`（补齐含税价倒算与 `rounding_diff` 口径），与 VI 同源 | SO/PO 已统一在该内核，CI 自带舍入与抬头合计 ⇒ 同一平台存在两套金额口径，长期会漂移 | §22.1（销售侧对照）、§22.14 D-VI-27 | P2 | 架构 |

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
- 调整行金额必须由计算层按 §22.2 重算（T1 数量 / T2 价格 / T3 纯金额，见 §22.5），不允许只改 `unit_price` 不改金额。

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

- 行金额口径：`lines[]` 只给 `qty` 未给 `net_amount` / `tax_amount` 时，按**原行单价 × 新数量**重算净额、按**原税率**重算税额（§22.5 T1），避免「数量是部分、金额是全额」的口径失衡；`tax_rate_percent` 缺失时按原行税额比例缩放并做容差校验。
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
- 不按定价模板重新取价（发票侧只对位快照，§22.4）；价格差异二选一表达：① 调整行显式给 `unit_price` 并按 §22.2 重算（T2）；② `qty=0` 的纯金额调整（T3）。**不再**限定「只能改数量」（D-VI-25）。

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

---

## 22. 采购金额与费用计算契约（细化，2026-11-12 追加）

> 本节是 §4 / §5 / §6 / §11 / §21 的**实施级细化**，不改变对象骨架与已裁决事项；与本节冲突处以本节为准（冲突清单见 §22.15）。
> 输入：2026-11-12 对采购侧「定价模板 / 价格配置 / 价格与金额变更 / 计划外运费 / 税 / 金额计算」的代码审查结论（16 条缺口，记 `G-1 ~ G-16`）。

### 22.0 缺口 → 条款映射

| # | 缺口（审查结论） | 级别 | 落点 |
|---|---|---|---|
| G-1 | 行 / 头金额无服务端重算链路（前端只读、后端不计算 ⇒ 金额恒 0 仍可过账，边 `amount=0`） | P0 | 22.1 / 22.2 / 22.3 / R-VI-24~26 |
| G-2 | 含税单价未参与价格匹配；行无税率快照，无法折算 | P0 | 22.2 / 22.4 / 22.7 / R-VI-27 |
| G-3 | 写边 `min(qty, open_qty)`、`min(qty, available)` 静默截断 | P0 | 22.8 / R-VI-28 |
| G-4 | 调整单改 `unit_price` 不重算金额（net/tax 取源金额 × 比例） | P1 | 22.5 / R-VI-31 |
| G-5 | 可开票量基数不一致（match 扣退货、写边不扣；`gr_based` 无退货来源） | P1 | 22.8 / 22.10 |
| G-6 | `match_mode` / `match_pricing_mode` 无参数解析，模式实际恒定 | P1 | 22.8 / 22.10 |
| G-7 | `receipt_price` 模式伪造 override | P1 | 22.4 |
| G-8 | 计划外运费 / 附加费无承载 | P1 | 22.6 |
| G-9 | R-VI-3 锚点回填条件化（`if not result.get`）、API 可注入 `po_unit_price` | P2 | 22.4 / 22.8 / R-VI-27 |
| G-10 | 供应商 / 币种校验可被空锚点绕过 | P2 | 22.8 |
| G-11 | 税：`tax_amount` 可编辑无校验、无税率、无 PO 税额比对 | P2 | 22.7 |
| G-12 | 舍入：`rounding_diff` 恒 0、`round(...,2)` 绕过币种精度 | P2 | 22.2 / 22.3 / R-VI-26 |
| G-13 | 红冲与调整并存无互斥检查；红边只取末条 active 边 | P2 | 22.5 / 22.8 |
| G-14 | 定价不可追溯（行无 `price_source` / `price_trace`） | P3 | 22.4 |
| G-15 | 调整单 `direction=1` + 负金额可能双重取负 | P3 | 22.5 |
| G-16 | 调整行 `unit_price` 与 `net_amount` 不同步；`qty=0` 纯金额行可能被跳过 | P3 | 22.5 |

> 编号约定：本节 `G-1 ~ G-16` 只属 2026-11-12 的金额/费用审查；2026-11-14「端到端 / 逆向 / 异常」复盘另行发现 12 条缺口，改用 `E2E-* / REV-* / EXC-*` 前缀，**不复用** `G-*`，清单见 §25.0。

### 22.1 三层计算链与唯一入口

| 层 | 载体 | 职责 | 禁止 |
|---|---|---|---|
| 输入层 | YAML `ui.editable` | 只暴露业务可改字段（`qty` / `unit_price` / `price_includes_tax` / `tax_rate_percent` / `tax_code_id` / 调整行金额） | 前端不得做任何金额换算 |
| 计算层 | **复用统一金额内核** `meta/services/sales_order_amount_service.py` 的 `SalesOrderAmountService`（模板方法：算术在内核，加载 / 写回由钩子注入） | 行 / 头金额、差额、税校验 | 禁止新建第三套金额算术；禁止在 handler / interceptor / 前端复制公式 |
| 汇总层 | `vendor_invoice_match_service` | 在 create / update / match / submit / post / 调整 / 红冲复制处调用计算层并落库 | 禁止跳过计算层直接写金额列 |

复用方式（新增薄子类，算术零复制，与 `purchase_order_guard_service._PurchaseOrderAmountService` 同一先例）：

```python
class VendorInvoiceAmountService(SalesOrderAmountService):
    """VI 专属口径；算术全部继承内核。"""
    # 覆写：_load_line / _load_order / _sum_lines / _write_line / _write_order（表名不同）
    # 覆写：_line_amounts(...)    ← 新增钩子，支持含税价倒算 / line_direct
    # 覆写：_header_amounts(...)  ← 新增钩子，支持 supplier_gross_amount / rounding_diff
```

内核最小扩展（**只加两个可覆写钩子，默认实现 = 现行 SO/PO 口径，零回归**）：

```python
def _line_amounts(self, *, qty, unit_price, price_includes_tax,
                  tax_rate_percent, tax_rounding, decimals) -> dict:
    # 默认：net = R(q×p)；tax = R(net×r/100)；gross = R(net+tax)
    # VI 覆写：22.2 路径 B（含税价倒算）+ line_direct（税额直录 + 容差校验）

def _header_amounts(self, *, sum_net, sum_tax, sum_gross, supplier_gross,
                    decimals, rounding_tolerance) -> dict:
    # 默认：R(Σ 行)
    # VI 覆写：追加 supplier_gross_amount / rounding_diff / 头恒等式校验
```

> **销售侧对照（C）**：SO / PO 侧已统一在该内核上 —— `sales_order_pricing_service`、`sales_order_header_discount_service`、`sales_order_expand_service`、`sales_order_guard_interceptor` 直接持有内核；`purchase_order_guard_service._PurchaseOrderAmountService` 用子类覆写四张表的加载 / 写回。**唯一例外**是 `customer_invoice_service`（自带舍入与抬头合计，未接内核），属已知不一致，见 TBD-15，本波不改。

触发点矩阵：

| 触发 | 必须重算 | 说明 |
|---|---|---|
| 行新增 / 修改 / 删除 | 该行 + 头 | `draft` / `submitted` 允许；`posted` 禁止直改（22.5） |
| `match` | 行 `price_diff_*` / `qty_over_receipt` | 匹配只读金额，不改金额事实 |
| `submit` / `post` | 全量行 + 头 | 过账前最后一次校验并落库（R-VI-18 同事务） |
| 调整单创建 | 调整行 + 调整头 | 见 22.5 |
| 红冲复制 | 复制行取负 + 头 | 仅符号翻转，不重算（R-VI-9） |

约束：

1. 算术方法必须**幂等**：同输入同输出。DB 访问只允许经 `_load_*` / `_write_*` 钩子，算术方法内禁止查询。
2. 币种精度一律由内核 `_currency_decimals()` 获取（真源 `currencies.decimal_places`，`currency.yaml` 已注明），禁止硬编码 2 位。
3. 禁止 `if not value: value = computed` 式「有值不覆盖」回填；`editable: false` 字段一律**覆盖写**（G-9）。
4. `direction` 不进入行级公式；行金额符号由红字复制 / 调整方向决定（22.5）。
5. 计算层错误一律抛业务异常（`VendorInvoiceError`），不返回「部分结果」。
6. **禁止新增第三套金额算术**（R-VI-33）：任何新的金额需求一律「内核 + 子类覆写钩子」，不得复制公式到新文件或 handler。

### 22.2 行金额公式（唯一口径）

符号：`q` 数量、`p` 单价、`pit` 含税标记（0/1）、`r` 税率（%）、`d = currencies.decimal_places`、`R(x) = round_amount(x, d)`。

| 路径 | 条件 | `net` | `tax` | `gross` |
|---|---|---|---|---|
| A 不含税价 | `pit = 0` | `R(q × p)` | `rate_calc`：`R(net × r / 100)`；`line_direct`：用户直录 | `R(net + tax)` |
| B 含税价 | `pit = 1` | `R(gross / (1 + r / 100))` | `R(gross − net)`（**吸收项**） | `R(q × p)` |

规则：

1. **行恒等式**：落库后必须满足 `gross_amount = net_amount + tax_amount`（R-VI-24）；任何差额一律吸入 `tax_amount`。
2. **舍入唯一入口** `round_amount`（`meta/core/rounding.py`）：禁止 `round(x, 2)`、禁止中间值预舍入；全精度计算，最后一步才 `R`（R-VI-26 / G-12）。
3. 路径 B 缺 `r`（`tax_rate_percent` 空且税码无税率）→ `VI_TAX_RATE_REQUIRED`，不得静默按 0 处理。
4. `line_direct` 模式（TBD-4 现行口径）：`tax_amount` 可录入，但必须满足 `|tax − R(net × r / 100)| ≤ vi_tax_tolerance_abs`，否则 `VI_TAX_MISMATCH`（R-VI-30）。
5. `q ≥ 0`（R-VI-32）；负向只由红字复制 / `adjustment_direction` 表达，禁止负数量。
6. 匹配用价格归一（不改落库单价）：`price_ex_tax = p`（`pit=0`）或 `p / (1 + r / 100)`（`pit=1`）。
7. `price_diff_amount = R((price_ex_tax − po_unit_price) × q)`；`price_diff_percent` 保留 4 位，仅展示口径。

### 22.3 头金额与 `rounding_diff`

| 字段 | 公式 | 说明 |
|---|---|---|
| `net_amount` | `R(Σ net_i)` | 行已舍入，`R` 幂等 ⇒ 等于 Σ |
| `tax_amount` | `R(Σ tax_i)` | 同上 |
| `gross_amount` | 有 `supplier_gross_amount` → 取其值；否则 `R(Σ gross_i)` | 供应商原件总额优先（业务事实） |
| `rounding_diff` | `R(gross_amount − net_amount − tax_amount)` | 无 `supplier_gross_amount` 时恒 0 |

- 头恒等式：`net_amount + tax_amount + rounding_diff = gross_amount`（R-VI-25）。
- 舍入差容差：`|rounding_diff| > vi_rounding_tolerance_abs` → `match_status='exception'`，原因 `VI_ROUNDING_DIFF_EXCEEDED`，需 `override_match` 方可过账。
- 新增头字段 `supplier_gross_amount`（22.11）；为空表示「以行为准」。
- 头级 `net_amount / tax_amount / gross_amount` 维持 `editable: false`，不接受前端直写。
- `supplier_gross_amount` 与 `gross_amount` 同符号口径（红字为负）。

### 22.4 定价模板与价格配置（发票侧只快照、不取价）

| 环节 | 归属 | 发票侧行为 |
|---|---|---|
| 定价模板匹配（`pricing_determination_service` / `purchase_pricing_service`） | PO 侧 | **不重跑**；发票只引用 PO 行快照 |
| 价格来源 | `purchase_order_line.unit_price`（不含税） | 复制到行 `po_unit_price`（只读） |
| 价格来源优先级 | ① PO 行快照 → ② 人工录入（`manual`） | `receipt_price` 本波**禁用** |
| 追溯 | PO 侧已写 `price_source` / `price_trace` | 发票行复制同名两列（只读） |

行字段语义（新增列见 22.11）：

| 字段 | 写入方 | 语义 |
|---|---|---|
| `po_unit_price` | 服务端 | 锚点 PO 行单价快照；API 入参一律剔除（R-VI-27 / G-9） |
| `price_source` | 服务端 | `po`（默认）/ `manual`（人工行）/ `adjustment`（调整单继承原行） |
| `price_trace` | 服务端 | JSON 快照 `{po_id, order_line_id, schedule_id, po_unit_price, price_source, snapshot_at}`；PO 侧 `price_trace` 存在时整段嵌入 |
| `tax_rate_percent` | 服务端 | 税率快照（%），取值 22.7；含税价行必填 |
| `price_includes_tax` | 用户（0/1） | 单价含税标记，写入后参与 22.2 / 22.8 归一 |

匹配模式 `match_pricing_mode`（**修订 §5.4**）：

| 取值 | 价格比对 | 本波状态 |
|---|---|---|
| `po_price` | 归一后不含税单价 vs `po_unit_price`，超 `vi_price_tolerance` → `exception` | 默认，启用 |
| `manual` | 不比对价格；必须 `override_match` + `override_reason='manual_pricing_required'` | 启用 |
| `receipt_price` | 无收货价可依（D-RC-9 / N4） | **禁用**：选择即 `VI_PRICING_MODE_UNSUPPORTED`，**不再伪造 override**（G-7 / D-VI-22） |

- `match_pricing_mode` 由控制参数 `vi_match_pricing_mode` 解析（22.10）；同一单据内价格来源必须一致，否则 `exception`。
- 发票侧**不新增** `price_list_id`：采购价格清单属于 PO 承诺（D-VI-26）。

### 22.5 价格与金额变更矩阵

可改范围（按状态）：

| 状态 | 改 `qty` | 改 `unit_price` | 改税码 / 税率 | 纯金额（`qty=0`） | 增 / 删行 | 载体 |
|---|---|---|---|---|---|---|
| `draft` | ✅ | ✅ | ✅ | ✅ | ✅ | 直接编辑 → 重算 |
| `submitted` | ✅ | ✅ | ✅ | ✅ | ✅ | 直接编辑 → 重算 |
| `posted` | ❌ | ❌ | ❌ | ❌ | ❌ | 只能调整单 / 红冲 |
| `cancelled` / `reversed` | ❌ | ❌ | ❌ | ❌ | ❌ | 终态 |

调整单三种表达（**修订 §21.8 末条**）：

| 类型 | 输入 | 计算规则 |
|---|---|---|
| T1 数量调整 | 只给 `qty` | 单价沿用原行 `unit_price`；`net = R(qty × unit_price)`；税按 22.2 路径 A；`tax_rate_percent` 缺失时按原行税额比例缩放并做容差校验 |
| T2 价格调整 | 只给 `unit_price`（`qty` 缺省取原行） | 必须按 22.2 全量重算 `net / tax / gross`；**禁止**只改 `unit_price` 不改金额（G-4 / R-VI-31） |
| T3 纯金额调整 | `qty=0` + 直接给 `net_amount`（可选 `tax_amount`） | `net` 采用输入；`tax` 未给则 `R(net × r / 100)`；`gross = R(net + tax)`；`line_direct` 下按 22.7 校验 |
| 组合 | `qty` + `unit_price`（+ 可选 `tax_rate_percent`） | 按 22.2 重算并覆盖输入 |

规则：

1. 调整行同样满足行恒等式（R-VI-24）；`unit_price` 与 `net_amount` 由计算层同步写入（G-16）。
2. `qty=0` 且 `net_amount=0` 的调整行 → `VI_ADJUSTMENT_EMPTY_LINE`（禁止空行占位，G-16）。
3. decrease 符号沿用 §21.3：数量存正数幅值、金额取负；`direction` 固定 `1`，**不得**再按 `direction` 乘 -1（G-15）。
4. 红冲与调整互斥（G-13）：原票存在 active 调整单时，红冲前必须先将其 decrease 清零，否则 `VI_ADJUSTMENT_PENDING`；原票 `reversed` 后调整单不可再 `increase`。
5. 调整单不重跑定价模板；价格差异用 T2 / T3 显式表达（D-VI-25）。

### 22.6 计划外运费与其他费用

**承载方式（D-VI-21）**：费用以**费用行**表达，不新增头级费用字段、不建费用表。

行类型种子（`type_definitions`，`scope_bo='vendor_invoice'`，`level='line'`）：

| code | 名称 | 行性质 | `qty` | `unit_price` | 税 |
|---|---|---|---|---|---|
| `VI_LINE_GOODS` | 物料行 | 正常（默认） | 实收量 | PO 快照 | 按 22.7 |
| `VI_LINE_SERVICE` | 服务行 | 正常 | 服务量 | 合同价 | 按 22.7 |
| `VI_LINE_FREIGHT` | 运费行 | 费用 | 1 | 运费金额 | 必填税码 |
| `VI_LINE_SURCHARGE` | 附加费行 | 费用 | 1 | 附加费金额 | 必填税码 |
| `VI_LINE_DISCOUNT` | 折扣行 | 费用（负向） | 1 | 负数金额 | 按税码 |

规则：

1. 费用行判定 = `line_type.code ∈ CHARGE_LINE_TYPE_CODES`（服务常量，**不新增物理列**）。
2. 费用行**不写 doc_flow 边**（无 PO 锚点、不占采购量），金额只进头（R-VI-29）。
3. 费用行豁免数量匹配（`qty_over_receipt = 0`）；价格容差改用绝对额 `vi_freight_tolerance_abs`。
4. 费用行仍参与头金额与税校验；`schedule_id` / `receipt_line_id` 必须为空；**非费用行**两锚点全空 → `VI_ANCHOR_REQUIRED`。
5. PO 对账：PO 头 `header_surcharge_amount`（或 `header_discount_amount`）非 0 时，发票费用行合计与其差额超 `vi_freight_tolerance_abs` → `exception`，原因 `VI_FREIGHT_OVER_TOLERANCE`；**不自动分摊**到物料行。
6. 费用 → 物料行 / 入库成本的分摊**本波不实现**；方案、波次边界与硬约束见 **22.6.1**（W8）；变更语义与单一事实源约束见 **22.6.2**。
7. 调整单：费用行可 increase / decrease（T2 / T3），但不写边，故 decrease 不做 `Σ_red_available` 校验。
8. 红冲：费用行随头一起取负复制。

#### 22.6.1 费用分摊方案（下一波，D-CH-01~12）

> 本节固化 §22.6 规则 6 的方案。依据：`采购费用分摊-Fusion研究与落地建议-2026-11-13.md`、`采购费用分摊-SAP研究与三方对比-2026-11-13.md`（SAP MM 条件技术 + MIRO unplanned delivery costs；Oracle Fusion AP 费用行分摊 + LCM）。
> **W6 不实现本节**：W6 只做费用行承载与 PO 对账（22.6 规则 1~5、7、8）；分摊归 **W8**，与成本域协同。
> 复用现有引擎：`meta/services/allocation_service.py`（`AllocationService.plan / plan_floor / allocate_by_rule / record_allocation_results`）+ `allocation_results` 留痕表；**不新建分摊引擎、不新建分摊表**。

##### 22.6.1.1 外部机制 → 本项目落点

| 外部做法 | 本项目落点 | 明确不做 |
|---|---|---|
| SAP Planned Delivery Cost（PO 条件类型，收货即记账） | 仅以**参考成本视图**表达（D-CH-11） | 不做应计 / 清算科目（D-CH-10） |
| SAP Unplanned Delivery Cost → 按**发票行价值**摊到物料行 | 费用行 → `allocate_by_rule` → 同发票物料行 | — |
| SAP Unplanned → 单独 G/L 科目（不借记库存） | `allocation_rules.target = expense` + 行 `expense_account_code` | 不产出凭证 |
| SAP account key / OBYC 科目映射、MR11 价差 | —— | 总账域能力，P3 明确取消 |
| SAP GTS 关务 landed cost（`/SAPSLL/LEGAL_CUS_TLC`） | —— | 域外 |
| Fusion AP 费用行 Allocate All / Specific Lines | P1 全摊；P2 支持按行子集 | — |
| Fusion LCM 四基数（Quantity/Value/Volume/Weight） | 沿用 `allocation_rules.basis` 六基数（已有） | 不新增基数 |

> 负向结论（证据缺口已声明）：S/4HANA 核心采购**不存在**独立 "Landed Cost" 应用/对象。P3 成本域由"待研究"改判为"**已确认不必做**"。

##### 22.6.1.2 波次边界

| 波次 | 范围 | 不做 |
|---|---|---|
| W6（已定） | 费用行承载、头金额与税、PO 对账容差 | 不产出 `allocation_results` |
| **W8-P1** | 同宿主单据内：宿主发票的费用行摊到**同发票物料行**；`basis ∈ {value, quantity, weight, volume, equal, manual}`；`target ∈ {cost, expense}` | 跨单据来源；费用行作目标；入库成本重估 |
| W8-P2 | 跨单据来源（运费商发票 → 货物单据 / 收货行）；显式行子集；参考成本视图 | 会计落点；存货计价 |
| P3（取消） | —— | account key / OBYC / 清算科目 / landed cost 对象 / GL 凭证 |

##### 22.6.1.3 决策表

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| D-CH-01 | 费用以**行**承载，不新增头级费用字段、不建费用表 | 头级 `freight_amount` | 沿用 D-VI-21；金额天然进 Σ 行 |
| D-CH-02 | 分摊一律走 `AllocationService.allocate_by_rule`，**禁止单据侧自写算法** | 发票侧内联分摊 | 引擎已覆盖六基数 / 取整 / floor / 留痕，销售侧已有先例 |
| D-CH-03 | 默认基数 `value`；`basis_field ∈ {net_amount, gross_amount}`，**两值都可用且必须快照进留痕** | 写死 `net_amount` | 不可抵扣进项税时 SAP 按含税毛额摊（F/S 双证据）；写死会系统性少摊税额部分 |
| D-CH-04 | 摊痕（`allocation_results`）与行分摊额（派生列）**分离** | 只留痕 / 只落列 | 查询性能 + 可回放 |
| D-CH-05 | 分摊**不改变**发票 / PO 金额校验，只做归属 | 分摊后重算头金额 | 避免破坏三单匹配与容差口径 |
| D-CH-06 | 重摊把旧结果置 `invalid`，**永不物理删除** | 先删后写 | 成本调整需历史比例 |
| D-CH-07 | **来源可跨，目标不可跨**：`source_document_type/id` 可指向另一张单据（如独立运费发票、另一供应商）；摊入行必须属于宿主单据 | 全部禁止跨单 / 全部放开 | SAP 支持运费付给另一供应商；目标跨单则爆炸半径不可控 |
| D-CH-08 | 若未来开 accrue-at-receipt，分摊只做成本调整，**不重复确认费用** | 分摊即确认费用 | 对齐 Fusion 官方语义 |
| D-CH-09 | `origin` 判定 = **宿主单据上是否存在该费用的金额锚点**（PO 头/行有 → `planned`；只来自发票费用行 → `unplanned`）；**禁止**按录入人/录入界面判定 | 按录入界面判定 | SAP 二分依据是"金额在采购时点是否已知"，与 `origin` 既有注释（业务语义非管线标识）一致 |
| D-CH-10 | 分摊**只产出归属金额**，不产出会计落点；"进存货 / 进价差 / 进独立科目"一律**不进** `allocation_results`，不新增 GL 字段 | 留痕中带科目与存货标志 | 本项目无物料计价与总账，硬建模会得到"有值但错值"的列 |
| D-CH-11 | 参考成本口径固定 `单价 × 数量 + 分摊费用`，以视图/计算列表达；**不参与校验、不入账、不写业务字段** | 落库为业务列 | 无 GL 时只能做视图 |
| D-CH-12 | 费用行**不做二次分摊**：费用行自身 `allocated_charge_amount = 0`，分摊目标集合**排除费用行** | 允许费用行互相摊 | SAP unplanned 只摊发票物料行；Fusion AP 费用行也只摊物料行，两证据一致 |

##### 22.6.1.4 数据与参数（W8-P1 增量）

| 项 | 内容 |
|---|---|
| 新增列 | `vendor_invoice_lines.allocated_charge_amount`，`number(18,4)`，默认 `0`，只读派生 |
| 新增参数 | `vi_charge_allocation_enabled`（bool，默认 `false`）、`vi_charge_allocation_rule_code`（string，指向 `allocation_rules.code`，默认按 `value`） |
| 留痕 | `allocation_results`：`charge_source='invoice'`、`document_type='vendor_invoice'`、`parent_id=发票头`、`document_line_id=物料行`；头 1 行记待摊总额 + 行 N 记摊得额，`basis_field` 快照 |
| 规则绑定 | `allocation_rules.code` ↔ `vi_charge_allocation_rule_code`；P1 单规则，**不新增**"费用类型 → 规则"映射表 |
| 触发 | `submit_vendor_invoice` 匹配通过后、置 `submitted` 前；草稿可 `compute` 预演（不落库） |

##### 22.6.1.5 硬约束（实现必须校验）

1. **守恒**：`Σ 物料行 allocated_charge_amount = Σ 费用行 net_amount`（口径与 `basis_field` 一致，以留痕快照为准）；不等 → 拒绝落库。
2. **不改金额**：分摊不改任何行 `net_amount`，不改头金额与 `rounding_diff`（D-CH-05）。
3. **费用行为零**：费用行 `allocated_charge_amount = 0`，且不进目标集合（D-CH-12）。
4. **余差**：取整差额按 `allocation_rules.rounding` 落到最后一行，不新造尾差行。
5. **零基数**：分母为 0 → 按 `floor` / 均分策略处理或拒绝，**不得产生 0/0**。
6. **重摊**：旧 `allocation_results` 置 `invalid` + 派生列重写；红冲 / 调整按原比例取负。
7. **顺序**：先匹配后分摊；`match_status` 未通过不得分摊。

错误码（W8 预留，不占用 W6 编号）：`VI_CHARGE_ALLOCATION_DISABLED`、`VI_CHARGE_ALLOC_BASE_ZERO`、`VI_CHARGE_ALLOC_CONSERVATION`、`VI_CHARGE_ALLOC_MIXED_SIGN`、`VI_CHARGE_ALLOC_MATCH_REQUIRED`（对应第 7 条"先匹配后分摊"；见 22.6.2.2）。

#### 22.6.2 费用变更与单一事实源约束

> 本节回答两件事：费用**本身**变更时怎么处理（22.6.2.1 ~ 22.6.2.3），以及"费用归属"在系统里**只能有一份事实**（22.6.2.4）。
> 证据：SAP KBA 3507926 / 3317057 / 3417121 / 2714115（见《采购费用分摊-SAP研究与三方对比-2026-11-13.md》§14）；Fusion 侧对照见《采购费用分摊-Fusion研究与落地建议-2026-11-13.md》§12。

##### 22.6.2.1 四条收敛原则（R-1 ~ R-4）

| # | 原则 | 含义 | 对标证据 | 落点 |
|---|---|---|---|---|
| R-1 | **一套规则，多入口** | 采购发票 / 贷项凭证 / 借项通知单 / 后续借代上的费用，共用同一套分摊规则与同一张留痕表；入口不同不产生第二套分摊机制 | SAP 贷项凭证可录 unplanned delivery cost 并按本凭证行项目金额分摊（KBA 3507926） | 承运载体是 `document_category`，不是新的分摊实现 |
| R-2 | **变更独立成单，不原地改数** | 金额变化只以新单据承载（贷项 / 借项 / 红冲），已过账单据的数字不改 | SAP 更正只剩 MR8M 冲销重开或后续借 / 贷补差；冲销一律生成反向凭证（KBA 2714115） | 复用 `reversal_of_invoice_id` + `direction` |
| R-3 | **变更独立重摊，不修历史** | 每张变更单只摊**本单**费用；被变更单据的旧留痕置 `invalid` 保留，可回放 | SAP 无 re-allocation，已过账凭证不回溯重算（KBA 3417121） | `D-CH-06` + 22.6.1.5 第 6 条 |
| R-4 | **分摊只做归属，不回写源单** | 不写 PO 条件 / 净价、不改收货、不改发票 `net_amount` 与头金额 | SAP 分摊只加大发票行金额 + 写 FI 分录，PO 历史不变（走独立 G/L 时甚至不进 PO 历史） | `D-CH-05` |

##### 22.6.2.2 变更矩阵（A / B / C / D）

| # | 变更形态 | 承载方式 | 分摊口径 | 旧留痕 | 触发点 |
|---|---|---|---|---|---|
| A | **同票内调整**（本票费用行金额修正） | 原地改本票费用行，**仅 `draft`** | 重跑本票分摊，基数 = 本票行金额 | 置 `invalid` 后重写 | `draft` 保存 / `submit` 前 |
| B | **贷项**（费用冲减 / 供应商退款） | 新单 `document_category='credit_memo'`、`direction=-1`，可引用原 PO / 收货 | 独立分摊本单费用（金额为负，按原比例取负） | 原票留痕**不动** | 贷项 `submit` |
| C | **借项 / 后续借代**（追加费用，只调金额不动数量） | 新单 `document_category='debit_memo'`、`direction=1` | 独立分摊本单费用 | 原票留痕**不动** | 借项 `submit` |
| D | **整票红冲** | `reversal_of_invoice_id` 指向原票的反向单 | 按原比例全额取负 | 原票留痕置 `invalid` | 红冲 `posted` |

约束：

1. **A 只在 `draft` 允许**；`submitted / posted` 一律走 B / C / D，禁止原地改数（R-2）。
2. **B / C 只重写本单行的 `allocated_charge_amount`**，不得回写原票任何字段（R-4）。
3. **借贷混行禁止**（对齐 SAP KBA 3317057"同凭证借贷行并存导致分摊异常"）：同一张变更单内若同时存在借方费用行与贷方费用行，分摊**直接拒绝**并返回 `VI_CHARGE_ALLOC_MIXED_SIGN`；需要混号时拆成两张单据。这是显式拒绝，不是"尽力摊"。
4. **D 的负数口径**：红冲单 `direction=-1`，摊得额按**原留痕比例取负**后写入，不重新计算比例（避免二次四舍五入漂移）；尾差由原留痕金额最大的行吸收。
5. **A 的幂等**：同一票重复 `submit` 不产生第二份 active 留痕；旧留痕先置 `invalid` 再写新行，全程同一事务。

##### 22.6.2.3 累计开票口径（裁决：不采纳，留 P2）

SAP 的分摊基数是「**迄今已开票金额 + 本凭证金额**」，比本 Spec P1 的「仅本票内分摊」更宽（KBA 3417121）。

**裁决：P1 保持「仅本票内分摊」**，理由：

- 累计口径需要读取历史 `active` 留痕并与本票金额相加，分母随开票次数增长，与 22.6.1.5 第 1 条守恒式（`Σ 物料行 allocated_charge_amount = Σ 本票费用行 net_amount`）**不同构**，会引入"本票摊额 ≠ 本票费用"的跨期尾差。
- 历史票一旦被 B / C / D 变更，"已开票金额"必须重算 ⇒ 等于把局部变更传播成全局重摊，违反 R-3。
- 我们的费用载体是**发票费用行**（D-VI-21），费用金额本身随票携带，不存在 SAP 那种"PO 侧 planned 条件金额跨多张收货发票累积"的场景。

**P2 若开跨单据分摊**（22.6.1.2 W8-P2），届时再以累计口径重做守恒式定义，并必须在 `allocation_results` 上新增 `allocation_basis_window`（`invoice` / `cumulative`）快照列，不得靠调用方约定。

##### 22.6.2.4 单一事实源约束（S-1 ~ S-4）

| # | 约束 | 判据 | 违反后果 |
|---|---|---|---|
| S-1 | **归属金额只有一份事实** = `allocation_results` 中 `status='active'` 的行 | 报表 / 视图 / API 读归属一律走该表或其派生视图 | 两处各存一份 ⇒ 对不上时无法判定谁对 |
| S-2 | **派生列是投影，不是事实** | `vendor_invoice_lines.allocated_charge_amount` 必须可由 active 留痕完整重算 | 派生列单独维护 ⇒ 必然漂移 |
| S-3 | **重摊置 `invalid`，永不物理删除** | 仅宿主单据删除时由 `deletion_policy: cascade` 级联清理 | 删除即丢历史比例，成本调整 / 审计无据 |
| S-4 | **分摊不回写源单** | PO 条件 / 净价 / 收货 / 发票金额均不得因分摊而变 | 回写即产生第二事实源，违反 R-4 |

> S-3 的两种删除语义必须区分：**「重摊了」** ⇒ 置 `invalid`（历史保留，可回放）；**「单没了」** ⇒ `cascade` 物理清理（历史无宿主可挂）。把两者混为一谈就会出现"重算一次丢一次凭证"的缺陷。
> 同构要求已落到代码：销售侧 `SalesOrderHeaderDiscountService._invalidate_traces` 亦由物理 `DELETE` 改为置 `invalid`（同一事务内），与 `meta/schemas/allocation_result.yaml` L11 / L486 契约对齐。

### 22.7 税

| 项 | 规则 |
|---|---|
| 税率快照 | `tax_rate_percent`（新增，`number(9,4)`，可空）；取值顺序：`tax_code.rate` → 行录入 → PO 行 `tax_rate_percent` |
| 税码必填 | 非费用行可继承物料税务分类；费用行必填；草稿可空，`submit` 前必填（`VI_TAX_CODE_REQUIRED`） |
| 计税模式 | `vi_tax_mode ∈ {line_direct, rate_calc}`；本波默认 `line_direct`（TBD-4），`rate_calc` 为可选开关 |
| `line_direct` | `tax_amount` 可录入，服务端按 22.2 规则 4 校验（R-VI-30）；`editable: true` |
| `rate_calc` | `tax_amount` 置 `editable: false`，由 22.2 计算；录入被忽略 |
| 含税价 | `price_includes_tax=1` 时税率必填，否则 `VI_TAX_RATE_REQUIRED`（G-2） |
| 调整单 | 税额一律按**新净额 × 原税率**重算，**不**按源金额比例（G-4） |
| 红冲 | 税行随复制取负，税率不变 |
| PO 税额比对 | 本波不做（TBD-14）；预留开关 `vi_po_tax_compare`（默认 `false`） |

### 22.8 匹配与金额一致性

1. **单一可开票量函数** `_open_qty(schedule_id, mode, receipt_line_id=None)`，`match` 与 `write_edges` **必须**调用同一实现（G-5）：
   - `po_based`：`open = schedule.qty_ordered − Σ normal(billing) + Σ red(billing)`；
   - `gr_based`：`open = Σ qty_invoiceable(receipt_line) − Σ normal(ap_match) + Σ red(ap_match)`，其中 `qty_invoiceable = qty_received − qty_rejected`（仅 `return_to_supplier` / `scrap` 扣减，D-VI-16）；
   - 已退货量：`receipt_line.qty_returned` 缺失时由退货 doc_flow 推导；两者皆无 ⇒ `gr_based` 不可用（22.10 默认改 `po_based`）。
2. **禁止静默截断**（G-3 / R-VI-28）：`qty > open + 容差` → `VI_QTY_EXCEEDED`；容差内 → `match_status='exception'` 且**不写边**；删除现有 `min(qty, open_qty)` / `min(qty, available)`。
3. 四维锚点回填（G-9）：`item_id / item_group_id / line_type_id / uom_id` 由服务端解析并**覆盖落库**，禁止 `if not result.get(...)` 条件回填；`item_group_id` 由物料反查必填。
4. 供应商 / 币种校验（G-10）：锚点为空也必须校验头 `supplier_account_id` / `currency_id`；PO 存在时须与 PO 头一致，否则 `VI_SUPPLIER_MISMATCH` / `VI_CURRENCY_MISMATCH`（R-VI-4 / R-VI-13）。
5. 价格比较一律用 22.2 归一后的不含税价（G-2）；`price_diff_amount` 公式见 22.2 规则 7。
6. `match_mode` 解析（G-6）：`vi_match_mode` 多级解析（org → document_type → line_type → item_group，0 哨兵 + `specificity_rank`），解析不到回落 `po_based`；头字段 `match_mode` 为创建时快照（不可变）。
7. 红边分摊：`decrease` 按 active normal 边 `rowid` FIFO 遍历冲减；“只取末条边”的实现必须改为累计可用量遍历（G-13）。

### 22.9 新增不变量（R-VI-24 ~ R-VI-33）

| ID | 不变量 | 校验点 |
|---|---|---|
| R-VI-24 | 行恒等式 `gross_amount = net_amount + tax_amount`（含税 / 不含税 / 调整 / 红字行均成立） | 计算层 + 落库前 |
| R-VI-25 | 头恒等式 `net + tax + rounding_diff = gross` | 计算层 + 过账前 |
| R-VI-26 | 金额只经 `round_amount(x, currencies.decimal_places)` 舍入 | 计算层（lint 禁止 `round(`） |
| R-VI-27 | `po_unit_price / price_source / price_trace / tax_rate_percent / price_includes_tax` 由服务端写，入参一律剔除 | handler 入参白名单 |
| R-VI-28 | 超量 / 超额边显式拒绝或置 `exception`，禁止 `min()` 截断 | `_write_edges` / `_write_credit_red_edges` |
| R-VI-29 | 费用行不写 doc_flow 边、不参与数量匹配 | 边写入层 |
| R-VI-30 | `line_direct` 税额偏差 ≤ `vi_tax_tolerance_abs` | 计算层 |
| R-VI-31 | 调整行金额必须由计算层按 22.2 重算，`unit_price` 与 `net_amount` 同步 | 调整单创建 |
| R-VI-32 | `qty ≥ 0`；负向只由红字复制 / `adjustment_direction` 表达 | schema + 服务 |
| R-VI-33 | 金额算术**单一实现**：VI 只允许继承 `SalesOrderAmountService` 并覆写钩子，禁止复制公式 / 新建平行金额服务 | 代码评审 + lint（禁止 `vendor_invoice` 内出现 `round(` / `× 税率` 硬编码） |
| R-VI-38 ~ R-VI-47 | 三单匹配补强（源单状态 / 费用对账 / UOM / 多异常 / 枚举闭合 / PO 税额 / 容差方向）；明细见 §24.4，本节不重复 | §24 |
| R-VI-48 ~ R-VI-59 | 端到端 / 逆向 / 异常一致性补强（收货红冲守卫 / 期次净额化 / 应付视图 / 退货贷项余量 / 贷项逆向 / 汇率 / PO 守卫 / 发票号 / 期间 / 供应商状态 / 取消收敛 / rematch）；明细见 §25.4 | §25 |

> 编号衔接：R-VI-19 仍留空（保留给 SES / ERS 结算模式），R-VI-20~23 属调整单（§21.1），本节从 24 起。

### 22.10 控制参数

| 参数 | 类型 | 默认 | 解析 | 超限动作 |
|---|---|---|---|---|
| `vi_match_mode` | enum `po_based/gr_based` | **`po_based`（由 `gr_based` 调整）** | 四维多级 | 快照到头条 |
| `vi_match_pricing_mode`（新） | enum `po_price/manual` | `po_price` | 四维多级 | 快照到行 |
| `vi_price_tolerance` | decimal | `0.00` | 四维 | 价格差异 → exception |
| `vi_qty_tolerance_receipt` | decimal | `0.00` | 四维 | 超收 → exception |
| `vi_qty_tolerance_order` | decimal | `0.00` | 四维 | 超订 → exception |
| `vi_amount_tolerance_abs` | decimal | `0.00` | 四维 | 头金额差 → exception |
| `vi_rounding_tolerance_abs` | decimal | `0.01` | 四维 | `rounding_diff` 超限 → exception |
| `vi_tax_tolerance_abs`（新） | decimal | `0.01` | 四维 | 税额差 → exception |
| `vi_freight_tolerance_abs`（新） | decimal | `0.00` | 四维 | 费用行 / PO 对账 → exception |
| `vi_tax_mode`（新） | enum `line_direct/rate_calc` | `line_direct` | 四维 | 决定 `tax_amount` 可编辑性 |
| `vi_po_tax_compare`（新，预留） | bool | `false` | 四维 | 开启后比对 PO 税额（TBD-14） |
| `vi_charge_allocation_enabled`（W8） | bool | `false` | 四维 | 未开启时分摊不执行（`VI_CHARGE_ALLOCATION_DISABLED`）；见 22.6.1.4 |
| `vi_charge_allocation_rule_code`（W8） | string | 按 `value` 的规则 code | 四维 | 分摊基数 / 取整 / target 由该规则决定 |

> `vi_match_mode` 默认值变更由迁移更新 `control_parameter_values`；复用 `control_parameter_def`，不建新表。

### 22.11 数据模型变更清单

| 对象 | 变更 | 类型 | 空 | 说明 |
|---|---|---|---|---|
| `vendor_invoices` | `supplier_gross_amount` | number(18,4) | 是 | 供应商发票原件总额（与 `gross_amount` 同符号），驱动 `rounding_diff` |
| `vendor_invoice_lines` | `tax_rate_percent` | number(9,4) | 是 | 税率快照（%），含税价行必填 |
| `vendor_invoice_lines` | `price_source` | string(20) | 是 | `po / manual / adjustment`；只读 |
| `vendor_invoice_lines` | `price_trace` | text | 是 | JSON 快照；只读；**不**建 JSON 索引 |
| `vendor_invoice_lines` | `allocated_charge_amount`（W8） | number(18,4) | 否 | 摊得费用额，默认 `0`；只读派生；费用行恒为 `0`（22.6.1.5） |
| `type_definitions` | 5 条 line 种子 | — | — | 22.6；`VI_LINE_GOODS` 为默认 |
| `control_parameter_def` | 7 条新参数（5 条 W6 + 2 条 W8） | — | — | 22.10 |
| `sales_order_amount_service` | 新增 2 个可覆写钩子 `_line_amounts` / `_header_amounts` | — | — | 默认实现 = 现行 SO/PO 口径（零回归）；VI 子类覆写（22.1） |
| YAML | `tax_amount.editable` 随 `vi_tax_mode`；`supplier_gross_amount / tax_rate_percent` 可编辑，其余只读 | — | — | 无新表 / 无新视图 |

**不新增**：头级 `freight_amount / surcharge_amount / other_amount`（用费用行）、费用分摊表（结果由 `allocation_results` 承载）、税率表、匹配结果表。

### 22.12 错误码

| 码 | 触发 | 处置 |
|---|---|---|
| `VI_AMOUNT_IDENTITY` | 行 / 头恒等式不成立 | 拒绝保存 |
| `VI_TAX_RATE_REQUIRED` | 含税价缺税率 | 拒绝 |
| `VI_TAX_CODE_REQUIRED` | `submit` 前缺税码 | 拒绝 |
| `VI_TAX_MISMATCH` | 直录税额超容差 | exception（可 override） |
| `VI_ROUNDING_DIFF_EXCEEDED` | 舍入差超容差 | exception |
| `VI_QTY_EXCEEDED` | 超可开票量 | 拒绝写边 |
| `VI_PRICE_OVER_TOLERANCE` | 价格超容差 | exception（原因 `price_over_tolerance`） |
| `VI_PRICING_MODE_UNSUPPORTED` | 选择 `receipt_price` | 拒绝 |
| `VI_ANCHOR_REQUIRED` | 非费用行无锚点 | 拒绝 |
| `VI_SUPPLIER_MISMATCH` / `VI_CURRENCY_MISMATCH` | 与 PO 头不一致 | 拒绝 |
| `VI_FREIGHT_OVER_TOLERANCE` | 费用与 PO 对账超限 | exception |
| `VI_ADJUSTMENT_EMPTY_LINE` | 调整行金额与数量均为 0 | 拒绝 |
| `VI_ADJUSTMENT_PENDING` | 红冲时存在 active 调整单 | 拒绝 |

### 22.13 验收判据与测试矩阵

| # | 场景 | 期望 | 测试落点 |
|---|---|---|---|
| A1 | 不含税价 `q=10 p=100 r=13 d=2` | net 1000.00 / tax 130.00 / gross 1130.00 | `test_vendor_invoice_amount.py` |
| A2 | 含税价 `q=3 p=113 r=13 d=2` | gross 339.00 / net 300.00 / tax 39.00（恒等式成立） | 同上 |
| A3 | 含税价缺税率 | `VI_TAX_RATE_REQUIRED` | 同上 |
| A4 | `d=0`（JPY）金额 1001.4 | 落库 1001（不得 1001.40） | 同上 |
| A5 | 供应商总额 1130.05 vs 行合计 1130.00 | `rounding_diff=0.05`；超容差 → exception | 同上 |
| A6 | PO 价 100，发票含税价 113（r=13） | 匹配通过（归一后 100.00） | `test_vendor_invoice_match.py` |
| A7 | 可开票 10，发票 12 | `VI_QTY_EXCEEDED`，不写边（不得静默写 10） | 同上 |
| A8 | `receipt_price` 模式 | `VI_PRICING_MODE_UNSUPPORTED` | 同上 |
| A9 | 调整单只改 `unit_price` 100→110，q=5 | net 550.00 / tax 71.50（13%）/ gross 621.50 | `test_vendor_invoice_adjustment.py` |
| A10 | 调整单 `qty=0` + `net=-50` | 纯金额递减，不写边 | 同上 |
| A11 | 运费行 50（税 6%）+ 物料行 1000 | 头 net 1050 / tax 133 / gross 1183；无运费边 | `test_vendor_invoice_charge_line.py`（新） |
| A12 | 费用合计与 PO `header_surcharge_amount` 差 10，容差 0 | `VI_FREIGHT_OVER_TOLERANCE` → exception | 同上 |

运行入口：`python d:\filework\test.py --single meta/tests/test_vendor_invoice_amount.py`（禁 `pytest`）。

### 22.14 Decision Log 追加

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| D-VI-21 | 计划外费用用**费用行**承载，不新增头级费用字段 | 头级 `freight_amount` 等 | 金额天然进 Σ 行；无需分摊表；与销售侧抬头折扣/附加费可对位 |
| D-VI-22 | `receipt_price` 本波禁用而非伪造 override | 保留自动 override | 无收货价即无比较基准，伪造 override 使差异不可审计（G-7） |
| D-VI-23 | 含税价匹配统一折算为不含税价，税率必须快照 | 直接比含税价 | PO 价为不含税（`purchase_order_line.unit_price`），混比产生假差异（G-2） |
| D-VI-24 | `vi_match_mode` 默认改 `po_based` | 保持 `gr_based` | `gr_based` 依赖 `qty_returned`，退货扣减未落地（G-5） |
| D-VI-25 | 调整行允许显式 `unit_price` 并按 22.2 重算 | 仅允许纯金额调整（原 §21.8 口径） | 价格变更是真实业务；只改价不改金额会产出错账（G-4 / G-16） |
| D-VI-26 | 发票侧不新增 `price_list_id`、不重跑定价模板 | 发票侧重新取价 | 定价属 PO 承诺，发票只对位快照（§1.2 边界） |
| D-VI-27 | 金额计算**统一复用** `SalesOrderAmountService` 内核（子类 + 钩子），不新建独立金额服务 | 新建 `vendor_invoice_amount_service.py` 纯函数（首版草案）；或复制公式 | 销售侧 SO/PO 已统一在该内核（C）；再建一套即第三套算术，口径漂移与回归风险不可控 |
| D-CH-01~12 | 费用分摊 12 条决策：费用以行承载、只走 `allocate_by_rule`、`basis_field ∈ {net_amount, gross_amount}`、来源可跨/目标不可跨、`origin` 按金额锚点判定、分摊不产会计落点、参考成本只做视图、费用行不可为目标 | 见 22.6.1.3 逐条备选 | 分摊属成本域；本波只固化方案不实现（W8），避免与 W6 费用行承载耦合 |
| D-CH-13 | 费用变更按 **R-1~R-4** 与变更矩阵 **A / B / C / D** 落地；**累计开票口径不采纳**（P1 仅本票，P2 再议） | 累计口径（SAP KBA 3417121）/ 变更回写原票 / 重算历史票 | 累计口径与 22.6.1.5 守恒式不同构，且把局部变更放大成全局重摊（违反 R-3）；回写原票产生第二事实源（22.6.2.1 / 22.6.2.3） |
| D-CH-14 | 同票**借贷混行显式拒绝**（`VI_CHARGE_ALLOC_MIXED_SIGN`），不做"尽力摊" | 允许混行、按净额摊 | SAP KBA 3317057 已证实同凭证借贷行并存时分摊异常；净额摊会掩盖方向错误（22.6.2.2 约束 3） |

### 22.15 对既有条款的修订索引

| 既有条款 | 修订 |
|---|---|
| §4.2 行字段表 | 增 `tax_rate_percent / price_source / price_trace`；`tax_amount` 可编辑性随 `vi_tax_mode` |
| §5.4 `match_pricing_mode` 三值表 | `receipt_price` 改为禁用（22.4）；补价格归一与 `vi_match_pricing_mode` 参数 |
| §6.3 R-VI-6 | 以 22.2 两条路径替换，明确含税路径与税额吸收项 |
| §6.3 R-VI-7 | 以 22.3 头恒等式替换「Σ 行」简式，增加 `rounding_diff` |
| §11.2 | 头金额合计仍落列；`supplier_gross_amount` 为**输入**而非派生 |
| §21.3 金额口径 | 保留符号规则；补「调整行恒等式 + 计算层重算」 |
| §21.5 行金额折算 | 按原行**单价 × 新数量**重算净额，税按原税率重算（不是源金额 × 数量比例） |
| §21.8 末条 | 改为「不重跑定价模板；价格差异用 T2 显式 `unit_price` 或 T3 纯金额表达」（D-VI-25） |
| §22.6 规则 6 | 由「费用 → 物料行 / 入库成本的分摊不在本波，归成本域」改为「本波不实现；方案、波次边界与硬约束见 22.6.1（W8）」 |
| §22.6.1.5 第 6 条 | 「重摊置 `invalid`」由单句细化为 **22.6.2** 的四种变更形态（A/B/C/D）与 S-1~S-4 单一事实源约束；并明确区分「重摊了」（置 `invalid`）与「单没了」（`cascade` 物理清理）两种清理语义 |

### 22.16 实施波次归属

| 波次 | 内容 |
|---|---|
| W2（金额链路） | 22.1 **内核钩子扩展 + VI 子类** / 22.2 / 22.3 / 22.11 金额列与 `supplier_gross_amount` |
| W5（匹配） | 22.4 / 22.8 / 22.10 参数解析 |
| W6（税与费用） | 22.6 / 22.7 / line 种子 / 参数 |
| W7（调整单） | 22.5 T1 / T2 / T3 重算 |
| W8-P1（费用分摊） | 22.6.1：`allocated_charge_amount` 列 / 2 个 `vi_charge_allocation_*` 参数 / 分摊接线 / 7 条硬约束；22.6.2：A（同票内调整）与 D（整票红冲）两种变更形态 / R-1~R-4 / S-1~S-4 |
| W8-P2（可选） | 22.6.1.2：跨单据来源、显式行子集、参考成本视图；22.6.2.2：B（贷项）与 C（借项）独立重摊；22.6.2.3：累计开票口径 + `allocation_basis_window` 快照列 |

---

## 23. 应付付款计划（AP Payment Plan）— 与 AR 对称契约（2026-11-14 追加）

> 状态：**已实施（2026-11-14，方案 A；迁移 `v271__vendor_invoice_schedule`；带出链同日对齐 AR）**
> 实现落点：`meta/schemas/vendor_invoice_schedule.yaml`、`vendor_invoice.yaml#payment_term_id`、`vendor_account.yaml#default_payment_term_id`、`meta/services/vendor_invoice_match_service.py#_generate_schedules`、`meta/services/vendor_payment_term_service.py`（带出链）、`meta/api/bo_api.py#_apply_vendor_invoice_defaults`、`meta/migrations/v271__vendor_invoice_schedule.py`
> 验证：`meta/tests/test_vendor_invoice_schedule.py`（11 例，含 4 例带出链）、`meta/tests/migrations/test_vendor_invoice_migrations.py::test_v271_schedule_table_and_columns`
> 方案：**A —— 先追平 AR 结构**；折扣 / 预付 / 付款事实层另立波次（见 §23.9）
> 参照：`meta/schemas/customer_invoice_schedule.yaml`（结构母本）、`spec-sales-order-billing-object-model-2026-11-07.md` §23 / §30.5（设计稿与 AR 实现口径）
> 契约来源：`meta/services/customer_invoice_service.py` `_generate_schedules`（L1627-L1682）、`payment_term_schedule_service`（日期单一真源）

### 23.0 一句话结论

采购侧**模板层已完整、实例层为零**：`payment_term` / `payment_term_line` / 日期推算服务都在，但 `vendor_invoice` 没有付款条件字段、没有期次对象、也没有生成点。本节按「默认对称」原则，把 AR 的发票级期次逐字段搬到 AP，**不引入采购侧独有形状**；三单匹配、付款执行等采购专属能力全部落在期次形状之外（§23.8）。

### 23.1 现状审计（采购侧付款计划）

| 层 | 现状 | 证据 | 缺口 |
|---|---|---|---|
| 模板层 | 完整 | `payment_term.yaml`（code / name / basis_date_rule / cutoff_day / status）、`payment_term_line.yaml`（seq / percentage / offset_months / fixed_day_of_month / offset_days / discount_percent / discount_days） | 无 |
| 日期推算 | 单一真源 | `payment_term_schedule_service.py`（只看日期，不管金额/凭证/催收） | 无 |
| 合同层 | PO 有付款条件字段 | `purchase_order.yaml` `payment_term_id`，注释「空 = 供应商档案默认」 | 原为死引用（`vendor_account` 无对应字段），已由 §23.5 (2) + 带出链补齐 |
| 实例层 | **无** | `vendor_invoice.yaml` 无 `payment_term_id` / `due_date` / 期次对象；`generated_schema.sql` 无任何 AP 期次表 | 本节补齐 |
| 付款事实层 | **无** | 无 `vendor_payment` / `payment_allocation`（`generated_schema.sql` 仅有 `vendor_invoices`） | 延后（§23.9） |

### 23.2 对称裁决表（六个设计点）

原则：**默认对称**；只有具备真实采购专属业务逻辑才允许不对称，且不对称不得改期次形状。

| # | 设计点 | AR 现状 | AP 处置 | 理由 |
|---|---|---|---|---|
| 1 | 期次挂载层级 | 发票级（`customer_invoice_schedule`），不挂订单 | **对称**：发票级（`vendor_invoice_schedule`），不挂 PO | PO 侧已有 `purchase_order_schedule`（`schedule_kind` 仅 `delivery`/`service`），承载到货/服务计划；付款期次的基准是发票，不是 PO |
| 2 | 发票头付款条件 | `customer_invoice.payment_term_id`（空 = 即期） | **对称**：新增 `vendor_invoice.payment_term_id` | 无付款条件字段则期次无输入源 |
| 3 | 往来方默认条件 | `customer_account.default_payment_term_id`（解析链：档案 → 单据类型参数 → 留空） | **对称**：新增 `vendor_account.default_payment_term_id`，同一条解析链 | 同时消除 PO 注释的死引用 |
| 4 | 现金折扣 | 模板有 `discount_percent` / `discount_days`，但 AR 期次**未快照**折扣日/折扣额 | **两侧都不做**（本波） | 折扣是「双侧共同升级」事项，不接受单侧先行（单侧会让 AP 比 AR 多一层语义） |
| 5 | 预付 | 设计稿 §23 有 `is_prepayment` / `deposit_amount`，**未落地**；仓库无 `prepayment` 对象 | **两侧都不引入**；不建 Fusion 式「预付发票」 | 预付在 Fusion 是独立发票类型（create → pay → apply），属付款域；凭单侧凭空引入会造出第二套发票语义 |
| 6 | 到期日位置 | 行级 `due_date`；头无 `due_date` | **对称**：行级 | 一期一日；头级 `due_date` 在多期场景无意义 |

### 23.3 字段级对称契约（逐字段一一对应）

父字段命名沿用 `invoice_id`（`vendor_invoice_line` 的父字段也是 `invoice_id`），**不改成 `vendor_invoice_id`**；累计列沿用 `amount_applied`，**不改名为 `amount_paid`**——两侧同名才能让服务层、页面、报表走同一套口径。

| # | AR（`customer_invoice_schedule`） | AP（`vendor_invoice_schedule`） | 类型 / 约束 | 语义 |
|---|---|---|---|---|
| 1 | `invoice_id` | `invoice_id` | integer，必填 | 父字段（所属发票） |
| 2 | `schedule_no` | `schedule_no` | integer，必填 | 期次序号，从 1 递增；唯一键 `invoice_id + schedule_no` |
| 3 | `payment_term_line_id` | `payment_term_line_id` | integer，可空 | 来源付款条件行；即期为 NULL |
| 4 | `ratio_percent` | `ratio_percent` | number(4 位小数)，必填 | 期次比例快照 |
| 5 | `due_date` | `due_date` | date，必填 | 到期日（≥ 发票日期） |
| 6 | `amount` | `amount` | number(币种精度)，必填 | 期次金额；Σ = 头 `gross_amount` |
| 7 | `amount_applied` | `amount_applied` | number，必填，默认 0 | 已核销金额；付款域落地前恒 0、只读 |
| 8 | `status` | `status` | string，必填，默认 `open` | `open`/`partial`/`closed`/`cancelled`（状态机两侧同构） |
| 9 | `created_at` / `updated_at` | 同 | datetime | 审计字段（audit_aspect 管理） |

> 差异项：**0 个字段差异**。AP 侧唯一新增的是标签文案（「未收款 → 未付款」「已收清 → 已付清」），不改字段名、不改枚举值。

### 23.4 `vendor_invoice_schedule` 对象定义（新表 `vendor_invoice_schedules`）

对齐 `customer_invoice_schedule.yaml` 的元数据声明：

| 元数据项 | 取值 |
|---|---|
| `name` / `table_name` | 应付期次 / `vendor_invoice_schedules` |
| `parent_object` / `hierarchy.parent_field` | `vendor_invoice` / `invoice_id` |
| `semantics.category` | `business_document_line` |
| `aliases` | 应付期次 / 付款计划 / Vendor Invoice Schedule |
| `deletion_policy.mode` | `restrict`（期次随头只读，不单独删除） |
| `org_scope` | `mode: chain` / `via: invoice_id` / `host: vendor_invoice` / `function: accounting` / `write_check: true` |
| `audit` | 全开，update 用 `changed_only` |
| `ui_view_config.skip_auto_menu` | `true`（由发票详情子表呈现，不建独立菜单） |

**索引**（与 AR 同名同形，便于跨侧比对）：

| 索引名 | 字段 | 唯一 |
|---|---|---|
| `uq_vendor_invoice_schedule_no` | `(invoice_id, schedule_no)` | 是 |
| `idx_vendor_invoice_schedule_invoice` | `(invoice_id)` | 否 |
| `idx_vendor_invoice_schedule_status_due` | `(status, due_date)` | 否 |

**关系**（两条，与 AR 一一对应）：

| id | source → target | 基数 | 说明 |
|---|---|---|---|
| `vendor_invoice_schedule_to_invoice` | `invoice_id` → `vendor_invoice.id` | N:1 | 所属发票 |
| `vendor_invoice_schedule_to_term_line` | `payment_term_line_id` → `payment_term_line.id` | N:1（可空） | 来源付款条件行 |

### 23.5 新增的两个头字段

**（1）`vendor_invoice.payment_term_id`**

| 属性 | 取值 | 说明 |
|---|---|---|
| 类型 / 可空 | integer / 可空 | 与 `customer_invoice.payment_term_id` 同构 |
| description | 付款条件快照；空 = 即期（过账时生成 1 期 100%） | 与 AR 文案一致 |
| 带出链 | 由 PO 匹配生成时取 PO `payment_term_id` → 手工录入时取 `vendor_account.default_payment_term_id` → 留空（即期） | 对齐 Fusion「PO → 供应商地点 → 录入覆盖」；**过账前可改，过账后随头只读**。**已实施（2026-11-14）**：创建钩子 `bo_api#_apply_vendor_invoice_defaults` 取供应商默认；过账时 `_generate_schedules` 若头仍空，按行锚点（`schedule_id` → `order_line_id` → `receipt_line_id`）回溯 PO 条件并回写头快照，再退供应商默认 |
| value_help | `payment_term`，候选 `status: active` | 存量已停用条件回显不受限（不读 value_filter） |

**（2）`vendor_account.default_payment_term_id`**

| 属性 | 取值 |
|---|---|
| 类型 / 可空 | integer / 可空 |
| 解析链 | 档案本字段 → 单据类型控制参数 `default_payment_term` → 留空（不阻断保存） |
| description | 供应商级默认付款条件；新建采购单据时带出，可改 |
| 落点 | `vendor_account.yaml` 字段序列中插入 `tax_classification_id` 之后（对齐 `customer_account` 的字段序） |

**（3）连带修正**：`purchase_order.yaml` `payment_term_id` 的注释「空 = 供应商档案默认」在本字段落地后成为真引用，保持原文案；本波只做校验说明，不改语义。

### 23.6 新增不变量（R-VI-34 ~ R-VI-37）

| 编号 | 不变量 | 对应 AR |
|---|---|---|
| **R-VI-34** | Σ `amount` = 头 `gross_amount`；尾差归最后一期；不一致拒绝过账 | R-INV-21 |
| **R-VI-35** | `posted` 后任何期次不可改（严格只读，不做重排期 / 不重算） | R-INV-22 |
| **R-VI-36** | 红字单 / 取消单不生成期次 | R-INV-24（并使 §6.3 R-VI-15 从占位约束升级为可执行约束） |
| **R-VI-37** | 头不设已付金额列；`amount_applied` 默认 0，付款域落地前不写 | R-INV-25 |

### 23.7 生成流程（过账时，与 AR 同序）

```
post(vendor_invoice)
  ├─ 红字/取消单 → 跳过（R-VI-36）
  └─ 正向单 → _generate_schedules(header, lines)
       0. 头 payment_term_id 为空 ⇒ 带出链解析（行锚点回溯 PO → 供应商默认）并回写头快照
       1. payment_term_id 为空 或 条件无行
            ⇒ 1 期：ratio=100、payment_term_line_id=NULL、due_date = invoice_date
       2. 否则 resolve_base_date(term, invoice_date) + compute_due_date(...) 逐行推算
       3. 校验：任一期 due_date < invoice_date ⇒ 拒绝
       4. 金额按币种精度分配（尾差归最后一期），Σ = gross 校验
       5. 逐行写入：schedule_no 递增、amount_applied=0、status=open
       6. 未过账 / 已红冲 时任何写入均被守卫拒绝
```

- 日期推算**复用** `payment_term_schedule_service`（`resolve_base_date` + `compute_due_date`），AP 不新增推算逻辑。
- 错误码按 AR 口径新增两条：`VENDOR_INVOICE_TERM_INVALID`（到期日早于发票日期 / 条件非法）、`VENDOR_INVOICE_AMOUNT_MISMATCH`（期次合计 ≠ 价税合计）。
- 基准日取 `invoice_date`（与 AR 一致，不取 `posting_date`）。

### 23.8 允许的采购专属差异（都在期次形状之外）

| 差异 | 为什么 AP 必须有 | 落在哪 |
|---|---|---|
| 三单匹配锚点 | AP 发票行要指回 PO 行 / 收货行才能校验（`vendor_invoice_line.schedule_id` 指 `purchase_order_schedule`） | **行级**，与付款期次是两个概念；本节不动 |
| 付款执行 | 付款批 / payment run / pay alone / 付款冻结（hold） | **付款域**（`vendor_payment` + 付款批对象），延后 |
| 预扣税 / 费用 | 预扣税改变实付金额，但不改变「应付到期金额」 | 付款域；期次 `amount` 仍是应计应付额 |

> 结论：**AP 相对 AR 的差异全部在「期次之外」**，期次本身 8 个字段零差异。

### 23.9 本波范围 / 延后项 / 迁移

**本波做（方案 A）**

1. `vendor_invoice_schedule.yaml`（新对象，§23.4）
2. `vendor_invoice.payment_term_id`（新列，§23.5-1）
3. `vendor_account.default_payment_term_id`（新列，§23.5-2）
4. `vendor_invoice_match_service.post()` 过账钩子 `_generate_schedules` + 守卫（R-VI-34~37）
5. 发票详情「应付期次」只读子表（无独立菜单）
6. 付款条件带出链（对齐 AR）：`vendor_payment_term_service` + `bo_api#_apply_vendor_invoice_defaults`（创建取供应商默认）+ 过账兜底（行锚点回溯 PO → 供应商默认 → 回写头快照）

**本波不做（延后，需双侧同步立项）**

| 延后项 | 原因 |
|---|---|
| 折扣日 / 折扣额快照 | AR 未做；单侧推进会造出不对称 |
| 预付（`is_prepayment` / `deposit_amount` / 预付发票） | 两侧均未落地；属付款域 |
| `vendor_payment` / `payment_allocation` / 付款批 / 账龄 | 付款事实层，独立波次 |
| PO 级付款计划（`purchase_order_schedule` 扩展 `schedule_kind='payment'`） | 判定为不需要：期次基准是发票（与 Fusion / AR 一致） |

**迁移**：新增期次表 + 2 个可空列，均不下推历史数据（存量已过账发票不补生成期次，按「空 = 无期次」处理；如需补，另开一次性脚本并留审计）。

**出口判据**：同一发票在 AR / AP 两侧期次数、`schedule_no`、`ratio_percent`、`due_date`、`amount`、`status` 逐项可比；Σ = 头价税合计；红字 0 期次；`posted` 后改期次被拒。

### 23.10 对既有条款的修订索引

| 既有条款 | 修订 |
|---|---|
| §6.3 R-VI-15（L428，「红字发票不生成付款计划，付款域未建」） | 由占位约束升级为可执行约束（R-VI-36），付款域未建的部分仅剩「付款事实层」 |
| §15 TBD-3（付款/预付对象延后） | 维持延后；但「应付分期无处落地」的空白由本节补齐 |
| §3.3 头字段表 | 追加 `payment_term_id` |
| §22.11 数据模型变更清单 | 追加 `vendor_invoice_schedules` 与 `vendor_account.default_payment_term_id` |

---

## 24. 三单匹配能力补强（W10，2026-11-14 细化）

> 依据：对 `meta/services/vendor_invoice_match_service.py` 的逐函数审计（C）+ SAP `OMR6` / Fusion `AP_INVOICE_MATCH` 对标（S/F）。
> 口径：**不新增表、不新增物理列、不新增迁移**；只做「判定口径闭合」+「源单前置约束」+「YAML 枚举收敛」。
> 本节为对 §22 的**增量修订**，冲突时以本节为准（见 §24.9 修订索引）。
> 状态：**W10-1 已实施（2026-11-14）** — R-VI-38 ~ R-VI-47 全部落码，§24.7 的 #1~#13 由 `meta/tests/test_vendor_invoice_match_gaps.py` 覆盖，#14 由既有 25 例 match 测试回归；YAML 枚举已收敛，`generated_schema.sql` 已重新生成。

### 24.0 结论先行

| # | 结论 | 证据 |
|---|---|---|
| M-1 | 三单匹配**骨架完整**：双模式、四维容差、余量推导、行级例外、过账重算均已具备 | C（§24.1） |
| M-2 | 缺的不是能力，而是**口径闭合**：费用对账只有单 PO 路径、异常原因只留首个、UOM 无一致性校验 | C（§24.2 A 类） |
| M-3 | **源单前置约束缺失**：`_open_qty` 不校验 PO / 收货单头状态，草稿收货与已关闭 PO 仍可对碰 | C（§24.2 A-3） |
| M-4 | 有 2 个枚举值 + 2 个参数**已播种但无消费点**（`currency_mismatch` / `supplier_mismatch`；`vi_po_tax_compare` / `tolerance_direction`） | C（§24.2 B 类） |
| M-5 | 标准 3-way 的「PO 行级 + 多收货累计」未实现，`no_receipt` 例外放行无路径 | 裁决延后至 W10-2（§24.8） |

### 24.1 能力审计矩阵

| 能力 | 现状 | 判定 | 证据 |
|---|---|---|---|
| 2-way / 3-way 模式 | `po_based` / `gr_based` 分层解析，头级快照 | 已覆盖 | `_resolve_match_mode` |
| 可开票余量 | po：`promised − returned − billing`；gr：`qty_invoiceable − ap_match` | 已覆盖 | `_open_qty` L362-381 |
| 质检折抵 | 仅 `return_to_supplier` / `scrap` 扣减 | 已覆盖（D-VI-16） | `qty_invoiceable` L265-276 |
| 价格校验 | 单价差 vs PO 快照，仅上界 | 部分（见 B-3） | `_allowed_upper` L481-487 |
| 数量校验 | 按模式取 `vi_qty_tolerance_order` / `_receipt` | 已覆盖 | `_match_line` |
| 税额校验 | 行税额自身容差 `vi_tax_tolerance_abs` | 部分（见 B-2） | `_validate_line_tax` L956+ |
| 费用对账 | 单 PO、仅 surcharge、无锚点放行 | **缺陷** | `_validate_charge_reconciliation` L975-1014 |
| 锚点快照 | item / uom / po_unit_price 由源单覆盖 | 部分（见 A-2） | `_normalize_line_anchors` L1175-1211 |
| 例外放行 | 行级 `override_*`，post 按行绕过 | 已覆盖 | R-VI-16 |
| 匹配结论落地 | 头/行 `match_status` + 单值 reason | **缺陷** | `_aggregate` L1427 / L1444 |
| 重复发票 | 供应商 + 规范化号硬拦 | 已覆盖 | R-VI-14 |
| 过账重算 | `BEGIN IMMEDIATE` 内重跑 match | 已覆盖 | R-VI-18 |

### 24.2 缺陷清单

#### A 类（会算错 / 会放过，W10-1 必修）

| ID | 缺陷 | 根因 | 影响 |
|---|---|---|---|
| A-1 | 费用对账只覆盖**单 PO** 且**只对 surcharge** | 反查 PO 后 `break` 于首个带 schedule 的行；`target = surcharge`，仅当其为 0 才回退 `discount` | 多 PO 合并发票只对第一张；`surcharge` 与 `discount` **同时非 0** 时漏掉折扣侧（差额 = 折扣额，误报 `VI_FREIGHT_OVER_TOLERANCE`）。**注**：PO 头 `header_discount_amount` 为负值存储，故「仅折扣」场景当前回退是偶然正确的 |
| A-2 | 费用行不写 doc_flow 边且**无替代余量约束** | R-VI-29 明确「费用行不写边」 | 同一笔 PO 附加费可被多张发票重复报销，无上限保护 |
| A-3 | **源单状态不校验** | `_open_qty` 只读数量与消耗 | PO `draft` / `closed` / `cancelled` 仍可开票；收货单 `draft` / `cancelled` / `reversed` 仍可被 3-way 匹配 |
| A-4 | UOM **无一致性校验** | 源单 uom 直接覆盖行入参，不比对 | 发票按「箱」、PO 按「件」时，数量按错误单位静默通过 |
| A-5 | 异常原因**只存首个** | `_aggregate` / `_persist_line_result` 取 `reasons[0]` | 同行多异常不可见，用户改完一条再报下一条 |
| A-6 | 纯费用发票**完全绕过对账** | `_validate_charge_reconciliation` 无 `order_id` 直接 `return ''` | 无 PO 锚点的运费/附加费发票零校验过账 |

#### B 类（已声明未接通）

| ID | 项 | 现状 | 处置 |
|---|---|---|---|
| B-1 | `match_status` 枚举 `currency_mismatch` / `supplier_mismatch` | YAML 已播种，服务层从不产出（币种/供应商实为硬 `raise`） | **删除枚举值**（§24.5） |
| B-2 | `match_status` 枚举 `no_receipt` | 无产出路径 | **接线**：`gr_based` 行缺收货锚点 → 置该状态 + 可 override（R-VI-45） |
| B-3 | `vi_po_tax_compare` | v264 播种标「预留」，无消费 | 按 §24.3.6 消费（R-VI-46） |
| B-4 | `tolerance_direction` | `_param_def` 已查询，全库无消费点 | 按 §24.3.7 消费（R-VI-47）；默认行为不变（仅上界） |

#### C 类（标准 3-way 能力，W10-2 / W10-3）

| ID | 缺口 | 处置 |
|---|---|---|
| C-1 | `gr_based` 粒度为**收货行**，不支持「PO 行 + 多收货单累计」 | W10-2 契约见 §24.8 |
| C-2 | 无匹配工作台 / 差异池 / 批量提交 | W10-3；维持 §1.2 的波次边界 |
| C-3 | 费用行无法归属到具体 PO（多 PO 场景） | W10-1 以「拒绝 + 可执行提示」替代（R-VI-39），不做自动拆分 |

### 24.3 判定口径细化

#### 24.3.1 源单状态白名单（R-VI-38）

| 源单 | 可匹配状态 | 其他状态 |
|---|---|---|
| `purchase_orders.status` | `confirmed` | `draft` / `closed` / `cancelled` → `VI_SOURCE_STATUS_INVALID` |
| `receipts.status` | `posted` | `draft` / `cancelled` / `reversed` → `VI_SOURCE_STATUS_INVALID` |

- 校验时机：`_open_qty` 取数前（`match()` 与 `post()` 重算共用同一入口）。
- **不可 override**：源单状态是事实约束，不提供行级放行（避免「草稿收货直接入账」）。
- 已 `closed` 的 PO 若确有未开票余量，走 PO 侧「重新打开」流程，不在发票侧留后门。

#### 24.3.2 费用对账算法（R-VI-39 ~ R-VI-42）

```
charges = [l for l in lines if is_charge_line(l)]        # 运费 / 附加费 / 折扣
goods   = [l for l in lines if not is_charge_line(l)]
po_ids  = distinct(order_id 反查(goods 行, 经 schedule / order_line / receipt_line))
total   = Σ charge.net_amount                            # 折扣行为负值
tol     = vi_freight_tolerance_abs

if po_ids 为空:
    → abs(total) ≤ tol ? '' : 'VI_CHARGE_UNANCHORED'    # R-VI-42
if |po_ids| > 1:
    → 所有 PO 头 (surcharge + discount) 均为 0 且 abs(total) ≤ tol ? ''
      : 'VI_CHARGE_MULTI_PO_UNSUPPORTED'                # R-VI-39
po = 唯一 PO
target = po.header_surcharge_amount + po.header_discount_amount   # R-VI-40，discount 为负
if abs(total - target) > tol: → REASON_FREIGHT
```

- **R-VI-40**：禁止 `if not target` 式回退；`surcharge` 与 `discount` 必须**同时累加**。
- **R-VI-41（费用余量）**：过账时校验同一 PO 下**已过账发票**的费用行合计（含负向折扣）≤ `surcharge + discount` + `vi_freight_tolerance_abs`，超出 → `VI_CHARGE_EXHAUSTED`（exception，可 override）。
  - 统计口径：`vendor_invoices.status IN ('posted','reversed')` 按 `document_category='invoice'` 计入；红字贷项按 `direction` 负向冲减后参与合计（与 `v_doc_flow_consumed_qty` 同构，但费用行无边，故就地聚合）。
  - 边界：费用行不写边（R-VI-29 不变），本约束是**唯一**的费用上限保护。
- **R-VI-42**：纯费用发票（无任何 PO 锚点）费用合计非 0 → `VI_CHARGE_UNANCHORED`（例外可放行，需 override 留痕，适用于无 PO 的零星运费）。
- 对账基准：**分摊前**行金额（`_allocate_charges` 不改合计，二者等价）；`document_category` 仅 `invoice` 参与，贷项/借项/调整单跳过（维持现状）。

#### 24.3.3 UOM 一致性（R-VI-43）

- 规则：发票行 `uom_id` 非空且 ≠ 源单（PO 行 / 收货行）`uom_id` → `VI_UOM_MISMATCH`，**拒绝**，不做静默覆盖、不做自动换算。
- `_normalize_line_anchors` 保留「源单覆盖」语义，但**先比对后覆盖**：比对失败即抛错，不写库。
- 源单 `uom_id` 为空时以发票行值为准（历史数据兜底）。

#### 24.3.4 异常原因多值（R-VI-44）

- 落库格式：
  - 单值 → 纯文本（`price_over_tolerance`），**保持现有前端与测试兼容**；
  - 多值 → JSON 数组字符串（`["price_over_tolerance","qty_over_receipt_tolerance"]`），顺序按 `REASON_*` 常量声明序。
- 解析约定：读取方先尝试 `json.loads`，失败按纯文本处理（前端必须容错）。
- `_aggregate`（头级）取**全部**行 reason 去重并集；`_persist_line_result`（行级）写该行全部 reason。

#### 24.3.5 匹配枚举闭合（R-VI-45）

| 枚举值 | 处置 |
|---|---|
| `unmatched` / `matched` / `exception` / `overridden` | 保持 |
| `no_receipt` | **接线**：`gr_based` 且行无 `receipt_line_id` → `match_status='no_receipt'`，reason `VI_NO_RECEIPT`；按 R-VI-16 可 override（对齐 D-VI-3「兼容先开票后收货」） |
| `currency_mismatch` / `supplier_mismatch` | **从 YAML 删除**（硬 `VI_CURRENCY_MISMATCH` / `VI_SUPPLIER_MISMATCH` 已是事实出口，保留即幽灵枚举） |

#### 24.3.6 PO 税额比对（R-VI-46）

- 条件：参数 `vi_po_tax_compare = true`（默认 false，保持向后兼容）。
- 计算：`expected_tax = round_amount(发票行不含税金额 × PO 行 tax_rate_percent / 100)`；PO 行为含税价口径时先按税率反算不含税金额。
- 比对：`abs(行 tax_amount − expected_tax) > vi_tax_tolerance_abs` → reason `VI_PO_TAX_MISMATCH`（与既有 `VI_TAX_MISMATCH` 区分：前者对 PO 税率，后者对行内税基/税率自洽）。
- 源单缺 `tax_rate_percent` 时跳过（不阻断历史单据）。

#### 24.3.7 容差方向（R-VI-47）

- 取值来源：`control_parameter_def` 既有列 `tolerance_direction`，作用于 `vi_price_tolerance`。
- 语义：`null` / `upper` → 仅上界（**默认，行为不变**，对齐 A8 / SAP `DQ`）；`both` → 上下界；`lower` → 仅下界。
- 下界失败 reason：`price_under_tolerance`（新增）；上界仍为 `price_over_tolerance`。
- 数量容差**不**支持 `both`（对齐 A8，防止「少开票」被误判为异常）。

### 24.4 新增不变量总表（§6.3 追加）

| 编号 | 不变量 | 落点 |
|---|---|---|
| R-VI-38 | 源单（PO / 收货单）状态必须 ∈ 白名单 | `_open_qty` 前置 |
| R-VI-39 | 含费用行的发票，非费用行锚定 PO 必须唯一（或各 PO 头费用全 0） | `_validate_charge_reconciliation` |
| R-VI-40 | 费用对账目标 = `surcharge + discount`（折扣负值，禁止回退） | 同上 |
| R-VI-41 | 同一 PO 已过账费用合计 ≤ 头费用合计 + 容差 | `post()` 事务内 |
| R-VI-42 | 无 PO 锚点的费用发票，费用合计非 0 即 exception | `_validate_charge_reconciliation` |
| R-VI-43 | 行 uom 必须等于源单 uom（禁止静默覆盖） | `_normalize_line_anchors` |
| R-VI-44 | 多异常不得丢弃（单值纯文本 / 多值 JSON 数组） | `_aggregate` / `_persist_line_result` |
| R-VI-45 | `match_status` 枚举每个值必须有产出路径 | `_match_line` / YAML |
| R-VI-46 | `vi_po_tax_compare=true` 时按 PO 行税率重算比对 | `_validate_line_tax` |
| R-VI-47 | 价格容差方向由 `tolerance_direction` 决定，默认仅上界 | `_allowed_upper`（改名 `_allowed_bounds`） |

### 24.5 错误码与 reason 字典（增量）

| 类型 | 常量 | 触发 | 可否 override |
|---|---|---|---|
| 硬错 | `VI_SOURCE_STATUS_INVALID` | R-VI-38 | 否 |
| 硬错 | `VI_UOM_MISMATCH` | R-VI-43 | 否 |
| 硬错 | `VI_CHARGE_MULTI_PO_UNSUPPORTED` | R-VI-39 多 PO 费用 | 否（需拆票） |
| 行异常 | `VI_CHARGE_EXHAUSTED` | R-VI-41 | 是 |
| 行异常 | `VI_CHARGE_UNANCHORED` | R-VI-42 | 是 |
| 行异常 | `VI_NO_RECEIPT` | R-VI-45 | 是 |
| 行异常 | `VI_PO_TAX_MISMATCH` | R-VI-46 | 是 |
| 行异常 | `price_under_tolerance` | R-VI-47 下界 | 是 |

### 24.6 数据模型与参数变更

| 项 | 变更 | 迁移 |
|---|---|---|
| 表 / 列 | **无**（`match_exception_reason` 已是 text，可存 JSON） | 无 |
| `vendor_invoice.yaml` `match_status` 枚举 | 删除 `currency_mismatch` / `supplier_mismatch` | YAML 变更 + `sync_schema --generate` |
| `control_parameter_value` | 可选：`vi_price_tolerance.tolerance_direction='both'`（不播种，默认不进配置） | 无 |
| `vi_po_tax_compare` | 保持默认 false | 无 |

### 24.7 测试矩阵（W10-1）

| # | 用例 | 期望 |
|---|---|---|
| 1 | 单 PO，surcharge=50 且 discount=-20，费用行合计 30 | matched |
| 2 | 单 PO，surcharge=50 且 discount=-20，费用行合计 50 | `VI_FREIGHT_OVER_TOLERANCE` |
| 3 | 双 PO 合并发票含费用行（任一 PO 头费用非 0） | `VI_CHARGE_MULTI_PO_UNSUPPORTED` |
| 4 | 双 PO 合并发票含费用行（两 PO 头费用全 0，费用合计 0） | matched |
| 5 | 纯费用发票，费用合计 100，无 PO 锚点 | `VI_CHARGE_UNANCHORED` |
| 6 | 同一 PO 第二张发票重复报销同额附加费 | `VI_CHARGE_EXHAUSTED` |
| 7 | PO `closed` 仍有余量 | `VI_SOURCE_STATUS_INVALID` |
| 8 | 收货单 `draft` 作为 3-way 锚点 | `VI_SOURCE_STATUS_INVALID` |
| 9 | 发票行 uom ≠ PO 行 uom | `VI_UOM_MISMATCH` |
| 10 | 一行同时超价 + 超量 | reason 为 2 元 JSON 数组 |
| 11 | `gr_based` 行无 `receipt_line_id` | `no_receipt` + override 后可过账 |
| 12 | `vi_po_tax_compare=true`，行税额偏离 PO 税率重算值 | `VI_PO_TAX_MISMATCH` |
| 13 | `tolerance_direction='both'`，单价低于 PO 价超容差 | `price_under_tolerance` |
| 14 | 默认参数回归（既有 25 例 match 测试） | 全绿，行为不变 |

### 24.8 波次划分

| 波次 | 范围 | 迁移 | 备注 |
|---|---|---|---|
| **W10-1（已实施 2026-11-14）** | R-VI-38 ~ R-VI-47 + YAML 枚举收敛 | 无 | 低风险；除 R-VI-44 需前端容错外无外部影响 |
| W10-2 | C-1：`gr_based` 增加「PO 行聚合锚点」——`order_line_id` 为锚，余量 = `Σ qty_invoiceable(该行全部收货行) − Σ ap_match 已耗（按收货行集合聚合）`；`no_receipt` 例外路径复用 R-VI-45 | 无（复用 `order_line_id` 列） | 需先补视图按 `source_id IN (...)` 聚合的查询契约 |
| W10-3 | C-2：匹配工作台 / 差异池 / 批量提交 | 无 | 维持 §1.2「本波不做」的边界，独立波次评估 |

### 24.9 对既有条款的修订索引

| 既有条款 | 修订 |
|---|---|
| §22.6 费用规则第 5 条（「PO 头附加费/折扣非 0 时比对」） | 补全算法与符号口径 → §24.3.2（R-VI-39 ~ 42），明确「多 PO 拒绝 + 折扣负值累加 + 费用余量 + 无锚点不放行」 |
| §22.9 / R-VI-29（费用行不写边） | 维持；但补 R-VI-41 作为唯一费用上限保护 |
| §5.2 / A8（数量容差单向） | 维持；价格容差方向由 R-VI-47 显式化 |
| §22.8 匹配口径 | 追加 R-VI-38（源单状态）、R-VI-43（UOM）、R-VI-45（枚举闭合） |
| §22.10 行类型与税额 | 追加 R-VI-46（PO 税额比对） |
| §3.3 / `vendor_invoice.yaml` `match_status` 枚举 | 删除 `currency_mismatch` / `supplier_mismatch`，接线 `no_receipt` |
| §1.2 边界（匹配工作台不做） | 维持，W10-3 再评估 |
| §6.3 不变量表 | 追加 R-VI-38 ~ R-VI-47 |

### 24.10 明确不做

- 不做费用行**自动拆分到多 PO**（按金额比例拆分会制造不可解释的分摊事实）。
- 不做 UOM **自动换算**（需要换算率主数据，属基础资料波次）。
- 不做匹配**审批流** / 付款挂起（D-VI-12 / D-VI-17 已裁决）。
- 不做行级多币种（D-VI-18 永久关闭）。

---

## 25. 端到端 / 逆向 / 异常一致性补强（2026-11-14 复盘追加）

> 触发：2026-11-14 以「业务单据流端到端 → 逆向 → 异常」三视角对 `vendor_invoice` 域做只读代码复核（证据等级 `C`：逐文件读实现，非推断）。
> 结论：§22 ~ §24 已把**正向匹配**（三单对碰 / 费用 / 税 / 容差 / UOM）做扎实；缺口集中在**跨域联动**（收货 / PO / 应付期次 / 退货）与**逆向路径闭合**。本节不改已实施条款行为（R-VI-38 ~ 47 维持），只补链路。
> 编号约定：本节缺口用 `E2E-*`（正向端到端）/ `REV-*`（逆向）/ `EXC-*`（异常），**不复用** §22.0 的 `G-1 ~ G-16`；新不变量从 **R-VI-48** 起。

### 25.0 缺口台账（分档）

| # | 缺口 | 档位 | 证据（C） | 落点 |
|---|---|---|---|---|
| E2E-01 | 应付期次只写不读：`vendor_invoice_schedules` 全仓仅 INSERT（`vendor_invoice_match_service.py` 期次写入点），无 UPDATE / DELETE、无生产读方；`amount_applied` 恒 0、无逾期 / 账龄出口 ⇒ §23 生成的期次是「死数据」 | 承诺未实现 | 期次唯一写入点 + 全仓 grep 无读方 | R-VI-50 / 25.6 视图 |
| E2E-02 | 退货贷项无敞口追踪：`v_vendor_return_open_amount` 仅存在于本 Spec 未实现；`return_line` 锚点贷项行 `invoice_line_id` 为空 ⇒ 不写冲减边；无「贷项金额 ≤ 退货可贷金额」校验（全仓无 `VI_RETURN_EXCEEDED`） | 真遗漏 | `_insert_lines` 回指逻辑 + 全仓 grep | R-VI-51 |
| E2E-03 | PO 侧无 billing 消耗守卫：`purchase_order_guard_service` 无任何 `invoiced / billing / consumed` 判定 ⇒ 已开票的 PO 仍可关闭 / 改量 / 删行，在途发票变悬挂 | 真遗漏 | 同目录 grep No matches | R-VI-54 |
| REV-01 | 收货红冲不校验发票消耗（**P0 最高**）：`receipt_service.reverse()` 仅校验 posted / red / 重复红冲；`receipt.yaml` 的 `doc_flow` 补偿 `rule_ids` 不含 `receipt_line_to_vendor_invoice_line`（`ap_match`）⇒ 已 3-way 匹配的收货单可红冲，`ap_match` 边悬挂；再叠加 `_open_qty` 的 `max(..., 0.0)` ⇒ 负余量被静默吞掉 | 真遗漏（最高） | `receipt_service.py` `reverse()` + `receipt.yaml` `doc_flow` | R-VI-48 |
| REV-02 | 逆向不联动应付期次：红字单 / 调整单 / 取消单一律不生成期次（`_generate_schedules` 直接 `return []`），原票期次又只读（R-VI-35）⇒ 红冲后应付台账仍显示全额待付（**负债虚增**） | 真遗漏 | `_generate_schedules` docstring / 分支 | R-VI-49（修订 R-VI-36） |
| REV-03 | 贷项 / 借项不可再更正：`_assert_reversible` 要求 `document_role='invoice'` + `direction=1`；`create_adjustment` 原单仅接受 `invoice / adjustment` ⇒ 贷项开错（多贷）无红冲、无调整路径，只能取消重开且取消不适用 posted | 真遗漏 | `_assert_reversible` / `create_adjustment` | R-VI-52 |
| EXC-01 | 外币汇率零校验：`_validate_amounts` 只校行 / 头算术恒等式，全仓 `exchange_rate` 在匹配服务无命中 ⇒ `exchange_rate = 0 / NULL` 的外币发票可过账，本位币金额无意义 | 真遗漏 | `_validate_amounts` | R-VI-53 |
| EXC-02 | 空供应商发票号可过账：查重键含 `supplier_invoice_no`，空号归一为 `''`，对空号不构成硬拦 ⇒ 多张空号发票并存、无法与供应商对账 | 真遗漏 | `normalize_supplier_invoice_no` + 查重路径 | R-VI-55 |
| EXC-03 | 期间 / 过账日期无约束：`posting_date` 缺省取 `invoice_date`，可回填任意历史月；无「期间已关闭」概念 | 真遗漏 | 过账 / 红冲日期取值 | R-VI-56 |
| EXC-04 | 供应商主数据有效性未校验：停用 / 冻结供应商仍可建票过账（只校 `supplier_account_id` 存在且与 PO 一致） | 真遗漏 | `_validate_supplier` | R-VI-57 |
| EXC-05 | `cancellation` 类型是死枚举：`document_category='cancellation'` 已 seed（`VENDOR_INVOICE_CANCEL`）、`line_source_policy` 已声明，但动作面只有 `cancel`（draft/submitted → cancelled）与 `reverse`（生成 `credit_memo`），**无 `create_cancellation`** | 真遗漏（口径不一致） | `vendor_invoice_actions.py` | R-VI-58 |
| EXC-06 | `no_receipt` 放行后无重匹配入口：置 `no_receipt` 可强制过账，但收货到货后无幂等 `rematch` 动作回填 `ap_match` 边 | 真遗漏（可用性） | 动作面 grep | R-VI-59 |

**已裁决、不重复立项**（复核确认属既有边界）：付款事实层 / 付款批 / 账龄（§23.9 独立波次）、预付与现金折扣（同）、GL / GR-IR（§1.2 无 GL 域）、W10-2（`gr_based` PO 行聚合锚点）、W10-3（匹配工作台）、匹配方案对象（D-VI-20）、行级多币种（D-VI-18）。

### 25.1 正向端到端对账矩阵

| 环节 | 上游事实 | 本域动作 | 下游联动 | 现状 | 补齐 |
|---|---|---|---|---|---|
| PO → 发票 | `purchase_order_schedule` 计划量 | `billing` 边 | PO 已开票量 | 有边；PO 侧无守卫 | R-VI-54 |
| 收货 → 发票 | `receipt_line.qty_received` | `ap_match` 边 | 收货行已开票量 | 有边；收货红冲不查边 | R-VI-48 |
| 退货 → 贷项 | `vendor_return` 行 | 贷项行（`return_line` 锚点） | 退货敞口 | 无追踪、无边 | R-VI-51 |
| 发票 → 应付 | 过账 | `vendor_invoice_schedules` | 付款波次 | 只写不读 | R-VI-50 |
| 发票 → 逆向 | 红冲 / 调整 | 红字单 / 调整单 | 应付净额 | 期次不联动 | R-VI-49 |

### 25.2 逆向链路（红冲 / 取消 / 调整 / 退货）

#### 25.2.1 收货红冲前置守卫（REV-01 / R-VI-48）

- 规则：收货单 `reverse()` 前必须检查其行是否存在**未被红字抵消**的 `ap_match` 消耗（`normal − red > 0`，按 `receipt_line_id` 聚合 `v_doc_flow_consumed_qty`）。
- 命中 ⇒ 拒绝，错误码 `RC_CONSUMED_BY_VENDOR_INVOICE`（`field='receipt_line_id'`，message 列出占用发票号）；**不走 override**。
- 处置指引写进 message：先红冲 / 冲减对应发票行 → 再红冲收货单。
- **YAML 侧不做补偿**：`receipt.yaml` 的 `doc_flow.rule_ids` **不得**加入 `receipt_line_to_vendor_invoice_line`（发票消耗边是应付事实，不能由收货红冲「代为补偿」）；守卫在 `receipt_service.reverse` 前置执行。
- 兜底：`_open_qty` 的 `max(..., 0.0)` **保留**（防历史脏数据抛负），但新增负余量告警投影（25.6 `v_vendor_invoice_negative_open`），把静默吞掉改为可观测。

#### 25.2.2 应付期次净额化（REV-02 / R-VI-49，**修订 R-VI-36**）

- `R-VI-36` 原口径「红字单 / 取消单不生成期次」改写为：
  - `credit_memo`（含红冲生成的红票）与 `adjustment(direction=decrease)`：**生成负额期次**（`amount = -|原期次金额 × 比例|`、`ratio_percent = -|ratio|`、`due_date` 沿用原期次、`status='open'`），使「原期次 + 负期次」净额 = 原票 − 红冲；
  - `adjustment(direction=increase)`：生成**正额期次**（与蓝票同口径）；
  - `cancellation`：**仍不生成期次**（取消只作用于 draft/submitted，从未生成过期次，口径不变）。
- 守住 `R-VI-35`（posted 后期次只读）：原票期次**不就地修改**，只追加反向期次；净额由视图求和（单一事实源）。
- `due_date` 对齐：负额期次取被冲原期次的 `due_date`；原票无期次（缺付款条件）时负额期次也不生成，`audit_logs` 记 `schedule_skip_reason='source_has_no_schedule'`。
- 唯一入口：`_generate_schedules(invoice_id, header, lines)` 增加 `sign = -1` 分支；禁止在 `reverse()` / `create_adjustment()` 内另写 INSERT。

#### 25.2.3 贷项 / 借项的更正路径（REV-03 / R-VI-52）

- `_assert_reversible` 放宽 `document_role` 白名单为 `invoice / credit_memo / debit_memo`，并要求目标类型 `reversal_type_id` 已配置且 `direction` **与原单相反**（§3.2 已 seed：`credit_memo → debit_memo`、`debit_memo → credit_memo`）。
- 更正单 `document_category` **由类型严格派生**，不得硬写 `credit_memo`（`red_meta.document_category` 缺失即抛 `VI_TYPE_INVALID`）；头 / 行金额一律取原单镜像取反（发票正行 → 贷项负行；贷项负行 → 借项正行）。
- `create_adjustment` 原单白名单扩为 `invoice / credit_memo / debit_memo / adjustment`；`increase` **仅允许 `invoice` 原单**（其余抛 `VI_ADJUSTMENT_INCREASE_UNSUPPORTED`）；贷项 / 借项原单的 `decrease` 只落金额台账与期次，不写消耗边（原单本就无正向边）。
- 借项通知单仍不写 `billing / ap_match` 消耗边（维持 §21 口径）⇒ 其逆向只影响金额台账与期次，不影响可开票余量。
- 贷项红冲（→ 借项）的边处理：`write_red_edges_for_red_doc` 对 `debit_memo` 逐行按 `invoice_line_id`（= 贷项行 id）撤销贷项留下的 active 红字边（A 档 `reverse_edge`），恢复原发票边可用量；`_find_red_document` 不再按 `direction < 0` 过滤（借项 direction = +1）。

#### 25.2.4 取消与 `cancellation` 类型收敛（EXC-05 / R-VI-58）

- 现状：`cancel()` 是**状态迁移**（draft/submitted → cancelled，posted 拒绝）；`cancellation` 类型从未被任何动作创建。
- 裁决（取 **A**）：
  - **A（推荐，低风险）**：`type_definitions` 中 `VENDOR_INVOICE_CANCEL` 置 `status='inactive'`（保留行以兼容历史引用）；`line_source_policy[CATEGORY_CANCELLATION]` 保留但标注「暂无创建入口」；文档口径明确「取消 = 状态迁移，不是单据」。
  - B：实现 `create_cancellation`（生成 `cancellation` 单据 + `reversal_of_invoice_id` 回指 + 不生成期次）——成本高、与 `reverse` 语义重叠，本次不取。
- 若未来出现「供应商开具取消单」的合规硬要求，再走 B（TBD-VI-C1）。

### 25.3 异常与边界（EXC-01 ~ EXC-06）

| # | 规则 | 校验点 | 错误码 | 参数 |
|---|---|---|---|---|
| EXC-01 | 头币种 ≠ 本位币时 `exchange_rate` 必填且 `> 0`；本位币时归一为 1 | 过账前 | `VI_EXCHANGE_RATE_REQUIRED` | 无 |
| EXC-02 | `supplier_invoice_no` 非空方可 submit / post；空号票据只允许停留 draft | submit / post | `VI_SUPPLIER_NO_REQUIRED` | `vi_require_supplier_invoice_no`（默认 true） |
| EXC-03 | `posting_date` ∈ [当前会计月 − `vi_period_open_months_back`, 系统日 + `vi_posting_date_forward_days`]；红字日期 ≥ 原票 `posting_date`（既有 `VI_REVERSAL_DATE_INVALID` 保留） | 过账 / 红冲 | `VI_PERIOD_CLOSED` / `VI_POSTING_DATE_INVALID` | `vi_period_open_months_back`(2) / `vi_posting_date_forward_days`(0) |
| EXC-04 | `supplier_account_id` 对应供应商须 `status='active'`（停用 / 冻结拒绝新票；已 posted 票不受影响） | 创建（draft 可留）/ 过账 | `VI_SUPPLIER_INACTIVE` | 无 |
| EXC-05 | 见 25.2.4（cancellation 收敛） | — | — | — |
| EXC-06 | 见 25.3.1（`rematch`） | — | — | — |

#### 25.3.1 `no_receipt` 重匹配（EXC-06 / R-VI-59）

- 新增动作 `vendor_invoice.rematch`：`POST /api/v1/vendor_invoices/{id}/rematch`，`from_states: posted`，仅对 `match_status='no_receipt'` 或存在未回填 `receipt_line_id` 的 `gr_based` 行生效。
- 语义：**只补边、不改金额**——按当前可开票余量重算该行 `ap_match` 边，状态 `overridden → matched` 并留痕（`audit_logs.action='rematch'`）。
- 幂等：行已有足额 `ap_match` 边时直接返回 `noop`（不重复写边，`uq_doc_flow_idem` 兜底）。
- 禁止：`posted` 后改数量 / 单价 / 税额（维持 §6 状态机）；`rematch` 拒绝金额字段入参。

### 25.4 新增不变量（R-VI-48 ~ R-VI-59）

| ID | 不变量 | 校验点 | 缺口 |
|---|---|---|---|
| R-VI-48 | 收货单红冲前，其行不得存在未抵消的 `ap_match` 消耗（`normal − red > 0`） | `receipt_service.reverse` 前置 | REV-01 |
| R-VI-49 | 应付敞口 = 原票期次 + 红字负额期次 + 调整正 / 负额期次之和；原票期次只读，禁止就地扣减 | `_generate_schedules` + 视图 | REV-02 |
| R-VI-50 | 期次表必须有生产读方（≥1 个视图 / 接口）；`amount_applied` 只由付款域写，付款域落地前恒 0，视图中以 `open_amount = amount` 表达 | `v_vendor_payable_open` | E2E-01 |
| R-VI-51 | 退货贷项金额 ≤ 对应退货行未贷金额（`v_vendor_return_open_amount.amount_open`） | 贷项 submit / 过账 | E2E-02 |
| R-VI-52 | 贷项 / 借项 / 调整单均可逆向更正；更正单方向必须与原单相反（由 `reversal_type_id` 保证） | `_assert_reversible` | REV-03 |
| R-VI-53 | 外币发票 `exchange_rate` 必填且 `> 0`；本位币归一为 1 | 过账前 | EXC-01 |
| R-VI-54 | PO 关闭 / 改量 / 删行前，不得存在未抵消的 `billing` 消耗 | `purchase_order_guard_service` | E2E-03 |
| R-VI-55 | `supplier_invoice_no` 非空方可 submit / post（开关可关，默认开） | submit / post | EXC-02 |
| R-VI-56 | `posting_date` ∈ [当前月 − N 月, 系统日 + M 天]；红字日期 ≥ 原票过账日期 | 过账 / 红冲 | EXC-03 |
| R-VI-57 | 供应商须 `active` 才可过账（草稿允许暂存） | 过账 | EXC-04 |
| R-VI-58 | `cancellation` 类无创建入口，`VENDOR_INVOICE_CANCEL` 置 inactive；「取消」= 状态迁移 | 类型种子 + 动作面 | EXC-05 |
| R-VI-59 | `rematch` 只补 `ap_match` 边、不改金额、幂等 | 动作面 | EXC-06 |

> 编号衔接：R-VI-48 承接 §24 的 R-VI-47；R-VI-19 仍保留给 SES / ERS。

### 25.5 错误码增量

| 错误码 | 触发 | 可 override | 层级 |
|---|---|---|---|
| `RC_CONSUMED_BY_VENDOR_INVOICE` | 收货行已被 3-way 匹配，红冲被拒 | 否 | 收货域 |
| `PO_CONSUMED_BY_VENDOR_INVOICE` | PO 计划行存在未抵消 `billing` 消耗，关闭 / 改量被拒 | 否 | PO 域 |
| `VI_RETURN_EXCEEDED` | 贷项金额超过退货可贷余量 | 否 | 发票域 |
| `VI_EXCHANGE_RATE_REQUIRED` | 外币缺汇率或 `≤ 0` | 否 | 发票域 |
| `VI_SUPPLIER_NO_REQUIRED` | 供应商发票号为空 | 是（开关关闭时不触发） | 发票域 |
| `VI_PERIOD_CLOSED` | 过账日期早于开放期间 | 否 | 发票域 |
| `VI_POSTING_DATE_INVALID` | 过账日期晚于允许的未来天数 | 否 | 发票域 |
| `VI_SUPPLIER_INACTIVE` | 供应商非 active | 否 | 发票域 |
| `VI_REMATCH_NOT_APPLICABLE` | 行无需重匹配 / 无可开票余量 | 否 | 发票域 |

> 既有 `VI_REVERSAL_DATE_INVALID` / `VI_NOT_REVERSIBLE` / `VI_REVERSAL_EXISTS` 保留；R-VI-52 后 `VI_NOT_REVERSIBLE` 仅在 `document_role` 不在白名单时触发（未配 `reversal_type_id` 抛 `VI_REVERSAL_NOT_DECLARED`）。

### 25.6 数据模型 / 视图 / 迁移（W11-1 v272 / W11-2 v273）

| 变更 | 内容 | 迁移 |
|---|---|---|
| `vendor_invoice_schedules.amount / ratio_percent` | 允许负值（红字负额期次）；若存在 `CHECK (amount >= 0)` 放宽为 `amount <> 0` | v272 |
| 新视图 `v_vendor_payable_open` | `supplier_account_id / invoice_id / schedule_no / due_date / amount / amount_applied / open_amount(= amount − amount_applied) / aging_bucket(0-30/31-60/61-90/90+) / currency_id`，供付款波次与逾期报表读取 | v272（`generated_schema.sql` 重建） |
| 新视图 `v_vendor_return_open_amount` | `return_line_id / qty_returned / amount_returned / amount_credited / amount_open`；退货 = 退货收货行（`receipts.document_type_id` → `type_definitions.scope_bo='receipt' AND document_category='return'`，状态 posted）；`amount_returned = ABS(qty_received) × PO 行单价`（D-RC-9 收货行无价）；`amount_credited` = 按 `vendor_invoice_lines.return_line_id` 聚合 **posted** 贷项行 `ABS(net_amount)`（贷项被红冲后原单置 reversed 自动剔除） | v273 |
| 新视图 `v_vendor_invoice_negative_open` | 负余量告警投影：`(source_bo, source_id, pool, open_qty)` where `open_qty < 0`（把 `max(0)` 静默吞掉变为可观测） | v272 |
| `receipt.yaml` | `doc_flow.rule_ids` **保持不含** `receipt_line_to_vendor_invoice_line`（25.2.1）；补注释说明守卫位置 | YAML 注释 + `sync_schema --generate` |
| `control_parameter_def` | 新增 `vi_require_supplier_invoice_no`(bool, true)、`vi_period_open_months_back`(int, 2)、`vi_posting_date_forward_days`(int, 0) | v272 seed |
| `type_definitions` | `VENDOR_INVOICE_CANCEL.status='inactive'` | v272 |
| 动作面 | 新增 `vendor_invoice.rematch` | YAML `actions` + handler |
| 表结构 | 其余 **无新增列**（汇率、供应商状态均读上游，不落副本） | — |

### 25.7 波次划分（W11 / W12 / W13）

| 波次 | 范围 | 迁移 | 风险 |
|---|---|---|---|
| **W11-1（P0，建议先做）** ✅ 已实施（2026-11-14） | R-VI-48（收货红冲守卫）+ R-VI-49（期次净额化，修订 R-VI-36）+ R-VI-50（`v_vendor_payable_open`）+ `v_vendor_invoice_negative_open` | v272 | 触及收货域与期次写入分支；需回归 §23 既有 9 例期次测试 |
| **W11-2（P1）** ✅ 已实施（2026-11-14） | R-VI-51（退货贷项余量 + `v_vendor_return_open_amount`）+ R-VI-52（贷项逆向）+ R-VI-53（汇率） | v273 | 类型白名单放宽，已补「贷项红冲 → 借项」用例 |
| **W12（P2）** | R-VI-54（PO 守卫）+ R-VI-55（发票号必填）+ R-VI-56（期间）+ R-VI-57（供应商状态） | v272 | PO 守卫可能影响既有 PO 关闭测试；参数默认值须保守 |
| **W13（P3）** | R-VI-58（cancellation 收敛）+ R-VI-59（`rematch`） | v272 / 无 | 低风险；`rematch` 需前端按钮与权限码 |

> 顺序理由：W11-1 修的是「账不实」（红冲后负债虚增、收货红冲留悬挂边），必须先于任何付款域工作；W11-2 修「退货与错单的处理路径」；W12 / W13 是防护性校验与可用性补强。

### 25.8 对既有条款的修订索引

| 既有条款 | 修订 |
|---|---|
| §23.6 / **R-VI-36**（红字单 / 取消单不生成期次） | **改写**为「红字 / 贷项与调整 decrease 生成负额期次；cancellation 仍不生成」，见 25.2.2 |
| §23.6 / R-VI-35（posted 后期次只读） | **维持**；补「只读 = 不就地改，净额靠追加反向期次」 |
| §23.6 / R-VI-37（`amount_applied` 恒 0） | **维持**；补 R-VI-50 视图出口（`open_amount = amount − 0`） |
| §22.8 第 1 条 / R-VI-28（禁止静默截断） | **维持** `max(...,0.0)` 作为脏数据兜底，新增 `v_vendor_invoice_negative_open` 告警 |
| §22.9 不变量表 | 追加 R-VI-48 ~ R-VI-59（25.4） |
| §6 状态机 / `_assert_reversible` | 逆向白名单由 `invoice` 扩为 `invoice / credit_memo / debit_memo`（R-VI-52） |
| §3.2 类型种子（`VENDOR_INVOICE_CANCEL`） | `status='inactive'`（R-VI-58） |
| §1.2 边界（不做匹配工作台） | 维持；`rematch` 属单行幂等补边，不是工作台 |
| §24.8 波次（W10-2 / W10-3） | 维持；W11+ 见 25.7 |

### 25.9 明确不做 / 待决

- 不做 GL 凭证 / GR-IR 科目（§1.2 维持）。
- 不做付款域（`vendor_payment` / `payment_allocation` / 付款批 / 核销逻辑）：本节只提供 `v_vendor_payable_open` 读出口与账龄桶**字段口径**，实际逾期计算与核销归付款波次。
- 不做期间**账务锁定表**（`accounting_period` 对象）：R-VI-56 用参数做**软约束**，真锁定待会计域。
- 不做 PO 自动改量重匹配（R-VI-54 只拒绝，不自动调整）。
- **TBD-VI-C1**：供应商取消单（`cancellation` 单据化）——仅当出现合规硬要求时再评估（25.2.4 方案 B）。
- **TBD-VI-C2**：退货贷项自动生成（维持 D-VI-11 软配对，只做上限校验不强制配对）。

### 25.10 测试矩阵（建议）

| # | 用例 | 期望 |
|---|---|---|
| 1 | 收货行已被 3-way 匹配（`ap_match` active），红冲收货单 | `RC_CONSUMED_BY_VENDOR_INVOICE` |
| 2 | 先红冲发票（红边抵消 `ap_match`），再红冲收货单 | 成功，边净额为 0 |
| 3 | 红冲 posted 蓝票（有 2 条期次） | 生成 2 条**负额**期次，`v_vendor_payable_open` 净额 = 0 |
| 4 | 调整 decrease（-100）于已过账票 | 生成 -100 期次，净额 = 原 − 100 |
| 5 | 调整 increase | 生成正额期次 |
| 6 | 取消 draft 发票 | 不生成期次（口径不变） |
| 7 ✅ | 贷项（`credit_memo`, posted）红冲 | 生成 `debit_memo`，方向相反；期次净额同向抵扣（`test_vendor_invoice_reversal_platform.py`） |
| 8 ✅ | 贷项 `create_adjustment(decrease)` / `(increase)` | decrease 成功；increase 被拒（R-VI-52）（`test_vendor_invoice_adjustment.py`） |
| 9 ✅ | 外币发票 `exchange_rate` 为空 / 0 | `VI_EXCHANGE_RATE_REQUIRED`（`test_vendor_invoice_match.py`） |
| 10 | 供应商发票号空串直接 submit | `VI_SUPPLIER_NO_REQUIRED` |
| 11 | `vi_require_supplier_invoice_no=false` + 空号 | 允许过账 |
| 12 | `posting_date` 早于 3 个月前（参数=2） | `VI_PERIOD_CLOSED` |
| 13 | `posting_date` 为明天（forward=0） | `VI_POSTING_DATE_INVALID` |
| 14 | 停用供应商建票 + 过账 | 草稿可建；过账 `VI_SUPPLIER_INACTIVE` |
| 15 | PO 有 active `billing` 边，关闭 PO | `PO_CONSUMED_BY_VENDOR_INVOICE` |
| 16 | `no_receipt` 已过账 → 收货到货 → `rematch` | 写 `ap_match` 边、置 `matched`，金额不变 |
| 17 | 同一行重复 `rematch` | `noop`，不重复写边 |
| 18 ✅ | 退货行 `amount_credited` 已满，再开贷项 | `VI_RETURN_EXCEEDED`（`test_vendor_invoice_match.py`） |
| 19 | 回归：§23 既有 9 例期次 + §24 的 14 例 | 全绿（默认参数行为不变） |

> 实施前置：迁移 v272 / v273 与视图需 `sync_schema --generate` 后跑 `python d:\filework\test.py --file meta/tests/services/test_vendor_invoice_match.py` + `--file meta/tests/migrations/test_vendor_invoice_migrations.py` + 收货域回归。

### 25.11 规则模型落位与 SSOT 收敛（2026-11-14 已实施）

> 目的：把 R-VI-48 ~ R-VI-59 在**规则模型 / 元数据 / 代码 / 视图**四层里各归其位，
> 消除「同一政策两处定义」。判定口径（L1~L4）：

| 层 | 载体 | 判据 |
|---|---|---|
| L1 规则模型 | YAML `rules:`（`constraint` / `validation`）+ `control_parameter_def` | 政策可调、按 org / 单据类型 / 行类型 / 物料组差异化、需拦截留痕 |
| L2 元数据声明 | `type_definitions.document_role` / `doc_flow_rule` / `line_source_policy` | 类型、方向、角色、边规则等结构性语义 |
| L3 代码 | 服务层 | 算法与跨对象不变量（规则引擎无跨 BO metric） |
| L4 视图 | SQL 派生视图 | 一切「现在有多少」的聚合，只读不反写 |

#### 25.11.1 逐条落位

| 规则 | 落位 | 状态 / 说明 |
|---|---|---|
| R-VI-48 收货红冲守卫 | L3 | 已实施；与 R-VI-54 共用 `v_doc_flow_consumed_qty` 口径，禁止再写第二份 SUM SQL |
| R-VI-49 期次镜像 | L3（算法）+ L2（策略） | 算法已实施；`category → 镜像 / 跳过` 待 `document_role.schedule_policy` 平台评审后上移 |
| R-VI-50 双视图 | L4 | 已实施；`aging` 30/60/90 为**报表契约常量**（视图读不到参数），如需组织差异只在报表层参数化 |
| R-VI-51 退货贷项余量 | L4（视图 v273）+ L3（拦截） | 已实施；余量走 `v_vendor_return_open_amount` 派生视图，不得落缓存列；拦截挂在 `submit` / `post` 两条路径 |
| R-VI-52 贷项逆向 | L2（元数据）+ L3（借项撤边） | 已实施；方向与 `document_category` 由 `reversal_type_id` 严格派生，服务只读元数据；借项撤销贷项红字边属跨对象写操作，落 L3 |
| R-VI-53 汇率必填 | **L3（原拟 L1）** | 已实施；规则引擎 `validation` / `cross_field` 无跨 BO 查询，读不到 `currencies.code`，故落服务层；外币且 `exchange_rate` 为空 / ≤0 → `VI_EXCHANGE_RATE_REQUIRED`，本位币归一为 1 |
| R-VI-54 PO 未确认守卫 | L3 | 跨对象，复用 R-VI-48 的消耗量 helper |
| R-VI-55 供应商发票号开关 | **L1（必须）** | `vi_require_supplier_invoice_no`（bool）+ `validation`；禁止硬编码开关 |
| R-VI-56 过账日期窗口 | **L1（必须）** | `vi_posting_window_past_months` / `vi_posting_window_future_days` + `constraint`，维度 org + document_type |
| R-VI-57 供应商启用 | L1 优先 / L3 兜底 | 取决于 metric 能否查供应状态；不得写成常量集合 |
| R-VI-58 取消单不可建 | L2 | `type_definitions` 停用 + 入口配置，不在代码里 `if category == cancellation` |
| R-VI-59 重复匹配幂等 | L3 + 平台约束 | `uq_doc_flow_idem` 兜底，已实施 |

#### 25.11.2 SSOT 硬约束（已收敛）

1. **行来源策略**：唯一事实源 = `vendor_invoice.yaml` 的 `line_source_policy` 段；
   服务通过 `_line_source_policy()` 读取（与 `customer_invoice` 同范式），**代码内不留副本**。
2. **参数默认值**：唯一事实源 = `control_parameter_defs.default_value`（v264 播种）；
   已删除 `DEFAULT_TAX_TOLERANCE`，定义缺失时按 0 严格校验，不在代码里复制政策默认值。
3. **池名**：唯一事实源 = `meta/core/doc_flow_schema.py` 的 `POOL_BILLING` / `POOL_AP_MATCH`；
   服务与迁移（含 v272 视图 DDL）一律引用常量，禁止字面量。
4. **待评审**：`document_role` 增 `schedule_policy ∈ {mirror, skip, none}`；
   未落地前，`category → 镜像集合` 只允许存在一处模块级常量。

#### 25.11.3 W12 动工门禁

- 新增可调政策必须先「`control_parameter_defs` 播种 + YAML `rules:` 声明」再写判定代码；先代码后参数视为违规。
- 新增跨对象守卫必须复用 `v_doc_flow_consumed_qty` + core 池常量，禁止另写一份消耗量 SQL。
- 禁止任何物理缓存量列（沿用 N3 / D-VI-4）。
- 读模型（视图）只增不改语义；分档阈值变更需同步本 Spec 与本条。

#### 25.11.4 回归证据

2026-11-14 收敛后：`test_vendor_invoice_match`(25) / `test_vendor_invoice_schedule`(13) /
`test_receipt_reversal`(11) / `test_vendor_invoice_migrations`(13) /
`test_receipt_service`(30) / `test_vendor_invoice_adjustment`(30) /
`test_vendor_invoice_reversal_platform`(8) —— 7 文件 130 例全绿。

2026-11-14 W11-2 落地后增补：`test_vendor_invoice_match` 31 例（含 R-VI-51 视图 / 超限拦截、R-VI-53 汇率 4 例）、
`test_vendor_invoice_migrations` 14 例（含 v273 migrate / verify / rollback）、
`test_vendor_invoice_reversal_platform` 新增「贷项红冲 → 借项 + 撤销红字边」1 例、
`test_vendor_invoice_adjustment` 原「贷项源被拒」用例替换为「贷项 decrease 允许 / increase 被拒」—— 全绿。