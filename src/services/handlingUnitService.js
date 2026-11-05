import { apiV1 } from '@/utils/httpClient'
import boService from '@/services/boService'

/**
 * 包装容器作业 API（v218）。
 * 读接口走 handling_unit read；封箱 / 解封由后端独立权限控制。
 */

export function listHandlingUnits(params = {}) {
  return apiV1.get('/handling-units', { params })
}

export function scanHandlingUnit(huNo, orgId) {
  return apiV1.get('/handling-units/scan', {
    params: { hu_no: huNo, org_id: orgId || undefined }
  })
}

export function getHandlingUnitContents(huId, mode = 'direct') {
  return apiV1.get(`/handling-units/${huId}/contents`, { params: { mode } })
}

export function sealHandlingUnit(huId) {
  return apiV1.post(`/handling-units/${huId}/seal`, {})
}

export function unsealHandlingUnit(huId) {
  return apiV1.post(`/handling-units/${huId}/unseal`, {})
}

export function batchSealHandlingUnits(huIds) {
  return apiV1.post('/handling-units/batch-seal', { hu_ids: huIds })
}

export function queryDocumentHuLinks(params = {}) {
  return boService.query('document_hu_link_view', params)
}
