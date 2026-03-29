<template>
  <div class="stats-display">
    <div
      v-for="stat in stats"
      :key="stat.key"
      class="stat-item"
    >
      <span class="stat-value">{{ stat.current }}/{{ stat.total }}</span>
      <span class="stat-label">{{ stat.label }}</span>
    </div>
  </div>
</template>

<script>
export default {
  name: 'StatsDisplay',
  props: {
    stats: {
      type: Array,
      required: true,
      validator: (stats) => stats.every(stat => 
        stat.key && stat.label && typeof stat.current === 'number' && typeof stat.total === 'number'
      )
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.stats-display {
  display: flex;
  gap: var(--spacing-lg);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
}

.stat-value {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--color-primary);
}

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

// 响应式
@include respond-to('md') {
  .stats-display {
    gap: var(--spacing-md);
  }

  .stat-value {
    font-size: var(--font-size-lg);
  }
}

@include respond-to('sm') {
  .stats-display {
    gap: var(--spacing-sm);
  }

  .stat-value {
    font-size: var(--font-size-md);
  }

  .stat-label {
    font-size: 10px;
  }
}
</style>
