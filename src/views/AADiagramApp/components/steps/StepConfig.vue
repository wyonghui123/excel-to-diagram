<template>
  <div class="step-config">
    <div class="config-panel">
      <div class="panel-body no-padding-top">
        <template v-if="chartType === 'businessObject'">
          <CenterDomainSelect
            v-if="previewData"
            :color-group-by="configStore.colorGroupBy"
            :color-scheme="configStore.colorScheme"
            :node-text-color="configStore.nodeTextColor"
            :center-scope-color="configStore.centerScopeColor"
            :custom-colors="configStore.customColors || {}"
            :sub-domains="subDomains"
            :domains="domains"
            :service-modules="serviceModules"
            :center-scope-markers="passedCenterScopeMarkers"
            :center-scope-bo-codes="centerScopeBoCodes"
            :business-objects="businessObjects"
            :center-scope-highlight="configStore.centerScopeHighlight"
            :annotation-category-filter="configStore.annotationCategoryFilter"
            @update:colorGroupBy="configStore.updateColorGroupBy"
            @update:colorScheme="configStore.updateColorScheme"
            @update:nodeTextColor="configStore.updateNodeTextColor"
            @update:centerScopeColor="configStore.updateCenterScopeColor"
            @update:customColors="configStore.updateCustomColors"
            @update:centerScopeHighlight="configStore.updateCenterScopeHighlight"
            @update:annotationCategoryFilter="configStore.setAnnotationCategoryFilter"
          />
        </template>

        <template v-if="chartType === 'serviceModule'">
          <ServiceModuleConfig
            v-if="previewData"
            :color-group-by="configStore.colorGroupBy"
            :color-scheme="configStore.colorScheme"
            :node-text-color="configStore.nodeTextColor"
            :center-scope-color="configStore.centerScopeColor || '#808080'"
            :custom-colors="configStore.customColors || {}"
            :sub-domains="subDomains"
            :domains="domains"
            :service-modules="serviceModules"
            :center-scope="configStore.centerScope"
            :center-scope-highlight="configStore.centerScopeHighlight"
            :business-objects="businessObjects"
            :annotation-category-filter="configStore.annotationCategoryFilter"
            @update:colorGroupBy="configStore.updateColorGroupBy"
            @update:colorScheme="configStore.updateColorScheme"
            @update:nodeTextColor="configStore.updateNodeTextColor"
            @update:centerScopeColor="configStore.updateCenterScopeColor"
            @update:customColors="configStore.updateCustomColors"
            @update:centerScopeHighlight="configStore.updateCenterScopeHighlight"
            @update:annotationCategoryFilter="configStore.setAnnotationCategoryFilter"
          />
        </template>

        <LayoutSelector
          ref="layoutSelectorRef"
          v-if="previewData && containers.length > 0"
          :layout-engine="configStore.layoutEngine"
          :chart-type="chartType"
          :chart-type-changed="chartTypeChanged"
          :layout-type="configStore.layoutType"
          :assignment-mode="configStore.assignmentMode"
          :containers="containers"
          :domain-products="passedDomainProducts"
          :positions="configStore.positions"
          :preserve-model-order="configStore.preserveModelOrder"
          :layout-control-config="configStore.layoutControlConfig"
          :color-scheme="configStore.colorScheme"
          :color-group-by="configStore.colorGroupBy"
          :custom-colors="configStore.customColors || {}"
          :color-mapping="colorMapping"
          :links="previewData?.relationships || []"
          :center-scope="passedCenterScope"
          :center-scope-markers="passedCenterScopeMarkers"
          :center-scope-color="configStore.centerScopeColor"
          @update:config="handleUpdateConfig"
          @update:layout-control-config="handleLayoutControlConfigUpdate"
          @add-group="handleAddGroup"
          @reset-chart-type-changed="$emit('reset-chart-type-changed')"
        />

        <div class="config-section">
          <div class="advanced-options-header" @click="toggleAdvancedOptions">
            <span class="section-title">高级选项</span>
            <AppIcon :name="showAdvancedOptions ? 'chevron-up' : 'chevron-down'" size="sm" />
          </div>

          <div v-show="showAdvancedOptions" class="advanced-options-content">
            <div class="form-row">
              <div class="form-item">
                <label class="form-label">关系连线模式</label>
                <div class="radio-group">
                  <label class="radio-option" :class="{ active: configStore.layoutEngine === 'elk' }">
                    <input
                      type="radio"
                      value="elk"
                      :checked="configStore.layoutEngine === 'elk'"
                      @change="configStore.updateLayoutEngine('elk')"
                    />
                    <span class="radio-label">
                      <span class="radio-name">直线（默认）</span>
                      <span class="radio-desc">更好的屏幕适配能力</span>
                    </span>
                  </label>
                  <label class="radio-option" :class="{ active: configStore.layoutEngine === 'dagre' }">
                    <input
                      type="radio"
                      value="dagre"
                      :checked="configStore.layoutEngine === 'dagre'"
                      @change="configStore.updateLayoutEngine('dagre')"
                    />
                    <span class="radio-label">
                      <span class="radio-name">曲线</span>
                      <span class="radio-desc">稳定可靠，自动布局</span>
                    </span>
                  </label>
                </div>
              </div>
            </div>

            <div class="form-row">
              <div class="form-item">
                <label class="form-label">
                  <input
                    type="checkbox"
                    v-model="enableLegacyMode"
                    @change="handleLegacyModeChange"
                  />
                  启用旧版非分组控制 <AppIcon name="enabled" size="sm" />
                </label>
                <span v-if="enableLegacyMode" class="form-warning">
                  旧版模式将在未来版本移除
                </span>
              </div>
            </div>

            <div class="form-row">
              <div class="form-item">
                <label class="form-label">隐藏关系标签拖尾线</label>
                <select
                  :value="configStore.hideLinkLabelTails === null ? 'auto' : (configStore.hideLinkLabelTails ? 'yes' : 'no')"
                  @change="configStore.updateHideLinkLabelTails($event.target.value === 'auto' ? null : ($event.target.value === 'yes'))"
                  class="form-select"
                >
                  <option value="auto">自动（ELK隐藏，Dagre显示）</option>
                  <option value="yes">是（强制隐藏）</option>
                  <option value="no">否（强制显示）</option>
                </select>
                <span class="form-hint">自动模式根据布局引擎决定，ELK布局默认隐藏，Dagre布局默认显示</span>
              </div>
            </div>

            <div class="form-row">
              <div class="form-item">
                <label class="form-label">显示备注图标</label>
                <select
                  :value="configStore.showAnnotationIcons ? 'yes' : 'no'"
                  @change="configStore.updateShowAnnotationIcons($event.target.value === 'yes')"
                  class="form-select"
                >
                  <option value="no">否（默认）</option>
                  <option value="yes">是</option>
                </select>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed } from 'vue'
import { AppButton } from '../../../../components/common'
import { AppIcon } from '../../../../components/common/AppIcon'
import CenterDomainSelect from '../../../../components/CenterDomainSelect.vue'
import ServiceModuleConfig from '../../../../components/ServiceModuleConfig.vue'
import LayoutSelector from '../LayoutSelector.vue'
import { useLayoutControl } from '../../../../composables/useLayoutControl'
import { useDiagramConfigStore } from '../../../../stores/diagramConfigStore'

export default {
  name: 'StepConfig',
  components: { AppButton, AppIcon, CenterDomainSelect, ServiceModuleConfig, LayoutSelector },
  props: {
    previewData: Object,
    subDomains: Array,
    domains: Array,
    serviceModules: Array,
    domainProducts: {
      type: Array,
      default: () => []
    },
    chartType: {
      type: String,
      default: 'businessObject'
    },
    chartTypeChanged: {
      type: Boolean,
      default: false
    },
    containers: {
      type: Array,
      default: () => []
    },
    businessObjects: {
      type: Array,
      default: () => []
    },
    // 关键修复 v34: 总数统计 (5 个指标) - 来自 useDiagramData.displayStats.total
    total: {
      type: Object,
      default: null
    }
  },
  emits: ['generate', 'prev', 'reset-chart-type-changed'],
  setup(props) {
    const configStore = useDiagramConfigStore()

    const layoutControlConfigRef = ref(null)
    const { layoutControlConfig } = useLayoutControl()
    layoutControlConfigRef.value = layoutControlConfig

    const showAdvancedOptions = ref(false)
    const enableLegacyMode = ref(false)

    const passedDomainProducts = computed(() => {
      // 优先使用 props.domainProducts（从 index.vue 传入的 filteredDomainProducts）
      // 只有当 domainProducts 为空时才 fallback 到 previewData?.domainProducts
      return props.domainProducts?.length > 0
        ? props.domainProducts
        : (props.previewData?.domainProducts || [])
    })
    const passedCenterScope = computed(() => configStore.centerScope || [])
    const passedCenterScopeMarkers = computed(() => configStore.centerScopeMarkers)

    const colorMapping = computed(() => {
      const scheme = configStore.colorScheme || 'default'
      const colorGroupBy = configStore.colorGroupBy || 'domain'
      const customColors = configStore.customColors || {}
      const centerScopeHighlight = configStore.centerScopeHighlight !== false

      const COLOR_SCHEMES = {
        default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
        vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
        pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
        warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
        cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
        business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
        nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
      }

      const colors = COLOR_SCHEMES[scheme] || COLOR_SCHEMES.default
      let items = []
      if (colorGroupBy === 'serviceModule') {
        items = (props.serviceModules || []).map(sm => sm.name || sm)
      } else if (colorGroupBy === 'subDomain') {
        items = props.subDomains || []
      } else {
        items = props.domains || []
      }

      const centerBoCodes = configStore.centerBoCodes || new Set()
      const allBusinessObjects = props.businessObjects || []

      const isFullyInCenterScope = (groupName) => {
        const groupBoCodes = new Set()
        allBusinessObjects.forEach(bo => {
          if (colorGroupBy === 'serviceModule') {
            if (bo.serviceModuleName === groupName || bo.serviceModule === groupName) {
              groupBoCodes.add(bo.code || bo.name)
            }
          } else if (colorGroupBy === 'subDomain') {
            if (bo.subDomain === groupName) {
              groupBoCodes.add(bo.code || bo.name)
            }
          } else {
            if (bo.domain === groupName) {
              groupBoCodes.add(bo.code || bo.name)
            }
          }
        })
        if (groupBoCodes.size === 0) return false
        for (const code of groupBoCodes) {
          if (!centerBoCodes.has(code)) {
            return false
          }
        }
        return true
      }

      const mapping = {}
      let colorIndex = 0
      items.forEach((item) => {
        if (centerScopeHighlight && isFullyInCenterScope(item)) {
          return
        }
        mapping[item] = customColors[item] || colors[colorIndex % colors.length]
        colorIndex++
      })

      return mapping
    })

    const centerScopeBoCodes = configStore.centerBoCodes

    return {
      configStore,
      layoutControlConfigRef,
      showAdvancedOptions,
      enableLegacyMode,
      passedDomainProducts,
      passedCenterScope,
      passedCenterScopeMarkers,
      colorMapping,
      centerScopeBoCodes
    }
  },
  data() {
    return {
      localLayoutControlConfig: {
        enabled: true,
        overallDirection: 'TB',
        groups: [],
        engine: 'elk',
        preserveOrder: true
      }
    }
  },
  watch: {
    'configStore.centerScope': {
      immediate: true,
      handler() {}
    },
    'configStore.centerScopeMarkers': {
      immediate: true,
      handler() {}
    },
    'configStore.centerScopeColor': {
      immediate: true,
      handler() {}
    }
  },
  methods: {
    handleUpdateConfig(keyOrUpdates, value) {
      if (typeof keyOrUpdates === 'string') {
        const key = keyOrUpdates
        const actionName = 'update' + key.charAt(0).toUpperCase() + key.slice(1)
        if (typeof this.configStore[actionName] === 'function') {
          this.configStore[actionName](value)
        } else if (typeof this.configStore['update' + key.replace(/([A-Z])/g, '_$1').toUpperCase().slice(1)] === 'function') {
          // handle special cases like layoutEngine
        } else {
          // fallback: direct update via config store
          console.warn('[StepConfig] No action for key:', key, 'value:', value)
        }
      } else {
        Object.entries(keyOrUpdates).forEach(([key, value]) => {
          const actionName = 'update' + key.charAt(0).toUpperCase() + key.slice(1)
          if (typeof this.configStore[actionName] === 'function') {
            this.configStore[actionName](value)
          }
        })
      }
    },
    handleLayoutControlConfigUpdate(value) {
      console.log('[StepConfig] handleLayoutControlConfigUpdate:', JSON.stringify(value, null, 2))
      this.localLayoutControlConfig = value
      console.log('[StepConfig] calling configStore.updateLayoutControlConfig')
      this.configStore.updateLayoutControlConfig(value)
    },
    handleGenerate() {
      this.$emit('generate')
    },
    toggleAdvancedOptions() {
      this.showAdvancedOptions = !this.showAdvancedOptions
    },
    handleLegacyModeChange() {
      if (this.enableLegacyMode) {
        console.warn('[StepConfig] 启用旧版非分组控制，此模式将在未来版本移除')
      }
      this.configStore.updateAssignmentMode(this.enableLegacyMode ? 'legacy' : 'auto')
    },
    handleAddGroup() {
      console.log('[StepConfig] handleAddGroup - forwarding to layout control')
      const currentConfig = this.configStore.layoutControlConfig || this.localLayoutControlConfig
      const newGroup = {
        id: `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        title: `分组 ${(currentConfig.groups?.length || 0) + 1}`,
        groupType: 'custom',
        direction: 'TB',
        visible: true,
        enabled: true,
        style: {
          fill: '#f5f5f5',
          stroke: '#333333',
          strokeWidth: 1,
          strokeDasharray: ''
        },
        containers: [],
        children: [],
        parentId: null
      }
      const newConfig = {
        ...currentConfig,
        groups: [newGroup, ...(currentConfig.groups || [])]
      }
      this.handleLayoutControlConfigUpdate(newConfig)
    },
    handleAutoGroup() {
      console.log('[StepConfig] handleAutoGroup - triggering auto group')
      if (this.$refs.layoutSelectorRef) {
        this.$refs.layoutSelectorRef.triggerAutoGroup()
      }
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-config {
  height: 100%;
}

.config-panel {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-body {
  flex: 1;
  padding: var(--spacing-xl);
  overflow: auto;
}

.panel-header-simple {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow: auto;

  &.no-padding-top {
    padding-top: 0;
  }
}

.form-hint {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}

@include respond-to('sm') {
  .panel-header-simple {
    padding: var(--spacing-sm) var(--spacing-md);
  }

  .panel-body {
    padding: var(--spacing-md);
  }
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

.form-row {
  display: flex;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-md);
  align-items: flex-start;
}

.form-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.form-select {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  background: white;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: var(--color-primary);
  }
}

.layout-templates {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.layout-template-option {
  display: flex;
  align-items: center;
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
    background: var(--color-bg-secondary);
  }

  &.active {
    border-color: var(--color-primary);
    background: rgba(234, 88, 12, 0.08);
  }
}

.template-icon {
  font-size: 24px;
  margin-right: var(--spacing-md);
  width: 32px;
  text-align: center;
}

.template-info {
  flex: 1;
}

.template-name {
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.template-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.config-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.config-input {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  width: 100px;

  &:focus {
    outline: none;
    border-color: var(--color-primary);
  }
}

.config-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.annotation-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: #fff3cd;
  border: 1px solid #ffeaa7;
  border-radius: var(--radius-md);
  margin-top: var(--spacing-md);
  font-size: var(--font-size-sm);
  color: #856404;
}

.hint-icon {
  font-size: 16px;
}

.advanced-options-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;

  .toggle-icon {
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
  }

  &:hover {
    opacity: 0.8;
  }
}

.advanced-options-content {
  margin-top: var(--spacing-md);
}

.form-warning {
  font-size: var(--font-size-sm);
  color: #856404;
  background: #fff3cd;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  border: 1px solid #ffeaa7;
}

input[type="checkbox"] {
  margin-right: var(--spacing-xs);
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
    background: rgba(234, 88, 12, 0.08);
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
