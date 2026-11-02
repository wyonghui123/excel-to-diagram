# Tasks: Transfer Order（调拨单）对象模型

> 配套规格：`docs/specs/spec-transfer-order-object-model-2026-11-02.md`
> 状态：已实施（T1-T10 全部完成；v190 迁移 verify PASS，TO 测试 85 用例 + PO/Receipt 回归 102 用例全绿）
> 日期：2026-11-02（实施完成日）

---

## 0. 前置约束

1. 测试唯一入口：`python d:\filework\test.py --single|--file|--failed`，禁止 pytest。
2. 服务管理只用 `scripts/service_manager.py` / `service_manager.ps1`；后端改动验证用私有槽位。
3. 数据库不直读写 `meta/architecture.db`；迁移走 `MigrationRunner`。
4. 迁移号：`v188` / `v189` 已占用，本波使用 `v190`。
5. 涉及两条启动路径的拦截器必须双处注册：`meta/core/app_builder.py` 与 `meta/server.py`。
6. 本波不实现任何库存域对象；`qty_shipped` / `qty_received` 是单据缓存。

---

## 1. Schema 对象

### T1.1 `meta/schemas/transfer_order.yaml`

新增头对象：

- `id: transfer_order`
- `name: 调拨单`
- `table_name: transfer_orders`
- `description: 调拨单头（调拨行见 transfer_order_line）`
- `display_name_field: transfer_order_no`
- `aspects: [audit_aspect, document_type_aspect]`
- `semantics.category: business_document`；`business_key: [transfer_order_no]`

字段（按 Spec §3.1）：

- `transfer_order_no`：string(30)，required，unique，取号生成，`ui.readonly`
- `document_type_id`：由 `document_type_aspect` 提供（不重复声明）
- `transfer_date`：date，required
- `status`：enum draft / released / closed / cancelled，default draft
- `fulfillment_status`：enum open / partially_shipped / shipped / partially_received / received，nullable，`semantics.hint: 只读缓存，由服务层派生`
- `from_org_id`：integer，required，value_help → `org`（active 过滤）；`ui.relation: org`
- `to_org_id`：同上
- `legal_entity_id`：integer，required，`ui.readonly: true`；语义"法人实体快照（由 from/to 上溯，不直接维护）"
- `from_location_id` / `to_location_id`：integer，nullable，value_help → `location`
- `project_id`：integer，nullable，value_help → `project`
- `actual_ship_date`：date，nullable，`ui.readonly`
- `carrier_name`：string(100)，nullable
- `waybill_no`：string(50)，nullable
- `remark`：text，nullable

索引（按 Spec §3.3）。

关系：

- `transfer_order_to_type_definition`
- `transfer_order_to_from_org`
- `transfer_order_to_to_org`
- `transfer_order_to_legal_entity`
- `transfer_order_to_from_location`
- `transfer_order_to_to_location`
- `transfer_order_to_project`

`ui_view_config`：

- list 列：`transfer_order_no` / `transfer_date` / `from_org_id` / `to_org_id` / `status` / `fulfillment_status` / `document_type_id`
- form 分区：单据信息（类型 / 日期 / 状态）、组织与库位（from/to org、legal entity 只读、from/to location）、来源与项目（project_id）、发运信息（actual_ship_date / carrier_name / waybill_no 只读）、其他（remark）
- detail：tabs 基本信息 + 调拨行
- `child_sections`: `transfer_order_line`，title 调拨行

`category_config` 权限码按 Spec §9.1。

### T1.2 `meta/schemas/transfer_order_line.yaml`

新增行对象：

- `id: transfer_order_line`
- `name: 调拨行`
- `table_name: transfer_order_lines`
- `display_name_field: line_no`
- `parent_object: transfer_order`
- `hierarchy.enabled: true`，`parent_field: transfer_order_id`

字段（按 Spec §3.2）：

- `transfer_order_id`：integer，required，`ui.relation: transfer_order`
- `line_no`：integer，required
- `line_type_id`：integer，required，`ui.readonly: true`；语义"由头类型 default_type_id 带出，本波固定 TRF_GOODS"
- `item_id`：integer，required，value_help → `item`（active、`item_type='goods'`）
- `uom_id`：integer，required，value_help → `uom`
- `qty`：number，required，`gt: 0`，`decimal_places: 6`
- `qty_shipped`：number，required，default 0，`gte: 0`，`decimal_places: 6`，`ui.readonly`
- `qty_received`：number，required，default 0，`gte: 0`，`decimal_places: 6`，`ui.readonly`
- `status`：enum open / closed / cancelled，default open
- `fulfillment_status`：enum 同头，nullable，只读缓存
- `remark`：text

索引：`transfer_order_id` / `item_id` / `line_type_id` + `UNIQUE(transfer_order_id, line_no)`。

关系：

- `transfer_order_line_to_order`
- `transfer_order_line_to_line_type`
- `transfer_order_line_to_item`
- `transfer_order_line_to_uom`

`ui_view_config`：`skip_auto_menu: true`，作为头详情子表。

---

## 2. 迁移

### T2 `meta/migrations/v190__transfer_order_object.py`

结构仿 `v186__receipt_object.py`：

1. 常量和建表：

```python
SCOPE_BO = 'transfer_order'
HEADER_TYPE = ('TRF_STD', '标准调拨单', 'standard',
               '同法人不同库存组织之间的内部调拨单据类型')
LINE_TYPE = ('TRF_GOODS', '标准物料行', 'material', 1,
             '可发货、可收货的实物物料行')
NUMBER_SEQUENCE = ('TRF', '调拨单编号', 'TRF-{DATE:yyyymm}-{SEQ:6}',
                   'transfer_date', 1, 'error',
                   '调拨单按调拨日期年度取号')
```

`transfer_orders` DDL（列、类型、默认值按 Spec §3.1）：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `transfer_order_no VARCHAR(30) NOT NULL UNIQUE`
- `document_type_id INTEGER NOT NULL`
- `transfer_date DATE NOT NULL`
- `status VARCHAR(20) NOT NULL DEFAULT 'draft'`
- `fulfillment_status VARCHAR(30) NULL`
- `from_org_id INTEGER NOT NULL`
- `to_org_id INTEGER NOT NULL`
- `legal_entity_id INTEGER NOT NULL`
- `from_location_id INTEGER NULL`
- `to_location_id INTEGER NULL`
- `project_id INTEGER NULL`
- `actual_ship_date DATE NULL`
- `carrier_name VARCHAR(100) NULL`
- `waybill_no VARCHAR(50) NULL`
- `remark TEXT NULL`
- 审计列（与平台一致：`created_at` / `updated_at` / `created_by` / `updated_by`）

`transfer_order_lines` DDL：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `transfer_order_id INTEGER NOT NULL`
- `line_no INTEGER NOT NULL`
- `line_type_id INTEGER NOT NULL`
- `item_id INTEGER NOT NULL`
- `uom_id INTEGER NOT NULL`
- `qty DECIMAL(20,6) NOT NULL`
- `qty_shipped DECIMAL(20,6) NOT NULL DEFAULT 0`
- `qty_received DECIMAL(20,6) NOT NULL DEFAULT 0`
- `status VARCHAR(20) NOT NULL DEFAULT 'open'`
- `fulfillment_status VARCHAR(30) NULL`
- `remark TEXT NULL`
- 审计列
- `UNIQUE (transfer_order_id, line_no)`

2. 类型种子（按 `(scope_bo, level, code)` 判重，已存在只刷新名称/说明，不覆盖 status）：

- header INSERT：`(code, name, scope_bo, level, document_category, status, description, created_at)`
- line INSERT：`(code, name, scope_bo, level, line_category, delivery_relevant, status, description, created_at)`

3. 绑定：

- header `TRF_STD.default_type_id = TRF_GOODS.id`
- header `TRF_STD.number_sequence_id = TRF.id`

4. 编号序列：按 v177 的 `NUMBER_SEQUENCE` 元组与 `number_sequences` INSERT 列口径写入。

5. 权限（10 条，双段式）：

- `transfer_order:transfer_order_create/read/update/delete/list`
- `transfer_order:transfer_order_release/ship/receive/cancel/close`

6. 菜单：

- `menu_code: transfer-order-management`
- `menu_name: 调拨单`
- `parent_menu: procurement`
- `page_type: object_list`
- `primary_object_type: transfer_order`
- `object_types: ['transfer_order']`
- `bo_bindings: [{bo_id: transfer_order, role: primary, include_actions: [create, read, update, delete, list]}]`
- `required_permissions` 为 CRUD 5 条
- `sort_order: 3`
- `icon: Van`（或同语义图标）
- `show_in_sidebar: 0`（与 receipt 一致）
- `data_permission_hint.resource_types: ['transfer_order']`

7. `verify()` 输出 PASS / FAIL，至少检查：

- 两张表存在且列集合匹配
- 索引存在
- `TRF_STD` 的 `document_category='standard'`、`default_type_id` 指向 `TRF_GOODS`、`number_sequence_id` 指向 `TRF`
- `TRF_GOODS` 的 `line_category='material'`、`delivery_relevant=1`
- 序列 `TRF` 存在
- 10 条权限存在
- 菜单与菜单权限存在

### T2.1 `meta/scripts/init_menu_permissions.py`

在 `MIGRATION_OWNED_MENUS` 白名单追加 `'transfer-order-management'`，避免初始化脚本第 7.5/7.6 步删除 migration 建的菜单。

---

## 3. 服务与守卫

### T3.1 `meta/services/transfer_order_guard_service.py`

新增 `TransferOrderGuardService`，至少提供：

- `validate_create(data)`
- `validate_update(order_id, data)`
- `validate_delete(order_id)`
- `validate_release(order_id)`
- `validate_ship(order_id, payload)`
- `validate_receive(order_id, payload)`
- `validate_cancel(order_id)`
- `validate_close(order_id)`
- `validate_line(order_id, line_data)`
- `resolve_legal_entity(org_id)`（复用 sourcing 上溯口径，或调用 `SourcingService._resolve_legal_entity`）

校验项对应 R-TO-0 ~ R-TO-13。

### T3.2 `meta/services/transfer_order_service.py`

新增 `TransferOrderService`，至少提供：

- `release(order_id, user_context=None)`
- `ship(order_id, payload, user_context=None)`
- `cancel(order_id, reason=None, user_context=None)`
- `close(order_id, user_context=None)`
- `recompute_fulfillment(order_id)`（头 + 行派生）
- `apply_receipt(order_id, receipt_lines)`（供 `ReceiptService.post` 调用）
- `reverse_receipt(order_id, receipt_lines)`（供 `ReceiptService.reverse` 调用）
- `create_from_transfer_order(...)` 不放在本服务；收货单创建委托 `ReceiptService`

实现要求：

- 所有状态迁移单事务；
- `ship` 使用条件 UPDATE 原子累加，禁止读-改-写竞态；
- `apply_receipt` 按净收（`qty_received - qty_rejected`）累加，超 `qty_shipped` 拒绝；
- 全部行收满时头 `status='closed'`、`fulfillment_status='received'`；
- `reverse_receipt` 扣减并把因收满而 closed 的头回退为 released。

---

## 4. 拦截器

### T4.1 `meta/core/interceptors/transfer_order_guard_interceptor.py`

新增 `TransferOrderGuardInterceptor`：

- 拦截 `transfer_order` / `transfer_order_line` 的 create / update / delete；
- 创建时归一化默认值、校验类型、组织、法人、行；
- release / ship / receive / cancel / close 委托 `TransferOrderService`；
- 错误码至少包含：`TO_TYPE_INVALID` / `TO_ORG_INVALID` / `TO_ORG_SAME` / `TO_LE_MISMATCH` / `TO_LE_UNRESOLVED` / `TO_LINE_INVALID` / `TO_QTY_INVALID` / `TO_STATUS_INVALID` / `TO_OVER_SHIP` / `TO_OVER_RECEIVE`。

### T4.2 双处注册

- `meta/core/app_builder.py`（`with_interceptors`）追加 `register_interceptor(TransferOrderGuardInterceptor())`
- `meta/server.py`（`create_app`）追加同段代码

两处必须一致，缺一会静默失效。

---

## 5. 动作

### T5.1 `meta/services/transfer_order_actions.py`

新增 5 个 handler（结构仿 `receipt_actions.py`）：

- `release_handler(params, context=None)`
- `ship_handler(params, context=None)`
- `receive_handler(params, context=None)`
- `cancel_handler(params, context=None)`
- `close_handler(params, context=None)`

`receive_handler` 调 `ReceiptService.create_from_transfer_order(...)`，返回 draft 收货单 id；不直接过账。

### T5.2 `meta/services/bo_action_registrations.py`

按 receipt 既有条目格式追加 5 条：

- `transfer_order` / `release` → `transfer_order_actions.release_handler`
- `transfer_order` / `ship` → `transfer_order_actions.ship_handler`
- `transfer_order` / `receive` → `transfer_order_actions.receive_handler`
- `transfer_order` / `cancel` → `transfer_order_actions.cancel_handler`
- `transfer_order` / `close` → `transfer_order_actions.close_handler`

---

## 6. 收货桥接

### T6.1 `meta/services/receipt_service.py`

新增 / 修改：

- `create_from_transfer_order(transfer_order_id, lines, receipt_date=None, ...)`：按 Spec §7.2 映射创建 draft 收货单；
- `post`：当 `source_doc_type='transfer_order'` 时，不调 PO 计划行回写与 `PurchaseOrderFulfillmentService`，改调 `TransferOrderService.apply_receipt`；
- `reverse`：当来源为 TO 时调 `TransferOrderService.reverse_receipt`；
- 草稿删除 / cancel 不触碰 TO 数量。

### T6.2 `meta/services/receipt_guard_service.py`

- TO 来源跳过 PO 专属校验（供应商、计划行、PO 容差）；
- 新增 TO 校验：`source_line_id` 必须属于 `source_doc_id` 指向的 TO；收货净收累计不得超过 TO 行 `qty_shipped`；TO 头必须 `status='released'`。

### T6.3 `meta/schemas/receipt.yaml`

- `source_doc_type` 的 `transfer_order` 标签由"转移单"改为"调拨单"（仅文案，无结构变更）。

---

## 7. 测试

### T7.1 `meta/tests/transfer_order_test_doubles.py`

提供 TO 测试数据构造：组织（含 inventory 职能 / legal_entity 职能）、法人、物料、单位、库位、单据类型、TO 头/行。

### T7.2 `meta/tests/test_transfer_order_schema.py`

断言：

- schema registry 能加载 `transfer_order` / `transfer_order_line`
- 字段集合、必填、默认值、索引、关系与 Spec 一致
- `TRF_STD` / `TRF_GOODS` 类型种子存在，scope / level / category 正确
- `TRF_STD.default_type_id` 指向 `TRF_GOODS`
- `TRF` 序列存在，pattern / date_field 正确

### T7.3 `meta/tests/test_transfer_order_service.py`

覆盖：

- 创建草稿：取号、默认行类型、legal_entity 快照
- release：冻结字段
- ship：部分发货 / 全部发货 / 超发拒绝
- receive：生成 draft 收货单
- 收货 post：回写净收、全部收满自动 close
- 收货 reverse：扣减、closed 回退 released
- cancel：未发货可取消；已发货拒绝
- close：短收结案；在途未清拒绝
- delete：仅 draft

### T7.4 `meta/tests/test_transfer_order_guard.py`

覆盖：

- 同组织拒绝、缺 inventory 职能拒绝
- 跨法人拒绝、法人解析失败拒绝
- 非 goods 物料拒绝
- 行类型 scope 错误拒绝
- release 后修改冻结字段拒绝
- 库位相同拒绝（同时存在时）

### T7.5 `meta/tests/test_transfer_order_receipt_bridge.py`

覆盖：

- 收货头字段映射（source / org / supplier / location）
- 收货行 `source_line_id` / `schedule_id` / `order_id`
- 净收回写与超收拒绝
- 红冲冲减
- PO 来源收货回归不受影响

---

## 8. 验证与验收

### T8.1 迁移执行

新增 `.trae/debug/to_run_migration.py`（仿 `rec_run_migration.py`），走 `MigrationRunner.run_migration` 执行 v190；执行后打印 verify 结果。

新增 `.trae/debug/to_state.py` 以 `PRAGMA table_info` 动态读列，检查：

- 两表列集合
- 类型 / 序列 / 权限 / 菜单行
- 示例 TO 数据

### T8.2 测试命令

```powershell
python d:\filework\test.py --single meta/tests/test_transfer_order_schema.py
python d:\filework\test.py --single meta/tests/test_transfer_order_service.py
python d:\filework\test.py --single meta/tests/test_transfer_order_guard.py
python d:\filework\test.py --single meta/tests/test_transfer_order_receipt_bridge.py
python d:\filework\test.py --failed
```

### T8.3 回归

- `meta/tests/test_receipt_service.py`
- `meta/tests/test_receipt_reversal.py`
- `meta/tests/test_receipt_allocation.py`
- `meta/tests/test_purchase_order_schema.py`
- `meta/tests/test_demand_allocation_schema.py`

### T8.4 验收清单

- [ ] v190 verify PASS
- [ ] schema 注册无报错
- [ ] 四个新测试文件全绿
- [ ] 既有收货 / PO / 需求分配测试全绿
- [ ] TO 全链路（create → release → ship → receive → post → close）可跑
- [ ] 收货红冲回退 TO 数量与状态
- [ ] 代码无库存域依赖、无金额字段
- [ ] 菜单不被 `init_menu_permissions.py` 清理

---

## 9. 文档同步

### T9

- `docs/specs/spec-receipt-object-model-2026-11-01.md` 追加“TO 来源收货字段映射”小节；
- `docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md` 追加 TO 落地状态；
- 本 Spec 与 tasks 的状态从“待评审”改为“已实施”。

PO / receipt 的跨法人一致性守卫（R-RC-19 / `purchase_legal_entity_id`）不在本波实现，保留在 TBD-10。

---

## 10. 提交

实施与验证完成后，按 Conventional Commits 提交：

```
feat(transfer-order): add transfer order object model and receipt bridge
```

仅在用户确认后提交；不 push。

---

## 11. 审批

本 tasks 与配套 Spec 需用户确认以下 3 项后才能进入实施：

1. 行类型只建 `TRF_GOODS`（不建 `TRF_TEXT`）；
2. 不建金额 / 成本字段（成本留给库存域 TODO）；
3. `from_location_id` / `to_location_id` 可空（默认组织级调拨）。

确认后按 T1 → T9 顺序实施；T10 提交需另行确认。
