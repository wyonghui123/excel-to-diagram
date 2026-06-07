<template>
  <el-button
    :type="elType"
    :size="elSize"
    :disabled="disabled || loading"
    :loading="loading"
    :icon="hasIconProp ? icon : undefined"
    :round="circle"
    :plain="ghost"
    :class="buttonClasses"
    @click="handleClick"
  >
    <slot v-if="$slots.default" />
  </el-button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (value) => ['primary', 'secondary', 'text', 'danger', 'success', 'warning'].includes(value)
  },
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['xs', 'sm', 'md', 'lg', 'xl'].includes(value)
  },
  disabled: {
    type: Boolean,
    default: false
  },
  loading: {
    type: Boolean,
    default: false
  },
  type: {
    type: String,
    default: 'button'
  },
  icon: {
    type: [Object, Function],
    default: null
  },
  block: {
    type: Boolean,
    default: false
  },
  circle: {
    type: Boolean,
    default: false
  },
  ghost: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['click'])

const variantMap = {
  primary: 'primary',
  secondary: 'default',
  text: 'text',
  danger: 'danger',
  success: 'success',
  warning: 'warning'
}

const sizeMap = {
  xs: 'small',
  sm: 'small',
  md: 'default',
  lg: 'large',
  xl: 'large'
}

const elType = computed(() => variantMap[props.variant] || 'default')
const elSize = computed(() => sizeMap[props.size] || 'default')

const buttonClasses = computed(() => {
  const classes = []
  if (props.block) classes.push('app-button--block')
  if (props.size === 'xs') classes.push('app-button--xs')
  if (props.size === 'xl') classes.push('app-button--xl')
  return classes
})

const hasIconProp = computed(() => {
  return props.icon !== null && props.icon !== undefined
})

const handleClick = (event) => {
  if (props.disabled || props.loading) return
  emit('click', event)
}
</script>

<style scoped>
.app-button--block {
  display: flex;
  width: 100%;
}

.app-button--xs {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}

.app-button--xl {
  height: 48px;
  padding: 0 24px;
  font-size: 16px;
}
</style>
