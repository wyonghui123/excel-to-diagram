<template>
  <el-date-picker
    :model-value="modelValue"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    :clearable="clearable"
    :format="format"
    :value-format="valueFormat"
    :readonly="readonly"
    :size="elSize"
    :empty-text="emptyText"
    :teleported="false"
    popper-class="app-datepicker-popper"
    @update:model-value="handleChange"
    @focus="emit('focus')"
    @blur="emit('blur')"
    @change="emit('change', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, Array, Date, Number, null],
    default: null
  },
  type: {
    type: String,
    default: 'date'
  },
  placeholder: {
    type: String,
    default: '请选择日期'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  clearable: {
    type: Boolean,
    default: true
  },
  format: {
    type: String,
    default: 'YYYY-MM-DD'
  },
  valueFormat: {
    type: String,
    default: 'YYYY-MM-DD'
  },
  readonly: {
    type: Boolean,
    default: false
  },
  size: {
    type: String,
    default: 'default'
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur'])

const elSize = computed(() => {
  if (props.size === 'large') return 'large'
  if (props.size === 'small') return 'small'
  return 'default'
})

function handleChange(value) {
  emit('update:modelValue', value)
}
</script>

<style scoped>
:deep(.el-date-editor) {
  width: 100%;
}

:deep(.app-datepicker-popper) {
  z-index: var(--z-index-select) !important;
}
</style>
