<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="modelValue" class="drawer" :class="drawerClasses">
        <div
          v-if="mask"
          class="drawer__mask"
          @click="handleMaskClick"
        ></div>
        <div class="drawer__wrapper" :style="wrapperStyle">
          <div v-if="$slots.header || title" class="drawer__header">
            <slot name="header">
              <h3 class="drawer__title">{{ title }}</h3>
              <button
                v-if="closable"
                type="button"
                class="drawer__close"
                @click="handleClose"
              >
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                </svg>
              </button>
            </slot>
          </div>
          <div class="drawer__body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="drawer__footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch, onMounted, onUnmounted, useSlots } from 'vue'

const slots = useSlots()

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: ''
  },
  width: {
    type: [String, Number],
    default: '600px'
  },
  placement: {
    type: String,
    default: 'right',
    validator: (value) => ['left', 'right'].includes(value)
  },
  closable: {
    type: Boolean,
    default: true
  },
  mask: {
    type: Boolean,
    default: true
  },
  maskClosable: {
    type: Boolean,
    default: true
  },
  keyboard: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'update:modelValue',
  'open',
  'close'
])

const drawerClasses = computed(() => [
  `drawer--${props.placement}`
])

const wrapperStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width
}))

const handleClose = () => {
  emit('update:modelValue', false)
  emit('close')
}

const handleMaskClick = () => {
  if (props.maskClosable) {
    handleClose()
  }
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && props.keyboard && props.modelValue) {
    handleClose()
  }
}

const lockBodyScroll = () => {
  document.body.style.overflow = 'hidden'
}

const unlockBodyScroll = () => {
  document.body.style.overflow = ''
}

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    emit('open')
    lockBodyScroll()
  } else {
    unlockBodyScroll()
  }
})

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  unlockBodyScroll()
})
</script>

<style scoped>
.drawer {
  position: fixed;
  inset: 0;
  z-index: var(--z-index-modal);
}

.drawer__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
}

.drawer__wrapper {
  position: absolute;
  top: 0;
  bottom: 0;
  max-width: 100vw;
  background: var(--color-bg-container);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer--right .drawer__wrapper {
  right: 0;
}

.drawer--left .drawer__wrapper {
  left: 0;
}

.drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: var(--border-width-thin) solid var(--color-border-secondary);
  flex-shrink: 0;
}

.drawer__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
}

.drawer__close {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xs);
  margin: calc(-1 * var(--spacing-xs));
  margin-left: var(--spacing-sm);
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: var(--transition-fast);
}

.drawer__close:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.drawer__body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow-y: auto;
  color: var(--color-text-primary);
}

.drawer__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: var(--border-width-thin) solid var(--color-border-secondary);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.3s var(--ease-out);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-active .drawer__wrapper,
.drawer-leave-active .drawer__wrapper {
  transition: transform 0.3s var(--ease-out);
}

.drawer--right.drawer-enter-from .drawer__wrapper,
.drawer--right.drawer-leave-to .drawer__wrapper {
  transform: translateX(100%);
}

.drawer--left.drawer-enter-from .drawer__wrapper,
.drawer--left.drawer-leave-to .drawer__wrapper {
  transform: translateX(-100%);
}

@media (max-width: 768px) {
  .drawer__wrapper {
    width: 100% !important;
  }

  .drawer__header {
    padding: var(--spacing-md);
  }

  .drawer__body {
    padding: var(--spacing-md);
  }

  .drawer__footer {
    padding: var(--spacing-md);
  }
}
</style>
