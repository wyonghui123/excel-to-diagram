# P2 收口：主数据生命周期消费端 / calc_result 真实单据链路 / 变式物料化

> 版本 v1.0（2026-10-30）· 状态：待批准
> 范围：仅 P2 三项。不改平台既有抽象，只补「声明有、消费无」的缝。
> 依据：`ARCHITECTURE_V3.md` §0.4.7 债务排序第 2/5 位 + 附录 A P2。

---

## 0. 结论先行

| 项 | 当前事实 | 定性 | 本 spec 处置 |
|---|---|---|---|
| 5 主数据生命周期 D1 消费端 | `item.status` 四态与状态机已定义；写入门禁走通用 `validate_value_helps`，但**只对声明了 `value_filter.status` 的字段生效** | 部分实现 | 加「引用字段台账测试」+ 缺口字段补 `value_filter`；补 draft 拒绝 / inactive 结算两组运行时测试 |
| 6 价格/税务端到端 | 价格链路已接线（草稿取价 → `calc_results`）；**行级结果 `level` 被写成 `header`**，违反 `calc_result.yaml` 语义；税务走金额快照、不在 `calc_result` 链；无真实单据集成测试 | 接线有缺陷 | 修 `level` 推导 + 存量数据修正（如有）+ 新增真实链路集成测试；税务口径写入文档 |
| 7 变式物料化 | v117 只落字段；全仓无消费者、无写入点；测试仅断言默认值 | 只有声明 | Phase 0 固化「未实现」事实并标注 `[计划]`；Phase 1/2 另立 spec（本 spec 不实现） |

---

## 1. 项 5：主数据生命周期 D1 消费端

### 1.1 事实（取证）

- `meta/schemas/item.yaml` L606-635：`status` ∈ `draft / active / frozen / inactive`；draft「不可被单据引用」；inactive「阻止新单据引用；老单据可继续结算」。
- 状态机：`activate_item`（draft/inactive → active）、`deactivate_item`（active/frozen → inactive，`preconditions: [reference_restrict]`），L654-686。
- 写入门禁唯一实现：`meta/core/value_help_accessor.py::validate_value_helps`（L78-134）——判据仅取自字段 `value_help.source.value_filter`，且需 `behavior.validation` 为真；**字段未声明 filter ⇒ 无约束**。
- 调用点：`meta/api/bo_api.py` L547（create）、L1213/L1235（update/批量）；`meta/services/manage_service.py` L340/L383/L597（Excel 导入/批量）。
- `meta/schemas/sales_order_line.yaml` 共 7 处 `value_filter`：`item_id` L196-205（`status: active`）、`tax_code_id` L425-427、发货点 L546-548、引用行 L735-736 等。
- 服务行特判：`meta/services/sales_order_guard_service.py` W2-SVC-2（L30-34、L445）——取 `value_help.value_filter.status`，未声明回落 `active`。
- 结算/金额链路：`meta/services/sales_order_amount_service.py` 只读 `tax_rates` 生效区间 + `tax_code.rounding`，**不对 item.status 做任何检查** ⇒「inactive 可结算」在代码上成立（属应为行为）。

### 1.2 缺口

1. 覆盖是「字段级 opt-in」：单据行引用主数据的字段若漏写 `value_filter.status`，draft/inactive 一律放行且无告警。
2. 无任何运行时测试证明「draft 被拒」与「inactive 老单据可结算」。
3. 平台层没有「哪些字段必须带状态过滤」的台账断言，缺口只能靠人眼。

### 1.3 决策

- **不新增运行期强制策略**（不在平台层对 `target_bo ∈ 主数据锚` 的字段自动注入 `status: active`）——会改变存量对象行为，且无法表达「某些字段允许 draft」。改为**测试台账 + 定向补声明**。
- 结算路径**不加** inactive 拦截；用测试固化该行为，防止后人误加。

### 1.4 变更清单（decision-complete）

1. 新增 `meta/tests/test_master_data_lifecycle_consumption.py`：
   - `test_all_document_reference_fields_declare_status_filter`：遍历 `registry` 全对象，凡 `bo_sub_category ∈ {document, master_data_detail}` 且字段 `value_help.source.target_bo ∈ {item, party, org, location, uom, currency, tax_code, territory, item_group, price_list, rate_table}` 者，断言 `value_help.source.value_filter` 含 `status` 或 `status__in`；豁免名单以模块级常量 `STATUS_FILTER_EXEMPT = {('object','field'): '理由'}` 白名单维护（初始为空）。
   - `test_draft_item_rejected_on_line_create`：临时 sqlite 建 `items` / `sales_order_lines`，插入 `status='draft'` 物料，调用 `validate_value_helps(registry.get('sales_order_line'), {'item_id': id})` → 返回非空错误；`active` → 空列表；`inactive` → 非空错误。
   - `test_inactive_item_settlement_not_blocked`：构造已确认订单行（`item_id` 指向后改为 `inactive` 的物料），调用 `SalesOrderAmountService.recompute_order(order_id)` → 不抛错，且 `tax_amount` 按 `tax_rates` 正常算出。
2. 按 1 的台账测试首跑报告，对缺口字段在对应 YAML 补 `value_filter.status: active`（仅单据/明细对象的主数据引用字段；`sales_order_line` 现有 7 处不动）。
3. 首跑若发现 `sales_order_line` 之外的关键单据对象缺声明 → 同一 PR 内补齐，不单独立项。

---

## 2. 项 6：价格 / 税务在真实单据上跑通 calc_result 链

### 2.1 事实（取证）

- 行级取价：`meta/services/sales_order_pricing_service.py::price_line`（L102-188）→ `pricing_determination_service.determine_line`（L244+）→ `pricing_service.price_line(persist=True)`。
- `determine_line` 组参 `common`（L341-354）含 `document_type='sales_order'`、`document_id`、`document_line_id`，**未传 `level`**；`pricing_service.price_line` 签名默认 `level="header"`（L337）。
- `calc_result.yaml` L155-176：`level` 语义「与 `document_line_id` 的空值一致」；`pricing_api.py` L225-240 强制一致性（仅 API 路径），内部服务路径无此校验。
- ⇒ 实际落库：行级结果 `level='header'` + `document_line_id` 非空，自相矛盾。
- 税务不在 `calc_result`：全仓无 tax 类 `calc_procedure`（grep `TAX_STD` / tax 过程零命中）；税额由 `sales_order_amount_service` 直接计算（税率生效区间 + 税码舍入方向），属「金额快照」。
- 测试现状：`meta/tests/test_sales_order_pricing_wire.py` 用 `_FakeDS` + `_StubDet`（L20-60、L94），**不落真实 `calc_results`**；全仓无「真实单据 → calc_results」断言。

### 2.2 决策

- **修 `level` 推导**（唯一源码修复点）：`pricing_service.determine` 的 `level` 参数改为 `Optional[str] = None`，按 `document_line_id` 推导；调用方显式传值且与 `document_line_id` 空值不一致 → 抛 `PricingError`（fail-fast，与 API 口径一致）。`pricing_determination_service.determine_line` 签名不变。
- **税务口径**：明确「税不走 `calc_result`」为既定设计，不改造成 tax 过程；在文档与测试中固化（税前/税/含税由金额服务写单据统计字段）。
- **存量数据修正**：新增 `meta/migrations/v159__fix_calc_result_level.py`——`UPDATE calc_results SET level='line' WHERE document_line_id IS NOT NULL AND level='header'`；`verify` 校验该反例数为 0；`rollback` 依据备份表回填。实施前先在 DB 副本计数，为 0 则跳过迁移并记录结论。

### 2.3 变更清单（decision-complete）

1. `meta/services/pricing_service.py`：`def determine(..., level: Optional[str] = None, ...)`；函数体首部：
   ```python
   derived = 'line' if document_line_id is not None else 'header'
   if level is None:
       level = derived
   elif level != derived:
       raise PricingError(...)
   ```
   受影响调用方核查：`pricing_api.py`（显式传值且已自校验，仍通过）、`pricing_determination_service.py`（未传 → 推导生效）；`grep -n "price_line(" meta/` 全量确认无其它显式误传。
2. 新增 `meta/tests/test_sales_order_pricing_e2e.py`：
   - 夹具：复用 `test_configuration_price.py` 的「registry yaml 建真表」模式，建 `items / sales_orders / sales_order_lines / rate_tables / rate_records / calc_procedures / calc_procedure_steps / calc_results / calc_details / currency / tax_codes / tax_rates`；插入 1 客户、1 active 物料、1 价目表 + 费率记录。
   - `test_line_price_persists_line_level_calc_result`：真 `PricingService` + 真 `PricingDeterminationService` 调 `SalesOrderPricingService.price_line(line_id, force=True)` → 断言 `calc_results` 恰 1 条 `document_type='sales_order' AND document_line_id=<line> AND level='line' AND status='active'`，`net_amount` 与 `calc_details` 步数一致。
   - `test_reprice_invalidates_previous_result`：再次 `price_line(force=True)` → 旧行 `status='invalid'`、active 仍为 1。
   - `test_tax_is_amount_snapshot_not_calc_result`：设 `tax_code` + `tax_rates` 生效区间，调 `SalesOrderAmountService.recompute_order` → 行/抬头 tax 正确；断言 `calc_results` 无新增税相关行（固化口径）。
   - `test_confirmed_order_tax_snapshot_immutable`：确认后改 `tax_rates` → 重算不改变已确认金额（快照语义）。
3. `docs/ARCHITECTURE_V3.md` §0.4.2 L4 行「定价/税务链路尚未在真实单据跑通」改为实测口径（价格已验、税务为金额快照）；附录 A 对应条目降为 `[事实]`（仅在 2 通过后改）。

---

## 3. 项 7：变式物料化（`config_materialize_policy` + `variant_item_id`）

### 3.1 事实（取证）

- `meta/migrations/v117__configuration_price_and_materialize_fields.py`：新增 `items.config_materialize_policy`（off/manual/auto，默认 off）与 `configurations.variant_item_id`（可空，FK→items）。
- 全仓 grep：仅迁移、种子（一律写 `'off'`）、测试断言默认值；**无任何读取/写入消费点**。
- `meta/tests/test_configuration_price.py` L804/L807 只断言默认 `off` / `None`。
- `ARCHITECTURE_V3.md` L680-685 / L857-869 已列为缺口。

### 3.2 决策

- **本 spec 不实现物化**。只做 Phase 0：把「未实现」变成可验证事实，防止后续误判已接线。
- Phase 1（manual）/ Phase 2（auto）另立 spec，边界见 3.4。

### 3.3 变更清单（decision-complete，Phase 0）

1. 新增 `meta/tests/test_configuration_materialize_inert.py`：
   - `test_policy_defaults_to_off`：`items` 建表后默认值 `off`。
   - `test_manual_policy_does_not_write_variant_item_id`：物料置 `manual`，走配置解算/匹配服务后断言 `configurations.variant_item_id` 仍 `NULL`（固化「声明未消费」）。
   - `test_variant_item_id_has_no_writer`：对 `meta/` 源码做文本断言：除 `v117` 迁移与测试外，无 `UPDATE configurations SET ... variant_item_id` 语句。
2. `docs/ARCHITECTURE_V3.md` L680-685 / L857-869：`[缺口]` → `[计划]`，写明「Phase 0 已固化未实现事实；Phase 1 manual 物化未立 spec」。

### 3.4 Phase 1 边界（供后续 spec，不在本 spec 实施）

> Phase 1 已另立并细化：[2026-10-30-variant-item-materialization-spec.md](../../superpowers/specs/2026-10-30-variant-item-materialization-spec.md)。
> 以新 spec 为准，本小节以下内容已被修订（编码改「模型号+序号」、重复调用由「拒绝」改「幂等复用」、入口由 REST 端点改「配置实例动作」）。

- 新增 `meta/services/configuration_materialize_service.py::materialize(configuration_id)`：
  - 前置：`configurations.solved_at` 非空、`variant_item_id` 为空、模型物料 `config_materialize_policy ∈ {manual, auto}`；否则拒（`MATERIALIZE_NOT_ALLOWED` / `ALREADY_MATERIALIZED`）。
  - 物料化：`items` 新行——`code = model.code + '-' + configuration.code`（无 code 用 id）、`name = model.name + ' / ' + 配置摘要`、`item_type/base_uom/purchase_uom/sales_uom` 继承模型、`status='draft'`（走签发流程）、`config_materialize_policy='off'`（防递归）；回写 `configurations.variant_item_id`；落审计。
  - API：`POST /api/v1/configurations/<id>/materialize`（`configuration_api.py`）+ 权限动作 `configuration:configuration_materialize`（权限种子迁移）。
- 验收：off 拒绝、manual 生成 1 个 draft 变式物料、重复调用拒绝、审计可查。
- Phase 2（auto）：解算成功后自动触发同一 service，属事件化改造，范围外。

---

## 4. 验收与验证命令

铁律：禁 pytest，唯一入口 `python d:\filework\test.py`。

```powershell
python d:\filework\test.py --single meta/tests/test_master_data_lifecycle_consumption.py
python d:\filework\test.py --single meta/tests/test_sales_order_pricing_e2e.py
python d:\filework\test.py --single meta/tests/test_configuration_materialize_inert.py
python d:\filework\test.py --single meta/tests/test_sales_order_pricing_wire.py
python d:\filework\test.py --single meta/tests/test_pricing_service.py
python d:\filework\test.py --single meta/tests/test_configuration_price.py
```

迁移（可选，先副本验证）：

```powershell
python meta/migrations/v159__fix_calc_result_level.py <db_copy>
```

完成判据：
- 三个新测试文件全绿；
- `test_sales_order_pricing_wire.py` 与 `test_pricing_service.py` 零回归；
- DB 副本上 `document_line_id IS NOT NULL AND level='header'` 反例数 = 0（迁移后）。

## 5. 风险与回滚

| 风险 | 处置 |
|---|---|
| `level` fail-fast 触发未知内部调用方 | 实施前 `grep -n "price_line(" meta/` 全量核对；`test_pricing_service.py` 回归 |
| v159 存量修正误伤头级行 | 条件严格限定 `document_line_id IS NOT NULL`；备份表留 id 列表；rollback 回填 |
| 台账测试口径过严（豁免对象多） | 豁免用白名单常量显式列举理由，不做模糊豁免 |
| Phase 0 文本断言与源码格式耦合 | 断言只匹配 `variant_item_id` 赋值语句，不匹配注释 |

## 6. 需批准时确认的决策点

1. 项 6 是否接受 `pricing_service.determine` 的 `level` 默认值由 `"header"` 改为 `None`（推导）——影响所有未显式传 `level` 的调用方；本 spec 判断应改。
2. 项 6 存量修正是否落为迁移 v159（还是仅在文档记录现状）。
3. 项 7 是否只做 Phase 0（本 spec），Phase 1/2 另立 spec。
