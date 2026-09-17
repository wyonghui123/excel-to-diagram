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
    it('saved() 默认文案是 "数据已保存"', () => {
      const m = useCrudMessage()
      m.saved()
      expect(mockUseMessage.success).toHaveBeenCalledWith('数据已保存')
    })

    it('saved("用户") 文案是 "用户已保存"', () => {
      const m = useCrudMessage()
      m.saved('用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户已保存')
    })

    it('created() 文案是 "用户已创建"', () => {
      const m = useCrudMessage()
      m.created('用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户已创建')
    })

    it('updated() 文案是 "角色已更新"', () => {
      const m = useCrudMessage()
      m.updated('角色')
      expect(mockUseMessage.success).toHaveBeenCalledWith('角色已更新')
    })

    it('deleted() 文案是 "数据已删除"', () => {
      const m = useCrudMessage()
      m.deleted()
      expect(mockUseMessage.success).toHaveBeenCalledWith('数据已删除')
    })

    it('stateChanged("锁定", "用户") 文案是 "用户已锁定"', () => {
      const m = useCrudMessage()
      m.stateChanged('锁定', '用户')
      expect(mockUseMessage.success).toHaveBeenCalledWith('用户已锁定')
    })

    it('stateChanged("激活") 默认 entity 是 "数据"', () => {
      const m = useCrudMessage()
      m.stateChanged('激活')
      expect(mockUseMessage.success).toHaveBeenCalledWith('数据已激活')
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
      expect(mockUseMessage.error).toHaveBeenCalledWith('操作失败', null)
    })

    it('error("保存失败") 自定义文案', () => {
      const m = useCrudMessage()
      m.error('保存失败')
      expect(mockUseMessage.error).toHaveBeenCalledWith('保存失败', null)
    })

    it('error() 优先从 err.response.data.message 提取', () => {
      const m = useCrudMessage()
      const err = { response: { data: { message: '用户名已存在' } } }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenCalledWith('用户名已存在', err)
    })

    it('error() 其次从 err.message 提取', () => {
      const m = useCrudMessage()
      const err = { message: 'Network Error' }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenCalledWith('Network Error', err)
    })

    it('error() err 无有效消息时用 defaultMsg', () => {
      const m = useCrudMessage()
      const err = {}
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('保存失败', err)
    })

    it('error() null err 时用 defaultMsg', () => {
      const m = useCrudMessage()
      m.error('保存失败', null)
      expect(mockUseMessage.error).toHaveBeenCalledWith('保存失败', null)
    })

    it('networkError() 文案是 "网络连接失败，请检查网络后重试"', () => {
      const m = useCrudMessage()
      m.networkError()
      expect(mockUseMessage.error).toHaveBeenCalledWith('网络连接失败，请检查网络后重试')
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
      expect(mockUseMessage.success).toHaveBeenLastCalledWith('A已保存')
      m2.saved('B')
      expect(mockUseMessage.success).toHaveBeenLastCalledWith('B已保存')
    })
  })

  describe('[Spec 22 2026-09-13] extractErrorMessage 增强识别 apiV2 包装格式', () => {
    it('识别 apiV2 包装格式 { message, httpStatus, code }', () => {
      const m = useCrudMessage()
      // ActionPermissionInterceptor 拒绝时 apiV2.put 返回的格式
      const err = {
        success: false,
        data: null,
        message: '缺少权限 activate（state_transition: enable_user, object: user）',
        code: 'ERR_403_FORBIDDEN',
        httpStatus: 403,
      }
      m.error('启用失败', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith(
        '缺少权限 activate（state_transition: enable_user, object: user）',
        err,
      )
    })

    it('识别 axios 原生错误格式（向后兼容）', () => {
      const m = useCrudMessage()
      const err = { response: { data: { message: '用户名已存在' } } }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('用户名已存在', err)
    })

    it('识别通用 Error.message 格式（向后兼容）', () => {
      const m = useCrudMessage()
      const err = { message: 'Network Error' }
      m.error('保存失败', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('Network Error', err)
    })

    it('fallback: 全部字段空时使用 defaultMsg', () => {
      const m = useCrudMessage()
      m.error('保存失败', {})
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('保存失败', {})
    })
  })

  describe('[Spec 22 2026-09-13] isPermissionDenied 检测', () => {
    it('apiV2 包装格式 httpStatus=403', async () => {
      const { isPermissionDenied } = await import('@/composables/useCrudMessage.js')
      expect(isPermissionDenied({ httpStatus: 403 })).toBe(true)
    })

    it('apiV2 包装格式 code=ERR_403_FORBIDDEN', async () => {
      const { isPermissionDenied } = await import('@/composables/useCrudMessage.js')
      expect(isPermissionDenied({ code: 'ERR_403_FORBIDDEN' })).toBe(true)
    })

    it('axios 原生 response.status=403', async () => {
      const { isPermissionDenied } = await import('@/composables/useCrudMessage.js')
      expect(isPermissionDenied({ response: { status: 403 } })).toBe(true)
    })

    it('非 403 不算权限拒绝', async () => {
      const { isPermissionDenied } = await import('@/composables/useCrudMessage.js')
      expect(isPermissionDenied({ httpStatus: 500 })).toBe(false)
      expect(isPermissionDenied({})).toBe(false)
      expect(isPermissionDenied(null)).toBe(false)
    })
  })

  describe('[Spec 22 2026-09-13] permissionDenied 专用反馈', () => {
    it('后端有具体 message 时优先显示', () => {
      const m = useCrudMessage()
      const err = {
        success: false,
        message: '缺少权限 lock（state_transition: lock_user, object: user）',
        httpStatus: 403,
      }
      m.permissionDenied('锁定', err, 'lock')
      expect(mockUseMessage.error).toHaveBeenLastCalledWith(
        '缺少权限 lock（state_transition: lock_user, object: user）',
        err,
      )
    })

    it('后端无 message 时前端组装 + 显示权限码提示', () => {
      const m = useCrudMessage()
      const err = { httpStatus: 403 }
      m.permissionDenied('启用', err, 'activate')
      expect(mockUseMessage.error).toHaveBeenLastCalledWith(
        '当前用户无权限启用（需权限 activate）',
        err,
      )
    })

    it('后端无 message 且无 actionRef 时显示通用提示', () => {
      const m = useCrudMessage()
      const err = { httpStatus: 403 }
      m.permissionDenied('启用', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith(
        '当前用户无权限启用',
        err,
      )
    })
  })

  describe('[Spec 22 2026-09-13] stateChangeFailed 自动识别 403', () => {
    it('err.httpStatus=403 → 走 permissionDenied', () => {
      const m = useCrudMessage()
      const err = {
        message: '缺少权限 activate',
        httpStatus: 403,
      }
      m.stateChangeFailed('启用', err, 'activate')
      // 期望显示后端 message
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('缺少权限 activate', err)
    })

    it('err 非 403 → 走通用 error 显示失败', () => {
      const m = useCrudMessage()
      const err = {
        message: '数据库连接超时',
        httpStatus: 500,
      }
      m.stateChangeFailed('启用', err)
      expect(mockUseMessage.error).toHaveBeenLastCalledWith('启用失败', err)
    })
  })
})