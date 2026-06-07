<template>
  <div class="product-tree">
    <div class="tree-header">
      <div class="tree-search">
        <input
          v-model="searchQuery"
          type="text"
          class="tree-search-input"
          placeholder="搜索产品..."
        />
      </div>
    </div>

    <div class="tree-list">
      <div v-if="loading" class="tree-loading">加载中...</div>
      <div v-else-if="filteredProducts.length === 0" class="tree-empty">
        {{ searchQuery ? '无匹配产品' : '暂无产品' }}
      </div>
      <div
        v-else
        v-for="product in filteredProducts"
        :key="product.id"
        class="tree-item"
        :class="{ 'tree-item--active': selectedProduct?.id === product.id }"
        @click="$emit('select', product)"
      >
        <div class="tree-item-name" :title="product.name">{{ product.name }}</div>
        <div class="tree-item-actions">
          <button class="tree-item-btn" title="编辑" @click.stop="$emit('edit', product)">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
            </svg>
          </button>
          <button class="tree-item-btn tree-item-btn--danger" title="删除" @click.stop="$emit('delete', product)">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div class="tree-footer">
      <button class="tree-add-btn" @click="$emit('create')">
        <svg viewBox="0 0 24 24" width="16" height="16">
          <path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
        </svg>
        <span>新增产品</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  products: {
    type: Array,
    default: () => []
  },
  selectedProduct: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

defineEmits(['select', 'create', 'edit', 'delete'])

const searchQuery = ref('')

const filteredProducts = computed(() => {
  if (!searchQuery.value) return props.products
  const query = searchQuery.value.toLowerCase()
  return props.products.filter(p =>
    p.name?.toLowerCase().includes(query) ||
    p.code?.toLowerCase().includes(query)
  )
})
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.product-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tree-header {
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}

.tree-search-input {
  width: 100%;
  height: var(--input-height-md);
  padding: 0 var(--spacing-md);
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  outline: none;
  transition: var(--transition-normal);

  &::placeholder {
    color: var(--color-text-placeholder);
  }

  &:hover {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }
}

.tree-list {
  flex: 1;
  overflow-y: auto;
  @include scrollbar;
}

.tree-loading,
.tree-empty {
  @include flex-center;
  padding: var(--spacing-xxl);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-md);
}

.tree-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background var(--transition-fast);
  border-left: 3px solid transparent;

  &:hover {
    background: var(--color-bg-secondary);

    .tree-item-actions {
      opacity: 1;
    }
  }

  &--active {
    background: var(--color-selected);
    border-left-color: var(--color-primary);

    .tree-item-name {
      color: var(--color-primary);
      font-weight: var(--font-weight-medium);
    }
  }
}

.tree-item-name {
  flex: 1;
  @include text-ellipsis;
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
}

.tree-item-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.tree-item-btn {
  @include flex-center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--transition-fast);

  &:hover {
    background: var(--color-bg-tertiary);
    color: var(--color-text-secondary);
  }

  &--danger:hover {
    background: var(--color-error-bg);
    color: var(--color-error);
  }
}

.tree-footer {
  padding: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}

.tree-add-btn {
  @include button-primary;
  width: 100%;
}
</style>
