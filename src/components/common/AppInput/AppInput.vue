<template>
  <div :class="wrapperClasses">
    <label v-if="label" class="app-input__label">
      {{ label }}
      <span v-if="required" class="app-input__required">*</span>
    </label>
    <el-input
      :model-value="modelValue"
      :type="currentInputType"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="readonly"
      :maxlength="maxlength"
      :min="min"
      :max="max"
      :step="step"
      :autocomplete="autocomplete"
      :autofocus="autofocus"
      :name="name"
      :id="inputId"
      :size="elSize"
      :clearable="clearable"
      :show-password="showPasswordToggle && type === 'password'"
      :prefix-icon="prefixIcon"
      :suffix-icon="suffixIcon"
      @update:model-value="handleInput"
      @focus="handleFocus"
      @blur="handleBlur"
      @change="handleChange"
      @keydown="handleKeydown"
      @clear="handleClear"
    >
      <template v-if="$slots.prefix" #prefix>
        <slot name="prefix" />
      </template>
      <template v-if="$slots.suffix" #suffix>
        <slot name="suffix" />
      </template>
    </el-input>
    <div v-if="error" class="app-input__error">{{ error }}</div>
    <div v-else-if="hint" class="app-input__hint">{{ hint }}</div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: ''
  },
  type: {
    type: String,
    default: 'text'
  },
  placeholder: {
    type: String,
    default: ''
  },
  label: {
    type: String,
    default: ''
  },
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  disabled: {
    type: Boolean,
    default: false
  },
  readonly: {
    type: Boolean,
    default: false
  },
  required: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  hint: {
    type: String,
    default: ''
  },
  clearable: {
    type: Boolean,
    default: false
  },
  prefixIcon: {
    type: [Object, Function],
    default: null
  },
  suffixIcon: {
    type: [Object, Function],
    default: null
  },
  maxlength: {
    type: Number,
    default: undefined
  },
  min: {
    type: Number,
    default: undefined
  },
  max: {
    type: Number,
    default: undefined
  },
  step: {
    type: Number,
    default: undefined
  },
  autocomplete: {
    type: String,
    default: 'off'
  },
  autofocus: {
    type: Boolean,
    default: false
  },
  name: {
    type: String,
    default: ''
  },
  id: {
    type: String,
    default: ''
  },
  showPasswordToggle: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'update:modelValue',
  'input',
  'focus',
  'blur',
  'change',
  'clear',
  'keydown'
])

const inputId = computed(() => props.id || `app-input-${Math.random().toString(36).substr(2, 9)}`)
const isFocused = ref(false)

const sizeMap = {
  sm: 'small',
  md: 'default',
  lg: 'large'
}

const elSize = computed(() => sizeMap[props.size] || 'default')

const wrapperClasses = computed(() => [
  'app-input',
  `app-input--${props.size}`,
  {
    'app-input--disabled': props.disabled,
    'app-input--error': props.error,
    'app-input--focused': isFocused.value
  }
])

const currentInputType = computed(() => props.type)

const handleInput = (value) => {
  emit('update:modelValue', value)
  emit('input', value)
}

const handleFocus = (event) => {
  isFocused.value = true
  emit('focus', event)
}

const handleBlur = (event) => {
  isFocused.value = false
  emit('blur', event)
}

const handleChange = (value) => {
  emit('change', value)
}

const handleClear = () => {
  emit('update:modelValue', '')
  emit('clear')
}

const handleKeydown = (event) => {
  emit('keydown', event)
}
</script>

<style scoped>
.app-input {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 4px);
  width: 100%;
}

.app-input__label {
  font-size: var(--font-size-sm, 13px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--color-text-primary, #333);
  line-height: 1.5;
}

.app-input__required {
  color: var(--color-error);
  margin-left: 2px;
}

.app-input--error :deep(.el-input__wrapper) {
  border-color: var(--color-error);
}

.app-input__error {
  font-size: 12px;
  color: var(--color-error);
  line-height: 1.5;
}

.app-input__hint {
  font-size: 12px;
  color: var(--color-text-tertiary, #999);
  line-height: 1.5;
}
</style>
