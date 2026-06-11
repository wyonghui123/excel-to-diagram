<template>
  <nav class="step-navigator">
    <!-- 上一步按钮 -->
    <button
      v-if="hasPrev"
      class="nav-btn nav-btn--prev"
      @click.stop="$emit('prev')"
    >
      <AppIcon name="arrow-left" size="sm" />
      <span class="nav-btn__text">上一步</span>
    </button>

    <div class="step-navigator__steps">
      <div
        v-for="(step, index) in steps"
        :key="step.originalIndex !== undefined ? step.originalIndex : index"
        :class="['step-item', {
          'is-active': current === index,
          'is-completed': current > index,
          'is-disabled': !canAccess(index)
        }]"
        @click.stop.prevent="handleStepClick(index)"
      >
        <div class="step-indicator">
          <AppIcon v-if="current > index" name="check" size="xs" class="step-check" />
          <span v-else class="step-number">{{ index + 1 }}</span>
        </div>
        <span class="step-title">{{ step.title }}</span>
        <!-- 统计信息内联 -->
        <span v-if="index <= current && stepStats[step.originalIndex] && hasStats(stepStats[step.originalIndex], step.originalIndex)" class="step-stats-inline">
          {{ formatMinimalStats(stepStats[step.originalIndex], step.originalIndex) }}
        </span>
        <div v-if="index < steps.length - 1" class="step-connector">
          <div class="step-line"></div>
        </div>
      </div>
    </div>

    <!-- 下一步按钮 -->
    <button
      v-if="hasNext"
      class="nav-btn nav-btn--next"
      @click.stop="$emit('next')"
    >
      <span class="nav-btn__text">{{ nextLabel }}</span>
      <AppIcon name="arrow-right" size="sm" />
    </button>
  </nav>
</template>

<script>
import { AppIcon } from '@/components/common/AppIcon'

export default {
  name: 'StepNavigator',
  components: {
    AppIcon
  },
  props: {
    steps: {
      type: Array,
      required: true
    },
    current: {
      type: Number,
      default: 0
    },
    stepStats: {
      type: Object,
      default: () => ({})
    },
    hasPrev: {
      type: Boolean,
      default: false
    },
    hasNext: {
      type: Boolean,
      default: false
    },
    nextLabel: {
      type: String,
      default: '下一步'
    }
  },
  emits: ['change', 'prev', 'next'],
  methods: {
    handleStepClick(index) {
      if (!this.canAccess(index)) {
        return
      }
      this.$emit('change', index)
    },
    canAccess(index) {
      return index <= this.current + 1
    },
    hasStats(stats, index) {
      if (index === 4) {
        return stats && (
          (stats.serviceModules > 0) ||
          (stats.businessObjects > 0) ||
          (stats.objectRelations > 0) ||
          (stats.serviceModuleRelations > 0)
        )
      }
      if (index === 2) {
        return stats && stats.businessObjects >= 0
      }
      return stats && stats.businessObjects > 0
    },
    formatMinimalStats(stats, index) {
      if (!stats) return ''
      const parts = []
      const isCenter = index === 1
      const isIncremental = index === 2
      const prefix = isIncremental ? '+' : ''
      const isConfig = index === 4

      if (isConfig) {
        if (stats.serviceModules > 0) parts.push(`${stats.serviceModules}服务模块`)
        if (stats.businessObjects > 0) parts.push(`${stats.businessObjects}对象`)
        if (stats.objectRelations > 0) parts.push(`${stats.objectRelations}关系`)
        if (stats.serviceModuleRelations > 0) parts.push(`${stats.serviceModuleRelations}模块关系`)
        return parts.join(' · ') || ''
      }

      if (isCenter) {
        if (stats.domains > 0) parts.push(`${stats.domains}领域`)
        if (stats.subDomains > 0) parts.push(`${stats.subDomains}子域`)
        parts.push(`${stats.businessObjects}对象`)
        return parts.join(' · ')
      }

      if (isIncremental) {
        parts.push(`${prefix}${stats.domains || 0}领域`)
        parts.push(`${prefix}${stats.subDomains || 0}子域`)
        parts.push(`${prefix}${stats.businessObjects || 0}对象`)
        if (stats.externalBusinessObjects > 0) parts.push(`${prefix}${stats.externalBusinessObjects}外部对象`)  // v29
        parts.push(`${prefix}${stats.objectRelations || 0}关系`)
        return parts.join(' · ')
      }

      if (stats.domains > 0) parts.push(`${stats.domains}领域`)
      if (stats.subDomains > 0) parts.push(`${stats.subDomains}子域`)
      parts.push(`${stats.businessObjects}对象`)
      if (stats.objectRelations > 0) parts.push(`${stats.objectRelations}关系`)

      return parts.join(' · ')
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.step-navigator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: 8px var(--spacing-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
}

/* 导航按钮（上一步/下一步） */
.nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(234, 88, 12, 0.04);
  }

  &:active {
    transform: scale(0.97);
  }

  &--next {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: white;

    &:hover {
      background: var(--color-primary-dark, #c44a0a);
      border-color: var(--color-primary-dark, #c44a0a);
      color: white;
    }
  }
}

.nav-btn__text {
  font-size: 13px;
}

/* 步骤区域 */
.step-navigator__steps {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.step-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  position: relative;

  &:hover:not(.is-disabled) {
    background: rgba(234, 88, 12, 0.06);
  }

  &.is-active {
    background: rgba(234, 88, 12, 0.1);

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
    opacity: 0.45;
  }
}

.step-indicator {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  @include flex-center;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.step-check {
  font-size: 12px;
}

.step-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  transition: color 0.2s ease;
}

/* 内联统计信息 */
.step-stats-inline {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-left: 2px;
}

.step-connector {
  display: flex;
  align-items: center;
  padding: 0 2px;
}

.step-line {
  width: 24px;
  height: 2px;
  background: var(--color-border-light, #e8e8e8);
  border-radius: 1px;
  transition: background 0.2s ease;

  .is-completed + .step-connector &,
  .is-active + .step-connector & {
    background: var(--color-success);
  }
}

// 响应式
@include respond-to('md') {
  .step-navigator {
    padding: 6px var(--spacing-md);
    gap: var(--spacing-sm);
  }

  .nav-btn__text {
    display: none;
  }

  .nav-btn {
    padding: 6px 10px;
  }

  .step-connector {
    display: none;
  }

  .step-stats-inline {
    display: none;
  }
}

@include respond-to('sm') {
  .step-navigator {
    padding: 4px var(--spacing-sm);
    gap: var(--spacing-xs);
  }

  .step-item {
    padding: 4px 8px;
  }

  .step-title {
    font-size: 12px;
  }

  .step-indicator {
    width: 20px;
    height: 20px;
    font-size: 11px;
  }
}
</style>
