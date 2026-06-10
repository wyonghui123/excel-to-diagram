/**
 * columnOrderService - 列序策略服务
 *
 * 业务职责：统一处理 el-table-column 的列顺序,支持 3 种策略:
 *   1. yaml_position - 严格按 YAML 中 position 字段排序 (兼容老 yaml)
 *   2. manual        - 业务方手动指定列顺序
 *   3. smart_default - 6 桶智能规则(默认):
 *        business_key(10) → primary(20) → status(30) → parent_ref(40) → business(50) → system(90)
 *
 * 关键设计:
 *   - 零破坏: yaml_position 模式下,所有列都按 position 升序
 *   - 零破坏: smart_default 模式下,**有 position 的列保持原位**, 无 position 的列按 6 桶规则追加到尾部
 *   - 覆盖: override.business_keys / primary_fields / status_fields 显式指定后,优先级最高
 *   - 父级引用桶内按 hierarchy.level 升序(根节点在前)
 *
 * @module services/columnOrderService
 */

/**
 * 6 桶定义 (按 weight 升序 = 默认输出顺序)
 */
export const COLUMN_BUCKETS = Object.freeze({
  BUSINESS_KEY: { id: 'business_key', weight: 10, label: '业务键' },
  PRIMARY:      { id: 'primary',      weight: 20, label: '主标识' },
  STATUS:       { id: 'status',       weight: 30, label: '分类/状态' },
  PARENT_REF:   { id: 'parent_ref',   weight: 40, label: '父级引用' },
  BUSINESS:     { id: 'business',     weight: 50, label: '业务属性' },
  SYSTEM:       { id: 'system',       weight: 90, label: '系统字段' },
})

/**
 * 系统字段识别集合 (system 桶)
 */
const SYSTEM_FIELD_KEYS = new Set([
  'id', 'uuid',
  'created_at', 'created_by', 'updated_at', 'updated_by',
  'deleted_at', 'is_deleted',
])

/**
 * 状态/分类字段识别集合 (status 桶)
 * 注意:只按字段名识别,业务方可在 override 中改判
 */
const STATUS_FIELD_KEYS = new Set([
  'status', 'state', 'type', 'category', 'kind',
  'is_active', 'is_enabled', 'enabled', 'active',
])

/**
 * 父级引用字段识别 (parent_ref 桶)
 * 命中规则: field.hierarchy.parent_id 等于自己 或 field.semantics === 'parent_key'
 *          或字段名以 _id/_key 结尾且 field.foreign_key === true
 */
const PARENT_REF_FIELD_KEYS_SUFFIX = ['_id', '_key', 'parent_id', 'parent_key', 'parent_code']

/**
 * 业务方显式覆盖配置(可选)
 *
 * @typedef {Object} ColumnOrderOverride
 * @property {string[]} [business_keys] - 强制划入 business_key 桶
 * @property {string[]} [primary_fields] - 强制划入 primary 桶
 * @property {string[]} [status_fields] - 强制划入 status 桶
 * @property {string[]} [parent_ref_fields] - 强制划入 parent_ref 桶
 * @property {string[]} [system_fields] - 强制划入 system 桶
 */

/**
 * @typedef {Object} ColumnOrderConfig
 * @property {'yaml_position'|'manual'|'smart_default'} [strategy='smart_default']
 * @property {string[]} [manual_order] - manual 策略下的列顺序
 * @property {ColumnOrderOverride} [override] - smart_default 策略下的桶强制覆盖
 */

/**
 * 主入口: 按配置对列进行排序
 *
 * @param {Array} columns - 列配置数组
 * @param {Array} [fields=[]] - 字段元数据(用于判断 semantics/hierarchy)
 * @param {ColumnOrderConfig} [config={}] - 列序配置
 * @returns {Array} 排序后的列(新数组,不影响原数组)
 */
export function sortColumnsByDefaultOrder(columns, fields = [], config = {}) {
  if (!Array.isArray(columns) || columns.length === 0) {
    return []
  }

  const strategy = config.strategy || 'smart_default'

  if (strategy === 'yaml_position') {
    return yamlPositionSort(columns)
  }

  if (strategy === 'manual') {
    return manualSort(columns, config.manual_order || [])
  }

  return smartDefaultSort(columns, fields, config)
}

/**
 * yaml_position 策略: 严格按 position 升序,无 position 的列追加到尾部
 *
 * @param {Array} columns
 * @returns {Array}
 */
function yamlPositionSort(columns) {
  return [...columns].sort((a, b) => {
    const pa = positionOf(a)
    const pb = positionOf(b)
    if (pa === pb) return 0
    // 都无 position 保持原顺序
    if (pa === null && pb === null) return 0
    // 无 position 的追加到尾部
    if (pa === null) return 1
    if (pb === null) return -1
    return pa - pb
  })
}

/**
 * manual 策略: 按 manual_order 给定的 key 顺序排序
 *
 * @param {Array} columns
 * @param {string[]} manualOrder
 * @returns {Array}
 */
function manualSort(columns, manualOrder) {
  if (!Array.isArray(manualOrder) || manualOrder.length === 0) {
    return [...columns]
  }
  // 用目标位置排序: manual_order 的第一个出现位置 → 目标数组下标
  // 遍历而非 Map,保证保留每个 key 的第一个出现位置(后者不覆盖前者)
  const orderMap = new Map()
  manualOrder.forEach((key, idx) => {
    const k = String(key)
    if (!orderMap.has(k)) orderMap.set(k, idx)
  })
  const listed = columns.filter(col => orderMap.has(keyOf(col)))
  const unlisted = columns.filter(col => !orderMap.has(keyOf(col)))
  const listedSorted = [...listed].sort((a, b) => {
    const pa = orderMap.get(keyOf(a)) ?? Infinity
    const pb = orderMap.get(keyOf(b)) ?? Infinity
    return pa - pb
  })
  return [...listedSorted, ...unlisted]
}

/**
 * smart_default 策略: 6 桶智能规则
 *
 * 步骤:
 *   1. 分离"有 position 的列"和"无 position 的列"
 *   2. 有 position 的列按 position 升序(保持原位,零破坏)
 *   3. 无 position 的列进 6 桶分类
 *   4. 每桶内按字段 hierarchy.level 升序,同 level 按字母序
 *   5. 合并输出
 *
 * @param {Array} columns
 * @param {Array} fields
 * @param {ColumnOrderConfig} config
 * @returns {Array}
 */
function smartDefaultSort(columns, fields, config) {
  const fieldMap = buildFieldMap(fields)
  const override = config.override || {}

  // 1. 分离
  const explicit = []
  const inferred = []
  for (const col of columns) {
    if (positionOf(col) !== null) {
      explicit.push(col)
    } else {
      inferred.push(col)
    }
  }

  // 2. 显式列按 position 升序
  explicit.sort((a, b) => positionOf(a) - positionOf(b))

  // 3. 推断列进 6 桶
  const buckets = {
    business_key: [],
    primary: [],
    status: [],
    parent_ref: [],
    business: [],
    system: [],
  }
  for (const col of inferred) {
    const bucketId = classifyField(col, fieldMap, override)
    buckets[bucketId].push(col)
  }

  // 4. 桶内排序
  for (const bucketId of Object.keys(buckets)) {
    buckets[bucketId].sort((a, b) => {
      const ka = keyOf(a)
      const kb = keyOf(b)
      const la = depthOf(a, fieldMap)
      const lb = depthOf(b, fieldMap)
      if (la !== lb) return la - lb
      return ka.localeCompare(kb)
    })
  }

  // 5. 合并: 显式列(有 position)在前 + 智能桶列在后
  return [
    ...explicit,
    ...buckets.business_key,
    ...buckets.primary,
    ...buckets.status,
    ...buckets.parent_ref,
    ...buckets.business,
    ...buckets.system,
  ]
}

/**
 * 6 桶分类 - 单字段分类
 *
 * 优先级:
 *   1. override 显式指定(最高)
 *   2. system 桶 (系统字段)
 *   3. business_key 桶 (YAML 标记 businessKey: true 或 override)
 *   4. primary 桶 (display_name/displayName 或 name + 显式业务键)
 *   5. status 桶 (status/state/type/category 等)
 *   6. parent_ref 桶 (hierarchy.parent_id 等于自己, 或 _id/_key 后缀 + foreign_key)
 *   7. business 桶 (默认)
 *
 * @param {Object} col
 * @param {Map<string, Object>} fieldMap
 * @param {ColumnOrderOverride} override
 * @returns {string} 桶 id
 */
export function classifyField(col, fieldMap, override = {}) {
  const key = keyOf(col)
  if (!key) return 'business'

  // 1. override 优先 (最高优先级)
  if (Array.isArray(override.business_keys) && override.business_keys.includes(key)) {
    return 'business_key'
  }
  if (Array.isArray(override.primary_fields) && override.primary_fields.includes(key)) {
    return 'primary'
  }
  if (Array.isArray(override.status_fields) && override.status_fields.includes(key)) {
    return 'status'
  }
  if (Array.isArray(override.parent_ref_fields) && override.parent_ref_fields.includes(key)) {
    return 'parent_ref'
  }
  if (Array.isArray(override.system_fields) && override.system_fields.includes(key)) {
    return 'system'
  }

  const lower = key.toLowerCase()

  const field = fieldMap.get(key) || fieldMap.get(lower) || {}

  // 2. business_key 桶 (YAML 标记 / semantics 标注 — 优先于 system 兜底)
  if (col.businessKey === true || col.business_key === true) {
    return 'business_key'
  }
  if (field.semantics === 'business_key' || field.semantics === 'businessId') {
    return 'business_key'
  }

  // 3. primary 桶
  if (field.semantics === 'display_name' || field.semantics === 'displayName') {
    return 'primary'
  }
  if (col.label === 'name' || lower === 'name' || lower === 'display_name' || lower === 'displayname') {
    return 'primary'
  }

  // 4. status 桶
  if (STATUS_FIELD_KEYS.has(lower)) {
    return 'status'
  }
  if (field.semantics === 'status' || field.semantics === 'state' || field.semantics === 'category') {
    return 'status'
  }

  // 5. parent_ref 桶
  if (isParentRef(col, field, fieldMap)) {
    return 'parent_ref'
  }

  // 6. system 桶 (兜底: id/uuid/created_at/... 在没有显式业务键标注时)
  if (SYSTEM_FIELD_KEYS.has(lower)) {
    return 'system'
  }

  // 7. business 桶 (默认)
  return 'business'
}

/**
 * 判断字段是否为父级引用
 *
 * 命中规则(任一):
 *   - field.hierarchy.parent_id === field.id (指向自己)
 *   - field.semantics === 'parent_key' / 'parent_id'
 *   - 字段名匹配 PARENT_REF_FIELD_KEYS_SUFFIX + field.foreign_key === true
 *
 * @param {Object} col
 * @param {Object} field
 * @param {Map<string, Object>} fieldMap
 * @returns {boolean}
 */
function isParentRef(col, field, fieldMap) {
  const key = keyOf(col)
  if (!key) return false

  // 规则 1: hierarchy.parent_id 指向自己
  const parentId = field.hierarchy && field.hierarchy.parent_id
  if (parentId && field.id && parentId === field.id) {
    return true
  }

  // 规则 2: semantics 标注
  const sem = field.semantics
  if (sem === 'parent_key' || sem === 'parent_id' || sem === 'parent') {
    return true
  }

  // 规则 3: 字段名 + foreign_key 标记
  const lower = key.toLowerCase()
  const isIdLike = PARENT_REF_FIELD_KEYS_SUFFIX.some(suffix => lower.endsWith(suffix) || lower === suffix)
  if (isIdLike && (field.foreign_key === true || field.foreignKey === true || field.isForeignKey === true)) {
    return true
  }

  return false
}

/**
 * 计算字段在 hierarchy 上的深度(根节点 level=0,子节点递增)
 * 同一桶内按 level 升序 = 根节点在前
 *
 * @param {Object} col
 * @param {Map<string, Object>} fieldMap
 * @returns {number}
 */
function depthOf(col, fieldMap) {
  const key = keyOf(col)
  if (!key) return 0
  const field = fieldMap.get(key) || fieldMap.get(key.toLowerCase()) || {}
  if (field.hierarchy && typeof field.hierarchy.level === 'number') {
    return field.hierarchy.level
  }
  return 0
}

/**
 * 提取列的 key(prop 优先,key 兜底)
 */
function keyOf(col) {
  return String(col.prop || col.key || col.field || col.id || '')
}

/**
 * 提取列的 position(数字类型才返回,否则 null)
 */
function positionOf(col) {
  const p = col.position
  if (typeof p === 'number' && Number.isFinite(p)) return p
  return null
}

/**
 * 构造 fields 数组 → Map, 兼容大小写查询
 */
function buildFieldMap(fields) {
  const map = new Map()
  if (!Array.isArray(fields)) return map
  for (const f of fields) {
    if (!f) continue
    if (f.name) map.set(String(f.name), f)
    if (f.id) map.set(String(f.id), f)
    if (f.code) map.set(String(f.code), f)
  }
  return map
}

export default {
  sortColumnsByDefaultOrder,
  classifyField,
  COLUMN_BUCKETS,
}
