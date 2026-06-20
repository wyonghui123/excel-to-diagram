<!--
  HelpCenterDrawer - P1 阶段，iframe 嵌入 /docs/user-guide/index.html
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
              <span>帮助中心</span>
            </div>
            <div class="help-drawer__header-actions">
              <button
                type="button"
                class="help-drawer__header-btn"
                aria-label="Open help docs in new tab"
                title="新窗口打开"
                @click="openInNewTab"
              >
                <svg viewBox="0 0 24 24" width="16" height="16">
                  <path
                    fill="currentColor"
                    d="M14 3v2h3.59L9.29 13.29l1.42 1.42L19 6.41V10h2V3h-7zM19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7z"
                  />
                </svg>
              </button>
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
          </div>

          <div class="help-drawer__body">
            <iframe
              v-if="modelValue"
              :key="iframeKey"
              :src="helpUrl"
              class="help-drawer__iframe"
              title="帮助文档"
              referrerpolicy="no-referrer-when-downgrade"
              @load="handleIframeLoad"
              @error="handleIframeError"
            ></iframe>

            <div v-if="loadError" class="help-drawer__fallback">
              <el-icon :size="48" class="help-drawer__fallback-icon"><Warning /></el-icon>
              <p class="help-drawer__fallback-title">无法加载帮助文档</p>
              <p class="help-drawer__fallback-desc">{{ loadError }}</p>
              <el-button type="primary" @click="retry">重试</el-button>
              <el-button @click="openInNewTab">新窗口打开</el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { QuestionFilled, Warning } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  width: {
    type: [Number, String],
    default: 880
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

const iframeKey = ref(0)
const loadError = ref('')

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}

function openInNewTab() {
  window.open(props.helpUrl, '_blank', 'noopener,noreferrer')
  emit('open-in-new-tab', props.helpUrl)
}

function retry() {
  loadError.value = ''
  iframeKey.value += 1
}

function handleIframeLoad() {
  loadError.value = ''
}

function handleIframeError() {
  loadError.value = `帮助文档加载失败：${props.helpUrl}`
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
      iframeKey.value += 1
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

.help-drawer__header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
}

.help-drawer__header-btn,
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

.help-drawer__header-btn:hover,
.help-drawer__close:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.help-drawer__body {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: var(--el-fill-color-blank, #ffffff);
}

.help-drawer__iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}

.help-drawer__fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg, 24px);
  text-align: center;
  gap: var(--spacing-sm, 8px);
}

.help-drawer__fallback-icon {
  color: var(--yonyou-orange-500, #f97316);
}

.help-drawer__fallback-title {
  font-size: var(--el-font-size-large, 16px);
  font-weight: 600;
  color: var(--el-text-color-primary, #1d2129);
  margin: 0;
}

.help-drawer__fallback-desc {
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-secondary, #86909c);
  margin: 0 0 var(--spacing-md, 16px);
  word-break: break-all;
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
