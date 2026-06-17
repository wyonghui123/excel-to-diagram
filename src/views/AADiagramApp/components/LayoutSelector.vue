<template>
  <div class="layout-selector">
    <div class="config-section global-group-section">
      <div class="global-group-header">
        <h3 class="section-title">分组控制</h3>
        <div class="header-actions">
          <div class="direction-toggle">
            <button
              class="direction-btn"
              :class="{ active: diagramConfigStore.layoutControlConfig?.overallDirection === 'LR' }"
              @click="updateOverallDirection('LR')"
              title="水平排列 (Left to Right)"
            >
              <AppIcon name="arrow-right" size="sm" />
              <span class="direction-label">水平</span>
            </button>
            <button
              class="direction-btn"
              :class="{ active: diagramConfigStore.layoutControlConfig?.overallDirection === 'TB' }"
              @click="updateOverallDirection('TB')"
              title="垂直排列 (Top to Bottom)"
            >
              <AppIcon name="arrow-down" size="sm" />
              <span class="direction-label">垂直</span>
            </button>
          </div>
          <button class="action-btn auto-group-btn" @click="handleAutoGroup" title="基于领域自动分组">
            <AppIcon name="lightning" size="sm" />
            <span>自动分组</span>
          </button>
          <button 
            class="action-btn advanced-mode-btn" 
            :class="{ active: advancedMode }"
            @click="advancedMode = !advancedMode" 
            title="高级模式"
          >
            <AppIcon name="settings" size="sm" />
            <span>高级</span>
          </button>
          <button class="action-btn add-group-btn" @click="handleAddGroup" title="新增分组">
            <AppIcon name="plus" size="sm" />
          </button>
        </div>
      </div>
      
      <!-- 高级模式展开区域 -->
      <div v-if="advancedMode" class="advanced-actions">
        <div class="virtual-layer-control">
          <button class="action-btn virtual-layer-btn" @click="showVirtualLayerDialog = true" title="自动虚拟分层">
            <AppIcon name="layers" size="sm" />
            <span>虚拟分层</span>
          </button>
          <div v-if="showVirtualLayerDialog" class="virtual-layer-dialog">
            <div class="dialog-title">自动虚拟分层</div>
            <div class="dialog-content">
              <label>分层数量：</label>
              <input
                type="number"
                v-model.number="virtualLayerCount"
                min="1"
                max="10"
                class="layer-count-input"
              />
            </div>
            <div class="dialog-actions">
              <button class="dialog-btn cancel" @click="showVirtualLayerDialog = false">取消</button>
              <button class="dialog-btn confirm" @click="handleAutoVirtualLayering">确定</button>
            </div>
          </div>
        </div>
        <button 
          class="action-btn sort-btn" 
          @click="handleOverallSort" 
          :disabled="!hasGroups"
          :title="hasGroups ? '对所有顶层分组进行排序' : '需要先创建分组'"
        >
          <AppIcon name="sort" size="sm" />
          <span>整体排序</span>
        </button>
        <button 
          class="action-btn sort-btn" 
          @click="handleInLayerSort" 
          :disabled="!hasVirtualLayers"
          :title="hasVirtualLayers ? '对每个虚拟层内部进行排序' : '需要先进行虚拟分层'"
        >
          <AppIcon name="sort" size="sm" />
          <span>层内排序</span>
        </button>
        <button 
          class="action-btn optimize-btn" 
          @click="handleOptimizeGroupState" 
          :disabled="!hasGroups"
          :title="hasGroups ? '优化大分组的启用状态，改善布局均衡性' : '需要先创建分组'"
        >
          <AppIcon name="settings" size="sm" />
          <span>优化分组</span>
        </button>
      </div>
    </div>

    <div class="config-section">
      <LayoutControlPanel
        ref="layoutControlPanelRef"
        :containers="containers"
        :domain-products="domainProducts || []"
        :chart-type="diagramConfigStore.chartType"
        :chart-type-changed="diagramConfigStore.chartTypeChanged"
        :model-value="diagramConfigStore.layoutControlConfig"
        :color-scheme="diagramConfigStore.colorScheme"
        :color-group-by="diagramConfigStore.colorGroupBy"
        :custom-colors="diagramConfigStore.customColors"
        :color-mapping="colorMapping"
        :links="links"
        :center-scope="passedCenterScope"
        :center-scope-markers="passedCenterScopeMarkers"
        :center-scope-color="diagramConfigStore.centerScopeColor"
        @update:model-value="handleLayoutControlUpdate"
        @reset-chart-type-changed="diagramConfigStore.resetChartTypeChanged()"
      />
    </div>
  </div>
</template>

<script>
import LayoutControlPanel from './LayoutControlPanel.vue'
import { AppIcon } from '@/components/common/AppIcon'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

export default {
  name: 'LayoutSelector',
  components: {
    LayoutControlPanel,
    AppIcon
  },
  props: {
    containers: {
      type: Array,
      default: () => []
    },
    links: {
      type: Array,
      default: () => []
    },
    colorMapping: {
      type: Object,
      default: () => ({})
    },
    domainProducts: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:config', 'update:layoutControlConfig', 'add-group', 'reset-chart-type-changed'],
  setup() {
    const diagramConfigStore = useDiagramConfigStore()
    return {
      diagramConfigStore
    }
  },
  data() {
    return {
      showVirtualLayerDialog: false,
      virtualLayerCount: 3,
      advancedMode: false
    }
  },
  watch: {
    domainProducts: {
      immediate: true,
      handler(newVal) {
        if (!newVal) {
          console.warn('[LayoutSelector] domainProducts is null or undefined!')
        }
      }
    },
    'diagramConfigStore.centerScope': {
      immediate: true,
      handler(newVal) {
      }
    },
    'diagramConfigStore.centerScopeMarkers': {
      immediate: true,
      handler(newVal) {
      }
    },
    'diagramConfigStore.centerScopeColor': {
      immediate: true,
      handler(newVal, oldVal) {
      }
    }
  },
  computed: {
    passedDomainProducts() {
      return this.domainProducts || []
    },
    passedCenterScope() {
      return this.diagramConfigStore.centerScope || []
    },
    passedCenterScopeMarkers() {
      return this.diagramConfigStore.centerScopeMarkers || { domains: new Map(), subDomains: new Map(), serviceModules: new Map() }
    },
    hasGroups() {
      const groups = this.diagramConfigStore.layoutControlConfig?.groups
      return groups && groups.length > 0
    },
    hasVirtualLayers() {
      const groups = this.diagramConfigStore.layoutControlConfig?.groups
      if (!groups || groups.length === 0) return false
      return groups.some(g => g._isVirtualLayer)
    }
  },
  methods: {
    updateConfig(key, value) {
      this.$emit('update:config', { [key]: value })
    },
    handleLayoutControlUpdate(value) {
      this.diagramConfigStore.updateLayoutControlConfig(value)
    },
    updateOverallDirection(direction) {
      const newConfig = {
        ...this.diagramConfigStore.layoutControlConfig,
        overallDirection: direction
      }
      this.diagramConfigStore.updateLayoutControlConfig(newConfig)
    },
    handleAddGroup() {
      this.$emit('add-group')
    },
    handleAutoGroup() {
      const panelRef = this.$refs.layoutControlPanelRef
      if (panelRef && panelRef.handleAutoGroupByDomain) {
        panelRef.handleAutoGroupByDomain()
      } else {
        console.warn('[LayoutSelector] layoutControlPanelRef is null or method not found')
      }
    },
    handleAutoVirtualLayering() {
      this.showVirtualLayerDialog = false
      const panelRef = this.$refs.layoutControlPanelRef
      if (panelRef && panelRef.handleAutoVirtualLayering) {
        panelRef.handleAutoVirtualLayering(this.virtualLayerCount)
      } else {
        console.warn('[LayoutSelector] layoutControlPanelRef is null or handleAutoVirtualLayering not found')
      }
    },
    handleOverallSort() {
      const panelRef = this.$refs.layoutControlPanelRef
      if (panelRef && panelRef.handleOverallSort) {
        panelRef.handleOverallSort()
      } else {
        console.warn('[LayoutSelector] layoutControlPanelRef is null or handleOverallSort not found')
      }
    },
    handleInLayerSort() {
      const panelRef = this.$refs.layoutControlPanelRef
      if (panelRef && panelRef.handleInLayerSort) {
        panelRef.handleInLayerSort()
      } else {
        console.warn('[LayoutSelector] layoutControlPanelRef is null or handleInLayerSort not found')
      }
    },
    handleOptimizeGroupState() {
      const panelRef = this.$refs.layoutControlPanelRef
      if (panelRef && panelRef.optimizeGroupEnabledState) {
        panelRef.optimizeGroupEnabledState()
      } else {
        console.warn('[LayoutSelector] layoutControlPanelRef is null or optimizeGroupEnabledState not found')
      }
    }
  }
}
</script>

<style scoped lang="scss">
.layout-selector {
  margin-top: 0;
}

.config-section {
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--color-border);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin-bottom: 0;
  color: var(--color-text-primary);
}

.global-group-section {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
}

.global-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.direction-toggle {
  display: flex;
  gap: 2px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-sm);
  padding: 2px;
  border: 1px solid var(--color-border);
}

.direction-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  background: transparent;
  border-radius: var(--radius-xs);
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  transition: all 0.2s ease;

  .direction-icon {
    font-size: 12px;
  }

  .direction-label {
    font-weight: 500;
  }

  &:hover {
    background: rgba(234, 88, 12, 0.08);
    color: var(--color-primary);
  }

  &.active {
    background: var(--color-primary);
    color: white;
  }
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  background: white;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--color-text-primary);

  .btn-icon {
    font-size: 12px;
  }

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
}

.auto-group-btn {
  &:hover {
    background: rgba(234, 88, 12, 0.04);
  }
}

.add-group-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px dashed var(--color-border);
  background: white;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--color-text-primary);
  padding: 0;
  font-size: 16px;
  font-weight: 500;

  .plus-icon {
    line-height: 1;
  }

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(234, 88, 12, 0.04);
  }
}

.virtual-layer-control {
  position: relative;
}

.virtual-layer-dialog {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  padding: var(--spacing-sm);
  z-index: 100;
  min-width: 180px;

  .dialog-title {
    font-size: var(--font-size-sm);
    font-weight: 600;
    margin-bottom: var(--spacing-sm);
    color: var(--color-text-primary);
  }

  .dialog-content {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);

    label {
      font-size: var(--font-size-xs);
      color: var(--color-text-secondary);
    }

    .layer-count-input {
      width: 60px;
      padding: 4px 8px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-xs);
      font-size: var(--font-size-xs);
    }
  }

  .dialog-actions {
    display: flex;
    gap: var(--spacing-xs);
    justify-content: flex-end;

    .dialog-btn {
      padding: 4px 12px;
      border-radius: var(--radius-xs);
      font-size: var(--font-size-xs);
      cursor: pointer;
      border: 1px solid var(--color-border);

      &.cancel {
        background: white;
        color: var(--color-text-secondary);
      }

      &.confirm {
        background: var(--color-primary);
        color: white;
        border-color: var(--color-primary);

        &:hover {
          background: darken(#ea580c, 10%);
        }
      }
    }
  }
}

.sort-btn {
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    
    &:hover {
      border-color: var(--color-border);
      color: var(--color-text-primary);
    }
  }
}

.optimize-btn {
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    
    &:hover {
      border-color: var(--color-border);
      color: var(--color-text-primary);
    }
  }
}

.advanced-mode-btn {
  &.active {
    background: var(--color-primary);
    color: white;
    border-color: var(--color-primary);
  }
}

.advanced-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px dashed var(--color-border);
  animation: slideDown 0.2s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
