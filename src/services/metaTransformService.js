/**
 * metaTransformService - 元数据转换服务
 *
 * 业务职责：将后端返回的元数据配置转换为前端组件格式。
 * 所有函数均为纯函数，不依赖 Vue 响应式。
 *
 * @module services/metaTransformService
 */

import { normalizeFilterType, inferFilterType } from './filterService'
import { sortColumnsByDefaultOrder } from './columnOrderService'

/**
 * 转换列定义为 Element Plus el-table-column 格式
 *
 * @param {Array} yamlColumns - YAML 定义的列
 * @param {Object} options - 选项
 * @param {string} options.filterDisplayMode - 过滤器显示模式 ('hover'|'always'|'manual')
 * @param {Array} [options.fields=[]] - 字段元数据(用于 smart_default 分类)
 * @param {Object} [options.columnOrder={}] - 列序配置 { strategy, manual_order, override }
 * @returns {Array} el-table-column 配置数组
 */
export function transformColumns(yamlColumns, options = {}) {
  const transformed = yamlColumns.map(col => {
    const fieldName = (col.key || col.field || col.id || '').toLowerCase()
    const inferredWidth = inferColumnWidth(col)
    const isDatetimeField = /(_at|_time|_date)$/.test(fieldName) && fieldName !== 'id'
    const colType = col.type || col.field_type || 'text'
    const resolvedType = isDatetimeField ? 'datetime' : colType

    return {
      key: col.key || col.field || col.id,
      prop: col.key || col.field || col.id,
      label: col.label || col.title,
      width: col.width || inferredWidth.width,
      minWidth: col.minWidth || inferredWidth.minWidth,

      sortable: (col.sortable !== false &&
                !col.hidden_sort &&
                !(col.slot || col.type === 'custom' || col.type === 'association')),

      resizable: col.resizable !== false,

      fixed: col.fixed || false,
      type: resolvedType,
      slot: col.slot || col.type === 'custom' || col.type === 'association',
      widget: col.widget,
      format: col.format,
      enum_type: col.enum_type || '',
      visible: col.visible !== false,
      default_visible: col.default_visible !== false,
      showOverflowTooltip: true,

      filterable: col.filterable !== false && !col.hidden_filter,
      filter_options: col.filter_options || col.filterOptions || col.options || [],
      filter_placeholder: col.filter_placeholder,
      filter_type: (() => {
        const backendType = normalizeFilterType(col.filter_type)
        if (backendType && backendType !== 'search') {
          return backendType
        }
        const enumValues = col.enum_values || col.enumValues || []
        if (enumValues.length > 0) {
          return 'select'
        }
        return inferFilterType(col)
      })(),

      filterTriggerMode: col.filterTriggerMode || options.filterDisplayMode || 'hover',

      badgeColors: col.badge_colors || col.badgeColors,
      options: col.options,
      enum_values: col.enum_values || col.enumValues || [],
      placeholder: col.placeholder,

      association: col.association,
      displayMode: col.displayMode || 'count',
      navigateTo: col.navigateTo,
      maxTags: col.maxTags || 2,

      businessKey: col.business_key || col.businessKey || false,
      // [BUG-V036 2026-06-29] YAML column 配置使用 `value_help` (snake_case),
      //   后端 API 可能返回 `value_help_config`, 前端转换后是 `valueHelpConfig`。
      //   三种命名都要支持, 否则 YAML 中配置的 FK 列头过滤和 FK link 都会丢失。
      //   与 filterService.js L95 的逻辑保持一致。
      valueHelpConfig: col.value_help_config || col.valueHelpConfig || col.value_help || null,

      editable: col.editable !== false,
      immutable: col.immutable === true,

      column_priority: col.column_priority || null,
      position: col.position,

      // [FIX 2026-06-10] 列头过滤时使用的 API 参数名 (默认与 key 相同)
      //   例: column prop=category_label, api_param_key=category_type → 请求 ?category_type=xxx
      api_param_key: col.api_param_key || col.apiParamKey || ''
    }
  })
  return sortColumnsByDefaultOrder(transformed, options.fields || [], options.columnOrder || {})
}

/**
 * 自动推断列优先级（compact mode 使用）
 * - required: id、business_key、display_name 等必须展示的列
 * - default: 常规辅助列
 * - optional: datetime、系统字段等仅完整页展示的列
 *
 * @param {Object} col - 列配置
 * @returns {string} 'required' | 'default' | 'optional'
 */
export function inferColumnPriority(col) {
  // 优先使用后端返回的值
  const backendPriority = col.importance || col.priority
  if (backendPriority) return backendPriority
  // Fallback: 推断逻辑
  const prop = (col.prop || col.key || '').toLowerCase()
  const type = (col.type || '').toLowerCase()
  const field = (col.field || '').toLowerCase()

  if (prop === 'id') return 'required'
  if (col.businessKey === true) return 'required'
  if (prop === 'code') return 'required'
  if (prop === 'name' || prop === 'display_name' || prop === 'username') return 'required'

  const sysFields = ['created_at', 'updated_at', 'created_by', 'updated_by']
  if (sysFields.includes(prop)) return 'default'
  if (sysFields.includes(field)) return 'default'
  if (type === 'datetime' || type === 'timestamp' || type === 'date') return 'default'

  return 'default'
}

/**
 * 转换操作按钮为统一格式
 *
 * @param {Array} yamlActions - YAML 定义的操作
 * @returns {Array} 统一格式 actions
 */
export function transformActions(yamlActions) {
  const defaultLabels = {
    batch_delete: '批量删除',
    batch_export: '批量导出',
    batch_update: '批量更新',
    create: '新建',
    export: '导出',
    import: '导入',
    delete: '删除',
    edit: '编辑'
  }
  return (yamlActions || []).map(action => {
    const actionKey = action.id || action.key
    const inferredPosition = inferActionPosition(action)
    const position = action.position || inferredPosition

    return {
      key: actionKey,
      label: action.label || defaultLabels[actionKey] || actionKey,
      icon: action.icon,
      variant: mapVariant(action.variant || action.type, position),
      position: position,
      permission: action.permission,
      condition: action.condition,
      confirmMessage: action.confirm || action.confirmMessage,
      confirmTitle: action.confirmTitle || '确认操作',
      show: action.show !== false,
      container: action.container,
      target: action.target,
      params: action.params
    }
  }).filter(a => a.show !== false)
}

/**
 * 智能推断操作位置
 *
 * @param {Object} action - 操作配置
 * @returns {string} 'toolbar' | 'row' | 'batch'
 */
export function inferActionPosition(action) {
  const actionId = (action.id || action.key || '').toLowerCase()
  const actionType = (action.type || '').toLowerCase()

  const toolbarActions = ['create', 'new', 'add', 'import', 'export']
  const rowActions = ['edit', 'delete', 'view', 'detail', 'update', 'remove']
  const batchActions = ['batch_delete', 'batch_export', 'batch_update']

  if (batchActions.some(id => actionId.includes(id)) || actionId.startsWith('batch_')) {
    return 'batch'
  }

  if (toolbarActions.some(id => actionId.includes(id) || actionType.includes(id))) {
    return 'toolbar'
  }

  if (rowActions.some(id => actionId.includes(id) || actionType.includes(id))) {
    return 'row'
  }

  return 'row'
}

/**
 * 映射变体名称到 Element Plus button type
 *
 * @param {string} variant - 原始变体名称
 * @param {string} position - 操作位置
 * @returns {string} Element Plus button type
 */
export function mapVariant(variant, position = 'row') {
  const map = {
    'primary': 'primary',
    'success': 'success',
    'warning': 'warning',
    'danger': 'danger',
    'info': 'info',
    'text': '',
    'default': ''
  }

  if (position === 'row') {
    return ''
  }

  return Object.prototype.hasOwnProperty.call(map, variant) ? map[variant] : (variant || '')
}

/**
 * 根据字段类型和配置推断列宽度
 * 参考 SAP Fiori、Salesforce Lightning、Material Design 最佳实践
 *
 * @param {Object} col - 列配置
 * @returns {{ width: number, minWidth: number }}
 */
export function inferColumnWidth(col) {
  // 优先使用后端返回的值
  if (col.width && col.width !== 'auto') {
    return { width: col.width, minWidth: col.minWidth || Math.floor(col.width * 0.8) }
  }
  // Fallback: 推断逻辑
  const type = (col.type || '').toLowerCase()
  const widget = (col.widget || '').toLowerCase()
  const field = (col.field || col.key || '').toLowerCase()
  const label = (col.label || col.title || '').toString()

  if (field === 'id' || field.endsWith('_id') || field === 'uuid') {
    return { width: 100, minWidth: 80 }
  }

  if (field === 'status' || field === 'state' || field.endsWith('_status')) {
    return { width: 120, minWidth: 100 }
  }

  if (type === 'datetime' || type === 'timestamp' || type === 'date' ||
      field.endsWith('_at') || field.endsWith('_date') || field.endsWith('_time')) {
    return { width: 160, minWidth: 140 }
  }

  if (field === 'username' || field === 'name' || field === 'display_name' ||
      field === 'title' || field.endsWith('_name')) {
    return { width: 150, minWidth: 120 }
  }

  if (field === 'email' || field.endsWith('_email')) {
    return { width: 200, minWidth: 150 }
  }

  if (field === 'description' || field === 'remark' || field === 'note' ||
      field.endsWith('_description')) {
    return { width: 250, minWidth: 200 }
  }

  if (type === 'integer' || type === 'number' || type === 'float' || type === 'decimal') {
    return { width: 100, minWidth: 80 }
  }

  if (type === 'boolean' || type === 'bool') {
    return { width: 80, minWidth: 60 }
  }

  if (type === 'enum' || type === 'enumeration' || type === 'select') {
    return { width: 120, minWidth: 100 }
  }

  if (widget === 'badge' || widget === 'tag') {
    return { width: 100, minWidth: 80 }
  }

  if (widget === 'avatar') {
    return { width: 60, minWidth: 50 }
  }

  if (type === 'association') {
    return { width: 120, minWidth: 100 }
  }

  const labelLength = label.length
  if (labelLength > 20) {
    return { width: 200, minWidth: 150 }
  } else if (labelLength > 10) {
    return { width: 150, minWidth: 120 }
  }

  return { width: 120, minWidth: 100 }
}

/**
 * 修正 datetime 后缀字段类型
 *
 * @param {Array} columns - 列配置数组（会被就地修改）
 */
export function fixDatetimeColumns(columns) {
  if (!columns || !columns.length) return
  columns.forEach(col => {
    const fieldName = col.key || col.prop || ''
    if (/(_at|_time|_date)$/.test(fieldName) && fieldName !== 'id') {
      col.type = 'datetime'
    }
  })
}

/**
 * 用字段元数据信息回填 columns
 * 包括 businessKey、valueHelp、enum_values 等字段级元数据
 *
 * @param {Array} columns - 列配置数组（会被就地修改）
 * @param {Array} fields - 字段定义数组
 * @param {Object} metaConfig - 元数据配置（用于回退 fields）
 * @returns {Array} 回填后的 columns（新数组）
 */
export function enrichColumnsWithFieldMeta(columns, fields, metaConfig = null) {
  if (!columns || !columns.length) return columns

  const effectiveFields = (fields && fields.length > 0)
    ? fields
    : (metaConfig?.fields || [])
  if (!effectiveFields.length) return JSON.parse(JSON.stringify(columns))

  const fieldMap = {}
  effectiveFields.forEach(f => {
    const key = f.id || f.key
    if (key) fieldMap[key] = f
  })

  columns.forEach(col => {
    const prop = col.prop || col.key
    if (!prop) return

    let matchedField = fieldMap[prop]
    if (!matchedField && prop.endsWith('_id')) {
      matchedField = fieldMap[prop.replace(/_id$/, '')]
    }

    if (matchedField) {
      if (matchedField.type) {
        col.type = matchedField.type
      }
      if (matchedField.ui?.widget) {
        col.widget = matchedField.ui.widget
      } else if (matchedField.widget) {
        col.widget = matchedField.widget
      }

      if (matchedField.business_key === true) {
        col.businessKey = true
      }

      if (matchedField.value_help) {
        const existingVHC = col.valueHelpConfig || col.value_help_config
        if (existingVHC) {
          col.valueHelpConfig = { ...matchedField.value_help, ...existingVHC, behavior: { ...matchedField.value_help.behavior, ...existingVHC.behavior } }
        } else {
          col.valueHelpConfig = matchedField.value_help
        }
        if (col.filter_type === 'search' || !col.filter_type) {
          col.filter_type = 'value_help'
        }
      }

      if (matchedField.enum_values && matchedField.enum_values.length > 0) {
        let colEnumValues = matchedField.enum_values
        const fieldType = (matchedField.type || '').toString().toLowerCase()
        if (fieldType === 'boolean' || fieldType === 'bool' || fieldType === 'booleanenum') {
          colEnumValues = matchedField.enum_values.map(e => {
            const rawVal = e.value
            let intVal = rawVal
            if (typeof rawVal === 'boolean') {
              intVal = rawVal ? 1 : 0
            } else if (typeof rawVal === 'string') {
              const lower = rawVal.toLowerCase()
              if (lower === 'true') intVal = 1
              else if (lower === 'false') intVal = 0
            }
            return { ...e, value: intVal }
          })
        }
        col.enum_values = colEnumValues
      }

      if (matchedField.hidden_in_form === true) {
        col.hidden_in_form = true
      }
      if (matchedField.hidden_in_detail === true) {
        col.hidden_in_detail = true
      }
      if (matchedField.hidden_in_list === true) {
        col.hidden_in_list = true
      }
    }
  })

  return JSON.parse(JSON.stringify(columns))
}

/**
 * 获取默认排序规则
 *
 * @param {Object} metaConfig - 元数据配置
 * @returns {string|null} 排序字符串，如 "-updated_at"
 */
export function getDefaultOrdering(metaConfig) {
  if (!metaConfig) return null

  const yamlOrd = metaConfig.listConfig?.defaultOrdering || metaConfig.list?.defaultOrdering || metaConfig.defaultOrdering
  if (yamlOrd) return yamlOrd

  const defaultSortConfig = metaConfig.list?.defaultSort
  if (defaultSortConfig?.field) {
    const prefix = defaultSortConfig.order === 'desc' ? '-' : ''
    return `${prefix}${defaultSortConfig.field}`
  }

  return null
}

/**
 * 过滤行操作（考虑权限和条件）
 *
 * @param {Array} rowActions - 行操作配置数组
 * @param {Object} row - 当前行数据
 * @param {string} objectType - 对象类型
 * @param {string|null} rowMutability - 行可维护性 ('locked'|'extensible'|'fully_editable'|null)
 * @param {Function} checkPermission - 权限检查函数
 * @param {Function} evaluateCondition - 条件评估函数
 * @returns {Array} 过滤后的行操作
 */
export function filterRowActions(rowActions, row, objectType, rowMutability, checkPermission, evaluateCondition) {
  return rowActions.filter(action => {
    if (checkPermission && !checkPermission(action)) return false
    if (evaluateCondition && !evaluateCondition(action.condition, row)) return false

    const actionKey = (action.key || '').toLowerCase()

    // [FIX 2026-06-13] 未保存的新行 (_isNew=true / __new_xxx)
    //   - 隐藏单行 edit/update (新行的编辑由 inline cell 处理)
    //   - 隐藏单行 delete (新行的"删除"应该走本地 removeNewRow, 不调后端)
    if (row && (row._isNew === true || (typeof row.id === 'string' && row.id.startsWith('__new_')))) {
      if (actionKey === 'edit' || actionKey === 'update' || actionKey === 'delete') {
        return false
      }
    }

    if (objectType === 'enum_type' && row?.category === 'system') {
      if (actionKey === 'edit' || actionKey === 'update' || actionKey === 'delete') {
        return false
      }
    }

    if (rowMutability === 'locked') {
      if (actionKey === 'edit' || actionKey === 'update' || actionKey === 'delete') {
        return false
      }
    }

    if (rowMutability === 'extensible') {
      if (actionKey === 'edit' || actionKey === 'update') {
        return false
      }
      if (actionKey === 'delete') {
        return row?.is_system !== true && row?.system_value !== true
      }
    }

    return true
  })
}

/**
 * 推断字段编辑配置
 *
 * @param {Object} column - 列配置
 * @returns {Object|null} 编辑配置
 */
export function inferFieldEditConfig(column) {
  if (!column) return null

  // 优先使用后端返回的值
  if (column.edit_config) return column.edit_config
  // Fallback: 推断逻辑

  if (column.valueHelpConfig && column.valueHelpConfig.source) {
    return {
      type: 'value_help',
      key: column.prop || column.name,
      valueHelpConfig: column.valueHelpConfig,
      required: column.edit_required || column.required
    }
  }

  const typeInferMap = {
    'text': 'text',
    'string': 'text',
    'number': 'number',
    'integer': 'number',
    'boolean': 'switch',
    'switch': 'switch',
    'select': 'select',
    'enum': 'select',
    'date': 'date',
    'datetime': 'datetime'
  }

  const widgetTypeMap = {
    'select': 'select',
    'switch': 'switch',
    'badge': 'select',
    'tag': 'select',
    'radio': 'select',
    'checkbox': 'checkbox'
  }

  const editType = column.edit_type || widgetTypeMap[column.widget] || typeInferMap[column.type] || 'text'

  return {
    type: editType,
    options: column.edit_options || column.options || column.enum_values,
    placeholder: column.edit_placeholder,
    defaultValue: column.edit_default_value,
    required: column.edit_required
  }
}
