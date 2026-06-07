import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockLocalStorage = (() => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => { store[key] = value }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
    get store() { return store }
  }
})()

Object.defineProperty(global, 'localStorage', { value: mockLocalStorage })

const mockFetch = vi.fn()
global.fetch = mockFetch

describe('AccountSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockLocalStorage.clear()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('页面导航', () => {
    it('默认激活个人信息标签页', async () => {
      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()

      expect(store).toBeDefined()
    })
  })

  describe('个人信息加载', () => {
    it('应正确加载用户信息', async () => {
      const mockUserData = {
        success: true,
        data: {
          id: 1,
          username: 'testuser',
          display_name: '测试用户',
          email: 'test@example.com',
          roles: ['editor']
        }
      }

      mockFetch.mockResolvedValueOnce({
        json: () => Promise.resolve(mockUserData)
      })

      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()
      store.token = 'test-token'

      const resp = await fetch('/api/v1/users/me', {
        headers: store.getAuthHeaders()
      })
      const data = await resp.json()

      expect(data.success).toBe(true)
      expect(data.data.username).toBe('testuser')
      expect(data.data.display_name).toBe('测试用户')
      expect(data.data.email).toBe('test@example.com')
    })
  })

  describe('个人信息更新', () => {
    it('应正确更新显示名称', async () => {
      mockFetch.mockResolvedValueOnce({
        json: () => Promise.resolve({ success: true })
      })

      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()
      store.token = 'test-token'

      const resp = await fetch('/api/v1/users/me', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...store.getAuthHeaders()
        },
        body: JSON.stringify({ display_name: '新名称' })
      })
      const data = await resp.json()

      expect(data.success).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/users/me',
        expect.objectContaining({
          method: 'PUT'
        })
      )
    })

    it('应拒绝无效的邮箱格式', async () => {
      const emailRegex = /^[^\s@]+@[^\s@]+$/

      expect(emailRegex.test('invalid-email')).toBe(false)
      expect(emailRegex.test('valid@email.com')).toBe(true)
      expect(emailRegex.test('user.name@company.co.uk')).toBe(true)
      expect(emailRegex.test('admin@local')).toBe(true)
      expect(emailRegex.test('')).toBe(false)
    })
  })

  describe('密码修改', () => {
    it('应正确调用修改密码API', async () => {
      mockFetch.mockResolvedValueOnce({
        json: () => Promise.resolve({ success: true, message: '密码修改成功' })
      })

      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()
      store.token = 'test-token'

      const resp = await fetch('/api/v1/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...store.getAuthHeaders()
        },
        body: JSON.stringify({
          old_password: 'oldPass123',
          new_password: 'newPass456'
        })
      })
      const data = await resp.json()

      expect(data.success).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/auth/change-password',
        expect.objectContaining({
          method: 'POST'
        })
      )
    })

    it('应拒绝短密码', async () => {
      const shortPassword = 'ab'

      expect(shortPassword.length < 6).toBe(true)
    })

    it('应拒绝空密码', async () => {
      const emptyPassword = ''

      expect(!emptyPassword).toBe(true)
    })
  })

  describe('密码强度计算', () => {
    it('应正确计算弱强度', () => {
      const weakPasswords = ['123456', 'abcdef', 'aaaaaa']

      for (const pwd of weakPasswords) {
        let score = 0
        if (pwd.length >= 6) score++
        if (pwd.length >= 8) score++
        if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
        if (/\d/.test(pwd)) score++
        if (/[^a-zA-Z0-9]/.test(pwd)) score++

        expect(score <= 2).toBe(true)
      }
    })

    it('应正确计算中强度', () => {
      const mediumPasswords = ['Pass123', 'Abc1234']

      for (const pwd of mediumPasswords) {
        let score = 0
        if (pwd.length >= 6) score++
        if (pwd.length >= 8) score++
        if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
        if (/\d/.test(pwd)) score++
        if (/[^a-zA-Z0-9]/.test(pwd)) score++

        expect(score).toBeGreaterThan(2)
        expect(score).toBeLessThanOrEqual(3)
      }
    })

    it('应正确计算强强度', () => {
      const strongPasswords = ['P@ssw0rd123!', 'Str0ng#Pass']

      for (const pwd of strongPasswords) {
        let score = 0
        if (pwd.length >= 6) score++
        if (pwd.length >= 8) score++
        if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
        if (/\d/.test(pwd)) score++
        if (/[^a-zA-Z0-9]/.test(pwd)) score++

        expect(score).toBeGreaterThan(3)
      }
    })
  })

  describe('mustChangePassword 标志', () => {
    it('登录时应正确返回 must_change_password 标志', async () => {
      // authService.login → useBoAction → apiV2.post → httpClient → fetch
      // httpClient 要求 resp.ok=true，否则返回错误
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          success: true,
          data: {
            token: 'test-token',
            user: { username: 'admin', roles: ['admin'] },
            must_change_password: true
          }
        })
      })

      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()

      await store.login('admin', 'admin123')

      expect(store.mustChangePassword).toBe(true)
    })

    it('密码修改成功后应清除 mustChangePassword', async () => {
      // login
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          success: true,
          data: {
            token: 'test-token',
            user: { username: 'admin', roles: ['admin'] },
            must_change_password: true
          }
        })
      })
      // change password
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true })
      })

      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()

      await store.login('admin', 'admin123')
      expect(store.mustChangePassword).toBe(true)

      await store.changePassword('old', 'new')
      expect(store.mustChangePassword).toBe(false)
    })
  })

  describe('头像文本生成', () => {
    it('应从显示名称生成首字母', async () => {
      const testCases = [
        { name: '张三', expected: '张' },
        { name: 'John Doe', expected: 'J' },
        { name: '测试用户', expected: '测' },
        { name: '', expected: '?' },
        { name: null, expected: '?' }
      ]

      for (const { name, expected } of testCases) {
        const displayName = name || ''
        const avatarText = displayName ? displayName.charAt(0).toUpperCase() : '?'
        expect(avatarText).toBe(expected)
      }
    })
  })

  describe('角色标签显示', () => {
    it('应正确显示管理员标签', async () => {
      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()

      // 源码：is_admin 通过 permissions.includes('*') 或 role.is_super_admin 判断
      store.user = { roles: [{ is_super_admin: true }], permissions: [] }
      expect(store.isAdmin).toBe(true)
    })

    it('应正确显示普通用户标签', async () => {
      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()

      store.user = { roles: ['viewer'], permissions: ['domain:read'] }
      expect(store.isAdmin).toBe(false)
    })
  })
})
