<template>
  <div class="condition-rule-editor">
    <div v-if="showInfo" class="editor-info">
      <AppAlert type="info">
        条件型权限通过属性条件匹配资源，新增满足条件的资源自动继承权限，无需手动配置。
      </AppAlert>
    </div>

    <div class="editor-section">
      <label class="section-label">
        资源类型 <span class="required">*</span>
      </label>
      <AppSelect
        v-model="form.resource_type"
        :options="resourceTypeOptions"
        placeholder="请选择资源类型"
        :disabled="mode === 'edit'"
        @change="handleResourceTypeChange"
      />
      <div v-if="errors.resource_type" class="field-error">{{ errors.resource_type }}</div>
    </div>

    <div class="editor-section">
      <label class="section-label">
        权限级别 <span class="required">*</span>
      </label>
      <div class="level-buttons">
        <AppButton
          v-for="level in permissionLevels"
          :key="level.value"
          :variant="form.permission_level === level.value ? 'primary' : 'secondary'"
          size="sm"
          @click="form.permission_level = level.value"
        >
          {{ level.label }}
        </AppButton>
      </div>
    </div>

    <div class="editor-section">
      <label class="checkbox-wrapper">
        <input type="checkbox" v-model="form.is_denied" />
        <span class="denied-label">禁止权限</span>
        <span class="denied-hint">（禁止权优先原则：禁止权优先于所有授权）</span>
      </label>
    </div>

    <div v-if="form.resource_type" class="editor-section">
      <label class="section-label">
        条件定义 <span class="required">*</span>
      </label>
      
      <div class="condition-mode-tabs">
        <AppButton
          :variant="conditionMode === 'dimension' ? 'primary' : 'secondary'"
          size="sm"
          @click="conditionMode = 'dimension'"
        >
          管理维度
        </AppButton>
        <AppButton
          :variant="conditionMode === 'custom' ? 'primary' : 'secondary'"
          size="sm"
          @click="conditionMode = 'custom'"
        >
          自定义条件
        </AppButton>
      </div>

      <div v-if="conditionMode === 'dimension'" class="dimension-mode">
        <div v-for="dim in sortedDimensions" :key="dim.code" class="dimension-item">
          <label class="dimension-label">
            <input
              type="checkbox"
              :checked="isDimensionSelected(dim.code)"
              @change="toggleDimension(dim)"
            />
            <span class="dimension-name">{{ dim.name }}</span>
            <span v-if="dim.relation_object" class="dimension-meta" title="支持Value Help">
              <AppIcon name="link" :size="12" />
            </span>
          </label>
          
          <div v-if="isDimensionSelected(dim.code)" class="dimension-config">
            <select
              v-model="dimensionConfigs[dim.code].operator"
              class="operator-select"
              @change="handleOperatorChange(dim)"
            >
              <option value="=">等于</option>
              <option value="!=">不等于</option>
              <option value="IN">包含于（多选）</option>
              <option value="LIKE">模糊匹配</option>
              <option value=">">大于</option>
              <option value=">=">大于等于</option>
              <option value="<">小于</option>
              <option value="<=">小于等于</option>
            </select>
            
            <div class="dimension-value">
              <template v-if="shouldUseValueHelp(dim)">
                <ValueHelpSelector
                  v-model="dimensionConfigs[dim.code].value"
                  :display-value="dimensionConfigs[dim.code].displayValue"
                  :options="valueHelpOptions[dim.code] || []"
                  :multiple="dimensionConfigs[dim.code].operator === 'IN'"
                  :placeholder="getValuePlaceholder(dim)"
                  :loading="valueHelpLoading[dim.code]"
                  @update:display-value="val => dimensionConfigs[dim.code].displayValue = val"
                  @search="query => loadValueHelp(dim, query)"
                  @change="handleValueChange(dim, $event)"
                />
              </template>
              <template v-else>
                <AppInput
                  v-model="dimensionConfigs[dim.code].value"
                  :placeholder="getValuePlaceholder(dim)"
                  @input="updateCondition"
                />
              </template>
            </div>
          </div>
        </div>
        
        <div v-if="availableDimensions.length === 0" class="empty-state">
          暂无可用管理维度
        </div>
      </div>

      <div v-if="conditionMode === 'custom'" class="custom-mode">
        <div class="field-help">
          <div class="field-help-header" @click="showFieldHelp = !showFieldHelp">
            <span><AppIcon name="clipboard" :size="14" /> 可用字段参考（点击展开）</span>
            <span class="toggle-icon">{{ showFieldHelp ? '▼' : '▶' }}</span>
          </div>
          <div v-if="showFieldHelp" class="field-help-content">
            <div v-if="fieldMetadata.length === 0" class="field-help-empty">
              加载中...
            </div>
            <div
              v-for="field in fieldMetadata"
              :key="field.id"
              class="field-help-item"
              @click="insertField(field)"
            >
              <span class="field-name">{{ field.name }}</span>
              <span class="field-column">{{ field.db_column }}</span>
              <span class="field-type">{{ field.field_type }}</span>
              <span v-if="field.is_foreign_key" class="field-fk" title="外键，支持Value Help">
                <AppIcon name="link" :size="12" /> {{ field.relation_object }}
              </span>
            </div>
          </div>
        </div>
        
        <textarea
          v-model="customCondition"
          rows="3"
          placeholder="如: product_id IN (1, 2, 3) AND domain_type = 'CORE'"
          class="custom-condition-input"
          @input="updateCondition"
        ></textarea>
        
        <div class="condition-hint">
          支持格式：field = value | field IN (v1, v2) | field != value | field LIKE '%value%' | field > value | AND 组合
        </div>
      </div>
    </div>

    <div v-if="form.condition" class="editor-section">
      <label class="section-label">生成的条件表达式</label>
      <div class="condition-preview">
        <code>{{ form.condition }}</code>
      </div>
      <div class="condition-friendly">
        <span class="friendly-label">业务语义：</span>
        <span class="friendly-text">{{ friendlyCondition }}</span>
      </div>
    </div>

    <div class="editor-section">
      <label class="checkbox-wrapper">
        <input type="checkbox" v-model="form.inherit_to_children" />
        向下继承（条件自动覆盖子级资源）
      </label>
    </div>

    <div class="editor-section">
      <label class="checkbox-wrapper">
        <input type="checkbox" v-model="form.propagate_to_parents" />
        向上传播（子级权限提供父级只读可见性）
      </label>
    </div>

    <div v-if="previewResult" class="editor-section preview-section">
      <label class="section-label">匹配资源预览</label>
      <div class="preview-result">
        <span class="preview-count">匹配 {{ previewResult.count }} 个资源</span>
        <div v-if="previewResult.resources?.length" class="preview-list">
          <span
            v-for="r in previewResult.resources.slice(0, 10)"
            :key="r.id"
            class="preview-item"
          >
            {{ r.name || r.code || `#${r.id}` }}
          </span>
          <span v-if="previewResult.count > 10" class="preview-more">
            ...等 {{ previewResult.count }} 个
          </span>
        </div>
      </div>
    </div>

    <div v-if="Object.keys(errors).some(k => errors[k])" class="editor-errors">
      <div v-for="(error, key) in errors" :key="key">
        <span v-if="error" class="error-item">
          <AppIcon name="warning" :size="14" /> {{ error }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { AppSelect, AppButton, AppAlert, AppInput } from '@/components/common'
import AppIcon from '../AppIcon/AppIcon.vue'
import ValueHelpSelector from './ValueHelpSelector.vue'
import { PERMISSION_LEVELS } from './types.js'
import permissionService from '@/services/permissionService'

const permissionLevels = PERMISSION_LEVELS

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  },
  dimensionId: {
    type: String,
    default: ''
  },
  fields: {
    type: Array,
    default: () => []
  },
  mode: {
    type: String,
    default: 'create',
    validator: (v) => ['create', 'edit'].includes(v)
  },
  dimensions: {
    type: Array,
    default: () => []
  },
  resourceTypes: {
    type: Array,
    default: () => [
      { value: 'domain', label: '领域' },
      { value: 'sub_domain', label: '子领域' },
      { value: 'service_module', label: '服务模块' },
      { value: 'business_object', label: '业务对象' }
    ]
  },
  showInfo: {
    type: Boolean,
    default: true
  },
  apiHeaders: {
    type: Object,
    default: () => ({})
  },
  apiBase: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'save', 'cancel', 'preview', 'validate'])

const resourceTypeOptions = computed(() => props.resourceTypes)

const form = reactive({
  resource_type: '',
  permission_level: 'read',
  is_denied: false,
  condition: '',
  inherit_to_children: true,
  propagate_to_parents: true
})

const errors = reactive({
  resource_type: '',
  condition: ''
})

const conditionMode = ref('dimension')
const customCondition = ref('')
const dimensionConfigs = reactive({})
const previewResult = ref(null)
const fieldMetadata = ref([])
const showFieldHelp = ref(false)
const valueHelpOptions = reactive({})
const valueHelpLoading = reactive({})

const HIDDEN_DIMENSIONS = [
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

const availableDimensions = computed(() => {
  if (!form.resource_type) return []
  return props.dimensions.filter(d =>
    !d.resource_types || d.resource_types.includes(form.resource_type)
  )
})

const sortedDimensions = computed(() => {
  const dims = availableDimensions.value.filter(dim => !HIDDEN_DIMENSIONS.includes(dim.code))
  
  const dimMap = {}
  dims.forEach(dim => { dimMap[dim.code] = dim })
  
  const getDepth = (dimCode, visited = new Set()) => {
    if (visited.has(dimCode)) return 0
    visited.add(dimCode)
    
    const dim = dimMap[dimCode]
    if (!dim || !dim.cascade_parent) return 0
    
    if (dimMap[dim.cascade_parent]) {
      return getDepth(dim.cascade_parent, visited) + 1
    }
    
    return 0
  }
  
  return [...dims].sort((a, b) => {
    const depthA = getDepth(a.code)
    const depthB = getDepth(b.code)
    return depthA - depthB
  })
})

const friendlyCondition = computed(() => {
  if (conditionMode.value === 'custom') {
    return generateFriendlyFromCustom(customCondition.value)
  }
  
  const parts = []
  for (const [code, config] of Object.entries(dimensionConfigs)) {
    const dim = props.dimensions.find(d => d.code === code)
    if (!dim || !config || !config.value) continue
    
    const operatorLabels = {
      '=': '=',
      '!=': '≠',
      'IN': '包含于',
      'LIKE': '匹配',
      '>': '>',
      '>=': '≥',
      '<': '<',
      '<=': '≤'
    }
    
    const opLabel = operatorLabels[config.operator] || config.operator
    
    if (config.operator === 'IN' && Array.isArray(config.selectedValues)) {
      const names = config.selectedValues.map(v => v.display_name || v.id)
      parts.push(`${dim.name} ${opLabel} (${names.join(', ')})`)
    } else {
      parts.push(`${dim.name} ${opLabel} ${config.displayValue || config.value}`)
    }
  }
  
  return parts.join(' 且 ')
})

function isDimensionSelected(code) {
  return !!dimensionConfigs[code]
}

function toggleDimension(dim) {
  if (dimensionConfigs[dim.code]) {
    delete dimensionConfigs[dim.code]
  } else {
    dimensionConfigs[dim.code] = {
      operator: '=',
      value: '',
      displayValue: '',
      selectedValues: [],
      searchText: ''
    }
  }
  updateCondition()
}

function handleOperatorChange(dim) {
  const config = dimensionConfigs[dim.code]
  if (!config) return
  
  config.value = ''
  config.displayValue = ''
  config.selectedValues = []
  updateCondition()
}

function shouldUseValueHelp(dim) {
  return dim.relation_object && !['LIKE', '>', '>=', '<', '<='].includes(dimensionConfigs[dim.code]?.operator)
}

function getValuePlaceholder(dim) {
  const config = dimensionConfigs[dim.code]
  if (!config) return '请输入值'
  
  if (config.operator === 'LIKE') {
    return '使用 % 作为通配符，如 %关键字%'
  }
  
  if (['>', '>=', '<', '<='].includes(config.operator)) {
    return '请输入数值'
  }
  
  if (config.operator === 'IN') {
    return '点击选择多个值...'
  }
  
  if (dim.cascade_parent) {
    const parentDim = props.dimensions.find(d => d.code === dim.cascade_parent)
    if (parentDim && isDimensionSelected(dim.cascade_parent)) {
      return `已过滤（基于${parentDim.name}）`
    }
  }
  
  return '请输入值或从列表选择...'
}

function updateCondition() {
  if (conditionMode.value === 'custom') {
    form.condition = customCondition.value
    emitModelUpdate()
    return
  }
  
  const parts = []
  for (const [code, config] of Object.entries(dimensionConfigs)) {
    const dim = props.dimensions.find(d => d.code === code)
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
  
  form.condition = parts.join(' AND ')
  emitModelUpdate()
}

function handleValueChange(dim, event) {
  const config = dimensionConfigs[dim.code]
  if (!config) return
  
  if (config.operator === 'IN' && Array.isArray(event)) {
    config.selectedValues = event
  }
  
  updateCondition()
  
  refreshChildDimensions(dim)
}

async function loadValueHelp(dim, search = '') {
  if (!dim.relation_object) return
  
  valueHelpLoading[dim.code] = true
  
  try {
    const params = { limit: '50' }
    if (search) params.search = search
    
    if (dim.cascade_parent) {
      const parentConfig = dimensionConfigs[dim.cascade_parent]
      if (parentConfig) {
        const parentDim = props.dimensions.find(d => d.code === dim.cascade_parent)
        if (parentDim) {
          const isMultiSelect = parentConfig.operator === 'IN'
          
          if (isMultiSelect && parentConfig.selectedValues?.length > 0) {
            const selectedIds = parentConfig.selectedValues.map(v => v.id).join(',')
            params[`filter_${parentDim.field}`] = selectedIds
            params.filter_mode = 'in'
          } else if (parentConfig.value) {
            params[`filter_${parentDim.field}`] = parentConfig.value
          }
        }
      }
    }
    
    const data = await permissionService.loadDimensionValues(dim.code, params)
    
    if (data.success) {
      valueHelpOptions[dim.code] = data.data || []
    }
  } catch (e) {
    console.error('Failed to load value help:', e)
  } finally {
    valueHelpLoading[dim.code] = false
  }
}

function refreshChildDimensions(parentDim) {
  const childDims = props.dimensions.filter(d => d.cascade_parent === parentDim.code)
  for (const childDim of childDims) {
    if (dimensionConfigs[childDim.code]) {
      dimensionConfigs[childDim.code].value = ''
      dimensionConfigs[childDim.code].displayValue = ''
      dimensionConfigs[childDim.code].selectedValues = []
    }
  }
}

async function loadFieldMetadata() {
  if (!form.resource_type) return
  
  try {
    const data = await permissionService.loadFieldMetadata(form.resource_type)
    if (data.success) {
      fieldMetadata.value = data.data || []
    }
  } catch (e) {
    console.error('Failed to load field metadata:', e)
  }
}

function insertField(field) {
  const current = customCondition.value
  const fieldRef = field.db_column
  customCondition.value = current ? `${current} ${fieldRef}` : fieldRef
  updateCondition()
}

function handleResourceTypeChange() {
  form.condition = ''
  customCondition.value = ''
  previewResult.value = null
  Object.keys(dimensionConfigs).forEach(k => delete dimensionConfigs[k])
  fieldMetadata.value = []
  showFieldHelp.value = false
  loadFieldMetadata()
  validateForm()
}

function generateFriendlyFromCustom(condition) {
  if (!condition) return ''
  
  let result = condition
  
  const fieldMap = {
    'domain_id': '领域',
    'sub_domain_id': '子领域',
    'service_module_id': '服务模块',
    'business_object_id': '业务对象',
    'version_id': '版本',
    'product_id': '产品',
    'status': '状态',
    'owner_id': '负责人',
    'created_by': '创建人'
  }
  
  for (const [field, name] of Object.entries(fieldMap)) {
    const regex = new RegExp(`\\b${field}\\b`, 'g')
    result = result.replace(regex, name)
  }
  
  result = result.replace(/\s*=\s*/g, ' = ')
  result = result.replace(/\s*!=\s*/g, ' ≠ ')
  result = result.replace(/\s+IN\s+/gi, ' 包含于 ')
  result = result.replace(/\s+LIKE\s+/gi, ' 匹配 ')
  result = result.replace(/\s+AND\s+/gi, ' 且 ')
  result = result.replace(/\s+OR\s+/gi, ' 或 ')
  result = result.replace(/'([^']+)'/g, '$1')
  
  return result
}

function validateForm() {
  let isValid = true
  errors.resource_type = ''
  errors.condition = ''
  
  if (!form.resource_type) {
    errors.resource_type = '请选择资源类型'
    isValid = false
  }
  
  if (!form.condition) {
    errors.condition = '请定义条件'
    isValid = false
  }
  
  emit('validate', { isValid, errors: { ...errors } })
  return isValid
}

function emitModelUpdate() {
  emit('update:modelValue', {
    resource_type: form.resource_type,
    permission_level: form.permission_level,
    is_denied: form.is_denied,
    condition: form.condition,
    inherit_to_children: form.inherit_to_children,
    propagate_to_parents: form.propagate_to_parents
  })
}

async function doPreview() {
  if (!validateForm()) return
  
  emit('preview', {
    condition: form.condition,
    resource_type: form.resource_type
  })
}

function parseConditionToDimConfigs(condition) {
  if (!condition) return
  
  const parts = condition.split(/\s+AND\s+/i)
  let matchedCount = 0
  
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
    
    const dim = props.dimensions.find(d => d.field === field)
    if (!dim) continue
    
    matchedCount++
    
    if (!dimensionConfigs[dim.code]) {
      dimensionConfigs[dim.code] = {
        operator: operator,
        value: '',
        displayValue: '',
        selectedValues: [],
        searchText: ''
      }
    }
    
    const config = dimensionConfigs[dim.code]
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
  
  if (matchedCount === 0 && condition) {
    conditionMode.value = 'custom'
    customCondition.value = condition
  }
}

watch(() => props.modelValue, (newVal) => {
  if (newVal && Object.keys(newVal).length > 0) {
    Object.assign(form, {
      resource_type: newVal.resource_type || '',
      permission_level: newVal.permission_level || 'read',
      is_denied: newVal.is_denied || false,
      condition: newVal.condition || '',
      inherit_to_children: newVal.inherit_to_children !== false,
      propagate_to_parents: newVal.propagate_to_parents !== false
    })
    
    if (form.resource_type) {
      loadFieldMetadata()
    }
    
    if (form.condition) {
      nextTick(() => parseConditionToDimConfigs(form.condition))
    }
  }
}, { immediate: true, deep: true })

onMounted(() => {
  if (props.modelValue && Object.keys(props.modelValue).length > 0) {
    Object.assign(form, props.modelValue)
  }
})

defineExpose({
  validate: validateForm,
  preview: doPreview,
  getFormData: () => ({ ...form }),
  reset: () => {
    form.resource_type = ''
    form.permission_level = 'read'
    form.is_denied = false
    form.condition = ''
    form.inherit_to_children = true
    form.propagate_to_parents = true
    customCondition.value = ''
    previewResult.value = null
    Object.keys(dimensionConfigs).forEach(k => delete dimensionConfigs[k])
    Object.keys(errors).forEach(k => errors[k] = '')
  }
})
</script>

<style scoped>
.condition-rule-editor {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.editor-info {
  margin-bottom: var(--spacing-xs);
}

.editor-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.section-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.required {
  color: var(--color-error);
}

.level-buttons {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.checkbox-wrapper {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: normal !important;
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.checkbox-wrapper input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.denied-label {
  color: var(--color-error);
  font-weight: var(--font-weight-medium);
}

.denied-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.condition-mode-tabs {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
}

.dimension-mode {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.dimension-item {
  padding: var(--spacing-sm);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.dimension-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  font-weight: normal !important;
}

.dimension-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.dimension-meta {
  font-size: var(--font-size-xs);
  margin-left: auto;
  color: var(--color-primary);
}

.dimension-config {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
  padding-left: 28px;
}

.operator-select {
  width: 130px;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.dimension-value {
  flex: 1;
  min-width: 0;
}

.empty-state {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.custom-mode {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.field-help {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.field-help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.field-help-header:hover {
  background: var(--color-bg-secondary);
}

.toggle-icon {
  font-size: var(--font-size-xs);
}

.field-help-content {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
}

.field-help-empty {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  text-align: center;
}

.field-help-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  border-bottom: 1px solid var(--color-border-subtle);
  transition: background var(--transition-fast);
}

.field-help-item:hover {
  background: var(--color-primary-bg);
}

.field-help-item:last-child {
  border-bottom: none;
}

.field-name {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
  min-width: 80px;
}

.field-column {
  color: var(--color-text-tertiary);
  font-family: monospace;
  font-size: var(--font-size-xs);
}

.field-type {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-xs);
  background: var(--color-bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.field-fk {
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  margin-left: auto;
}

.custom-condition-input {
  width: 100%;
  font-family: monospace;
  resize: vertical;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  min-height: 80px;
}

.custom-condition-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.condition-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.condition-preview {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-layout);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow-x: auto;
}

.condition-preview code {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.condition-friendly {
  margin-top: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--color-success-bg, rgba(34, 197, 94, 0.06));
  border: 1px solid var(--color-success-border, rgba(34, 197, 94, 0.15));
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.friendly-label {
  color: var(--color-success);
  font-weight: var(--font-weight-medium);
}

.friendly-text {
  color: var(--color-text-primary);
}

.preview-section {
  margin-top: var(--spacing-sm);
}

.preview-result {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-layout);
  border-radius: var(--radius-md);
}

.preview-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-xs);
}

.preview-item {
  padding: 2px 8px;
  background: var(--color-primary-bg);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-primary);
}

.preview-more {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.field-error {
  font-size: var(--font-size-xs);
  color: var(--color-error);
  margin-top: 2px;
}

.editor-errors {
  padding: var(--spacing-sm);
  background: var(--color-error-bg, rgba(239, 68, 68, 0.06));
  border: 1px solid var(--color-error-border, rgba(239, 68, 68, 0.15));
  border-radius: var(--radius-md);
}

.error-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--color-error);
}

@media (max-width: 640px) {
  .dimension-config {
    flex-direction: column;
    padding-left: 0;
  }
  
  .operator-select {
    width: 100%;
  }
  
  .level-buttons {
    flex-direction: column;
  }
  
  .level-buttons .app-button {
    width: 100%;
  }
}
</style>
