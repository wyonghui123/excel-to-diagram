<template>
  <div class="association-selector">
    <div class="association-selector__header">
      <span class="association-selector__label">{{ label }}</span>
      <span v-if="required" class="association-selector__required">*</span>
      <el-button
        v-if="!disabled && !readonly"
        type="primary"
        size="small"
        @click="openDialog"
      >
        {{ selectedItems.length > 0 ? '修改' : '选择' }}
      </el-button>
    </div>

    <div v-if="selectedItems.length > 0" class="association-selector__selected">
      <el-tag
        v-for="item in selectedItems"
        :key="item.id ?? item.value"
        closable
        :disable-transitions="false"
        @close="removeItem(item)"
      >
        {{ item[displayField] || item.display || item.name || item.code || item.id }}
      </el-tag>
    </div>
    <div v-else class="association-selector__empty">
      {{ placeholder || '点击选择' }}
    </div>

    <!-- 统一使用 SearchHelpDialog，获得所有交互优化 -->
    <SearchHelpDialog
      v-model:visible="dialogVisible"
      :value-help-config="valueHelpConfig"
      :multiple="multiple"
      :selected-value="selectedValues"
      :custom-fetcher="associationFetcher"
      @confirm="handleConfirm"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import SearchHelpDialog from '@/components/common/SearchHelpDialog.vue'
import boService from '@/services/boService'

const props = defineProps({
  modelValue: {
    type: [Array, Object],
    default: () => []
  },
  objectType: {
    type: String,
    required: true
  },
  associationName: {
    type: String,
    required: true
  },
  label: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: ''
  },
  multiple: {
    type: Boolean,
    default: true
  },
  required: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  readonly: {
    type: Boolean,
    default: false
  },
  displayField: {
    type: String,
    default: 'name'
  },
  displayColumns: {
    type: Array,
    default: () => [
      { prop: 'code', label: '编码', width: 120 },
      { prop: 'name', label: '名称', width: 150 }
    ]
  },
  filterParams: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const dialogVisible = ref(false)
const selectedItems = ref([])

// ===== 构建 valueHelpConfig 供 SearchHelpDialog 使用 =====
const valueHelpConfig = computed(() => ({
  source: {
    type: 'bo',
    target_bo: props.objectType,
    value_field: 'id',
    display_field: props.displayField === 'name' ? 'name' : props.displayField,
    code_field: 'code'
  },
  presentation: {
    result_type: 'dialog',
    page_size: 15,
    display_mode: 'flat',
    display_columns: props.displayColumns.map(col => ({
      field: col.prop,
      label: col.label,
      width: col.width
    }))
  }
}))

// ===== 自定义 Fetcher：将 boService.query 结果映射为 SearchHelpDialog 格式 =====
const associationFetcher = (params) => {
  const { page, pageSize: ps, keyword } = params || {}
  const queryParams = {
    page: page || 1,
    page_size: ps || 15,
    ...props.filterParams
  }
  if (keyword) queryParams.search = keyword

  return boService.query(props.objectType, queryParams).then(res => {
    if (!res.success) return { success: false, data: { items: [], total: 0 } }

    const rawData = res.data?.items || []
    const mappedItems = rawData.map(item => ({
      value: item.id,
      display: item[props.displayField] || item.name || item.code || String(item.id),
      code: item.code || '',
      // 保留原始数据用于确认回调
      _raw: item
    }))

    return {
      success: true,
      data: {
        items: mappedItems,
        total: res.data?.total || rawData.length
      }
    }
  })
}

// ===== 已选值（SearchHelpDialog 需要的格式）=====
const selectedValues = computed(() => {
  if (props.multiple) {
    return selectedItems.value.map(item => item.id ?? item.value)
  }
  const first = selectedItems.value[0]
  return first ? (first.id ?? first.value) : ''
})

// ===== 外部 modelValue 同步 =====
watch(() => props.modelValue, {
  handler(val) {
    if (props.multiple) {
      selectedItems.value = Array.isArray(val) ? [...val] : []
    } else {
      selectedItems.value = val ? [val] : []
    }
  },
  immediate: true,
  deep: true
})

function openDialog() {
  dialogVisible.value = true
}

function removeItem(item) {
  if (props.disabled || props.readonly) return
  const key = item.id ?? item.value
  const index = selectedItems.value.findIndex(i => (i.id ?? i.value) === key)
  if (index > -1) {
    selectedItems.value.splice(index, 1)
    emitValue()
  }
}

function handleConfirm(items) {
  // SearchHelpDialog 确认回调：
  // 单选: items = { value, display, code, _raw }
  // 多选: items = [{ value, display, code, _raw }, ...]

  if (props.multiple) {
    const arr = Array.isArray(items) ? items : [items]
    selectedItems.value = arr.map(item => item._raw || {
      id: item.value,
      [props.displayField]: item.display,
      code: item.code
    })
  } else {
    const item = items
    selectedItems.value = [item._raw || {
      id: item.value,
      [props.displayField]: item.display,
      code: item.code
    }]
  }
  emitValue()
}

function emitValue() {
  if (props.multiple) {
    emit('update:modelValue', [...selectedItems.value])
    emit('change', [...selectedItems.value])
  } else {
    const value = selectedItems.value[0] || null
    emit('update:modelValue', value)
    emit('change', value)
  }
}

defineExpose({
  openDialog,
  selectedItems
})
</script>

<style scoped>
.association-selector {
  width: 100%;
}
.association-selector__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.association-selector__label {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.association-selector__required {
  color: var(--el-color-danger);
}
.association-selector__selected {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  min-height: 40px;
  background-color: var(--el-fill-color-blank);
}
.association-selector__empty {
  padding: 8px 12px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}
</style>
