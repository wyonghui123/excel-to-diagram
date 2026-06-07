<template>
  <div class="page-shell" :class="[`page-shell--${variant}`, { 'page-shell--with-title-bar': showTitleBar }]">
    <!-- 标题栏（可选，与 RoleDetailUserGroupDetail 一致） -->
    <div v-if="showTitleBar" class="page-shell__title-bar">
      <div class="page-shell__title-bar-left">
        <button
          v-if="showBackButton"
          class="page-shell__back-link"
          @click="handleBack"
        >
          <AppIcon name="arrow-left" size="sm" />
          <span>返回</span>
        </button>

        <span v-if="showBackButton && breadcrumbs.length > 0" class="page-shell__sep"></span>

        <!-- 面包屑（替代标题） -->
        <div v-if="breadcrumbs.length > 0" class="page-shell__breadcrumb">
          <template v-for="(crumb, index) in breadcrumbs" :key="crumb.to || crumb.label || index">
            <span
              v-if="crumb.to"
              class="page-shell__breadcrumb-item page-shell__breadcrumb-link"
              @click="handleBreadcrumbNavigate(crumb)"
            >
              {{ crumb.label }}
            </span>
            <span v-else class="page-shell__breadcrumb-item">
              {{ crumb.label }}
            </span>
            <span v-if="index < breadcrumbs.length - 1" class="page-shell__breadcrumb-sep">/</span>
          </template>
        </div>

        <!-- 主标题（替代面包屑） -->
        <span v-else-if="title" class="page-shell__title">
          {{ title }}
        </span>
      </div>

      <div class="page-shell__title-bar-right">
        <slot name="title-bar-actions" />
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="page-shell__content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { AppIcon } from '@/components/common'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  subtitle: {
    type: String,
    default: ''
  },
  breadcrumbs: {
    type: Array,
    default: () => []
  },
  showBackButton: {
    type: Boolean,
    default: true
  },
  showTitleBar: {
    type: Boolean,
    default: true
  },
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'compact', 'full'].includes(v)
  }
})

const emit = defineEmits([
  'back',
  'navigate'
])

const router = useRouter()
const tabStore = useTabStore()

function handleBack() {
  if (props.breadcrumbs.length > 1) {
    const prevCrumb = props.breadcrumbs[props.breadcrumbs.length - 2]
    if (prevCrumb?.to) {
      router.push(prevCrumb.to)
      return
    }
  }

  emit('back')

  try {
    const currentPath = router.currentRoute.value.path
    const currentTab = tabStore.tabs.find(t => t.id === currentPath)
    const sourceTabId = currentTab?.meta?.sourceTabId

    tabStore.closeTab(currentPath)

    const remaining = tabStore.tabs
    if (remaining.length > 0) {
      if (sourceTabId) {
        const sourceTab = remaining.find(t => t.id === sourceTabId)
        if (sourceTab) {
          tabStore.switchTab(sourceTabId)
          router.push(sourceTab.path || sourceTab.id)
          return
        }
      }

      const activeTab = remaining.find(t => t.id === tabStore.activeTabId)
      if (activeTab) {
        router.push(activeTab.path || activeTab.id)
      } else if (remaining.length > 0) {
        const lastTab = remaining[remaining.length - 1]
        router.push(lastTab.path || lastTab.id)
      } else {
        router.push('/')
      }
    } else {
      router.push('/')
    }
  } catch (e) {
    router.push('/')
  }
}

function handleBreadcrumbNavigate(crumb) {
  emit('navigate', crumb)
  if (crumb.to) {
    router.push(crumb.to)
  }
}
</script>

<style scoped lang="scss">
.page-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
  overflow: hidden;
}

.page-shell--with-title-bar {
  .page-shell__content {
    flex: 1;
    overflow: auto;
  }
}

.page-shell--compact {
  .page-shell__title-bar {
    padding: var(--spacing-xs) var(--spacing-md);
  }
}

.page-shell--full {
  .page-shell__content {
    padding: 0;
  }
}

.page-shell__title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  flex-shrink: 0;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-base);
}

.page-shell__title-bar-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  min-width: 0;
  flex: 1;
}

.page-shell__title-bar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

.page-shell__back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  flex-shrink: 0;
}

.page-shell__back-link:hover {
  color: var(--color-primary);
  background: var(--color-bg-tertiary);
}

.page-shell__back-link:active {
  color: var(--color-primary-hover);
}

.page-shell__sep {
  width: 1px;
  height: 14px;
  background: var(--color-border);
  flex-shrink: 0;
}

.page-shell__breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-shell__breadcrumb-item {
  color: var(--color-text-secondary);
}

.page-shell__breadcrumb-link {
  cursor: pointer;
  transition: color 0.15s ease;
}

.page-shell__breadcrumb-link:hover {
  color: var(--color-primary);
}

.page-shell__breadcrumb-sep {
  color: var(--color-text-tertiary);
}

.page-shell__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-shell__content {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-md);
}
</style>
