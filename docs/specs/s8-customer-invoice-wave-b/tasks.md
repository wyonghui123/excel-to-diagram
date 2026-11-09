# S8 Wave B 任务清单（计划行开票）

> 关联规格：`spec.md`（同目录）
> 执行顺序：T25 → T26 → T27 → T28 → T29 → T30 → T31 → T32 → T33 → T34
> 前置：**D3 已有文档结论（D3-a 开票计划口径，见 spec §2 证据块），开工前仅需 PM 形式确认**
> 约束：只在 `D:\filework\s8-billing-worktree` 改动；禁止在主工作树 commit；禁止 pytest；
> 所有测试走 `python d:\filework\test.py --root D:\filework\s8-billing-worktree --file <path> --port 3012`。

---

## [x] T25 schema 派生字段补声明（D3 文案确认后执行）

**文件**
- 修改 `meta/schemas/sales_order_line.yaml`
- 修改 `meta/schemas/sales_order_schedule.yaml`
- 修改 `meta/schemas/sales_order.yaml`
- 修改 `meta/schemas/customer_invoice_line.yaml`

**内容**
- `sales_order_line.yaml`：新增只读派生字段 `billing_relevance`（enum `delivery/plan`）、
  `billed_qty`、`billed_amount`（`derived: true`、`ui.editable: false`、`required: false`）。
- `sales_order_schedule.yaml`：新增只读 `billed_amount`、`billing_status`
  （enum `none/partial/full/cancelled`）。
- `sales_order.yaml`：新增只读 `billing_status`（`none/partial/full`）、`billing_derived_at`。
- `customer_invoice_line.yaml`：`source_doc_type` enum 增加 `billing_schedule`；
  `billing_percent` 描述改为「按比例开票的比例（0-100）」。
- 若 D3 按建议批准：`sales_order_schedule.yaml` 的 `billing_percent` / `billing_amount` /
  `promised_date` 文案「收款」改「开票」；`sales_order_guard_service.py` R-SCH-11..15 注释同步。

**验收**
- YAML 可被 registry 加载，无重复字段、无未知 aspect。
- `meta/tests/test_schema_api.py` 通过；`meta/tests/test_sales_order_schedule_billing_amount.py` 通过。

**提交**
`feat(billing): 开票计划派生字段与来源枚举声明`

---

## [x] T26 迁移 v241（doc_flow 规则 + 到期索引）

**文件**
- 新增 `meta/migrations/v241__customer_invoice_billing_plan.py`
- 新增 `meta/tests/test_migration_v241.py`

**内容**
- 播种 `billing_schedule_to_customer_invoice`
  （`source_bo=sales_order_schedule`、`target_bo=customer_invoice_line`、
  `pool=billing`、`source_qty_field=billing_percent`、`status=active`）。
- 建索引 `idx_sos_billing_due (schedule_kind, billing_status, promised_date)`。
- `verify()`：规则存在且 active、索引存在、`billing_status` 合法值、`billed_amount>=0`。
- `rollback()`：删规则 + 索引，幂等。
- 测试用例 >= 3：upgrade 幂等 / verify 通过 / rollback 干净。

**验收**
```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v241.py --port 3012
```

**提交**（可与 T25 合并）
`feat(billing): v241 计划开票 doc_flow 规则与到期索引`

---

## [x] T27 服务：计划开票建单

**文件**
- 修改 `meta/services/customer_invoice_service.py`
- 修改 `meta/tests/factories/_customer_invoice_helpers.py`（如需 `billing_schedule` 夹具）

**内容**
- 新增常量与错误码（spec §5.1）。
- `create_from_schedule(payload)`（spec §5.2）：
  - `lines` 优先，兼容 `schedule_ids` / 单 `source_doc_id`。
  - 同订单校验、期次状态、订单状态、`billing_relevance='plan'`、比例/剩余金额校验。
  - 复用 `prepare_header`，行由 `_build_line_from_schedule` 生成。
- `_build_line_from_schedule`（spec §5.3）：期金额、remaining、尾差吸收、税额/总额、
  `qty=1`、`billing_basis='percent'`、`price_source='order'`、`order_unit_price=NULL`。
- `_assert_relevance(order_line, expected)` 改造；`create_manual` / `create_from_shipment`
  继续拒绝 plan 来源与 `schedule_id`。

**验收**
- 整期、多期、分次、超额、错来源、错状态、错订单等用例（spec §10.1 的 1-8、14）。

**提交**
`feat(billing): 计划期次生成销售发票草稿`

---

## [x] T28 服务：计划过账与派生

**文件**
- 修改 `meta/services/customer_invoice_service.py`

**内容**
- `post` 第 6 步 `_apply_billed` 增加 plan 分支（spec §5.4）：
  按 `schedule_id` 聚合、条件 UPDATE 防并发、更新后重算 `billing_status`。
- `_write_doc_flow_edges` 增加 plan 分支（`billing_schedule_to_customer_invoice`，
  `quantity=1`、`amount=net`）。
- `recompute_order_billing` 增加 plan 分支与混合聚合（spec §5.6）。
- `_assert_lines_available` 增加 plan 剩余金额与来源状态复核（spec §5.7）。

**验收**
- 过账后 `billed_amount` / `billing_status` / 订单 `billing_status` 正确；
  失败整体回滚；规则缺失只告警（spec §10.1 的 9、10、13）。

**提交**
`feat(billing): 计划期次过账回写与订单开票状态派生`

---

## [x] T29 服务：计划红冲

**文件**
- 修改 `meta/services/customer_invoice_service.py`

**内容**
- `_negate_line`：plan 行保留 `billing_basis='percent'`、`billing_percent`、`billing_base_amount`，
  `qty=-1`、金额取负。
- `reverse` 的 `_apply_billed(lines, sign=-1)`：plan 行扣减期次金额并重算状态；
  **不修改** `sales_order_schedules.status`；`customer_invoice_schedules` 仍置 cancelled。
- 防重复红冲、分配检查沿用。

**验收**
- 红冲后 `billed_amount` 精确还原、`billing_status` 回退、期次状态不变、
  红字行口径正确（spec §10.1 的 11、12）。

**提交**（T27-T29 可合并）
`feat(billing): 计划期次红冲回滚`

---

## [x] T30 守卫：R-INV-18 / R-SCH-17

**文件**
- 修改 `meta/core/interceptors/customer_invoice_guard_interceptor.py`
- 修改 `meta/services/sales_order_guard_service.py`
- 修改 `meta/tests/test_customer_invoice_guard.py`
- 修改 `meta/tests/test_sales_order_guard.py`
- 修改 `meta/tests/test_sales_order_schedule_guard.py`

**内容**
- 发票行守卫：放行 plan 行；禁止改 `schedule_id/billing_basis/billing_base_amount`；
  `submitted` 起冻结与 `customer_invoice_schedules` 只读保持不变（D27）。
- 订单守卫 R-INV-18a/b/c/d；计划守卫 R-SCH-17（spec §6.2）。
- 若 D3 批准，同步 R-SCH-11..15 文案。

**验收**
- 新增 >= 6 发票守卫用例 + >= 5 订单/计划守卫用例（spec §10.2 / §10.3）。

**提交**
`feat(billing): 开票计划字段守卫（R-INV-18 / R-SCH-17）`

---

## [x] T31 到期清单工具 + 只读 action

**文件**
- 新增 `meta/tools/billing_due_list.py`
- 修改 `meta/services/bo_action_registrations.py`
- 新增 `meta/tests/test_billing_due_list.py`
- 修改 `meta/tests/test_customer_invoice_actions.py`

**内容**
- 工具执行 spec §7.1 SQL；`as_of` 参数；只读；退出码 0/2/1。
- action `customer_invoice.list_due_schedules`（权限 `customer_invoice:customer_invoice_view`，
  `idempotent=True`），返回 `{items,total}`，支持 `as_of/order_id/分页`。

**验收**
- 到期清单 >= 4 用例（spec §10.5）；action contract 测试通过。

**提交**
`feat(billing): 到期开票清单查询与 action`

---

## [x] T32 前端入口：期次详情「生成销售发票」

**文件**
- 修改 `meta/schemas/sales_order_schedule.yaml`
- 新增 `meta/services/customer_invoice_actions.py` 中的 `create_from_schedule_handler`
- 修改 `meta/services/bo_action_registrations.py`

**内容**
- `ui_view_config.detail.actions` 追加 `create_invoice`
  （action `customer_invoice.create_from_schedule`，权限 `customer_invoice:customer_invoice_create`）。
- handler 白名单透传头字段；`schedule_id` 缺失时把 `source_doc_id` 当 `schedule_id`；
  `CustomerInvoiceError` → `_fail(str(exc), exc.rule)`。
- 注册 action：`object_type='customer_invoice'`、`category='business'`、
  `requires_auth=True`、`idempotent=False`。
- 复用 Wave A T10 的 `DetailPage.runBusinessAction`，不新增页面。

**验收**
```powershell
npm run build
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
```

**提交**
`feat(billing): 计划期次详情页生成销售发票入口`

---

## [x] T33 测试补齐

**文件**
- 修改 `meta/tests/test_customer_invoice_service.py`
- 修改 `meta/tests/test_customer_invoice_guard.py`
- 修改 `meta/tests/test_customer_invoice_actions.py`
- 新增/修改 `meta/tests/test_migration_v241.py`
- 新增 `meta/tests/test_billing_due_list.py`

**内容**：按 spec §10 完整矩阵补齐；夹具复用 `_customer_invoice_helpers.py`，
新增 `make_billing_schedule(...)`（如缺）。禁止 raw SQL 进入服务测试以外位置。

**验收**：spec §11 全部命令通过；新增用例数达 DoD。

**提交**
`test(billing): Wave B 计划开票用例补齐`

---

## [x] T34 回归 + 文档勾选 + 提交

**内容**
1. 跑 spec §11 全量命令 + `test_shipment_service.py` / `test_payment_term_schedule.py`。
2. 勾选 `spec.md` §1.2 与 `tasks.md` 各 T 完成框。
3. `git status` 只含 T25-T34 文件；逐文件 `git add` + commit（分组合并见各 T）。
4. 汇报：实现范围、D3/D11 落地口径、测试结果、遗留项（D27/D28/Wave C）。

**验收**
- 全量回归通过；`v241.verify()` 通过；到期清单干净数据退出码 0。
- 仅 s8 worktree 有新提交，主工作树未改动。

---

## 依赖关系

```
T25 ─┬─> T27 ─> T28 ─> T29
     │           └─> T30（需要 T27/T28 的校验与回写）
     └─> T26 ─> T31
T32 依赖 T27（handler）+ T26（规则）
T33 依赖 T26-T32
T34 收尾
```

## 完成定义（DoD）

- [x] T25-T34 全部完成，新增测试 >= 33 且全部通过。
- [x] D3 按既有文档结论 D3-a（开票计划）落地并经 PM 形式确认；D11 按「允许分次」落地。
- [x] 无新表/新列；无 AR、milestone_event、settlement_block_code、前端页面。
- [x] `customer_invoice_schedules` 只读未放开（D27）。
- [x] 仅 s8 worktree 提交，主工作树与 s7-worktree 未改动。