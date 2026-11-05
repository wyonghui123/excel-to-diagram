# P6 实现规格：序列号对象模型（主档 / 事件账 / 对象清单）

- 日期: 2026-11-03（v1.0）/ 2026-11-04（v1.1 细化）
- 状态: **P6a 已实施**（as-built）；v1.1 补充事务契约、测试矩阵与 §11 容器规格；**§11 为预研，未批准**；
  §11.14 已实施（D4 查询 UI）；**§11.15 为预研草案**（D17 / D18 / D19 与三项决策已定稿，待排期）
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
- 状态: **已实施**（as-built；v211 三表 + 服务 + 收货/发运接线，v212 调拨行容器列，v213 D4 查询 UI（MOMP），49 个新测试 + 17 例前端 hubOptions 测试）
- 迁移号: **v211**（HU 三表；`v207`–`v210` 均已被占用，顺延至 v211）+ **v212**（调拨行 `hu_no` / `hu_type`）+ **v213**（D4 查询 UI：菜单转 `multi_object_hub`）
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
| 收货 `receipt` | `post` 后 | 行可选 `hu_no` + `hu_type`；`create_hu` + `pack`；仅当装箱数量 = 行净收数量（v216 起拆箱由 `document_hu_links.qty` 承载，见 §11.15.5） |
| 完工 `receipt(source_doc_type='work_order')` | `post` 后 | 成品号可选装入成品箱；组件号不装 HU |
| 发运 `shipment` | `ship` 后 | 按 HU 装运：`ship_hu`；成员号级联 `shipped` |
| 调拨 `transfer_order` | 发运 / 收货 | 同组织：HU 整体 `move`；跨组织：**复制 HU 结构到目标组织**，源 HU 随发运置 `shipped`（v217 起改 `in_transit`，见下方修订），不改 `org_id`（依据 Infor LN 多公司 HU 复制）；数量账按叶子 `material` 行汇总 |
| 盘点 `inventory_count` | P7 | 按 HU 计数，差异写 `adjust` 事件 |
| 退货 `rma` | P7 | 按 HU 整箱退回 |

as-built（2026-11-04）：收货侧（含 TO 收货、完工成品）载体为 `receipt_lines.hu_no`；调拨发运侧由 `v212__transfer_line_hu.py` 给 `transfer_order_lines` 补 `hu_no` / `hu_type` 后接 `ship_transfer`；跨组织收货按源容器**整棵子树复制**到目标组织（`_clone_tree`，按目标组织重建批次、不复制序列号主档）。

修订（§11.15 D19）：v216 先落 `document_hu_links` 与「一行多箱」`qty`；
v217 起跨组织源容器由 `shipped` 改为 `in_transit`（受 v211 CHECK 约束，需重建表），目标侧仍新建 HU；
`receipt_lines.hu_no` 只保留「整行进一箱」快捷语义。

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
- 迁移 `v212__transfer_line_hu.py`：给 `transfer_order_lines` 补可选
  `hu_no` / `hu_type` 两列（调拨发运侧载体）。

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
| D5 | HU ↔ 单据关系模型（P1 止血 + v216 `document_hu_links`；`planned` / `in_transit` → v217） | D3（P1 + v216 已实施） |

as-built 备注：D1 / D2 / D3（收货、完工、发运、调拨发运、跨组织子树复制、红冲）已完成并测试通过；D4 查询 UI 已实施（§11.14：`handling_unit.yaml` 的 `hub` 声明 + v213 菜单转 `multi_object_hub`，`hu_contents` / `hu_stock` / `hu_where_used` 服务方法复用现有 BO 列表接口）。

D5（已实施）：P1 三项止血 + v216 `document_hu_links` 桥表（含 `pack_line` / 逆转回退 / 存量回填）已落地并通过 6 例单测；`planned` / `in_transit` 因 v211 CHECK 需重建表，拆到 v217。详见 §11.15。

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

### 11.14 D4 查询 UI 方案（MOMP 元数据驱动，已实施）

#### 11.14.1 现有链路（事实依据）

```
menus.page_type='multi_object_hub' + primary_object_type
  → GenericTabContainer.decorateComponentTab() 装配
  → MultiObjectHubPage 读该对象 ui_view_config.hub
  → resolveHubOptions(hub) → MultiObjectManagementPage（左树 + 多 tab）
```

- 左树：`hub.scope.type='hierarchy'`，`HierarchyScopeTree` 用 `boService.query(objectType, page_size)` 拉扁平列表，再按 `parentField` 在客户端建树。
- 过滤：`hub.filters.<objectType>.field` → `<field>__in = effective ids`；`effective = 勾选 ∪ 全部子孙`。
  未选范围时不加条件（看全量），符合主数据页预期。
- 右 tab：`hub.object_types` 决定顺序与过滤分派，`hub.tabs` 给中文标签。

#### 11.14.2 信息架构（一期，零新组件）

单菜单「包装容器」（`/inventory/handling-units`）：

| 区域 | 内容 | 元数据实现 |
|---|---|---|
| 左树 | 容器嵌套树（托盘 → 箱 → 料箱），节点文案 `hu_no`，徽标 `status` | `scope.object=handling_unit`、`parent_field=parent_hu_id`、`label_field/code_field=hu_no`、`badge_field=status` |
| 顶部搜索 | 输入容器号即时过滤树节点 | `scope.search_placeholder` |
| Tab 1 子容器 | **当前选中容器的直接子容器**（`handling_unit`） | `filters.handling_unit: field=parent_hu_id, mode=direct` |
| Tab 2 容器内容 | 选中容器的内容行（`handling_unit_item`），因 effective 含子孙，等价 `hu_contents(mode='exploded')` | `filters.handling_unit_item: field=hu_id` |
| Tab 3 容器事件 | 子树事件账（`hu_transaction`） | `filters.hu_transaction: field=hu_id` |

「逐层展开」是本次确认的口径：Tab 1 用 `mode: direct`（只取勾选节点自身，即 `parent_hu_id = 选中 id`），
避免选中托盘时把整棵子树的容器平铺出来；Tab 2 / Tab 3 仍取整棵子树（`effective`），
因为内容与事件天然需要聚合子孙。实现上给 `hubOptions.js` 增加：

- `buildFilterStrategies` 读 `rule.mode === 'direct'` → 取 `scopeIds[scope_key].selected`（缺省取 `effective`）；
- `buildScopeProps` 透传 `label_field` / `code_field`（`HierarchyScopeTree` 已有同名 props，缺省 `name` / `code`）；
  包装容器没有 `name` / `code` 字段，必须显式指向 `hu_no`，否则树节点标签为空。

以上均为既有组件内的 2 处小改（约 6 行），不新增页面组件。

「容器内容树」的呈现口径：左树负责结构下钻（选中托盘即见其全部子孙容器节点），Tab 2 负责叶子明细（物料 / 批次 / 序列号 / 数量），两层组合即等于 exploded 视图，且不需要新增页面组件。

#### 11.14.3 元数据声明（`handling_unit.yaml` 追加 `ui_view_config.hub`）

```yaml
  hub:
    object_types: [handling_unit, handling_unit_item, hu_transaction]
    default_tab: handling_unit
    tabs:
      handling_unit: 子容器
      handling_unit_item: 容器内容
      hu_transaction: 容器事件
    state_key: handlingUnitManagerState
    disable_version_context: true
    scope:
      type: hierarchy
      object: handling_unit
      scope_key: handling_unit
      parent_field: parent_hu_id
      label_field: hu_no
      code_field: hu_no
      order_by: hu_no
      badge_field: status
      badge_map:
        open:     { label: 未封箱, type: info }
        sealed:   { label: 已封箱, type: success }
        shipped:  { label: 已发运, type: warning }
        void:     { label: 已作废, type: danger }
      node_icon: folder
      search_placeholder: 输入容器号搜索
      empty_text: 暂无包装容器
      paginate_all: true
    filters:
      handling_unit: { field: parent_hu_id, mode: direct }
      handling_unit_item: { field: hu_id }
      hu_transaction: { field: hu_id }
```

要点：

- `scope_key` 必须出现在 `object_types` 内（`resolveHubOptions` 校验）。
- `badge_map` 的 `type` 取值按 `HierarchyScopeTree` 的既有契约（Element Plus tag type）；若组件吃 `color`，同步改键。
- `filters` 必须给每个 tab 显式声明：未声明的 tab 会落到关系过滤默认分支，注入噪声参数。
- `label_field` / `code_field` 是本次给 `hubOptions` 新增的透传键（`HierarchyScopeTree` 早已支持）：
  包装容器没有 `name` / `code`，不显式声明会导致树节点文本为空、搜索失效。

#### 11.14.4 菜单改造（新迁移 `v213__handling_unit_momp.py`）

v211 建的 `handling-unit-list` 是普通 `object_list`；需改为 MOMP：

```sql
UPDATE menus
   SET page_type = 'multi_object_hub',
       primary_object_type = 'handling_unit',
       object_types = '["handling_unit","handling_unit_item","hu_transaction"]',
       bo_bindings = '[{"bo_id":"handling_unit","role":"primary",
                       "include_actions":["read","create","update","delete"]},
                      {"bo_id":"handling_unit_item","role":"related",
                       "include_actions":["read","list"]},
                      {"bo_id":"hu_transaction","role":"related",
                       "include_actions":["read","list"]}]',
       required_permissions = '[handling_unit 4 条 + handling_unit_item 2 条 + hu_transaction 2 条]',
       auto_generated = 0
 WHERE menu_code = 'handling-unit-list';
```

- 幂等：整行形态（page_type / object_types / bo_bindings / required_permissions）全部一致时打印 `[SKIP]`；
  只写 `WHERE page_type <> ...` 会在半套状态（如权限串没更新）下漏修，故按整行比对。
- `required_permissions` 必须只引用 v211 实际注册的权限码（前端守卫是 every 判定，引用不存在的码会整页 403）；
  `verify` 显式检查 `permissions.code` 是否存在。
- `menu_permissions.required_permissions` 同步为同样 8 条（否则路由菜单可见但页面被 403）。
- `hu-transaction-list` 保持独立只读菜单，不并入 hub。

#### 11.14.5 按号查容器（三档，按成本递增）

1. **左树搜索**（一期，已实施）：`scope.search_placeholder` + 树组件本地过滤（匹配 `labelField` / `codeField`，
   两者均为 `hu_no`），输入 `P1` 即定位节点。
2. **列表搜索**（一期，已实施）：`ui_view_config.list.searchFields: [hu_no]`，右侧 tab 直接按号查。
3. **深链定位**（二期）：`/inventory/handling-units?hu_no=HU-001` 自动选中树节点。需 `HierarchyScopeTree` 增加 `initialSelected` 或在 hub 侧 `scopeAdapter` 初始化，属前端小改。

服务层已具备 `hu_where_used(serial_no)`（按序列号反查容器），一期不放页面入口，二期可加「序列号反查」Tab 或查询框。

#### 11.14.6 二期：图形内容树（可选）

若需要「树形卡片」而非表格呈现，走 `MultiObjectManagementPage` 的 chart 视图：

- `viewMode='chart'` 时渲染业务方注入的 `detailContent` slot；
- 需给 `resolveHubOptions` 增加 `hub.detail_content` 声明 → `MultiObjectHubPage` 传 slot；
- 新增 `HandlingUnitContentTree.vue`，数据直接调 `GET /api/handling_unit/<id>/contents?mode=exploded`（服务层已有）。

评估：一期表格 + 左树下钻已覆盖 90% 场景；图形树仅在「托盘装箱可视化」明确需要时再做。

#### 11.14.7 边界与风险

| 项 | 处理 |
|---|---|
| 树拉全量 | `paginate_all: true`；HU 单组织建议 < 2000 节点，超出时二期加服务端树接口 |
| 多组织混合 | 一期树不按 `org_id` 过滤，靠列表列区分；二期给 `HierarchyScopeTree` 加 `extraFilters`（需组件小改） |
| `shipped` / `void` 容器 | 保留在树中（`location_id` 为空），徽标区分，不提供装箱操作入口 |
| 空容器 | Tab 2 空态「该容器为空」`handling_unit_items` 无行 |
| 未建 HU 表 | 菜单与页面照常渲染，列表返回空（后端 `hu_schema_ready` 只门控过账，不门控查询） |
| 树字段裁剪 | `HierarchyScopeTree` 目前取全字段；HU 列多，二期评估只取 `id/hu_no/parent_hu_id/status/org_id` |

#### 11.14.8 验收

- 新增 `meta/tests/test_hu_momp.py`（8 例，已通过）：YAML `hub` 契约（三对象 / 默认 tab / `parent_field` /
  `label_field` / `mode: direct`）；三个 hub 对象的 schema 与 `ui_config.list` 存在；迁移形态、幂等、
  `menu_permissions` 同步、菜单缺失跳过、权限码缺失时 `verify` 失败、`downgrade` 恢复。
- 前端 Vitest（`hubOptions.spec.js` 17 例，已通过）：补 `mode: direct` 只取 `selected`、
  内容/事件 tab 仍取 `effective`、未选范围不过滤、`labelField/codeField` 透传。
- 手工验收：建托盘 P1 + 子箱 C1 + 装 SN 件 → 打开页面，左树 P1→C1 可展开；选中 P1，Tab 1 只列 C1（不列 C1 的下级），
  Tab 2 显示子树内 SN 行；输入 `P1` 可搜索定位。

#### 11.14.9 改动文件清单

| 文件 | 改动 |
|---|---|
| `meta/schemas/handling_unit.yaml` | 追加 `ui_view_config.hub`（§11.14.3）；头部枚举迁移号 v208 → v211 |
| `meta/migrations/v213__handling_unit_momp.py` | 新增：菜单转 MOMP + `menu_permissions` 同步 + 幂等 / 回滚 / verify |
| `meta/tests/test_hu_momp.py` | 新增：YAML 契约 + 迁移幂等 + 权限码校验 + 回滚（8 例） |
| `src/components/common/MultiObjectHubPage/hubOptions.js` | `mode: direct`（约 3 行）+ `label_field` / `code_field` 透传（2 行）+ 契约注释 |
| `src/components/common/MultiObjectHubPage/__tests__/hubOptions.spec.js` | 追加 handling_unit hub 解析断言（`direct` / `effective` / 显示字段） |
| 二期：`src/components/common/HandlingUnitContentTree.vue`、`MultiObjectHubPage.vue` | 图形内容树（暂不做） |

### 11.15 HU 与单据的关系模型：SAP / Oracle 对标与缺口（预研，待批准）

> 本节是**预研与规格草案**，未批准实施。结论来源：SAP `VEKP` / `VEPO` / `UNVEL`、Oracle
> `WSH_DELIVERY_ASSIGNMENTS` / `WSH_DELIVERY_DETAILS` / `WMS_LPN_CONTENTS` 的表结构与状态机。

#### 11.15.1 对标事实：SAP

| 表 | 关键列 | 含义 |
|---|---|---|
| `VEKP`（HU 抬头） | `VPOBJ` / `VPOBJKEY` | HU 绑定一个单据对象（外向交货 01 / 内向交货 03 / 装运 04 / 生产订单 08-09 / 跨组织交货 21-23） |
| `VEKP` | `STATUS` | 9 态：Planned / 已实现库存未过账 / 库位非 HU / 库位为 HU / 盘点中 / 在途 / 已过账发货 / 已删除 / 目视检查 |
| `VEKP` | `UEVEL` | 上层 HU（子箱指向父托盘） |
| `VEKP` | `MAGEW` / `ZUL_AUFL` | 允许载重 / 允许附加量（容量约束） |
| `VEKP` | `PACKVORSCHR` + `PACKVORSCHR_ST` | 装箱指令号 + 合规状态（undefined / violated / tolerated / fulfilled） |
| `VEKP` | `KZGVH` | 封闭包装标记 |
| `VEPO`（内容行） | `VENUM` + `VEPOS` | 内容行主键（HU 号 + 行号） |
| `VEPO` | `VBELN` / `POSNR` | **指向交货单行**（一箱可对多行，一行可进多箱） |
| `VEPO` | `UNVEL` | 下层 HU（父托盘行指向子箱） |
| `VEPO` | `XCHAR` | 暂定分配标记（未确认的装箱关系） |
| `VBELN_GEN` / `POSNR_GEN` | — | 包装物料自动生成的交货行 |

**结论**：SAP 中 HU 与单据行是**多对多**，关系落点是 HU 内容行（`VEPO`），而不是单据行上的单值字段；
`XCHAR` 表明「暂定分配」是原生一等状态。

#### 11.15.2 对标事实：Oracle

| 表 | 关键列 | 含义 |
|---|---|---|
| `WSH_DELIVERY_ASSIGNMENTS` | `DELIVERY_DETAIL_ID` / `DELIVERY_ID` | 交货行 ↔ 交货单的显式桥表；`DELIVERY_ID` 为空即「未分配」 |
| `WSH_DELIVERY_ASSIGNMENTS` | `PARENT_DELIVERY_DETAIL_ID` | **装箱层级**：该行装在哪个容器行下 |
| `WSH_DELIVERY_DETAILS` | — | 容器（LPN）本身也是一行交货明细 |
| `WMS_LPN_CONTENTS` | — | LPN 内容明细（物料 / 批次 / 序列号 / 数量） |
| LPN context | — | 11 态，含 Receiving / Stores / In Transit / Packing / Picked / Loaded for shipment 等 |

**结论**：Oracle 用**显式桥表 + 层级列**表达装箱，且「未分配」是一等状态；容器态覆盖到「在途」而不止步于「已发运」。

#### 11.15.3 本地现状（as-built）

- 物理模型：`handling_units`（抬头/当前态）、`handling_unit_items`（内容投影）、`hu_transactions`（事件账）。
- 单据侧：`receipt_lines` / `shipment_lines` / `transfer_order_lines` 各带**单值** `hu_no` + `hu_type`（v211 加的列）。
- 事件侧：`hu_transactions` 已有 `doc_type` / `doc_id` / `line_id`，幂等键
  `(hu_id, txn_type, doc_type, doc_id, line_id, serial_id)`（应用层 SELECT-then-INSERT，无 DB 唯一索引）。
- 服务侧：`pack_receipt`（收货建箱/装箱，不封箱）、`ship_hu`（要求 `sealed` + 有库位、成员 SN 必须 `in_stores`）、
  `ship_shipment`（逐行调用 `ship_hu`，无去重）、`ship_transfer`（同组织 `move` / 跨组织 `ship`）、
  `reverse_document`（只回退 `create` / `pack` / `ship` / `move`）。

#### 11.15.4 缺口矩阵

| # | 缺口 | 严重度 | 证据（现状） | 对标 |
|---|---|---|---|---|
| 1 | 同一 HU 出现在同单据多行 → 第二次调用失败，**整单发运回滚** | **P1** | `ship_shipment` 逐行 `ship_hu` 无去重；`ship_hu` 对非 `sealed` 直接抛错 | SAP 一箱多行 `VEPO` 原生 |
| 2 | HU 与序列号发运**顺序冲突**：先 `_register_shipment_serials`（SN→`shipped`）再 `_ship_hus`，而 `ship_hu` 要求成员 SN `in_stores` | **P1** | `shipment_service` 先登记 SN 后发 HU | Oracle 容器态与序列号态同源推进 |
| 3 | `status` / `hu_no` / `parent_hu_id` 等状态字段在表单可编辑，未标不可变 | **P1** | `handling_unit.yaml` 的 `status` 仍是可编辑下拉 | SAP `STATUS` 只由事务推进 |
| 4 | 单据行 `hu_no` 是**单值**：一行一箱，一箱多行只能重复填写 | **P1**（模型级） | `receipt_line` / `shipment_line` / `transfer_order_line` 的 `hu_no VARCHAR(40)` | SAP `VEPO.VBELN/POSNR`、Oracle `WSH_DELIVERY_ASSIGNMENTS` |
| 5 | 收货装箱后不封箱，无「封箱」作业节点 | P2 | `pack_receipt` 只 `pack` 不 `seal` | SAP `KZGVH` 封闭包装 |
| 6 | 无单据 → 容器的**正向清单**（只能从 `hu_transactions` 反查） | P2 | 仅有 `hu_where_used(serial_no)` | Oracle 容器内容报表 |
| 7 | 无预分配 / 装箱计划（`planned` 态） | P2 | 状态机只有 `open / sealed / shipped / void` | SAP `Planned` + `XCHAR`；Oracle `DELIVERY_ID` 为空 |
| 8 | 无容量 / 超装校验 | P2 | 无载重、体积、件数上限 | SAP `MAGEW` / `ZUL_AUFL` |
| 9 | 跨组织调拨缺「在途」容器态：源侧直接 `shipped`、目标侧新建 `sealed`，容器身份只靠 `hu_no` 串 | P2 | `ship_transfer` 跨组织走 `ship` | SAP `In transit`；Oracle LPN `In Transit` |
| 10 | 无装箱单 / 箱贴 | P3 | §11.12 已明示不做 | 同左（对标有，但不纳入本阶段） |
| 11 | 无装箱指令合规校验 | P3 | — | SAP `PACKVORSCHR_ST`（不做） |

**无缺口（对齐良好）**：嵌套单父 `UEVEL` / `UNVEL`、空箱复用、HU 不改变库存余额、SSCC 校验位。

#### 11.15.5 建议方案 D17–D19

**D17（新增）：v216 建 `document_hu_links` 显式桥表**

关系从「单据行上的单值文本」下沉为「独立关系行」，对应 SAP `VEPO.VBELN/POSNR` 与 Oracle `WSH_DELIVERY_ASSIGNMENTS`：

```sql
CREATE TABLE document_hu_links (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_type      VARCHAR(30) NOT NULL,   -- receipt / shipment / transfer_order / work_order
  doc_id        INTEGER NOT NULL,
  line_id       INTEGER,                -- 单据行；表头级关系可空
  hu_id         INTEGER NOT NULL,
  direction     VARCHAR(10) NOT NULL,   -- in / out
  link_type     VARCHAR(20) NOT NULL DEFAULT 'packed',  -- planned / packed / shipped
  tentative     INTEGER NOT NULL DEFAULT 0,  -- 1 = 暂定分配（SAP XCHAR / Oracle 未分配）
  qty           REAL,                   -- 该行在该容器内的数量；空 = 整行
  org_id        INTEGER,
  created_at    DATETIME NOT NULL,
  created_by    INTEGER,
  updated_at    DATETIME,
  remark        VARCHAR(255)
);

-- line_id 可空，普通 UNIQUE 在 SQLite 下会放过重复，必须用表达式唯一索引
CREATE UNIQUE INDEX uq_document_hu_link ON document_hu_links(
  doc_type, doc_id, COALESCE(line_id, 0), hu_id, direction);
CREATE INDEX idx_document_hu_doc  ON document_hu_links(doc_type, doc_id);
CREATE INDEX idx_document_hu_hu   ON document_hu_links(hu_id);
CREATE INDEX idx_document_hu_line ON document_hu_links(line_id);
```

口径：

- **一行一关系**：`(doc, line, hu, direction)` 只有一行，`link_type` 沿 `planned → packed → shipped` 推进（不追加重复行）；
  全量历史仍由 `hu_transactions` 承载，桥表只是当前关系投影。
- `tentative=1` 表示未经作业确认的预分配（对应 SAP `XCHAR`、Oracle `DELIVERY_ID IS NULL`）。
- `qty` 是**一行多箱的承载列**（对标 SAP `VEPO.VEMNG`、Oracle 容器明细数量），不是可选装饰：
  行只有 1 条 link 时 `NULL` 表示「整行全量」；一旦该行出现第 2 条 link，所有 link 必须写显式 `qty`。
- 校验：同一 `(doc_type, line_id, direction)` 的 `SUM(qty)` 不得超过单据行数量（容差沿用现有
  `transfer_over_ship_percent` / `transfer_over_receive_percent` 口径）；`SUM(qty) = 行数量` 才算该行装箱完成。
- 落地边界：v216 提供 `pack_line(doc_type, doc_id, line_id, hu_id, qty)` 服务入口承载拆箱；
  现有 `receipt_lines.hu_no` 快捷路径语义不变（整行进一箱）。自动分配与拆箱 UI 不在 v216。
- 关系行仍**一行一关系**（`line_id` + `hu_id` + `direction` 唯一），不做「同一行同一箱多条 qty 行」。
- 枚举：`document_hu_link_type`（`planned` / `packed` / `shipped`）、`document_hu_direction`（`in` / `out`）。
- 权限：`document_hu_link:document_hu_link_read`（只读）；不建独立菜单（由 HU hub 二期加「关联单据」tab 承载）。
- 回填：按 `hu_no` 反查 `handling_units.id`，把存量 `receipt_lines`（`in` / `packed`）、
  `shipment_lines`（`out` / `shipped`）、`transfer_order_lines`（`out` / `shipped`）迁入；
  `hu_no` 无法解析的行**跳过并计数告警**，不阻断迁移。

**D18（新增）：单据行 `hu_no` 降级为快捷录入**

保留 `hu_no` / `hu_type` 两列（兼容存量与手工录单），但语义改为「快捷录入：过账时由服务
`resolve_or_create_hu(hu_no)` 转成 `document_hu_links` 行」；不再把它当作事实源。
与 D7（`serial_no` 快捷录入）同口径。

**D19（修订 H4）：状态机补 `planned` / `in_transit`**

| From | To | 触发 |
|---|---|---|
| `planned` | `open` | 计划转实体（一期只占位，不产生） |
| `planned` | `void` | 计划取消 |
| `open` | `sealed` | 封箱 |
| `sealed` | `in_transit` | 跨组织调拨发出（P2 启用） |
| `in_transit` | `sealed` | 目标组织确认到达（P2 启用） |
| `sealed` | `shipped` | 本组织发运 |
| `in_transit` | `shipped` | 跨组织直接走完（P2） |
| 任意（非 `shipped` / `void`） | `void` | 作废 |

一期目标：新增两个枚举值 + `sealed ↔ in_transit` 两条迁移；`planned` 仅占位，等装箱计划一并启用。

> 落地拆分：v216 只建 `document_hu_links` 与 P1 接线，**不改** `handling_units` 的
> `CHECK (status IN ('open','sealed','shipped','void'))`。SQLite 改 CHECK 必须重建表
> （连带索引与 `handling_unit_items` / `hu_transactions` 外键），风险独立，故
> `planned` / `in_transit` 与 `sealed ↔ in_transit` 状态迁移统一推到 **v217**。

#### 11.15.6 P1 止血（不依赖 v216，先落三项）

| 项 | 改法 | 文件 |
|---|---|---|
| #1 发运去重 | `ship_shipment` / `ship_transfer` 先按 `hu_no` 归并为 `hu_no → [line_id]`，每 HU 只调一次 `ship_hu`，并把全部 `line_id` 一次写入事件；对已 `shipped` 的同单据 HU 视为幂等跳过（`[SKIP]` 日志） | `meta/services/handling_unit_service.py` |
| #2 顺序冲突 | `shipment_service` 改为**先** `_ship_hus` **后** `_register_shipment_serials`；同时让 `register_shipment` 对「同 `(doc_type=shipment, doc_id)` 已 link」的号幂等跳过，避免反向顺序再次踩坑 | `meta/services/shipment_service.py`、`meta/services/serial_number_service.py` |
| #3 语义不可变 | `handling_unit.yaml` 给 `hu_no` / `status` / `parent_hu_id` / `root_hu_id` / `cycle_no` / `sealed_at` / `shipped_at` / `voided_at` 标 `semantics.immutable: true`，状态只由 BO action 推进 | `meta/schemas/handling_unit.yaml` |

三项均不改变物理表结构，可在 v216 之前独立发布。

#### 11.15.7 v216 之后的接线

| 方法 | 变更 |
|---|---|
| `pack_receipt` | 每行写 `link(direction=in, link_type=packed, tentative=0)`；同键已存在则 UPDATE `link_type`，不追加 |
| `ship_hu` | 增加 `line_ids` 入参（缺省 `[line_id]`）；一次把该 HU 所有行的 link 推进到 `shipped`，事件仍写一条（`line_id` 取首行，其余行 id 记 `remark` 或拆多事件） |
| `ship_shipment` | 按 `hu_no` 归并后调用；回写全部行 link |
| `ship_transfer` | 同组织 `move` 不写 link；跨组织写 `direction=out`（源，`org_id=from`，源 HU 置 `in_transit`）+ `direction=in`（目标，`org_id=to`，目标侧新建 HU 置 `sealed`） |
| `reverse_document` | 按 link 回退（`shipped → packed → 删除`），并写反向 `hu_transactions`；**不物理删 link 行**（审计优先，沿用 D13 口径） |
| 新查询 | `hu_documents(hu_id)`（容器 → 单据）、`document_hus(doc_type, doc_id)`（单据 → 容器）、`unassigned_hus(org_id)`（`tentative=1`） |

#### 11.15.8 分期

| 步骤 | 内容 | 依赖 |
|---|---|---|
| P1-1 | 发运去重（#1） | 无 |
| P1-2 | SN/HU 顺序与幂等（#2） | 无 |
| P1-3 | 语义不可变标注（#3） | 无 |
| v216 | `document_hu_links`（含 `qty` 拆箱语义）+ `pack_line` 入口 + 存量回填 + 上述接线（**不含** `planned` / `in_transit`） | P1 |
| v217 | 状态机补 `planned` / `in_transit`（重建 `handling_units` CHECK）+ 跨组织 `sealed ↔ in_transit` 迁移 | v216 |
| v218 | 收货封箱节点（#5）、单据→容器正查 UI（#6，hub 加「关联单据」tab） | v217 |
| 二期 | 装箱单 / 箱贴（#10）、容量校验（#8）、装箱计划（#7 → `planned` 实启用） | v218 |
| 不做 | 装箱指令合规（#11） | — |

#### 11.15.9 验收

| 测试文件 | 覆盖 |
|---|---|
| `meta/tests/test_hu_ship_dedup.py` | 同一 HU 出现在两行 → 只发一次，两行 link 均为 `shipped`；重复过账幂等 |
| `meta/tests/test_hu_serial_order.py` | 序列号物料 + 装箱发运 → 先 HU 后 SN 不冲突；反向顺序亦幂等 |
| `meta/tests/test_hu_document_links.py` | v216 建表/唯一索引（含 `COALESCE(line_id,0)` 兜 NULL）/迁移幂等/回填/回滚；`pack_receipt` 写 link；`ship_hu` 推进；`reverse_document` 回退；**一行多箱 qty 汇总校验**（`SUM(qty)` 不得超行数量、等于行数量才算完成） |
| `meta/tests/test_hu_transit.py` | 跨组织调拨 `sealed → in_transit → sealed`；`in_transit` 不清空 `org_id` |
| `meta/tests/test_hu_immutable.py` | YAML `semantics.immutable` 覆盖 8 个字段 |

入口：`python d:\filework\test.py --single <path>`（禁止 pytest）。

#### 11.15.10 决策（已按 SAP / Oracle 对标定稿，不再逐项确认）

**决策 1：一行多箱 / 部分装箱 —— 纳入 v216，`qty` 是一等列**

| 对标 | 事实 |
|---|---|
| SAP `VEPO` | 内容行主键 `(VENUM, VEPOS)`，每行带 `VBELN` + `POSNR` + `VEMNG`，即「某交货行的某数量进了某箱」；一行拆多箱、一箱装多行都是原生能力 |
| Oracle | 容器本身是 `WSH_DELIVERY_DETAILS` 的一行，数量落在容器明细 / `WMS_LPN_CONTENTS`；`PARENT_DELIVERY_DETAIL_ID` 表达层级，因此同样是行 ↔ 箱的多对多 |

本地现状为什么必须补：`handling_unit_items` **没有** `doc_type` / `doc_id` / `line_id`（只有
`item_id` / `batch_id` / `serial_id` / `qty`），单据行只有单值 `hu_no`，且 §11.5 明写「仅当装箱数量 = 行净收数量」。
这套结构只能表达「一行整箱」，连「一箱多行」都要靠重复写多行实现，**一行多箱完全无法表达**。

结论：v216 把 `qty` 落成真实语义列（见 §11.15.5），并新增 `pack_line(doc_type, doc_id, line_id, hu_id, qty)`
服务入口；`receipt_lines.hu_no` 仍表示「整行进一箱」，作为快捷录入保留。这样模型一次到位，
后端先具备拆箱能力，前端拆箱 UI 与自动分配留到 v218。

**决策 2：跨组织调拨目标侧 —— 保持新建 HU（你的判断成立）**

| 对标 | 事实 |
|---|---|
| SAP | `VEKP.WERKS` 是工厂级对象；跨工厂调拨在途态为 `STATUS=In transit`，收货工厂以自己的 HU 对象承接（物理标签同一个，系统内是目标工厂的新对象） |
| Oracle | LPN 归属组织，`LPN context` 含 `In Transit`；目标组织收货时按 LPN 号重建 LPN |

结论：保持 `_clone_tree` 在目标组织新建 HU、复用同一 `hu_no`。配套修订：源 HU 由 `sealed → in_transit`
（**不再**直接 `shipped`），目标侧新 HU 为 `sealed`；两侧各写一条 link（源 `direction=out`、目标 `direction=in`，
同一 `transfer_order` + 行），据此可还原「同一箱的跨组织链路」。`in_transit` 不清 `org_id`（仍属源组织），
正好与「新建」互补：源对象可查、目标对象可操作。

**决策 3：`planned` —— 只加枚举值，不产生数据；预分配用 `tentative`**

| 对标 | 事实 |
|---|---|
| SAP | `STATUS=Planned` 是 HU 生命周期态；`XCHAR` 是「关系暂定」标记，二者是两个机制 |
| Oracle | 「未分配」由 `WSH_DELIVERY_ASSIGNMENTS.DELIVERY_ID IS NULL` 表达，同样不是容器状态 |

本地没有装箱计划单据，若让 `planned` 真的产生数据，必须先造计划对象（超出本阶段）。
结论：`hu_status` 加 `planned` 枚举值但**不产生数据**（保留位，状态机无入边）；当期真正需要的是
`document_hu_links.tentative=1`，用它查「未确认装箱 / 预分配」，并可按需在 v218 接装箱计划。

#### 11.15.11 改动文件清单（预估）

| 文件 | 改动 |
|---|---|
| `meta/migrations/v216__document_hu_links.py` | 新增：桥表 + 4 索引 + 2 枚举 + 2 权限 + 存量回填（`planned` / `in_transit` 见 v217） |
| `meta/schemas/document_hu_link.yaml` | 新增：只读对象，`skip_auto_menu: true` |
| `meta/services/handling_unit_service.py` | 去重、`line_ids`、link 写入/推进、`pack_line`（一行多箱）、`hu_documents` / `document_hus` |
| `meta/services/shipment_service.py` | 调换 SN / HU 顺序 |
| `meta/services/serial_number_service.py` | `register_shipment` 幂等跳过已 link 的号 |
| `meta/services/transfer_order_service.py` | 跨组织 `in_transit` 接线（v217） |
| `meta/schemas/handling_unit.yaml` | 状态枚举补 2 值；8 个字段 `semantics.immutable` |
| `meta/schemas/receipt_line.yaml` / `shipment_line.yaml` / `transfer_order_line.yaml` | `hu_no` 描述改「快捷录入」 |
| `meta/tests/test_hu_ship_dedup.py` 等 5 个 | 见 §11.15.9 |

> 以上为**方案草案**，未动代码；D17 / D18 / D19 与 §11.15.10 三项决策已定稿，实施前只需确认排期。
