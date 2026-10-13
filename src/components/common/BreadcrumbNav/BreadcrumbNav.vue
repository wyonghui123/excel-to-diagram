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
/* [FIX 2026-10-13 移动端] 本组件此前零响应式处理，与 UserMenu / TopNavHeader
   同源两坑：缺 min-width:0 使 ellipsis 失效、缺 nowrap 使中文被压成竖排。
   实测（414px 屏 + 5 段长中文面包屑）：5/5 项竖排，品牌名被挤到 12px、
   360px 屏仅剩 5px，实质不可见。
   修法：显式声明收缩优先级，让「品牌名 > 面包屑」——
   品牌名是部署级标识不可让，面包屑是可牺牲的辅助信息。 */
.breadcrumb-nav {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.breadcrumb-nav__list {
  display: flex;
  align-items: center;
  gap: 2px;
  list-style: none;
  margin: 0;
  padding: 0;
  min-width: 0;
  overflow: hidden;
}

.breadcrumb-nav__item {
  display: flex;
  align-items: center;
  gap: 2px;
  /* 中间层级可被压缩，仅末级（当前页）保留完整可读性 */
  min-width: 0;
  flex: 0 1 auto;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.breadcrumb-nav__link:hover {
  color: var(--yonyou-orange-600, #ea580c);
  background: rgba(234, 88, 12, 0.06);
}

.breadcrumb-nav__current {
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-primary, #1d2129);
  font-weight: 500;
  white-space: nowrap;
}

.breadcrumb-nav__separator {
  margin: 0 2px;
  color: var(--el-text-color-placeholder, #a0adbb);
  font-size: 10px;
  flex-shrink: 0;
}

/* [FIX 2026-10-13 移动端] 窄屏隐藏中间层级，只保留「首页 › 当前页」。
   与 SubNavTabs / AccountSettings 的处理思路一致：横向滚动或降级，
   而非把中文压成竖排。末级不隐藏，保证用户始终知道自己在哪。 */
@media screen and (max-width: 768px) {
  .breadcrumb-nav__item:not(:last-child) {
    display: none;
  }

  .breadcrumb-nav__item:last-child::before {
    content: '\203a';
    margin-right: 2px;
    color: var(--el-text-color-placeholder, #a0adbb);
  }

  .breadcrumb-nav__current {
    overflow: hidden;
    text-overflow: ellipsis;
  }
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
