# 字段控制模型改进方案

## 一、现状分析

### 1.1 当前字段控制属性分布

| 属性 | 定义位置 | 作用 | 问题 |
|------|----------|------|------|
| `required` | `MetaField.required` | 数据库必填 | ✅ 正确 |
| `business_key` | `SemanticAnnotation.business_key` | 业务键标识 | ❌ 缺少只读控制 |
| `ui.editable` | `UIAnnotation.editable` | UI 可编辑 | ❌ 无法区分新建/编辑 |
| `ui.visible` | `UIAnnotation.visible` | UI 可见 | ✅ 正确 |

### 1.2 前端硬编码问题

```javascript
// DynamicForm.vue 中的硬编码
const HIERARCHY_READONLY_FIELDS = {
  version: ['product_id'],
  domain: ['version_id'],
  sub_domain: ['version_id', 'domain_id'],
  service_module: ['version_id', 'domain_id', 'sub_domain_id'],
  business_object: ['version_id'],
  relationship: ['version_id']
}
```

**问题**：
1. 父键只读逻辑硬编码在前端
2. 业务键只读逻辑未实现（编辑时应只读）
3. 与元数据定义脱节，维护困难

### 1.3 后端导入导出问题

```python
# import_export_service.py 中的字段控制
def _is_field_editable(self, field) -> bool:
    """判断字段是否可编辑（用于导入）"""
    # 只判断了 _id 后缀的字段
    if field.id.endswith('_id') and field.id != 'id':
        # 检查是否是父对象ID
        ...
```

**问题**：
1. 未考虑 `business_key` 字段的只读性
2. 未考虑 `immutable` 属性
3. 与前端逻辑不一致

## 二、SAP CDS View 参考

### 2.1 SAP 字段控制注解

| SAP 注解 | 作用 | 对应场景 |
|----------|------|----------|
| `@Core.Immutable` | 创建后不可变 | 业务键、主键 |
| `@ObjectModel.readOnly: true` | 始终只读 | 系统字段、计算字段 |
| `@mandatory` | 必填 | 关键业务字段 |
| `@UI.Hidden` | 隐藏 | 技术字段 |
| `@ObjectModel.readOnly: 'EXTERNAL_CALCULATION'` | 外部计算 | 自动推导字段 |

### 2.2 SAP 字段控制逻辑

```
字段可编辑性判断流程：
1. @ObjectModel.readOnly: true → 始终只读
2. @Core.Immutable + mode='edit' → 只读
3. @Core.Immutable + mode='create' → 可编辑
4. 默认 → 根据 @UI.editable 判断
```

## 三、改进方案

### 3.1 扩展 SemanticAnnotation 模型

```python
@dataclass
class SemanticAnnotation:
    """语义标注 - 参考 SAP CDS View 注解体系"""
    
    # === 现有属性 ===
    meaning: str = ""
    business_key: bool = False
    display_name: bool = False
    pattern: str = ""
    examples: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    category: str = ""
    hierarchy_level: int = 0
    custom: Dict[str, Any] = field(default_factory=dict)
    
    # === 导入导出属性 ===
    data_category: str = ""
    import_visible: bool = True
    export_visible: bool = False
    import_order: int = 100
    virtual: bool = False
    
    # === 新增字段控制属性（参考 SAP CDS View）===
    immutable: bool = False      # 创建后不可变（类似 @Core.Immutable）
    parent_key: bool = False     # 父对象键标识（用于层级关联）
    mandatory: bool = False      # 业务必填（类似 @mandatory，区别于数据库 required）
```

### 3.2 属性语义说明

| 属性 | 类型 | 说明 | SAP 对应 |
|------|------|------|----------|
| `immutable` | bool | 创建后不可变，新建时可编辑，编辑时只读 | `@Core.Immutable` |
| `parent_key` | bool | 父对象键，用于层级关联，新建时可编辑，编辑时只读 | SAP 层级模型 |
| `mandatory` | bool | 业务必填，前端显示必填标记，不影响数据库 | `@mandatory` |
| `required` | bool | 数据库必填，影响数据库约束 | NOT NULL |
| `business_key` | bool | 业务键标识，应同时设置 `immutable: true` | `@ObjectModel.semanticKey` |

### 3.3 YAML 字段定义示例

```yaml
fields:
  # 业务键字段 - immutable: true
  - id: code
    name: 编码
    type: string
    required: true                    # 数据库必填
    semantics:
      meaning: 领域的唯一标识编码
      business_key: true              # 业务键标识
      immutable: true                 # 创建后不可变
      import_order: 2
    ui:
      visible: true
      editable: true                  # 默认可编辑，但 immutable 优先

  # 父键字段 - parent_key: true
  - id: version_id
    name: 版本
    type: integer
    required: true
    semantics:
      meaning: 关联的产品版本
      parent_key: true                # 父对象键
      immutable: true                 # 创建后不可变
    ui:
      widget: select
      relation: version

  # 普通必填字段 - mandatory: true
  - id: name
    name: 名称
    type: string
    required: true
    semantics:
      meaning: 领域的显示名称
      display_name: true
      mandatory: true                 # 业务必填
      import_order: 20
    ui:
      visible: true
      editable: true

  # 虚拟字段 - virtual: true
  - id: version_name
    name: 版本名称
    type: string
    storage: virtual
    semantics:
      meaning: 关联版本的显示名称
      virtual: true
    ui:
      visible: true
      editable: false                 # 虚拟字段不可编辑
```

### 3.4 前端字段控制逻辑重构

```javascript
/**
 * 判断字段是否可编辑
 * 参考 SAP Fiori Elements 字段控制逻辑
 */
function isFieldEditable(fieldId) {
  const field = getField(fieldId)
  if (!field) return false
  
  const mode = props.mode  // 'create' | 'edit'
  const semantics = field.semantics || {}
  
  // 1. immutable 字段：编辑时只读
  if (semantics.immutable && mode === 'edit') {
    return false
  }
  
  // 2. parent_key 字段：编辑时只读（与 immutable 逻辑相同）
  if (semantics.parent_key && mode === 'edit') {
    return false
  }
  
  // 3. virtual 字段：始终只读
  if (semantics.virtual) {
    return false
  }
  
  // 4. 默认使用 ui.editable
  return field.ui?.editable !== false
}

/**
 * 判断字段是否必填
 */
function isFieldRequired(fieldId) {
  const field = getField(fieldId)
  if (!field) return false
  
  // 1. 数据库必填
  if (field.required) return true
  
  // 2. 业务必填
  if (field.semantics?.mandatory) return true
  
  // 3. 新建时的 immutable 字段必填
  if (field.semantics?.immutable && props.mode === 'create') {
    return true
  }
  
  return false
}
```

### 3.5 后端导入导出字段控制

```python
def _is_field_editable(self, field, mode: str = 'edit') -> bool:
    """判断字段是否可编辑（用于导入导出）
    
    参考 SAP CDS View 字段控制逻辑：
    1. immutable 字段：编辑时只读
    2. parent_key 字段：编辑时只读
    3. virtual 字段：始终只读
    4. 系统字段：始终只读
    """
    readonly_field_ids = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}
    
    if field.id in readonly_field_ids:
        return False
    
    if field.semantics.virtual:
        return False
    
    if mode == 'edit':
        if field.semantics.immutable or field.semantics.parent_key:
            return False
    
    return field.ui.editable if hasattr(field, 'ui') else True
```

## 四、实施任务

### Task 1: 扩展 SemanticAnnotation 模型
- 文件: `meta/core/models.py`
- 内容: 添加 `immutable`, `parent_key`, `mandatory` 属性

### Task 2: 更新 yaml_loader.py
- 文件: `meta/core/yaml_loader.py`
- 内容: 在 `parse_semantics` 函数中解析新属性

### Task 3: 更新 YAML 文件
- 文件: `meta/schemas/*.yaml`
- 内容: 为所有 `business_key: true` 的字段添加 `immutable: true`
- 内容: 为所有父键字段添加 `parent_key: true`

### Task 4: 重构前端字段控制
- 文件: `src/views/ArchDataManageApp/components/DynamicForm.vue`
- 内容: 移除 `HIERARCHY_READONLY_FIELDS` 硬编码
- 内容: 实现基于元数据的字段控制逻辑

### Task 5: 更新导入导出服务
- 文件: `meta/services/import_export_service.py`
- 内容: 更新 `_is_field_editable` 方法
- 内容: 更新 `_get_export_headers_with_editable` 方法

### Task 6: 添加测试
- 文件: `meta/tests/test_field_control.py`
- 内容: 测试 `immutable` 字段在新建/编辑时的行为
- 内容: 测试 `parent_key` 字段在新建/编辑时的行为
- 内容: 测试 `mandatory` 字段的必填验证

## 五、字段属性速查表

| 字段类型 | required | business_key | immutable | parent_key | mandatory | 新建时 | 编辑时 |
|----------|----------|--------------|----------|------------|-----------|--------|--------|
| 业务键 | ✅ | ✅ | ✅ | ❌ | ❌ | 可编辑+必填 | 只读 |
| 父键 | ✅ | ❌ | ✅ | ✅ | ❌ | 可编辑+必填 | 只读 |
| 普通必填 | ✅ | ❌ | ❌ | ❌ | ✅ | 可编辑+必填 | 可编辑+必填 |
| 普通可选 | ❌ | ❌ | ❌ | ❌ | ❌ | 可编辑 | 可编辑 |
| 虚拟字段 | ❌ | ❌ | ❌ | ❌ | ❌ | 只读 | 只读 |
| 系统字段 | ❌ | ❌ | ❌ | ❌ | ❌ | 只读 | 只读 |

## 六、兼容性说明

### 6.1 向后兼容
- `immutable` 默认为 `False`，不影响现有字段
- `parent_key` 默认为 `False`，不影响现有字段
- `mandatory` 默认为 `False`，不影响现有字段

### 6.2 迁移策略
1. 先添加属性定义（不影响现有行为）
2. 更新 YAML 文件添加新属性
3. 更新前端逻辑使用新属性
4. 移除硬编码逻辑
