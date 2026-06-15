/**
 * permissionService - 权限管理服务层
 *
 * FR-UI-007: 封装所有权限管理相关的 API 调用和业务逻辑
 * 消除 7 个 Vue 组件中的 30 处 fetch() 调用和 8 类重复业务逻辑
 */

import { apiV1, apiV2 } from '@/utils/httpClient'

// ==================== 常量 ====================

/**
 * 权限级别配置（统一来源，消除 5 处重复定义）
 */
export const PERMISSION_LEVELS = {
  none: { label: '无权限', type: 'info' },
  read: { label: '只读', type: '' },
  write: { label: '可编辑', type: 'warning' },
  admin: { label: '完全管理', type: 'success' },
  manage: { label: '管理', type: 'success' },
}

/**
 * 资源类型标签（统一来源，消除 4 处重复定义）
 */
export const RESOURCE_LABELS = {
  domain: '领域',
  sub_domain: '子领域',
  service_module: '服务模块',
  business_object: '业务对象',
  product: '产品',
  version: '版本',
  relationship: '关系',
  annotation: '标注',
}

/**
 * 维度父子映射
 */
export const DIMENSION_PARENT_MAP = {
  product: null,
  version: 'product',
  domain: 'version',
  sub_domain: 'domain',
}

/**
 * 维度层级
 */
export const DIMENSION_LEVEL_MAP = {
  product: 0,
  version: 1,
  domain: 2,
  sub_domain: 3,
}

/**
 * 父字段映射
 */
export const PARENT_FIELD_MAP = {
  version: 'product_id',
  domain: 'version_id',
  sub_domain: 'domain_id',
}

/**
 * 隐藏维度列表
 */
export const HIDDEN_DIMENSIONS = [
  'domain_type', 'organization', 'department', 'employee',
  'created_by', 'created_at', 'owner_id',
]

/**
 * 操作标签
 */
export const ACTION_LABELS = {
  create: '创建',
  read: '查看',
  update: '编辑',
  delete: '删除',
  export: '导出',
  manage: '管理',
}

// ==================== 纯函数 ====================

/**
 * 权限级别 -> Tag 类型映射
 * @param {string} level - 'read'|'write'|'admin'|'manage'|'none'
 * @returns {'success'|'warning'|'danger'|'info'|''}
 */
export function getPermissionLevelType(level) {
  return PERMISSION_LEVELS[level]?.type ?? ''
}

/**
 * 权限级别 -> 中文标签
 * @param {string} level
 * @returns {string}
 */
export function getPermissionLevelLabel(level) {
  return PERMISSION_LEVELS[level]?.label ?? level
}

/**
 * 资源类型 -> 中文标签
 * @param {string} resourceType
 * @returns {string}
 */
export function getResourceLabel(resourceType) {
  return RESOURCE_LABELS[resourceType] ?? resourceType
}

/**
 * 根据 resource_type 查找维度中文名
 * @param {Array} dimensions - 维度列表
 * @param {string} resourceType
 * @returns {string}
 */
export function getDimensionName(dimensions, resourceType) {
  const dim = dimensions.find(d => d.code === resourceType || d.id === resourceType)
  return dim?.name ?? getResourceLabel(resourceType)
}

// ==================== API 函数 ====================

/**
 * 加载角色列表
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function loadRoles(params = {}) {
  const r = await apiV1.get('/roles', { params })
  return r.success ? r : { data: r.data }
}

/**
 * 加载角色详情
 * @param {number} roleId
 * @returns {Promise<object>}
 */
export async function loadRole(roleId) {
  return await apiV1.get(`/roles/${roleId}`)
}

/**
 * 加载管理维度列表
 * [MIGRATION 2026-06-14] v1 顶层 CRUD 已 sunset (410), 改调 v2 /api/v2/bo/management_dimension
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function loadDimensions(params = {}) {
  return await apiV2.get('/bo/management_dimension', { params })
}

/**
 * 加载维度字段
 * [MIGRATION 2026-06-14] /fields 端点后端 v1/v2 均未实现, 保留函数接口但加 TODO
 * @param {number|string} dimensionId
 * @returns {Promise<object>}
 */
export async function loadDimensionFields(dimensionId) {
  // TODO: 后端 /api/v2/bo/management_dimension/{id}/fields 端点尚未实现
  //       暂时返回空响应避免前端崩溃, 后续补全后端
  return Promise.resolve({ success: false, data: { fields: [] }, message: '/fields 端点待实现' })
}

/**
 * 加载维度实例（Value Help）
 * [MIGRATION 2026-06-14] v1 无此子路径, 改 v2
 * @param {string} dimCode - 维度代码
 * @param {object} [params] - search, limit, filter_* 等
 * @returns {Promise<object>}
 */
export async function loadDimensionValues(dimCode, params = {}) {
  return await apiV2.get(`/bo/management_dimension/dimensions/${dimCode}/values`, { params })
}

/**
 * 加载维度实例（分页，用于 DimensionScopePanel）
 * [MIGRATION 2026-06-14] v1 无 management-dimensions blueprint, 改 v2
 * @param {number|string} dimensionId
 * @param {object} [params] - page, page_size, search, filter_*
 * @returns {Promise<object>}
 */
export async function loadDimensionInstances(dimensionId, params = {}) {
  return await apiV2.get(`/bo/management_dimension/${dimensionId}/instances`, { params })
}

/**
 * 加载角色的权限规则
 * @param {number} roleId
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function loadPermissionRules(roleId, params = {}) {
  return await apiV1.get(`/roles/${roleId}/permission-rules`, { params })
}

/**
 * 保存权限规则（新建 / 编辑 / 批量）
 * @param {number} roleId
 * @param {object} rule - 规则数据
 * @param {'create'|'update'|'batch'} mode
 * @returns {Promise<object>}
 */
export async function savePermissionRules(roleId, rule, mode = 'create') {
  if (mode === 'batch') {
    return await apiV1.post(`/roles/${roleId}/permission-rules/batch`, rule)
  }
  if (mode === 'update' && rule.id) {
    return await apiV1.put(`/roles/${roleId}/permission-rules/${rule.id}`, rule)
  }
  return await apiV1.post(`/roles/${roleId}/permission-rules`, rule)
}

/**
 * 删除权限规则
 * @param {number} roleId
 * @param {number} ruleId
 * @returns {Promise<object>}
 */
export async function deletePermissionRule(roleId, ruleId) {
  return await apiV1.delete(`/roles/${roleId}/permission-rules/${ruleId}`)
}

/**
 * 切换规则启用/禁用
 * @param {number} roleId
 * @param {number} ruleId
 * @param {object} patchData - { is_enabled: boolean }
 * @returns {Promise<object>}
 */
export async function patchPermissionRule(roleId, ruleId, patchData) {
  return await apiV1.patch(`/roles/${roleId}/permission-rules/${ruleId}`, patchData)
}

/**
 * 计算规则影响范围
 * @param {number} roleId
 * @param {object} rule
 * @returns {Promise<object>}
 */
export async function calculateImpact(roleId, rule) {
  return await apiV1.post(`/roles/${roleId}/calculate-impact`, rule)
}

/**
 * 加载字段元数据
 * @param {string} resourceType
 * @returns {Promise<object>}
 */
export async function loadFieldMetadata(resourceType) {
  return await apiV1.get('/permission-rules/field-metadata', { params: { resource_type: resourceType } })
}

/**
 * 预览条件匹配
 * @param {object} previewData - { condition, resource_type }
 * @returns {Promise<object>}
 */
export async function previewCondition(previewData) {
  return await apiV1.post('/permission-rules/preview', previewData)
}

/**
 * 加载统一权限配置
 * @param {number} roleId
 * @returns {Promise<object>}
 */
export async function loadUnifiedPermissions(roleId) {
  return await apiV1.get(`/roles/${roleId}/unified-permissions`)
}

/**
 * 保存菜单权限
 * @param {number} roleId
 * @param {object} permissions
 * @returns {Promise<object>}
 */
export async function saveMenuPermissions(roleId, permissions) {
  return await apiV1.put(`/roles/${roleId}/menu-permissions`, permissions)
}

/**
 * 加载维度范围
 * @param {number} roleId
 * @returns {Promise<object>}
 */
export async function loadDimensionScopes(roleId) {
  return await apiV1.get(`/roles/${roleId}/dimension-scopes`)
}

/**
 * 保存维度范围
 * @param {number} roleId
 * @param {object} scopes
 * @returns {Promise<object>}
 */
export async function saveDimensionScopes(roleId, scopes) {
  return await apiV1.post(`/roles/${roleId}/dimension-scopes`, scopes)
}

/**
 * 自动推导权限
 * @param {number} roleId
 * @returns {Promise<object>}
 */
export async function derivePermissions(roleId) {
  return await apiV1.get(`/roles/${roleId}/derived-permissions`)
}

/**
 * 查询字段重叠警告
 * @param {number} roleId
 * @param {string} resourceType
 * @returns {Promise<object>}
 */
export async function loadOverlapWarnings(roleId, resourceType) {
  return await apiV1.get(`/roles/${roleId}/overlaps`, { params: { resource_type: resourceType } })
}

/**
 * 加载条件规则列表
 * [MIGRATION 2026-06-14] v1 顶层 CRUD 已 sunset (410), 改调 v2 /api/v2/permission-rules
 * @param {object} [params] - role_id 等
 * @returns {Promise<object>}
 */
export async function loadConditionRules(params = {}) {
  return await apiV2.get('/permission-rules', { params })
}

/**
 * 删除条件规则
 * [MIGRATION 2026-06-14] 改调 v2
 * @param {number} ruleId
 * @returns {Promise<object>}
 */
export async function deleteConditionRule(ruleId) {
  return await apiV2.delete(`/permission-rules/${ruleId}`)
}

/**
 * 保存条件规则
 * [MIGRATION 2026-06-14] 改调 v2
 * @param {object} rule
 * @returns {Promise<object>}
 */
export async function saveConditionRule(rule) {
  return await apiV2.post('/permission-rules', rule)
}

/**
 * 搜索用户（用于批量授权）
 * @param {string} keyword
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function searchUsers(keyword, params = {}) {
  return await apiV1.get('/users', { params: { keyword, page_size: 20, ...params } })
}

/**
 * 批量设置数据权限
 * @param {object} data - { user_ids, resource_type, resource_id, permission_level, inherit_to_children }
 * @returns {Promise<object>}
 */
export async function batchDataPermissions(data) {
  return await apiV1.post('/users/batch-data-permissions', data)
}

/**
 * 为用户组添加数据权限
 * @param {number} groupId
 * @param {object} data
 * @returns {Promise<object>}
 * @deprecated 此处使用 v1 子路径 /user-groups/{id}/data-permissions.
 *   v1 顶层 5 个端点 (GET/POST/PUT/DELETE /user-groups) 已 sunset (410),
 *   迁移到 /api/v2/bo/user_group. 该子路径暂未 sunset, 仍可使用;
 *   后续如该子路径也 sunset, 需迁移到 v2 等价接口 (e.g. data-permission BO action).
 */
export async function addGroupDataPermission(groupId, data) {
  return await apiV1.post(`/user-groups/${groupId}/data-permissions`, data)
}

/**
 * 加载对象类型元数据
 * @returns {Promise<object>}
 */
export async function loadObjectTypes() {
  return await apiV1.get('/meta/objects')
}

/**
 * 加载资源列表（分页）
 * @param {string} resourceType
 * @param {object} [params] - page, page_size, keyword
 * @returns {Promise<object>}
 */
export async function loadResources(resourceType, params = {}) {
  return await apiV1.get(`/${resourceType}`, { params })
}

export default {
  // 常量
  PERMISSION_LEVELS,
  RESOURCE_LABELS,
  DIMENSION_PARENT_MAP,
  DIMENSION_LEVEL_MAP,
  PARENT_FIELD_MAP,
  HIDDEN_DIMENSIONS,
  ACTION_LABELS,
  // 纯函数
  getPermissionLevelType,
  getPermissionLevelLabel,
  getResourceLabel,
  getDimensionName,
  // API 函数
  loadRoles,
  loadRole,
  loadDimensions,
  loadDimensionFields,
  loadDimensionValues,
  loadDimensionInstances,
  loadPermissionRules,
  savePermissionRules,
  deletePermissionRule,
  patchPermissionRule,
  calculateImpact,
  loadFieldMetadata,
  previewCondition,
  loadUnifiedPermissions,
  saveMenuPermissions,
  loadDimensionScopes,
  saveDimensionScopes,
  derivePermissions,
  loadOverlapWarnings,
  loadConditionRules,
  deleteConditionRule,
  saveConditionRule,
  searchUsers,
  batchDataPermissions,
  addGroupDataPermission,
  loadObjectTypes,
  loadResources,
}
