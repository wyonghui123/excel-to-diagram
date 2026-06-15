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
      折叠按钮：放在 layout 根级别（不是 sidebar 内部），避免 sidebar 折叠 width:0 时被 overflow:hidden 裁掉。
      通过 v-if 控制渲染，折叠态也显示以便用户重新展开。
    -->
    <button
      v-if="sidebarCollapsible"
      class="master-detail-layout__collapse-btn"
      :class="{ 'master-detail-layout__collapse-btn--collapsed': isCollapsed }"
      @click="toggleCollapse"
      :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
      :style="collapseBtnStyle"
      type="button"
    >
      <svg
        class="master-detail-layout__collapse-icon"
        :class="{ 'master-detail-layout__collapse-icon--collapsed': isCollapsed }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'

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

const sidebarStyle = computed(() => {
  if (isCollapsed.value) {
    return { width: '0px' }
  }
  return { width: `${currentWidth.value}px` }
})

/**
 * 折叠按钮位置：始终位于 sidebar 右边缘外侧
 * - 展开态：left = sidebar 宽度，固定不动
 * - 折叠态：left = 8px（左对齐），方便用户找到
 */
const collapseBtnStyle = computed(() => {
  if (isCollapsed.value) {
    return { left: '8px' }
  }
  return { left: `${currentWidth.value - 12}px` }
})

function toggleCollapse() {
  const newState = !isCollapsed.value
  emit('update:sidebarCollapsed', newState)
  emit('collapse-change', newState)
}

function getClientX(event) {
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
  document.body.style.overflow = ''
}

onMounted(async () => {
  await nextTick()
  const parsed = parseInt(props.sidebarWidth, 10)
  if (!Number.isNaN(parsed) && parsed > 0) {
    currentWidth.value = parsed
  }
})

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

.master-detail-layout__sidebar-content {
  flex: 1;
  overflow: auto;
  min-width: 0;
}

/* 拖拽分隔条：可见的握把 + 宽 hit 区域 */
.master-detail-layout__resizer {
  flex-shrink: 0;
  width: 12px;
  /* 负 margin-left 让 hit 区域跨越 sidebar 边缘 6px，hit-test 体验更好 */
  margin-left: -6px;
  margin-right: -6px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 让 hit 区域不因 margin 收缩 */
  pointer-events: auto;
  touch-action: none;
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

/*
 * 折叠按钮：放在 layout 根级别，避免 sidebar 折叠时 overflow:hidden 裁切
 * - 展开态：left = sidebar.width - 12 (盖在 sidebar 右边线上)
 * - 折叠态：left = 8px (独立显示在左边缘)
 */
.master-detail-layout__collapse-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  z-index: 20;
  color: var(--color-text-secondary);
  transition: background-color 0.15s ease, color 0.15s ease, left var(--transition-normal), border-radius 0.15s ease;
  padding: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.master-detail-layout__collapse-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  z-index: 21;
}

.master-detail-layout__collapse-btn--collapsed {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.12);
}

.master-detail-layout__collapse-icon {
  width: 16px;
  height: 16px;
  transition: transform var(--transition-normal);
}

.master-detail-layout__collapse-icon--collapsed {
  transform: rotate(180deg);
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

  .master-detail-layout__collapse-btn {
    top: 0;
    right: 0;
    left: auto !important;
    transform: none;
    border-radius: 0 0 0 var(--radius-sm);
    width: 48px;
    height: 24px;
  }

  .master-detail-layout__collapse-icon {
    transform: rotate(-90deg);
  }

  .master-detail-layout__collapse-icon--collapsed {
    transform: rotate(90deg);
  }
}
</style>
