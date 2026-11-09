# Oracle Fusion 开票与更正深度研究（2026-11-09）

> 目的：为 S8 Wave A（customer_invoice）的覆盖度缺口提供 Fusion 侧事实依据。
> 范围：Fusion Cloud ERP 26D Receivables（AR）+ 26B SCM Order Management / Pricing。
> 结论只采用 docs.oracle.com 官方文档；找不到官方来源的条目标注「未找到官方来源」。

---

## 0. 结论先行

1. **Fusion AR 没有「发票级 Reverse（冲销）」动作**。26D 官方文档中发票更正只有三条路：
   **Void、Credit Memo、Adjustment**；`reversal date / reason / category` 属于**收款冲销**，
   debit memo reversal 也是收款侧概念。
2. **「取消」与「贷项」必须分开**：Void 仅适用于**未过账、无任何活动**的单据；
   一旦过账或已有核销，只能开 **Credit Memo**（可部分、可引用原单行、也可 on-account）。
3. **借项通知单（Debit Memo）与发票没有链接**，是独立单据、独立编号，用于补收（价格更正、漏收运费等）。
4. **AR 不是改价的地方**。价格真相在 Pricing / Order Management：改价 = Price Override + Reason（可配必填）+ 审批；
   开票后的价格更正走 **Credit and Rebill**（贷项冲原票 + Duplicate 重开票）。
5. **两段式生命周期**：Incomplete →（可选 Pending Approval）→ Complete；Complete 才生成付款计划、
   才进入账龄，Document Number 也在 Complete 阶段分配。

---

## 1. Fusion AR 的单据类型（Transaction Class）

官方通过 transaction class 区分单据，类型上有一组控制开关：

| 控制项 | 含义 |
|---|---|
| `naturalApplicationOnlyFlag` | 核销只能到余额为 0，禁止超额 |
| `allowOverapplicationFlag` | 允许超额核销 |
| `openReceivableFlag` | 是否计入客户余额 / 账龄 |
| `postToGLFlag` | 是否过账总账 |
| `allowAdjustmentPostingFlag` | 是否允许调整 |
| `allowFreightFlag` | 是否允许运费行 |
| `levelOfControlOfTransactionCompletion` | 完成控制级别：ALL / 仅负金额行 / NONE |

单据类别：

| Class | 语义 | 与发票的关系 |
|---|---|---|
| Invoice | 标准应收 | — |
| Credit Memo | 减少应收/收入，可引用原发票行，可 on-account | 可部分、可全额 |
| Debit Memo | 增加应收（补收） | **官方明确无链接**，只能用 Cross Reference 备注 |
| Chargeback | 核销时关闭原借项并新建借项 | 与贷项互斥（贷项不能 apply 到 chargeback） |
| Adjustment | 直接改原单余额，不产生新单据 | 发票/行/费用/税/运费五级 |
| Deposit / Guarantee / Bills Receivable | 预收/担保/票据 | 本波无关 |

来源：
- [Receivables Transaction Type BO](https://docs.oracle.com/en/cloud/saas/financials/26d/fabof/bo_oraErpCoreReceivablesSetup_ReceivablesTransactionType.html)
- [Requirements for Completing a Receivables Transaction](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/requirements-for-completing-a-receivables-transaction.html)
- [Natural Application and Overapplication](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/natural-application-and-overapplication.html)

---

## 2. 更正手段对比（本研究的核心）

| 手段 | 是否新单据 | 适用前提 | 是否可部分 | 引用原单 | 审批/限额 |
|---|---|---|---|---|---|
| **Void** | 否（原单改为 Void 类型） | 未过账、无收款/贷项/调整等活动 | — | — | 受文档号删除控制 |
| **Credit Memo** | 是（独立单号） | 已过账即可；已收款需先 unapply | 可部分/全额 | 可选（行级引用） | 贷项请求走 AMX 审批 |
| **Debit Memo** | 是（独立单号） | 补收场景 | 可 | **不支持**（无链接） | 不纳入完成审批控制 |
| **Adjustment** | 否（改原单余额） | 尾差/争议减免 | 按层级 | 隐含原单 | 按 document type + 币种 + 金额限额 |
| **Chargeback** | 是 | 争议转新借项 | — | 关闭原借项 | 不纳入完成审批控制 |

### 2.1 Void
- 需要单据**未过账 GL**、且**没有任何活动**（收款、贷项、调整）；已分配文档号时还受
  「Allow transaction deletion」与顺序编号限制。
- Void 后单据仍在，但类型为 Void、`Open Receivable=No`、`Post to GL=No`，不计余额与账务。
- 官方没有 `reversed` 状态。

### 2.2 Credit Memo
- 创建入口：Billing 工作区 Create Transaction（Transaction Class = Credit Memo）；
  正式流程是 Credit Memo Request + AMX 审批组，额度由 approval group 控制。
- 引用原单：AutoInvoice 用 `REFERENCE_LINE_ID` 或 `REFERENCE_LINE_ATTRIBUTE1-15`；
  **不填任何 REFERENCE_* 即为 on-account credit**。
- 硬约束：**贷项会计日期 ≥ 原发票会计日期**；同币种；Open Receivable 设置需一致；
  不能对 chargeback 应用贷项；税/运费行不允许超额核销。
- 已付款发票：先 unapply 收款，再按未应用金额开贷项。

### 2.3 Debit Memo
- 用途：价格更正、漏收运费、迟付费用。
- 与发票**无链接**，只能靠 Cross Reference / Special Instructions 留参考信息。
- 建议使用独立 transaction source 以便独立编号。
- 完成审批控制不适用于 debit memo / chargeback / bills receivable。

### 2.4 Adjustment
- 层级：Invoice（整单/分期）、Line、Charges（滞纳金/罚息）、Tax、Freight。
- 审批：document type = Adjustment，按币种 + 金额区间；超限进入 Pending Approval。
- 状态：Pending Approval / Approved / Rejected / More Research；只有 Approved/Rejected 可过账。
- 控制项：`Adjustment Reason Required = Yes` 时原因必填；不允许 overapplication 时不能翻转余额符号。
- 与贷项区别：adjustment 无独立单据、无收入行、不能 on-account、不能被单独 apply。

来源：
- [Options for Posted and Non-Posted Activities](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/options-for-posted-and-non-posted-activities-using-transaction.html)
- [How Can I Credit a Transaction That Was Already Paid](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/how-can-i-credit-a-transaction-that-was-already-paid.html)
- [AutoInvoice Import and Credit Memos](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/autoinvoice-import-and-credit-memos.html)
- [When Do I Create a Debit Memo](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/when-do-i-create-a-debit-memo.html)
- [How You Manage Adjustments](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/how-you-manage-adjustments-to-receivables-transactions.html)
- [How Adjustments Are Calculated](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/how-adjustments-to-transactions-are-calculated.html)

---

## 3. 编号、完成与可修改性

- `TransactionNumber` 创建时按 source 生成；`DocumentNumber` 在启用文档序列时于 **Complete 阶段**分配。
- Complete 生成付款计划；`Open Receivable=Yes` 才进入账龄与催收。
- Incomplete 可自由修改；启用完成控制时由指定审批人 Complete（ALL / 仅负金额行 / NONE）。
- 不能改回 Incomplete：已全额付款、已过账、已打印、有核销、有生效收入或有事项；
  顺序文档号已分配时也不能（防断号）。
- 完成后 REST 仅允许 PATCH：InvoiceStatus、PaymentTerms、TransactionDate、打印相关字段等；
  付款条件在已过账或有核销时也不可改。

来源：
- [Guidelines for Transaction Numbering](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/guidelines-for-transaction-numbering.html)
- [Control of Transaction Completion](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/control-of-transaction-completion-overview.html)
- [Why Can't I Incomplete the Transaction](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/why-can-t-i-incomplete-the-transaction.html)
- [Points to Consider When Updating Receivables Invoices](https://docs.oracle.com/en/cloud/saas/financials/26d/farfa/Points_to_Consider_When_Updating_Receivables_Invoices.html)

---

## 4. 价格与改价

### 4.1 价格真相在 Pricing / OM，不在 AR
- 价目表、折扣表、定价策略在 Pricing Administration 维护；下单时 OM 调 Pricing 计价。
- OM 行可手工调价：Discount Amount/Percent、Markup Amount/Percent、**Price Override**；
  执行需 `Update Order Pricing Details` 权限。
- 每次调价有 **Reason** 字段（只记录、不影响价格），默认值可用 `ORA_FOM_DEFAULT_ADJ_REASON` 配置，
  可配置为必填。
- 已提交订单改价需 **Create Revision**（变更单）；Awaiting Billing 行不能更新/取消；
  Shipped 行不能取消只能退货。
- 审批规则可按金额、数量、**price override** 触发。

### 4.2 AR 侧
- 发票行 Unit Price 允许手工录入正数或负数；memo line 默认取 list price，可改为实际售价。
- 官方**没有**「行价覆盖必须填 reason」的字段；审批发生在交易级（完成控制）或调整/贷项级。
- 开票后的价格更正：**Credit and Rebill** —— Credit Transaction 整单贷记 + Duplicate 重开票，
  用 Rebill Source Transaction 关联原单。

来源：
- [Edit Price on Order Lines](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fauom/edit-price-on-order-lines.html)
- [Manage Other Behavior on Sales Orders](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fauom/other-behavior-on-sales-orders.html)
- [Revise Sales Orders](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fauom/revise-sales-orders-you-already-submitted.html)
- [How Pricing Prices Sales Orders](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faupr/how-pricing-prices-sales-orders.html)
- [Guidelines for Entering Invoice Lines](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/guidelines-for-entering-invoice-lines.html)
- [How Do I Credit and Rebill a Transaction](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/how-do-i-credit-and-rebill-a-transaction.html)

---

## 5. UI 与权限

### 5.1 页面与动作
| 场景 | Fusion 页面 | 动作 |
|---|---|---|
| 建发票 | Create Transaction | Transaction Class = Invoice，保存为 Incomplete，再 Complete |
| 建贷项 | Create Transaction / Credit Transaction | Transaction Class = Credit Memo |
| 建借项 | Create Transaction | Transaction Class = Debit Memo |
| 查/管发票 | Manage Transactions | 搜索、打开 Review Transaction |
| 发票详情动作 | Review Transaction | Credit Transaction、Submit a Dispute、Duplicate |
| 调整 | Billing → Adjustments / Approve Adjustments | 按 Invoice/Line/Charges/Tax/Freight |
| 核销/反冲 | Manage Receipts → Edit Receipt | Apply / Unapply / Reverse（收款侧） |
| 价格更正 | 无专用动作 | Credit and Rebill（贷项 + Duplicate） |

### 5.2 权限与职责分离
- Billing Specialist Segregated Role 中的独立权限：`Create Receivables Invoice`、
  `Create Receivables Credit Memo`、`Create Receivables Transaction`、
  `Approve Receivables Adjustment`、`Delete Receivables Transaction`、`Dispute Receivables Transaction`。
- 调整限额按 document type（Adjustment / Receipt Write-off / Credit Memo Refund）+ 币种 + 金额。
- 贷项请求审批走 AMX/SOA 工作流，独立权限如 `IEX_REVIEW_CREDIT_REQUEST_PRIV`。

来源：
- [Billing Specialist Segregated Role](https://docs.oracle.com/en/cloud/saas/financials/26d/oafrm/Billing_Specialist_Segregated_Role_job_roles.html)
- [Approval Limits Document Types](https://docs.oracle.com/en/cloud/saas/financials/26d/fairp/approval-limits-document-types.html)
- [Credit Memo Request Approval Process](https://docs.oracle.com/en/cloud/saas/financials/26d/faofc/what-s-the-credit-memo-request-approval-process.html)

---

## 6. 与我方 Wave A 的逐项对照

| Fusion 能力 | 我方现状 | 判定 |
|---|---|---|
| Transaction class：Invoice / CM / DM / CB / ADJ | 只有 SINV / SCR / SDN 三个类型，且无头级类别 | **偏差**：需 `document_category` |
| Void（未过账未核销可作废） | draft/submitted → cancelled | **对齐**（无需改名） |
| Credit Memo（可部分、可 on-account、引用原单行） | reverse 整单红冲，强制引用原单 | **部分对齐**：缺 on-account、缺部分冲销 |
| Debit Memo（独立、无链接） | SDN 仅类型占位，无流程 | **未覆盖**（上游明确本期不做） |
| Adjustment + 审批限额 | 无 | **未覆盖**（AR 波次） |
| 发票级 Reverse | 我方有 `reversed` 状态 + 红字单 | **Fusion 无此动作**；我方是「贷记 + 原单置已贷记」的本地组合 |
| Incomplete → Pending Approval → Complete | draft → submitted → posted，无审批 | **部分对齐**：缺审批闸门 |
| Document Number 在 Complete 分配 | 建单即取号（草稿已有正式号） | **偏差**（可接受，但需在规格中声明） |
| Transaction Source / 分组规则 | 类型绑定 number_sequence | **大体对齐** |
| Price Override + Reason（OM 侧） | D13 仅列占位，无规则 | **未覆盖** |
| Credit and Rebill | 无 | **未覆盖** |
| Create Transaction / Credit Transaction / Duplicate 专用入口 | 通用表单 + 状态按钮 | **未覆盖** |
| 动作级权限拆分（create invoice / create CM / approve adjustment / delete / dispute） | 5 个：view/create/post/reverse/cancel | **部分对齐**：缺 print、独立贷项、审批 |

---

## 7. 对我方模型的建议（按优先级）

### P0（语义纠偏，不改表结构）
1. **正名**：Wave A 的「红字单」在 Fusion 语义下是 **Credit Memo（贷项凭证）**，不是「取消单据」。
   `reverse` 动作保留，但对外文案与 `document_category` 应标注 `credit_memo`；
   `cancelled` 才对应 Void。
2. **写明 `reversed` 是本地扩展**：Fusion 没有发票级 reverse/reversed；我方 `reversed` = 「已被贷记」，
   在规格中显式声明，避免后续对标时误判。
3. 红冲 UI 必须能填 `reversal_reason`（当前通用状态按钮只发 status，点红冲必然失败）。

### P1（模型补齐）
4. 头表增加 `document_category`：`invoice / credit_memo / debit_memo / cancellation`；
   `type_definitions.document_category` 继续作为类型级默认值。
5. `customer_invoice_line` 补 `price_diff_amount`（`net - order_unit_price × qty`），
   并落实 D13 校验：`unit_price != order_unit_price` 时 `price_change_reason` 必填。
6. 贷项引用原单改为**可选**（为 on-account credit 留口），引用时校验：
   同币种、贷项日期 ≥ 原过账日、原单无活跃核销。

### P2（流程与 UI）
7. `create_from_shipment` 暴露为 BO action（列表页按钮 + 权限），否则发货开票只能靠代码。
8. 增加独立「创建贷项」入口（选原单 → 带出负行），不要只靠状态按钮。
9. 权限补 `print` 与独立的 `credit_memo` 动作；审批闸门（限额表）留给 AR 波次。
10. 借项单维持「不做业务」；若未来放开，按 Fusion 口径**不强制引用原单**。

---

## 8. 未决与取证限制

- 26D 官方文档未提供「预置 transaction type 名称清单」与各类型 creation sign 对照表；
  需在 Manage Transaction Types 实例中核对。
- 「Freeze Price」不是 Oracle 官方术语，仅第三方连接器文档使用，不作为设计依据。
- Fusion 发票级 Reverse 在 26D 文档中未找到；若历史版本存在，仅影响命名，不影响「贷记 + 新单」的结论。
- 发票坏账核销（write-off）的官方专门说明未找到，仅确认 Receipt Write-off 有独立限额。
