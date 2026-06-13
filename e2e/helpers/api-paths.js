/**
 * E2E API 路径集中 (v3.18.4+ Phase 6 健壮性)
 *
 * [!!!] 硬编码 API URL 散落 30+ 处, 后端改路径要改 30 个 spec [!!!]
 * [!!!] 本文件集中所有 API URL, 后端改路径只改这里 [!!!]
 *
 * 设计:
 * - 每个业务对象一个 getter, 参数化
 * - 后端改路径只改这里, spec 不用动
 * - 支持 build() 模式生成查询字符串
 *
 * 用法:
 *   import { API } from '../helpers/api-paths.js'
 *   await page.request.get(API.audit.logs({ level: 'ERROR' }))
 *   await page.request.post(API.bo.create('product'), { data: {...} })
 */

const V1 = '/api/v1'
const V2 = '/api/v2'

/**
 * 工具: 拼查询字符串
 * @param {Record<string, any>} params
 * @returns {string} ?key=value&... (无参数返回空串)
 */
function qs(params) {
  if (!params) return ''
  const entries = Object.entries(params).filter(([_, v]) => v !== null && v !== undefined)
  if (entries.length === 0) return ''
  return '?' + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
}

export const API = {
  // ============ Auth ============
  auth: {
    devLogin: (username = 'admin') => `${V1}/auth/dev-login?username=${username}`,
  },

  // ============ Audit Log (v1 + v2 兼容) ============
  audit: {
    /**
     * 审计日志查询
     * @param {Object} filters
     *   - page (default 1)
     *   - page_size (default 200)
     *   - log_category (business|security|operation|performance|system)
     *   - log_level (DEBUG|INFO|WARNING|ERROR|CRITICAL)
     *   - object_type (role|product|...)
     *   - action (CREATE|UPDATE|DELETE|ASSOCIATE|...)
     */
    logs: (filters = {}) => `${V1}/audit/logs${qs({ page: 1, page_size: 200, ...filters })}`,
    logsV2: (filters = {}) => `${V2}/audit/logs${qs({ page: 1, page_size: 200, ...filters })}`,
  },

  // ============ Business Object (v2) ============
  bo: {
    // 列表
    list: (type, filters = {}) => `${V2}/bo/${type}${qs({ page: 1, page_size: 200, ...filters })}`,
    product: (filters = {}) => `${V2}/bo/product${qs({ page_size: 1, ...filters })}`,
    version: (productId, filters = {}) => `${V2}/bo/version${qs({ product_id: productId, page_size: 1, ...filters })}`,

    // CRUD
    create: (type) => `${V2}/bo/${type}`,
    get: (type, id) => `${V2}/bo/${type}/${id}`,
    update: (type, id) => `${V2}/bo/${type}/${id}`,
    delete: (type, id) => `${V2}/bo/${type}/${id}`,
    batchDelete: (type) => `${V2}/bo/${type}/batch-delete`,

    // 关联
    createAssociation: () => `${V2}/bo/association`,
  },

  // ============ Roles (v1) ============
  roles: {
    list: (filters = {}) => `${V1}/roles${qs({ page: 1, page_size: 1, ...filters })}`,
  },

  // ============ Frontend Navigation URLs ============
  routes: {
    home: '/',
    productManagement: '/product-management',
    productDetail: (id) => `/product-management/${id}`,
    productVersionDetail: (productId, versionId) => `/product-management/${productId}/version/${versionId}`,
    archData: (productId, versionId, tab = null) => {
      const params = new URLSearchParams()
      if (productId) params.set('productId', productId)
      if (versionId) params.set('versionId', versionId)
      if (tab) params.set('tab', tab)
      const qs_str = params.toString()
      return `/system/archdata${qs_str ? '?' + qs_str : ''}`
    },
    roleDetail: (id) => `/system/role-detail/${id}`,
    userGroups: '/user-permission/user-groups',
    systemAdmin: '/system-admin',
  },

  // ============ Health ============
  health: {
    check: '/api/v2/health',
  },
}

/**
 * 反向工具: 从 API path 提取 type
 * 例: extractType('/api/v2/bo/product/123') → 'product'
 * 用于清理时 (cleanup() 要知道 type)
 */
export function extractTypeFromPath(path) {
  const match = path.match(/\/api\/v\d+\/bo\/([^/]+)/)
  return match ? match[1] : null
}
