<template>
  <div
    :class="['collapsible-panel', {
      'is-collapsed': !expanded,
      'cp--height-full': heightFull
    }, props.class]"
    :style="containerStyle"
  >
    <div
      v-if="collapsible && collapsePosition === 'outside'"
      class="collapsible-panel__collapse-btn"
      @click="handleToggle"
      :title="expanded ? '折叠' : '展开'"
    >
      <el-icon :size="16">
        <ArrowLeft v-if="!expanded" />
        <ArrowRight v-else />
      </el-icon>
    </div>

    <div class="collapsible-panel__container">
      <div
        v-if="collapsible"
        class="collapsible-panel__header"
        @click="handleToggle"
      >
        <div class="collapsible-panel__header-left">
          <slot name="header">
            <span v-if="title" class="collapsible-panel__title">{{ title }}</span>
            <span v-if="badge" class="collapsible-panel__badge">
              {{ badge }}
            </span>
          </slot>
        </div>

        <div class="collapsible-panel__header-right">
          <slot name="extra" />
          <button
            v-if="collapsible && collapsePosition === 'header'"
            class="collapsible-panel__toggle"
            type="button"
          >
            <el-icon :size="14">
              <ArrowUp v-if="expanded" />
              <ArrowDown v-else />
            </el-icon>
          </button>
        </div>
      </div>

      <div v-show="expanded || !collapsible" class="collapsible-panel__content">
        <slot />
      </div>

      <div
        v-if="resizable && expanded"
        class="collapsible-panel__resizer"
        @mousedown="startResize"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ArrowLeft, ArrowRight, ArrowUp, ArrowDown } from '@element-plus/icons-vue'

/**
 * @typedef {Object} CollapsiblePanelProps
 * @property {string} [title] - 面板标题
 * @property {number|null} [badge] - 标题栏徽章数字
 * @property {boolean} [collapsible] - 是否可折叠
 * @property {boolean} [defaultExpanded] - 默认展开状态
 * @property {boolean} [resizable] - 是否可拖拽调整宽度
 * @property {number} [minWidth] - 最小宽度 (px)
 * @property {number} [maxWidth] - 最大宽度 (px)
 * @property {number} [defaultWidth] - 默认宽度 (px)
 * @property {'header'|'outside'} [collapsePosition] - 折叠按钮位置
 * @property {boolean} [heightFull] - 高度是否100%
 * @property {string} [class] - 额外CSS类
 */

/** @type {CollapsiblePanelProps} */
const props = defineProps({
  /** 面板标题 */
  title: {
    type: String,
    default: ''
  },
  /** 标题栏徽章数字 */
  badge: {
    type: Number,
    default: null
  },
  /** 是否可折叠 */
  collapsible: {
    type: Boolean,
    default: true
  },
  /** 默认展开状态 */
  defaultExpanded: {
    type: Boolean,
    default: true
  },
  /** 是否可拖拽调整宽度 */
  resizable: {
    type: Boolean,
    default: false
  },
  /** 最小宽度 (px) */
  minWidth: {
    type: Number,
    default: 200
  },
  /** 最大宽度 (px) */
  maxWidth: {
    type: Number,
    default: 600
  },
  /** 默认宽度 (px) */
  defaultWidth: {
    type: Number,
    default: 280
  },
  /** 折叠按钮位置 */
  collapsePosition: {
    type: String,
    default: 'header',
    validator: (v) => ['header', 'outside'].includes(v)
  },
  /** 高度是否100% */
  heightFull: {
    type: Boolean,
    default: true
  },
  /** 额外CSS类 */
  class: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:expanded', 'update:width', 'toggle', 'resize'])

const expanded = ref(props.defaultExpanded)
const currentWidth = ref(props.defaultWidth)
const isResizing = ref(false)

const containerStyle = computed(() => {
  const style = {}

  if (props.heightFull) {
    style.height = '100%'
  }

  if (!expanded.value) {
    if (props.heightFull) {
      style.width = '48px'
      style.minWidth = '48px'
    }
  } else {
    style.width = `${currentWidth.value}px`
  }

  return style
})

watch(() => props.defaultExpanded, (val) => {
  expanded.value = val
})

/**
 * 处理折叠/展开切换
 */
function handleToggle() {
  if (!props.collapsible) return
  expanded.value = !expanded.value
  emit('update:expanded', expanded.value)
  emit('toggle', expanded.value)
}

/**
 * 开始拖拽调整宽度
 * @param {MouseEvent} e
 */
function startResize(e) {
  if (!props.resizable || !expanded.value) return

  e.preventDefault()
  isResizing.value = true

  const startX = e.clientX
  const startWidth = currentWidth.value

  const handleMouseMove = (moveEvent) => {
    const delta = moveEvent.clientX - startX
    const newWidth = Math.min(
      props.maxWidth,
      Math.max(props.minWidth, startWidth + delta)
    )
    currentWidth.value = newWidth
  }

  const handleMouseUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    emit('update:width', currentWidth.value)
    emit('resize', currentWidth.value)
  }

  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
</script>

<style scoped>
.collapsible-panel {
  display: flex;
  position: relative;
  background: var(--color-bg-container);
  transition: width 0.3s ease;
  overflow: hidden;
}

.collapsible-panel.is-collapsed {
  width: 48px;
  min-width: 48px;
}

/* Vertical panel: keep full width when collapsed */
.collapsible-panel.is-collapsed:not(.cp--height-full) {
  width: auto;
  min-width: auto;
}

.collapsible-panel__collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  flex-shrink: 0;
  cursor: pointer;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-right: var(--border-width-thin) solid var(--color-border);
  transition: all 0.2s;
}

.collapsible-panel__collapse-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.collapsible-panel__container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  position: relative;
  border-right: var(--border-width-thin) solid var(--color-border);
}

.collapsible-panel.is-collapsed .collapsible-panel__container {
  border-right: none;
}

.collapsible-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  user-select: none;
  border-bottom: var(--border-width-thin) solid var(--color-border);
  background: var(--color-bg-secondary);
  min-height: 48px;
}

.collapsible-panel__header:hover {
  background: var(--color-bg-hover);
}

.collapsible-panel__header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.collapsible-panel__title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.collapsible-panel__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  background: var(--color-primary-bg, #fff7ed);
  color: var(--color-primary, #ea580c);
  border-radius: 10px;
  font-size: var(--font-size-xs, 11px);
  font-weight: 500;
  flex-shrink: 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.collapsible-panel__header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

.collapsible-panel__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}

.collapsible-panel__toggle:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.collapsible-panel__content {
  flex: 1;
  overflow: auto;
  min-height: 0;
}

.collapsible-panel__resizer {
  position: absolute;
  top: 0;
  right: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s;
  z-index: 10;
}

.collapsible-panel__resizer:hover {
  background: var(--color-primary-light-8);
}

.collapsible-panel__resizer:active {
  background: var(--color-primary);
}
</style>
