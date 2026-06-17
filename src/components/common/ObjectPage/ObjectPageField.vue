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
      <span
        v-else
        :class="['op-field-value', isBusinessKey(fieldKey) && 'op-field-value--primary']"
      >{{ formatReadValue(fieldKey) }}</span>
    </template>

    <ValueHelpField
      v-else-if="valueHelpFieldKeys.has(fieldKey)"
      :key="`vh-${fieldKey}-${formRenderKey}`"
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
    <ElInput
      v-else-if="isCodeAutoManagedFinal(isCodeAutoManaged) && fieldKey === 'code'"
      v-model="formData[fieldKey]"
      :disabled="isFieldReadonly(fieldKey)"
      :placeholder="codeFieldPlaceholder || codeFieldPlaceholderInjected || getFieldPlaceholder(fieldKey)"
      @update:model-value="onCodeInput"
    >
      <template #suffix>
        <span v-if="!isFieldDirtyFinal('code')" class="kt-badge kt-badge--auto">
          {{ codeFieldTagText || codeFieldTagTextInjected || '自动' }}
        </span>
        <a
          v-else
          class="kt-reset-link"
          :title="'重置为根据父对象自动生成的编码'"
          @click.prevent.stop="onCodeResetFinal"
        >重置为自动生成</a>
      </template>
    </ElInput>
    <component
      v-else
      :is="resolveWidgetComponent(getFieldWidget(fieldKey))"
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
import { inject } from 'vue'
// [FIX] 显式导入 Element Plus 组件以支持动态 <component :is> 渲染
//   - unplugin-vue-components 只能自动导入模板中的字面量标签
//   - 动态 :is="字符串" 不会触发自动导入，必须显式 import
import {
  ElInput,
  ElInputNumber,
  ElSelect,
  ElDatePicker,
  ElSwitch,
  ElRadioGroup,
  ElCheckbox
} from 'element-plus'

// [NEW 2026-06-10] 注入 KeyTemplate 上下文（由 ObjectPageShell 提供）
// 通过 provide/inject 模式，避免在 ObjectPageContent / FieldGroupSection 中转 props
// 兼容旧用法：显式 props 仍生效（inject 提供默认值）
const keyTemplateContext = inject('keyTemplateContext', null)
const isCodeAutoManagedInjected = keyTemplateContext?.isCodeAutoManaged
const isFieldDirtyInjected = keyTemplateContext?.isFieldDirty
const markFieldDirtyInjected = keyTemplateContext?.markFieldDirty
const onCodeResetInjected = keyTemplateContext?.onCodeReset
// [NEW v1.1 2026-06-11] user_editable 相关 UI 提示
const codeFieldPlaceholderInjected = keyTemplateContext?.codeFieldPlaceholder
const codeFieldTagTextInjected = keyTemplateContext?.codeFieldTagText
const codeFieldTagTypeInjected = keyTemplateContext?.codeFieldTagType

// 合并 inject + props：props 优先（向后兼容直接传入的场景）
const isCodeAutoManagedFinal = (val) => {
  if (val === true) return true
  if (isCodeAutoManagedInjected?.value === true) return true
  return false
}
const isFieldDirtyFinal = (key) => {
  // 优先使用 inject（由 ObjectPageShell 提供）
  if (typeof isFieldDirtyInjected === 'function') {
    return isFieldDirtyInjected(key)
  }
  // 兼容旧用法：直接传 props.isFieldDirty
  if (typeof props.isFieldDirty === 'function') {
    const result = props.isFieldDirty(key)
    // 防止默认 `() => () => false` 误判：返回值是函数则忽略
    if (typeof result === 'function') return false
    return result === true
  }
  return false
}

const ELEMENT_PLUS_WIDGET_MAP = {
  'el-input': ElInput,
  'el-input-number': ElInputNumber,
  'el-select': ElSelect,
  'el-date-picker': ElDatePicker,
  'el-switch': ElSwitch,
  'el-radio-group': ElRadioGroup,
  'el-checkbox': ElCheckbox
}

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
  fieldPolicy: {          // [DECORATIVE] [NEW] v1.3 / FR-6.2: 外部 useFieldPolicy 注入
    type: Object,
    default: null
  },
  // [NEW 2026-06-10] KeyTemplate 集成：code 字段状态指示器
  isCodeAutoManaged: {
    type: Boolean,
    default: false
  },
  isFieldDirty: {
    type: Function,
    default: () => () => false
  },
  markFieldDirty: {
    type: Function,
    default: null
  },
  onCodeReset: {
    type: Function,
    default: null
  },
  // [NEW v1.1 2026-06-11] user_editable 模式相关 props
  codeFieldPlaceholder: {
    type: String,
    default: ''
  },
  codeFieldTagText: {
    type: String,
    default: ''
  },
  codeFieldTagType: {
    type: String,
    default: 'info'
  }
})

const emit = defineEmits(['field-update', 'field-display-update', 'out-mapping'])

// [NEW 2026-06-10] code 字段输入处理：触发 field-update + 标记 dirty
function onCodeInput(value) {
  emit('field-update', { key: props.fieldKey, value })
  // 优先 props，fallback 到 inject
  if (typeof props.markFieldDirty === 'function' && props.markFieldDirty !== null) {
    props.markFieldDirty('code')
  } else if (typeof markFieldDirtyInjected === 'function') {
    markFieldDirtyInjected('code')
  }
}

// [NEW 2026-06-10] 点击"重置为自动生成"链接（props 路径）
function onCodeReset() {
  if (typeof props.onCodeReset === 'function' && props.onCodeReset !== null) {
    props.onCodeReset()
  }
}

// [NEW 2026-06-10] 模板用的 reset 入口（优先 inject 因为这是从 ObjectPageShell 提供的）
function onCodeResetFinal() {
  if (typeof onCodeResetInjected === 'function') {
    onCodeResetInjected()
  } else {
    onCodeReset()
  }
}

// [NEW 2026-06-10] 默认的 isFieldDirty 函数（兜底）
function defaultIsFieldDirty() {
  return false
}

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

function resolveWidgetComponent(widgetName) {
  return ELEMENT_PLUS_WIDGET_MAP[widgetName] || ElInput
}

function getFieldLabel(key) {
  const def = props.fieldDefs[key]
  return def?.label || key
}

// [FIX 2026-06-16] 业务键(主key) 标识：DetailPage.computedFieldDefs 透传 business_key=true，
//   用于 view 模式下让主key 字段值用 YonDesign primary 橙色显示
function isBusinessKey(key) {
  return props.fieldDefs[key]?.business_key === true
}

function isRequired(key) {
  // [DECORATIVE] [NEW] v1.3 / FR-6.2: 优先走 useFieldPolicy.requiredMap（后端策略）
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
  // [DECORATIVE] [NEW] v1.3 / FR-6.5: 优先后端 display_values
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
  // [FIX 2026-06-10] browse 模式下优先用 display_values / <key>_display / <key>_name
  // 让 virtual FK 字段（如 domain_name / sub_domain_name / service_module_name）即使
  // formData[key] 在某些边界场景下为空，也能正确显示后端注入的 display 值。
  const dv = props.formData?.display_values?.[key]
  if (dv != null && dv !== '') return dv
  const displayKey = props.formData[`${key}_display`]
    ? `${key}_display`
    : `${key.replace(/_id$/, '')}_name`
  const displayValue = props.formData[displayKey]
  if (displayValue != null && displayValue !== '') return displayValue

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

  // [FIX] 在 editing 模式下：readonly 字段（如 version_id 等 context_field）始终保持 readonly，
  // 用户不能编辑——其值由 DetailPage 从 selectedVersionId 自动注入。immutable 在 editing 模式
  // (add) 下不生效（immutable 主要是 update 时保护），但 readonly 一直生效。
  if (props.editing) {
    if (fieldDef.readonly === true) return true
    if (fieldDef.immutable === true && props.objectId && props.objectId !== 'new') return true
    if (props.isCascadeField(key)) {
      const parentField = props.getCascadeParent(key)
      if (parentField && !props.formData[parentField]) return true
    }
    return false
  }

  if (fieldDef.editable === false) return true
  if (fieldDef.readonly === true) return true
  if (fieldDef.immutable === true && props.objectId && props.objectId !== 'new') return true

  if (props.isCascadeField(key)) {
    const parentField = props.getCascadeParent(key)
    if (parentField && !props.formData[parentField]) return true
  }

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
  let currentDisplay = props.formData?.[displayKey]
  // [FIX 2026-06-16] 对于 virtual FK 字段（如 source_domain_id），
  // 后端返回的 display 字段是 source_domain_name 而非 source_domain_id_display
  // 需要同时查找 _name 后缀的字段作为 fallback
  if (!currentDisplay && key.endsWith('_id')) {
    const nameKey = key.replace(/_id$/, '_name')
    currentDisplay = props.formData?.[nameKey]
  }
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

/* [FIX 2026-06-16] 业务键(主key) 高亮：YonDesign primary 橙色，font-weight 500 */
.op-field-value--primary {
  color: var(--color-primary);
  font-weight: 500;
}

/* [NEW 2026-06-10] KeyTemplate 状态指示器
   - .kt-badge: 角标通用样式
   - .kt-badge--auto: 浅绿底 "自动" 标识
   - .kt-reset-link: 主题色 "重置" 链接 */
.kt-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  line-height: 1.5;
  font-weight: 500;
  user-select: none;
}

.kt-badge--auto {
  background: #e6f7e6;
  color: #1d6f42;
  border: 1px solid #b6e0c2;
}

.kt-reset-link {
  font-size: 12px;
  color: var(--el-color-primary, #1565c0);
  cursor: pointer;
  user-select: none;
  text-decoration: none;
  padding: 0 2px;
}

.kt-reset-link:hover {
  text-decoration: underline;
  color: var(--el-color-primary-light-3, #4096ff);
}
</style>
