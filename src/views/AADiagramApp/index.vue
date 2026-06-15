<template>
  <div class="aa-diagram-app">
    <StepNavigator
      :steps="steps"
      :current="currentStep"
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
import { computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDiagramSteps } from './composables/useDiagramSteps.js'
import { useDiagramData } from './composables/useDiagramData.js'
import { useDiagramConfigStore } from '../../stores/diagramConfigStore.js'
import { useChartArchDataStore } from '../../stores/chartArchDataStore'
import StepNavigator from './components/StepNavigator.vue'

// 步骤组件（2026-06-13: 6 步骤已废弃，仅保留 3 步骤: 类型/配置/展示）
import StepChartType from './components/steps/StepChartType.vue'
import StepConfig from './components/steps/StepConfig.vue'
import StepDisplay from './components/steps/StepDisplay.vue'

export default {
  name: 'AADiagramApp',
  components: {
    StepNavigator,
    StepChartType,
    StepConfig,
    StepDisplay
  },
  setup() {
    const router = useRouter()
    const {
      steps,
      currentStep,
      currentStepInfo,
      goToStep,
      nextStep,
      prevStep,
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
      chartType,
      chartTypeChanged,
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
      // DEBUG 临时解构
      filteredRelations,
      generateDiagram,
      resetChartTypeChanged,
      saveCenterScopePreset,
      loadCenterScopePreset,
      deleteCenterScopePreset,
      toggleRelationNode,
      centerScopeMarkers,
      filteredDomainProducts,
      initFromArchDataManager: initDataFromArch,
      isInitializedFromArchData,
      // [2026-06-15] 缓存读取 (切 tab 时恢复 diagramData)
      loadCachedDiagram
    } = useDiagramData()

    // 步骤组件的 props (3 步骤模式: 0=类型, 1=配置, 2=展示)
    const stepProps = computed(() => {
      const propsMap = {
        0: {
          modelValue: chartType.value,
          // 关键修复 v36: 范围汇总 props 恢复 (StepChartType 内部 StepScopeSummary 需用)
          center: displayStats.value.center,
          incremental: displayStats.value.incremental,
          total: displayStats.value.total
        },
        1: {
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
        2: {
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

    // 步骤组件的事件
    const stepEvents = computed(() => {
      const eventsMap = {
        0: {
          'update:modelValue': (val) => configStore.updateChartType(val),
          'next': nextStep,
          'prev': onNavPrev
        },
        1: {
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
          'prev': onNavPrev
        },
        2: {
          'prev': onNavPrev,
          'regenerate': () => goToStep(1)
        }
      }
      return eventsMap[currentStep.value] || {}
    })

    /**
     * 步骤导航统计信息 (3 步骤模式)
     *  - 步骤0（类型）: displayStats.total - 显示总数统计
     *  - 步骤1（配置）: displayStats.config - 根据图表类型显示不同统计
     *  - 步骤2（展示）: null - 不显示统计
     */
    const stepStats = computed(() => {
      return {
        0: displayStats.value.total,          // 类型步骤 - 显示总数
        1: displayStats.value.config,         // 配置步骤 - 显示图表类型相关统计
        2: null                               // 展示步骤 - 不显示统计
      }
    })

    // 导航栏按钮: 在第一步也显示"上一步"（用于返回架构数据管理）
    const canNavPrev = computed(() => {
      return currentStep.value >= 0  // 始终允许 (第一步是返回架构管理)
    })
    const canNavNext = computed(() => {
      return currentStep.value < steps.value.length - 1
    })
    const navNextLabel = computed(() => {
      // 配置步骤显示"生成图表"而不是"下一步"
      if (currentStep.value === 1) return '生成图表'
      return '下一步'
    })

    const onNavPrev = () => {
      if (currentStep.value === 0) {
        // 3 步骤模式的第一步（类型）：上一步返回架构数据管理页面
        sessionStorage.setItem('returningFromDiagram', 'true')
        router.push('/system/archdata')
      } else if (currentStep.value > 0) {
        // 其他情况：正常回退上一步
        prevStep()
      }
    }

    const onNavNext = () => {
      if (currentStep.value === 1) {
        // 配置步骤：触发生成 + 跳转到展示页
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

    const handleStepChange = (index) => {
      goToStep(index)
    }

    watch(currentStep, (newStep) => {
      if (newStep === 1) {
        const hasSelectedRelations = selectedRelationNodeIds.value && selectedRelationNodeIds.value.length > 0
        if (!hasSelectedRelations) {
          configStore.updateCenterScopeHighlight(false)
        }
      }
      // [v32] 同步到 sessionStorage, F5 后能恢复精确步骤
      sessionStorage.setItem('archDataCurrentStep', String(newStep))
    })

    onMounted(async () => {
      // 先重置所有步骤状态，确保每次进入都是干净状态
      resetSteps()

      // [v32] 双层数据源 (Pinia 主 + sessionStorage 备份):
      //   1) chartArchStore (Pinia in-memory): 跨组件共享, 用于 tab re-click
      //   2) sessionStorage 备份: 应对 F5 刷新场景
      //      - F5 后 Pinia 状态丢失, 但 sessionStorage 保留
      //      - 此时 onMounted 读 sessionStorage 兜底
      //   行为:
      //     A) 首次进入 (有 archData): 加载数据, 默认 step 0
      //     B) F5 刷新 (Pinia 空, sessionStorage 有): 从 sessionStorage 读
      //     C) 直接 URL 访问 /archdata-chart (都空): 2026-06-13 重定向到 /system/archdata
      //        (6 步骤 fallback 已废弃)
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

          // 恢复 currentStep (3 步骤模式: 0/1/2)
          // 优先级: 1) sessionStorage (F5 后) > 2) 默认 0
          let restoredStep = null
          const savedStepStr = sessionStorage.getItem('archDataCurrentStep')
          if (savedStepStr) {
            const savedStep = parseInt(savedStepStr, 10)
            if (Number.isFinite(savedStep) && savedStep >= 0 && savedStep <= 2) {
              restoredStep = savedStep
            }
          }

          // [2026-06-15] step 2 (展示) 恢复条件:
          //   - 用户上次在展示页 → 期望切回来看到图
          //   - 但 diagramData 是 useDiagramData() 的局部 ref(null), 切 tab 后丢失
          //   - 解决: 尝试从 Pinia 缓存读, 命中才允许 step 2
          //   - 未命中: 范围/配置可能变了, 或 30 分钟 TTL 过期, 或 F5 后 Pinia 状态丢失
          //            → 回退到 step 1 (让用户重新生成, 避免展示 stale 图)
          if (restoredStep === 2) {
            const cachedDiagram = loadCachedDiagram()
            if (cachedDiagram) {
              console.log('[v44] diagramData 缓存命中, 保留 step 2')
            } else {
              console.log('[v44] diagramData 缓存未命中 (范围/配置变了 / TTL 过期 / F5 丢失), 回退到 step 1')
              restoredStep = 1
            }
          }

          currentStep.value = restoredStep !== null ? restoredStep : 0
        } catch (err) {
          console.error('[v32] Failed to initialize from arch data:', err)
        }
      } else {
        // [2026-06-13] 6 步骤 fallback 已废弃
        //   之前: 走 6 步骤默认流程 (StepUpload → StepScope → StepScope → StepChartType → StepConfig → StepDisplay)
        //   现在: 重定向到架构管理页, 让用户先选择数据
        console.log('[v40] no archData (neither Pinia nor sessionStorage), redirecting to arch manager (6-step fallback deprecated)')
        router.replace('/system/archdata')
        return
      }

      // [v32] 监听 chartArchStore.sequence, 处理"已在 chart tab 内再次点 图表视图"场景
      //   - 路由不变 (router.push 相同路径不会 re-mount), 需通过 sequence 触发重新初始化
      watch(() => chartArchStore.sequence, async (newSeq) => {
        if (newSeq > 0) {
          const newArchData = chartArchStore.archData
          if (newArchData) {
            console.log('[v32] chartArchStore.sequence changed, re-initializing')
            resetSteps()
            try {
              await initDataFromArch(newArchData)
              currentStep.value = 0
            } catch (err) {
              console.error('[v32] re-initialization failed:', err)
            }
          }
        }
      })

      // 测试专用: dev 环境暴露组件状态到 window，方便 e2e 测试
      if (import.meta.env.DEV) {
        console.log('[AADiagramApp] mounted (new), DEV=', import.meta.env.DEV)
        window.__diagramApp = {
          diagramData,
          currentStep,
          goToStep,
          nextStep,
          prevStep,
          generateDiagram,
          previewData,
          chartType,
          centerScope,
          router,
          chartArchStore,
          // DEBUG 临时暴露
          selectedRelationNodeIds,
          relationCategoryTree,
          filteredRelations
        }
        console.log('[AADiagramApp] window.__diagramApp exposed (new)')
      }
    })

    return {
      steps,
      currentStep,
      currentStepInfo,
      goToStep,
      handleStepChange,
      previewData,
      displayStats,
      stepStats,
      stepProps,
      stepEvents,
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
