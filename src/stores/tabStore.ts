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
  /**
   * [FR-016] 静态 label (来自路由元数据或业务静态名称)
   *  - 持久化时优先用 staticLabel
   *  - 动态 label (来自后端数据) 不持久化,在还原时由业务重新计算
   */
  staticLabel?: string
  /**
   * [FR-016] 标记 label 是否动态 (默认 true)
   *  - true: label 由后端/业务动态生成,持久化时丢弃
   *  - false: label 来自路由 meta.title 等静态来源,可安全持久化
   */
  dynamicLabel?: boolean
}

export const useTabStore = defineStore('tab', () => {
  const tabs = ref<Tab[]>([])
  const activeTabId = ref<string | null>(null)
  const maxTabs = ref(10)

  function openTab(tab: Omit<Tab, 'id'> & { id?: string }) {
    const tabId = tab.id || tab.path || String(Date.now())

    const existing = tabs.value.find(t => t.id === tabId)
    if (existing) {
      // [FR-016] 只在 dynamicLabel=true 时更新 label
      //   dynamicLabel=false 表示 label 已被业务页设置为具体值，不应被路由覆盖
      if (existing.dynamicLabel !== false && existing.label !== tab.label) {
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
      meta: tab.meta,
      // [FR-016] 标记 label 是否动态
      //   业务层调用 openTab({ dynamicLabel: false }) 表示静态 label
      staticLabel: tab.staticLabel,
      dynamicLabel: tab.dynamicLabel !== false  // 默认为 true
    }

    tabs.value.push(newTab)
    activeTabId.value = tabId

    return newTab
  }

  /**
   * [FR-016] 更新 tab 的动态 label
   *  - 当业务计算出新 label 时调用
   *  - 如果 tab 处于 dynamicLabel 状态,会更新 label
   */
  function updateTabLabel(tabId: string, newLabel: string) {
    const tab = tabs.value.find(t => t.id === tabId)
    if (!tab) return
    tab.label = newLabel
    // 转为静态 (避免下次还原时被清空)
    if (tab.dynamicLabel) {
      tab.staticLabel = newLabel
      tab.dynamicLabel = false
    }
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
    updateTabLabel,
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
  // [FR-016] 改用 localStorage 跨标签页共享 + 动态 label 过滤
  persist: {
    key: 'tab-store',
    storage: localStorage,  // [FR-016] 从 sessionStorage → localStorage
    pick: ['tabs', 'activeTabId'],
    // [FR-016] 自定义序列化: 动态 label 在序列化时用 staticLabel 替代
    serializer: {
      serialize: (value) => {
        const tabs = value.tabs?.map((t) => ({
          ...t,
          // 动态 label 不持久化,用 staticLabel 替代 (如未设置则用当前 label)
          label: t.dynamicLabel !== false
            ? (t.staticLabel || t.label)
            : t.label
        })) || []
        return JSON.stringify({ ...value, tabs })
      },
      deserialize: (value) => {
        try {
          const parsed = JSON.parse(value)
          // 清理历史残留的 __pending__ 标记
          if (parsed.tabs) {
            parsed.tabs = parsed.tabs.map((t) => {
              if (t.label === '__pending__') {
                // 优先用 staticLabel,否则标记为动态让业务层重新计算
                return { ...t, label: t.staticLabel || t.label, dynamicLabel: true }
              }
              return t
            })
          }
          return parsed
        } catch (_) {
          return { tabs: [], activeTabId: null }
        }
      }
    }
  }
})

export default useTabStore
