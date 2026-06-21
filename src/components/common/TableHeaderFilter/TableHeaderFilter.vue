<template>
  <el-popover
    ref="popoverRef"
    :visible="popoverVisible"
    :placement="dynamicPlacement"
    :width="popoverWidth"
    trigger="manual"
    :show-arrow="true"
    :offset="4"
    :popper-options="{
      strategy: 'fixed',
      modifiers: [
        { name: 'preventOverflow', options: { boundary: 'viewport', padding: 8 } },
        { name: 'flip', options: { fallbackPlacements: ['bottom-end', 'top-start', 'top-end'], padding: 8 } },
        { name: 'shift', options: { padding: 8 } }
      ]
    }"
    @update:visible="handleVisibleChange"
  >
    <template #reference>
      <span 
        :ref="el => { if (el) { filterTriggerRef = el; setupFilterTriggerListener(el) } }"
        class="filter-trigger" 
        :class="{ 'is-active': isFiltered }" 
        :title="isFiltered ? filterTooltip : '点击设置过滤条件'"
      >
        <el-icon class="filter-icon" :class="{ 'is-active': isFiltered }">
          <Search />
        </el-icon>
        <!-- 过滤计数徽章 -->
        <span v-if="isFiltered && filterCount > 0" class="filter-badge">
          {{ filterCount }}
        </span>
      </span>
    </template>
    
    <div class="filter-panel" @click.stop>
      <!-- 文本搜索过滤 -->
      <div v-if="filterType === 'search'" class="filter-content">
        <el-input
          ref="searchInputRef"
          v-model="searchValue"
          :placeholder="placeholder || '请输入搜索条件'"
          clearable
          size="default"
          @input="handleSearchInput"
          @keyup.enter="handleConfirm"
        />
        <div class="filter-actions">
          <el-button size="small" @click.stop="handleReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleConfirm">确定</el-button>
        </div>
      </div>
      
      <!-- 下拉选择过滤（支持多选） -->
      <div v-else-if="filterType === 'select'" class="filter-content">
        <div class="filter-actions filter-actions--top">
          <el-button size="small" @click.stop="handleReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleConfirm">确定</el-button>
        </div>
        <el-select
          v-model="selectValue"
          :placeholder="enumLoading ? '加载中...' : placeholder || '请选择'"
          :multiple="true"
          :collapse-tags="true"
          :collapse-tags-tooltip="true"
          :loading="enumLoading"
          clearable
          size="default"
          style="width: 100%"
          popper-class="filter-select-dropdown"
          @change="handleSelectChange"
          @visible-change="handleSelectVisibleChange"
        >
          <el-option
            v-for="opt in resolvedOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
      
      <!-- 日期范围过滤 -->
      <div v-else-if="filterType === 'date-range'" class="filter-content">
        <div class="filter-actions filter-actions--top">
          <el-button size="small" @click.stop="handleReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleConfirm">确定</el-button>
        </div>
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          size="default"
          style="width: 100%"
          popper-class="filter-datepicker-popper"
          @change="handleDateChange"
        />
      </div>
      
      <!-- 数字范围过滤 -->
      <div v-else-if="filterType === 'number-range'" class="filter-content">
        <div class="number-range-inputs">
          <el-input-number
            v-model="numberMin"
            :placeholder="'最小值'"
            controls-position="right"
            size="default"
            style="width: 100%"
          />
          <span class="number-range-sep">至</span>
          <el-input-number
            v-model="numberMax"
            :placeholder="'最大值'"
            controls-position="right"
            size="default"
            style="width: 100%"
          />
        </div>
        <div class="filter-actions">
          <el-button size="small" @click.stop="handleReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleConfirm">确定</el-button>
        </div>
      </div>
      
      <!-- 多选过滤 -->
      <div v-else-if="filterType === 'multi-select'" class="filter-content">
        <el-checkbox-group v-model="multiValues" size="default" @change="handleCheckboxChange">
          <el-checkbox
            v-for="opt in resolvedOptions"
            :key="opt.value"
            :label="opt.value"
          >
            {{ opt.label }}
          </el-checkbox>
        </el-checkbox-group>
        <div class="filter-actions">
          <el-button size="small" @click.stop="handleReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleConfirm">确定</el-button>
        </div>
      </div>

      <!-- Value Help 过滤 -->
      <div v-else-if="filterType === 'value_help' && resolvedValueHelpConfig" class="filter-content">
        <div class="filter-actions filter-actions--top">
          <el-button size="small" @click.stop="handleValueHelpReset">重置</el-button>
          <el-button type="primary" size="small" @click.stop="handleValueHelpConfirm">确定</el-button>
        </div>
        <ValueHelpField
          ref="valueHelpRef"
          :model-value="valueHelpValue"
          :value-help-config="resolvedValueHelpConfig"
          :placeholder="placeholder"
          :form-values="formValues"
          @update:model-value="handleValueHelpChange"
          @update:displayValue="handleValueHelpDisplayChange"
        />
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { Search } from '@element-plus/icons-vue'
import ValueHelpField from '@/components/common/ValueHelpField.vue'

const props = defineProps({
  filterType: {
    type: String,
    default: 'search'
  },
  placeholder: {
    type: String,
    default: ''
  },
  options: {
    type: Array,
    default: () => []
  },
  enumType: {
    type: String,
    default: ''
  },
  modelValue: {
    type: [String, Array, Object],
    default: null
  },
  width: {
    type: Number,
    default: 240
  },
  valueHelpConfig: {
    type: Object,
    default: null
  },
  // 当前过滤上下文（用于 value_help 的 parameter_bindings，如 version_id）
  formValues: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue', 'filter-change'])

const popoverVisible = ref(false)
const manualCloseRequested = ref(false)
const popoverRef = ref(null)  // Popover 元素引用
const filterTriggerRef = ref(null)  // 过滤触发器引用
const searchInputRef = ref(null)
const valueHelpRef = ref(null)  // Value Help 组件引用
const valueHelpValue = ref(null)  // Value Help 临时值（确认前）
const valueHelpDisplayValue = ref('')  // Value Help 显示文本（确认前）
const searchValue = ref('')
const selectValue = ref([])
const dateRange = ref([])
const numberMin = ref(undefined)
const numberMax = ref(undefined)
const multiValues = ref([])
const dynamicOptions = ref([])
const enumLoading = ref(false)
const dynamicPlacement = ref('bottom-start')

const resolvedOptions = computed(() => {
  if (props.options && props.options.length > 0) return props.options
  if (dynamicOptions.value.length > 0) return dynamicOptions.value
  return []
})

// 确保 valueHelpConfig 有默认值，支持多选
const resolvedValueHelpConfig = computed(() => {
  if (!props.valueHelpConfig || !props.valueHelpConfig.behavior) {
    return null
  }
  return {
    ...props.valueHelpConfig,
    behavior: {
      ...props.valueHelpConfig.behavior,
      multiple: props.valueHelpConfig.behavior?.multiple !== undefined
        ? props.valueHelpConfig.behavior.multiple
        : true  // 默认启用多选
    }
  }
})

async function loadEnumOptions() {
  if (!props.enumType || props.options?.length > 0 || dynamicOptions.value.length > 0) return
  enumLoading.value = true
  try {
    const { default: EnumService } = await import('@/services/enumService.js')
    const values = await EnumService.loadOptions(props.enumType, { cache: true, throwError: false })
    dynamicOptions.value = values.map(v => ({
      value: v.value || v.code,
      label: v.label || v.name || v.value || v.code
    }))
  } catch (e) {
    console.warn('[TableHeaderFilter] 加载枚举选项失败:', e)
  } finally {
    enumLoading.value = false
  }
}

watch(() => props.enumType, (newVal) => {
  if (newVal) loadEnumOptions()
}, { immediate: true })

// 是否已设置过滤条件
const isFiltered = computed(() => {
  if (props.modelValue === null || props.modelValue === undefined) {
    return false
  }
  if (Array.isArray(props.modelValue)) {
    return props.modelValue.length > 0
  }
  if (typeof props.modelValue === 'string') {
    return props.modelValue !== ''
  }
  return true
})

// 过滤条件数量
const filterCount = computed(() => {
  if (!isFiltered.value) return 0
  
  if (props.filterType === 'date-range' && Array.isArray(props.modelValue)) {
    return props.modelValue.filter(v => v).length
  }
  if (props.filterType === 'number-range' && Array.isArray(props.modelValue)) {
    return props.modelValue.filter(v => v !== undefined && v !== null && v !== '').length
  }
  if ((props.filterType === 'select' || props.filterType === 'multi-select') && Array.isArray(props.modelValue)) {
    return props.modelValue.length
  }
  if (props.filterType === 'value_help') {
    return props.modelValue ? 1 : 0
  }
  return 1
})

// 当前过滤值显示文本
const currentFilterDisplay = computed(() => {
  if (!isFiltered.value) return ''
  
  switch (props.filterType) {
    case 'search':
      return `包含 "${props.modelValue}"`
    case 'select':
      // 多选时显示已选项数量或具体标签
      if (Array.isArray(props.modelValue) && props.modelValue.length > 0) {
        const labels = props.modelValue.map(val => {
          const opt = resolvedOptions.value.find(o => o.value === val)
          return opt ? opt.label : val
        })
        if (labels.length <= 2) {
          return labels.join('、')
        }
        return `${labels[0]}、${labels[1]} 等 ${labels.length} 项`
      }
      return '未选择'
    case 'date-range':
      if (Array.isArray(props.modelValue) && props.modelValue.length === 2) {
        return `${props.modelValue[0] || '...'} 至 ${props.modelValue[1] || '...'}`
      }
      return '已设置时间范围'
    case 'number-range':
      if (Array.isArray(props.modelValue)) {
        const min = props.modelValue[0]
        const max = props.modelValue[1]
        if (min !== undefined && min !== null && max !== undefined && max !== null) {
          return `${min} 至 ${max}`
        }
        if (min !== undefined && min !== null) return `≥ ${min}`
        if (max !== undefined && max !== null) return `≤ ${max}`
      }
      return '已设置数值范围'
    case 'multi-select':
      if (Array.isArray(props.modelValue)) {
        return `已选 ${props.modelValue.length} 项`
      }
      return '已选择'
    case 'value_help':
      // 使用已保存的显示文本
      if (valueHelpDisplayValue.value) {
        // 如果是多选且显示文本包含逗号，格式化显示
        if (Array.isArray(props.modelValue) && props.modelValue.length > 0) {
          const displays = valueHelpDisplayValue.value.split(',').map(s => s.trim())
          if (displays.length <= 2) {
            return displays.join('、')
          }
          return `${displays[0]}、${displays[1]} 等 ${displays.length} 项`
        }
        return valueHelpDisplayValue.value
      }
      // 回退：显示值
      if (Array.isArray(props.modelValue)) {
        return `已选 ${props.modelValue.length} 项`
      }
      return String(props.modelValue)
    default:
      return String(props.modelValue)
  }
})

// 过滤提示文本
const filterTooltip = computed(() => {
  return currentFilterDisplay.value ? `当前过滤: ${currentFilterDisplay.value}` : '点击设置过滤条件'
})

// Popover 宽度
const popoverWidth = computed(() => {
  if (props.filterType === 'date-range') {
    return 360
  }
  if (props.filterType === 'number-range') {
    return 320
  }
  if (props.filterType === 'multi-select') {
    return Math.max(props.width, 200)
  }
  return Math.max(props.width, 240)
})

// 监听外部值变化
watch(() => props.modelValue, (newVal) => {
  initFromValue(newVal)
}, { immediate: true })

// 监听 popover 打开，自动聚焦输入框
watch(popoverVisible, async (visible) => {
  if (visible) {
    await nextTick()
    if (props.filterType === 'search' && searchInputRef.value) {
      searchInputRef.value.focus()
    }
    // 动态修正 popover 位置，防止溢出视口
    await nextTick()
    constrainPopoverPosition()
    // 监听器已在 togglePopover 中添加
  } else {
    // 移除监听器
    document.removeEventListener('click', handleClickOutside, true)
  }
})

// 动态约束 popover 位置，防止超出视口右边界
function constrainPopoverPosition() {
  // el-popover teleported 到 body 后的 DOM 选择
  let popoverEl = popoverRef.value?.$el?.popper || popoverRef.value?.$el
  
  // 确保是 DOM 元素
  if (!popoverEl || typeof popoverEl.getBoundingClientRect !== 'function') {
    // 尝试从 popoverRef 中获取 popper 元素
    if (popoverRef.value?.popperRef?.popperInstanceRef?.popper) {
      popoverEl = popoverRef.value.popperRef.popperInstanceRef.popper
    } else {
      return
    }
  }
  
  // 再次检查
  if (!popoverEl || typeof popoverEl.getBoundingClientRect !== 'function') return

  const rect = popoverEl.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const padding = 8

  // 右边界溢出检测与修正
  if (rect.right > viewportWidth - padding) {
    const overflow = rect.right - viewportWidth + padding
    const currentLeft = parseFloat(getComputedStyle(popoverEl).left) || rect.left
    popoverEl.style.left = `${currentLeft - overflow}px`
  }

  // 左边界溢出检测与修正（flip 到左侧时可能发生）
  if (rect.left < padding) {
    const underflow = padding - rect.left
    const currentLeft = parseFloat(getComputedStyle(popoverEl).left) || rect.left
    popoverEl.style.left = `${currentLeft + underflow}px`
  }
}

// 点击外部区域关闭 popover
function handleClickOutside(event) {
  if (!popoverVisible.value) return

  const target = event.target

  // 点击的是触发器 → 不关闭（由 togglePopover 处理切换）
  if (target.closest('.filter-trigger')) return

  // 点击的是当前 popover 面板内部（filter-panel）→ 不关闭
  if (target.closest('.filter-panel')) return

  // 点击的是当前组件的 el-popover 元素本身 → 不关闭
  // 需要检查当前 popover 的 reference 元素
  const triggerEl = filterTriggerRef.value
  if (triggerEl && triggerEl.closest('.el-popover')) {
    if (triggerEl.closest('.el-popover').contains(target)) return
  }

  // 点击的是 Element Plus 的弹出层（select下拉、日期选择器等）→ 不关闭
  if (target.closest('.el-select-dropdown')) return
  if (target.closest('.el-picker-panel')) return
  if (target.closest('.el-date-editor')) return
  if (target.closest('.el-overlay')) return

  // 点击的是其他区域 → 关闭
  manualCloseRequested.value = true
  popoverVisible.value = false
  initFromValue(props.modelValue)
}

// 初始化内部值
function initFromValue(value) {
  if (value === null || value === undefined) {
    searchValue.value = ''
    selectValue.value = []
    dateRange.value = []
    numberMin.value = undefined
    numberMax.value = undefined
    multiValues.value = []
    valueHelpValue.value = null
    return
  }
  
  switch (props.filterType) {
    case 'search':
      searchValue.value = typeof value === 'string' ? value : ''
      break
    case 'select':
      // 支持单值或数组
      selectValue.value = Array.isArray(value) ? [...value] : (value ? [value] : [])
      break
    case 'date-range':
      dateRange.value = Array.isArray(value) ? [...value] : []
      break
    case 'number-range':
      if (Array.isArray(value)) {
        numberMin.value = value[0] !== undefined && value[0] !== null ? value[0] : undefined
        numberMax.value = value[1] !== undefined && value[1] !== null ? value[1] : undefined
      } else {
        numberMin.value = undefined
        numberMax.value = undefined
      }
      break
    case 'multi-select':
      multiValues.value = Array.isArray(value) ? [...value] : []
      break
    case 'value_help':
      valueHelpValue.value = value
      break
  }
}

function handleValueHelpChange(value) {
  // 保存临时值，不直接关闭弹窗
  valueHelpValue.value = value
}

function handleValueHelpDisplayChange(displayValue) {
  // 保存显示文本，用于当前过滤显示
  valueHelpDisplayValue.value = displayValue
}

function handleValueHelpConfirm() {
  // 确认时 emit 值并关闭弹窗
  emit('update:modelValue', valueHelpValue.value)
  emit('filter-change', valueHelpValue.value)
  manualCloseRequested.value = true
  popoverVisible.value = false
}

function handleValueHelpReset() {
  // 重置时 emit null 并关闭弹窗
  valueHelpValue.value = null
  valueHelpDisplayValue.value = ''
  emit('update:modelValue', null)
  emit('filter-change', null)
  manualCloseRequested.value = true
  popoverVisible.value = false
}

// 处理多选下拉的变化（阻止下拉关闭）
function handleSelectChange(val) {
  // 多选模式下，选择后下拉应该保持打开
  // 这里只是记录变化，不需要额外处理
}

// 处理多选下拉的显示/隐藏状态
function handleSelectVisibleChange(visible) {
  // 如果下拉关闭了，不需要做任何事情
  // popover 会处理关闭逻辑
}

// 处理 Popover 显示/隐藏
function handleVisibleChange(visible) {
  if (!visible && !manualCloseRequested.value) {
    return
  }
  popoverVisible.value = visible
  if (!visible) {
    initFromValue(props.modelValue)
  }
  manualCloseRequested.value = false
}

function togglePopover() {
  if (popoverVisible.value) {
    manualCloseRequested.value = true
    // 关闭时直接移除监听器
    document.removeEventListener('click', handleClickOutside, true)
  }
  // 打开前根据触发器位置动态决定 placement
  if (!popoverVisible.value) {
    calculateDynamicPlacement()
  }
  popoverVisible.value = !popoverVisible.value

  // 打开后立即添加监听器（不使用 setTimeout）
  if (popoverVisible.value) {
    nextTick(() => {
      document.addEventListener('click', handleClickOutside, true)
    })
  }
}

// 设置过滤触发器点击监听器
let filterTriggerClickHandler = null
function setupFilterTriggerListener(el) {
  if (!el) return
  
  // 移除旧的监听器
  if (filterTriggerClickHandler) {
    el.removeEventListener('click', filterTriggerClickHandler)
  }
  
  // 创建新的监听器
  filterTriggerClickHandler = (e) => {
    e.stopPropagation()
    togglePopover()
  }
  
  // 添加监听器
  el.addEventListener('click', filterTriggerClickHandler)
}

// 根据触发器在视口中的位置动态计算 placement
function calculateDynamicPlacement() {
  // 优先使用 filterTriggerRef（ref 回调设置的引用）
  let el = filterTriggerRef.value

  // fallback：在 DOM 中查找最近的 trigger
  if (!el) {
    el = document.querySelector('.filter-trigger.is-active') ||
         document.querySelector('.filter-trigger:hover') ||
         document.querySelector('.filter-trigger')
  }

  if (!el) {
    dynamicPlacement.value = 'bottom-start'
    return
  }

  const rect = el.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const popoverW = popoverWidth.value

  // 如果触发器右边缘 + 弹窗宽度 > 视口宽度 → 用 bottom-end（弹窗左对齐触发器右边缘）
  if (rect.left + popoverW > viewportWidth - 8) {
    dynamicPlacement.value = 'bottom-end'
  } else {
    dynamicPlacement.value = 'bottom-start'
  }
}

// 搜索输入（实时过滤）
function handleSearchInput() {
  // 可选：实时过滤
}

// 多选框变化
function handleCheckboxChange() {
  // 可选：实时过滤
}

// 日期变化
function handleDateChange() {
  // 可选：实时过滤
}

// 确认过滤
function handleConfirm() {
  let value = null
  
  switch (props.filterType) {
    case 'search':
      value = searchValue.value.trim()
      break
    case 'select':
      // 始终返回数组
      value = selectValue.value && selectValue.value.length > 0 ? [...selectValue.value] : null
      break
    case 'date-range':
      value = dateRange.value && dateRange.value.length === 2 ? [...dateRange.value] : null
      break
    case 'number-range':
      if (numberMin.value !== undefined && numberMin.value !== null || numberMax.value !== undefined && numberMax.value !== null) {
        value = [numberMin.value ?? null, numberMax.value ?? null]
      } else {
        value = null
      }
      break
    case 'multi-select':
      value = multiValues.value && multiValues.value.length > 0 ? [...multiValues.value] : null
      break
  }
  
  emit('update:modelValue', value)
  emit('filter-change', value)
  manualCloseRequested.value = true
  popoverVisible.value = false
}

// 重置
function handleReset() {
  searchValue.value = ''
  selectValue.value = []
  dateRange.value = []
  numberMin.value = undefined
  numberMax.value = undefined
  multiValues.value = []
  
  emit('update:modelValue', null)
  emit('filter-change', null)
  manualCloseRequested.value = true
  popoverVisible.value = false
}

// 组件卸载时清理事件监听器
onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside, true)
  // 清理原生点击事件监听器
  if (filterTriggerRef.value && filterTriggerClickHandler) {
    filterTriggerRef.value.removeEventListener('click', filterTriggerClickHandler)
  }
})

// 原生点击事件监听器（作为后备方案）
onMounted(() => {
  nextTick(() => {
    // 延迟添加监听器，确保 DOM 完全渲染
    setTimeout(() => {
      const el = filterTriggerRef.value || document.querySelector('.filter-trigger')
      if (el && !filterTriggerClickHandler) {
        setupFilterTriggerListener(el)
      }
    }, 100)
  })
})
</script>

<style scoped>
/* 过滤触发器 - 默认隐藏，由父组件 .column-header:hover :deep(.filter-trigger) 控制显示 */
.filter-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 18px;
  height: 18px;
  margin-left: 4px;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0;
  z-index: 1;
}

.filter-icon {
  font-size: 11px;        /* 更小的图标（SAP 标准 10-12px） */
  color: #909399;
  transition: color 0.15s ease;
}

.filter-icon:hover {
  color: var(--el-color-primary, #ea580c);
}

.filter-icon.is-active {
  color: var(--el-color-primary, #ea580c);
}

/* 过滤计数徽章 - SAP 风格：小而精致 */
.filter-badge {
  position: absolute;
  top: -3px;              /* 更紧凑的定位 */
  right: -3px;
  min-width: 12px;
  height: 12px;
  padding: 0 2px;
  font-size: 9px;          /* 更小的字体 */
  line-height: 12px;
  text-align: center;
  color: #fff;
  background-color: #f56c6c;
  border-radius: 6px;
  transform: scale(1);     /* 不缩放，保持清晰 */
  font-weight: 500;
}

/* 弹窗面板 */
.filter-panel {
  padding: 16px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filter-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.number-range-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.number-range-sep {
  color: #909399;
  font-size: 13px;
  flex-shrink: 0;
}

/* 确保输入组件完整显示 */
:deep(.el-input),
:deep(.el-select) {
  width: 100%;
}

:deep(.el-date-editor) {
  width: 100% !important;
}

:deep(.el-date-editor .el-range-input) {
  width: 42%;
}

:deep(.el-date-editor .el-range-separator) {
  width: auto;
  padding: 0 4px;
}

.filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  margin-top: 4px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  background: #fff;
  z-index: 2;
  box-shadow: 0 -2px 4px rgba(0, 0, 0, 0.04);
}

/* 顶部版本：用于 select 类型，避免被 el-select 下拉覆盖 */
.filter-actions--top {
  position: static;
  border-top: none;
  border-bottom: 1px solid #f0f0f0;
  margin-top: 0;
  margin-bottom: 4px;
  padding-top: 0;
  padding-bottom: 12px;
  box-shadow: none;
}

/* 让 el-select 下拉可滚动，防止覆盖 filter-actions */
:deep(.filter-select-dropdown) {
  max-height: 180px !important;
  overflow-y: auto !important;
}

/* 让 el-date-picker 弹层可滚动 */
:deep(.filter-datepicker-popper) {
  max-height: 320px !important;
  overflow-y: auto !important;
}

/* 多选样式 */
:deep(.el-checkbox) {
  display: flex;
  margin-right: 0;
  padding: 6px 0;
  height: auto;
}

:deep(.el-checkbox-group) {
  max-height: 220px;
  overflow-y: auto;
  padding: 4px 0;
}

/* Tag 样式调整 */
:deep(.el-tag) {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
