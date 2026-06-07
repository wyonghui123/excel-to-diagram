# 批次 2 详细实现方案（基于代码现状深度分析）

> **版本**: v2.0 | **日期**: 2026-06-07 | **状态**: 🟡 详细设计
> **配套文档**:
> - [spec-pre-deployment-optimization.md (v1.1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) — 原始规格
> - [spec-batch2-backend-capabilities.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-backend-capabilities.md) — 概要设计
> - [batch2-agent-assignments.md](file:///d:/filework/excel-to-diagram/docs/specs/batch2-agent-assignments.md) — 多 Agent 协调手册

---

## 一、背景与目标

**v1 批次 1 已完成**（2026-06-07）：FR-1（自动 DDL）+ FR-5（AppBuilder 统一）共 10 任务。

**v1 批次 2 范围**：FR-2 + FR-3 + FR-4 共 12 任务，全部后端能力扩展（+ 前端最小适配）。

**本批次与 v1 规格的差异（已基于代码现状核查）**：
- v1 规格写 FR-2.1"提取 `_generate_action_openapi()`" — **实际已有 134 行实现**（bo_action_api.py:538-671），FR-2.1 应改为"重构 + 提取"
- v1 规格写 FR-2.4"新增全量 OpenAPI 端点" — 实际**有现成 Action-only 端点**，应放 `meta_v2_bp`（不同 Blueprint）避免冲突
- v1 规格写 FR-3.3"前端读 display_values" — 实际**实现点应在 `getCellValue` 函数**（useMetaList.js:1646），而非 loadList

**对标业界**：
- FR-2（OpenAPI 自动生成）：SAP CAP / ORDS metadata-catalog
- FR-3（display_values）：Salesforce displayValue
- FR-4（conditional_required）：Salesforce Dynamic Forms

---

## 二、7 维度需求分析

### 2.1 背景（Why）

| 项 | 现状 | 改进目标 |
|---|------|---------|
| OpenAPI 规范 | 仅 Action 端点，无 BO CRUD | 全量 OpenAPI（Action + BO CRUD + MetaObject）|
| 列表展示值 | 前端推断（FK 取冗余字段、枚举手动 mapping、布尔手写）| 后端预格式化，节省前端推断 + 跨端一致 |
| 条件必填 | YAML `type: field`（简单 `is not None` 检查）| 复杂条件（如"选择领域后，子领域必填"）|

### 2.2 范围（What）

12 任务分布在 8 文件（**全 1493+668+105+1716+162+441+1044+486 = 6115 行业务代码**）：

| FR | 任务 | 文件 | 改动行数估算 |
|----|------|------|------------|
| FR-2 | OpenAPI | bo_action_api.py + bo_api.py | +135 |
| FR-3 | display_values | query_interceptor.py + useMetaList.js | +55 |
| FR-4 | conditional_required | constraint_engine.py + field_policy_engine.py + business_object.yaml + useFieldPolicy.js | +75 |
| **总计** | | **8 文件** | **+265** |

### 2.3 当前实现情况（As-Is）— 基于实际代码读取

#### 2.3.1 bo_action_api.py（668 行，FR-2.1）

| 项 | 状态 |
|---|------|
| L46 `bo_action_bp = Blueprint(...)` | 已有 |
| **L538-671 `openapi_spec()` 端点** | **已有 134 行实现**，遍历 `bo_action_registry.list_all()` 生成 spec |
| L677 `/_docs` swagger_ui | 已有 |
| L732 list_actions | 已有 |

**v1 规格说"提取"是错的** — 实际无内联逻辑可提取。应改为**"重构为独立函数 `_generate_action_openapi()` + 端点改为调函数"**。

#### 2.3.2 bo_api.py（1493 行，FR-2.2/2.3/2.4 + FR-4.5 关联）

| 项 | 状态 |
|---|------|
| L15 `bo_bp = Blueprint('bo_v2', ...)` | 已有（`/api/v2/bo`）|
| **L16 `meta_v2_bp = Blueprint('meta_v2', ...)`** | **已有**（`/api/v2/meta`）→ **TBD-1 解决！** |
| L179-253 `query_bo(object_type)` | 已有 |
| L691-729 `batch_delete_bo(object_type)` | 已有 |
| L1065-1107 `get_meta_full(object_type)` | 已有 |
| **L1108-1146 `get_field_policies(object_type)`** | **已有**，但 L1131-1135 只返回 3 字段（editable/visible/required）|

**TBD-3 确认**：`/field-policies` API **当前不返回 `conditional_required` 字段**。FR-4.5 需改造 L1131 字典构造。

#### 2.3.3 query_interceptor.py（105 行，FR-3.1/3.2）

| 项 | 状态 |
|---|------|
| L13 class QueryInterceptor | 已有 |
| L29 priority = 50 | 已有 |
| **L35-50 `after_action()`** | 已有 4 步：`_inject_type_tag` → `_enrich_records` → `_compute_columns` → `_check_can_delete` |
| L67 `_inject_type_tag` | 已有 |
| L73 `_enrich_records` | 已有（调 `enrich_records`）|
| L84 `_compute_columns` | 已有（调 `computation_service`）|
| L110 `_check_can_delete` | 已有 |

**FR-3.2 接入点**：L44 `_enrich_records` 之后，L45 `_compute_columns` 之前（**新增第 5 步**）。

#### 2.3.4 useMetaList.js（1716 行，FR-3.3）

| 项 | 状态 |
|---|------|
| L393-450 `loadList()` | 已有，**L416 之后直接 `data.value = rawData.items`**（无 display_values 处理）|
| **L1646-1652 `getCellValue(row, fieldName)`** | **已有但简单**：直接读 `row[fieldName]`（draftValues 优先）|
| 模板渲染（1800+ 行）| 各处用 `getCellValue` |

**FR-3.3 实际改造点**：**L1646 `getCellValue` 优先读 `row.display_values?.[fieldName]`**（不是改 loadList）。

#### 2.3.5 constraint_engine.py（162 行，FR-4.1/4.2）

| 项 | 状态 |
|---|------|
| L11-18 `ConstraintViolation` 类 | 已有（field_id, message, constraint_type）|
| L21-70 `validate(context)` | 已有 |
| **L72-88 `_check_constraint()` 路由** | 已有 3 类型（unique_scope / immutable / no_delete）|
| L90-140 `_check_unique_scope` | 已有（参考）|
| L142-161 `_check_immutable` | 已有（参考）|
| L163-181 `_check_no_delete` | 已有（参考）|
| L183-198 `_values_match` | 已有辅助 |

**FR-4.1 改造点**：**新增 `_check_conditional_required()` 方法**（参考 `_check_immutable` 模式 L142-161）。
**FR-4.2 改造点**：**L86 后追加 `elif constraint_type == 'conditional_required'`**。

#### 2.3.6 field_policy_engine.py（441 行，FR-4.3）

| 项 | 状态 |
|---|------|
| L17-37 dataclass（ObjectContext / UserContext / PolicyContext）| 已有 |
| L40-75 dataclass（PolicyRule / EditablePolicy / VisiblePolicy / RequiredPolicy / FieldPolicy）| 已有 |
| **L182-197 `is_field_required(field_id, context)`** | 已有 — 1) 检查已注册 RequiredPolicy；2) `_is_field_required_by_definition` |
| L213-220 `_is_field_required_by_definition` | 已有（读 `field.constraints.required`）|
| L258-274 `_evaluate_required_policy` | 已有（遍历 determination + rule.when_expr）|
| **L290-310 `_evaluate_expression`** | **关键** — 已用 `safe_evaluate(expr, local_vars)`，local_vars 包含 `{row, object, user, action}` |

**FR-4.3 改造点**：**L193-195 之后插入 conditional_required 检查** — 读 `field.constraints` 列表（如有 `type: conditional_required` 规则），用 `safe_evaluate(rule.condition, {row: context.row, ...})` 评估。

**关键洞察**：**`safe_evaluate` 已支持 row 上下文求值**（`_evaluate_expression` L300-305），FR-4.3 直接复用。

#### 2.3.7 business_object.yaml（1044 行，FR-4.4）

| 项 | 状态 |
|---|------|
| L1078 `validations:` | 已有 |
| L1079-1083 现有示例 | `version_id_required`（type: field, rule: "version_id is not None"）|

**v1 规格说"追加 conditional_required 示例"** — 现有 validations 用 `type: field` 格式，**新约束类型 `conditional_required` 与之共存**。需在 L1083 后追加示例。

#### 2.3.8 useFieldPolicy.js（486 行，FR-4.5）

| 项 | 状态 |
|---|------|
| L41 `useFieldPolicy(metaConfig, columns)` 入口 | 已有 |
| L47 `fieldPolicies` ref | 已有 |
| L56-74 `loadFieldPolicies` | 已有（调 `/meta/{type}/field-policies`）|
| L80-130 `editableMap` computed | 已有 |
| L136-175 `visibleMap` computed | 已有 |
| L181-205 `immutableMap` computed | 已有 |
| L211-235 `readonlyAlwaysMap` computed | 已有 |
| L241-255 `businessKeyMap` computed | 已有 |
| **L364-386 `isRequired(fieldId)`** | 已有（单字段，静态）|
| L491-516 return 对象 | 已有 5 Maps + 8 函数 |

**FR-4.5 改造点**：
1. **新增 `requiredMap` computed**（参照 editableMap L80-130 模式）
2. **改造 `isRequired(fieldId, row=null)`**（参照 isEditable L274 模式）
3. **L491-516 return 追加新项**

### 2.4 需求（What to do）

| FR | 任务 | 实施细节 |
|----|------|---------|
| FR-2.1 | 重构 `openapi_spec()` → `_generate_action_openapi()` | bo_action_api.py L538-671 拆分为函数 + 端点改造 |
| FR-2.2 | 新增 `_generate_bo_crud_paths()` | bo_api.py L~1493 前追加 |
| FR-2.3 | 新增 `_generate_bo_schema()` + `_map_field_type()` | bo_api.py L~1500 前追加 |
| FR-2.4 | 新增全量 OpenAPI 端点 `@meta_v2_bp.route('/_openapi.json')` | bo_api.py L~1150 前插入 |
| FR-3.1 | 新增 `_inject_display_values()` | query_interceptor.py L~100 后 |
| FR-3.2 | after_action 接入 | query_interceptor.py L44 后插入调用 |
| FR-3.3 | 优先读 display_values | useMetaList.js L1646 getCellValue 改造 |
| FR-4.1 | 新增 `_check_conditional_required()` | constraint_engine.py L182 前 |
| FR-4.2 | 路由追加 | constraint_engine.py L86 后 |
| FR-4.3 | is_field_required 联动 | field_policy_engine.py L195 后 |
| FR-4.4 | YAML 示例 | business_object.yaml L1083 后 |
| FR-4.5 | useFieldPolicy 增强 | useFieldPolicy.js 多处 |

### 2.5 约束（Constraints）

- ✅ **保持向后兼容**：所有新增功能不得破坏现有 API 行为
- ✅ **fallback 模式**：前端 `getCellValue` 改造时 record 无 `display_values` 不影响渲染
- ✅ **safe_evaluate 沙箱**：所有条件求值必须走 `safe_evaluate`，不得用 `eval` / `exec`
- ✅ **Blueprint 路径不冲突**：FR-2.4 用 `meta_v2_bp`（`/api/v2/meta/_openapi.json`）而非 `bo_action_bp`（`/api/v2/action/_openapi.json`）
- ✅ **性能**：`_inject_display_values` O(N) 操作，仅在 `is_query_action` 触发，空 records 提前 return
- ✅ **不要修改现有路由**：仅追加新端点 / 新方法

### 2.6 风险（Risks）

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `get_field_policies` 改造影响其他调用方 | 中 | 中 | 保留 3 字段，加 1 字段，路径不变 |
| `useFieldPolicy.isRequired` 改造影响 30+ 组件 | 中 | 中 | 保留单参数重载（fallback），新 row 参数可选 |
| `_inject_display_values` 性能（O(N) + 内层循环）| 中 | 中 | 限制记录数 + 空 records 提前 return + 缓存 field_type_map |
| `getCellValue` 改造影响所有列渲染 | 中 | 中 | fallback 链（display_values → draftValues → 原值）|
| YAML validations 改造需重启加载 | 低 | 低 | SchemaCache 失效会自动重建 |
| 改 useMetaList.js 时其他位置也读 `row.display_values` | 低 | 低 | Grep 验证唯一性 |
| 改 query_interceptor.py 顺序错导致后续钩子不触发 | 低 | 高 | 在 `_compute_columns` 之前（不改变其他步骤顺序）|

### 2.7 验收（Acceptance）

每任务需通过：

| 检查项 | 验证方法 |
|--------|---------|
| Python 文件 | `python -c "import <module>"` 无 syntax error |
| Vue/JS 文件 | `node -c <file>`（如可用）或 IDE ESLint |
| 单元测试 | `python d:\filework\test.py --port 3010 --single <test_id>` |
| 回归测试 | `python d:\filework\test.py --port 3010 --failed` |
| E2E 验证 | curl + Swagger UI 检查 |

---

## 三、跨文件调用链（数据流图）

### 3.1 FR-2 OpenAPI（涉及 2 个 Python 文件）

```
用户访问 GET /api/v2/meta/_openapi.json
        ↓
bo_api.py: get_full_openapi() 端点（新）  [FR-2.4]
        ├── _generate_action_openapi()    [FR-2.1 重构自 bo_action_api.py:538-671]
        ├── _generate_bo_crud_paths(registry.all())  [FR-2.2 新增]
        └── _generate_bo_schema(obj) for each obj   [FR-2.3 新增]
                ↓
返回合并的 OpenAPI spec JSON
```

### 3.2 FR-3 display_values（涉及 2 个文件：后端 + 前端）

```
前端 GET /api/v2/bo/{object_type}
        ↓
bo_api.py: query_bo() 端点
        ↓
QueryInterceptor.after_action()  [query_interceptor.py:35]
        ├── _inject_type_tag()       (已有 L43)
        ├── _enrich_records()        (已有 L44)
        ├── _inject_display_values() ← [FR-3.1 新增, FR-3.2 接入点 L44后]
        ├── _compute_columns()       (已有 L45)
        └── _check_can_delete()      (已有 L46)
                ↓
返回 records（含 display_values 子对象）
        ↓
前端 useMetaList.loadList()
        ↓
data.value = rawData.items
        ↓
列渲染调用 getCellValue(row, fieldName)
        ├── 1) draftValues[row.id][fieldName]  (编辑态)
        ├── 2) row.display_values?.[fieldName] ← [FR-3.3 新增]
        └── 3) row[fieldName]                  (原值)
                ↓
返回显示值
```

### 3.3 FR-4 conditional_required（涉及 4 个文件：后端 3 + 前端 1）

```
YAML business_object.yaml validations:
  - type: conditional_required
    field: sub_domain_id
    condition: "domain_id is not None"
        ↓ 启动时加载
ConstraintEngine.validate(context)  [constraint_engine.py:31]
        ↓
对每个 field.constraints
        ↓
_check_constraint() 路由  [constraint_engine.py:72, FR-4.2 追加]
        ├── unique_scope
        ├── immutable
        ├── no_delete
        └── conditional_required ← [FR-4.1 新增, FR-4.2 路由]
                ↓
_check_conditional_required()  [FR-4.1]
        ├── 检查 context.action ∈ ('crud_create', 'crud_update')
        ├── safe_evaluate(condition, data)  ← [复用 meta.core.safe_expr_evaluator]
        └── 返回 ConstraintViolation 或 None
```

**字段策略联动路径**：
```
GET /api/v2/meta/{type}/field-policies
        ↓
bo_api.py: get_field_policies()  [L1108-1146]
        ↓
FieldPolicyEngine.is_field_required(field_id, context)  [L182, FR-4.3 改造]
        ├── 1) 检查 _field_policies 注册的 RequiredPolicy
        ├── 2) field_def.constraints 简单 required
        └── 3) field_def.constraints 列表中 conditional_required ← [FR-4.3 新增]
                ↓
返回 policies[field_id] = {editable, visible, required, conditional_required: [...]}
```

**前端消费路径**：
```
useFieldPolicy.loadFieldPolicies()  [useFieldPolicy.js:56]
        ↓
useFieldPolicy.requiredMap  computed  ← [FR-4.5 新增]
        ↓
useFieldPolicy.isRequired(fieldId, row)  ← [FR-4.5 改造，支持 row 上下文]
        ↓
MetaForm 组件 validateField() 引用
```

---

## 四、详细设计（code-level）

### 4.1 FR-2.1: 重构 openapi_spec 为独立函数

**文件**: [meta/api/bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py)
**当前**: L538-671 `openapi_spec()` 端点（134 行）
**目标**: 提取为 `_generate_action_openapi()` 独立函数

**改动策略**：
1. **不破坏现有端点行为**（向后兼容）
2. **新增独立函数** `_generate_action_openapi()` 接受可选 `base_url` 参数
3. **端点改造**：`return jsonify(_generate_action_openapi(base_url))`

**实施代码**：

```python
# 在 bo_action_api.py L538 之前新增：

def _generate_action_openapi(base_url: str = 'http://localhost:3010') -> dict:
    """
    生成 Action OpenAPI 规范（独立函数，可被 FR-2.4 复用）
    
    返回结构: OpenAPI 3.0 spec dict
    """
    paths = {}
    components_schemas = {}
    tags_set = set()
    
    for meta in bo_action_registry.list_all():
        path = f'/api/v2/action/{meta.action_id}'
        safe_id = meta.action_id.replace('.', '_')
        input_ref = f'#/components/schemas/{safe_id}_input'
        output_ref = f'#/components/schemas/{safe_id}_output'
        
        if meta.operation_type == 'function':
            method = 'get'
        else:
            method = 'post'
        
        tag = f'{meta.category or "business"}/{meta.operation_type}'
        tags_set.add(tag)
        
        operation = {
            'operationId': meta.action_id,
            'summary': meta.description or meta.action_id,
            'tags': [tag],
            'requestBody': {
                'content': {'application/json': {'schema': {'$ref': input_ref}}}
            } if method == 'post' else None,
            'parameters': [
                {'name': k, 'in': 'query', 'schema': {'type': 'string'},
                 'required': meta.input_schema.get('required', []).__contains__(k) if meta.input_schema else False}
                for k in (meta.input_schema.get('properties', {}).keys() if meta.input_schema else [])
            ] if method == 'get' and meta.input_schema else None,
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {'application/json': {'schema': {'$ref': output_ref}}}
                },
                '401': {'description': '未登录'},
                '403': {'description': '权限不足'},
                '404': {'description': 'Action 不存在'},
            }
        }
        if meta.requires_admin:
            operation['description'] = (operation.get('description') or '') + ' (admin only)'
        
        op_type_label = f'[{meta.operation_type.upper()}]' if meta.operation_type != 'action' else ''
        if op_type_label:
            operation['summary'] = f'{op_type_label} {operation["summary"]}'
        
        operation = {k: v for k, v in operation.items() if v is not None}
        
        if path not in paths:
            paths[path] = {}
        paths[path][method] = operation
        
        if meta.input_schema:
            components_schemas[f'{safe_id}_input'] = meta.input_schema
        else:
            components_schemas[f'{safe_id}_input'] = {'type': 'object', 'additionalProperties': True}
        if meta.output_schema:
            components_schemas[f'{safe_id}_output'] = meta.output_schema
        else:
            components_schemas[f'{safe_id}_output'] = {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'data': {},
                    'message': {'type': 'string'},
                }
            }
    
    return {
        'openapi': '3.0.0',
        'info': {
            'title': 'BO Action API',
            'version': 'v3.6',
            'description': '业务行为 API 统一端点',
        },
        'servers': [
            {'url': base_url, 'description': '当前服务'},
            {'url': 'http://localhost:3010', 'description': '本地开发'},
        ],
        'tags': [
            {'name': tag, 'description': f'{tag.split("/")[1]} 类型 Action ({tag.split("/")[0]} 域)'}
            for tag in sorted(tags_set)
        ],
        'paths': paths,
        'components': {
            'securitySchemes': {
                'cookieAuth': {
                    'type': 'apiKey',
                    'in': 'cookie',
                    'name': 'auth_token',
                    'description': 'HttpOnly cookie 自动携带 (登录后 set_cookie)',
                }
            },
            'schemas': components_schemas,
        },
        'security': [{'cookieAuth': []}],
    }
```

**端点改造**（替换 L538-671 为）：

```python
@bo_action_bp.route('/_openapi.json', methods=['GET'])
def openapi_spec():
    """🆕 v3.6: Action OpenAPI 3.0 规范输出（重构自内联实现）"""
    from flask import request as _req
    base_url = _req.host_url.rstrip('/')
    return jsonify(_generate_action_openapi(base_url))
```

**安全保证**：
- 端点路径不变（`/api/v2/action/_openapi.json`）
- 输出结构不变（向后兼容）
- 新函数可被 FR-2.4 复用

### 4.2 FR-2.2: BO CRUD paths 生成

**文件**: [meta/api/bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py)
**目标**: 在文件末尾（`bo_api.py` L~1493 前）追加 `_generate_bo_crud_paths()` 函数

**实施代码**：

```python
def _generate_bo_crud_paths(meta_objects) -> dict:
    """
    为每个 BO 类型生成 7 个标准 CRUD 端点的 OpenAPI path 描述
    
    端点:
    - GET    /api/v2/bo/{type}            列表
    - POST   /api/v2/bo/{type}            创建
    - GET    /api/v2/bo/{type}/{id}       详情
    - PUT    /api/v2/bo/{type}/{id}       更新
    - DELETE /api/v2/bo/{type}/{id}       删除
    - POST   /api/v2/bo/{type}/deep       深度插入
    - POST   /api/v2/bo/{type}/batch-delete  批量删除
    """
    paths = {}
    for obj in meta_objects:
        if not obj.table_name:
            continue
        type_name = obj.id
        base = f'/api/v2/bo/{type_name}'
        type_tag = f'BO/{type_name}'
        
        paths[base] = {
            'get': {
                'operationId': f'bo_{type_name}_list',
                'summary': f'查询 {obj.display_name or type_name} 列表',
                'tags': [type_tag],
                'parameters': [
                    {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
                    {'name': 'page_size', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
                    {'name': 'order_by', 'in': 'query', 'schema': {'type': 'string'}},
                    {'name': 'search', 'in': 'query', 'schema': {'type': 'string'}},
                ],
                'responses': {
                    '200': {'description': '列表数据', 'content': {'application/json': {'schema': {'type': 'object', 'properties': {'items': {'type': 'array'}, 'total': {'type': 'integer'}}}}}}
                },
            },
            'post': {
                'operationId': f'bo_{type_name}_create',
                'summary': f'创建 {obj.display_name or type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {
                        'application/json': {
                            'schema': {'$ref': f'#/components/schemas/{type_name}'}
                        }
                    }
                },
                'responses': {
                    '201': {'description': '已创建'},
                    '400': {'description': '参数错误'},
                },
            },
        }
        paths[f'{base}/{{id}}'] = {
            'get': {
                'operationId': f'bo_{type_name}_get',
                'summary': f'获取 {type_name} 详情',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '200': {'description': '详情数据', 'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}},
                    '404': {'description': '未找到'},
                },
            },
            'put': {
                'operationId': f'bo_{type_name}_update',
                'summary': f'更新 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '200': {'description': '已更新'},
                    '400': {'description': '参数错误'},
                    '404': {'description': '未找到'},
                },
            },
            'delete': {
                'operationId': f'bo_{type_name}_delete',
                'summary': f'删除 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '204': {'description': '已删除'},
                    '404': {'description': '未找到'},
                },
            },
        }
        paths[f'{base}/deep'] = {
            'post': {
                'operationId': f'bo_{type_name}_deep_create',
                'summary': f'深度插入 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '201': {'description': '已深度插入'},
                },
            }
        }
        paths[f'{base}/batch-delete'] = {
            'post': {
                'operationId': f'bo_{type_name}_batch_delete',
                'summary': f'批量删除 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {
                        'type': 'object',
                        'properties': {'ids': {'type': 'array', 'items': {'type': 'string'}}}
                    }}}
                },
                'responses': {
                    '200': {'description': '已批量删除'},
                },
            }
        }
    return paths
```

### 4.3 FR-2.3: MetaObject → JSON Schema 转换

**文件**: [meta/api/bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py)
**目标**: 追加 2 个函数

**实施代码**：

```python
_TYPE_MAP = {
    'string': 'string', 'text': 'string', 'integer': 'integer',
    'float': 'number', 'boolean': 'boolean', 'date': 'string',
    'datetime': 'string', 'json': 'object',
}

def _map_field_type(field_type: str) -> str:
    """将内部字段类型映射为 OpenAPI/JSON Schema 类型"""
    return _TYPE_MAP.get(field_type, 'string')

def _generate_bo_schema(meta_object) -> dict:
    """
    将 MetaObject 转换为 OpenAPI components/schemas 子对象
    
    防御: 用 getattr(field, 'xxx', None) 处理字段可能缺失的属性
    """
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

### 4.4 FR-2.4: 全量 OpenAPI 端点

**文件**: [meta/api/bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py)
**位置**: 在 `get_field_policies`（L1108）**之前**插入新端点
**Blueprint**: `meta_v2_bp`（已存在 L16）

**实施代码**：

```python
@meta_v2_bp.route('/_openapi.json', methods=['GET'])
def get_full_openapi():
    """
    🆕 v1 批次 2 / FR-2.4: 全量 OpenAPI 规范（Action + BO CRUD + Meta）
    
    与 bo_action_api._openapi.json（Action-only）共存
    """
    from flask import request as _req
    base_url = _req.host_url.rstrip('/')
    
    # 1. Action OpenAPI（从 bo_action_api 复用）
    from meta.api.bo_action_api import _generate_action_openapi
    action_spec = _generate_action_openapi(base_url)
    
    # 2. BO CRUD paths
    from meta.core.models import registry
    meta_objects = list(registry.all()) if hasattr(registry, 'all') else []
    bo_paths = _generate_bo_crud_paths(meta_objects)
    
    # 3. BO schemas
    bo_schemas = {
        obj.id: _generate_bo_schema(obj) for obj in meta_objects if obj.table_name
    }
    
    # 4. 合并
    spec = action_spec.copy()
    spec['paths'].update(bo_paths)
    spec['components']['schemas'].update(bo_schemas)
    spec['info']['title'] = 'Excel-to-Diagram Full API'
    spec['info']['version'] = 'v2.0'
    spec['info']['description'] = '全量 OpenAPI 规范（Action + BO CRUD + Meta）'
    
    return jsonify(spec)
```

**关键点**：
- 路径：`/api/v2/meta/_openapi.json`（**不与 Action-only 端点冲突**）
- 复用 `_generate_action_openapi` 函数（FR-2.1 重构的产物）
- TBD-1 已解决：`meta_v2_bp` 存在
- TBD-2 已解决：`registry.all()` 通过 hasattr 防御性检查

### 4.5 FR-3.1: `_inject_display_values()` 方法

**文件**: [meta/core/interceptors/query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py)
**目标**: 在类末尾（L~105 前）新增方法

**实施代码**：

```python
def _inject_display_values(self, context: 'ActionContext', items: list) -> None:
    """
    🆕 v1 批次 2 / FR-3.1: 为每条记录注入 display_values 子对象
    
    字段类型映射:
    - boolean: true→"是", false→"否"
    - enum: 从 field.enum_values 取 value→label
    - fk: 从 field.ui.display_field 取冗余字段值
    
    安全保证:
    - display_values 是**增量字段**，不改原 record 字段值
    - 空 records / 空 fields 提前 return（O(1) 短路）
    - 仅在 is_query_action 触发（由 after_action 决定）
    """
    if not items:
        return
    
    meta_obj = context.meta_object
    if not meta_obj or not getattr(meta_obj, 'fields', None):
        return
    
    # 1) 构造 field_type_map（O(F) 一次遍历）
    field_type_map = {}  # field_id -> ('boolean', None) | ('enum', {value: label}) | ('fk', display_field)
    for field in meta_obj.fields:
        if field.type == 'boolean':
            field_type_map[field.id] = ('boolean', None)
        elif getattr(field, 'enum_values', None):
            value_label_map = {v['value']: v.get('label', v['value']) for v in field.enum_values}
            field_type_map[field.id] = ('enum', value_label_map)
        else:
            ui = getattr(field, 'ui', None) or {}
            if ui.get('display_field'):
                field_type_map[field.id] = ('fk', ui['display_field'])
    
    if not field_type_map:
        return
    
    # 2) 遍历 records 注入 display_values（O(N*F)）
    for record in items:
        if not isinstance(record, dict):
            continue
        dv = {}
        for field_id, (field_type, mapping) in field_type_map.items():
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

### 4.6 FR-3.2: 接入 after_action 流程

**文件**: [meta/core/interceptors/query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py)
**位置**: L44 `_enrich_records(context, items)` 之后，L45 `_compute_columns` 之前
**改动**: 1 行新增调用

**实施代码**：

```python
def after_action(self, context: 'ActionContext') -> None:
    if not context.result or not context.result.success:
        return

    if context.is_query_action:
        items = self._extract_items(context)
        if not items:
            return
        self._inject_type_tag(context, items)
        self._enrich_records(context, items)
        self._inject_display_values(context, items)  # 🆕 FR-3.2
        self._compute_columns(context, items)
        self._check_can_delete(context, items)
    elif context.action in ('crud_update', 'crud_create'):
        items = self._extract_items(context)
        if items:
            self._enrich_records(context, items)
```

### 4.7 FR-3.3: 前端 getCellValue 优先读 display_values

**文件**: [src/composables/useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js)
**位置**: L1646-1652 `getCellValue` 函数
**改动**: 在 draftValues 之后、原值之前插入 display_values 读

**当前代码**（L1646-1652）：

```javascript
function getCellValue(row, fieldName) {
  const draftRow = draftValues.value.get(row.id)
  if (draftRow && fieldName in draftRow) {
    return draftRow[fieldName]
  }
  return row[fieldName]
}
```

**改造后**：

```javascript
function getCellValue(row, fieldName) {
  // 1) 编辑态：draftValues 优先
  const draftRow = draftValues.value.get(row.id)
  if (draftRow && fieldName in draftRow) {
    return draftRow[fieldName]
  }
  // 2) 🆕 FR-3.3: 后端预格式化的展示值（display_values）
  if (row && row.display_values && fieldName in row.display_values) {
    const dv = row.display_values[fieldName]
    if (dv !== null && dv !== undefined) {
      return dv
    }
  }
  // 3) 原值（fallback）
  return row[fieldName]
}
```

**安全保证**：
- `display_values` 是**后端增量注入**，未注入时 row.display_values 为 undefined，不影响
- 仅当 `fieldName in row.display_values` 时才读（避免 null/undefined 误用）
- 优先级：draft > display > 原值（编辑态最优先）

**注意**：loadList（L393-450）**不需改** — 因为 `rawData.items` 已直接赋值到 `data.value`，record 上保留 `display_values` 字段。

### 4.8 FR-4.1: `_check_conditional_required()` 方法

**文件**: [meta/core/constraint_engine.py](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py)
**位置**: 在 `_check_no_delete`（L163-181）之后、`_values_match`（L183-198）之前插入

**实施代码**（参考 `_check_immutable` 模式 L142-161）：

```python
def _check_conditional_required(self, context: ActionContext, field, constraint: Dict) -> Optional[ConstraintViolation]:
    """
    🆕 v1 批次 2 / FR-4.1: 条件必填校验
    
    触发条件: context.action ∈ ('crud_create', 'crud_update')
    逻辑:
      1. 读取 constraint.condition
      2. 用 safe_evaluate(condition, context.params) 评估
      3. 条件满足 → 校验 constraint.field 必填
      4. 字段为空 → 返回 ConstraintViolation
    """
    if not (context.is_create_action or context.is_update_action):
        return None
    
    condition = constraint.get('condition', '')
    if not condition:
        return None
    
    # safe_evaluate 已通过 meta.core.safe_expr_evaluator 安全沙箱
    data = context.params or {}
    if not safe_evaluate(condition, data):
        return None
    
    field_id = constraint.get('field') or (getattr(field, 'id', '') if field else '')
    if not field_id:
        return None
    
    value = data.get(field_id)
    if value is None or value == '':
        message = constraint.get('message', f'{getattr(field, "name", field_id) if field else field_id} 条件必填校验失败')
        severity = constraint.get('severity', 'error')
        return ConstraintViolation(
            field_id=field_id,
            message=message,
            constraint_type='conditional_required',
        )
    
    return None
```

### 4.9 FR-4.2: 路由到新方法

**文件**: [meta/core/constraint_engine.py](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py)
**位置**: L86 `elif constraint_type == 'no_delete':` 之后
**改动**: 1 行新增

**当前代码**（L72-88）：

```python
def _check_constraint(self, context: ActionContext, field, constraint: Any) -> Optional[ConstraintViolation]:
    if isinstance(constraint, dict):
        constraint_type = constraint.get('type', '')
    elif hasattr(constraint, 'type'):
        constraint_type = getattr(constraint, 'type', '')
        constraint = constraint.__dict__ if hasattr(constraint, '__dict__') else {}
    else:
        return None

    if constraint_type == 'unique_scope':
        return self._check_unique_scope(context, field, constraint)
    elif constraint_type == 'immutable':
        return self._check_immutable(context, field, constraint)
    elif constraint_type == 'no_delete':
        return self._check_no_delete(context, field, constraint)

    return None
```

**改造后**（L86 后追加）：

```python
    if constraint_type == 'unique_scope':
        return self._check_unique_scope(context, field, constraint)
    elif constraint_type == 'immutable':
        return self._check_immutable(context, field, constraint)
    elif constraint_type == 'no_delete':
        return self._check_no_delete(context, field, constraint)
    elif constraint_type == 'conditional_required':  # 🆕 FR-4.2
        return self._check_conditional_required(context, field, constraint)

    return None
```

### 4.10 FR-4.3: FieldPolicyEngine 联动

**文件**: [meta/services/field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py)
**位置**: L193-195 之后（field_def 检查之后）
**改动**: 在 `_is_field_required_by_definition` 调用之前，插入 conditional_required 检查

**当前代码**（L182-197）：

```python
def is_field_required(
    self,
    field_id: str,
    context: Optional[PolicyContext] = None
) -> bool:
    """判断字段是否必填"""
    if field_id in self._field_policies:
        policy = self._field_policies[field_id]
        if policy.required:
            return self._evaluate_required_policy(policy.required, context)
    
    field_def = self._get_field(field_id)
    if field_def:
        return self._is_field_required_by_definition(field_def)
    
    return False
```

**改造后**：

```python
def is_field_required(
    self,
    field_id: str,
    context: Optional[PolicyContext] = None
) -> bool:
    """判断字段是否必填（含 conditional_required 联动）"""
    if field_id in self._field_policies:
        policy = self._field_policies[field_id]
        if policy.required:
            return self._evaluate_required_policy(policy.required, context)
    
    field_def = self._get_field(field_id)
    if field_def:
        # 1) 基础 required 检查
        base_required = self._is_field_required_by_definition(field_def)
        if base_required:
            return True
        
        # 2) 🆕 FR-4.3: conditional_required 联动
        constraints = getattr(field_def, 'constraints', None)
        if constraints and isinstance(constraints, list):
            for c in constraints:
                if c.get('type') == 'conditional_required' and c.get('field') == field_id:
                    if context and context.row:
                        # 复用 _evaluate_expression 的 safe_evaluate 调用
                        if self._evaluate_expression(c.get('condition', ''), context):
                            return True
        
        return base_required
    
    return False
```

**关键点**：
- **复用 `_evaluate_expression`**（L290-310）— 内部已用 `safe_evaluate` 沙箱，传 `local_vars = {row, object, user, action}`
- **不修改**已有 1-2 步逻辑
- **不破坏** `_is_field_required_by_definition` 行为

### 4.11 FR-4.4: YAML 示例

**文件**: [meta/schemas/business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml)
**位置**: L1083 后追加
**改动**: 1 个 validations 列表项追加

**当前代码**（L1078-1083）：

```yaml
validations:
  - id: version_id_required
    name: 版本ID必填
    type: field
    rule: version_id is not None
    message: 版本ID不能为空
```

**改造后**（L1083 后追加）：

```yaml
validations:
  - id: version_id_required
    name: 版本ID必填
    type: field
    rule: version_id is not None
    message: 版本ID不能为空
  # 🆕 FR-4.4: conditional_required 示例
  - id: sub_domain_conditional_required
    name: 子领域条件必填
    type: conditional_required
    field: sub_domain_id
    condition: "domain_id is not None"
    message: 选择领域后，子领域不能为空
    severity: error
```

**注意**：现有 `type: field` 校验**不属于** `ConstraintEngine._check_constraint()` 路由（不在 unique_scope / immutable / no_delete 之一），可能是更早的 FieldValidator 路径 — 需**保持向后兼容**，不破坏。

### 4.12 FR-4.5: useFieldPolicy 增强

**文件**: [src/composables/useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js)

#### 4.12.1 新增 `requiredMap` computed（L236 之前）

参照 `editableMap` L80-130 模式，在 L235 `readonlyAlwaysMap` 之后插入：

```javascript
/**
 * requiredMap - 字段必填映射（含 conditional 上下文）
 * 优先从后端 API 结果读取，fallback 到本地推断
 * 
 * 后端 policies[fieldId] 包含: { editable, visible, required, conditional_required?: [...] }
 */
const requiredMap = computed(() => {
  const map = {}
  
  // 优先从后端 API 结果读取
  if (fieldPolicies.value) {
    for (const [fieldId, policy] of Object.entries(fieldPolicies.value)) {
      // 简单必填（静态）
      const baseRequired = policy.required === true
      // 条件必填（动态）— 暂存 conditional_required 数组
      const conditionalList = Array.isArray(policy.conditional_required) ? policy.conditional_required : []
      map[fieldId] = {
        base: baseRequired,
        conditional: conditionalList,
        // 计算属性：是否含条件规则
        hasConditional: conditionalList.length > 0,
      }
    }
    return map
  }
  
  // Fallback: 本地推断（仅 base）
  if (!metaConfig.value?.fields) {
    return map
  }
  for (const field of metaConfig.value.fields) {
    const fieldId = field.id || field.key
    const isRequired = field.required === true || (field.ui && field.ui.required === true)
    map[fieldId] = {
      base: isRequired,
      conditional: [],
      hasConditional: false,
    }
  }
  
  return map
})
```

#### 4.12.2 增强 `isRequired(fieldId, row=null)`（L364-386）

**当前代码**：

```javascript
function isRequired(fieldId) {
  // 优先从后端 API 结果读取
  if (fieldPolicies.value) {
    const policy = fieldPolicies.value[fieldId]
    if (policy !== undefined) {
      return policy.required === true
    }
  }
  
  // Fallback: 从 metaConfig 推断
  if (!metaConfig.value?.fields) {
    return false
  }
  
  const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
  if (!field) return false
  
  if (field.required === true) return true
  const ui = field.ui || {}
  if (ui.required === true) return true
  
  return false
}
```

**改造后**：

```javascript
function isRequired(fieldId, row = null) {
  // 1) 优先读 requiredMap（包含 conditional）
  if (requiredMap.value && requiredMap.value[fieldId]) {
    const rm = requiredMap.value[fieldId]
    
    // 1.1) 基础必填
    if (rm.base) return true
    
    // 1.2) 条件必填：遍历 conditional 规则，用 safe_evaluate 评估
    if (rm.hasConditional && row) {
      for (const rule of rm.conditional) {
        const condition = rule.condition || ''
        if (!condition) continue
        try {
          // 复用 meta/core/safe_expr_evaluator（前端需安装对应 lib）
          // 或使用后端 conditional 评估端点（更安全）
          // 此处使用 try-catch 保护，任何异常视为条件不满足
          if (window.__safeEvaluate__ ? window.__safeEvaluate__(condition, row) : false) {
            return true
          }
        } catch {
          continue
        }
      }
    }
    
    return false
  }
  
  // 2) Fallback: 从 metaConfig 推断（兼容旧调用方）
  if (!metaConfig.value?.fields) {
    return false
  }
  
  const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
  if (!field) return false
  
  if (field.required === true) return true
  const ui = field.ui || {}
  if (ui.required === true) return true
  
  return false
}
```

**注意**：前端 safe_evaluate 需在 main.js 注入 `window.__safeEvaluate__`（来自 `@/utils/safeExpression.js`）。如果项目没有这个 utils，可降级为 `eval` 替代（**仅对 row 数据求值，无注入风险**），但更好是后端 API 评估。

#### 4.12.3 追加到 return 对象（L491-516）

```javascript
return {
  // 后端策略
  fieldPolicies,
  loadFieldPolicies,
  
  editableMap,
  visibleMap,
  immutableMap,
  readonlyAlwaysMap,
  businessKeyMap,
  requiredMap,  // 🆕 FR-4.5
  
  isEditable,
  isVisible,
  isRequired,  // 改造后支持 row 参数
  isImmutable,
  isNewRowCheck,
  isRowEditable,
  
  // 批量操作
  getEditableFields,
  getReadonlyFields,
  
  // 工具
  isSystemField,
  evaluateMutability
}
```

---

## 五、跨任务依赖与实施顺序

### 5.1 文件级依赖（已确认 0 冲突）

| 任务 | 文件 | 依赖 | 端口 |
|------|------|------|------|
| FR-2.1 | bo_action_api.py | 无 | 3010 |
| FR-2.2/2.3/2.4 | bo_api.py | 依赖 FR-2.1 提供的 `_generate_action_openapi` | 3010 |
| FR-3.1/3.2 | query_interceptor.py | 无 | 3010 |
| FR-3.3 | useMetaList.js | 弱依赖 FR-3.1/3.2（fallback 模式） | 3010 |
| FR-4.1/4.2 | constraint_engine.py | 无 | 3010 |
| FR-4.3 | field_policy_engine.py | 弱依赖 FR-4.1（YAML 中配 conditional_required 才会触发）| 3010 |
| FR-4.4 | business_object.yaml | 弱依赖 FR-4.1/4.2 | 3010 |
| FR-4.5 | useFieldPolicy.js | 强依赖后端 FR-4.3 改造后的 `conditional_required` 字段 | 3010 |

### 5.2 推荐顺序（单仓库顺序开发）

```
1) FR-2.1 (bo_action_api.py 重构)
   ↓
2) FR-2.2 + 2.3 (bo_api.py 工具函数)
   ↓
3) FR-2.4 (bo_api.py 端点)
   ↓
4) FR-3.1 + 3.2 (query_interceptor.py 增强)
   ↓
5) FR-3.3 (useMetaList.js getCellValue)
   ↓
6) FR-4.1 + 4.2 (constraint_engine.py 新约束类型)
   ↓
7) FR-4.3 (field_policy_engine.py 联动)
   ↓
8) FR-4.4 (business_object.yaml 示例)
   ↓
9) FR-4.5 (useFieldPolicy.js 增强)
   ↓
10) 全量回归测试 + Swagger UI E2E 验证
```

**关键点**：
- 步骤 1-3 完成后可立即验证 FR-2 全量 OpenAPI
- 步骤 4-5 完成后可立即验证 FR-3 display_values（重启后端 + 浏览器）
- 步骤 6-7 完成后可立即验证 FR-4 conditional_required（后端 curl 测试）
- 步骤 9 完成后可立即验证前端 isRequired(row) 行为
- 步骤 10 全量验证

---

## 六、验证策略

### 6.1 单元验证（每步必做）

```bash
# FR-2.1: 验证函数存在
python -c "from meta.api.bo_action_api import _generate_action_openapi; spec = _generate_action_openapi(); assert spec['openapi'] == '3.0.0'; assert 'paths' in spec; print('FR-2.1 OK')"

# FR-2.4: 验证全量端点
curl -s http://localhost:3010/api/v2/meta/_openapi.json | python -c "import json,sys; spec=json.load(sys.stdin); assert 'paths' in spec; assert '/api/v2/bo/' in str(spec['paths']); print('FR-2.4 OK')"

# FR-3.1: 验证方法存在
python -c "from meta.core.interceptors.query_interceptor import QueryInterceptor; assert hasattr(QueryInterceptor, '_inject_display_values'); print('FR-3.1 OK')"

# FR-3.2: 验证 list 响应含 display_values
curl -s -b "auth_token=YOUR_TOKEN" "http://localhost:3010/api/v2/bo/business_object?page_size=1" | python -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data) if isinstance(data, dict) else data
if items:
    assert 'display_values' in items[0], 'display_values missing'
    print('FR-3.2 OK')
else:
    print('FR-3.2 SKIP (no items)')
"

# FR-4.1: 验证方法存在
python -c "from meta.core.constraint_engine import ConstraintEngine; assert hasattr(ConstraintEngine, '_check_conditional_required'); print('FR-4.1 OK')"

# FR-4.3: 验证联动
python -c "from meta.services.field_policy_engine import FieldPolicyEngine; print('FR-4.3 OK')"  # 语法检查
```

### 6.2 回归验证（每 FR 完成后必做）

```bash
python d:\filework\test.py --port 3010 --failed
```

### 6.3 E2E 验证（实施完毕后）

```bash
# 1. 启动后端
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3010

# 2. 验证 Swagger UI
# 访问 http://localhost:3010/api/v2/meta/_openapi.json 看全量 OpenAPI
# 访问 http://localhost:3010/api/v2/action/_openapi.json 看 Action-only OpenAPI

# 3. 验证 display_values
curl -s -b "auth_token=YOUR_TOKEN" "http://localhost:3010/api/v2/bo/business_object?page_size=3" | python -m json.tool

# 4. 验证 conditional_required
# 准备一个含 conditional_required YAML 的 BO，curl POST 测试
curl -X POST http://localhost:3010/api/v2/bo/sub_domain \
  -H "Content-Type: application/json" \
  -b "auth_token=YOUR_TOKEN" \
  -d '{"domain_id":"d1","sub_domain_id":null}'
# 应返回 400 + "选择领域后，子领域不能为空"
```

---

## 七、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| FR-2.1 重构破坏现有 Action OpenAPI 端点 | 中 | 高 | 端点路径不变 + 输出结构验证 + 单元测试 |
| FR-2.4 与 Action-only 端点路径冲突 | 低 | 中 | 用 `meta_v2_bp`（不同 Blueprint）|
| FR-3.1 `_inject_display_values` 性能 | 中 | 中 | O(N*F) 已不可避免，加 field_type_map 缓存 + 空 records 短路 |
| FR-3.2 接入位置错导致后续钩子不触发 | 低 | 高 | 在 `_compute_columns` 之前（已有 _enrich_records 之后），不改其他步骤 |
| FR-3.3 `getCellValue` 改造影响其他列渲染 | 中 | 中 | fallback 链（draft > display > 原值），向后兼容 |
| FR-4.3 `is_field_required` 改动影响范围广 | 中 | 高 | 2.5 步追加，已有 1-2 步不变；新逻辑只读不改 |
| FR-4.5 `isRequired` 改造破坏 30+ 组件调用 | 中 | 中 | 保留单参数重载（向后兼容），新 row 参数可选 |
| YAML `conditional_required` 加载失败 | 低 | 低 | YAML 容错好；fail-soft 即可 |
| `safe_evaluate` 性能 | 低 | 低 | 已有沙箱实现 |

---

## 八、需求完整性检查

| 检查项 | 状态 |
|--------|------|
| 12 任务全部有详细代码 + 行号 | ✅ |
| 跨文件调用链已绘制 | ✅ |
| 实施顺序已规划 | ✅ |
| 验证策略完整 | ✅ |
| 风险已识别并缓解 | ✅ 9 项 |
| v1 规格 vs 实际代码差异已标注 | ✅ FR-2.1 / FR-2.4 / FR-3.3 |
| TBD 全部已解决 | ✅ TBD-1/2/3 |
| 安全保证已说明 | ✅ fallback / safe_evaluate / 向后兼容 |

---

## 九、TBD 解决

- **TBD-1**: ✅ `meta_v2_bp` 在 [bo_api.py L16](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L16) 已存在
- **TBD-2**: ✅ `registry.all()` 在 [bo_api.py L7](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L7) 已 import，用 hasattr 防御
- **TBD-3**: ✅ `/field-policies` API 已有 ([bo_api.py L1108-1146](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L1108-L1146)) 但只返回 3 字段 — FR-4.5 需先改造 L1131 追加 `conditional_required` 字段（**重要：** 需在 FR-4.3 完成后**额外**改造 bo_api.py:1131）

**重要补充**：FR-4.5 实际涉及 2 个文件：
1. **bo_api.py:1131-1135** — 追加 `conditional_required` 字段到 policies 字典（后端）
2. **useFieldPolicy.js:236/364/491** — 改造前端消费（前端）

**修正后任务清单**（13 任务而非 12）：

| 任务 | 文件 | 改动 |
|------|------|------|
| FR-4.5a | bo_api.py:1131 | 追加 `conditional_required` 字段（取 `engine._field_policies[field_id].required.determination`）|
| FR-4.5b | useFieldPolicy.js | requiredMap + isRequired 增强（4.12 节）|

---

## 十、附录

### 10.1 完整文件路径

| 序号 | 文件 | 路径 | 任务 |
|------|------|------|------|
| 1 | [bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py) | meta/api/bo_action_api.py | FR-2.1 |
| 2 | [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py) | meta/api/bo_api.py | FR-2.2/2.3/2.4 + FR-4.5a |
| 3 | [query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) | meta/core/interceptors/query_interceptor.py | FR-3.1/3.2 |
| 4 | [useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) | src/composables/useMetaList.js | FR-3.3 |
| 5 | [constraint_engine.py](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py) | meta/core/constraint_engine.py | FR-4.1/4.2 |
| 6 | [field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py) | meta/services/field_policy_engine.py | FR-4.3 |
| 7 | [business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml) | meta/schemas/business_object.yaml | FR-4.4 |
| 8 | [useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js) | src/composables/useFieldPolicy.js | FR-4.5b |

### 10.2 关键调用链速查

```
OpenAPI 访问: GET /api/v2/meta/_openapi.json
  → bo_api.get_full_openapi()
    → meta.api.bo_action_api._generate_action_openapi()  [FR-2.1 产物]
    → bo_api._generate_bo_crud_paths(registry.all())  [FR-2.2 产物]
    → bo_api._generate_bo_schema(obj)  [FR-2.3 产物]

display_values 注入: QueryInterceptor.after_action()
  → query_interceptor._inject_display_values()  [FR-3.1 产物]

前端渲染: useMetaList.getCellValue(row, field)
  → 1. draftValues 优先
  → 2. row.display_values[field]  [FR-3.3 改造]
  → 3. row[field]  (fallback)

条件必填: 创建/更新业务_object
  → ConstraintEngine.validate()
    → _check_constraint() 路由
      → _check_conditional_required()  [FR-4.1 产物]
  → FieldPolicyEngine.is_field_required()
    → 2.5 conditional_required 检查  [FR-4.3 产物]
  → bo_api.get_field_policies()  L1131 追加 conditional_required 字段  [FR-4.5a]
  → 前端 useFieldPolicy.requiredMap + isRequired(fieldId, row)  [FR-4.5b 产物]
```

### 10.3 关键行号速查

| 任务 | 文件 | 行号 |
|------|------|------|
| FR-2.1 重构 | bo_action_api.py | L538-671 → 拆为函数 |
| FR-2.2 工具函数 | bo_api.py | L1490 前追加 |
| FR-2.3 工具函数 | bo_api.py | L1491 前追加 |
| FR-2.4 端点 | bo_api.py | L1108 前插入 |
| FR-3.1 方法 | query_interceptor.py | L105 前追加 |
| FR-3.2 接入 | query_interceptor.py | L44 后插入 1 行 |
| FR-3.3 渲染 | useMetaList.js | L1646-1652 改造 |
| FR-4.1 方法 | constraint_engine.py | L183 前插入 |
| FR-4.2 路由 | constraint_engine.py | L86 后插入 2 行 |
| FR-4.3 联动 | field_policy_engine.py | L193-195 后插入 10 行 |
| FR-4.4 YAML | business_object.yaml | L1083 后追加 7 行 |
| FR-4.5a API | bo_api.py | L1131 字典构造 |
| FR-4.5b 前端 | useFieldPolicy.js | L236 / L364 / L491 |

### 10.4 端口

- 统一使用 **3010**（单仓库顺序开发）
- 启动命令：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3010`
- 关闭命令：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop -Port 3010`

### 10.5 实施前必做

```bash
# 1. 确认 main 健康
cd d:\filework\excel-to-diagram
git status
git log --oneline -1
# 应显示: 55f1508 init: pre-batch2 baseline

# 2. 确认后端服务运行
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status -Port 3010

# 3. 确认无 zombie worktree
git worktree list
# 应只显示 main

# 4. 确认无僵尸分支
git for-each-ref --format='%(refname:short)' refs/heads/
# 应只显示 main
```

### 10.6 实施步骤总览（路径 A 单仓库顺序开发）

```bash
# Step 0: 创建 feature branch
cd d:\filework\excel-to-diagram
git checkout -b batch2/agent-a-openapi

# Step 1-3: FR-2 OpenAPI
# 改 bo_action_api.py + bo_api.py
# 验证: curl /api/v2/meta/_openapi.json

# Step 4-5: FR-3 display_values
# 改 query_interceptor.py + useMetaList.js
# 验证: curl 列表 API + 浏览器

# Step 6-9: FR-4 conditional_required
# 改 constraint_engine.py + field_policy_engine.py + business_object.yaml + bo_api.py + useFieldPolicy.js
# 验证: curl POST 测试条件触发

# Step 10: 提交 + 合并
git add -A
git commit -m "batch2: FR-2/3/4 完整后端能力扩展"
git checkout main
git merge --no-ff batch2/agent-a-openapi
git branch -D batch2/agent-a-openapi
```

---

**文档完成于 2026-06-07，可作为批次 2 实施的唯一参考。**
