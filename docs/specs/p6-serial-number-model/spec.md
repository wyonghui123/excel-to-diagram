# P6 实现规格：序列号对象模型（主档 / 事件账 / 对象清单）

- 日期: 2026-11-03（v1.0）/ 2026-11-04（v1.1 细化）
- 状态: **P6a 已实施**（as-built）；v1.1 补充事务契约、测试矩阵与 §11 容器规格；**§11 为预研，未批准**
- 上游依据:
  - SAP / Oracle 序列号对象模型研究结论（`EQUI.GERNR` / `EQBS` / `OBJK` 与 `INV_SERIAL_NUMBERS`）
  - SAP HU（`VEKP` / `VEPO` / `UNVEL`、EWM `/SCWM/HUHDR`）与 Oracle LPN（`WMS_LICENSE_PLATE_NUMBERS` / `INV_LICENSE_PLATE_NUMBERS` / OTM `SHIP_UNIT`）专题研究
  - 8 个头部产品二次研究结论（D365 / Infor LN·M3 / NetSuite / Odoo / Manhattan / IFS / 金蝶 / 用友）
  - P5 规格 `docs/specs/p5-routing-branch-parallel-batch-selection/spec.md` 的 D10–D12（批次组织隔离、单据行不挂批次）
  - `meta/schemas/inventory_transaction.yaml`（追加式数量账，无序列号字段）
- 迁移号: **v202**（仓库实际最大前缀 `v201__inventory_foundation.py`）

## 1. 目标与范围

**做（P6a，本 Spec 的实现边界）**：

1. 新建三张表：`serial_numbers`（主档 + 当前态）、`serial_transactions`（序列号事件账）、`document_serial_links`（对象清单）。
2. `items` 增三个开关：`serial_tracked` / `require_on_receipt` / `require_on_issue`。
3. 序列号服务：建档、录号校验、状态流转、按号查历史。
4. 收货过账、发运过账的录号前置校验（含 `qty=1` 快捷录入兼容）。
5. 迁移 v202：建表 / 加列 / 枚举 / 权限 / 菜单 / 历史 `serial_no` 回填。

**不做（后续阶段，勿在本 Spec 讨论）**：

- 调拨、盘点、调整、退货/RMA 的序列号执行（P6b）。
- 生产完工成品号与组件单父谱系落地（P6c；本 Spec 只建 `parent_serial_id` / `relation_type` 字段，不做服务与 UI）。
- 多父 genealogy、跨组织谱系、全局唯一（P7）。
- 序列号级预留、拣货拆号（与 P5 D12 同口径，不做）。
- `serial_balances`（不建；序列号本身即最小库存单位）。
- 给 `inventory_transactions` 加 `serial_id`（明确禁止）。
- 把序列号升级为设备/资产对象（不引入 EAM、维修状态机、设备结构树）。
- P6a 不做行内嵌子表 UI；录号走独立列表 + 过账接口入参。

## 2. 已定决策

| # | 决策 | 依据 |
|---|---|---|
| D1 | 采用**独立主档**，不用纯库存维度 | Oracle / NetSuite / 金蝶 / 用友 / Infor LN 均建独立记录；本地需要“按号查状态与历史” |
| D2 | 唯一键 `(item_id, org_id, serial_no)`，默认组织级 | Oracle 同键；P5 D10 批次组织隔离口径一致 |
| D3 | 状态拆三轴：`usage_status` / `quality_status` / `current_location_id` | IFS 条件·运行·位置，Oracle 用途·质量双状态 |
| D4 | 主档是投影，`serial_transactions` 是真相 | 本地 `inventory_balances` 投影哲学；避免 Odoo/NetSuite 无状态导致的聚合成本 |
| D5 | 数量账不加序列号；桥接放 `serial_transactions.inventory_transaction_id` | 一条数量行 `qty>1` 对应 N 个号；纯状态变更无数量 |
| D6 | 用统一 `document_serial_links` 替代 N 张单据子表 | SAP `OBJK` 对象清单；加单据类型不需要加表 |
| D7 | 单据行 `serial_no` 保留为快捷录入，`qty>1` 强制走子表 | 兼容存量；避免单值文本承载多号 |
| D8 | `items` 三个开关拆开，不用单一枚举 | D365 收货/发货分开控制 + `blank allowed`；金蝶“全部收发货 / 仅发货” |
| D9 | `source_type` 含 `issue_created` | 金蝶允许只在发货环节建号 |
| D10 | `parent_serial_id` + `relation_type`（`assembly` / `packaging`） | 金蝶批号序列号关系、Infor LN `Top Serial Number`、Manhattan 嵌套序列号 |
| D11 | 状态流转走服务层白名单，禁止任意跳转 | 用友出库校验在库、Oracle 状态枚举 |
| D12 | 序列号不挂销售订单行 / 调拨单行 | 沿用 P5 D12；拆号属执行层 |
| D13 | 反冲不删 `document_serial_links` | 审计优先；反冲只写反向事件并回退状态 |
| D14 | 回填只处理 `qty=1` 的存量行，`qty>1` 标记待清洗 | 单值文本无法可靠拆分，不自动猜测 |
| D15 | **不把序列号合并进批次物理模型**（不建「数量恒为 1 的 batch」）；批次做组、序列号做件，仅用 `serial_numbers.batch_id` 可空关联 | SAP / Oracle / Dynamics 365 / Odoo / NetSuite 均为两套独立主档；无一家用 batch 行表达单件 |
| D16 | 序列号唯一性范围保留扩展位：当前固定 `(item_id, org_id, serial_no)`，P7 再做 item / org / across-org 可配置 | Oracle 唯一性三档可配；当前取值即其 organization 档 |

## 3. 数据模型

### 3.1 `serial_numbers`

| 列 | 类型 | 可空 | 默认 | 语义 |
|---|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | 否 | — | 技术主键 |
| `item_id` | INTEGER | 否 | — | 物料 |
| `org_id` | INTEGER | 否 | — | 当前归属库存组织 |
| `serial_no` | VARCHAR(64) | 否 | — | 序列号 |
| `uii` | VARCHAR(64) | 是 | — | 唯一物料标识（SAP UII 口径，外部合规用） |
| `batch_id` | INTEGER | 是 | — | 批次（先批后序，可空） |
| `revision` | VARCHAR(20) | 是 | — | 修订版 |
| `usage_status` | VARCHAR(20) | 否 | `defined` | 用途状态 |
| `quality_status` | VARCHAR(20) | 否 | `unrestricted` | 质量状态 |
| `current_location_id` | INTEGER | 是 | — | 当前库位；`defined` / `issued` / `shipped` 时为空 |
| `parent_serial_id` | INTEGER | 是 | — | 父序列号（单父） |
| `relation_type` | VARCHAR(20) | 是 | — | `assembly` / `packaging` |
| `parent_item_id` | INTEGER | 是 | — | 父件物料 |
| `source_type` | VARCHAR(20) | 否 | — | `received` / `produced` / `opening` / `issue_created` |
| `source_doc_type` | VARCHAR(50) | 是 | — | 来源单据类型 |
| `source_doc_id` | INTEGER | 是 | — | 来源单据主键 |
| `received_at` | DATETIME | 是 | — | 收货时间 |
| `produced_at` | DATETIME | 是 | — | 完工时间 |
| `shipped_at` | DATETIME | 是 | — | 发运时间 |
| `scrapped_at` | DATETIME | 是 | — | 报废时间 |
| `remark` | VARCHAR(255) | 是 | — | 备注 |
| `created_by` / `created_at` / `updated_by` / `updated_at` | — | 是 | — | 平台审计列 |

索引：

- `uq_serial_number`：`(item_id, org_id, serial_no)` 唯一
- `uq_serial_uii`：`(uii)` 部分唯一 `WHERE uii IS NOT NULL`
- `idx_serial_org_item`：`(org_id, item_id)`
- `idx_serial_parent`：`(parent_serial_id)`
- `idx_serial_status`：`(usage_status)`

枚举：

- `serial_usage_status`：`defined`（已建档未入库）/ `in_stores`（在库）/ `in_transit`（在途）/ `issued`（已发出待运）/ `shipped`（已发运）/ `consumed`（已耗用）/ `returned`（已退回）/ `scrapped`（已报废，终态）
- `serial_quality_status`：`unrestricted` / `inspection` / `blocked`

### 3.2 `serial_transactions`

| 列 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `id` | INTEGER PK | 否 | 技术主键 |
| `serial_id` | INTEGER | 否 | 序列号 |
| `inventory_transaction_id` | INTEGER | 是 | 桥接数量账；纯状态变更时为空 |
| `txn_type` | VARCHAR(20) | 否 | 事件类型 |
| `txn_date` | DATETIME | 否 | 事件时间 |
| `org_from_id` / `org_to_id` | INTEGER | 是 | 组织迁移 |
| `location_from_id` / `location_to_id` | INTEGER | 是 | 库位迁移 |
| `batch_from_id` / `batch_to_id` | INTEGER | 是 | 批次迁移 |
| `usage_from` / `usage_to` | VARCHAR(20) | 是 | 用途状态变化 |
| `quality_from` / `quality_to` | VARCHAR(20) | 是 | 质量状态变化 |
| `doc_type` / `doc_id` / `line_id` | VARCHAR / INTEGER | 是 | 来源单据 |
| `remark` | VARCHAR(255) | 是 | 备注 |
| `created_by` / `created_at` | — | 是 | 审计 |

`serial_txn_type` 枚举：`create` / `receive` / `issue` / `transfer_out` / `transfer_in` / `ship` / `return` / `adjust` / `status_change` / `scrap`。

索引：`(serial_id, txn_date)`、`(inventory_transaction_id)`、`(doc_type, doc_id)`。

### 3.3 `document_serial_links`

| 列 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `id` | INTEGER PK | 否 | 技术主键 |
| `doc_type` | VARCHAR(30) | 否 | `receipt` / `shipment` / `transfer_order` / `work_order` / `inventory_count` / `rma` |
| `doc_id` | INTEGER | 否 | 单据主键 |
| `line_id` | INTEGER | 否 | 单据行主键 |
| `serial_id` | INTEGER | 否 | 序列号 |
| `direction` | VARCHAR(10) | 否 | `in` / `out` |
| `created_at` | DATETIME | 是 | — |

索引：`uq_document_serial_link`：`(doc_type, line_id, serial_id)` 唯一；`idx_document_serial_doc`：`(doc_type, doc_id)`；`idx_document_serial_serial`：`(serial_id)`。

`receipt_serial_lines` / `shipment_serial_lines` **不建物理表**，作为 `document_serial_links` 按 `doc_type` 的过滤视图。

### 3.4 `items` 追加列

| 列 | DDL | 语义 |
|---|---|---|
| `serial_tracked` | `INTEGER NOT NULL DEFAULT 0` | 是否序列号管理 |
| `require_on_receipt` | `INTEGER NOT NULL DEFAULT 0` | 收货是否强制录号 |
| `require_on_issue` | `INTEGER NOT NULL DEFAULT 0` | 发货是否强制录号 |

服务层约束：`require_on_receipt = 1` 或 `require_on_issue = 1` 时，`serial_tracked` 必须为 1。

### 3.5 状态流转白名单

| From | To | 触发 |
|---|---|---|
| `defined` | `in_stores` | 收货 / 完工入库 / 期初导入 |
| `in_stores` | `issued` | 领用 / 待发 |
| `in_stores` | `in_transit` | 调拨转出（P6b） |
| `in_transit` | `in_stores` | 调拨转入（P6b） |
| `issued` | `shipped` | 发运过账 |
| `issued` | `consumed` | 领用消耗（P6b） |
| `issued` | `returned` | 退回（P6b） |
| `returned` | `in_stores` | 退回入库（P6b） |
| 任意（除 `scrapped`） | `scrapped` | 报废（P6b） |

`scrapped` 为终态，不可再流转。`quality_status` 独立流转，不改变 `usage_status`。

## 4. Schema YAML 变更

### 4.1 新建

- `meta/schemas/serial_number.yaml`：对象 `serial_number`，表 `serial_numbers`，`aspects: [audit_aspect]`，`display_name_field: serial_no`；字段按 §3.1；`serial_no` 标 `business_key: true`；索引 5 条（部分唯一用 `type: partial` + `condition: "uii IS NOT NULL"`）。
- `meta/schemas/serial_transaction.yaml`：对象 `serial_transaction`，表 `serial_transactions`，只读（`skip_auto_menu: true` 由列表菜单承载）；字段按 §3.2。
- `meta/schemas/document_serial_link.yaml`：对象 `document_serial_link`，表 `document_serial_links`；字段按 §3.3；`skip_auto_menu: true`。

三个对象的 `ui_view_config.list` 至少包含：序列号 / 物料 / 组织 / 批次 / 用途状态 / 质量状态 / 当前库位（links 表为 单据类型 / 单据 / 行 / 序列号 / 方向）。

### 4.2 修改

- `meta/schemas/items.yaml`：追加 `serial_tracked` / `require_on_receipt` / `require_on_issue`（boolean，`fieldGroup: 序列号`，`fieldGroupPosition: 210`）。
- `meta/schemas/receipt_line.yaml`：`serial_no.max_length` 64 → 200（对齐 `generated_schema.sql` 的 `VARCHAR(200)`）；`description` 改为“快捷录入：qty=1 时可直接录号；qty>1 必须走序列号子表”。
- `meta/schemas/shipment_line.yaml`：同上。

### 4.3 菜单与权限

- `serial-number-list`：挂 `master-data`，`sort_order=107`（v199 `batch-selection-policy-list` 占 106；实施时以 DB 当前最大值为准，被占用则顺延）。
- `serial-transaction-list`：只读，挂 `inventory` 根菜单，`sort_order=7`（v201 库存只读菜单占 6）。
- `document-serial-link-list`：只读，挂 `inventory` 根菜单，`sort_order=8`。
- 权限：`serial_number:serial_number_{read|create|update|delete}`、`serial_transaction:serial_transaction_read`、`document_serial_link:document_serial_link_read`。
- 枚举类型由 v202 注册：`serial_usage_status` / `serial_quality_status` / `serial_source_type` / `serial_relation_type` / `serial_txn_type`。

## 5. 服务层

新建 `meta/services/serial_number_service.py`。

异常：`SerialNumberError(message, field_name, rule)`。

| 方法 | 行为 |
|---|---|
| `create_serial(payload)` | 校验 `item.serial_tracked=1`；校验 `(item, org, serial)` 唯一；初始 `usage_status=defined`；写 `create` 事件 |
| `validate_line_serials(item_id, org_id, qty, serials, direction, doc)` | 数量必须等于 qty；同批不得重复；方向 `out` 时所有号必须 `in_stores` / `issued`；`serial_tracked=0` 时 serials 必须为空 |
| `register_receipt(receipt_id)` | 按 `receipt_line` 逐行：`require_on_receipt=1` 时校验数量；建号或复用已有号；写 `receive` 事件 + `document_serial_links(direction=in)`；主档置 `in_stores` + `current_location_id` |
| `register_shipment(shipment_id)` | `require_on_issue=1` 时校验数量；校验在库；写 `ship` 事件 + `links(direction=out)`；主档置 `shipped`、`current_location_id=NULL`、`shipped_at` |
| `change_status(serial_id, to_status, reason, doc=None)` | 按 §3.5 白名单；写 `status_change` 事件；非法跳转抛 `SERIAL_STATUS_TRANSITION_INVALID` |
| `reverse_serial_event(inventory_transaction_id)` | 反冲时写反向事件并回退主档状态；不删除原 link |
| `trace_serial(serial_no, org_id=None)` | 返回主档 + 事件时间线 + 关联单据；跨组织时按 org 分组 |

状态流转必须由服务层统一执行；禁止前端直接 PATCH `usage_status`。

### 5.1 事务、幂等与并发（as-built）

| 项 | 契约 |
|---|---|
| 事务边界 | 服务方法不 `commit`；由 BO Action / 过账调用方用 `framework.transaction()` 包裹，异常即整单回滚 |
| 取号 | 服务不取号；单号在事务外生成（R-RC-8），避免长事务持有编号锁 |
| link 幂等 | `document_serial_links` 唯一键 `(doc_type, line_id, serial_id)`；重复调用只复用已有行，不新增 |
| 事件幂等 | 写事件前按 `(serial_id, txn_type, doc_type, doc_id, line_id)` 查重；重复过账不产生重复事件 |
| 数量账桥接 | 收货用 `inventory_transactions.source_event_key='receipt:<id>:post'` + `source_line_id` 定位；发运当前不桥接数量账（`inventory_transaction_id=NULL`） |
| 并发建档 | 依赖 `uq_serial_number` 兜底；捕获唯一键冲突后转 `SERIAL_DUPLICATE` |
| 处理顺序 | 先读单据头 → 逐行读 link / 主档 → 写事件 → 更新主档；禁止跨行批量 UPDATE |

### 5.2 快捷录入判定矩阵（细化 §6.1）

| # | 条件 | 行为 |
|---|---|---|
| R1 | `serial_tracked=0` 且行内 `serial_no` 非空 | 拒绝：`SERIAL_ITEM_NOT_TRACKED` |
| R2 | `serial_tracked=1`、无 link、行内 `serial_no` 非空、净收 = 1 | 建号或复用 + `link(direction=in)` |
| R3 | `serial_tracked=1`、无 link、行内 `serial_no` 非空、净收 > 1 | 拒绝：`SERIAL_SINGLE_VALUE_WITH_MULTI_QTY` |
| R4 | `require_on_receipt=1` 且 link 数 ≠ 净收 | 拒绝：`SERIAL_RECEIPT_COUNT_MISMATCH` |
| R5 | `require_on_receipt=0` 且无 link | 允许过账，不写序列号事件 |
| S1 | `require_on_issue=1` 且 link 数 ≠ 发运数量 | 拒绝：`SERIAL_ISSUE_COUNT_MISMATCH` |
| S2 | `require_on_issue=1`、无 link、无 `serial_no`、`require_on_receipt=0` | 按数量自动生成 `DN-L<line>-n`，`source_type=issue_created` |
| S3 | 发运号状态不在 `in_stores/issued`（`issue_created + defined` 除外） | 拒绝：`SERIAL_NOT_AVAILABLE` |

### 5.3 错误码目录

| 错误码 | 触发点 |
|---|---|
| `SERIAL_ITEM_REQUIRED` / `SERIAL_ORG_REQUIRED` / `SERIAL_NO_REQUIRED` | 建档或追溯必填缺失 |
| `SERIAL_NO_TOO_LONG` | 序列号超过 64 字符 |
| `SERIAL_ITEM_NOT_TRACKED` | 未启序列号管理的物料出现序列号 |
| `SERIAL_DUPLICATE` / `SERIAL_DUPLICATE_IN_LINE` | 主档唯一键冲突 / 同一行重复号 |
| `SERIAL_COUNT_MISMATCH` | `validate_line_serials` 数量不符 |
| `SERIAL_NOT_FOUND` / `SERIAL_NOT_AVAILABLE` | 号不存在 / 出库状态不可用 |
| `SERIAL_SINGLE_VALUE_WITH_MULTI_QTY` | 数量 > 1 却只给单值号 |
| `SERIAL_RECEIPT_COUNT_MISMATCH` / `SERIAL_ISSUE_COUNT_MISMATCH` | 收货 / 发运 link 数量不符 |
| `SERIAL_STATUS_INVALID` / `SERIAL_STATUS_TRANSITION_INVALID` | 未知状态 / 白名单外跳转 |
| `SERIAL_ORG_MISMATCH` | 序列号组织与单据组织不一致 |
| `SERIAL_SOURCE_TYPE_INVALID` / `SERIAL_QUALITY_STATUS_INVALID` / `SERIAL_TXN_TYPE_INVALID` | 枚举值非法 |
| P6b/P6c 扩展 | `SERIAL_TRANSFER_COUNT_MISMATCH`、`SERIAL_STATUS_PAIR_INVALID`、`SERIAL_COMPLETION_*`、`SERIAL_COMPONENT_*`、`SERIAL_PARENT_ALREADY_SET` |

### 5.4 反冲契约

- `reverse_serial_event(inventory_transaction_id)` 只反冲桥接到该数量账事件的序列号事件。
- 跳过 `usage_from/usage_to` 为空的行；若主档当前状态 ≠ 原事件 `usage_to`，跳过（防重复反冲与脏回退）。
- 写 `adjust` 反向事件，交换 `org/location/batch/usage` 的 from/to，`inventory_transaction_id` 复用原值。
- 回退主档：`in_stores` 恢复 `current_location_id`；`defined` 清空库位；`shipped` 清空 `shipped_at`。
- **不删除** `document_serial_links` 与原事件（D13）。
- 发运事件 `inventory_transaction_id=NULL`，本方法不覆盖发运取消；发运回退需由单据层另行走“重开序列号”逻辑（P6b 边界）。

## 6. 过账钩子与拦截器

### 6.1 过账前置校验

- 收货过账（`receipt` 的 post 动作）：
  - `item.require_on_receipt=1` 且 `qty_received>1`：必须存在 `document_serial_links(doc_type='receipt', line_id)` 且数量 = `qty_received`，否则抛 `SERIAL_RECEIPT_COUNT_MISMATCH`。
  - `qty_received=1` 且 `serial_no` 非空：服务自动建 link（快捷录入）。
  - `qty_received>1` 且 `serial_no` 非空：抛 `SERIAL_SINGLE_VALUE_WITH_MULTI_QTY`。
- 发运过账（`shipment` 的 ship 动作）：
  - `item.require_on_issue=1`：link 数量必须 = `qty`，且所有序列号 `usage_status='in_stores'`。
  - `qty=1` 且 `serial_no` 非空：自动建 link。

### 6.2 拦截器

- `serial_number_guard`：`serial_numbers` 的 create / update 校验（物料已开启管理、唯一键、状态合法、`scrapped` 不可改）。
- `serial_tracking_guard`：收货 / 发运过账前置校验（§6.1）。
- 两个拦截器同时注册到双启动路径（与 P5 的 `batch_selection_policy_guard` / `work_definition_sequence_guard` 同口径）。

## 7. 迁移 v202

文件：`meta/migrations/v202__serial_number_model.py`。

1. 建三表 + 索引。
2. `items` 加三列（SQLite `ALTER TABLE ADD COLUMN`）。
3. 注册 5 个枚举类型与值。
4. 注册权限与三个菜单。
5. 回填：
   - 收货行：`serial_no` 非空且 `qty_received=1` → 建主档（`source_type='received'`、`usage_status='in_stores'`、`org_id=receipt.org_id`）+ link。
   - 发运行：`serial_no` 非空且 `qty=1` → 主档（不存在则建，`source_type='received'`）+ link；主档置 `shipped`、`shipped_at`；`org_id` 取 `shipment.ship_from_location_id → location.org_id`。
   - `qty>1` 但 `serial_no` 非空：跳过，写迁移日志 `SERIAL_BACKFILL_SKIPPED_MULTI_QTY`。
   - 重复 `(item, org, serial)`：保留最早一条，冲突行写日志 `SERIAL_BACKFILL_DUPLICATE`。
   - 回填幂等：每次先按唯一键查询是否存在。
6. 迁移完成后校验：三表存在、`items` 三列存在、枚举存在、回填计数与日志。

## 8. 测试

- 唯一键：同物料同组织重复号拒绝；跨组织同号允许。
- 状态机：合法流转通过；`scrapped→in_stores`、`defined→shipped` 拒绝。
- 收货：`require_on_receipt=1` 且 `qty=1` 快捷录入；`qty=3` 无子表拒绝；`qty=3` 三号通过。
- 发运：`require_on_issue=1` 且号不在库拒绝；正常发运置 `shipped`。
- 反冲：状态回退、原 link 保留。
- 按号查历史：返回主档 + 事件 + 单据。
- 回填：`qty=1` 行入库；`qty>1` 行跳过并留日志。
- 入口：`python d:\filework\test.py --single <path>`（禁止 pytest）。

### 8.1 测试矩阵（as-built）

| 测试文件 | 覆盖 |
|---|---|
| `meta/tests/test_serial_number_schema.py` | 三表字段 / 索引 / 枚举 / items 三开关 |
| `meta/tests/test_serial_number_migration.py` | v202 幂等、回填、跳过与冲突日志 |
| `meta/tests/test_serial_number_service.py` | 建档、唯一键、状态机、追溯、反冲 |
| `meta/tests/test_serial_tracking_posting.py` | 收货 / 发运快捷录入、数量不符、未启管理物料 |
| `meta/tests/test_serial_transfer_posting.py` | 调拨发运 / 收货（P6b 回归） |
| `meta/tests/test_serial_adjustment_count_posting.py` | 调整 / 盘点（P6b 回归） |
| `meta/tests/test_serial_completion_genealogy.py` | 完工建档 / 组件单父谱系（P6c 回归） |

## 9. 风险

| 风险 | 处置 |
|---|---|
| 回填重复号 | 保留最早、冲突写日志，人工清洗 |
| `qty>1` 单值存量 | 不自动拆分，标记待清洗 |
| 发运 `serial_no` 是逗号拼接串 | 回填前先探测；命中拼接串的行整体跳过并告警 |
| 宽度不一致（YAML 64 / DDL 200） | YAML 统一到 200，DDL 不动 |
| 跨组织同号 | 按组织隔离，报表必须带 `org_id` |
| 并发建档 | 唯一键兜底；服务捕获后转业务错误 |
| 仅发货管理模式的建档时点 | `source_type=issue_created` 预留，P6b 实现 |

## 10. 分期

| 阶段 | 内容 | 状态 |
|---|---|---|
| P6a（本 Spec） | 三表 + items 三开关 + 收货/发运录号 + 按号查历史 + 回填 | 已实施 |
| P6b | 调拨 / 盘点 / 调整 / 退货；`quality_status` 流转；`issue_created` 建档 | 已实施（`docs/specs/p6b-serial-execution/spec.md`） |
| P6c | 完工成品号 + 组件单父谱系（`relation_type=assembly`） | 已实施（`docs/specs/p6c-serial-genealogy/spec.md`） |
| P6a-2（预研） | 包装容器：HU/LPN、装箱/拆箱、嵌套、整箱发运 | 本 §11 v1.1 细化，未批准 |
| P7 | 全局唯一（`serial_uniqueness_scope`）、多父谱系、序列号级预留、跨组织谱系 | 未启动 |

## 11. P6a-2 增量规格：包装容器（HU/LPN）

- 日期: 2026-11-04（v1.1 细化，v1.2 实施）
- 状态: **已实施**（as-built；v211 已落三表 + 服务 + 收货/发运接线 + 35 个新测试；调拨发运侧与 D4 查询 UI 见 §11.11 备注）
- 迁移号: **v211**（`v207__project_task_index.py`、`v208__work_order_project_task.py`、`v209__project_structure_baseline.py`、`v210__sales_order_line_project_task.py` 均已被占用，顺延至 v211）
- 对标: SAP `VEKP` / `VEPO` / `UNVEL`、EWM `/SCWM/HUHDR`；Oracle EBS `WMS_LICENSE_PLATE_NUMBERS` / `WMS_LPN_CONTENTS`、Fusion `INV_LICENSE_PLATE_NUMBERS`、Shipping `WSH_DELIVERY_DETAILS`

### 11.1 术语映射与三条边界

| 本项目 | SAP | Oracle | 说明 |
|---|---|---|---|
| `handling_units` | HU 抬头 `VEKP` | LPN 抬头 | 容器当前态 |
| `handling_unit_items` | HU 内容行 `VEPO` | `WMS_LPN_CONTENTS` | 装了什么（当前态） |
| `hu_transactions` | HU 状态日志 / `HUSSTAT` | LPN 历史 | 容器事件账 |
| `parent_hu_id` / `root_hu_id` | `UNVEL` 单上层 | `PARENT_LPN_ID` / `OUTERMOST_LPN_ID` | 单父 + 冗余根 |
| `packaging_item_id` | `VELIN=2` 辅助包装 | Container Item | 可选容器物料 |
| （不做）运输单元 | EWM TU / THU | OTM `SHIP_UNIT` | 见 §11.12 |

三条边界（研究结论，任何实现不得突破）：

1. HU 是**库存之上的物流层**。`inventory_balances` 不增加 `hu_id`；余额仍按 `(item, org, location, batch)` 记，HU 只做归属与追溯。
2. 装箱**不改变** `serial_numbers.usage_status`；只有整箱发运 / 整箱移库过账才驱动成员号状态。
3. HU 与运输单元**不是 1:1**（一托可拆多发，多托可合一载）。因此运输字段（承运人、路线、装载顺序、运费）**不进 HU 表**；将来出现运输域时另建 `ship_units`，用 `hu_id` 弱引用。

### 11.2 对象模型

#### 11.2.1 `handling_units`（容器抬头 / 当前态）

| 列 | 类型 | 可空 | 默认 | 语义 |
|---|---|---|---|---|
| `id` | INTEGER PK | 否 | - | 技术主键 |
| `hu_no` | VARCHAR(40) | 否 | - | 容器号；可放 SSCC-18 |
| `hu_type` | VARCHAR(20) | 否 | `carton` | `pallet` / `carton` / `bin` / `container` / `other` |
| `packaging_item_id` | INTEGER | 是 | - | 容器物料（托盘/箱型），对应 Oracle Container Item |
| `org_id` | INTEGER | 否 | - | 归属库存组织 |
| `location_id` | INTEGER | 是 | - | 当前库位；`open` 未定库位时为空，`sealed` 后必填 |
| `parent_hu_id` | INTEGER | 是 | - | 上层 HU（单父） |
| `root_hu_id` | INTEGER | 是 | - | 最外层 HU（自身为顶层时等于 `id`） |
| `status` | VARCHAR(20) | 否 | `open` | `open` / `sealed` / `shipped` / `void` |
| `is_reusable` | INTEGER | 否 | 0 | 周转箱/托盘复用开关 |
| `cycle_no` | INTEGER | 否 | 1 | 第几次使用（复用箱递增） |
| `gross_weight` | DECIMAL(18,4) | 是 | - | 毛重（录入或汇总，不自动换算） |
| `tare_weight` | DECIMAL(18,4) | 是 | - | 皮重 |
| `net_weight` | DECIMAL(18,4) | 是 | - | 净重 |
| `volume` | DECIMAL(18,6) | 是 | - | 体积 |
| `uom_id` | INTEGER | 是 | - | 重量/体积单位 |
| `source_doc_type` / `source_doc_id` | VARCHAR(50) / INTEGER | 是 | - | 建箱来源 |
| `sealed_at` / `shipped_at` / `voided_at` | DATETIME | 是 | - | 状态时间 |
| `remark` | VARCHAR(255) | 是 | - | 备注 |
| `created_by` / `created_at` / `updated_by` / `updated_at` | - | 是 | - | 平台审计列 |

索引与约束：

- `uq_hu_no`：`(org_id, hu_no)` 唯一
- `idx_hu_parent`：`(parent_hu_id)`；`idx_hu_root`：`(root_hu_id)`
- `idx_hu_location`：`(location_id)`；`idx_hu_status`：`(status)`
- 服务层约束：`parent_hu_id != id`；父子必须同 `org_id`；父必须为 `open`；变更父子时重算子树 `root_hu_id`；禁止成环

#### 11.2.2 `handling_unit_items`（容器内容投影）

| 列 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `id` | INTEGER PK | 否 | 技术主键 |
| `hu_id` | INTEGER | 否 | 容器 |
| `content_type` | VARCHAR(20) | 否 | `material` / `packaging` / `hu` |
| `item_id` | INTEGER | 是 | 物料；`content_type='hu'` 时为空 |
| `batch_id` | INTEGER | 是 | 批次 |
| `serial_id` | INTEGER | 是 | 序列号；为序列号行时 `qty` 必须为 1 |
| `child_hu_id` | INTEGER | 是 | 嵌套子容器；`content_type='hu'` 时必填 |
| `qty` | DECIMAL(18,4) | 否 | 数量 |
| `uom_id` | INTEGER | 是 | 单位 |
| `created_at` | DATETIME | 是 | - |

索引与约束：

- `uq_hu_serial`：`(hu_id, serial_id)` 部分唯一 `WHERE serial_id IS NOT NULL`
- `uq_serial_in_hu`：`(serial_id)` 全局部分唯一 `WHERE serial_id IS NOT NULL`（一个号同一时点只能在一个容器）
- `uq_hu_child`：`(hu_id, child_hu_id)` 部分唯一 `WHERE child_hu_id IS NOT NULL`
- `ck_hu_item_content`：内容类型与列组合必须一致
  - `material`：`item_id` 非空、`child_hu_id` 空；`serial_id` / `batch_id` 可空
  - `packaging`：`item_id` 非空；`serial_id` / `batch_id` / `child_hu_id` 必须为空（依据 IFS：序列号/批次跟踪件不得作包装物料）
  - `hu`：`child_hu_id` 非空、`qty = 0`、`item_id` / `batch_id` / `serial_id` 必须为空
- 仅 `material` 行允许 `serial_id` 非空；序列号行 `qty` 必须为 1
- `idx_hu_item_serial`：`(serial_id)`；`idx_hu_item_item`：`(item_id, batch_id)`
- 嵌套用 `child_hu_id` 行表达，不再重复写 `parent_hu_id`（父关系只存 `handling_units` 一处）

#### 11.2.3 `hu_transactions`（容器事件账）

| 列 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `id` | INTEGER PK | 否 | 技术主键 |
| `hu_id` | INTEGER | 否 | 容器 |
| `serial_id` | INTEGER | 是 | 涉及的序列号 |
| `child_hu_id` | INTEGER | 是 | 涉及的子容器 |
| `txn_type` | VARCHAR(20) | 否 | 事件类型（见下） |
| `from_hu_id` / `to_hu_id` | INTEGER | 是 | 拆并迁移 |
| `from_location_id` / `to_location_id` | INTEGER | 是 | 库位迁移（`move` 记录） |
| `doc_type` / `doc_id` / `line_id` | VARCHAR(30) / INTEGER | 是 | 来源单据 |
| `txn_at` | DATETIME | 否 | 事件时间 |
| `remark` | VARCHAR(255) | 是 | 备注 |
| `created_by` / `created_at` | - | 是 | 审计 |

`hu_txn_type` 枚举：`create` / `pack` / `unpack` / `move` / `consolidate` / `split` / `seal` / `unseal` / `ship` / `reverse` / `reuse` / `void`。

索引：`(hu_id, txn_at)`、`(serial_id, txn_at)`、`(doc_type, doc_id)`。

> 命名说明：原 §11 草案的 `serial_hu_links` 更名为 `hu_transactions`。理由：`consolidate` / `split` / `move` / `seal` 发生在容器层，没有序列号可挂；用 `serial_hu_links` 会让一半事件无主体。

### 11.3 HU 状态机

| From | To | 触发 | 前置 |
|---|---|---|---|
| `open` | `sealed` | `seal(hu_id)` | 内容非空；全部内容同库位；子 HU 均已 `sealed` |
| `sealed` | `open` | `unseal(hu_id)` | 未发运；保留内容（临时开箱） |
| `open` / `sealed` | `void` | `void_hu(hu_id, reason)` | 内容为空；非空须先 `unpack` |
| `sealed` | `shipped` | `ship_hu(hu_id, shipment_id)` | 已 `sealed`；有库位；成员号均在库 |
| `sealed` | `open` | `reuse(hu_id)` | `is_reusable=1`；内容为空；`cycle_no+1` |
| `shipped` | `sealed` | 发运红冲 | 仅由 `reverse_hu_transaction` 驱动 |

`shipped` / `void` 为终态，不可直接改；`shipped` 只能经单据红冲回到 `sealed`。

### 11.4 服务层

新建 `meta/services/handling_unit_service.py`。异常：`HandlingUnitError(message, field_name, rule)`。

| 方法 | 行为 |
|---|---|
| `create_hu(payload)` | 校验 `hu_no` 组织内唯一；18 位纯数字时校验 GS1 SSCC 校验位；`root_hu_id=id`；写 `create` 事件 |
| `pack(hu_id, lines)` | HU 必须 `open`；序列号必须 `in_stores`；号库位必须等于 HU 库位（HU 未定库位时取首个号库位）；全局唯一归属兜底；写 `pack` 事件 + 内容行 |
| `unpack(hu_id, lines)` | HU 必须 `open`（`sealed` 须先 `unseal`）；删除内容行；写 `unpack` 事件 |
| `move(hu_id, to_location_id, doc=None)` | 同组织内递归改子树 `location_id`；写 `move` 事件（含 `from/to`）；跨组织不走此方法，见 §11.5 |
| `consolidate(source_hu_ids, target_hu_id)` | 目标 `open`、同组织、同库位；源内容并入目标；源置 `void`；写 `consolidate` 事件 |
| `split(hu_id, lines, target_hu_id)` | 源不能为 `shipped`；目标 `open`、同组织、同库位；写 `split` 事件 |
| `seal(hu_id)` | 按 §11.3 前置校验；写 `seal` 事件 |
| `unseal(hu_id)` | `sealed → open`；写 `unseal` 事件 |
| `reuse(hu_id)` | 复用型空箱（`open` 或 `sealed`）回到 `open`，`cycle_no+1`；写 `reuse` 事件 |
| `void_hu(hu_id, reason)` | 内容非空时拒绝；写 `void` 事件 |
| `ship_hu(hu_id, shipment_id)` | HU 置 `shipped`；成员号 `in_stores → shipped`；写 `ship` 事件 |
| `reverse_hu_transaction(hu_txn_id)` | 反向事件；不删除内容行与历史事件 |
| `hu_contents(hu_no, org_id, mode='direct'\|'exploded')` | `direct` 返回直接子行；`exploded` 递归返回叶子 `material` 行 + 路径；附事件时间线 |
| `hu_stock(hu_id, mode='exploded')` | 按 `(item, batch, serial)` 汇总叶子 `material` 行；只读，不改库存账 |
| `hu_where_used(serial_no, org_id)` | 反查序列号当前所在 HU、根 HU 与嵌套路径，以及历史容器 |

事务与幂等契约（沿用 §5.1）：

- 服务不 `commit`；由 BO Action / 过账调用方 `framework.transaction()` 包裹。
- 事件幂等键 `(hu_id, txn_type, doc_type, doc_id, line_id, serial_id)`；重复调用只复用已有事件。
- 内容行幂等由 `uq_hu_serial` / `uq_hu_child` 兜底；冲突转业务错误，不做静默覆盖。
- 处理顺序：读 HU 头 → 校验状态与组织 → 逐行校验号归属与库位 → 写事件 → 改内容投影 → 改 HU 头。

状态白名单补充：`ship_hu` 需要 `in_stores → shipped`，该跳转**仅限整箱发运**，需在 P6a §3.5 白名单追加一条并注明触发来源为 `hu_transactions.txn_type='ship'`；散件发运仍走 `in_stores → issued → shipped`。

### 11.5 单据接线

| 单据 | 动作 | 接线 |
|---|---|---|
| 收货 `receipt` | `post` 后 | 行可选 `hu_no` + `hu_type`；`create_hu` + `pack`；仅当装箱数量 = 行净收数量 |
| 完工 `receipt(source_doc_type='work_order')` | `post` 后 | 成品号可选装入成品箱；组件号不装 HU |
| 发运 `shipment` | `ship` 后 | 按 HU 装运：`ship_hu`；成员号级联 `shipped` |
| 调拨 `transfer_order` | 发运 / 收货 | 同组织：HU 整体 `move`；跨组织：**复制 HU 结构到目标组织**，源 HU 随发运置 `shipped`，不改 `org_id`（依据 Infor LN 多公司 HU 复制）；数量账按叶子 `material` 行汇总 |
| 盘点 `inventory_count` | P7 | 按 HU 计数，差异写 `adjust` 事件 |
| 退货 `rma` | P7 | 按 HU 整箱退回 |

as-built 边界（2026-11-04）：收货侧（含 TO 收货、完工成品）已接线，载体为 `receipt_lines.hu_no`；**调拨发运侧未接线**——`transfer_order_lines` 无 `hu_no` 载体，需后续补列后再接；跨组织收货按行扁平建箱，**不做子树结构复制**。

门控：所有接线先用 `hu_schema_ready(ds)` 判断三表是否存在；不存在时整条支路 no-op，不影响 P6a/P6b/P6c 主流程。

### 11.6 Schema YAML / 菜单 / 权限 / 迁移

- 新建 `meta/schemas/handling_unit.yaml`（`handling_units`，`display_name_field: hu_no`，`aspects: [audit_aspect]`，`hu_no` 标 `business_key: true`）。
- 新建 `meta/schemas/handling_unit_item.yaml`（`handling_unit_items`，`skip_auto_menu: true`）。
- 新建 `meta/schemas/hu_transaction.yaml`（`hu_transactions`，只读，`skip_auto_menu: true`）。
- 菜单：`handling-unit-list` 挂 `inventory` 根菜单（`sort_order=9`）；`hu-transaction-list` 只读（`sort_order=10`）。实施时以 DB 当前最大值为准。
- 权限：`handling_unit:handling_unit_{read|create|update|delete}`、`handling_unit_item:handling_unit_item_read`、`hu_transaction:hu_transaction_read`。
- 枚举：`hu_type` / `hu_status` / `hu_content_type` / `hu_txn_type`（v211 注册）。
- 迁移 `v211__handling_unit.py`：建三表 + 索引 + 枚举 + 权限 + 菜单；另给
  `receipt_lines` / `shipment_lines` 补可选 `hu_no` / `hu_type` 两列；
  **不回填历史数据**（存量无容器信息，不做猜测）。

### 11.7 错误码

| 码 | 触发 |
|---|---|
| `HU_NOT_FOUND` | `hu_id` / `hu_no` 不存在（也用于目标库位缺失） |
| `HU_NO_REQUIRED` | 建箱未填 `hu_no` |
| `HU_NO_TOO_LONG` | `hu_no` 超过 40 字符 |
| `HU_TYPE_INVALID` | `hu_type` 不在枚举内 |
| `HU_NO_DUPLICATE` | 组织内 `hu_no` 重复 |
| `HU_SERIAL_CONTENT_TYPE_INVALID` | `packaging` / `hu` 行挂了 `serial_id` / `batch_id` |
| `HU_SSCC_CHECKSUM_INVALID` | `hu_no` 为 18 位纯数字但 GS1 mod-10 校验位不符 |
| `HU_STATUS_INVALID` | 当前状态不允许该动作（如 `sealed` 直接 `pack`） |
| `HU_PARENT_SELF` | `parent_hu_id = id` |
| `HU_PARENT_CYCLE` | 父子关系成环 |
| `HU_PARENT_ORG_MISMATCH` | 父子不同组织 |
| `HU_PARENT_NOT_OPEN` | 父 HU 非 `open` |
| `HU_CONTENT_EMPTY` | `seal` 时无内容 |
| `HU_CONTENT_LOCATION_MISMATCH` | 内容与 HU 库位不一致 |
| `HU_SERIAL_NOT_IN_STORES` | 装箱号不在库 |
| `HU_SERIAL_ALREADY_PACKED` | 号已属于其他 HU |
| `HU_CHILD_STATUS_INVALID` | 子 HU 未 `sealed` 却装父 |
| `HU_NOT_EMPTY` | 作废 / 复用 / 删除时仍有内容 |
| `HU_NOT_REUSABLE` | 非复用型执行 `reuse` |
| `HU_SHIP_STATUS_INVALID` | 非 `sealed` 执行 `ship_hu` |
| `HU_ORG_MISMATCH` | 目标 HU 与来源不同组织 |

### 11.8 已定决策（H1–H9）

| # | 决策 | 依据 |
|---|---|---|
| H1 | **组织内唯一** `(org_id, hu_no)` | Oracle LPN 绑定 inventory org；SAP `VEKP` 带工厂；Infor LN 多公司转移是“复制 HU 结构到收货公司”。跨组织按复制 + 源 HU 置 `shipped` 处理，不做全局唯一 |
| H2 | **单父 + 冗余根**（`parent_hu_id` + `root_hu_id`），禁止 DAG | SAP `UNVEL` 单上层；Oracle Fusion 用 `PARENT_LPN_ID` + `OUTERMOST_LPN_ID` 同样是单父 + 冗余最外层。物理包装不可能同时属于两个容器；运输域的重切分用 Ship Unit 表达，不污染 HU |
| H3 | **允许复用，但仅限 `is_reusable=1`**；`hu_no` 不放开唯一 | Oracle 空 LPN 可复用；周转箱/托盘是常态。历史留在 `hu_transactions`，`cycle_no` 标识第几次使用；一次性纸箱不复用 |
| H4 | `open → sealed → shipped`，加 `void`；不引入 `received/in_stock` | 仓储已由 `location_id` + 状态表达；SAP 的 `0001/0010/0020/0030` 细分对当前业务过重。`open` 对应 `0001/0010`，`sealed` 对应 `0030`，`shipped` 对应 `0050` |
| H5 | **HU 占库位，HU 不等于库位**（不做 LPN 模式） | 我们的余额维度是 `(item, org, location, batch)`；引入 LPN 即库位会让 balance 维度爆炸，且与 P5 批次口径冲突。同库位允许多 HU |
| H6 | **不生成 SSCC，只校验**：`hu_no` 为 18 位纯数字时校验 GS1 mod-10 校验位，失败抛 `HU_SSCC_CHECKSUM_INVALID`；不分配 GS1 前缀、不打印标签 | SSCC 公司前缀是 GS1 注册资源，系统无此主数据。SAP 靠编号范围 + EXIDA 类型 C/D 生成，我们既无编号范围也无打印域。只做校验约十行代码，可拦截外部录入错误 |
| H7 | **不自动汇总重量/体积**，只存录入值 | 仓库核查：`items` 仅有 `net_weight` / `gross_weight`（float），**无重量单位字段、无 volume**。自动汇总会产生 kg/g 歧义，体积无数据来源。将来补 `weight_uom` + `volume` 后再引入“建议值 + 人工覆盖” |
| H8 | **不允许空 HU 发运**；空容器发运走普通发运行（`item` = 容器物料），与 HU 对象无关 | `ship_hu` 的语义是级联成员号 `shipped`，空箱没有成员号；`seal` 已要求内容非空。可回收托盘/周转箱属容器物料的收发，不是 HU 发运 |
| H9 | **允许混物料 / 混批次**，不做同质校验，不加 `homogeneous_flag` | SAP HU 默认可混装（除非包装规范限制）；Oracle `HOMOGENEOUS_CONTAINER` 是可选标志。我们无包装规范主数据，硬性限制会阻塞常规收货。需要时由未来的 `packaging_spec` 约束，不预埋恒为 false 的字段 |

### 11.9 扩展位（不在本次实现）

| 项 | 触发条件 |
|---|---|
| 包装规范 `packaging_spec`（同质约束、自动选箱、拆箱） | 需要按箱型/物料约束装箱时 |
| 重量体积自动汇总 | `items` 补 `weight_uom` + `volume` 后 |
| SSCC 生成、前缀分配、标签打印 | 接入 GS1 前缀与打印域时 |
| 运输层 `ship_units`（承运人/路线/装载/运费/ASN） | 出现独立运输域或对接 3PL 时 |

### 11.10 测试矩阵

| 测试文件 | 覆盖 |
|---|---|
| `meta/tests/test_hu_schema.py` | 三表字段 / 索引 / 部分唯一 / 枚举 |
| `meta/tests/test_hu_service.py` | 建箱、SSCC 校验、装箱、拆箱、密封、复用、作废、成环拒绝、跨组织拒绝 |
| `meta/tests/test_hu_nesting.py` | 父子嵌套、`root_hu_id` 维护、`move` 递归、`consolidate` / `split` |
| `meta/tests/test_hu_posting.py` | 收货装箱、完工装箱、整箱发运、红冲回退、门控 no-op |

入口：`python d:\filework\test.py --single <path>`（禁止 pytest）。

### 11.11 分期

| 步骤 | 内容 | 依赖 |
|---|---|---|
| D1 | v211 建表 + `handling_unit_service` 全动作（create / pack / unpack / move / consolidate / split / seal / unseal / reuse / void / ship / reverse + 3 查询） | 无 |
| D2 | 嵌套与迁移（`move` / `consolidate` / `split` / `reuse`） | D1 |
| D3 | 单据接线（收货 / 完工 / 发运 / 调拨）+ 红冲 | D1、D2 |
| D4 | 查询 UI（容器内容树、按号查容器） | D1 |

as-built 备注：D1 / D2 / D3（收货、完工、发运、红冲）已完成并测试通过；D3 的调拨发运侧未接线（缺 `transfer_order_lines.hu_no`）；D4 查询 UI 未实施（`hu_contents` / `hu_stock` / `hu_where_used` 服务方法已就绪，仅缺页面入口）。

### 11.12 明确不做

- SSCC 前缀分配与生成、标签打印、条码规则（仅保留 18 位纯数字的校验位校验）。
- HU 级库存余额表（继续复用 `inventory_balances`）。
- 包装规范（packaging specification）自动拆箱 / 自动选箱。
- LPN 即库位模式（`HU == location`）。
- 运输域：承运人、路线、装载顺序、运费、ASN/EDI 856、OTM Ship Unit / THU。
- HU 与销售订单行 / 调拨单行的预留关系（P7）。

### 11.13 嵌套容器的库存口径与内容查询

#### 11.13.1 库存账不按 HU 记

- `inventory_balances` 仍是唯一库存账，维度 `(item, org, location, batch)`；HU 不是账本，不新增余额行，也不产生第二套库存。
- **嵌套不增加库存数量**：父 HU 的“库存”是子树叶子 `material` 行之和，不是父行与子行重复相加。
- `content_type='hu'` 行 `qty=0`，只表达结构；任何数量汇总必须只取 `material` 行。
- 对照 IFS：IFS 把 `handling unit` 挂在库存记录上（未装箱为 0）；我们不挂，所以“未装箱”= 无 `handling_unit_items` 记录，不需要哨兵值。

#### 11.13.2 两种查询口径

| 方法 | 口径 | 用途 |
|---|---|---|
| `hu_contents(mode='direct')` | 直接子行（含 `content_type='hu'`） | 编辑容器、查看当前层 |
| `hu_contents(mode='exploded')` | 递归到叶子，返回 `material` 行 + 嵌套路径 | 查看整托实际装了什么 |
| `hu_stock()` | `exploded` 后按 `(item, batch, serial)` 聚合 | 回答“这托里有多少库存” |

#### 11.13.3 能看到的字段

- 物料、数量、单位、批次 `batch_id`、序列号 `serial_id`；库位取 HU 头 `location_id`，内容行不单独存库位。
- 序列号实时状态（`usage_status` / `quality_status`）仍以 `serial_numbers` 为准；`handling_unit_items` 只存归属，不复制状态。
- 批次属性通过 `batch_id` 关联批次主档。

#### 11.13.4 不重复计数的保证

- 序列号件：`uq_serial_in_hu` 全局部分唯一，一个号只能出现在一条 `material` 行。
- 批次/非序列号件：同一物理件只在一条 `material` 行登记，靠作业规范；`pack` 不做同 `(item, batch)` 自动合并（同批次可能是不同物理件），也不跨父子层搬移已有行。
- 嵌套只通过 `content_type='hu'` 行表达，**不把子容器内容复制到父容器**。

#### 11.13.5 与库存可用量的关系

- HU 不冻结库存：`sealed` 不改变 `inventory_balances` 可用量；质量冻结走 `serial_numbers.quality_status` 或批次质量状态。
- 按 HU 汇总得到的是“已装箱数量”，不等于组织总库存；未装箱库存不在任何 HU 中。
- 可选一致性校验（非强制）：`hu_stock()` 之和不得超过同维度 `inventory_balances`；超出说明装箱数据与账不符，交人工处置，不做自动修正。

#### 11.13.6 明确不做

- 不建 `hu_balances` / HU 级余额表。
- 不按 HU 做库存预留、拣货分配（P7）。
- 不做父子层数量对账触发器。
