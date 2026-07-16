<!--
  PublicHelpDrawer - P3 公开版帮助中心
  - 不需要登录: 任何用户访问 ?help=&step= 都能看
  - 体验与登录后 HelpCenterDrawer 完全一致: 支持最大化、URL ?step= 自动展开
  - URL ?max=1 时默认最大化, 适合文档 / 演示 / 录屏场景
  - 独立挂载到 body, 不受 AppRootLayout 控制
  - 关闭时清理 URL 中的 ?help=&step= query, 避免刷新又重新打开
-->
<template>
  <Teleport to="body">
    <Transition name="public-help-fade">
      <div v-if="visible" class="public-help-drawer" role="dialog" aria-label="Help Center">
        <div class="public-help-drawer__mask" @click="handleClose"></div>
        <div class="public-help-drawer__wrapper" :style="wrapperStyle" :class="{ 'is-maximized': isMaximized }">
          <div class="public-help-drawer__header">
            <div class="public-help-drawer__title">
              <el-icon class="public-help-drawer__title-icon" :size="20">
                <QuestionFilled />
              </el-icon>
              <span>操作场景</span>
            </div>
            <div class="public-help-drawer__header-actions">
              <button
                type="button"
                class="public-help-drawer__header-btn"
                :aria-label="isMaximized ? 'Restore' : 'Maximize'"
                :title="isMaximized ? '还原' : '最大化'"
                @click="toggleMaximize"
              >
                <svg v-if="!isMaximized" viewBox="0 0 24 24" width="16" height="16">
                  <path
                    fill="currentColor"
                    d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"
                  />
                </svg>
                <svg v-else viewBox="0 0 24 24" width="16" height="16">
                  <path
                    fill="currentColor"
                    d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"
                  />
                </svg>
              </button>
              <button
                type="button"
                class="public-help-drawer__close"
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

          <div class="public-help-drawer__body">
            <HelpAccordion :scenario-id="scenarioId" :initial-step="initialStep" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { HelpAccordion } from '@/components/common/HelpAccordion'

const props = defineProps({
  width: {
    type: [Number, String],
    default: 880
  }
})

const visible = ref(false)
const scenarioId = ref(null)
const initialStep = ref(null)
// [FIX P3 2026-06-30] 公开版支持最大化, 与登录版体验一致
const isMaximized = ref(false)

function toggleMaximize() {
  isMaximized.value = !isMaximized.value
}

const wrapperStyle = computed(() => {
  if (isMaximized.value) return {}
  return {
    width: typeof props.width === 'number' ? `${props.width}px` : props.width
  }
})

function readUrl() {
  const params = new URLSearchParams(window.location.search)
  const help = params.get('help')
  const step = parseInt(params.get('step'), 10)
  if (help) {
    scenarioId.value = help
    initialStep.value = Number.isFinite(step) ? step : null
    // [FIX P3 2026-06-30] URL ?max=1 时默认最大化
    //   用于公开文档/演示/录屏场景, 一打开就是全屏
    isMaximized.value = params.get('max') === '1'
    return true
  }
  return false
}

function handleClose() {
  visible.value = false
  // 清理 URL 中的 help/max query, 避免刷新又重新打开
  const url = new URL(window.location.href)
  url.searchParams.delete('help')
  url.searchParams.delete('step')
  url.searchParams.delete('max')
  window.history.replaceState({}, '', url.toString())
}

function handleKeydown(e) {
  if (!visible.value) return
  if (e.key === 'Escape') {
    // 先还原最大化, 再关闭
    if (isMaximized.value) {
      isMaximized.value = false
    } else {
      handleClose()
    }
  }
}

watch(visible, (val) => {
  if (val) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
    isMaximized.value = false
  }
})

onMounted(() => {
  if (readUrl()) {
    visible.value = true
  }
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.public-help-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: var(--z-index-modal, 2000);
  display: flex;
  justify-content: flex-end;
}

.public-help-drawer__mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
}

.public-help-drawer__wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
  max-width: 95vw;
  background: var(--el-bg-color, #ffffff);
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
  height: 100%;
  transition: width 0.25s ease, max-width 0.25s ease;
}

/* [FIX P3 2026-06-30] 最大化 */
.public-help-drawer__wrapper.is-maximized {
  width: 100% !important;
  max-width: 100vw;
  height: 100%;
}

.public-help-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-lg, 24px);
  border-bottom: 1px solid var(--el-border-color-light, #ebeef5);
  flex-shrink: 0;
}

.public-help-drawer__title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  font-size: var(--el-font-size-large, 16px);
  font-weight: 600;
  color: var(--yonyou-orange-600, #ea580c);
}

.public-help-drawer__title-icon {
  color: var(--yonyou-orange-600, #ea580c);
}

.public-help-drawer__header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
}

.public-help-drawer__header-btn,
.public-help-drawer__close {
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

.public-help-drawer__header-btn:hover,
.public-help-drawer__close:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.public-help-drawer__body {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: var(--el-fill-color-blank, #ffffff);
}

.public-help-fade-enter-active,
.public-help-fade-leave-active {
  transition: opacity 0.25s ease;
}

.public-help-fade-enter-active .public-help-drawer__wrapper,
.public-help-fade-leave-active .public-help-drawer__wrapper {
  transition: transform 0.25s ease, width 0.25s ease, max-width 0.25s ease;
}

.public-help-fade-enter-from,
.public-help-fade-leave-to {
  opacity: 0;
}

.public-help-fade-enter-from .public-help-drawer__wrapper,
.public-help-fade-leave-to .public-help-drawer__wrapper {
  transform: translateX(100%);
}
</style>
