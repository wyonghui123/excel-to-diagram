import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useAuthStore } from './authStore'  // [FR-001] 绑定用户

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
      // [v32] 应用调用方显式提供的 closable/pinned (防止 localStorage 恢复的 stale 值)
      if (tab.closable !== undefined) {
        existing.closable = tab.closable !== false
      }
      if (tab.pinned !== undefined) {
        existing.pinned = tab.pinned
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

  // [FR-003] in-memory user 变化清空 tabs
  //   场景：用户A登录(开tabs) → 登出 → 用户B登录(同浏览器)
  //   in-memory state 仍是 A 的 tabs, B 看到 A 的 tab
  //   修复: 监听 auth.user.id 变化, 变化时清空 tabs
  //   守护: oldId === undefined 时不触发 (初始化时不误清空)
  const authStore = useAuthStore()
  watch(
    () => authStore.user?.id ?? null,
    (newId, oldId) => {
      // [NFR-003] 首次 (hydrate 之前) 不清空, 避免初始化时误清空
      if (oldId === undefined) return
      if (newId === oldId) return
      // [NFR-003] 跨用户清空 (含 trace_id)
      const traceId = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID().replace(/-/g, '')
        : `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      console.debug(`[tabStore] user changed, clearing tabs: ${oldId} -> ${newId}, trace_id=${traceId}`)
      tabs.value = []
      activeTabId.value = null
    }
  )

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
    // [FR-001] 附加 _userId 字段,deserialize 时校验跨用户
    serializer: {
      serialize: (value) => {
        const auth = useAuthStore()  // pinia 自动按需 hydrate
        const tabs = value.tabs?.map((t) => ({
          ...t,
          // 动态 label 不持久化,用 staticLabel 替代 (如未设置则用当前 label)
          label: t.dynamicLabel !== false
            ? (t.staticLabel || t.label)
            : t.label
        })) || []
        return JSON.stringify({
          ...value,
          tabs,
          _userId: auth.user?.id ?? null,  // [FR-001] 绑定用户 id
        })
      },
      deserialize: (value) => {
        try {
          const parsed = JSON.parse(value)
          // [FR-002] 跨用户检测: 不匹配则清空 (防 tabs 跨用户泄漏)
          const auth = useAuthStore()
          const currentUserId = auth.user?.id ?? null
          const persistedUserId = parsed._userId ?? null
          if (persistedUserId !== null && persistedUserId !== currentUserId) {
            // [NFR-003] 输出清空日志 (含 trace_id)
            const traceId = (typeof crypto !== 'undefined' && crypto.randomUUID)
              ? crypto.randomUUID().replace(/-/g, '')
              : `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
            console.debug(`[tabStore] user mismatch, clearing tabs: persisted=${persistedUserId}, current=${currentUserId}, trace_id=${traceId}`)
            return { tabs: [], activeTabId: null }
          }
          // [FR-002] legacy 升级: _userId 为 null (老数据) → 升级为当前 user,保留 tabs
          // (向后兼容, 防止大规模用户丢 tabs)
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
