# P6c 完工成品号与组件单父谱系 Spec

> 版本：v1.1（2026-11-04，按 Oracle / SAP 对标复核后修订 D4 / D5）
> 状态：**待确认**（D1-D8 需用户拍板后实施）
> 前置：P6a 序列号对象模型（`docs/specs/p6-serial-number-model/spec.md`）、P6b 执行层（`docs/specs/p6b-serial-execution/spec.md`）均已实施
> 定位：P6b 解决「单据动、序列号跟着动」；P6c 解决「生产完工时成品建档，并把用掉的组件号挂到成品号下」

---

## 1. 背景与目标

### 1.1 现状核实（纠正前一版判断）

| 事实 | 位置 | 结论 |
|---|---|---|
| 生产工单对象已存在，`order_type` 枚举含 `production` | [work_order.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/work_order.yaml#L119-L145) | 不需要新建工单对象 |
| 生产工单由 `_create_production` 创建，强制需求来源（`sales_order_schedule` / `sales_order_line` / `project_task`），并做组件展开 | [work_order_service.py](file:///d:/filework/excel-to-diagram/meta/services/work_order_service.py#L308-L411) | 组件清单已有载体：`work_order_components` |
| `work_order` 表**不持久化** `item_id` / `qty`，只在建单时从需求来源推导后传给组件展开 | [work_order_service.py](file:///d:/filework/excel-to-diagram/meta/services/work_order_service.py#L353-L398) | 完工数量不能从工单反查，只能由收货单行提供 |
| 工单状态是 `New / In Progress / Waiting / Resolved / Closed / Cancelled`，`resolve` 面向 SLA 结算，**没有完工语义** | [work_order.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/work_order.yaml#L426-L466) | P6c 不改工单状态机 |
| 收货单 `source_doc_type` 枚举**已含 `work_order`** | [receipt.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/receipt.yaml#L151-L176) | 完工入库可走收货单，无需新单据 |
| 但 `receipt_service` 只实现了 `purchase_order` / `transfer_order` 两支 | [receipt_service.py](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L51-L52)、[L338](file:///d:/filework/excel-to-diagram/meta/services/receipt_service.py#L327-L339) | `work_order` 分支待补 |
| 仓库**没有领料 / 组件发料单据** | `meta/schemas` 无 `material_issue*` | 组件序列号没有天然采集点，必须在完工环节补录 |
| `serial_numbers` 已有 `parent_serial_id` / `relation_type` / `source_type='produced'` / `produced_at` | [serial_number.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/serial_number.yaml#L417-L593)、v202 迁移 | 谱系字段齐备，P6c 零迁移 |

### 1.2 目标

1. 完工入库复用收货单，`source_doc_type='work_order'`；成品按序列号管理时建档（`source_type='produced'`）。
2. 组件序列号在完工单上补录，落到 `document_serial_links`（`doc_type='work_order'`，`line_id = work_order_component.id`）。
3. 过账时把组件号挂到成品号下：组件号 `parent_serial_id = 成品号`、`relation_type='assembly'`，组件状态置 `consumed`。
4. 谱系只做**单父**：一个组件号只能属于一个成品号；成品号可有多个子组件。

### 1.3 非目标

- 工单完工数量累计、超产/欠产校验（需给 `work_order` 加列 + 新迁移，见 D4）；
- 工单状态机自动化（完工即 `Resolved`，见 D5）；
- 多父谱系、包装嵌套 `packaging`、跨组织谱系（P7）；
- 序列号级预留、拣货拆号（P7）；
- 领料单据本体（不新建 `material_issue` 对象）。

---

## 2. Oracle / SAP 对标结论

| 议题 | Oracle EBS / Fusion | SAP S/4HANA（PP / EWM） | 本系统 P6c 口径 |
|---|---|---|---|
| 完工入口 | WIP Completion / Move Transaction；完工时必须指定子库存与货位 | 生产订单收货（MIGO，移动类型 101），与采购收货共用同一收货事务 | 复用 `receipt`（`source_doc_type='work_order'`），与 SAP 同构 |
| 完工与关单 | Completion 只增加完工数量；`Close Discrete Job` 是独立步骤（要求无待处理 WIP 事务，单独结算差异） | 收货 → 最终确认 CNF → TECO（技术完成）→ CLSD（关闭），四段独立 | 完工过账不自动关单（D5） |
| 组件号采集点 | ① 正常工单在 **WIP 发料**时把组件批次/序列号绑定到成品号；② 无工单完工场景在完成界面逐号录入（`Serial Entry Mode = Individual`） | 收货后通过 COIB / 设备层级（IE02，落 `V_EQUI_SER`）把组件号挂到成品号；也可用 EWM 预期收货（EGR）按已知序列号收货 | 无领料单据，只能在完工单补录（D6）；若后续做领料单，采集点应前移到发料 |
| 组件状态 | 状态枚举：Defined(1) / Resides in Stores(3) / Issued out of Stores(4) / Intransit(5) / Receiving(7) / Resides in WIP(8)，**没有 consumed** | 序列号不维护「消耗」态；消耗事实由物料凭证（261 发料）表达 | 组件只写 `issue`（`in_stores→issued`），不引入 consumed 态（D4 已修订） |
| 谱系承载 | Fusion `INV_SERIAL_NUMBERS.PARENT_ITEM_ID` 是**按物料**而非按序列号的父项；R12 把批次/序列号谱系合并为同一查询 | 设备层级（superior / inferior equipment），逐号父子 | `serial_numbers.parent_serial_id` 逐号、子指父；比 Oracle 更细，与 SAP 设备层级一致 |
| 包装嵌套 | — | EWM 嵌套 HU（多级包装） | 留 P7（`relation_type='packaging'`） |

**四条复核结论**

1. 完工入口复用收货单 = SAP 路线（生产订单 GR 与采购 GR 同属 MIGO），成立；Oracle 的 WIP Completion 是独立事务，不做照搬。
2. 「完工 ≠ 关单」在 Oracle（Completion vs Close Discrete Job）与 SAP（GR/CNF/TECO/CLSD 四段）都有硬证据，D5 成立。
3. 两家的序列号都**没有** consumed 终态：Oracle 到 `Issued out of Stores` 即止，SAP 靠物料凭证表达消耗。因此原 D4「两条事件走到 consumed」应收敛为**一条 `issue` 事件**。
4. 组件号采集点：Oracle 在发料或完工界面，SAP 在收货后建设备层级；本系统没有领料单，完工单补录是唯一可行点——这是**模型缺口**而非设计偏好，P7 前应补领料单据把采集点前移。

Sources:

- [On Manufacturing Work Order-less Completion（Oracle，Serial Entry Mode = Individual 时逐号挂谱系）](https://www.orafaq.com/papers/WorkOrderlessCompletion-Guenther.pdf)
- [Oracle R12 Inventory What's New（WIP 发料时绑定组件批次/序列号，谱系查询合并）](https://erpstuff.com/viewtopic.php?t=2243)
- [Understanding MTL_SERIAL_NUMBERS.CURRENT_STATUS（状态 1/3/4/5/7/8，无 consumed）](https://www.oracleappsnfusion.com/2014/08/understanding-mtlserialnumber.html)
- [INV_SERIAL_NUMBERS 字段（PARENT_ITEM_ID = Parent item for component genealogy）](https://summit-bi.com/resources/fusion-reference/tables/inv_serial_numbers)
- [SAP 序列号与设备层级（IE02 superior/inferior，V_EQUI_SER）](https://jig.netlify.app/sap-serial-number-management.html)
- [SAP COIB：按生产数据把组件序列号挂到成品序列号](https://www.erpgreat.com/production/serial-number-for-component.htm)
- [Production Order in SAP：GR → 最终确认 → TECO → CLSD](https://www.guru99.com/production-order-sap-pp.html)
- [SAP EWM 嵌套 HU（多级包装）](https://mdpgroup.com/en/blog/how-to-use-handling-unit-management-in-sap-ewm/)

---

## 3. 关键决策（待确认）

| # | 决策 | 推荐方案 | 理由 / 影响 |
|---|---|---|---|
| **D1** | 完工入口 | 复用 `receipt`，新增 `ReceiptService.create_from_work_order()`，`source_doc_type='work_order'` | 枚举已存在；与 `create_from_transfer_order` 同构；不新增单据对象 |
| **D2** | 完工收货单的组织/库位来源 | 由收货单表头**显式提供** `inventory_org_id` / `deliver_to_location_id`（工单无这两个字段） | 工单表确实没有 org/location，硬约束，不能反查 |
| **D3** | 成品号建档时点与状态 | 在收货过账（`post`）内复用 P6b「前置校验 + 过账后登记」两段式；建档写 `create`（`defined`）+ `receive`（`in_stores`），`source_type='produced'`，`produced_at = actual_arrival_date` | 与 P6a 收货口径一致；不引入「defined 直跳 in_stores 单事件」的新写法 |
| **D4** | 组件消耗的状态跃迁 | 组件只写**一条** `issue` 事件（`in_stores→issued`），不追加 `consumed` | **已按对标修订**：Oracle 序列号无 consumed 态（到 `Issued out of Stores` 即止），SAP 消耗由物料凭证表达；`consumed` 保留给领用核销（P6b 已实现 `issued→consumed`）。零迁移，且少一条事件 |
| **D5** | 完工是否自动关闭工单 | **不自动**。完工过账只写序列号事件；工单仍由人工 `resolve_work_order` 收口 | 双重外部证据：Oracle `Completion` 与 `Close Discrete Job` 分离；SAP 收货 → CNF → TECO → CLSD 四段独立。加上本系统工单无数量字段，无法区分部分/全部完工，自动 Resolved 必误关 |
| **D6** | 组件号的采集位置 | `document_serial_links`：`doc_type='work_order'`、`doc_id=work_order_id`、`line_id=work_order_component.id`、`direction='out'` | 复用 P6a D6 的单一链接表；`line_id` 指向组件行，天然支持 `qty>1` 多号；`doc_type` 无 CHECK 枚举，零迁移 |
| **D7** | 组件号合法性 | 必须满足：① `usage_status='in_stores'`；② `item_id = work_order_components.component_item_id`；③ `org_id` 与收货单表头一致；④ 数量 = `qty_required`（`optional_flag=1` 的行允许 0..qty） | 防止「随手挂谱系」；`qty_required` 已由展开逻辑算好 |
| **D8** | 成品号数量契约 | 与 P6b D11 同口径：`qty=1` 用收货行 `serial_no` 快捷列；`qty>1` 用 `document_serial_links`（`doc_type='receipt'`）| 不重复造第二套录号规则 |

**迁移结论**：P6c **零迁移**。`receipt.source_doc_type` 枚举含 `work_order`；`serial_numbers` 已有谱系字段；`document_serial_links.doc_type` 无枚举约束。只有两种情况才需补 v204：新增 `in_stores→consumed` 直边（改 `TRANSITIONS` + `txn_type`），或自动关单（给 `work_order` 加累计完工列）。两者当前均不推荐。

> **实施补充（2026-11-04，A1 已批准）**：库存移动类型种子缺少 `RCV_WO`，而 `_post_receipt_inventory` 会校验类型必须存在。因此新增 [v204__inventory_work_order_receipt_type.py](file:///d:/filework/excel-to-diagram/meta/migrations/v204__inventory_work_order_receipt_type.py)，只插入一行 `RCV_WO`（`category=receipt`、`direction=in`）；**表结构仍零变更**。


---

## 4. 数据与关系

```
work_order (order_type='production')
   └─ work_order_components  (component_item_id, qty_required, optional_flag)
          ↑ line_id
document_serial_links  (doc_type='work_order', doc_id=work_order.id, line_id=component.id, direction='out')
          ↓ serial_id
serial_numbers (组件号)  ── parent_serial_id ──▶ serial_numbers (成品号)
                          relation_type='assembly'

receipt (source_doc_type='work_order', source_doc_id=work_order.id)
   └─ receipt_lines (item_id=成品, qty, serial_no 快捷列)
          ↑ serial_id
document_serial_links  (doc_type='receipt', doc_id=receipt.id, line_id=receipt_line.id, direction='in')
```

不新增表、不新增列；谱系方向为「子指父」：`parent_serial_id` 写在**组件号**上，指向成品号。

---

## 5. 业务流程

### 5.1 完工入库

1. `create_from_work_order(work_order_id, location_id, lines)`：校验工单存在且 `order_type='production'`、`status ∈ {New, In Progress}`；表头写 `source_doc_type='work_order'`、`source_doc_id`、`inventory_org_id`、`deliver_to_location_id`。
2. 行级：`item_id` / `qty` / `serial_no`（可选快捷）由调用方显式给；不校验是否等于需求数量（D5）。
3. `post(receipt_id)`：
   - 前置：`serial_schema_ready(ds)` 为真时，校验成品行录号完整性（复用 P6b `_validate_serial_tracking`）；校验组件链接的合法性（D7）。
   - 过账：走既有 `_post_receipt_inventory` 生成数量事务。
   - 登记：成品号建档（`source_type='produced'`）+ `in_stores`；组件号写 `issue`（`in_stores→issued`），并写 `parent_serial_id` / `relation_type`。

### 5.2 组件号录入（无领料单前提）

完工单提供「组件序列号」录入面板：按 `work_order_components` 逐行列出 `component_item_id` / `qty_required`，每行录入 `qty_required` 个号；落 `document_serial_links`（D6）。后端入口复用 P6b `SerialNumberService.link_serials(...)`。

### 5.3 红冲

复用 P6a `reverse_serial_event(inventory_transaction_id)`：成品号反向事件回退（`in_stores→defined` 的反向写法），组件号回退到 `in_stores`。**谱系不解除**（与 P6a D13「不删 links」一致），保留历史归属。

---

## 6. 接口清单

| 接口 | 归属 | 说明 |
|---|---|---|
| `ReceiptService.create_from_work_order(work_order_id, location_id, lines)` | receipt_service | 生成完工收货单（`source_doc_type='work_order'`） |
| `SerialNumberService.precheck_completion(work_order_id, receipt_id)` | serial_number_service | 成品录号完整性 + 组件合法性（无副作用） |
| `SerialNumberService.register_completion(work_order_id, receipt_id, event_key)` | serial_number_service | 成品建档 + 组件消耗 + 写谱系 |
| `SerialNumberService.genealogy(serial_id, depth=1)` | serial_number_service | 单层正/反向谱系查询（只读） |

错误码（新增）：

| 规则码 | 触发条件 |
|---|---|
| `SERIAL_COMPLETION_WORK_ORDER_INVALID` | 工单不存在或非 `production` |
| `SERIAL_COMPONENT_NOT_IN_STORES` | 组件号不在库 |
| `SERIAL_COMPONENT_ITEM_MISMATCH` | 组件号物料与 `component_item_id` 不符 |
| `SERIAL_COMPONENT_COUNT_MISMATCH` | 组件号数量 ≠ `qty_required` |
| `SERIAL_PARENT_ALREADY_SET` | 组件号已有其他父号（单父约束） |

---

## 7. 测试计划

新增 `meta/tests/test_serial_completion_genealogy.py`（内存库，装 v202 三表 + 最小 `work_order` / `work_order_components` / `receipt` / `receipt_lines` 替身）：

1. 完工过账：成品 1 号建档 → `create` + `receive`，`usage_status='in_stores'`，`source_type='produced'`。
2. `qty=2` 成品走 `document_serial_links`，两号各一条 link。
3. 组件号 3 个挂到 1 个成品号：组件全部 `issued`，`parent_serial_id` 指向成品号，`relation_type='assembly'`。
4. 组件号不在库 → `SERIAL_COMPONENT_NOT_IN_STORES`。
5. 组件物料不符 → `SERIAL_COMPONENT_ITEM_MISMATCH`。
6. 组件数量不符 → `SERIAL_COMPONENT_COUNT_MISMATCH`。
7. 组件号已有父号 → `SERIAL_PARENT_ALREADY_SET`。
8. 未启用序列号的成品行：不建档、不要求录号（沿用 P6b 放行口径）。
9. 红冲后：成品号与组件号状态回退，`document_serial_links` 保留、`parent_serial_id` 保留。

回归：`test_serial_tracking_posting.py`、`test_serial_transfer_posting.py`、`test_serial_adjustment_count_posting.py`、`test_receipt_service.py`、`test_work_order_service.py`。

验证入口：`python d:\filework\test.py --single meta/tests/test_serial_completion_genealogy.py`。

---

## 8. 待确认事项

1. **D4 组件消耗写法**：按 Oracle/SAP 对标，建议只写 `issue`（`in_stores→issued`），不追加 `consumed`。若业务坚持「装配即不可再售」的强语义，再补 `status_change`（两条事件，仍零迁移）；不建议新增 `in_stores→consumed` 直边。
2. **D5 工单收口**：完工后是否要求人工 `resolve`？还是引入「全部组件已挂 + 成品号数达标」自动判定（需工单数量列）？
3. **组件号缺省行为**：`optional_flag=1` 的组件行留空是否允许？`qty_required=0` 的行是否隐藏？
4. **前端排期**：完工单「组件序列号」面板与序列号详情「谱系」只读区，是否与后端同批交付？
