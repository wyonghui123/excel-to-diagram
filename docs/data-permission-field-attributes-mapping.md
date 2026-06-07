# 数据权限模型与字段属性的关系分析

## 一、概念定义

### 1. 数据权限级别

| 级别 | 英文 | 说明 |
|------|------|------|
| 无权限 | none | 完全不可见 |
| 只读 | read | 可查看，不可修改 |
| 编辑 | write | 可查看、可创建、可修改 |
| 管理 | admin | 完全控制，包括删除 |

### 2. 字段属性

| 属性 | 说明 | 值 |
|------|------|-----|
| `editable` | 字段是否可编辑 | true/false |
| `readonly` | 字段是否只读 | true/false |
| `visibility` | 字段可见性 | visible/hidden/masked |

### 3. 字段级安全属性（扩展）

| 属性 | 说明 | 值 |
|------|------|-----|
| `readable_by` | 可读取的角色/权限级别 | ['read', 'write', 'admin'] |
| `writable_by` | 可写入的角色/权限级别 | ['write', 'admin'] |
| `sensitivity` | 敏感级别 | public/internal/confidential/restricted |

## 二、关系模型

### 1. 权限级别与字段属性映射

```
数据权限级别          字段可见性          字段可编辑性
─────────────────────────────────────────────────────
none                 hidden             false
read                 visible/masked     false
write                visible            true (部分字段)
admin                visible            true (全部字段)
```

### 2. 字段级权限矩阵

```
                    │  无权限  │  只读   │  编辑   │  管理   │
─────────────────────────────────────────────────────────────
字段可见性           │  hidden  │ visible │ visible │ visible │
字段可编辑           │    -     │  false  │ partial │  true   │
字段可删除           │    -     │  false  │  false  │  true   │
敏感字段可见         │  hidden  │ masked  │ masked  │ visible │
```

## 三、详细映射规则

### 1. 可见性规则 (visibility)

```python
def get_field_visibility(field, permission_level):
    """获取字段可见性"""
    
    # 1. 检查字段本身的可见性定义
    if field.visibility == 'hidden':
        return 'hidden'
    
    # 2. 根据权限级别判断
    if permission_level == 'none':
        return 'hidden'
    
    # 3. 检查字段的 readable_by 定义
    readable_by = field.readable_by or ['read', 'write', 'admin']
    if permission_level not in readable_by:
        return 'hidden'
    
    # 4. 检查敏感字段
    if field.sensitivity in ('confidential', 'restricted'):
        if permission_level == 'read':
            return 'masked'  # 脱敏显示
        elif permission_level == 'write' and field.sensitivity == 'restricted':
            return 'masked'  # 高敏感字段，编辑权限也脱敏
    
    return 'visible'
```

### 2. 可编辑性规则 (editable)

```python
def get_field_editability(field, permission_level):
    """获取字段可编辑性"""
    
    # 1. 无权限或只读权限，不可编辑
    if permission_level in ('none', 'read'):
        return False
    
    # 2. 检查字段本身的 readonly 定义
    if field.readonly == True:
        return False
    
    # 3. 检查字段的 writable_by 定义
    writable_by = field.writable_by or ['write', 'admin']
    if permission_level not in writable_by:
        return False
    
    # 4. 检查字段是否是系统字段
    if field.system_field and permission_level != 'admin':
        return False  # 系统字段只有管理员可编辑
    
    # 5. 检查字段是否是创建后不可修改
    if field.immutable_after_create:
        # 需要上下文判断是创建还是修改
        return 'create_only'
    
    return True
```

### 3. 只读规则 (readonly)

```python
def get_field_readonly(field, permission_level):
    """获取字段只读状态"""
    
    # readonly 是 editable 的反向
    editability = get_field_editability(field, permission_level)
    
    if editability == True:
        return False
    elif editability == 'create_only':
        return 'create_only'  # 创建时可编辑，之后只读
    else:
        return True
```

## 四、字段元模型定义

### 1. YAML Schema 扩展

```yaml
# meta/schemas/business_object.yaml
fields:
  - id: code
    name: 编码
    type: string
    required: true
    unique: true
    
    # 字段级权限控制
    visibility: visible           # 基础可见性
    readable_by: ['read', 'write', 'admin']  # 可读取的权限级别
    writable_by: ['write', 'admin']          # 可写入的权限级别
    sensitivity: public           # 敏感级别
    
  - id: name
    name: 名称
    type: string
    required: true
    visibility: visible
    readable_by: ['read', 'write', 'admin']
    writable_by: ['write', 'admin']
    sensitivity: public
    
  - id: description
    name: 描述
    type: text
    visibility: visible
    readable_by: ['read', 'write', 'admin']
    writable_by: ['write', 'admin']
    sensitivity: internal
    
  - id: cost_amount
    name: 成本金额
    type: decimal
    visibility: visible
    readable_by: ['write', 'admin']  # 只读权限不可见
    writable_by: ['admin']           # 只有管理员可修改
    sensitivity: confidential        # 机密级别
    
  - id: internal_notes
    name: 内部备注
    type: text
    visibility: visible
    readable_by: ['admin']           # 只有管理员可见
    writable_by: ['admin']
    sensitivity: restricted          # 限制级别
    
  - id: created_at
    name: 创建时间
    type: datetime
    readonly: true                   # 系统字段，只读
    system_field: true
    
  - id: created_by
    name: 创建人
    type: string
    readonly: true
    system_field: true
    
  - id: status
    name: 状态
    type: string
    immutable_after_create: true     # 创建后不可修改
```

### 2. 敏感级别定义

```yaml
# 敏感级别与权限映射
sensitivity_levels:
  public:
    description: 公开信息
    visible_for: ['read', 'write', 'admin']
    
  internal:
    description: 内部信息
    visible_for: ['read', 'write', 'admin']
    mask_for: []  # 不脱敏
    
  confidential:
    description: 机密信息
    visible_for: ['write', 'admin']
    mask_for: ['read']  # 只读权限脱敏
    
  restricted:
    description: 限制信息
    visible_for: ['admin']
    mask_for: ['read', 'write']  # 编辑权限也脱敏
```

## 五、运行时计算

### 1. 字段属性计算服务

```python
class FieldAttributeService:
    """字段属性计算服务"""
    
    def compute_field_attributes(self, object_type: str, user_id: int) -> dict:
        """计算用户对所有字段的属性"""
        
        # 1. 获取用户对该对象的数据权限级别
        permission_level = self.get_permission_level(user_id, object_type)
        
        # 2. 获取对象的所有字段定义
        meta_obj = meta_registry.get(object_type)
        fields = meta_obj.fields
        
        # 3. 计算每个字段的属性
        result = {}
        for field in fields:
            result[field.id] = {
                'visibility': self._compute_visibility(field, permission_level),
                'editable': self._compute_editability(field, permission_level),
                'readonly': self._compute_readonly(field, permission_level),
            }
        
        return result
    
    def _compute_visibility(self, field, permission_level):
        """计算字段可见性"""
        if permission_level == 'none':
            return 'hidden'
        
        # 检查 readable_by
        readable_by = getattr(field, 'readable_by', ['read', 'write', 'admin'])
        if permission_level not in readable_by:
            return 'hidden'
        
        # 检查敏感级别
        sensitivity = getattr(field, 'sensitivity', 'public')
        if sensitivity == 'confidential' and permission_level == 'read':
            return 'masked'
        if sensitivity == 'restricted' and permission_level in ('read', 'write'):
            return 'masked'
        
        return 'visible'
    
    def _compute_editability(self, field, permission_level):
        """计算字段可编辑性"""
        if permission_level in ('none', 'read'):
            return False
        
        # 检查 readonly 属性
        if getattr(field, 'readonly', False):
            return False
        
        # 检查 writable_by
        writable_by = getattr(field, 'writable_by', ['write', 'admin'])
        if permission_level not in writable_by:
            return False
        
        # 检查系统字段
        if getattr(field, 'system_field', False) and permission_level != 'admin':
            return False
        
        return True
    
    def _compute_readonly(self, field, permission_level):
        """计算字段只读状态"""
        return not self._compute_editability(field, permission_level)
```

### 2. API 响应示例

```json
// GET /api/v1/business_object/fields/attributes?user_id=123
{
  "object_type": "business_object",
  "user_id": 123,
  "permission_level": "write",
  "fields": {
    "code": {
      "visibility": "visible",
      "editable": true,
      "readonly": false
    },
    "name": {
      "visibility": "visible",
      "editable": true,
      "readonly": false
    },
    "description": {
      "visibility": "visible",
      "editable": true,
      "readonly": false
    },
    "cost_amount": {
      "visibility": "masked",
      "editable": false,
      "readonly": true
    },
    "internal_notes": {
      "visibility": "hidden",
      "editable": false,
      "readonly": true
    },
    "created_at": {
      "visibility": "visible",
      "editable": false,
      "readonly": true
    },
    "status": {
      "visibility": "visible",
      "editable": false,
      "readonly": true
    }
  }
}
```

## 六、前端应用

### 1. 表单渲染

```vue
<template>
  <form>
    <template v-for="field in fields" :key="field.id">
      <!-- 隐藏字段：不渲染 -->
      <template v-if="fieldAttributes[field.id].visibility === 'hidden'">
        <!-- skip -->
      </template>
      
      <!-- 脱敏字段：显示脱敏值 -->
      <template v-else-if="fieldAttributes[field.id].visibility === 'masked'">
        <div class="form-group">
          <label>{{ field.name }}</label>
          <span class="masked-value">******</span>
          <span class="permission-hint">
            <AppIcon name="lock" />
            需要更高权限查看
          </span>
        </div>
      </template>
      
      <!-- 只读字段：禁用输入 -->
      <template v-else-if="fieldAttributes[field.id].readonly">
        <div class="form-group">
          <label>{{ field.name }}</label>
          <input :value="data[field.id]" disabled />
        </div>
      </template>
      
      <!-- 可编辑字段 -->
      <template v-else>
        <div class="form-group">
          <label>{{ field.name }}</label>
          <input v-model="data[field.id]" />
        </div>
      </template>
    </template>
  </form>
</template>
```

### 2. 列表渲染

```vue
<template>
  <table>
    <thead>
      <tr>
        <th v-for="field in visibleFields" :key="field.id">
          {{ field.name }}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in data" :key="row.id">
        <td v-for="field in visibleFields" :key="field.id">
          <!-- 根据可见性渲染 -->
          <template v-if="fieldAttributes[field.id].visibility === 'masked'">
            ******
          </template>
          <template v-else>
            {{ row[field.id] }}
          </template>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script>
export default {
  computed: {
    visibleFields() {
      return this.fields.filter(
        f => this.fieldAttributes[f.id].visibility !== 'hidden'
      )
    }
  }
}
</script>
```

## 七、完整权限矩阵

### 示例：业务对象字段权限矩阵

| 字段 | 敏感级别 | 无权限 | 只读 | 编辑 | 管理 |
|------|---------|--------|------|------|------|
| code | public | hidden | visible/readonly | visible/editable | visible/editable |
| name | public | hidden | visible/readonly | visible/editable | visible/editable |
| description | internal | hidden | visible/readonly | visible/editable | visible/editable |
| cost_amount | confidential | hidden | **masked**/readonly | visible/readonly | visible/editable |
| internal_notes | restricted | hidden | **hidden** | **masked**/readonly | visible/editable |
| created_at | system | hidden | visible/readonly | visible/readonly | visible/readonly |
| status | immutable | hidden | visible/readonly | visible/readonly | visible/editable |

## 八、总结

### 关系模型

```
数据权限级别
    │
    ├──→ 字段可见性 (visibility)
    │      ├── none → hidden
    │      ├── read → visible/masked (取决于敏感级别)
    │      ├── write → visible/masked (取决于敏感级别)
    │      └── admin → visible
    │
    ├──→ 字段可编辑性 (editable)
    │      ├── none → false
    │      ├── read → false
    │      ├── write → true (部分字段)
    │      └── admin → true (全部字段)
    │
    └──→ 字段只读状态 (readonly)
           └── readonly = !editable
```

### 核心规则

1. **可见性优先**：先判断可见性，再判断可编辑性
2. **敏感级别影响**：高敏感字段在低权限时脱敏或隐藏
3. **系统字段保护**：系统字段只有管理员可修改
4. **创建后不可变**：部分字段创建后变为只读
