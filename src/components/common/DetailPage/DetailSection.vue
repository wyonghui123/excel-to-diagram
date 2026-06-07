<template>
  <div class="detail-section">
    <div v-if="title" class="ds-header">
      <span class="ds-title">{{ title }}</span>
    </div>
    
    <div v-if="loading" class="ds-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    
    <div v-else-if="(!data || isCreating) && visibleFields.length > 0" class="ds-grid">
      <div
        v-for="field in visibleFields"
        :key="field.id"
        class="ds-item"
        :class="{ 'ds-item--full': field.span === 'full' }"
      >
        <label class="ds-label">
          {{ field.label }}
          <span v-if="field.required" class="ds-required">*</span>
        </label>
        <div class="ds-value">
          <template v-if="isCreating || editing">
            <template v-if="(field.enum_values && field.enum_values.length > 0) || field.type === 'enum'">
              <el-select
                v-model="editData[field.id]"
                :placeholder="'请选择' + field.label"
                size="small"
                clearable
                :teleported="false"
                popper-class="app-select-popper"
              >
                <el-option
                  v-for="opt in getFieldOptions(field)"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
            
            <template v-else-if="field.type === 'boolean'">
              <el-switch v-model="editData[field.id]" />
            </template>
            
            <template v-else-if="field.type === 'date'">
              <AppDatePicker
                v-model="editData[field.id]"
                type="date"
                :placeholder="'请选择' + field.label"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
              />
            </template>
            
            <template v-else-if="field.type === 'datetime'">
              <AppDatePicker
                v-model="editData[field.id]"
                type="datetime"
                :placeholder="'请选择' + field.label"
                size="small"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </template>
            
            <template v-else-if="field.type === 'number' || field.type === 'integer'">
              <el-input-number
                v-model="editData[field.id]"
                :placeholder="'请输入' + field.label"
                size="small"
                controls-position="right"
              />
            </template>
            
            <template v-else-if="field.type === 'text' || field.type === 'textarea'">
              <el-input
                v-model="editData[field.id]"
                type="textarea"
                :rows="3"
                :placeholder="'请输入' + field.label"
                size="small"
              />
            </template>
            
            <template v-else-if="field.id === 'password'">
              <el-input
                v-model="editData[field.id]"
                type="password"
                :placeholder="'请输入' + field.label"
                size="small"
                show-password
              />
            </template>
            
            <template v-else>
              <el-input
                v-model="editData[field.id]"
                :placeholder="'请输入' + field.label"
                size="small"
              />
            </template>
          </template>
          <template v-else>
            <span class="ds-placeholder">-</span>
          </template>
        </div>
      </div>
    </div>
    
    <div v-else-if="!data" class="ds-empty">
      <span>暂无数据</span>
    </div>
    
    <div v-else class="ds-grid">
      <div
        v-for="field in visibleFields"
        :key="field.id"
        class="ds-item"
        :class="{ 'ds-item--full': field.span === 'full' }"
      >
        <label class="ds-label">{{ field.label }}</label>
        <div class="ds-value">
          <template v-if="editing && isFieldEditable(field)">
            <template v-if="(field.enum_values && field.enum_values.length > 0) || field.type === 'enum'">
              <el-select
                v-model="editData[field.id]"
                :placeholder="'请选择' + field.label"
                size="small"
                clearable
              >
                <el-option
                  v-for="opt in getFieldOptions(field)"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
            
            <template v-else-if="field.type === 'boolean'">
              <el-switch v-model="editData[field.id]" />
            </template>
            
            <template v-else-if="field.type === 'date'">
              <AppDatePicker
                v-model="editData[field.id]"
                type="date"
                :placeholder="'请选择' + field.label"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
              />
            </template>

            <template v-else-if="field.type === 'datetime'">
              <AppDatePicker
                v-model="editData[field.id]"
                type="datetime"
                :placeholder="'请选择' + field.label"
                size="small"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </template>
            
            <template v-else-if="field.type === 'number' || field.type === 'integer'">
              <el-input-number
                v-model="editData[field.id]"
                :placeholder="'请输入' + field.label"
                size="small"
                controls-position="right"
              />
            </template>
            
            <template v-else-if="field.type === 'text' || field.type === 'textarea'">
              <el-input
                v-model="editData[field.id]"
                type="textarea"
                :rows="3"
                :placeholder="'请输入' + field.label"
                size="small"
              />
            </template>
            
            <template v-else-if="field.type === 'association' || field.type === 'reference'">
              <el-select
                v-model="editData[field.id]"
                :placeholder="'请选择' + field.label"
                size="small"
                clearable
                filterable
              >
                <el-option
                  v-for="opt in getFieldOptions(field)"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
            
            <template v-else>
              <el-input
                v-model="editData[field.id]"
                :placeholder="'请输入' + field.label"
                size="small"
              />
            </template>
          </template>
          
          <template v-else>
            <template v-if="field.type === 'association' || field.type === 'reference'">
              <AssociationCell
                :value="getFieldValue(field)"
                :config="field"
                :object-type="field.target_type"
                @click="handleAssociationClick(field, $event)"
              />
            </template>
            
            <template v-else-if="(field.enum_values && field.enum_values.length > 0) || field.type === 'enum'">
              <el-tag
                v-if="getFieldValue(field)"
                :type="getEnumTagType(field, getFieldValue(field))"
                size="small"
              >
                {{ formatEnumValue(field, getFieldValue(field)) }}
              </el-tag>
              <span v-else class="ds-value--empty">-</span>
            </template>
            
            <template v-else-if="field.type === 'boolean'">
              <el-tag
                :type="getFieldValue(field) ? 'success' : 'info'"
                size="small"
              >
                {{ getFieldDisplayValue(field) }}
              </el-tag>
            </template>
            
            <template v-else-if="field.type === 'date' || field.type === 'datetime'">
              <span>{{ formatDateValue(getFieldValue(field), field.type) }}</span>
            </template>
            
            <template v-else-if="field.type === 'json' || field.type === 'object'">
              <el-popover
                placement="top"
                :width="400"
                trigger="click"
                :teleported="false"
                popper-class="app-popover-popper"
              >
                <template #reference>
                  <el-button size="small" text>
                    <el-icon><Document /></el-icon>
                    查看详情
                  </el-button>
                </template>
                <pre class="ds-json">{{ JSON.stringify(getFieldValue(field), null, 2) }}</pre>
              </el-popover>
            </template>
            
            <template v-else>
              <span :class="{ 'ds-value--empty': !getFieldValue(field) }">
                {{ getFieldDisplayValue(field) }}
              </span>
            </template>
          </template>
        </div>
      </div>
    </div>
    
    <slot />
  </div>
</template>

<script setup>
import { computed, ref, reactive, watch } from 'vue'
import { Loading, Document } from '@element-plus/icons-vue'
import AssociationCell from '@/components/bo/AssociationCell.vue'
import { AppDatePicker } from '@/components/common/AppDatePicker'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  fields: {
    type: Array,
    default: () => []
  },
  detailFields: {
    type: Array,
    default: () => []
  },
  data: {
    type: Object,
    default: () => ({})
  },
  schema: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  },
  readonly: {
    type: Boolean,
    default: true
  },
  editable: {
    type: Boolean,
    default: false
  },
  editing: {
    type: Boolean,
    default: false
  },
  saving: {
    type: Boolean,
    default: false
  },
  editData: {
    type: Object,
    default: () => ({})
  },
  hiddenFields: {
    type: Array,
    default: () => []
  },
  isCreating: {
    type: Boolean,
    default: false
  },
  readonlyFields: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['field-change', 'association-click'])

const SYSTEM_FIELDS = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

function getFieldPermission(fieldId) {
  const globalField = props.schema?.fields?.find(f => f.id === fieldId)
  const detailField = props.detailFields?.find(f => f.id === fieldId)
  
  const basePermission = {
    visible: globalField?.visible ?? true,
    editable: globalField?.editable ?? true,
    readonly: globalField?.readonly ?? false,
    hiddenInDetail: globalField?.hidden_in_detail ?? false
  }
  
  if (detailField) {
    return {
      visible: detailField.visible ?? basePermission.visible,
      editable: detailField.editable ?? basePermission.editable,
      readonly: detailField.readonly ?? basePermission.readonly,
      hiddenInDetail: basePermission.hiddenInDetail
    }
  }
  
  return basePermission
}

const visibleFields = computed(() => {
  return props.fields.filter(f => {
    if (props.hiddenFields.includes(f.id)) return false
    if (f.hidden) return false
    
    const permission = getFieldPermission(f.id)
    if (!permission.visible) return false
    if (permission.hiddenInDetail) return false
    
    return true
  })
})

function isFieldEditable(field) {
  if (props.readonly) return false
  if (props.readonlyFields.includes(field.id)) return false
  
  const permission = getFieldPermission(field.id)
  
  if (permission.hiddenInDetail) return false
  if (permission.readonly) return false
  if (!permission.editable) return false
  if (!permission.visible) return false
  
  if (SYSTEM_FIELDS.includes(field.id)) return false
  
  return true
}

function getFieldValue(field) {
  if (!props.data) return null
  return props.data[field.id]
}

function getFieldDisplayValue(field) {
  // [DECORATIVE] [NEW] v1.3 / FR-6.6: 优先后端 display_values
  if (props.data?.display_values?.[field.id] !== undefined) {
    return props.data.display_values[field.id]
  }

  const value = getFieldValue(field)
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  
  if (field.type === 'boolean') {
    return value ? '是' : '否'
  }
  
  if (field.display_field && props.data[field.display_field]) {
    return props.data[field.display_field]
  }
  
  if (field.formatter) {
    return field.formatter(value, props.data)
  }
  
  return value
}

function getFieldOptions(field) {
  if (field.enum_values && field.enum_values.length > 0) {
    return field.enum_values.map(opt => ({
      value: opt.value != null ? opt.value : opt.id,
      label: opt.label || opt.name || String(opt.value ?? opt.id ?? '')
    }))
  }
  if (field.options && field.options.length > 0) {
    return field.options.map(opt => ({
      value: opt.value != null ? opt.value : opt.id,
      label: opt.label || opt.name || String(opt.value ?? opt.id ?? '')
    }))
  }
  // 关联/引用字段：缺少 options 时，用当前值 + _display 字段构造最小选项，
  // 避免编辑态 select 显示为空（用户至少能看到当前关联记录）。
  if (field.type === 'association' || field.type === 'reference') {
    const currentValue = props.data?.[field.id]
    const displayKey = field.id + '_display'
    const currentDisplay = props.data?.[displayKey]
    if (currentValue !== null && currentValue !== undefined && currentDisplay) {
      return [{ value: currentValue, label: String(currentDisplay) }]
    }
  }
  return []
}

function _isEnumMatch(optValue, dataValue) {
  if (optValue === dataValue) return true
  if (String(optValue) === String(dataValue)) return true
  const numOpt = Number(optValue)
  const numData = Number(dataValue)
  if (!isNaN(numOpt) && !isNaN(numData) && numOpt === numData) return true
  return false
}

function formatEnumValue(field, value) {
  if ((!field.enum_values || field.enum_values.length === 0) && (!field.options || field.options.length === 0)) return value
  
  const options = field.enum_values || field.options || []
  const option = options.find(o => _isEnumMatch(o.value, value) || _isEnumMatch(o.id, value))
  return option?.label || option?.name || value
}

function getEnumTagType(field, value) {
  if ((!field.enum_values || field.enum_values.length === 0) && (!field.options || field.options.length === 0)) return ''
  
  const options = field.enum_values || field.options || []
  const option = options.find(o => _isEnumMatch(o.value, value) || _isEnumMatch(o.id, value))
  return option?.color || option?.tagType || option?.tag_type || ''
}

function formatDateValue(value, type) {
  if (!value) return '-'
  
  let date
  
  if (typeof value === 'number') {
    date = new Date(value)
  } else if (typeof value === 'string') {
    if (/^\d+$/.test(value)) {
      date = new Date(parseInt(value, 10))
    } else {
      date = new Date(value)
    }
  } else if (value instanceof Date) {
    date = value
  } else {
    return String(value)
  }
  
  if (isNaN(date.getTime())) {
    return String(value)
  }
  
  const pad = (n) => String(n).padStart(2, '0')
  
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  const seconds = pad(date.getSeconds())
  
  if (type === 'date') {
    return `${year}-${month}-${day}`
  }
  
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

function handleAssociationClick(field, item) {
  emit('association-click', { field, item, data: props.data })
}
</script>

<style scoped>
.detail-section {
  width: 100%;
}

.ds-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.ds-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ds-actions {
  display: flex;
  gap: 8px;
}

.ds-actions .el-button {
  border-radius: 6px;
}

.ds-loading,
.ds-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.ds-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.ds-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ds-item--full {
  grid-column: span 2;
}

.ds-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.ds-required {
  color: var(--el-color-danger);
  margin-left: 2px;
}

.ds-value {
  font-size: 14px;
  color: var(--el-text-color-primary);
  line-height: 1.5;
  min-height: 22px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.ds-value--empty {
  color: var(--el-text-color-placeholder);
}

.ds-value :deep(.el-input),
.ds-value :deep(.el-select),
.ds-value :deep(.el-date-editor),
.ds-value :deep(.el-input-number) {
  width: 100%;
}

.ds-json {
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  overflow: auto;
  max-height: 300px;
}

:deep(.el-tag) {
  border-radius: 4px;
}

:deep(.el-button) {
  border-radius: 6px;
}
</style>
