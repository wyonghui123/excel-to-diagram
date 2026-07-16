<template>
  <div class="step-scope-summary">
    <div class="step-scope-summary__cards">
      <!-- 对象范围 -->
      <div class="summary-card summary-card--center">
        <div class="summary-card__head">
          <span class="summary-card__title">对象范围</span>
          <span class="summary-card__subtitle">直接选择</span>
        </div>
        <div class="summary-card__stats" v-if="hasCenter">
          <div class="stat-item">
            <span class="stat-item__num">{{ center.domains }}</span>
            <span class="stat-item__label">领域</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num">{{ center.subDomains }}</span>
            <span class="stat-item__label">子域</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num">{{ center.serviceModules }}</span>
            <span class="stat-item__label">服务</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num">{{ center.businessObjects }}</span>
            <span class="stat-item__label">对象</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num">{{ center.objectRelations }}</span>
            <span class="stat-item__label">关系</span>
          </div>
        </div>
        <span v-else class="summary-card__empty">—</span>
      </div>

      <!-- 关系范围（增量） -->
      <div class="summary-card summary-card--incremental">
        <div class="summary-card__head">
          <span class="summary-card__title">关系范围</span>
          <span class="summary-card__subtitle">通过关系</span>
        </div>
        <div class="summary-card__stats" v-if="hasIncremental">
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--plus">+{{ incremental.domains }}</span>
            <span class="stat-item__label">域</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--plus">+{{ incremental.subDomains }}</span>
            <span class="stat-item__label">子</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--plus">+{{ incremental.serviceModules }}</span>
            <span class="stat-item__label">服</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--plus">+{{ incremental.businessObjects }}</span>
            <span class="stat-item__label">对</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--plus">+{{ incremental.objectRelations }}</span>
            <span class="stat-item__label">关系</span>
          </div>
        </div>
        <span v-else class="summary-card__empty">—</span>
      </div>

      <!-- 总数 -->
      <div class="summary-card summary-card--total">
        <div class="summary-card__head">
          <span class="summary-card__title">总数</span>
          <span class="summary-card__subtitle">中心 ∪ 关系</span>
        </div>
        <div class="summary-card__stats" v-if="hasTotal">
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--total">{{ total.domains }}</span>
            <span class="stat-item__label">领域</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--total">{{ total.subDomains }}</span>
            <span class="stat-item__label">子域</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--total">{{ total.serviceModules }}</span>
            <span class="stat-item__label">服务</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--total">{{ total.businessObjects }}</span>
            <span class="stat-item__label">对象</span>
          </div>
          <div class="stat-item">
            <span class="stat-item__num stat-item__num--total">{{ total.objectRelations }}</span>
            <span class="stat-item__label">关系</span>
          </div>
        </div>
        <span v-else class="summary-card__empty">—</span>
      </div>
    </div>
  </div>
</template>

<script>
import { ElNotification } from 'element-plus'

/**
 * [V007.50 P0 2026-07-09] 业务对象图 关系数量告警 - 提前到步骤 1
 *
 * 用户诉求: V007.49 告警在 BO 图渲染时 (步骤 2 展示页) 弹, 但用户希望
 *   在步骤 1 (StepChartType 内 StepScopeSummary 卡片) 就看到提示
 *   避免用户已经做完所有配置进 step 2 才看到警告
 *
 * 实现:
 *   - 在 StepScopeSummary 组件内 watch 监听 total.objectRelations
 *   - 超过阈值 (100) 立即弹 ElNotification (右下角)
 *   - 用 module-level _lastWarnedStep1Key 防止重复弹 (用户调整范围时)
 *   - 仅在 BO 图触发 (chartType prop, 默认 'businessObject')
 */
const RELATIONSHIP_WARN_THRESHOLD = 100
let _lastWarnedStep1Key = null  // 'above:N' or null

function warnTooManyRelationshipsStep1(count, chartType) {
  if (chartType !== 'businessObject') return
  const isAbove = count > RELATIONSHIP_WARN_THRESHOLD
  const wasAbove = _lastWarnedStep1Key !== null
  if (wasAbove && isAbove) {
    // 已在 above 状态, 数量变化不重复
    return
  }
  if (!isAbove) {
    if (wasAbove) {
      _lastWarnedStep1Key = null
    }
    return
  }
  // 第一次越过阈值 (≤100 → >100), 告警
  _lastWarnedStep1Key = `above:${count}`
  ElNotification({
    title: '业务对象图关系数量过多',
    message: `当前关系数量 ${count} 条, 超过推荐阈值 ${RELATIONSHIP_WARN_THRESHOLD} 条, 可能影响图表加载和渲染性能。建议缩小对象和关系范围, 或采用服务模块图查看整体结构。`,
    type: 'warning',
    duration: 8000,
    position: 'bottom-right',
    showClose: true,
  })
}

export default {
  name: 'StepScopeSummary',
  props: {
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
    },
    // [V007.50 P0] 图表类型 - 决定是否告警 (只 BO 图告警)
    chartType: {
      type: String,
      default: 'businessObject'
    }
  },
  computed: {
    hasCenter() {
      return this.center && this.center.businessObjects > 0
    },
    hasIncremental() {
      // 关键修复：关系范围可能仅新增关系（src/tgt 都在中心范围内），
      // 此时 businessObjects/domains/subDomains/serviceModules 都是 0，
      // 但 objectRelations > 0，因此需一并检查所有增量维度。
      if (!this.incremental) return false
      return this.incremental.businessObjects > 0
        || this.incremental.domains > 0
        || this.incremental.subDomains > 0
        || this.incremental.serviceModules > 0
        || this.incremental.objectRelations > 0
    },
    hasTotal() {
      return this.total && this.total.businessObjects > 0
    }
  },
  watch: {
    // [V007.50 P0] 监听 total.objectRelations 变化, 超阈值弹通知
    'total.objectRelations': {
      handler(newCount) {
        if (typeof newCount !== 'number') return
        warnTooManyRelationshipsStep1(newCount, this.chartType)
      },
      immediate: true
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

/* 紧凑单行布局: 3 张卡片横向并排, 高度 ~52px */
.step-scope-summary {
  width: 100%;
  margin: 0 0 var(--spacing-sm) 0;
}

.step-scope-summary__cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.summary-card {
  display: flex;
  flex-direction: column;
  padding: 6px 12px;
  background: var(--color-bg-primary);
  transition: background 0.2s ease;

  &:hover {
    background: var(--color-bg-secondary);
  }

  &--center {
    border-top: 2px solid var(--color-primary);
  }

  &--incremental {
    border-top: 2px solid var(--color-info);
  }

  &--total {
    border-top: 2px solid var(--color-text-primary);
    background: var(--color-bg-secondary);
  }
}

.summary-card__head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}

.summary-card__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.1;
}

.summary-card__subtitle {
  font-size: 10px;
  color: var(--color-text-tertiary);
  line-height: 1.1;
}

.summary-card__stats {
  display: flex;
  align-items: baseline;
  gap: 2px 8px;
  flex-wrap: wrap;
}

.stat-item {
  display: inline-flex;
  align-items: baseline;
  gap: 1px;
}

.stat-item__num {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;

  &--plus {
    color: var(--color-info);
  }

  &--total {
    color: var(--color-primary);
    font-size: 15px;
  }
}

.summary-card--center .stat-item__num {
  color: var(--color-primary);
}

.summary-card__empty {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.stat-item__label {
  font-size: 10px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

/* 响应式: 中等屏改成纵向 */
@include respond-to('md') {
  .step-scope-summary__cards {
    grid-template-columns: 1fr;
  }
}
</style>
