/**
 * useCrudMessage 单元测试
 *
 * 验证 CRUD 操作语义化反馈封装的行为：
 * 1. 各方法生成正确的文案
 * 2. 错误信息智能提取 (err.response.data.message)
 * 3. 透传 useMessage 的 success/error/warning/info/confirm
 *
 * @see docs/superpowers/specs/2026-06-09-user-lock-and-feedback-design.md
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// mock useMessage，避免依赖 NotificationContainer
const mockUseMessage = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  confirm: vi.fn(),
  show: vi.fn(),
  remove: vi.fn(),
  clearAll: vi.fn(),
}

vi.mock('@/composables/useMessage', () => ({
  useMessage: () => mockUseMessage,
}))

// import 必须在 mock 之后
const { useCrudMessage } = await import('@/composables/useCrudMessage.js')

describe('useCrudMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('成功反馈', () => {
    it('saved() 默认文案是 "数据保存成功"', () => {
      const m = useCrudMessage()
      m.saved()
      expect(mockUseMessage.success).toHaveBeenCalledWith('数据保存成功')
    })

    it('saved("用户") 文案是 "用户保存成功"', () => {
      const m = useCrudMessage()
      m.saved('用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户保存成功')
    })

    it('created() 文案是 "用户创建成功"', () => {
      const m = useCrudMessage()
      m.created('用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户创建成功')
    })

    it('updated() 文案是 "角色更新成功"', () => {
      const m = useCrudMessage()
      m.updated('角色')
      expect(mockUseMessage.success).toHaveBeenCalledWith('角色更新成功')
    })

    it('deleted() 文案是 "数据删除成功"', () => {
      const m = useCrudMessage()
      m.deleted()
      expect(mockUseMessage.success).toHaveBeenCalledWith('数据删除成功')
    })

    it('stateChanged("锁定", "用户") 文案是 "用户已锁定"', () => {
      const m = useCrudMessage()
      m.stateChanged('锁定', '用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户已锁定')
    })

    it('stateChanged("激活") 默认 entity 是 "用户"', () => {
      const m = useCrudMessage()
      m.stateChanged('激活')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户已激活')
    })

    it('profileUpdated() 文案是 "个人信息已更新"', () => {
      const m = useCrudMessage()
      m.profileUpdated()
      expect(mockUseMessage.success).toHaveBeenCalledWith('个人信息已更新')
    })

    it('passwordChanged() 文案是 "密码修改成功"', () => {
      const m = useCrudMessage()
      m.passwordChanged()
      expect(mockUseMessage.success).toHaveBeenCalledWith('密码修改成功')
    })

    it('preferencesSaved() 文案是 "偏好设置已保存"', () => {
      const m = useCrudMessage()
      m.preferencesSaved()
      expect(mockUseMessage.success).toHaveBeenCalledWith('偏好设置已保存')
    })
  })

  describe('错误反馈', () => {
    it('error() 默认文案 "操作失败"', () => {
      const m = useCrudMessage()
      m.error()
      expect(mockUseMessage.error).toHaveBeenCalledWith('操作失败')
    })

    it('error("保存失败") 自定义文案', () => {
      const m = useCrudMessage()
      m.error('保存失败')
      expect(mockUseMessage.error).toHaveBeenCalledWith('保存失败')
    })

    it('error() 优先从 err.response.data.message 提取', () => {
      const m = useCrudMessage()
      const err = { response: { data: { message: '用户名已存在' } } }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenCalledWith('用户名已存在')
    })

    it('error() 其次从 err.message 提取', () => {
      const m = useCrudMessage()
      const err = { message: 'Network Error' }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenCalledWith('Network Error')
    })

    it('error() err 无有效消息时用 defaultMsg', () => {
      const m = useCrudMessage()
      const err = {}
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenCalledWith('保存失败')
    })

    it('error() null err 时用 defaultMsg', () => {
      const m = useCrudMessage()
      m.error('保存失败', null)
      expect(mockUseMessage.error).toHaveBeenCalledWith('保存失败')
    })

    it('networkError() 文案是 "网络错误，请稍后重试"', () => {
      const m = useCrudMessage()
      m.networkError()
      expect(mockUseMessage.error).toHaveBeenCalledWith('网络错误，请稍后重试')
    })
  })

  describe('透传 useMessage', () => {
    it('success() 透传 useMessage.success', () => {
      const m = useCrudMessage()
      m.success('自定义消息')
      expect(mockUseMessage.success).toHaveBeenCalledWith('自定义消息')
    })

    it('warning() 透传 useMessage.warning', () => {
      const m = useCrudMessage()
      m.warning('警告')
      expect(mockUseMessage.warning).toHaveBeenCalledWith('警告')
    })

    it('info() 透传 useMessage.info', () => {
      const m = useCrudMessage()
      m.info('提示')
      expect(mockUseMessage.info).toHaveBeenCalledWith('提示')
    })

    it('confirm() 透传 useMessage.confirm', () => {
      const m = useCrudMessage()
      m.confirm({ title: '确认', content: '是否继续?' })
      expect(mockUseMessage.confirm).toHaveBeenCalledWith({ title: '确认', content: '是否继续?' })
    })
  })

  describe('每次调用返回新对象', () => {
    it('多次 useCrudMessage() 调用互不影响', () => {
      const m1 = useCrudMessage()
      const m2 = useCrudMessage()
      // 不同引用（虽然底层 useMessage 是同一份 ref，但包装对象应该是新的）
      expect(m1).not.toBe(m2)
      // 但行为一致
      m1.saved('A')
      expect(mockUseMessage.success).toHaveBeenLastCalledWith('A保存成功')
      m2.saved('B')
      expect(mockUseMessage.success).toHaveBeenLastCalledWith('B保存成功')
    })
  })
})