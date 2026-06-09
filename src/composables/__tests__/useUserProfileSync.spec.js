/**
 * useUserProfileSync 单元测试
 *
 * 验证用户资料变更实时同步器的行为：
 * 1. sync() 立即更新 authStore.user 的 display_name / email
 * 2. reload() 调用 authStore.loadFromCookie('refresh')
 * 3. authStore.user 不存在时 sync() 是 no-op
 *
 * @see docs/superpowers/specs/2026-06-09-user-lock-and-feedback-design.md
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// mock authStore
const mockAuthStore = {
  user: ref({
    display_name: 'Old Name',
    email: 'old@example.com',
  }),
  loadFromCookie: vi.fn().mockResolvedValue(true),
}

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => mockAuthStore,
}))

import { ref } from 'vue'
const { useUserProfileSync } = await import('@/composables/useUserProfileSync.js')

describe('useUserProfileSync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthStore.user = {
      display_name: 'Old Name',
      email: 'old@example.com',
    }
  })

  describe('sync()', () => {
    it('同步 display_name 到 authStore.user', () => {
      const { sync } = useUserProfileSync()
      sync({ display_name: 'New Name' })
      expect(mockAuthStore.user.display_name).toBe('New Name')
    })

    it('同步 email 到 authStore.user', () => {
      const { sync } = useUserProfileSync()
      sync({ email: 'new@example.com' })
      expect(mockAuthStore.user.email).toBe('new@example.com')
    })

    it('同时同步 display_name 和 email', () => {
      const { sync } = useUserProfileSync()
      sync({ display_name: 'New', email: 'n@e.com' })
      expect(mockAuthStore.user.display_name).toBe('New')
      expect(mockAuthStore.user.email).toBe('n@e.com')
    })

    it('updates 为 null 时不报错 (no-op)', () => {
      const { sync } = useUserProfileSync()
      expect(() => sync(null)).not.toThrow()
      expect(mockAuthStore.user.display_name).toBe('Old Name') // 不变
    })

    it('updates 为 undefined 时不报错', () => {
      const { sync } = useUserProfileSync()
      expect(() => sync(undefined)).not.toThrow()
    })

    it('空 updates 对象也不报错', () => {
      const { sync } = useUserProfileSync()
      expect(() => sync({})).not.toThrow()
      expect(mockAuthStore.user.display_name).toBe('Old Name') // 不变
    })

    it('authStore.user 不存在时是 no-op', () => {
      mockAuthStore.user = null
      const { sync } = useUserProfileSync()
      expect(() => sync({ display_name: 'X' })).not.toThrow()
    })

    it('只传 display_name 时 email 不变', () => {
      const { sync } = useUserProfileSync()
      sync({ display_name: 'Only Display' })
      expect(mockAuthStore.user.display_name).toBe('Only Display')
      expect(mockAuthStore.user.email).toBe('old@example.com') // email 未变
    })

    it('只传 email 时 display_name 不变', () => {
      const { sync } = useUserProfileSync()
      sync({ email: 'only@email.com' })
      expect(mockAuthStore.user.email).toBe('only@email.com')
      expect(mockAuthStore.user.display_name).toBe('Old Name') // display_name 未变
    })
  })

  describe('reload()', () => {
    it('调用 authStore.loadFromCookie 并传 "refresh" 模式', async () => {
      const { reload } = useUserProfileSync()
      mockAuthStore.loadFromCookie.mockResolvedValue(true)
      const result = await reload()
      expect(mockAuthStore.loadFromCookie).toHaveBeenCalledWith('refresh')
      expect(result).toBe(true)
    })

    it('loadFromCookie 返回 false 时 reload 也返回 false', async () => {
      const { reload } = useUserProfileSync()
      mockAuthStore.loadFromCookie.mockResolvedValue(false)
      const result = await reload()
      expect(result).toBe(false)
    })

    it('authStore.loadFromCookie 不存在时不报错', async () => {
      // 模拟旧版 authStore 没有 loadFromCookie
      const original = mockAuthStore.loadFromCookie
      delete mockAuthStore.loadFromCookie
      const { reload } = useUserProfileSync()
      const result = await reload()
      expect(result).toBe(false)
      // 恢复
      mockAuthStore.loadFromCookie = original
    })
  })
})