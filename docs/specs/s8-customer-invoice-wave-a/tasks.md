# S8 Wave A 任务清单（customer_invoice）

> 关联规格：`spec.md`（同目录）
> 执行顺序：T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8
> 约束：只在 `D:\filework\s8-billing-worktree` 改动；禁止在主工作树 commit；禁止 pytest；
> 所有测试走 `python d:\filework\test.py --root D:\filework\s8-billing-worktree --file <path> --port 3012`。

---

## [x] T1 schema 三件套

**文件**
- 新增 `meta/schemas/customer_invoice.yaml`
- 新增 `meta/schemas/customer_invoice_line.yaml`
- 新增 `meta/schemas/customer_invoice_schedule.yaml`

**内容**：按 `spec.md` §3 字段/状态机/索引/约束；结构镜像
`shipment.yaml`、`shipment_line.yaml`、`sales_order_schedule.yaml` 的
`aspects` / `ui_view_config` / `relations` / `semantics` 写法。

**验收**
- YAML 可被 `meta.core.models.registry` 加载，无重复字段、无未知 aspect。
- `numbering` 声明被 `DocumentNumberService._read_numbering('customer_invoice')` 读到。
- 状态枚举与 §3.1 一致（5 态）。

---

## [x] T2 迁移 v231

**文件**
- 新增 `meta/migrations/v231__customer_invoice.py`

**内容**：按 `spec.md` §4 九步；镜像 `v177__purchase_order_object.py` 的
`upgrade` / `verify` / `_table_exists` / `_column_exists` / 类型与序列插入 / 权限 grant 写法。

**验收**
- `upgrade` 幂等（连续执行两次不报错、不重复种子）。
- `verify()` 直接查 DB 校验 §4 全部检查项，失败返回/抛出而非仅打印。
- 回填后 `billing_relevance` 仅 `delivery` / `plan`。

---

## [x] T3 服务骨架与建单

**文件**
- 新增 `meta/services/customer_invoice_service.py`

**内容**
- 常量、`CustomerInvoiceError`、数值/时间/事务工具。
- `prepare_header` / `create_from_shipment` / `create_manual` / `recalc`。
- 写头/写行/载入订单、发货、计划行、订单行的 `_load_*` / `_write_*`。

**验收**
- 手工建单与发货建单都能返回 `{id, invoice_no, status:'draft', line_ids}`。
- `plan` / `none` 来源分别抛 `INVOICE_RELEVANCE_NOT_SUPPORTED` / `INVOICE_SOURCE_MISMATCH`。
- 超量抛 `INVOICE_QTY_EXCEEDED`；金额按 ROUND_HALF_UP 4 位。

---

## [x] T4 服务状态流转与过账

**文件**
- 修改 `meta/services/customer_invoice_service.py`

**内容**
- `submit` / `cancel` / `post`（§5.4 八步）/ `recompute_order_billing`。
- `_generate_schedules`（尾差归最后一期；`resolve_base_date` + `compute_due_date`）。
- billed 条件更新与 doc_flow attach；`_emit_accounting_event_hook` 空实现。

**验收**
- 过账失败时事务回滚：头仍 `submitted`、billed 不变、无期次、无边。
- 过账成功：Σ期次=gross；`billed_qty` / `billed_amount` / `billing_status` 正确。
- doc_flow 规则缺失时过账仍成功（仅告警）。

---

## [x] T5 红冲

**文件**
- 修改 `meta/services/customer_invoice_service.py`

**内容**
- `reverse`：红字头/行（负数量负金额、`reversal_of_invoice_id`、`original_invoice_line_id`）、
  原期次 cancelled、billed 反向回写、原单 reversed、`INVOICE_ALLOCATION_EXISTS` 检查。
- `INVOICE_REVERSE_EXISTS` 防重复红冲。

**验收**
- 红字单无期次、金额为负、`posting_date >= 原 posting_date`。
- 红冲后 `shipment_line.billed_qty` 与 `order_line.billed_*` 回到红冲前。
- 已红冲原单不可再次红冲。

---

## [x] T6 守卫拦截器

**文件**
- 新增 `meta/core/interceptors/customer_invoice_guard_interceptor.py`
- 修改 `meta/server.py`（import + 注册）
- 修改 `meta/core/app_builder.py`（import + 注册）

**内容**：按 `spec.md` §6 表格实现 header / line / schedule 三类写保护；
状态迁移委托服务；`priority=51`。

**验收**
- `posted`/`reversed`/`cancelled` 头不可改、不可删。
- `submitted` 头冻结源字段；`draft` 可改。
- 行 XOR / relevance / 可用量 / 金额重算生效。
- schedule 任意写一律拒绝。
- 拦截器在两条注册路径都生效（单测直接实例化 + 注册函数各验一次）。

---

## [x] T7 一致性检查工具

**文件**
- 新增 `meta/tools/check_billing_relevance_consistency.py`

**内容**：执行 §20.4 两条 SQL；打印违规明细；返回退出码（0=无违规，1=有违规）。

**验收**
- 手工造 1 条违规数据后退出码 1；修复后 0。
- 不修改任何数据（只读查询）。

---

## [x] T8 测试与回归

**文件**
- 新增 `meta/tests/test_customer_invoice_service.py`（>=14 用例）
- 新增 `meta/tests/test_customer_invoice_schedule.py`（>=6 用例）
- 新增 `meta/tests/test_customer_invoice_guard.py`（>=8 用例）
- 新增 `meta/tests/test_migration_v231.py`（>=4 用例）

**内容**：按 `spec.md` §8 矩阵；夹具使用 in-memory sqlite + `_MemDS`，
表结构与种子直接复用 v231 的 DDL 常量（避免两处漂移）。

**验收**
```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
```
全部通过；再跑回归：
```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_shipment_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_payment_term_schedule.py --port 3012
```

---

## 收尾（批准后执行）

1. 复核 `git status`：只含 T1-T8 列出的文件。
2. 在 s8 worktree `git add`（逐文件）+ `git commit`，message：
   `feat(billing): customer invoice wave A (schema, v231, service, guard, tests)`。
3. 汇报：实现范围、回避的 TBD、测试结果、待拍板项（D19/D27/D28）。

---

## 依赖关系

```
T1 ─┬─> T2 ─┬─> T3 ─> T4 ─> T5
    │       └─> T8（migration 用例）
    └─> T6（需要 T3/T4 的 prepare/validate 方法）
T7 独立（只依赖 T2 的列）
```

## 完成定义（DoD）

- [x] T1-T8 全部完成，测试通过数 >= 32。
- [x] `verify()` 自检通过；`check_billing_relevance_consistency.py` 在干净数据上退出码 0。
- [x] 无 TBD 相关表/字段被引入（无 accounting_event、无 settlement_block_code、无 AR 收款核销）。
- [x] 仅 s8 worktree 有一个新 commit，主工作树与 s7-worktree 未改动。

---

# B2 发货开票入口（spec §13）

## [x] T9 后端 Action `customer_invoice.create_from_shipment`

**新增**
- `meta/services/customer_invoice_actions.py`
  - `_ok` / `_fail` / `_blank` / `_set_user_context`（镜像 `receipt_actions.py`）
  - `_service()`：`CustomerInvoiceService(get_data_source('sqlite', database=get_meta_db_path()))`
  - `create_from_shipment_handler(params, context=None)`：
    `shipment_id = params.get('shipment_id') or params.get('source_doc_id')`；
    白名单透传 `invoice_date/posting_date/document_type_id/payment_term_id/incoterm_code/remark/lines`；
    `CustomerInvoiceError` → `_fail(str(exc), exc.rule or 'INVOICE_INVALID')`
- `meta/tests/test_customer_invoice_actions.py`（3 用例，见 spec §13.6）

**修改**
- `meta/services/bo_action_registrations.py`：注册
  `customer_invoice.create_from_shipment`，
  `permission_required='customer_invoice:customer_invoice_create'`，
  `object_type='customer_invoice'`，`category='business'`，`requires_auth=True`，`idempotent=False`

**验收**
```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_bo_action_contract.py --port 3012
```

## [x] T10 发货单详情页按钮 + 权限门

**修改**
- `meta/schemas/shipment.yaml`：`ui_view_config.detail.actions` 追加
  `create_invoice`（`permission: customer_invoice:customer_invoice_create`，
  `action: customer_invoice.create_from_shipment`）
- `src/components/common/DetailPage/DetailPage.vue`：
  - `computedActions` 分离业务动作（含 `action`）/ 声明式动作；业务动作按
    `authStore.hasPermission(a.permission)` 过滤；全为业务动作时以默认按钮集为底追加
  - 新增 `runBusinessAction(action)`：确认 → `useBoAction().call(action.action,
    { source_doc_id: props.id, ...(action.params || {}) })` → 成功提示 + `handleRefresh()`
  - `handleObjectPageAction` 的 `default:` 分支派发 `action.action`

**验收**
```powershell
npm run build   # 在 D:\filework\s8-billing-worktree 执行
```

## [x] T11 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
```

- `git status` 仅含 T9-T10 文件；`git add` 逐文件 + commit：
  `feat(billing): 发货单详情页生成销售发票（BO action + 权限门）`
- 汇报：action 契约、按钮派发口径、测试结果。

---

# B3 价格变更 D13（spec §14）

## [x] T12 数据层：`price_diff_amount` 列 + v233 迁移

**修改 / 新增**
- `meta/migrations/v231__customer_invoice.py`：`LINE_DDL` 与 verify 列清单加
  `price_diff_amount NUMERIC(18,4) NOT NULL DEFAULT 0`
- 新增 `meta/migrations/v233__customer_invoice_line_price_diff.py`
  （加列 + 回填 + verify + rollback，幂等）
- `meta/schemas/customer_invoice_line.yaml`：新增派生字段
  `price_diff_amount`（`derived: true`、`ui.editable: false`）
- `meta/tests/factories/_customer_invoice_helpers.py`：
  `insert_line_without_price_diff` / `line_price_diffs`
- 新增 `meta/tests/test_migration_v233.py`（3 用例）

## [x] T13 服务与守卫：改价原因必填 + 差额派生

**修改**
- `meta/services/customer_invoice_service.py`
  - `validate_line_write`：发货行 / 订单行分支调用 `_apply_price_override`
  - 新增 `_apply_price_override`：覆盖价 / 原因必填 / `price_source` 切换
  - `_finalize_line`：派生 `price_diff_amount`
  - `_negate_line`：红字行差额取负
- `meta/core/interceptors/customer_invoice_guard_interceptor.py`：
  `_LINE_NORMALIZED_KEYS` 加 `price_diff_amount`
- `meta/tests/test_customer_invoice_service.py`：新增 2 用例

## [x] T14 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v232.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_schema_api.py --port 3012
```

- `git add` 逐文件 + commit：
  `feat(billing): 发票行改价差额与原因必填（D13）`

---

# B4 行类型行为（spec §15）

## [x] T15 服务层行类型规则

**修改**
- `meta/services/customer_invoice_service.py`
  - 常量 `LINE_CATEGORY_MATERIAL / SERVICE / DISCOUNT`
  - `_resolve_line_type`：默认 `INV_ITEM`；校验 `scope_bo=customer_invoice` + `level=line`
  - `_apply_line_type_rules`：服务行空 item / 物料行必填 item / 折扣行负金额
  - `_finalize_line` 调用上述规则；红字行豁免金额方向校验
- `meta/tests/factories/_customer_invoice_helpers.py`：`set_order_line_item` / `type_id`
- `meta/tests/test_customer_invoice_service.py`：新增 6 用例

## [x] T16 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_schema_api.py --port 3012
```

- `git add` 逐文件 + commit：
  `feat(billing): 发票行类型行为（服务行空物料、折扣行负金额）`

---

# B5 独立贷项入口（spec §16）

## [x] T17 服务层 create_credit_from_invoice + 过账方向修正

**修改**
- `meta/services/customer_invoice_service.py`
  - 新增 `create_credit_from_invoice`：原单须 posted、无重复贷项 / 红字、
    无活跃核销、贷项日期 ≥ 原过账日、可按 `line_ids` 选行
  - `submit` / `post` 对红字 / 贷项单跳过 `_assert_lines_available`
  - `post` 的 `_apply_billed` 方向：`-1 if _is_red(header) else 1`
- `meta/services/customer_invoice_actions.py`：`create_credit_from_invoice_handler`
- `meta/services/bo_action_registrations.py`：注册
  `customer_invoice.create_credit_from_invoice`（权限沿用 create）
- `meta/schemas/customer_invoice.yaml`：detail.actions「创建贷项」
- 测试：service 6 用例、action 3 用例、helpers `shipment_billed`

## [x] T18 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v232.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v233.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_schema_api.py --port 3012
```

- `git add` 逐文件 + commit：
  `feat(billing): standalone credit memo from posted invoice (B5)`

---

# B6 权限补齐与菜单分组（spec §17）

## [x] T19 权限 / 菜单 / 打印

**修改**
- `meta/migrations/v231__customer_invoice.py`：PERMISSIONS 扩到 7 个动作
  （新增 `print` / `credit_memo`）
- `meta/migrations/v234__customer_invoice_permissions_menu.py`：旧库补权限 +
  授予 admin/default；存在「应收」父菜单时挂载 `customer_invoice-list`
- `meta/services/bo_action_registrations.py`：贷项 action 权限改为
  `customer_invoice:customer_invoice_credit_memo`
- `meta/schemas/customer_invoice.yaml`：detail.actions 增加「打印」，
  「创建贷项」权限同步
- `src/components/common/DetailPage/DetailPage.vue`：`case 'print'` →
  `window.print()`
- 测试：`test_migration_v234.py` 3 用例；v231 / actions 断言更新；
  helpers 增加 menus 表与 `build_permission_file`

## [x] T20 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v232.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v233.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v234.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
```

- 前端 `npm run build`（DetailPage 变更）
- `git add` 逐文件 + commit：
  `feat(billing): invoice print/credit permissions and menu group (B6)`

---

# B7 doc_flow 反向边（spec §18）

## [x] T21 规则 + 服务写边

**修改**
- `meta/migrations/v235__customer_invoice_credit_doc_flow.py`（新建）
  - doc_flow_rule upsert `customer_invoice_to_credit_memo`
    （source_bo=target_bo=customer_invoice_line，source_qty_field=qty，pool=billing）
  - verify：规则存在且 status=active；rollback：删除规则
- `meta/services/customer_invoice_service.py`
  - 新增常量 `CREDIT_DOC_FLOW_RULE_ID = 'customer_invoice_to_credit_memo'`
  - `_write_doc_flow_edges`：行有 `original_invoice_line_id` 时写反向引用边
    （source=原行 id、target=当前行 id，qty/amount 取 abs），然后 continue
  - `reverse()`：插入红字行后调用 `_write_doc_flow_edges(red_header, red_lines)`
- 测试
  - `meta/tests/test_migration_v235.py` 3 用例：插规则 / 幂等 / 回滚
  - `meta/tests/test_customer_invoice_service.py` 2 用例：
    贷项过账与红冲各写一条引用边（monkeypatch attach_edge 捕获参数）

## [x] T22 回归 + 提交

```powershell
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_service.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_actions.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_guard.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_customer_invoice_schedule.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v231.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_migration_v235.py --port 3012
python d:\filework\test.py --root D:\filework\s8-billing-worktree --file meta/tests/test_schema_api.py --port 3012
```

- `git add` 逐文件 + commit：
  `feat(billing): doc flow reverse edges for credit memo (B7)`
