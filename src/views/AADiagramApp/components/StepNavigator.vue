<template>
  <nav class="step-navigator">
    <div
      v-for="(step, index) in steps"
      :key="index"
      :class="['step-item', {
        'is-active': current === index,
        'is-completed': current > index,
        'is-disabled': !canAccess(index)
      }]"
      @click="canAccess(index) && $emit('change', index)"
    >
      <div class="step-indicator">
        <span v-if="current > index" class="step-check">✓</span>
        <span v-else class="step-number">{{ index + 1 }}</span>
      </div>
      <div class="step-content">
        <div class="step-title">{{ step.title }}</div>
        <div class="step-desc">{{ step.desc }}</div>
      </div>
      <div v-if="index < steps.length - 1" class="step-connector">
        <div class="step-line"></div>
      </div>
    </div>
  </nav>
</template>

<script>
export default {
  name: 'StepNavigator',
  props: {
    steps: {
      type: Array,
      required: true
    },
    current: {
      type: Number,
      default: 0
    }
  },
  emits: ['change'],
  methods: {
    canAccess(index) {
      return index <= this.current + 1
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.step-navigator {
  display: flex;
  justify-content: center;
  padding: var(--spacing-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  gap: var(--spacing-xs);
}

.step-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-normal);

  &:hover:not(.is-disabled) {
    background: rgba(24, 144, 255, 0.05);
  }

  &.is-active {
    .step-indicator {
      background: var(--color-primary);
      color: white;
    }

    .step-title {
      color: var(--color-primary);
      font-weight: 600;
    }
  }

  &.is-completed {
    .step-indicator {
      background: var(--color-success);
      color: white;
    }
  }

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
}

.step-indicator {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  @include flex-center;
  font-size: var(--font-size-md);
  font-weight: 600;
  transition: all var(--transition-normal);
}

.step-check {
  font-size: var(--font-size-lg);
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-title {
  font-size: var(--font-size-md);
  font-weight: 500;
  color: var(--color-text-primary);
  transition: color var(--transition-normal);
}

.step-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.step-connector {
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-sm);
}

.step-line {
  width: 40px;
  height: 2px;
  background: var(--color-border);
  transition: background var(--transition-normal);

  .is-completed + .step-connector &,
  .is-active + .step-connector & {
    background: var(--color-success);
  }
}

// 响应式
@include respond-to('md') {
  .step-navigator {
    padding: var(--spacing-md);
  }

  .step-connector {
    display: none;
  }
}

@include respond-to('sm') {
  .step-navigator {
    padding: var(--spacing-sm);
    gap: var(--spacing-xs);
  }

  .step-item {
    flex-direction: column;
    padding: var(--spacing-xs);
    min-width: 60px;
  }

  .step-content {
    display: none;
  }

  .step-indicator {
    width: 28px;
    height: 28px;
    font-size: var(--font-size-sm);
  }
}
</style>
