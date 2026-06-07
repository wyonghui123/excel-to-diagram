/**
 * authService - 认证服务层
 *
 * FR-UI-002: 封装所有 /api/v1/auth/* 和 /api/v1/users/* 调用
 * FR-GAP-005: 迁移 .vue inline fetch 到 service 层
 *
 * 双通道访问:
 *   - v2 action 端点: login, logout (通过 useBoAction)
 *   - v1 REST 端点: getProfile, updateProfile, changePassword (通过 httpClient)
 */

import { apiV1 } from '@/utils/httpClient'
import { useBoAction } from '@/composables/useBOAction'

// ============================================================================
// v2 Action 端点（登录/登出）
// ============================================================================

/**
 * 用户登录
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{success: boolean, data?: {user: object, must_change_password: boolean}, message?: string}>}
 */
export async function login(username, password) {
  const { callPost } = useBoAction()
  return await callPost('user.authenticate', { username, password })
}

/**
 * 用户登出
 * @returns {Promise<{success: boolean}>}
 */
export async function logout() {
  const { callPost } = useBoAction()
  try {
    return await callPost('user.logout', {})
  } catch (e) {
    return { success: false }
  }
}

// ============================================================================
// v1 REST 端点（用户资料/密码）
// ============================================================================

/**
 * 获取当前用户资料
 * GET /api/v1/users/me
 *
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function getProfile() {
  return await apiV1.get('/users/me')
}

/**
 * @deprecated 使用 getProfile() — 别名保留兼容
 */
export const getCurrentUser = getProfile

/**
 * 更新用户资料
 * PUT /api/v1/users/me
 *
 * @param {object} profileData - { display_name, email, ... }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function updateProfile(profileData) {
  return await apiV1.put('/users/me', profileData)
}

/**
 * 修改密码
 * POST /api/v1/auth/change-password
 *
 * @param {string} oldPassword
 * @param {string} newPassword
 * @returns {Promise<{success: boolean, message?: string}>}
 */
export async function changePassword(oldPassword, newPassword) {
  return await apiV1.post('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export default {
  login,
  logout,
  getProfile,
  getCurrentUser: getProfile, // 别名，兼容 authStore
  updateProfile,
  changePassword,
}
