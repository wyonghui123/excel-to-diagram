# S8 Wave B 计划行开票（billing schedule）实施规格

> 状态：**待批准（批准前不写代码）**
> 日期：2026-11-09
> 工作树：`D:\filework\s8-billing-worktree`（分支 `agent/s8-billing`，基线 `7f155528`，端口 3012）
> 上游设计：`D:\filework\s7-worktree\docs\specs\spec-sales-order-billing-object-model-2026-11-07.md`
> §0.2 / §6 R-INV-3 / §20（计划行开票）/ §30.5（billing schedule）/ §31（Wave 划分）
> 上游 Wave A 规格：`docs/specs/s8-customer-invoice-wave-a/spec.md`
> 口径：只做「计划期次 → 销售发票」；不改表结构，不碰 AR，不做里程碑自动触发、服务确认开票。

---

## 0. 结论先行

| # | 问题 | 本波结论 |
|---|---|---|
| 0.1 | 计划行怎么开票 | 新增 `create_from_schedule`：按 `sales_order_schedules(schedule_kind='billing')` 生成草稿发票行，行上落 `schedule_id` + `billing_basis='percent'` |
| 0.2 | 是否需要新表 | **不需要**。Wave A 已建 `schedule_id` / `billing_percent` / `billing_base_amount` 与三张派生列 |
| 0.3 | 金额口径 | `期金额 = ROUND(billing_percent/100 × order_line.net_amount, 4)`；发票行 `qty=1`、`unit_price=行净额` |
| 0.4 | 一期能否开多票 | 允许（D11 采纳「分次」），累计以 `sales_order_schedules.billed_amount` 为准，不得超过期金额；尾差归最后一次 |
| 0.5 | 回写 | 过账累加 `sales_order_schedules.billed_amount` 并重算 `billing_status`；**不写** `shipment_line.billed_qty` / `order_line.billed_qty` |
| 0.6 | 红冲 | 红字行保留 `schedule_id` 与 `billing_basis='percent'`，金额取负；回滚 `billed_amount` 并重算状态；**原开票计划不置 cancelled** |
| 0.7 | doc_flow | 新增规则 `billing_schedule_to_customer_invoice`（v241 播种），红冲沿用既有 `customer_invoice_to_credit_memo` |
| 0.8 | 期次受控变更（D27） | 保持严格只读；`customer_invoice_schedules` 仍禁止任何写；`sales_order_schedules` 仅在 `billed_amount=0` 时允许编辑（R-SCH-17） |
| 0.9 | 容差冻结（D28） | 不做；不建 `settlement_block_code`；超订单总额不阻断 |
| 0.10 | 到期清单 | 不建表；只读查询 + BO action `customer_invoice.list_due_schedules`（无前端页面） |
| 0.11 | 迁移号 | `v241__customer_invoice_billing_plan.py`（当前最大 v240） |

---

## 1. 目标与验收口径

### 1.1 目标

在 Wave A（发货开票 / 手工开票）之上打开 **plan 分支**，让销售订单的开票计划（期次）成为发票来源：

```
sales_order_line(billing_relevance='plan')
  └─ sales_order_schedules(schedule_kind='billing', billing_percent, promised_date)
        └─(create_from_schedule)─> customer_invoice_line(schedule_id, billing_basis='percent')
              └─ post ─> sales_order_schedules.billed_amount += 行净额
                         sales_order_schedules.billing_status = none/partial/full
                         sales_orders.billing_status 重新派生
                         doc_flow: billing_schedule_to_customer_invoice
```

### 1.2 验收（全部满足才算完成）

- [x] `create_from_schedule` 可从一张/多张 billing 期次生成草稿发票；跨订单、非 plan 行、已作废/已兑现阶段一律拒绝。
- [x] 期金额、行净额、税额、总额按 §5.3 口径四舍五入到 4 位；Σ 行净额 = 头 `net_amount`。
- [x] `post` 原子完成：期次 `billed_amount` 累加、`billing_status` 更新、订单 `billing_status` 重新派生、doc_flow 边写入；失败整体回滚。
- [x] 同一期分次开票累计不超期金额；超容差以 `INVOICE_PLAN_EXCEEDED` 拒绝（并发由条件 UPDATE 兜底）。
- [x] `reverse` 红冲后 `billed_amount` 精确还原、`billing_status` 回退；原开票计划状态不变；红字行保留 percent 口径。
- [x] `billing_relevance` 成为受控字段（R-INV-18）：非 draft 锁定、被非取消发票行引用锁定、plan 必须有开票计划。
- [x] 到期清单只读查询与 action 可用，不产生任何写操作。
- [x] 新增测试：service >= 13、guard >= 6、sales_order_guard/schedule_guard >= 5、migration v241 >= 3、due_list >= 4、actions >= 3。
- [x] 回归：invoice / shipment / sales_order / payment_term / doc_flow / bo_action 既有用例全通过。

### 1.3 非目标（本波明确不做）

- 里程碑事件自动触发开票（`milestone_event` 表不做，计划期次由人工/到期清单驱动）。
- 服务确认开票（Wave C）、贷项行级部分冲销、借项通知单业务。
- 到期清单前端页面、订单页批量勾选（仅 action + 工具脚本）。
- 计划行改价（D13 仅适用 delivery 行；plan 行 `price_diff_amount` 恒 0）。
- 期次受控变更（重排期、金额调整）、超容差冻结（D28）、跨币种、合并跨客户开票。
- `sales_order_schedules.status` 自动流转到 `completed`（进度只看 `billing_status`）。
- AR 收款/核销/账龄/预付。

---

## 2. 待拍板决策（实现前置）

| 编号 | 决策 | 本波建议 | 若否决的影响 |
|---|---|---|---|
| **D3** | `sales_order_schedules.billing_percent/billing_amount/promised_date` 当前文案是「收款比例 / 收款金额 / 收款日」，架构与上游设计文档均定义为**开票计划（billing plan）** | **按既有文档结论 D3-a 执行**：本波把它当开票计划；只把 schema `name/description` 与 R-SCH-11..15 注释中的「收款」改为「开票」，**不改列名** | 若业务正式确认它其实是**收款计划**（与三份既有文档冲突），Wave B 暂停，另起开票计划字段/对象，不能直接复用本列 |
| **D11** | 同一期是否允许分次开票 | **允许**，累计 ≤ 期金额，尾差归最后一次 | 若要求「一期一票」，删去 §5.3 的 `billing_percent` 入参分支，剩余不足直接拒绝 |
| **D27** | 期次受控变更 | **维持严格只读**（Wave A 口径不放开） | — |
| **D28** | 超订单总额容差冻结 | **不做** | — |
| **D31** | 计划期次开票是否要求 `promised_date <= 今天` | **不强制**：action 允许提前开票，到期清单负责「该开了」的可见性 | 若要求硬门禁，`create_from_schedule` 增加 `INVOICE_PLAN_NOT_DUE` |

> **D3 依据（2026-11-09 全仓核查，非新未知项）**：仓库已有明确文档结论，D3 应按 **D3-a（开票计划口径）** 执行：
> - `docs/ARCHITECTURE_V3.md` §468（架构级）：「计划行……只承载承诺交期/承诺量/**开票比例**」；§545 列清单含 `billing_percent` / `billing_amount`。
> - `docs/specs/spec-sales-order-billing-object-model-2026-11-07.md`（s7 工作树）§0.2 第 21/66 行：「`sales_order_schedules(schedule_kind='billing')` 是**开票计划（billing plan）**，不是发票」；「字段命名写成『收款比例/收款金额/收款日』，实际是开票里程碑，这是要澄清的核心语义债」；§21.3/§21.4 结论「收款计划 ≠ 开票计划，必须拆」，推荐 **D3-a**「把 `sales_order_schedules` 文案彻底锁死为开票计划」；§30.4 `billing_percent` =「本期开票比例（相对 `billing_base_amount`）」。
> - `docs/superpowers/specs/2026-10-26-sales-order-schedule-line-spec.md` 第 241 行：`billing_percent` 为开票比例（0 < p ≤ 100），金额按 `billing_percent / 100 × 行净额` 派生、不落库。
> - 唯一不一致：`meta/schemas/sales_order_schedule.yaml` 的 `name/description` 仍写「收款比例/收款金额/收款日」——正是上文所述文案债，也是 T25 要改的对象。
>
> 因此 PM 签字本质是**对既有结论的形式确认**，不是重新定义语义；本规格全部内容以「D3 = 开票计划（D3-a）」为前提。

### 2.1 来源互斥（R-INV-3 扩展）

| `source_doc_type` | Wave A | Wave B |
|---|---|---|
| `shipment` | ✅ | ✅ |
| `sales_order` | ✅（手工整单） | ✅ |
| `manual` | ✅ | ✅ |
| `billing_schedule` | ❌ 拒绝 | ✅（仅 plan 行） |
| `service_confirmation` | ❌ 拒绝 | ❌ 仍拒绝（Wave C） |

`billing_schedule` 行必须满足：`schedule_id` 非空、`shipment_line_id` 空、`order_line_id` 空、`billing_basis='percent'`、`0 < billing_percent <= 100`、`qty=1`、对应订单行 `billing_relevance='plan'`。

---

## 3. 数据模型

> **本波不建表、不加列**。以下列均由 v236 创建，Wave B 只补 schema 声明（UI/API 可见性）与一个索引。

### 3.1 既有列（v236 已建）

| 表 | 列 | 本波角色 |
|---|---|---|
| `sales_order_lines` | `billing_relevance` (`delivery`/`plan`) | 决定行走哪条开票分支；R-INV-18 受控 |
| `sales_order_lines` | `billed_qty` / `billed_amount` | delivery 分支沿用；plan 分支不写 |
| `sales_order_schedules` | `billed_amount` | **plan 分支唯一累计真源** |
| `sales_order_schedules` | `billing_status` (`none`/`partial`/`full`/`cancelled`) | plan 分支派生 |
| `sales_orders` | `billing_status` / `billing_derived_at` | 聚合派生（delivery + plan） |
| `customer_invoice_lines` | `schedule_id` / `billing_percent` / `billing_base_amount` / `billing_basis` | 计划开票行落值 |

### 3.2 schema 补声明（T25）

| 文件 | 变更 |
|---|---|
| `meta/schemas/sales_order_line.yaml` | 新增只读派生字段 `billing_relevance`（enum）、`billed_qty`、`billed_amount`；`ui.editable: false`、`derived: true` |
| `meta/schemas/sales_order_schedule.yaml` | 新增只读派生字段 `billed_amount`、`billing_status`；`billed_amount` 不出现在可编辑表单 |
| `meta/schemas/sales_order.yaml` | 新增只读派生字段 `billing_status`、`billing_derived_at` |
| `meta/schemas/customer_invoice_line.yaml` | `source_doc_type` enum 增加 `billing_schedule`；`billing_percent` 描述改为「按比例开票的比例（0-100）」，去掉「预留」字样 |
| `meta/schemas/sales_order_schedule.yaml` | 若 D3 批准：`billing_percent` / `billing_amount` / `promised_date` 文案由「收款」改「开票」 |

> 仅元数据声明，不改 DDL；`verify()` 仍以 DB 列为准。

### 3.3 索引（v241）

```sql
CREATE INDEX IF NOT EXISTS idx_sos_billing_due
  ON sales_order_schedules (schedule_kind, billing_status, promised_date);
```

服务到期清单与 `billing_status` 扫描使用。

### 3.4 行键约定

`billing_schedule` 行（v236 CHECK 已允许）：

- `source_doc_type = 'billing_schedule'`
- `source_doc_id = schedule.order_id`（头级来源 = 订单）
- `source_line_id = schedule.id`
- `schedule_id = schedule.id`
- `shipment_line_id = NULL`、`order_line_id = NULL`（保持三键 XOR）
- 订单/订单行通过 `schedule.order_line_id` 反查，不落冗余外键

---

## 4. 迁移 `meta/migrations/v241__customer_invoice_billing_plan.py`

> 镜像 `v240__customer_invoice_credit_doc_flow.py` 的 `upgrade / verify / rollback / _table_exists` 结构；幂等。

执行顺序：

1. **播种 doc_flow 规则**（先查 `rule_id` 再插）：

   | 字段 | 值 |
   |---|---|
   | `rule_id` | `billing_schedule_to_customer_invoice` |
   | `source_bo` | `sales_order_schedule` |
   | `target_bo` | `customer_invoice_line` |
   | `pool` | `billing` |
   | `source_qty_field` | `billing_percent`（语义标记；attach 时显式传 `qty=1`） |
   | `status` | `active` |

2. **建索引**：§3.3。
3. **verify()**（直接查 DB，失败抛错）：
   - 规则存在、`status='active'`、`pool='billing'`、source/target 正确。
   - 索引存在。
   - `sales_order_schedules.billing_status` 无非法值（`none/partial/full/cancelled`）。
   - `sales_order_schedules.billed_amount >= 0`。
4. **rollback()**：删除规则 + 索引（仅当无引用）。
5. **迁移测试**：`meta/tests/test_migration_v241.py`（连续 upgrade 不重复、verify 通过、rollback 干净）。

---

## 5. 服务层 `meta/services/customer_invoice_service.py`

### 5.1 常量与错误码（新增）

| 常量 / 错误 | 含义 |
|---|---|
| `SOURCE_PLAN = 'billing_schedule'` | 计划来源 |
| `BILLING_BASIS_PERCENT = 'percent'` | 计划行口径 |
| `INVOICE_PLAN_EXCEEDED` | 期次剩余金额不足 |
| `INVOICE_PLAN_STATE_INVALID` | 期次已作废/已兑现/非 billing kind |
| `INVOICE_ORDER_STATE_INVALID` | 订单不是 confirmed/closed |
| `INVOICE_PLAN_ORDER_MISMATCH` | 一次开票混入多张订单 |
| `INVOICE_PLAN_PERCENT_INVALID` | 比例 ≤0、>100 或超过剩余比例 |
| `INVOICE_RELEVANCE_NOT_PLAN` | 订单行不是 `plan` |

错误对象沿用 `CustomerInvoiceError(rule=...)`，action 层 `_fail(str(exc), exc.rule)`。

### 5.2 `create_from_schedule(payload)`

入参：

```json
{
  "schedule_ids": [101, 102],
  "lines": [{"schedule_id": 101, "billing_percent": 30}],
  "invoice_date": "2026-11-09",
  "payment_term_id": 3,
  "remark": "..."
}
```

- `lines` 优先于 `schedule_ids`；两者至少一个非空。
- `source_doc_id` 兼容：当只传单个 `source_doc_id`（前端 schedule 详情按钮）时按 `schedule_id` 解释。
- 一次开票只允许同一 `order_id`；混单 → `INVOICE_PLAN_ORDER_MISMATCH`。
- 来源校验（逐期次）：
  1. 期次存在、`schedule_kind='billing'`、`status IN ('planned','confirmed')`，否则 `INVOICE_PLAN_STATE_INVALID`。
  2. 订单 `status IN ('confirmed','closed')`，否则 `INVOICE_ORDER_STATE_INVALID`。
  3. 订单行 `billing_relevance='plan'`，否则 `INVOICE_RELEVANCE_NOT_PLAN`。
  4. `billing_percent` 属 (0,100]；入参比例 ≤ 剩余比例 + EPS，否则 `INVOICE_PLAN_PERCENT_INVALID`。
  5. 剩余金额 > EPS，否则 `INVOICE_PLAN_EXCEEDED`。
- 头字段从订单快照（客户、币种、汇率、销售组织、项目、付款条件默认值），与 `create_from_shipment` 共用 `prepare_header`。
- 返回 `{id, invoice_no, status:'draft', line_ids}`。

### 5.3 `_build_line_from_schedule(schedule, order_line, percent_override=None)`

计算口径（统一 `ROUND_HALF_UP` 4 位）：

```
base            = order_line.net_amount
period_amount   = ROUND(schedule.billing_percent / 100 * base, 4)
billed          = schedule.billed_amount
remaining       = period_amount - billed
remaining_pct   = schedule.billing_percent - ROUND(billed / base * 100, 4)
```

- 未传 `billing_percent`：进入「收尾模式」→ `net = remaining`，行 `billing_percent = ROUND(net/base*100, 4)`。
- 传入 `p`：`net = ROUND(p/100 * base, 4)`；若 `abs(net - remaining) <= 0.01` 则 `net = remaining`（尾差吸收并关期）。
- 行值：`qty=1`、`unit_price=net`、`billing_basis='percent'`、`billing_base_amount=base`、`billing_percent` 按上式、`tax_code_id/tax_rate_percent` 取订单行、`price_source='order'`、`order_unit_price=NULL`（plan 不做改价）、`price_diff_amount=0`。
- 税额：`tax = ROUND(net * tax_rate_percent / 100, 4)`；`gross = net + tax`。
- 描述/物料/UOM/项目透传订单行。

### 5.4 过账 `post`（在 Wave A 八步上扩展）

1-5 步不变（校验、状态、期次生成、快照）。
6. **回写** `_apply_billed(lines, sign=+1)`：
   - delivery 行：沿用 Wave A（`shipment_line.billed_qty`、`order_line.billed_qty/billed_amount`）。
   - plan 行：按 `schedule_id` **聚合**后更新一次：
     ```sql
     UPDATE sales_order_schedules
        SET billed_amount = ROUND(billed_amount + :delta, 4)
      WHERE id = :schedule_id
        AND ROUND(billed_amount + :delta, 4) <= :period_amount + 0.0001
     ```
     影响行数必须为 1，否则 `INVOICE_PLAN_EXCEEDED`（并发双过账的兜底）。
   - 更新后 `billing_status = none / partial / full`（`billed<=EPS` → none；`billed>=period-EPS` → full；其余 partial）。
7. **doc_flow** `_write_doc_flow_edges`：plan 行走 `billing_schedule_to_customer_invoice`，`source_id=schedule_id`、`target=line_id`、`quantity=1`、`amount=net`。规则缺失只告警，不阻断。
8. **重算订单** `recompute_order_billing`（见 5.6）。

### 5.5 红冲 `reverse`（扩展）

- 红字行 `_negate_line`：
  - plan 行：`qty=-1`、净额/税额/总额取负、**保留** `billing_basis='percent'`、`billing_percent` 与 `billing_base_amount`；不得强制改成 `quantity`。
  - delivery 行：保持 Wave A 行为。
- `_apply_billed(red_lines, sign=-1)`：
  - plan 行按 `abs(net)` 从 `billed_amount` 扣减，条件 `billed_amount - :delta >= -0.0001`，并重算 `billing_status`。
  - **不修改** `sales_order_schedules.status`（原开票计划保持 planned/confirmed）。
- `customer_invoice_schedules`（本发票 AR 期次）仍全部置 cancelled（Wave A 行为不变）。
- 原单 → `reversed`；`INVOICE_REVERSE_EXISTS` / `INVOICE_ALLOCATION_EXISTS` 检查沿用。

### 5.6 `recompute_order_billing`（扩展）

- delivery 行：沿用 Wave A（`billed_qty >= qty` 判 full）。
- plan 行：查 `sales_order_schedules`（`schedule_kind='billing'`、`status<>'cancelled'`）的 `billing_status`：
  - 无期次 → `none`
  - 全部 `full` → `full`
  - 全部 `none` → `none`
  - 其余 → `partial`
- 订单级聚合：所有 delivery 行 full **且** 所有 plan 行 full → `full`；完全无开票活动 → `none`；其余 `partial`。
- `billing_derived_at = NOW`。
- 触发范围：plan 行需经 `schedule_id → order_line_id → order_id` 反查订单。

### 5.7 可用量校验 `_assert_lines_available`（扩展）

- plan 行：重新计算 `remaining = period_amount - billed_amount`，要求 `net <= remaining + EPS`；同时复核 5.2 的来源状态（防止草稿期间订单被取消/期次作废）。
- 红字行跳过。
- delivery 行行为不变。

### 5.8 `_assert_relevance` 调整

改为 `_assert_relevance(order_line, expected)`：

- delivery 路径要求 `delivery`；plan 路径要求 `plan`。
- `billing_relevance='none'` 或与路径不符 → `INVOICE_RELEVANCE_NOT_PLAN` / `INVOICE_SOURCE_MISMATCH`。

`create_manual` / `create_from_shipment` 的 plan 来源继续 fail-closed：手工行带 `schedule_id` → `INVOICE_SOURCE_MISMATCH`。

---

## 6. 守卫拦截器

### 6.1 `customer_invoice_guard_interceptor.py`

- 行写入（draft）：放行 `schedule_id` 路径，但必须通过 `service.validate_line_write` 的 5.2/5.7 校验；`billing_schedule` 行禁止改 `schedule_id`、`billing_basis`、`billing_base_amount`。
- `_LINE_NORMALIZED_KEYS` 已含 `billing_percent/billing_base_amount/billing_basis`，确认 `price_diff_amount` 仍在（Wave A 已加）。
- `submitted/posted/reversed/cancelled` 头字段冻结、`customer_invoice_schedules` 任意写拒绝：**保持不变**（D27 严格只读）。

### 6.2 销售订单守卫 `sales_order_guard_service.py`（R-INV-18）

| 规则 | 内容 | 错误码 |
|---|---|---|
| R-INV-18a | `billing_relevance` 仅 `draft` 可改；`submitted` 起只读 | `BILLING_RELEVANCE_LOCKED` |
| R-INV-18b | 订单行被任何非 cancelled 发票行引用（`schedule_id` 或 `shipment_line_id`）→ 锁定 | `BILLING_RELEVANCE_LOCKED` |
| R-INV-18c | 设为 `plan` 必须同时满足 `billing_method='milestone'` 且至少一条 `schedule_kind='billing'` 期次 | `BILLING_PLAN_REQUIRED` |
| R-INV-18d | `plan → delivery` 且任一期次 `billed_amount > 0` → 拒绝 | `BILLING_PLAN_IN_USE` |
| R-SCH-17 | 期次 `billed_amount > 0` 时禁止改 `billing_percent/promised_date`、禁止 `status='cancelled'`、禁止删除 | `BILLING_SCHEDULE_IN_USE` |

> R-SCH-11..15 既有校验保留；若 D3 批准，只改文案不改规则。

---

## 7. 到期清单（只读）

### 7.1 工具 `meta/tools/billing_due_list.py`

```sql
SELECT o.order_no, ol.line_no, s.id AS schedule_id, s.sequence_no,
       s.promised_date, s.billing_percent, ol.net_amount,
       ROUND(s.billing_percent / 100.0 * ol.net_amount, 4) AS period_amount,
       s.billed_amount,
       ROUND(s.billing_percent / 100.0 * ol.net_amount, 4) - s.billed_amount AS remaining,
       s.billing_status
  FROM sales_order_schedules s
  JOIN sales_order_lines ol ON ol.id = s.order_line_id
  JOIN sales_orders o       ON o.id = ol.order_id
 WHERE s.schedule_kind = 'billing'
   AND s.status IN ('planned', 'confirmed')
   AND s.billing_status <> 'full'
   AND s.promised_date <= :as_of
   AND o.status IN ('confirmed', 'closed')
 ORDER BY s.promised_date, o.order_no, s.sequence_no;
```

- `:as_of` 默认今天；只读；退出码 0（无到期）/ 2（有到期，便于脚本判断）/ 1（异常）。
- 不修改任何数据。

### 7.2 BO action `customer_invoice.list_due_schedules`

- 注册于 `meta/services/bo_action_registrations.py`：`permission_required='customer_invoice:customer_invoice_view'`、`requires_auth=True`、`idempotent=True`。
- 返回 `{items:[...], total}`，字段同上；支持 `as_of` / `order_id` / 分页参数。
- **不做前端页面**。

---

## 8. 前端入口（最小）

- `meta/schemas/sales_order_schedule.yaml` `ui_view_config.detail.actions` 追加：
  ```yaml
  - key: create_invoice
    label: 生成销售发票
    action: customer_invoice.create_from_schedule
    permission: customer_invoice:customer_invoice_create
  ```
- 复用 Wave A T10 的 `DetailPage.runBusinessAction`：`source_doc_id=props.id` 传入，服务 action 在无 `schedule_id` 时把 `source_doc_id` 当 `schedule_id`。
- 成功 toast + `handleRefresh()`；不新增页面、不做跳转。

---

## 9. 规则清单（新增/变更）

| 规则 | 说明 |
|---|---|
| R-INV-3（扩展） | `billing_schedule` 仅 plan 行可入；其余来源互斥不变 |
| R-INV-24 | 计划开票必须来源 `billing` 期次且订单 confirmed/closed |
| R-INV-25 | 期次累计开票金额 ≤ 期金额；尾差归最后一次 |
| R-INV-26 | 期次开票行 `qty=1`、`billing_basis='percent'`、`billing_percent ∈ (0,100]` |
| R-INV-27 | 红冲按 `abs(net)` 回滚期次金额；原期次状态不回退 |
| R-INV-28 | 订单 `billing_status` = delivery 与 plan 分支的联合派生 |
| R-INV-18（新增） | `billing_relevance` 受控（见 6.2） |
| R-SCH-17（新增） | 期次有开票金额后只读（见 6.2） |

---

## 10. 测试矩阵

### 10.1 服务 `test_customer_invoice_service.py`（新增 >= 13）

1. 单期次整期开票：期金额/税额/总额正确。
2. 同一订单多期次合并一张发票。
3. 同一期次分次开票（30% + 剩余），尾差归最后一次。
4. 超过剩余金额 → `INVOICE_PLAN_EXCEEDED`。
5. 非 plan 订单行 → `INVOICE_RELEVANCE_NOT_PLAN`。
6. 期次 `cancelled/completed` → `INVOICE_PLAN_STATE_INVALID`。
7. 订单非 confirmed/closed → `INVOICE_ORDER_STATE_INVALID`。
8. 多订单混开 → `INVOICE_PLAN_ORDER_MISMATCH`。
9. 过账后 `billed_amount`、`billing_status`（partial/full）正确。
10. 过账触发订单 `billing_status`（含 delivery + plan 混合）正确。
11. 红冲后 `billed_amount` 还原、`billing_status` 回退、期次状态不变。
12. 红字 plan 行保持 `billing_basis='percent'` 与负金额。
13. 并发兜底：期次剩余不足时第二次过账失败并整体回滚。
14. 手工行携带 `schedule_id` → `INVOICE_SOURCE_MISMATCH`。

### 10.2 守卫 `test_customer_invoice_guard.py`（新增 >= 6）

1. draft 新增 plan 行成功，XOR 违规失败。
2. `submitted` 头字段冻结不变。
3. 期次耗尽后过账被拒。
4. draft 修改 `billing_percent` 重新校验。
5. `customer_invoice_schedules` 写操作仍拒绝。
6. plan 行修改 `schedule_id/billing_basis` 被拒。

### 10.3 订单/计划守卫（新增 >= 5）

- `test_sales_order_guard.py`：R-INV-18a/b/c/d 各 1 例。
- `test_sales_order_schedule_guard.py`：R-SCH-17（有金额禁改比例/禁作废）1-2 例。

### 10.4 迁移 `test_migration_v241.py`（>= 3）

1. upgrade 幂等、规则唯一。
2. verify 通过、索引存在。
3. rollback 删除干净。

### 10.5 到期清单 `test_billing_due_list.py`（>= 4）

1. 只返回到期且非 full、订单 confirmed/closed。
2. 排除 full/cancelled 期次与 draft 订单。
3. `remaining` 计算正确。
4. `as_of` 生效。

### 10.6 action `test_customer_invoice_actions.py`（>= 3）

1. `create_from_schedule` 成功。
2. 业务错误透传 `rule`。
3. `source_doc_id` 作为 `schedule_id` 的兼容路径。

---

## 11. 回归与验收命令

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v241.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_billing_due_list.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_sales_order_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_sales_order_schedule_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_sales_order_schedule_billing.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_sales_order_schedule_billing_amount.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_bo_action_contract.py --port 3012
```

---

## 12. 完成定义（DoD）

- [ ] D3 已由 PM 签字（按「开票计划」口径）。
- [ ] T25-T34 全部完成，新增测试全部通过。
- [ ] `v241.verify()` 通过；到期清单工具在干净数据退出码 0。
- [ ] 无新表/新列；无 AR、无 milestone_event、无 settlement_block_code、无前端页面。
- [ ] `customer_invoice_schedules` 只读口径未放开（D27）。
- [ ] 仅 s8 worktree 提交；主工作树与 s7-worktree 未改动。