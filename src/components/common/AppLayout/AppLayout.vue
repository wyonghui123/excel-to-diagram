<template>
  <AppShell :show-sidebar="showSidebar" :show-tabs="showTabs" :sidebar-width="sidebarVisible ? sidebarWidth : 0">
    <template #header>
      <TopNavHeader
        :logo-url="logoUrl"
        :logo-alt="logoAlt"
        :logo-text="logoText"
        :breadcrumbs="breadcrumbs"
        @logo-click="handleLogoClick"
        @notification-click="$emit('notification-click')"
        @user-command="$emit('user-command', $event)"
        @ai-click="$emit('ai-click')"
        @favorites-click="$emit('favorites-click')"
        @recent-click="$emit('recent-click')"
      />
    </template>

    <template v-if="showTabs" #tabs>
      <div class="tabs-container" ref="tabsContainerRef">
        <button
          class="sidebar-toggle-btn"
          :class="{ 'is-active': sidebarVisible }"
          @click.stop="toggleSidebar"
          type="button"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path v-if="!sidebarVisible" d="M3 4H13M3 8H13M3 12H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <path v-else d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </button>
        <AppTabs
          :tabs="tabs"
          :model-value="activeTabId"
          :max-tabs="maxTabs"
          @update:model-value="handleTabChange"
          @tab-click="handleTabClick"
          @tab-close="handleTabClose"
        />
      </div>
    </template>

    <template #sidebar v-if="showSidebar">
      <AppSideNav
        v-if="sidebarItems.length > 0"
        :items="sidebarItems"
        :model-value="sidebarActive"
        @update:model-value="handleSidebarSelect"
      />
      <slot v-else name="sidebar" />
    </template>

    <slot />

    <template #footer v-if="$slots.footer">
      <slot name="footer" />
    </template>
  </AppShell>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { AppShell, TopNavHeader, AppTabs, AppSideNav } from '@/components/common'
import { useTabStore } from '@/stores/tabStore'

const appShellRef = ref(null)
const tabsContainerRef = ref(null)

const props = defineProps({
  showSidebar: {
    type: Boolean,
    default: true
  },
  showTabs: {
    type: Boolean,
    default: true
  },
  sidebarWidth: {
    type: [Number, String],
    default: 240
  },
  sidebarItems: {
    type: Array,
    default: () => []
  },
  sidebarActive: {
    type: [String, Number],
    default: ''
  },
  maxTabs: {
    type: Number,
    default: 10
  },
  logoUrl: {
    type: String,
    default: ''
  },
  logoAlt: {
    type: String,
    default: 'Logo'
  },
  logoText: {
    type: String,
    default: 'ArchWorkspace'
  },
  breadcrumbs: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'logo-click',
  'notification-click',
  'user-command',
  'tab-change',
  'tab-click',
  'tab-close',
  'sidebar-select',
  'sidebar-collapse',
  'ai-click',
  'favorites-click',
  'recent-click'
])

const router = useRouter()
const tabStore = useTabStore()

const sidebarVisible = ref(false)

const tabs = computed(() => tabStore.tabs)
const activeTabId = computed({
  get: () => tabStore.activeTabId,
  set: (val) => tabStore.switchTab(val)
})

function handleOutsideClick(e) {
  if (!sidebarVisible.value) return

  const toggleBtn = e.target.closest('.sidebar-toggle-btn')
  const sidebar = e.target.closest('.app-shell__sidebar')

  if (!toggleBtn && !sidebar) {
    sidebarVisible.value = false
    emit('sidebar-collapse', false)
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
})

function toggleSidebar() {
  sidebarVisible.value = !sidebarVisible.value
  emit('sidebar-collapse', sidebarVisible.value)
}

function handleLogoClick() {
  emit('logo-click')
}

function handleSidebarSelect(key) {
  const item = findItemByKey(props.sidebarItems, key)

  emit('sidebar-select', key)

  if (item?.to && !item.children?.length) {
    router.push(item.to)
  }

  if (sidebarVisible.value) {
    sidebarVisible.value = false
    emit('sidebar-collapse', false)
  }
}

function findItemByKey(items, key) {
  for (const item of items) {
    if (item.key === key) return item
    if (item.children) {
      const found = findItemByKey(item.children, key)
      if (found) return found
    }
  }
  return null
}

function handleTabChange(tabId) {
  tabStore.switchTab(tabId)
  const tab = tabStore.tabs.find(t => t.id === tabId)
  if (tab) {
    router.push(tab.path || tab.id)
  }
  emit('tab-change', tabId)
}

function handleTabClick(tab) {
  emit('tab-click', tab)
}

function handleTabClose(tabId) {
  const tab = tabStore.tabs.find(t => t.id === tabId)
  const sourceTabId = tab?.meta?.sourceTabId

  tabStore.closeTab(tabId)

  if (tabStore.tabs.length === 0) {
    router.push('/')
  } else {
    if (sourceTabId) {
      const sourceTab = tabStore.tabs.find(t => t.id === sourceTabId)
      if (sourceTab) {
        tabStore.switchTab(sourceTabId)
        router.push(sourceTab.path || sourceTab.id)
        emit('tab-close', tabId)
        return
      }
    }

    const activeTab = tabStore.tabs.find(t => t.id === tabStore.activeTabId)
    if (activeTab) {
      router.push(activeTab.path || activeTab.id)
    } else {
      const remaining = tabStore.tabs
      if (remaining.length > 0) {
        const lastTab = remaining[remaining.length - 1]
        router.push(lastTab.path || lastTab.id)
      } else {
        router.push('/')
      }
    }
  }
  emit('tab-close', tabId)
}
</script>

<style scoped>
.tabs-container {
  display: flex;
  align-items: center;
  flex: 1;
  height: 100%;
}

.sidebar-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  margin-right: var(--spacing-sm, 8px);
  border: none;
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 4px;
  flex-shrink: 0;
}

.sidebar-toggle-btn:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--yonyou-orange-600, #ea580c);
}

.sidebar-toggle-btn.is-active {
  background: var(--yonyou-orange-50, #fff7ed);
  color: var(--yonyou-orange-600, #ea580c);
}
</style>
