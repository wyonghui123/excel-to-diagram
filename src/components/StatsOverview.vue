<template>
  <div class="stats-overview">
    <h3 class="stats-title">统计概览</h3>

    <div v-if="loading" class="stats-loading">
      <div class="loading-spinner"></div>
    </div>

    <template v-else>
      <div class="stats-section">
        <div class="stats-subtitle">平台全貌</div>
        <div class="stats-grid">
          <div
            v-for="item in platformStats"
            :key="item.key"
            class="stat-card"
          >
            <div class="stat-icon" :class="`stat-icon--${item.key}`" v-html="item.svgIcon"></div>
            <div class="stat-body">
              <span class="stat-value">{{ item.value }}</span>
              <span class="stat-label">{{ item.label }}</span>
            </div>
            <div
              v-if="item.trendLabel"
              class="stat-trend"
              :class="`stat-trend--${item.trendType}`"
            >
              {{ item.trendLabel }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="scopedData" class="stats-section stats-section--scoped">
        <div class="stats-subtitle">
          我的范围
          <span class="scoped-dimensions">
            <el-tag
              v-for="label in scopedData.dimension_labels"
              :key="label"
              size="small"
              type="info"
            >{{ label }}</el-tag>
          </span>
        </div>
        <div class="stats-grid">
          <div
            v-for="item in scopedStats"
            :key="item.key"
            class="stat-card stat-card--scoped"
          >
            <div class="stat-icon" :class="`stat-icon--${item.key}`" v-html="item.svgIcon"></div>
            <div class="stat-body">
              <span class="stat-value">{{ item.value }}</span>
              <span class="stat-label">{{ item.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

import { apiV1 } from '@/utils/httpClient'

const statIcons = {
  products: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
  versions: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
  domains: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  business_objects: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>',
  relationships: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M7.5 7.5L10.5 15.5"/><path d="M16.5 7.5L13.5 15.5"/><path d="M8 6h8"/></svg>'
}

const rawData = ref({
  products: 0,
  versions: 0,
  domains: 0,
  business_objects: 0,
  relationships: 0
})

const trends = ref({})
const scopedData = ref(null)
const loading = ref(false)

const platformStats = computed(() => {
  return [
    buildStatItem('products', '产品', statIcons.products),
    buildStatItem('versions', '版本', statIcons.versions),
    buildStatItem('domains', '领域', statIcons.domains),
    buildStatItem('business_objects', '业务对象', statIcons.business_objects),
    buildStatItem('relationships', '关系', statIcons.relationships)
  ]
})

const scopedStats = computed(() => {
  if (!scopedData.value) return []
  return [
    {
      key: 'domains',
      label: '领域',
      value: scopedData.value.domains || 0,
      svgIcon: statIcons.domains
    },
    {
      key: 'business_objects',
      label: '业务对象',
      value: scopedData.value.business_objects || 0,
      svgIcon: statIcons.business_objects
    },
    {
      key: 'relationships',
      label: '关系',
      value: scopedData.value.relationships || 0,
      svgIcon: statIcons.relationships
    }
  ]
})

function buildStatItem(key, label, svgIcon) {
  const value = rawData.value[key] || 0
  const trendData = trends.value[key] || {}
  const weekCount = trendData.week || 0
  const monthCount = trendData.month || 0
  let trendLabel = ''
  let trendType = 'none'
  if (monthCount > 0 && weekCount > 0) {
    trendLabel = '+' + monthCount
    trendType = 'up'
  } else if (monthCount > 0) {
    trendLabel = '+' + monthCount
    trendType = 'up'
  }
  return { key, label, value, svgIcon, trendLabel, trendType }
}

onMounted(async () => {
  loading.value = true
  try {
    const result = await apiV1.get('/stats/overview')
    if (result.success) {
      const data = result.data || {}
      rawData.value = {
        products: data.products || 0,
        versions: data.versions || 0,
        domains: data.domains || 0,
        business_objects: data.business_objects || 0,
        relationships: data.relationships || 0
      }
      trends.value = result.data?.trends || {}
      scopedData.value = result.data?.scoped || null
    }
  } catch (e) {
  } finally {
    loading.value = false
  }
})
</script>

<style lang="scss">
@import '../styles/mixins.scss';

.stats-overview {
  background: #fff;
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-secondary);
  padding: var(--spacing-lg);
}

.stats-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-md) 0;
}

.stats-section {
  margin-bottom: var(--spacing-md);

  &:last-child {
    margin-bottom: 0;
  }
}

.stats-section--scoped {
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-secondary);
}

.stats-subtitle {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.scoped-dimensions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--spacing-md);

  .stats-section--scoped & {
    grid-template-columns: repeat(3, 1fr);
  }
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  gap: var(--spacing-xs);
  position: relative;

  &--scoped {
    background: var(--color-bg-primary);
    border: 1px dashed var(--color-border-secondary);
  }
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  @include flex-center;

  &--products {
    background: #fff7ed;
    color: #ea580c;
  }

  &--versions {
    background: #eff6ff;
    color: #2563eb;
  }

  &--domains {
    background: #f0fdf4;
    color: #16a34a;
  }

  &--business_objects {
    background: #f5f3ff;
    color: #7c3aed;
  }

  &--relationships {
    background: var(--yonyou-orange-50);
    color: var(--yonyou-orange-600);
  }
}

.stat-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-value {
  font-size: var(--font-size-xxxl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.stat-trend {
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  line-height: 1.4;

  &--up {
    color: #16a34a;
    background: #f0fdf4;
  }

  &--none {
    color: var(--color-text-quaternary);
  }
}

.stats-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: var(--spacing-lg);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border-secondary);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .stats-section--scoped .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
