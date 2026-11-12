/**
 * engineeringChangeService - 工程变更单（ECM）专用 API
 *
 * 对齐后端 meta/api/engineering_change_api.py（只调用，不改动）:
 *   GET  /api/v1/engineering-changes                   列表（status/item_id/project_id + 分页）
 *   GET  /api/v1/engineering-changes/<id>              详情（头 + 明细）
 *   POST /api/v1/engineering-changes/diff              只读差异预览
 *   POST /api/v1/engineering-changes                   创建（draft）
 *   POST /api/v1/engineering-changes/<id>/submit       提交评审
 *   POST /api/v1/engineering-changes/<id>/approve      批准
 *   POST /api/v1/engineering-changes/<id>/reject       驳回
 *   POST /api/v1/engineering-changes/<id>/cancel       取消
 *   POST /api/v1/engineering-changes/<id>/apply        应用到生产 BOM
 *   GET  /api/v1/engineering-changes/<id>/where-used   影响预览（只读）
 *
 * 写操作全部走上述专用端点，不经过通用 /bo/...（spec §7 / §8）。
 * 响应契约由 httpClient 统一透出：{ success, data, message, code, businessCode, details }。
 *
 * @module services/engineeringChangeService
 */

import { apiV1 } from '@/utils/httpClient'

function _idPath(changeId, suffix = '') {
  return `/engineering-changes/${encodeURIComponent(changeId)}${suffix}`
}

/**
 * 变更单列表。
 * @param {{status?:string,item_id?:number,project_id?:number,page?:number,page_size?:number}} [params]
 */
export async function listChanges(params = {}) {
  return apiV1.get('/engineering-changes', { params })
}

/**
 * 变更单详情（头 + lines）。
 * @param {number|string} changeId
 */
export async function getChange(changeId) {
  return apiV1.get(_idPath(changeId))
}

/**
 * 只读差异预览（不落库）。
 * @param {{source_structure_id:number, target_structure_id:number, as_of?:string}} payload
 */
export async function diffStructures(payload) {
  return apiV1.post('/engineering-changes/diff', payload)
}

/**
 * 从差异创建变更单（draft）。
 * @param {{change_type:string,title:string,reason?:string,effective_date:string,project_id?:number,lines:Array<object>}} payload
 */
export async function createChange(payload) {
  return apiV1.post('/engineering-changes', payload)
}

/**
 * 提交评审（draft → in_review）。
 * @param {number|string} changeId
 * @param {{comment?:string}} [payload]
 */
export async function submitChange(changeId, payload = {}) {
  return apiV1.post(_idPath(changeId, '/submit'), payload)
}

/**
 * 批准（in_review → approved）。
 * @param {number|string} changeId
 * @param {string} [comment]
 */
export async function approveChange(changeId, comment) {
  return apiV1.post(_idPath(changeId, '/approve'), { comment })
}

/**
 * 驳回（in_review → rejected，原因必填）。
 * @param {number|string} changeId
 * @param {string} reason
 */
export async function rejectChange(changeId, reason) {
  return apiV1.post(_idPath(changeId, '/reject'), { reason })
}

/**
 * 取消（draft / in_review / approved → cancelled）。
 * @param {number|string} changeId
 * @param {string} [reason]
 */
export async function cancelChange(changeId, reason) {
  return apiV1.post(_idPath(changeId, '/cancel'), { reason })
}

/**
 * 应用到生产 BOM（approved → applied）。
 * @param {number|string} changeId
 */
export async function applyChange(changeId) {
  return apiV1.post(_idPath(changeId, '/apply'), {})
}

/**
 * 影响预览（只读：受影响父项结构 + 在途工单）。
 * @param {number|string} changeId
 */
export async function getImpact(changeId) {
  return apiV1.get(_idPath(changeId, '/where-used'))
}

export default {
  listChanges,
  getChange,
  diffStructures,
  createChange,
  submitChange,
  approveChange,
  rejectChange,
  cancelChange,
  applyChange,
  getImpact
}
