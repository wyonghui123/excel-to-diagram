<!--
  [V1.2.0 2026-06-15] BoListSelector.vue - 跨域关系 List 模式 (4 级级联 + 跨域 toggle)
  ===================================================================
  用途: 跨域关系创建时, 默认用 4 级级联 (Domain → Sub-domain → Service Module → BO) 选择 BO
  行为:
    - 默认套 read scope (用户只能看到自己有 read 权限的 BO)
    - 用户主动勾选"跨域浏览"后, 调 boService.query 时带 ?include_out_of_scope=true&reason=...
    - toggle 状态会写入 /_diagnostics 供后续审计 (后端 B.3 落地)
  Props:
    - productId (Number, required)
    - allowCrossDomain (Boolean): 是否允许"跨域浏览" toggle (默认 true)
    - disabled (Boolean)
    - filterParams (Object): 额外的过滤参数
  Emits:
    - update:selected (Object): 选中的 BO { id, code, name, ... }
    - cross-domain-toggled (Boolean): toggle 状态变化
  Spec: .trae/specs/cross-domain-relationship-permission/spec.md (T3.1.1 + Option B)
-->
<template>
  <div class="bo-list-selector">
    <!-- 跨域浏览 toggle (Option B) -->
    <div v-if="allowCrossDomain" class="bo-list-selector__toggle">
      <el-switch
        v-model="crossDomainEnabled"
        active-text="允许跨域浏览"
        inactive-text="仅本域"
        inline-prompt
        :disabled="disabled"
        @change="handleCrossDomainToggle"
      />
      <el-tooltip
        v-if="crossDomainEnabled"
        content="您将看到所有域的 BO (含无 read 权限的)。写时仍受 functional perm (OR-edit) 校验, 不一定可创建。"
        placement="top"
      >
        <el-icon class="bo-list-selector__toggle-icon"><Warning /></el-icon>
      </el-tooltip>
    </div>

    <!-- 4 级级联 / 列表选择 -->
    <SearchHelpDialog
      v-model:visible="dialogVisible"
      :value-help-config="valueHelpConfig"
      :custom-fetcher="customFetcher"
      :selected-value="selectedValue"
      @confirm="handleConfirm"
    />

    <!-- 触发按钮 -->
    <el-button
      :disabled="disabled"
      @click="openDialog"
    >
      {{ selectedBo ? '已选择: ' + (selectedBo.name || selectedBo.code) : '从列表选择 BO' }}
    </el-button>

    <!-- 已选 BO 信息 -->
    <div v-if="selectedBo" class="bo-list-selector__selected">
      <el-tag closable @close="clearSelection">
        <strong>{{ selectedBo.code }}</strong> — {{ selectedBo.name }}
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import SearchHelpDialog from '@/components/common/SearchHelpDialog.vue'
import boService from '@/services/boService'

const props = defineProps({
  productId: {
    type: [Number, String],
    required: true
  },
  modelValue: {
    type: Object,
    default: null
  },
  allowCrossDomain: {
    type: Boolean,
    default: true
  },
  disabled: {
    type: Boolean,
    default: false
  },
  filterParams: {
    type: Object,
    default: () => ({})
  },
  displayColumns: {
    type: Array,
    default: () => [
      { prop: 'code', label: '编码', width: 140 },
      { prop: 'name', label: '名称', width: 200 }
    ]
  }
})

const emit = defineEmits([
  'update:modelValue',
  'update:selected',
  'cross-domain-toggled',
  'change'
])

// ===== State =====
const dialogVisible = ref(false)
const crossDomainEnabled = ref(false)
const selectedBo = ref(props.modelValue)

// ===== Computed =====
const valueHelpConfig = computed(() => ({
  source: {
    type: 'bo',
    target_bo: 'business_object',
    value_field: 'id',
    display_field: 'name',
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

const selectedValue = computed(() => {
  return selectedBo.value?.id ?? ''
})

// ===== Watch =====
watch(() => props.modelValue, (val) => {
  selectedBo.value = val
}, { immediate: true, deep: true })

// ===== Custom Fetcher (根据 crossDomainEnabled 决定是否带 include_out_of_scope) =====
const customFetcher = (params) => {
  const { page, pageSize, keyword } = params || {}
  const queryParams = {
    page: page || 1,
    page_size: pageSize || 15,
    product_id: props.productId,
    ...props.filterParams
  }
  if (keyword) queryParams.search = keyword

  // 跨域浏览开关: 带 include_out_of_scope + reason
  if (crossDomainEnabled.value) {
    queryParams.include_out_of_scope = true
    queryParams.reason = 'cross_domain_relationship_create'
  }

  return boService.query('business_object', queryParams).then(res => {
    if (!res.success) return { success: false, data: { items: [], total: 0 } }
    const rawData = res.data?.items || res.data || []
    return {
      success: true,
      data: {
        items: rawData.map(item => ({
          value: item.id,
          display: item.name || item.code,
          code: item.code || '',
          _raw: item
        })),
        total: res.data?.total ?? rawData.length
      }
    }
  })
}

// ===== Methods =====
function openDialog() {
  if (props.disabled) return
  dialogVisible.value = true
}

function handleConfirm(items) {
  // SearchHelpDialog 单选回调: items = { value, display, code, _raw }
  const item = Array.isArray(items) ? items[0] : items
  if (!item) return
  const bo = item._raw || {
    id: item.value,
    code: item.code,
    name: item.display
  }
  selectedBo.value = bo
  emit('update:modelValue', bo)
  emit('update:selected', bo)
  emit('change', bo)
  dialogVisible.value = false
}

function clearSelection() {
  selectedBo.value = null
  emit('update:modelValue', null)
  emit('update:selected', null)
  emit('change', null)
}

function handleCrossDomainToggle(val) {
  // 通知父组件, 父组件可写入 /_diagnostics (后端审计)
  emit('cross-domain-toggled', val)
  // 跨域模式开启时, 强制刷新列表 (让新数据可见)
  if (dialogVisible.value) {
    // 触发 dialog 内部 fetcher 重新加载
    dialogVisible.value = false
    setTimeout(() => { dialogVisible.value = true }, 50)
  }
}

defineExpose({
  openDialog,
  clearSelection,
  isCrossDomain: () => crossDomainEnabled.value
})
</script>

<style scoped>
.bo-list-selector {
  width: 100%;
}

.bo-list-selector__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px 12px;
  background-color: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: var(--el-border-radius-base);
}

.bo-list-selector__toggle-icon {
  color: var(--el-color-warning);
  cursor: help;
}

.bo-list-selector__selected {
  margin-top: 8px;
}
</style>
