<template>
  <div class="op-field">
    <label>{{ getFieldLabel(fieldKey) }}<span v-if="isRequired(fieldKey)" class="op-required">*</span></label>

    <template v-if="!editing">
      <FkLinkField
        v-if="isFkField(fieldKey)"
        :value="formData[fieldKey]"
        :display-value="getFieldDisplayValue(fieldKey)"
        :target-object-type="getFkTargetObjectType(fieldKey)"
      />
      <el-tag
        v-else-if="enumFieldKeys.has(fieldKey) && formData[fieldKey] != null && formData[fieldKey] !== ''"
        :type="getEnumColor(fieldKey, formData[fieldKey])"
        size="small"
      >
        {{ getEnumLabel(fieldKey, formData[fieldKey]) }}
      </el-tag>
      <span v-else class="op-field-value">{{ formatReadValue(fieldKey) }}</span>
    </template>

    <ValueHelpField
      v-else-if="valueHelpFieldKeys.has(fieldKey)"
      :key="`vh-${fieldKey}-${formData[fieldKey] ?? 'null'}-${formRenderKey}`"
      :model-value="formData[fieldKey]"
      :value-help-config="getValueHelpConfigWithFallback(fieldKey)"
      :form-values="formData"
      :field-key="fieldKey"
      :disabled="isFieldReadonly(fieldKey)"
      @update:model-value="val => emit('field-update', { key: fieldKey, value: val })"
      @update:display-value="val => emit('field-display-update', { key: fieldKey, displayValue: val })"
      @out-mapping="updates => emit('out-mapping', updates)"
    />
    <el-select
      v-else-if="getFieldWidget(fieldKey) === 'el-select'"
      v-model="formData[fieldKey]"
      :disabled="isFieldReadonly(fieldKey)"
      :placeholder="getFieldPlaceholder(fieldKey)"
      clearable
      @update:model-value="val => emit('field-update', { key: fieldKey, value: val })"
    >
      <el-option
        v-for="opt in getFieldOptions(fieldKey)"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
    <component
      v-else
      :is="getFieldWidget(fieldKey)"
      v-model="formData[fieldKey]"
      v-bind="getFieldProps(fieldKey)"
      :disabled="isFieldReadonly(fieldKey)"
      :placeholder="getFieldPlaceholder(fieldKey)"
      @update:model-value="val => emit('field-update', { key: fieldKey, value: val })"
    />
  </div>
</template>

<script setup>
import ValueHelpField from '../ValueHelpField.vue'
import FkLinkField from '../FkLinkField/FkLinkField.vue'
import { dateFormatService } from '@/services/DateFormatService'

const props = defineProps({
  fieldKey: {
    type: String,
    required: true
  },
  formData: {
    type: Object,
    required: true
  },
  fieldDefs: {
    type: Object,
    required: true
  },
  editing: {
    type: Boolean,
    default: false
  },
  valueHelpFieldKeys: {
    type: Set,
    default: () => new Set()
  },
  enumFieldKeys: {
    type: Set,
    default: () => new Set()
  },
  objectType: {
    type: String,
    default: null
  },
  objectId: {
    type: [String, Number],
    default: null
  },
  isCascadeField: {
    type: Function,
    default: () => false
  },
  getCascadeParent: {
    type: Function,
    default: () => null
  },
  formRenderKey: {
    type: Number,
    default: 0
  },
  fieldPolicy: {          // 🆕 v1 批次 3 / FR-6.2: 外部 useFieldPolicy 注入
    type: Object,
    default: null
  }
})

const emit = defineEmits(['field-update', 'field-display-update', 'out-mapping'])

function _mapFieldTypeToWidget(fieldType) {
  const map = {
    'string': 'el-input',
    'text': 'el-input',
    'integer': 'el-input-number',
    'float': 'el-input-number',
    'boolean': 'el-switch',
    'date': 'el-date-picker',
    'datetime': 'el-date-picker',
    'json': 'el-input'
  }
  return (fieldType || '').toLowerCase() in map ? map[fieldType.toLowerCase()] : 'el-input'
}

function resolveWidgetName(name) {
  if (name.startsWith('el-')) return name
  return `el-${name}`
}

function getFieldLabel(key) {
  const def = props.fieldDefs[key]
  return def?.label || key
}

function isRequired(key) {
  // 🆕 v1 批次 3 / FR-6.2: 优先走 useFieldPolicy.requiredMap（后端策略）
  if (props.fieldPolicy?.requiredMap?.value?.[key] !== undefined) {
    return props.fieldPolicy.requiredMap.value[key] === true
  }
  // Fallback: 本地 fieldDefs
  return props.fieldDefs[key]?.required === true
}

function isFkField(key) {
  const fieldDef = props.fieldDefs[key]
  if (!fieldDef?.valueHelp?.source) return false
  return fieldDef.valueHelp.source.type === 'bo'
}

function getFieldDisplayValue(key) {
  // 🆕 v1 批次 3 / FR-6.5: 优先后端 display_values
  const dv = props.formData?.display_values?.[key]
  if (dv !== undefined && dv !== null) return dv

  const displayKey = props.formData[`${key}_display`]
    ? `${key}_display`
    : `${key.replace(/_id$/, '')}_name`
  const displayValue = props.formData[displayKey]
  if (displayValue) return displayValue
  const value = props.formData[key]
  return value ?? ''
}

function getFkTargetObjectType(key) {
  const fieldDef = props.fieldDefs[key]
  if (!fieldDef?.valueHelp?.source) return null
  return fieldDef.valueHelp.source.target_bo || null
}

function _isEnumMatch(optValue, dataValue, isBoolean) {
  if (optValue === dataValue) return true
  if (isBoolean) {
    if (optValue === (dataValue ? 1 : 0)) return true
    if ((optValue ? 1 : 0) === (dataValue ? 1 : 0)) return true
  }
  if (String(optValue) === String(dataValue)) return true
  const numOpt = Number(optValue)
  const numData = Number(dataValue)
  if (!isNaN(numOpt) && !isNaN(numData) && numOpt === numData) return true
  return false
}

function getEnumOptions(key) {
  const fieldDef = props.fieldDefs[key]
  if (!fieldDef?.options?.length) return []
  return fieldDef.options.map(opt => {
    if (typeof opt === 'object') return opt
    return { value: opt, label: String(opt), color: 'info' }
  })
}

function getEnumLabel(key, value) {
  const options = getEnumOptions(key)
  const fieldDef = props.fieldDefs[key]
  const isBoolean = fieldDef?.type === 'boolean'
  const found = options.find(o => _isEnumMatch(o.value, value, isBoolean))
  return found?.label ?? value
}

function getEnumColor(key, value) {
  const options = getEnumOptions(key)
  const fieldDef = props.fieldDefs[key]
  const isBoolean = fieldDef?.type === 'boolean'
  const found = options.find(o => _isEnumMatch(o.value, value, isBoolean))
  const colorMap = { success: 'success', warning: 'warning', danger: 'danger', error: 'danger', info: 'info', primary: '' }
  if (found?.color) {
    return colorMap[found.color] || ''
  }
  return ''
}

function formatReadValue(key) {
  const value = props.formData[key]
  if (value == null || value === '') return '-'

  const fieldDef = props.fieldDefs[key]
  const widget = fieldDef?.widget || fieldDef?.type || 'text'

  if (widget === 'switch' || widget === 'el-switch' || widget === 'boolean') {
    return value === true || value === 1 || value === '1' ? '是' : '否'
  }

  if (widget === 'datetime' || widget === 'date') {
    try {
      const date = new Date(value)
      if (isNaN(date.getTime())) return value || '-'
      return dateFormatService.format(date, { dateStyle: 'medium', timeStyle: 'short' })
    } catch {
      return value
    }
  }

  if (fieldDef?.options?.length) {
    const isBoolean = fieldDef?.type === 'boolean'
    const opt = fieldDef.options.find(o => {
      if (typeof o === 'object') {
        return _isEnumMatch(o.value, value, isBoolean)
      }
      return o === value
    })
    if (opt && typeof opt === 'object') return opt.label ?? value
  }

  return value
}

function isFieldReadonly(key) {
  const fieldDef = props.fieldDefs[key]
  if (!fieldDef) return true

  if (fieldDef.editable === false) return true
  if (fieldDef.readonly === true) return true
  if (fieldDef.immutable === true && props.objectId && props.objectId !== 'new') return true

  if (props.isCascadeField(key)) {
    const parentField = props.getCascadeParent(key)
    if (parentField && !props.formData[parentField]) return true
  }

  if (props.editing) return false
  return true
}

function getFieldWidget(key) {
  const def = props.fieldDefs[key]
  if (!def) return 'el-input'
  if (def.options && def.options.length > 0) return 'el-select'
  const widgetMap = {
    text: 'el-input',
    textarea: 'el-input',
    number: 'el-input-number',
    select: 'el-select',
    date: 'el-date-picker',
    datetime: 'el-date-picker',
    switch: 'el-switch',
    radio: 'el-radio-group',
    checkbox: 'el-checkbox',
    value_help: 'ValueHelpField'
  }
  if (def.widget) {
    const known = widgetMap[def.widget]
    if (known) return known
    return resolveWidgetName(def.widget)
  }
  return _mapFieldTypeToWidget(def.type)
}

function getFieldProps(key) {
  const def = props.fieldDefs[key]
  const fieldProps = {}
  if (def?.type === 'textarea') fieldProps.type = 'textarea'
  if (def?.type === 'date') fieldProps.type = 'date'
  if (def?.type === 'datetime') fieldProps.type = 'datetime'
  if (def?.options) fieldProps.options = def.options
  if (def?.precision !== undefined) fieldProps.precision = def.precision
  if (def?.min !== undefined) fieldProps.min = def.min
  if (def?.max !== undefined) fieldProps.max = def.max
  return fieldProps
}

function getFieldPlaceholder(key) {
  const def = props.fieldDefs[key]
  return def?.placeholder || `请输入${def?.label || key}`
}

function getValueHelpConfig(key) {
  const fieldDef = props.fieldDefs[key]
  return fieldDef?.valueHelp || null
}

function getValueHelpConfigWithFallback(key) {
  const config = getValueHelpConfig(key)
  if (!config) return null
  // 如果当前 formData 中已经有 _display 字段值，则在 behavior 中添加 initial_options
  // 让 ValueHelpField 初始就有匹配当前 value 的 option
  const currentValue = props.formData?.[key]
  const displayKey = key + '_display'
  const currentDisplay = props.formData?.[displayKey]
  if (currentValue == null || currentValue === '' || !currentDisplay) {
    return config
  }
  return {
    ...config,
    behavior: {
      ...config.behavior,
      initial_options: [
        { value: currentValue, display: currentDisplay, code: '' }
      ]
    }
  }
}

function getFieldOptions(key) {
  const def = props.fieldDefs[key]
  if (!def?.options) return []
  return def.options.map(opt => ({
    value: opt.value != null ? opt.value : opt.id,
    label: opt.label || opt.name || String(opt.value ?? opt.id ?? '')
  }))
}
</script>

<style scoped>
.op-field {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
  width: 100%;
  padding: 4px 0;
}

.op-field > .el-input,
.op-field > .el-select,
.op-field > .el-input-number,
.op-field > .el-date-editor {
  flex: 1 !important;
  min-width: 0 !important;
  max-width: none !important;
  width: auto !important;
}

.op-field > .el-input .el-input__wrapper,
.op-field > .el-select .el-input__wrapper {
  width: auto !important;
  max-width: none !important;
}

.op-field label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
  flex-shrink: 0;
  white-space: nowrap;
  min-width: 70px;
}

.op-field .el-textarea {
  display: flex !important;
  flex-direction: column !important;
  width: 100% !important;
  max-width: 100%;
  min-height: 60px !important;
}

.op-field .el-textarea .el-textarea__inner {
  min-height: 60px !important;
  width: 100% !important;
}

.op-field .el-textarea label {
  width: 100% !important;
}

.op-required {
  color: var(--color-error);
  font-weight: 700;
}

.op-field-value {
  flex: 1;
  font-size: 14px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.6;
}
</style>
