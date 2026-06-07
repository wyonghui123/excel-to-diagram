# Phase 18.3: 级联下拉 cascade_select

> **状态**: 🚧 进行中
> **依赖**: M18.1 ✅ (YAML Schema cascade_select 配置)
> **预估工时**: 2 天
> **独立 Spec**: [phase-18-3-cascade-select/spec.md](phase-18-3-cascade-select/spec.md)

---

## 1. 背景与目标

### 1.1 问题描述

创建架构对象（domain/sub_domain/service_module/business_object）时，需要选择完整的层级路径：
```
产品 → 版本 → 领域 → 子领域 → 服务模块
```

当前问题：
- DynamicForm 没有统一的级联下拉机制
- 存在硬编码的 `CASCADE_PARAM_MAP`
- 无法从 YAML 声明式配置中自动推导级联关系

### 1.2 元数据驱动原则

```
┌─────────────────────────────────────────────────────────────┐
│                    元数据驱动架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   YAML 配置声明 ──► Composable 解释 ──► 组件渲染              │
│         │                │                │                  │
│         ▼                ▼                ▼                  │
│   cascade_select    useCascadeSelect   AppSelect           │
│   hierarchies       useHierarchy       MetaTable           │
│   context           useVersionContext    ContextSelector      │
│                                                             │
│   原则：配置即代码，无硬编码                                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 YAML 配置现状

| 对象 | cascade_select | 级联深度 | 状态 |
|------|--------------|----------|------|
| domain | → sub_domain | 1 | ✅ 已配置 |
| sub_domain | → service_module | 2 | ✅ 已配置 |
| service_module | → business_object | 3 | ✅ 已配置 |
| business_object | 无 | 5 | ⚠️ 需补充 |

---

## 2. YAML 配置规范

### 2.1 cascade_select 配置块

```yaml
cascade_select:
  - field: <当前字段ID>
    parent_object: <父对象名称>
    parent_display_field: <父对象显示字段>
    filter_by: <父对象过滤参数字段>
```

### 2.2 配置示例

**domain.yaml**:
```yaml
cascade_select:
  - field: sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: domain_id
```

**sub_domain.yaml**:
```yaml
cascade_select:
  - field: service_module_id
    parent_object: service_module
    parent_display_field: name
    filter_by: sub_domain_id
```

**service_module.yaml**:
```yaml
cascade_select:
  - field: business_object_id
    parent_object: business_object
    parent_display_field: name
    filter_by: service_module_id
```

### 2.3 business_object 补充 cascade_select

```yaml
# business_object.yaml 需要补充
cascade_select:
  - field: domain_id
    parent_object: domain
    parent_display_field: name
    filter_by: version_id
  - field: sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: domain_id
  - field: service_module_id
    parent_object: service_module
    parent_display_field: name
    filter_by: sub_domain_id
```

---

## 3. 核心设计：useCascadeSelect

### 3.1 设计原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **YAML 即唯一真相** | 所有配置从 metaObject.cascade_select 读取 | `config.field`, `config.parent_object` |
| **无硬编码对象名** | 动态读取 parent_object | `boService.query(config.parent_object)` |
| **无硬编码参数字段** | 动态读取 filter_by | `params[config.filter_by]` |
| **无硬编码显示字段** | 动态读取 parent_display_field | `item[config.displayField]` |
| **声明式配置** | YAML 声明，运行时解释 | 无 if/elif 对象判断 |

### 3.2 API 设计

```typescript
// useCascadeSelect(metaObject: Ref<MetaObject>)

interface CascadeConfig {
  field: string              // 当前字段ID
  parentField: string        // 父字段（filter_by）
  parentObject: string       // 父对象（parent_object）
  displayField: string      // 显示字段（parent_display_field）
}

// 状态
cascadeConfig: Ref<CascadeConfig[]>    // YAML 中读取的级联配置
cascadeChain: Map<string, CascadeConfig>  // field → config 映射
cascadeFields: string[]               // 级联字段列表

// 方法
loadCascadeOptions(fieldId: string, parentValue: any): Promise<CascadeOption[]>
clearDownstream(fieldId: string): void
isCascadeField(fieldId: string): boolean
getParentField(fieldId: string): string | null
getOptions(fieldId: string): CascadeOption[]
isLoading(fieldId: string): boolean
```

### 3.3 级联链自动构建

```
YAML cascade_select 配置
        │
        ▼
    cascadeConfig[] (数组)
        │
        ▼
    cascadeChain (Map<fieldId, Config>)
        │
        ├──► cascadeFields (级联字段ID列表)
        │
        └──► parentFields (父字段列表)
```

---

## 4. 级联加载流程

### 4.1 流程图

```
父字段值变化
    │
    ▼
┌───────────────────────────────────────┐
│ 1. 清空当前字段下游的所有选项              │
│    clearDownstream(fieldId)             │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. 构造 API 参数                        │
│    params = {                          │
│      [config.filter_by]: parentValue,   │
│      pageSize: 1000                    │
│    }                                   │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. 动态调用 API                         │
│    boService.query(config.parent_object,│
│                   { filters: params })  │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 4. 映射选项并存储                       │
│    options[fieldId] = items.map(item => │
│      ({ value: item.id,                │
│        label: item[displayField] }))   │
└───────────────────────────────────────┘
    │
    ▼
    渲染 AppSelect 组件
```

### 4.2 核心代码

```javascript
async function loadCascadeOptions(fieldId, parentValue) {
  const config = cascadeChain.value[fieldId]
  if (!config || !parentValue) {
    options.value[fieldId] = []
    return []
  }
  
  loading.value[fieldId] = true
  try {
    const params = {}
    params[config.parentField] = parentValue
    params.pageSize = 1000
    
    const result = await boService.query(
      config.parentObject,
      { filters: params }
    )
    
    if (result.success) {
      const items = result.data?.items || result.data || []
      options.value[fieldId] = items.map(item => ({
        value: item.id,
        label: item[config.displayField] || item.name || item.code,
        _raw: item
      }))
    }
  } finally {
    loading.value[fieldId] = false
  }
}
```

---

## 5. MetaForm 集成

### 5.1 集成方案

```vue
<template>
  <MetaForm :fields="enhancedFields" />
</template>

<script setup>
import { computed } from 'vue'
import { useCascadeSelect } from '@/composables/useCascadeSelect'

const props = defineProps({
  metaObject: Object,
  fields: Array
})

const cascade = useCascadeSelect(toRef(props, 'metaObject'))

// 增强 fields，注入级联选项
const enhancedFields = computed(() => {
  return props.fields.map(field => {
    if (cascade.isCascadeField(field.key)) {
      return {
        ...field,
        options: cascade.getOptions(field.key),
        disabled: cascade.isLoading(field.key) || 
                  !formData.value[cascade.getParentField(field.key)]
      }
    }
    return field
  })
})
</script>
```

### 5.2 AppSelect 增强

```vue
<AppSelect
  v-model="formData[field.key]"
  :options="getCascadeOptions(field.key) || field.options || []"
  :loading="isCascadeLoading(field.key)"
  :disabled="field.disabled || isCascadeDisabled(field.key)"
  @change="onCascadeChange(field.key, $event)"
/>
```

```javascript
function getCascadeOptions(fieldKey) {
  if (cascade.isCascadeField(fieldKey)) {
    return cascade.getOptions(fieldKey)
  }
  return null
}

function isCascadeDisabled(fieldKey) {
  if (!cascade.isCascadeField(fieldKey)) return false
  const parentField = cascade.getParentField(fieldKey)
  return !formData.value[parentField]
}

function onCascadeChange(fieldKey, newValue) {
  cascade.clearDownstream(fieldKey)
  if (newValue) {
    cascade.loadCascadeOptions(fieldKey, newValue)
  }
}
```

---

## 6. 层级归属区块

### 6.1 YAML fieldGroup 配置

```yaml
fields:
  - id: version_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 10

  - id: domain_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 15

  - id: sub_domain_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 20

  - id: service_module_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 25
```

### 6.2 MetaForm 字段分组渲染

```vue
<div v-for="group in fieldGroups" :key="group.name">
  <div class="field-group-title">{{ group.name }}</div>
  <div class="field-group-fields">
    <div v-for="field in group.fields" :key="field.key">
      <!-- 渲染字段 -->
    </div>
  </div>
</div>
```

---

## 7. 编辑时反向推断

### 7.1 流程

```
加载已有数据 (e.g., { service_module_id: 5 })
    │
    ▼
┌───────────────────────────────────────┐
│ 1. 加载 service_module                    │
│    loadCascadeOptions('service_module_id', 5) │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. 获取父级 sub_domain_id                 │
│    serviceModule.sub_domain_id = 3       │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. 递归加载父级                          │
│    loadCascadeOptions('sub_domain_id', 3) │
│    loadCascadeOptions('domain_id', ...)   │
└───────────────────────────────────────┘
    │
    ▼
    填充 formData，完成初始化
```

### 7.2 useCascadeSelect 扩展

```javascript
async function inferParentFields(currentFieldId, currentValue) {
  const config = cascadeChain.value[currentFieldId]
  if (!config) return
  
  const result = await boService.read(config.parentObject, currentValue)
  if (result.success) {
    const parentValue = result.data[config.parentField]
    if (parentValue) {
      formData[config.parentField] = parentValue
      await inferParentFields(config.parentField, parentValue)
    }
  }
}
```

---

## 8. 版本上下文集成

### 8.1 上下文已定时隐藏

```javascript
// 使用 useVersionContext 获取上下文
const { selectedVersionId } = useVersionContext()

// 过滤级联选项（版本内的数据）
async function loadCascadeOptions(fieldId, parentValue) {
  const config = cascadeChain.value[fieldId]
  const params = {
    [config.parentField]: parentValue,
    pageSize: 1000
  }
  
  // 添加版本上下文过滤
  if (selectedVersionId.value) {
    params.version_id = selectedVersionId.value
  }
  
  const result = await boService.query(config.parentObject, { filters: params })
  // ...
}
```

---

## 9. 实现清单

### 9.1 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1 | useCascadeSelect.js | `src/composables/useCascadeSelect.js` | ✅ |

### 9.2 待完成

| # | 任务 | 文件 | 依赖 |
|---|------|------|------|
| 1 | business_object.yaml 补充 cascade_select | `meta/schemas/business_object.yaml` | M18.1 ✅ |
| 2 | MetaForm 级联选项注入 | `src/components/common/MetaForm.vue` | useCascadeSelect ✅ |
| 3 | MetaForm 字段分组渲染 | `MetaForm.vue` | YAML fieldGroup ✅ |
| 4 | 版本上下文过滤 | useCascadeSelect | useVersionContext ✅ |
| 5 | 编辑时反向推断 | useCascadeSelect | - |
| 6 | 集成测试 | - | 全部完成 |

---

## 10. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | 创建 business_object: 5级级联正常 | 创建页面测试 |
| 2 | 父字段变更→下游自动清空 | 变更父字段测试 |
| 3 | 编辑模式下父字段 immutable | 编辑页面测试 |
| 4 | 版本上下文已定时过滤 | 切换版本测试 |
| 5 | 编辑时反向推断正常 | 编辑已有数据测试 |
| 6 | YAML cascade_select 是唯一配置来源 | 无硬编码对象名 |

---

## 11. 技术对比

### 11.1 重构前（DynamicForm）

```javascript
// 硬编码 CASCADE_PARAM_MAP
const CASCADE_PARAM_MAP = {
  'domain_id': 'version_id',
  'sub_domain_id': 'domain_id',
  'service_module_id': 'sub_domain_id',
}

// 硬编码关系
if (field.ui?.relation === 'sub_domain') {
  url = `/api/v1/domains/${parentId}/sub_domains`
}
```

### 11.2 重构后（useCascadeSelect）

```javascript
// 无硬编码
const params = {
  [config.parentField]: parentValue,
  pageSize: 1000
}
const result = await boService.query(config.parentObject, { filters: params })
```

---

## 12. 后续计划

| 里程碑 | 内容 | 依赖 |
|---------|------|------|
| M18.4 | ObjectTreePanel 树形导航 | M18.2 ✅ + M18.3 ✅ |
| M18.6 | 三栏布局整合 | M18.2 + M18.3 + M18.4 + M18.5 |

---

## 13. 变更记录

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2025-01-09 | 初始创建 | AI |
| 2025-01-09 | useCascadeSelect.js 创建完成 | AI |
