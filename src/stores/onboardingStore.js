import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useOnboardingStore = defineStore('onboarding', () => {
  const hasCompletedTour = ref(false)
  const currentTourStep = ref(0)
  const shownHints = ref(new Set())
  const skippedTour = ref(false)
  const tourCompletedAt = ref(null)
  const tourType = ref(null)

  const shouldShowTour = computed(() => !hasCompletedTour.value && !skippedTour.value)

  function shouldShowHint(hintId) {
    return !shownHints.value.has(hintId)
  }

  function startTour(type) {
    tourType.value = type
    currentTourStep.value = 0
  }

  function completeTour() {
    hasCompletedTour.value = true
    tourCompletedAt.value = new Date().toISOString()
  }

  function skipTour() {
    skippedTour.value = true
  }

  function resetTour() {
    hasCompletedTour.value = false
    skippedTour.value = false
    currentTourStep.value = 0
    tourCompletedAt.value = null
    tourType.value = null
  }

  function setCurrentStep(step) {
    currentTourStep.value = step
  }

  function markHintShown(hintId) {
    shownHints.value.add(hintId)
  }

  function resetAllHints() {
    shownHints.value.clear()
  }

  return {
    hasCompletedTour,
    currentTourStep,
    shownHints,
    skippedTour,
    tourCompletedAt,
    tourType,
    shouldShowTour,
    shouldShowHint,
    startTour,
    completeTour,
    skipTour,
    resetTour,
    setCurrentStep,
    markHintShown,
    resetAllHints,
  }
}, {
  persist: {
    key: 'onboarding',
    storage: localStorage,
    paths: ['hasCompletedTour', 'skippedTour', 'shownHints', 'tourCompletedAt'],
    serializer: {
      serialize: (state) => {
        const raw = JSON.parse(JSON.stringify(state))
        return JSON.stringify({
          ...raw,
          shownHints: [...state.shownHints],
        })
      },
      deserialize: (raw) => {
        const parsed = JSON.parse(raw)
        return {
          ...parsed,
          shownHints: new Set(parsed.shownHints || []),
        }
      },
    },
  },
})
