<template>
  <div 
    class="inline-edit-cell"
    :class="{ 
      'is-editing': editing,
      'is-hovered': hovered && !editing,
      'is-quick-mode': mode === 'quick',
      'is-direct-mode': mode === 'direct',
      'is-modified': isModified && !immutable,
      'is-immutable': !editable,
      'is-editable': editable,
      'is-required': fieldConfig?.required
    }"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
  >
    <!-- Quick Edit 模式: 悬停显示编辑图标（仅可编辑字段） -->
    <template v-if="mode === 'quick'">
      <span v-if="!editing" class="cell-display" :class="{ 'not-editable': !editable }" @click="handleCellClick">
        <span v-if="fieldConfig?.required" class="required-star">*</span>
        <span class="cell-value">{{ displayValue }}</span>
        <el-icon 
          v-if="hovered && editable" 
          class="edit-icon" 
          @click.stop="handleStartEdit"
        >
          <Edit />
        </el-icon>
      </span>
      
      <div v-else class="cell-editor">
        <ValueHelpField
          v-if="fieldConfig.type === 'value_help'"
          :model-value="currentValue"
          :value-help-config="fieldConfig.valueHelpConfig"
          :form-values="row"
          @update:model-value="handleValueChange"
        />
        <el-select
          v-else-if="fieldConfig.type === 'select'"
          ref="inputRef"
          :model-value="currentValue"
          v-bind="inputProps"
          size="small"
          @change="handleSelectChange"
          @blur="handleBlur"
          @keyup.escape="handleCancelEdit"
        >
          <el-option
            v-for="opt in fieldConfig.options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <component
          v-else
          :is="inputComponent"
          ref="inputRef"
          :model-value="currentValue"
          v-bind="inputProps"
          size="small"
          @update:model-value="handleValueChange"
          @blur="handleBlur"
          @keyup.enter="handleFinishEdit"
          @keyup.escape="handleCancelEdit"
          @keydown.tab="handleTab"
        />
      </div>
    </template>

    <!-- Direct Entry 模式 -->
    <template v-else>
      <!-- 不可编辑字段: 显示只读文本 -->
      <span v-if="!editable" class="cell-display not-editable">
        <span v-if="fieldConfig?.required" class="required-star">*</span>
        <span class="cell-value">{{ displayValue }}</span>
      </span>

      <!-- 可编辑字段: 显示输入控件 -->
      <template v-else>
        <ValueHelpField
          v-if="fieldConfig.type === 'value_help'"
          :model-value="currentValue"
          :value-help-config="fieldConfig.valueHelpConfig"
          :form-values="row"
          @update:model-value="handleValueChange"
        />
        <el-select
          v-else-if="fieldConfig.type === 'select'"
          :model-value="currentValue"
          v-bind="inputProps"
          size="small"
          class="direct-input"
          @change="handleSelectChange"
          @focus="handleFocus"
        >
          <el-option
            v-for="opt in fieldConfig.options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <component
          v-else
          :is="inputComponent"
          :model-value="currentValue"
          v-bind="inputProps"
          size="small"
          class="direct-input"
          @update:model-value="handleValueChange"
          @focus="handleFocus"
        />
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, reactive } from 'vue'
import { Edit } from '@element-plus/icons-vue'
import ValueHelpField from '@/components/common/ValueHelpField.vue'
import { boService } from '@/services/boService.js'
import { formatDate } from '@/composables/useMetaList'

const props = defineProps({
  row: {
    type: Object,
    required: true
  },
  fieldName: {
    type: String,
    required: true
  },
  fieldConfig: {
    type: Object,
    default: () => ({})
  },
  value: {
    type: [String, Number, Boolean, null],
    default: null
  },
  editing: {
    type: Boolean,
    default: false
  },
  hovered: {
    type: Boolean,
    default: false
  },
  mode: {
    type: String,
    default: 'quick',
    validator: (v) => ['quick', 'direct'].includes(v)
  },
  originalValue: {
    type: [String, Number, Boolean, null],
    default: undefined
  },
  immutable: {
    type: Boolean,
    default: false
  },
  editable: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'hover',
  'leave',
  'start-edit',
  'finish-edit',
  'cancel-edit',
  'update:value'
])

const inputRef = ref(null)
const currentValue = ref(props.value)
const isInternalChange = ref(false)

watch(() => props.value, (newVal) => {
  if (!isInternalChange.value) {
    currentValue.value = newVal
  }
})

const isModified = computed(() => {
  const original = props.originalValue !== undefined ? props.originalValue : props.row[props.fieldName]
  if ((currentValue.value == null && original == null) ||
      (currentValue.value === '' && original == null) ||
      (currentValue.value == null && original === '')) {
    return false
  }
  return currentValue.value !== original
})

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

const inputProps = computed(() => {
  const type = props.fieldConfig?.type
  const result = {}

  if (!props.editable) {
    result.disabled = true
  }
  
  switch (type) {
    case 'number':
      result.precision = 0
      result.controls = false
      result.style = 'width: 100%'
      break
    case 'select':
      result.placeholder = props.fieldConfig?.placeholder || '请选择'
      result.clearable = true
      result.style = 'width: 100%'
      break
    case 'date':
      result.type = 'date'
      result.placeholder = props.fieldConfig?.placeholder || '请选择日期'
      result.format = 'YYYY-MM-DD'
      result.valueFormat = 'YYYY-MM-DD'
      result.style = 'width: 100%'
      break
    case 'datetime':
      result.type = 'datetime'
      result.placeholder = props.fieldConfig?.placeholder || '请选择时间'
      result.format = 'YYYY-MM-DD HH:mm:ss'
      result.valueFormat = 'YYYY-MM-DD HH:mm:ss'
      result.style = 'width: 100%'
      break
    case 'switch':
      result.inlinePrompt = true
      result.activeText = '是'
      result.inactiveText = '否'
      break
    case 'checkbox':
      result.label = props.fieldConfig?.placeholder || ''
      break
    default:
      result.placeholder = props.fieldConfig?.placeholder || '请输入'
      result.clearable = true
      break
  }
  
  return result
})

const vhDisplayCache = reactive({})

async function resolveVhDisplay(fieldKey, value, valueHelpConfig) {
  if (!valueHelpConfig || !value) return
  const cacheKey = `${fieldKey}:${value}`
  if (vhDisplayCache[cacheKey]) return

  try {
    const source = valueHelpConfig.source
    if (!source) return
    let sourceType = source.type
    let sourceId = ''
    if (sourceType === 'enum') {
      sourceId = source.enum_type_id || ''
    } else if (sourceType === 'bo') {
      sourceId = source.target_bo || ''
    } else if (sourceType === 'custom') {
      sourceId = source.endpoint || ''
    }
    if (!sourceId) return

    const response = await boService.resolveValueHelp(sourceType, sourceId, value)
    if (response.success && response.data?.display) {
      vhDisplayCache[cacheKey] = response.data.display
    }
  } catch (e) {
    // ignore
  }
}

const displayValue = computed(() => {
  const val = currentValue.value
  if (val == null) return '-'
  
  const type = props.fieldConfig?.type
  
  if (type === 'switch' || type === 'boolean') {
    return val ? '是' : '否'
  }
  
  if (type === 'checkbox') {
    return val ? '[DECORATIVE]' : '-'
  }
  
  if (type === 'select') {
    const opt = props.fieldConfig?.options?.find(o => o.value === val)
    return opt?.label || val
  }

  if (type === 'value_help') {
    const cacheKey = `${props.fieldConfig?.key || props.field}:${val}`
    if (vhDisplayCache[cacheKey]) return vhDisplayCache[cacheKey]
    const displayField = `${props.fieldConfig?.key || props.field}_display`
    if (props.row?.[displayField]) return props.row[displayField]
    const nameField = `${(props.fieldConfig?.key || props.field).replace(/_id$/, '')}_name`
    if (props.row?.[nameField]) return props.row[nameField]
    resolveVhDisplay(props.fieldConfig?.key || props.field, val, props.fieldConfig?.valueHelpConfig)
    return val
  }

  if (type === 'datetime') {
    return formatDate(val, 'YYYY-MM-DD HH:mm:ss')
  }

  if (type === 'date') {
    return formatDate(val, 'YYYY-MM-DD')
  }
  
  return val
})

function handleMouseEnter() {
  emit('hover')
}

function handleMouseLeave() {
  emit('leave')
}

function handleCellClick() {
  if (!props.editing) {
    handleStartEdit()
  }
}

function handleStartEdit() {
  emit('start-edit')
  nextTick(() => {
    if (inputRef.value?.$el) {
      const input = inputRef.value.$el.querySelector('input') || inputRef.value.$el
      input?.focus()
    }
  })
}

function handleFinishEdit() {
  emit('finish-edit')
}

function handleCancelEdit() {
  currentValue.value = props.originalValue !== undefined ? props.originalValue : props.row[props.fieldName]
  emit('cancel-edit')
}

function handleBlur() {
  if (props.fieldConfig?.type === 'select') return
  setTimeout(() => {
    emit('finish-edit')
  }, 100)
}

function handleSelectChange(val) {
  handleValueChange(val)
  nextTick(() => {
    emit('finish-edit')
  })
}

function handleTab(event) {
  emit('finish-edit')
}

function handleFocus() {
  emit('start-edit')
}

function handleValueChange(newVal) {
  isInternalChange.value = true
  currentValue.value = newVal
  emit('update:value', newVal)
  nextTick(() => {
    isInternalChange.value = false
  })
}

defineExpose({
  focus: () => {
    nextTick(() => {
      if (inputRef.value?.$el) {
        const input = inputRef.value.$el.querySelector('input') || inputRef.value.$el
        input?.focus()
      }
    })
  }
})
</script>

<style scoped>
.inline-edit-cell {
  position: relative;
  min-height: 28px;
  display: flex;
  align-items: center;
  width: 100%;
  overflow: hidden;
  box-sizing: border-box;
}

.cell-display {
  display: flex;
  align-items: center;
  width: 100%;
  cursor: default;
}

.cell-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.required-star {
  color: #f56c6c;
  margin-right: 2px;
  font-size: 12px;
  line-height: 1;
  flex-shrink: 0;
}

.edit-icon {
  margin-left: 4px;
  color: var(--el-color-primary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.inline-edit-cell.is-hovered .edit-icon {
  opacity: 1;
}

.inline-edit-cell.is-editing {
  background: #fff8e6;
  border-radius: 2px;
}

.inline-edit-cell.is-modified:not(.is-editing) {
  background: #f0f9eb;
}

.inline-edit-cell.is-immutable {
  background: #f5f7fa !important;
  color: #909399 !important;
}

.inline-edit-cell.is-immutable .cell-value {
  font-style: italic;
}

.inline-edit-cell.is-editable.is-hovered .cell-display {
  background: #ecf5ff;
  border-radius: 4px;
  cursor: pointer;
}

.inline-edit-cell.is-editable.is-hovered .cell-value {
  color: var(--el-color-primary);
}

.inline-edit-cell.not-editable {
  cursor: not-allowed;
}

.is-immutable .cell-display {
  padding: 0 8px;
}

.cell-editor {
  width: 100%;
  display: flex;
  align-items: center;
  overflow: hidden;
}

.cell-editor :deep(.el-input),
.cell-editor :deep(.el-input-number),
.cell-editor :deep(.el-select),
.cell-editor :deep(.el-date-editor) {
  width: 100%;
  min-width: 0;
}

.cell-editor :deep(.el-select .el-input__wrapper) {
  width: 100%;
}

.cell-editor :deep(.el-input__wrapper) {
  box-sizing: border-box;
}

.is-direct-mode .direct-input {
  width: 100%;
  min-width: 0;
}

.is-direct-mode :deep(.el-input__wrapper) {
  background: transparent;
  box-shadow: none;
  padding: 0 4px;
}

.is-direct-mode :deep(.el-input__wrapper:hover) {
  background: #f5f7fa;
}

.is-direct-mode :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}

.is-direct-mode .is-immutable .cell-display {
  padding: 0 4px;
}
</style>
