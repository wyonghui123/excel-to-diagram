# FieldPolicyEngine: 统一字段策略引擎重构方案

## Why

当前系统存在以下问题：

1. **editable determination 逻辑分散**：`isCellEditable()` 在前端硬编码，后端 view\_config\_service.py 也有独立逻辑，系统字段判断在多处重复
2. **模块 4 的 mutability 逻辑不可复用**：枚举类型的 `locked/fully_editable/extensible` 逻辑硬编码在 enum\_api.py 中，其他对象无法复用
3. **Action vs CRUD 关系在 view\_config\_service 混在一起**：导入/导出按钮的显示逻辑与列配置 enrichment 混在一个函数中
4. **缺乏统一的字段策略机制**：无法声明式地定义字段在什么情况下可编辑/可见/必填

**机会**：提取统一的 FieldPolicy 引擎，将 determination 规则声明式化，实现完全元数据驱动。

## What Changes

### 核心变更

1. **创建 FieldPolicyEngine（后端）**

   * 统一的字段策略引擎

   * 支持 determination 规则声明

   * 上下文因素自动收集

2. **创建 useFieldPolicy（前端）**

   * 统一的字段策略 Hook

   * 与后端规则一致

   * 支持动态响应

3. **重构 view\_config\_service.py**

   * 拆分 `_merge_default_actions()` 和 `_enrich_columns()`

   * 将 Action vs CRUD 逻辑提取为独立模块

4. **扩展 YAML Schema**

   * 新增 `field_policy` 声明结构

   * 支持 `when/then` 条件规则

### 架构分层（重构后）

```
┌─────────────────────────────────────────────────────────────────┐
│                    目标架构分层                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 5: 页面组件（MetaListPage / ObjectPage）                  │
│            ↓                                                     │
│  Layer 4: useFieldPolicy() ← 统一字段策略 Hook                 │
│            ↓                                                     │
│  Layer 3: FieldPolicyEngine ← 策略引擎                        │
│            ├─ DeterminationRules ← 规则定义                        │
│            ├─ ContextFactors ← 上下文因素                        │
│            └─ PolicyEvaluator ← 规则求值                         │
│            ↓                                                     │
│  Layer 2: view_config_service.py                                │
│            ├─ ActionPolicy ← Action vs CRUD 关系                 │
│            └─ ColumnEnrichment ← 列配置丰富                       │
│            ↓                                                     │
│  Layer 1: YAML 元数据                                          │
│            ├─ semantics.field_policy ← 策略声明                   │
│            ├─ semantics.mutability ← 枚举特有逻辑（可复用）        │
│            └─ ui.editable ← 显式配置                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Impact

### Affected specs

* Phase 17: Inline Edit（依赖 FieldPolicyEngine）

* Phase 9: 通用能力模型（Action vs CRUD 逻辑重构）

* Phase 13: DisplayName（使用 FieldPolicyEngine）

### Affected code

* `meta/services/field_policy_engine.py` ← 新建

* `meta/services/view_config_service.py` ← 重构

* `src/composables/useFieldPolicy.js` ← 新建

* `src/composables/useMetaList.js` ← 简化

* `meta/core/models.py` ← 新增 FieldPolicy dataclass

***

## ADDED Requirements

### Requirement: FieldPolicyEngine 后端策略引擎

系统 SHALL 提供统一的字段策略引擎，支持以下功能：

#### Capability: 策略声明解析

* 从 YAML `field.semantics.field_policy` 解析策略声明

* 支持 `determination` 规则列表

* 支持 `when` 条件表达式和 `value` 结果值

#### Capability: 上下文因素收集

* 自动收集行级别因素：`is_new`, `is_system`, `created_at`

* 自动收集对象级别因素：`mutability`, `type`

* 自动收集用户级别因素：`roles`, `permissions`

* 自动收集操作级别因素：`action` (create/update/read)

#### Capability: 策略求值

* 按优先级顺序评估规则

* 支持 `default` 兜底值

* 支持表达式求值（安全的 sandbox 环境）

#### Scenario: 枚举字段 editable determination

* **WHEN** 枚举类型的 `mutability` 为 `locked`

* **THEN** 所有字段的 `editable` 返回 `false`

* **WHEN** 枚举类型的 `mutability` 为 `extensible` 且字段 `is_system` 为 `true`

* **THEN** 该字段的 `editable` 返回 `false`

* **WHEN** 枚举类型的 `mutability` 为 `extensible` 且字段 `is_system` 为 `false`

* **THEN** 该字段的 `editable` 返回 `true`

#### Scenario: 新行 editable determination

* **WHEN** 行是新增行（id 以 `__new_` 开头）

* **THEN** 所有非系统字段的 `editable` 返回 `true`

***

### Requirement: useFieldPolicy 前端 Hook

系统 SHALL 提供统一的前端字段策略 Hook：

#### Capability: editable 映射

* 返回 `Map<fieldId, editable>` 映射

* 与后端 FieldPolicyEngine 规则一致

* 支持响应式更新

#### Capability: 动态策略

* 接收 `row` 参数判断是否新行

* 接收 `context` 参数用于复杂判定

#### Scenario: MetaListPage 集成

* **WHEN** MetaListPage 进入编辑模式

* **THEN** 调用 `useFieldPolicy` 获取 editable 映射

* **AND** InlineEditCell 根据映射显示编辑状态

***

### Requirement: ActionPolicy 动作策略

系统 SHALL 提供动作级别的策略处理：

#### Capability: Action vs CRUD 关系

* **WHEN** 对象没有 create/edit/delete 操作

* **THEN** 不显示新建按钮

* **WHEN** 对象有 create/edit 操作但无 delete

* **THEN** 只显示新建和编辑按钮

#### Capability: Import/Export 显示策略

* **WHEN** 对象有 create/update 操作

* **AND** `import_export.import_enabled` 为 `true`

* **THEN** 显示导入按钮

* **WHEN** `import_export.export_enabled` 为 `true`

* **THEN** 显示导出按钮（只需要读取权限）

#### Scenario: 枚举类型 Action 过滤

* **WHEN** 枚举类型的 `mutability` 为 `locked`

* **THEN** 移除 create/edit/delete 操作

* **AND** 只保留 read/export 操作

***

### Requirement: YAML Schema 扩展

#### YAML Example: field\_policy 声明

```yaml
fields:
  - id: code
    semantics:
      field_policy:
        editable:
          determination:
            - when: "row.is_new == true"
              value: true
            - when: "object.mutability == 'locked'"
              value: false
            - when: "object.mutability == 'extensible' && row.is_system == true"
              value: false
            - default: true

  - id: created_at
    semantics:
      field_policy:
        editable:
          determination:
            - value: false

  - id: name
    semantics:
      mutability: extensible  # 复用 mutability determination 逻辑
```

#### YAML Example: 对象级 mutability 声明

```yaml
id: enum_value
name: 枚举值
semantics:
  mutability: extensible  # locked | fully_editable | extensible

fields:
  - id: code
    semantics:
      immutable: true  # 始终不可修改
```

\*\*\*---

### Requirement: FieldPolicy Validation（API Service 层）

系统 SHALL 在后端 API 层独立做 FieldPolicy validation，防止恶意请求绕过前端直接调用 API。

#### Capability: 前端与后端分离

* **前端 Dynamic UI**：提供用户体验层面的 editable 控制

* **后端 Validation**：提供安全层面的 editable 验证

#### Scenario: 防止恶意更新

* **WHEN** 恶意用户绕过前端，直接 POST 请求修改 locked 枚举的值

* **THEN** 后端 validation 拦截并返回错误：`"字段 'code' 在当前上下文中不可编辑"`

#### Scenario: 防止修改系统字段

* **WHEN** 恶意用户尝试修改 `is_system=true` 的枚举值

* **THEN** 后端 validation 拦截并返回错误：`"系统字段不可修改"`

#### Scenario: 新行与现有行区分

* **WHEN** 创建新行时

* **THEN** `is_new=true`，code 字段可编辑

* **WHEN** 更新现有行时

* **THEN** `is_new=false`，code 字段不可编辑

***

## MODIFIED Requirements

### Requirement: view\_config\_service.py 重构

#### Current State

* `_merge_default_actions()` 混入了 Action vs CRUD 逻辑和 Import/Export 逻辑

* `_enrich_columns()` 混入了 editable/immutable 提取逻辑

#### Target State

* `_merge_default_actions()` 只负责合并默认操作

* `_enrich_columns()` 调用 FieldPolicyEngine 提取策略

* ActionPolicy 独立处理动作级别策略

* ColumnPolicy 独立处理列级别策略

***

## REMOVED Requirements

### Requirement: 硬编码的系统字段判断

**Reason**: 系统字段判断逻辑分散在后端和前端多处，应该统一在 FieldPolicyEngine

**Migration**:

* 后端：FieldPolicyEngine 内置 `SYSTEM_FIELDS` 集合

* 前端：useFieldPolicy 读取后端返回的 editable 映射

***

## Technical Design

### 1. FieldPolicyEngine 核心结构

```python
# meta/services/field_policy_engine.py

@dataclass
class FieldPolicy:
    """字段策略声明"""
    editable: Optional['EditablePolicy'] = None
    visible: Optional['VisiblePolicy'] = None
    required: Optional['RequiredPolicy'] = None

@dataclass
class EditablePolicy:
    """可编辑策略"""
    determination: List['PolicyRule'] = None
    default: bool = True

@dataclass
class PolicyRule:
    """策略规则"""
    when: str = None  # 条件表达式
    value: Any = None  # 结果值

class FieldPolicyEngine:
    """字段策略引擎"""
    
    def __init__(self, meta_object, data_source=None):
        self.meta_object = meta_object
        self.data_source = data_source
        self._field_policies = self._load_field_policies()
        self._system_fields = self._load_system_fields()
    
    def determine_editable(self, field_id: str, context: 'PolicyContext') -> bool:
        """判定字段是否可编辑"""
        # 1. 系统字段硬编码
        if field_id in self._system_fields:
            return False
        
        # 2. 显式配置优先
        field = self._get_field(field_id)
        if hasattr(field, 'ui') and hasattr(field.ui, 'editable'):
            if field.ui.editable is not None:
                return field.ui.editable
        
        # 3. immutable 语义
        if self._is_immutable(field):
            return False
        
        # 4. 策略规则判定
        policy = self._field_policies.get(field_id)
        if policy and policy.editable:
            return self._evaluate_policy(policy.editable, context)
        
        # 5. 枚举 mutability 逻辑
        if context.object.mutability:
            return self._evaluate_mutability(field, context)
        
        return True
    
    def _evaluate_mutability(self, field, context):
        """评估 mutability determination"""
        mutability = context.object.mutability
        
        if mutability == 'locked':
            return False
        elif mutability == 'fully_editable':
            return True
        elif mutability == 'extensible':
            # 非系统字段可编辑
            is_system = getattr(field, 'is_system', False)
            return not is_system
```

### 2. PolicyContext 上下文

```python
@dataclass
class PolicyContext:
    """策略评估上下文"""
    row: Dict[str, Any] = None  # 行数据
    object: 'ObjectContext' = None  # 对象上下文
    user: 'UserContext' = None  # 用户上下文
    action: str = 'read'  # 操作类型

@dataclass
class ObjectContext:
    """对象上下文"""
    mutability: str = None  # locked | fully_editable | extensible
    type: str = None  # 对象类型

@dataclass
class UserContext:
    """用户上下文"""
    roles: List[str] = None
    permissions: List[str] = None
```

### 3. useFieldPolicy Hook

```javascript
// src/composables/useFieldPolicy.js
export function useFieldPolicy(metaConfig) {
  const policyEngine = computed(() => metaConfig.value?.policy_engine)
  
  // editable 映射
  const editableMap = computed(() => {
    const map = {}
    if (!metaConfig.value?.fields) return map
    
    metaConfig.value.fields.forEach(field => {
      map[field.id] = field.editable !== false
    })
    return map
  })
  
  // 判断单个字段是否可编辑
  function isEditable(fieldId, row) {
    // 新行判定
    const isNew = String(row?.id)?.startsWith('__new_')
    
    // 获取基础 editable 值
    let editable = editableMap.value[fieldId]
    if (editable === false) return false
    
    // immutable 字段在非新行时不可编辑
    const column = columns.value.find(c => c.prop === fieldId || c.key === fieldId)
    if (column?.immutable && !isNew) return false
    
    return true
  }
  
  return {
    editableMap,
    isEditable
  }
}
```

### 4. PolicyEvaluator 安全表达式

```python
class PolicyEvaluator:
    """安全的策略表达式求值器"""
    
    SAFE_BUILTINS = {
        'True': True, 'False': False, 'None': None,
        'and': lambda a, b: a and b,
        'or': lambda a, b: a or b,
        'not': lambda a: not a,
        'in': lambda a, b: a in b,
    }
    
    def evaluate(self, expression: str, context: PolicyContext) -> Any:
        """评估表达式"""
        # 安全替换上下文变量
        env = {
            'row': context.row or {},
            'object': context.object or {},
            'user': context.user or {},
        }
        env.update(self.SAFE_BUILTINS)
        
        # 安全求值
        try:
            return eval(expression, {"__builtins__": {}}, env)
        except Exception:
            return None
```

### 5. FieldPolicy Validation（API Service 层）

**关键**：前端 Dynamic UI 控制了 editable，但 **后端 API 必须独立做 validation**，防止恶意请求绕过前端直接调用 API。

```python
class FieldPolicyValidationInterceptor:
    """FieldPolicy 验证拦截器（后端独立验证）"""
    
    def before_create(self, context: ActionContext):
        """创建前验证"""
        self._validate_fields(context, action='create')
    
    def before_update(self, context: ActionContext):
        """更新前验证"""
        self._validate_fields(context, action='update')
    
    def _validate_fields(self, context: ActionContext, action: str):
        """验证字段是否符合 FieldPolicy"""
        engine = FieldPolicyEngine(context.meta_object)
        data = context.params
        
        # 加载旧数据（用于判断是否新行）
        old_data = self._load_old_data(context) if context.object_id else None
        is_new = old_data is None
        
        for field_id, value in data.items():
            field = context.meta_object.get_field(field_id)
            if not field:
                continue
            
            context = PolicyContext(
                row={'is_new': is_new, **data, **old_data} if old_data else {'is_new': True, **data},
                object=ObjectContext(mutability=context.meta_object.mutability),
                action=action
            )
            
            if not engine.determine_editable(field_id, context):
                return ValidationError(
                    f"字段 '{field.name}' 在当前上下文中不可编辑",
                    field_id=field_id
                )
```

### 6. BOFramework 集成

```python
# meta/core/bo_framework.py
class BOFramework:
    def execute(self, object_type: str, action: str, params: Dict):
        # ... 现有逻辑 ...
        
        # FieldPolicy Validation
        if action in ('crud_create', 'crud_update'):
            validation = FieldPolicyValidationInterceptor()
            error = validation.validate(object_type, action, params)
            if error:
                return ActionResult(success=False, message=str(error))
        
        # ... 继续执行 ...
```

***

## Implementation Phases

### Phase 1: FieldPolicyEngine 基础 (MVP)

* 创建 FieldPolicyEngine 类

* 实现 `determine_editable()` 方法

* 支持 mutability 逻辑

* 支持系统字段识别

### Phase 2: 前端集成

* 创建 useFieldPolicy Hook

* MetaListPage 集成

* InlineEditCell 使用

### Phase 3: ActionPolicy 重构

* 从 view\_config\_service 提取 ActionPolicy

* 重构 \_merge\_default\_actions()

* 导入/导出按钮逻辑迁移

### Phase 4: YAML Schema 扩展

* 新增 field\_policy 声明结构

* 向后兼容现有 semantics

* 文档更新

***

## Success Criteria

1. **一致性**：前端 `isEditable()` 与后端 `determine_editable()` 结果一致
2. **可复用**：mutability 逻辑可复用到其他业务对象
3. **声明式**：editable determination 完全由 YAML 驱动
4. **可测试**：FieldPolicyEngine 单元测试覆盖
5. **向后兼容**：现有 YAML 配置无需修改即可工作

