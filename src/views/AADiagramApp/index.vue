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
import { useChartArchDataStore } from '../../stores/chartArchDataStore'

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

    // [v32] 架构数据图表的"数据来源" Pinia store
    //  - 由架构管理页 (MultiObjectManagementPage) 的 "图表视图" 按钮写入
    //  - onMounted 读这个, 不再读 sessionStorage / module cache
    const chartArchStore = useChartArchDataStore()

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
      // DEBUG 临时解构
      filteredRelations,
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
          modelValue: chartType.value,
          // 关键修复 v36: 范围汇总 props 恢复 (StepChartType 内部 StepScopeSummary 需用)
          center: displayStats.value.center,
          incremental: displayStats.value.incremental,
          total: displayStats.value.total
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

      // [v32] 双层数据源 (Pinia 主 + sessionStorage 备份):
      //   1) chartArchStore (Pinia in-memory): 跨组件共享, 用于 tab re-click
      //   2) sessionStorage 备份: 应对 F5 刷新场景
      //      - F5 后 Pinia 状态丢失, 但 sessionStorage 保留
      //      - 此时 onMounted 读 sessionStorage 兜底
      //   行为:
      //     A) 首次进入 (有 archData): 切 3 步骤模式 + 加载数据, 默认 step 3
      //     B) F5 刷新 (Pinia 空, sessionStorage 有): 从 sessionStorage 读, 仍走 3 步骤
      //     C) 直接 URL 访问 /archdata-chart (都空): 走 6 步骤默认流程
      let archData = chartArchStore.archData

      if (!archData) {
        // [v32-FIX] F5 刷新场景: Pinia 状态丢失, 从 sessionStorage 读
        const archDataStr = sessionStorage.getItem('archDataForDiagram')
          || sessionStorage.getItem('lastArchDataForDiagram')
        if (archDataStr) {
          try {
            archData = JSON.parse(archDataStr)
            // 重新写回 Pinia, 让后续 tab 切换也能用上
            chartArchStore.setArchData(archData)
            console.log('[v32] F5 refresh: restored archData from sessionStorage')
          } catch (err) {
            console.error('[v32] Failed to parse archData from sessionStorage:', err)
          }
        }
      }

      if (archData) {
        try {
          // 切到 3 步骤模式 (类型 → 配置 → 展示)
          initFromArchDataManager()

          // 加载数据 (下游 initDataFromArch 内部逻辑零修改, archData 结构一致)
          await initDataFromArch(archData)

          // 关键修复 v33: 恢复 chartType (F5 刷新后颜色配置区域消失)
          //   chartType 决定 StepConfig 中 CenterDomainSelect / ServiceModuleConfig 是否渲染
          //   F5 后 configStore 重建, chartType='', v-if 不满足 → 颜色区域消失
          //   修复: 从 sessionStorage.archDataChartType 恢复
          const savedChartType = sessionStorage.getItem('archDataChartType')
          if (savedChartType && !configStore.chartType) {
            configStore.updateChartType(savedChartType)
            console.log('[v33] F5 refresh: restored chartType=', savedChartType)
          }

          // 恢复 currentStep
          // 优先级: 1) sessionStorage (F5 后) > 2) 默认 3
          let restoredStep = null
          const savedStepStr = sessionStorage.getItem('archDataCurrentStep')
          if (savedStepStr) {
            const savedStep = parseInt(savedStepStr, 10)
            if (Number.isFinite(savedStep) && savedStep >= 3 && savedStep <= 5) {
              restoredStep = savedStep
            }
          }
          currentStep.value = restoredStep !== null ? restoredStep : 3
        } catch (err) {
          console.error('[v32] Failed to initialize from arch data:', err)
        }
      } else {
        console.log('[v32] no archData (neither Pinia nor sessionStorage), using 6-step default flow')
      }

      // [v32] 监听 chartArchStore.sequence, 处理"已在 chart tab 内再次点 图表视图"场景
      //   - 路由不变 (router.push 相同路径不会 re-mount), 需通过 sequence 触发重新初始化
      watch(() => chartArchStore.sequence, async (newSeq) => {
        if (newSeq > 0) {
          const newArchData = chartArchStore.archData
          if (newArchData) {
            console.log('[v32] chartArchStore.sequence changed, re-initializing')
            resetSteps()
            initFromArchDataManager()
            try {
              await initDataFromArch(newArchData)
              currentStep.value = 3
            } catch (err) {
              console.error('[v32] re-initialization failed:', err)
            }
          }
        }
      })

      // [v32-FIX] 监听 currentStep 变化, 同步到 sessionStorage (F5 后能恢复精确步骤)
      //   场景: 3 步骤模式下用户从 step 3 走到 step 4/5, F5 后要恢复
      watch(currentStep, (newStep) => {
        if (initFromArchData.value) {
          sessionStorage.setItem('archDataCurrentStep', String(newStep))
        } else {
          // 6 步骤模式不保留
          sessionStorage.removeItem('archDataCurrentStep')
        }
      })

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
          initFromArchData,
          // 测试用: 模拟 tab 系统二次点击 chart 触发组件 re-mount
          router,
          // [v32] 暴露 chartArchStore, e2e 测试可直接验证 store 状态
          chartArchStore,
          // DEBUG 临时暴露
          selectedRelationNodeIds,
          relationCategoryTree,
          filteredRelations
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
        // [v32] 不再需要清除 sessionStorage 中的 archData 备份 (已废弃)
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
