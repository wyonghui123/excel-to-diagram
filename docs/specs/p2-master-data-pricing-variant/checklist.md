# Checklist — P2 收口（项 5 / 6 / 7）

> 逐项验证后才可勾选。测试一律 `python d:\filework\test.py --single <file>`，禁 pytest。

## 项 5 — 主数据生命周期消费端

- [x] 引用字段台账测试存在且通过：遍历 document / master_data_detail 对象的 `target_bo ∈ 主数据锚` 字段，全部声明 `value_filter.status|status__in`，`gaps == []`
- [x] draft 物料在单据行写入时被拒（`validate_value_helps` 返回错误）
- [x] inactive 物料在**新建**行时被拒
- [x] active 物料正常放行
- [x] inactive 物料在**既有单据结算**时不被拦截（`SalesOrderAmountService` 正常算出税额）

## 项 6 — calc_result 真实单据链路

- [x] `PricingService.determine` 的 `level` 默认 `None`，按 `document_line_id` 推导（有行 → `line`，无行 → `header`）
- [x] 显式传 `level` 且与 `document_line_id` 空值不一致时抛 `PricingError`
- [x] 真实链路测试：`price_line(force=True)` 落库 `calc_results` 恰 1 条 `level='line'` 且 `document_line_id` 非空、`status='active'`
- [x] 重算后旧结果 `status='invalid'`，active 仍为 1
- [x] 税务为金额快照：`calc_results` 无税相关新增行，`sales_order_lines` net/tax_base/tax_rate_percent/tax_amount/gross 与 `tax_rates` 生效区间一致
- [x] 已确认单据的税务快照不被税率变更影响
- [x] `test_sales_order_pricing_wire.py` / `test_pricing_service.py` / `test_pricing_api.py` 零回归
- [x] DB 副本统计 `document_line_id IS NOT NULL AND level='header'` 反例数已记录（>0 则 v159 迁移并验证 migrate/verify/rollback；=0 则跳过并记录）

## 项 7 — 变式物料化 Phase 0

- [x] `config_materialize_policy` 默认 `off`（建表/种子）
- [x] 物料置 `manual` 后走配置解算，`configurations.variant_item_id` 仍 `NULL`（固化未消费）
- [x] 源码文本断言：除 v117 迁移与测试外无 `variant_item_id` 写入点
- [x] `ARCHITECTURE_V3.md` 两处 `[缺口]` 改为 `[计划]` 并写明 Phase 0 已固化

## 收尾

- [x] spec §4 六条命令全部 exit 0
- [x] `docs/ARCHITECTURE_V3.md` §0.4.2 / 附录 A 为实测口径（含「已实现 / 存在但未接线 / 缺失」对照）
- [x] 无新增未提交的无关文件；spec 文档保留（本 spec 产出：3 测试 + v159 迁移 + spec 三文档 + ARCHITECTURE/pricing_service 修改；`scripts/service_manager.ps1`、`docs/superpowers/specs/2026-10-29-so-wave3/`、`test_arch_startup_collision_guard.py` 为本次之前的既有改动，按规范不回滚）
