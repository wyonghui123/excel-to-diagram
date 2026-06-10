# 审计日志字段名称显示问题修复方案

## 🎯 问题分析

### 问题现象
删除角色时，审计日志显示的字段名称错误：
- "版本编码" → 应该是 "角色编码"
- "版本名称" → 应该是 "角色名称"
- "版本描述" → 应该是 "描述"
- "是否系统值" → 应该是 "系统角色"

### 根本原因

前端在加载字段映射时，使用全局的字段映射表：

```javascript
// 当前实现（有问题）
const FIELD_NAME_MAP = ref({})

// 遍历所有对象
for (const obj of result.data) {
  // 加载字段映射
  for (const field of objResult.data.fields) {
    map[field.id] = field.name  // 后加载的会覆盖先加载的
  }
}
```

当多个对象有相同字段 ID 时（如 `code`, `name`, `description`），后加载的对象会覆盖先加载的字段映射。

### 执行流程

1. 加载 role 对象：`code` → "角色编码"
2. 加载 version 对象：`code` → "版本编码"
3. 最终全局映射：`code` → "版本编码"
4. 显示 role 审计日志时，错误地使用了 version 的字段名称

## 🔧 解决方案

### 方案一：为每个对象类型维护独立的字段映射（推荐）

修改 `AuditLogManagement.vue`：

```javascript
// 修改前
const FIELD_NAME_MAP = ref({})

// 修改后
const FIELD_NAME_MAP_BY_TYPE = ref({})

const loadFieldNamesFromMeta = async () => {
  try {
    const response = await fetch(`${API_BASE}/meta/objects`, {
      headers: authStore.getAuthHeaders()
    })
    const result = await response.json()
    
    if (result.success && result.data) {
      const mapByType = {}
      
      for (const obj of result.data) {
        try {
          const objResponse = await fetch(`${API_BASE}/meta/objects/${obj.id}`, {
            headers: authStore.getAuthHeaders()
          })
          const objResult = await objResponse.json()
          
          if (objResult.success && objResult.data?.fields) {
            // 为每个对象类型创建独立的字段映射
            const fieldMap = { ...COMMON_FIELD_NAMES }
            
            for (const field of objResult.data.fields) {
              if (field.id && field.name) {
                fieldMap[field.id] = field.name
              }
            }
            
            mapByType[obj.id] = fieldMap
          }
          
          if (objResult.success && objResult.data?.name) {
            OBJECT_TYPE_MAP[obj.id] = objResult.data.name
          }
        } catch (e) {
          console.warn(`Failed to load fields for ${obj.id}:`, e)
        }
      }
      
      FIELD_NAME_MAP_BY_TYPE.value = mapByType
      fieldMapLoaded.value = true
      console.log(`[AuditLog] Loaded field names for ${Object.keys(mapByType).length} object types`)
    }
  } catch (error) {
    console.error('[AuditLog] Failed to load field names from metadata:', error)
  }
}

// 修改 getFieldName 方法
const getFieldName = (fieldKey, objectType) => {
  if (!fieldKey || fieldKey === '_record') return '-'
  
  // 如果提供了对象类型，使用该类型的字段映射
  if (objectType && FIELD_NAME_MAP_BY_TYPE.value[objectType]) {
    return FIELD_NAME_MAP_BY_TYPE.value[objectType][fieldKey] || fieldKey
  }
  
  // 否则使用通用字段映射
  return COMMON_FIELD_NAMES[fieldKey] || fieldKey
}
```

修改模板中的调用：

```vue
<!-- 修改前 -->
<span class="field-name">{{ getFieldName(log.field_name) }}</span>

<!-- 修改后 -->
<span class="field-name">{{ getFieldName(log.field_name, log.object_type) }}</span>
```

### 方案二：在审计日志中存储对象类型信息

修改后端，在审计日志记录时包含字段名称：

```python
# 在 AuditInterceptor 中
def _log_delete(self, context: ActionContext, config: AuditActionConfig) -> None:
    # ... 现有代码 ...
    
    for field in fields_to_log:
        # 获取字段的显示名称
        field_name = self._get_field_display_name(context.meta_object, field)
        
        audit_service.log(
            object_type=context.object_type,
            object_id=context.object_id,
            action='DELETE',
            field_name=field,  # 字段 ID
            field_display_name=field_name,  # 字段显示名称
            old_value=str(old_data.get(field)) if old_data.get(field) is not None else '',
            new_value='',
            user_id=str(context.user_id) if context.user_id else None,
            user_name=context.user_name,
            trace_id=context.trace_id,
        )

def _get_field_display_name(self, meta_object, field_id: str) -> str:
    """获取字段的显示名称"""
    for field in meta_object.fields:
        if field.id == field_id:
            return field.name
    return field_id
```

前端直接使用 `field_display_name`：

```javascript
<span class="field-name">{{ log.field_display_name || getFieldName(log.field_name) }}</span>
```

## 📊 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| 方案一 | 前端修改小，性能好 | 需要传递 objectType | ⭐⭐⭐⭐⭐ |
| 方案二 | 数据完整，前端简单 | 需要修改后端和数据库 | ⭐⭐⭐⭐ |

## 🚀 实施步骤

### 方案一实施步骤

1. 修改 `AuditLogManagement.vue`：
   - 将 `FIELD_NAME_MAP` 改为 `FIELD_NAME_MAP_BY_TYPE`
   - 修改 `loadFieldNamesFromMeta` 方法
   - 修改 `getFieldName` 方法，接受 `objectType` 参数

2. 修改模板：
   - 在调用 `getFieldName` 时传递 `log.object_type`

3. 测试验证：
   - 删除角色，检查字段名称是否正确
   - 删除用户组，检查字段名称是否正确
   - 删除版本，检查字段名称是否正确

## ✅ 预期效果

修复后，删除角色时的审计日志应该显示：
- "角色编码" ✅
- "角色名称" ✅
- "描述" ✅
- "系统角色" ✅

---

**创建时间**：2026-05-09  
**问题类型**：前端字段映射错误  
**影响范围**：审计日志显示  
**修复优先级**：高
