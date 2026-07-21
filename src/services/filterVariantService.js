/**
 * filterVariantService - 筛选方案管理服务
 *
 * FR-GAP-005: 封装 /api/v1/filter-variants/* 调用，消除 .vue inline fetch
 *
 * @module services/filterVariantService
 */

import { apiV1, apiV2 } from '@/utils/httpClient'

/**
 * 查询筛选方案列表
 * GET /api/v1/filter-variants?object_type=...
 *
 * @param {object} params - { object_type, ... }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function queryFilterVariants(params = {}) {
  return await apiV2.get('/bo/filter_variant', { params })
}

/**
 * 创建筛选方案
 * POST /api/v2/bo/filter_variant
 *
 * @param {object} data - { object_type, name, filters, is_default, ... }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function createFilterVariant(data) {
  return await apiV2.post('/bo/filter_variant', data)
}

/**
 * 设置默认筛选方案
 * POST /api/v1/filter-variants/:id/set-default
 *
 * @param {string|number} id
 * @returns {Promise<{success: boolean, message?: string}>}
 */
export async function setDefaultFilterVariant(id) {
  return await apiV1.post(`/filter-variants/${id}/set-default`)
}

/**
 * 删除筛选方案
 * DELETE /api/v2/bo/filter_variant/:id
 *
 * @param {string|number} id
 * @returns {Promise<{success: boolean, message?: string}>}
 */
export async function deleteFilterVariant(id) {
  return await apiV2.delete(`/bo/filter_variant/${id}`)
}

export default {
  queryFilterVariants,
  createFilterVariant,
  setDefaultFilterVariant,
  deleteFilterVariant,
}
