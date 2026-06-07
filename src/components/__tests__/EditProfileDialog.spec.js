import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import EditProfileDialog from '@/components/EditProfileDialog.vue'

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    user: { username: 'testuser' },
    userDisplayName: 'Test User',
    getAuthHeaders: () => ({ 'Authorization': 'Bearer test-token' })
  })
}))

vi.mock('@/composables/useMessage', () => ({
  useMessage: () => ({
    success: vi.fn(),
    error: vi.fn()
  })
}))

const mockFetch = vi.fn()
global.fetch = mockFetch

describe('EditProfileDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('基本渲染', () => {
    it('应该渲染对话框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('.dialog-overlay').exists()).toBe(true)
      expect(wrapper.find('.dialog-card').exists()).toBe(true)
    })

    it('应该显示标题",个人信息"', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('.dialog-header h3').text()).toBe('个人信息')
    })

    it('应该显示关闭按钮', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('.close-btn').exists()).toBe(true)
    })

    it('应该显示头像', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('.avatar').exists()).toBe(true)
    })

    it('应该显示用户名输入框（禁用状态）', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      const usernameInput = wrapper.find('input[placeholder="请输入用户名"]')
      expect(usernameInput.exists()).toBe(true)
      expect(usernameInput.attributes('disabled')).toBeDefined()
    })

    it('应该显示显示名称输入框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      const displayNameInput = wrapper.find('input[placeholder="请输入显示名称"]')
      expect(displayNameInput.exists()).toBe(true)
    })

    it('应该显示邮箱输入框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      const emailInput = wrapper.find('input[type="email"]')
      expect(emailInput.exists()).toBe(true)
    })

    it('不应该显示手机号码输入框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('input[placeholder="请输入手机号码"]').exists()).toBe(false)
    })

    it('不应该显示部门输入框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('input[placeholder="请输入部门"]').exists()).toBe(false)
    })

    it('不应该显示职位输入框', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('input[placeholder="请输入职位"]').exists()).toBe(false)
    })

    it('应该显示取消和保存按钮', () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })
      expect(wrapper.find('.btn-secondary').text()).toBe('取消')
      expect(wrapper.find('.btn-primary').text()).toBe('保存')
    })
  })

  describe('数据加载', () => {
    it('加载完成后应该填充表单数据', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            username: 'testuser',
            display_name: 'Test User',
            email: 'test@example.com'
          }
        })
      })

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const displayNameInput = wrapper.find('input[placeholder="请输入显示名称"]')
      expect(displayNameInput.element.value).toBe('Test User')

      const emailInput = wrapper.find('input[type="email"]')
      expect(emailInput.element.value).toBe('test@example.com')
    })

    it('API 调用失败时应该显示错误', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'))

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      expect(wrapper.find('.error-msg').exists()).toBe(false)
    })
  })

  describe('表单验证', () => {
    it('显示名称为空时应该显示错误', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            username: 'testuser',
            display_name: '',
            email: 'test@example.com'
          }
        })
      })

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const displayNameInput = wrapper.find('input[placeholder="请输入显示名称"]')
      await displayNameInput.setValue('')
      await wrapper.find('.btn-primary').trigger('click')

      expect(wrapper.find('.error-msg').text()).toBe('显示名称不能为空')
    })

    it('邮箱格式错误时应该显示错误', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            username: 'testuser',
            display_name: 'Test User',
            email: ''
          }
        })
      })

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const emailInput = wrapper.find('input[type="email"]')
      await emailInput.setValue('invalid-email')
      await wrapper.find('.btn-primary').trigger('click')

      expect(wrapper.find('.error-msg').text()).toBe('请输入有效的电子邮件地址')
    })
  })

  describe('表单提交', () => {
    it('提交成功时应该调用保存 API', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            username: 'testuser',
            display_name: 'Test User',
            email: 'test@example.com'
          }
        })
      })

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const displayNameInput = wrapper.find('input[placeholder="请输入显示名称"]')
      await displayNameInput.setValue('New Name')
      await wrapper.find('.btn-primary').trigger('click')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/users/me',
        expect.objectContaining({
          method: 'PUT',
          body: expect.stringContaining('display_name')
        })
      )
    })

    it('提交中时按钮应该显示加载状态', async () => {
      mockFetch.mockImplementation(() => new Promise(() => {}))

      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            username: 'testuser',
            display_name: 'Test User',
            email: 'test@example.com'
          }
        })
      })

      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      wrapper.find('.btn-primary').trigger('click')

      await nextTick()

      const submitBtn = wrapper.find('.btn-primary')
      expect(submitBtn.attributes('disabled')).toBeDefined()
      expect(submitBtn.text()).toBe('保存中...')
    })
  })

  describe('关闭行为', () => {
    it('点击关闭按钮应该触发 close 事件', async () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await wrapper.find('.close-btn').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })

    it('点击遮罩应该触发 close 事件', async () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await wrapper.find('.dialog-overlay').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })

    it('点击取消按钮应该触发 close 事件', async () => {
      const wrapper = mount(EditProfileDialog, {
        global: { stubs: { teleport: true } }
      })

      await wrapper.find('.btn-secondary').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })
  })
})
