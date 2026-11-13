# 执行方案：采购发票金额链路 W2（内核钩子 + VI 薄子类）

> 依据：[采购发票对象模型 Spec v1.2](../specs/spec-vendor-invoice-object-model-2026-11-11.md) §22
> 前置结论：D-VI-27（金额计算复用 `SalesOrderAmountService` 内核，禁止第三套算术）
> 约束：测试只走 `python d:\filework\test.py`；金额舍入只走 `meta/core/rounding.py`；不新增金额服务文件

---

## 1. 范围与目标

本轮（W2）只做 **22.1 内核钩子扩展 + VI 薄子类 + 22.2 / 22.3 行头公式** 的落地骨架，不触碰匹配（W5）、税与费用行（W6）、调整单（W7）。

目标：

1. 内核 `SalesOrderAmountService` 增加两个可覆写钩子，**默认实现与现行 SO/PO 逐位一致（零回归）**。
2. 建立 `VendorInvoiceAmountService(SalesOrderAmountService)` 薄子类，只覆写加载 / 写回 / 两个钩子，算术零复制。
3. 补齐 A1-A5 单测（行/头公式、含税倒算、0 位币种、`rounding_diff`）。

### 1.1 明确不做

- 不改 `customer_invoice_service`（TBD-15，已登记）。
- 不新建 `vendor_invoice_amount_service.py` 纯函数服务。
- 不在 handler / interceptor / 前端复制任何公式。
- 不改 `vendor_invoice_match_service` 的匹配逻辑（属 W5，见 §6）。

---

## 2. 通用能力沉淀（本轮核心）

| # | 能力 | 沉淀位置 | 复用方 | 说明 |
|---|---|---|---|---|
| G1 | **行金额算术钩子** | `SalesOrderAmountService._line_amounts(...)` | SO / PO（默认路径 A）/ VI（路径 B + line_direct） | 输入 `qty / unit_price / price_includes_tax / tax_rate_percent / tax_rounding / decimals / sign / net_adjustment`，输出 `net / tax_base / tax / gross` |
| G2 | **头金额算术钩子** | `SalesOrderAmountService._header_amounts(...)` | SO / PO（默认 Σ 行）/ VI（supplier_gross + rounding_diff） | 输入 `sum_net / sum_tax / sum_gross / supplier_gross / decimals / rounding_tolerance`，默认只回三项 |
| G3 | **薄子类注入模式** | `VendorInvoiceAmountService` + 既有 `_PurchaseOrderAmountService` | 所有需要新单据金额的域 | 子类只覆写 `_load_* / _sum_lines / _write_* / 钩子`；算术永远继承 |
| G4 | **舍入唯一入口** | `meta/core/rounding.py::round_amount / round_by_mode` | 内核与所有子类 | 精度取 `currencies.decimal_places`，方向取 `tax_code.rounding`；禁止 `round(x, 2)` |

> 判断标准：**新增一种单据的金额 = 新增一个只有加载/写回的薄子类**，不是新增一个金额服务文件。这条同时作为 R-VI-33 的可执行判据。

---

## 3. 文件级改动清单（W2）

| # | 文件 | 改动 | 类型 |
|---|---|---|---|
| F1 | `meta/services/sales_order_amount_service.py` | 新增 `_line_amounts` / `_header_amounts`；`recompute_line` / `recompute_order` 改为经钩子计算；默认口径不变 | 改 |
| F2 | `meta/services/vendor_invoice_amount_service.py` | 新增 `VendorInvoiceAmountService(SalesOrderAmountService)`：覆写 `_load_line / _load_order / _sum_lines / _write_line / _write_order / _line_amounts / _header_amounts` | 新增 |
| F3 | `meta/schemas/vendor_invoice.yaml` | 头增 `supplier_gross_amount`（W2 只加此列；`rounding_diff` 已存在） | 改 |
| F4 | `meta/schemas/vendor_invoice_line.yaml` | 行增 `tax_rate_percent`（W2 只加此列；`price_source / price_trace` 属 W5） | 改 |
| F5 | `meta/migrations/v260__vendor_invoice_amount_columns.py` | 加两列：`vendor_invoices.supplier_gross_amount`、`vendor_invoice_lines.tax_rate_percent`（幂等 + verify + rollback 清值） | 新增 |
| F6 | `meta/tests/test_vendor_invoice_amount.py` | A1-A5（VI 子类级，8 条） | 新增 |
| F7 | `meta/tests/test_sales_order_amount.py` | 内核钩子零回归 + 含税路径单测（7 条） | 改 |
| F8 | `meta/services/vendor_invoice_match_service.py` | `_validate_amounts` 接入 VI 子类重算 | **延后到 W6**（本波接线会使既有 submit 用例金额被重算，属行为变更；等税模式确定后一次接入） |

依赖顺序：**F1 → F7（验证零回归）→ F5（先有列）→ F2 → F3/F4 → F6**。F8 延后 W6。

> 实际执行时调整为 F5 先于 F2：子类 `_load_order` 需要 `supplier_gross_amount` 列，
> 否则真实库 SELECT 会失败。

---

## 4. 钩子契约（F1 落地口径）

### 4.1 `_line_amounts`

```python
def _line_amounts(self, *, qty, unit_price, price_includes_tax=None,
                  tax_rate_percent=None, tax_rounding=None, decimals=2,
                  sign=Decimal('1'), net_adjustment=Decimal('0')) -> dict
```

| 条件 | 计算 | 返回键 |
|---|---|---|
| `price_includes_tax` 为真且 `tax_rate_percent` 非空（路径 B） | `gross = R(q×p×sign)`；`net = R(gross/(1+r/100))`；`tax = R(gross−net)` | `net_amount / tax_base_amount / tax_amount / gross_amount` |
| 其余（路径 A，默认） | `net = R(R(q×p×sign) + net_adjustment)`；`tax = R_tax(net×r/100)`；`gross = net + tax` | 同上 |

- 默认实现 = 现行 SO/PO 口径（`net_adjustment` 仅 SO 抬头折扣/附加费使用）。
- VI 子类在默认基础上补 `line_direct` 税额容差校验与 `price_includes_tax` 必填税率校验。
- 算术内**禁止**查询数据库；所有读库留在 `_load_*`。

### 4.2 `_header_amounts`

```python
def _header_amounts(self, *, sum_net, sum_tax, sum_gross, supplier_gross=None,
                    decimals=2, rounding_tolerance=None) -> dict
```

| 实现 | 返回 |
|---|---|
| 默认（SO/PO） | `{net_amount: R(sum_net), tax_amount: R(sum_tax), gross_amount: R(sum_gross)}`（**只三项**，避免污染 PO 的通用 UPDATE 列） |
| VI 覆写 | 上述三项 + `gross_amount = R(supplier_gross)`（非空时）+ `rounding_diff = R(gross − net − tax)`；超 `rounding_tolerance` 时由上层置 `exception` |

---

## 5. 数据模型与迁移（F5）

| 变更 | 类型 | 空 | 默认 |
|---|---|---|---|
| `vendor_invoices.supplier_gross_amount` | number(18,4) | 是 | NULL |
| `vendor_invoice_lines.tax_rate_percent` | number(9,4) | 是 | NULL |
| `vendor_invoice_lines.price_source` | string(20) | 是 | NULL（W5） |
| `vendor_invoice_lines.price_trace` | text | 是 | NULL（W5） |
| `type_definitions` 5 条 line 种子 | — | — | W6 |
| 5 条控制参数 | — | — | W5/W6（spec §22.10） |
| `vi_match_mode` 默认 | — | — | W5：`gr_based` → `po_based` |

回滚：列可 `ALTER TABLE ... DROP COLUMN`（SQLite ≥ 3.35）；本次 v260 采用「清值保留列」（与 v259 一致）。种子与参数默认值在对应波次迁移中回滚。

---

## 6. 后续波次（本轮不执行）

| 波次 | 改动 | 关键文件 |
|---|---|---|
| W5 匹配 | ✅ 已完成（2026-11-13）：`_open_qty` 单一实现；删除 `min(qty, open_qty)` / `min(qty, available)`；`receipt_price` → `VI_PRICING_MODE_UNSUPPORTED`；四维参数解析走 `ControlParameterResolver`；默认 `po_based`（v261） | `vendor_invoice_match_service.py`、`sales_order_amount_service.py`（`net_unit_price`）、`meta/schemas/vendor_invoice.yaml`、`v261__vendor_invoice_match_mode_default.py` |
| W6 税与费用 | `_line_amounts` 接入 `line_direct` 容差；费用行 5 类种子；费用行不写边 | `vendor_invoice_amount_service.py`、`v260` |
| W7 调整单 | `_build_adjustment_lines` 改为调用 VI 子类重算（删 `round(...,2)` 与比例缩放）；`rounding_diff` 同步 | `vendor_invoice_match_service.py` |

---

## 7. 测试矩阵映射（spec §22.13）

| # | 场景 | 落点 | 本轮 |
|---|---|---|---|
| A1 | 不含税 `q10 p100 r13 d2` | `test_vendor_invoice_amount.py` | ✅ |
| A2 | 含税 `q3 p113 r13 d2` | 同上 | ✅ |
| A3 | 含税缺税率 → `VI_TAX_RATE_REQUIRED` | 同上 | ✅ |
| A4 | `d=0` JPY 1001.4 → 1001 | 同上 | ✅ |
| A5 | 供应商总额 1130.05 vs 行 1130.00 → `rounding_diff=0.05` | 同上 | ✅ |
| A6 | PO 价 100 / 含税 113 匹配通过 | `test_vendor_invoice_match.py` | ✅ W5 |
| A7 | 可开票 10 / 发票 12 → `VI_QTY_EXCEEDED` | 同上 | ✅ W5 |
| A8 | `receipt_price` → `VI_PRICING_MODE_UNSUPPORTED` | 同上 | ✅ W5 |
| A9 | 调整单改价 100→110 q5 | `test_vendor_invoice_adjustment.py` | ✅ W7 |
| A10 | 调整单 `qty=0 net=-50` | 同上 | ✅ W7 |
| A11 | 运费行 50(6%) + 物料 1000 | `test_vendor_invoice_charge_line.py` | ✅ W6 |
| A12 | 费用与 PO 附加费差 10 | 同上 | ✅ W6 |

回归基线：改动 F1 后先跑 `python d:\filework\test.py --file meta/tests/test_sales_order_amount.py`，再跑采购订单相关金额测试，确认默认路径逐位不变。

---

## 8. 执行检查点

1. F1 落盘 → F7 单测通过（SO 默认路径零回归 + 含税路径 A2）。
2. F2 落盘 → F6 中 A1-A5 通过。
3. F5 迁移 → `meta/tests/migrations/test_vendor_invoice_migrations.py` 增补断言。
4. F8 接线后跑 `meta/tests/test_vendor_invoice_adjustment.py` + `meta/tests/services/test_vendor_invoice_match.py`，确认既有行为不变（W7 前只接计算，不改匹配）。

### 8.1 本轮执行结果（2026-11-12，W2）

| 步骤 | 结果 |
|---|---|
| F1 内核钩子 | ✅ `_line_amounts` / `_header_amounts` 落盘，默认路径与 SO/PO 逐位一致 |
| F7 内核单测 | ✅ `test_sales_order_amount.py` 19 passed（新增 7 条）；PO 金额 + 舍入回归通过 |
| F5 迁移 v260 | ✅ 两列落盘；幂等 / verify / rollback 断言通过（迁移测试 7 passed） |
| F2 VI 薄子类 | ✅ `VendorInvoiceAmountService`：算术零复制，只覆写加载 / 写回 + 两个钩子 |
| F3/F4 Schema | ✅ 头 `supplier_gross_amount` / 行 `tax_rate_percent` |
| F6 VI 单测 | ✅ `test_vendor_invoice_amount.py` 8 passed（A1-A5 + 端到端写回） |
| 既有 VI 回归 | ✅ match / guard / adjustment / reversal / migrations 共 69 passed |
| F8 接线 | ⏸ 延后 W6（税模式与 line_direct 确定后统一接入，避免本波改变既有 submit 行为） |

### 8.2 W5 执行结果（2026-11-13）

| 项 | 结果 |
|---|---|
| 可开量单一口径 | ✅ `_open_qty(schedule_id, mode, receipt_line_id)` 为唯一实现；po_based 用 `promised − returned − consumed(billing)`，gr_based 用 `qty_invoiceable − consumed(ap_match)`；五处调用点全部改走该函数 |
| 去静默截断 | ✅ 删除 `min(qty, open_qty)` / `min(qty, available)`；超量分两级：`qty > open + 容差` 且未 override → `VI_QTY_EXCEEDED`（硬错误，不落库）；`open < qty ≤ open + 容差` → `match_status='exception'` 不写边；override 显式放行按**全额**写边 |
| 红冲 FIFO | ✅ 贷项/取消按 `_find_active_edges`（ORDER BY rowid）逐条冲减；总量超余量 → `VI_RED_QTY_EXCEEDED`，不再按单边封顶 |
| 价格模式 | ✅ `receipt_price` → `VI_PRICING_MODE_UNSUPPORTED`（删除 `REASON_RECEIPT_PRICE_MODE` 降级路径） |
| 含税价归一 | ✅ 比较用不含税单价：内核新增 `SalesOrderAmountService.net_unit_price()`（复用 `_line_amounts`，无第二套算术）；VI 侧 `_net_unit_price` 取 `price_includes_tax` + 税率（行优先，缺省按 `tax_code_id` 查 `tax_rates`）与币种精度 |
| 四维参数 | ✅ 删除本地 `_DIM_WEIGHTS` 打分，改走 `ControlParameterResolver.resolve`；dims 用 `or 0` 避免"行要求维度但调用方未提供"导致漏命中 |
| 默认匹配模式 | ✅ Schema `match_mode.default: po_based`；新增 `v261` 把 `vi_match_mode` 的 `default_value` 由 `gr_based` 改为 `po_based`（幂等 + verify + rollback），历史单据 `match_mode` 快照不回写 |
| 单测 | ✅ `test_vendor_invoice_match.py` 16 passed（A6/A7/A8 + 容差内 exception + 超冲拒绝 + 部分红冲 FIFO）；`test_vendor_invoice_migrations.py` 9 passed（新增 v261） |
| 既有 VI 回归 | ✅ match / guard / adjustment / reversal / amount + SO 金额共 77 passed |

**已知限制（Spec §22.8「创建时快照 vi_match_mode」未实现）**：采购发票创建走通用 BO create，无类型级 create hook；当前以 schema 默认值 + v261 参数默认值实现"新单据默认 po_based"，而非把四维解析结果快照进头表。后续若需按组织/单据类型差异化默认，应在 BO create 钩子落地后补快照，届时 v261 之后再加一版数据迁移回填。

### 8.3 二次检查结论（2026-11-13）

对 W5 落地做第二遍遗漏检查，结论分三类。

**A. 修复项（本轮已改）**

| # | 缺口 | 修复 |
|---|---|---|
| 1 | 枚举自洽：`match_mode.default=po_based` 但 `is_initial` 仍在 `gr_based`（违反平台「`is_initial` 必须与 `default` 一致」约定） | `vendor_invoice.yaml` 把 `is_initial: true` 移到 `po_based` 枚举项 |
| 2 | 单源快照落后：`generated_schema.sql` 缺 W2 的 `supplier_gross_amount` / `tax_rate_percent`，且 `match_mode DEFAULT` 仍 `gr_based` | `python -m meta.tools.sync_schema --generate` 重新生成（4 insertions / 2 deletions）；`--check --against snapshot` 全 0 漂移 |
| 3 | 错误契约外泄：匹配路径含税行缺税率抛裸 `SalesOrderAmountError`（API 层可能 500） | `_net_unit_price` 捕获并转 `VendorInvoiceError('VI_TAX_RATE_REQUIRED', field='tax_rate_percent')`；新增 `test_price_includes_tax_without_rate_rejected` |
| 4 | 舍入缺位：`price_diff_amount` / `price_diff_percent` 用原始浮点，未按 Spec §22.2 规则 7 舍入（`R((p−po_price)×q)` / 4 位） | 改走唯一舍入入口 `round_amount`（金额取币种 `decimal_places`，比例 4 位） |
| 5 | G-9 锚点快照可被行入参污染：`_normalize_line_anchors` 用 `if not result.get(...)` 条件回填，API 可注入 `po_unit_price` 绕过价格容差；`item_group_id` 允许为空锚 | 改为**源单为准**（schedule → PO 行 / receipt_line → PO 行均强制覆盖 `item_id` / `uom_id` / `line_type_id`，`po_unit_price` 有值即覆写）；新增 `_item_group_id` 由 `items` 表反查（表缺失时 try/except 兜底 None） |

**B. 保留项（已裁决，不改）**

| 项 | 保留理由 |
|---|---|
| `match_pricing_mode` 枚举保留 `receipt_price` | Spec §22.4 语义即「禁用：选择即报错」，选项保留 + 服务端硬错 `VI_PRICING_MODE_UNSUPPORTED` 才符合契约 |
| `match_exception_reason` 枚举保留 `receipt_price_mode` | DB CHECK 由 v252 固化；删除将造成 YAML 与生产库 CHECK 不可调和漂移。服务已不产出该值，属历史兼容值 |
| `v252` DDL `DEFAULT 'gr_based'` / `v253` seed `gr_based` | 历史迁移不可改（checksum）；由 v261 + create 时 `field.default` 覆盖 |

**C. 遗留项（后续波次）**

| 项 | 原因 |
|---|---|
| `vi_match_pricing_mode` 未 seed / 未解析 | Spec §22.10 新增参数，依赖 create 时快照能力（与 B 段已知限制同源）；当前 `match_pricing_mode` 走 schema 默认 `po_price`。方案见 §9.1 |
| 行 `price_source` / `price_trace` 未落列 | Spec §22.4 R-VI-27 追溯字段（P3），需先做表变更 + API 入参剔除，属独立波次。方案见 §9.2 |

**回归验证（本轮改动后全量重跑）**：match / amount / sales-order-amount / adjustment / guard / reversal-platform / migrations 共 **103 passed**（Exit 0），确认 `_normalize_line_anchors` 源单覆盖对 adjustment / credit memo / reversal 写边路径无副作用。

### 8.4 W6 执行结果（2026-11-13，税与费用行）

| 项 | 结果 |
|---|---|
| 迁移 v264 | ✅ `v264__vendor_invoice_charge_line_seed.py`：5 个 line 类型（GOODS material / SERVICE service / FREIGHT freight / SURCHARGE misc / DISCOUNT misc，仅 GOODS `is_default=1`）+ 4 参数（`vi_tax_mode` line_direct、`vi_tax_tolerance_abs` 0.01、`vi_freight_tolerance_abs` 0.00、`vi_po_tax_compare` false，均 `target_bo='vendor_invoice'`）；先查后插幂等 + verify（类型/`line_category`/默认唯一/参数 active）+ rollback（删 4 参数 → 5 类型） |
| 金额层 line_direct | ✅ `VendorInvoiceAmountService._line_amounts` 覆写：非含税 + `tax_mode=line_direct` + 有直录税额时，按 `tax_codes.rounding` 计算 `R_tax(net×r/100)` 与直录值比较，超 `vi_tax_tolerance_abs` 置 `tax_mismatch=True` 并采用直录税额重算 gross；`_resolve_tax_settings` 四维解析参数，异常兜底 `(line_direct, 0.01)` |
| 匹配层税额例外 | ✅ `_validate_line_tax`（invoice / debit_memo）：`tax_mismatch` → 行 `exception` + `VI_TAX_MISMATCH`，头聚合为 exception；已 override 行不覆盖；`submit` 按既有例外规则拒绝 |
| 费用行识别 | ✅ 按 `type_definitions.code ∈ {VI_LINE_FREIGHT, VI_LINE_SURCHARGE, VI_LINE_DISCOUNT}` 判定（不新增物理列），实例级缓存 `_line_type_cache` |
| 费用行匹配 | ✅ `_match_line` 早返回：不挂锚点、不参与数量/价格匹配（`qty_over_receipt=0.0`、`price_diff=None`）；`_validate_anchors` 新增「费用行不得挂 schedule / receipt 锚点」→ `VI_ANCHOR_CONFLICT` |
| 费用行核对 | ✅ `_validate_charge_reconciliation`（仅 `CATEGORY_INVOICE`）：费用行净额合计 vs PO 头 `header_surcharge_amount`（为 0 再用 `header_discount_amount`），超 `vi_freight_tolerance_abs` → 头 `exception` + `VI_FREIGHT_OVER_TOLERANCE` |
| 不写 doc_flow 边 | ✅ `_write_edges` 三条写边循环（红冲 / 调整单 / 正向 invoice）均跳过费用行（R-VI-29） |
| 测试 | ✅ 新增 `meta/tests/test_vendor_invoice_charge_line.py` 7 passed（A11 金额 1050/133/1183、容差内外税额、A12 超差头例外、费用行无边、锚点拒绝）；migrations 11 passed（新增 v264 幂等/回滚）；match / amount / adjustment / charge 64 passed；SO 金额 19 passed |

**偏差登记**

| # | 偏差 | 原因 |
|---|---|---|
| 1 | 金额层**不抛** `VI_TAX_MISMATCH`，改为返回 `tax_mismatch` 标志并采用直录税额 | Spec §22.12 把税额不符定义为**可 override 的匹配例外**；若金额层在保存/重算时抛错，行永远无法落库形成 exception，也就永远无法被 override |
| 2 | 费用行 vs PO 头核对限定 `CATEGORY_INVOICE`，PO 由非费用行 `schedule_id → order_id` 反查 | 费用行本身无锚点（§22.6），贷项/调整单的符号语义与正票不同，先只覆盖正票，避免红冲/调整场景误报 |
| 3 | 费用行排除出 `_validate_price_source_consistency` 的 sources 判定 | 物料行走 receipt 锚点归一为 `po`、费用行为 `manual`，若不排除会把正常组合误判为 `price_source_inconsistent`（A12 实测） |
| 4 | `vi_po_tax_compare` 仅 seed，未接消费逻辑 | Spec §22.10 标注为可选项；与 PO 行税额比对依赖调整单/红冲子类重算（W7），本轮只落种子与默认值 |

### 8.5 W7 执行结果（2026-11-13，调整单接入金额内核）

| 项 | 结果 |
|---|---|
| 子类新方法 | ✅ `VendorInvoiceAmountService.compute_adjustment_line(header, source, *, qty, unit_price, net_amount, tax_amount, direction)`：T1/T2/T3 三档统一走内核 `_line_amounts`，无第二套算术；`sign` 由 `direction` 显式给出（不再让 `recompute_line` 按 `document_category` 猜正负） |
| 比例缩放删除 | ✅ `_build_adjustment_lines` 整段重写，删除 `round(..., 2)` 与「按数量比例缩放原行金额/税额」；行 `net/tax/gross/tax_base` 全部来自内核返回值 |
| 税率快照与回退 | ✅ 行优先用源行 `tax_rate_percent`；缺失时按 `tax_code_id` 查 `tax_rates`（取 `invoice_date` 有效期）；仍缺失则用源行隐含税率 `abs(源税额)×100/源净额`（§22.7 G-4），不按金额比例；`tax_rate_percent` 快照保持 NULL，不伪造 |
| 头金额同事务重算 | ✅ 插入调整行后在同一事务内调 `recompute_order(adjustment_id)`，`net/tax/gross/rounding_diff` 由金额内核回写；不再手工求和、不硬编码 `rounding_diff=0` |
| 票面总额丢弃 | ✅ `_ADJUSTMENT_HEADER_DROP` 新增 `supplier_gross_amount`：原票票面总额不得覆盖调整单 gross（否则 `rounding_diff` 会被算成巨大值） |
| 空行拦截 | ✅ 调整行 `qty=0` 且 `net_amount=0` → `VI_ADJUSTMENT_EMPTY_LINE`（§22.5 规则 2）；自动整单模式仍静默跳过源行零数量零金额行（保持既有行为） |
| 调整行税额例外 | ✅ `_validate_line_tax` 类别集合扩展为 `invoice / debit_memo / adjustment`：T3 直录税额超 `vi_tax_tolerance_abs` 时落 `VI_TAX_MISMATCH` 例外（可 override，§22.12） |
| 测试 | ✅ `test_vendor_invoice_adjustment.py` 30 passed：A9 改价 100→110（qty 5 → net 550 / tax 71.5 / gross 621.5）、A10 纯金额 `qty=0 net=-50`（decrease，头 -50/-6.5/-56.5，不写红字边）、T1 数量调整按税率快照（net 20 / tax 2.6，非按原税额比例 2.0）、T3 直录税额超差 → `VI_TAX_MISMATCH`、空行拒绝、票面总额丢弃 + `rounding_diff` 重算 |
| 回归 | ✅ match 25 / amount 8 / charge_line 7 / guard 20 / reversal_platform 8 / migrations 11 / sales_order_amount 19，合计 **128 passed**（Exit 0） |

**偏差登记**

| # | 偏差 | 原因 |
|---|---|---|
| 1 | 显式 `net_amount` 优先于 `qty × unit_price`，`unit_price` 反算为 `|net|/qty`（qty=0 时为 0） | T3 语义是「净额直录」；同时兼容既有 `qty=4 + net=40` 用例，避免同一入参算出两个金额 |
| 2 | T1（仅 qty）强制走路径 A（不含税价基准），即使源行 `price_includes_tax=1` | Spec §22.5 T1 明确「单价取源行、税按路径 A 计算」；含税源行在 T1 下的净额可能与原行略有差异，属预期行为，已登记 |
| 3 | 隐含税率回退时 `tax_rate_percent` 保持 NULL | 隐含税率是从原行金额反推的近似值，写入快照会伪装成「明确税率」；保持 NULL 让下游能区分「未提供」与「提供」 |
| 4 | 自动整单模式跳过源行零数量且零金额行，不报 `VI_ADJUSTMENT_EMPTY_LINE` | 整单调整面对的是全部原行，原票可能存在合法的零金额占位行；只有调用方显式指定空行才视为错误 |

---

## 9. 遗留项实施方案（2026-11-13）

### 9.0 范围、原则与顺序

- 目标：关闭 §8.3 C 两项，使 Spec §22.10 / §22.4 / R-VI-27 契约闭环。
- 原则：仍是**平台通用能力**——`price_source` / `price_trace` 与销售侧 `customer_invoice_lines`（v244）保持同一模型与同一语义；不新增金额服务、不复制算术、不改历史迁移（v252 / v253 不动）。
- 依赖顺序（不可颠倒的两处）：
  1. **先有列再写值**：v262 加列 → `generated_schema.sql` 重生成 → 服务写值。
  2. **先有参数再解析**：v263 seed 参数 → 解析函数 → create 快照。
  3. 入参剔除与一致性校验放在服务写值之后（否则校验会读到空列）。
- 迁移编号：`v262__vendor_invoice_line_price_trace.py`（加列 + 历史回填）、`v263__vendor_invoice_pricing_mode_seed.py`（参数 seed）。两者互相独立，编号按执行顺序。

### 9.1 遗留①：`vi_match_pricing_mode`（seed + 解析 + 快照）

**决策 D1：头级快照，与 `vi_match_mode` 同构。**
Spec §22.10 写「快照到行」，但 §22.11 数据模型没有行级 `match_pricing_mode` 列；行级价格来源由 `price_source`（§9.2）承载。若为字面「行级模式」新增列，需先改 Spec 数据模型，本轮不做（列入待决）。依据：§22.4 要求「同一单据内价格来源必须一致」，单据级单值即天然一致。

| # | 落点 | 改动 |
|---|---|---|
| 1 | `meta/migrations/v263__vendor_invoice_pricing_mode_seed.py`（新增） | 照 v253 `_do_params` 模板：`code='vi_match_pricing_mode'`、`name='采购发票定价模式'`、`domain='procurement'`、`value_type='enum'`、`default_value='po_price'`、`target_bo='vendor_invoice'`、`status='active'`；desc：`po_price=按采购订单价 / manual=人工定价（需 override）`。幂等（按 code 先查后对齐）+ `verify`（断言 domain / status / default_value）+ `rollback`（按 code 删）。 |
| 2 | `vendor_invoice_match_service.py` 新增 `_resolve_match_pricing_mode(header)` | 与 `_resolve_match_mode`（L360-374）同构：头快照 ∈ `{po_price, manual}` → 直接用；否则 `ControlParameterResolver.resolve('vi_match_pricing_mode', {org_id, document_type_id})`；broad except / 非法值 → `PRICING_PO_PRICE`。 |
| 3 | `_match_line`（L813） | `pricing = _s(header.get('match_pricing_mode')) or PRICING_PO_PRICE` 改为 `pricing = self._resolve_match_pricing_mode(header)`。 |
| 4 | `vendor_invoice_guard_interceptor._guard_header` crud_create 分支（L126-138） | 新增 create 快照：`params['match_pricing_mode']` 为空时写入 `service._resolve_match_pricing_mode(params)`（创建期只有 `org_id` / `document_type_id` 两维，行级维度尚不可得）。`crud_update` 不改（快照只读）。红冲 / 调整单复制头字段已含 `match_pricing_mode`，自动继承原单。 |
| 5 | `meta/schemas/vendor_invoice.yaml` 的 `match_exception_reason` 枚举 | 新增 `price_source_inconsistent`（见 §9.2 一致性校验），否则前端展示缺失。 |

语义不变项（只补来源，不改行为）：`manual` 且行无 override → `MATCH_UNMATCHED` + `manual_pricing_required`；`receipt_price` → `VI_PRICING_MODE_UNSUPPORTED` 硬错。

验收：
- 参数命中 `manual`（org / 单据类型维度）→ 新单据头快照为 `manual`，匹配行为与显式传 `manual` 一致。
- 参数未配置 → 解析兜底 `po_price`，与现状逐位一致（零回归）。
- 空入参创建 → 头为 `po_price`，API 仍可正常建单（不因缺参数报错）。

### 9.2 遗留②：行 `price_source` / `price_trace`（加列 + 写值 + 入参剔除）

**Schema（`meta/schemas/vendor_invoice_line.yaml`，插在 `po_unit_price` 之后）**

| 字段 | 类型 | 空 | 约定 |
|---|---|---|---|
| `price_source` | `string(20)` | 是（NULL） | `enum_values: po / manual / adjustment`；`semantics.immutable: true`；`ui.editable: false`；默认 NULL |
| `price_trace` | `text` | 是（NULL） | JSON 快照；`semantics.immutable: true`；`ui.editable: false`；**不建索引**（Spec §22.11） |

**迁移 v262（`ALTER TABLE` + 回填）**

1. `PRAGMA table_info(vendor_invoice_lines)` 幂等判断后 `ADD COLUMN price_source VARCHAR(20)` / `ADD COLUMN price_trace TEXT`（均可空，无 DEFAULT）。
2. 历史回填（仅 `price_source IS NULL`，天然幂等；`price_trace` 无法重建，保持 NULL，不伪造快照）：
   1. 头 `document_category = 'adjustment'` 的行 → `adjustment`；
   2. `order_line_id IS NOT NULL` 的行 → `po`；
   3. 其余 → `manual`。
3. `verify`：两列存在且可空；回填后无 `price_source IS NULL` 的行；幂等复跑无变化。
4. `rollback`：两列置 NULL（保留列，与 v259 / v260 一致，不做 `DROP COLUMN`）。
5. 重新生成单源：`python -m meta.tools.sync_schema --generate`，再 `--check --against snapshot` 须 0 漂移。

**服务写入点（`vendor_invoice_match_service.py`）**

| 位置 | 改动 |
|---|---|
| `_normalize_line_anchors`（L761-797） | 返回前调用新私有 `_price_snapshot(header, result)`：有 PO 锚（`order_line_id` 且 `po_unit_price` 非空）→ `price_source='po'` + trace；无锚 → `manual`；**已为 `adjustment` 的行不覆盖**（调整行无锚点，避免被降级为 manual）。 |
| `_match_line` 返回体（L833 起两个分支） | 结果字典补 `price_source` / `price_trace`（取自 normalized line），否则 `_persist_line_result` 无处取值。 |
| `_persist_line_result`（L967-978） | UPDATE 列表加 `price_source = ?, price_trace = ?`。 |
| `_build_adjustment_lines`（L1462-1489） | `row.update` 写 `price_source='adjustment'`；`price_trace` = 原行 trace（JSON 解析失败则 `{}`）+ `original_line_id` + `snapshot_at` 覆写，PO 键（`po_id/order_line_id/schedule_id/po_unit_price`）整段保留（§22.4「PO 侧存在时整段嵌入」）。 |
| `_insert_lines`（L1581-1615） | 不改：按 DB 列过滤后自动复制。红字行保留原 `po/manual`（红冲复制的是原价格事实），非 `adjustment`。 |

**trace 结构与工具**

- 键固定：`{po_id, order_line_id, schedule_id, po_unit_price, price_source, snapshot_at}`；PO 侧不存在时省略 PO 键，只留 `{price_source, snapshot_at}`。
- `po_id` 由 `_order_line(order_line_id)['order_id']` 取；`snapshot_at` 用服务 `_now()`。
- 序列化统一 `json.dumps(..., ensure_ascii=False, sort_keys=True)`，空值写 `None`（不写空串）。

**入参剔除（R-VI-27 / G-9）**

- 落点：`VendorInvoiceGuardInterceptor._guard_line` 入口（L273-276 之后）新增 `_SERVER_OWNED_LINE_KEYS = ('po_unit_price', 'price_source', 'price_trace')`，对 `crud_create` / `crud_update` 的 `params` 逐键 `pop`（`crud_delete` 无入参，不受影响）。
- 范围说明（偏差登记）：`tax_rate_percent` / `price_includes_tax` **本轮不剔除**——前者取值依赖 §22.7 税查找（W6 `vi_tax_mode` 落地后收口），后者是 §22.4 明示的用户可编辑开关。W6 完成后把 `tax_rate_percent` 加入该集合，并在 §8.3 A 段补记。

**一致性校验（Spec §22.4）**

- 落点：`match()` 内 `_validate_source_policy`（L430）之后新增 `_validate_price_source_consistency(header, normalized)`。
- 规则：同一单据内 `price_source` 集合 ⊆ `{po, manual}` 且混用 → 行置 `MATCH_EXCEPTION` / `match_exception_reason='price_source_inconsistent'`，头聚合为 `exception`（不抛硬错，允许 override 流程）。
- 调整单整单 `adjustment`，不参与混用判定；`match_exception_reason` 列为 `VARCHAR(200)` 无 CHECK（v252 L67/L109），新增原因码**不需要迁移**，只需 §9.1 第 5 步补 YAML 枚举。

### 9.3 测试与 factory 同步

| 文件 | 改动 |
|---|---|
| `meta/tests/factories/_vendor_invoice_helpers.py` | `LINE_DDL` 来自 v252（不可改）→ 在 `make_env` 内按 v258/v259 模式追加幂等 ALTER：`price_source` / `price_trace`；`insert_line` 增加可选 `price_source=None, price_trace=None`。漏改会直接报 `no such column: price_source`。 |
| `meta/tests/services/test_vendor_invoice_match.py` | +5：po 行 `price_source='po'` 且 trace 六个键齐全；无锚行 `manual`；调整行 `adjustment` 且 trace 带 `original_line_id`；po+manual 混用 → `exception/price_source_inconsistent`；参数 `vi_match_pricing_mode='manual'` 解析生效。 |
| `meta/tests/test_vendor_invoice_guard.py` | +2：create / update 注入 `po_unit_price` / `price_source` / `price_trace` 均被剔除（断言落库值仍为服务端值）。 |
| `meta/tests/migrations/test_vendor_invoice_migrations.py` | v262：加列 + 回填口径 + 幂等 + verify + rollback；v263：seed + 幂等 + verify + rollback。 |
| `meta/tests/services/test_vendor_invoice_match.py`（既有 17 条） | 回归：normalized 结果新增两键不得影响 `_write_edges` / `_write_credit_red_edges`（dict 传递，无白名单拷贝，理论无影响）。 |

执行顺序与验证命令（唯一入口）：

```
python d:\filework\test.py --file meta/tests/migrations/test_vendor_invoice_migrations.py
python d:\filework\test.py --file meta/tests/services/test_vendor_invoice_match.py
python d:\filework\test.py --file meta/tests/test_vendor_invoice_guard.py
python d:\filework\test.py --file meta/tests/test_vendor_invoice_amount.py
python d:\filework\test.py --file meta/tests/test_vendor_invoice_adjustment.py
python d:\filework\test.py --file meta/tests/test_vendor_invoice_reversal_platform.py
```

另跑 `python scripts/lint_tests.py`（全量，不接受文件路径参数）。

### 9.4 风险与回退

| 风险 | 处置 |
|---|---|
| 历史行 `price_source` 只能近似回填，`price_trace` 不可重建 | 回填仅 `IS NULL`；trace 留 NULL 并在 UI 按「无快照」展示，不伪造数据 |
| 重跑匹配会把 `po ↔ manual` 按最新锚点改写 | 语义正确（锚点变化即来源变化）；唯一例外是 `adjustment` 必须保留，`_price_snapshot` 显式跳过 |
| 测试 helper DDL 与生产迁移不同步 | 先改 `make_env` ALTER，再跑 match / guard 测试；CI 以迁移测试兜底 |
| Spec §22.10「快照到行」与 §22.11 无行级列冲突 | 决策 D1（单据级快照 + 行级 `price_source`）；若 PM 要求字面行级，另开一版 Spec + 迁移（本轮不做） |
| 参数维度只到组织 / 单据类型（创建期无行） | 与 `vi_match_mode` 一致；行级 `line_type_id/item_group_id` 仅参与容差解析（`resolve_param`），不参与定价模式 |
| 回退 | v262 `rollback` 置 NULL 保留列；v263 `rollback` 删参数；服务层回退为「只读 schema 默认」，不依赖列是否为空（空值即无快照） |

### 9.5 执行结果（2026-11-13）

| 项 | 结果 |
|---|---|
| 遗留① 参数 seed | ✅ `v263__vendor_invoice_pricing_mode_seed.py`：`vi_match_pricing_mode`（enum / default `po_price` / target_bo `vendor_invoice`），幂等对齐 + verify + rollback |
| 遗留① 参数解析 | ✅ `_resolve_match_pricing_mode(header)`：头快照 → `ControlParameterResolver.resolve` → 兜底 `po_price`；`receipt_price` 保留快照直取，仍由 `_match_line` 抛 `VI_PRICING_MODE_UNSUPPORTED`（语义不变） |
| 遗留① create 快照 | ✅ Guard `_guard_header` crud_create：`match_pricing_mode` 为空时写入四维解析结果；红冲 / 调整单复制头字段自动继承 |
| 遗留① 枚举 | ✅ `vendor_invoice.yaml` `match_exception_reason` 增 `price_source_inconsistent` |
| 遗留② 迁移 v262 | ✅ 两列（`price_source VARCHAR(20)` / `price_trace TEXT`，可空）+ 历史回填（adjustment → po → manual，仅 `IS NULL`）；幂等 / verify / rollback 覆盖 |
| 遗留② Schema | ✅ `vendor_invoice_line.yaml` 在 `po_unit_price` 后加两字段（只读、immutable、无索引）；`sync_schema --generate` 重生成，`--check --against snapshot` 0 漂移 |
| 遗留② 写值 | ✅ `_price_snapshot`（normalize 末尾，adjustment 不覆盖）/ `_match_line` 两分支返回体 / `_persist_line_result` UPDATE / `_build_adjustment_lines` + `_adjustment_price_trace`（保留 PO 键整段） |
| 遗留② 入参剔除 | ✅ Guard `_guard_line` 入口 pop `po_unit_price` / `price_source` / `price_trace`（crud_create / crud_update）；`tax_rate_percent` / `price_includes_tax` 按方案留 W6 |
| 遗留② 一致性校验 | ✅ `_validate_price_source_consistency(header, normalized, results)`：po+manual 混用 → 未放通行 `exception/price_source_inconsistent`；调整单跳过；已 override 行保留 |
| factory | ✅ `make_env` 幂等 ALTER 两列；`insert_line` 可选两参数；新增 `seed_pricing_mode_param` |
| 单测 | ✅ match 25 passed（+6）/ guard 20 passed（+2）/ migrations 10 passed（+2）/ amount 8 / adjustment 24 / reversal 8 / SO 金额 19，全部绿 |
| lint | ✅ `scripts/lint_tests.py` 无新增项（既有 high=181 为存量） |
| 偏差登记 | `_validate_price_source_consistency` 落在 `match()` 结果回填之后并接收 `results` 参数（方案写的是 `(header, normalized)` 且位置在 `_validate_source_policy` 后）——因为冲销 / 补收 / 调整类行在 `_match_line` 内提前返回，只有回填阶段才能统一覆盖；规则与豁免口径不变 |