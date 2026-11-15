/**
 * 审批策略 API 客户端（审批流 M3）
 *
 * 后端契约：meta/api/approval_policy_api.py
 *   GET    /api/v1/approval-policies              列表（page / page_size / filters）
 *   GET    /api/v1/approval-policies/options      编辑器下拉项（对象 / 运算符 / 字典）
 *   GET    /api/v1/approval-policies/preview      命中试算（薄适配 resolver）
 *   GET    /api/v1/approval-policies/:id          详情（含 conditions / steps）
 *   POST   /api/v1/approval-policies              新建（version=1）
 *   PUT    /api/v1/approval-policies/:id          保存（version+1，子表整体替换）
 *
 * 权限：rule_center:read / rule_center:write（后端强制，前端仅做按钮可见性）。
 */
import { apiV1 } from '@/utils/httpClient'

export function listApprovalPolicies(params = {}) {
  return apiV1.get('/approval-policies', { params })
}

export function getApprovalPolicyOptions() {
  return apiV1.get('/approval-policies/options')
}

export function getApprovalPolicy(policyId) {
  return apiV1.get(`/approval-policies/${encodeURIComponent(policyId)}`)
}

export function createApprovalPolicy(payload) {
  return apiV1.post('/approval-policies', payload)
}

export function saveApprovalPolicy(policyId, payload) {
  return apiV1.put(`/approval-policies/${encodeURIComponent(policyId)}`, payload)
}

export function previewApprovalPolicy(params = {}) {
  return apiV1.get('/approval-policies/preview', { params })
}