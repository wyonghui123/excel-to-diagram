# 审计日志字段名称显示问题修复完成

## ✅ 修复完成

**修复时间**：2026-05-09  
**修复文件**：`src/views/SystemManagement/AuditLogManagement.vue`  
**修复方案**：为每个对象类型维护独立的字段映射

## 🔧 修复内容

### 1. 修改字段映射存储结构

**修改前**：
```javascript
const FIELD_NAME_MAP = ref({})  // 全局字段映射
```

**修改后**：
```javascript
const FIELD_NAME_MAP_BY_TYPE = ref({})  // 按对象类型分组的字段映射
```

### 2. 修改字段映射加载逻辑

**修改前**：
```javascript
const map = { ...COMMON_FIELD_NAMES }

for (const field of objResult.data.fields) {
  map[field.id] = field.name  // 所有对象共享一个映射
}

FIELD_NAME_MAP.value = map
```

**修改后**：
```javascript
const mapByType = {}

for (const obj of result.data) {
  const fieldMap = { ...COMMON_FIELD_NAMES }
  
  for (const field of objResult.data.fields) {
    fieldMap[field.id] = field.name  // 每个对象独立的映射
  }
  
  mapByType[obj.id] = fieldMap  // 按对象类型存储
}

FIELD_NAME_MAP_BY_TYPE.value = mapByType
```

### 3. 修改字段名称获取方法

**修改前**：
```javascript
const getFieldName = (fieldKey) => {
  if (!fieldKey || fieldKey === '_record') return '-'
  return FIELD_NAME_MAP.value[fieldKey] || fieldKey
}
```

**修改后**：
```javascript
const getFieldName = (fieldKey, objectType) => {
  if (!fieldKey || fieldKey === '_record') return '-'
  
  // 根据对象类型获取对应的字段映射
  if (objectType && FIELD_NAME_MAP_BY_TYPE.value[objectType]) {
    return FIELD_NAME_MAP_BY_TYPE.value[objectType][fieldKey] || fieldKey
  }
  
  // 回退到通用字段映射
  return COMMON_FIELD_NAMES[fieldKey] || fieldKey
}
```

### 4. 修改模板调用

**修改前**：
```vue
<span class="field-name">{{ getFieldName(log.field_name) }}</span>
```

**修改后**：
```vue
<span class="field-name">{{ getFieldName(log.field_name, log.object_type) }}</span>
```

## 📊 修复效果

### 修复前
删除角色时显示：
- ❌ "版本编码"
- ❌ "版本名称"
- ❌ "版本描述"
- ❌ "是否系统值"

### 修复后
删除角色时显示：
- ✅ "角色编码"
- ✅ "角色名称"
- ✅ "描述"
- ✅ "系统角色"

## 🧪 验证方法

### 1. 刷新前端页面
```bash
# 清除浏览器缓存
# 按 Ctrl+Shift+Delete 清除缓存
# 或使用无痕模式打开
```

### 2. 测试不同对象类型

#### 测试角色删除
1. 创建一个测试角色
2. 删除该角色
3. 查看审计日志
4. 验证字段名称：
   - ✅ 角色编码
   - ✅ 角色名称
   - ✅ 描述
   - ✅ 系统角色

#### 测试用户删除
1. 创建一个测试用户
2. 删除该用户
3. 查看审计日志
4. 验证字段名称：
   - ✅ 用户名
   - ✅ 显示名称
   - ✅ 邮箱
   - ✅ 状态

#### 测试版本删除
1. 创建一个测试版本
2. 删除该版本
3. 查看审计日志
4. 验证字段名称：
   - ✅ 版本编码
   - ✅ 版本名称
   - ✅ 版本描述

### 3. 检查控制台日志
打开浏览器开发者工具（F12），查看控制台输出：
```
[AuditLog] Loaded field names for 25 object types
[AuditLog] Object types: ['user', 'role', 'user_group', 'version', ...]
```

## 📝 技术说明

### 为什么会出现这个问题？

前端使用全局字段映射表，当多个对象有相同字段 ID 时，后加载的对象会覆盖先加载的字段映射。

**执行顺序示例**：
1. 加载 role 对象：`code` → "角色编码"
2. 加载 version 对象：`code` → "版本编码"
3. 最终全局映射：`code` → "版本编码"（覆盖了 role 的映射）
4. 显示 role 审计日志时，错误地使用了 version 的字段名称

### 解决方案原理

为每个对象类型维护独立的字段映射表，避免不同对象之间的字段映射冲突。

**数据结构**：
```javascript
{
  "role": {
    "code": "角色编码",
    "name": "角色名称",
    "description": "描述",
    "is_system": "系统角色"
  },
  "version": {
    "code": "版本编码",
    "name": "版本名称",
    "description": "版本描述"
  },
  "user": {
    "username": "用户名",
    "display_name": "显示名称",
    "email": "邮箱"
  }
}
```

## 🎯 影响范围

### 受影响的功能
- ✅ 审计日志列表显示
- ✅ 审计日志详情显示
- ✅ 所有对象类型的审计日志

### 不受影响的功能
- ✅ 审计日志记录（后端）
- ✅ 审计日志查询
- ✅ 审计日志导出

## 📚 相关文档

- [审计日志字段名称修复方案](file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_FIELD_NAME_FIX.md)
- [V2 迁移完成报告](file:///d:/filework/excel-to-diagram/docs/archive/fixes/MIGRATION_COMPLETED_REPORT.md)
- [权限管理系统测试报告](file:///D:/filework/excel-to-diagram/docs/PERMISSION_TEST_REPORT.md)

## ✅ 修复验证清单

- [x] 修改字段映射存储结构
- [x] 修改字段映射加载逻辑
- [x] 修改字段名称获取方法
- [x] 修改模板调用
- [ ] 刷新前端页面验证
- [ ] 测试角色删除
- [ ] 测试用户删除
- [ ] 测试版本删除
- [ ] 检查控制台日志

---

**修复完成时间**：2026-05-09  
**修复状态**：✅ 代码修复完成，待前端验证  
**下一步**：刷新前端页面并测试验证
