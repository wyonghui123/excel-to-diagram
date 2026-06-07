<template>
  <section class="perm-section">
    <div class="perm-header">
      <h4>
        <AppIcon name="layers" :size="14" />
        管理维度范围
      </h4>
      <span v-if="dimensionsLoading" class="summary-item">加载中...</span>
      <span v-else class="summary-item assigned">
        {{ configuredCount }} / {{ sortedDimensions.length }} 维度已配置
      </span>
    </div>

    <p class="perm-guide">
      配置角色的管理维度范围。系统将基于此自动推导菜单、功能权限和数据权限规则。
    </p>

    <div v-if="dimensions.length === 0" class="empty-hint">
      暂无可用的管理维度，请先确认元数据正确加载。
    </div>

    <div
      v-for="dim in sortedDimensions"
      :key="dim.id + '-' + refreshTrigger"
      class="dimension-row"
      :class="{ 'dimension-row--has-parent': getParentDim(dim.id) }"
    >
      <div class="dimension-row-header">
        <span class="dimension-label">{{ dim.name }}</span>
        <span class="dimension-code">{{ dim.id }}</span>
        <span v-if="getParentDim(dim.id)" class="dimension-cascade-hint">
          {{ getParentDim(dim.id).name }}
        </span>
      </div>

      <div class="dimension-values">
        <el-tag
          v-for="val in (selectedValues[dim.id] || [])"
          :key="val.id + '-' + readyFlag"
          closable
          size="small"
          :disable-transitions="false"
          @close="removeDimensionValue(dim.id, val.id)"
        >
          {{ val.name || val.code || val.id }}
        </el-tag>
        <el-button
          size="small"
          :icon="Plus"
          @click="openValuePicker(dim)"
        >
          添加{{ dim.name }}
        </el-button>
        <span v-if="getParentDim(dim.id) && !hasParentValues(dim.id)" class="cascade-disabled-hint">
          上级未选，所有选项可用
        </span>
        <span v-else-if="getParentDim(dim.id) && hasParentValues(dim.id)" class="cascade-active-hint">
          已按上级过滤
        </span>
      </div>

      <label class="inherit-toggle">
        <input
          type="checkbox"
          :checked="inheritFlags[dim.id] !== false"
          @change="toggleInherit(dim.id)"
        />
        <span>包含下级（自动扩展子级资源）</span>
      </label>
    </div>

    <div class="perm-actions-bar">
      <button class="btn btn-ghost" @click="autoDerive" :disabled="autoDeriving">
        {{ autoDeriving ? '推导中...' : '自动推导并应用' }}
      </button>
      <div class="actions-spacer"></div>
      <button
        class="btn btn-primary"
        @click="saveDimensionScopes"
        :disabled="saving"
      >
        {{ saving ? '保存中...' : '保存维度范围' }}
      </button>
    </div>

    <SearchHelpDialog
      v-show="pickerDim"
      v-model:visible="pickerVisible"
      :value-help-config="pickerValueHelpConfig"
      :multiple="true"
      :selected-value="pickerSelectedIds"
      :custom-fetcher="pickerFetcher"
      @confirm="handlePickerConfirm"
    />
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { AppIcon } from '@/components/common/AppIcon'
import SearchHelpDialog from '@/components/common/SearchHelpDialog.vue'
import * as permService from '@/services/permissionService'

const props = defineProps({
  roleId: {
    type: String,
    required: true
  }
})

const emit = defineEmits({
  'dimension-scopes-saved': () => true,
  'auto-derived': (result) => true
})

// [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
// 新的层级链: product → version → domain → sub_domain (4层)

const DIMENSION_PARENT_LABEL = {
  'version': '所属产品',
  'domain': '所属版本',
  'sub_domain': '所属领域'
  // 'service_module': '所属子领域',  // 已移除
  // 'business_object': '所属服务模块'  // 已移除
}

const dimensions = ref([])
const dimensionsLoading = ref(false)
const selectedValues = reactive({ product: [], version: [], domain: [], sub_domain: [] })
const inheritFlags = reactive({})
const saving = ref(false)
const refreshTrigger = ref(0)
const readyFlag = ref(0)
const autoDeriving = ref(false)

const pickerVisible = ref(false)
const pickerDim = ref(null)

const sortedDimensions = computed(() => {
  return [...dimensions.value].sort((a, b) => {
    const levelA = permService.DIMENSION_LEVEL_MAP[a.id] ?? 99
    const levelB = permService.DIMENSION_LEVEL_MAP[b.id] ?? 99
    return levelA - levelB
  })
})

const configuredCount = computed(() =>
  Object.values(selectedValues).filter(v => v && v.length > 0).length
)

function getParentDim(dimId) {
  const parentId = permService.DIMENSION_PARENT_MAP[dimId]
  if (!parentId) return null
  return dimensions.value.find(d => d.id === parentId) || null
}

function hasParentValues(dimId) {
  const parentId = permService.DIMENSION_PARENT_MAP[dimId]
  if (!parentId) return true
  const vals = selectedValues[parentId] || []
  return vals.length > 0
}

function getParentFilterParams(dimId) {
  const parentId = permService.DIMENSION_PARENT_MAP[dimId]
  if (!parentId) return {}
  const parentValues = selectedValues[parentId] || []
  if (parentValues.length === 0) return {}
  const parentField = permService.PARENT_FIELD_MAP[dimId]
  if (!parentField) return {}
  return { [`filter_${parentField}`]: parentValues.map(v => v.id) }
}

function cascadeClearDownstream(dimId) {
  const queue = [dimId]
  while (queue.length > 0) {
    const currentId = queue.shift()
    for (const childId of Object.keys(permService.DIMENSION_PARENT_MAP)) {
      if (permService.DIMENSION_PARENT_MAP[childId] === currentId) {
        selectedValues[childId] = []
        queue.push(childId)
      }
    }
  }
}

const parentValueSnapshots = reactive({})

function snapshotParentValues() {
  for (const childId of Object.keys(permService.DIMENSION_PARENT_MAP)) {
    const parentId = permService.DIMENSION_PARENT_MAP[childId]
    if (parentId) {
      parentValueSnapshots[childId] = [...(selectedValues[parentId] || [])].map(v => v.id).sort().join(',')
    }
  }
}

watch(() => {
  const result = {}
  for (const childId of Object.keys(permService.DIMENSION_PARENT_MAP)) {
    const parentId = permService.DIMENSION_PARENT_MAP[childId]
    if (parentId) {
      result[childId] = [...(selectedValues[parentId] || [])].map(v => v.id).sort().join(',')
    }
  }
  return result
}, (newSnapshots) => {
  for (const childId of Object.keys(newSnapshots)) {
    const oldSnapshot = parentValueSnapshots[childId]
    const newSnapshot = newSnapshots[childId]
    if (oldSnapshot !== undefined && oldSnapshot !== newSnapshot) {
      cascadeClearDownstream(permService.DIMENSION_PARENT_MAP[childId])
    }
  }
  snapshotParentValues()
}, { deep: true })

function initParentSnapshots() {
  snapshotParentValues()
}

// 用于在对话框关闭后保留已选择的 dimId
const lastConfirmedDimId = ref(null)

const pickerValueHelpConfig = computed(() => {
  if (!pickerDim.value) return {}
  const dimId = pickerDim.value.id
  const parentLabel = DIMENSION_PARENT_LABEL[dimId]
  const cols = [
    { field: 'name', label: '名称' },
    { field: 'code', label: '编码' }
  ]
  if (parentLabel) {
    cols.push({ field: 'parent_name', label: parentLabel })
  }
  return {
    source: { type: 'bo', target_bo: dimId },
    presentation: {
      display_mode: 'flat',
      display_columns: cols
    },
    behavior: { multiple: true }
  }
})

const pickerSelectedIds = computed(() => {
  if (!pickerDim.value) return []
  return (selectedValues[pickerDim.value.id] || []).map(v => v.id)
})

function getSelectedValues(dimId) {
  return selectedValues[dimId] || []
}

function toggleInherit(dimId) {
  inheritFlags[dimId] = !(inheritFlags[dimId] !== false)
}

async function loadDimensions() {
  dimensionsLoading.value = true
  try {
    const result = await permService.loadDimensions()
    const dims = (result.data?.dimensions || result.data || [])
    dimensions.value = dims

    for (const dim of dims) {
      if (!(dim.id in selectedValues)) {
        selectedValues[dim.id] = []
      }
      if (!(dim.id in inheritFlags)) {
        inheritFlags[dim.id] = true
      }
    }
  } catch (e) {
    console.error('Failed to load dimensions:', e)
    ElMessage.error('加载管理维度失败')
  } finally {
    dimensionsLoading.value = false
  }
}

async function loadDimensionScopes() {
  if (!props.roleId) return
  try {
    const result = await permService.loadDimensionScopes(props.roleId)
    if (result.success && result.data) {
      for (const scope of result.data) {
        const dimId = scope.dimension_code
        const values = scope.dimension_values || []
        if (values.length > 0) {
          // Use direct assignment with new array reference - Vue 3 Proxy tracks this
          selectedValues[dimId] = values.map(v => {
            if (typeof v === 'object') return v
            return { id: v, name: String(v), code: String(v) }
          })
        }
        inheritFlags[dimId] = scope.inherit_children !== 0 && scope.inherit_children !== false
      }
    }
    // Force re-render by toggling readyFlag and dimensions
    readyFlag.value++
    dimensions.value = [...dimensions.value]
  } catch (e) {
    console.error('Failed to load dimension scopes:', e)
  }
}

function removeDimensionValue(dimId, valId) {
  if (!selectedValues[dimId]) return
  const filtered = selectedValues[dimId].filter(v => v.id !== valId)
  selectedValues[dimId] = filtered
  if (filtered.length === 0) {
    cascadeClearDownstream(dimId)
  }
}

function openValuePicker(dim) {
  pickerDim.value = dim
  pickerVisible.value = true
}

async function pickerFetcher(params) {
  if (!pickerDim.value) return { success: true, data: { items: [], total: 0 } }
  const { page, pageSize: ps, keyword } = params || {}

  const serviceParams = {
    page: page || 1,
    page_size: ps || 20,
  }
  if (keyword) serviceParams.search = keyword

  const parentFilter = getParentFilterParams(pickerDim.value.id)
  Object.assign(serviceParams, parentFilter)

  // Get already selected IDs for delta filtering
  const selectedIds = new Set((selectedValues[pickerDim.value.id] || []).map(v => v.id))

  try {
    const result = await permService.loadDimensionInstances(pickerDim.value.id, serviceParams)
    const allInstances = result.data?.instances || result.data || []
    // Delta: exclude already selected items
    const instances = allInstances.filter(inst => !selectedIds.has(inst.id))
    const total = result.data?.pagination?.total_count || instances.length
    return {
      success: true,
      data: {
        items: instances.map(inst => ({
          ...inst,
          value: inst.id,
          display: inst.name || inst.code || String(inst.id)
        })),
        total
      }
    }
  } catch (e) {
    console.error('Failed to load dimension instances:', e)
    return { success: false, data: { items: [], total: 0 } }
  }
}

function handlePickerConfirm(selection) {
  if (!pickerDim.value) return
  const dimId = pickerDim.value.id
  const items = Array.isArray(selection) ? selection : (selection ? [selection] : [])
  
  // 增量添加：保留之前的选择，只添加新的
  const existingItems = selectedValues[dimId] || []
  const existingIds = new Set(existingItems.map(v => v.id))
  const newItems = items
    .filter(item => {
      const id = item.value != null ? item.value : item.id
      return !existingIds.has(id)
    })
    .map(item => {
      const id = item.value != null ? item.value : item.id
      // 尝试多种字段名来获取名称
      const name = item.display || item.name || item.title || item.label || item.username || item.code || String(id)
      return {
        id: id,
        name: name,
        code: item.code || ''
      }
    })
  
  selectedValues[dimId] = [...existingItems, ...newItems]
  
  // 保存 dimId，用于对话框重新打开时
  lastConfirmedDimId.value = dimId
  pickerVisible.value = false
  pickerDim.value = null
}

async function autoDerive() {
  autoDeriving.value = true
  try {
    await saveDimensionScopesInternal()
    const result = await permService.derivePermissions(props.roleId)
    if (result.success) {
      emit('auto-derived', result.data)
      ElMessage.success(
        `推导完成: ${result.data.recommended_menus?.length || 0} 个推荐菜单, ${result.data.derived_permissions?.length || 0} 项功能权限`
      )
    } else {
      ElMessage.error(result.message || '自动推导失败')
    }
  } catch (e) {
    console.error('Auto derive failed:', e)
    ElMessage.error('自动推导失败')
  } finally {
    autoDeriving.value = false
  }
}

async function saveDimensionScopesInternal() {
  const scopes = []
  for (const dim of sortedDimensions.value) {
    const vals = selectedValues[dim.id] || []
    if (vals.length > 0) {
      scopes.push({
        dimension_code: dim.id,
        dimension_values: vals.map(v => v.id),
        inherit_children: inheritFlags[dim.id] !== false,
        scope_mode: 'include'
      })
    }
  }

  const result = await permService.saveDimensionScopes(props.roleId, scopes)
  if (!result.success) {
    throw new Error(result.message || '保存失败')
  }
  return result
}

async function saveDimensionScopes() {
  saving.value = true
  try {
    await saveDimensionScopesInternal()
    ElMessage.success('维度范围保存成功')
    emit('dimension-scopes-saved')
  } catch (e) {
    console.error('Save dimension scopes failed:', e)
    ElMessage.error('保存维度范围失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadDimensions()
  await loadDimensionScopes()
  initParentSnapshots()
})
</script>

<style scoped lang="scss">
.perm-section {
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border-light);
}

.perm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.perm-header h4 {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.summary-item {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);

  &.assigned {
    background: var(--color-success-bg);
    color: var(--color-success);
  }
}

.perm-guide {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-primary, #1890ff);
  line-height: 1.5;
}

.empty-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
  text-align: center;
  padding: var(--spacing-lg);
}

.dimension-row {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.dimension-row-header {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.dimension-label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.dimension-code {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  font-family: monospace;
}

.dimension-cascade-hint {
  font-size: 11px;
  color: var(--yonyou-orange-600, #ea580c);
  background: rgba(234, 88, 12, 0.08);
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.dimension-cascade-hint::before {
  content: '上级: ';
  font-weight: 400;
  opacity: 0.7;
}

.dimension-row--has-parent {
  border-left: 3px solid var(--yonyou-orange-200, #fed7aa);
}

.dimension-values {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  align-items: center;
  margin-bottom: var(--spacing-sm);
}

.inherit-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;

  input[type="checkbox"] {
    cursor: pointer;
  }
}

.derived-preview {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: var(--radius-sm);

  h5 {
    margin: 0 0 var(--spacing-sm);
    font-size: var(--font-size-sm);
    color: var(--color-text-primary);
  }
}

.derived-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
}

.derived-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;

  strong {
    color: var(--color-primary);
  }
}

.derived-detail {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.derived-detail-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-spotlight);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.perm-actions-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-light);
}

.actions-spacer {
  flex: 1;
}

.btn {
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
    color: var(--color-text-primary);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  &.btn-primary {
    background: var(--yonyou-orange-600, #ea580c);
    color: white;
    border-color: var(--yonyou-orange-600, #ea580c);

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }
}

.cascade-disabled-hint {
  font-size: 11px;
  color: var(--color-text-quaternary);
  margin-left: var(--spacing-sm);
  font-style: italic;
}

.cascade-active-hint {
  font-size: 11px;
  color: var(--color-success, #22c55e);
  margin-left: var(--spacing-sm);
  font-weight: 500;
}

.cascade-active-hint::before {
  content: '';
}
</style>
