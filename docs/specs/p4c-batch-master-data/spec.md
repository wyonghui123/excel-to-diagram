# P4c 批次主数据实现规格（batches + batch_attribute_values）

- 日期: 2026-11-03
- 状态: **待批准**（批准后才动代码）
- 上游依据:
  - `docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md` v0.5 §11（P4c）/ §11.7（特性接入）
  - 主 Spec v1.22 附 C.3
- 迁移号: **v196**（当前最大 `v195__purchase_legal_entity.py`；spec 正文里的 v193 是旧估算，不采用）

## 1. 目标与范围

**做**：建 `batches`（最小批次主数据）+ `batch_attribute_values`（复用属性字典的值表），并接入守卫拦截器、迁移、权限、菜单与测试。

**不做**（已拍板，勿重复讨论）：
- 不建 `characteristics_json` / `batch_characteristics` / `batch_characteristic_values`
- 不建 `batch_type_attribute` 特征集档案层
- 不建批次库存 / 批次成本 / 多父 genealogy（P5）
- 不建 `batch_selection_policy`（P5）
- 不回填 `receipt_lines.lot_no` / `shipment_lines.lot_no`（沿用 Q5 现状）

## 2. 数据模型

### 2.1 `batches` → `meta/schemas/batches.yaml`（对象 id `batch`）

| 字段 | 类型 | 可空 | 默认 | 约束 |
|---|---|---|---|---|
| `id` | integer | 否 | — | 主键 |
| `batch_no` | string(60) | 否 | — | 非空；唯一键组成 |
| `item_id` | integer | 否 | — | → `items`，restrict |
| `org_id` | integer | 否 | — | → `orgs`（工厂/库存组织），restrict |
| `qty` | number | 否 | — | `> 0` |
| `qty_uom_id` | integer | 否 | — | → `uoms`；须与物料 `base_uom` 同 `uom_group` |
| `parent_batch_id` | integer | 是 | — | 自引用 → `batches`；禁自指/成环（深度 ≤ 10） |
| `status` | string(20) | 否 | `planned` | `planned` / `in_process` / `closed` |
| `quality_status` | string(20) | 否 | `unrestricted` | `unrestricted` / `inspection` / `blocked` |
| `source` | string(20) | 否 | `manual` | `production` / `purchase` / `manual` / `adjustment` |
| `produced_at` | datetime | 是 | — | — |
| `expiry_date` | date | 是 | — | `>= date(produced_at)`（`produced_at` 空则不校验） |
| `potency_pct` | number (REAL) | 是 | — | `0 <= x <= 100`；**物理列**，不进 EAV |
| `description` | string(255) | 是 | — | — |
| `created_at` / `updated_at` | datetime | 是 | — | 审计 |

索引：
- `uq_batch_item_org_no`：唯一 `(item_id, org_id, batch_no)`
- `idx_batch_item`、`idx_batch_org`、`idx_batch_status`、`idx_batch_quality_status`、`idx_batch_parent`、`idx_batch_produced_at`

关系：`to_item` / `to_org` / `to_qty_uom`（N:1，真外键）；`to_parent_batch`（N:1 自引用，`on_delete=restrict`）。
删除策略：`mode: restrict`；`batch_attribute_values.batch_id` 与自引用子批次构成 `restrict_on`。

枚举以 YAML `enum_values` 内联声明 + 迁移种子双写（两处取值必须一致）。

### 2.2 `batch_attribute_values` → `meta/schemas/batch_attribute_values.yaml`（对象 id `batch_attribute_value`）

严格照 `meta/schemas/_attribute_value_template.yaml`：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | integer | 否 | — | 主键 |
| `tenant_id` | integer | 否 | 0 | 0 = 平台层 |
| `batch_id` | integer | 否 | — | → `batches`（真外键） |
| `attribute_id` | integer | 否 | — | → `attribute_definitions`（真外键） |
| `seq` | integer | 否 | 1 | 单值属性恒 1 |
| `description` | text | 是 | — | 值备注 |
| `value_text` / `value_number` / `value_boolean` / `value_date` / `value_datetime` | text/float/boolean/date/datetime | 是 | — | 按 `data_type` 互斥填充 |

索引：
- `uidx_batch_attr_value`：唯一 `(tenant_id, batch_id, attribute_id, seq)`
- `idx_batch_attr_value_attr`：`(attribute_id)`（影响预览/引用计数）
- `idx_batch_attr_value_batch`：`(tenant_id, batch_id)`（按批次读全量值）

**命名强约束**：表名必须以 `_attribute_values` 结尾且含 `attribute_id` —— `AttributeImpactService` 靠此自动发现引用表；改名会绕过“被引用定义禁止删除”保护。

`ui_view_config.skip_auto_menu: true`，但**必须补全 list / form / detail 三态**（对象仍可能被抽屉/分区渲染，缺配置会出现裸 ID 列与零字段抽屉）。

## 3. 服务层

### 3.1 `meta/services/batch_service.py`

```python
class BatchError(Exception):           # field_name / rule
class BatchService:
    def __init__(self, data_source)
    def validate_batch(self, payload, existing=None) -> dict
    def validate_required_attributes(self, tenant_id, batch_id, item_group_code) -> None
```

`validate_batch` 规则（规则码供测试断言）：

| 码 | 规则 |
|---|---|
| `BATCH_NO_REQUIRED` | `batch_no` 去空后不能为空，长度 ≤ 60 |
| `BATCH_ITEM_REQUIRED` | `item_id` 必填 |
| `BATCH_ORG_REQUIRED` | `org_id` 必填 |
| `BATCH_QTY_INVALID` | `qty > 0` |
| `BATCH_UOM_REQUIRED` | `qty_uom_id` 必填 |
| `BATCH_UOM_GROUP` | 单位与 `items.base_uom` 必须同 `uom_group`（跨组拒绝） |
| `BATCH_STATUS_INVALID` | `status` 不在三值内 |
| `BATCH_QUALITY_STATUS_INVALID` | `quality_status` 不在三值内 |
| `BATCH_SOURCE_INVALID` | `source` 不在四值内 |
| `BATCH_BLOCKED_CANNOT_CLOSE` | `quality_status='blocked'` 时目标 `status='closed'` 拒绝 |
| `BATCH_EXPIRY_INVALID` | `expiry_date < date(produced_at)` |
| `BATCH_POTENCY_INVALID` | `potency_pct` 不在 `[0, 100]` |
| `BATCH_PARENT_SELF` | `parent_batch_id == id` |
| `BATCH_PARENT_MISSING` | 父批次不存在 |
| `BATCH_PARENT_CYCLE` | 沿父链成环或深度 > 10 |
| `BATCH_REQUIRED_ATTRIBUTE_MISSING` | 更新时缺必填批次特性值 |

关键实现口径：
- 更新场景先 `merged = old ∪ payload` 再校验（部分字段更新不能误判必填）。
- `qty_uom_id` 校验通过 `items.base_uom → uoms.uom_group_id` 比对，查询失败/缺数据时**跳过**（fail-open），不阻断主数据维护。
- 父链检查从**目标父批次**向上走，命中当前 `id` 即成环；步数计数 > 10 抛 `BATCH_PARENT_CYCLE`。
- 必填特性：`AttributeScopeService(self.ds).required_attribute_ids(tenant_id, 'batch', item_group_code)`；`item_group_code` 取 `items.item_group_id → item_groups.code`。
  - **仅 `existing` 有 `id` 时校验**（create 时尚无 `batch_id`，不可能有值行）；缺失定义直接拒绝，不自动补空行。
- 本服务只读校验，不写业务字段；写路径仍走通用 BO API。

### 3.2 `meta/services/batch_attribute_value_service.py`

```python
class BatchAttributeValueService(AttributeValueService):
    VALUE_TABLE = 'batch_attribute_values'
    OWNER_FIELD = 'batch_id'
    def __init__(self, data_source): ...
```

不覆写 `validate_write`：继承的租户边界、互斥单列、类型对应列、`seq` 规则、`status='active'` 拒绝停用定义全部直接生效。批次是租户对象，**不做** `ItemAttributeValueService` 那样的 platform-only 限制。

### 3.3 `meta/core/interceptors/batch_guard_interceptor.py`（新增，优先级 56）

- `OBJECT = 'batch'`，仅 `crud_create` / `crud_update`。
- `before_action` 取 `params` 与 `old_data`，调用 `BatchService.validate_batch`，`BatchError → ValidationFailedError`（沿用 `ProcessInstructionGuardInterceptor` 的 details 结构）。
- **注册两条启动路径，缺一静默失效**：
  - `meta/server.py`（`ProcessInstructionGuardInterceptor` 之后）
  - `meta/core/app_builder.py`（`AttributeGuardInterceptor` 附近）

### 3.4 扩展 `meta/core/interceptors/attribute_guard_interceptor.py`

- `GUARDED_OBJECTS` 追加 `'batch_attribute_value'`。
- `before_action` 分支：`elif object_id == 'batch_attribute_value': BatchAttributeValueService(...).validate_write(data)`。
- 不加入 `_DELETE_GUARDED`（值行可删）。

### 3.5 扩展 `meta/schemas/attribute_scope.yaml` 注释

在文件头设计边界处补一句：`scope_type='item_group'` 原语义为「该分类下的物料」；批次侧解析 `resolve(tenant, 'batch', 分类编码)` 时语义扩为「该分类下物料的批次」。**仅注释，不改字段与解析逻辑。**

## 4. 迁移 `meta/migrations/v196__batch_foundation.py`

照 `v191/v192` 骨架（`migrate(db_path, skip_backup=False)` 签名、幂等 `[SKIP]`、`verify`、`rollback` + `downgrade = rollback`、`__main__`）：

1. `TABLES`：`batches`、`batch_attribute_values`（显式 `CREATE TABLE IF NOT EXISTS` + FK + CHECK，防仅 sync_schema 漏建）。
2. `INDEXES`：上表 7 + 3 条索引，逐条 `CREATE ... IF NOT EXISTS`。
3. `ENUM_SEEDS`：`batch_status` / `batch_quality_status` / `batch_source` 三组。
4. `PERMISSIONS`：`batch` 与 `batch_attribute_value` 各 4 条双段式 `{bo}:{bo}_{action}`；授予 `admin` / `default`。
5. 菜单：`batch-management`，`menu_path='/batches'`，`page_type='object_list'`，`primary_object_type='batch'`，`parent_menu='master-data'`，`sort_order=104`（v188 生产版本占 103），`required_permissions` 为 batch 4 条；同时写 `menu_permissions`。
6. 回滚：删菜单 + 授权/权限 + 索引 + 表；枚举保留（可能被引用）。

## 5. 测试

### `meta/tests/test_batches.py`
- YAML 声明：表名、字段集合、唯一索引、三个枚举值、`skip_auto_menu` 与三态 UI 配置。
- v196 迁移：临时库建依赖表 → `migrate` → `verify`；重复执行幂等；`rollback` 删表。
- 唯一约束真实生效：同 `(item, org, batch_no)` 二次插入 `IntegrityError`；换 org 可复用。
- `BatchService`：qty ≤ 0、跨 uom_group、状态/质量状态/来源越界、blocked 不能 closed、`expiry < produced`、potency 越界、父批次自指、父不存在、成环/深度超限、缺必填特性（含 `scope_ref='batch'` 分类级范围）。

### `meta/tests/test_batch_attribute_values.py`
- YAML 声明与模板列对齐（五值列 + `tenant_id/batch_id/attribute_id/seq`）。
- `BatchAttributeValueService`：类型列不符拒绝、同行两列非空拒绝、零列拒绝、停用定义拒绝、租户私有跨租户拒绝、单值 `seq>1` 拒绝、多值允许。
- `AttributeGuardInterceptor`：`should_execute` 对 `batch_attribute_value` 的 create/update 为真、delete 为假；违规写入抛 `ValidationFailedError` 且 `rule` 正确。

## 6. 验证步骤

```powershell
python d:\filework\test.py --single meta/tests/test_batches.py
python d:\filework\test.py --single meta/tests/test_batch_attribute_values.py
python d:\filework\test.py --failed        # 若有失败，按状态机串行复跑
```

迁移落地（dev 库）由 test.py 测试快照承接；确需手工执行时用：
`python meta\core\migration_runner.py`（禁止 pytest / 直连 DB 改数据）。

## 7. 风险与取舍

| 风险 | 处理 |
|---|---|
| 必填特性在 create 时无法校验（无 `batch_id`） | 明确只在 update 校验；create 后首次编辑补值。不引入 after_action 回滚风险 |
| 父链查询失败导致 fail-open | 与既有属性服务一致，宁可放行不阻断主数据维护；测试注入失败路径 |
| `attribute_scopes` 分类级语义被误解 | schema 注释 + 测试用例 `scope_ref='batch'` + item_group 范围 |
| 菜单与 init 脚本 UPSERT 不一致 | 菜单由 v196 声明并置 `skip_auto_menu: true`，不改 init 脚本 |

## 8. 批准项

- 本规格批准后再写代码；**不 commit**（未获用户授权）。
- 两项待确认均按默认执行：
  1. `attribute_scopes.item_group` 语义扩展写进注释；
  2. 本期不建 `batch_type_attribute`。
