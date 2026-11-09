# S8 Wave A 销售发票（customer_invoice）实施规格

> 状态：**待批准（批准前不写代码）**
> 日期：2026-11-09
> 工作树：`D:\filework\s8-billing-worktree`（分支 `agent/s8-billing`，基线 `e35fe99d`，端口 3012）
> 上游设计：`D:\filework\s7-worktree\docs\specs\spec-sales-order-billing-object-model-2026-11-07.md` §4-§11 / §20 / §30 / §31
> 口径：只做 Wave A（发货开票 + 手工开票），`plan` 分支 fail-closed 拒绝；不含贷项/部分冲销/合并开票/跨币种/AR 台账/UI 页面。

---

## 1. 目标与验收口径

### 1.1 目标

把「开票计划（半成品）」接到一张独立事实单据上，补齐销售链路：

```
shipment_line --(delivery)--> customer_invoice_line --> customer_invoice(post)
                                                         ├─ customer_invoice_schedule（期次）
                                                         ├─ doc_flow 边（pool=billing）
                                                         └─ 回写 shipment_line.billed_qty / order_line.billed_* / billing_status
```

### 1.2 验收（全部满足才算完成）

- [ ] 三张新表 + 五个派生列由 v231 迁移幂等创建，`verify()` 自检通过。
- [ ] 从已发运/已签收的发货单可生成草稿发票；重复开票、超量开票被拒。
- [ ] `post` 原子完成：状态→posted、期次生成（Σ金额=gross）、billed 回写、doc_flow 边写入、billing_status 派生。
- [ ] `reverse` 生成红字发票（负数量/负金额、无期次），回滚 billed、取消原期次、原单→reversed。
- [ ] `plan`/`none` 开票来源一律 fail-closed，错误码可定位。
- [ ] 新增测试：service >= 14、schedule >= 6、guard >= 8、migration >= 4，全部通过。
- [ ] 回归：shipment / sales order / payment term 既有测试无失败。

### 1.3 非目标（本波明确不做）

- 计划行开票（Wave B）、服务确认开票（Wave C）、里程碑事件。
- 贷项凭证行级部分冲销、借项通知单业务、合并跨单开票、跨币种。
- AR 收款/核销/账龄/预付（`amount_applied` 仅保留 0 默认列）。
- 期次受控变更（D27：严格只读，不做重排期）、超容差冻结（D28：不建 `settlement_block_code`）。
- 前端页面与菜单手工配置（菜单由 `menu_auto_generator` 从 schema 自动生成）。

---

## 2. 已定口径与 TBD 回避

| TBD | 本波处理 | 落地方式 |
|---|---|---|
| D3 `billing_percent` 口径 | 不触碰 | 不改 `sales_order_schedules.billing_percent` 语义；计划分支不参与开票 |
| D6 L2 会计事件 | 只留 hook | `_emit_accounting_event_hook()` 空实现，不建表、不发消息 |
| D11 一期分次 | 不做 | 期次只在过账时按付款条件一次性生成；无计划分期开票 |
| D14/D15/D19 收款/核销/预付 | 不做 | 不建收款/核销对象；红冲前查询 `payment_allocations`，表不存在按 0 处理 |
| D20 合同对象 | 不做 | 无合同外键、无合同金额校验 |
| D27 期次受控变更 | 采用严格版 R-INV-22 | `customer_invoice_schedule` 任何写操作拒绝；红冲仅把原期次置 cancelled |
| D28 容差冻结 | 不做 | 不建 `settlement_block_code`；超订单金额不阻断（留给 AR 侧决策） |

**来源互斥（R-INV-3）**：Wave A 只允许 `shipment` / `sales_order` / `manual` 三种 `source_doc_type`；`billing_schedule` 与 `service_confirmation` 一律返回 `INVOICE_RELEVANCE_NOT_SUPPORTED`。

---

## 3. 数据模型

> 三个 YAML 的结构（`aspects` / `ui_view_config` / `relations` / `indexes` / `semantics`）镜像
> `meta/schemas/shipment.yaml`、`shipment_line.yaml`、`sales_order_schedule.yaml`；下面只列本对象的决策内容。

### 3.1 `meta/schemas/customer_invoice.yaml`

- `id: customer_invoice`，`table_name: customer_invoices`，`display_name_field: invoice_no`
- `aspects: [audit_aspect, document_type_aspect]`
- `numbering: {no_field: invoice_no, date_field: invoice_date, type_table: type_definitions}`
- `org_scope: {mode: direct, field: org_id, function: finance, write_check: true}`
- `deletion_policy: {mode: restrict, cascade_delete: [customer_invoice_lines]}`
- `audit: {enabled: true, create: all, update: changed_only, delete: business_only}`
- 不声明 `revision_policy`

字段（与 §4 + §30.3 对齐）：

| 字段 | 类型 | 必填 | 备注 |
|---|---|---|---|
| id | integer | 是 | PK |
| invoice_no | string(30) | 是 | 唯一、取号后不可改 |
| document_type_id | integer | 是 | `scope_bo=customer_invoice` + `level=header` |
| invoice_date | date | 是 | 编号日期段基准 |
| posting_date | date | 否 | 过账时为空则取 invoice_date |
| status | enum | 是 | draft / submitted / posted / cancelled / reversed |
| customer_account_id | integer | 是 | 售达方 |
| bill_to_account_id | integer | 否 | 空=售达方 |
| payer_account_id | integer | 否 | 空=售达方 |
| bill_to_address_text | string(512) | 否 | 地址快照 |
| tax_registration_no | string(64) | 否 | 购方税号快照 |
| currency_id | integer | 是 | 必须等于订单币种（R-INV-18） |
| exchange_rate | number(18,8) | 否 | 快照 |
| exchange_rate_type | string(20) | 否 | 快照 |
| exchange_rate_date | date | 否 | 快照 |
| payment_term_id | integer | 否 | 过账时为空按即期（1 期 100%） |
| incoterm_code | string(16) | 否 | 快照 |
| net_amount / tax_amount / gross_amount | number(18,4) | 是 | 服务层汇总，默认 0 |
| org_id | integer | 是 | 财务归属 |
| sales_org_id | integer | 否 | 数据范围 |
| project_id | integer | 否 | 单项目时填 |
| reversal_of_invoice_id | integer | 否 | 红字单指向原单 |
| reversal_reason | string(256) | 否 | 红冲原因 |
| remark | text | 否 | 备注 |
| created_at / updated_at | datetime | 是 | audit_aspect |

状态机（rules）：

```
draft --submit--> submitted --post--> posted --reverse--> reversed
  └--cancel--┘        └--cancel--┘
```

- `state_field_policies.readonly`（UI 元数据，守卫做强校验）：
  - `submitted`: invoice_no / document_type_id / customer_account_id / bill_to_account_id / payer_account_id / currency_id / exchange_rate / exchange_rate_type / exchange_rate_date / org_id / sales_org_id
  - `posted` / `reversed` / `cancelled`: 全部业务字段只读

### 3.2 `meta/schemas/customer_invoice_line.yaml`

- `id: customer_invoice_line`，`table_name: customer_invoice_lines`
- `parent_object: customer_invoice`，`hierarchy: {parent_field: invoice_id, parent_object: customer_invoice}`
- `aspects: [audit_aspect]`；`deletion_policy: {mode: cascade}`（随头级联，头删除由守卫限制为 draft）
- 唯一键：`(invoice_id, line_no)`；索引：`(shipment_line_id)`、`(schedule_id)`、`(order_line_id)`

字段（§5 + §30.4）：

| 字段 | 类型 | 必填 | 备注 |
|---|---|---|---|
| id / invoice_id / line_no | integer | 是 | 行号在头内唯一 |
| line_type_id | integer | 是 | `scope_bo=customer_invoice` + `level=line` |
| source_doc_type | enum | 是 | shipment / sales_order / manual（其余拒绝） |
| source_doc_id | integer | 否 | 来源头 id |
| source_line_id | integer | 否 | 来源行 id |
| shipment_line_id / schedule_id / order_line_id | integer | 否 | 语义快照键，只读 |
| item_id | integer | 否 | 服务行可空 |
| description | string(512) | 是 | 快照 |
| uom_id | integer | 是 | 快照 |
| qty | number(18,4) | 是 | 非红字 > 0 |
| billing_basis | enum | 是 | quantity / percent / amount（Wave A 仅 quantity、amount） |
| unit_price | number(18,6) | 是 | 快照/反算 |
| net_amount / tax_amount / gross_amount | number(18,4) | 是 | 服务层计算 |
| tax_code_id | integer | 是 | 快照 |
| tax_rate_percent | number(9,4) | 是 | 快照 |
| project_id / project_task_id | integer | 否 | 透传 |
| billing_percent | number(9,4) | 否 | 按比例行使用（Wave A 仅预留） |
| billing_base_amount | number(18,4) | 否 | 按金额行依据（Wave A 预留） |
| price_source | enum | 是 | order / manual |
| order_unit_price | number(18,6) | 否 | 改价前订单单价快照 |
| price_change_reason | string(256) | 否 | 改价原因 |
| price_change_approved_by | string(64) | 否 | 改价审批人 |
| original_invoice_line_id | integer | 否 | 红字行指向原发票行 |

约束（迁移 DDL 内 CHECK，schema 无声明机制）：

```sql
CHECK (
  (shipment_line_id IS NOT NULL AND schedule_id IS NULL AND order_line_id IS NULL)
  OR (shipment_line_id IS NULL AND schedule_id IS NOT NULL AND order_line_id IS NULL)
  OR (shipment_line_id IS NULL AND schedule_id IS NULL AND order_line_id IS NOT NULL)
  OR (shipment_line_id IS NULL AND schedule_id IS NULL AND order_line_id IS NULL)
)
CHECK (billing_basis IN ('quantity','percent','amount'))
CHECK (source_doc_type IN ('shipment','sales_order','manual','billing_schedule','service_confirmation'))
```

### 3.3 `meta/schemas/customer_invoice_schedule.yaml`

- `id: customer_invoice_schedule`，`table_name: customer_invoice_schedules`
- `parent_object: customer_invoice`，`hierarchy: {parent_field: invoice_id, parent_object: customer_invoice}`
- `aspects: [audit_aspect]`；`deletion_policy: {mode: restrict}`
- 唯一键：`(invoice_id, schedule_no)`；索引：`(status, due_date)`、`(invoice_id)`
- 无 rules / 无状态机（`status` 为服务层派生字段）

| 字段 | 类型 | 必填 | 备注 |
|---|---|---|---|
| id / invoice_id / schedule_no | integer | 是 | 期次序号 1..N |
| payment_term_line_id | integer | 否 | 回指付款条件行 |
| ratio_percent | number(9,4) | 是 | 比例快照 |
| due_date | date | 是 | 到期日 |
| amount | number(18,4) | 是 | Σ=gross，尾差归最后一期 |
| amount_applied | number(18,4) | 是 | 默认 0；AR 未建，本波不写 |
| status | enum | 是 | open / partial / closed / cancelled，默认 open |
| created_at / updated_at | datetime | 是 | audit_aspect |

### 3.4 派生列（ALTER）

| 表 | 列 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| sales_order_lines | billing_relevance | varchar(16) NOT NULL | 'delivery' | delivery / plan |
| sales_order_lines | billed_qty | decimal(18,4) NOT NULL | 0 | 发票净数量累计 |
| sales_order_lines | billed_amount | decimal(18,4) NOT NULL | 0 | 发票净额累计 |
| sales_order_schedules | billed_amount | decimal(18,4) NOT NULL | 0 | Wave B 用，本波恒 0 |
| sales_order_schedules | billing_status | varchar(16) NOT NULL | 'none' | none / partial / full / cancelled |
| shipment_lines | billed_qty | decimal(18,4) NOT NULL | 0 | 已开票数量 |
| sales_orders | billing_status | varchar(16) NOT NULL | 'none' | none / partial / full |
| sales_orders | billing_derived_at | datetime NULL | NULL | 派生时间 |

---

## 4. 迁移 `meta/migrations/v231__customer_invoice.py`

> 编号说明：本 worktree 当前最大 v230，故用 v231。`doc-flow-worktree` 有未合并的 v231/v232，
> 合并时按实际顺序重排（迁移内容不变）。结构镜像 `v177__purchase_order_object.py`（建表/类型/序列/权限/verify）。

执行顺序：

1. **建表**（`CREATE TABLE IF NOT EXISTS`）：`customer_invoices`、`customer_invoice_lines`、`customer_invoice_schedules`，含 §3.2 的 CHECK 与全部列。
2. **建索引**：唯一键 + 查询索引（见 §3.1-3.3）。
3. **ALTER 加列**（先查 `PRAGMA table_info` 再用）：§3.4 全部 8 列。
4. **类型种子**（`type_definitions`，先查 code 后插）：
   - 头：`SINV`（标准销售发票，standard）、`SCR`（红字销售发票，credit_memo）、`SDN`（销售借项通知单，debit_memo），`scope_bo=customer_invoice`、`level=header`。
   - 行：`INV_ITEM`（物料行）、`INV_SERVICE`（服务行）、`INV_DISCOUNT`（折扣行），`scope_bo=customer_invoice`、`level=line`、`line_category` 分别 material/service/discount、`delivery_relevant` 1/0/0。
   - **纠偏**：上游 §9 写的行类型 code `ITEM/SERVICE/DISCOUNT` 与全局唯一约束冲突（`type_definitions.code` UNIQUE），统一加 `INV_` 前缀。
5. **编号序列种子**（`number_sequences`）：`SINV` / `SCR` / `SDN`，pattern 均为 `{CODE}-{DATE:yyyymm}-{SEQ:5}`，`date_field=invoice_date`，`start_value=1`，`on_exhaust='error'`；回填 `type_definitions.number_sequence_id`。
6. **回填 `billing_relevance`**：
   ```sql
   UPDATE sales_order_lines SET billing_relevance =
     CASE WHEN billing_method = 'milestone'
            AND EXISTS (SELECT 1 FROM sales_order_schedules s
                        WHERE s.order_line_id = sales_order_lines.id
                          AND s.schedule_kind = 'billing')
          THEN 'plan' ELSE 'delivery' END;
   ```
7. **doc_flow 规则种子**（`doc_flow_rule`，先查后插）：`shipment_to_customer_invoice`，`source_bo=shipment_line`、`target_bo=customer_invoice_line`、`source_qty_field=qty`、`pool=billing`。
8. **权限种子**（`permissions`，双段式，grant 到 admin/default）：
   `customer_invoice:customer_invoice_view` / `_create` / `_post` / `_reverse` / `_cancel`。
9. **不写** `settlement_block_code`（D28）、不建会计事件表（D6）。

`verify()` 检查项：

- 三表存在；8 个派生列存在；唯一索引存在。
- `SINV/SCR/SDN/INV_ITEM/INV_SERVICE/INV_DISCOUNT` 存在且 `scope_bo=customer_invoice`；三个序列已绑定。
- `doc_flow_rule` 有 `shipment_to_customer_invoice`。
- `billing_relevance` 只含 delivery/plan；`plan` 行至少有一条 billing 计划行；非法值计数为 0。
- 所有 `billed_qty` / `billed_amount` 初始为 0，`billing_status='none'` 之外的值计数为 0。
- 权限 5 条存在且已授权 admin/default。
- **直接查 DB 验证**（不信 `print`），失败抛错并返回 `ok=False`。

---

## 5. 服务 `meta/services/customer_invoice_service.py`

### 5.1 骨架（镜像 shipment_service）

- 常量：表名、状态、来源类型、规则码。
- `CustomerInvoiceError(ValueError)` 携带 `field_name` / `rule`。
- `_now()` / `_to_decimal()` / `_round(value, places)` / `_blank()` / `_atomic(ds)`。
- 构造：`def __init__(self, data_source, platform_data_source=None)`。
- 覆写点：`_load_*` / `_write_*` 便于测试注入。
- 事务：`post` / `reverse` / `submit` / `cancel` 用 `_atomic(self.ds)`；取号在事务外。

### 5.2 方法清单

| 方法 | 签名 | 行为 |
|---|---|---|
| create_from_shipment | `(payload) -> dict` | 校验发货状态→逐行算可用量→建头+行→回算汇总→返回 id/invoice_no/status |
| create_manual | `(payload) -> dict` | 手工建单（order_line 或 manual 行），同样走行校验 |
| recalc | `(invoice_id) -> dict` | 重算行净/税/毛与头汇总；仅 draft/submitted |
| submit | `(invoice_id) -> dict` | draft→submitted；校验至少 1 行、来源可用 |
| post | `(invoice_id) -> dict` | submitted→posted；原子完成 §5.4 八步 |
| cancel | `(invoice_id) -> dict` | draft/submitted→cancelled |
| reverse | `(invoice_id, reason) -> dict` | posted→reversed + 生成红字发票；§5.5 |
| prepare_header | `(payload, *, for_reversal=False) -> dict` | 守卫用：补默认值、取号、状态= draft |
| validate_line_write | `(payload, existing=None, invoice=None) -> dict` | 守卫用：XOR/来源/可用量/金额重算 |
| recompute_order_billing | `(order_id) -> dict` | 重算订单与订单行 billing_status |

### 5.3 建单规则

`create_from_shipment`：

1. 载入 `shipments`：状态必须是 `shipped` / `delivered`；`reversed` / `cancelled` / 之前状态 → `INVOICE_SHIPMENT_STATE_INVALID`。
2. 行缺省 = 该发货单未取消行中 `qty - billed_qty > 0` 的行。
3. 每行：
   - `shipment_line.schedule_id → sales_order_schedule(order_line_id) → sales_order_line`。
   - `billing_relevance` 必须为 `delivery`：
     - `plan` → `INVOICE_RELEVANCE_NOT_SUPPORTED`
     - 其他/空 → `INVOICE_SOURCE_MISMATCH`
   - 可用量 = `shipment_line.qty - COALESCE(billed_qty,0)`；请求量（缺省=可用量）必须 `> 0` 且 `<= 可用量`，否则 `INVOICE_QTY_EXCEEDED`。
   - 金额：`net = ROUND(qty × order_line.unit_price, 4)`；`tax = ROUND(net × tax_rate/100, 4)`；`gross = net + tax`；`unit_price = order_line.unit_price`；`price_source='order'`。
   - 行类型默认 `INV_ITEM`；`description = order_line.description or ('物料#%s' % item_id)`；`uom_id` 取订单行。
4. 头快照：`customer_account_id` / `bill_to_account_id` / `payer_account_id` / `bill_to_address_text` / `currency_id` / `exchange_rate*` / `payment_term_id` / `incoterm_code` / `org_id` / `sales_org_id` / `project_id` 全部取自订单。
5. 取号：`DocumentNumberService(self.ds).allocate_for('customer_invoice', payload, required=True)`（事务外）。
6. 事务内写头（status=draft）→ 写行（line_no=1..N）→ `recalc`。
7. 不写 doc_flow、不回写 billed、不生成期次。

`create_manual`：

- 头必填：`customer_account_id`、`currency_id`、`invoice_date`、`org_id`。
- 行来源三选一：
  - `shipment_line_id` → 按 delivery 规则（同上）。
  - `order_line_id` → 校验 `billing_relevance='delivery'`；可用量 = `order_line.qty - billed_qty`；单价取订单行。
  - 全空 → `source_doc_type='manual'`、`billing_basis=amount`、`qty=1`、`unit_price=payload.net_amount`、`tax_rate_percent` 必填、`price_source='manual'`。
- `schedule_id` / `source_doc_type='billing_schedule'` → `INVOICE_RELEVANCE_NOT_SUPPORTED`（Wave B）。

### 5.4 `post` 原子步骤

1. 载入头，状态必须 `submitted`，否则 `INVOICE_STATE_INVALID`。
2. 明细校验：至少 1 行；逐行 R-INV-3；来源未红冲（发货单非 reversed）；R-INV-4 可用量；R-INV-9 编号唯一。
3. 汇总校验：`header.net/tax/gross == Σ line`（差额 > 0.0001 → `INVOICE_AMOUNT_MISMATCH`，R-INV-7）。
4. 生成期次（R-INV-21/24/26）：
   - 无 `payment_term_id` 或付款条件无行 → 1 期：ratio 100、due=invoice_date、amount=gross。
   - 有付款条件：读 `payment_terms(basis_date_rule, cutoff_day)` + `payment_term_lines(seq, percentage, offset_months, fixed_day_of_month, offset_days)`；
     - `base = payment_term_schedule_service.resolve_base_date(term, invoice_date)`
     - `due_i = compute_due_date(base, term_line)`
     - 前 N-1 期 `amount_i = ROUND(gross × ratio_i / 100, 4)`；最后一期 `= gross - Σ`（尾差归最后一期，R-INV-26）。
     - 逐期顺延合并：`amount <= 0` 的期次并入下一期；若最后仍有剩余则并入上一期。
     - 任一期 `due_date < invoice_date` → `INVOICE_TERM_INVALID`。
     - 断言 `Σ amount == gross`，否则抛 `INVOICE_AMOUNT_MISMATCH`。
   - 红字单（`reversal_of_invoice_id` 非空）跳过此步（R-INV-24）。
5. 回写 billed（R-INV-16，缺一即回滚整单）：
   ```sql
   UPDATE shipment_lines
      SET billed_qty = ROUND(COALESCE(billed_qty,0) + ?, 4)
    WHERE id = ?
      AND ROUND(COALESCE(billed_qty,0) + ?, 4) <= ROUND(qty, 4);
   -- rowcount != 1 -> INVOICE_QTY_EXCEEDED
   UPDATE sales_order_lines
      SET billed_qty = ROUND(COALESCE(billed_qty,0) + ?, 4),
          billed_amount = ROUND(COALESCE(billed_amount,0) + ?, 4)
    WHERE id = ?
      AND ROUND(COALESCE(billed_qty,0) + ?, 4) <= ROUND(qty, 4);
   -- rowcount != 1 -> INVOICE_QTY_EXCEEDED
   ```
6. 写 doc_flow 边：按发货单分组，逐 `shipment_line_id → invoice_line_id` 调
   `meta.core.doc_flow_attach.attach_edge(ds, platform_ds, 'shipment_to_customer_invoice', shipment_line_id, invoice_line_id, qty, target_item=str(invoice_line_id), unit=str(uom_id), derived_by='customer_invoice_service')`；失败只告警不阻断（与 shipment 一致）。
7. 状态更新：`posting_date = payload or invoice_date`；`status='posted'`；`updated_at`。
8. 事务提交后：`recompute_order_billing(order_id)` 重算受影响订单；`_emit_accounting_event_hook(invoice)` 空实现（D6）。

### 5.5 `reverse` 规则

1. 仅 `posted` 可红冲；`reversal_reason` 必填；同一原单已有红字单 → `INVOICE_REVERSE_EXISTS`。
2. R-INV-23：查 `payment_allocations`（表不存在视为 0）；若有 `status='active'` 且 `amount > 0` 的核销 → `INVOICE_ALLOCATION_EXISTS`。
3. 事务内：
   - 建红字头：复制原头，`reversal_of_invoice_id=原 id`，`document_type_id` 取 `SCR`，`invoice_date=today`，`posting_date=max(today, 原 posting_date)`（R-INV-14），金额取负，`status=draft`。
   - 建红字行：复制原行，`qty/net/tax/gross` 取负，`billing_basis='quantity'`，`original_invoice_line_id=原行 id`，保留来源键。
   - 红字单直接置 `submitted` → 走 §5.4 第 4 步跳过期次、第 5 步反向回写：
     ```sql
     UPDATE shipment_lines SET billed_qty = ROUND(COALESCE(billed_qty,0) - ?, 4)
      WHERE id = ? AND ROUND(COALESCE(billed_qty,0) - ?, 4) >= 0;
     ```
   - 原期次全部置 `status='cancelled'`，`amount_applied` 不变。
   - 原单 `status='reversed'`；红字单 `status='posted'`。
4. 事务后 `recompute_order_billing`。

### 5.6 派生 `billing_status`

- 订单行：`billed_qty >= qty` → `full`；`> 0` → `partial`；否则 `none`。
- 订单：所有行 `full` → `full`；任一行 `> 0` → `partial`；否则 `none`；同时更新 `billing_derived_at`。
- 计划行派生（Wave B）本波不写，保持 `none`。

### 5.7 错误码

`INVOICE_SHIPMENT_STATE_INVALID` / `INVOICE_RELEVANCE_NOT_SUPPORTED` / `INVOICE_SOURCE_MISMATCH` / `INVOICE_QTY_EXCEEDED` / `INVOICE_LINE_XOR` / `INVOICE_AMOUNT_MISMATCH` / `INVOICE_STATE_INVALID` / `INVOICE_POSTED_READONLY` / `INVOICE_DELETE_FORBIDDEN` / `INVOICE_SCHEDULE_IMMUTABLE` / `INVOICE_ALLOCATION_EXISTS` / `INVOICE_REVERSE_EXISTS` / `INVOICE_TERM_INVALID` / `INVOICE_POSTING_DATE_INVALID` / `INVOICE_NUMBER_UNAVAILABLE`。

---

## 6. 守卫 `meta/core/interceptors/customer_invoice_guard_interceptor.py`

优先级 `51`（与 shipment 同批，对象不同互不冲突）；`should_execute` 覆盖
`customer_invoice` / `customer_invoice_line` / `customer_invoice_schedule` 的 create/update/delete。

| 对象 | 动作 | 行为 |
|---|---|---|
| header | create | `prepare_header` 补默认类型（SINV）、取号、status=draft、金额 0；任何非 draft 的显式状态拒绝 |
| header | update | 当前 `posted`/`reversed`/`cancelled` → 除状态迁移外全字段拒绝（`INVOICE_POSTED_READONLY`）；`submitted` 冻结 §3.1 readonly 列表；状态迁移委托：submitted→`submit`，posted→`post`，cancelled→`cancel`，reversed→`reverse` |
| header | delete | 仅 draft 可删，否则 `INVOICE_DELETE_FORBIDDEN` |
| line | create/update | 调 `validate_line_write`：XOR、来源类型、relevance、可用量（排除本行）、金额重算；父单非 draft → 拒绝 |
| line | delete | 父单仅 draft 可删行 |
| schedule | create/update/delete | 一律 `INVOICE_SCHEDULE_IMMUTABLE`（R-INV-22） |

注册（两处都要）：

- `meta/server.py`：import + `register_interceptor(CustomerInvoiceGuardInterceptor())`
- `meta/core/app_builder.py`：import + 注册到链

---

## 7. 工具与文档

- `meta/tools/check_billing_relevance_consistency.py`：
  执行 §20.4 两条 SQL（plan 行无 billing 计划、delivery 行无 delivery 计划），打印违规行，返回退出码 0/1。
- 不改上游 spec（`s7-worktree` 只读）。
- 不新增前端页面。

---

## 8. 测试矩阵

### 8.1 `meta/tests/test_customer_invoice_service.py`（>=14）

夹具：in-memory sqlite + `_MemDS(query/execute)`；建表和种子镜像 v231；预置客户、币种、税码、订单（delivery 行）、发货单（staged→shipped）。

1. `create_from_shipment` happy：头/行快照、行号、金额、币种、客户。
2. 拒绝 draft/staged 发货单。
3. 拒绝 reversed 发货单。
4. `plan` relevance → `INVOICE_RELEVANCE_NOT_SUPPORTED`。
5. `none`/缺 relevance → `INVOICE_SOURCE_MISMATCH`。
6. 超可开数量 → `INVOICE_QTY_EXCEEDED`。
7. 部分开票：第一次 40/100 过账后可用 60；第二次 60 成功。
8. 第二次 61 失败且 billed 不变。
9. 无付款条件 → 1 期，due=invoice_date，amount=gross。
10. 有付款条件 30/60/10，gross=1000.01 → 300.00 / 600.01 / 100.00（尾差）。
11. post 回写 shipment_line.billed_qty、order_line.billed_qty/billed_amount、订单 billing_status=partial。
12. 重复 post → `INVOICE_STATE_INVALID`。
13. cancel：draft/submitted 可；posted 拒绝。
14. reverse：红字单 posted、金额为负、无期次、原单 reversed、原期次 cancelled、billed 归零、订单 billing_status 回到 none。
15. reverse 时存在 active 核销 → `INVOICE_ALLOCATION_EXISTS`。
16. 头汇总与行不一致 → `INVOICE_AMOUNT_MISMATCH` 且事务回滚（status 仍 submitted）。

### 8.2 `meta/tests/test_customer_invoice_schedule.py`（>=6）

1. 无付款条件：1 期 100%。
2. 30/60/10：到期日按 offset_days。
3. 尾差：gross=0.01 → 三期合并为有效正额且 Σ=gross。
4. 比例合计 90：最后一期吸收差额（amount > 比例金额）。
5. 比例合计 110：最后一期为负 → 并入上一期，Σ=gross。
6. 到期日早于 invoice_date → `INVOICE_TERM_INVALID`。
7. 红字单不生成期次。
（>=6 即通过，允许合并用例。）

### 8.3 `meta/tests/test_customer_invoice_guard.py`（>=8）

1. posted 头更新业务字段被拒。
2. posted 头删除被拒。
3. submitted 头改 invoice_no 被拒。
4. 状态迁移到 posted 委托 service.post。
5. 行 XOR（同时带 shipment_line_id + order_line_id）被拒。
6. 行 relevance=plan 被拒。
7. 行金额被服务重算（篡改 unit_price 不生效/被覆盖）。
8. schedule 任意写被拒。
9. draft 头可删除，级联删行。
10. 手工行缺 tax_rate → 拒绝。

### 8.4 `meta/tests/test_migration_v231.py`（>=4）

1. 三表 + 索引创建成功。
2. 8 个派生列存在且默认值正确。
3. 类型/序列/规则/权限种子存在并已绑定。
4. 回填：milestone + billing 计划 → plan；其余 → delivery；verify 通过。
5. 幂等：`upgrade` 二次执行不报错、无重复种子。

### 8.5 回归

- `meta/tests/test_shipment_service.py`
- `meta/tests/test_sales_order_service.py`（或实际文件名）
- `meta/tests/test_payment_term_schedule.py`
- `meta/tests/test_payment_term_guard.py`

---

## 9. 验证命令与通过标准

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_shipment_service.py --port 3012
```

通过标准：上述命令全部 `passed`；禁止 `pytest`；失败用 `--single` 定位后重跑。
全部通过后在 **s8 worktree** `git add` + `git commit`（不碰主工作树、不碰 s7-worktree）。

---

## 10. 风险与回滚

| 风险 | 处理 |
|---|---|
| v231 与 doc-flow-worktree 的 v231/v232 合并冲突 | 合并时按主树实际顺序重排文件名与 `MIGRATION_NAME`，内容不变；本波不改他人迁移 |
| 期次比例合计非 100 | 尾差归最后一期，不报错；到期日异常才报 `INVOICE_TERM_INVALID` |
| 回写 billed 并发超量 | 条件 UPDATE + rowcount 校验，失败整单回滚（R-INV-16） |
| doc_flow 表/规则缺失 | attach 失败仅告警，不阻断过账（与 shipment 一致） |
| AR 核销表不存在 | 视为 0 条核销，允许红冲（D14/D19 未定稿的隔离） |
| 回滚方式 | 本波仅新增表/列/服务/测试，不改既有表结构；回滚 = 撤销 commit + 不执行 v231 |

---

## 11. 需批准项（Approval Checklist）

- [ ] 范围：仅后端 Wave A（对象/schema/迁移/服务/守卫/测试），不做 UI 页面。
- [ ] 迁移号用 **v231**（已知与 doc-flow-worktree 未合并编号冲突，合并期重排）。
- [ ] 行类型 code 用 `INV_ITEM` / `INV_SERVICE` / `INV_DISCOUNT`（修正上游 §9 的全局唯一冲突）。
- [ ] 计划开票 fail-closed（`plan` 一律拒绝），严格期次只读（D27），不建 `settlement_block_code`（D28）。
- [ ] 允许开始编码（S8-A1..A9）。

---

## 12. 语义校准与后续修复（2026-11-09，Fusion 26D 对标）

> 依据：`docs/specs/research-fusion-billing-deep-dive-2026-11-09.md`。
> 本节只校准语义与补齐 P0 缺口，不改变 Wave A 的业务范围。

### 12.1 术语正名

| 我方术语 | Fusion 对应 | 说明 |
|---|---|---|
| `cancelled`（draft/submitted → cancelled） | Void | 仅未过账、无活动可作废 |
| 红字发票（`SCR`，负数量负金额） | Credit Memo | 我方「红冲」= 贷记，不是取消 |
| `reversed`（原单终态） | 无直接对应 | 本地扩展，表示「已被贷记」 |
| `document_category=debit_memo` | Debit Memo | 与发票无链接，本期不开放业务 |

### 12.2 已执行修复（P0）

1. **单据类别**：`customer_invoices` 新增 `document_category`（v232），
   由 `type_definitions.document_category` 派生，生成后不可改；
   `standard→invoice` / `credit_memo→credit_memo` / `debit_memo→debit_memo`。
2. **红冲原因**：`reverse` 规则声明 `ui_hints.input_fields`，
   通用状态按钮弹窗收集 `reversal_reason` 后随 PUT 提交。
3. **发货行 XOR**：`validate_line_write` 不再拒绝
   `shipment_line_id + 冗余 order_line_id`（与 v231 CHECK 一致）；
   仅 `schedule_id` 与其余来源互斥。

### 12.3 仍未覆盖（后续波次）

- 行级贷项 / 部分冲销 / on-account credit（Fusion Credit Memo 能力）
- Adjustment 对象与限额审批
- 借项通知单业务（Fusion 口径：不强制引用原单）
- 价格变更（D13）：需补 `price_diff_amount` 与「改价原因必填」；
  开票后价格更正按 Credit and Rebill 处理
- Complete 前审批闸门、打印权限、`create_from_shipment` 的 UI 入口

---

## 13. B2 发货开票入口（BO Action + 详情页按钮 + 权限）

> 目标：让「发货单 → 草稿销售发票」可由真实用户触发，不再只能靠代码。
> **决策：入口放发货单详情页标题栏，不做列表行内按钮。**
> 依据（已核实）：`src/views/GenericObjectList.vue` + `MetaListPage` 的行操作只派发
> `detail/view/edit/delete` 等 CRUD 语义，没有业务 Action 派发通道；
> 而 `src/components/common/DetailPage/DetailPage.vue` 的 `computedActions`
> 已从 `ui_view_config.detail.actions` 装配按钮，是最小改动点。

### 13.1 后端 Action

**新建 `meta/services/customer_invoice_actions.py`**（镜像 `receipt_actions.py` 结构）：

- `_ok(data, message)` / `_fail(message, code)` / `_blank(value)` / `_set_user_context()`
  （`_set_user_context` 直接复用 `receipt_actions.py` 的实现口径：写 `bo_framework.set_user_context`）。
- `_service()`：
  ```python
  from meta.core.datasource import get_data_source
  from meta.core.db_path import get_meta_db_path
  return CustomerInvoiceService(
      get_data_source('sqlite', database=get_meta_db_path()))
  ```
- `create_from_shipment_handler(params, context=None) -> dict`：
  1. `_set_user_context()`
  2. `shipment_id = params.get('shipment_id') or params.get('source_doc_id')`；
     空 → `_fail('缺少 shipment_id（发货单 id）', 'INVALID_ARGUMENT')`
  3. 白名单透传：`invoice_date / posting_date / document_type_id /
     payment_term_id / incoterm_code / remark / lines`（`_blank` 的跳过）；
     未给 `invoice_date` 时默认当天（详情页按钮不弹日期）。
  4. `data = _service().create_from_shipment(payload)`
  5. `CustomerInvoiceError` → `_fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')`
  6. 成功 → `_ok(data, '已生成销售发票 %s（草稿）' % data.get('invoice_no', ''))`
- 事务：服务层 `create_from_shipment` 内部已有 `_atomic(self.ds)`，
  Action 不再自行包事务（与收货 action 的「action 控事务」不同，避免嵌套）。

**编辑 `meta/services/bo_action_registrations.py`**：

```python
from meta.services.customer_invoice_actions import create_from_shipment_handler
...
registry.register(
    'customer_invoice.create_from_shipment',
    create_from_shipment_handler,
    description='由已发运/已签收发货单生成草稿销售发票（可按行部分开票）',
    object_type='customer_invoice',
    category='business',
    permission_required='customer_invoice:customer_invoice_create',
    input_schema={
        'type': 'object',
        'properties': {
            'shipment_id': {'type': 'integer'},
            'invoice_date': {'type': 'string'},
            'posting_date': {'type': 'string'},
            'document_type_id': {'type': 'integer'},
            'payment_term_id': {'type': 'integer'},
            'remark': {'type': 'string'},
            'lines': {'type': 'array', 'items': {'type': 'object'}},
        },
    },
    output_schema={
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'invoice_no': {'type': 'string'},
            'status': {'type': 'string'},
        },
    },
    requires_auth=True,
    idempotent=False,
)
```

### 13.2 schema 声明（发货单）

`meta/schemas/shipment.yaml` → `ui_view_config.detail` 下新增 `actions`（仅业务动作）：

```yaml
  detail:
    actions:
      - id: create_invoice
        label: 生成销售发票
        icon: plus
        variant: secondary
        permission: customer_invoice:customer_invoice_create
        action: customer_invoice.create_from_shipment
```

### 13.3 前端派发（DetailPage）

`src/components/common/DetailPage/DetailPage.vue`（`authStore` 与 `ElMessage` 已在该文件引用）：

1. `computedActions` 拆分 YAML 动作：
   - **业务动作** = 含 `action` 字段的条目；先按 `a.permission` 用
     `authStore.hasPermission(a.permission)` 过滤。
   - **声明式动作** = 其余（edit/delete/...），保持现有「YAML 非空即替换默认按钮」语义。
   - 合并规则：
     - `yamlActions` 为空 → 维持现有默认集（edit/save/cancel/delete）。
     - `yamlActions` 全为业务动作 → 默认集为底，追加业务动作。
     - `yamlActions` 含声明式动作 → 现有替换逻辑，末尾追加业务动作（行为向后兼容）。
2. 新增 `runBusinessAction(action)`：
   ```js
   await ElMessageBox.confirm('将从该发货单生成草稿销售发票，是否继续？', '生成销售发票')
   const result = await useBoAction().call(action.action, {
     source_doc_id: props.id, ...(action.params || {})
   })
   result.success ? ElMessage.success(result.message) : ElMessage.error(result.message)
   ```
   成功后调用现有 `handleRefresh()` 刷新详情。
3. `handleObjectPageAction` 的 `default:` 分支：
   `if (action.action) await runBusinessAction(action)`；其余分支不变。
4. 状态门槛：前端**不判断**发货状态，统一由后端
   `INVOICE_SHIPMENT_STATE_INVALID` 拒绝并回显，避免双份口径漂移。

### 13.4 权限口径

| 层 | 机制 | 状态 |
|---|---|---|
| 后端 | `bo_action_registry.call` 校验 `permission_required`（`'*'` 放行） | 已存在 |
| 前端 | 按钮声明 `permission`，`authStore.hasPermission` 过滤 | 本次新增 |
| 数据 | v231 已创建并授予 admin/default `customer_invoice:customer_invoice_create` | 无需新迁移 |

### 13.5 明确不做

- 列表行内「生成发票」按钮（通用列表无业务 action 派发通道，避免改通用列表）。
- 生成后自动跳转发票详情（只回显单号，用户自行进入发票列表）。
- 行选择弹窗（默认全部可开票行；部分开票走 Action 的 `lines` 参数，留给后续波次）。

### 13.6 测试与验收

新增 `meta/tests/test_customer_invoice_actions.py`（3 用例，夹具复用
`meta/tests/factories/_customer_invoice_helpers.py`，`monkeypatch.setattr`
把 `customer_invoice_actions._service` 指向测试连接）：

1. 已发运发货单 + 2 行 → 返回 `id/invoice_no/status=draft`，库内
   `document_category=invoice`、行数与金额汇总正确。
2. 缺 `shipment_id` → `success=False, code=INVALID_ARGUMENT`，库内无新增。
3. 发货单状态 `draft` → `success=False, code=INVOICE_SHIPMENT_STATE_INVALID`，库内无新增。

注册契约：`register_all_bo_actions(registry)` 后断言
`registry.get('customer_invoice.create_from_shipment')` 的
`object_type='customer_invoice'`、`permission_required='customer_invoice:customer_invoice_create'`。

验收命令：

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_bo_action_contract.py --port 3012
```

前端：`npm run build`（worktree 内）通过；不做 E2E。

### 13.7 需批准项

- [ ] 入口放发货单详情页标题栏（非列表行内）。
- [ ] 默认全量开票（不做行选择 UI）。
- [ ] 允许开始实现 T9-T11。

---

## 14. B3 价格变更（D13，Fusion「Credit and Rebill」口径）

> 决策：**草稿行允许覆盖订单单价，但必须填写改价原因**；差额派生到
> `price_diff_amount`；开票后的价格更正不在本波（按 Fusion 走红冲 + 重开）。

### 14.1 数据

- `v231` `LINE_DDL` 增加 `price_diff_amount NUMERIC(18,4) NOT NULL DEFAULT 0`（新库）。
- 新迁移 `v233__customer_invoice_line_price_diff.py`：
  - 既有库 `ALTER TABLE customer_invoice_lines ADD COLUMN`；
  - 回填 `ROUND((unit_price - COALESCE(order_unit_price, unit_price)) × qty, 4)`；
  - `verify` 校验列存在、无 NULL、与公式一致；`rollback` DROP COLUMN。
- `meta/schemas/customer_invoice_line.yaml` 新增 `price_diff_amount`
  （`derived: true`，`ui.editable: false`）。

### 14.2 服务规则

`validate_line_write` → 新增 `_apply_price_override`：

- 参考价一律取 `order_unit_price`（订单行单价快照）；手工行（为空）不约束，差额恒 0。
- 覆盖价 = 入参 `unit_price`；未提交时沿用行上现值与原因（只改数量不清原因）。
- 差额 `= (unit_price - order_unit_price) × qty`，ROUND 4 位，由 `_finalize_line` 派生。
- 有差额且 `price_change_reason` 为空 → `INVOICE_PRICE_REASON_REQUIRED`。
- 有差额 → `price_source='manual'`，保留 `price_change_reason/approved_by`；
  无差额 → `price_source='order'`，原因与审批人清空。
- 红字行 `_negate_line` 同步取负 `price_diff_amount`。
- 守卫 `_LINE_NORMALIZED_KEYS` 增加 `price_diff_amount`（确保写回）。

### 14.3 明确不做

- 开票后改价（posted 行只读；Fusion 口径为 Credit and Rebill）。
- 改价审批流（只保留 `price_change_approved_by` 字段，不接审批引擎）。
- 跨币种差额换算（差额与单价同币种）。

### 14.4 测试与验收

- 新增 `meta/tests/test_migration_v233.py`（3 用例：加列回填 / 幂等 / 回滚）。
- `test_customer_invoice_service.py` 新增 2 用例：
  1. 改价缺原因 → `INVOICE_PRICE_REASON_REQUIRED`；补原因后差额 = 80、`price_source=manual`；
  2. 已改价行只改数量 → 保留覆盖价与原因，差额按新数量重算。
- 回归：`test_customer_invoice_guard.py`、`test_customer_invoice_schedule.py`、
  `test_migration_v231.py`、`test_migration_v232.py`、`test_schema_api.py`。

---

## 15. B4 行类型行为（SERVICE 空 item / DISCOUNT 负金额）

> 决策：行类型由 `line_type_id → type_definitions.line_category` 解析；
> 服务行允许空物料，物料行（非手工）必须关联物料；只有折扣行允许负金额。

### 15.1 规则

`_finalize_line` → `_apply_line_type_rules`（发货 / 订单 / 手工行统一经过）：

| line_category | item_id | 金额方向 | 说明 |
|---|---|---|---|
| material | 发货 / 订单来源必填；手工行可空 | net ≥ 0 | 空 item 抛 `INVOICE_LINE_ITEM_REQUIRED` |
| service | 可空 | net ≥ 0 | `description` 必填（沿用既有校验） |
| discount | 可空 | net < 0 | 非负抛 `INVOICE_LINE_AMOUNT_INVALID` |

- `line_type_id` 为空 → 默认 `INV_ITEM`（material）。
- `line_type_id` 必须属于 `scope_bo='customer_invoice'` 且 `level='line'`，
  否则 `INVOICE_LINE_TYPE_INVALID`。
- 非折扣行净额为负 → `INVOICE_LINE_AMOUNT_INVALID`。
- 红字行（`original_invoice_line_id` 非空）跳过金额方向校验；物料 / 服务约束
  沿用原行（原行写入时已校验）。

### 15.2 明确不做

- 不新增行类型（沿用 v231 的 `INV_ITEM / INV_SERVICE / INV_DISCOUNT`）。
- 折扣行不做自动分摊 / 反算（由用户直接给负净额）。
- 不做行类型与订单行类型的联动校验（手工行自由选择）。

### 15.3 测试与验收

- `test_customer_invoice_service.py` 新增 6 用例：
  1. 服务行空 item 建单成功；
  2. 订单行来源物料行空 item → `INVOICE_LINE_ITEM_REQUIRED`；
  3. 折扣行负金额成功（net=-50 / gross=-56.5）；
  4. 折扣行非负金额 → `INVOICE_LINE_AMOUNT_INVALID`；
  5. 非折扣行负金额 → `INVOICE_LINE_AMOUNT_INVALID`；
  6. 头类型当作行类型 → `INVOICE_LINE_TYPE_INVALID`。
- 回归：guard / schedule / v231 / v232 / v233 / schema_api / actions。

---

## 16. B5 独立贷项入口（Credit Memo）

> 决策：贷项不再只依赖「红冲」状态按钮；已过账发票详情页提供「创建贷项」，
> 生成引用原单的贷项草稿，后续走 submit / post 正常状态机。

### 16.1 接口

BO Action：`customer_invoice.create_credit_from_invoice`

| 参数 | 必填 | 说明 |
|---|---|---|
| source_invoice_id / source_doc_id | 是 | 原发票 id |
| invoice_date | 否 | 贷项日期，默认当天；不得早于原过账日 |
| line_ids | 否 | 原发票行 id 子集；缺省复制全部行（整行取负） |
| reason | 否 | 贷项原因，默认「独立贷项」，写入 reversal_reason |
| remark | 否 | 备注 |

前端入口：`customer_invoice.yaml` detail.actions「创建贷项」
（权限 `customer_invoice:customer_invoice_create`）。

### 16.2 服务规则

- 原发票必须 `posted`，否则 `INVOICE_STATE_INVALID`。
- 同一原发票已有非 cancelled 的引用单（贷项或红字）→ `INVOICE_CREDIT_EXISTS`。
- 原发票存在未取消的核销 → 沿用 `_assert_no_active_allocation`。
- 贷项日期 < 原过账日期 → `INVOICE_POSTING_DATE_INVALID`。
- 行：默认全部行；`line_ids` 必须是原单行子集，否则 `INVOICE_SOURCE_MISMATCH`。
- 头：类型 `SCR`（document_category=credit_memo）、`reversal_of_invoice_id`=原单、
  `reversal_reason`=reason、status=draft、金额由负行汇总。
- 草稿阶段不改原单状态、不回写 billed、不生成期次。
- 过账：`post` 对红字 / 贷项单跳过可用量校验，`_apply_billed(sign=-1)` 扣减进度，
  不生成收款期次。

### 16.3 明确不做

- 不支持部分数量贷项（`line_ids` 只能整行取负）；Wave B 再做按数量 / 金额拆分。
- 不支持一张原单多张并存贷项（未核销前）。

### 16.4 测试与验收

- service 6 用例：负行复制 / 原单须已过账 / 重复贷项 / 日期早于过账 /
  按行选择 / 贷项过账回滚进度。
- action 3 用例：建单成功 / 缺原单 id / 注册契约。
- 回归：guard / schedule / v231 / v232 / v233 / schema_api。

---

## 17. B6 权限补齐与菜单分组

> 决策：补 print 与独立 credit_memo 权限；贷项按钮改挂独立权限；
> 发票菜单在存在「应收」父菜单时自动归组，否则保持顶层（不阻断）。

### 17.1 权限

| code | 用途 | 挂载点 |
|---|---|---|
| customer_invoice:customer_invoice_print | 打印发票详情 | detail.actions「打印」 |
| customer_invoice:customer_invoice_credit_memo | 创建贷项 | B5 action + detail.actions「创建贷项」 |

- v231 权限种子扩到 7 个动作（新库开箱可用）。
- v234 迁移为旧库补写并授予 admin / default；幂等。

### 17.2 菜单分组

- 菜单仍由 `menu_auto_generator` 生成；v234 在 `menus` 存在名称含「应收」的
  父菜单时，把 `customer_invoice-list` 挂到其下（sort_order=50）。
- 无父菜单（当前环境）保持顶层，迁移不阻断、verify 不强制。

### 17.3 打印

- DetailPage 新增 `case 'print'`：调用浏览器 `window.print()` 打印当前详情页。
- 列表页 print 不在本期（列表导出已有 export）。

### 17.4 测试与验收

- v234 3 用例：补权限 + 挂菜单 / 无父菜单保持顶层 / 幂等 + 回滚。
- v231 权限断言更新为 7 权限、14 授权。
- action 契约：credit_memo 权限断言更新。
- 回归：schema_api / actions / service / guard / schedule / v231-v233。

---

## 18. B7 doc_flow 反向边（贷项 / 红字引用原发票行）

> 问题：`doc_flow_attach.attach_edge` 对 `qty <= 0` 直接返回 False，
> 贷项 / 红字负行过账写不出任何转单事实边；`reverse()` 亦未写边。
> 决策：新增反向引用规则，按「原发票行 → 贷项 / 红字行」写正数量事实边。

### 18.1 规则 `customer_invoice_to_credit_memo`

| 字段 | 值 |
|---|---|
| rule_id | customer_invoice_to_credit_memo |
| source_bo | customer_invoice_line |
| target_bo | customer_invoice_line |
| source_qty_field | qty |
| pool | billing |

- v235 迁移幂等 upsert（同 v231 `_do_rule` 口径）；verify 要求规则存在且 active；
  rollback 删除规则。
- Σ 校验：源行 = 原发票行，pool=billing；贷项整行取负时 consumed == source_qty。

### 18.2 服务改动

- `_write_doc_flow_edges`：行存在 `original_invoice_line_id`（红字 / 贷项）时，
  写 source=原行 id、target=当前行 id 的引用边，数量 / 金额取 `abs()`，
  rule_id=新规则，然后 `continue`；否则维持发货行边逻辑。
- `reverse()`：红字头 / 行插入并更新状态、重算订单开票状态后，
  调用 `_write_doc_flow_edges(red_header, red_lines)` 补写引用边。
- 贷项草稿过账（B5）走 `post()` 同一路径，自动写引用边。

### 18.3 边界

- 不补偿原「发货行 → 原发票行」正向边（冲销补偿属后续批次）。
- 红字 / 贷项行虽复制 `shipment_line_id`，但走引用边分支，不重复写发货边。
- 边写入失败仅告警，不阻断过账 / 红冲（与 `attach_edge` 既有降级口径一致）。

### 18.4 测试与验收

- v235 3 用例：插规则 / 幂等 / 回滚。
- service 2 用例（monkeypatch `meta.core.doc_flow_attach.attach_edge` 捕获参数）：
  - 贷项过账：rule_id / source=原行 id / target=贷项行 id / qty>0 / amount>0；
  - 红冲：红字行同样写引用边且 source=原行 id。
- 回归：service / actions / guard / schedule / v231-v235 / schema_api。

---

## 19. B8 三项决策落地（D19 / D27 / D28）

> 决策口径沿用 §2：D19 分离但可默认、D27 严格只读、D28 不做冻结。

### 19.1 D19 发票日期与过账日期分离

- `invoice_date`：编号日期段与期次到期日的基准，建单必填。
- `posting_date`：过账时可独立传入；为空时取 `invoice_date`；早于 `invoice_date`
  抛 `INVOICE_POSTING_DATE_INVALID`。
- 不引入独立会计期间对象，不做期间关账校验（留给财务期间模块）。

### 19.2 D27 期次受控变更：严格只读

- `customer_invoice_schedule` 的新增 / 修改 / 删除经 action 一律被守卫拒绝，
  规则 `INVOICE_SCHEDULE_IMMUTABLE`（R-INV-22）。
- 期次只在过账时由服务生成；红冲仅由服务内部把原期次置 `cancelled`，
  不开放手工重排期。

### 19.3 D28 容差冻结：不做

- 不引入 `settlement_block_code` 或任何冻结字段。
- 开票金额超过订单行金额不阻断过账（本波无容差校验，留给 AR 侧决策）。

### 19.4 测试与验收

- service 新增 2 用例：
  - `test_post_defaults_posting_date_to_invoice_date`（D19 默认取发票日期）；
  - `test_over_order_amount_does_not_block_posting`（D28 超额不阻断，gross=2260）。
- guard 既有 `INVOICE_SCHEDULE_IMMUTABLE` 用例覆盖 D27。
- 回归：service / guard；v231-v235、actions、schedule、schema_api 维持通过。

