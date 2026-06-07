# 批次 3 细化实施方案 — FR-6 UI 完整适配

> **版本**: v1.0 | **日期**: 2026-06-07 | **状态**: 🟡 实施中
>
> 基于实际代码分析（2026-06-07），细化 v2 spec FR-6 的 7 子任务。

---

## 1. 代码现状分析

### 1.1 FR-6.1: 激活 field-policies API

| 文件 | 现状 | 改动 |
|------|------|------|
| `useFieldPolicy.js` L41-533 | `loadFieldPolicies()` 已实现但**无 `autoLoad()` 入口**、无 `policiesLoaded` ref | +10 行 |
| `useMetaList.js` L1340-1348 | 已导入 useFieldPolicy 但**只解构 `editableMap` 等 5 项**，未调 `loadFieldPolicies` | +3 行 |
| `ObjectDetailPage.vue` L301-314 | `loadEntityMeta()` 加载 UIConfig，**不调 field-policies API** | +5 行 |

### 1.2 FR-6.2: 暴露 requiredMap/editableMap/visibleMap

| 文件 | 现状 | 改动 |
|------|------|------|
| `useFieldPolicy.js` L506-532 | return 已含 `requiredMap, editableMap, visibleMap, immutableMap, readonlyAlwaysMap`（批次 2 成果） | 无需改动 |
| `ObjectPageField.vue` L139-141 | `isRequired(key)` 读 `fieldDefs[key]?.required === true`，不走 useFieldPolicy | 需新增 prop + 改造 |

### 1.3 FR-6.3: isRequiredByRow 重载

| 文件 | 现状 | 改动 |
|------|------|------|
| `useFieldPolicy.js` L379-401 | `isRequired(fieldId)` 存在，**无 row 参数重载** | +60 行（新函数 + evaluateCondition） |

### 1.4 FR-6.4: MetaListPage cell 渲染接入 display_values

| 文件 | 现状 | 改动 |
|------|------|------|
| `useMetaList.js` L1646-1652 | `getCellValue()` 已读 `row.display_values[fieldName]`（批次 2 FR-3.3） | 无需改动 |
| `MetaListPage.vue` L279 | `:value="getCellValue(row, column.prop)"`（仅 InlineEditCell 用） | 无需改动 |
| `MetaListPage.vue` L302-346 | 非 inline 分支用 `row[column.prop]` 直接，不走 display_values | +5 行 wrapper + 模板替换 |

### 1.5 FR-6.5: ObjectPageField 只读渲染接入 display_values

| 文件 | 现状 | 改动 |
|------|------|------|
| `ObjectPageField.vue` L149-157 | `getFieldDisplayValue()` 读 `${key}_display` / `${key}_name`，不读 `formData.display_values` | +5 行 |

### 1.6 FR-6.6: DetailSection 渲染接入 display_values

| 文件 | 现状 | 改动 |
|------|------|------|
| `DetailSection.vue` L406-425 | `getFieldDisplayValue()` 不读 `data.display_values` | +5 行 |

### 1.7 FR-6.7: MetaForm 集成 useFieldPolicy 支持条件必填

| 文件 | 现状 | 改动 |
|------|------|------|
| `MetaForm.vue` L185-210 | props 无 `fieldPolicy` | +2 行 prop |
| `MetaForm.vue` L275-304 | `validateField()` 仅判断 `field.required` | +15 行 |
| `MetaDialog.vue` L1-160 | 无 useFieldPolicy 导入，未传 fieldPolicy 给 MetaForm | +10 行 |

---

## 2. 实施顺序

```
FR-6.1 (useFieldPolicy 新增 autoLoad + useMetaList/ObjectDetailPage 调用)
  → FR-6.2 (ObjectPageField isRequired 改造)
  → FR-6.3 (isRequiredByRow 重载)
  → FR-6.4 (MetaListPage cell 渲染)
  → FR-6.5 (ObjectPageField display_values)
  → FR-6.6 (DetailSection display_values)
  → FR-6.7 (MetaForm + MetaDialog)
```

**理由**：
- 6.1 先做：激活 API 调用，为 6.2/6.3 提供数据
- 6.2 是 6.3 的前置（requiredMap 已存在，isRequiredByRow 是对它的扩展）
- 6.4/6.5/6.6 是独立渲染适配，可并行（但同文件冲突，顺序做）
- 6.7 最后：依赖 6.3 的 isRequiredByRow

---

## 3. 逐任务实施

### FR-6.1: 激活 field-policies API

**文件 1**: `src/composables/useFieldPolicy.js`

在 return 之前新增：

```js
/**
 * 🆕 v1 批次 3 / FR-6.1: 字段策略是否已加载
 */
const policiesLoaded = ref(false)

/**
 * 🆕 v1 批次 3 / FR-6.1: 自动加载入口
 * 列表页 / 详情页 mount 时调用，激活后端 field-policies API
 * 
 * @param {string} objectType - 对象类型 (如 'user', 'role')
 * @param {string} context - 上下文 (read|create|update)
 * @param {string} mutability - 可变性 (locked|extensible|fully_editable)
 * @returns {Promise<boolean>}
 */
async function autoLoad(objectType, context = 'read', mutability = null) {
  if (!objectType) return false
  policiesLoaded.value = false
  const ok = await loadFieldPolicies(objectType, context, mutability)
  policiesLoaded.value = ok
  return ok
}
```

并在 **return 中添加导出**：

```js
return {
  // ...
  autoLoad,           // 🆕 FR-6.1
  policiesLoaded,     // 🆕 FR-6.1
  // ...
}
```

**文件 2**: `src/composables/useMetaList.js` L1348

在 `useFieldPolicy(metaConfig, columns)` 解构后增加 autoLoad 调用：

```js
const {
  autoLoad,         // 🆕 FR-6.1
  // ... 原有
} = useFieldPolicy(metaConfig, columns)
```

在 `init()` 中 L367 `await _loadMetaConfig()` 之后加入：

```js
// 🆕 v1 批次 3 / FR-6.1: 激活 field-policies API
if (objectType && autoLoad) {
  autoLoad(objectType, 'read').catch(e => {
    console.warn('[useMetaList] autoLoad field-policies failed:', e)
  })
}
```

**文件 3**: `src/views/ObjectDetailPage.vue`

在 `loadEntityMeta()` L304 之后加入：

```js
// 🆕 v1 批次 3 / FR-6.1: 激活 field-policies API
import { useFieldPolicy } from '@/composables/useFieldPolicy'
// (在 setup 顶层)
const { autoLoad } = useFieldPolicy(
  computed(() => entityMeta.value),
  computed(() => [])
)
// 在 loadEntityMeta() 中 L306 之后:
if (objectType.value && autoLoad) {
  autoLoad(objectType.value, 'read').catch(e => {
    console.warn('[ObjectDetailPage] autoLoad field-policies failed:', e)
  })
}
```

---

### FR-6.2: ObjectPageField isRequired 改造

**文件**: `src/components/common/ObjectPage/ObjectPageField.vue`

**改造 L139-141**: 把 `isRequired` 从本地 `fieldDefs.required` 改为接受 `fieldPolicy` prop：

```js
// 新增 prop
const props = defineProps({
  // ... 原有 props
  fieldPolicy: {          // 🆕 FR-6.2: 外部 useFieldPolicy 注入
    type: Object,
    default: null
  }
})
```

**替换 L139-141 的 isRequired**:

```js
function isRequired(key) {
  // 🆕 FR-6.2: 优先走 useFieldPolicy.requiredMap（后端策略，非后端策略无此项）
  if (props.fieldPolicy?.requiredMap?.value?.[key] !== undefined) {
    return props.fieldPolicy.requiredMap.value[key] === true
  }
  // Fallback: 本地 fieldDefs
  return props.fieldDefs[key]?.required === true
}
```

**调用方改造**：所有使用 `<ObjectPageField>` 的组件需传入 `fieldPolicy` prop。但实际上 ObjectPageField 被 DetailPage 使用，DetailPage 被 ObjectDetailPage 使用。最简方案：ObjectPageField 保留 fallback（现有逻辑），传不传 fieldPolicy 都工作。

---

### FR-6.3: isRequiredByRow 重载

**文件**: `src/composables/useFieldPolicy.js`

在 `isRequired()` 函数之后（L401 后）新增两个函数：

```js
/**
 * 🆕 v1 批次 3 / FR-6.3: 条件必填评估器
 * 用 new Function + with(row) 沙箱评估条件表达式
 * 
 * @param {string} condition - 条件表达式 (如 "params.get('domain_id') is not None")
 * @param {Object} row - 行数据
 * @returns {boolean}
 */
function evaluateCondition(condition, row) {
  if (!condition || !row) return false
  try {
    // 安全沙箱：仅允许 row 属性访问
    const fn = new Function('row', `with(row) { return !!((${condition}) || false); }`)
    return Boolean(fn({ ...row }))
  } catch {
    return false
  }
}

/**
 * 🆕 v1 批次 3 / FR-6.3: 基于 row 上下文的重载 isRequired
 * 
 * 先调基础 isRequired(fieldId)，再检查 conditional_required 条件是否满足。
 * 任一满足则返回 true。
 * 
 * @param {string} fieldId - 字段标识
 * @param {Object} row - 行数据（用于条件评估）
 * @returns {boolean}
 */
function isRequiredByRow(fieldId, row = null) {
  // 1. 基础必填（后端 API + 本地 fallback）
  if (isRequired(fieldId)) return true

  // 2. 检查 requiredMap（批次 2 从 field-policies API 提取的 conditional_required）
  if (requiredMap.value && row) {
    const rules = requiredMap.value[fieldId]
    if (rules && Array.isArray(rules) && rules.length > 0) {
      for (const rule of rules) {
        if (rule.condition && evaluateCondition(rule.condition, row)) {
          return true
        }
      }
    }
  }

  // 3. Fallback: 检查 metaConfig 中的 conditional_required 声明
  if (metaConfig.value?.fields && row) {
    const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
    if (field?.conditional_required) {
      const rules = Array.isArray(field.conditional_required) 
        ? field.conditional_required 
        : [field.conditional_required]
      for (const rule of rules) {
        if (rule.condition && evaluateCondition(rule.condition, row)) {
          return true
        }
      }
    }
  }

  return false
}
```

**在 return 中添加导出**：

```js
return {
  // ...
  isRequiredByRow,     // 🆕 FR-6.3
  evaluateCondition,   // 🆕 FR-6.3 (供 MetaForm 独立复用)
}
```

---

### FR-6.4: MetaListPage cell 渲染接入 display_values

**文件**: `src/components/common/MetaListPage/MetaListPage.vue`

getCellValue 已从 useMetaList 导入（L715），已在 inline 编辑模式用（L279），已在 batch 2 中读取 display_values。

**新增 wrapper**（在 script 中已有 getCellValue 解构的位置附近）：

```js
/**
 * 🆕 v1 批次 3 / FR-6.4: 读取 display_value（优先后端注入）
 * getCellValue 已处理 display_values，此处薄封装供模板用
 */
function getCellDisplayValue(row, column) {
  return getCellValue(row, column.prop)
}
```

**模板改造**（L338-346，format 分支和默认分支）：把 `row[column.prop]` 替换为 `getCellDisplayValue(row, column)` 在适用处：

当前代码（L334-347）：
```html
<template v-else>
  <template v-if="column.format === 'datetime' || column.type === 'datetime'">
    {{ formatDate(row[column.prop]) }}
  </template>
  <template v-else-if="column.format === 'code' && row[column.prop]">
    <code class="cell-code-text">{{ row[column.prop] }}</code>
  </template>
  <template v-else-if="column.type === 'ellipsis'">
    <span class="ellipsis-text">{{ row[column.prop] || '-' }}</span>
  </template>
  <template v-else>
    {{ row[column.prop] ?? '-' }}
  </template>
</template>
```

改造后：
```html
<template v-else>
  <template v-if="column.format === 'datetime' || column.type === 'datetime'">
    {{ formatDate(getCellDisplayValue(row, column)) }}
  </template>
  <template v-else-if="column.format === 'code' && getCellDisplayValue(row, column)">
    <code class="cell-code-text">{{ getCellDisplayValue(row, column) }}</code>
  </template>
  <template v-else-if="column.type === 'ellipsis'">
    <span class="ellipsis-text">{{ getCellDisplayValue(row, column) || '-' }}</span>
  </template>
  <template v-else>
    {{ getCellDisplayValue(row, column) ?? '-' }}
  </template>
</template>
```

---

### FR-6.5: ObjectPageField 只读渲染接入 display_values

**文件**: `src/components/common/ObjectPage/ObjectPageField.vue`

**改造 L149-157** `getFieldDisplayValue()`:

```js
function getFieldDisplayValue(key) {
  // 🆕 v1 批次 3 / FR-6.5: 优先后端 display_values
  const dv = props.formData?.display_values?.[key]
  if (dv !== undefined && dv !== null) return dv

  // 原逻辑: `${key}_display` 或 `${key}_name`
  const displayKey = props.formData[`${key}_display`]
    ? `${key}_display`
    : `${key.replace(/_id$/, '')}_name`
  const displayValue = props.formData[displayKey]
  if (displayValue) return displayValue

  // 原值
  const value = props.formData[key]
  return value ?? ''
}
```

---

### FR-6.6: DetailSection 渲染接入 display_values

**文件**: `src/components/common/DetailPage/DetailSection.vue`

**改造 L406-425** `getFieldDisplayValue()`:

```js
function getFieldDisplayValue(field) {
  // 🆕 v1 批次 3 / FR-6.6: 优先后端 display_values
  if (props.data?.display_values?.[field.id] !== undefined) {
    return props.data.display_values[field.id]
  }

  const value = getFieldValue(field)
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  
  if (field.type === 'boolean') {
    return value ? '是' : '否'
  }
  
  if (field.display_field && props.data[field.display_field]) {
    return props.data[field.display_field]
  }
  
  if (field.formatter) {
    return field.formatter(value, props.data)
  }
  
  return value
}
```

---

### FR-6.7: MetaForm + MetaDialog 集成条件必填

**文件 1**: `src/components/common/MetaForm.vue`

**新增 prop**（在 L185 附近 props 定义中追加）:

```js
fieldPolicy: {    // 🆕 FR-6.7: useFieldPolicy 注入
  type: Object,
  default: null
}
```

**改造 L275-304** `validateField()`:

```js
function validateField(key) {
  const field = props.fields.find(f => f.key === key)
  if (!field) return true

  const visibilityFn = props.fieldVisibility[key]
  if (typeof visibilityFn === 'function' && !visibilityFn(formData)) {
    delete errors[key]
    return true
  }

  const val = formData[key]

  // 🆕 v1 批次 3 / FR-6.7: 条件必填检查（后端 conditional_required 联动）
  if (props.fieldPolicy?.isRequiredByRow) {
    const isConditionallyRequired = props.fieldPolicy.isRequiredByRow(key, formData)
    if (isConditionallyRequired) {
      if (val == null || String(val).trim() === '') {
        const rules = props.fieldPolicy.requiredMap?.value?.[key]
        const msg = rules?.[0]?.message || `${field.label}不能为空`
        errors[key] = msg
        return false
      }
    }
  } else if (field.required && (val == null || String(val).trim() === '')) {
    // 原必填逻辑：仅在无 fieldPolicy 时生效
    errors[key] = field.requiredMessage || `${field.label}不能为空`
    return false
  }

  if (field.rules && Array.isArray(field.rules)) {
    for (const rule of field.rules) {
      const result = rule(val, formData)
      if (result !== true && result !== undefined) {
        errors[key] = typeof result === 'string' ? result : `${field.label}格式不正确`
        return false
      }
    }
  }

  delete errors[key]
  return true
}
```

**文件 2**: `src/components/common/MetaDialog.vue`

**script 改造**（在 import 区域新增）:

```js
import { useFieldPolicy, computed } from 'vue'
// ... 原有 imports

const { autoLoad, isRequiredByRow, requiredMap } = useFieldPolicy(
  computed(() => props.meta),
  computed(() => metaFields.value)
)
```

**在 `handleSave` 前新增 lifecycle**:

```js
// 🆕 FR-6.7: 表单挂载时激活 field-policies API（create/update 上下文）
import { onMounted } from 'vue'

onMounted(() => {
  // MetaDialog 无 objectType prop，从 meta.label 推断
  // 实际 objectType 由调用方提供，暂时跳过
})
```

注：MetaDialog 缺少 `objectType` prop，暂不启用 autoLoad。条件必填本已通过 `MetaForm` 的 `fieldPolicy` prop 接收。

**template 改造**（L9-22），传入 fieldPolicy:

```html
<MetaForm
  v-if="visible"
  ref="formRef"
  key="meta-form"
  :fields="metaFields"
  :model-value="initialFormData"
  :layout="formLayout"
  :label-position="labelPosition"
  :field-policy="fieldPolicy"   <!-- 🆕 FR-6.7 -->
  @update:model-value="handleDataChange"
>
```

**script 中定义 fieldPolicy computed**:

```js
const fieldPolicy = computed(() => ({
  isRequiredByRow,
  requiredMap
}))
```

---

## 4. 改动清单总览

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| 6.1a | `useFieldPolicy.js` | +`autoLoad()` + `policiesLoaded` ref + return 导出 | +20 |
| 6.1b | `useMetaList.js` | 解构 autoLoad + `init()` 中调用 | +5 |
| 6.1c | `ObjectDetailPage.vue` | import useFieldPolicy + `loadEntityMeta()` 中调用 autoLoad | +10 |
| 6.2 | `ObjectPageField.vue` | +`fieldPolicy` prop + `isRequired()` 改造 | +10 |
| 6.3 | `useFieldPolicy.js` | +`evaluateCondition()` + `isRequiredByRow()` + return 导出 | +60 |
| 6.4 | `MetaListPage.vue` | +`getCellDisplayValue()` wrapper + 模板替换 6 处 | +10 |
| 6.5 | `ObjectPageField.vue` | `getFieldDisplayValue()` 优先读 `formData.display_values` | +5 |
| 6.6 | `DetailSection.vue` | `getFieldDisplayValue()` 优先读 `props.data.display_values` | +5 |
| 6.7a | `MetaForm.vue` | +`fieldPolicy` prop + `validateField()` 集成 `isRequiredByRow` | +20 |
| 6.7b | `MetaDialog.vue` | +`useFieldPolicy` + `fieldPolicy` computed + 传参 MetaForm | +10 |

**总计**: 10 文件, ~155 行改动。

---

## 5. 安全保证

- **Fallback**：所有改动都保留原逻辑，后端不返回时不影响功能
- **渐进式接入**：6.1 激活 API 后，6.2-6.7 按优先级消费
- **条件评估隔离**：`evaluateCondition` 用 `new Function()` 沙箱
- **不破坏现有渲染**：display_values 读不到就走原分支
- **MetaForm 兼容**：不传 fieldPolicy 时走原 `field.required` 逻辑

---

## 6. 验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| 6.1 | `useFieldPolicy` 有 `autoLoad` / `policiesLoaded` | grep 源码 |
| 6.1 | `useMetaList.init()` 调用 `autoLoad` | grep 调用链 |
| 6.1 | `ObjectDetailPage.loadEntityMeta()` 调用 `autoLoad` | grep 调用链 |
| 6.2 | `ObjectPageField.isRequired` 读 `fieldPolicy.requiredMap` | grep 源码 |
| 6.2 | 无 `fieldPolicy` 时 fallback 到 `fieldDefs.required` | 代码逻辑 |
| 6.3 | `isRequiredByRow` 在 row 包含条件字段时返回 true | 代码逻辑 |
| 6.3 | 条件不满足时返回 false | 代码逻辑 |
| 6.4 | `getCellDisplayValue` 封装 `getCellValue` | grep 源码 |
| 6.5 | `getFieldDisplayValue` 读 `formData.display_values` | grep 源码 |
| 6.6 | `getFieldDisplayValue` 读 `props.data.display_values` | grep 源码 |
| 6.7 | `MetaForm.validateField` 调 `fieldPolicy.isRequiredByRow` | grep 源码 |
| 6.7 | `MetaDialog` 传 `fieldPolicy` 给 `MetaForm` | grep 模板 |
