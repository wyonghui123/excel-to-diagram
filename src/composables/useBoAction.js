/**
 * useBoAction - v3 BO Action 统一门面
 *
 * 调用后端业务 Action（user.authenticate / user.logout / {bo}.batch_save 等）
 * 通过统一端点 POST /api/v2/action/{action_id}
 *
 * 优势:
 * - 统一鉴权链 (登录态 / 拦截器链)
 * - 自动 Cookie 认证 (HttpOnly cookie 携带)
 * - 统一错误格式 { success, data, message }
 * - 业务逻辑下沉到后端, 前端零业务
 *
 * 用法:
 *   import { useBoAction } from '@/composables/useBoAction'
 *   const { call } = useBoAction()
 *   const r = await call('user.authenticate', { username, password })
 *   if (r.success) { ... }
 */
import { apiV2 } from '@/utils/httpClient'
import { useAuthStore } from '@/stores/authStore'

const BO_ACTION_BASE = '/action/'

/**
 * 业务 Action 统一调用
 * @param {string} actionId - 业务 Action ID (e.g. 'user.authenticate')
 * @param {object} params - Action 参数
 * @param {object} options - 选项
 * @param {string} options.method - HTTP 方法 (GET/POST/PUT/DELETE)
 * @returns {Promise<{success: boolean, data: any, message: string}>}
 */
async function callAction(actionId, params = {}, options = {}) {
  const authStore = useAuthStore()
  const method = (options.method || 'POST').toUpperCase()
  const path = BO_ACTION_BASE + actionId

  try {
    if (method === 'GET') {
      const query = new URLSearchParams(
        Object.entries(params).filter(([_, v]) => v !== null && v !== undefined)
      ).toString()
      const fullPath = query ? `${path}?${query}` : path
      return await apiV2.get(fullPath, { authStore })
    } else if (method === 'DELETE') {
      const query = new URLSearchParams(
        Object.entries(params).filter(([_, v]) => v !== null && v !== undefined)
      ).toString()
      const fullPath = query ? `${path}?${query}` : path
      return await apiV2.delete(fullPath, { authStore })
    } else if (method === 'PUT') {
      return await apiV2.put(path, params, { authStore })
    } else {
      // POST (default)
      return await apiV2.post(path, params, { authStore })
    }
  } catch (e) {
    return {
      success: false,
      data: null,
      message: e?.message || '网络错误',
      code: e?.code || 'internal_error',  // [DECORATIVE] v3.7
    }
  }
}

/**
 * Composable 入口
 */
export function useBoAction() {
  return {
    call: callAction,
    callGet: (actionId, params) =>
      callAction(actionId, params, { method: 'GET' }),
    callPost: (actionId, params) =>
      callAction(actionId, params, { method: 'POST' }),
    callPut: (actionId, params) =>
      callAction(actionId, params, { method: 'PUT' }),
    callDelete: (actionId, params) =>
      callAction(actionId, params, { method: 'DELETE' }),
  }
}

export default useBoAction
