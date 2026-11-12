# Wave C 决策项外部 ERP 对标研究

> 日期：2026-11-10
> 关联：`docs/specs/s8-customer-invoice-wave-c/spec.md` §3（D40–D47）
> 目的：用外部产品事实支撑 Wave C 的 8 个待拍板决策，给出可执行建议。

---

## 0. 结论摘要（推荐拍板组合）

| 编号 | 推荐 | 与现 spec 的差异 |
|---|---|---|
| D40 | 计划字段放**订单行**（5 列） | 一致 |
| D41 | 订单 confirmed 同事务生成 + 幂等 action 补跑；**submit 阶段前置校验** | 一致，补一条前置校验 |
| D42 | **单候选自动匹配；多候选必须显式指定原票行**，否则报错 | **调整**（原为无条件 FIFO） |
| D43 | 保持“贷项回退开票进度”，声明为**净额法**，与 Fusion/NetSuite 的总额法不同 | 一致，补口径声明 |
| D44 | 引用原票行**以 qty 为主**；`amount` 仅用于价格差异/无数量场景；on-account 只允许 amount | **收紧**（原为 qty/amount 平级二选一） |
| D45 | 本波做 on-account 贷项 | 一致 |
| D46 | 只阻断 `partial`；`none`/`full` 放行，`none` 记录审计日志 | 一致 |
| D47 | 阻断（fail-closed） | 一致 |

一句话：**D40/D41/D43/D45/D46/D47 按现 spec 拍板；D42 从“无条件 FIFO”改为“单候选自动、多候选显式”；D44 收紧为“数量优先”。**

> 关于「ICP」：常见 ERP 缩写中无明确对应。本报告按最接近的 IFS、Infor（LN/CloudSuite）覆盖；若您指的是其它产品，请告知具体名称，我再补一轮。

---

## 1. 研究范围与方法

- 覆盖产品：Oracle Fusion（AR + Order Management）、SAP S/4HANA SD、NetSuite（Advanced Billing）、Dynamics 365 Supply Chain、IFS、Infor LN、Sage Intacct。
- 关注维度：
  1. 开票计划挂在**订单头还是行**；
  2. 计划期次**何时生成**、是否随订单确认产生；
  3. 期次类型（等分/里程碑/按服务期分摊/提前滞后）；
  4. 退货 → 贷项的**原票追溯**与部分贷项；
  5. 贷项是否改变原票金额/开票进度（总额法 vs 净额法）；
  6. on-account（无原票）贷项；
  7. 订单关闭与开票完成度的关系。
- 证据来源：厂商官方帮助/文档优先，辅以实施方文档；来源见 §7。

---

## 2. 产品能力对照

| 维度 | Oracle Fusion | SAP S/4HANA | NetSuite | Dynamics 365 | IFS | Infor LN |
|---|---|---|---|---|---|---|
| 计划粒度 | AR 按发票/发票行；OM 按订单行 | **按订单行**（可在抬头定义计划并应用到所有行） | 计划挂项目， sourcing 到销售订单行；SO 有 Schedule 子页 | 按销售订单行 | 按订单行（阶段付款）/合同计划 | **按销售订单行分期** |
| 计划生成时机 | 订单/开票时确定 | 订单录入时系统**自动建议**周期性或里程碑计划 | 由项目计划派生，项目变更会**重算**发票计划 | 订单确认/开票时 | 订单行维护阶段付款 | 订单行维护分期计划 |
| 期次类型 | 行级数量/金额、分期 | 周期性、里程碑（日期行） | Standard / Fixed Bid Interval / Fixed Bid Milestone / T&M / Charge-based | 交货/开票计划 | 周期计划、阶段付款（progress %、lead time、前置里程碑） | 分期（频率、起始日） |
| 退货贷项原票追溯 | 贷项可引用原票行，按行部分贷记 | 退货订单/贷项请求**引用发票** | 贷项单可 Apply 到指定发票或 Auto Apply | 退货行用 Find sales order **引用已开票订单行**，校验数量不超已开票 | 退货/贷项参照原单 | 贷项参照原发票 |
| 部分/多次贷项 | 支持（行级 qty+unit price 或 amount） | 支持（部分数量/金额） | 支持（行级数量/金额） | 支持（按退货行数量） | 支持 | 支持 |
| 无原票贷项（on-account） | 支持；未应用余额保留在贷项单 | 支持（无发票参照的贷项） | 支持；未应用余额保留（Unapplied） | 支持（credit only 流程） | 支持（预付款/贷项） | 支持 |
| 贷项对原票 | **原票金额不变**，发票余额减少（例：5000 → 4000） | 贷项是独立 billing document，引用原票 | 贷项是独立交易，Apply 后抵减应收 | 贷项单独立，关联退货单 | 贷项独立 | 贷项独立 |
| 订单关闭 | OM 行开票/贷项完成后关闭 | 整体处理状态 C 需交货+开票完成 | 订单/项目计费完成后关闭 | 订单开票完成后关闭 | 订单完成需开票 | 交货并开票后关闭分期 |

---

## 3. 逐项证据与建议

### D40 计划生成字段放哪

**外部事实**
- SAP：billing plan 是“**single item** in a sales document 的日期计划”；也可在抬头定义并对所有 item 生效。([billing 说明](http://amlan.freetzi.com/billing.html))
- Infor LN：分期计划在**销售订单行**上维护（Sales Order - Installments）。([Infor LN Installments](https://docs.infor.com/ln/10.4/en-us/lnolh/help/td/onlinemanual/000069.html))
- IFS：阶段付款/预付款按订单行（progress percentage、lead time、前置里程碑）。([IFS Stage Payments](https://wssifshelp.wilhelmsen.com/ifsdoc/documentation/en/Procurement/ActivityEnterMilestonesStagePaymentsManually.htm))
- NetSuite：计划随项目 sourcing 到销售订单行，SO 上可查看/覆盖 Schedule。([NetSuite Project Billing](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1204906.html))

**建议：维持“5 列放 `sales_order_lines`”。**
理由：行级是主流；抬头级只能表达“全单同一计划”，无法覆盖多行不同周期/里程碑。若未来需要“抬头默认值”，用“确认时把抬头默认复制到空值行”即可，不改变存储位置，也不需要新表。

---

### D41 自动生成触发点

**外部事实**
- SAP：订单录入时系统可**自动建议**周期性或里程碑计划（订单保存即带计划）。([billing 说明](http://amlan.freetzi.com/billing.html)、[里程碑 billing plan item API](https://saptix.com/2026/05/20/milestone-billing-for-service-sales-in-sap-s-4hana/))
- NetSuite：计划从项目派生到 SO；项目/任务变更会触发发票计划**重算**。([NetSuite Project Billing](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1204906.html))
- IFS：计划在订单行维护，开票从计划驱动。

**建议：维持“订单 confirmed after-write hook，同事务生成 + 幂等 action 手工补跑”。**
补充一条：**订单 submit 阶段做计划字段前置校验**（期数/间隔/锚点/服务期是否存在、`plan` 行是否缺少期数），把 fail-closed 的错误提前到提交，而不是确认时才失败。这不改变 D47 的阻断语义，只降低确认失败率。

---

### D42 退货贷项分配策略（本报告唯一建议调整项）

**外部事实**
- Oracle AR：贷项可 Apply 到**任意未结发票**，支持全部或部分应用；未应用余额保留在贷项单。([Oracle 退货到贷记 QRG](https://sites.oracle.com/documents/link/web?IdcService=GET_FILE&dLinkID=LDAB349DF59589D39E3AAE2EC775B0B97F897BE36208&item=fFileGUID:DBF3B1CA080D3B49301D15CE3D96EEB5090238B3396A&scsOriginalFileName=QRG_FF_STD_Return%20to%20Credit_zh-CN.pdf))
- NetSuite：贷项单可勾选 **Auto Apply** 自动应用到“最早期未结发票”，也可手工指定发票 Apply。([Applying a Customer Credit Memo](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_N1312521.html))
- Dynamics 365：退货行必须用 **Find sales order** 引用已开票销售订单行，并校验退货数量不超过已开票数量。([Sales returns](https://learn.microsoft.com/en-gb/dynamics365/supply-chain/sales-marketing/sales-returns))
- SAP：退货订单/贷项请求**引用发票**，再生成贷项。([Credit Memo Request](https://manildra.training/Training/Sales/WI/02cusser/CreditMemoReq.pdf))

**结论**：FIFO 是“便利默认”，不是业务正确性。主流产品都允许显式指定原票；Dynamics 强制引用已开票行并校验数量，Oracle/NetSuite 允许“自动应用到最早发票”但也可手工指定。

**建议：从“无条件 FIFO”改为“单候选自动、多候选显式”。**
- 原订单行只有 **1 张**已过账正数发票行有可贷余额 → 自动匹配（等效 FIFO，无歧义）。
- 有 **多张**候选（跨票/多次开票）且未传 `source_invoice_id` / `invoice_line_ids` → 返回 `INVOICE_RETURN_ORIGIN_AMBIGUOUS`，要求显式指定。
- 提供 `auto_allocate='fifo'` 显式开关，供“确实要按最早票冲减”的调用方使用（默认关闭）。
- 分配后仍按行级累计额度校验（R-INV-20 / R-RET-10）。

影响：§6.3 入参增加可选 `source_invoice_id` / `invoice_line_ids`、枚举 `auto_allocate`；新增错误码；测试 C3 增加“多候选未指定→报错”用例。工作量约 +0.5 天。

---

### D43 贷项是否回退开票进度

**外部事实**
- Oracle AR：贷项应用到发票后，**原票金额不变**，发票余额减少（例：5000 → 4000）。([Invoices and Credit Memos in Oracle AR](https://erpschools.com/erps/articles/invoices-and-credit-memos-in-oracle-ar))
- Oracle AR 表：贷项行用 `QUANTITY_CREDITED` 记录被贷记数量，原票行数量不被改写。([AR Tables](https://www.oracleerpappsguide.com/2012/01/accounts-receivables-ar-tables-information.html))
- NetSuite / SAP / Dynamics：贷项均为独立单据，通过 Apply/引用关联原票，原票保持原额。

**结论**：主流是“总额法”——原票毛额保留，贷项独立抵减应收与未开票数量。
本系统 `billed_amount` / `billing_status` 表达的是**净开票进度**，贷项回退进度 = 净额法，是内部简化。

**建议：保持现状（回退），并在 spec/UI/对账说明中明确“净额法”口径。**
- 不改 `post` sign 策略，避免重写 Wave A 用例（已有 `test_credit_post_rolls_back_billed_progress` 固化该语义）。
- 在 AR/GL 波次若要求 Fusion 口径（原票毛额 + 贷项独立），单独立项改造，不在本波。
- 必须保留可追溯字段（`original_invoice_line_id`、`reversal_of_invoice_id`），保证能还原毛额。

---

### D44 部分贷项的金额口径

**外部事实**
- Oracle AR：行级贷项可输入 **Quantity + Unit Price 或 Amount**；输入数量单价时系统计算金额。([Crediting Transaction Lines](https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtTopicFile.iHelp%7CHelpServlet%7CUS%7Car%7C@t_cmline/))
- Oracle AR 表：贷项行记录 `QUANTITY_CREDITED`（数量口径可审计）。
- Dynamics：以退货行**数量**为准，并校验不超过已开票数量。
- NetSuite：贷项行有数量、单价、金额，允许按金额调整。

**建议：引用原票行时以 `qty` 为主，`amount` 仅用于价格差异/无数量场景。**
- `qty` 场景：金额 = `ROUND(qty × 原行单价, 4)`，税额按原行税率比例分摊，plan 行按比例换算（R-INV-24）。
- `amount` 场景：仅允许在 `reason_code` 为价格差异/折扣调整等“非数量原因”时使用；必须 ≤ 原行剩余可贷金额；数量记 0 或空。
- on-account 贷项：只允许 `amount`（无原行数量可引用）。
- 前端默认只暴露数量输入；金额输入放到“差异调整”模式，减少误用。

影响：§6.4.1 入参语义收紧（API 仍可二选一，但增加 reason 约束）；测试 C4 增加“amount 用于数量原因被拒”用例。工作量约 +0.5 天。

---

### D45 on-account 贷项是否本波做

**外部事实**
- Oracle：支持 on-account 贷项，未应用余额保留在贷项单，可后续应用到任意发票。([Apply On-Account Credit Memos](https://doc.erpcloud.more4apps.com/cloud-finance/receivables/cm/applyCm.html))
- NetSuite：贷项单未应用部分保留为 Unapplied，可后续 Apply。([Applying a Customer Credit Memo](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_N1312521.html))
- SAP：支持无发票参照的贷项。
- Dynamics 365：credit only 流程（不要求实物退回）直接生成贷项。

**建议：做。** 独立入口 `create_credit_on_account`，无原票追溯，金额必须为负；不参与计划/发货进度回退。风险低、与主流一致，且能覆盖“折扣/补偿/争议”场景。

---

### D46 订单关闭校验强度

**外部事实**
- SAP：销售订单**整体处理状态 C** 需交货与开票均完成；开票状态独立跟踪。([SAP 状态说明](https://www.erpgreat.com/sap-sd/explain-the-meaning-of-an-open-sales-order.htm)、[MCVBUK 状态字段](https://leanx.eu/sap/table/mcvbuk/))
- Oracle OM：订单行在**开票/贷项完成后**才关闭。([Fusion OM Worksheet](https://oraclenana.com/Fusion%20OM%20Worksheet.pdf))
- Infor LN：交货并开票后才关闭分期/订单。([Infor LN Installments](https://docs.infor.com/ln/10.4/en-us/lnolh/help/td/onlinemanual/000069.html))

**建议：维持“只阻断 `partial`；`none`/`full` 放行”。**
- `partial` 表示“开了但没开完”，关闭会造成应收遗漏，必须阻断。
- `none` 放行是现实需要（服务类/历史单/免费单/线下已结），但写入审计日志（关闭动作 remark 或 audit），便于事后抽查。
- `full` 放行。
- 附加建议（低成本）：关闭前若存在**草稿状态发票**，阻断并提示先过账或删除，避免“关闭后遗留草稿票”。

---

### D47 期次生成失败是否阻断订单确认

**外部事实**
- SAP：billing plan 是订单的一部分，计划日期非法时订单保存直接报错，不存在“无计划的已确认订单”。
- NetSuite：计划随订单派生，非法/缺失会在开票阶段暴露为不可计费。
- Oracle OM：订单行进入“Awaiting Billing”前必须完成计费计划校验（含部分 RMA 的 Review Complete）。([Oracle 文档片段](https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtTopicFile.iHelp%7CHelpServlet%7CUS%7Cont%7C@deletems/))

**建议：维持 fail-closed（同事务回滚，`ORDER_BILLING_PLAN_INVALID`）。**
配套：
1. submit 阶段前置校验（见 D41），错误定位到 `line_no` + 字段；
2. 幂等 action `sales_order.generate_billing_plan` 供历史订单/失败重试补跑；
3. 错误信息区分“字段缺失/非法”与“服务期交集为 0”，便于前端提示。

---

## 4. 若采纳本报告，spec/tasks 需要的改动

| 位置 | 改动 | 规模 |
|---|---|---|
| spec §3 D42 | 改为“单候选自动、多候选显式、可选 `auto_allocate='fifo'`”；新增错误码 `INVOICE_RETURN_ORIGIN_AMBIGUOUS` | 小 |
| spec §6.3 | 入参增加可选 `source_invoice_id` / `invoice_line_ids` / `auto_allocate`；分配算法改写 | 中 |
| spec §6.4.1 | `amount` 增加 `reason_code` 约束（仅差异调整）；前端默认 qty | 小 |
| spec §6.5 / R-ORD-05 | `none` 放行并记审计；关闭前检查草稿发票 | 小 |
| spec §6.2 / T38 | submit 前置校验计划字段 | 小 |
| tasks T37/T39/T40/T42 | 对应测试用例 +3~5 条 | 小 |

合计增量约 1.5 人天，不改变“无新表、只加 5 列/1 权限/1 doc_flow/2 索引”的边界。

---

## 5. 风险与未决

1. **D42 收紧会让调用方多传参数**：可通过 `auto_allocate='fifo'` 兼容旧行为；默认策略更安全。
2. **D43 净额法与 Fusion 报表口径不同**：需在 AR/GL 波次做口径映射（毛额 = 净额 + 累计贷项）。
3. **D44 收紧可能挡住“按金额退货”的合理场景**：用 `reason_code` 白名单放行（价格差异、折扣、运费调整）。
4. **D46 `none` 放行**存在应收遗漏风险：用审计日志 + 关闭后报表抽查兜底；若合规要求更严，可配置为阻断。
5. **「ICP」指代待确认**：若指某特定产品（如 IFS / Infor / 其它），请告知，我补充该产品证据并复核结论。

---

## 6. 建议的拍板方式

按 §0 的组合一次性拍板即可，其中只有两项需要您明确表态：

- **D42**：接受“单候选自动、多候选显式”（推荐），还是坚持“无条件 FIFO”？
- **D44**：接受“数量优先、金额仅差异调整”（推荐），还是保持“qty/amount 平级二选一”？

其余 6 项按现 spec 执行。拍板后我按 `tasks.md` 从 T35 开始实施。

---

## 7. 来源

- [Oracle Receivables – Crediting Transaction Lines](https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtTopicFile.iHelp%7CHelpServlet%7CUS%7Car%7C@t_cmline/)
- [Oracle 退货到贷记 快速参考指南（QRG）](https://sites.oracle.com/documents/link/web?IdcService=GET_FILE&dLinkID=LDAB349DF59589D39E3AAE2EC775B0B97F897BE36208&item=fFileGUID:DBF3B1CA080D3B49301D15CE3D96EEB5090238B3396A&scsOriginalFileName=QRG_FF_STD_Return%20to%20Credit_zh-CN.pdf)
- [Oracle AR – Invoices and Credit Memos](https://erpschools.com/erps/articles/invoices-and-credit-memos-in-oracle-ar)
- [Oracle AR Tables – QUANTITY_CREDITED](https://www.oracleerpappsguide.com/2012/01/accounts-receivables-ar-tables-information.html)
- [Oracle Fusion Order Management Worksheet](https://oraclenana.com/Fusion%20OM%20Worksheet.pdf)
- [Oracle Receivables – Invoicing and Payments（billing plan review / 部分 RMA）](https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtAnchor.deletems/vtTopicFile.iHelp%7CHelpServlet%7CUS%7Cont%7C@deletems/)
- [SAP Billing Plan 说明（按订单行、自动建议周期性/里程碑）](http://amlan.freetzi.com/billing.html)
- [SAP S/4HANA Milestone Billing（billing plan item API）](https://saptix.com/2026/05/20/milestone-billing-for-service-sales-in-sap-s-4hana/)
- [SAP Credit Memo Request（引用发票）](https://manildra.training/Training/Sales/WI/02cusser/CreditMemoReq.pdf)
- [SAP 销售订单状态（整体处理状态）](https://www.erpgreat.com/sap-sd/explain-the-meaning-of-an-open-sales-order.htm)
- [SAP MCVBUK 状态字段](https://leanx.eu/sap/table/mcvbuk/)
- [NetSuite Project Billing（计划类型、派生到销售订单、重算）](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N1204906.html)
- [NetSuite Billing Schedule（Suitescript，5 类计划）](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_3899748827.html)
- [NetSuite Applying a Customer Credit Memo（Auto Apply 最早发票）](https://docs.public.oneportal.content.oci.oraclecloud.com/en/cloud/saas/netsuite/ns-online-help/section_N1312521.html)
- [Dynamics 365 Sales returns（Find sales order、数量校验、credit only）](https://learn.microsoft.com/en-gb/dynamics365/supply-chain/sales-marketing/sales-returns)
- [IFS Stage Payments（progress %、lead time、前置里程碑）](https://wssifshelp.wilhelmsen.com/ifsdoc/documentation/en/Procurement/ActivityEnterMilestonesStagePaymentsManually.htm)
- [IFS Activity Prepayment Based Invoice](https://wssifshelp.wilhelmsen.com/ifsdoc/documentation/en/Sales/ActivityPrepaymentBasedInvoice.htm)
- [Infor LN Installments（按订单行分期）](https://docs.infor.com/ln/10.4/en-us/lnolh/help/td/onlinemanual/000069.html)
- [Sage Intacct Fixed fee projects with percent complete billings](https://www-p50491.intacct.com/ia/docs/en_US/help_action/Projects/Type_of_projects/fixed-fee-projects-with-percent-complete-billings.htm)