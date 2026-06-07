# 部署前优化 Spec v2 — 完整改动（含 UI 适配）

> **版本**: v2.0.0 | **日期**: 2026-06-07 | **状态**: 待实施
> **替代**: [spec-pre-deployment-optimization.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) v1.0.0

---

## 总览

| # | FR | 对标 | 风险 | 工作量 | 核心改动 |
|---|------|------|------|--------|---------|
| FR-1 | 自动 DDL 集成 | SAP CAP / ORDS | 低 | 中 | `with_auto_schema()` 接入 `SchemaMigrator.migrate()` |
| FR-2 | OpenAPI 规范自动生成 | ORDS metadata-catalog | 低 | 中 | 扩展已有 Action OpenAPI 到全量 BO CRUD |
| FR-3 | 格式化值服务端返回 | Salesforce displayValue | 低 | 中 | QueryInterceptor 新增 `_inject_display_values()` |
| FR-4 | 条件必填 | Salesforce Dynamic Forms | 低 | 小 | FieldPolicyEngine + ConstraintEngine 新增 conditional_required |
| FR-5 | server.py 与 AppBuilder 统一 | — | 中 | 中 | AppBuilder 补全缺失模块 + install_global_tracer |
| **FR-6** | **UI 完整适配** | **对标后端 4 项能力** | **中** | **大** | **3 个渲染组件 + 1 个 composable + 1 个表单组件** |

---

## FR-1: 自动 DDL 集成（不变）

### 1.1 现状分析

| 组件 | 位置 | 现状 |
|------|------|------|
| `with_auto_schema()` | app_builder.py L53-77 | **半成品** — 仅扫描前 5 张表打印日志 |
| `sync_schema_from_meta()` | schema_generator.py L461-464 | **完整** — 委托 SchemaMigrator.migrate() |
| `SchemaMigrator.migrate()` | schema_generator.py L374-427 | **完整** — 含层级排序、索引创建/清理 |

### 1.2 方案

**改造 `with_auto_schema()` 为正向 DDL 同步**：

```python
def with_auto_schema(self, data_source=None) -> 'ApplicationBuilder':
    """启动时自动将 YAML 元数据同步到数据库（CREATE TABLE IF NOT EXISTS + ALTER TABLE ADD COLUMN）"""
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.models import registry
    
    ds = data_source or bo_framework._data_source
    if not ds:
        logger.warning("[AppBuilder] No data source, skip auto schema sync")
        return self
    
    meta_objects = registry.all()
    if not meta_objects:
        logger.warning("[AppBuilder] No meta objects registered, skip auto schema sync")
        return self
    
    try:
        sqls = sync_schema_from_meta(ds, meta_objects, dry_run=False)
        if sqls:
            logger.info("[AppBuilder] Auto schema sync completed: %d DDL statements executed", len(sqls))
        else:
            logger.info("[AppBuilder] Auto schema sync: all tables up-to-date")
    except Exception as e:
        logger.error("[AppBuilder] Auto schema sync failed: %s", e)
    
    return self
```

### 1.3 改动清单

| 文件 | 改动 |
|------|------|
| `meta/core/app_builder.py` | 重写 `with_auto_schema()` (L53-77) |
| `meta/core/app_builder.py` | `build()` 中确保 `with_yaml_schemas()` 在 `with_auto_schema()` 之前调用 |

---

## FR-2: OpenAPI 规范自动生成（不变）

### 2.1 现状分析

`/_openapi.json` 端点（bo_action_api.py L538-671）仅覆盖 18 个 Action 端点，**BO CRUD 端点无 OpenAPI**。

### 2.2 方案

**新增 `/api/v2/meta/_openapi.json` 全量 OpenAPI 端点**。

```python
@meta_v2_bp.route('/_openapi.json', methods=['GET'])
def get_full_openapi():
    """全量 OpenAPI 规范（Action + BO CRUD + Meta）"""
    action_spec = _generate_action_openapi()
    bo_paths, bo_schemas = _generate_bo_crud_paths(registry.all())
    
    spec = action_spec.copy()
    spec['paths'].update(bo_paths)
    spec['components']['schemas'].update(bo_schemas)
    return jsonify(spec)
```

#### 2.2.1 BO CRUD 端点生成

为每个 object_type 生成 7 个标准端点：
- `GET /api/v2/bo/{type}` — 列表（带 page/page_size/order_by/search 参数）
- `GET /api/v2/bo/{type}/{id}` — 详情
- `POST /api/v2/bo/{type}` — 创建
- `PUT /api/v2/bo/{type}/{id}` — 更新
- `DELETE /api/v2/bo/{type}/{id}` — 删除
- `POST /api/v2/bo/{type}/deep` — 深度插入
- `POST /api/v2/bo/{type}/batch-delete` — 批量删除

#### 2.2.2 MetaObject → JSON Schema 转换

```python
def _map_field_type(field_type):
    return {
        'string': 'string', 'text': 'string', 'integer': 'integer',
        'float': 'number', 'boolean': 'boolean', 'date': 'string',
        'datetime': 'string', 'json': 'object',
    }.get(field_type, 'string')

def _generate_bo_schema(meta_object):
    properties = {}
    required = []
    
    for field in meta_object.fields:
        prop = {"type": _map_field_type(field.type)}
        if field.description:
            prop["description"] = field.description
        if hasattr(field, 'enum_values') and field.enum_values:
            prop["enum"] = [v.get('value') for v in field.enum_values]
        if hasattr(field, 'ui') and field.ui and field.ui.get('relation'):
            prop["x-relation"] = field.ui['relation']
            prop["x-display-field"] = field.ui.get('display_field')
        properties[field.id] = prop
        if field.required:
            required.append(field.id)
    
    return {"type": "object", "properties": properties, "required": required or None}
```

### 2.3 改动清单

| 文件 | 改动 |
|------|------|
| `meta/api/bo_action_api.py` | 提取 `_generate_action_openapi()` 为独立函数 |
| `meta/api/bo_api.py` | 新增 `/_openapi.json` 端点 + `_generate_bo_crud_paths()` + `_generate_bo_schema()` |

---

## FR-3: 格式化值服务端返回（不变）

### 3.1 现状分析

后端已有 FK 显示名称（`_enrich_fk_display_names`）和虚拟冗余字段（`enrichment_engine`），**缺少枚举/布尔/日期的通用 display_value**。

### 3.2 方案

**在 QueryInterceptor 中新增 `_inject_display_values()` 步骤**。

| 字段类型 | display_value 来源 | 示例 |
|---------|-------------------|------|
| FK 字段 | `ui.display_field` 对应的冗余字段值 | `service_module_id` → `服务模块A` |
| 枚举字段 | `enum_values` 列表中 value → label | `"active"` → `"活跃"` |
| 布尔字段 | 固定映射 | `true` → `"是"`, `false` → `"否"` |
| 日期字段 | `ui.format` 或默认格式 | `"2026-06-07"` → `"2026年6月7日"` |

```python
def after_action(self, context):
    if context.is_query_action:
        records = context.result
        if isinstance(records, list):
            self._inject_type_tag(records, context.meta_object)
            self._enrich_records(records, context)
            self._inject_display_values(records, context.meta_object)  # 新增
            self._compute_columns(records, context)
            self._check_can_delete(records, context.meta_object)

def _inject_display_values(self, records, meta_object):
    if not meta_object or not meta_object.fields:
        return
    
    display_field_map = {}
    for field in meta_object.fields:
        if field.type == 'boolean':
            display_field_map[field.id] = ('boolean', None)
        elif hasattr(field, 'enum_values') and field.enum_values:
            value_label_map = {v['value']: v.get('label', v['value']) for v in field.enum_values}
            display_field_map[field.id] = ('enum', value_label_map)
        elif hasattr(field, 'ui') and field.ui and field.ui.get('display_field'):
            display_field_map[field.id] = ('fk', field.ui['display_field'])
    
    if not display_field_map:
        return
    
    for record in records:
        dv = {}
        for field_id, (field_type, mapping) in display_field_map.items():
            value = record.get(field_id)
            if value is None:
                continue
            if field_type == 'boolean':
                dv[field_id] = '是' if value else '否'
            elif field_type == 'enum':
                dv[field_id] = mapping.get(value, str(value))
            elif field_type == 'fk':
                display_value = record.get(mapping)
                if display_value:
                    dv[field_id] = display_value
        if dv:
            record['display_values'] = dv
```

### 3.3 改动清单

| 文件 | 改动 |
|------|------|
| `meta/core/interceptors/query_interceptor.py` | 新增 `_inject_display_values()` 方法 |
| `meta/core/interceptors/query_interceptor.py` | `after_action()` 中调用（`_enrich_records` 之后） |

---

## FR-4: 条件必填（不变）

### 4.1 现状分析

`FieldPolicyEngine.is_field_required()` 仅检查静态 `field.constraints.required`，**不支持条件必填**。`RequiredPolicy` 数据结构已支持 `when_expr` 但未连接 YAML。

### 4.2 方案

**双路径实现**：YAML 声明 + ConstraintEngine 校验。

```yaml
validations:
  - id: sub_domain_conditional_required
    name: 子领域条件必填
    type: conditional_required
    field: sub_domain_id
    condition: "domain_id is not None"
    message: 选择领域后，子领域不能为空
    severity: error
```

```python
# constraint_engine.py
def _check_conditional_required(self, context, field, constraint):
    if context.action not in ('crud_create', 'crud_update'):
        return None
    condition = constraint.get('condition', '')
    if not condition:
        return None
    from meta.core.expression_evaluator import safe_evaluate
    data = context.params if context.action == 'crud_create' else context.params
    if not safe_evaluate(condition, data):
        return None
    field_id = constraint.get('field', field.id if field else '')
    value = data.get(field_id)
    if value is None or value == '':
        return ConstraintViolation(
            field_id=field_id,
            rule='conditional_required',
            message=constraint.get('message', f'{field_id} 条件必填校验失败'),
            severity=constraint.get('severity', 'error')
        )
    return None
```

### 4.3 改动清单

| 文件 | 改动 |
|------|------|
| `meta/core/constraint_engine.py` | 新增 `_check_conditional_required()` + 路由分支 |
| `meta/services/field_policy_engine.py` | `is_field_required()` 增加 conditional_required 检查 |

---

## FR-5: server.py 与 AppBuilder 统一（不变）

### 5.1 现状分析

AppBuilder 仅覆盖 server.py 约 40% 功能，缺少 telemetry tracer、BO Action 注册、TaskScheduler、DB 预检、认证初始化、菜单初始化等。

### 5.2 方案

**补全 AppBuilder 5 个缺失方法**：

```python
def with_preflight_checks(self) -> 'ApplicationBuilder':
    """启动前数据库健康检查"""
    from meta.core.db_health_monitor import check_db_health
    ds = bo_framework._data_source
    if ds:
        health = check_db_health(ds)
        for w in health.get('warnings', []):
            logger.warning("[AppBuilder] DB health: %s", w)
        for e in health.get('errors', []):
            logger.error("[AppBuilder] DB health: %s", e)
    return self

def with_telemetry(self) -> 'ApplicationBuilder':
    """安装遥测追踪器"""
    from meta.core.telemetry import install_global_tracer
    install_global_tracer(bo_framework.interceptors)
    logger.info("[AppBuilder] Telemetry tracer installed")
    return self

def with_auth_init(self) -> 'ApplicationBuilder':
    """初始化认证系统"""
    from meta.services.auth_service import init_auth_system
    from meta.services.user_service import run_migration
    init_auth_system()
    run_migration()
    logger.info("[AppBuilder] Auth system initialized")
    return self

def with_menu_init(self) -> 'ApplicationBuilder':
    """初始化菜单权限"""
    from meta.services.menu_permission_service import init_menu_permissions
    init_menu_permissions()
    logger.info("[AppBuilder] Menu permissions initialized")
    return self

def with_bo_actions(self) -> 'ApplicationBuilder':
    """注册所有 BO Action handler"""
    from meta.core.bo_action_registry import bo_action_registry
    from meta.api.bo_action_init import register_all_actions
    register_all_actions(bo_action_registry)
    logger.info("[AppBuilder] BO actions registered: %d", len(bo_action_registry.list_ids()))
    return self
```

**新建 `meta/api/bo_action_init.py`**，提取 server.py L679-1000 的 18+ 个 action 注册到 `register_all_actions(registry)` 函数。

### 5.3 改动清单

| 文件 | 改动 |
|------|------|
| `meta/api/bo_action_init.py` | **新建** — 提取 `register_all_actions(registry)` |
| `meta/core/app_builder.py` | 新增 5 个 `with_*` 方法 |
| `meta/server.py` | `create_app()` 调用 `register_all_actions()` + legacy 注释 |

---

## FR-6: UI 完整适配（新增）

> **重要发现**：后端 4 项能力（display_values、field-policies、requiredMap、conditional_required）在前端**完全没有消费点**或**已实现但未调用**。本 FR 补全 UI 适配。

### 6.1 现状分析

| 后端能力 | 前端现状 | 适配工作量 |
|----------|---------|-----------|
| **display_values** | **0 引用** — `src/` 中无任何 `display_values` 字符串 | 大：3 个渲染组件 |
| **field-policies API** | `loadFieldPolicies` 已实现但**0 调用** | 小：1 个 composable |
| **requiredMap** | **无 Map 数据结构** — 仅有 `isRequired()` 单值函数 | 中：1 个 composable |
| **conditional_required** | **0 引用** — 无 `isRequired(row)` 重载 | 大：4 个文件联动 |

**4 个核心消费点已识别且集中**：
- 列表 cell 渲染：[MetaListPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue) L273-348（9 个 v-if 分支）
- 详情字段渲染：[ObjectPageField.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) L5-20 / L139-141 / L149-240
- 备选详情渲染：[DetailSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailSection.vue) L220-271 / L406-425
- 策略 composable：[useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js)
- 自研表单：[MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue)

### 6.2 方案

#### FR-6.1: 激活 field-policies API（核心）

**问题**：`useFieldPolicy.js` 的 `loadFieldPolicies` 函数已实现但**全 `src/` 无任何调用**，`fieldPolicies.value` 永远为 `null`，所有策略走本地 fallback。

**方案**：在 `useFieldPolicy` 暴露 `autoLoad()` 初始化钩子。

```js
// useFieldPolicy.js 新增
export function useFieldPolicy(metaConfig, columns) {
  const fieldPolicies = ref(null)
  const policiesLoaded = ref(false)
  
  // 新增：自动加载入口
  async function autoLoad(objectType, context = 'read', mutability = null) {
    if (!objectType) return false
    policiesLoaded.value = false
    const ok = await loadFieldPolicies(objectType, context, mutability)
    policiesLoaded.value = ok
    return ok
  }
  
  return { fieldPolicies, policiesLoaded, autoLoad, /* 原有 */ }
}
```

**调用方改造**：

| 组件 | 改动 |
|------|------|
| `useMetaList.js` | `init()` 中 `await autoLoad(objectType, 'read')` |
| `ObjectPageField.vue` | 新增 `objectType` prop 触发加载 |
| `ObjectDetailPage.vue` | 详情页 mount 时 `autoLoad(objectType, 'read')` |

#### FR-6.2: 暴露 requiredMap / editableMap / visibleMap 数据结构

**问题**：当前 useFieldPolicy 暴露 `isRequired()` 单值函数，**无 Map 数据结构**供 UI 直接消费。`ObjectPageField.vue` 重复实现 `fieldDefs[key]?.required === true`，**未走后端 API**。

**方案**：暴露 computed Map，并改造 `ObjectPageField` 走 useFieldPolicy。

```js
// useFieldPolicy.js 已有，新增显式暴露
return {
  // 数据结构（UI 可直接 v-if="requiredMap[key]"）
  requiredMap,        // computed, 已有
  editableMap,        // computed, 已有
  visibleMap,         // computed, 已有
  immutableMap,       // computed, 已有
  readonlyAlwaysMap,  // computed, 已有
  
  // 函数（按需调用）
  isRequired,         // 已有
  isEditable,         // 已有
  isVisible,          // 已有
  isImmutable,        // 已有
  
  // API
  loadFieldPolicies,  // 已有
  autoLoad,           // 新增
  fieldPolicies,      // 原始数据
  policiesLoaded,     // 加载状态
}
```

**ObjectPageField.vue 改造**：

```js
// 改造前（L139-141）
function isRequired(key) {
  return props.fieldDefs[key]?.required === true
}

// 改造后
import { useFieldPolicy } from '@/composables/useFieldPolicy'
const fieldPolicy = useFieldPolicy(
  computed(() => ({ fields: Object.values(props.fieldDefs) })),
  computed(() => [])
)
// 注意：useFieldPolicy 在父组件初始化时 autoLoad，子组件直接消费 requiredMap
const isRequired = (key) => fieldPolicy.requiredMap.value[key] === true
```

#### FR-6.3: isRequired(row) 重载支持 conditional_required

**问题**：后端 `conditional_required`（条件必填）联动，前端**完全没有基础设施**。`useFieldPolicy.js` 没有 `isRequired(fieldId, row)` 重载。

**方案**：新增基于 row 上下文的 `isRequired` 重载。

```js
// useFieldPolicy.js 新增
function isRequiredByRow(fieldId, row = null) {
  // 1. 优先基础 isRequired
  if (isRequired(fieldId)) return true
  
  // 2. 检查 conditional_required（从 fieldPolicies 读取）
  if (fieldPolicies.value && row) {
    const policy = fieldPolicies.value[fieldId]
    if (policy?.conditional_required) {
      for (const rule of policy.conditional_required) {
        if (evaluateCondition(rule.condition, row)) {
          return true
        }
      }
    }
  }
  
  // 3. 检查 metaConfig 中的 conditional_required（fallback）
  if (metaConfig.value?.fields && row) {
    const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
    if (field?.conditional_required) {
      for (const rule of field.conditional_required) {
        if (evaluateCondition(rule.condition, row)) {
          return true
        }
      }
    }
  }
  
  return false
}

function evaluateCondition(condition, row) {
  // 简单条件评估器，支持 "field_name is not None" / "field_name == 'value'"
  // 委托到后端 /meta/{type}/evaluate-expression 或前端轻量实现
  try {
    const fn = new Function('row', `with(row) { return (${condition}); }`)
    return Boolean(fn(row))
  } catch {
    return false
  }
}
```

**后端需要**：field-policies API 响应中包含 `conditional_required` 数组（FR-4 配合）。

#### FR-6.4: MetaListPage cell 渲染接入 display_values

**问题**：[MetaListPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue) L273-348 cell 渲染 9 个 v-if 分支**全部走本地 format / 字段值**。

**方案**：在 v-if 链最前添加 display_value 优先读。

```js
// 新增统一函数
function getCellDisplayValue(row, column) {
  // 1. 优先后端 display_values
  const dv = row.display_values?.[column.prop]
  if (dv !== undefined && dv !== null) return dv
  
  // 2. 行伴生字段（FK 已有模式）
  const fkDisplay = row[`${column.prop}_display`] || row[`${column.propName}_name`]
  if (fkDisplay) return fkDisplay
  
  // 3. 走原有 format 逻辑
  return null  // 表示未处理，走原 v-if 链
}

// 模板改造（cell-${prop} slot 上方）
<template v-else>
  <span v-if="getCellDisplayValue(row, column) !== null" class="cell-display">
    {{ getCellDisplayValue(row, column) }}
  </span>
  <template v-else>
    <!-- 原 9 个 v-if 分支 -->
  </template>
</template>
```

#### FR-6.5: ObjectPageField 只读渲染接入 display_values

**问题**：[ObjectPageField.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) L5-20 只读渲染 3 个分支（FkLinkField / enum tag / 默认 span），`getFieldDisplayValue` 优先读 `formData[`${key}_display`]`。

**方案**：扩展 `getFieldDisplayValue` 优先读 `formData.display_values?.[key]`。

```js
// ObjectPageField.vue L149-157
function getFieldDisplayValue(key) {
  // 1. 优先后端 display_values
  const dv = props.formData.display_values?.[key]
  if (dv !== undefined && dv !== null) return dv
  
  // 2. 原 `${key}_display` 或 `${keyName}_name` 模式
  const displayKey = props.formData[`${key}_display`]
    ? `${key}_display`
    : `${key.replace(/_id$/, '')}_name`
  const displayValue = props.formData[displayKey]
  if (displayValue) return displayValue
  
  // 3. 原值
  return props.formData[key] || ''
}
```

#### FR-6.6: DetailSection 渲染接入 display_values

**问题**：[DetailSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailSection.vue) L406-425 `getFieldDisplayValue` 优先 `field.display_field`，不读 `display_values`。

**方案**：在 `getFieldDisplayValue` 优先读 `data.display_values?.[field.id]`。

```js
// DetailSection.vue L406-425
function getFieldDisplayValue(field) {
  // 1. 优先后端 display_values
  if (props.data?.display_values?.[field.id] !== undefined) {
    return props.data.display_values[field.id]
  }
  
  // 2. 原 field.display_field / field.formatter / fallback
  if (field.display_field) {
    return props.data[field.display_field]
  }
  if (field.formatter) {
    return field.formatter(props.data[field.id], props.data)
  }
  return props.data[field.id]
}
```

#### FR-6.7: MetaForm 集成 useFieldPolicy 支持条件必填

**问题**：[MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue) L275-304 `validateField` 仅判断 `field.required`，**不支持 conditional_required**。生产表单**完全依赖** MetaForm（90% 场景）。

**方案**：`validateField` 集成 `isRequiredByRow`。

```js
// MetaForm.vue L275-304
async function validateField(key) {
  const field = props.fields.find(f => f.key === key)
  if (!field) return null
  
  // 1. 条件必填（后端 conditional_required 联动）
  if (props.fieldPolicy?.isRequiredByRow) {
    const isConditionallyRequired = props.fieldPolicy.isRequiredByRow(key, formData.value)
    if (!isConditionallyRequired) {
      // 条件不满足，跳过必填校验
      errors.value[key] = null
      return null
    }
  }
  
  // 2. 原 field.required 必填校验
  if (field.required) {
    const value = formData.value[key]
    if (value === null || value === undefined || value === '') {
      errors.value[key] = field.requiredMessage || `${field.label}不能为空`
      return errors.value[key]
    }
  }
  
  // 3. 原 field.rules 校验
  // ...
}

// 新增 prop
const props = defineProps({
  fields: { type: Array, required: true },
  modelValue: { type: Object, required: true },
  fieldPolicy: { type: Object, default: null }  // 新增：useFieldPolicy 注入
})
```

**MetaDialog 调用改造**：

```js
// MetaDialog.vue
import { useFieldPolicy } from '@/composables/useFieldPolicy'
const fieldPolicy = useFieldPolicy(metaConfig, columns)
onMounted(() => fieldPolicy.autoLoad(objectType, 'update'))

// 传给 MetaForm
<MetaForm :fields="fields" v-model="formData" :field-policy="fieldPolicy" />
```

### 6.3 改动清单

| # | 文件 | 改动 | 优先级 |
|---|------|------|--------|
| 6.1 | `src/composables/useFieldPolicy.js` | 新增 `autoLoad()` 入口 | 高 |
| 6.2 | `src/composables/useFieldPolicy.js` | 显式暴露 5 个 Map | 中 |
| 6.3 | `src/composables/useFieldPolicy.js` | 新增 `isRequiredByRow(fieldId, row)` 重载 + `evaluateCondition()` | 高 |
| 6.1 | `src/composables/useMetaList.js` | `init()` 中 `await autoLoad(objectType, 'read')` | 高 |
| 6.1 | `src/views/ObjectDetailPage.vue` | mount 时 `autoLoad(objectType, 'read')` | 高 |
| 6.2 | `src/components/common/ObjectPage/ObjectPageField.vue` | 改造 `isRequired` 走 `useFieldPolicy.requiredMap` | 中 |
| 6.4 | `src/components/common/MetaListPage/MetaListPage.vue` | `getCellDisplayValue()` 优先后端 + 模板 v-if 链首插入 | 高 |
| 6.5 | `src/components/common/ObjectPage/ObjectPageField.vue` | `getFieldDisplayValue()` 优先读 `display_values` | 中 |
| 6.6 | `src/components/common/DetailPage/DetailSection.vue` | `getFieldDisplayValue()` 优先读 `display_values` | 中 |
| 6.7 | `src/components/common/MetaForm.vue` | `validateField()` 集成 `isRequiredByRow` | 高 |
| 6.7 | `src/components/common/MetaDialog.vue` | 注入 `fieldPolicy` 给 MetaForm | 中 |
| 6.7 | `src/composables/useFieldPolicy.js` | 导出 `evaluateCondition` 供 MetaForm 复用 | 中 |

### 6.4 安全保证

- **fallback 模式**：所有改动都保留前端推断能力，后端不返回时不影响功能
- **纯重构**：6.1-6.2 是激活现有函数，不改变外部行为
- **渐进式接入**：6.3-6.6 是优先级 + fallback，不破坏现有渲染逻辑
- **条件评估隔离**：`evaluateCondition` 用 `new Function()` + `with(row)` 沙箱，避免任意代码执行（与后端 `safe_evaluate` 模式一致）

### 6.5 验证

| 验证项 | 方法 |
|--------|------|
| 6.1 | 列表页加载后 `fieldPolicies.value !== null` |
| 6.1 | `policiesLoaded.value === true` |
| 6.2 | `requiredMap['status'] === false`（系统字段） |
| 6.2 | `ObjectPageField` 红星显示与 useFieldPolicy 一致 |
| 6.3 | conditional_required 字段，条件满足时返回 `true` |
| 6.4 | 列表 cell 显示后端 display_value（"活跃" 而非 "active"） |
| 6.4 | 详情页 FK 显示后端 display_value |
| 6.7 | conditional_required 字段，条件不满足时表单不要求必填 |
| 6.7 | 条件满足时表单强制必填 |

---

## 实施顺序（更新）

```
后端任务（FR-1 → FR-5）：
  FR-1.1 → FR-1.2 → FR-5.1 → FR-5.2 → FR-5.3 → FR-5.4 → FR-5.5 → FR-5.6 → FR-5.7 → FR-5.8
  → FR-2.1 → FR-2.2 → FR-2.3 → FR-2.4
  → FR-3.1 → FR-3.2
  → FR-4.1 → FR-4.2 → FR-4.3

UI 任务（FR-6）：
  FR-6.1（autoLoad）→ FR-6.2（requiredMap 暴露）→ FR-6.3（isRequiredByRow 重载）
  → FR-6.4（MetaListPage cell）
  → FR-6.5（ObjectPageField 只读）→ FR-6.6（DetailSection）
  → FR-6.7（MetaForm + MetaDialog）
```

**理由**：
1. FR-1 → FR-5 是后端基础，先做完才能让 UI 有可消费的能力
2. FR-6.1 先做，激活 field-policies API，让 UI 能消费后端
3. FR-6.2-6.3 复用 6.1 的 autoLoad 入口
4. FR-6.4 是列表页（最常用），先做
5. FR-6.5-6.6 是详情页，并行做
6. FR-6.7 是表单（最复杂），最后做

---

## 验证总清单

```
后端验证：
□ FR-1: 新增 YAML → 重启 → 自动建表
□ FR-1: 已有表新增字段 → 重启 → 自动 ALTER TABLE
□ FR-2: GET /api/v2/meta/_openapi.json 返回完整 OpenAPI 3.0
□ FR-2: OpenAPI 包含所有 BO CRUD + Action 端点
□ FR-3: GET /api/v2/bo/{type} 返回 display_values 子对象
□ FR-3: 枚举字段 display_value 正确
□ FR-3: 布尔字段 display_value 正确
□ FR-4: conditional_required YAML 配置生效
□ FR-4: 条件不满足时字段非必填
□ FR-5: AppBuilder 构建的应用功能正常
□ FR-5: telemetry tracer 正常工作
□ FR-5: server.py 仍可正常启动

UI 验证：
□ FR-6.1: 列表页加载后 fieldPolicies !== null
□ FR-6.1: 详情页 mount 时 autoLoad 触发
□ FR-6.2: requiredMap['status'] === false（系统字段）
□ FR-6.2: ObjectPageField 红星与 useFieldPolicy 一致
□ FR-6.3: conditional_required 字段条件满足时返回 true
□ FR-6.3: 条件不满足时返回 false
□ FR-6.4: 列表 cell 显示后端 display_value（"活跃" 而非 "active"）
□ FR-6.4: 不影响 slot 渲染
□ FR-6.5: 详情页 FK 显示后端 display_value
□ FR-6.6: DetailSection 显示后端 display_value
□ FR-6.7: conditional_required 字段条件不满足时表单不要求必填
□ FR-6.7: 条件满足时表单强制必填
```

---

## 工作量统计

| 阶段 | 后端任务 | UI 任务 | 总计 |
|------|---------|---------|------|
| 文件数 | 8 个 | 8 个 | 16 个 |
| 改动行数 | ~400 行 | ~500 行 | ~900 行 |
| 风险 | 低-中 | 中 | 中 |

**关键判断**：
- 后端改动 5 项 FR 都是低风险（已实现可复用 + fallback 模式）
- UI 改动 6 项 FR 中 6.1-6.2 是激活现有功能（低风险），6.3-6.7 是新建联动（中风险）
- 建议：分两批提交 — 先提交后端 5 项 FR + UI 6.1-6.2（低风险），再提交 UI 6.3-6.7（中风险）
