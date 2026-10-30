# Tasks — P2 收口（项 5 / 6 / 7）

> 执行前置：本 spec 经批准（含 §6 三个决策点）。
> 测试入口铁律：`python d:\filework\test.py`，禁 pytest。

## Phase 1 — 项 5 生命周期消费端

- [x] T5.1 新增 `meta/tests/test_master_data_lifecycle_consumption.py`（台账 + draft 拒绝 + inactive 结算三用例）
- [x] T5.2 首跑台账用例，导出缺口字段清单 → 结论：**gaps == []**（单据/明细对象的主数据引用字段已全部声明 status 过滤且写校验开启）
- [x] T5.3 对缺口字段在对应 YAML 补 `value_filter.status: active`（单据/明细对象的主数据引用字段）→ 无缺口，跳过
- [x] T5.4 `python d:\filework\test.py --single meta/tests/test_master_data_lifecycle_consumption.py` 全绿（5 passed）

## Phase 2 — 项 6 calc_result 真实单据链路

- [x] T6.0 前置核查：`grep -n "price_line(" meta/` 列出全部调用方（65 命中），确认无显式 `level` 误传；仅 `pricing_api.py` 传 `level` 且其自身已强制与 `document_line_id` 一致
- [x] T6.1 修改 `meta/services/pricing_service.py::determine`：`level` 默认 `None` + 按 `document_line_id` 推导 + 不一致抛 `PricingError`
- [x] T6.2 新增 `meta/tests/test_sales_order_pricing_e2e.py`（4 用例：行级落库 / 重算作废 / 税务快照 / 确认后不可变）→ 真链路（无桩）4 passed
- [x] T6.3 运行 T6.2 与回归：`test_sales_order_pricing_wire.py`（27 passed）、`test_pricing_service.py`（65 passed），连同 e2e 4 passed 全部 Exit 0
- [x] T6.4 DB 副本统计 `document_line_id IS NOT NULL AND level='header'` 反例数 → **28**（副本共 36 行；另 8 行为合规表头行）
- [x] T6.5 反例数 28 > 0 → 新增 `meta/migrations/v159__fix_calc_result_level.py`：副本首次 migrate 修正 28 行 / verify PASS；rollback 还原 28 行反例并删备份表；二次执行修正 0 行（幂等）
- [x] T6.6 `docs/ARCHITECTURE_V3.md` §0.4.2 / 附录 A 改为实测口径（L71/L73/L125/L128/L155/L573/L585/L588 共 8 处；CHANGELOG v3.12）

## Phase 3 — 项 7 变式物料化 Phase 0（明示未实现）

- [x] T7.1 新增 `meta/tests/test_configuration_materialize_inert.py`（3 用例）→ 3 passed（消费链用 ConfigurationMatchService）
- [x] T7.2 `docs/ARCHITECTURE_V3.md` L680-685 / L857-869 `[缺口]` → `[计划]`（§4.1 L685 / §5.6 L860 / §5.7 L871 三处，注明 Phase 0 由 3 passed 固化）
- [x] T7.3 运行 `python d:\filework\test.py --single meta/tests/test_configuration_materialize_inert.py` → 3 passed，Exit 0

## 收尾

- [x] T8.1 按 spec §4 全量命令复跑（含 `test_configuration_price.py`）→ 六条全 Exit 0：5 + 4 + 3 + 27 + 65 + 41 = **145 passed**，0 failed
- [x] T8.2 汇总「已实现 / 存在但未接线 / 缺失」对照表更新到 ARCHITECTURE 附录 A → 新增 §A.1（8 行对照，L898-911），CHANGELOG v3.13
