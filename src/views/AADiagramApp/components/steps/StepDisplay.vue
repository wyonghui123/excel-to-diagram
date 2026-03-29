<template>
  <div class="step-display">
    <div class="display-panel">
      <div class="panel-header-simple">
        <AppButton type="secondary" @click="$emit('prev')">← 上一步</AppButton>
        <div class="header-actions">
          <AppButton 
            v-if="feishuEnabled" 
            type="secondary" 
            @click="showFeishuBot = true"
            class="feishu-btn"
          >
            🤖 飞书机器人
          </AppButton>
          <AppButton 
            v-if="feishuEnabled" 
            type="secondary" 
            @click="showFeishuImport = true"
            class="feishu-btn"
          >
            📥 飞书导入
          </AppButton>
          <div class="chart-type-badge" :class="chartType">
            <span class="badge-icon">{{ chartTypeIcon }}</span>
            <span class="badge-text">{{ chartTypeText }}</span>
          </div>
        </div>
      </div>
      <div class="panel-body diagram-panel">
        <div v-if="diagramData" class="diagram-container">
          <MermaidComponent 
            :diagram-data="diagramData" 
            :diagram-type="chartType"
            :annotation-config="annotationConfig"
            :layout-engine="layoutConfig.layoutEngine"
            :layout-type="layoutConfig.layoutType"
            :layout-containers="layoutConfig.containers"
            :layout-positions="layoutConfig.positions"
            :zone-row-count="layoutConfig.zoneRowCount"
            :preserve-model-order="layoutConfig.preserveModelOrder"
            :layout-control-config="layoutConfig.layoutControlConfig"
          />
        </div>
        <div v-else class="empty-state">
          <div class="empty-icon">📊</div>
          <p>图表尚未生成</p>
          <AppButton type="primary" @click="$emit('regenerate')">去配置参数</AppButton>
        </div>
      </div>
    </div>

    <!-- 飞书机器人面板 -->
    <FeishuBotPanel 
      v-if="showFeishuBot" 
      @close="showFeishuBot = false"
      @command="handleFeishuCommand"
    />

    <!-- 飞书数据导入 -->
    <FeishuDataImport 
      v-if="showFeishuImport" 
      @close="showFeishuImport = false"
      @import="handleFeishuImport"
    />
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { AppButton } from '../../../../components/common'
import MermaidComponent from '../../../../components/MermaidComponent.vue'
import FeishuBotPanel from '../../../../components/FeishuBotPanel.vue'
import FeishuDataImport from '../../../../components/FeishuDataImport.vue'

export default {
  name: 'StepDisplay',
  components: { AppButton, MermaidComponent, FeishuBotPanel, FeishuDataImport },
  props: {
    diagramData: Object,
    chartType: {
      type: String,
      default: 'businessObject'
    },
    annotationConfig: {
      type: Object,
      default: null
    }
  },
  emits: ['prev', 'regenerate', 'command', 'import'],
  setup(props, { emit }) {
    const feishuEnabled = ref(false)
    const showFeishuBot = ref(false)
    const showFeishuImport = ref(false)

    onMounted(() => {
      const savedConfig = localStorage.getItem('archWorkspaceConfig')
      if (savedConfig) {
        try {
          const config = JSON.parse(savedConfig)
          feishuEnabled.value = config.feishuEnabled || false
        } catch (e) {
          console.error('加载飞书配置失败:', e)
        }
      }
    })

    const handleFeishuCommand = (command) => {
      emit('command', command)
    }

    const handleFeishuImport = (data) => {
      emit('import', data)
    }

    return {
      feishuEnabled,
      showFeishuBot,
      showFeishuImport,
      handleFeishuCommand,
      handleFeishuImport
    }
  },
  computed: {
    chartTypeText() {
      return this.chartType === 'businessObject' ? '业务对象图' : '服务模块图'
    },
    chartTypeIcon() {
      return this.chartType === 'businessObject' ? '📊' : '🔄'
    },
    layoutConfig() {
      console.log('[StepDisplay] annotationConfig:', this.annotationConfig)
      console.log('[StepDisplay] layoutEngine:', this.annotationConfig?.layoutEngine, 'layoutType:', this.annotationConfig?.layoutType, 'preserveModelOrder:', this.annotationConfig?.preserveModelOrder)
      console.log('[StepDisplay] layoutControlConfig:', this.annotationConfig?.layoutControlConfig, 'overallDirection:', this.annotationConfig?.layoutControlConfig?.overallDirection)
      return {
        layoutEngine: this.annotationConfig?.layoutEngine || 'dagre',
        layoutType: this.annotationConfig?.layoutType || 'default',
        containers: this.annotationConfig?.containers || null,
        positions: this.annotationConfig?.positions || [],
        zoneRowCount: this.annotationConfig?.zoneRowCount || 3,
        preserveModelOrder: this.annotationConfig?.preserveModelOrder || false,
        layoutControlConfig: this.annotationConfig?.layoutControlConfig || null
      }
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-display {
  height: 100%;
}

.display-panel {
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

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.feishu-btn {
  background: linear-gradient(135deg, #3370ff 0%, #2c5de6 100%) !important;
  color: #fff !important;
  border: none !important;
}

.chart-type-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  font-weight: 500;

  &.businessObject {
    background: rgba(24, 144, 255, 0.1);
    color: var(--color-primary);
  }

  &.serviceModule {
    background: rgba(82, 196, 26, 0.1);
    color: var(--color-success);
  }
}

.badge-icon {
  font-size: var(--font-size-lg);
}

.panel-body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow: auto;

  &.diagram-panel {
    padding: 0;
  }
}

.diagram-container {
  height: 100%;
}

.empty-state {
  @include flex-center;
  flex-direction: column;
  height: 100%;
  gap: var(--spacing-md);
}

.empty-icon {
  font-size: 64px;
}

.empty-state p {
  font-size: var(--font-size-md);
  color: var(--color-text-tertiary);
}

@include respond-to('sm') {
  .panel-header-simple {
    padding: var(--spacing-sm) var(--spacing-md);
  }

  .panel-body {
    padding: var(--spacing-md);
  }

  .empty-icon {
    font-size: 48px;
  }
}
</style>
