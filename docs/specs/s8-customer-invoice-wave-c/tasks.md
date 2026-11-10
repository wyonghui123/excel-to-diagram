# S8 Wave C 任务清单（开票完备性补齐）

> 关联规格：`spec.md`（同目录）
> 执行顺序：T35 → T36 → T37 → T38 → T39 → T40 → T41 → T42 → T43 → T44 → T45
> 前置：D40-D47 形式确认（spec §3）；D43 建议保持现状，若改则 T39/T40 与 Wave A 用例同步返工
> 约束：只在 `D:\filework\s8-billing-worktree` 改动；禁止在主工作树 commit；禁止 pytest；
> 所有测试走 `python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file <path>`

---

## [x] T35 迁移 v242（5 列 + 权限 + doc_flow 规则 + 索引）

**文件**
- 新增 `meta/migrations/v242__customer_invoice_wave_c.py`
- 新增 `meta/tests/test_migration_v242.py`

**内容**
- `ALTER TABLE sales_order_lines` 加 5 列：`billing_period_count`、`billing_interval_months`、
  `billing_anchor_date`、`billing_lead_days`、`billing_proration`（spec §4.1）。
- 权限 `customer_invoice:customer_invoice_submit`：插入 + 授予 admin/default + 挂
  `customer_invoice-list` 菜单（复用 v239 挂载函数）。
- 播种 doc_flow 规则 `return_shipment_line_to_credit_memo`
  （source `shipment_line` / target `customer_invoice_line` / pool `billing`）。
- 索引 `idx_sol_billing_plan`、`idx_cil_original_line`（先查后建）。
- `verify()`：列、默认值、权限、菜单、规则、索引、枚举合法性；`rollback()` 全量幂等回退。

**验收**
```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file meta/tests/test_migration_v242.py
```
用例 ≥ 4：upgrade 幂等 / verify 通过 / verify 捕获非法 `billing_proration` / rollback 干净。

**提交**
`feat(billing): v242 计划字段、提交权限与退货贷项 doc_flow`

---

## [x] T36 单据动作：submit / post / reverse

**文件**
- 修改 `meta/services/customer_invoice_actions.py`
- 修改 `meta/services/bo_action_registrations.py`
- 修改 `meta/tests/test_customer_invoice_actions.py`

**内容**
- 3 个 handler（spec §6.1）：`submit_handler` / `post_handler` / `reverse_handler`。
- 入参 `{invoice_id}`（兼容 `source_doc_id`）；`reverse` 必填 `reversal_date`、`reason`。
- 幂等语义：submit 已提交返回当前；post 已过账返回当前；reverse 已有红字单返回其 id。
- 注册 3 个 action：`object_type='customer_invoice'`、`category='business'`、`requires_auth=True`；
  权限分别为 `submit`（新增）/`post`/`reverse`。
- 错误统一 `_fail(str(exc), exc.rule)`；不新增旁路写库。

**验收**
- spec §10.1 的 9 条用例全过；action contract 测试（输入 schema、权限、幂等标记）通过。

**提交**
`feat(billing): 销售发票提交/过账/红冲 business action`

---

## [x] T37 计划生成服务

**文件**
- 新增 `meta/services/billing_plan_service.py`
- 新增 `meta/tests/factories/_billing_plan_helpers.py`（如需）
- 新增 `meta/tests/test_billing_plan_service.py`

**内容**
- `generate_for_order(order_id)` / `generate_for_line(order, line)`（spec §6.2）。
- 复用 `payment_term_schedule_service.add_months`；比例 4 位、尾差归末期；按日分摊。
- 每行写入前过 `validate_schedule_write`；幂等（R-INV-23，`billed_amount>0` 永不重算）。
- 里程碑行返回空，不自动生成。

**验收**
- spec §10.2 的 12 条用例全过（均分/固定价/里程碑/锚点/提前滞后/按日/零交集/幂等）。

**提交**
`feat(billing): 开票计划期次自动生成服务`

---

## [x] T38 订单确认触发 + 手工补跑 action

**文件**
- 修改 `meta/core/interceptors/sales_order_guard_interceptor.py`（after-write 钩子）
- 修改 `meta/services/bo_action_registrations.py`
- 新增 `meta/tests/test_billing_plan_trigger.py`

**内容**
- 订单 status → `confirmed` 后调用 `BillingPlanService.generate_for_order`，同事务；失败回滚确认。
- 注册 `sales_order.generate_billing_plan`（`idempotent=True`，权限 `sales_order:sales_order_update`）。
- 仅当订单存在 `billing_relevance='plan'` 行时执行。

**验收**
- 确认即生成；重复确认不重复生成；计划非法时确认回滚且错误码为 `ORDER_BILLING_PLAN_INVALID`；
  手工 action 可补跑。

**提交**（可与 T37 合并）
`feat(billing): 订单确认自动生成开票计划`

---

## [x] T39 退货 → 贷项

**文件**
- 修改 `meta/services/customer_invoice_service.py`
- 修改 `meta/tests/factories/_customer_invoice_helpers.py`
- 修改 `meta/tests/test_customer_invoice_service.py`
- 修改 `meta/tests/test_shipment_service.py`（退货发货单夹具如缺）

**内容**
- `create_from_shipment` 增加 `document_category='return'` 拦截（R-INV-19，
  `INVOICE_RETURN_SHIPMENT_NOT_BILLABLE`）。
- 新增 `create_credit_from_return_shipment(payload)`（spec §6.3）：
  退货行 → `reference_line_id` 原订单行 → 已过账正数发票行 FIFO 分配 → 负数贷项行。
- 行/头字段复制与来源键按 spec §6.3 第 6/7 步；累计退货量校验（R-RET-10）。
- `_write_doc_flow_edges` 贷项分支：先写 `customer_invoice_to_credit_memo`（若有原行），
  再按 `source_doc_type='return_shipment'` 追加 `return_shipment_line_to_credit_memo`。
- 注册 action `customer_invoice.create_credit_from_return_shipment`（权限 `credit_memo`）。

**验收**
- spec §10.3 的 10 条用例全过；两条 doc_flow 边同时存在。

**提交**
`feat(billing): 退货发货单生成贷项通知单`

---

## [x] T40 部分贷项 / 多次贷项 / on-account

**文件**
- 修改 `meta/services/customer_invoice_service.py`
- 修改 `meta/services/customer_invoice_actions.py`
- 修改 `meta/services/bo_action_registrations.py`
- 修改 `meta/tests/test_customer_invoice_service.py`
- 修改 `meta/tests/test_customer_invoice_actions.py`

**内容**
- `create_credit_from_invoice` 支持 `lines: [{invoice_line_id, qty|amount}]`（spec §6.4.1）；
  删除 `_find_red_invoice` 整单拦截，改行级累计额度（R-INV-20 `INVOICE_CREDIT_EXCEEDED`）。
- `_negate_line` 参数化：数量、金额、税额比例、plan 比例换算（R-INV-24）。
- 新增 `create_credit_on_account`（spec §6.4.2，R-INV-21）；`_is_red` 改为
  `document_category='credit_memo' or reversal_of_invoice_id`。
- 注册 action `customer_invoice.create_credit_on_account`（权限 `credit_memo`）。
- `_assert_reversible` 保留：已有贷项时禁止整单 reverse。

**验收**
- spec §10.4 的 10 条用例全过；Wave A 既有贷项用例（含
  `test_credit_post_rolls_back_billed_progress`）不回归。

**提交**
`feat(billing): 贷项部分冲销与 on-account 贷项`

---

## [x] T41 守卫规则

**文件**
- 修改 `meta/services/customer_invoice_service.py`（行级 plan/贷项身份锁定）
- 修改 `meta/services/sales_order_guard_service.py`
- 修改 `meta/tests/test_customer_invoice_guard.py`
- 修改 `meta/tests/test_sales_order_guard.py`
- 修改 `meta/tests/test_sales_order_schedule_guard.py`

**内容**
- 贷项行锁定：`original_invoice_line_id`、`source_doc_type/source_line_id` 非 draft 起不可改；
  on-account 行不得出现任何行键（R-INV-21）。
- 计划字段锁定：`billing_period_count/billing_interval_months/billing_anchor_date/
  billing_lead_days/billing_proration` 仅在订单 draft 且未生成期次时可改。
- R-RET-10：退货行累计退货量 ≤ 原行已开票量。
- 尾差常量注释：0.01（%）与 0.0001（元）用途分开说明。

**验收**
- spec §10.5 的 7 条用例全过。

**提交**
`feat(billing): 贷项与计划字段守卫（R-INV-19..24 / R-RET-10）`

---

## [x] T42 订单关闭校验 billing_status

**文件**
- 修改 `meta/services/sales_order_guard_service.py`
- 修改 `meta/tests/test_sales_order_guard.py`

**内容**
- 关闭前置追加 `billing_status='partial' → ORDER_BILLING_INCOMPLETE`（R-ORD-05 / D46）。
- `none` / `full` 放行；文案注明「未开票关闭需人工确认」。

**验收**
- partial 拒绝、none 放行、full 放行 3 条用例；既有 fulfillment 用例不回归。

**提交**（可与 T41 合并）
`feat(billing): 订单关闭校验开票状态`

---

## [x] T43 YAML / 前端入口

**文件**
- 修改 `meta/schemas/sales_order_line.yaml`
- 修改 `meta/schemas/customer_invoice.yaml`
- 修改 `meta/schemas/shipment.yaml`
- 修改 `meta/schemas/sales_order.yaml`

**内容**
- `sales_order_line.yaml`：5 个计划字段；`billing_relevance='plan'` 时可见；
  `milestone` 隐藏期数/间隔；`daily` 提示需服务期（spec §8.1）。
- `customer_invoice.yaml`：详情动作新增 `create_credit_on_account`；`post`/`reverse` 确认文案补充。
- `shipment.yaml`：退货发货单隐藏「生成销售发票」入口（`document_category != 'return'`）。
- `sales_order.yaml`：详情动作 `generate_billing_plan`（仅 `billing_status in (none, partial)`）。

**验收**
```powershell
npm run build
python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file meta/tests/test_schema_api.py,meta/tests/test_sales_order_line_schema.py
```
- YAML 可加载、无重复字段、无未知 aspect；条件可见表达式不报错。

**提交**
`feat(billing): 开票计划字段与单据动作前端声明`

---

## [x] T44 测试补齐

**文件**
- 修改 `meta/tests/test_customer_invoice_service.py`
- 修改 `meta/tests/test_customer_invoice_actions.py`
- 修改 `meta/tests/test_customer_invoice_guard.py`
- 新增 `meta/tests/test_billing_plan_service.py`
- 新增 `meta/tests/test_billing_plan_trigger.py`
- 新增 `meta/tests/test_migration_v242.py`

**内容**
- 按 spec §10 全矩阵补齐（C1 9 / C2 12 / C3 10 / C4 10 / C5 7 / 迁移 4，合计 ≥ 52）。
- 夹具：`make_billing_schedule(...)`、`make_return_shipment(...)`、`make_plan_line(...)`；
  禁止 raw SQL 进入 service 测试以外位置。

**验收**：spec §11 全部命令通过，新增用例数达标。

**提交**
`test(billing): Wave C 用例补齐`

---

## [x] T45 回归 + 文档勾选 + 分组提交

**内容**
1. 跑 spec §11 全量命令；额外跑 `test_sales_order_service.py`、`test_doc_flow.py`。
2. 勾选 `spec.md` §1.2 与 `tasks.md` 各 T 完成框。
3. `git status` 只含 T35-T44 文件；逐文件 `git add`，按各 T 提交信息分组 commit。
4. 汇报：实现范围、D40-D47 落地口径、测试数、遗留（AR/GL/税/Debit Memo/发票号时机）。

**验收**
- 全量回归通过；`v242.verify()` 通过；仅 s8 worktree 有新提交。

---

## 依赖关系

```
T35 ─┬─> T37 ─> T38
     │     └─> T41
     ├─> T36
     ├─> T39 ─> T40
     └─> T43
T42 依赖 T41（守卫共用）
T44 依赖 T35-T43
T45 收尾
```

## 完成定义（DoD）

- [x] T35-T45 全部完成，新增测试 ≥ 52 全部通过。
- [x] D40-D47 已确认；D43 按「保留贷项回退进度」落地并在 spec 声明差异。
- [x] 无新表；仅 `sales_order_lines` 5 列 + 1 权限 + 1 doc_flow 规则 + 2 索引。
- [x] 三个单据动作可经 business action 调用，且与状态按钮语义一致。
- [x] 退货发货单无法正向开票；退货贷项可追溯、可部分、可跨票拆分。
- [x] 贷项支持部分数量/金额/多次/on-account；累计不超原行。
- [x] AR / 收入确认 / GL / 税 / Debit Memo / 发票号时机 均未越界实现（仅留契约）。

---

## 实现级细化（2026-11-10 批准后基线）

### 通用约定（全任务适用）

| 项 | 约定 |
|---|---|
| 错误类型 | 服务层抛 `CustomerInvoiceError(message, field_name, rule)`；action 层 `_fail(str(exc), exc.rule)` |
| 金额精度 | `_round(x, 4)`（ROUND_HALF_UP）；金额比较 `EPSILON=0.0001`；比例比较 `PERCENT_TAIL_TOLERANCE=0.01`，二者禁止互换 |
| 事务 | service 内 `with _atomic(self.ds)`；订单确认触发必须与确认同事务（拦截器透传 ds，不另起连接/事务） |
| 幂等 | 所有 action `idempotent=True`；服务方法先查终态再写入 |
| 迁移 | 结构、函数命名、helper（`_table_exists`/`_column_exists`）完全对齐 v241，不引入新框架 |
| 数据边界 | 不建新表；不改既有列语义；不改 Wave A/B 已固化用例 |

### T35 实现细化（v242）

- `upgrade()` 固定顺序：① 5 列 → ② 权限 → ③ 菜单挂载 → ④ doc_flow 规则 → ⑤ 2 个索引；每步先查后写。
- 5 列 DDL 严格按 spec §4.1，`billing_interval_months` / `billing_lead_days` / `billing_proration` 用 `DEFAULT`，`billing_period_count` / `billing_anchor_date` 允许 NULL。
- 权限插入字段对齐 v239 既有记录（`permission_code/name/module/action` 等）；授予 `admin`、`default` 两个权限集。
- doc_flow 规则字段：`rule_id='return_shipment_line_to_credit_memo'`、`source_bo='shipment_line'`、`target_bo='customer_invoice_line'`、`source_qty_field='qty'`、`pool='billing'`、`status='active'`。
- `verify()` 断言：5 列存在+默认值；权限记录与两个权限集映射；菜单 `customer_invoice-list` 挂载；doc_flow 规则 active 且四要素正确；两个索引存在（`idx_cil_original_line` 接受同列等价索引）。
- `verify()` 非法数据断言：`billing_proration NOT IN ('none','daily')`、`billing_period_count NOT BETWEEN 1 AND 60`、`billing_interval_months NOT BETWEEN 1 AND 12` 任一命中即抛错。
- `rollback()` 逆序：索引 → 规则 → 菜单/权限映射 → 权限 → 5 列（SQLite `ALTER TABLE DROP COLUMN` 可用则删，否则重建表或跳过并明确 toast）；全过程幂等。
- 测试函数：
  - `test_v242_upgrade_idempotent`
  - `test_v242_verify_ok`
  - `test_v242_verify_rejects_invalid_proration`
  - `test_v242_rollback_clean`

### T36 实现细化（单据动作）

- handler 签名与注册方式沿用文件内既有 `*_handler`（参考 `create_from_shipment_handler` / `create_credit_handler`）。
- 入参归一：`_invoice_id(payload)` 依次读 `invoice_id`、`source_doc_id`、`source_id`；为空 → `INVOICE_STATE_INVALID`。
- `submit_handler`：`payload` 仅取 id，调 `service.submit(invoice_id)`；前置 `draft`，`submitted/posted` 直接返回当前状态，`cancelled/reversed` → `INVOICE_STATE_INVALID`。
- `post_handler`：已 `posted` 返回当前（不得二次 `_apply_billed`）；`reversed/cancelled` → `INVOICE_STATE_INVALID`；`draft` → `INVOICE_STATE_INVALID`（必须先 submit）。
- `reverse_handler`：`reason` 必填（trim 后非空）；`reversal_date` 缺省 = `invoice_date`；已有非取消红字单 → 直接返回其 `{id, invoice_no, status}`；原票为红字 → `INVOICE_STATE_INVALID`。
- 返回体统一 `{id, invoice_no, status}`；reverse 追加 `original_invoice_id`。
- 注册：`object_type='customer_invoice'`、`category='business'`、`requires_auth=True`、`idempotent=True`、`input_schema` 中 `invoice_id` 必填，reverse 追加 `reason` 必填。
- 测试函数（≥9）：
  `test_action_submit_ok` / `test_action_submit_idempotent` / `test_action_submit_invalid_state` /
  `test_action_post_ok` / `test_action_post_idempotent` / `test_action_post_from_draft_rejected` /
  `test_action_reverse_ok` / `test_action_reverse_idempotent` / `test_action_reverse_requires_reason`

### T37 实现细化（计划生成服务）

- `BillingPlanService(ds, platform_ds=None)`，构造对齐既有 service；暴露 `generate_for_order(order_id, *, triggered_by='confirm') -> list[int]`、`generate_for_line(order, line) -> list[dict]`。
- `generate_for_order`：加载订单（`status='confirmed'`）+ 全部行；过滤 `billing_relevance='plan'`；逐行 `generate_for_line`；任一行失败 → 抛 `ORDER_BILLING_PLAN_INVALID`（同事务由调用方回滚）；返回新期次 id 列表（无 plan 行 → `[]`）。
- `generate_for_line` 分派：
  - `billing_method in (None,'fixed_price')` → N=1，percent=100
  - `time_and_material` → N=`billing_period_count or 1`，`percent_i = ROUND(100/N,4)`，末期 = `100 - Σ前N-1`
  - `milestone` → `[]`
- 日期：`anchor = billing_anchor_date or order.confirmed_at日期 or today`；`promised_date_i = add_months(anchor,(i-1)*interval) + billing_lead_days`（复用 `payment_term_schedule_service.add_months`）。
- 按日：窗口 `[add_months(anchor,(i-1)*interval), add_months(anchor,i*interval))` 与 `[service_start_date, service_end_date]` 交集天数；百分比 = 交集/总交集×100（4 位，末期吸差）；总交集 0 → `ORDER_BILLING_PLAN_INVALID`；任一端缺失 → 退化均分。
- 幂等：行已存在 `schedule_kind='billing' AND status<>'cancelled'` → 返回既有 id、不新增；行 `billed_amount>0` → 不重算直接返回。
- 写库：`data = {order_id, order_line_id, project_id, plant_location_id, schedule_kind:'billing', promised_qty:None, milestone_code:None, billing_percent, promised_date, status:'planned', billing_status:'none', billed_amount:0}`；先 `validate_schedule_write(data, old=None)` 再 insert。
- 测试函数（≥12）：
  `test_generate_tm_three_periods` / `test_generate_fixed_price_single_period` / `test_generate_milestone_skipped` /
  `test_generate_anchor_and_interval_dates` / `test_generate_lead_days_positive` / `test_generate_lead_days_negative` /
  `test_generate_daily_proration_first_period` / `test_generate_daily_without_service_dates_falls_back` /
  `test_generate_daily_zero_overlap_rejected` / `test_generate_idempotent_existing_schedules` /
  `test_generate_skips_when_billed_amount_positive` / `test_generate_returns_empty_without_plan_lines`

### T38 实现细化（确认触发 + 补跑）

- 在 `sales_order_guard_interceptor` 既有 after-write 入口追加：仅当 `old.status != 'confirmed' and new.status == 'confirmed'` 且存在 plan 行时调用 `BillingPlanService(self.ds...).generate_for_order(order_id, triggered_by='confirm')`；异常包装为 `ORDER_BILLING_PLAN_INVALID` 向上抛，确认事务回滚。
- 注册 `sales_order.generate_billing_plan`：handler 读 `order_id/source_doc_id`，校验订单 `confirmed/closed`，`idempotent=True`，权限 `sales_order:sales_order_update`；返回 `{order_id, created:[ids], skipped:bool}`。
- 测试函数：
  `test_confirm_triggers_plan_generation` / `test_confirm_twice_no_duplicate` /
  `test_confirm_invalid_plan_rolls_back` / `test_action_generate_billing_plan_backfill`

### T39 实现细化（退货贷项）

- `create_from_shipment` 开头（状态校验前）加：`shipment.get('document_category') == 'return'` → `INVOICE_RETURN_SHIPMENT_NOT_BILLABLE`（R-INV-19）。
- `create_credit_from_return_shipment(payload)` 按 spec §6.3 九步实现；内部小函数：
  - `_require_return_shipment(shipment_id)`：存在 + `document_category='return'` + 状态合法
  - `_resolve_return_origin(return_line)`：`order_line_id` → 退货订单行 → `reference_line_id` → 原订单行
  - `_load_creditable_invoice_lines(order_line_id)`：join 头，`status='posted'`、`original_invoice_line_id IS NULL`、`qty>0`，按 `(invoice_date, id)` 升序
  - `_alloc_fifo(qty, candidates)`：按剩余可贷量切分，返回 `[(invoice_line, alloc_qty)]`
- 累计退货量校验：`ΣABS(历史退货贷项 qty WHERE source_line_id 属于该退货订单行系) + 本次 ≤ Σ已开票`。
- 贷项行 `_negate_line` 需支持显式数量/金额（T40 同一改造），来源键复制原行。
- doc_flow：`_write_doc_flow_edges` 贷项分支改为先写 `customer_invoice_to_credit_memo`（有 original 行时），再判 `source_doc_type=='return_shipment'` 追加 `return_shipment_line_to_credit_memo`（`attach_edge` 数量=分配量、金额=ABS(net)），不 `continue`。
- 注册 action `customer_invoice.create_credit_from_return_shipment`，权限 `customer_invoice:credit_memo`。
- 测试函数（≥10）：
  `test_return_shipment_forward_billing_rejected` / `test_return_credit_single_invoice` /
  `test_return_credit_fifo_across_two_invoices` / `test_return_credit_partial_qty` /
  `test_return_credit_missing_origin_rejected` / `test_return_credit_exceeds_billed_qty_rejected` /
  `test_return_credit_accumulated_exceeds_rejected` / `test_return_credit_line_source_keys` /
  `test_return_credit_writes_two_doc_flow_edges` / `test_return_credit_duplicate_return_line_rejected`

### T40 实现细化（部分/多次/on-account 贷项）

- `create_credit_from_invoice`：
  - `lines` 归一：元素允许 `invoice_line_id`+`qty` 或 `invoice_line_id`+`amount`；两者同给 → `INVOICE_CREDIT_AMOUNT_INVALID`；都缺 → 取剩余可贷。
  - 行级额度：`remaining_qty = orig.qty - ΣABS(posted credit qty)`；`remaining_amount = orig.net - ΣABS(posted credit net)`；超 `EPSILON` → `INVOICE_CREDIT_EXCEEDED`。
  - 移除 `_find_red_invoice` 调用；保留 `_assert_reversible`（有贷项禁止整单 reverse）。
  - `_negate_line(line, line_no, *, qty=None, amount=None)`：按显式值取负；税额按原行 `tax_amount/net_amount` 比例换算；plan 行 `billing_percent = ROUND(orig_percent * credit_amount / orig_net, 4)`。
- `create_credit_on_account(payload)`：客户/币种必填；≥1 行；每行 `net<0`；行键全空；`source_doc_type='manual'`；头 `reversal_of_invoice_id=NULL`、`document_category='credit_memo'`；`_is_red` 改为 `document_category=='credit_memo' or reversal_of_invoice_id`。
- 注册 `customer_invoice.create_credit_on_account`（权限 `customer_invoice:credit_memo`）。
- 测试函数（≥10）：
  `test_credit_partial_qty` / `test_credit_partial_amount` / `test_credit_twice_within_limit` /
  `test_credit_exceeds_limit_rejected` / `test_credit_qty_and_amount_both_rejected` /
  `test_credit_plan_line_percent_conversion` / `test_credit_on_account_ok` /
  `test_credit_on_account_positive_rejected` / `test_credit_on_account_missing_customer_rejected` /
  `test_is_red_detects_on_account`

### T41 实现细化（守卫）

- 服务层（写入路径）与守卫层（更新路径）双保险，错误码复用 `R-INV-19..24` / `R-RET-10`。
- 贷项行锁字段：`original_invoice_line_id`、`source_doc_type`、`source_line_id`、`shipment_line_id`、`schedule_id`、`order_line_id` 非 draft 起不可改（`INVOICE_CREDIT_LINE_LOCKED`）。
- 计划字段锁：5 列仅订单 draft 且该行无任何非取消 billing 期次时可改（`ORDER_BILLING_PLAN_LOCKED`）。
- 尾差常量注释落在 service 顶部（两常量各一段）。
- 测试函数（≥7）：
  `test_guard_return_shipment_not_billable` / `test_guard_credit_line_keys_locked` /
  `test_guard_on_account_no_line_keys` / `test_guard_plan_fields_locked_after_schedule` /
  `test_guard_return_qty_not_exceed_billed` / `test_guard_credit_amount_within_limit` /
  `test_guard_tolerances_not_interchangeable`

### T42 实现细化（订单关闭）

- `sales_order_guard_service` 关闭分支追加：`billing_status == 'partial'` → `ORDER_BILLING_INCOMPLETE`；`none` 放行并写审计备注（不阻断）；`full` 放行。
- 测试：`test_close_order_rejected_when_billing_partial` / `test_close_order_allowed_when_billing_none` / `test_close_order_allowed_when_billing_full`。

### T43 实现细化（YAML）

- `sales_order_line.yaml`：5 字段 + `visible_when`（`billing_relevance=='plan'`）；`milestone` 隐藏 `billing_period_count/billing_interval_months`；`billing_proration=='daily'` 时 hint 提示服务期。
- `customer_invoice.yaml`：`detail.actions` 加 `create_credit_on_account`（`permission: customer_invoice:credit_memo`, 分组「更多」）；`post`/`reverse` confirm 文案补充。
- `shipment.yaml`：`ui_view_config` 对 `document_category=='return'` 隐藏「生成销售发票」。
- `sales_order.yaml`：`detail.actions` 加 `generate_billing_plan`（`permission: sales_order:sales_order_update`，`visible_when: billing_status in (none, partial)`）。
- 验收：YAML 加载、无重复字段、`npm run build` 通过、schema 相关测试通过。

### T44 测试补齐

- 只改测试文件；夹具放 `meta/tests/factories/`；不写 raw SQL 到 service 测试之外。
- 汇总新增用例：C1 9 + C2 12 + C3 10 + C4 10 + C5 7 + 迁移 4 = 52。

### T45 收尾

- 全量命令按 spec §11；额外 `test_sales_order_service.py`、`test_doc_flow.py`。
- 勾选 spec §1.2 与本文件 T35-T44 复选框；逐文件 `git add`，按各 T 提交信息分组 commit（仅 worktree）；`git status` 复核无 `MagicMock/`。
- 汇报模板：实现范围 / D40-D47 落地口径 / 测试数 / 遗留（AR、GL、税、Debit Memo、发票号时机）。