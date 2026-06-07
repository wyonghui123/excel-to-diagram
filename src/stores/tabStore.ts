import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Tab {
  id: string
  label: string
  path?: string
  icon?: string
  badge?: string | number
  closable?: boolean
  pinned?: boolean
  meta?: Record<string, any>
}

export const useTabStore = defineStore('tab', () => {
  const tabs = ref<Tab[]>([])
  const activeTabId = ref<string | null>(null)
  const maxTabs = ref(10)

  function openTab(tab: Omit<Tab, 'id'> & { id?: string }) {
    const tabId = tab.id || tab.path || String(Date.now())

    const existing = tabs.value.find(t => t.id === tabId)
    if (existing) {
      if (existing.label !== tab.label) {
        existing.label = tab.label
      }
      activeTabId.value = existing.id
      return existing
    }

    if (tabs.value.length >= maxTabs.value) {
      console.warn('Tab 数量已达上限')
      return null
    }

    const newTab: Tab = {
      id: tabId,
      label: tab.label,
      path: tab.path,
      icon: tab.icon,
      badge: tab.badge,
      closable: tab.closable !== false,
      pinned: tab.pinned || false,
      meta: tab.meta
    }

    tabs.value.push(newTab)
    activeTabId.value = tabId

    return newTab
  }

  function closeTab(tabId: string) {
    const index = tabs.value.findIndex(t => t.id === tabId)
    if (index === -1) return

    const tab = tabs.value[index]
    if (tab.pinned) return

    tabs.value.splice(index, 1)

    if (activeTabId.value === tabId) {
      const newActive = tabs.value[index] || tabs.value[index - 1]
      activeTabId.value = newActive?.id || null
    }
  }

  function switchTab(tabId: string) {
    activeTabId.value = tabId
  }

  function replaceTabId(oldId: string, newId: string, newPath?: string) {
    const tab = tabs.value.find(t => t.id === oldId)
    if (!tab) return

    tab.id = newId
    if (newPath !== undefined) {
      tab.path = newPath
    }

    if (activeTabId.value === oldId) {
      activeTabId.value = newId
    }
  }

  function pinTab(tabId: string) {
    const tab = tabs.value.find(t => t.id === tabId)
    if (tab) {
      tab.pinned = !tab.pinned
    }
  }

  function closeAllTabs() {
    tabs.value = tabs.value.filter(t => t.pinned)
    activeTabId.value = tabs.value[tabs.value.length - 1]?.id || null
  }

  function closeOtherTabs(keepTabId: string) {
    tabs.value = tabs.value.filter(t => t.pinned || t.id === keepTabId)
    if (tabs.value.find(t => t.id === activeTabId.value)?.pinned) {
      activeTabId.value = keepTabId
    }
  }

  // Getters
  const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value))
  const pinnedTabs = computed(() => tabs.value.filter(t => t.pinned))
  const closableTabs = computed(() => tabs.value.filter(t => !t.pinned))
  const hasOverflow = computed(() => tabs.value.length > 8)

  return {
    tabs,
    activeTabId,
    maxTabs,
    openTab,
    closeTab,
    switchTab,
    replaceTabId,
    pinTab,
    closeAllTabs,
    closeOtherTabs,
    activeTab,
    pinnedTabs,
    closableTabs,
    hasOverflow
  }
}, {
  // [FR-006] 升级到 v4 持久化语法 (pick 替代 paths)
  // 注意: tabStore 的 localStorage 切换属于 FR-016 (M3),此处保留 sessionStorage
  persist: {
    key: 'tab-store',
    storage: sessionStorage,
    pick: ['tabs', 'activeTabId']
  }
})

export default useTabStore
