# P6c 实施任务清单（完工成品号 + 组件单父谱系）

> 依据：[spec.md](./spec.md) v1.1（D1-D8 已定）
> 状态：**待批准**（A1-A3 三个实施级决策需拍板）
> 前置：P6a / P6b 已提交（`a3a506f8` / `1b265943`）

---

## 0. 已核实的关键事实（实施时直接依赖）

| 事实 | 位置 |
|---|---|
| `work_orders` 无 `item_id/qty`，只有 `order_type/status/work_order_no` | [v163__work_order_production_components.py](file:///d:/filework/excel-to-diagram/meta/migrations/v163__work_order_production_components.py#L51-L67)、[test_work_order_production.py](file:///d:/filework/excel-to-diagram/meta/tests/test_work_order_production.py#L93-L130) |
| `work_order_components` 字段：`component_item_id / qty_required / optional_flag / line_no` | 同上 |
| `receipt_lines` 已有 `serial_no / qty_received / qty_rejected` | [receipt_test_doubles.py](file:///d:/filework/excel-to-diagram/meta/tests/receipt_test_doubles.py#L92-L113) |
| 收货 `post()` 按 `source_doc_type` 分派；TO 支路已有 `_serial_ready` 两段式 | [receipt_service.py](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L327-L477) |
| `_post_receipt_inventory` 的 `transaction_type` 必须能在 `inventory_transaction_types` 查到 | [inventory_guard_service.py](file:///d:/filework/excel-to-diagram/meta/services/inventory_guard_service.py#L259-L326) |
| 库存移动类型种子只有 `RCV_PO / RCV_TO / ISSUE_TO_SHIP / OPENING / REVERSAL`，**无 RCV_WO** | [v201__inventory_foundation.py](file:///d:/filework/excel-to-diagram/meta/migrations/v201__inventory_foundation.py#L44-L55) |
| 序列号可复用积木：`_line_serials / _ensure_serial / _insert_txn / _ensure_link / _links / _find_inv_tx / reverse_serial_event` | [serial_number_service.py](file:///d:/filework/excel-to-diagram/meta/services/serial_number_service.py#L1366-L1556) |

**结论**：spec 的「零迁移」在**表结构**层面成立，但库存移动类型 `RCV_WO` 需要一行种子数据，否则真实过账会报 `INV_TYPE_INVALID`。这是 A1 待拍板项。

---

## 1. 待批准决策（A1-A3）

| # | 决策点 | 推荐 | 备选 | 影响 |
|---|---|---|---|---|
| **A1** | 完工入库的库存移动类型 | 新增迁移 `v204__inventory_work_order_receipt_type.py`，只插一行 `RCV_WO`（category=`receipt`, direction=`in`），`verify()` 断言存在 | 复用 `RCV_PO`，零迁移但报表会把完工混入采购收货 | 推荐项是**数据种子**，不是表结构变更 |
| **A2** | 一张完工单有多个成品号时，组件挂到哪个父号 | 无显式 `parent_serial_id` 且有组件号时抛 `SERIAL_COMPLETION_PARENT_AMBIGUOUS`（新增第 6 个错误码） | 默认挂第一个成品号（静默、易错） | 推荐项把「无法判断」显式暴露 |
| **A3** | 红冲是否走 `receipt.reverse()` | 新增 `_reverse_work_order()`，内部调用 `SerialNumberService.reverse_completion()`；谱系与 link 不删除 | 只提供 `reverse_completion()`，由调用方手动串联 | 推荐项让「红冲」有完整公共入口 |

---

## 2. 代码任务

### T1 — serial_number_service 完工与谱系
- [x] 已完成（`precheck_completion / register_completion / reverse_completion / genealogy` + 内部工具）

文件：[meta/services/serial_number_service.py](file:///d:/filework/excel-to-diagram/meta/services/serial_number_service.py)

1. 顶部常量：
   - `DOC_WORK_ORDER = 'work_order'`
   - `WORK_ORDER_TABLE = 'work_orders'`
   - `WORK_ORDER_COMPONENT_TABLE = 'work_order_components'`
2. 新增 `precheck_completion(work_order_id, receipt_id)`（无副作用）：
   - `_require_production_order(work_order_id)`：存在 + `order_type='production'` + `status ∈ {new, in progress}`，否则 `SERIAL_COMPLETION_WORK_ORDER_INVALID`。
   - 成品行复用 P6b `_precheck_line(line, net, DOC_RECEIPT, 'require_on_receipt', 'SERIAL_RECEIPT_COUNT_MISMATCH')`。
   - 组件行调 `_completion_groups(...)` 做 D7 校验。
3. 新增 `register_completion(work_order_id, receipt_id, event_key=None, parent_serial_id=None)`：
   - 先 `_completion_groups` 全量校验（失败即不改库）；
   - 事务内：`_produce_line` 逐成品行（`source_type='produced'`、`produced_at`=收货日期、写 `receive` + link）；
   - `_completion_parent` 解析父号（A2）；
   - `_consume_component` 逐组件号：写一条 `issue`（`in_stores→issued`），UPDATE `current_location_id=NULL`、`parent_serial_id=父号`、`relation_type='assembly'`。
4. 新增 `reverse_completion(work_order_id, receipt_id)`：
   - 取 `serial_transactions` 中 `doc_type='receipt' AND doc_id=receipt_id` 的 `receive`，及 `doc_type='work_order' AND doc_id=work_order_id` 的 `issue`；
   - 对状态仍等于 `usage_to` 的号写反向 `adjust` 回事件，UPDATE 状态；**不删 link、不清 parent_serial_id/relation_type**；幂等。
5. 新增 `genealogy(serial_id, depth=1)`：只读，`parents` 向上、`children` 向下，`depth` 截断 1..5，防环。
6. 内部工具：`_require_production_order / _completion_groups / _produce_line / _consume_component / _completion_parent / _genealogy_up / _genealogy_down`。
7. 新增错误码：`SERIAL_COMPONENT_NOT_IN_STORES / SERIAL_COMPONENT_ITEM_MISMATCH / SERIAL_COMPONENT_COUNT_MISMATCH / SERIAL_PARENT_ALREADY_SET`（+ A2 的 `SERIAL_COMPLETION_PARENT_AMBIGUOUS`）。

### T2 — receipt_service 完工收货支路
- [x] 已完成（`prepare_work_order_header / create_from_work_order / _post_work_order / _reverse_work_order` + 序列号包装）

文件：[meta/services/receipt_service.py](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py)

1. `SOURCE_WORK_ORDER = 'work_order'`（**不加入** `SOURCE_SUPPORTED`，避免影响 PO 默认分支）。
2. `prepare_header()` 增加 `work_order` 分支 → `prepare_work_order_header(header)`：
   - 工单存在、`order_type='production'`、状态 `new / in progress`；
   - `inventory_org_id` 与 `deliver_to_location_id` 必填（D2）；
   - 复用 `_validate_inventory_org / _validate_location_org`；
   - `purchase_org_id / supplier_party_id` 置空；`source_doc_no = work_order_no`；取号。
3. `create_from_work_order(work_order_id, location_id, lines, inventory_org_id=None, receipt_date=None, document_type_id=None, remark=None)`，结构与 `create_from_transfer_order` 同构。
4. `create_receipt()` 增加 work_order 校验器与归一化：
   - `_validate_work_order_line(line, work_order, doc_type)`
   - `_normalized_work_order_payload(checked)`
5. `post()` 分派：`source_doc_type == 'work_order'` → `_post_work_order(header, actual_arrival_date)`。
6. `_post_work_order()`：
   - 行校验 → `serial_ready` 时 `_precheck_work_order_serials()`；
   - 行/头置 `posted`；
   - `_post_receipt_inventory(header, checked, 'RCV_WO')`（A1）；
   - `_register_work_order_serials(work_order_id, receipt_id, event_key='receipt:<id>:post')`；
   - 返回 `work_order_id`，**不自动关单**（D5）。
7. `reverse()` 分派：`source_doc_type == 'work_order'` → `_reverse_work_order()`：
   - 建红字单（复制原行，`reversal_of_receipt_id` 指向原单）→ 直接置 posted → 原单置 reversed；
   - `_reverse_receipt_inventory()`；
   - `SerialNumberService.reverse_completion()`；
   - 返回 `reversal_receipt_id`。

### T3 — 迁移（仅 A1 采用推荐项时）
- [x] 已完成（[v204__inventory_work_order_receipt_type.py](file:///d:/filework/excel-to-diagram/meta/migrations/v204__inventory_work_order_receipt_type.py)，A1 采用推荐项）

文件：`meta/migrations/v204__inventory_work_order_receipt_type.py`

- `_do_upgrade(conn)`：`INSERT OR IGNORE INTO inventory_transaction_types (code,name,category,direction,affects_on_hand,sort_order,description) VALUES ('RCV_WO','生产工单完工入库','receipt','in',1,15,'生产工单来源收货过账形成的入库')`。
- `_do_downgrade(conn)`：`DELETE ... WHERE code='RCV_WO'`。
- `verify(conn)`：断言 code 存在、`category='receipt'`、`direction='in'`。
- 幂等：连跑两次结果一致。

### T4 — 测试
- [x] 已完成（[test_serial_completion_genealogy.py](file:///d:/filework/excel-to-diagram/meta/tests/test_serial_completion_genealogy.py)，11 例全绿：10 功能 + 1 v204 幂等校验）

新文件：`meta/tests/test_serial_completion_genealogy.py`（内存 SQLite，装 v202 三表 + 最小 `work_orders / work_order_components / receipts / receipt_lines / inventory_transactions / orgs / org_functions / locations / items` 替身）。

| # | 用例 | 断言 |
|---|---|---|
| 1 | 完工 1 号快捷录入 | 建档（`create` + `receive`），`in_stores`，`source_type='produced'`，`produced_at` 有值 |
| 2 | 成品 `qty=2` 走 links | 两条 `document_serial_links(doc_type='receipt', direction='in')` |
| 3 | 3 个组件号挂 1 个成品 | 组件全部 `issued`、`parent_serial_id=成品号`、`relation_type='assembly'`、各一条 `issue` 事件 |
| 4 | 组件号不在库 | `SERIAL_COMPONENT_NOT_IN_STORES`，且无任何写入 |
| 5 | 组件物料不符 | `SERIAL_COMPONENT_ITEM_MISMATCH` |
| 6 | 组件数量不符 | `SERIAL_COMPONENT_COUNT_MISMATCH` |
| 7 | 组件已有父号 | `SERIAL_PARENT_ALREADY_SET` |
| 8 | 成品未启序列号 | 不建档、不要求录号、组件仍可正常消耗 |
| 9 | 红冲 | 成品号/组件号状态回退；`document_serial_links` 与 `parent_serial_id` 保留 |
| 10 | `genealogy()` | 成品号 `children` 含 3 个组件；组件号 `parents` 指向成品 |

回归：`test_serial_tracking_posting.py`、`test_serial_transfer_posting.py`、`test_serial_adjustment_count_posting.py`、`test_receipt_service.py`、`test_work_order_service.py`。

---

## 3. 验证步骤

```powershell
python d:\filework\test.py --single meta/tests/test_serial_completion_genealogy.py
python d:\filework\test.py --single meta/tests/test_serial_tracking_posting.py
python d:\filework\test.py --single meta/tests/test_serial_transfer_posting.py
python d:\filework\test.py --single meta/tests/test_serial_adjustment_count_posting.py
python d:\filework\test.py --single meta/tests/test_receipt_service.py
python d:\filework\test.py --single meta/tests/test_work_order_service.py
```

- [x] 新文件 11 例全绿（`test_serial_completion_genealogy.py`）
- [x] `test_serial_tracking_posting.py` 全绿
- [x] `test_serial_transfer_posting.py` 全绿
- [x] `test_serial_adjustment_count_posting.py` 全绿
- [x] `test_receipt_service.py` 30 例 / `test_receipt_reversal.py` 8 例全绿
- [x] `test_work_order_service.py` / `test_work_order_production.py` 全绿
- [x] `test_inventory_schema.py` 全绿

验收口径：
- 新文件 11 例全绿；6 套回归无新增失败；
- 不 commit、不部署；
- 若 A1 采用 v204，额外验证 `python d:\filework\test.py --single meta/tests/test_inventory_schema.py`（断言新类型存在）。

---

## 4. 明确不做

- 不自动关闭工单（D5）；
- 不写 `consumed`、不加 `in_stores→consumed` 直边（D4）；
- 不新建领料/发料单据；
- 不给 `inventory_transactions` 加 `serial_id`；
- 不做多父谱系 / 包装嵌套 / 跨组织谱系（P7）。
