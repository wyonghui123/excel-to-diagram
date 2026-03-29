<template>
  <div class="aa-diagram-app">
    <AppHeader
      title="AA图"
      :show-back="true"
      @back="$emit('back-to-landing')"
    >
      <template #center>
        <StatsDisplay
          v-if="previewData"
          :stats="displayStats"
        />
      </template>
    </AppHeader>

    <StepNavigator
      :steps="steps"
      :current="currentStep"
      @change="goToStep"
    />

    <main class="main-content">
      <component
        :is="currentStepInfo.component"
        v-bind="stepProps"
        v-on="stepEvents"
      />
    </main>
  </div>
</template>

<script>
import { computed } from 'vue'
import { AppHeader } from '../../components/common'
import StepNavigator from './components/StepNavigator.vue'
import StatsDisplay from './components/StatsDisplay.vue'
import { useDiagramSteps } from './composables/useDiagramSteps.js'
import { useDiagramData } from './composables/useDiagramData.js'

// 步骤组件
import StepUpload from './components/steps/StepUpload.vue'
import StepScope from './components/steps/StepScope.vue'
import StepChartType from './components/steps/StepChartType.vue'
import StepConfig from './components/steps/StepConfig.vue'
import StepDisplay from './components/steps/StepDisplay.vue'

export default {
  name: 'AADiagramApp',
  components: {
    AppHeader,
    StepNavigator,
    StepChartType,
    StatsDisplay,
    StepUpload,
    StepScope,
    StepConfig,
    StepDisplay
  },
  emits: ['back-to-landing'],
  setup() {
    const {
      steps,
      currentStep,
      currentStepInfo,
      goToStep,
      nextStep,
      prevStep
    } = useDiagramSteps()

    const {
      loading,
      error,
      previewData,
      rawData,
      selectedScope,
      chartType,
      diagramConfig,
      diagramData,
      availableSubDomains,
      availableDomains,
      displayStats,
      handleFileUpload,
      generateDiagram,
      updateSelectedStats
    } = useDiagramData()

    // 步骤组件的 props
    const stepProps = computed(() => {
      const propsMap = {
        0: { loading: loading.value, error: error.value },
        1: {
          previewData: previewData.value,
          rawData: rawData.value,
          modelValue: selectedScope.value
        },
        2: {
          modelValue: chartType.value
        },
        3: {
          previewData: previewData.value,
          subDomains: availableSubDomains.value,
          domains: availableDomains.value,
          config: diagramConfig.value,
          chartType: chartType.value
        },
        4: { 
          diagramData: diagramData.value, 
          chartType: chartType.value,
          annotationConfig: diagramConfig.value
        }
      }
      return propsMap[currentStep.value] || {}
    })

    // 处理文件上传并自动跳转
    const handleFileUploadAndNext = async (file) => {
      await handleFileUpload(file)
      // 数据加载完成后自动跳转到下一步
      if (previewData.value) {
        nextStep()
      }
    }

    // 步骤组件的事件
    const stepEvents = computed(() => {
      const eventsMap = {
        0: {
          'file-selected': handleFileUploadAndNext
        },
        1: {
          'update:modelValue': (val) => selectedScope.value = val,
          'update:selectedStats': updateSelectedStats,
          'next': nextStep,
          'prev': prevStep
        },
        2: {
          'update:modelValue': (val) => chartType.value = val,
          'next': nextStep,
          'prev': prevStep
        },
        3: {
          'update:config': (val) => Object.assign(diagramConfig.value, val),
          'generate': () => {
            try {
              generateDiagram()
              nextStep()
            } catch (err) {
              console.error('生成图表失败:', err)
            }
          },
          'prev': prevStep
        },
        4: {
          'prev': prevStep,
          'regenerate': () => goToStep(3)
        }
      }
      return eventsMap[currentStep.value] || {}
    })

    return {
      steps,
      currentStep,
      currentStepInfo,
      goToStep,
      previewData,
      displayStats,
      stepProps,
      stepEvents
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.aa-diagram-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
}

.main-content {
  flex: 1;
  padding: var(--spacing-lg);
  overflow: auto;

  @include respond-to('md') {
    padding: var(--spacing-md);
  }

  @include respond-to('sm') {
    padding: var(--spacing-sm);
  }
}
</style>
