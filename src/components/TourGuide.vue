<template>
  <Teleport to="body">
    <Transition name="tour-fade">
      <div v-if="isVisible" class="tour-overlay" :class="{ 'is-centered': isCentered }">
        <div v-if="currentStep" class="tour-container">
          <div v-if="currentStep.highlight && targetElement" class="tour-highlight" :style="highlightStyle"></div>
          
          <div class="tour-tooltip" :style="tooltipStyle" :class="[`placement-${currentStep.placement || 'bottom'}`]">
            <div class="tour-header">
              <span class="tour-step-indicator">{{ currentStepIndex + 1 }} / {{ steps.length }}</span>
              <button class="tour-close" @click="handleClose">
                <AppIcon name="close" size="sm" />
              </button>
            </div>
            
            <div class="tour-body">
              <h3 class="tour-title">{{ currentStep.title }}</h3>
              <p class="tour-content">{{ currentStep.content }}</p>
            </div>
            
            <div class="tour-footer">
              <div class="tour-dots">
                <span
                  v-for="(step, index) in steps"
                  :key="step.target || step.title || index"
                  :class="['tour-dot', { active: index === currentStepIndex }]"
                  @click="goToStep(index)"
                ></span>
              </div>
              
              <div class="tour-actions">
                <AppButton
                  v-if="currentStepIndex > 0"
                  variant="secondary"
                  size="sm"
                  @click="prevStep"
                >
                  上一步
                </AppButton>
                
                <AppButton
                  v-if="currentStepIndex < steps.length - 1"
                  variant="primary"
                  size="sm"
                  @click="nextStep"
                >
                  下一步
                </AppButton>
                
                <AppButton
                  v-else
                  variant="primary"
                  size="sm"
                  @click="handleComplete"
                >
                  完成
                </AppButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { AppIcon, AppButton } from './common'
import { useOnboardingStore } from '@/stores/onboardingStore'

export default {
  name: 'TourGuide',
  components: {
    AppIcon,
    AppButton
  },
  props: {
    steps: {
      type: Array,
      required: true
    },
    autoStart: {
      type: Boolean,
      default: false
    }
  },
  emits: ['complete', 'close', 'step-change'],
  setup(props, { emit }) {
    const isVisible = ref(false)
    const currentStepIndex = ref(0)
    const targetElement = ref(null)
    const elementRect = ref(null)
    
    const onboardingStore = useOnboardingStore()
    
    const currentStep = computed(() => {
      return props.steps[currentStepIndex.value] || null
    })
    
    const isCentered = computed(() => {
      return currentStep.value?.placement === 'center'
    })
    
    const highlightStyle = computed(() => {
      if (!elementRect.value || isCentered.value) return {}
      
      const padding = 8
      return {
        top: `${elementRect.value.top - padding}px`,
        left: `${elementRect.value.left - padding}px`,
        width: `${elementRect.value.width + padding * 2}px`,
        height: `${elementRect.value.height + padding * 2}px`
      }
    })
    
    const tooltipStyle = computed(() => {
      if (isCentered.value) return {}
      if (!elementRect.value) return {}
      
      const padding = 16
      const tooltipWidth = 320
      const tooltipHeight = 200
      
      const placement = currentStep.value?.placement || 'bottom'
      let top, left
      
      switch (placement) {
        case 'top':
          top = elementRect.value.top - tooltipHeight - padding
          left = elementRect.value.left + (elementRect.value.width - tooltipWidth) / 2
          break
        case 'bottom':
          top = elementRect.value.bottom + padding
          left = elementRect.value.left + (elementRect.value.width - tooltipWidth) / 2
          break
        case 'left':
          top = elementRect.value.top + (elementRect.value.height - tooltipHeight) / 2
          left = elementRect.value.left - tooltipWidth - padding
          break
        case 'right':
          top = elementRect.value.top + (elementRect.value.height - tooltipHeight) / 2
          left = elementRect.value.right + padding
          break
        default:
          top = elementRect.value.bottom + padding
          left = elementRect.value.left
      }
      
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      
      if (left < 0) left = padding
      if (left + tooltipWidth > viewportWidth) left = viewportWidth - tooltipWidth - padding
      if (top < 0) top = padding
      if (top + tooltipHeight > viewportHeight) top = viewportHeight - tooltipHeight - padding
      
      return {
        top: `${top}px`,
        left: `${left}px`,
        position: 'fixed'
      }
    })
    
    const updateElementRect = async () => {
      if (!currentStep.value?.target) {
        elementRect.value = null
        return
      }
      
      await nextTick()
      
      const selector = currentStep.value.target
      targetElement.value = document.querySelector(selector)
      
      if (targetElement.value) {
        const rect = targetElement.value.getBoundingClientRect()
        elementRect.value = {
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height,
          bottom: rect.bottom,
          right: rect.right
        }
        
        targetElement.value.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        })
      }
    }
    
    const start = () => {
      isVisible.value = true
      currentStepIndex.value = 0
      updateElementRect()
    }
    
    const stop = () => {
      isVisible.value = false
    }
    
    const nextStep = () => {
      if (currentStepIndex.value < props.steps.length - 1) {
        currentStepIndex.value++
        emit('step-change', currentStepIndex.value)
        updateElementRect()
      }
    }
    
    const prevStep = () => {
      if (currentStepIndex.value > 0) {
        currentStepIndex.value--
        emit('step-change', currentStepIndex.value)
        updateElementRect()
      }
    }
    
    const goToStep = (index) => {
      if (index >= 0 && index < props.steps.length) {
        currentStepIndex.value = index
        emit('step-change', index)
        updateElementRect()
      }
    }
    
    const handleClose = () => {
      stop()
      emit('close')
    }
    
    const handleComplete = () => {
      onboardingStore.completeTour()
      stop()
      emit('complete')
    }
    
    const handleKeydown = (e) => {
      if (!isVisible.value) return
      
      switch (e.key) {
        case 'Escape':
          handleClose()
          break
        case 'ArrowRight':
          nextStep()
          break
        case 'ArrowLeft':
          prevStep()
          break
      }
    }
    
    watch(currentStepIndex, () => {
      updateElementRect()
    })
    
    onMounted(() => {
      window.addEventListener('keydown', handleKeydown)
      window.addEventListener('resize', updateElementRect)
      
      if (props.autoStart) {
        start()
      }
    })
    
    onBeforeUnmount(() => {
      window.removeEventListener('keydown', handleKeydown)
      window.removeEventListener('resize', updateElementRect)
    })
    
    return {
      isVisible,
      currentStepIndex,
      currentStep,
      isCentered,
      targetElement,
      highlightStyle,
      tooltipStyle,
      start,
      stop,
      nextStep,
      prevStep,
      goToStep,
      handleClose,
      handleComplete
    }
  }
}
</script>

<style lang="scss" scoped>
@import '../styles/mixins.scss';

.tour-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: var(--z-index-tour);
  
  &.is-centered {
    @include flex-center;
  }
}

.tour-highlight {
  position: fixed;
  border: 2px solid var(--color-primary);
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
  pointer-events: none;
  transition: all 0.3s ease;
  z-index: 1;
}

.tour-container {
  position: relative;
  z-index: 2;
}

.tour-tooltip {
  width: 320px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  animation: tour-pop-in 0.3s ease;
  
  &.placement-center {
    margin: auto;
  }
}

.tour-header {
  @include flex-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  color: white;
}

.tour-step-indicator {
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.tour-close {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: white;
  cursor: pointer;
  @include flex-center;
  border-radius: var(--radius-sm);
  transition: background var(--transition-normal);
  
  &:hover {
    background: rgba(255, 255, 255, 0.2);
  }
}

.tour-body {
  padding: var(--spacing-md);
}

.tour-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.tour-content {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: 1.6;
}

.tour-footer {
  @include flex-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.tour-dots {
  display: flex;
  gap: var(--spacing-xs);
}

.tour-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-border);
  cursor: pointer;
  transition: all var(--transition-normal);
  
  &:hover {
    background: var(--color-text-tertiary);
  }
  
  &.active {
    background: var(--color-primary);
    transform: scale(1.2);
  }
}

.tour-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.tour-fade-enter-active,
.tour-fade-leave-active {
  transition: opacity 0.3s ease;
}

.tour-fade-enter-from,
.tour-fade-leave-to {
  opacity: 0;
}

@keyframes tour-pop-in {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
