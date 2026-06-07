<template>
  <div :class="collapseClasses">
    <div 
      class="app-collapse__header" 
      @click="handleToggle"
      :tabindex="disabled ? -1 : 0"
      @keydown.enter="handleToggle"
      @keydown.space.prevent="handleToggle"
    >
      <div class="app-collapse__header-content">
        <slot name="header">
          <div class="app-collapse__title-wrapper">
            <AppIcon 
              v-if="icon" 
              :name="icon" 
              :size="iconSize"
              class="app-collapse__icon"
            />
            <h3 v-if="title" class="app-collapse__title">{{ title }}</h3>
          </div>
          <div v-if="$slots.extra" class="app-collapse__extra">
            <slot name="extra" />
          </div>
        </slot>
      </div>
      <AppIcon 
        name="chevron-down"
        :size="16"
        :class="['app-collapse__arrow', { 'app-collapse__arrow--expanded': expanded }]"
      />
    </div>
    <transition
      name="collapse"
      @enter="onEnter"
      @after-enter="onAfterEnter"
      @leave="onLeave"
      @after-leave="onAfterLeave"
    >
      <div v-show="expanded" class="app-collapse__content">
        <div class="app-collapse__body">
          <slot />
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { AppIcon } from '../AppIcon'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  icon: {
    type: String,
    default: ''
  },
  iconSize: {
    type: [Number, String],
    default: 16
  },
  defaultExpanded: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  }
})

const emit = defineEmits(['change', 'update:expanded'])

const expanded = ref(props.defaultExpanded)

watch(() => props.defaultExpanded, (val) => {
  expanded.value = val
})

const collapseClasses = computed(() => [
  'app-collapse',
  `app-collapse--${props.size}`,
  {
    'app-collapse--disabled': props.disabled,
    'app-collapse--expanded': expanded.value
  }
])

function handleToggle() {
  if (props.disabled) return
  expanded.value = !expanded.value
  emit('change', expanded.value)
  emit('update:expanded', expanded.value)
}

function onEnter(el) {
  el.style.height = '0'
  el.style.overflow = 'hidden'
}

function onAfterEnter(el) {
  el.style.height = el.scrollHeight + 'px'
  setTimeout(() => {
    el.style.height = ''
    el.style.overflow = ''
  }, 300)
}

function onLeave(el) {
  el.style.height = el.scrollHeight + 'px'
  el.style.overflow = 'hidden'
  requestAnimationFrame(() => {
    el.style.height = '0'
  })
}

function onAfterLeave(el) {
  el.style.height = ''
  el.style.overflow = ''
}
</script>

<style scoped>
.app-collapse {
  background: var(--color-bg-1, #ffffff);
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-md, 6px);
  overflow: hidden;
  transition: all 0.3s ease;
}

.app-collapse:hover {
  border-color: var(--color-primary-light, #c9cdd4);
}

.app-collapse--expanded {
  border-color: var(--color-primary, #165dff);
}

.app-collapse--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-collapse--disabled .app-collapse__header {
  cursor: not-allowed;
}

.app-collapse__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.app-collapse--sm .app-collapse__header {
  padding: 12px;
}

.app-collapse--lg .app-collapse__header {
  padding: 20px;
}

.app-collapse__header:hover {
  background-color: var(--color-fill-1, #f7f8fa);
}

.app-collapse__header:focus {
  outline: 2px solid var(--color-primary, #165dff);
  outline-offset: -2px;
}

.app-collapse__header-content {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.app-collapse__title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.app-collapse__icon {
  color: var(--color-text-2, #4e5969);
  flex-shrink: 0;
}

.app-collapse__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-1, #1d2129);
  line-height: 1.5;
}

.app-collapse--sm .app-collapse__title {
  font-size: 14px;
}

.app-collapse--lg .app-collapse__title {
  font-size: 18px;
}

.app-collapse__extra {
  margin-left: 16px;
  flex-shrink: 0;
}

.app-collapse__arrow {
  color: var(--color-text-3, #86909c);
  transition: transform 0.3s ease;
  flex-shrink: 0;
  margin-left: 12px;
}

.app-collapse__arrow--expanded {
  transform: rotate(180deg);
}

.app-collapse__content {
  overflow: hidden;
  transition: height 0.3s ease;
}

.app-collapse__body {
  padding: 16px;
  padding-top: 0;
  border-top: 1px solid var(--color-border, #e5e6eb);
}

.app-collapse--sm .app-collapse__body {
  padding: 12px;
  padding-top: 0;
}

.app-collapse--lg .app-collapse__body {
  padding: 20px;
  padding-top: 0;
}

.collapse-enter-active,
.collapse-leave-active {
  transition: height 0.3s ease;
}
</style>
