/**
 * authService 单元测试
 *
 * 覆盖:
 *  - login (成功/失败)
 *  - logout (成功/异常降级)
 *  - getProfile (成功/失败)
 *  - getCurrentUser (是 getProfile 的别名)
 *  - updateProfile (成功/失败)
 *  - changePassword (成功/失败)
 *
 * 策略：mock @/utils/httpClient 的 apiV1 + @/composables/useBOAction
 * 使用 vi.hoisted 避免 isolate:true 下 mock 链断裂
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.hoisted 让 mock 函数引用在 import 之前就创建
const mocks = vi.hoisted(() => ({
  apiV1Get: vi.fn(),
  apiV1Put: vi.fn(),
  apiV1Post: vi.fn(),
  callPost: vi.fn(),
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: mocks.apiV1Get,
    put: mocks.apiV1Put,
    post: mocks.apiV1Post,
  },
}))

vi.mock('@/composables/useBOAction', () => ({
  useBoAction: () => ({
    callPost: mocks.callPost,
  }),
}))

import {
  login,
  logout,
  getProfile,
  getCurrentUser,
  updateProfile,
  changePassword,
} from '../authService.js'

// 工具：构造 httpClient 标准响应
function okResp(data) {
  return {
    success: true,
    data,
    message: '',
    httpStatus: 200,
    traceId: 'trace-test',
  }
}

function failResp(httpStatus, message = 'error') {
  return {
    success: false,
    data: null,
    message,
    code: 'ERR',
    httpStatus,
    traceId: 'trace-test',
  }
}

describe('authService', () => {
  beforeEach(() => {
    mocks.apiV1Get.mockReset()
    mocks.apiV1Put.mockReset()
    mocks.apiV1Post.mockReset()
    mocks.callPost.mockReset()
  })

  // =========================================================================
  // login
  // =========================================================================
  describe('login', () => {
    it('成功登录应返回用户数据和 must_change_password 标志', async () => {
      const userData = { id: 1, username: 'admin', display_name: '管理员' }
      mocks.callPost.mockResolvedValueOnce(
        okResp({ user: userData, must_change_password: false })
      )

      const result = await login('admin', 'pass123')

      expect(result.success).toBe(true)
      expect(result.data.user).toEqual(userData)
      expect(result.data.must_change_password).toBe(false)
      expect(mocks.callPost).toHaveBeenCalledWith('user.authenticate', {
        username: 'admin',
        password: 'pass123',
      })
    })

    it('登录失败应返回错误信息', async () => {
      mocks.callPost.mockResolvedValueOnce(
        failResp(401, '用户名或密码错误')
      )

      const result = await login('admin', 'wrong')

      expect(result.success).toBe(false)
      expect(result.message).toBe('用户名或密码错误')
      expect(mocks.callPost).toHaveBeenCalledWith('user.authenticate', {
        username: 'admin',
        password: 'wrong',
      })
    })
  })

  // =========================================================================
  // logout
  // =========================================================================
  describe('logout', () => {
    it('成功登出应返回 success: true', async () => {
      mocks.callPost.mockResolvedValueOnce(okResp({}))

      const result = await logout()

      expect(result.success).toBe(true)
      expect(mocks.callPost).toHaveBeenCalledWith('user.logout', {})
    })

    it('登出异常应降级返回 success: false 而不抛出', async () => {
      mocks.callPost.mockRejectedValueOnce(new Error('网络错误'))

      const result = await logout()

      expect(result.success).toBe(false)
    })
  })

  // =========================================================================
  // getProfile
  // =========================================================================
  describe('getProfile', () => {
    it('成功获取用户资料', async () => {
      const profile = { id: 1, username: 'admin', display_name: '管理员', email: 'admin@test.com' }
      mocks.apiV1Get.mockResolvedValueOnce(okResp(profile))

      const result = await getProfile()

      expect(result.success).toBe(true)
      expect(result.data).toEqual(profile)
      expect(mocks.apiV1Get).toHaveBeenCalledWith('/users/me')
    })

    it('获取用户资料失败应返回错误', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(failResp(401, '未授权'))

      const result = await getProfile()

      expect(result.success).toBe(false)
      expect(result.message).toBe('未授权')
    })
  })

  // =========================================================================
  // getCurrentUser
  // =========================================================================
  describe('getCurrentUser', () => {
    it('getCurrentUser 是 getProfile 的别名', () => {
      expect(getCurrentUser).toBe(getProfile)
    })

    it('调用 getCurrentUser 应与 getProfile 行为一致', async () => {
      const profile = { id: 2, username: 'user1' }
      mocks.apiV1Get.mockResolvedValueOnce(okResp(profile))

      const result = await getCurrentUser()

      expect(result.success).toBe(true)
      expect(result.data).toEqual(profile)
      expect(mocks.apiV1Get).toHaveBeenCalledWith('/users/me')
    })
  })

  // =========================================================================
  // updateProfile
  // =========================================================================
  describe('updateProfile', () => {
    it('成功更新用户资料', async () => {
      const updated = { id: 1, display_name: '新名字', email: 'new@test.com' }
      mocks.apiV1Put.mockResolvedValueOnce(okResp(updated))

      const result = await updateProfile({ display_name: '新名字', email: 'new@test.com' })

      expect(result.success).toBe(true)
      expect(result.data).toEqual(updated)
      expect(mocks.apiV1Put).toHaveBeenCalledWith('/users/me', {
        display_name: '新名字',
        email: 'new@test.com',
      })
    })

    it('更新用户资料失败应返回错误', async () => {
      mocks.apiV1Put.mockResolvedValueOnce(failResp(422, '邮箱格式不正确'))

      const result = await updateProfile({ email: 'invalid' })

      expect(result.success).toBe(false)
      expect(result.message).toBe('邮箱格式不正确')
    })
  })

  // =========================================================================
  // changePassword
  // =========================================================================
  describe('changePassword', () => {
    it('成功修改密码', async () => {
      mocks.apiV1Post.mockResolvedValueOnce(okResp({}))

      const result = await changePassword('oldPass', 'newPass')

      expect(result.success).toBe(true)
      expect(mocks.apiV1Post).toHaveBeenCalledWith('/auth/change-password', {
        old_password: 'oldPass',
        new_password: 'newPass',
      })
    })

    it('修改密码失败应返回错误', async () => {
      mocks.apiV1Post.mockResolvedValueOnce(failResp(400, '原密码不正确'))

      const result = await changePassword('wrongOld', 'newPass')

      expect(result.success).toBe(false)
      expect(result.message).toBe('原密码不正确')
    })
  })
})
