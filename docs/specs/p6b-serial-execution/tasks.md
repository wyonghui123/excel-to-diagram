# P6b 序列号执行层 · 任务清单

> 依据：`docs/specs/p6b-serial-execution/spec.md`（v1.1，已确认）
> 迁移：**无**（v202 三表 + 枚举已齐；三张单据行 `serial_no` 由 YAML 声明 + `sync_schema_from_meta` 补列）
> 测试入口：`python d:\filework\test.py --single <path>`，禁止 pytest

## 任务依赖

```
T1 服务扩展（唯一改动点 serial_number_service.py）
  ├── T2 调拨接线（FR-001/002）
  ├── T3 调整接线（FR-002/003/004/009）
  ├── T4 盘点接线（FR-005/006）
  ├── T5 发货建档（FR-007，服务内部）
  └── T6 拦截器收口（FR-008）
        ↓
T7 新增/扩展测试
T8 全量回归 + 文档收口
```

---

## T1 扩展 `meta/services/serial_number_service.py`

- [x] 1.1 新增常量：`DOC_TRANSFER='transfer_order'`、`DOC_ADJUSTMENT='inventory_adjustment'`、`DOC_COUNT='inventory_count'`、`DOC_RETURN='return'`、`QUALITY_TRANSITIONS`（`unrestricted↔inspection↔blocked`，禁止自反）。
- [x] 1.2 `link_serials(...)`：按 `serial_no` 解析（须同 item/org）；`direction='in'` 且 `create_missing=True` 时建 `defined` 壳号（`source_type='opening'`），再 `_ensure_link`；返回 `{'linked': n}`。
- [x] 1.3 `precheck_transfer_ship(transfer_order_id, lines)`：号数 = `lines[line_id]`；号必须 `in_stores` 且属调出组织（`transfer_orders.from_org_id`）。
- [x] 1.4 `register_transfer_ship(transfer_order_id, lines, event_key, txn_date=None)`：逐号写 `transfer_out`（`usage in_stores→in_transit`，`org_from_id=from_org_id`，`location_from_id=from_location_id or serial.current_location_id`），`inventory_transaction_id=_find_inv_tx(event_key, str(line_id))`；主档 `in_transit` + `current_location_id=NULL`；`(serial_id,'transfer_out','transfer_order',order_id,line_id)` 幂等。
- [x] 1.5 `precheck_transfer_receipt` / `register_transfer_receipt(transfer_order_id, lines, event_key, txn_date=None)`：仅契约实现；`lines` 项含 `line_id/qty/to_org_id/to_location_id`；写 `transfer_in`（`in_transit→in_stores`）并迁 `org_id` / `current_location_id`；无原事件时 WARNING 跳过。
- [x] 1.6 `precheck_adjustment(adjustment_id)`：按 `inventory_adjustments.adjustment_type` 逐行校验，错误码按 spec §8。
- [x] 1.7 `register_adjustment(adjustment_id, event_key=None)`：
  - `qty_decrease` / `scrap`：`in_stores→scrapped`，写 `scrap`，置 `scrapped_at`，写 `direction='out'` 链接；
  - `status_transfer`：只切 `quality_status`，写 `status_change`（`quality_from/quality_to`），不写链接、不动 `usage_status`、不同步批次；
  - `qty_increase` / `opening`：建号或激活 `defined`，`in_stores` + 行 `to_stock_status` + 行/头库位，写 `adjust` 与 `direction='in'` 链接；
  - `count_difference`：只做事件（不复制盘点链接）。
- [x] 1.8 `precheck_count(count_id)`：`variance≠0` 行号数 = `|variance|`；盘亏号须 `in_stores`、质量 = 行 `stock_status`、组织/库位 = 行范围；盘盈号不得与主档重复。
- [x] 1.9 `register_count(count_id, event_key=None)`：盘亏写 `scrap` + `scrapped`；盘盈建 `opening` 号 → `adjust` → `in_stores`；回填 `inventory_transaction_id`；盘点链接保留不删。
- [x] 1.10 `return_serial(serial_id, location_id=None, to_stores=False)`：`issued→returned` 写 `return`；`to_stores=True` 再 `returned→in_stores`。
- [x] 1.11 `change_quality_status(serial_id, to_quality, reason='', doc=None)`：三值白名单 + `scrapped` 拒绝 + 写 `status_change`。
- [x] 1.12 修改 `_precheck_line`：`require_on_issue=1 & require_on_receipt=0` 且无 link / 无 `serial_no` 的发运行跳过数量前置校验（FR-007）。
- [x] 1.13 修改 `_register_shipment_line`：上述组合按 `qty` 建 `source_type='issue_created'` 号（`source_doc_type='shipment'`、`source_doc_id`），再走 `ship`；重复/超长 → `SERIAL_ISSUE_CREATE_FAILED`。
- [x] 1.14 修改 `reverse_serial_event`：同时回退 `quality_from/quality_to`；已有反向事件（`remark LIKE '反冲%'`）幂等跳过；找不到原事件只 WARNING（`SERIAL_REVERSE_SOURCE_MISSING`）。

## T2 调拨接线 `meta/services/transfer_order_service.py`

- [x] 2.1 `_post_ship_inventory` 内 `InventoryPostingService.post(entries, source)` 成功后：`serial_schema_ready(self.ds)` 为真则 `register_transfer_ship(header, items, event_key, ship_date)`。
- [x] 2.2 `SerialNumberError` 转 `TransferOrderError(str(e), field_name=e.field_name, rule=e.rule)`，连同数量账整体回滚。

## T3 调整接线 `meta/services/inventory_adjustment_service.py`

- [x] 3.1 `post`：`posting.post(...)` 成功后、`UPDATE status=posted` 前调用 `register_adjustment(header['id'], 'adjustment:%s' % adjustment_no)`；`serial_schema_ready` 为真才启用。
- [x] 3.2 `SerialNumberError → InventoryError(error.rule, str(error))`（不吞错，整体回滚）。
- [x] 3.3 `reverse`：`posting.reverse(...)` 后对每个 `tx_id` 调 `reverse_serial_event(tx_id)`；结果不回写数量账。

## T4 盘点接线 `meta/services/inventory_count_service.py`

- [x] 4.1 `submit`：状态写入前 `precheck_count(count_id)`；`SerialNumberError → InventoryError(rule)`。
- [x] 4.2 `post`：`posting.post(...)` 成功后调用 `register_count(count_id, 'count:%s' % count_no)`（同事务）。
- [x] 4.3 `cancel`：仅删 `document_serial_links(doc_type='inventory_count', doc_id=count_id)`，不写事件。

## T5 发货建档（FR-007）

- [x] 5.1 全部落在 `SerialNumberService`（T1.12/T1.13），`meta/services/shipment_service.py` 不改接线。
- [x] 5.2 自动号格式 `AUTO-{delivery_no}-{line_id}-{seq}`，长度 ≤ 64；撞号重试 3 次，仍失败抛 `SERIAL_ISSUE_CREATE_FAILED`。

## T6 拦截器收口 `meta/core/interceptors/serial_number_guard_interceptor.py`

- [x] 6.1 `crud_update` 且 `quality_status` 值变化：调用 `change_quality_status(serial_id, new, reason=params.get('remark') or '序列号质量状态变更')`，然后放行持久化（写入同值）。
- [x] 6.2 `usage_status` 直接变更仍拒绝（沿用 P6a）；`scrapped` 号任何修改拒绝。
- [x] 6.3 `SerialNumberError → ValidationFailedError`（沿用现有映射）。

## T7 测试

- [x] 7.1 新建 `meta/tests/test_serial_transfer_posting.py`：内存库需含 `transfer_orders(from_org_id/from_location_id/order_no)`、`transfer_order_lines(serial_no VARCHAR(200))`、v202 三表、`inventory_transactions`；覆盖号数/组织/状态、`transfer_out` 事件、桥接、`transfer_in` 迁组织、回滚。
- [x] 7.2 新建 `meta/tests/test_serial_adjustment_count_posting.py`：用 v203 `TABLES` DDL + 手动加 `serial_no` 列；覆盖状态转移、减少/报废、增加/期初、盘盈/盘亏、数量不符、幂等。
- [x] 7.3 扩展 `meta/tests/test_serial_number_service.py`：质量白名单、`scrapped` 拒绝、`return_serial`、`link_serials`、`reverse_serial_event` 质量回退。
- [x] 7.4 扩展 `meta/tests/test_serial_tracking_posting.py`：`issue_created` 建档、`require_on_issue` 数量不符仍拒绝。

## T8 回归与文档

- [x] 8.1 逐文件运行 T7 的 4 个文件，全绿。
- [x] 8.2 回归：`test_inventory_adjustment_service.py`、`test_inventory_count_service.py`、`test_inventory_counting_freeze.py`、`test_inventory_adjustment_schema.py`、`test_serial_number_schema.py`。
- [x] 8.3 本文件勾选完成；spec §12 与实现一致；如发现口径偏差（如 TBD-4 壳号时点），先改 spec 再改代码。
- [x] 8.4 不 commit（等待用户指令）。

## 完成判定

1. 新增 2 个测试文件 + 2 个扩展文件全绿；
2. P6a / INV-4 回归无新增失败；
3. 所有 P6b 事件（除纯 `status_change`）都带 `inventory_transaction_id` 且可反查；
4. 重复过账、重复登记、重复红冲均不产生重复事件。
