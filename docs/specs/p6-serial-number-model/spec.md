# P6 实现规格：序列号对象模型（主档 / 事件账 / 对象清单）

- 日期: 2026-11-03
- 状态: **待批准**（批准后才动代码）
- 上游依据:
  - SAP / Oracle 序列号对象模型研究结论（`EQUI.GERNR` / `EQBS` / `OBJK` 与 `INV_SERIAL_NUMBERS`）
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

| 阶段 | 内容 |
|---|---|
| P6a（本 Spec） | 三表 + items 三开关 + 收货/发运录号 + 按号查历史 + 回填 |
| P6b | 调拨 / 盘点 / 调整 / 退货；`quality_status` 流转；`issue_created` 建档（已细化：`docs/specs/p6b-serial-execution/spec.md`） |
| P6c | 完工成品号 + 组件单父谱系（`relation_type=assembly`） |
| P7 | 全局唯一（`serial_uniqueness_scope`）、多父谱系、包装嵌套（`packaging`）、序列号级预留 |
