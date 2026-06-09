## 目录

1. [〇、变更摘要（vs v1 详细方案）](#〇-变更摘要（vs-v1-详细方案）)
2. [一、批次 2 整体进度](#一-批次-2-整体进度)
3. [二、Agent A 战报（FR-2 全部 + FR-4.5a）](#二-agent-a-战报（fr-2-全部-fr-45a）)
4. [三、待实施任务详细方案](#三-待实施任务详细方案)
5. [四、4 Agent 协调计划](#四-4-agent-协调计划)
6. [五、验证方案](#五-验证方案)
7. [六、风险评估](#六-风险评估)
8. [七、附录](#七-附录)

---
# 批次 2 详细实现方案 v2（基于实际代码现状 + 实施战报）

> **版本**: v2.0 | **日期**: 2026-06-07 | **状态**: 🟢 实施中
> **配套文档**:
> - [spec-pre-deployment-optimization.md (v1.1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) — v1 原始规格
> - [spec-batch2-backend-capabilities.md (v1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-backend-capabilities.md) — 概要设计
> - [spec-batch2-detailed-plan.md (v1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan.md) — 早期详细方案（保留作历史）
> - [batch2-agent-assignments.md](file:///d:/filework/excel-to-diagram/docs/specs/batch2-agent-assignments.md) — 多 Agent 协调手册

---

## 〇、变更摘要（vs v1 详细方案）

| 项 | v1 假设 | v2 实际 |
|---|---------|---------|
| FR-2.1 起点 | 无内联实现，需从零写 | **bo_action_api.py:538-671 已有 134 行内联实现**，v2 改为"提取为独立函数" |
| FR-2.4 端点路径 | 复用 bo_action_bp 加 method | **新建 `meta_v2_bp` blueprint 端点** `/api/v2/meta/_openapi.json` |
| FR-2.3 字段类型 | 假设 `field.type` str | **实际 `field.field_type` 是 FieldType enum**，需 `.value` |
| FR-2.3 UI 元数据 | 假设 `field.ui` 是 dict | **实际 `field.ui` 是 UIAnnotation 对象**（dataclass）|
| FR-2.3 enum_values | 假设元素是 dict | **实际可能是 str 或 dict**（需兼容）|
| FR-3.3 改造点 | loadList 阶段 | **`getCellValue()` 函数**（useMetaList.js:1646）优先读 display_values |
| FR-4.5a 实施 | 推迟到 FR-4.5 一起做 | **Agent A 顺手先做**（与 FR-2.4 同一文件，便利）|

---

## 一、批次 2 整体进度

### 1.1 任务状态总览

| 任务 | 标题 | 状态 | 代码进度 | 验证状态 | Agent |
|------|------|------|---------|---------|-------|
| FR-2.1 | 提取 Action OpenAPI 生成函数 | 🟡 代码完成 | 100% | ⏳ 端点 200 OK ✅ / 待跑回归 | A |
| FR-2.2 | 新增 BO CRUD paths 生成 | 🟡 代码完成 | 100% | ⏳ 端点 500（剩 1 bug） | A |
| FR-2.3 | MetaObject → JSON Schema 转换 | 🟡 代码完成 | 100% | ⏳ 端点 500（同上） | A |
| FR-2.4 | 全量 OpenAPI 端点 | 🟡 代码完成 | 100% | ⏳ 端点 500（修中） | A |
| FR-4.5a | API 响应追加 conditional_required | 🟡 代码完成 | 100% | ⏳ 待跑回归 | A |
| FR-3.1 | 新增 `_inject_display_values()` | ⏳ 未开始 | 0% | — | B |
| FR-3.2 | 接入 after_action 流程 | ⏳ 未开始 | 0% | — | B |
| FR-3.3 | 前端读 display_values | ⏳ 未开始 | 0% | — | C |
| FR-4.1 | ConstraintEngine 新增 `_check_conditional_required()` | ⏳ 未开始 | 0% | — | D |
| FR-4.2 | 路由到新方法 | ⏳ 未开始 | 0% | — | D |
| FR-4.3 | FieldPolicyEngine 联动 | ⏳ 未开始 | 0% | — | D |
| FR-4.4 | YAML 示例 | ⏳ 未开始 | 0% | — | D |
| FR-4.5 | 前端读 conditional_required | ⏳ 未开始 | 0% | — | C |

**统计**：13 子任务，已写代码 5（38%），未开始 8（62%）。

### 1.2 分支状态

| 分支 | 状态 | 提交 | 备注 |
|------|------|------|------|
| `main` | 稳定 | — | 批次 1 已合并 |
| `batch2/agent-a-openapi` | 🟡 已创建 0 commit | 0 | 5 任务代码已就绪，待 500 修复后提交 |

---

## 二、Agent A 战报（FR-2 全部 + FR-4.5a）

### 2.1 已完成代码清单

| 文件 | 改动 | 行号 | 内容 |
|------|------|------|------|
| `meta/api/bo_action_api.py` | FR-2.1 | L538-665 | 新增 `_generate_action_openapi(base_url)` 函数（128 行） |
| `meta/api/bo_action_api.py` | FR-2.1 | L668-680 | 端点 `openapi_spec()` 简化为 4 行（调函数） |
| `meta/api/bo_api.py` | FR-2.4 | L1112-1156 | 新增 `get_full_openapi()` 端点（45 行，含 try/except） |
| `meta/api/bo_api.py` | FR-4.5a | L1180-1211 | `get_field_policies` 字典追加 `conditional_required` 字段 |
| `meta/api/bo_api.py` | FR-2.2/2.3 | L1870-2030 | 新增 4 个工具函数（160 行）：`_TYPE_MAP` / `_map_field_type` / `_generate_bo_schema` / `_generate_bo_crud_paths` |

### 2.2 调试战报：4 个连续 Bug + 修复方法

| # | 错误信息 | 根本原因 | 修复方法 | 状态 |
|---|---------|---------|---------|------|
| 1 | `SyntaxError: expected 'except' or 'finally' block` at L1566 | 用 Edit 工具以 `# 按 BO 分组...` 为锚点插入 166 行新代码，**但锚点实际位于 L1729（在 try 块内，缩进 12 空格）**，新代码缩进 0 空格，破坏 try 块结构 | Python 脚本删除 L1562-1724 错误插入（`lines[:1561] + lines[1724:]`），用 L1856 唯一锚点重新追加到文件末尾顶层位置 | ✅ 已修复 |
| 2 | `AttributeError: 'MetaField' object has no attribute 'type'` | v1 假设 `field.type` 是 str，**实际 MetaField 用 `field_type: FieldType`（enum）** | `field_type = getattr(field, 'field_type', None) or getattr(field, 'type', None)` + `_map_field_type` 加 `if hasattr(field_type, 'value'): field_type = field_type.value` | ✅ 已修复 |
| 3 | `AttributeError: 'UIAnnotation' object has no attribute 'get'` | v1 假设 `field.ui` 是 dict，**实际 `field.ui` 是 UIAnnotation 对象（dataclass）**，没有 `.get()` 方法 | `isinstance(ui, dict) ? ui.get('relation') : getattr(ui, 'relation', None)` | ✅ 已修复 |
| 4 | `AttributeError: 'str' object has no attribute 'get'` at L1904 | v1 假设 `field.enum_values` 元素都是 `Dict[str, Any]`，**实际可能是 str** | **待修复**：见 §2.3 | ❌ 待修复 |

### 2.3 待修复 Bug #4 修复方案

**位置**：`d:\filework\excel-to-diagram\meta\api\bo_api.py` L1904

**当前代码**（有 bug）：
```python
if getattr(field, 'enum_values', None):
    prop["enum"] = [v.get('value') for v in field.enum_values]  # BUG
```

**修复后代码**（兼容 str 和 dict）：
```python
if getattr(field, 'enum_values', None):
    enum_list = []
    for v in field.enum_values:
        if isinstance(v, dict):
            enum_list.append(v.get('value'))
        else:
            enum_list.append(v)  # 兼容 str
    if enum_list:
        prop["enum"] = enum_list
```

**修复后剩余验证步骤**：
1. 杀掉 backend PID 6748（`Stop-Process -Id 6748 -Force` 或 taskkill）
2. 清 `__pycache__/bo_api.cpython-314.pyc`
3. 重启 backend：`Start-Process python waitress_server.py -RedirectStandardOutput logs/server.out.log`
4. curl 验证：
   - `curl.exe http://localhost:3010/api/v2/action/_openapi.json` → 200 OK
   - `curl.exe http://localhost:3010/api/v2/meta/_openapi.json` → 200 OK
5. 跑 `python d:\filework\test.py --port 3010 --failed` 回归
6. `git add` + `commit` + `merge main` + `delete branch`

### 2.4 关键发现（实施经验教训）

1. **元数据 dataclass 假设陷阱**：v1 规格基于"通用"模型写代码，但实际项目用 dataclass + FieldType enum，所有 `.type` 都得改 `.field_type`、所有 `ui.get()` 都得改 `getattr(ui, ...)`。**v1 规格偏差是实施最大阻力**。
2. **Edit 工具缩进陷阱**：用锚点插入大段代码时，**必须用 Read 工具确认锚点缩进**，不能假设顶层缩进。安全做法：永远用文件末尾的顶层函数（不在 try/while 内）作为锚点。
3. **多形态数据防御**：`_generate_bo_schema` 必须用 `getattr + isinstance` 双保险处理 `ui`（dict 或 dataclass）和 `enum_values`（list of dict or str）。**v1 规格没考虑这点**。
4. **Blueprint 复用陷阱**：`@meta_v2_bp.route('/_openapi.json')` 路径与 `@bo_action_bp.route('/_openapi.json')` 路径不同（前者 `/api/v2/meta/_openapi.json`，后者 `/api/v2/action/_openapi.json`），**两个端点都需保留**（Action-only 端点兼容老调用方）。

---

## 三、待实施任务详细方案

### 3.1 Agent B 工作量：FR-3 display_values（3 任务）

#### FR-3.1 新增 `_inject_display_values()`

**目标**：在 `QueryInterceptor.after_action()` 后给每条 record 追加 `display_values` 字段。

**文件**：`d:\filework\excel-to-diagram\meta\core\interceptors\query_interceptor.py`

**现状代码**（L35-50）：
```python
def after_action(self, context: 'ActionContext') -> None:
    if not context.result or not context.result.success:
        return
    if context.is_query_action:
        items = self._extract_items(context)
        if not items:
            return
        self._inject_type_tag(context, items)   # 步骤 1
        self._enrich_records(context, items)    # 步骤 2
        self._compute_columns(context, items)   # 步骤 3
        self._check_can_delete(context, items)  # 步骤 4
```

**目标代码**（FR-3.1 + FR-3.2 合并）：
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
        self._inject_display_values(context, items)  # 🆕 FR-3.1: 新增
        self._compute_columns(context, items)
        self._check_can_delete(context, items)
    # ... (crud_update/crud_create 块不变)

def _inject_display_values(self, context: 'ActionContext', items: list) -> None:
    """🆕 v1 批次 2 / FR-3.1: 为每条记录追加 display_values 字段
    
    规则:
    - FK 字段 → 关联对象的 display_field 值（通过 enrichment_engine）
    - enum 字段 → 枚举标签（metaObj.fields[].enum_values 中 label/value）
    - boolean 字段 → 是/否 标签
    - date/datetime → 格式化字符串
    """
    object_type = context.object_type
    try:
        from meta.core.models import registry
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return
    except Exception:
        return
    
    # 1. 收集需要处理的字段（按类型分类）
    fk_fields = []   # relation 类型
    enum_fields = []  # 有 enum_values
    bool_fields = []  # field_type == BOOLEAN
    date_fields = []  # field_type in (DATE, DATETIME)
    
    for field in meta_obj.fields:
        ui = getattr(field, 'ui', None)
        relation = None
        if isinstance(ui, dict):
            relation = ui.get('relation')
        else:
            relation = getattr(ui, 'relation', None) if ui else None
        
        if relation:
            fk_fields.append((field.id, relation, display_field))
        elif getattr(field, 'enum_values', None):
            enum_fields.append(field)
        elif field.field_type and field.field_type.name in ('BOOLEAN',):
            bool_fields.append(field.id)
        elif field.field_type and field.field_type.name in ('DATE', 'DATETIME'):
            date_fields.append(field.id)
    
    for item in items:
        if not isinstance(item, dict):
            continue
        display_values = item.get('display_values', {})
        
        # FK: 直接用 enrichment 阶段的虚拟字段（field_id_display）
        for field_id, relation, display_field in fk_fields:
            virtual_key = f'{field_id}_display'
            if virtual_key in item:
                display_values[field_id] = item[virtual_key]
        
        # enum: 查 enum_values
        for field in enum_fields:
            value = item.get(field.id)
            if value is None:
                continue
            for ev in field.enum_values:
                if isinstance(ev, dict) and ev.get('value') == value:
                    display_values[field.id] = ev.get('label', str(value))
                    break
                elif ev == value:
                    display_values[field.id] = str(value)
                    break
        
        # boolean
        for fid in bool_fields:
            v = item.get(fid)
            if v is None:
                continue
            display_values[fid] = '是' if v else '否'
        
        # date
        for fid in date_fields:
            v = item.get(fid)
            if v is None:
                continue
            display_values[fid] = str(v)[:10] if 'DATE' in str(field.field_type) else str(v)[:19]
        
        if display_values:
            item['display_values'] = display_values
```

**关键设计决策**：
- **FK 直接复用 enrichment 引擎**：`enrich_records` 已生成 `<field>_display` 虚拟字段，**FR-3.1 不应重复造轮子**
- **enum 多形态兼容**：用 `isinstance(ev, dict)` 防御（与 §2.3 修复方法一致）
- **try/except 容错**：缺 meta_obj 时静默跳过，不影响主流程

#### FR-3.2 接入 after_action 流程

**内容**：在 `QueryInterceptor.after_action()` 中 `_enrich_records` 之后、`_compute_columns` 之前调用 `self._inject_display_values(context, items)`（见上 §3.1 目标代码）。

**关键约束**：
- 必须在 `_enrich_records` **之后**调用（依赖 `<field>_display` 虚拟字段）
- 必须在 `_compute_columns` **之前**调用（计算列可能引用 display_values，但应保持拦截器单向依赖链）
- 不影响 `crud_update` / `crud_create` 分支（创建后单条不需要 display_values）

#### FR-3.3 前端读 display_values

**文件**：`d:\filework\excel-to-diagram\src\composables\useMetaList.js`

**现状**（L1646-1652）：
```javascript
function getCellValue(row, fieldName) {
  // 优先读 draftValues（编辑模式）
  if (draftValues.value[row.id] && draftValues.value[row.id][fieldName] !== undefined) {
    return draftValues.value[row.id][fieldName]
  }
  return row[fieldName] || ''
}
```

**目标代码**：
```javascript
function getCellValue(row, fieldName) {
  // 🆕 v1 批次 2 / FR-3.3: 优先读 display_values（后端预格式化）
  if (row?.display_values?.[fieldName] !== undefined) {
    // 编辑模式优先 draftValues（防止覆盖用户输入）
    if (draftValues.value[row.id]?.[fieldName] !== undefined) {
      return draftValues.value[row.id][fieldName]
    }
    return row.display_values[fieldName]
  }
  // 兼容：编辑模式 draftValues
  if (draftValues.value[row.id]?.[fieldName] !== undefined) {
    return draftValues.value[row.id][fieldName]
  }
  return row[fieldName] || ''
}
```

**关键设计决策**：
- **`display_values` 优先于 `row[fieldName]`**：后端格式化是单一可信源
- **编辑模式 draftValues 优先于 display_values**：用户在编辑时输入的原始值必须保留
- **向后兼容**：display_values 缺失时退回旧逻辑

---

### 3.2 Agent C 工作量：前端适配（2 任务）

#### FR-3.3 详细方案

见 §3.1 Agent B 的 FR-3.3（**实际由 Agent C 实施**，因为是前端代码）。

#### FR-4.5 详细方案

**目标**：`useFieldPolicy.js` 读 `fieldPolicies[id].conditional_required` 数组，构造 `requiredMap` 供 UI 表单动态校验。

**文件**：`d:\filework\excel-to-diagram\src\composables\useFieldPolicy.js`

**现状**（L122-128 `loadFieldPolicies`）：
```javascript
async function loadFieldPolicies(objectType, context = 'read', mutability = null) {
  const response = await api.get(`/api/v2/meta/${objectType}/field-policies`, {
    params: { context, mutability }
  })
  if (response.success) {
    fieldPolicies.value = response.data  // {field_id: {editable, visible, required}}
    return response.data
  }
}
```

**目标代码**（追加 requiredMap 状态）：
```javascript
// 状态
const fieldPolicies = ref({})          // 已有
const requiredMap = ref({})            // 🆕 FR-4.5: {field_id: [{condition, message, severity}]}
const conditionalErrors = ref({})      // 🆕 FR-4.5: {field_id: 'message'}

async function loadFieldPolicies(objectType, context = 'read', mutability = null) {
  const response = await api.get(`/api/v2/meta/${objectType}/field-policies`, {
    params: { context, mutability }
  })
  if (response.success) {
    fieldPolicies.value = response.data
    
    // 🆕 FR-4.5: 提取 conditional_required 到 requiredMap
    const newRequiredMap = {}
    for (const [fieldId, policy] of Object.entries(response.data)) {
      if (policy.conditional_required && policy.conditional_required.length > 0) {
        newRequiredMap[fieldId] = policy.conditional_required
      }
    }
    requiredMap.value = newRequiredMap
    return response.data
  }
}

// 🆕 FR-4.5: 评估条件必填
function evaluateConditionalRequired(formData) {
  const newErrors = {}
  for (const [fieldId, rules] of Object.entries(requiredMap.value)) {
    for (const rule of rules) {
      try {
        // 用安全表达式求值（与后端 safe_evaluate 保持一致）
        const conditionMet = evaluateExpression(rule.condition, formData)
        if (conditionMet && !formData[fieldId]) {
          newErrors[fieldId] = rule.message
          break  // 一条规则触发就足够
        }
      } catch (e) {
        console.warn(`[useFieldPolicy] condition eval error for ${fieldId}:`, e)
      }
    }
  }
  conditionalErrors.value = newErrors
  return Object.keys(newErrors).length === 0
}

// 安全的表达式求值（沙箱）
function evaluateExpression(expr, data) {
  // 简单实现：支持 === !== && || > < 基础运算符
  // 复杂场景用 new Function() 沙箱（生产环境应限制）
  const safeGlobals = { undefined, null, true, false, NaN, Infinity }
  const fn = new Function('data', `
    with (data) {
      return (${expr})
    }
  `)
  return Boolean(fn({ ...safeGlobals, ...data }))
}
```

**关键设计决策**：
- **后端是 source of truth**：API 返回 `conditional_required` 数组，前端不解析 YAML
- **客户端二次校验**（非权威）：用户提交前检查，作为 UX 增强；后端 ConstraintEngine 是最终防线
- **沙箱表达式**：前端用 `new Function + with` 简单沙箱，复杂场景用 JEXL/Vuelti 库

---

### 3.3 Agent D 工作量：FR-4 conditional_required 后端（4 任务）

#### FR-4.1 ConstraintEngine 新增 `_check_conditional_required()`

**文件**：`d:\filework\excel-to-diagram\meta\core\constraint_engine.py`

**新增方法**（追加到 ConstraintEngine 类）：
```python
def _check_conditional_required(
    self, context: ActionContext, field, constraint: Dict
) -> Optional[ConstraintViolation]:
    """🆕 v1 批次 2 / FR-4.1: 条件必填校验
    
    YAML 示例:
    ```yaml
    fields:
      - id: sub_domain_id
        constraints:
          - type: conditional_required
            condition: "value is not None"  # 当主领域已选时，子领域必填
            message: "选择领域后，子领域必填"
            severity: error
    ```
    
    Args:
        context: ActionContext（含 params + old_data）
        field: 字段定义
        constraint: 约束声明 dict
    
    Returns:
        ConstraintViolation or None
    """
    # 仅在 create/update 时校验（read 不需要）
    if not (context.is_create_action or context.is_update_action):
        return None
    
    field_id = field.id if isinstance(field.id, str) else str(field.id)
    new_value = context.params.get(field_id)
    
    # 已有值：跳过（已被填了）
    if new_value is not None and new_value != '':
        return None
    
    # 评估条件
    condition = constraint.get('condition', '')
    if not condition:
        return None
    
    # 构造求值上下文
    eval_data = {
        'value': new_value,
        'old_value': context.old_data.get(field_id) if context.old_data else None,
        'params': dict(context.params),  # 整行数据
        'old_data': dict(context.old_data) if context.old_data else {},
        'True': True,
        'False': False,
        'None': None,
    }
    
    try:
        condition_met = safe_evaluate(condition, eval_data)
    except Exception as e:
        logger.warning(f"[ConstraintEngine] conditional_required condition error: {e}")
        return None
    
    if not condition_met:
        return None
    
    # 条件满足但字段为空 → 违反
    return ConstraintViolation(
        field_id=field_id,
        message=constraint.get('message', f'{field.name}为条件必填字段'),
        constraint_type='conditional_required',
    )
```

#### FR-4.2 路由到新方法

**修改**（`constraint_engine.py` L72-88 `_check_constraint`）：
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
    elif constraint_type == 'conditional_required':  # 🆕 FR-4.2
        return self._check_conditional_required(context, field, constraint)
    
    return None
```

#### FR-4.3 FieldPolicyEngine 联动

**目标**：`is_field_required()` 中检查 constraints 是否有 `conditional_required` 类型，如有则加入判定。

**文件**：`d:\filework\excel-to-diagram\meta\services\field_policy_engine.py`

**修改**（L182-197 `is_field_required`）：
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
            if self._evaluate_required_policy(policy.required, context):
                return True
    
    field_def = self._get_field(field_id)
    if field_def:
        # 静态 required（已实现）
        if self._is_field_required_by_definition(field_def):
            return True
        # 🆕 FR-4.3: 条件必填（如果存在 conditional_required 规则，标记为"可能必填"）
        constraints = getattr(field_def, 'constraints', None)
        if constraints and self._has_conditional_required(constraints):
            # 实际值由前端/后端 ConstraintEngine 评估
            # 此处返回 True（保守策略：UI 显示星号）
            return True
    
    return False

@staticmethod
def _has_conditional_required(constraints) -> bool:
    """检查 constraints 是否声明了 conditional_required"""
    if isinstance(constraints, list):
        return any(
            isinstance(c, dict) and c.get('type') == 'conditional_required'
            for c in constraints
        )
    if isinstance(constraints, dict):
        return constraints.get('type') == 'conditional_required'
    return False
```

**关键设计决策**：
- **保守策略**：UI 端只要有 conditional_required 规则就显示星号，**实际校验由后端 ConstraintEngine 兜底**
- **避免双重评估**：前端 `evaluateConditionalRequired` 做 UX 提示，后端是权威

#### FR-4.4 YAML 示例

**文件**：`d:\filework\excel-to-diagram\meta\schemas\business_object.yaml`

**追加示例**（在 `examples:` 段）：
```yaml
examples:
  # ... 已有示例
  - id: conditional_required_demo
    description: "领域-子领域条件必填示例"
    fields:
      - id: name
        type: string
        required: true
      - id: domain_id
        type: string
        required: true
      - id: sub_domain_id
        type: string
        constraints:
          - type: conditional_required
            condition: "value.get('domain_id') is not None"
            message: "选择领域后，子领域必填"
            severity: error
          - type: conditional_required
            condition: "value.get('domain_id') == 'finance'"
            message: "财务领域必须选择子领域"
            severity: error
```

---

## 四、4 Agent 协调计划

### 4.1 已落地 Agent A 的合并路径

**前置条件**：
1. 修复 §2.3 bug #4（`field.enum_values` 兼容 str）
2. 端点返回 200 OK（Action-only + Full）
3. `python d:\filework\test.py --port 3010 --failed` 通过

**执行步骤**：
```bash
# 在 d:\filework\excel-to-diagram
git status                            # 确认 5 文件改动
git add meta/api/bo_action_api.py meta/api/bo_api.py
git commit -m "feat(batch2-agentA): FR-2 全量 OpenAPI + FR-4.5a conditional_required

- FR-2.1: 提取 _generate_action_openapi() 独立函数
- FR-2.2/2.3: 新增 _generate_bo_crud_paths / _generate_bo_schema / _map_field_type
- FR-2.4: 新增 /api/v2/meta/_openapi.json 全量端点
- FR-4.5a: get_field_policies API 响应追加 conditional_required 字段

🤖 Generated with Trae AI
Co-Authored-By: Trae <noreply@trae.ai>"

git checkout main
git merge --no-ff batch2/agent-a-openapi
git branch -d batch2/agent-a-openapi
```

### 4.2 Agent B 启动顺序（FR-3 后端）

**前置**：
- Agent A 已合并（无冲突代码）
- 端口 3010 backend 正在跑

**Agent B 提示词模板**：
```text
你是 Agent B，负责批次 2 FR-3 后端实现。

## 范围（3 任务，全部在 d:\filework\excel-to-diagram\）
- FR-3.1: meta/core/interceptors/query_interceptor.py 新增 _inject_display_values()
- FR-3.2: query_interceptor.py after_action 调用 _inject_display_values
- FR-3.3: src/composables/useMetaList.js:1646 getCellValue 读 display_values

## 详细方案（必读）
docs/specs/spec-batch2-detailed-plan-v2.md §3.1

## 实施步骤
1. cd d:\filework\excel-to-diagram
2. git checkout -b batch2/agent-b-display-values
3. 按 §3.1 实施
4. 跑 python d:\filework\test.py --port 3010 --failed
5. curl 验证 GET /api/v2/bo/user?page=1 → 检查 response.items[0].display_values
6. git add + commit + merge main

## 关键约束
- 不改 FR-2 已合并代码
- FR-3.1 必须兼容 str 和 dict 两种 enum_values 元素（参考 §2.3 bug #4 修复方法）
- FR-3.3 是前端代码，注意 src/composables/ 目录

## 报告
完成后报告：分支名、commit hash、test.py 输出、curl 输出
```

### 4.3 Agent C 启动顺序（前端 FR-3.3 + FR-4.5）

**前置**：
- Agent B 已合并（FR-3.3 依赖后端 display_values）

**注意**：FR-3.3 实际在 `useMetaList.js`（前端），由 Agent C 实施更合理。Agent B 提示词中已将 FR-3.3 标为"前端代码"，让 Agent B 只做后端、Agent C 接手前端。

### 4.4 Agent D 启动顺序（FR-4 后端）

**前置**：
- Agent A 已合并（FR-4.5a 字段已加）
- 无需依赖 Agent B/C

**Agent D 可独立启动**（4 任务全部在约束引擎 + 策略引擎 + YAML）。

### 4.5 合并冲突矩阵

| 合并路径 | 冲突文件 | 冲突原因 | 解决方案 |
|---------|---------|---------|---------|
| Agent A → main | 无 | — | 直接 merge |
| Agent B → main | `meta/core/interceptors/query_interceptor.py` | 唯一改动文件 | 直接 merge |
| Agent C → main | `src/composables/useMetaList.js` + `useFieldPolicy.js` | 2 独立文件 | 直接 merge |
| Agent D → main | `meta/core/constraint_engine.py` + `field_policy_engine.py` + `business_object.yaml` | 3 独立文件 | 直接 merge |
| Agent B → Agent C | 无 | 不同文件 | 串行 merge |
| Agent A → Agent D | `meta/api/bo_api.py`（FR-4.5a 字段）| 同一文件 | 协调：Agent D 严禁碰 bo_api.py |

---

## 五、验证方案

### 5.1 单元级验证（每任务完成必跑）

```bash
# 1. Python 语法 / import
cd d:\filework\excel-to-diagram
python -c "from meta.api import bo_api, bo_action_api; print('OK')"

# 2. 端点 smoke test
curl.exe http://localhost:3010/api/v2/action/_openapi.json | python -m json.tool | head -20
curl.exe http://localhost:3010/api/v2/meta/_openapi.json | python -m json.tool | head -20
curl.exe http://localhost:3010/api/v2/meta/user/field-policies | python -m json.tool | head -20

# 3. 列表响应含 display_values
curl.exe -b "auth_token=xxx" "http://localhost:3010/api/v2/bo/user?page=1&page_size=2" | python -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('items', []):
    print('id:', item.get('id'), 'display_values:', list((item.get('display_values') or {}).keys()))
"
```

### 5.2 回归测试

```bash
# 全量回归（Agent A/B/C/D 完成后跑）
python d:\filework\test.py --port 3010 --all
# 有假失败再跑串行
python d:\filework\test.py --port 3010 --failed
```

### 5.3 E2E 验证（FR-3 重点）

```bash
# 启动 frontend
cd d:\filework\excel-to-diagram
npm run dev:frontend  # 或 service_manager.ps1 start frontend

# 浏览器手工验证
# 1. 打开 http://localhost:5173/user
# 2. 检查列表中 FK 字段（如 role_name）显示的是关联对象的 display_name，不是 ID
# 3. 检查 boolean 字段显示"是/否"
# 4. 检查 enum 字段显示 label（如 status="active" 显示"活跃"）
```

### 5.4 FR-4 E2E 验证

```bash
# 1. 在 business_object.yaml 加 conditional_required_demo 对象
# 2. 创建测试数据：domain_id=finance, sub_domain_id=空 → 应报错
# 3. 用 Postman 调用 POST /api/v2/bo/conditional_required_demo，验证 400 错误
# 4. 浏览器打开表单页面，检查 UI 显示星号
# 5. 提交表单，验证前端 + 后端双重校验
```

---

## 六、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **dataclass vs dict 假设不匹配** | 实施中频繁踩坑 | §2.3 已总结：永远用 `getattr + isinstance` 防御 |
| **前端 `new Function` 沙箱** | 表达式注入 | 生产环境用 JEXL 库；MVP 用基础白名单 |
| **enrichment_engine 不生成 `<field>_display`** | FR-3.1 FK 字段无值 | 实施时 grep 确认 enrichment_engine 输出；缺失则补 |
| **ConstraintEngine 串行校验开销** | 大表单性能 | FR-4.1 用 `safe_evaluate` 缓存表达式编译结果 |
| **多 Agent 端口冲突** | 测试假失败 | D.7 规范：每 Agent 用独立端口（3010-3019）+ per-port DB snapshot |

---

## 七、附录

### 7.1 完整文件改动清单

| 文件 | 任务 | 改动类型 | 行数 |
|------|------|---------|------|
| `meta/api/bo_action_api.py` | FR-2.1 | 提取函数 + 简化端点 | +130 -8 = +122 |
| `meta/api/bo_api.py` | FR-2.2/2.3/2.4/4.5a | 新增端点 + 工具函数 + 字典字段 | +165 |
| `meta/core/interceptors/query_interceptor.py` | FR-3.1/3.2 | 新增方法 + 调用 | +60 |
| `src/composables/useMetaList.js` | FR-3.3 | 修改 getCellValue | +10 -3 = +7 |
| `src/composables/useFieldPolicy.js` | FR-4.5 | 新增 requiredMap + evaluateConditionalRequired | +50 |
| `meta/core/constraint_engine.py` | FR-4.1/4.2 | 新增方法 + 路由 | +50 -2 = +48 |
| `meta/services/field_policy_engine.py` | FR-4.3 | 修改 is_field_required + 新增辅助方法 | +18 -1 = +17 |
| `meta/schemas/business_object.yaml` | FR-4.4 | 追加示例 | +20 |
| **总计** | **13 任务** | **8 文件** | **+519 行** |

### 7.2 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-07 上午 | 批次 1 收尾，更新 v1 规格 |
| 2026-06-07 中午 | 生成 v1 详细方案 + Agent 协调手册 |
| 2026-06-07 下午 | Agent A 实施 FR-2 全部 4 任务 + FR-4.5a，4 bug 中已修 3 |
| 2026-06-07 傍晚 | Agent A 端点 200 OK、回归通过、commit + merge（目标）|
| 2026-06-08 | Agent B/C/D 并行启动 |
| 2026-06-09 | 批次 2 全部完成，回归 + E2E |

### 7.3 后续批次衔接

- **批次 3（v1 剩余）**：FR-6 UI 完整适配（详情页、抽屉、对话框）
- **批次 4（v2 引入）**：GraphQL 协议层（v1 规规格外）
- **批次 5（v2 引入）**：OpenTelemetry 全链路追踪
