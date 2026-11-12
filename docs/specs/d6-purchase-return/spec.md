# D6 采购退货正向对象（RTV）实施规格

* 状态：**待审批**
* 日期：2026-11-06
* 权威依据：[spec-reversal-platform-2026-11-06.md](../spec-reversal-platform-2026-11-06.md) §11 / §12 D6
* 迁移号：**v227**（§11.7 的 v224 为旧编号；v224-v226 已被占用）
* 性质：正向对象补充，**不走** ReversalOrchestrator；退货出库的红冲仍由既有编排器接管

---

## 1. 决策

| 编号 | 决策 |
| --- | --- |
| D13 | `document_category` 三值化：`standard`（正向）/ `return`（业务退货，独立过账）/ `red`（红字纠错，不独立过账，必须有 `reversal_of_*`） |
| D16 | 退货必须可回指原单：`purchase_orders.origin_purchase_order_id` / `origin_receipt_id` |
| D17 | 原 PO 不重开（SAP 路线）：退货量记 `purchase_order_schedules.returned_qty`，`received_qty` 不变 |
| D18 | 退货出库复用 `receipt` 单据，`category='return'`、方向 `out`、移动类型 `RETURN_TO_VENDOR`；不新建 BO |
| D19 | 退货收货的库存红冲复用 `inventory_reverse_by_event`（方向自动翻转），不新增库存原语 |
| D20 | 红字收货单（`red`）仍禁止再次红冲 |

---

## 2. 数据模型

### 2.1 单据类型种子（`type_definitions`）

| code | name | scope_bo | level | document_category | 说明 |
| --- | --- | --- | --- | --- | --- |
| `RCV_RETURN`（已存在） | 红字收货单 | `receipt` | `header` | **`return` → `red`** | 仅红冲生成，不独立过账 |
| `RETURN_PO`（新增） | 退货采购单 | `purchase_order` | `header` | `return` | 退货业务单 |
| `VENDOR_RETURN`（新增） | 采购退货出库单 | `receipt` | `header` | `return` | 退货出库事实 |

同时新增编号序列 `RPO`（退货采购单）与 `RTV`（退货出库单），并绑定到对应类型的
`number_sequence_id`，格式沿用 v186 的 `{PREFIX}-{DATE:yyyymm}-{SEQ:6}`。

### 2.2 字段

| 表 | 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `purchase_orders` | `origin_purchase_order_id` | INTEGER NULL | NULL | 原采购订单 |
| `purchase_orders` | `origin_receipt_id` | INTEGER NULL | NULL | 触发退货的原收货单（可退量上限依据） |
| `purchase_orders` | `return_reason` | TEXT NULL | NULL | 退货原因 |
| `purchase_order_schedules` | `returned_qty` | REAL NOT NULL | 0 | 已退货量（独立口径，`received_qty` 对退货恒不变） |
| `receipts` | `return_to` | TEXT NOT NULL | `supplier` | 退货去向；本期仅 `supplier`，预留 `receiving` |

### 2.3 库存事务类型与边规则

* `inventory_transaction_types` 新增 `RETURN_TO_VENDOR`（`category='issue'`，`direction='out'`）。
* `doc_flow_rule` 新增 `receipt_line_to_return_out_txn`：
  `source_bo=receipt_line`、`target_bo=inventory_transaction`、`source_qty_field=qty`、
  `pool=inventory_return_out`。
* `v_demand_trace_graph.signed_qty` 增加分支：
  `rule_id IN ('shipment_line_to_return_in_txn', 'receipt_line_to_return_out_txn')` 时取 `-quantity`，
  红字再取反。`meta/schemas/demand_trace_graph.yaml` 的 `view_definition` 与迁移 SQL 必须逐字一致。

---

## 3. 服务改造（`meta/services/receipt_service.py`）

1. **常量**：新增 `DOC_CATEGORY_RED`、`RETURN_TXN_TYPE='RETURN_TO_VENDOR'`、
   `INBOUND_EDGE_RULE='receipt_line_to_inventory_txn'`、`RETURN_EDGE_RULE='receipt_line_to_return_out_txn'`；
   `DOC_CATEGORIES` 三值化；`_require_document_type` 接受三值。
2. **红字约束**：`prepare_header` / `prepare_transfer_header` / `prepare_work_order_header`
   仅在 `document_category == 'red'` 时要求 `reversal_of_receipt_id`（`return` 不再要求）。
3. **过账分流**：`post()` 中
   * `red` 直接拒绝独立过账（`RC_CATEGORY_INVALID`）；
   * `return` 走退货出库分支，`standard` 维持现有入库分支。
4. **类别一致性守卫**：新增 `_assert_category_consistency(order, doc_type)`。
   `red` 跳过；`standard` 要求来源 PO 类型类别为 `standard`；`return` 要求来源 PO 类型类别为
   `return`（`RC_CATEGORY_MISMATCH`）。
5. **退货行校验**：`_validate_line` 增加 `is_return`；退货行 `qty_rejected` 必须为 0
   （`RC_RETURN_REJECTED_NOT_ALLOWED`）。
6. **可退量上限**：新增 `_assert_return_limit(order, line, net)`；当 `origin_receipt_id` 非空时，
   按 `receipt_lines.schedule_id` 汇总原收货净收，校验
   `已退 + 本单 <= 原净收`（`RC_RETURN_OVER_LIMIT`）。
7. **库存过账**：`_post_receipt_inventory(..., txn_type, direction)`；
   退货使用 `RETURN_TO_VENDOR` + `direction='out'` + 库存组织/发货库位；
   `event_key` 仍为 `receipt:{id}:post`，保证既有红冲按事件键可逆。
8. **序列号**：退货出库前调用新增 `SerialNumberService.precheck_receipt_return(receipt_id)`；
   过账后调用 `register_receipt_return(receipt_id, txn_by_line)` 写出库事件
   （`txn_type='return_to_vendor'`、`inventory_transaction_id` 指向库存事务），
   使 `reverse_serial_event` 能在红冲时回退。
9. **边规则分流**：`_write_receipt_inbound_edges` 增加 `rule_id` 参数；
   退货写 `receipt_line_to_return_out_txn`，标准单保持 `receipt_line_to_inventory_txn`。
10. **计划行重算**：
    * 标准单沿用 `_apply_schedule_receipt`（累加 `received_qty`/`rejected_qty`）；
    * 退货单在同一事务内调用新增 `recompute_schedule_returned(schedule_id)`，
      **按已过账退货行聚合重算** `returned_qty`（幂等，不做增量）；
    * 退货单不写 `demand_allocations`（需求分配只服务正向收货）。
11. **红冲**：`reverse()` 仅拒绝 `red`；`_create_purchase_reversal_document` 按原单类别分支：
    * 标准/其它 → 现有 `schedules`（回退 `received_qty`）；
    * 退货 → `schedules` 置空、新增 `returned_schedules`（红字过账后由投影重算 `returned_qty`）。

---

## 4. 逆向原语（`meta/core/reversal_primitives.py`）

* 新增 `recompute_schedule_returned(ds, args, ctx)`：读取 `args.items` 中的 `schedule_id`，
  调用 `ReceiptService.recompute_schedule_returned`；注册名 `recompute_schedule_returned`（17 → 18）。
* `receipt.yaml` 的 `doc_effect.projection` 增加一项：
  `{primitive: recompute_schedule_returned, items: "{reversal.doc.returned_schedules}"}`；
  标准单该列表为空，原语空转。
* `doc_effect.edge.rule_ids` 增加 `receipt_line_to_return_out_txn`。

---

## 5. 审批维度（`meta/services/document_approval_service.py`）

* `_load_record` 在记录含 `document_type_id` 时补充 `document_category`
  （查 `type_definitions`），使审批条件表达式可直接引用该字段。
* 不改条件求值引擎。

---

## 6. 入口（收货详情「退货」）

* `meta/services/receipt_actions.py` 新增 `create_vendor_return_handler`：
  入参 `receipt_id`、`lines[{schedule_id, qty}]`、`return_reason`、`receipt_date`。
  1. 校验原收货 `posted`、来源为 `purchase_order`；
  2. 创建退货采购单（`RETURN_PO`，`origin_purchase_order_id` / `origin_receipt_id` / `return_reason`），
     行与计划行按传入数量复制；
  3. 创建 `VENDOR_RETURN` 草稿收货单（`return_to='supplier'`），行挂新计划行；
  4. 返回 `{purchase_order_id, receipt_id}`。
* `meta/services/bo_action_registrations.py` 注册 BO 动作 `receipt.create_vendor_return`，
  并在 `receipt.yaml` 的 `rules` / `ui_hints` 增加入口声明（`from_states: [posted]`）。
* 采购订单新建时选择 `RETURN_PO` 类型即可（纯元数据，无需代码）。

---

## 7. 迁移 `meta/migrations/v227__purchase_return_object.py`

* `upgrade()`：
  1. `RCV_RETURN` 置 `document_category='red'`、`name='红字收货单'`；
  2. 插入 `RETURN_PO` / `VENDOR_RETURN` 类型与 `RPO` / `RTV` 序列并绑定；
  3. 插入 `RETURN_TO_VENDOR` 事务类型、`receipt_line_to_return_out_txn` 边规则；
  4. `PRAGMA table_info` 守卫下 ALTER 五列（§2.2）；
  5. 重建 `v_demand_trace_graph`。
* `verify()`：类型/事务类型/边规则/五列/视图含新规则分支，缺一失败。
* `downgrade()`：删除新种子与边规则；`RCV_RETURN` 恢复 `return`；视图恢复旧 SQL；
  新增列置 NULL 但保留列（SQLite 降级安全，文件内注明）。
* 全部语句幂等（`INSERT OR IGNORE` / `UPDATE ... WHERE` / 列存在性守卫）。

---

## 8. Schema 声明同步

| 文件 | 变更 |
| --- | --- |
| `meta/schemas/receipt.yaml` | 头部注释三值化；新增 `return_to`；`doc_effect.edge.rule_ids` 加退货规则；新增 `recompute_schedule_returned` 投影；`red` 不独立过账的注释 |
| `meta/schemas/purchase_order.yaml` | 新增 `origin_purchase_order_id` / `origin_receipt_id` / `return_reason`（只读/可选） |
| `meta/schemas/purchase_order_schedule.yaml` | 新增 `returned_qty`（只读、默认 0） |
| `meta/schemas/demand_trace_graph.yaml` | `signed_qty` 增加退货出库分支 |
| `meta/schemas/receipt.yaml` rules | 新增 `create_vendor_return`（非状态迁移动作，`from_states: [posted]`） |

---

## 9. 验收（AC-RP-11 ~ AC-RP-19）

| 编号 | 用例 |
| --- | --- |
| AC-RP-11 | 退货采购单 + `VENDOR_RETURN` 收货单可创建 |
| AC-RP-12 | 标准 PO 建退货收货 → `RC_CATEGORY_MISMATCH` |
| AC-RP-13 | 退货出库过账：库存 -N、移动类型 `RETURN_TO_VENDOR`、边规则 `receipt_line_to_return_out_txn` |
| AC-RP-14 | `returned_qty += N`，`received_qty` 不变，原 PO 不重开 |
| AC-RP-15 | 超可退量 → `RC_RETURN_OVER_LIMIT` |
| AC-RP-16 | 审批条件引用 `document_category` 生效 |
| AC-RP-17 | 退货收货红冲：库存回补、`returned_qty` 回退、原退货行 `reversed` |
| AC-RP-18 | 原 PO 仍可继续新建普通 PO（不被重开） |
| AC-RP-19 | 序列号物料：退货出库写 `return_to_vendor` 事件；红冲后序列号回 `in_stores` |

测试文件：`meta/tests/test_purchase_return.py`（9 例）。

---

## 10. 验证命令

```powershell
python d:\filework\test.py --file meta/tests/test_purchase_return.py
python d:\filework\test.py --file meta/tests/test_receipt_service.py
python d:\filework\test.py --file meta/tests/test_receipt_reversal.py
python d:\filework\test.py --file meta/tests/test_doc_flow_reconcile.py
python d:\filework\test.py --file meta/tests/test_demand_trace_graph.py
```

迁移由测试夹具自动执行；若需单独验证，运行 `python d:\filework\test.py --single meta/tests/test_purchase_return.py`。

---

## 11. 非目标

* 不做 `return_to='receiving'`（本期仅枚举占位）。
* 不做无原收货的供应商退货。
* 不重开原 PO 未收量。
* 不改库存成本/科目语义。
* 不新增独立 `supplier_return` BO。
