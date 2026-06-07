<template>
  <el-select
    :model-value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :clearable="clearable"
    :filterable="searchable"
    :multiple="multiple"
    :size="elSize"
    :empty-text="emptyText"
    :teleported="false"
    popper-class="app-select-popper"
    @update:model-value="handleChange"
    @focus="emit('focus')"
    @blur="emit('blur')"
  >
    <template v-for="group in optionGroups" :key="group.label">
      <el-option-group v-if="group.isGroup" :label="group.label">
        <el-option
          v-for="option in group.options"
          :key="option.value"
          :label="option.label"
          :value="option.value"
          :disabled="option.disabled"
        >
          <slot name="option" :option="option">
            <span>{{ option.label }}</span>
          </slot>
        </el-option>
      </el-option-group>
    </template>
    <template v-if="!isGrouped">
      <el-option
        v-for="option in options"
        :key="option.value"
        :label="option.label"
        :value="option.value"
        :disabled="option.disabled"
      >
        <slot name="option" :option="option">
          <span>{{ option.label }}</span>
        </slot>
      </el-option>
    </template>
    <template v-if="$slots['dropdown-footer']" #footer>
      <slot name="dropdown-footer" />
    </template>
  </el-select>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, Number, Array],
    default: ''
  },
  options: {
    type: Array,
    default: () => []
  },
  placeholder: {
    type: String,
    default: '请选择'
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
  clearable: {
    type: Boolean,
    default: false
  },
  searchable: {
    type: Boolean,
    default: false
  },
  searchPlaceholder: {
    type: String,
    default: '搜索...'
  },
  emptyText: {
    type: String,
    default: '无匹配选项'
  },
  multiple: {
    type: Boolean,
    default: false
  },
  ariaRequired: {
    type: String,
    default: undefined
  },
  ariaInvalid: {
    type: String,
    default: undefined
  },
  ariaDescribedby: {
    type: String,
    default: undefined
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur'])

const sizeMap = {
  sm: 'small',
  md: 'default',
  lg: 'large'
}

const elSize = computed(() => sizeMap[props.size] || 'default')

const isGrouped = computed(() => {
  return props.options.length > 0 && props.options.some(opt => 'options' in opt)
})

const optionGroups = computed(() => {
  if (!isGrouped.value) return []
  return props.options.map(group => ({
    label: group.label,
    isGroup: true,
    options: group.options || []
  }))
})

const handleChange = (value) => {
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<style scoped>
:deep(.el-select) {
  width: 100%;
}

:deep(.app-select-popper) {
  z-index: var(--z-index-select) !important;
  max-height: none !important;
}

/* 修复下拉框内部多余滚动条（4 个选项完全不需要滚动） */
:deep(.app-select-popper .el-select-dropdown) {
  max-height: 320px !important;
}

:deep(.app-select-popper .el-select-dropdown__wrap) {
  max-height: 320px !important;
  overflow-y: auto;
}

:deep(.app-select-popper .el-scrollbar) {
  height: auto !important;
}
</style>
