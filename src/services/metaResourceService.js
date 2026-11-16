/**
 * metaResourceService - YAML 声明式资源页执行器（S8）
 *
 * 只服务 ui-meta 的三个声明块：
 *   list.data_source  { url, method, items_path, total_path, params_map }
 *   list.stats        { url, method, items_from }
 *   list.actions[]    { position, dialog, http, confirm, success_message,
 *                       refresh, enabled_when }
 *
 * 纪律：不引入前端表达式语言。
 *   - URL 占位符只支持 {row.<field>} / {id}
 *   - 文案占位符只支持 {row.<field>} / {data.<field>}
 *   - enabled_when 只支持 { field, in: [] }
 */
import { apiV1, apiV2 } from '@/utils/httpClient'
import { ElMessageBox } from 'element-plus'

const API_V2_PREFIX = '/api/v2'
const API_V1_PREFIX = '/api/v1'

const JSON_FIELD_TYPES = new Set(['json', 'object'])
const NUMBER_WIDGETS = new Set(['number', 'integer', 'float', 'decimal'])

/** 按点路径取值（'data.items' → source.data.items） */
export function pathGet(source, dotPath) {
  if (source === null || source === undefined || !dotPath) return undefined
  return String(dotPath)
    .split('.')
    .filter(Boolean)
    .reduce((acc, key) => (acc === null || acc === undefined ? undefined : acc[key]), source)
}

/** YAML 里的 URL 带 /api/v2 前缀，apiV2 命名空间会统一拼接，故此处裁掉 */
export function toApiPath(url) {
  const text = String(url || '')
  if (!text) return text
  if (!text.startsWith(API_V2_PREFIX)) return text
  const rest = text.slice(API_V2_PREFIX.length)
  return rest || '/'
}

/**
 * 按 URL 前缀选择 httpClient 命名空间（v1 / v2）。
 * 声明式 data_source / action 允许指向存量 v1 端点，避免拼成 /api/v2/api/v1/...。
 *
 * @returns {{namespace: object, path: string}}
 */
export function resolveRequest(url) {
  const text = String(url || '')
  if (text.startsWith(API_V1_PREFIX)) {
    return { namespace: apiV1, path: text.slice(API_V1_PREFIX.length) || '/' }
  }
  if (text.startsWith(API_V2_PREFIX)) {
    return { namespace: apiV2, path: text.slice(API_V2_PREFIX.length) || '/' }
  }
  return { namespace: apiV2, path: text }
}

/**
 * 排序桥接（D7）：params_map 同时声明 sort_field / sort_direction 时，
 * 把前端 ordering（'-field' / 'field'）拆成两个后端参数并删除 ordering。
 * 未声明时原样返回，现有资源页零影响。
 */
export function applyOrderingBridge(params, paramsMap) {
  const map = paramsMap || {}
  const fieldKey = map.sort_field
  const directionKey = map.sort_direction
  const ordering = params?.ordering
  if (!fieldKey || !directionKey || !ordering) return params
  const text = String(ordering)
  const desc = text.startsWith('-')
  const result = { ...params }
  result[fieldKey] = desc ? text.slice(1) : text
  result[directionKey] = desc ? 'desc' : 'asc'
  delete result.ordering
  return result
}

/** params_map 的方向是「后端参数名 → 前端参数名」，这里反转为前端 → 后端 */
function invertParamsMap(paramsMap) {
  const result = {}
  Object.entries(paramsMap || {}).forEach(([backendKey, frontKey]) => {
    if (frontKey) result[frontKey] = backendKey
  })
  return result
}

function compactParams(source) {
  const result = {}
  Object.entries(source || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    result[key] = value
  })
  return result
}

/**
 * 构造 MetaListPage 的 fetcher。
 *
 * @param {object} dataSource - ui-meta list.data_source
 * @param {object|Function} extraParams - 页面级额外查询参数（前端参数名）
 * @returns {(params: object) => Promise<{success:boolean, data:{items:Array,total:number}}>}
 */
export function buildFetcher(dataSource, extraParams = {}) {
  const config = dataSource || {}
  const itemsPath = config.items_path || 'data.items'
  const totalPath = config.total_path || 'data.total'
  const frontToBackend = invertParamsMap(config.params_map)

  const resolveExtra = () => (typeof extraParams === 'function' ? extraParams() : extraParams)

  return async (params = {}) => {
    const merged = applyOrderingBridge(compactParams({
      ...compactParams(resolveExtra() || {}),
      ...compactParams(params),
    }), config.params_map)
    const query = {}
    Object.entries(merged).forEach(([key, value]) => {
      const backendKey = frontToBackend[key] || key
      query[backendKey] = value
    })

    const { namespace, path } = resolveRequest(config.url)
    const result = await namespace.get(path, { params: query })
    // 命名空间已把响应体 body.data 解包到 result.data，这里按 YAML 的
    // items_path/total_path（如 'data.items'）在包一层 data 的根上取值，
    // 兼容两种后端返回（带/不带 data 包装）；total 再回退顶层透传值。
    const root = { data: result?.data }
    const items = pathGet(root, itemsPath) ?? pathGet(result?.data, itemsPath)
    const total = pathGet(root, totalPath) ?? pathGet(result?.data, totalPath) ?? result?.total
    const list = Array.isArray(items) ? items : []
    const meta = result?.data?.meta
    return {
      success: !!result && result.success !== false,
      data: {
        items: list,
        total: total === undefined ? list.length : total,
        // 仅当响应含 meta（如 /api/v2/jobs/runs 的 meta.filters）时附加，供页面维持动态筛选选项。
        ...(meta ? { meta } : {}),
      },
      message: result?.message || '',
    }
  }
}

/** 取指标条数据：stats 块声明取值来源，不做任何二次聚合 */
export async function fetchStats(statsConfig) {
  if (!statsConfig?.url) return null
  const result = await apiV2.get(toApiPath(statsConfig.url))
  if (!result?.success) return null
  const from = statsConfig.items_from || 'by_status'
  const items = pathGet(result.data, from)
  return {
    ...(result.data || {}),
    items: Array.isArray(items) ? items : [],
  }
}

export function isActionEnabled(action, row) {
  const rule = action?.enabled_when
  if (!rule || !rule.field) return true
  const allowed = Array.isArray(rule.in) ? rule.in : (rule.in === undefined ? null : [rule.in])
  if (!allowed) return true
  const current = row ? row[rule.field] : undefined
  return allowed.map((item) => String(item)).includes(String(current))
}

// ------------------------------------------------------------ 条件可见性（M0）
// 封闭文法：{ field, in | equals | not_empty }；未知形式按「可见/可编辑」降级。
// roles 仅展示层过滤，且未注入角色上下文时不隐藏（后端仍鉴权）。

let _currentRoles = null
const _warnedKeys = new Set()

/** 注入当前用户角色；传 null 关闭角色过滤（默认放行）。 */
export function setCurrentRoles(roles) {
  _currentRoles = Array.isArray(roles) ? roles : null
}

/** 同一 objectType+code 只告警一次，避免列表滚动刷屏。 */
export function warnOnce(objectType, code, message) {
  const key = `${objectType || 'unknown'}:${code}`
  if (_warnedKeys.has(key)) return
  _warnedKeys.add(key)
  console.warn(`[meta-ui] ${key}: ${message}`)
}

export function rolesAllowed(roles) {
  if (!Array.isArray(roles) || roles.length === 0) return true
  if (!Array.isArray(_currentRoles)) return true
  return roles.some((role) => _currentRoles.includes(role))
}

export function evalCondition(condition, row) {
  if (!condition || typeof condition !== 'object') return true
  const field = condition.field
  if (!field) return true
  const current = row ? row[field] : undefined
  if (Array.isArray(condition.in)) {
    return condition.in.map((item) => String(item)).includes(String(current))
  }
  if (Object.prototype.hasOwnProperty.call(condition, 'equals')) {
    if (current === condition.equals) return true
    if (current === null || current === undefined) return false
    return String(current) === String(condition.equals)
  }
  if (Object.prototype.hasOwnProperty.call(condition, 'not_empty')) {
    const empty = current === null || current === undefined || current === ''
    return condition.not_empty ? !empty : empty
  }
  return true
}

export function isVisible(decl, row) {
  if (!decl) return true
  return rolesAllowed(decl.roles) && evalCondition(decl.visible_when, row)
}

export function isActionVisible(action, row) {
  return isVisible(action, row)
}

/** 后端 field_policies 优先；readonly_when 条件命中 → 只读（不隐藏）。 */
export function isFieldReadonly(field, row, policies = {}) {
  if (!field) return true
  const policy = policies?.[field.key]
  if (policy && policy.writable === false) return true
  if (!rolesAllowed(field.roles)) return true
  if (field.readonly) return true
  return evalCondition(field.readonly_when, row)
}

export function mergeFieldPolicies(fieldPolicies = {}, localDecl = {}) {
  const key = localDecl.key || localDecl.field
  const policy = fieldPolicies?.[key] || {}
  return {
    ...localDecl,
    readable: policy.readable !== undefined ? policy.readable : localDecl.readable !== false,
    writable: policy.writable !== undefined ? policy.writable : localDecl.writable !== false,
    roles: (policy.roles && policy.roles.length) ? policy.roles : (localDecl.roles || []),
    readonly_when: policy.readonly_when || localDecl.readonly_when || null,
  }
}

/** URL 占位符：{row.x} / {id} */
export function resolveActionUrl(action, row) {
  const template = action?.http?.url || ''
  return toApiPath(template.replace(/\{(?:row\.)?([\w.]+)\}/g, (match, key) => {
    const value = pathGet(row, key)
    return encodeURIComponent(value === null || value === undefined ? '' : value)
  }))
}

/** 文案占位符：{row.x} / {data.x} */
export function renderTemplate(text, { row = null, data = null } = {}) {
  if (!text) return ''
  return String(text).replace(/\{([^{}]+)\}/g, (match, token) => {
    let value
    if (token.startsWith('row.')) value = pathGet(row, token.slice(4))
    else if (token.startsWith('data.')) value = pathGet(data, token.slice(5))
    else value = row ? row[token] : undefined
    return value === null || value === undefined ? '' : String(value)
  })
}

async function confirmAction(action, row) {
  const message = renderTemplate(action?.confirm, { row })
  if (!message) return true
  try {
    await ElMessageBox.confirm(message, action.confirm_title || '确认操作', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}

/**
 * 执行声明式动作（confirm → http → 成功文案）。
 *
 * @returns {Promise<{ok:boolean, canceled?:boolean, skip?:boolean, message?:string, data?:any}>}
 */
export async function runAction(action, { row = null, body } = {}) {
  const http = action?.http
  if (!http?.url) return { ok: true, skip: true }

  const confirmed = await confirmAction(action, row)
  if (!confirmed) return { ok: false, canceled: true }

  const resolved = resolveActionUrl(action, row)
  const { namespace, path } = resolveRequest(resolved)
  const method = String(http.method || 'post').toLowerCase()

  let result
  try {
    if (method === 'get') {
      result = await namespace.get(path, body === undefined ? undefined : { params: body })
    } else if (method === 'delete') {
      result = await namespace.delete(path, body === undefined ? undefined : { body })
    } else if (typeof namespace[method] === 'function') {
      result = await namespace[method](path, body === undefined ? {} : body)
    } else {
      return { ok: false, message: `不支持的 HTTP 方法: ${method}` }
    }
  } catch (error) {
    return { ok: false, message: error?.message || '请求失败' }
  }

  const message = renderTemplate(action?.success_message, { row, data: result?.data })
  if (result?.success === false) {
    return { ok: false, message: result?.message || message || '操作失败', data: result?.data }
  }
  return { ok: true, message, data: result?.data }
}

// ---------------------------------------------------------------- 通用表单

/** ui-meta form.fields → MetaForm 控件声明 */
export function toFormControls(fields, {
  editing = false, keyField = 'code', model = null, policies = {},
} = {}) {
  return (fields || []).map((field) => {
    const widget = field.widget || field.field_type || 'text'
    let type = 'text'
    if (widget === 'switch') type = 'switch'
    else if (widget === 'select' || (field.options || []).length) type = 'select'
    else if (widget === 'textarea') type = 'textarea'
    else if (widget === 'password') type = 'password'
    else if (NUMBER_WIDGETS.has(widget)) type = 'number'

    const readonlyByCondition = isFieldReadonly(
      { key: field.key, readonly: field.readonly, roles: field.roles, readonly_when: field.readonly_when },
      model,
      policies,
    )

    return {
      key: field.key,
      label: field.label,
      type,
      required: !!field.required,
      // 业务主键编辑态只读（连接页的 code）+ 字段策略/条件只读
      disabled: readonlyByCondition || (!!editing && field.key === keyField),
      placeholder: field.placeholder || '',
      defaultValue: field.default ?? (type === 'switch' ? false : ''),
      options: (field.options || []).map((opt) => ({ value: opt.value, label: opt.label })),
    }
  })
}

function isJsonField(field) {
  return !!field && JSON_FIELD_TYPES.has(field.field_type)
}

export function emptyFormModel(metaFields) {
  const model = {}
  ;(metaFields || []).forEach((field) => {
    model[field.key] = isJsonField(field)
      ? ''
      : (field.widget === 'switch' ? !!field.default : (field.default ?? ''))
  })
  return model
}

export function formModelFromRow(metaFields, row) {
  const model = {}
  ;(metaFields || []).forEach((field) => {
    const value = row ? row[field.key] : undefined
    if (isJsonField(field)) {
      model[field.key] = value ? JSON.stringify(value, null, 2) : ''
      return
    }
    if (field.widget === 'switch') {
      model[field.key] = value === undefined || value === null ? !!field.default : !!value
      return
    }
    model[field.key] = value ?? field.default ?? ''
  })
  return model
}

/** 表单模型 → 请求体；JSON 字段做语法校验，空值不提交 */
export function payloadFromForm(metaFields, model, { editing = false, keyField = 'code' } = {}) {
  const payload = {}
  Object.entries(model || {}).forEach(([key, value]) => {
    if (editing && key === keyField) return
    const field = (metaFields || []).find((item) => item.key === key)
    if (isJsonField(field)) {
      const text = String(value ?? '').trim()
      if (!text) return
      try {
        payload[key] = JSON.parse(text)
      } catch {
        throw new Error(`${key} 不是合法 JSON`)
      }
      return
    }
    if (value === '' || value === null) return
    payload[key] = value
  })
  return payload
}
