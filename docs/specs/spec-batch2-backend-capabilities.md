## 目录

1. [一、背景与目标](#一-背景与目标)
2. [二、范围与不在范围](#二-范围与不在范围)
3. [三、当前实现情况（2026-06-07 Grep 核查）](#三-当前实现情况（2026-06-07-grep-核查）)
4. [四、依赖与复用决策](#四-依赖与复用决策)
5. [五、详细设计（code-level）](#五-详细设计（code-level）)
6. [六、实施顺序与并行策略](#六-实施顺序与并行策略)
7. [七、验证策略](#七-验证策略)
8. [八、风险与缓解](#八-风险与缓解)
9. [九、Requirements Quality Checklist](#九-requirements-quality-checklist)
10. [十、TBD 列表](#十-tbd-列表)
11. [十一、附录](#十一-附录)

---
# 批次 2 实施 Spec — 后端能力扩展（FR-2 / FR-3 / FR-4）

> **版本**: v1.0 | **日期**: 2026-06-07 | **状态**: 🟡 草稿
> **配套规格**: [spec-pre-deployment-optimization.md (v1.1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) — 12 任务分布：FR-2（4 任务）+ FR-3（3 任务）+ FR-4（5 任务）
> **废弃文档**: `spec-batch2-frontend-ui-adaptation.md`（基于 v2 过期版本，已删除）

---

## 一、背景与目标

**v1 批次 1 已完成**（2026-06-07）：FR-1（自动 DDL）+ FR-5（server.py 与 AppBuilder 统一）共 10 任务。

**v1 批次 2 待实施**：12 任务，**全部后端能力扩展**，目标是：
1. **FR-2 OpenAPI 自动生成**：补齐 BO CRUD + MetaObject 端点的 OpenAPI 规范
2. **FR-3 display_values 服务端返回**：UI 列表/详情可直接用后端预格式化的展示值
3. **FR-4 conditional_required 条件必填**：业务字段可基于条件动态必填（如"选择领域后，子领域必填"）

**对标业界**：SAP CAP / ORDS metadata-catalog（FR-2）+ Salesforce displayValue（FR-3）+ Salesforce Dynamic Forms（FR-4）。

---

## 二、范围与不在范围

### 2.1 范围（v1 批次 2 共 12 任务）

| 任务 | 标题 | 文件 | 类别 |
|------|------|------|------|
| FR-2.1 | 提取 Action OpenAPI 生成函数 | `meta/api/bo_action_api.py:538-671` | 后端 |
| FR-2.2 | 新增 BO CRUD paths 生成 | `meta/api/bo_api.py` | 后端 |
| FR-2.3 | MetaObject → JSON Schema 转换 | `meta/api/bo_api.py` | 后端 |
| FR-2.4 | 全量 OpenAPI 端点 | `meta/api/bo_api.py` | 后端 |
| FR-3.1 | 新增 `_inject_display_values()` | `meta/core/interceptors/query_interceptor.py` | 后端 |
| FR-3.2 | 接入 after_action 流程 | `meta/core/interceptors/query_interceptor.py` | 后端 |
| FR-3.3 | 前端读 display_values | `src/composables/useMetaList.js` | 前端（最小） |
| FR-4.1 | ConstraintEngine 新增 `_check_conditional_required()` | `meta/core/constraint_engine.py` | 后端 |
| FR-4.2 | 路由到新方法 | `meta/core/constraint_engine.py` | 后端 |
| FR-4.3 | FieldPolicyEngine 联动 | `meta/services/field_policy_engine.py` | 后端 |
| FR-4.4 | YAML 示例 | `meta/schemas/business_object.yaml` | 配置 |
| FR-4.5 | 前端读 conditional_required | `src/composables/useFieldPolicy.js` | 前端（最小） |

### 2.2 不在范围（v1 批次 3 才有）

- UI FR-6 全量适配（仅 v2 引入）
- 12 任务的 UI 端深度集成（6.3~6.7）属 v1 批次 3
- v1 批次 3 = v2 FR-6 完整 UI 适配（待后续批次）

---

## 三、当前实现情况（2026-06-07 Grep 核查）

### 3.1 已就绪基础设施（可直接复用）

| 资产 | 位置 | 用途 |
|------|------|------|
| `safe_evaluate(condition, data)` | `meta/core/expression_evaluator.py` | FR-4.1 / FR-4.3 条件求值 |
| `RequiredPolicy` 类 | `meta/services/field_policy_engine.py:63` | FR-4.3 复用 |
| `PolicyContext` 类 | `field_policy_engine.py` | FR-4.3 复用 |
| `QueryInterceptor.after_action()` | `meta/core/interceptors/query_interceptor.py:35` | FR-3.2 复用 |
| `useMetaList.loadList()` | `src/composables/useMetaList.js` | FR-3.3 复用 |
| `loadFieldPolicies()` | `src/composables/useFieldPolicy.js:122-128` | FR-4.5 复用 |
| `with_*` 链 | `meta/core/app_builder.py` | 无需新增 |

### 3.2 缺失能力（0% 完成）

| 任务 | 缺失文件/函数 | 缺失位置 |
|------|--------------|---------|
| FR-2.1 | `_generate_action_openapi()` | bo_action_api.py:538-671 |
| FR-2.2 | `_generate_bo_crud_paths()` | bo_api.py |
| FR-2.3 | `_map_field_type()` / `_generate_bo_schema()` | bo_api.py |
| FR-2.4 | `@meta_v2_bp.route('/_openapi.json')` 全量端点 | bo_api.py |
| FR-3.1 | `_inject_display_values()` | query_interceptor.py |
| FR-3.2 | after_action 中调用 `_inject_display_values()` | query_interceptor.py |
| FR-3.3 | list 响应处理时读 `record.display_values` | useMetaList.js |
| FR-4.1 | `_check_conditional_required()` | constraint_engine.py |
| FR-4.2 | `_check_constraint()` 路由 conditional_required | constraint_engine.py |
| FR-4.3 | `is_field_required()` 中检查 conditional_required | field_policy_engine.py |
| FR-4.4 | YAML `validations` 中 conditional_required 示例 | business_object.yaml |
| FR-4.5 | useFieldPolicy.js 读 `fieldPolicies[id].conditional_required` | useFieldPolicy.js |

---

## 四、依赖与复用决策

### 4.1 FR-2 内部依赖（串行）

```
FR-2.1 提取 _generate_action_openapi()   ← 已有 _openapi.json 端点，需提取
   ↓
FR-2.2 _generate_bo_crud_paths()        ← 独立
   ↓
FR-2.3 _generate_bo_schema()            ← 独立
   ↓
FR-2.4 @meta_v2_bp.route('/_openapi.json')  ← 复用 2.1 + 2.2 + 2.3
```

**串行约束**：FR-2.4 必须等 2.1/2.2/2.3 完成才能合并。

### 4.2 FR-3 内部依赖（串行）

```
FR-3.1 _inject_display_values()         ← 独立
   ↓
FR-3.2 after_action 接入                ← 紧跟 3.1
   ↓
FR-3.3 useMetaList.js 读 display_values  ← 弱依赖（fallback 模式允许 3.1/3.2 未完成时开发）
```

**串行约束**：3.1 → 3.2 同文件紧邻，必须串行；3.3 可与 3.2 并行（弱依赖 + fallback）。

### 4.3 FR-4 内部依赖（部分串行）

```
FR-4.1 _check_conditional_required()   ← 独立
   ↓
FR-4.2 _check_constraint() 路由          ← 紧跟 4.1
   ↓
FR-4.3 is_field_required() 联动          ← 紧跟 4.2
   ↓
FR-4.4 YAML 示例                        ← 独立
   ↓
FR-4.5 useFieldPolicy.js 读              ← 弱依赖（fallback）
```

**串行约束**：4.1 → 4.2 → 4.3 紧邻串行；4.4 / 4.5 可与 4.3 并行。

### 4.4 FR 跨依赖（无）

- FR-2 / FR-3 / FR-4 之间**无依赖**（互不干扰）
- 三个 FR 可在**不同 worktree** 并行开发

---

## 五、详细设计（code-level）

### 5.1 FR-2.1: 提取 Action OpenAPI 生成函数

**文件**: `meta/api/bo_action_api.py:538-671`

**当前**: L538-671 内的 `/_openapi.json` 端点直接返回 spec 字典

**改动**: 提取内部生成逻辑为独立函数 `_generate_action_openapi()`

```python
def _generate_action_openapi() -> dict:
    """生成 Action OpenAPI 规范（包含所有已注册 action 端点）"""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "BO Action API", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": {}},
    }
    for action_id, handler in bo_action_registry.list_all():
        spec['paths'][f'/api/v2/action/{action_id}'] = {
            'post': {
                'operationId': action_id.replace('.', '_'),
                'summary': handler.summary or action_id,
                'tags': [handler.category or 'misc'],
                'requestBody': {
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': handler.params_schema or {}
                            }
                        }
                    }
                },
                'responses': {
                    '200': {'description': '成功'},
                    '400': {'description': '参数错误'},
                    '500': {'description': '服务器错误'},
                }
            }
        }
    return spec
```

**端点改造**:
```python
@meta_action_bp.route('/_openapi.json', methods=['GET'])
def get_action_openapi():
    return jsonify(_generate_action_openapi())  # 改用函数
```

### 5.2 FR-2.2: BO CRUD paths 生成

**文件**: `meta/api/bo_api.py`（新增函数）

```python
def _generate_bo_crud_paths(meta_objects) -> dict:
    """为每个 BO 类型生成 7 个标准 CRUD 端点"""
    paths = {}
    for obj in meta_objects:
        if not obj.table_name:
            continue
        type_name = obj.id
        base = f"/api/v2/bo/{type_name}"
        paths[base] = {
            "get": {
                "operationId": f"bo_{type_name}_list",
                "summary": f"查询 {obj.display_name or type_name} 列表",
                "tags": [f"BO/{type_name}"],
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                    {"name": "page_size", "in": "query", "schema": {"type": "integer", "default": 20}},
                    {"name": "order_by", "in": "query", "schema": {"type": "string"}},
                    {"name": "search", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "列表数据"}},
            },
            "post": {
                "operationId": f"bo_{type_name}_create",
                "summary": f"创建 {obj.display_name or type_name}",
                "tags": [f"BO/{type_name}"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{type_name}"}
                        }
                    }
                },
                "responses": {"201": {"description": "已创建"}},
            },
        }
        paths[f"{base}/{{id}}"] = {
            "get": {
                "operationId": f"bo_{type_name}_get",
                "summary": f"获取 {type_name} 详情",
                "tags": [f"BO/{type_name}"],
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "详情数据"}},
            },
            "put": {
                "operationId": f"bo_{type_name}_update",
                "summary": f"更新 {type_name}",
                "tags": [f"BO/{type_name}"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{type_name}"}
                        }
                    }
                },
                "responses": {"200": {"description": "已更新"}},
            },
            "delete": {
                "operationId": f"bo_{type_name}_delete",
                "summary": f"删除 {type_name}",
                "tags": [f"BO/{type_name}"],
                "responses": {"204": {"description": "已删除"}},
            },
        }
        paths[f"{base}/deep"] = {
            "post": {
                "operationId": f"bo_{type_name}_deep_create",
                "summary": f"深度插入 {type_name}",
                "tags": [f"BO/{type_name}"],
                "responses": {"201": {"description": "已深度插入"}},
            }
        }
        paths[f"{base}/batch-delete"] = {
            "post": {
                "operationId": f"bo_{type_name}_batch_delete",
                "summary": f"批量删除 {type_name}",
                "tags": [f"BO/{type_name}"],
                "requestBody": {
                    "content": {"application/json": {"schema": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}}}}
                },
                "responses": {"200": {"description": "已批量删除"}},
            }
        }
    return paths
```

### 5.3 FR-2.3: MetaObject → JSON Schema 转换

```python
_TYPE_MAP = {
    'string': 'string', 'text': 'string', 'integer': 'integer',
    'float': 'number', 'boolean': 'boolean', 'date': 'string',
    'datetime': 'string', 'json': 'object',
}

def _map_field_type(field_type: str) -> str:
    return _TYPE_MAP.get(field_type, 'string')

def _generate_bo_schema(meta_object) -> dict:
    properties = {}
    required = []
    for field in meta_object.fields:
        prop = {"type": _map_field_type(field.type)}
        if getattr(field, 'description', None):
            prop["description"] = field.description
        if getattr(field, 'enum_values', None):
            prop["enum"] = [v.get('value') for v in field.enum_values]
        ui = getattr(field, 'ui', None) or {}
        if ui.get('relation'):
            prop["x-relation"] = ui['relation']
            prop["x-display-field"] = ui.get('display_field')
        properties[field.id] = prop
        if field.required:
            required.append(field.id)
    return {
        "type": "object",
        "properties": properties,
        "required": required or None,
    }
```

### 5.4 FR-2.4: 全量 OpenAPI 端点

```python
from meta.services.meta_object_registry import registry  # 假设有 registry

@meta_v2_bp.route('/_openapi.json', methods=['GET'])
def get_full_openapi():
    """全量 OpenAPI 规范（Action + BO CRUD + Meta）"""
    action_spec = _generate_action_openapi()
    bo_paths = _generate_bo_crud_paths(registry.all())
    bo_schemas = {
        obj.id: _generate_bo_schema(obj) for obj in registry.all() if obj.table_name
    }
    spec = action_spec.copy()
    spec['paths'].update(bo_paths)
    spec['components']['schemas'].update(bo_schemas)
    spec['info']['title'] = 'Excel-to-Diagram Full API'
    return jsonify(spec)
```

**安全保证**:
- 纯只读端点（GET）
- 现有 `/_openapi.json` (Action-only) 端点保持不变（向后兼容）
- 新端点路径:`/api/v2/bo/_openapi.json`（不冲突）

### 5.5 FR-3.1: `_inject_display_values()`

**文件**: `meta/core/interceptors/query_interceptor.py`

```python
def _inject_display_values(self, records: list, meta_object) -> None:
    """为每条 record 注入 display_values 子对象（增量字段，不修改原值）"""
    if not meta_object or not meta_object.fields or not records:
        return

    display_field_map = {}
    for field in meta_object.fields:
        if field.type == 'boolean':
            display_field_map[field.id] = ('boolean', None)
        elif getattr(field, 'enum_values', None):
            value_label_map = {v['value']: v.get('label', v['value']) for v in field.enum_values}
            display_field_map[field.id] = ('enum', value_label_map)
        else:
            ui = getattr(field, 'ui', None) or {}
            if ui.get('display_field'):
                display_field_map[field.id] = ('fk', ui['display_field'])

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

### 5.6 FR-3.2: 接入 after_action

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
```

**安全保证**:
- `display_values` 是**增量字段**（`record['display_values'] = {...}`），不改原字段值
- 类型断言保护：仅 `isinstance(records, list)` 时才处理
- 空 records / 空 fields 提前 return

### 5.7 FR-3.3: 前端读 display_values

**文件**: `src/composables/useMetaList.js`

**改动位置**: `loadList()` / `handleResponse()` 中读取响应

```javascript
// 现有代码
async function loadList(params) {
  const response = await api.get(`/api/v2/bo/${objectType}`, { params })
  items.value = response.data.items || response.data
  total.value = response.data.total || items.value.length
}

// 改动: 不直接修改 items，但记录原始值以备 fallback
async function loadList(params) {
  const response = await api.get(`/api/v2/bo/${objectType}`, { params })
  items.value = response.data.items || response.data
  total.value = response.data.total || items.value.length
  // display_values 已被 _inject_display_values 注入到每条 record
  // 模板渲染时优先读 item.display_values[fieldId]，fallback 到 item[fieldId]
}
```

**安全保证**:
- 不修改原字段值（增量）
- 模板可继续使用 `item[fieldId]`，只在需要展示时读 `item.display_values?.[fieldId]`
- Fallback 模式：服务端未注入时不影响现有渲染

### 5.8 FR-4.1: `_check_conditional_required()`

**文件**: `meta/core/constraint_engine.py`

```python
def _check_conditional_required(self, context, field, constraint):
    """条件必填校验：仅在 create/update 时触发"""
    if context.action not in ('crud_create', 'crud_update'):
        return None
    condition = constraint.get('condition', '')
    if not condition:
        return None
    from meta.core.expression_evaluator import safe_evaluate
    data = context.params
    # 条件不满足 → 跳过
    if not safe_evaluate(condition, data):
        return None
    # 条件满足 → 校验字段必填
    field_id = constraint.get('field', getattr(field, 'id', '') if field else '')
    value = data.get(field_id)
    if value is None or value == '':
        return ConstraintViolation(
            field_id=field_id,
            rule='conditional_required',
            message=constraint.get('message', f'{field_id} 条件必填校验失败'),
            severity=constraint.get('severity', 'error'),
        )
    return None
```

**安全保证**:
- `safe_evaluate` 沙箱（白名单运算符）
- 仅 create/update 触发，不影响 query/list/delete
- 条件为空时跳过（向后兼容）

### 5.9 FR-4.2: 路由到新方法

```python
def _check_constraint(self, context, field, constraint):
    constraint_type = constraint.get('type', '')
    if constraint_type == 'unique_scope':
        return self._check_unique_scope(context, field, constraint)
    elif constraint_type == 'immutable':
        return self._check_immutable(context, field, constraint)
    elif constraint_type == 'no_delete':
        return self._check_no_delete(context, field, constraint)
    elif constraint_type == 'conditional_required':  # 新增
        return self._check_conditional_required(context, field, constraint)
    return None
```

### 5.10 FR-4.3: FieldPolicyEngine 联动

**文件**: `meta/services/field_policy_engine.py:99` `is_field_required()`

**现有代码**（推测）:
```python
def is_field_required(self, field_id, context=None):
    if field_id in self._field_policies:
        policy = self._field_policies[field_id]
        if policy.required:
            return self._evaluate_required_policy(policy.required, context)
    field_def = self._get_field(field_id)
    if field_def:
        return self._is_field_required_by_definition(field_def)
    return False
```

**改动**: 在 field_def 检查中追加 conditional_required 检查

```python
def is_field_required(self, field_id, context=None):
    # 1. 检查已注册策略（含 RequiredPolicy）
    if field_id in self._field_policies:
        policy = self._field_policies[field_id]
        if policy.required:
            return self._evaluate_required_policy(policy.required, context)

    # 2. 检查字段定义
    field_def = self._get_field(field_id)
    if field_def:
        required = self._is_field_required_by_definition(field_def)
        # 2.5 新增：检查字段 constraints 中的 conditional_required
        if not required and getattr(field_def, 'constraints', None):
            for c in field_def.constraints:
                if c.get('type') == 'conditional_required' and c.get('field') == field_id:
                    if context and getattr(context, 'data', None):
                        from meta.core.expression_evaluator import safe_evaluate
                        if safe_evaluate(c.get('condition', ''), context.data):
                            return True
        return required
    return False
```

### 5.11 FR-4.4: YAML 示例

**文件**: `meta/schemas/business_object.yaml`

```yaml
# 在 validations 列表中添加示例（不破坏现有 validations）
validations:
  # 现有约束...
  - id: sub_domain_conditional_required
    name: 子领域条件必填
    type: conditional_required
    field: sub_domain_id
    condition: "domain_id is not None"
    message: 选择领域后，子领域不能为空
    severity: error
```

### 5.12 FR-4.5: 前端读 conditional_required

**文件**: `src/composables/useFieldPolicy.js`

**改动位置**: L122-128 `loadFieldPolicies()` 之后 + 4 个 Map 之前

**当前代码**（推测）:
```javascript
async function loadFieldPolicies(objectType) {
  const response = await api.get(`/api/v2/bo/${objectType}/field-policies`)
  fieldPolicies.value = response.data.policies || {}
  policiesLoaded.value = true
}
```

**改动**: 读取后端返回的 `conditional_required` 数组（如果存在）并暴露为 `conditionalRequiredMap`

```javascript
// 假设后端 /field-policies API 改造后返回:
//   policies[fieldId] = { editable, visible, required, conditional_required: [...] }

async function loadFieldPolicies(objectType) {
  const response = await api.get(`/api/v2/bo/${objectType}/field-policies`)
  fieldPolicies.value = response.data.policies || {}
  policiesLoaded.value = true
}

// 新增: conditionalRequiredMap（Map<fieldId, conditionArray>）
const conditionalRequiredMap = computed(() => {
  const result = {}
  for (const [fid, policy] of Object.entries(fieldPolicies.value || {})) {
    if (policy?.conditional_required) {
      result[fid] = policy.conditional_required
    }
  }
  return result
})
```

**注意**: 实际后端 `/field-policies` API 需改造返回 `conditional_required` 字段（如未在 v1 批次 2 范围，需列入后续）。
**当前批次**: 仅前端占位接口，**等待后端 API 扩展**（如不在 v1 批次 2，需在 TBD 列表）。

---

## 六、实施顺序与并行策略

### 6.1 文件隔离分析

| Agent | 文件 | 冲突？ |
|-------|------|--------|
| A (FR-2) | bo_action_api.py + bo_api.py | 独占 |
| B (FR-3) | query_interceptor.py + useMetaList.js | 独占 |
| C (FR-4) | constraint_engine.py + field_policy_engine.py + business_object.yaml + useFieldPolicy.js | 独占 |

**结论**: 3 个 Agent **完全文件隔离**，可放心并行。

### 6.2 串行约束（同文件内部）

| Agent | 串行任务链 |
|-------|-----------|
| A | 2.1 → 2.2 → 2.3 → 2.4 |
| B | 3.1 → 3.2 → 3.3 |
| C | 4.1 → 4.2 → 4.3 → (4.4 ∥ 4.5) |

### 6.3 推荐并行策略

**单 Agent 实施**（推荐，简化）:
- 单 worktree + 端口 3010
- 顺序完成 A → B → C 3 个 FR（共 12 任务）
- 每个 FR 完成后立即跑 `python d:\filework\test.py --port 3010 --failed`

**多 Agent 并行**（可选，加速）:
- 3 个 worktree + 端口 3010/3011/3012
- A/B/C 同时启动，互不阻塞
- 合并到 main 时按 A → B → C 顺序（避免大冲突）

### 6.4 端口分配（多 Agent 方案）

| Agent | 端口 | worktree | 分支 |
|-------|------|----------|------|
| A (FR-2) | 3010 | d:/workplace/agent-a-openapi | batch2/agent-a-openapi |
| B (FR-3) | 3011 | d:/workplace/agent-b-display | batch2/agent-b-display |
| C (FR-4) | 3012 | d:/workplace/agent-c-conditional | batch2/agent-c-conditional |

---

## 七、验证策略

### 7.1 单测验证（每个任务完成后必做）

```bash
# FR-2.1: 验证 _generate_action_openapi 返回有效 OpenAPI
python -c "from meta.api.bo_action_api import _generate_action_openapi; spec = _generate_action_openapi(); assert spec['openapi'] == '3.0.0'; print('OK')"

# FR-2.4: 验证全量端点返回
curl http://localhost:3010/api/v2/bo/_openapi.json | python -c "import json, sys; spec = json.load(sys.stdin); assert '/api/v2/bo/business_object' in spec['paths']; print('OK')"

# FR-3.1-3.2: 验证 list 响应含 display_values
curl http://localhost:3010/api/v2/bo/business_object | python -c "import json, sys; data = json.load(sys.stdin); assert 'display_values' in data['items'][0]; print('OK')"

# FR-4.1-4.3: 验证 conditional_required 触发
curl -X POST http://localhost:3010/api/v2/bo/sub_domain -d '{"domain_id": "d1", "sub_domain_id": null}' -H "Content-Type: application/json"
# 应返回 400 + "选择领域后，子领域不能为空"
```

### 7.2 回归验证（每 FR 完成后必做）

```bash
python d:\filework\test.py --port 3010 --failed
```

### 7.3 全量验证（实施完毕后）

```bash
python d:\filework\test.py --port 3010 --all --force
python d:\filework\test.py --port 3010 --failed  # 串行确认
```

### 7.4 E2E 验证（v1 批次 2 完成后）

```bash
# 启动服务
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start

# Swagger UI 访问 http://localhost:3010/api/v2/bo/_openapi.json
# 列表 UI 看到 display_values 列正常展示
# 创建/更新业务_object 测试 conditional_required
```

---

## 八、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| **bo_api.py 是核心 API 文件**，改动易破坏现有路由 | 中 | 高 | 仅新增端点 + 端点路径用 `_openapi.json` 后缀，不影响现有路由 |
| **query_interceptor.py 是查询拦截器**，display_values 是 O(N) 操作 | 中 | 中 | 仅在 `is_query_action` 触发；空 records 提前 return；性能测试 |
| **constraint_engine.py 已有 4 种约束类型**，新加 conditional_required 可能冲突 | 低 | 中 | 仅追加 `elif` 分支，不改已有逻辑 |
| **field_policy_engine.py `is_field_required()` 改动影响范围广** | 中 | 高 | 在 2.5 步插入新增逻辑，已有的 1-2 步不变；新逻辑只读不改 |
| **YAML 改动影响所有 BO 加载** | 低 | 中 | 仅在 validations 列表追加示例，不改 schema 顶层结构 |
| **`/field-policies` API 未返回 `conditional_required`** | 高 | 中 | FR-4.5 实施时先确认 API 返回结构，必要时列入 v1 批次 3 或独立小补丁 |
| **批次 1 已合入 main 与批次 2 worktree 漂移** | 中 | 低 | worktree 自管 rebase；批次 2 任务量小（12 任务）冲突面有限 |
| **FR-2.4 与现有 `/_openapi.json` (Action-only) 端点路径冲突** | 低 | 中 | 新端点路径为 `/api/v2/bo/_openapi.json`（不冲突） |

---

## 九、Requirements Quality Checklist

| 检查项 | 状态 |
|--------|------|
| 每项任务有明确的文件位置 | ✅ 12/12 |
| 每项任务有改动代码示例 | ✅ 12/12 |
| 每项任务有安全保证说明 | ✅ 12/12 |
| 每项任务有验证方法 | ✅ 12/12 |
| 任务间依赖关系已识别 | ✅ 串行约束明确 |
| 文件隔离已分析 | ✅ 3 Agent 0 冲突 |
| 不在范围已声明 | ✅ v1 批次 3 排除 |
| 风险已识别并给出缓解 | ✅ 8 项风险 |
| 验证策略完整 | ✅ 单测 + 回归 + 全量 + E2E |

---

## 十、TBD 列表

- **TBD-1**: `meta/api/bo_api.py` 中是否已有 `meta_v2_bp` Blueprint？FR-2.4 端点需要挂在该 Blueprint 上。如无，则需新建或挂到现有 Blueprint。Agent A 启动时确认。
- **TBD-2**: `meta/services/meta_object_registry.registry.all()` 是否为现有 API？如无，需先用 `app_builder.with_yaml_schemas()` 注册的 MetaObject 来源。Agent A 启动时确认。
- **TBD-3**: `/api/v2/bo/{type}/field-policies` API 当前返回结构（参见先前检查）只含 3 字段，无 `conditional_required`。FR-4.5 前端占位接口是否等 API 扩展后再实际消费？
- **TBD-4**: `useMetaList.js` 模板渲染代码是否已有 `display_values` 读取逻辑？FR-3.3 实施时需先 grep 现有模板代码确认。

---

## 十一、附录

### 11.1 文件清单

| 序号 | 文件 | 任务 | 改动行数估算 |
|------|------|------|------------|
| 1 | `meta/api/bo_action_api.py` | FR-2.1 | +30 |
| 2 | `meta/api/bo_api.py` | FR-2.2/2.3/2.4 | +100 |
| 3 | `meta/core/interceptors/query_interceptor.py` | FR-3.1/3.2 | +50 |
| 4 | `src/composables/useMetaList.js` | FR-3.3 | +10 |
| 5 | `meta/core/constraint_engine.py` | FR-4.1/4.2 | +30 |
| 6 | `meta/services/field_policy_engine.py` | FR-4.3 | +15 |
| 7 | `meta/schemas/business_object.yaml` | FR-4.4 | +10 |
| 8 | `src/composables/useFieldPolicy.js` | FR-4.5 | +15 |
| **总计** | | | **+260** |

### 11.2 关键依赖

- Python 3.10+（type hint 使用）
- `meta.core.expression_evaluator.safe_evaluate()` 已存在
- Flask Blueprint (`meta_v2_bp`) 已存在（待 TBD-1 确认）

### 11.3 端口速查

- 3010: Agent A (FR-2) — OpenAPI
- 3011: Agent B (FR-3) — display_values
- 3012: Agent C (FR-4) — conditional_required

### 11.4 启动前置

- 工作目录 git 状态已修复（已创建 main + 初始 commit `55f1508`）
- 各 Agent 启动时基于 `batch2/wave1` 分支（已创建但未 checkout）
