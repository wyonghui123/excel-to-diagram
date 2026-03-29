import { ref, computed } from 'vue'

const STEPS = [
  { title: '导入', desc: '上传Excel文件', component: 'StepUpload' },
  { title: '范围', desc: '选择数据范围', component: 'StepScope' },
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
    // 可以回到已完成的步骤或当前步骤的下一步
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
