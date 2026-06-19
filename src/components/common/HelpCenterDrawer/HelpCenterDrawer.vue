<!--
  HelpCenterDrawer - P0 占位版本
  后续 P1 阶段将嵌入 iframe 加载 /docs/user-guide/index.html
-->
<template>
  <Teleport to="body">
    <Transition name="help-drawer">
      <div v-if="modelValue" class="help-drawer" role="dialog" aria-label="Help Center">
        <div class="help-drawer__mask" @click="handleClose"></div>
        <div class="help-drawer__wrapper" :style="wrapperStyle">
          <div class="help-drawer__header">
            <div class="help-drawer__title">
              <el-icon class="help-drawer__title-icon" :size="20">
                <QuestionFilled />
              </el-icon>
              <span>Help Center</span>
            </div>
            <button
              type="button"
              class="help-drawer__close"
              aria-label="Close help center"
              @click="handleClose"
            >
              <svg viewBox="0 0 24 24" width="20" height="20">
                <path
                  fill="currentColor"
                  d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
                />
              </svg>
            </button>
          </div>

          <div class="help-drawer__body">
            <!-- P0 placeholder, P1 will embed iframe -->
            <div class="help-drawer__placeholder">
              <el-empty description="Help docs coming soon">
                <template #image>
                  <div class="help-drawer__placeholder-icon">
                    <el-icon :size="64"><DocumentCopy /></el-icon>
                  </div>
                </template>
                <div class="help-drawer__placeholder-text">
                  <p class="help-drawer__placeholder-title">User Guide - V1 Placeholder</p>
                  <p class="help-drawer__placeholder-desc">
                    P0 stage - Drawer only.<br />
                    P1 stage - iframe embed /docs/user-guide/index.html
                  </p>
                </div>
                <el-button type="primary" @click="openInNewTab">
                  Open in new tab (placeholder)
                </el-button>
              </el-empty>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { QuestionFilled, DocumentCopy } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  width: {
    type: [Number, String],
    default: 800
  },
  helpUrl: {
    type: String,
    default: '/docs/user-guide/index.html'
  }
})

const emit = defineEmits(['update:modelValue', 'close', 'open-in-new-tab'])

const wrapperStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width
}))

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}

function openInNewTab() {
  window.open(props.helpUrl, '_blank', 'noopener,noreferrer')
  emit('open-in-new-tab', props.helpUrl)
}

function handleKeydown(e) {
  if (!props.modelValue) return
  if (e.key === 'Escape') {
    e.preventDefault()
    handleClose()
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
  }
)

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.help-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: var(--z-index-modal, 2000);
  display: flex;
  justify-content: flex-end;
}

.help-drawer__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
}

.help-drawer__wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
  max-width: 95vw;
  background: var(--el-bg-color, #ffffff);
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
  height: 100%;
}

.help-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg, 24px);
  border-bottom: 1px solid var(--el-border-color-light, #ebeef5);
  flex-shrink: 0;
}

.help-drawer__title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  font-size: var(--el-font-size-large, 16px);
  font-weight: 600;
  color: var(--yonyou-orange-600, #ea580c);
}

.help-drawer__title-icon {
  color: var(--yonyou-orange-600, #ea580c);
}

.help-drawer__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.help-drawer__close:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.help-drawer__body {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg, 24px);
}

.help-drawer__placeholder {
  width: 100%;
  max-width: 480px;
  text-align: center;
}

.help-drawer__placeholder-icon {
  color: var(--yonyou-orange-500, #f97316);
  display: flex;
  justify-content: center;
  margin-bottom: var(--spacing-md, 16px);
}

.help-drawer__placeholder-text {
  margin: var(--spacing-md, 16px) 0 var(--spacing-lg, 24px);
}

.help-drawer__placeholder-title {
  font-size: var(--el-font-size-large, 16px);
  font-weight: 600;
  color: var(--el-text-color-primary, #1d2129);
  margin: 0 0 var(--spacing-sm, 8px);
}

.help-drawer__placeholder-desc {
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-secondary, #86909c);
  line-height: 1.6;
  margin: 0;
}

.help-drawer-enter-active,
.help-drawer-leave-active {
  transition: opacity 0.25s ease;
}

.help-drawer-enter-active .help-drawer__wrapper,
.help-drawer-leave-active .help-drawer__wrapper {
  transition: transform 0.25s ease;
}

.help-drawer-enter-from,
.help-drawer-leave-to {
  opacity: 0;
}

.help-drawer-enter-from .help-drawer__wrapper,
.help-drawer-leave-to .help-drawer__wrapper {
  transform: translateX(100%);
}
</style>
