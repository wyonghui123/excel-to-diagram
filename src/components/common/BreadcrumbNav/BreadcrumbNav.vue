<template>
  <nav class="breadcrumb-nav" :aria-label="ariaLabel">
    <ol class="breadcrumb-nav__list">
      <li
        v-for="(item, index) in visibleItems"
        :key="item.to || item.name || item.label || index"
        class="breadcrumb-nav__item"
      >
        <router-link
          v-if="item.to && index < items.length - 1"
          :to="item.to"
          class="breadcrumb-nav__link"
        >
          {{ item.label }}
        </router-link>
        <span v-else class="breadcrumb-nav__current">
          {{ item.label }}
        </span>
        <span
          v-if="index < items.length - 1"
          class="breadcrumb-nav__separator"
        >
          {{ separator }}
        </span>
      </li>
      <li v-if="hasOverflow" class="breadcrumb-nav__ellipsis">
        <button class="breadcrumb-nav__ellipsis-btn" @click="showAll = true">
          ...
        </button>
      </li>
    </ol>
  </nav>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  items: {
    type: Array,
    required: true
  },
  separator: {
    type: String,
    default: '›'
  },
  maxItems: {
    type: Number,
    default: 5
  },
  homeItem: {
    type: Object,
    default: () => ({ label: '首页', to: '/' })
  },
  ariaLabel: {
    type: String,
    default: '面包屑导航'
  }
})

const showAll = ref(false)

const visibleItems = computed(() => {
  const result = []
  
  if (props.homeItem) {
    result.push(props.homeItem)
  }
  
  if (showAll.value || props.items.length <= props.maxItems) {
    result.push(...props.items)
  } else {
    result.push(...props.items.slice(-props.maxItems + 1))
  }
  
  return result
})

const hasOverflow = computed(() => props.items.length > props.maxItems)
</script>

<style scoped>
.breadcrumb-nav {
  display: inline-flex;
  align-items: center;
}

.breadcrumb-nav__list {
  display: flex;
  align-items: center;
  gap: 2px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.breadcrumb-nav__item {
  display: flex;
  align-items: center;
  gap: 2px;
}

.breadcrumb-nav__link {
  display: inline-flex;
  align-items: center;
  padding: 2px 4px;
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #606266);
  text-decoration: none;
  border-radius: var(--el-border-radius-small, 4px);
  transition: all 0.2s;
}

.breadcrumb-nav__link:hover {
  color: var(--yonyou-orange-600, #ea580c);
  background: rgba(234, 88, 12, 0.06);
}

.breadcrumb-nav__current {
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-primary, #1d2129);
  font-weight: 500;
}

.breadcrumb-nav__separator {
  margin: 0 2px;
  color: var(--el-text-color-placeholder, #a0adbb);
  font-size: 10px;
}

.breadcrumb-nav__ellipsis {
  display: flex;
  align-items: center;
}

.breadcrumb-nav__ellipsis-btn {
  padding: 2px 4px;
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #606266);
  background: transparent;
  border: none;
  cursor: pointer;
}

.breadcrumb-nav__ellipsis-btn:hover {
  color: var(--yonyou-orange-600, #ea580c);
}
</style>
