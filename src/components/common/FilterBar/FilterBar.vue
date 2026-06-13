<template>
  <div class="filter-bar">
    <div class="filter-bar__body">
      <div class="filter-bar__fields">
        <div 
          v-for="field in fields" 
          :key="field.key"
          class="filter-bar__field"
          :class="'filter-bar__field--' + (field.type || 'text')"
        >
          <label class="filter-bar__label">{{ field.label }}</label>
          
          <div v-if="!field.type || field.type === 'text'" class="filter-bar__input-wrap">
            <input
              class="filter-bar__input"
              type="text"
              :placeholder="field.placeholder || '请输入' + field.label"
              :value="getModelValue(field.key)"
              @input="updateModel(field.key, $event.target.value)"
              @keyup.enter="$emit('search')"
            />
            <button 
              v-if="getModelValue(field.key)"
              class="filter-bar__clear"
              type="button"
              @click="updateModel(field.key, '')"
            >×</button>
          </div>
          
          <div v-else-if="field.type === 'select'" class="filter-bar__select-wrap">
            <select
              class="filter-bar__select"
              :value="getModelValue(field.key)"
              @change="updateModel(field.key, $event.target.value)"
            >
              <option v-if="field.placeholder && !hasEmptyOption(field)" value="">{{ field.placeholder }}</option>
              <option
                v-for="opt in (field.options || [])"
                :key="opt.value"
                :value="opt.value"
              >{{ opt.label }}</option>
            </select>
          </div>

          <div v-else-if="field.type === 'value_help'" class="filter-bar__value-help-wrap">
            <ValueHelpField
              :model-value="getModelValue(field.key)"
              :value-help-config="field.valueHelpConfig || field.value_help"
              :placeholder="field.placeholder || '请选择' + field.label"
              :form-values="modelValue"
              @update:model-value="updateModel(field.key, $event)"
            />
          </div>
          
          <div v-else-if="field.type === 'datetime'" class="filter-bar__datetime-wrap">
            <DateTimePicker
              :model-value="getModelValue(field.key)"
              :placeholder="field.placeholder || '请选择' + field.label"
              :show-time="field.showTime !== false"
              :show-seconds="field.showSeconds === true"
              size="md"
              clearable
              @update:model-value="updateModel(field.key, $event)"
            />
          </div>

          <div v-else-if="field.type === 'date-range' || field.type === 'datetime-range'" class="filter-bar__date-range-wrap">
            <DateTimePicker
              :model-value="getDateValue(field.key, 'start')"
              :placeholder="field.placeholder?.[0] || '开始日期'"
              :show-time="field.type === 'datetime-range'"
              :show-seconds="field.showSeconds === true"
              size="md"
              clearable
              @update:model-value="updateDateRange(field.key, 'start', $event)"
            />
            <span class="filter-bar__date-separator">~</span>
            <DateTimePicker
              :model-value="getDateValue(field.key, 'end')"
              :placeholder="field.placeholder?.[1] || '结束日期'"
              :show-time="field.type === 'datetime-range'"
              :show-seconds="field.showSeconds === true"
              size="md"
              clearable
              @update:model-value="updateDateRange(field.key, 'end', $event)"
            />
            <button
              v-if="hasDateRangeValue(field.key)"
              class="filter-bar__clear-inline"
              type="button"
              @click="clearDateRange(field.key)"
            >×</button>
          </div>
          
          <div v-else-if="field.type === 'number'" class="filter-bar__input-wrap">
            <input
              class="filter-bar__input"
              type="number"
              :placeholder="field.placeholder || '请输入' + field.label"
              :value="getModelValue(field.key)"
              @input="updateModel(field.key, $event.target.value)"
            />
          </div>

          <!-- 用户类型（渲染为文本输入框，支持模糊搜索） -->
          <div v-else-if="field.type === 'user'" class="filter-bar__input-wrap">
            <input
              class="filter-bar__input"
              type="text"
              :placeholder="field.placeholder || '请输入' + field.label"
              :value="getModelValue(field.key)"
              @input="updateModel(field.key, $event.target.value)"
              @keyup.enter="$emit('search')"
            />
            <button 
              v-if="getModelValue(field.key)"
              class="filter-bar__clear"
              type="button"
              @click="updateModel(field.key, '')"
            >×</button>
          </div>

          <!-- 多选下拉框 multi-select -->
          <div v-else-if="field.type === 'multi-select'" class="filter-bar__multi-select-wrap">
            <div 
              class="filter-bar__multi-select"
              @click.stop="toggleMultiSelect(field.key)"
              :class="{ active: activeMultiSelect === field.key }"
            >
              <span class="filter-bar__multi-value">
                {{ getMultiSelectLabel(field) }}
              </span>
              <span class="filter-bar__multi-arrow">▼</span>
            </div>
            
            <!-- 下拉面板 -->
            <div 
              v-if="activeMultiSelect === field.key"
              class="filter-bar__multi-dropdown"
              @click.stop
            >
              <div class="filter-bar__multi-header">
                <button 
                  class="filter-bar__multi-action"
                  @click="selectAllOptions(field)"
                >全选</button>
                <button 
                  class="filter-bar__multi-action"
                  @click="clearAllOptions(field)"
                >清空</button>
              </div>
              <div class="filter-bar__multi-options">
                <label 
                  v-for="opt in (field.options || [])" 
                  :key="opt.value"
                  class="filter-bar__multi-option"
                  :class="{ selected: isOptionSelected(field.key, opt.value) }"
                >
                  <input
                    type="checkbox"
                    :value="opt.value"
                    :checked="isOptionSelected(field.key, opt.value)"
                    @change="toggleOption(field.key, opt.value)"
                  />
                  <span>{{ opt.label }}</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="filter-bar__actions">
        <button 
          v-if="showReset"
          class="filter-bar__btn filter-bar__btn--reset"
          @click="handleReset"
        >重置</button>
        <button 
          class="filter-bar__btn filter-bar__btn--search"
          @click="$emit('search')"
        >查询</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { DateTimePicker } from '@/components/common'
import ValueHelpField from '@/components/common/ValueHelpField.vue'

const props = defineProps({
  fields: {
    type: Array,
    required: true,
    validator: (val) => val.every(f => f.key)
  },
  modelValue: {
    type: Object,
    default: () => ({})
  },
  showReset: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'search', 'reset'])

function getModelValue(key) {
  const val = props.modelValue?.[key]
  if (val === undefined || val === null) return ''
  return val
}

function updateModel(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function getDateValue(key, rangeType) {
  const val = props.modelValue?.[key]
  if (!val) return ''
  if (Array.isArray(val)) {
    return rangeType === 'start' ? (val[0] || '') : (val[1] || '')
  }
  return rangeType === 'start' ? val : ''
}

function updateDateRange(key, rangeType, value) {
  const currentVal = props.modelValue?.[key] || []
  const newVal = Array.isArray(currentVal) ? [...currentVal] : ['', '']
  
  if (rangeType === 'start') {
    newVal[0] = value
  } else {
    newVal[1] = value
  }
  
  emit('update:modelValue', { ...props.modelValue, [key]: newVal })
}

function hasDateRangeValue(key) {
  const val = props.modelValue?.[key]
  if (!val) return false
  if (Array.isArray(val)) return val[0] || val[1]
  return !!val
}

function clearDateRange(key) {
  emit('update:modelValue', { ...props.modelValue, [key]: [] })
}

function handleReset() {
  emit('update:modelValue', {})
  emit('reset')
}

function hasEmptyOption(field) {
  const options = field.options || []
  return options.some(opt => opt.value === '' || opt.value === null || opt.value === undefined)
}

// ============ Multi-Select Logic ============
const activeMultiSelect = ref(null)

function toggleMultiSelect(key) {
  activeMultiSelect.value = activeMultiSelect.value === key ? null : key
}

function getMultiSelectLabel(field) {
  const val = props.modelValue?.[field.key]
  if (!val || !Array.isArray(val) || val.length === 0) {
    return field.placeholder || '请选择' + field.label
  }
  
  const selectedLabels = val.map(v => {
    const opt = (field.options || []).find(o => o.value === v)
    return opt ? opt.label : v
  })
  
  if (selectedLabels.length <= 2) {
    return selectedLabels.join(', ')
  }
  return `已选 ${selectedLabels.length} 项`
}

function isOptionSelected(fieldKey, value) {
  const val = props.modelValue?.[fieldKey]
  return Array.isArray(val) && val.includes(value)
}

function toggleOption(fieldKey, value) {
  const currentVal = props.modelValue?.[fieldKey] || []
  const newVal = [...currentVal]
  
  const idx = newVal.indexOf(value)
  if (idx >= 0) {
    newVal.splice(idx, 1)
  } else {
    newVal.push(value)
  }
  
  emit('update:modelValue', { ...props.modelValue, [fieldKey]: newVal })
}

function selectAllOptions(field) {
  const allValues = (field.options || []).map(o => o.value)
  emit('update:modelValue', { ...props.modelValue, [field.key]: allValues })
}

function clearAllOptions(field) {
  emit('update:modelValue', { ...props.modelValue, [field.key]: [] })
}

// 点击外部关闭下拉框
const handleOutsideClick = () => {
  activeMultiSelect.value = null
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.filter-bar {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.filter-bar__body {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.filter-bar__fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  flex: 1;
  min-width: 0;
}

.filter-bar__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
  flex: 0 1 auto;
}

.filter-bar__field--date-range,
.filter-bar__field--datetime-range {
  min-width: 360px;
  max-width: 480px;
}

.filter-bar__field--datetime {
  min-width: 180px;
}

.filter-bar__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.filter-bar__input-wrap,
.filter-bar__select-wrap,
.filter-bar__date-wrap,
.filter-bar__date-range-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.filter-bar__input {
  width: 100%;
  height: var(--input-height, 32px);
  padding: 0 var(--spacing-sm);
  padding-right: 26px;
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
  box-sizing: border-box;
  transition: all 0.2s;
}

.filter-bar__input::placeholder {
  color: var(--color-text-quaternary);
}

.filter-bar__input:hover:not(:disabled) {
  border-color: var(--color-primary);
}

.filter-bar__input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(24,144,255,0.1);
}

.filter-bar__date-input {
  min-width: 110px;
  color-scheme: light;
}

.filter-bar__clear {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--radius-full);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s;
}

.filter-bar__clear:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.filter-bar__clear-inline {
  margin-left: 6px;
  padding: 0 6px;
  height: 28px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.filter-bar__clear-inline:hover {
  background: #ffccc7;
  color: #ff4d4f;
}

.filter-bar__select {
  width: 100%;
  height: var(--input-height, 32px);
  padding: 0 24px 0 var(--spacing-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3' fill='none' stroke='%23999' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  background-size: 10px;
  box-sizing: border-box;
  transition: all 0.2s;
}

.filter-bar__select:hover {
  border-color: var(--color-primary);
}

.filter-bar__select:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(24,144,255,0.1);
}

.filter-bar__date-range-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
}

.filter-bar__date-separator {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
  white-space: nowrap;
  flex-shrink: 0;
}

.filter-bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.filter-bar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--btn-height-sm);
  padding: 0 var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  border-radius: var(--radius-button);
  cursor: pointer;
  border: var(--border-width-thin) solid transparent;
  transition: all var(--transition-normal);
  box-sizing: border-box;
  font-family: var(--font-family);
}

.filter-bar__btn--reset {
  background: var(--color-bg-secondary);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

.filter-bar__btn--reset:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-bg-secondary);
}

.filter-bar__btn--search {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-text-inverse);
}

.filter-bar__btn--search:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

/* ============ Multi-Select Styles ============ */
.filter-bar__multi-select-wrap {
  position: relative;
}

.filter-bar__multi-select {
  width: 100%;
  min-width: 160px;
  height: var(--input-height, 32px);
  padding: 0 var(--spacing-sm) 0 24px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: all 0.2s;
  box-sizing: border-box;
  position: relative;
}

.filter-bar__multi-select::after {
  content: '';
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  border: 4px solid transparent;
  border-top-color: var(--color-text-quaternary);
  pointer-events: none;
}

.filter-bar__multi-select:hover {
  border-color: var(--color-primary);
}

.filter-bar__multi-select.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(24,144,255,0.1);
}

.filter-bar__multi-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
}

.filter-bar__multi-arrow {
  font-size: 10px;
  color: var(--color-text-quaternary);
  margin-left: var(--spacing-xs);
}

.filter-bar__multi-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 100%;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  z-index: 1000;
  animation: dropdownFadeIn 0.15s ease-out;
}

@keyframes dropdownFadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.filter-bar__multi-header {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-secondary);
}

.filter-bar__multi-action {
  padding: 2px var(--spacing-sm);
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.15s;
}

.filter-bar__multi-action:hover {
  color: var(--color-primary-hover);
  text-decoration: underline;
}

.filter-bar__multi-options {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
}

.filter-bar__multi-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background 0.15s;
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.filter-bar__multi-option:hover {
  background: var(--color-bg-secondary);
}

.filter-bar__multi-option.selected {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.filter-bar__multi-option input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  cursor: pointer;
}
</style>
