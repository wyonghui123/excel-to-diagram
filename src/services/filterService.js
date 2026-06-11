/**
 * FilterService — 元数据驱动过滤器服务
 * 
 * 纯函数服务层，负责所有与过滤相关的纯逻辑。
 * 从 useMetaList.js 抽离，不依赖 Vue 响应式状态。
 *
 * 设计参考：
 *   - SAP SADL (Service Adaptation Definition Language) 过滤框架
 *   - Salesforce LDS (Lightning Data Service) Filter
 *   - 后端 filter_service.py 的设计模式
 *
 * 使用方式：
 *   import { inferFilterType, addFilterParam, buildFilterQueryParams } from '@/services/filterService'
 */

// ======== 工具函数 ========

/**
 * 判断是否为 Vue 内部属性
 * @param {string} key
 * @returns {boolean}
 */
export function isInternalProp(key) {
  return key.startsWith('__v_') ||
    key === 'fn' ||
    key === '_value' ||
    key === 'dep' ||
    key === 'deps' ||
    key === 'depsTail' ||
    key === 'effect' ||
    key === 'flags' ||
    key === 'globalVersion' ||
    key === '__v_isRef' ||
    key === '__v_isReadonly' ||
    key === '__v_isShallow' ||
    key === '__v_isReactive' ||
    key === 'isSSR'
}

/**
 * 格式化日期为 YYYY-MM-DD HH:mm:ss 格式
 * @param {Date|string} date - 日期
 * @param {boolean} isEndTime - 是否是结束时间（自动设置为 23:59:59）
 * @returns {string} 格式化后的日期字符串
 */
export function formatDate(date, isEndTime = false) {
  if (!date) return ''

  if (typeof date === 'string') {
    if (date.includes(' ') || date.includes('T')) {
      return date
    }
    if (isEndTime) {
      return `${date} 23:59:59`
    }
    return `${date} 00:00:00`
  }

  const d = new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')

  if (isEndTime) {
    return `${year}-${month}-${day} 23:59:59`
  }

  const hours = String(d.getHours()).padStart(2, '0')
  const minutes = String(d.getMinutes()).padStart(2, '0')
  const seconds = String(d.getSeconds()).padStart(2, '0')

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

// ======== 类型推断 ========

/**
 * 根据字段属性推断过滤控件类型
 * @param {Object} col - 列/字段定义 { type, widget, options, format }
 * @returns {string} 过滤控件类型：search | select | date-range | number-range
 */
export function inferFilterType(col) {
  // 优先使用后端返回的值
  if (col.filter_type) {
    const normalized = normalizeFilterType(col.filter_type)
    if (normalized !== 'search') {
      return normalized
    }
  }
  // Fallback: 推断逻辑
  const type = (col.type || col.field_type || '').toLowerCase()
  const widget = (col.widget || '').toLowerCase()
  const options = col.filter_options || col.filterOptions || col.options || []
  const format = (col.format || '').toLowerCase()
  const valueHelpConfig = col.value_help_config || col.valueHelpConfig || col.value_help || null

  if (type === 'datetime' || type === 'timestamp' || type === 'date' ||
      format === 'datetime' || format === 'date') {
    return 'date-range'
  }

  // FK 字段有 value_help 配置时，使用 value_help 过滤器
  if (valueHelpConfig && (valueHelpConfig.source || valueHelpConfig.presentation)) {
    return 'value_help'
  }

  if (options.length > 0) {
    return 'select'
  }

  if (type === 'enum' || type === 'enumeration') {
    return 'select'
  }

  if (widget === 'select' || widget === 'badge' || widget === 'tag' || widget === 'radio') {
    return 'select'
  }

  if (type === 'integer' || type === 'number' || type === 'float' || type === 'decimal') {
    return 'number-range'
  }

  return 'search'
}

/**
 * 标准化过滤类型名称（兼容旧命名）
 * @param {string} filterType
 * @returns {string}
 */
export function normalizeFilterType(filterType) {
  if (!filterType) return 'search'
  const t = filterType.toLowerCase().trim()
  const map = {
    'date_range': 'date-range',
    'daterange': 'date-range',
    'datetime-range': 'date-range',
    'datetimerange': 'date-range',
    'number_range': 'number-range',
    'numberrange': 'number-range',
    'select': 'select',
    'multi-select': 'multi-select',
    'multiselect': 'multi-select',
    'multi_select': 'multi-select',
    'enum': 'select',  // enum 类型使用 select（下拉多选）
    'search': 'search',
    'text': 'search',
    'date-range': 'date-range',
    'number-range': 'number-range',
    'value_help': 'value_help',
    'valuehelp': 'value_help'
  }
  return map[t] || 'search'
}

// ======== 字段生成 ========

/**
 * 从字段定义自动生成过滤字段配置
 * @param {Array} fields - YAML 字段定义数组
 * @param {Object} [metaConfig] - 元数据配置 { field_display_names }
 * @returns {Array} FilterBar fields 配置数组
 */
export function generateFiltersFromFields(fields, metaConfig) {
  if (!fields || fields.length === 0) {
    return []
  }

  const fieldDisplayNames = metaConfig?.field_display_names || {}
  const localFieldTypes = {}

  return fields
    .filter(field => field.filterable === true)
    .map(field => {
      let type = 'text'
      let format = null

      const fieldType = field.type?.toLowerCase() || field.field_type?.toLowerCase()

      if (fieldType === 'datetime' || fieldType === 'timestamp' || fieldType === 'date') {
        type = 'datetime-range'
        format = 'YYYY-MM-DD HH:mm:ss'
      } else if (fieldType === 'enum' || field.filter_type === 'enum') {
        type = 'select'
      } else if (fieldType === 'integer' || fieldType === 'number') {
        type = 'number-range'
      }

      const key = field.key || field.id || field.field
      if (key) {
        localFieldTypes[key] = type
      }

      const label = fieldDisplayNames[key] || field.label || field.name || field.semantics?.display_name || field.id

      const placeholder = field.filter_placeholder || field.placeholder || `请输入${label}`

      let options = field.filter_options || field.options || []
      if (fieldType === 'enum' && field.filter_options) {
        options = [
          { value: '', label: `全部${label}` },
          ...field.filter_options
        ]
      }

      return {
        key: key,
        label: label,
        type: type,
        placeholder: placeholder,
        options: options,
        multiple: field.multiple || false,
        defaultValue: field.defaultValue || '',
        defaultVisible: field.defaultVisible !== false,
        clearable: true,
        format: format,
        showTime: type === 'datetime-range',
        showSeconds: false
      }
    })
}

/**
 * 将 YAML 过滤器定义转换为 FilterBar 字段格式
 * @param {Array} yamlFilters - YAML filters 数组
 * @param {Object} [metaConfig] - 元数据配置 { list: { tableColumns } }
 * @returns {Array} FilterBar fields 配置数组
 */
export function transformFilters(yamlFilters, metaConfig) {
  const tableColumns = metaConfig?.list?.tableColumns || metaConfig?.list?.columns || []
  const autoGeneratedFields = generateFiltersFromFields(tableColumns, metaConfig)

  if (yamlFilters && yamlFilters.length > 0) {
    const explicitFields = yamlFilters.map(filter => ({
      key: filter.key || filter.id || filter.field,
      label: filter.label || filter.name,
      type: filter.type || 'text',
      placeholder: filter.placeholder || `请输入${filter.label || filter.name || ''}`,
      options: filter.options || [],
      multiple: filter.multiple || false,
      defaultValue: filter.defaultValue || '',
      defaultVisible: filter.defaultVisible !== false,
      clearable: true,
      showTime: filter.showTime,
      showSeconds: filter.showSeconds,
      fieldOptions: filter.fieldOptions,
      format: filter.format
    }))

    return [...explicitFields, ...autoGeneratedFields]
  }

  return autoGeneratedFields
}

/**
 * 用后端 filters 的类型信息回填 columns 的 filter_type
 * @param {Array} columns - 列定义数组
 * @param {Array} rawFilters - 后端 /api/v2/bo/{type}/ 返回的 filters 数组
 */
export function backfillColumnFilterType(columns, rawFilters) {
  if (!columns || !columns.length) return

  const filterMap = {}
  rawFilters.forEach(f => {
    const key = f.key || f.id || f.field
    if (key) filterMap[key] = f
  })

  // 使用 JSON.parse(JSON.stringify) 来确保 Vue 响应式系统能够检测到变化
  const updatedColumns = JSON.parse(JSON.stringify(columns))

  updatedColumns.forEach(col => {
    const colKey = col.prop || col.key
    const matched = filterMap[colKey]

    if (matched) {
      const rawType = matched.type || matched.filter_type || ''
      const normalized = normalizeFilterType(rawType)
      if (normalized !== 'search') {
        col.filter_type = normalized
      }
      if (matched.options && matched.options.length > 0 && (!col.filter_options || col.filter_options.length === 0)) {
        col.filter_options = matched.options
      }
      if (matched.value_help) {
        col.filter_type = 'value_help'
        col.value_help = matched.value_help
        col.valueHelpConfig = matched.value_help
      }
    }

    if (!col.filter_type || col.filter_type === 'search') {
      const inferred = inferFilterType(col)
      if (inferred !== 'search') {
        col.filter_type = inferred
      }
    }
  })

  // 替换原数组
  columns.length = 0
  columns.push(...updatedColumns)
}

/**
 * 获取过滤字段的默认值映射
 * @param {Array} filterFields
 * @returns {Object} { fieldKey: defaultValue }
 */
export function getDefaultFilterValues(filterFields) {
  const defaults = {}
  filterFields.forEach(field => {
    if (field.defaultValue !== undefined && field.defaultValue !== '') {
      defaults[field.key] = field.defaultValue
    }
  })
  return defaults
}

// ======== 参数构建 ========

/**
 * 向参数字典添加单个过滤参数
 * @param {Object} params - 目标参数字典 (mutated)
 * @param {string} key - 字段 key
 * @param {*} value - 过滤值
 * @param {Array} columns - 列定义（用于类型查找）
 * @param {Array} filterFields - 过滤字段定义（用于 filter_type 查找）
 * @param {Object} [options] - { debug: false }
 */
export function addFilterParam(params, key, value, columns, filterFields, options = {}) {
  if (value === '' || value === null || value === undefined) {
    return
  }

  if (key === 'keyword') {
    params['search'] = value
    return
  }

  if (key.includes('__')) {
    params[key] = String(value)
    if (options.debug) {
      console.log(`[FilterService] 原始参数透传: ${key}=${value}`)
    }
    return
  }

  const field = columns.find(f => f.prop === key) ||
                filterFields.find(f => f.key === key)
  const fieldType = (field?.type || 'text').toLowerCase()
  const fieldFormat = (field?.format || '').toLowerCase()
  const filterType = (field?.filter_type || '').toLowerCase()
  // [FIX 2026-06-10] 支持 api_param_key: 把前端 prop 名映射到后端 API 参数名
  //   例: column prop=category_label, api_param_key=category_type → 请求 ?category_type=xxx
  //   默认与 key 保持一致
  const apiKey = (field?.api_param_key || field?.apiParamKey || key)

  if (options.debug) {
    console.log(`[FilterService] 添加过滤参数: ${key}=${value} (type: ${fieldType}, format: ${fieldFormat}, filterType: ${filterType})`)
  }

  const isDateRange = Array.isArray(value) && (
    key.endsWith('_range') ||
    fieldType === 'datetime' ||
    fieldType === 'timestamp' ||
    fieldType === 'date' ||
    fieldType === 'datetime-range' ||
    fieldType === 'date_range' ||
    fieldFormat === 'datetime' ||
    fieldFormat === 'date' ||
    filterType === 'date-range' ||
    filterType === 'date_range'
  )

  if (isDateRange) {
    const baseKey = key.endsWith('_range') ? key.replace('_range', '') : key
    if (value[0]) {
      params[`${baseKey}_start`] = formatDate(value[0], false)
      if (options.debug) {
        console.log(`[FilterService] 日期开始: ${baseKey}_start=${params[`${baseKey}_start`]}`)
      }
    }
    if (value[1]) {
      params[`${baseKey}_end`] = formatDate(value[1], true)
      if (options.debug) {
        console.log(`[FilterService] 日期结束: ${baseKey}_end=${params[`${baseKey}_end`]}`)
      }
    }
  } else if (Array.isArray(value)) {
    // 数组值：可能是多选或范围
    // 只有当明确指定为 number-range 类型且数组有两个元素时才处理为范围
    const isRangeFilterType = filterType === 'number-range' || filterType === 'number_range'
    const isNumericField = fieldType === 'integer' || fieldType === 'float' || fieldType === 'number' || fieldType === 'decimal'

    if (isRangeFilterType && value.length === 2 && isNumericField) {
      // 明确的范围过滤（两个元素的数组 + number-range 类型）
      // 使用 __gte/__lte 后缀（后端 persistence_interceptor._try_build_computed_filter 识别）
      const min = value[0]
      const max = value[1]
      if (min !== null && min !== undefined && min !== '') {
        params[`${apiKey}__gte`] = String(min)
      }
      if (max !== null && max !== undefined && max !== '') {
        params[`${apiKey}__lte`] = String(max)
      }
    } else if (value.length === 1 && isNumericField) {
      // 单元素数组 + 数字字段：当作单值处理（如 FK 字段选择）
      params[apiKey] = String(value[0])
      if (options.debug) {
        console.log(`[FilterService] 单值过滤: ${apiKey}=${value[0]}`)
      }
    } else {
      // 多选过滤：使用 __in
      params[`${apiKey}__in`] = value.join(',')
      if (options.debug) {
        console.log(`[FilterService] 多选过滤: ${apiKey}__in=${params[`${apiKey}__in`]}`)
      }
    }
  } else {
    const textTypes = ['text', 'string', 'varchar', 'email', 'ellipsis']
    const isTextField = textTypes.includes(fieldType)
    const isIdField = key.endsWith('_id')
    const isNumericValue = typeof value === 'number' || /^-?\d+$/.test(String(value))

    if (isTextField && !isIdField && !isNumericValue) {
      params[`${apiKey}__like`] = `%${value}%`
      if (options.debug) {
        console.log(`[FilterService] 模糊过滤: ${apiKey} LIKE '%${value}%'`)
      }
    } else {
      params[apiKey] = String(value)
      if (options.debug) {
        console.log(`[FilterService] 精确过滤: ${apiKey}=${value}`)
      }
    }
  }
}

/**
 * 从过滤值构建完整 API 查询参数
 * @param {Object} options - {
 *   page: number,
 *   pageSize: number,
 *   keyword: string,
 *   filterValues: Object,
 *   headerFilterValues: Object,
 *   columns: Array,
 *   filterFields: Array,
 *   sortProp: string,
 *   sortOrder: string,     // 'ascending' | 'descending'
 *   defaultOrdering: string, // eg "-updated_at"
 *   extraParams: Object,
 *   debug: boolean
 * }
 * @returns {Object} API 请求参数 (filters, keyword, sort, page, page_size 等)
 */
export function buildFilterQueryParams(options = {}) {
  const {
    page,
    pageSize,
    keyword,
    filterValues = {},
    headerFilterValues = {},
    columns = [],
    filterFields = [],
    sortProp,
    sortOrder,
    defaultOrdering,
    extraParams = {},
    debug = false
  } = options

  const params = {
    page: page,
    page_size: pageSize,
    ...extraParams
  }

  if (keyword && keyword.trim()) {
    params.keyword = keyword.trim()
    if (debug) {
      console.log(`[FilterService] 关键词搜索: "${keyword}"`)
    }
  }

  Object.keys(filterValues)
    .filter(key => !isInternalProp(key))
    .forEach(key => {
      addFilterParam(params, key, filterValues[key], columns, filterFields, { debug })
    })

  Object.keys(headerFilterValues)
    .filter(key => !isInternalProp(key))
    .forEach(key => {
      addFilterParam(params, key, headerFilterValues[key], columns, filterFields, { debug })
    })

  if (sortProp && sortOrder) {
    const prefix = sortOrder === 'descending' ? '-' : ''
    params.ordering = `${prefix}${sortProp}`
  } else if (defaultOrdering) {
    params.ordering = defaultOrdering
  }

  return params
}

// ======== 合并 ========

/**
 * 合并多个过滤源（后覆盖前）
 * @param {...Object} filterSources
 * @returns {Object}
 */
export function mergeFilters(...filterSources) {
  const result = {}
  filterSources.forEach(source => {
    if (source && typeof source === 'object') {
      Object.keys(source).forEach(key => {
        if (source[key] !== '' && source[key] !== null && source[key] !== undefined) {
          result[key] = source[key]
        }
      })
    }
  })
  return result
}

/**
 * 添加导出过滤参数（用于构建 API 查询参数）
 * 处理日期范围、数字范围、多选、文本模糊匹配等场景
 *
 * @param {Object} params - 参数对象（会被就地修改）
 * @param {string} key - 过滤字段名
 * @param {*} value - 过滤值
 * @param {Array} columns - 列配置数组（用于查找字段类型）
 * @param {Array} filterFields - 过滤字段配置数组
 * @param {Function} formatDateFn - 日期格式化函数 (date, isEndTime) => string
 */
export function addExportFilterParam(params, key, value, columns = [], filterFields = [], formatDateFn = null) {
  if (value === '' || value === null || value === undefined) {
    return
  }

  const field = columns.find(f => f.prop === key) ||
                filterFields.find(f => f.key === key)
  const fieldType = (field?.type || 'text').toLowerCase()
  const fieldFormat = (field?.format || '').toLowerCase()
  const filterType = (field?.filter_type || '').toLowerCase()

  const isDateRange = Array.isArray(value) && (
    key.endsWith('_range') ||
    fieldType === 'datetime' ||
    fieldType === 'timestamp' ||
    fieldType === 'date' ||
    fieldType === 'datetime-range' ||
    fieldType === 'date_range' ||
    fieldFormat === 'datetime' ||
    fieldFormat === 'date' ||
    filterType === 'date-range' ||
    filterType === 'date_range'
  )

  if (isDateRange) {
    const baseKey = key.endsWith('_range') ? key.replace('_range', '') : key
    if (value[0]) {
      params[`${baseKey}_start`] = formatDateFn ? [formatDateFn(value[0], false)] : [String(value[0])]
    }
    if (value[1]) {
      params[`${baseKey}_end`] = formatDateFn ? [formatDateFn(value[1], true)] : [String(value[1])]
    }
  } else if (Array.isArray(value) && (filterType === 'number-range' || filterType === 'number_range' ||
             fieldType === 'integer' || fieldType === 'float' || fieldType === 'number' || fieldType === 'decimal')) {
    const min = value[0]
    const max = value[1]
    if (min !== null && min !== undefined && min !== '') {
      params[`${key}_min`] = [String(min)]
    }
    if (max !== null && max !== undefined && max !== '') {
      params[`${key}_max`] = [String(max)]
    }
  } else if (Array.isArray(value)) {
    params[`${key}__in`] = [value.join(',')]
  } else {
    const textTypes = ['text', 'string', 'varchar', 'email', 'ellipsis']

    if (textTypes.includes(fieldType)) {
      params[`${key}__like`] = [`%${value}%`]
    } else {
      params[key] = [value]
    }
  }
}
