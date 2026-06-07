<template>
  <div class="master-detail-layout" :class="{ 'master-detail-layout--collapsed': isCollapsed }">
    <aside
      :class="['master-detail-layout__sidebar', { 'master-detail-layout__sidebar--collapsed': isCollapsed }]"
      :style="sidebarStyle"
    >
      <div class="master-detail-layout__sidebar-content">
        <slot name="master" />
      </div>
    </aside>

    <button
      v-if="sidebarCollapsible"
      class="master-detail-layout__collapse-btn"
      :class="{ 'master-detail-layout__collapse-btn--collapsed': isCollapsed }"
      :style="collapseBtnStyle"
      @click="toggleCollapse"
      :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
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

    <div
      v-if="showBorder && !isCollapsed"
      class="master-detail-layout__resizer"
      @mousedown="startResize"
    />

    <main class="master-detail-layout__detail">
      <slot name="detail" />
      <slot name="empty" />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

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
const currentWidth = ref(parseInt(props.sidebarWidth, 10))
const isResizing = ref(false)

const sidebarStyle = computed(() => {
  if (isCollapsed.value) {
    return { width: '0px' }
  }
  return { width: `${currentWidth.value}px` }
})

const collapseBtnStyle = computed(() => {
  if (isCollapsed.value) {
    return { left: '0px' }
  }
  return { left: `${currentWidth.value}px` }
})

function toggleCollapse() {
  const newState = !isCollapsed.value
  emit('update:sidebarCollapsed', newState)
  emit('collapse-change', newState)
}

function startResize(event) {
  if (isCollapsed.value) return
  
  isResizing.value = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function handleResize(event) {
  if (!isResizing.value) return
  
  const newWidth = event.clientX
  if (newWidth >= props.minWidth && newWidth <= props.maxWidth) {
    currentWidth.value = newWidth
  }
}

function stopResize() {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onMounted(() => {
  currentWidth.value = parseInt(props.sidebarWidth, 10)
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
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

.master-detail-layout__sidebar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-container);
  border-right: 1px solid var(--color-border);
  transition: width var(--transition-normal);
  overflow: hidden;
  position: relative;
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
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  cursor: pointer;
  z-index: 10;
  color: var(--color-text-secondary);
  transition: all var(--transition-fast), left var(--transition-normal);
}

.master-detail-layout--collapsed .master-detail-layout__collapse-btn {
  border-left: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.08);
}

.master-detail-layout__collapse-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.master-detail-layout__collapse-icon {
  width: 16px;
  height: 16px;
  transition: transform var(--transition-normal);
}

.master-detail-layout__collapse-icon--collapsed {
  transform: rotate(180deg);
}

.master-detail-layout__resizer {
  width: 6px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  position: relative;
  transition: background var(--transition-fast);
}

.master-detail-layout__resizer:hover {
  background: var(--color-primary-light);
}

.master-detail-layout__resizer:active {
  background: var(--color-primary);
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

  .master-detail-layout__collapse-btn {
    left: auto;
    right: 0;
    top: 0;
    transform: none;
    border-left: 1px solid var(--color-border);
    border-radius: 0 0 0 var(--radius-sm);
    margin-left: 0;
    width: 48px;
    height: 24px;
  }

  .master-detail-layout--collapsed .master-detail-layout__collapse-btn {
    left: auto;
    right: 0;
    border-radius: var(--radius-sm);
  }

  .master-detail-layout__collapse-icon {
    transform: rotate(-90deg);
  }

  .master-detail-layout__collapse-icon--collapsed {
    transform: rotate(90deg);
  }
}
</style>
