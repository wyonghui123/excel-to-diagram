<template>
  <div class="meta-form" :class="[`meta-form--${layout}`, { 'meta-form--label-top': labelPosition === 'top' }]">
    <div
      v-for="field in visibleFields"
      :key="field.key"
      class="mf-item"
      :class="[
        { 'mf-item--error': errors[field.key], 'mf-item--required': field.required },
        field.span ? `mf-span-${field.span}` : ''
      ]"
      role="group"
      :aria-labelledby="labelPosition !== 'none' ? `mf-label-${field.key}` : undefined"
      :aria-invalid="errors[field.key] ? 'true' : undefined"
    >
      <label v-if="labelPosition !== 'none'" :id="`mf-label-${field.key}`" class="mf-label">
        {{ field.label }}
        <span v-if="field.required" class="mf-required">*</span>
      </label>
      <div class="mf-control">
        <template v-if="field.slot">
          <slot :name="`field-${field.key}`" :field="field" :value="formData[field.key]" :error="errors[field.key]" />
        </template>

        <input
          v-else-if="field.type === 'text'"
          v-model="formData[field.key]"
          type="text"
          class="mf-input"
          :class="{ 'mf-input--error': errors[field.key] }"
          :placeholder="field.placeholder || `请输入${field.label}`"
          :disabled="field.disabled"
          :aria-required="field.required ? 'true' : undefined"
          :aria-invalid="errors[field.key] ? 'true' : undefined"
          :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          @blur="validateField(field.key)"
        />

        <input
          v-else-if="field.type === 'number'"
          v-model.number="formData[field.key]"
          type="number"
          class="mf-input"
          :class="{ 'mf-input--error': errors[field.key] }"
          :placeholder="field.placeholder || `请输入${field.label}`"
          :disabled="field.disabled"
          :aria-required="field.required ? 'true' : undefined"
          :aria-invalid="errors[field.key] ? 'true' : undefined"
          :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          @blur="validateField(field.key)"
        />

        <textarea
          v-else-if="field.type === 'textarea'"
          v-model="formData[field.key]"
          class="mf-textarea"
          :class="{ 'mf-textarea--error': errors[field.key] }"
          :placeholder="field.placeholder || `请输入${field.label}`"
          :rows="field.rows || 3"
          :disabled="field.disabled"
          :aria-required="field.required ? 'true' : undefined"
          :aria-invalid="errors[field.key] ? 'true' : undefined"
          :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          @blur="validateField(field.key)"
        ></textarea>

        <AppSelect
          v-else-if="field.type === 'select' || (field.options && field.options.length > 0)"
          v-model="formData[field.key]"
          :options="getOptionsWithDisplay(field.key, field.options) || []"
          :placeholder="field.placeholder || `请选择${field.label}`"
          :disabled="field.disabled"
          :aria-required="field.required ? 'true' : undefined"
          :aria-invalid="errors[field.key] ? 'true' : undefined"
          :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          @change="validateField(field.key)"
        />

        <ValueHelpField
          v-else-if="(field.type === 'value_help' || field.value_help) && !isDualMode(field)"
          v-model="formData[field.key]"
          :value-help-config="field.valueHelpConfig || field.value_help"
          :disabled="field.disabled"
          :placeholder="field.placeholder || `请选择${field.label}`"
          :form-values="formData"
          @update:model-value="val => { formData[field.key] = val }"
          @update:display-value="val => { displayValues[field.key] = val }"
          @change="validateField(field.key)"
        />

        <!-- [V1.2.0 2026-06-15] 元数据驱动: dual_mode: true → 渲染 BoSelectorDualMode
             适用: 跨域关系 / 跨域 BO 引用等场景
             详见 .trae/specs/cross-domain-relationship-permission/spec.md (Option B)
        -->
        <BoSelectorDualMode
          v-else-if="(field.type === 'value_help' || field.value_help) && isDualMode(field)"
          :model-value="formData[field.key]"
          :product-id="getProductIdForField(field)"
          :label="field.label"
          :required="field.required"
          :allow-cross-domain="true"
          :disabled="field.disabled"
          @update:model-value="val => { formData[field.key] = val }"
          @cross-domain-toggled="(val) => onDualModeToggle(field.key, val)"
          @code-error="(err) => onDualModeCodeError(field.key, err)"
        />

        <label v-else-if="field.type === 'checkbox'" class="mf-checkbox">
          <input
            v-model="formData[field.key]"
            type="checkbox"
            class="mf-checkbox-input"
            :disabled="field.disabled"
            :aria-required="field.required ? 'true' : undefined"
            :aria-invalid="errors[field.key] ? 'true' : undefined"
            :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          />
          <span class="mf-checkbox-label">{{ field.checkboxLabel || '' }}</span>
        </label>

        <label v-else-if="field.type === 'switch'" class="mf-switch">
          <input
            v-model="formData[field.key]"
            type="checkbox"
            class="mf-switch-input"
            :disabled="field.disabled"
            :aria-required="field.required ? 'true' : undefined"
            :aria-invalid="errors[field.key] ? 'true' : undefined"
            :aria-describedby="errors[field.key] ? `mf-error-${field.key}` : undefined"
          />
          <span class="mf-switch-track"></span>
        </label>

        <span v-if="errors[field.key]" :id="`mf-error-${field.key}`" class="mf-error" role="alert">{{ errors[field.key] }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed, watch, inject } from 'vue'
import AppSelect from './AppSelect/AppSelect.vue'
import ValueHelpField from './ValueHelpField.vue'
import BoSelectorDualMode from './ValueHelp/BoSelectorDualMode.vue'

const props = defineProps({
  fields: {
    type: Array,
    required: true,
    validator: (val) => val.every(f => f.key)
  },
  modelValue: {
    type: Object,
    default: () => ({})
  },
  layout: {
    type: String,
    default: 'vertical',
    validator: (v) => ['vertical', 'horizontal', 'inline'].includes(v)
  },
  labelPosition: {
    type: String,
    default: 'top',
    validator: (v) => ['top', 'left', 'none'].includes(v)
  },
  labelWidth: {
    type: String,
    default: '80px'
  },
  fieldVisibility: {
    type: Object,
    default: () => ({})
  },
  fieldDependencies: {
    type: Object,
    default: () => ({})
  },
  fieldPolicy: {            // [DECORATIVE] [NEW] v1.3 / FR-6.7: useFieldPolicy 注入
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'cross-domain-toggled', 'code-error'])

// [V1.2.0 2026-06-15] 元数据驱动: dual_mode 识别
// 父组件可通过 provide('productId', ...) 注入 productId; 缺省时回退到 props.productId
const providedProductId = inject('productId', null)

function isDualMode(field) {
  // 检查多种 value_help 配置位置
  const vh = field.valueHelp || field.valueHelpConfig || field.value_help
  return vh && vh.dual_mode === true
}

function getProductIdForField(field) {
  // 优先级: field.productId > provided > 路由 query > 默认 1
  if (field.productId) return field.productId
  if (providedProductId?.value) return providedProductId.value
  if (typeof window !== 'undefined' && window.location) {
    const url = new URL(window.location.href)
    const q = url.searchParams.get('productId')
    if (q) return Number(q)
  }
  return 1  // 兜底默认 product
}

function onDualModeToggle(fieldKey, val) {
  // 转发给父组件, 供审计 (B.3 落地)
  emit('cross-domain-toggled', { fieldKey, enabled: val, ts: new Date().toISOString() })
  console.info('[MetaForm] dual-mode cross-domain toggled:', fieldKey, val)
}

function onDualModeCodeError(fieldKey, errCode) {
  emit('code-error', { fieldKey, code: errCode, ts: new Date().toISOString() })
  console.warn('[MetaForm] dual-mode code error:', fieldKey, errCode)
}

const formData = reactive({})
const displayValues = reactive({})
const errors = reactive({})
const previousFormData = {}

let isDependencyUpdating = false

function setFieldValue(key, value) {
  if (key in formData) {
    formData[key] = value
  }
}

function setFieldValues(values) {
  if (!values || typeof values !== 'object') return
  Object.entries(values).forEach(([key, value]) => {
    if (key in formData) {
      formData[key] = value
    }
  })
}

function initFormData(source) {
  Object.keys(formData).forEach(key => delete formData[key])
  Object.keys(previousFormData).forEach(key => delete previousFormData[key])
  Object.keys(displayValues).forEach(key => delete displayValues[key])
  props.fields.forEach(f => {
    formData[f.key] = source?.[f.key] ?? f.defaultValue ?? ''
    previousFormData[f.key] = formData[f.key]
  })
  if (source) {
    Object.keys(source).forEach(key => {
      if (!(key in formData)) {
        formData[key] = source[key]
        previousFormData[key] = source[key]
      }
    })
    // [DECORATIVE] [NEW] v1.3: 初始化 display_values（从后端返回的编辑数据中提取）
    if (source.display_values) {
      Object.entries(source.display_values).forEach(([key, displayValue]) => {
        displayValues[key] = displayValue
      })
    }
  }
}

initFormData(props.modelValue)

watch(() => props.modelValue, (newVal) => {
  if (!newVal) return
  Object.keys(formData).forEach(key => {
    if (!(key in newVal)) delete formData[key]
  })
  Object.entries(newVal).forEach(([key, val]) => {
    if (formData[key] !== val) formData[key] = val
  })
}, { deep: true })

watch(formData, (val) => {
  emit('update:modelValue', { ...val })
}, { deep: true })

watch(formData, (newVal, oldVal) => {
  if (isDependencyUpdating || Object.keys(props.fieldDependencies).length === 0) return

  isDependencyUpdating = true

  try {
    Object.keys(props.fieldDependencies).forEach(key => {
      const dependency = props.fieldDependencies[key]
      if (!dependency || typeof dependency.onChange !== 'function') return

      const newValue = newVal[key]
      const oldValue = previousFormData[key]

      if (newValue !== oldValue) {
        const context = {
          setFieldValue,
          setFieldValues,
          getFormData: () => ({ ...formData })
        }
        dependency.onChange(newValue, { ...formData }, context)
      }
    })
  } finally {
    Object.keys(formData).forEach(key => {
      previousFormData[key] = formData[key]
    })
    isDependencyUpdating = false
  }
}, { deep: true })

const visibleFields = computed(() => {
  return props.fields.filter(f => {
    if (f.visible === false) return false
    const visibilityFn = props.fieldVisibility[f.key]
    if (typeof visibilityFn === 'function') {
      return visibilityFn(formData)
    }
    return true
  })
})

function setFormData(data) {
  initFormData(data)
}

function resetForm() {
  clearErrors()
  props.fields.forEach(f => {
    formData[f.key] = f.defaultValue ?? ''
  })
  emit('update:modelValue', { ...formData })
}

function clearErrors() {
  Object.keys(errors).forEach(key => delete errors[key])
}

/**
 * [DECORATIVE] [NEW] v1.3: 获取增强的 options（支持 display_values）
 * 对于下拉选择字段，如果后端返回了 display_values，用它来增强 options 的 label
 */
function getOptionsWithDisplay(fieldKey, options) {
  if (!options || !Array.isArray(options)) return options
  const dv = displayValues[fieldKey]
  if (!dv) return options

  // 找到当前值对应的 option，用 display_values 增强 label
  return options.map(opt => {
    if (opt.value === formData[fieldKey] && dv !== opt.label) {
      return { ...opt, label: String(dv) }
    }
    return opt
  })
}

function validateField(key) {
  const field = props.fields.find(f => f.key === key)
  if (!field) return true

  const visibilityFn = props.fieldVisibility[key]
  if (typeof visibilityFn === 'function' && !visibilityFn(formData)) {
    delete errors[key]
    return true
  }

  const val = formData[key]

  // [DECORATIVE] [NEW] v1.3 / FR-6.7: 条件必填检查（后端 conditional_required 联动）
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

function validateAll() {
  clearErrors()
  let valid = true
  for (const field of visibleFields.value) {
    if (!validateField(field.key)) valid = false
  }
  return valid
}

function getFormData() {
  return { ...formData }
}

defineExpose({
  setFormData,
  resetForm,
  validateAll,
  validateField,
  getFormData,
  clearErrors,
  formData,
  displayValues,
  errors,
  setFieldValue,
  setFieldValues
})
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.meta-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.mf-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.meta-form--horizontal .mf-item {
  flex-direction: row;
  align-items: flex-start;

  .mf-label {
    width: v-bind(labelWidth);
    min-width: v-bind(labelWidth);
    flex-shrink: 0;
    padding-top: 7px;
    line-height: var(--line-height-normal);
    text-align: right;
  }

  .mf-control {
    flex: 1;
  }
}

.meta-form--inline {
  flex-direction: row;
  flex-wrap: wrap;
  gap: var(--spacing-lg);

  .mf-item {
    flex: 1;
    min-width: 200px;
  }
}

.mf-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: var(--line-height-normal);
  white-space: nowrap;
}

.mf-required {
  color: var(--color-error);
  margin-left: var(--spacing-xxs);
}

.mf-input {
  width: 100%;
  height: var(--input-height-md);
  padding: 0 var(--spacing-md);
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  outline: none;
  transition: var(--transition-normal);

  &::placeholder {
    color: var(--color-text-placeholder);
  }

  &:hover:not(:disabled) {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }

  &:disabled {
    background: var(--color-bg-disabled);
    cursor: not-allowed;
    color: var(--color-text-disabled);
  }

  &--error {
    border-color: var(--color-error);

    &:focus {
      box-shadow: 0 0 0 2px var(--color-error-bg);
    }
  }
}

.mf-textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  outline: none;
  resize: vertical;
  transition: var(--transition-normal);

  &::placeholder {
    color: var(--color-text-placeholder);
  }

  &:hover:not(:disabled) {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }

  &:disabled {
    background: var(--color-bg-disabled);
    cursor: not-allowed;
    color: var(--color-text-disabled);
  }

  &--error {
    border-color: var(--color-error);

    &:focus {
      box-shadow: 0 0 0 2px var(--color-error-bg);
    }
  }
}

.mf-checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  height: var(--input-height-md);
}

.mf-checkbox-input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.mf-checkbox-label {
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
}

.mf-switch {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  height: var(--input-height-md);
}

.mf-switch-input {
  display: none;

  &:checked + .mf-switch-track {
    background: var(--color-primary);

    &::after {
      left: calc(100% - 17px);
    }
  }

  &:disabled + .mf-switch-track {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.mf-switch-track {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--color-border);
  border-radius: var(--radius-full);
  transition: background var(--transition-normal);

  &::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    transition: left var(--transition-normal);
    box-shadow: var(--shadow-sm);
  }
}

.mf-error {
  font-size: var(--font-size-xs);
  color: var(--color-error);
  line-height: var(--line-height-tight);
}
</style>
