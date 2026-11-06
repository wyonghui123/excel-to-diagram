# D6 采购退货（RTV）任务清单

> 规格：[spec.md](./spec.md) ｜ 权威依据：[spec-reversal-platform-2026-11-06.md](../spec-reversal-platform-2026-11-06.md) §11 / §12 D6
> 执行顺序按依赖排列；T1-T6 为后端主链，T7 为入口，T8 为回归与回填。

## [x] T1 迁移 v227

* 新建 `meta/migrations/v227__purchase_return_object.py`
* `upgrade()` 按规格 §7 顺序执行；`verify()` / `downgrade()` 齐全且幂等
* 验证：`python d:\filework\test.py --single meta/tests/test_purchase_return.py`（先跑迁移链）
* 完成判据：`type_definitions` 中 `RCV_RETURN=red`、`RETURN_PO`/`VENDOR_RETURN=return`；
  `received_qty` 列不变，`returned_qty`/`origin_*`/`return_reason`/`return_to` 存在

## [x] T2 Schema 声明同步

* 修改 `meta/schemas/receipt.yaml`、`purchase_order.yaml`、`purchase_order_schedule.yaml`、
  `demand_trace_graph.yaml`，内容见规格 §8
* 验证：YAML 可被加载（服务测试启动即校验）；`demand_trace_graph` 视图 SQL 与迁移逐字一致

## [x] T3 收货服务主链

* 修改 `meta/services/receipt_service.py`：规格 §3 第 1-8、10-11 项
* 关键新增：`_assert_category_consistency`、`_assert_return_limit`、
  `recompute_schedule_returned`、`_post_receipt_inventory` 的 `direction` 参数、
  退货边规则分流
* 验证：标准收货既有测试全绿（`test_receipt_service.py`）

## [x] T4 逆向原语与 doc_effect

* 修改 `meta/core/reversal_primitives.py`：新增并注册 `recompute_schedule_returned`
* 修改 `meta/schemas/receipt.yaml`：投影 + `edge.rule_ids`
* 验证：`test_receipt_reversal.py`、`test_reversal_platform.py`

## [x] T5 序列号出库事件

* 修改 `meta/services/serial_number_service.py`：
  新增 `TXN_RETURN_VENDOR='return_to_vendor'` 到 `TXN_TYPES`；
  新增 `precheck_receipt_return(receipt_id)` 与 `register_receipt_return(receipt_id, txn_by_line)`
* 验证：AC-RP-19（序列号退货出库 + 红冲回退）

## [x] T6 审批维度

* 修改 `meta/services/document_approval_service.py` 的 `_load_record`，
  注入 `document_category`（仅当记录含 `document_type_id`）
* 验证：AC-RP-16

## [x] T7 收货详情「退货」入口

* 修改 `meta/services/receipt_actions.py`：新增 `create_vendor_return_handler`
* 修改 `meta/services/bo_action_registrations.py`：注册 `receipt.create_vendor_return`
* 修改 `meta/schemas/receipt.yaml`：动作声明（`from_states: [posted]`）
* 验证：AC-RP-11 通过动作创建退货 PO + 退货收货草稿

## [x] T8 测试与回填

* 新建 `meta/tests/test_purchase_return.py`（9 例，规格 §9）
* 回归：`test_receipt_service` / `test_receipt_reversal` / `test_doc_flow_reconcile` /
  `test_demand_trace_graph` / `test_purchase_order*`
* 回填 `docs/specs/spec-reversal-platform-2026-11-06.md` §12 D6 标「✅ 已实施」+ 回归记录

## 完成判据

1. 规格 §9 的 9 个用例全绿；
2. 上述回归套件无新增失败；
3. `git status` 仅包含 D6 相关文件；
4. 规格 §12 D6 已回填。
