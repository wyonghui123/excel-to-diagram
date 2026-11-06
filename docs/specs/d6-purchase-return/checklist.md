# D6 采购退货（RTV）验收清单

> 规格：[spec.md](./spec.md) ｜ 任务：[tasks.md](./tasks.md)
> 验证时间：2026-11-06 ｜ 测试入口：`python d:\filework\test.py`

## 验收项（AC-RP-11 ~ AC-RP-19）

- [x] AC-RP-11 退货采购单 + `VENDOR_RETURN` 收货单可创建
  （`create_vendor_return_handler`；退货出库过账用例覆盖）
- [x] AC-RP-12 标准 PO 建退货收货 → `RC_CATEGORY_MISMATCH`
  （`prepare_header` 建单阶段校验）
- [x] AC-RP-13 退货出库过账：库存 -N、移动类型 `RETURN_TO_VENDOR`、边规则
  `receipt_line_to_return_out_txn`
- [x] AC-RP-14 `returned_qty += N`，`received_qty` 不变，原 PO 不重开
- [x] AC-RP-15 超可退量 → `RC_RETURN_OVER_LIMIT`
- [x] AC-RP-16 审批条件引用 `document_category` 生效
- [x] AC-RP-17 退货收货红冲：库存回补、`returned_qty` 回退、原退货行 `reversed`
- [x] AC-RP-18 原 PO 仍可继续新建普通 PO（不被重开）
- [x] AC-RP-19 序列号物料：退货出库写 `return_to_vendor` 事件；红冲后序列号回 `in_stores`

## 工程项

- [x] `v227__purchase_return_object.py` 迁移可幂等执行，`verify()` 返回 bool，`downgrade()` 可用
- [x] Schema 同步：`receipt.yaml` / `purchase_order.yaml` / `purchase_order_schedule.yaml` /
      `demand_trace_graph.yaml`，YAML 可加载且视图 SQL 与迁移一致
- [x] 逆向原语注册表含 `recompute_schedule_returned`（17→18）
- [x] BO 动作 `receipt.create_vendor_return` 已注册且带权限 `receipt:receipt_create_vendor_return`
- [x] 回归无新增失败：`test_receipt_service` / `test_receipt_reversal` / `test_receipt_schema` /
      `test_doc_flow_reconcile` / `test_demand_trace_graph` / `test_purchase_order*` /
      `test_document_approval` / `test_bo_action_*` / `test_reversal_platform`

## 已知既有失败（与 D6 无关）

- `test_serial_tracking_posting` 发运 4 例：内联 `shipment_lines` 缺 `project_task_id`（HEAD 既有）
- `test_yaml_single_source_of_truth` 10 例：仍断言已迁移的 `user_group` / `role_permissions`
