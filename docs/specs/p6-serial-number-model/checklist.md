# P6a 验收清单

> 对应 [spec.md](./spec.md) / [tasks.md](./tasks.md)。每项以测试或直读代码为证据。

## Schema

- [x] `serial_number` 对象声明 §3.1 全部字段，`serial_no` 为业务键且 `max_length=64`
- [x] `serial_numbers` 5 条索引已声明：`uq_serial_number` / `uq_serial_uii`（部分唯一）/ `idx_serial_org_item` / `idx_serial_parent` / `idx_serial_status`
- [x] `serial_transaction` / `document_serial_link` 为只读面（仅 read/list，无 create/update/delete）
- [x] `serial_transactions` 3 条索引、`document_serial_links` 3 条索引（含 `uq_document_serial_link`）
- [x] `items` 三开关 `serial_tracked` / `require_on_receipt` / `require_on_issue`（boolean，默认 0，分组 210）
- [x] `receipt_line.serial_no` 与 `shipment_line.serial_no` 宽度统一为 200，描述为快捷录入口径
- [x] 未建 `receipt_serial_lines` / `shipment_serial_lines` 物理表
- [x] `inventory_transactions` 未新增 `serial_id`

## 服务

- [x] `SerialNumberError` 携带 `message` / `field_name` / `rule`
- [x] `create_serial` 校验 `item.serial_tracked=1`、唯一键、初始 `defined`，并写 `create` 事件
- [x] `validate_line_serials` 校验数量相等、同批不重复、`out` 方向在库、未管理物料不得传号
- [x] `register_receipt`：建号或复用、`in_stores` + `current_location_id`、写 `receive` 事件与 `links(direction=in)`
- [x] `register_shipment`：校验在库、`shipped` + `current_location_id=NULL` + `shipped_at`、写 `ship` 事件与 `links(direction=out)`
- [x] `change_status` 按 §3.5 白名单执行，非法跳转抛 `SERIAL_STATUS_TRANSITION_INVALID`
- [x] `reverse_serial_event` 写反向事件并回退状态，原 link 保留
- [x] `trace_serial` 返回主档 + 事件时间线 + 关联单据，跨组织按 `org_id` 分组

## 过账与拦截器

- [x] 收货 `qty=1` 且 `serial_no` 非空 → 自动建 link；`qty>1` 单值 → `SERIAL_SINGLE_VALUE_WITH_MULTI_QTY`
- [x] 收货 `require_on_receipt=1` 且 link 数量不符 → `SERIAL_RECEIPT_COUNT_MISMATCH`
- [x] 发运 `require_on_issue=1` 且号不在库 → 拒绝；正常发运置 `shipped`
- [x] P59 / P60 两个拦截器已实现，并在 `app_builder.py` 与 `server.py` 双路径注册
- [x] 非法保存被转 `ValidationFailedError`

## 迁移 v202

- [x] 三表 + 索引 + `items` 三列 + 5 枚举 + 权限 + 三菜单（107 / 7 / 8）
- [x] 回填：`qty=1` 收货行与发运行建主档 + link；`org_id` 分别取 `receipt.org_id` 与 `ship_from_location_id → location.org_id`
- [x] `qty>1` 单值行跳过并写 `SERIAL_BACKFILL_SKIPPED_MULTI_QTY`；重复号保留最早并写 `SERIAL_BACKFILL_DUPLICATE`
- [x] 迁移幂等（重复 `migrate` 打印 `[SKIP]`）与 `rollback` 可回退
- [x] `verify` 校验三表、三列、枚举与回填计数

## 测试

- [x] `test_serial_number_schema.py` 全绿
- [x] `test_serial_number_service.py` 全绿
- [x] `test_serial_tracking_posting.py` 全绿
- [x] `test_serial_number_migration.py` 全绿
- [x] `test_items_default_rules.py` / `test_receipt_schema.py` / `test_shipment_schema_rules.py` 全绿
- [x] 全量回归无新增失败

## v218 单据↔容器查询与封箱作业台（已实施）

- [x] `document_hu_link_view` 已建，仅 read/list，`view_definition` 与迁移 SQL 一致
- [x] 视图 18 列齐全，`doc_no` / `doc_date` / `line_no`（shipment 回退 `line_id`）正确
- [x] hub「关联单据」tab 可按 `hu_id` 子树（effective）过滤，父托盘能带出子箱单据（视图 `hu_id__in` 用例覆盖）
- [x] `badge_map` 已补 `planned` / `in_transit`
- [x] 反查页支持「单据查容器」「容器查单据」两个方向
- [x] 封箱页扫码预检返回 `can_seal` + `blockers`，与 `seal()` 规则一致
- [x] 封箱 / 解封 / 批量封箱接口权限与 404/409/400/403 映射正确
- [x] 两菜单 `custom_page` 静态路由已注册，非 admin 无 seal 权限时 403
- [x] `test_hu_document_link_view.py` / `test_hu_seal_api.py` 全绿；HU 四文件回归全绿
- [x] 生产入口冒烟：`/api/v1/handling-units` 不死锁 410、`/scan` 返回结构化 `HU_NOT_FOUND`
- [x] FE 运行态冒烟：`/warehouse/handling-unit-docs` 与 `/warehouse/handling-unit-seal` 均渲染成功且无 JS 错误
- [x] 真实数据全链路手验待真实库迁移（120 条 pending 收尾后执行），不阻塞本次代码交付

## 边界

- [x] 未实现调拨 / 盘点 / 调整 / 退货的序列号执行
- [x] 未实现生产完工号与谱系服务、未实现多父 / 跨组织谱系 / 全局唯一
- [x] 未建 `serial_balances`，未引入设备 / 资产 / 维修状态机
- [x] 未做行内嵌子表 UI
