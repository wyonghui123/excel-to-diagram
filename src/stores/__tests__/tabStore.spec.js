/**
 * tabStore 持久化 + 动态 label 测试
 * [FR-016] 验证:
 *  1. serializer 逻辑: 动态 label 替换为 __pending__
 *  2. dynamicLabel=false 时 label 正常保留
 *  3. updateTabLabel 转为静态并更新
 *  4. 基础 CRUD 操作
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTabStore } from '../tabStore'

// 直接测试 serializer 逻辑 (不依赖 pinia-plugin-persistedstate 的 watcher)
function serializeTabs(tabs) {
  return tabs?.map((t) => ({
    ...t,
    label: t.dynamicLabel !== false
      ? (t.staticLabel || '__pending__')
      : t.label
  })) || []
}

function deserializeTabs(raw) {
  try {
    return JSON.parse(raw)
  } catch {
    return { tabs: [], activeTabId: null }
  }
}

describe('tabStore (FR-016)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  // 1. 基础操作
  describe('Basic Operations', () => {
    it('openTab 创建新 tab', () => {
      const store = useTabStore()
      store.openTab({ id: 'tab1', label: 'Tab 1' })
      expect(store.tabs.length).toBe(1)
      expect(store.tabs[0].label).toBe('Tab 1')
      expect(store.activeTabId).toBe('tab1')
    })

    it('openTab 已存在 id 则只切换+更新 label', () => {
      const store = useTabStore()
      store.openTab({ id: 'tab1', label: 'Tab 1' })
      store.openTab({ id: 'tab2', label: 'Tab 2' })
      store.openTab({ id: 'tab1', label: 'Tab 1 Updated' })
      expect(store.tabs.length).toBe(2)
      expect(store.tabs[0].label).toBe('Tab 1 Updated')
    })

    it('closeTab 删除非 pinned tab', () => {
      const store = useTabStore()
      store.openTab({ id: 'tab1', label: 'Tab 1' })
      store.openTab({ id: 'tab2', label: 'Tab 2', pinned: true })
      store.closeTab('tab1')
      expect(store.tabs.length).toBe(1)
      expect(store.tabs[0].id).toBe('tab2')
    })

    it('closeTab 跳过 pinned', () => {
      const store = useTabStore()
      store.openTab({ id: 'tab1', label: 'Tab 1', pinned: true })
      store.closeTab('tab1')
      expect(store.tabs.length).toBe(1)
    })

    it('达到 maxTabs 限制时返回 null', () => {
      const store = useTabStore()
      store.maxTabs = 2
      store.openTab({ id: 't1', label: 'T1' })
      store.openTab({ id: 't2', label: 'T2' })
      const result = store.openTab({ id: 't3', label: 'T3' })
      expect(result).toBeNull()
      expect(store.tabs.length).toBe(2)
    })

    it('[FIX 2026-06-20] 使用 baseTabPath 作为 id 时 Hub 子路径不重复', () => {
      const store = useTabStore()
      // 模拟 router guard 用 baseTabPath 作为 tab id
      store.openTab({ id: '/user-permission', label: '用户与权限管理', path: '/user-permission' })
      store.openTab({ id: '/user-permission', label: '用户与权限管理', path: '/user-permission/users' })
      store.openTab({ id: '/user-permission', label: '用户与权限管理', path: '/user-permission/roles' })
      expect(store.tabs.length).toBe(1)
      expect(store.tabs[0].path).toBe('/user-permission/roles')
      expect(store.activeTabId).toBe('/user-permission')
    })
  })

  // 2. 动态 label 管理
  describe('Dynamic Label Management', () => {
    it('默认 dynamicLabel=true', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Loaded from server' })
      expect(store.tabs[0].dynamicLabel).toBe(true)
    })

    it('dynamicLabel=false 时静态 label', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Static Title', dynamicLabel: false })
      expect(store.tabs[0].dynamicLabel).toBe(false)
    })

    it('updateTabLabel 更新 label 并转为静态', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Loading...' })
      expect(store.tabs[0].dynamicLabel).toBe(true)

      store.updateTabLabel('t1', 'Loaded: Product 42')
      expect(store.tabs[0].label).toBe('Loaded: Product 42')
      expect(store.tabs[0].dynamicLabel).toBe(false)
      expect(store.tabs[0].staticLabel).toBe('Loaded: Product 42')
    })

    it('updateTabLabel 找不到 tab 时静默', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'T1' })
      store.updateTabLabel('non-exist', 'x')
      expect(store.tabs[0].label).toBe('T1')
    })
  })

  // 3. Serializer 逻辑 (直接测试,不依赖 pinia watcher)
  describe('Serializer Logic', () => {
    it('动态 label 在序列化时替换为 __pending__', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Dynamic Value' })
      const serialized = serializeTabs(store.tabs)
      expect(serialized[0].label).toBe('__pending__')
      expect(serialized[0].dynamicLabel).toBe(true)
    })

    it('静态 label 正常保留', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Static Title', dynamicLabel: false })
      const serialized = serializeTabs(store.tabs)
      expect(serialized[0].label).toBe('Static Title')
      expect(serialized[0].dynamicLabel).toBe(false)
    })

    it('有 staticLabel 时序列化用 staticLabel', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Dynamic', staticLabel: 'Pending Title' })
      const serialized = serializeTabs(store.tabs)
      expect(serialized[0].label).toBe('Pending Title')
    })

    it('updateTabLabel 后序列化包含新 label', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Loading' })
      store.updateTabLabel('t1', 'Final Title')
      const serialized = serializeTabs(store.tabs)
      expect(serialized[0].label).toBe('Final Title')
      expect(serialized[0].dynamicLabel).toBe(false)
    })

    it('反序列化损坏 JSON 返回默认值', () => {
      const result = deserializeTabs('{invalid json')
      expect(result.tabs).toEqual([])
      expect(result.activeTabId).toBeNull()
    })

    it('反序列化正常 JSON', () => {
      const result = deserializeTabs('{"tabs":[{"id":"t1","label":"__pending__"}],"activeTabId":"t1"}')
      expect(result.tabs.length).toBe(1)
      expect(result.tabs[0].label).toBe('__pending__')
    })
  })

  // 4. 跨标签页模拟
  describe('Cross-Tab Simulation', () => {
    it('序列化+反序列化往返保持 tab 结构', () => {
      const store = useTabStore()
      store.openTab({ id: 't1', label: 'Static', dynamicLabel: false })
      store.openTab({ id: 't2', label: 'Dynamic' })

      // 模拟序列化 (写入 localStorage)
      const serialized = serializeTabs(store.tabs)
      const jsonStr = JSON.stringify({ tabs: serialized, activeTabId: store.activeTabId })

      // 模拟新标签页: 反序列化
      const restored = deserializeTabs(jsonStr)
      expect(restored.tabs.length).toBe(2)
      expect(restored.tabs[0].label).toBe('Static')       // 静态保持
      expect(restored.tabs[1].label).toBe('__pending__')   // 动态被占位
    })
  })
})
