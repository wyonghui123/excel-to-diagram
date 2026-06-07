# MetaList Inline Editing 组件设计方案

**版本**: v1.0  
**日期**: 2026-05-13  
**状态**: 待实现

---

## 1. 功能概述

在 MetaList 列表组件内支持 **行内编辑（Inline Editing）** 功能，允许用户直接在表格单元格中修改数据，无需跳转到详情页。

**参考案例**：
- SAP Fiori Elements: Inline Edit / Mass Edit
- Salesforce Lightning: lightning-datatable inline editing (Quick Edit / Direct Entry)

---

## 2. 设计理念

### 2.1 两种编辑模式

| 模式 | 描述 | 适用场景 | 参考 |
|------|------|----------|------|
| **Quick Edit** | 悬停显示铅笔图标，点击进入编辑，Tab切换，Enter保存 | 偶尔修改少量数据 | SAP Fiori / Salesforce |
| **Direct Entry** | 单元格直接显示输入框，输入即编辑 | 大量数据录入 | Salesforce |

### 2.2 核心原则

- **渐进增强**：默认只读模式，配置后才启用编辑功能
- **配置驱动**：所有行为由元数据 YAML 配置控制
- **状态隔离**：编辑中的数据与原始数据分离
- **批量操作**：支持多行编辑后一次性保存

---

## 3. 配置规范

### 3.1 设计原则：单一事实来源

**核心原则**：字段的基础定义只在 `columns` 中存在，`inlineEdit` 只配置模式级别选项。

```
columns        → 字段定义（单一事实来源）
inlineEdit     → 编辑模式配置（不重复定义字段）
```

### 3.2 YAML 配置示例

```yaml
# enum_value.yaml
ui_view_config:
  list:
    # 字段定义（单一事实来源）
    columns:
      - name: display_name
        label: 显示名称
        width: 150
        editable: true                    # 可编辑标记
        
      - name: sort_order
        label: 排序号
        width: 80
        type: number
        editable: true
        
      - name: is_active
        label: 启用状态
        width: 80
        type: switch
        editable: true
        edit_default_value: true          # 编辑时的默认值
        
      - name: is_default
        label: 默认值
        width: 80
        type: checkbox
        editable: true
        edit_condition: "${row.mutability !== 'system'}"  # 动态编辑条件
        
      - name: status
        label: 状态
        width: 100
        type: select
        editable: true
        options:
          - value: active
            label: 激活
          - value: inactive
            label: 停用

    # Inline Edit 模式配置（只配置模式级别选项）
    inlineEdit:
      enabled: true                       # 是否启用行内编辑
      mode: quick                         # quick | direct
      autoSave: false                     # 是否失焦自动保存（默认false）
      toolbarPosition: bottom             # top | bottom
```

### 3.3 字段编辑相关属性

以下属性定义在 `columns` 中，用于控制字段的编辑行为：

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `editable` | boolean | 是否可编辑 | `true` |
| `edit_type` | string | 编辑输入类型（覆盖字段类型） | `text`, `number`, `switch` |
| `edit_condition` | string | 动态编辑条件表达式 | `${row.mutability !== 'system'}` |
| `edit_default_value` | any | 编辑时的默认值 | `true` |
| `edit_options` | array | 编辑时的选项（覆盖字段选项） | `[{value, label}]` |
| `edit_placeholder` | string | 编辑输入框占位符 | `"请输入"` |
| `edit_required` | boolean | 编辑时是否必填 | `true` |

### 3.4 类型自动推断规则

编辑输入类型根据字段 `type` 自动推断，无需显式指定 `edit_type`：

| 字段 type | 推断 edit_type | 输入组件 |
|-----------|----------------|----------|
| `text` / `string` | `text` | el-input |
| `number` / `integer` | `number` | el-input-number |
| `boolean` | `switch` | el-switch |
| `select` / `enum` | `select` | el-select |
| `date` | `date` | el-date-picker |
| `datetime` | `datetime` | el-date-picker |

### 3.5 条件表达式

支持 `${row.fieldName}` 模板语法，用于动态控制字段是否可编辑：

```yaml
edit_condition: "${row.mutability !== 'system'}"
edit_condition: "${row.is_editable === true}"
edit_condition: "${row.category === 'user'}"
```

表达式求值逻辑：
```javascript
// 将模板转换为可执行表达式
const expression = condition.replace(/\$\{row\.(\w+)\}/g, (_, field) => {
  return JSON.stringify(row[field])
})
return eval(expression)  // 返回 true/false
```

---

## 4. 组件架构

### 4.1 文件结构

```
src/components/common/MetaListPage/
├── MetaListPage.vue              # 主组件（已存在，修改）
├── InlineEditCell.vue            # 可编辑单元格
├── InlineEditToolbar.vue          # 编辑工具栏
└── composables/
    └── useInlineEdit.js          # Inline Edit Composable（可合并到useMetaList.js）
```

### 4.2 组件层次

```
MetaListPage.vue
├── Toolbar (工具栏)
├── AdvancedFilterPanel (高级筛选)
├── el-table (表格)
│   ├── el-table-column (列)
│   │   └── InlineEditCell.vue (可编辑单元格)
│   │       ├── QuickEditCell.vue (悬停编辑模式)
│   │       └── DirectEditCell.vue (直接输入模式)
│   └── el-table-column (操作列)
├── Pagination (分页)
└── InlineEditToolbar.vue (编辑工具栏，浮动)
```

---

## 5. 状态管理

### 5.1 新增状态（useMetaList.js 或 useInlineEdit.js）

```javascript
// ======== Inline Edit 状态 ========

/** Inline Edit 配置（从元数据解析） */
const inlineEditConfig = ref({
  enabled: false,
  mode: 'quick',           // 'quick' | 'direct'
  autoSave: false,
  toolbarPosition: 'bottom',
  fields: []
})

/** 是否处于编辑模式 */
const editMode = ref(false)

/** 编辑中的草稿值 Map<rowId, Map<fieldName, { oldValue, newValue }>> */
const draftValues = ref(new Map())

/** 当前正在编辑的单元格 { rowId, fieldName } */
const editingCell = ref(null)

/** 当前悬停的行/列 { rowId, fieldName } */
const hoveredCell = ref(null)

// ======== 计算属性 ========

/** 是否有未保存的修改 */
const hasUnsavedChanges = computed(() => draftValues.value.size > 0)

/** 获取当前编辑模式的组件 */
const editCellComponent = computed(() => {
  return inlineEditConfig.value.mode === 'quick' 
    ? 'QuickEditCell' 
    : 'DirectEditCell'
})
```

### 5.2 新增方法

```javascript
// ======== Inline Edit 方法 ========

/**
 * 启用编辑模式
 */
function enableInlineEdit() {
  editMode.value = true
}

/**
 * 禁用编辑模式（会提示保存）
 */
async function disableInlineEdit() {
  if (hasUnsavedChanges.value) {
    const confirmed = await ElMessageBox.confirm(
      '有未保存的修改，是否放弃？',
      '提示',
      { type: 'warning' }
    )
    if (!confirmed) return false
  }
  cancelEdit()
  editMode.value = false
  return true
}

/**
 * 开始编辑单元格
 * @param {Object} row - 行数据
 * @param {string} fieldName - 字段名
 */
function startEditCell(row, fieldName) {
  editingCell.value = { rowId: row.id, fieldName }
}

/**
 * 结束当前单元格编辑
 * @param {boolean} save - 是否保存
 */
function finishEditCell(save = true) {
  if (!editingCell.value) return
  
  const { rowId, fieldName } = editingCell.value
  
  if (save) {
    // draftValues 已在 v-model 中更新
  } else {
    // 恢复旧值
    cancelCellEdit(rowId, fieldName)
  }
  
  editingCell.value = null
}

/**
 * 更新单元格草稿值
 * @param {string} rowId - 行ID
 * @param {string} fieldName - 字段名
 * @param {any} newValue - 新值
 */
function updateDraftValue(rowId, fieldName, newValue) {
  const rowDrafts = draftValues.value.get(rowId) || {}
  rowDrafts[fieldName] = newValue
  draftValues.value.set(rowId, rowDrafts)
}

/**
 * 取消单元格编辑
 */
function cancelCellEdit(rowId, fieldName) {
  const rowDrafts = draftValues.value.get(rowId)
  if (rowDrafts) {
    delete rowDrafts[fieldName]
    if (Object.keys(rowDrafts).length === 0) {
      draftValues.value.delete(rowId)
    }
  }
}

/**
 * 取消所有编辑
 */
function cancelEdit() {
  draftValues.value.clear()
  editingCell.value = null
}

/**
 * 保存所有编辑
 */
async function saveDraftValues() {
  if (draftValues.value.size === 0) return
  
  loading.value = true
  try {
    const updates = []
    for (const [rowId, fields] of draftValues.value.entries()) {
      for (const [fieldName, newValue] of Object.entries(fields)) {
        updates.push({
          id: rowId,
          [fieldName]: newValue
        })
      }
    }
    
    const result = await boService.batchUpdate(objectType.value, updates)
    
    if (result.success) {
      ElMessage.success(`成功保存 ${updates.length} 项修改`)
      draftValues.value.clear()
      await refresh()
    } else {
      throw new Error(result.message)
    }
  } catch (e) {
    handleError('保存修改', e)
  } finally {
    loading.value = false
  }
}

/**
 * 判断单元格是否可编辑
 * @param {Object} row - 行数据
 * @param {string} fieldName - 字段名
 */
function isCellEditable(row, fieldName) {
  if (!inlineEditConfig.value.enabled) return false
  
  // 从 columns 中获取字段配置（单一事实来源）
  const column = columns.value.find(c => c.prop === fieldName || c.name === fieldName)
  if (!column || !column.editable) return false
  
  // 检查条件表达式
  if (column.edit_condition) {
    const template = column.edit_condition
    const expression = template.replace(/\$\{row\.(\w+)\}/g, (_, field) => {
      return JSON.stringify(row[field])
    })
    try {
      return eval(expression)
    } catch {
      return false
    }
  }
  
  return true
}

/**
 * 获取字段编辑配置
 * @param {string} fieldName - 字段名
 */
function getFieldEditConfig(fieldName) {
  const column = columns.value.find(c => c.prop === fieldName || c.name === fieldName)
  if (!column) return null
  
  // 类型自动推断
  const typeInferMap = {
    'text': 'text',
    'string': 'text',
    'number': 'number',
    'integer': 'number',
    'boolean': 'switch',
    'select': 'select',
    'enum': 'select',
    'date': 'date',
    'datetime': 'datetime'
  }
  
  return {
    type: column.edit_type || typeInferMap[column.type] || 'text',
    options: column.edit_options || column.options,
    placeholder: column.edit_placeholder,
    defaultValue: column.edit_default_value,
    required: column.edit_required
  }
}

/**
 * 获取单元格显示值（优先草稿值）
 */
function getCellValue(row, fieldName) {
  const draftRow = draftValues.value.get(row.id)
  if (draftRow && fieldName in draftRow) {
    return draftRow[fieldName]
  }
  return row[fieldName]
}

/**
 * 判断单元格是否正在编辑
 */
function isEditing(rowId, fieldName) {
  return editingCell.value?.rowId === rowId && editingCell.value?.fieldName === fieldName
}

/**
 * 判断单元格是否被悬停
 */
function isHovered(rowId, fieldName) {
  return hoveredCell.value?.rowId === rowId && hoveredCell.value?.fieldName === fieldName
}
```

---

## 6. 视图层实现

### 6.1 单元格模板（el-table-column #default slot）

```vue
<template #default="{ row }">
  <!-- 动态插槽：优先使用自定义插槽 -->
  <slot 
    v-if="$slots[`cell-${column.prop}`]" 
    :name="`cell-${column.prop}`" 
    :row="row" 
    :column="column" 
    :editing="isEditing(row.id, column.prop)"
  />

  <!-- Inline Edit 单元格 -->
  <InlineEditCell
    v-else-if="isCellEditable(row, column.prop) && editMode"
    :row="row"
    :field-name="column.prop"
    :field-config="getFieldEditConfig(column.prop)"
    :value="getCellValue(row, column.prop)"
    :editing="isEditing(row.id, column.prop)"
    :hovered="isHovered(row.id, column.prop)"
    :mode="inlineEditConfig.mode"
    @hover="hoveredCell = { rowId: row.id, fieldName: column.prop }"
    @leave="hoveredCell = null"
    @start-edit="startEditCell(row, column.prop)"
    @finish-edit="finishEditCell(true)"
    @cancel-edit="finishEditCell(false)"
    @update:value="(val) => updateDraftValue(row.id, column.prop, val)"
  />

  <!-- 只读单元格 -->
  <template v-else>
    <template v-if="column.format === 'datetime'">
      {{ formatDate(row[column.prop]) }}
    </template>
    <template v-else-if="column.type === 'ellipsis'">
      <span class="ellipsis-text">{{ row[column.prop] ?? '-' }}</span>
    </template>
    <template v-else>
      {{ row[column.prop] ?? '-' }}
    </template>
  </template>
</template>
```

### 6.2 InlineEditCell 组件

```vue
<!-- InlineEditCell.vue -->
<template>
  <div 
    class="inline-edit-cell"
    :class="{ 
      'is-editing': editing,
      'is-hovered': hovered && !editing,
      'is-quick-mode': mode === 'quick',
      'is-direct-mode': mode === 'direct'
    }"
    @mouseenter="$emit('hover')"
    @mouseleave="$emit('leave')"
  >
    <!-- Quick Edit: 悬停显示编辑图标 -->
    <template v-if="mode === 'quick'">
      <span v-if="!editing" class="cell-display">
        <span class="cell-value">{{ displayValue }}</span>
        <el-icon 
          v-if="hovered" 
          class="edit-icon" 
          @click.stop="$emit('start-edit')"
        >
          <Edit />
        </el-icon>
      </span>
      
      <component
        v-else
        :is="inputComponent"
        :model-value="modelValue"
        v-bind="inputProps"
        size="small"
        @update:model-value="$emit('update:value', $event)"
        @blur="$emit('finish-edit')"
        @keyup.enter="$emit('finish-edit')"
        @keyup.escape="$emit('cancel-edit')"
      />
    </template>

    <!-- Direct Entry: 直接显示输入框 -->
    <template v-else>
      <component
        :is="inputComponent"
        :model-value="modelValue"
        v-bind="inputProps"
        size="small"
        :class="{ 'is-editing': true }"
        @update:model-value="$emit('update:value', $event)"
        @blur="handleBlur"
        @focus="handleFocus"
      />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Edit, Check, Close } from '@element-plus/icons-vue'

const props = defineProps({
  row: Object,
  fieldName: String,
  fieldConfig: Object,
  value: [String, Number, Boolean],
  editing: Boolean,
  hovered: Boolean,
  mode: {
    type: String,
    default: 'quick'  // 'quick' | 'direct'
  }
})

const emit = defineEmits([
  'hover', 'leave', 'start-edit', 'finish-edit', 
  'cancel-edit', 'update:value'
])

// 根据字段类型获取输入组件
const inputComponent = computed(() => {
  const typeMap = {
    'text': 'el-input',
    'number': 'el-input-number',
    'switch': 'el-switch',
    'checkbox': 'el-checkbox',
    'select': 'el-select',
    'date': 'el-date-picker',
    'datetime': 'el-date-picker'
  }
  return typeMap[props.fieldConfig?.type] || 'el-input'
})

// 输入组件属性
const inputProps = computed(() => {
  const type = props.fieldConfig?.type
  const result = {}
  
  switch (type) {
    case 'number':
      result.precision = 0
      result.controls = false
      break
    case 'select':
      result.placeholder = '请选择'
      result.clearable = true
      break
    case 'date':
      result.type = 'date'
      result.placeholder = '请选择日期'
      result.format = 'YYYY-MM-DD'
      break
    case 'datetime':
      result.type = 'datetime'
      result.placeholder = '请选择时间'
      result.format = 'YYYY-MM-DD HH:mm:ss'
      break
    case 'switch':
    case 'checkbox':
      result.active-text = ''
      result.inactive-text = ''
      break
  }
  
  return result
})

// 显示值
const displayValue = computed(() => {
  if (props.value == null) return '-'
  if (props.fieldConfig?.type === 'switch') {
    return props.value ? '是' : '否'
  }
  if (props.fieldConfig?.type === 'select') {
    const opt = props.fieldConfig.options?.find(o => o.value === props.value)
    return opt?.label || props.value
  }
  return props.value
})

function handleBlur() {
  if (props.mode === 'direct') {
    emit('finish-edit')
  }
}

function handleFocus() {
  emit('start-edit')
}
</script>

<style scoped>
.inline-edit-cell {
  position: relative;
  min-height: 28px;
  display: flex;
  align-items: center;
}

.inline-edit-cell.is-hovered .edit-icon {
  opacity: 1;
}

.inline-edit-cell.is-editing {
  background: #fff8e6;
}

.edit-icon {
  margin-left: 4px;
  color: var(--el-color-primary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.cell-value {
  flex: 1;
}

.is-direct-mode .cell-value {
  display: none;
}

.is-direct-mode .el-input,
.is-direct-mode .el-input-number,
.is-direct-mode .el-select {
  width: 100%;
}
</style>
```

### 6.3 InlineEditToolbar 组件

```vue
<!-- InlineEditToolbar.vue -->
<template>
  <transition name="toolbar-slide">
    <div v-if="show" class="inline-edit-toolbar" :class="position">
      <div class="toolbar-content">
        <el-icon class="warning-icon"><WarningFilled /></el-icon>
        <span class="draft-count">
          {{ draftCount }} 项已修改
        </span>
        <el-divider direction="vertical" />
        <el-button size="small" @click="$emit('cancel')">
          取消
        </el-button>
        <el-button 
          type="primary" 
          size="small" 
          :loading="saving"
          @click="$emit('save')"
        >
          保存
        </el-button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { WarningFilled } from '@element-plus/icons-vue'

defineProps({
  show: Boolean,
  draftCount: Number,
  position: {
    type: String,
    default: 'bottom'  // 'top' | 'bottom'
  },
  saving: Boolean
})

defineEmits(['save', 'cancel'])
</script>

<style scoped>
.inline-edit-toolbar {
  position: sticky;
  left: 0;
  z-index: 100;
  background: #fff;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 4px;
  padding: 8px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.inline-edit-toolbar.bottom {
  bottom: 80px;
  margin-top: -40px;
}

.inline-edit-toolbar.top {
  top: 0;
  margin-bottom: -40px;
}

.toolbar-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.warning-icon {
  color: var(--el-color-warning);
}

.draft-count {
  font-size: 14px;
  color: var(--el-color-text-regular);
}

.toolbar-slide-enter-active,
.toolbar-slide-leave-active {
  transition: all 0.3s ease;
}

.toolbar-slide-enter-from,
.toolbar-slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
```

---

## 7. 交互流程

### 7.1 Quick Edit 模式

```
1. 用户悬停单元格 → 显示铅笔图标
2. 用户点击编辑图标 → 进入编辑状态，单元格变黄
3. 用户修改值 → 实时更新草稿
4. 用户按 Tab / Enter → 保存当前单元格，切换到下一个可编辑单元格
5. 用户按 Escape → 取消当前编辑
6. 用户点击单元格外部 → 保存当前编辑
7. 系统底部显示工具栏 → "3 项已修改 | 取消 | 保存"
8. 用户点击保存 → 批量更新所有草稿值
```

### 7.2 Direct Entry 模式

```
1. 用户直接看到输入框 → 可立即编辑
2. 用户输入值 → 实时更新草稿
3. 用户按 Tab → 切换到下一个输入框，自动保存当前值
4. 系统底部显示工具栏 → "3 项已修改 | 取消 | 保存"
5. 用户点击保存 → 批量更新所有草稿值
```

---

## 8. 与现有组件集成

### 8.1 useMetaList.js 扩展

在 `useMetaList.js` 的 `return` 中新增：

```javascript
// Inline Edit 相关
inlineEditConfig,
editMode,
draftValues,
editingCell,
hoveredCell,
hasUnsavedChanges,

// 方法
enableInlineEdit,
disableInlineEdit,
startEditCell,
finishEditCell,
updateDraftValue,
cancelEdit,
saveDraftValues,
isCellEditable,
getCellValue,
isEditing,
isHovered,
getFieldEditConfig
```

### 8.2 MetaListPage.vue 修改

在表格列的 `#default` slot 中添加 InlineEditCell 逻辑：

```vue
<template #default="{ row }">
  <!-- 新增: Inline Edit 单元格 -->
  <InlineEditCell
    v-if="isCellEditable(row, column.prop) && editMode"
    :row="row"
    :field-name="column.prop"
    :field-config="getFieldEditConfig(column.prop)"
    :value="getCellValue(row, column.prop)"
    :editing="isEditing(row.id, column.prop)"
    :hovered="isHovered(row.id, column.prop)"
    :mode="inlineEditConfig.mode"
    @hover="hoveredCell = { rowId: row.id, fieldName: column.prop }"
    @leave="hoveredCell = null"
    @start-edit="startEditCell(row, column.prop)"
    @finish-edit="finishEditCell(true)"
    @update:value="(val) => updateDraftValue(row.id, column.prop, val)"
  />

  <!-- 原有: 自定义插槽 -->
  <slot 
    v-else-if="$slots[`cell-${column.prop}`]" 
    :name="`cell-${column.prop}`" 
    :row="row" 
    :column="column" 
  />

  <!-- 原有: 默认渲染 -->
  <template v-else>
    ...
  </template>
</template>
```

在表格下方添加 InlineEditToolbar：

```vue
<!-- 在 el-table 后，pagination 前 -->
<InlineEditToolbar
  :show="hasUnsavedChanges"
  :draft-count="draftValues.size"
  :position="inlineEditConfig.toolbarPosition"
  :saving="loading"
  @save="saveDraftValues"
  @cancel="cancelEdit"
/>
```

---

## 9. 实现步骤

### Phase 1: 基础状态管理
- [ ] 在 `useMetaList.js` 中添加 inline edit 状态
- [ ] 实现基础方法（enableInlineEdit, disableInlineEdit, isCellEditable 等）
- [ ] 从元数据解析 inlineEditConfig

### Phase 2: 单元格组件
- [ ] 创建 `InlineEditCell.vue` 组件
- [ ] 实现 Quick Edit 模式
- [ ] 实现 Direct Entry 模式
- [ ] 支持多种输入类型（text, number, switch, select 等）

### Phase 3: 工具栏组件
- [ ] 创建 `InlineEditToolbar.vue` 组件
- [ ] 实现显示/隐藏动画
- [ ] 实现保存/取消逻辑

### Phase 4: 集成测试
- [ ] 在 `MetaListPage.vue` 中集成 InlineEditCell
- [ ] 测试 Quick Edit 模式
- [ ] 测试 Direct Entry 模式
- [ ] 测试批量保存
- [ ] 测试条件表达式

---

## 10. 测试用例

### 10.1 Quick Edit 测试

```
1. 悬停可编辑单元格 → 显示铅笔图标
2. 悬停不可编辑单元格 → 不显示图标
3. 点击编辑图标 → 单元格进入编辑状态
4. 修改值 → 底部工具栏显示修改数量
5. 按 Tab → 保存当前，切换到下一个
6. 按 Escape → 取消当前编辑
7. 点击保存 → 调用 batchUpdate
8. 保存成功 → 刷新列表
```

### 10.2 Direct Entry 测试

```
1. 进入页面 → 所有可编辑单元格显示输入框
2. 输入值 → 实时更新草稿
3. 按 Tab → 自动保存，切换到下一个
4. 点击保存 → 调用 batchUpdate
```

### 10.3 条件编辑测试

```
1. system 类型的枚举值 → is_default 字段不可编辑
2. user 类型的枚举值 → is_default 字段可编辑
```

---

## 11. 参考资料

- [SAP Fiori Inline Edit](https://jerry.blog.csdn.net/article/details/152716803)
- [SAP Fiori Mass Edit](https://qiita.com/tami/items/3e0742da9d9a2ac8d620)
- [Salesforce Lightning Data Table](https://developer.salesforce.com/docs/platform/lwc/guide/data-table-inline-edit.html)
- [Avonni Data Table Inline Editing](https://docs.avonnicomponents.com/dynamic-components/tutorials/components/data-table/enable-inline-editing)

---

## 12. 负责人

- **UI Agent**: 实现 InlineEditCell.vue, InlineEditToolbar.vue
- **Logic Agent**: 扩展 useMetaList.js
- **Integration**: MetaListPage.vue 集成
