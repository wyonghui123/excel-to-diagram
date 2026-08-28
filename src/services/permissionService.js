/**
 * permissionService - 权限管理服务层
 *
 * FR-UI-007: 封装所有权限管理相关的 API 调用和业务逻辑
 * 消除 7 个 Vue 组件中的 30 处 fetch() 调用和 8 类重复业务逻辑
 */

import { apiV1, apiV2 } from '@/utils/httpClient'
import { logger } from '@/utils/logger'

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
// [P2-Matrix-02 / Phase 6 2026-08-25] 业务对象（受权限控制的数据资源）中文标签
// 注意: 用户/角色/用户组 是「权限主体」(principal)，不在此列表
//        它们的权限分配走专用路径（用户详情/角色详情/用户组详情）
export const RESOURCE_LABELS = {
  domain: '领域',
  sub_domain: '子领域',
  service_module: '服务模块',
  business_object: '业务对象',
  product: '产品',
  version: '版本',
  relationship: '关系',
  annotation: '标注',
  audit_log: '审计日志',
}

// [Phase 6 2026-08-25] 权限主体白名单（与后端 _IDENTITY_RESOURCE_TYPES 同步）
//   这些 rt 不参与功能权限矩阵资源列表
export const IDENTITY_RESOURCE_TYPES = new Set(['user', 'role', 'user_group'])

/**
 * 维度父子映射
 *
 * 静态 fallback，优先使用 buildDimensionMapsFromConfig() 从 YAML 动态生成。
 */
export const DIMENSION_PARENT_MAP = {
  product: null,
  version: 'product',
  domain: 'version',
  sub_domain: 'domain',
}

/**
 * 维度层级
 *
 * 静态 fallback，优先使用 buildDimensionMapsFromConfig() 从 YAML 动态生成。
 */
export const DIMENSION_LEVEL_MAP = {
  product: 0,
  version: 1,
  domain: 2,
  sub_domain: 3,
}

/**
 * 父字段映射
 *
 * 静态 fallback，优先使用 buildDimensionMapsFromConfig() 从 YAML 动态生成。
 */
export const PARENT_FIELD_MAP = {
  version: 'product_id',
  domain: 'version_id',
  sub_domain: 'domain_id',
}

/**
 * 从 hierarchies.yaml 配置动态生成维度映射常量
 *
 * @deprecated [P1-Base-03] 由 loadPermissionMeta() 的 metaCache（/permission_dimension/meta）
 *   取代。hierarchyConfig 为空/异常时返回空映射，调用方应改用 metaCache。
 *   保留仅为兼容历史调用方，新代码禁止使用。
 *
 * 替代 DIMENSION_PARENT_MAP / DIMENSION_LEVEL_MAP / PARENT_FIELD_MAP 的硬编码版本。
 * 当 hierarchyConfig 可用时，应优先使用此函数的返回值。
 *
 * @param {Object} hierarchyConfig - 来自 hierarchyService.fetchHierarchyConfig() 的配置
 * @returns {{ parentMap: Object, levelMap: Object, fieldMap: Object, labelMap: Object }}
 */
export function buildDimensionMapsFromConfig(hierarchyConfig) {
  const levels = hierarchyConfig?.hierarchy_levels || {}
  const parentMap = {}
  const levelMap = {}
  const fieldMap = {}
  const labelMap = {}

  for (const [objType, cfg] of Object.entries(levels)) {
    // 跳过非维度层级 (relationship 等)
    if (cfg.kind === 'association') continue

    parentMap[objType] = cfg.parent_object || null
    levelMap[objType] = cfg.level
    labelMap[objType] = cfg.display_name || objType
    if (cfg.filter_param) {
      fieldMap[objType] = cfg.filter_param
    }
  }

  return { parentMap, levelMap, fieldMap, labelMap }
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

// ==================== 权限配置元数据缓存（[P1-Base-03] /meta） ====================

const META_CACHE_KEY = 'permission_dimension_meta_cache'
const META_CACHE_TTL_MS = 5 * 60 * 1000 // 5min

/** @type {Object|null} /permission_dimension/meta 返回的 data（内存缓存） */
let metaCache = null
/** @type {Promise|null} 并发去重中的加载 Promise */
let metaCachePromise = null

function readLocalMetaCache() {
  try {
    const raw = localStorage.getItem(META_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || !parsed.at || Date.now() - parsed.at > META_CACHE_TTL_MS) return null
    return parsed.data
  } catch (_) {
    return null
  }
}

function writeLocalMetaCache(data) {
  try {
    localStorage.setItem(META_CACHE_KEY, JSON.stringify({ at: Date.now(), data }))
  } catch (_) { /* ignore */ }
}

/**
 * 加载权限配置元数据（[P1-Base-03] 后端 /permission_dimension/meta 聚合端点）
 *
 * 三级来源：内存缓存 → localStorage 缓存（TTL 5min）→ 后端。并发去重。
 * API 失败时返回 null（调用方走常量 fallback，UI 不白屏）。
 *
 * @returns {Promise<Object|null>} meta data：含 resource_type_labels / action_labels /
 *   dimension_priority / hierarchies_ui_config / normalizedFor* 等
 */
export async function loadPermissionMeta() {
  if (metaCache) return metaCache
  if (metaCachePromise) return metaCachePromise

  metaCachePromise = (async () => {
    const local = readLocalMetaCache()
    if (local) {
      metaCache = local
      return local
    }
    try {
      const r = await apiV2.get('/bo/permission_dimension/meta')
      if (r.success && r.data) {
        metaCache = r.data
        writeLocalMetaCache(r.data)
        return r.data
      }
      logger?.warn?.('[permissionService] loadPermissionMeta 失败，labels 走常量 fallback')
      return null
    } catch (e) {
      logger?.warn?.('[permissionService] loadPermissionMeta 异常，labels 走常量 fallback', e)
      return null
    }
  })().finally(() => { metaCachePromise = null })

  return metaCachePromise
}

/**
 * 清除权限配置元数据缓存（改 yaml 后调试用）
 */
export function invalidatePermissionMetaCache() {
  metaCache = null
  try { localStorage.removeItem(META_CACHE_KEY) } catch (_) { /* ignore */ }
}

/**
 * scopeCode 匹配失败时的结构化错误（5.5.4 P0 铁律）
 *
 * 后端返回 400 {"error":"SCOPE_CODE_INVALID","available_scope_codes":[...]} 时抛出。
 * 调用方必须展示错误并停止，**绝对禁止** catch 后重试不带 scope_code 的请求
 * （防 2026-08-08 全量 3230 对象加载 30s+ 卡死事故）。
 */
export class ScopeCodeInvalidError extends Error {
  constructor(message, availableScopeCodes = []) {
    super(message)
    this.name = 'ScopeCodeInvalidError'
    this.availableScopeCodes = availableScopeCodes
  }
}

/**
 * [P0 红线] 带 scope_code 的元数据请求保护
 *
 * 后端识别到 scopeCode 无效时返回 400 SCOPE_CODE_INVALID → 抛 ScopeCodeInvalidError；
 * 其余情况原样返回响应。调用方在 catch 中显示 Warning AppAlert，不得静默降级。
 *
 * @param {Object} [params] - 请求参数（应含 scope_code）
 * @returns {Promise<Object>} httpClient 统一响应
 */
export async function loadPermissionMetaWithScope(params = {}) {
  const r = await apiV2.get('/bo/permission_dimension/meta', { params })
  if (!r.success && r.error === 'SCOPE_CODE_INVALID') {
    throw new ScopeCodeInvalidError(
      r.message || '范围编码（scope_code）无效',
      r.available_scope_codes || [],
    )
  }
  return r
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
 * [P1-Base-03] metaCache（/permission_dimension/meta）优先，fallback 常量
 * @param {string} level
 * @returns {string}
 */
export function getPermissionLevelLabel(level) {
  const levels = metaCache?.permission_level_labels
  if (levels && levels[level]?.label) return levels[level].label
  return PERMISSION_LEVELS[level]?.label ?? level
}

/**
 * 资源类型 -> 中文标签
 * [P1-Base-03] metaCache（/permission_dimension/meta）优先，fallback 常量
 * @param {string} resourceType
 * @returns {string}
 */
export function getResourceLabel(resourceType) {
  const labels = metaCache?.resource_type_labels
  if (labels && labels[resourceType]) return labels[resourceType]
  return RESOURCE_LABELS[resourceType] ?? resourceType
}

/**
 * 动作 -> 中文标签
 * [P1-Base-03] metaCache（/permission_dimension/meta）优先，fallback 常量
 * @param {string} action - 'create'|'read'|'update'|'delete'|'export'|'manage'
 * @returns {string}
 */
export function getActionLabel(action) {
  const labels = metaCache?.action_labels
  if (labels && labels[action]) return labels[action]
  return ACTION_LABELS[action] ?? action
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
  const r = await apiV2.get('/bo/role', { params })
  // v2 返回分页格式 {items, total, page, page_size}，适配为 v1 格式 {data: [array]}
  if (r.success && r.data?.items) {
    return { success: true, data: r.data.items }
  }
  return r.success ? r : { data: r.data }
}

/**
 * 加载角色详情
 * @param {number} roleId
 * @returns {Promise<object>}
 */
export async function loadRole(roleId) {
  return await apiV2.get(`/bo/role/${roleId}`)
}

/**
 * 加载权限维度列表
 * [MIGRATION 2026-06-14] v1 顶层 CRUD 已 sunset (410), 改调 v2 /api/v2/bo/permission_dimension
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function loadDimensions(params = {}) {
  return await apiV2.get('/bo/permission_dimension', { params })
}

/**
 * 加载维度字段
 * [MIGRATION 2026-06-14] /fields 端点后端 v1/v2 均未实现, 保留函数接口但加 TODO
 * @param {number|string} dimensionId
 * @returns {Promise<object>}
 */
export async function loadDimensionFields(dimensionId) {
  // TODO: 后端 /api/v2/bo/permission_dimension/{id}/fields 端点尚未实现
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
  return await apiV2.get(`/bo/permission_dimension/dimensions/${dimCode}/values`, { params })
}

/**
 * 加载维度实例（分页，用于 DimensionScopePanel）
 * [MIGRATION 2026-06-14] v1 无 management-dimensions blueprint, 改 v2
 * @param {number|string} dimensionId
 * @param {object} [params] - page, page_size, search, filter_*
 * @returns {Promise<object>}
 */
export async function loadDimensionInstances(dimensionId, params = {}) {
  return await apiV2.get(`/bo/permission_dimension/${dimensionId}/instances`, { params })
}

/**
 * [2026-08-28 下沉到 service 层] 纯业务主键表达式的 ID→名称水合
 *
 * 场景：历史持久化规则（data_permission_rules.condition）只有技术表达式
 *   如 `id IN (1,2,3)` / `id = 5`，且无 condition_display 列，
 *   资源矩阵刷新后只能展示裸 ID。本函数解析表达式、翻页拉取实例列表，
 *   把 ID 映射回显示名，返回「名称1、名称2」格式
 *   （与 ConditionRuleDialog 纯业务主键条件的 condition_display 同口径）。
 *
 * 与 ConditionRuleDialog.hydratePickerNames 策略一致：
 *   后端 instances 接口 page_size 上限 100，按需循环翻页直至凑齐全部目标 ID。
 *
 * @param {string} resourceType - 资源类型（BO 编码，作为 instances 接口的维度 ID）
 * @param {string} expr - 条件表达式（如 "id IN (1,2)" / "id = 5"）
 * @returns {Promise<string>} 水合后的展示文本；无法解析/水合失败返回 ''
 */
export async function hydrateIdExpressionDisplay(resourceType, expr) {
  const m = String(expr || '').match(/^\s*id\s+(?:in|=)\s*\(?\s*([\d,\s]+?)\s*\)?\s*$/i)
  if (!m || !resourceType) return ''
  const ids = m[1].split(',').map((s) => s.trim()).filter(Boolean)
  if (ids.length === 0) return ''
  try {
    const pending = new Set(ids)
    const byId = new Map()
    for (let page = 1; page <= 100 && pending.size > 0; page++) {
      const res = await loadDimensionInstances(resourceType, { page, page_size: 100 })
      const insts = res.data?.instances || res.data || []
      if (!Array.isArray(insts) || insts.length === 0) break
      for (const inst of insts) {
        byId.set(String(inst.id), inst)
        pending.delete(String(inst.id))
      }
      const total = Number(res.data?.pagination?.total_count || 0)
      if (total && page * 100 >= total) break
    }
    return ids
      .map((id) => byId.get(id)?.name || byId.get(id)?.code || id)
      .join('、')
  } catch (e) {
    logger.warn('[permissionService] hydrateIdExpressionDisplay failed:', resourceType, e)
    return ''
  }
}

/**
 * 加载角色的权限规则
 * @param {number} roleId
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function loadPermissionRules(roleId, params = {}) {
  const r = await apiV2.get('/bo/permission_rule', { params: { role_id: roleId, ...params } })
  // v2 返回分页格式，适配为 v1 格式 {data: {role_id, rules: [...]}}
  if (r.success && r.data?.items) {
    return { success: true, data: { role_id: roleId, rules: r.data.items } }
  }
  return r
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
 * [v41 2026-08-27] 保存角色「资源 × 动作」矩阵手动授权
 *
 * 入参 cells: [{ resource_type, action, granted }, ...]
 * 后端保证：granted=true → INSERT/确保 role_permissions；granted=false → DELETE。
 *
 * @param {number} roleId
 * @param {Array<{resource_type:string, action:string, granted:boolean}>} cells
 * @returns {Promise<object>}
 */
export async function saveResourceActionMatrix(roleId, cells) {
  return await apiV1.put(`/roles/${roleId}/resource-action-matrix`, { cells })
}

/**
 * [2026-08-28] 角色权限一致性体检（替代原「模拟预览」占位按钮）
 * 6 项校验：不可达功能权限 / 空授权菜单 / 写权限无数据范围 /
 * 范围无关联菜单 / 残留排除记录 / 超级权限提示
 * @param {number} roleId
 * @returns {Promise<object>} { ok, issues[], summary }
 */
export async function runPermissionAudit(roleId) {
  return await apiV1.get(`/roles/${roleId}/permission-audit`)
}

/**
 * [2026-08-28] 一键清理体检发现的残留排除记录（安全：不动 granted=1 授权行）
 * @param {number} roleId
 * @returns {Promise<object>} { deleted_residual_excludes[], deleted_count }
 */
export async function cleanupPermissionResidue(roleId) {
  return await apiV1.post(`/roles/${roleId}/permission-audit/cleanup`)
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
 * [v48 2026-08-27] 更新条件规则（v2 PUT，写 data_permission_rules 统一表）
 * @param {number|string} ruleId
 * @param {object} patch  { condition, inherit_to_children, propagate_to_parents, ... }
 */
export async function updateConditionRule(ruleId, patch) {
  return await apiV2.put(`/permission-rules/${ruleId}`, patch)
}

/**
 * 搜索用户（用于批量授权）
 * @param {string} keyword
 * @param {object} [params]
 * @returns {Promise<object>}
 */
export async function searchUsers(keyword, params = {}) {
  return await apiV2.get('/bo/user', { params: { keyword, page_size: 20, ...params } })
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
  RESOURCE_LABELS,
  IDENTITY_RESOURCE_TYPES,
  // 动态映射生成（从 hierarchies.yaml 配置）
  buildDimensionMapsFromConfig,
  // 纯函数
  getPermissionLevelType,
  getPermissionLevelLabel,
  getResourceLabel,
  getActionLabel,
  getDimensionName,
  // 元数据缓存（P1-Base-03）
  loadPermissionMeta,
  invalidatePermissionMetaCache,
  loadPermissionMetaWithScope,
  ScopeCodeInvalidError,
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
  saveResourceActionMatrix,
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
