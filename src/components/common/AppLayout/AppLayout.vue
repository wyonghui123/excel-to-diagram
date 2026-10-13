<template>
  <AppShell
    :show-sidebar="showSidebar"
    :show-tabs="showTabs"
    :sidebar-width="sidebarVisible ? sidebarWidth : 0"
    @scrim-click="closeSidebar"
  >
    <template #header>
      <TopNavHeader
        :logo-url="logoUrl"
        :logo-alt="logoAlt"
        :logo-text="logoText"
        :breadcrumbs="breadcrumbs"
        :is-help-active="isHelpActive"
        :show-menu-button="showSidebar"
        :menu-open="sidebarVisible"
        @logo-click="handleLogoClick"
        @notification-click="$emit('notification-click')"
        @user-command="$emit('user-command', $event)"
        @ai-click="$emit('ai-click')"
        @favorites-click="$emit('favorites-click')"
        @recent-click="$emit('recent-click')"
        @help-click="handleHelpClick"
        @menu-toggle="toggleSidebar"
      />
    </template>

    <template v-if="showTabs" #tabs>
      <div class="tabs-container" ref="tabsContainerRef">
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
    // [FIX 2026-10-13] 原默认值 'ArchWorkspace' 与 TopNavHeader 的
    // 'BIP应用架构管理' 相互矛盾，且两者都与 useInstanceInfo 的兜底值重复定义。
    // 现在统一为空串，由 TopNavHeader 回落 useInstanceInfo —— 品牌名单一来源，
    // 部署改名不会漏改。
    default: ''
  },
  breadcrumbs: {
    type: Array,
    default: () => []
  },
  isHelpActive: {
    type: Boolean,
    default: false
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
  'recent-click',
  'help-click'
])

const router = useRouter()
const tabStore = useTabStore()

const sidebarVisible = ref(false)

const tabs = computed(() => tabStore.tabs)
const activeTabId = computed({
  get: () => tabStore.activeTabId,
  set: (val) => tabStore.switchTab(val)
})

// [2026-10-12 移动端] 统一的关闭入口：遮罩点击 / 点外部 / 选中菜单后都走这里
function closeSidebar() {
  if (!sidebarVisible.value) return
  sidebarVisible.value = false
  emit('sidebar-collapse', false)
}

function handleOutsideClick(e) {
  if (!sidebarVisible.value) return

  const toggleBtn = e.target.closest('.sidebar-toggle-btn')
  const sidebar = e.target.closest('.app-shell__sidebar')

  if (!toggleBtn && !sidebar) {
    closeSidebar()
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

function handleHelpClick(payload) {
  emit('help-click', payload)
}

function handleSidebarSelect(key) {
  const item = findItemByKey(props.sidebarItems, key)

  emit('sidebar-select', key)

  if (item?.to && !item.children?.length) {
    router.push(item.to)
  }

  // [2026-10-12 移动端] 移动端抽屉模式下，选中菜单后自动收起，
  // 否则菜单会一直遮挡内容区
  closeSidebar()
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
</style>
