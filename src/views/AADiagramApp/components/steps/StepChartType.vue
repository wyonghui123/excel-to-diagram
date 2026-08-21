<template>
  <div class="step-chart-type">
    <div class="chart-type-panel">
      <div class="panel-body">
        <!-- 关键修复 v36: 恢复范围汇总 (StepScopeSummary) - 之前误删 -->
        <!--   误读用户需求: 用户说"导航上第一步统计去掉"是指 StepNavigator 上的文字, -->
        <!--   不是 StepChartType 步骤内部的内容区域 (StepScopeSummary 卡片) -->
        <!--   修复: 把 StepScopeSummary 加回来 + 保留 StepNavigator 修改 -->
        <StepScopeSummary
          :center="center"
          :incremental="incremental"
          :total="total"
        />

        <h2 class="section-title">选择图表类型</h2>
        <p class="section-desc">请选择要生成的图表类型</p>
        
        <div class="chart-options">
          <div
            :class="['chart-option', { 'is-selected': modelValue === 'businessObject' }]"
            @click="selectType('businessObject')"
          >
            <div class="option-icon"><AppIcon name="arrow-right" size="xl" /></div>
            <div class="option-content">
              <h3>业务对象图</h3>
              <p>展示业务对象之间的关系和依赖</p>
            </div>
            <div class="option-check">
              <AppIcon v-if="modelValue === 'businessObject'" name="check" size="md" />
            </div>
          </div>
          
          <div
            :class="['chart-option', { 'is-selected': modelValue === 'serviceModule' }]"
            @click="selectType('serviceModule')"
          >
            <div class="option-icon"><AppIcon name="lightning" size="xl" /></div>
            <div class="option-content">
              <h3>服务模块图</h3>
              <p>展示服务模块之间的调用关系</p>
            </div>
            <div class="option-check">
              <AppIcon v-if="modelValue === 'serviceModule'" name="check" size="md" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { AppButton } from '../../../../components/common'
import { AppIcon } from '../../../../components/common/AppIcon'
import StepScopeSummary from './StepScopeSummary.vue'

export default {
  name: 'StepChartType',
  components: { AppButton, AppIcon, StepScopeSummary },
  props: {
    modelValue: {
      type: String,
      default: ''
    },
    // 关键修复 v36: 范围汇总 props 恢复 (用户要求保留内容区域)
    center: {
      type: Object,
      default: null
    },
    incremental: {
      type: Object,
      default: null
    },
    total: {
      type: Object,
      default: null
    }
  },
  emits: ['update:modelValue', 'next', 'prev'],
  methods: {
    selectType(type) {
      this.$emit('update:modelValue', type)
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-chart-type {
  height: 100%;
}

.chart-type-panel {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header-simple {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-body {
  flex: 1;
  padding: var(--spacing-xl);
  overflow: auto;
}

.section-title {
  font-size: var(--font-size-xxl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
  text-align: center;
}

.section-desc {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  text-align: center;
  margin-bottom: var(--spacing-xl);
}

.chart-options {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-lg);
  max-width: 800px;
  margin: 0 auto;
}

.chart-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  background: var(--color-bg-secondary);
  border: 2px solid transparent;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-normal);

  &:hover {
    border-color: var(--color-primary);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  &.is-selected {
    border-color: var(--color-primary);
    background: rgba(234, 88, 12, 0.05);
  }
}

.option-icon {
  font-size: 48px;
  flex-shrink: 0;
}

.option-content {
  flex: 1;

  h3 {
    font-size: var(--font-size-lg);
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-xs);
  }

  p {
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
  }
}

.option-check {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary);
  color: white;
  @include flex-center;
  font-size: var(--font-size-lg);
  flex-shrink: 0;
}

@include respond-to('md') {
  .panel-body {
    padding: var(--spacing-lg);
  }

  .chart-options {
    grid-template-columns: 1fr;
  }

  .option-icon {
    font-size: 36px;
  }
}

@include respond-to('sm') {
  .panel-header-simple {
    padding: var(--spacing-sm) var(--spacing-md);
  }

  .panel-body {
    padding: var(--spacing-md);
  }

  .chart-option {
    padding: var(--spacing-lg);
  }

  .option-icon {
    font-size: 32px;
  }
}
</style>
