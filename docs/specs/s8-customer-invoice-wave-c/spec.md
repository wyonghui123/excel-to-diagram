# S8 Wave C 开票完备性补齐实施规格

> 状态：**待批准（批准前不写代码）**
> 日期：2026-11-10
> 工作树：`D:\filework\s8-billing-worktree`（分支 `agent/s8-billing`，端口 3012）
> 上游：`docs/specs/s8-customer-invoice-wave-a/spec.md`、`docs/specs/s8-customer-invoice-wave-b/spec.md`
> 对标依据：`docs/specs/research-fusion-billing-deep-dive-2026-11-09.md`
> 口径：只做 P1 四项 + P3 三项一致性；AR / 收入确认 + GL / 税引擎 / 借项通知单为**非目标**，只留接口位。

---

## 0. 结论先行

| # | 问题 | 本波结论 |
|---|---|---|
| 0.1 | 过账/冲销为什么「不可调用」 | 状态流转走 `customer_invoice.yaml` 的 state_transition + 守卫拦截器，前端按钮本已存在；缺的是 **BO business action**，业务动作 API 无法触达。本波补 `submit/post/reverse` 三个 action |
| 0.2 | 期次怎么自动生成 | 订单确认时按行生成：`billing_method` + 5 个新列（期数/间隔/锚点/提前滞后天/尾差口径）→ `sales_order_schedules(schedule_kind='billing')`。里程碑仍手工 |
| 0.3 | 退货怎么产生贷项 | 新增 `create_credit_from_return_shipment`：退货行 → `reference_line_id` 原订单行 → 已过账发票行 FIFO 分配数量 → 负数贷项行；同事务写 `return_shipment_line_to_credit_memo` doc_flow 边 |
| 0.4 | 一票一贷项怎么解除 | 删除 `_find_red_invoice` 的整单拦截，改为**行级累计额度**校验 `INVOICE_CREDIT_EXCEEDED`；支持部分数量/部分金额 |
| 0.5 | on-account 贷项 | 新增 `create_credit_on_account`：无原票、无行引用、金额必须为负、必须指定客户与币种 |
| 0.6 | 贷项是否回退开票进度 | **保持现状**（`post` 对贷项 `sign=-1` 回退 `billed_qty/billed_amount`，允许重开票）；与 Fusion「贷项不改原票进度」的差异在 §2.3 显式声明，不在本波改 |
| 0.7 | 退货发货单能否正向开票 | **不能**。`create_from_shipment` 增加 `document_category='return'` 拦截（当前无校验，是真实缺陷） |
| 0.8 | 订单关闭校验 | 增加 `billing_status != 'partial'` 前置；`none`/`full` 放行（不阻断尚未开票即关闭的历史流程） |
| 0.9 | 0.01 与 0.0001 | 两层尾差，**不是笔误**：`PERCENT_TAIL_TOLERANCE=0.01` 管比例合计（%），`EPSILON=0.0001` 管金额（元）。本波写进规则说明，不合并常量 |
| 0.10 | 发票号何时分配 | 现状 draft 即取号；Fusion 在 Complete 分配。本波**不改**，作为已知偏差记录（P3） |
| 0.11 | 需要新表吗 | **不需要**。仅 `sales_order_lines` 加 5 列 + 1 条权限 + 1 条 doc_flow 规则（v242） |
| 0.12 | 迁移号 | `v242__customer_invoice_wave_c.py`（当前最大 v241） |

---

## 1. 目标与范围

### 1.1 目标

把「数据层闭环成立、业务操作不闭环」的四个 P1 缺口补成可调用、可审计、可回归的能力：

```
① 单据操作        draft ─submit→ submitted ─post→ posted ─reverse→ 红字 posted
                  全部通过 BO action 暴露（当前只能靠详情页状态按钮）

② 计划自动生成    订单 confirmed ──> 按行生成 billing 期次（期数/间隔/锚点/提前滞后/按日尾差）
                  当前只能逐条手工建 sales_order_schedules

③ 退货贷项        退货发货单（document_category='return'）
                  ──> 追溯原订单行 ──> 冲减已过账发票行 ──> 负数贷项（部分数量）
                  当前：正向开票会把退货开成正数发票；且无 doc_flow 边

④ 贷项粒度        部分数量/部分金额/多次贷项/on-account
                  当前：一票仅一张贷项 + 整行取负
```

### 1.2 验收（全部满足才算完成）

- [ ] `customer_invoice.submit / post / reverse` 三个 business action 注册、鉴权、可重复调用（幂等语义见 §6.1）。
- [ ] action 调用与状态按钮语义一致：同样的校验、同样的错误码、同样的派生回写；绕过守卫的路径不存在。
- [ ] 订单确认后自动生成 billing 期次；比例合计 = 100（容差 0.01%）；期金额按 4 位四舍五入，尾差归最后一期；重复确认不重复生成。
- [ ] `fixed_price` → 1 期 100%；`time_and_material` → 按期数均分；`milestone` → 不自动生成（必须手工带 `milestone_code`）。
- [ ] `billing_proration='daily'` 且行有 `service_start_date/service_end_date` 时按天分摊；无服务期时退化为均分。
- [ ] 退货发货单无法通过任何正向开票入口生成发票（`create_from_shipment` 拦截）。
- [ ] `create_credit_from_return_shipment` 能按退货行数量追溯到已过账发票行，生成负数贷项；找不到原票行时拒绝；跨多张原票按 FIFO 拆分。
- [ ] 同一发票行可多次贷项，但累计数量与金额不得超过原行（4 位精度）。
- [ ] `create_credit_on_account` 生成 on-account 贷项，行无 `original_invoice_line_id`、金额为负、无开票进度回退副作用（无 shipment/schedule/order 行键）。
- [ ] 订单关闭在 `billing_status='partial'` 时被拒绝。
- [ ] 全量回归通过；主工作树与 s7-worktree 未改动。

### 1.3 非目标（P2/P3，本波明确不做）

| 类别 | 不做内容 | 预留方式 |
|---|---|---|
| AR | 收款、核销、账龄、催收、对账单、信用额度/冻结 | 贷项已按「负应收单据」建模；后续 AR 波次直接消费 `customer_invoices` |
| 收入确认 + GL | SLA、收入计划、科目推导、过账凭证 | `_emit_accounting_event_hook` 保持 no-op，本波只补事件字段注释（§6.6） |
| 税 | 税引擎、税码判定、税差异 | 行税额仍按行税率简单计算 |
| 借项通知单 | Debit Memo 独立单据 | 留 `document_category` 枚举位注释，不建表 |
| 里程碑自动触发 | 事件驱动开票 | 里程碑期次继续手工建，`billing_method='milestone'` 只做校验 |
| 全额/部分坏账、退单 | 坏账核销、退款 | — |
| 发票号时机 | Complete 阶段取号 | §9 声明为已知偏差 |
| 贷项 PDF / 邮件 | 贷项打印模板与发送 | `print` 沿用发票模板（§8.3 记录限制） |

---

## 2. Fusion 对标依据（只列本波要落的部分）

| 缺口 | Fusion 26D 行为 | 本波落点 |
|---|---|---|
| 单据操作不可调用 | 交易有 Incomplete→Complete、Void、Credit Memo、Adjustment 明确动作 | `submit/post/reverse` 三 action；Void 不做（已有 cancel 仅限 draft） |
| 期次不自动生成 | Invoice Plan / Bill Plan 由订单计费计划按频率、相对天数、比例生成 | `billing_plan_service` + 行级计划字段 |
| 退货无贷项 | RMA → 退货入库 → AutoInvoice 生成 Credit Memo（引用原发票行） | `create_credit_from_return_shipment` |
| 一票一贷项 / 整行取负 | Credit Memo 可部分、可引用行、可 on-account | 行级额度 + 部分数量/金额 + on-account |
| 过账/冲销无 action | Complete / Credit 均为显式动作，受权限与限额控制 | action + 权限（post/reverse 已有权限码，submit 新增） |

### 2.1 与 Fusion 的语义差（必须显式声明）

1. **贷项回退开票进度**：Fusion 贷项不改原票的开票进度；本仓库 `post` 对贷项 `sign=-1` 回退 `billed_qty/billed_amount`（`test_credit_post_rolls_back_billed_progress` 已固化该行为）。本波**保留**，因为它支撑「贷项后重开票（credit & rebill）」。
2. **无 Void**：Fusion 未过账且无活动可 Void；本仓库只能 cancel（draft）或 reverse（posted）。不新增 Void。
3. **无 Adjustment**：尾差减免仍靠贷项或后续 AR 调整，不做原单余额直接调整。
4. **发票号时机**：见 §9。

### 2.2 退货链路的对象事实（本波据此实现）

- 退货不是独立对象：`sales_orders.order_type.document_category='return'`，行 `line_type_id` 表现 `return`。
- 退货行用 `sales_order_lines.reference_line_id` 回指原销售订单行（R-RET-1~9 已存在）。
- 退货发货单是 `shipments.document_category='return'`，行数量为正、方向由抬头决定。
- 因此「退货单 → 贷项」= 退货发货单 → 退货行 → 原订单行 → 原发票行；**不新建 sales_return 对象**。

---

## 3. 待拍板决策

| 编号 | 决策 | 建议 | 否决影响 |
|---|---|---|---|
| **D40** | 计划生成字段放哪 | 新增 5 列到 `sales_order_lines`（期数/间隔/锚点/提前滞后/尾差口径） | 若要求放订单头：多行不同计划无法表达，需另建计划表 |
| **D41** | 自动生成触发点 | 订单 confirmed 的 after-write hook，同事务；另提供幂等 action 手工补跑 | 若只保留手工 action：Fusion 的「确认即产生账单计划」不成立 |
| **D42** | 退货贷项分配策略 | 单候选自动匹配（等效 FIFO）；多候选必须显式指定 `source_invoice_id`/`invoice_line_ids`，否则 `INVOICE_RETURN_ORIGIN_AMBIGUOUS`；可选 `auto_allocate='fifo'` 显式开启无条件 FIFO（§3.1） | 若坚持无条件 FIFO：多票场景可能冲错原票，审计不可追溯 |
| **D43** | 贷项是否回退开票进度 | 保持现状（回退），声明本系统为**净额法**（billed = 已开票 − 已贷项），与 Fusion/NetSuite 的总额法不同（§3.1） | 若改为不回退：需改 `post` 的 sign 策略并重写 Wave A 用例 |
| **D44** | 部分贷项的金额口径 | 引用原票行时**以 `qty` 为主**（金额 = `ROUND(qty × unit_price, 4)`）；`amount` 仅用于价格差异/无数量场景且需 `reason_code`；on-account 只允许 `amount`（§3.1） | 若保持 qty/amount 平级：数量不可追溯，易被误用 |
| **D45** | on-account 贷项是否本波做 | 做（独立入口 `create_credit_on_account`） | 若不做：删除 §6.5，退货贷项不受影响 |
| **D46** | 订单关闭校验强度 | 只阻断 `partial`；`none`/`full` 放行，`none` 记审计；另建议关闭前阻断草稿发票（§3.1） | 若要求「必须 full」：历史未开票即关闭的单据将无法关闭 |
| **D47** | 期次生成失败是否阻断订单确认 | 阻断（同事务回滚，返回 `ORDER_BILLING_PLAN_INVALID`） | 若改为告警放行：可能产生无计划的可开票订单 |

### 3.1 外部 ERP 对标结论（2026-11-10）

完整证据与来源见 [research-wave-c-decisions-2026-11-10.md](../research-wave-c-decisions-2026-11-10.md)。要点：

| 编号 | 外部事实 | 结论 |
|---|---|---|
| D40 | SAP 的 billing plan 是“单个订单行”的日期计划；Infor LN 按订单行分期；IFS 按订单行阶段付款；NetSuite 计划随项目 sourcing 到订单行 | 行级 5 列正确，无需新建计划表 |
| D41 | SAP 订单录入即自动建议周期性/里程碑计划；NetSuite 计划随订单派生并随项目变更重算 | 确认时同事务生成 + 幂等补跑；**增加 submit 前置校验** |
| D42 | Oracle AR 可对任意未结发票部分应用；NetSuite 支持 Auto Apply 最早发票但可手工指定；Dynamics 退货行强制引用已开票订单行 | **单候选自动、多候选显式**，避免冲错票 |
| D43 | Fusion/NetSuite/SAP 均为“原票金额不变 + 贷项独立单据”，属总额法；本系统 billed 是净额 | 保持回退，明确声明**净额法**口径差异 |
| D44 | Oracle AR 行级可“数量+单价或金额”；Dynamics 以数量为准并校验 ≤ 已开票量 | 引用原票行**数量优先**，金额仅差异调整 |
| D45 | Oracle on-account 贷项、NetSuite Unapplied、SAP 无参照贷项均支持 | 本波做 |
| D46 | SAP 整体处理状态 C 需交货+开票完成；Oracle OM 行开票/贷项后才关闭 | 只阻断 `partial`，`none` 放行但记审计 |
| D47 | SAP/NetSuite 的计划是订单的一部分，非法计划在订单保存时即失败 | fail-closed 正确 |

**待用户最后确认的两项**：D42（单候选自动 vs 无条件 FIFO）、D44（数量优先 vs qty/amount 平级）。其余 6 项按本表执行。

---

## 4. 数据模型变更（v242）

### 4.1 `sales_order_lines` 新增 5 列

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `billing_period_count` | INTEGER NULL | NULL | 开票期数 1..60；`plan` 行必填（`fixed_price` 可空=1） |
| `billing_interval_months` | INTEGER NULL | 1 | 期间隔月数 1..12 |
| `billing_anchor_date` | DATE NULL | NULL | 首期起算日；空 = 订单确认日 |
| `billing_lead_days` | INTEGER NULL | 0 | 提前(+)/滞后(-)天数，作用于 `promised_date` |
| `billing_proration` | VARCHAR(8) NULL | `none` | `none` 均分 / `daily` 按服务期天数分摊 |

约束（`verify()` 直接查 DB）：

- `billing_proration IN ('none','daily') OR IS NULL`
- `billing_period_count BETWEEN 1 AND 60 OR IS NULL`
- `billing_interval_months BETWEEN 1 AND 12 OR IS NULL`
- `billing_relevance='plan'` 且 `billing_method='time_and_material'` 时 `billing_period_count IS NOT NULL`

### 4.2 权限（v242）

新增 `customer_invoice:customer_invoice_submit`（提交），授予 admin / default 权限集，并挂到 `customer_invoice-list` 菜单（复用 v239 的挂载逻辑）。

### 4.3 doc_flow 规则（v242）

| 字段 | 值 |
|---|---|
| `rule_id` | `return_shipment_line_to_credit_memo` |
| `source_bo` | `shipment_line` |
| `target_bo` | `customer_invoice_line` |
| `source_qty_field` | `qty` |
| `pool` | `billing` |
| `status` | `active` |

### 4.4 索引（v242）

```sql
CREATE INDEX IF NOT EXISTS idx_sol_billing_plan
  ON sales_order_lines (billing_relevance, billing_method);

CREATE INDEX IF NOT EXISTS idx_cil_original_line
  ON customer_invoice_lines (original_invoice_line_id);
```

> `idx_cil_original_line` 支撑行级贷项额度聚合；若该列已有索引则 `verify()` 接受已有索引，不重复建。

---

## 5. 规则编号（新增）

| 编号 | 规则 | 落点 |
|---|---|---|
| **R-INV-19** | 退货发货单禁止正向开票；`create_from_shipment` 下单 `document_category='return'` → `INVOICE_RETURN_SHIPMENT_NOT_BILLABLE` | service |
| **R-INV-20** | 贷项行累计（数量/金额，4 位）不得超过原发票行；多次贷项按累计判断 | service |
| **R-INV-21** | on-account 贷项：无 `original_invoice_line_id`、无 shipment/schedule/order 行键、金额必须为负 | service |
| **R-INV-22** | 退货贷项必须追溯到已过账、非红字发票行；无法追溯拒绝 | service |
| **R-INV-23** | 计划生成幂等：订单/行已有非取消 billing 期次时不重复生成 | service |
| **R-INV-24** | 部分贷项比例换算：plan 行按 `原billing_percent × 贷项金额 / 原行净额` 重算，保留 4 位 | service |
| **R-RET-10** | 退货行累计退货数量 ≤ 原行已开票数量（含跨票） | guard + service |
| **R-ORD-05** | 订单关闭：`billing_status='partial'` 拒绝（`ORDER_BILLING_INCOMPLETE`） | guard |

---

## 6. 服务实现

### 6.1 C1：单据动作（`customer_invoice_actions.py` + `bo_action_registrations.py`）

| action | handler | service | 权限 | 幂等 |
|---|---|---|---|---|
| `customer_invoice.submit` | `submit_handler` | `submit(invoice_id)` | `customer_invoice:customer_invoice_submit` | 是：已 `submitted/posted` 直接返回当前状态 |
| `customer_invoice.post` | `post_handler` | `post(invoice_id)` | `customer_invoice:customer_invoice_post` | 是：已 `posted` 返回当前状态；`reversed/cancelled` 拒绝 |
| `customer_invoice.reverse` | `reverse_handler` | `reverse({invoice_id, reversal_date, reason})` | `customer_invoice:customer_invoice_reverse` | 是：已存在该原票的红字发票 → 返回其 id |

入参统一：`{invoice_id}`（兼容 `source_doc_id`），`reverse` 额外 `reversal_date`、`reason`（必填，Fusion 的 reversal reason 语义）。
返回统一：`{id, invoice_no, status}`；`reverse` 返回红字单 `{id, invoice_no, status:'posted', original_invoice_id}`。

约束：

- action 只允许走 service 公开方法，不直接写库；错误用 `CustomerInvoiceError` → `_fail(str(exc), exc.rule)`。
- 不得绕过守卫：action 内部调用的 service 方法必须已有状态前置校验（§5 已有），不新增旁路。
- `category='business'`、`requires_auth=True`，`object_type='customer_invoice'`。
- `reverse` 的 `reason` 落 `customer_invoices.reversal_reason`（列为现有列；若为空则拒绝）。

### 6.2 C2：期次自动生成（新增 `meta/services/billing_plan_service.py`）

```python
class BillingPlanService:
    def generate_for_order(self, order_id, *, triggered_by='confirm') -> list[int]
    def generate_for_line(self, order, line) -> list[dict]
```

规则：

1. 只处理 `billing_relevance='plan'` 的行；`delivery` 行跳过。
2. `billing_method` 分派：
   - `fixed_price` / NULL → 1 期 100%
   - `time_and_material` → `billing_period_count` 期均分
   - `milestone` → 返回 `[]`（必须手工建期次并带 `milestone_code`）
3. 比例分配：`percent_i = 100 / N` 四舍五入 4 位，最后一期 = `100 - Σ前N-1`（尾差归末期）。
4. 日期：`anchor = billing_anchor_date or order 确认日`；`promised_date_i = add_months(anchor, (i-1)*interval) + billing_lead_days`。
5. `billing_proration='daily'` 且行有 `service_start_date/service_end_date`：
   - 每期窗口 = `[add_months(anchor, (i-1)*interval), add_months(anchor, i*interval))`
   - 与 `[service_start, service_end]` 求交集天数；`percent_i = 交集天数 / 总交集天数 × 100`（4 位，末期吸收尾差）
   - 总交集为 0 → `ORDER_BILLING_PLAN_INVALID`
6. 幂等（R-INV-23）：该行已存在 `status <> 'cancelled'` 的 billing 期次时跳过；行 `billed_amount > 0` 时任何情况下不重算。
7. 写入：`sales_order_schedules` 行字段 = `order_id/order_line_id/project_id/plant_location_id`（继承）、`schedule_kind='billing'`、`promised_qty=NULL`、`milestone_code=NULL`、`billing_percent`、`promised_date`、`status='planned'`、`billing_status='none'`、`billed_amount=0`。
8. 每行写入前调用 `sales_order_guard_service.validate_schedule_write(data, old=None)`；校验失败 → 整个订单确认回滚（D47）。
9. 触发：`sales_order_guard_interceptor` 的 after-write（status → `confirmed`）调用 `generate_for_order`；另有 BO action `sales_order.generate_billing_plan`（`idempotent=True`）供补跑。

### 6.3 C3：退货 → 贷项（`customer_invoice_service.create_credit_from_return_shipment`）

入参：

```json
{
  "return_shipment_id": 88,
  "return_line_ids": [901, 902],
  "invoice_date": "2026-11-10",
  "reason": "客户退货",
  "remark": "..."
}
```

流程：

1. 加载发货单：存在、`document_category='return'`、`status IN ('shipped','delivered')`，否则 `INVOICE_RETURN_ORIGIN_MISSING`；`return_line_ids` 为空 → 取全部行。
2. 逐退货行：`qty > 0`；`order_line_id` → 退货订单行，取 `reference_line_id`；为空 → `INVOICE_RETURN_ORIGIN_MISSING`；原行必须存在。
3. 累计退货量校验（R-RET-10）：原订单行已开票数量 = Σ 已过账正数发票行 `qty`（按 `order_line_id` 或 `shipment_line.order_line_id`）；Σ 历史退货贷项数量（按 `source_line_id` 归属原行聚合）不得超限。
4. 找原发票行（D42 FIFO）：`customer_invoice_lines` join `customer_invoices`，条件 = 原订单行、`status='posted'`、`original_invoice_line_id IS NULL`、`qty > 0`；按 `(invoice_date, invoice_line.id)` 升序，取剩余可贷数量（原数量 − 已贷数量）。
5. 分摊：退货行数量按 FIFO 拆成 1..N 个贷项行；每个贷项行数量 = `-分配量`，金额 = `-ROUND(分配量 × 原行 unit_price, 4)`。
6. 行字段：`source_doc_type='return_shipment'`、`source_doc_id=退货发货单 id`、`source_line_id=退货发货单行 id`、`original_invoice_line_id=原发票行 id`、`shipment_line_id/order_line_id/schedule_id` 从原发票行复制（D43：贷项仍回退开票进度）、`billing_basis/billing_percent/billing_base_amount` 从原行按 §6.4 规则换算。
7. 头字段：客户/币种/汇率/销售组织/项目/付款条件从原发票头复制（不是退货订单），`reversal_of_invoice_id = 原发票 id`（红字标识），`document_type_id` 取贷项通知单类型。
8. 找不到任何原发票行 → `INVOICE_RETURN_ORIGIN_MISSING`；原票已全额贷项 → `INVOICE_CREDIT_EXCEEDED`。
9. doc_flow：过账时同时写两条边——`return_shipment_line_to_credit_memo`（数量 = 分配量、金额 = 贷项净额绝对值）与既有 `customer_invoice_to_credit_memo`（按 `original_invoice_line_id`）。因此 `_write_doc_flow_edges` 的贷项分支不能再 `continue`，需按 `source_doc_type` 追加。

### 6.4 C4：部分贷项 / 多次贷项 / on-account

#### 6.4.1 `create_credit_from_invoice` 改造

入参扩展（向后兼容旧 `line_ids`）：

```json
{
  "source_invoice_id": 12,
  "invoice_date": "2026-11-10",
  "reason": "部分退货",
  "lines": [
    {"invoice_line_id": 101, "qty": 2},
    {"invoice_line_id": 102, "amount": 50.00}
  ]
}
```

- `lines` 为空 → 沿用 `line_ids` 或全量（旧行为）。
- 每个元素必须二选一：`qty` 或 `amount`；都给 → `INVOICE_CREDIT_AMOUNT_INVALID`。
- 未给数量/金额 → 取该行**剩余可贷**（原数量 − 已贷数量、原净额 − 已贷净额）。
- 校验（R-INV-20）：
  - `0 < 贷项数量 ≤ 剩余数量 + EPSILON`
  - `0 < 贷项金额 ≤ 剩余金额 + EPSILON`
  - 剩余按 4 位精度计算：`SUM(ABS(credit.qty))`、`SUM(ABS(credit.net_amount))`，只统计 `status='posted'` 贷项。
  - 超出 → `INVOICE_CREDIT_EXCEEDED`（替换原 `INVOICE_CREDIT_ALREADY_EXISTS` 整单拦截）。
- 行生成（`_negate_line` 增加参数）：
  - `qty = -贷项数量`
  - `unit_price = 原行 unit_price`（不变）
  - `net_amount = -贷项金额`（= `ROUND(数量 × 单价, 4)` 或显式金额）
  - `tax_amount = -ROUND(税基比例 × 贷项净额, 4)`，税基比例 = 原行 `tax_amount / net_amount`（原税额为 0 则为 0）
  - `gross_amount = net_amount + tax_amount`
  - `billing_basis/billing_percent/billing_base_amount`：原行按比例维护，则 `billing_percent = ROUND(原percent × 贷项金额 / 原行净额, 4)`；否则原值置空（R-INV-24）
  - 其余来源键（`shipment_line_id/schedule_id/order_line_id/original_invoice_line_id`）从原行复制
- **不再**调用 `_find_red_invoice`；`_assert_reversible` 保留（已有贷项时禁止 reverse 整单，防止重复冲减）。
- 头 `reversal_of_invoice_id` 仍设为原票（用于红字标识、`_is_red`、负数行、进度回退）。

#### 6.4.2 `create_credit_on_account`（D45）

入参：

```json
{
  "customer_id": 10,
  "currency_id": 1,
  "exchange_rate": 1.0,
  "invoice_date": "2026-11-10",
  "reason": "价格折让",
  "lines": [
    {"description": "年度返利", "qty": 1, "unit_price": -1000.00, "tax_code_id": null}
  ]
}
```

- 必须至少 1 行；每行 `net_amount < 0`（或由 `qty × unit_price` 计算后 < 0），否则 `INVOICE_ON_ACCOUNT_LINE_INVALID`。
- 行：`original_invoice_line_id/shipment_line_id/schedule_id/order_line_id` 全空；`source_doc_type='manual'`。
- 头：`reversal_of_invoice_id=NULL`；`document_category='credit_memo'`；`customer_id/currency_id` 必填。
- `_is_red` 改为 `document_category == 'credit_memo' or reversal_of_invoice_id`，保证 on-account 贷项按红字处理（负数、不走可用量校验、不生成应收期次）。
- 因无行键，`post` 的 `_apply_billed` 天然无副作用（R-INV-21 的可验证结果）。

### 6.5 C5：订单关闭与尾差口径

- `sales_order_guard_service` 的关闭前置（当前只校验 `fulfillment_status`）追加：
  - `billing_status='partial'` → `ORDER_BILLING_INCOMPLETE`
  - `none` / `full` → 放行（D46）
- 尾差口径写进规则注释与 spec（0.9）：
  - 金额比较统一 `EPSILON=0.0001`（元）
  - 比例合计容差 `PERCENT_TAIL_TOLERANCE=0.01`（%）
  - 计划开票累计超出期金额 > `EPSILON` → `INVOICE_PLAN_EXCEEDED`；超出 ≤ `EPSILON` 视为尾差接受
  - 比例校验不得使用金额常量，反向亦然

### 6.6 会计事件接口位（只留契约，不实现）

`_emit_accounting_event_hook` 仍为 no-op，但补一段契约注释，P2 的收入确认/GL 波次按此消费：

```
event_type: customer_invoice.posted | credit_memo.posted | invoice.reversed
payload: invoice_id, invoice_no, document_category, customer_id, currency_id,
         invoice_date, net_amount, tax_amount, gross_amount, line_count,
         source_breakdown: {shipment, schedule, return_shipment, manual}
触发点: post()/reverse() 提交事务前（同事务事件表），失败不影响单据
```

---

## 7. 迁移 `meta/migrations/v242__customer_invoice_wave_c.py`

镜像 v241 的 `upgrade / verify / rollback / _table_exists / _column_exists` 结构；幂等。

1. `ALTER TABLE sales_order_lines ADD COLUMN ...`（§4.1；已存在则跳过）。
2. 权限：插入 `customer_invoice:customer_invoice_submit` + 授予 admin/default + 挂菜单（复用 v239 的挂载函数）。
3. 播种 doc_flow 规则 `return_shipment_line_to_credit_memo`（先查后插）。
4. 建索引（§4.4；先查后建）。
5. `verify()`（直查 DB，失败抛错）：
   - 5 列存在且默认值正确
   - 权限与菜单挂载存在
   - doc_flow 规则 active、pool/source/target 正确
   - 索引存在（或同列等价索引）
   - `billing_proration` / 期数 / 间隔无非法值
6. `rollback()`：删规则 + 权限 + 菜单挂载 + 索引 + 5 列（仅当列为空/可删），幂等。

迁移测试 `meta/tests/test_migration_v242.py`：upgrade 幂等 / verify 通过 / 非法数据被 verify 捕获 / rollback 干净。

---

## 8. YAML 与前端

### 8.1 `sales_order_line.yaml`

新增只读/可编辑 5 字段（`billing_plan_*` 语义），条件可见：`billing_relevance='plan'` 时显示；`ui.editable` 仅在订单 draft 可编辑（沿用 R-INV-18 锁定口径）。`milestone` 时隐藏期数/间隔，`daily` 时提示需服务期。

### 8.2 `customer_invoice.yaml`

- `list.actions` 保持 create/export；**不新增**（动作按钮在详情页状态区）。
- `detail.actions` 保持 create_credit/print；新增 `create_credit_on_account`（permission `credit_memo`），按钮分组「更多」。
- `state_transition` 规则文案补充：`post` 的 confirm 提示「过账后不可修改，只能红冲」；`reverse` 要求 `reversal_date/reason`（沿用现有字段，不改结构）。

### 8.3 `shipment.yaml` / `sales_order.yaml`

- `shipment.yaml`：退货发货单详情页隐藏「生成销售发票」入口（`ui_view_config` 条件绑定 `document_category != 'return'`）。
- `sales_order.yaml`：详情页新增动作 `generate_billing_plan`（permission `sales_order:sales_order_update`，仅 `billing_status in (none, partial)` 可用）。

前端不新增页面；全部复用 `DetailPage.runBusinessAction` 与 `StateTransitionButtons`。

---

## 9. 状态机（本波之后的完整口径）

```
customer_invoice
  draft ──submit(action)──> submitted ──post(action)──> posted
    │                         │                          │
    │ cancel                  │ cancel                   │ reverse(action) ──> 红字 posted
    ▼                         ▼                          │                 （新单，原单不变）
  cancelled               cancelled                      └──（无 Void；Fusion Void 不实现）

sales_order
  draft ─confirm─> confirmed ─(after-write: generate billing plan)─> schedules(planned)
    │                 │
    │                 └─ close 前置：fulfillment_status 通过 AND billing_status != 'partial'
    ▼
  cancelled

credit memo（含 return / partial / on-account）
  draft ─post─> posted（负数行；回退开票进度或 on-account 无副作用）
```

**发票号时机（已知偏差）**：本仓库 draft 即分配 `invoice_no`；Fusion 在 Complete 阶段分配 `DocumentNumber`。本波不改（改时机需动唯一索引、断号策略与打印）。记录为 P3，后续如改，需单独立项。

---

## 10. 测试矩阵

### 10.1 C1 actions（`test_customer_invoice_actions.py`）≥ 9

1. submit 成功：draft → submitted，返回状态
2. submit 幂等：已 submitted 再调，返回同状态、无新历史
3. submit 拒绝：posted/cancelled → `INVOICE_STATE_INVALID`
4. post 成功：submitted → posted，回写与状态按钮一致
5. post 幂等：已 posted 再调，返回同状态、无二次回写
6. post 拒绝：draft（未提交）
7. reverse 成功：posted → 红字 posted，红字单 id 返回
8. reverse 幂等：再调返回同一红字 single id
9. reverse 拒绝：reason 为空 / 原票为红字

### 10.2 C2 计划生成（新增 `test_billing_plan_service.py`）≥ 12

均分 3 期比例 33.3333/33.3333/33.3334；固定价 1 期；里程碑跳过；锚点 + 间隔日期；提前 5 天/滞后 5 天；按日分摊首期；无服务期退化均分；服务期零交集拒绝；已有期次幂等；`billed_amount>0` 不重算；确认后自动生成（order confirm hook）；手工 action 补跑。

### 10.3 C3 退货贷项（`test_customer_invoice_service.py`）≥ 10

退货发货单正向开票拒绝；退货贷项单票追溯；跨两票 FIFO 拆分；部分数量；找不到原票拒绝；退货数量超已开票拒绝；累计退货超限拒绝；红字行来源键正确；过账写两条 doc_flow 边；重复提交同一退货行拒绝。

### 10.4 C4 部分/on-account 贷项 ≥ 10

部分数量；部分金额；两次部分贷项累计不超限；超额拒绝；qty+amount 同时给拒绝；plan 行比例换算；on-account 成功（负数、无行键、无进度回退）；on-account 正数拒绝；on-account 缺客户拒绝；`_is_red` 识别 on-account。

### 10.5 C5 guard ≥ 7

R-INV-19 / R-INV-20 / R-INV-21 / R-INV-23 / R-RET-10 / R-ORD-05 各 1+；尾差常量不可互换（0.01 vs 0.0001 边界用例 2 条）。

### 10.6 迁移 ≥ 4

upgrade 幂等 / verify 通过 / verify 捕获非法 `billing_proration` / rollback 干净。

---

## 11. 回归命令（唯一入口）

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file meta/tests/test_customer_invoice_service.py,meta/tests/test_customer_invoice_actions.py,meta/tests/test_customer_invoice_guard.py,meta/tests/test_billing_plan_service.py,meta/tests/test_migration_v242.py,meta/tests/test_sales_order_guard.py,meta/tests/test_sales_order_schedule_guard.py,meta/tests/test_shipment_service.py,meta/tests/test_payment_term_schedule.py,meta/tests/test_doc_flow.py,meta/tests/test_bo_action_registry.py
```

前端：`npm run build`（仅 YAML 变更时跑，确保 schema 校验通过）。

---

## 12. 风险与遗留

| 风险 | 影响 | 缓解 |
|---|---|---|
| 确认时生成失败阻断订单 | 订单确认失败率上升 | 计划字段由守卫前置校验；错误码明确；提供 `generate_billing_plan` 补跑 |
| 退货贷项 FIFO 与原票不匹配 | 贷到错误发票 | 只匹配同订单行 + 已过账 + 正数行；测试覆盖跨票拆分 |
| 贷项回退进度（D43）与 Fusion 不一致 | 对账口径差异 | spec 声明；AR 波次若要求 Fusion 口径，独立立项改造 |
| on-account 贷项进入应收负余额 | AR 未实现，暂不体现 | 仅保证单据与 doc_flow 正确；AR 波次消费 |
| v242 加列影响既有数据集 | 迁移失败 | 全部 `_column_exists` 幂等；rollback 可回退 |
| 打印/邮件只覆盖发票 | 贷项无法出 PDF | 记录为 P3，后续模板波次 |

---

## 13. 交付物

1. 本规格 `spec.md` + `tasks.md`
2. 代码：v242 迁移、`billing_plan_service.py`、customer_invoice service/actions/guards、YAML、bo_action 注册
3. 测试：新增/修改 8 个测试文件，新增用例 ≥ 52
4. 提交：按 tasks.md 分组，仅 s8 worktree