<template>
  <div
    ref="rootRef"
    class="master-detail-layout"
    :class="{ 'master-detail-layout--collapsed': isCollapsed, 'master-detail-layout--resizing': isResizing }"
  >
    <aside
      :class="['master-detail-layout__sidebar', { 'master-detail-layout__sidebar--collapsed': isCollapsed }]"
      :style="sidebarStyle"
    >
      <div class="master-detail-layout__sidebar-header">
        <slot name="sidebar-header" />
        <button
          v-if="sidebarCollapsible && !isCollapsed"
          class="master-detail-layout__collapse-btn"
          @click="toggleCollapse"
          title="折叠侧边栏"
          type="button"
        >
          <svg class="master-detail-layout__collapse-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      </div>
      <div class="master-detail-layout__sidebar-content">
        <slot name="master" />
      </div>
    </aside>

    <div
      v-if="showBorder && !isCollapsed"
      ref="resizerRef"
      class="master-detail-layout__resizer"
      :class="{ 'master-detail-layout__resizer--dragging': isResizing }"
      title="左右拖动调整宽度"
      @mousedown="startResize"
      @touchstart="startResize"
    >
      <span class="master-detail-layout__resizer-handle" aria-hidden="true" />
    </div>

    <main class="master-detail-layout__detail">
      <slot name="detail" />
      <slot name="empty" />
    </main>

    <!--
      折叠态展开按钮：独立于 sidebar（sidebar 已 width:0 + overflow:hidden），
      固定在左上角，不与 resizer 重叠（resizer 在 v-if="!isCollapsed" 时已隐藏）。
    -->
    <button
      v-if="sidebarCollapsible && isCollapsed"
      class="master-detail-layout__expand-btn"
      @click="toggleCollapse"
      title="展开侧边栏"
      type="button"
    >
      <svg class="master-detail-layout__expand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 6 15 12 9 18" />
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  sidebarWidth: {
    type: String,
    default: '280px'
  },
  sidebarCollapsible: {
    type: Boolean,
    default: false
  },
  sidebarCollapsed: {
    type: Boolean,
    default: false
  },
  showBorder: {
    type: Boolean,
    default: true
  },
  minWidth: {
    type: Number,
    default: 200
  },
  maxWidth: {
    type: Number,
    default: 500
  }
})

const emit = defineEmits(['update:sidebarCollapsed', 'collapse-change'])

const isCollapsed = computed(() => props.sidebarCollapsed)
const currentWidth = ref(parseInt(props.sidebarWidth, 10) || 280)
const isResizing = ref(false)
const rootRef = ref(null)
const resizerRef = ref(null)

/**
 * 响应 props.sidebarWidth 变化：仅在非拖拽态同步，避免覆盖用户拖拽结果
 */
watch(() => props.sidebarWidth, (newVal) => {
  if (isResizing.value) return
  const parsed = parseInt(newVal, 10)
  if (!Number.isNaN(parsed) && parsed > 0) {
    currentWidth.value = parsed
  }
})

const sidebarStyle = computed(() => {
  if (isCollapsed.value) {
    return { width: '0px' }
  }
  return { width: `${currentWidth.value}px` }
})

function toggleCollapse() {
  const newState = !isCollapsed.value
  emit('update:sidebarCollapsed', newState)
  emit('collapse-change', newState)
}

function getClientX(event) {
  if (!event) return 0
  if (event.touches && event.touches.length) {
    return event.touches[0].clientX
  }
  if (event.changedTouches && event.changedTouches.length) {
    return event.changedTouches[0].clientX
  }
  return event.clientX
}

function getRootOffsetLeft() {
  if (!rootRef.value) return 0
  const rect = rootRef.value.getBoundingClientRect()
  return rect && typeof rect.left === 'number' ? rect.left : 0
}

function startResize(event) {
  if (isCollapsed.value) return

  isResizing.value = true
  document.addEventListener('mousemove', handleResize, { passive: false })
  document.addEventListener('mouseup', stopResize)
  document.addEventListener('touchmove', handleResize, { passive: false })
  document.addEventListener('touchend', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function handleResize(event) {
  if (!isResizing.value) return
  if (event && event.cancelable) event.preventDefault()

  const clientX = getClientX(event)
  const offsetLeft = getRootOffsetLeft()
  const newWidth = clientX - offsetLeft
  // 防御：确保 minWidth/maxWidth 是数字（父组件可能传字符串 "240px"）
  const minW = Number(props.minWidth) || 200
  const maxW = Number(props.maxWidth) || 500
  const clampedWidth = Math.min(maxW, Math.max(minW, Math.round(newWidth)))
  currentWidth.value = clampedWidth
}

function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  document.removeEventListener('touchmove', handleResize)
  document.removeEventListener('touchend', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onBeforeUnmount(() => {
  stopResize()
})
</script>

<style scoped>
.master-detail-layout {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-primary);
  position: relative;
}

/* 拖拽中：禁用 sidebar 的 width transition 避免视觉延迟 */
.master-detail-layout--resizing .master-detail-layout__sidebar {
  transition: none !important;
}

.master-detail-layout__sidebar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-container);
  border-right: 1px solid var(--color-border);
  transition: width var(--transition-normal);
  overflow: hidden;
  position: relative;
  min-width: 0;
}

.master-detail-layout__sidebar--collapsed {
  width: 0 !important;
  border-right: none;
}

.master-detail-layout__sidebar-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 4px 8px 0 8px;
  min-height: 32px;
  gap: 8px;
}

.master-detail-layout__sidebar-content {
  flex: 1;
  overflow: auto;
  min-width: 0;
}

/* 折叠按钮：在 sidebar header 内部右侧，不与 resizer 重叠 */
.master-detail-layout__collapse-btn {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: background-color 0.15s ease, color 0.15s ease;
  padding: 0;
}

.master-detail-layout__collapse-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.master-detail-layout__collapse-icon {
  width: 14px;
  height: 14px;
}

/* 展开按钮：sidebar 折叠时显示，固定在左上角 */
.master-detail-layout__expand-btn {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  z-index: 20;
  color: var(--color-text-secondary);
  transition: background-color 0.15s ease, color 0.15s ease;
  padding: 0;
  box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.1);
}

.master-detail-layout__expand-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.master-detail-layout__expand-icon {
  width: 16px;
  height: 16px;
}

/* 拖拽分隔条：可见的握把 + 宽 hit 区域 */
.master-detail-layout__resizer {
  flex-shrink: 0;
  width: 8px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  touch-action: none;
  /* 不用负 margin，避免 hit area 异常 */
}

.master-detail-layout__resizer-handle {
  width: 2px;
  height: 32px;
  background: var(--color-border);
  border-radius: 1px;
  transition: background 0.15s ease, height 0.15s ease;
  pointer-events: none;
  flex-shrink: 0;
}

.master-detail-layout__resizer:hover .master-detail-layout__resizer-handle,
.master-detail-layout__resizer--dragging .master-detail-layout__resizer-handle {
  background: var(--color-primary);
  height: 56px;
}

.master-detail-layout__detail {
  flex: 1;
  min-width: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  .master-detail-layout {
    flex-direction: column;
  }

  .master-detail-layout__sidebar {
    width: 100% !important;
    max-height: 40vh;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }

  .master-detail-layout__sidebar--collapsed {
    max-height: 0;
    border-bottom: none;
  }

  .master-detail-layout__resizer {
    display: none;
  }

  .master-detail-layout__collapse-btn,
  .master-detail-layout__expand-btn {
    width: 48px;
    height: 24px;
  }
}
</style>
