import { ref, computed } from 'vue'

const STEPS = [
  { title: '导入', desc: '上传Excel文件', component: 'StepUpload' },
  { title: '中心', desc: '选择中心范围', component: 'StepScope' },
  { title: '关系', desc: '选择关系范围', component: 'StepScope' },
  { title: '类型', desc: '选择图表类型', component: 'StepChartType' },
  { title: '配置', desc: '设置图表参数', component: 'StepConfig' },
  { title: '展示', desc: '查看关系图', component: 'StepDisplay' }
]

export function useDiagramSteps() {
  const currentStep = ref(0)
  const completedSteps = ref(new Set())
  const initFromArchData = ref(false)

  const steps = computed(() => STEPS)

  const visibleSteps = computed(() => {
    if (initFromArchData.value) {
      return STEPS.slice(3).map((step, i) => ({
        ...step,
        originalIndex: i + 3
      }))
    }
    return STEPS.map((step, i) => ({
      ...step,
      originalIndex: i
    }))
  })

  const displayCurrent = computed(() => {
    return initFromArchData.value ? currentStep.value - 3 : currentStep.value
  })

  const initFromArchDataManager = () => {
    initFromArchData.value = true
    currentStep.value = 3
  }

  const currentStepInfo = computed(() => STEPS[currentStep.value])

  const canGoToStep = (index) => {
    if (initFromArchData.value && index < 3) {
      return false
    }
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
    initFromArchData.value = false
  }

  const handlePrev = (emit) => {
    if (initFromArchData.value && currentStep.value === 3) {
      emit('back-to-landing')
    } else {
      if (currentStep.value > 0) {
        currentStep.value--
      }
    }
  }

  return {
    steps,
    visibleSteps,
    currentStep,
    displayCurrent,
    currentStepInfo,
    completedSteps,
    initFromArchData,
    canGoToStep,
    goToStep,
    nextStep,
    prevStep,
    handlePrev,
    resetSteps,
    initFromArchDataManager
  }
}
