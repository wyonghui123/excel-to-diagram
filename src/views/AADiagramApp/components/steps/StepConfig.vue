<template>
  <div class="step-config">
    <div class="config-panel">
      <div class="panel-header-simple">
        <AppButton type="secondary" @click="$emit('prev')">← 上一步</AppButton>
        <AppButton type="primary" size="lg" @click="handleGenerate">
          生成图表 →
        </AppButton>
      </div>
      <div class="panel-body no-padding-top">
        <!-- 业务对象图配置 -->
        <template v-if="chartType === 'businessObject'">
          <CenterDomainSelect
            v-if="previewData"
            :model-value="config.centerDomain"
            :color-group-by="config.colorGroupBy"
            :center-domain-color="config.centerDomainColor"
            :color-scheme="config.colorScheme"
            :text-color="config.textColor"
            :sub-domains="subDomains"
            :domains="domains"
            @update:model-value="updateConfig('centerDomain', $event)"
            @update:colorGroupBy="updateConfig('colorGroupBy', $event)"
            @update:centerDomainColor="updateConfig('centerDomainColor', $event)"
            @update:colorScheme="updateConfig('colorScheme', $event)"
            @update:textColor="updateConfig('textColor', $event)"
          />
        </template>

        <!-- 服务模块图配置 -->
        <template v-if="chartType === 'serviceModule'">
          <ServiceModuleConfig
            v-if="previewData"
            :model-value="config.centerDomain"
            :color-group-by="config.colorGroupBy"
            :center-domain-color="config.centerDomainColor"
            :color-scheme="config.colorScheme"
            :service-module-text-color="config.serviceModuleTextColor"
            :sub-domains="subDomains"
            :domains="domains"
            @update:model-value="updateConfig('centerDomain', $event)"
            @update:colorGroupBy="updateConfig('colorGroupBy', $event)"
            @update:centerDomainColor="updateConfig('centerDomainColor', $event)"
            @update:color-scheme="updateConfig('colorScheme', $event)"
            @update:serviceModuleTextColor="updateConfig('serviceModuleTextColor', $event)"
          />
        </template>

        <!-- 布局选择 -->
        <LayoutSelector
          v-if="previewData && containers.length > 0"
          :layout-engine="layoutEngine"
          :layout-type="layoutType"
          :assignment-mode="assignmentMode"
          :containers="containers"
          :positions="positions"
          :preserve-model-order="preserveModelOrder"
          :layout-control-config="layoutControlConfig"
          @update:config="updateConfig"
          @update:layout-control-config="handleLayoutControlConfigUpdate"
        />

        <!-- 每行最大字符数 -->

        <!-- 备注配置区域 -->
        <div class="config-section">
          <h3 class="section-title">备注配置</h3>

          <div class="form-row">
            <div class="form-item">
              <label class="form-label">显示备注图标</label>
              <select
                :value="config.showAnnotationIcons ? 'yes' : 'no'"
                @change="updateConfig('showAnnotationIcons', $event.target.value === 'yes')"
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
</template>

<script>
import { AppButton } from '../../../../components/common'
import CenterDomainSelect from '../../../../components/CenterDomainSelect.vue'
import ServiceModuleConfig from '../../../../components/ServiceModuleConfig.vue'
import LayoutSelector from '../LayoutSelector.vue'
import { useLayoutControl } from '../../../../composables/useLayoutControl'

export default {
  name: 'StepConfig',
  components: { AppButton, CenterDomainSelect, ServiceModuleConfig, LayoutSelector },
  props: {
    previewData: Object,
    subDomains: Array,
    domains: Array,
    config: Object,
    chartType: {
      type: String,
      default: 'businessObject'
    }
  },
  emits: ['update:config', 'generate', 'prev'],
  data() {
    return {
      localLayoutControlConfig: {
        enabled: false,
        overallDirection: 'TB',
        groups: [],
        engine: 'dagre',
        preserveOrder: true
      }
    }
  },
  created() {
    const { layoutControlConfig } = useLayoutControl()
    this.layoutControlConfigRef = layoutControlConfig
  },
  computed: {
    containers() {
      if (!this.previewData) return []
      
      if (this.chartType === 'serviceModule') {
        const subDomainMap = new Map()
        
        if (this.previewData.serviceModules) {
          this.previewData.serviceModules.forEach(sm => {
            if (!subDomainMap.has(sm.subDomain)) {
              const domain = this.previewData.domainProducts?.find(
                d => d.modules?.some(m => m.name === sm.subDomain)
              )
              subDomainMap.set(sm.subDomain, {
                id: sm.subDomain,
                name: sm.subDomain,
                fullTitle: domain ? `${domain.name} / ${sm.subDomain}` : sm.subDomain
              })
            }
          })
        }
        
        const result = [...subDomainMap.values()]
        console.log('[StepConfig] containers for serviceModule:', result.map((c, i) => `${i}: ${c.name}`))
        return result
      }
      
      if (this.previewData.domainProducts) {
        const containers = []
        this.previewData.domainProducts.forEach(domain => {
          if (domain.modules) {
            domain.modules.forEach(module => {
              containers.push({
                id: module.code || module.name,
                name: module.name,
                fullTitle: domain.name + ' / ' + module.name
              })
            })
          }
        })
        return containers
      }
      return []
    },
    layoutEngine() {
      return this.config.layoutEngine || 'dagre'
    },
    layoutType() {
      return this.config.layoutType || 'grouped'
    },
    layoutControlConfig() {
      return this.config.layoutControlConfig || this.localLayoutControlConfig
    }
  },
  methods: {
    updateConfig(keyOrUpdates, value) {
      if (typeof keyOrUpdates === 'string') {
        this.$emit('update:config', { [keyOrUpdates]: value })
      } else {
        this.$emit('update:config', keyOrUpdates)
      }
    },
    handleLayoutControlConfigUpdate(value) {
      console.log('[StepConfig] handleLayoutControlConfigUpdate:', value)
      this.localLayoutControlConfig = value
      this.$emit('update:config', { layoutControlConfig: value })
    },
    handleGenerate() {
      console.log('生成图表按钮被点击')
      this.$emit('generate')
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
    background: rgba(24, 144, 255, 0.08);
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
</style>
