/**
 * 测试 tabStore localStorage → sessionStorage 数据迁移 (FR-014 + TR-001)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

describe('migrateTabStoreLocalToSession (FR-014)', () => {
  let mockLocalStorage
  let mockSessionStorage

  beforeEach(() => {
    vi.resetModules()
    mockLocalStorage = {
      store: {},
      getItem(key) { return this.store[key] || null },
      setItem(key, val) { this.store[key] = val },
      removeItem(key) { delete this.store[key] },
      clear() { this.store = {} },
    }
    mockSessionStorage = {
      store: {},
      getItem(key) { return this.store[key] || null },
      setItem(key, val) { this.store[key] = val },
      removeItem(key) { delete this.store[key] },
      clear() { this.store = {} },
    }
    global.window = {
      localStorage: mockLocalStorage,
      sessionStorage: mockSessionStorage,
    }
  })

  afterEach(() => {
    delete global.window
    vi.restoreAllMocks()
  })

  it('localStorage 有数据，sessionStorage 无数据 → 迁移', async () => {
    const oldData = JSON.stringify({ tabs: [{ id: 1 }], activeTabId: 1 })
    mockLocalStorage.setItem('tab-store', oldData)

    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const result = migrateTabStoreLocalToSession()

    expect(result.migrated).toBe(true)
    expect(mockSessionStorage.getItem('tab-store')).toBe(oldData)
    expect(mockLocalStorage.getItem('tab-store')).toBeNull()
  })

  it('两处都有数据 → 清旧保新（避免冲突）', async () => {
    mockLocalStorage.setItem('tab-store', 'OLD_DATA')
    mockSessionStorage.setItem('tab-store', 'NEW_DATA')

    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const result = migrateTabStoreLocalToSession()

    expect(result.migrated).toBe(true)
    expect(mockSessionStorage.getItem('tab-store')).toBe('NEW_DATA')  // 保留
    expect(mockLocalStorage.getItem('tab-store')).toBeNull()         // 清除
  })

  it('仅 sessionStorage 有数据 → 无需迁移', async () => {
    mockSessionStorage.setItem('tab-store', 'SESSION_ONLY')

    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const result = migrateTabStoreLocalToSession()

    expect(result.migrated).toBe(false)
    expect(result.reason).toBe('session-only')
  })

  it('两处都无数据 → 无需迁移', async () => {
    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const result = migrateTabStoreLocalToSession()

    expect(result.migrated).toBe(false)
    expect(result.reason).toBe('no-data')
  })

  it('幂等：第二次调用应返回 already=true 不重复执行', async () => {
    mockLocalStorage.setItem('tab-store', 'DATA')

    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const first = migrateTabStoreLocalToSession()
    const second = migrateTabStoreLocalToSession()

    expect(first.migrated).toBe(true)
    expect(second.migrated).toBe(true)
    expect(second.already).toBe(true)
  })

  it('错误情况（如 localStorage 访问异常）不抛错', async () => {
    // 模拟 localStorage 抛错
    global.window.localStorage = {
      getItem() { throw new Error('SecurityError') },
      setItem() { throw new Error('SecurityError') },
      removeItem() { throw new Error('SecurityError') },
    }

    const { migrateTabStoreLocalToSession } = await import('@/stores/migration/tabStoreLocalToSession')
    const result = migrateTabStoreLocalToSession()

    expect(result.migrated).toBe(false)
    expect(result.reason).toBe('error')
  })
})
