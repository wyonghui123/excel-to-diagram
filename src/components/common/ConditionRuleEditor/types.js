import { PERMISSION_LEVELS } from '@/constants/permissionLevels.js'

export { PERMISSION_LEVELS }

export const CONDITION_OPERATORS = [
  { value: '=', label: '等于' },
  { value: '!=', label: '不等于' },
  { value: 'IN', label: '包含于（多选）' },
  { value: 'LIKE', label: '模糊匹配' },
  { value: '>', label: '大于' },
  { value: '>=', label: '大于等于' },
  { value: '<', label: '小于' },
  { value: '<=', label: '小于等于' }
]

export const RESOURCE_TYPES = [
  { value: 'domain', label: '领域' },
  { value: 'sub_domain', label: '子领域' },
  { value: 'service_module', label: '服务模块' },
  { value: 'business_object', label: '业务对象' }
]

export const HIDDEN_DIMENSIONS = [
  'domain_type',
  'organization',
  'organization_id',
  'department',
  'department_id',
  'employee',
  'created_by',
  'created_at',
  'owner_id'
]

export function createEmptyRule() {
  return {
    resource_type: '',
    permission_level: 'read',
    is_denied: false,
    condition: '',
    inherit_to_children: true,
    propagate_to_parents: true
  }
}

export function validateRule(rule) {
  const errors = {}
  
  if (!rule.resource_type) {
    errors.resource_type = '请选择资源类型'
  }
  
  if (!rule.condition) {
    errors.condition = '请定义条件'
  }
  
  return {
    isValid: Object.keys(errors).length === 0,
    errors
  }
}

export function generateConditionFromConfigs(dimensionConfigs, dimensions) {
  const parts = []
  
  for (const [code, config] of Object.entries(dimensionConfigs)) {
    const dim = dimensions.find(d => d.code === code)
    if (!dim || !config || !config.value) continue
    
    const field = dim.field
    const operator = config.operator
    let value = config.value
    
    if (operator === 'IN') {
      const values = Array.isArray(config.selectedValues)
        ? config.selectedValues.map(v => v.id)
        : (Array.isArray(value) ? value : [value])
      if (values.length > 0) {
        parts.push(`${field} IN (${values.join(', ')})`)
      }
    } else if (operator === 'LIKE') {
      const v = typeof value === 'string' ? `'${value}'` : value
      parts.push(`${field} LIKE ${v}`)
    } else if (['>', '>=', '<', '<='].includes(operator)) {
      parts.push(`${field} ${operator} ${value}`)
    } else {
      const v = isNaN(value) ? `'${value}'` : value
      parts.push(`${field} ${operator} ${v}`)
    }
  }
  
  return parts.join(' AND ')
}

export function parseConditionToConfigs(condition, dimensions) {
  if (!condition) return {}
  
  const configs = {}
  const parts = condition.split(/\s+AND\s+/i)
  
  for (const part of parts) {
    const trimmed = part.trim()
    
    let field, operator, valueStr
    const inMatch = trimmed.match(/^(\w+)\s+IN\s*\(([^)]+)\)$/)
    const likeMatch = trimmed.match(/^(\w+)\s+LIKE\s+(.+)$/)
    const compMatch = trimmed.match(/^(\w+)\s*(=|!=|>=|<=|>|<)\s*(.+)$/)
    
    if (inMatch) {
      field = inMatch[1]
      operator = 'IN'
      valueStr = inMatch[2].trim()
    } else if (likeMatch) {
      field = likeMatch[1]
      operator = 'LIKE'
      valueStr = likeMatch[2].trim().replace(/'/g, '')
    } else if (compMatch) {
      field = compMatch[1]
      operator = compMatch[2]
      valueStr = compMatch[3].trim().replace(/'/g, '')
    } else {
      continue
    }
    
    const dim = dimensions.find(d => d.field === field)
    if (!dim) continue
    
    configs[dim.code] = {
      operator: operator,
      value: operator === 'IN' ? valueStr.split(',').map(v => v.trim()).filter(Boolean) : valueStr,
      displayValue: valueStr,
      selectedValues: operator === 'IN' 
        ? valueStr.split(',').map(v => v.trim()).filter(Boolean).map(id => ({ id, display_name: id }))
        : []
    }
  }
  
  return configs
}
