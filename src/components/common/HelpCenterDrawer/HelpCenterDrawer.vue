<!--
  HelpCenterDrawer - P3 简化
  - 删除"切换产品版本" subtab: 只保留 "archdata-management"
  - 删除"章节手册" tab: 整个 HelpCenterDrawer 只展示"操作场景"
  - 新增最大化按钮: 抽屉可展开至全屏
  - 新增 URL 自动展开: ?help=archdata-management&step=2 直接打开对应步骤
-->
<template>
  <Teleport to="body">
    <Transition name="help-drawer">
      <div v-if="modelValue" class="help-drawer" role="dialog" aria-label="Help Center">
        <div class="help-drawer__mask" @click="handleClose"></div>
        <div class="help-drawer__wrapper" :style="wrapperStyle" :class="{ 'is-maximized': isMaximized }">
          <div class="help-drawer__header">
            <div class="help-drawer__title">
              <el-icon class="help-drawer__title-icon" :size="20">
                <QuestionFilled />
              </el-icon>
              <span>操作场景</span>
            </div>
            <div class="help-drawer__header-actions">
              <button
                type="button"
                class="help-drawer__header-btn"
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
  modelValue: {
    type: Boolean,
    default: false
  },
  width: {
    type: [Number, String],
    default: 880
  },
  scenarioId: {
    type: String,
    default: 'archdata-management'
  },
  // [FIX P3 2026-06-30] initial-step 提升为 prop, 由父组件从 URL 解析传入
  initialStep: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'close'])

// [FIX P3 2026-06-30] 最大化状态
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

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}

function handleKeydown(e) {
  if (!props.modelValue) return
  if (e.key === 'Escape') {
    // 先还原最大化, 再关闭
    if (isMaximized.value) {
      isMaximized.value = false
    } else {
      handleClose()
    }
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
      isMaximized.value = false
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
  transition: width 0.25s ease, max-width 0.25s ease;
}

/* [FIX P3 2026-06-30] 最大化 */
.help-drawer__wrapper.is-maximized {
  width: 100% !important;
  max-width: 100vw;
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

.help-drawer-enter-active,
.help-drawer-leave-active {
  transition: opacity 0.25s ease;
}

.help-drawer-enter-active .help-drawer__wrapper,
.help-drawer-leave-active .help-drawer__wrapper {
  transition: transform 0.25s ease, width 0.25s ease, max-width 0.25s ease;
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
