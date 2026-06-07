/**
 * annotationService - 标注管理服务
 *
 * FR-GAP-005: 封装 /api/v1/annotations/* 调用，消除 .vue inline fetch
 *
 * @module services/annotationService
 */

import { apiV1 } from '@/utils/httpClient'

/**
 * 查询标注列表
 * GET /api/v1/annotations?target_type=...&target_id=...&page=...&page_size=...
 *
 * @param {object} params - { target_type, target_id, page, page_size, ... }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function queryAnnotations(params = {}) {
  return await apiV1.get('/annotations', { params })
}

/**
 * 获取标注详情
 * GET /api/v1/annotations/:id
 *
 * @param {string|number} id
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function getAnnotation(id) {
  return await apiV1.get(`/annotations/${id}`)
}

/**
 * 创建标注
 * POST /api/v1/annotations
 *
 * @param {object} data - { target_type, target_id, category, content }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function createAnnotation(data) {
  return await apiV1.post('/annotations', data)
}

/**
 * 更新标注
 * PUT /api/v1/annotations/:id
 *
 * @param {string|number} id
 * @param {object} data - { category, content }
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
export async function updateAnnotation(id, data) {
  return await apiV1.put(`/annotations/${id}`, data)
}

/**
 * 删除标注
 * DELETE /api/v1/annotations/:id
 *
 * @param {string|number} id
 * @returns {Promise<{success: boolean, message?: string}>}
 */
export async function deleteAnnotation(id) {
  return await apiV1.delete(`/annotations/${id}`)
}

export default {
  queryAnnotations,
  getAnnotation,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
}
