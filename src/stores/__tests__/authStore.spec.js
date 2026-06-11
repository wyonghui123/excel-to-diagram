import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// vi.hoisted 让 mock 函数引用在 import 之前就创建（避免 isolate:false 下的链断）
const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  getCurrentUser: vi.fn(),
  changePassword: vi.fn(),
  updateProfile: vi.fn()
}))

vi.mock('@/services/authService', () => ({
  login: mocks.login,
  logout: mocks.logout,
  getCurrentUser: mocks.getCurrentUser,
  changePassword: mocks.changePassword,
  updateProfile: mocks.updateProfile
}))

import { useAuthStore } from '@/stores/authStore'

describe('authStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('login', () => {
    it('should login successfully with valid credentials', async () => {
      const mockUser = {
        user_id: 1,
        username: 'admin',
        display_name: 'Admin',
        email: 'admin@example.com',
        roles: ['admin'],
        permissions: ['*']
      }
      mocks.login.mockResolvedValueOnce({
        success: true,
        data: { user: mockUser, must_change_password: false }
      })

      const store = useAuthStore()

      const result = await store.login('admin', 'admin123')

      expect(result).toBe(true)
      expect(store.isLoggedIn).toBe(true)
      expect(store.user).toEqual(mockUser)
      expect(mocks.login).toHaveBeenCalledWith('admin', 'admin123')
    })

    it('should fail login with invalid credentials', async () => {
      mocks.login.mockResolvedValueOnce({
        success: false,
        message: '用户名或密码错误'
      })

      const store = useAuthStore()

      const result = await store.login('admin', 'wrong')

      expect(result).toBe(false)
      expect(store.isLoggedIn).toBe(false)
      expect(store.error).toBe('用户名或密码错误')
    })

    it('should handle network error', async () => {
      mocks.login.mockResolvedValueOnce({
        success: false,
        message: '网络错误，请检查服务是否启动'
      })

      const store = useAuthStore()

      const result = await store.login('admin', 'admin123')

      expect(result).toBe(false)
      expect(store.error).toBe('网络错误，请检查服务是否启动')
    })
  })

  describe('logout', () => {
    it('should clear auth state on logout', async () => {
      mocks.logout.mockResolvedValueOnce({ success: true })

      const store = useAuthStore()
      store.user = { username: 'admin' }

      await store.logout()

      expect(store.user).toBeNull()
      expect(mocks.logout).toHaveBeenCalled()
    })
  })

  describe('getAuthHeaders', () => {
    it('should return empty object (Cookie-based auth)', () => {
      const store = useAuthStore()

      const headers = store.getAuthHeaders()

      // 当前实现：Cookie 由浏览器自动携带，函数返回空对象
      expect(headers).toEqual({})
    })
  })

  describe('isAdmin', () => {
    it('should return true for super_admin role with wildcard permission', () => {
      const store = useAuthStore()
      // V1 简化 (spec-auth-object-category-v2-2026-06-10.md FR-V1-003):
      // admin 由 permissions 包含 '*' 识别, role.is_super_admin 已废弃
      store.user = {
        roles: [{ code: 'super_admin', name: '超级管理员' }],
        permissions: ['*']
      }

      expect(store.isAdmin).toBe(true)
    })

    it('should return true for wildcard permission', async () => {
      const store = useAuthStore()
      store.user = {
        roles: ['editor'],
        permissions: ['*']
      }

      expect(store.isAdmin).toBe(true)
    })

    it('should return false for non-admin', () => {
      const store = useAuthStore()
      store.user = {
        roles: ['viewer'],
        permissions: ['domain:read']
      }

      expect(store.isAdmin).toBe(false)
    })

    it('should return false when user is null', () => {
      const store = useAuthStore()
      expect(store.isAdmin).toBe(false)
    })
  })

  describe('changePassword', () => {
    it('should change password successfully', async () => {
      mocks.changePassword.mockResolvedValueOnce({
        success: true,
        message: '密码修改成功'
      })

      const store = useAuthStore()
      const result = await store.changePassword('oldPass', 'newPass')

      expect(result.success).toBe(true)
      expect(mocks.changePassword).toHaveBeenCalledWith('oldPass', 'newPass')
    })

    it('should clear mustChangePassword on success', async () => {
      mocks.changePassword.mockResolvedValueOnce({
        success: true,
        message: '密码修改成功'
      })

      const store = useAuthStore()
      store.mustChangePassword = true

      await store.changePassword('oldPass', 'newPass')

      expect(store.mustChangePassword).toBe(false)
    })
  })

  describe('loadFromCookie', () => {
    it('should restore session successfully', async () => {
      const mockUser = { user_id: 1, username: 'admin', display_name: 'Admin' }
      mocks.getCurrentUser.mockResolvedValueOnce({
        success: true,
        data: mockUser
      })

      const store = useAuthStore()
      const result = await store.loadFromCookie('restore')

      expect(result).toBe(true)
      expect(store.user).toEqual(mockUser)
      expect(store.sessionReady).toBe(true)
    })

    it('should handle session failure', async () => {
      mocks.getCurrentUser.mockResolvedValueOnce({
        success: false,
        message: 'Token expired'
      })

      const store = useAuthStore()
      const result = await store.loadFromCookie('restore')

      expect(result).toBe(false)
      expect(store.user).toBeNull()
      expect(store.sessionReady).toBe(true)
    })
  })
})
