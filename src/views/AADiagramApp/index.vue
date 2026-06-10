<template>
  <div class="aa-diagram-app">
    <StepNavigator
      :steps="visibleSteps"
      :current="displayCurrent"
      :step-stats="stepStats"
      :has-prev="canNavPrev"
      :has-next="canNavNext"
      :next-label="navNextLabel"
      @change="handleStepChange"
      @prev="onNavPrev"
      @next="onNavNext"
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
      handlePrev,
      resetSteps
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
          // 关键修复 v23：chartType 可能是空字符串（chartType 计算属性初值/未选类型），
          // 空字符串会让 MermaidComponent validator 失败 → Vue warn → props.diagramType = ''
          // 进而 useAnnotation.parseAnnotationsFromData 的 businessObject 分支被跳过
          // 只 parse link 的 annotation，node / serviceModule annotation 全丢失
          // 修复：空字符串 fallback 到 'businessObject'（MermaidComponent default 也是这个）
          chartType: chartType.value || 'businessObject',
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
      // 先重置所有步骤状态，确保每次进入都是干净状态（防止 keep-alive 或状态残留）
      resetSteps()

      const archDataStr = sessionStorage.getItem('archDataForDiagram')
      if (archDataStr) {
        try {
          const archData = JSON.parse(archDataStr)
          sessionStorage.setItem('lastArchDataForDiagram', archDataStr)
          sessionStorage.removeItem('archDataForDiagram')

          // 切到 3 步骤模式（类型 → 配置 → 展示），跳过导入/中心/关系 3 步
          // 这里调用的 initFromArchDataManager() 是 useDiagramSteps.js 的版本（line 60 解构）
          // 它把 initFromArchData.value 设为 true，currentStep.value = 3
          // 注意：useDiagramData.js 也有同名 initFromArchDataManager（被重命名为 initDataFromArch），
          // 那个是加载数据用的（带参 archData），line 304 调
          initFromArchDataManager()

          // 关键修复 v24：原本 line 303 + line 304 两行都在调
          // 之前误判 line 303 是 useDiagramData 版本（重命名后的 initDataFromArch）
          // 实际是 useDiagramSteps 版本（切 3 步骤模式）
          // 删了它导致 3 步骤模式没切 → 用户还是看 6 步骤导航
          // 修复：恢复 line 303，让两个调用都执行（步骤模式切换 + 数据加载）

          await initDataFromArch(archData)
        } catch (err) {
          console.error('Failed to initialize from arch data:', err)
        }
      }

      // 测试专用: dev 环境暴露组件状态到 window，方便 e2e 测试跳过 4 步流程
      // 仅 DEV 构建包含，production 构建 import.meta.env.DEV 为 false，被 dead-code-elimination 移除
      if (import.meta.env.DEV) {
        console.log('[AADiagramApp] mounted (new), DEV=', import.meta.env.DEV)
        window.__diagramApp = {
          diagramData,
          currentStep,
          goToStep,
          nextStep,
          prevStep,
          initFromArchDataManager,
          generateDiagram,
          previewData,
          chartType,
          relationFilteredBoCodes,
          centerScope,
          // 关键诊断字段：3 步骤模式状态
          visibleSteps,
          displayCurrent,
          initFromArchData
        }
        console.log('[AADiagramApp] window.__diagramApp exposed (new)')
      }
    })

    const handleStepChange = (displayIdx) => {
      const step = visibleSteps.value[displayIdx]
      if (step) {
        goToStep(step.originalIndex)
      }
    }

    // 导航栏 prev/next 按钮状态
    const canNavPrev = computed(() => {
      // 第一步也显示上一步（用于返回架构数据管理页面）
      return currentStep.value > 0 || initFromArchData.value
    })
    const canNavNext = computed(() => {
      const maxStep = visibleSteps.value.length - 1
      return displayCurrent.value < maxStep
    })
    const navNextLabel = computed(() => {
      // 配置步骤显示"生成图表"而不是"下一步"
      if (currentStep.value === 4) return '生成图表'
      return '下一步'
    })

    const onNavPrev = () => {
      if (initFromArchData.value && displayCurrent.value === 0) {
        // 3 步骤模式的第一步（类型）：上一步返回架构数据管理页面
        sessionStorage.setItem('returningFromDiagram', 'true')
        router.push('/system/archdata')
      } else if (currentStep.value > 0) {
        // 其他情况：正常回退上一步
        prevStep()
      }
    }

    const onNavNext = () => {
      if (currentStep.value === 4) {
        // 配置步骤：触发生成 + 跳转到展示页（与原 panel-header 按钮行为一致）
        try {
          generateDiagram()
          nextStep()
        } catch (err) {
          console.error('生成图表失败:', err)
        }
      } else if (canNavNext.value) {
        nextStep()
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
      goBack,
      canNavPrev,
      canNavNext,
      navNextLabel,
      onNavPrev,
      onNavNext
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
  padding: var(--spacing-md);
  overflow: auto;

  @include respond-to('md') {
    padding: var(--spacing-sm);
  }

  @include respond-to('sm') {
    padding: var(--spacing-xs);
  }
}
</style>
