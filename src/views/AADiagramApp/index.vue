<template>
  <div class="aa-diagram-app">
    <StepNavigator
      :steps="visibleSteps"
      :current="displayCurrent"
      :step-stats="stepStats"
      @change="handleStepChange"
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
import { computed, watch, onMounted, getCurrentInstance } from 'vue'
import { useRouter } from 'vue-router'
import { AppHeader } from '../../components/common'
import StepNavigator from './components/StepNavigator.vue'
import { useDiagramSteps } from './composables/useDiagramSteps.js'
import { useDiagramData } from './composables/useDiagramData.js'
import { useDiagramConfigStore } from '../../stores/diagramConfigStore.js'

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
    StepUpload,
    StepScope,
    StepConfig,
    StepDisplay
  },
  emits: ['back-to-landing'],
  setup() {
    const router = useRouter()
    const {
      steps,
      visibleSteps,
      currentStep,
      displayCurrent,
      currentStepInfo,
      goToStep,
      nextStep,
      prevStep,
      initFromArchData,
      initFromArchDataManager,
      handlePrev
    } = useDiagramSteps()

    const configStore = useDiagramConfigStore()

    const {
      loading,
      error,
      previewData,
      rawData,
      centerScope,
      selectedScope,
      chartType,
      chartTypeChanged,
      previousChartType,
      diagramConfig,
      diagramData,
      availableSubDomains,
      availableDomains,
      availableServiceModules,
      filteredContainers,
      displayStats,
      centerScopePresets,
      selectedRelationNodeIds,
      relationCategoryTree,
      relationFilteredBoCodes,
      handleFileUpload,
      generateDiagram,
      filterByRelation,
      setInternalRelationFilter,
      resetChartTypeChanged,
      saveCenterScopePreset,
      loadCenterScopePreset,
      deleteCenterScopePreset,
      toggleRelationNode,
      centerScopeMarkers,
      filteredDomainProducts,
      initFromArchDataManager: initDataFromArch,
      isInitializedFromArchData
    } = useDiagramData()

    // 监控 centerScopeMarkers 变化
    // 步骤组件的 props
    const stepProps = computed(() => {
      const propsMap = {
        0: { loading: loading.value, error: error.value },
        1: {
          stepMode: 'center',
          previewData: previewData.value,
          rawData: rawData.value,
          modelValue: centerScope.value,
          centerScope: centerScope.value,
          centerScopePresets: centerScopePresets.value,
          selectedRelationNodeIds: selectedRelationNodeIds.value,
          relationCategoryTree: relationCategoryTree.value
        },
        2: {
          stepMode: 'relation',
          previewData: previewData.value,
          rawData: rawData.value,
          modelValue: centerScope.value,
          centerScope: centerScope.value,
          centerScopePresets: centerScopePresets.value,
          selectedRelationNodeIds: selectedRelationNodeIds.value,
          relationCategoryTree: relationCategoryTree.value
        },
        3: {
          modelValue: chartType.value
        },
        4: {
          previewData: previewData.value,
          subDomains: availableSubDomains.value,
          domains: availableDomains.value,
          serviceModules: availableServiceModules.value,
          domainProducts: filteredDomainProducts.value,
          config: diagramConfig.value,
          chartType: chartType.value,
          chartTypeChanged: chartTypeChanged.value,
          containers: filteredContainers.value,
          centerScope: centerScope.value,
          centerScopeMarkers: centerScopeMarkers.value,
          centerScopeBoCodes: new Set(centerScope.value || []),
          businessObjects: previewData.value?.businessObjects || []
        },
        5: {
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
          'update:modelValue': (val) => {
            centerScope.value = val
          },
          'next': nextStep,
          'prev': prevStep,
          'filter-by-relation': filterByRelation,
          'internal-relation-filter': setInternalRelationFilter,
          'update:centerScope': (val) => {
            configStore.updateCenterScope(val)
          },
          'update:selectedRelationNodeIds': (val) => selectedRelationNodeIds.value = val,
          'save-center-scope-preset': saveCenterScopePreset,
          'load-center-scope-preset': loadCenterScopePreset,
          'delete-center-scope-preset': deleteCenterScopePreset,
          'toggle-relation-node': toggleRelationNode,
          'apply-relation-filter': (boCodes) => {
            if (boCodes && boCodes.length > 0) {
              relationFilteredBoCodes.value = boCodes
            } else {
              relationFilteredBoCodes.value = null
            }
          }
        },
        2: {
          'update:modelValue': (val) => {
            configStore.updateCenterScope(val)
          },
          'next': nextStep,
          'prev': prevStep,
          'filter-by-relation': filterByRelation,
          'internal-relation-filter': setInternalRelationFilter,
          'update:centerScope': (val) => {
            configStore.updateCenterScope(val)
          },
          'update:selectedRelationNodeIds': (val) => selectedRelationNodeIds.value = val,
          'save-center-scope-preset': saveCenterScopePreset,
          'load-center-scope-preset': loadCenterScopePreset,
          'delete-center-scope-preset': deleteCenterScopePreset,
          'toggle-relation-node': toggleRelationNode,
          'apply-relation-filter': (boCodes) => {
            if (boCodes && boCodes.length > 0) {
              relationFilteredBoCodes.value = boCodes
            } else {
              relationFilteredBoCodes.value = null
            }
          }
        },
        3: {
          'update:modelValue': (val) => configStore.updateChartType(val),
          'next': nextStep,
          'prev': handlePrevWrapper
        },
        4: {
          'update:config': (val) => {
            Object.assign(diagramConfig.value, val)
          },
          'reset-chart-type-changed': () => {
            resetChartTypeChanged()
          },
          'generate': () => {
            try {
              generateDiagram()
              nextStep()
            } catch (err) {
              console.error('生成图表失败:', err)
            }
          },
          'prev': handlePrevWrapper
        },
        5: {
          'prev': handlePrevWrapper,
          'regenerate': () => goToStep(4)
        }
      }
      return eventsMap[currentStep.value] || {}
    })

    /**
     * 步骤导航统计信息
     * 
     * 各步骤统计映射：
     * - 步骤0（导入）: displayStats.import - 显示导入的总数据量
     * - 步骤1（中心）: displayStats.center - 显示中心范围的完整统计（领域、子域、对象）
     * - 步骤2（关系）: displayStats.incremental - 显示相比中心新增的统计（带+前缀）
     * - 步骤3（类型）: displayStats.total - 显示总数统计（中心+外部）
     * - 步骤4（配置）: displayStats.config - 根据图表类型显示不同统计
     *   * 业务对象图：服务模块、对象、关系
     *   * 服务模块图：服务模块、模块关系
     * - 步骤5（展示）: null - 不显示统计
     */
    const stepStats = computed(() => {
      return {
        0: displayStats.value.import,         // 导入步骤 - 显示总数
        1: displayStats.value.center,         // 中心步骤 - 显示中心范围统计
        2: displayStats.value.incremental,    // 关系步骤 - 显示增量统计
        3: displayStats.value.total,          // 类型步骤 - 显示总数统计
        4: displayStats.value.config,         // 配置步骤 - 显示图表类型相关统计
        5: null                               // 展示步骤 - 不显示统计
      }
    })

    const handlePrevWrapper = () => {
      if (initFromArchData.value) {
        // 从架构管理跳转进来的, 任何步骤的 prev 都直接回到架构管理
        sessionStorage.setItem('returningFromDiagram', 'true')
        router.push('/system/archdata')
      } else {
        prevStep()
      }
    }

    watch(currentStep, (newStep, oldStep) => {
      if (newStep === 4) {
        const hasSelectedRelations = selectedRelationNodeIds.value && selectedRelationNodeIds.value.length > 0
        if (!hasSelectedRelations) {
          configStore.updateCenterScopeHighlight(false)
        }
      }
    })

    onMounted(async () => {
      const archDataStr = sessionStorage.getItem('archDataForDiagram')
      if (archDataStr) {
        try {
          const archData = JSON.parse(archDataStr)
          sessionStorage.setItem('lastArchDataForDiagram', archDataStr)
          sessionStorage.removeItem('archDataForDiagram')
          
          initFromArchDataManager()
          await initDataFromArch(archData)
        } catch (err) {
          console.error('Failed to initialize from arch data:', err)
        }
      }
    })

    const handleStepChange = (displayIdx) => {
      const step = visibleSteps.value[displayIdx]
      if (step) {
        goToStep(step.originalIndex)
      }
    }

    const goBack = () => {
      router.push('/')
    }

    return {
      steps,
      visibleSteps,
      currentStep,
      displayCurrent,
      currentStepInfo,
      goToStep,
      handleStepChange,
      previewData,
      displayStats,
      stepStats,
      stepProps,
      stepEvents,
      initFromArchData,
      goBack
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.aa-diagram-app {
  height: 100%;
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
