<template>
  <Teleport to="body">
    <Transition name="app-modal">
      <div
        v-if="modelValue"
        ref="modalRef"
        class="app-modal"
        :class="modalClasses"
        :style="modalStyle"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
      >
        <div class="app-modal__backdrop" @click="handleBackdropClick"></div>
        <div class="app-modal__container" :class="containerClasses" :style="containerStyle">
          <div v-if="$slots.header || title" class="app-modal__header">
            <slot name="header">
              <h3 :id="titleId" class="app-modal__title">{{ title }}</h3>
              <button
                v-if="showClose"
                type="button"
                class="app-modal__close"
                @click="handleClose"
              >
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                </svg>
              </button>
            </slot>
          </div>
          <div class="app-modal__body">
            <div class="app-modal__body-scroll">
              <slot />
            </div>
          </div>
          <div v-if="$slots.footer" class="app-modal__footer">
            <slot name="footer" />
          </div>
          <div v-else-if="showDefaultFooter" class="app-modal__footer">
            <AppButton variant="secondary" @click="handleCancel">
              {{ cancelText }}
            </AppButton>
            <AppButton variant="primary" :loading="confirmLoading" @click="handleConfirm">
              {{ confirmText }}
            </AppButton>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch, onMounted, onUnmounted, useSlots, ref, nextTick } from 'vue'
import AppButton from '../AppButton/AppButton.vue'

const slots = useSlots()
const modalRef = ref(null)
const triggerElement = ref(null)
const titleId = computed(() => `app-modal-title-${Math.random().toString(36).slice(2, 9)}`)
const props = defineProps({
  /**
   * 是否显示（v-model）
   */
  modelValue: {
    type: Boolean,
    default: false
  },
  /**
   * 标题
   */
  title: {
    type: String,
    default: ''
  },
  /**
   * 宽度
   */
  width: {
    type: [String, Number],
    default: 520
  },
  /**
   * 是否显示关闭按钮
   */
  showClose: {
    type: Boolean,
    default: true
  },
  /**
   * 是否显示默认底部按钮
   */
  showDefaultFooter: {
    type: Boolean,
    default: false
  },
  /**
   * 确认按钮文本
   */
  confirmText: {
    type: String,
    default: '确定'
  },
  /**
   * 取消按钮文本
   */
  cancelText: {
    type: String,
    default: '取消'
  },
  /**
   * 确认按钮加载状态
   */
  confirmLoading: {
    type: Boolean,
    default: false
  },
  /**
   * 是否点击遮罩关闭
   */
  closeOnClickOverlay: {
    type: Boolean,
    default: true
  },
  /**
   * 是否按ESC关闭
   */
  closeOnPressEscape: {
    type: Boolean,
    default: true
  },
  /**
   * 是否锁定背景滚动
   */
  lockScroll: {
    type: Boolean,
    default: true
  },
  /**
   * 自定义类名
   */
  customClass: {
    type: String,
    default: ''
  },
  zIndex: {
    type: [String, Number],
    default: null
  }
})

const emit = defineEmits([
  'update:modelValue',
  'close',
  'confirm',
  'cancel',
  'open'
])

const modalClasses = computed(() => [
  'app-modal',
  props.customClass
])

const containerClasses = computed(() => [
  'app-modal__container',
  {
    'app-modal__container--no-header': !props.title && !slots.header,
    'app-modal__container--no-footer': !props.showDefaultFooter && !slots.footer
  }
])

const containerStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width
}))

const modalStyle = computed(() => {
  if (props.zIndex != null) {
    return { zIndex: Number(props.zIndex) }
  }
  return {}
})

const handleClose = () => {
  emit('update:modelValue', false)
  emit('close')
}

const handleBackdropClick = () => {
  if (props.closeOnClickOverlay) {
    handleClose()
  }
}

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
  handleClose()
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && props.closeOnPressEscape && props.modelValue) {
    handleClose()
  }
  if (event.key === 'Tab' && props.modelValue && modalRef.value) {
    handleTabKey(event)
  }
}

const getFocusableElements = () => {
  if (!modalRef.value) return []
  const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  return Array.from(modalRef.value.querySelectorAll(selector)).filter(
    (el) => !el.hasAttribute('disabled') && el.offsetParent !== null
  )
}

const focusFirstElement = () => {
  const focusableElements = getFocusableElements()
  if (focusableElements.length > 0) {
    focusableElements[0].focus()
  }
}

const handleTabKey = (event) => {
  const focusableElements = getFocusableElements()
  if (focusableElements.length === 0) return

  const firstElement = focusableElements[0]
  const lastElement = focusableElements[focusableElements.length - 1]

  if (event.shiftKey) {
    if (document.activeElement === firstElement) {
      event.preventDefault()
      lastElement.focus()
    }
  } else {
    if (document.activeElement === lastElement) {
      event.preventDefault()
      firstElement.focus()
    }
  }
}

const saveTriggerElement = () => {
  triggerElement.value = document.activeElement
}

const restoreFocus = () => {
  if (triggerElement.value && typeof triggerElement.value.focus === 'function') {
    triggerElement.value.focus()
  }
  triggerElement.value = null
}

const lockBodyScroll = () => {
  if (props.lockScroll) {
    document.body.style.overflow = 'hidden'
  }
}

const unlockBodyScroll = () => {
  if (props.lockScroll) {
    document.body.style.overflow = ''
  }
}

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    saveTriggerElement()
    emit('open')
    lockBodyScroll()
    nextTick(() => {
      focusFirstElement()
    })
  } else {
    unlockBodyScroll()
    restoreFocus()
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
.app-modal {
  position: fixed;
  inset: 0;
  z-index: var(--z-index-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-md);
}

.app-modal__backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
}

.app-modal__container {
  position: relative;
  width: 100%;
  max-width: calc(100vw - var(--spacing-xl));
  max-height: calc(100vh - var(--spacing-xl));
  background: var(--color-bg-container);
  border-radius: var(--radius-modal);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: app-modal-in 0.3s var(--ease-out);
}

@keyframes app-modal-in {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* 头部 */
.app-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: var(--border-width-thin) solid var(--color-border-secondary);
}

.app-modal__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
}

.app-modal__close {
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

.app-modal__close:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

/* 内容区 */
.app-modal__body {
  flex: 1;
  padding: 0;
  overflow: visible;
  color: var(--color-text-primary);
  position: relative;
}

.app-modal__body-scroll {
  max-height: calc(100vh - 220px);
  padding: var(--spacing-lg);
  overflow-y: auto;
  overflow-x: visible;
}

/* 当弹窗内容包含 el-select 时，给 body-scroll 底部预留 180px，
   避免下拉被弹窗底部裁切（不影响没有 el-select 的弹窗） */
.app-modal__container:has(.el-select) .app-modal__body-scroll {
  padding-bottom: 200px;
}

.app-modal__container--no-header .app-modal__body-scroll {
  padding-top: var(--spacing-lg);
}

.app-modal__container--no-footer .app-modal__body-scroll {
  padding-bottom: var(--spacing-lg);
}

/* 底部 */
.app-modal__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: var(--border-width-thin) solid var(--color-border-secondary);
  background: var(--color-bg-secondary);
}

/* 动画 */
.app-modal-enter-active,
.app-modal-leave-active {
  transition: opacity 0.3s var(--ease-out);
}

.app-modal-enter-from,
.app-modal-leave-to {
  opacity: 0;
}

.app-modal-enter-active .app-modal__container,
.app-modal-leave-active .app-modal__container {
  transition: transform 0.3s var(--ease-out), opacity 0.3s var(--ease-out);
}

.app-modal-enter-from .app-modal__container,
.app-modal-leave-to .app-modal__container {
  opacity: 0;
  transform: translateY(-20px) scale(0.95);
}

/* 响应式 */
@media (max-width: 768px) {
  .app-modal {
    padding: var(--spacing-sm);
    align-items: flex-end;
  }

  .app-modal__container {
    width: 100%;
    max-width: 100%;
    max-height: calc(100vh - var(--spacing-lg));
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    animation: app-modal-in-mobile 0.3s var(--ease-out);
  }

  @keyframes app-modal-in-mobile {
    from {
      opacity: 0;
      transform: translateY(100%);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .app-modal__header {
    padding: var(--spacing-md);
  }

  .app-modal__body-scroll {
    padding: var(--spacing-md);
  }

  .app-modal__footer {
    padding: var(--spacing-md);
  }
}
</style>
