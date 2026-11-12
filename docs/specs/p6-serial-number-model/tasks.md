# P6 实施任务（P6a）

> 规格: [spec.md](./spec.md)；批准后按序执行，每项完成即验证。**不 commit**。
> 只做 P6a 边界：三表 + items 三开关 + 收货/发运录号 + 按号查历史 + 回填。
> P6b/P6c/P7 不在本批任务内。

## [x] T1 Schema：serial_number 主档

- 文件: `meta/schemas/serial_number.yaml`（新建）
- 内容:
  - 对象 `serial_number` / 表 `serial_numbers` / `display_name_field: serial_no` / `aspects: [audit_aspect]`。
  - §3.1 全部字段；`serial_no` 标 `business_key: true`、`max_length: 64`；布尔/枚举/关联字段三态 UI 补全。
  - 5 条索引：`uq_serial_number`（`item_id, org_id, serial_no`）、`uq_serial_uii`（部分唯一 `uii IS NOT NULL`）、`idx_serial_org_item`、`idx_serial_parent`、`idx_serial_status`。
  - 枚举引用：`serial_usage_status` / `serial_quality_status` / `serial_source_type` / `serial_relation_type`（值由 v202 注册，YAML 只声明）。
  - 三态 UI：`list` 7 列（序列号/物料/组织/批次/用途状态/质量状态/当前库位）、`form` 分组（身份 / 归属 / 状态 / 谱系 / 来源）、`detail` tab。
  - 四权限：`serial_number:serial_number_{read|create|update|delete}`。
- 验收: YAML 可加载、字段与 5 条索引声明用例通过。

## [x] T2 Schema：serial_transaction + document_serial_link

- 文件: `meta/schemas/serial_transaction.yaml`、`meta/schemas/document_serial_link.yaml`（新建）
- 内容:
  - 两个对象均只读：显式声明 `read` / `list` 动作 + `import_export.auto_crud: false`（与 `inventory_transaction.yaml` 同口径，避免 `ensure_crud_actions` 自动补 create/update/delete）。
  - 两者 `skip_auto_menu: true`，菜单由 T7 迁移的独立列表承载。
  - 字段按 §3.2 / §3.3；`txn_type` 引用 `serial_txn_type` 枚举；索引：`(serial_id, txn_date)`、`(inventory_transaction_id)`、`(doc_type, doc_id)`；links 表 `uq_document_serial_link`（`doc_type, line_id, serial_id`）+ `idx_document_serial_doc` + `idx_document_serial_serial`。
  - 不建 `receipt_serial_lines` / `shipment_serial_lines` 物理表。
- 验收: 两个 schema 声明用例通过；CRUD 动作集合只含 read/list。

## [x] T3 Schema 修改：items + 两个单据行

- 文件: `meta/schemas/items.yaml`
  - 追加 `serial_tracked` / `require_on_receipt` / `require_on_issue`（boolean，`fieldGroup: 序列号`，`fieldGroupPosition: 210`）。
- 文件: `meta/schemas/receipt_line.yaml`、`meta/schemas/shipment_line.yaml`
  - `serial_no.max_length` 64 → 200（对齐 `generated_schema.sql` 的 `VARCHAR(200)`）。
  - `serial_no.description` 改为“快捷录入：`qty=1` 时可直接录号；`qty>1` 必须走序列号子表”。
- 验收: `test_items_default_rules.py` / `test_receipt_schema.py` / `test_shipment_schema_rules.py` 相关断言翻新后通过。

## [x] T4 SerialNumberService

- 文件: `meta/services/serial_number_service.py`（新建）
- 内容:
  - `SerialNumberError(message, field_name, rule)`。
  - `create_serial(payload)`：`item.serial_tracked=1`、`(item, org, serial)` 唯一、初始 `defined`、写 `create` 事件。
  - `validate_line_serials(item_id, org_id, qty, serials, direction, doc)`：数量等于 `qty`、同批不重复、`out` 方向须在库、`serial_tracked=0` 时 `serials` 必须为空。
  - `register_receipt(receipt_id)` / `register_shipment(shipment_id)`：建号或复用、写事件、写 `document_serial_links`、更新主档三轴状态。
  - `change_status(serial_id, to_status, reason, doc=None)`：按 §3.5 白名单，非法跳转抛 `SERIAL_STATUS_TRANSITION_INVALID`。
  - `reverse_serial_event(inventory_transaction_id)`：写反向事件并回退主档状态，**不删** 原 link（D13）。
  - `trace_serial(serial_no, org_id=None)`：主档 + 事件时间线 + 关联单据；跨组织按 `org_id` 分组。
- 约束: 状态流转只走服务层，禁止前端 PATCH `usage_status`；不给 `inventory_transactions` 加 `serial_id`。
- 验收: 服务用例全绿（唯一键 / 状态机 / 反冲 / 按号查历史）。

## [x] T5 过账钩子接入

- 文件: `meta/services/receipt_service.py`（`post()` 与 `_post_receipt_inventory`）
  - 入口前：`require_on_receipt=1` 且 `qty_received>1` 必须已有等量 link，否则 `SERIAL_RECEIPT_COUNT_MISMATCH`。
  - `qty_received=1` 且 `serial_no` 非空 → 自动建 link。
  - `qty_received>1` 且 `serial_no` 非空 → `SERIAL_SINGLE_VALUE_WITH_MULTI_QTY`。
  - 过账成功后调 `register_receipt`。
- 文件: `meta/services/shipment_service.py`（`ship_confirm`）
  - 入口前：`require_on_issue=1` 时 link 数量 = `qty` 且全部 `in_stores`。
  - `qty=1` 且 `serial_no` 非空 → 自动建 link；成功后调 `register_shipment`。
- 约束: 不修改 `InventoryPostingService` 的追加式语义，桥接只用 `serial_transactions.inventory_transaction_id`（可空）。
- 验收: 收货/发运录号用例通过（含 `qty=1` 快捷与 `qty=3` 三号）。

## [x] T6 拦截器与双路径注册

- 新增 `meta/core/interceptors/serial_number_guard_interceptor.py`（P59）：`serial_numbers` 的 create / update 校验（物料已开启管理、唯一键、状态合法、`scrapped` 不可改）。
- 新增 `meta/core/interceptors/serial_tracking_guard_interceptor.py`（P60）：收货 / 发运过账前置校验（§6.1）。
- 修改 `meta/core/app_builder.py` 与 `meta/server.py` 各注册两个拦截器（与 P57/P58 同口径）。
- 验收: 启动路径导入无错；非法保存被转 `ValidationFailedError`。

## [x] T7 迁移 v202

- 文件: `meta/migrations/v202__serial_number_model.py`
- 内容:
  1. 三表 + 索引（含 `uq_serial_uii` 部分唯一）。
  2. `items` 加三列（SQLite `ALTER TABLE ADD COLUMN`，`INTEGER NOT NULL DEFAULT 0`）。
  3. 注册 5 个枚举：`serial_usage_status` / `serial_quality_status` / `serial_source_type` / `serial_relation_type` / `serial_txn_type`。
  4. 权限与授权（`admin` / `default`）；三个菜单：`serial-number-list`（master-data，`sort_order=107`）、`serial-transaction-list`（inventory，7）、`document-serial-link-list`（inventory，8）；实施时以 DB 当前最大值为准，被占用则顺延。
  5. 回填：`qty=1` 的收货行 / 发运行建主档 + link；`qty>1` 单值跳过并写 `SERIAL_BACKFILL_SKIPPED_MULTI_QTY`；重复号保留最早并写 `SERIAL_BACKFILL_DUPLICATE`；每行先查唯一键保证幂等。
- 接口: `migrate(db_path, skip_backup=False)` / `verify(db_path)` / `rollback(db_path)` / `downgrade = rollback`；表 / 索引 / 枚举 / 权限 / 菜单先查后用，重复执行打印 `[SKIP]`。
- 验收: `migrate → verify → 再 migrate → verify → rollback → verify 失败`。

## [x] T8 测试

- 新建 `meta/tests/test_serial_number_schema.py`（字段 / 5 索引 / 只读面 / 枚举引用）。
- 新建 `meta/tests/test_serial_number_service.py`（唯一键、状态机、反冲、按号查历史）。
- 新建 `meta/tests/test_serial_tracking_posting.py`（收货 / 发运录号与三种错误码）。
- 新建 `meta/tests/test_serial_number_migration.py`（v202 建表加列、枚举、菜单、回填幂等、rollback）。
- 修改 `test_items_default_rules.py`（三开关）、`test_receipt_schema.py`（`max_length` 200）、`test_shipment_schema_rules.py`（`max_length` 200）。
- 验收: 7 个文件 `python d:\\filework\\test.py --single <path>` 均通过（禁止 pytest）。

## [x] T9 回归与报告

- `python d:\filework\test.py --failed`（若有并发假失败，串行复跑确认）。
- 输出改动清单 + 测试结果；**不 commit、不部署**。

## [x] V218 单据↔容器查询与封箱作业台（方案已批准，spec §11.16）

- [x] V1 只读视图：新建 `meta/schemas/document_hu_link_view.yaml`（`is_view: true`、仅 read/list）与 `meta/migrations/v220__document_hu_link_view.py`（DROP+CREATE、verify 列数 18、缺基表 SKIP、rollback 仅删视图）；`view_definition` 与迁移 SQL 逐字一致。
- [x] V2 hub tab：`handling_unit.yaml` 的 `hub.object_types` 加 `document_hu_link_view`，tab 名「关联单据」，filter `{field: hu_id}`（effective 子树）；`badge_map` 补 `planned` / `in_transit`。
- [x] V3 反查页：新建 `src/views/HandlingUnitDocs.vue`（单据查容器 / 容器查单据两 tab），`src/services/handlingUnitService.js`，路由 `/warehouse/handling-unit-docs`（`business.js` + `dynamicRoutes.js` 白名单）。
- [x] V4 封箱台：服务抽 `seal_check`；新建 `meta/api/handling_unit_api.py`（6 端点，错误码 404/409/400/403）；`app_builder.with_blueprints` 注册；新建 `src/views/HandlingUnitSeal.vue` 与路由 `/warehouse/handling-unit-seal`。
  - [x] 生产入口补齐：`meta/server.py` 增加 blueprint 注册（否则 waitress 运行态 `/scan` 404、列表被通用 BO 路由兜底）与 v1 sunset 白名单 `handling-units`（否则 410）。
- [x] V5 权限/菜单：新建 `meta/migrations/v221__hu_seal_workbench.py`（`handling_unit:handling_unit_seal` / `_unseal`，admin 全授、default 只读；两菜单 `custom_page`，幂等 UPSERT + rollback）。
  - [x] 补建库存域根菜单 `inventory`（历史迁移只引用未创建；缺失时子菜单挂顶层且 `show_in_sidebar=0` ⇒ 侧栏不可见）。
- [x] V6 测试：新增 `meta/tests/test_hu_document_link_view.py`、`meta/tests/test_hu_seal_api.py`；回归 `test_hu_posting/transfer/schema/document_links`；`python -m meta.tools.sync_schema --generate` 后核对视图 DDL。
- [x] V7 验收：自动化（视图/API 测试、FE `npm run build`）+ 生产入口冒烟（3010 `/api/v1/handling-units` 返回空列表，`/scan` 返回 `HU_NOT_FOUND`）。真实数据手工验收（hub tab / 反查页 / 封箱页全链路）待真实库迁移（v211+ 共 120 条 pending，等并发 WIP 收尾后统一执行）。
