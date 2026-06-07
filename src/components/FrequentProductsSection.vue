<template>
  <div class="frequent-products-section">
    <div class="section-header">
      <span class="section-title">常用产品版本</span>
      <span class="section-hint">点击快速进入架构数据管理</span>
    </div>

    <div v-if="loading" class="section-loading">
      <span class="loading-spinner"></span>
    </div>

    <div v-else-if="items.length === 0" class="section-empty">
      暂无常用产品版本，请先访问架构数据管理
    </div>

    <div v-else class="product-list">
      <div
        v-for="item in items"
        :key="`${item.productId}-${item.versionId}`"
        class="product-item"
        @click="handleOpen(item)"
      >
        <div class="product-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
        </div>
        <div class="product-info">
          <span class="product-name">{{ item.productName }}</span>
          <span class="version-name">{{ item.versionName }}</span>
        </div>
        <button class="enter-btn" @click.stop="handleOpen(item)">进入</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  items: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['open-with-version'])

const handleOpen = (item) => {
  emit('open-with-version', {
    productId: item.productId,
    versionId: item.versionId
  })
}
</script>

<style lang="scss" scoped>
@import '../styles/mixins.scss';

.frequent-products-section {
  background: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-secondary);
  padding: var(--spacing-lg);
}

.section-header {
  @include flex-between;
  margin-bottom: var(--spacing-md);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.section-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.section-loading {
  @include flex-center;
  padding: var(--spacing-xl) 0;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.section-empty {
  @include flex-center;
  padding: var(--spacing-xl) 0;
  font-size: var(--font-size-md);
  color: var(--color-text-tertiary);
}

.product-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.product-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: background var(--transition-normal);

  &:hover {
    background: var(--color-bg-tertiary);
  }
}

.product-icon {
  @include flex-center;
  width: 36px;
  height: 36px;
  background: var(--color-bg-base);
  border-radius: var(--radius-lg);
  flex-shrink: 0;
  color: var(--color-text-secondary);
}

.product-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.product-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  @include text-ellipsis;
}

.version-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  @include text-ellipsis;
}

.enter-btn {
  @include button-secondary;
  font-size: var(--font-size-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  flex-shrink: 0;
}
</style>
