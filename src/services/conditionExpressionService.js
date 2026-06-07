/**
 * conditionExpressionService - 条件表达式 DSL 服务层
 *
 * FR-UI-008: 封装条件表达式的生成、翻译、解析逻辑
 * 消除 ConditionRuleDialog.vue 和 ConditionRuleEditor.vue 中的重复实现
 *
 * 所有函数均为纯函数，无 IO 副作用，便于单测
 */

/**
 * @typedef {Object} DimConfig
 * @property {string} dim        // dimension code
 * @property {string} op         // 操作符：=, !=, IN, NOT IN, LIKE, >, <, >=, <=
 * @property {string|number|string[]} value
 *
 * @typedef {Object} Dimension
 * @property {string} code
 * @property {string} name
 * @property {string} [field]    // 数据库字段名（可能与 code 不同）
 * @property {string} [cascade_parent]
 *
 * @typedef {Object} ValueNameMap
 * @property {string} [key]     // "dimCode_valueId" → display name
 */

// ==================== 字段名映射（后备） ====================

const FIELD_LABEL_MAP = {
  domain_id: '领域',
  sub_domain_id: '子领域',
  service_module_id: '服务模块',
  business_object_id: '业务对象',
  version_id: '版本',
  product_id: '产品',
  status: '状态',
  owner_id: '负责人',
  created_by: '创建人',
  organization_id: '组织',
  department_id: '部门',
  employee_id: '员工',
}

// ==================== 核心函数 ====================

/**
 * 根据维度配置生成条件表达式
 *
 * 示例:
 *   buildConditionFromDimensions(
 *     [{dim:'domain_id', op:'=', value:5}, {dim:'status', op:'IN', value:['active','draft']}],
 *     [{code:'domain_id', field:'domain_id'}, {code:'status', field:'status'}],
 *     'AND'
 *   )
 *   → "domain_id = 5 AND status IN ('active', 'draft')"
 *
 * @param {Object} dimConfigs - { dimCode: { operator, value, selectedValues } }
 * @param {Dimension[]} dimensions - 维度元数据
 * @param {'AND'|'OR'|'CUSTOM'} mode
 * @returns {string} 条件表达式字符串
 */
export function buildConditionFromDimensions(dimConfigs, dimensions, mode = 'AND') {
  if (!dimConfigs || mode === 'CUSTOM') return ''

  const parts = []
  for (const [code, config] of Object.entries(dimConfigs)) {
    const dim = dimensions.find(d => d.code === code)
    if (!dim || !config) continue

    const fieldName = dim.field || dim.code
    const op = (config.operator || '=').toUpperCase()

    if (op === 'IN') {
      const values = config.selectedValues?.map(v => v.id) || []
      if (values.length > 0) {
        parts.push(`${fieldName} IN (${values.join(', ')})`)
      }
    } else if (op === 'NOT IN') {
      const values = Array.isArray(config.value) ? config.value : [config.value]
      if (values.length > 0) {
        const formatted = values.map(v => typeof v === 'number' ? v : `'${v}'`)
        parts.push(`${fieldName} NOT IN (${formatted.join(', ')})`)
      }
    } else if (op === 'LIKE') {
      if (config.value) {
        parts.push(`${fieldName} LIKE '%${config.value}%'`)
      }
    } else if (op === '!=') {
      if (config.value) {
        parts.push(`${fieldName} != ${config.value}`)
      }
    } else if (op === '>' || op === '>=' || op === '<' || op === '<=') {
      if (config.value !== undefined && config.value !== '') {
        parts.push(`${fieldName} ${op} ${config.value}`)
      }
    } else {
      // 默认 =
      if (config.value) {
        const v = isNaN(config.value) ? `'${config.value}'` : config.value
        parts.push(`${fieldName} = ${v}`)
      }
    }
  }

  return parts.join(` ${mode} `)
}

/**
 * 将技术条件表达式翻译为用户友好的中文描述
 *
 * @param {string} condition - 条件表达式
 * @param {Object} dimConfigs - { dimCode: { operator, value, selectedValues } }
 * @param {ValueNameMap} valueNameMap - "dimCode_valueId" → display name
 * @param {Dimension[]} dimensions - 维度元数据
 * @param {Object} [options]
 * @param {string} [options.mode] - 'dimension'|'custom'
 * @param {string} [options.customCondition] - 自定义条件文本
 * @param {string} [options.backendFriendly] - 后端返回的友好描述
 * @returns {string} 友好描述
 */
export function translateToFriendlyCondition(condition, dimConfigs, valueNameMap, dimensions, options = {}) {
  if (!condition && !options.customCondition) return ''

  // 编辑模式下优先使用后端返回的友好描述（带质量门）
  if (options.backendFriendly) {
    const backend = String(options.backendFriendly).trim()
    if (backend) {
      const looksUntranslated =
        /_id\b/i.test(backend) ||
        /\b(IN|AND|OR)\b/.test(backend) ||
        /^\s*[\w_]+\s*(=|!=)/.test(backend)
      if (!looksUntranslated) {
        return backend
      }
    }
  }

  // 自定义模式
  if (options.mode === 'custom' && options.customCondition) {
    return generateSimpleFriendly(options.customCondition, dimensions, valueNameMap)
  }

  // 维度模式：逐条翻译
  if (dimConfigs && Object.keys(dimConfigs).length > 0) {
    const parts = []
    for (const [code, config] of Object.entries(dimConfigs)) {
      const dim = dimensions.find(d => d.code === code)
      if (!dim || !config) continue

      const op = (config.operator || '=').toUpperCase()

      if (op === 'IN') {
        const names = (config.selectedValues || []).map(v => {
          const key = `${dim.code}_${v.id}`
          return valueNameMap[key] || v.display_name || v.id
        })
        if (names.length > 0) {
          parts.push(`${dim.name} 包含于 (${names.join(', ')})`)
        }
      } else if (op === '!=') {
        if (config.value) {
          const key = `${dim.code}_${config.value}`
          const name = valueNameMap[key] || config.value
          parts.push(`${dim.name} ≠ ${name}`)
        }
      } else {
        if (config.value) {
          const key = `${dim.code}_${config.value}`
          const name = valueNameMap[key] || config.value
          parts.push(`${dim.name} = ${name}`)
        }
      }
    }

    if (parts.length > 0) {
      return parts.join(' 且 ')
    }
  }

  // 后备：简单替换
  if (condition) {
    return generateSimpleFriendly(condition, dimensions, valueNameMap)
  }

  return ''
}

/**
 * 简单的友好描述生成器（后备方案）
 *
 * @param {string} condition
 * @param {Dimension[]} [dimensions]
 * @param {ValueNameMap} [valueNameMap]
 * @returns {string}
 */
export function generateSimpleFriendly(condition, dimensions = [], valueNameMap = {}) {
  if (!condition) return ''

  let result = condition

  // 替换字段名（优先使用维度元数据，后备使用 FIELD_LABEL_MAP）
  for (const dim of dimensions) {
    const fieldName = dim.field || dim.code
    if (fieldName !== dim.name) {
      result = result.replace(new RegExp(`\\b${fieldName}\\b`, 'g'), dim.name)
    }
  }
  for (const [field, name] of Object.entries(FIELD_LABEL_MAP)) {
    const regex = new RegExp(`\\b${field}\\b`, 'g')
    result = result.replace(regex, name)
  }

  // 替换操作符
  result = result.replace(/\s*=\s*/g, ' = ')
  result = result.replace(/\s*!=\s*/g, ' ≠ ')
  result = result.replace(/\s+IN\s+/gi, ' 包含于 ')
  result = result.replace(/\s+AND\s+/gi, ' 且 ')
  result = result.replace(/\s+OR\s+/gi, ' 或 ')

  // 移除多余的引号
  result = result.replace(/'([^']+)'/g, '$1')

  // 尝试将 ID 替换为业务名称
  const idPattern = /\b(\d+|[A-Za-z0-9_]+)\b/g
  result = result.replace(idPattern, (match) => {
    for (const [key, value] of Object.entries(valueNameMap)) {
      if (key.endsWith(`_${match}`) || key.endsWith(`_${String(match)}`)) {
        return value
      }
    }
    return match
  })

  return result
}

/**
 * 按层级深度排序维度（父维度在前）
 *
 * @param {Dimension[]} dimensions
 * @param {Object} levelMap - { dimCode: depth }
 * @returns {Dimension[]}
 */
export function sortDimensionsByHierarchy(dimensions, levelMap = {}) {
  return [...dimensions].sort((a, b) => {
    const depthA = levelMap[a.code] ?? 0
    const depthB = levelMap[b.code] ?? 0
    return depthA - depthB
  })
}

/**
 * 过滤隐藏维度
 *
 * @param {Dimension[]} dimensions
 * @param {string[]} hiddenList
 * @returns {Dimension[]}
 */
export function filterHiddenDimensions(dimensions, hiddenList = []) {
  if (!hiddenList.length) return dimensions
  return dimensions.filter(d => !hiddenList.includes(d.code))
}

/**
 * 解析条件表达式为维度配置
 *
 * @param {string} condition - 条件表达式字符串
 * @param {Dimension[]} dimensions - 维度元数据
 * @returns {{ matched: Object, unmatched: boolean }} matched = { dimCode: { operator, value, selectedValues } }
 */
export function parseConditionToDimConfigs(condition, dimensions) {
  if (!condition) return { matched: {}, unmatched: false }

  const parts = condition.split(/\s+AND\s+/i)
  const matched = {}
  let matchedCount = 0

  for (const part of parts) {
    const trimmed = part.trim()

    let field, operator, valueStr
    const inMatch = trimmed.match(/^(\w+)\s+IN\s*\(([^)]+)\)$/)
    if (inMatch) {
      field = inMatch[1]
      operator = 'IN'
      valueStr = inMatch[2].trim()
    } else {
      const eqMatch = trimmed.match(/^(\w+)\s*(=|!=)\s*(.+)$/)
      if (eqMatch) {
        field = eqMatch[1]
        operator = eqMatch[2]
        valueStr = eqMatch[3].trim().replace(/'/g, '')
      } else {
        continue
      }
    }

    const dim = dimensions.find(d => (d.field || d.code) === field)
    if (!dim) continue

    matchedCount++

    if (!matched[dim.code]) {
      matched[dim.code] = {
        operator,
        value: '',
        displayValue: '',
        selectedValues: [],
        searchText: '',
      }
    }

    const config = matched[dim.code]
    config.operator = operator

    if (operator === 'IN') {
      const ids = valueStr.split(',').map(v => v.trim()).filter(Boolean)
      config.selectedValues = ids.map(id => ({ id, display_name: id }))
      config.value = ids.join(',')
    } else {
      config.value = valueStr
      config.displayValue = valueStr
    }
  }

  return {
    matched,
    unmatched: matchedCount === 0 && !!condition,
  }
}

/**
 * 校验条件表达式是否合法（简单检查）
 *
 * @param {string} condition
 * @returns {boolean}
 */
export function isValidCondition(condition) {
  if (!condition || !condition.trim()) return false
  // 简单检查：至少包含一个比较操作
  return /[=!<>]/.test(condition) || /\bIN\b/i.test(condition) || /\bLIKE\b/i.test(condition)
}

export default {
  buildConditionFromDimensions,
  translateToFriendlyCondition,
  generateSimpleFriendly,
  sortDimensionsByHierarchy,
  filterHiddenDimensions,
  parseConditionToDimConfigs,
  isValidCondition,
}
