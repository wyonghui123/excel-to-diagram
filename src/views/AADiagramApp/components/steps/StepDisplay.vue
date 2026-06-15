<template>
  <div class="step-display">
    <div class="display-panel">
      <!-- 紧凑工具栏：保留飞书按钮和图表类型 badge -->
      <div v-if="feishuEnabled || chartTypeText" class="toolbar-compact">
        <div class="chart-type-badge" :class="chartType">
          <AppIcon :name="chartTypeIcon" size="sm" class="badge-icon" />
          <span class="badge-text">{{ chartTypeText }}</span>
        </div>
        <div class="toolbar-compact__actions">
          <AppButton
            v-if="feishuEnabled"
            type="secondary"
            size="sm"
            @click="showFeishuBot = true"
          >
            飞书机器人
          </AppButton>
          <AppButton
            v-if="feishuEnabled"
            type="secondary"
            size="sm"
            @click="showFeishuImport = true"
          >
            飞书导入
          </AppButton>
          <AppButton
            type="secondary"
            size="sm"
            @click="handleBackToArch"
          >
            <AppIcon name="arrow-left" size="sm" />
            返回架构管理
          </AppButton>
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
          <div class="empty-icon"><AppIcon name="arrow-right" size="xl" /></div>
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
import { useRouter } from 'vue-router'
import { AppButton } from '../../../../components/common'
import { AppIcon } from '../../../../components/common/AppIcon'
import MermaidComponent from '../../../../components/MermaidComponent.vue'
import FeishuBotPanel from '../../../../components/FeishuBotPanel.vue'
import FeishuDataImport from '../../../../components/FeishuDataImport.vue'

export default {
  name: 'StepDisplay',
  components: { AppButton, AppIcon, MermaidComponent, FeishuBotPanel, FeishuDataImport },
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
    const router = useRouter()
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

    const handleBackToArch = () => {
      sessionStorage.setItem('returningFromDiagram', 'true')
      router.push('/system/archdata')
    }

    return {
      feishuEnabled,
      showFeishuBot,
      showFeishuImport,
      handleFeishuCommand,
      handleFeishuImport,
      handleBackToArch
    }
  },
  computed: {
    chartTypeText() {
      return this.chartType === 'businessObject' ? '业务对象图' : '服务模块图'
    },
    chartTypeIcon() {
      return this.chartType === 'businessObject' ? 'arrow-right' : 'lightning'
    },
    layoutConfig() {
      console.log('[StepDisplay.layoutConfig] annotationConfig:', this.annotationConfig)
      console.log('[StepDisplay.layoutConfig] annotationConfig?.layoutControlConfig:', this.annotationConfig?.layoutControlConfig)
      return {
        layoutEngine: this.annotationConfig?.layoutEngine || 'elk',
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

/* 紧凑工具栏 */
.toolbar-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px var(--spacing-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  gap: var(--spacing-sm);

  .chart-type-badge {
    flex-shrink: 0;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
  }
}

// [2026-06-15] 移除 .panel-body 的蓝色渐变 + 白色文字：
//   旧实现把整个 panel-body（含 empty-state）都染成蓝色 + 白字，
//   导致 "图表尚未生成" 状态显示成全屏蓝色，视觉上与系统不一致。
//   修复：panel-body 保持中性背景，仅在 diagram-container（Mermaid 画布）使用深色背景。
.panel-body {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  border: none;
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
    background: rgba(234, 88, 12, 0.1);
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
  .toolbar-compact {
    padding: 4px var(--spacing-md);
  }

  .panel-body {
    padding: var(--spacing-md);
  }

  .empty-icon {
    font-size: 48px;
  }
}
</style>
