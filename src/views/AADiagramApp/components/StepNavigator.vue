<template>
  <nav class="step-navigator">
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
        <AppIcon v-if="current > index" name="check" size="sm" class="step-check" />
        <span v-else class="step-number">{{ index + 1 }}</span>
      </div>
      <div class="step-content">
        <div class="step-title">{{ step.title }}</div>
        <div class="step-desc">{{ step.desc }}</div>
        <!-- 步骤统计信息 - 极简单行（只显示当前及已完成的步骤） -->
        <div v-if="index <= current && stepStats[step.originalIndex] && hasStats(stepStats[step.originalIndex], step.originalIndex)" class="step-stats-minimal">
          {{ formatMinimalStats(stepStats[step.originalIndex], step.originalIndex) }}
        </div>
      </div>
      <div v-if="index < steps.length - 1" class="step-connector">
        <div class="step-line"></div>
      </div>
    </div>
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
    }
  },
  emits: ['change'],
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
      // 配置步骤（索引4）检查是否有任何统计值
      if (index === 4) {
        return stats && (
          (stats.serviceModules > 0) ||
          (stats.businessObjects > 0) ||
          (stats.objectRelations > 0) ||
          (stats.serviceModuleRelations > 0)
        )
      }
      // 关系步骤（索引2）：始终显示统计，即使没有新增关系也显示 +0
      if (index === 2) {
        return stats && stats.businessObjects >= 0
      }
      // 其他步骤：只有当业务对象数量大于0时才显示统计
      return stats && stats.businessObjects > 0
    },
    formatMinimalStats(stats, index) {
      if (!stats) return ''
      const parts = []

      // 步骤1（中心步骤）显示完整统计（领域、子域、对象）
      const isCenter = index === 1

      // 步骤2（关系步骤）显示增量统计
      const isIncremental = index === 2
      const prefix = isIncremental ? '+' : ''

      // 步骤4（配置步骤）根据图表类型显示不同统计
      const isConfig = index === 4

      if (isConfig) {
        // 配置步骤：根据图表类型显示
        // 业务对象图：服务模块、对象、关系
        // 服务模块图：服务模块、服务模块关系
        if (stats.serviceModules > 0) parts.push(`${stats.serviceModules}服务模块`)
        if (stats.businessObjects > 0) parts.push(`${stats.businessObjects}对象`)
        if (stats.objectRelations > 0) parts.push(`${stats.objectRelations}关系`)
        if (stats.serviceModuleRelations > 0) parts.push(`${stats.serviceModuleRelations}模块关系`)
        return parts.join(' · ') || ''
      }

      // 中心步骤显示完整统计（领域、子域、对象）
      if (isCenter) {
        if (stats.domains > 0) parts.push(`${stats.domains}领域`)
        if (stats.subDomains > 0) parts.push(`${stats.subDomains}子域`)
        parts.push(`${stats.businessObjects}对象`)
        return parts.join(' · ')
      }

      // 关系步骤显示增量统计（始终显示所有项，包括0值）
      if (isIncremental) {
        parts.push(`${prefix}${stats.domains || 0}领域`)
        parts.push(`${prefix}${stats.subDomains || 0}子域`)
        parts.push(`${prefix}${stats.businessObjects || 0}对象`)
        parts.push(`${prefix}${stats.objectRelations || 0}关系`)
        return parts.join(' · ')
      }

      // 其他步骤（导入、类型）显示完整统计
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
  justify-content: center;
  padding: var(--spacing-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  gap: var(--spacing-xs);
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-normal);
  min-width: 120px;

  &:hover:not(.is-disabled) {
    background: rgba(234, 88, 12, 0.05);
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
  flex-shrink: 0;
  margin-top: 2px;
}

.step-check {
  font-size: var(--font-size-lg);
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 100px;
  white-space: nowrap;
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
  white-space: nowrap;
}

/* 极简统计样式 */
.step-stats-minimal {
  margin-top: 4px;
  font-size: 10px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-connector {
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-sm);
  align-self: center;
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

  .step-stats-minimal {
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
    align-items: center;
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
