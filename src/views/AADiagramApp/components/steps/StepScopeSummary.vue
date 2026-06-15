<template>
  <div class="step-scope-summary">
    <div class="step-scope-summary__cards">
      <!-- 中心范围 -->
      <div class="summary-card summary-card--center">
        <div class="summary-card__head">
          <span class="summary-card__title">中心范围</span>
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
