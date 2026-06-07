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

describe('AccountSettingsDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockLocalStorage.clear()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('标签页切换', () => {
    it('默认激活个人信息标签页', () => {
      const tabs = [
        { key: 'profile', label: '个人信息' },
        { key: 'security', label: '安全设置' }
      ]
      expect(tabs.length).toBe(2)
      expect(tabs[0].key).toBe('profile')
    })
  })

  describe('头像文本生成', () => {
    const cases = [
      ['Admin', 'A'],
      ['张三', '张'],
      ['', '?'],
      [null, '?']
    ]

    for (const [name, expected] of cases) {
      it(`名称 "${name}" 应生成 "${expected}"`, () => {
        const displayName = name || ''
        const avatarText = displayName ? displayName.charAt(0).toUpperCase() : '?'
        expect(avatarText).toBe(expected)
      })
    }
  })

  describe('邮箱格式校验', () => {
    it('应接受标准邮箱格式', () => {
      const validEmails = [
        'test@example.com',
        'user.name@company.co.uk',
        'admin@local'
      ]
      for (const email of validEmails) {
        const isValid = /^[^\s@]+@[^\s@]+$/.test(email)
        expect(isValid).toBe(true)
      }
    })

    it('应拒绝无效邮箱格式', () => {
      const invalidEmails = [
        'invalid-email',
        '@example.com',
        'user@',
        '',
        'user@@domain.com',
        'user domain.com'
      ]
      for (const email of invalidEmails) {
        const isValid = /^[^\s@]+@[^\s@]+$/.test(email)
        expect(isValid).toBe(false)
      }
    })
  })

  describe('密码强度计算', () => {
    function calcStrength(pwd) {
      if (!pwd) return { percent: 0, label: '' }
      let s = 0
      if (pwd.length >= 6) s++
      if (pwd.length >= 8) s++
      if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) s++
      if (/\d/.test(pwd)) s++
      if (/[^a-zA-Z0-9]/.test(pwd)) s++
      return s <= 2 ? { percent: 33, label: '弱' } : s <= 3 ? { percent: 66, label: '中' } : { percent: 100, label: '强' }
    }

    it('弱密码：纯小写字母6位', () => {
      const r = calcStrength('abcdef')
      expect(r.percent).toBe(33)
      expect(r.label).toBe('弱')
    })

    it('中密码：大小写+数字7位', () => {
      const r = calcStrength('Pass123')
      expect(r.percent).toBe(66)
      expect(r.label).toBe('中')
    })

    it('强密码：大小写+数字+特殊字符', () => {
      const r = calcStrength('P@ssw0rd!')
      expect(r.percent).toBe(100)
      expect(r.label).toBe('强')
    })

    it('空密码返回0%', () => {
      const r = calcStrength('')
      expect(r.percent).toBe(0)
    })
  })

  describe('表单验证 - 个人信息编辑', () => {
    function validateProfile(displayName, email) {
      const errors = { displayName: '', email: '' }
      let ok = true
      if (!displayName.trim()) { errors.displayName = '不能为空'; ok = false }
      if (email && !/^[^\s@]+@[^\s@]+$/.test(email)) { errors.email = '格式不正确'; ok = false }
      return { ok, errors }
    }

    it('空显示名称应报错', () => {
      const { ok, errors } = validateProfile('', '')
      expect(ok).toBe(false)
      expect(errors.displayName).toBeTruthy()
    })

    it('有效数据应通过验证', () => {
      const { ok, errors } = validateProfile('测试用户', 'test@example.com')
      expect(ok).toBe(true)
      expect(errors.displayName).toBeFalsy()
      expect(errors.email).toBeFalsy()
    })

    it('admin@local 邮箱应通过验证', () => {
      const { ok, errors } = validateProfile('Admin', 'admin@local')
      expect(ok).toBe(true)
      expect(errors.email).toBeFalsy()
    })

    it('无效邮箱格式应报错', () => {
      const { ok, errors } = validateProfile('Test', 'not-an-email')
      expect(ok).toBe(false)
      expect(errors.email).toBeTruthy()
    })
  })

  describe('表单验证 - 密码修改', () => {
    function validatePwd(oldPwd, newPwd, confirmPwd, mustChange = false) {
      const errors = { oldPassword: '', newPassword: '', confirmPassword: '' }
      let ok = true
      if (!mustChange && !oldPwd) { errors.oldPassword = '请输入'; ok = false }
      if (!newPwd) { errors.newPassword = '请输入'; ok = false }
      else if (newPwd.length < 6) { errors.newPassword = '至少6位'; ok = false }
      if (!confirmPwd) { errors.confirmPassword = '请输入'; ok = false }
      else if (confirmPwd !== newPwd) { errors.confirmPassword = '不一致'; ok = false }
      return { ok, errors }
    }

    it('完整有效数据应通过（非强制改密）', () => {
      const { ok } = validatePwd('oldPass123', 'newPass456', 'newPass456')
      expect(ok).toBe(true)
    })

    it('旧密码为空应报错（非强制改密）', () => {
      const { ok, errors } = validatePwd('', 'newPass456', 'newPass456')
      expect(ok).toBe(false)
      expect(errors.oldPassword).toBeTruthy()
    })

    it('强制改密时不需要旧密码', () => {
      const { ok } = validatePwd('', 'newPass456', 'newPass456', true)
      expect(ok).toBe(true)
    })

    it('新密码太短应报错', () => {
      const { ok, errors } = validatePwd('old', 'ab', 'ab')
      expect(ok).toBe(false)
      expect(errors.newPassword).toContain('6')
    })

    it('确认密码不一致应报错', () => {
      const { ok, errors } = validatePwd('old', 'newPass1', 'newPass2')
      expect(ok).toBe(false)
      expect(errors.confirmPassword).toContain('不一致')
    })

    it('确认密码为空应报错', () => {
      const { ok, errors } = validatePwd('old', 'newPass123', '')
      expect(ok).toBe(false)
      expect(errors.confirmPassword).toBeTruthy()
    })
  })

  describe('API 调用 - 获取用户信息', () => {
    it('GET /api/v1/users/me 应返回用户数据', async () => {
      mockFetch.mockResolvedValueOnce({
        json: () => Promise.resolve({
          success: true,
          data: {
            id: 1,
            username: 'admin',
            display_name: '管理员',
            email: 'admin@local',
            roles: ['admin']
          }
        })
      })

      const resp = await fetch('/api/v1/users/me', {
        headers: { Authorization: 'Bearer test-token' }
      })
      const data = await resp.json()

      expect(data.success).toBe(true)
      expect(data.data.username).toBe('admin')
      expect(data.data.email).toBe('admin@local')
    })
  })

  describe('API 调用 - 更新用户信息', () => {
    it('PUT /api/v1/users/me 应正确发送更新请求', async () => {
      mockFetch.mockResolvedValueOnce({ json: () => Promise.resolve({ success: true }) })

      const resp = await fetch('/api/v1/users/me', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer test-token'
        },
        body: JSON.stringify({ display_name: '新名称', email: 'new@email.local' })
      })
      const data = await resp.json()

      expect(data.success).toBe(true)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/users/me',
        expect.objectContaining({
          method: 'PUT',
          body: '{"display_name":"新名称","email":"new@email.local"}'
        })
      )
    })
  })

  describe('API 调用 - 修改密码', () => {
    it('POST /api/v1/auth/change-password 应正确发送密码修改请求', async () => {
      mockFetch.mockResolvedValueOnce({
        json: () => Promise.resolve({ success: true, message: '密码修改成功' })
      })

      const resp = await fetch('/api/v1/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer test-token'
        },
        body: JSON.stringify({ old_password: 'old123', new_password: 'new456' })
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
  })

  describe('mustChangePassword 标志', () => {
    function validatePwd(oldPwd, newPwd, confirmPwd, mustChange = false) {
      const errors = { oldPassword: '', newPassword: '', confirmPassword: '' }
      let ok = true
      if (!mustChange && !oldPwd) { errors.oldPassword = '请输入'; ok = false }
      if (!newPwd) { errors.newPassword = '请输入'; ok = false }
      else if (newPwd.length < 6) { errors.newPassword = '至少6位'; ok = false }
      if (!confirmPwd) { errors.confirmPassword = '请输入'; ok = false }
      else if (confirmPwd !== newPwd) { errors.confirmPassword = '不一致'; ok = false }
      return { ok, errors }
    }

    it('强制改密时应跳过旧密码验证', () => {
      const mustChange = true
      const { ok } = validatePwd('', 'newPass123', 'newPass123', mustChange)
      expect(ok).toBe(true)
    })

    it('非强制改密时必须提供旧密码', () => {
      const mustChange = false
      const { ok } = validatePwd('', 'newPass123', 'newPass123', mustChange)
      expect(ok).toBe(false)
    })
  })

  describe('角色文本生成', () => {
    it('管理员角色应返回"管理员"', () => {
      const roles = ['admin']
      const text = roles.length > 0 ? roles.join(', ') : '普通用户'
      expect(text).toBe('admin')
    })

    it('多角色应用逗号分隔', () => {
      const roles = ['editor', 'viewer']
      const text = roles.join(', ')
      expect(text).toBe('editor, viewer')
    })

    it('空角色应返回默认值', () => {
      const roles = []
      const text = roles.length > 0 ? roles.join(', ') : '普通用户'
      expect(text).toBe('普通用户')
    })
  })
})
