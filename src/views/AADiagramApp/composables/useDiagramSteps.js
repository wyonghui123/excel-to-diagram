import { ref, computed } from 'vue'

/**
 * 3 步骤模式（2026-06-13 重构后）:
 *   0: 类型 - 选择图表类型
 *   1: 配置 - 设置图表参数（颜色、布局等）
 *   2: 展示 - 查看关系图
 *
 * 入口:
 *   - 用户从 "架构数据管理" 页面 navigate 到本页面，自动进入 3 步骤模式
 *   - 直接 URL 访问 /archdata-chart 但没有 archData: 重定向到 /system/archdata（6 步骤已废弃）
 *
 * 状态:
 *   - useDiagramData().initFromArchDataManager(archData) 加载数据
 *   - 没有 6 步骤 fallback（之前是 STEPS 0-2 = 导入/中心/关系，已废弃）
 */
const STEPS = [
  { title: '类型', desc: '选择图表类型', component: 'StepChartType' },
  { title: '配置', desc: '设置图表参数', component: 'StepConfig' },
  { title: '展示', desc: '查看关系图', component: 'StepDisplay' }
]

export function useDiagramSteps() {
  const currentStep = ref(0)
  const completedSteps = ref(new Set())

  const steps = computed(() => STEPS)

  const currentStepInfo = computed(() => STEPS[currentStep.value])

  const canGoToStep = (index) => {
    if (index < 0 || index >= STEPS.length) return false
    return index <= currentStep.value + 1 || completedSteps.value.has(index)
  }

  const goToStep = (index) => {
    if (!canGoToStep(index)) return
    currentStep.value = index
  }

  const nextStep = () => {
    if (currentStep.value < STEPS.length - 1) {
      completedSteps.value.add(currentStep.value)
      currentStep.value++
    }
  }

  const prevStep = () => {
    if (currentStep.value > 0) {
      currentStep.value--
    }
  }

  const resetSteps = () => {
    currentStep.value = 0
    completedSteps.value.clear()
  }

  return {
    steps,
    currentStep,
    currentStepInfo,
    completedSteps,
    canGoToStep,
    goToStep,
    nextStep,
    prevStep,
    resetSteps
  }
}
