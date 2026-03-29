<template>
  <div class="layout-selector">
    <!-- 布局引擎选择 -->
    <div class="config-section">
      <h3 class="section-title">布局引擎</h3>
      <div class="radio-group">
        <label class="radio-option" :class="{ active: layoutEngine === 'dagre' }">
          <input
            type="radio"
            value="dagre"
            :checked="layoutEngine === 'dagre'"
            @change="updateConfig('layoutEngine', 'dagre')"
          />
          <span class="radio-label">
            <span class="radio-name">Dagre（默认）</span>
            <span class="radio-desc">稳定可靠，自动布局</span>
          </span>
        </label>
        <label class="radio-option" :class="{ active: layoutEngine === 'elk' }">
          <input
            type="radio"
            value="elk"
            :checked="layoutEngine === 'elk'"
            @change="updateConfig('layoutEngine', 'elk')"
          />
          <span class="radio-label">
            <span class="radio-name">ELK（实验性）</span>
            <span class="radio-desc">更好的屏幕适配能力</span>
          </span>
        </label>
      </div>
    </div>

    <!-- 整体方向选择 -->
    <div class="config-section">
      <h3 class="section-title">整体方向</h3>
      <div class="overall-direction-section">
        <div class="direction-options">
          <label class="direction-option" :class="{ active: layoutControlConfig?.overallDirection === 'TB' }">
            <input
              type="radio"
              value="TB"
              :checked="layoutControlConfig?.overallDirection === 'TB'"
              @change="updateOverallDirection('TB')"
            />
            <span class="direction-icon">⬇️</span>
            <span class="direction-text">垂直排列</span>
            <span class="direction-hint">（从上到下）</span>
          </label>
          <label class="direction-option" :class="{ active: layoutControlConfig?.overallDirection === 'LR' }">
            <input
              type="radio"
              value="LR"
              :checked="layoutControlConfig?.overallDirection === 'LR'"
              @change="updateOverallDirection('LR')"
            />
            <span class="direction-icon">➡️</span>
            <span class="direction-text">水平排列</span>
            <span class="direction-hint">（从左到右）</span>
          </label>
        </div>
        <div class="direction-note">
          💡 提示：分组顺序受节点连线方向影响
        </div>
      </div>
    </div>

    <!-- 分组控制 -->
    <div class="config-section">
      <h3 class="section-title">分组控制</h3>
      <LayoutControlPanel
        :containers="containers"
        :model-value="layoutControlConfig"
        @update:model-value="handleLayoutControlUpdate"
      />
    </div>
  </div>
</template>

<script>
import LayoutControlPanel from './LayoutControlPanel.vue'

export default {
  name: 'LayoutSelector',
  components: {
    LayoutControlPanel
  },
  props: {
    layoutEngine: {
      type: String,
      default: 'dagre'
    },
    containers: {
      type: Array,
      default: () => []
    },
    layoutControlConfig: {
      type: Object,
      default: () => ({
        enabled: false,
        overallDirection: 'TB',
        groups: [],
        engine: 'dagre',
        preserveOrder: true
      })
    }
  },
  emits: ['update:config', 'update:layoutControlConfig'],
  methods: {
    updateConfig(key, value) {
      console.log('[LayoutSelector] updateConfig:', key, '=', value)
      this.$emit('update:config', { [key]: value })
    },
    handleLayoutControlUpdate(value) {
      console.log('[LayoutSelector] handleLayoutControlUpdate:', value)
      this.$emit('update:layoutControlConfig', value)
    },
    updateOverallDirection(direction) {
      console.log('[LayoutSelector] updateOverallDirection:', direction)
      const newConfig = {
        ...this.layoutControlConfig,
        overallDirection: direction
      }
      this.$emit('update:layoutControlConfig', newConfig)
    }
  }
}
</script>

<style scoped lang="scss">
.layout-selector {
  margin-top: 0;
}

.config-section {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  margin-bottom: var(--spacing-md);
  color: var(--color-text-primary);
}

.overall-direction-section {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.direction-options {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
}

.direction-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;

  input {
    display: none;
  }

  &:hover {
    border-color: var(--color-primary-light);
    background: rgba(24, 144, 255, 0.04);
  }

  &.active {
    border-color: var(--color-primary);
    background: rgba(24, 144, 255, 0.08);
  }
}

.direction-icon {
  font-size: 16px;
}

.direction-text {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.direction-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.direction-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: rgba(24, 144, 255, 0.04);
  border-radius: var(--radius-sm);
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.radio-option {
  display: flex;
  align-items: flex-start;
  padding: var(--spacing-md);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;

  input {
    display: none;
  }

  &:hover {
    border-color: var(--color-primary-light);
  }

  &.active {
    border-color: var(--color-primary);
    background: rgba(24, 144, 255, 0.08);
  }
}

.radio-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.radio-name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.radio-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
</style>
