/**
 * jobParams - 作业参数元数据适配（spec §12.2.2，纯函数）
 *
 * 职责:
 *   · 把后端 `params_schema` 映射为 `MetaForm.fields`（元数据驱动，页面不写字段）；
 *   · 生成表单初始值（schema.default 兜底）；
 *   · 本地时间 → epoch 秒（后端唯一时间口径）。
 *
 * 边界:
 *   · 不实现任何参数校验 —— 唯一校验来源是后端 `sanitize_params`（spec IF-005）；
 *   · 不猜测类型：schema 缺失/为空时返回空表单，不渲染任何字段。
 */

//: 与后端 `job_params.SECRET_KEY_PARTS` 保持同源（仅用于选择 password 控件）。
export const SECRET_KEY_PARTS = ['password', 'token', 'secret', 'key']

//: 后端脱敏占位（spec NFR-006）：提交前必须剔除，避免把占位写回真实密钥。
export const REDACTED_PLACEHOLDER = '***'

/**
 * 键名是否按密钥处理（与后端 `is_secret_field` 同规则）。
 * @param {string} key
 * @returns {boolean}
 */
export function isSecretKey(key) {
  const name = String(key || '').toLowerCase()
  return SECRET_KEY_PARTS.some((part) => name.includes(part))
}

/**
 * 取 properties（schema 可能为 null / 非对象）。
 * @param {object|null|undefined} schema
 * @returns {object}
 */
function propertiesOf(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return {}
  const properties = schema.properties
  return properties && typeof properties === 'object' && !Array.isArray(properties)
    ? properties
    : {}
}

/**
 * `params_schema` → `MetaForm.fields`。
 * 映射: string→text / integer|number→number / boolean→switch /
 *       enum→select / const→text(disabled) / secret→password。
 * @param {object|null|undefined} schema
 * @returns {Array<object>}
 */
export function schemaToFields(schema) {
  const properties = propertiesOf(schema)
  const required = Array.isArray(schema && schema.required) ? schema.required : []
  return Object.keys(properties).map((key) => {
    const spec = (properties[key] && typeof properties[key] === 'object')
      ? properties[key]
      : {}
    const ui = (spec['x-ui'] && typeof spec['x-ui'] === 'object') ? spec['x-ui'] : {}
    const field = {
      key,
      label: ui.label || spec.title || key,
      required: required.includes(key)
    }
    if (spec.description) field.placeholder = spec.description

    if (ui.secret === true || isSecretKey(key)) {
      field.type = 'password'
      return field
    }
    if (spec.type === 'boolean') {
      field.type = 'switch'
      return field
    }
    if (spec.type === 'integer' || spec.type === 'number') {
      field.type = 'number'
      return field
    }
    if (Array.isArray(spec.enum) && spec.enum.length > 0) {
      field.type = 'select'
      field.options = spec.enum.map((value) => ({
        label: (ui.enum_labels && ui.enum_labels[value]) || String(value),
        value
      }))
      return field
    }
    field.type = 'text'
    if (Object.prototype.hasOwnProperty.call(spec, 'const')) field.disabled = true
    return field
  })
}

/**
 * 生成表单初始值：显式值优先，其次 `spec.default`，其余不出现。
 * @param {object|null|undefined} schema
 * @param {object|null|undefined} values
 * @returns {object}
 */
export function buildDefaults(schema, values) {
  const properties = propertiesOf(schema)
  const source = (values && typeof values === 'object') ? values : {}
  const result = {}
  Object.keys(properties).forEach((key) => {
    const spec = (properties[key] && typeof properties[key] === 'object')
      ? properties[key]
      : {}
    if (source[key] !== undefined) {
      result[key] = source[key]
    } else if (Object.prototype.hasOwnProperty.call(spec, 'default')) {
      result[key] = spec.default
    }
  })
  return result
}

/**
 * 剔除后端脱敏占位，避免把 `***` 当真实值提交。
 * @param {object|null|undefined} values
 * @returns {object}
 */
export function stripRedacted(values) {
  const source = (values && typeof values === 'object' && !Array.isArray(values))
    ? values
    : {}
  const result = {}
  Object.keys(source).forEach((key) => {
    if (source[key] === REDACTED_PLACEHOLDER) return
    result[key] = source[key]
  })
  return result
}

/**
 * 本地时间 / ISO8601 / epoch → epoch 秒；非法输入返回 null（交后端 400）。
 * @param {Date|number|string|null|undefined} value
 * @returns {number|null}
 */
export function toEpochSeconds(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number') {
    return Number.isFinite(value) ? Math.floor(value) : null
  }
  if (value instanceof Date) {
    const ts = value.getTime()
    return Number.isNaN(ts) ? null : Math.floor(ts / 1000)
  }
  const text = String(value).trim()
  if (/^-?\d+$/.test(text)) return Number(text)
  const parsed = Date.parse(text)
  return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000)
}