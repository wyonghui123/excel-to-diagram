<template>
  <div
    :class="cardClasses"
    @click="handleClick"
  >
    <div v-if="$slots.header || title" class="app-card__header">
      <slot name="header">
        <div class="app-card__title-wrapper">
          <h3 v-if="title" class="app-card__title">{{ title }}</h3>
          <p v-if="subtitle" class="app-card__subtitle">{{ subtitle }}</p>
        </div>
        <div v-if="$slots.extra" class="app-card__extra">
          <slot name="extra" />
        </div>
      </slot>
    </div>
    <div :class="bodyClasses">
      <slot />
    </div>
    <div v-if="$slots.footer" class="app-card__footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /**
   * 卡片标题
   */
  title: {
    type: String,
    default: ''
  },
  /**
   * 副标题
   */
  subtitle: {
    type: String,
    default: ''
  },
  /**
   * 尺寸
   * @values 'sm' | 'md' | 'lg'
   */
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  /**
   * 阴影级别
   * @values 'none' | 'sm' | 'md' | 'lg'
   */
  shadow: {
    type: String,
    default: 'sm',
    validator: (value) => ['none', 'sm', 'md', 'lg'].includes(value)
  },
  /**
   * 是否可交互（hover效果）
   */
  hoverable: {
    type: Boolean,
    default: false
  },
  /**
   * 是否可点击
   */
  clickable: {
    type: Boolean,
    default: false
  },
  /**
   * 是否禁用
   */
  disabled: {
    type: Boolean,
    default: false
  },
  /**
   * 是否加载中
   */
  loading: {
    type: Boolean,
    default: false
  },
  /**
   * 边框样式
   * @values 'default' | 'primary' | 'success' | 'warning' | 'error'
   */
  border: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'primary', 'success', 'warning', 'error'].includes(value)
  },
  /**
   * 圆角大小
   * @values 'none' | 'sm' | 'md' | 'lg' | 'xl'
   */
  radius: {
    type: String,
    default: 'md',
    validator: (value) => ['none', 'sm', 'md', 'lg', 'xl'].includes(value)
  }
})

const emit = defineEmits(['click'])

const cardClasses = computed(() => [
  'app-card',
  `app-card--${props.size}`,
  `app-card--shadow-${props.shadow}`,
  `app-card--border-${props.border}`,
  `app-card--radius-${props.radius}`,
  {
    'app-card--hoverable': props.hoverable,
    'app-card--clickable': props.clickable,
    'app-card--disabled': props.disabled,
    'app-card--loading': props.loading
  }
])

const bodyClasses = computed(() => [
  'app-card__body',
  `app-card__body--${props.size}`
])

const handleClick = (event) => {
  if (props.disabled || props.loading || !props.clickable) return
  emit('click', event)
}
</script>

<style scoped>
.app-card {
  background: var(--color-bg-container);
  overflow: hidden;
  transition: var(--transition-normal);
}

/* 尺寸变体 */
.app-card--sm .app-card__header {
  padding: var(--spacing-sm) var(--spacing-md);
}

.app-card--sm .app-card__body {
  padding: var(--spacing-md);
}

.app-card--sm .app-card__footer {
  padding: var(--spacing-sm) var(--spacing-md);
}

.app-card--md .app-card__header {
  padding: var(--spacing-md) var(--spacing-lg);
}

.app-card--md .app-card__body {
  padding: var(--spacing-lg);
}

.app-card--md .app-card__footer {
  padding: var(--spacing-md) var(--spacing-lg);
}

.app-card--lg .app-card__header {
  padding: var(--spacing-lg) var(--spacing-xl);
}

.app-card--lg .app-card__body {
  padding: var(--spacing-xl);
}

.app-card--lg .app-card__footer {
  padding: var(--spacing-lg) var(--spacing-xl);
}

/* 阴影变体 */
.app-card--shadow-none {
  box-shadow: none;
}

.app-card--shadow-sm {
  box-shadow: var(--shadow-sm);
}

.app-card--shadow-md {
  box-shadow: var(--shadow-md);
}

.app-card--shadow-lg {
  box-shadow: var(--shadow-lg);
}

/* 圆角变体 */
.app-card--radius-none {
  border-radius: 0;
}

.app-card--radius-sm {
  border-radius: var(--radius-sm);
}

.app-card--radius-md {
  border-radius: var(--radius-md);
}

.app-card--radius-lg {
  border-radius: var(--radius-lg);
}

.app-card--radius-xl {
  border-radius: var(--radius-xl);
}

/* 边框变体 */
.app-card--border-default {
  border: var(--border-width-thin) solid var(--color-border);
}

.app-card--border-primary {
  border: var(--border-width-thin) solid var(--color-primary);
}

.app-card--border-success {
  border: var(--border-width-thin) solid var(--color-success);
}

.app-card--border-warning {
  border: var(--border-width-thin) solid var(--color-warning);
}

.app-card--border-error {
  border: var(--border-width-thin) solid var(--color-error);
}

/* 头部 */
.app-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: var(--border-width-thin) solid var(--color-border-secondary);
}

.app-card__title-wrapper {
  flex: 1;
  min-width: 0;
}

.app-card__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
  text-align: left;
}

.app-card__subtitle {
  margin: var(--spacing-xs) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
}

.app-card__extra {
  margin-left: var(--spacing-md);
  flex-shrink: 0;
}

/* 内容区 */
.app-card__body {
  color: var(--color-text-primary);
}

/* 底部 */
.app-card__footer {
  display: flex;
  align-items: center;
  border-top: var(--border-width-thin) solid var(--color-border-secondary);
  background: var(--color-bg-secondary);
}

/* 可交互状态 */
.app-card--hoverable:hover:not(.app-card--disabled) {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.app-card--clickable {
  cursor: pointer;
}

.app-card--clickable:hover:not(.app-card--disabled) {
  box-shadow: var(--shadow-md);
}

.app-card--clickable:active:not(.app-card--disabled) {
  transform: translateY(0);
  box-shadow: var(--shadow-sm);
}

/* 禁用状态 */
.app-card--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.app-card--disabled .app-card__header,
.app-card--disabled .app-card__body,
.app-card--disabled .app-card__footer {
  pointer-events: none;
}

/* 加载状态 */
.app-card--loading {
  position: relative;
}

.app-card--loading::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (prefers-color-scheme: dark) {
  .app-card--loading::after {
    background: rgba(0, 0, 0, 0.5);
  }
}
</style>
