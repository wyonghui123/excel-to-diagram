<template>
  <el-dialog
    :model-value="visible"
    title="导出数据"
    :width="width || '560px'"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="export-dialog-content">
      <!-- 多类型导出模式：选择导出对象 -->
      <div v-if="multiTypeMode && availableMultiTypes.length > 0" class="multi-type-section">
        <div class="multi-type-section__label">选择导出对象</div>
        <div class="multi-type-section__items">
          <label
            v-for="item in availableMultiTypes"
            :key="item.value"
            class="multi-type-checkbox"
          >
            <input type="checkbox" v-model="selectedMultiTypes" :value="item.value" />
            <span>{{ item.label }}</span>
          </label>
        </div>
      </div>

      <!-- 单类型导出信息 -->
      <div v-else class="export-info">
        <p>导出 <strong>{{ objectTypeName }}</strong> 数据</p>
        <p class="tip">支持导出所有符合当前筛选条件的数据</p>
      </div>

      <!-- 导出模式选择（从元数据驱动，仅单对象模式） -->
      <div v-if="!multiTypeMode && showExportMode && hierarchyConfig?.enabled" class="export-mode">
        <div class="export-mode__label">导出模式</div>
        <el-radio-group v-model="localExportMode" class="export-mode__options">
          <el-radio value="single">单对象导出</el-radio>
          <el-radio value="cascade">级联导出（含所有子对象）</el-radio>
        </el-radio-group>
      </div>

      <!-- 级联对象选择（从元数据驱动） -->
      <div v-if="!multiTypeMode && localExportMode === 'cascade' && cascadeChain.length > 0" class="cascade-selection">
        <div class="cascade-selection__label">选择导出层级</div>
        <div class="cascade-selection__items">
          <el-checkbox
            v-for="item in cascadeChain"
            :key="item.field"
            v-model="item.selected"
            class="cascade-checkbox"
          >
            {{ item.label }}
            <template v-if="item.parentLabel">
              <span class="cascade-from">← 级联自 {{ item.parentLabel }}</span>
            </template>
          </el-checkbox>
        </div>
      </div>

      <el-form label-width="120px">
        <el-form-item v-if="!multiTypeMode" label="导出范围">
          <el-radio-group v-model="exportScope">
            <el-radio value="current">当前页 ({{ currentCount }} 条)</el-radio>
            <el-radio value="all">全部数据 ({{ totalCount }} 条)</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="multiTypeMode" label="导出范围">
          <span class="export-scope-hint">将导出已选择的 <strong>{{ selectedMultiTypes.length }}</strong> 个对象类型的所有数据</span>
        </el-form-item>

        <el-form-item label="包含筛选条件" v-if="includeFilters && hasFilters">
          <el-switch v-model="withFilters" />
          <span class="hint">勾选后，导出的数据将应用当前列表筛选条件</span>
        </el-form-item>

        <!-- 导出选项（从元数据驱动） -->
        <el-form-item v-if="showExportOptions" label="导出选项" class="export-options">
          <div class="export-options__items">
            <el-checkbox v-model="localOptions.includeHierarchyPath">
              包含层级路径列
            </el-checkbox>
            <el-checkbox v-model="localOptions.includeHierarchyIds">
              包含层级编码/名称
            </el-checkbox>
            <el-checkbox v-model="localOptions.protectSheet">
              保护工作表
            </el-checkbox>
            <el-checkbox v-model="localOptions.markReadonly">
              标记只读字段
            </el-checkbox>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <div v-if="exporting" class="export-progress">
      <el-progress
        :percentage="exportProgress"
        :stroke-width="10"
        :color="'#ea580c'"
      />
      <p class="export-progress__type" v-if="currentTypeName">
        正在导出 <strong>{{ currentTypeName }}</strong> ({{ currentIndex }}/{{ totalTypes }})
      </p>
      <p class="export-progress__percent">
        {{ progressMessage || `已完成 ${exportProgress}%` }}
      </p>
    </div>

    <template #footer>
      <el-button @click="handleClose" :disabled="exporting">取消</el-button>
      <el-button type="primary" :loading="loading || exporting" @click="handleExport">
        {{ exporting ? '导出中...' : (loading ? '导出中...' : '确认导出') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { metaService } from '@/services/metaService'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  objectType: {
    type: String,
    required: true
  },
  objectTypeName: {
    type: String,
    default: ''
  },
  filters: {
    type: Object,
    default: () => ({})
  },
  sortInfo: {
    type: Object,
    default: () => ({})
  },
  defaultSort: {
    type: Object,
    default: () => ({})
  },
  currentCount: {
    type: Number,
    default: 0
  },
  totalCount: {
    type: Number,
    default: 0
  },
  exportOptions: {
    type: Object,
    default: () => ({})
  },
  objectTypes: {
    type: Array,
    default: () => []
  },
  objectTypeLabels: {
    type: Object,
    default: () => ({})
  },
  showExportMode: {
    type: Boolean,
    default: false
  },
  showExportOptions: {
    type: Boolean,
    default: false
  },
  defaultExportMode: {
    type: String,
    default: 'single'
  },
  width: {
    type: String,
    default: '560px'
  },
  multiTypeMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'success', 'close'])

const loading = ref(false)
const exportScope = ref('current')
const withFilters = ref(true)
const localExportMode = ref(props.defaultExportMode || 'single')

const exporting = ref(false)
const exportProgress = ref(0)
const currentTypeName = ref('')
const currentIndex = ref(0)
const totalTypes = ref(0)
const progressMessage = ref('')

const availableMultiTypes = computed(() => {
  return props.objectTypes
    .filter(t => t && typeof t === 'string')
    .map(t => ({
      value: t,
      label: props.objectTypeLabels[t] || t
    }))
})

const selectedMultiTypes = ref([])

const localOptions = ref({
  includeHierarchyPath: props.exportOptions?.includeHierarchyPath ?? false,
  includeHierarchyIds: props.exportOptions?.includeHierarchyIds ?? false,
  protectSheet: props.exportOptions?.protectSheet ?? false,
  markReadonly: props.exportOptions?.markReadonly ?? false
})

const schema = ref(null)
const loadingSchema = ref(false)

const hierarchyConfig = computed(() => {
  if (!schema.value) return null
  return metaService.getHierarchyConfig(schema.value)
})

const cascadeChain = computed(() => {
  if (!schema.value) return []

  const chain = metaService.buildCascadeChain(schema.value)

  return chain.map(item => ({
    ...item,
    selected: true
  }))
})

const selectedCascadeFields = computed(() => {
  return cascadeChain.value
    .filter(item => item.selected)
    .map(item => item.field)
})

const objectTypeName = computed(() => {
  if (props.objectTypeName) return props.objectTypeName

  if (!schema.value) return props.objectType

  const fields = schema.value.fields || []
  const field = fields.find(f => f.id === props.objectType)
  return field?.name || schema.value.name || props.objectType
})

const includeFilters = computed(() => {
  return props.exportOptions?.includeFilters !== false
})

const hasFilters = computed(() => {
  return props.filters && Object.keys(props.filters).length > 0
})

watch(() => props.visible, (newVal) => {
  if (newVal) {
    resetState()
    loadSchema()
  }
})

onMounted(() => {
  if (props.visible) {
    loadSchema()
  }
})

async function loadSchema() {
  if (schema.value || loadingSchema.value) return

  loadingSchema.value = true
  try {
    const { metaService } = await import('@/services/metaService')
    const result = await metaService.getSchema(props.objectType)
    if (result.success && result.data) {
      schema.value = result.data
      const importConfig = metaService.getImportExportConfig(result.data)
      if (importConfig?.cascadeExport) {
        localExportMode.value = 'cascade'
      }
    }
  } catch (e) {
    console.error('[ExportDialog] 加载 schema 失败:', e)
  } finally {
    loadingSchema.value = false
  }
}

function resetState() {
  exportScope.value = 'current'
  withFilters.value = true
  localExportMode.value = props.defaultExportMode || 'single'
  selectedMultiTypes.value = props.objectTypes.filter(t => t && typeof t === 'string')
  localOptions.value = {
    includeHierarchyPath: props.exportOptions?.includeHierarchyPath ?? false,
    includeHierarchyIds: props.exportOptions?.includeHierarchyIds ?? false,
    protectSheet: props.exportOptions?.protectSheet ?? false,
    markReadonly: props.exportOptions?.markReadonly ?? false
  }
}

async function handleExport() {
  const selectedCount = props.multiTypeMode 
    ? selectedMultiTypes.value.length 
    : (localExportMode.value === 'cascade' ? selectedCascadeFields.value.length : 1)
  const useAsync = selectedCount > 1
  
  if (useAsync) {
    await handleExportAsync()
  } else {
    await handleExportSync()
  }
}

async function handleExportSync() {
  loading.value = true

  try {
    const params = {
      scope: localExportMode.value === 'cascade' ? 'cascade' : 'single',
      filters: {}
    }

    let effectiveObjectType = props.objectType

    if (props.multiTypeMode && selectedMultiTypes.value.length > 0) {
      params.scope = 'selected'
      params.selected_types = [...selectedMultiTypes.value]
      effectiveObjectType = selectedMultiTypes.value[0]
    } else if (localExportMode.value === 'cascade') {
      params.selected_types = selectedCascadeFields.value
    }

    if (withFilters.value && hasFilters.value) {
      params.filters = JSON.parse(JSON.stringify(props.filters))
    }

    if (props.sortInfo?.prop) {
      const order = props.sortInfo.order === 'ascending' ? '' : '-'
      params.ordering = `${order}${props.sortInfo.prop}`
    } else if (props.defaultSort?.prop) {
      const order = props.defaultSort.order === 'ascending' ? '' : '-'
      params.ordering = `${order}${props.defaultSort.prop}`
    }

    if (exportScope.value === 'current') {
      params.page = 1
      params.page_size = props.currentCount
    }

    params.options = {
      include_hierarchy_path: localOptions.value.includeHierarchyPath,
      include_hierarchy_ids: localOptions.value.includeHierarchyIds,
      protect_sheet: localOptions.value.protectSheet,
      mark_readonly: localOptions.value.markReadonly,
      include_operation_mode: true
    }

    const { boService } = await import('@/services/boService')
    const result = await boService.exportData(effectiveObjectType, params)

    if (result.success) {
      const count = result.total_rows || 0
      ElMessage.success(`导出成功，共 ${count} 条数据`)
      emit('success', { count })
      handleClose()
    } else {
      ElMessage.error(result.message || '导出失败')
    }
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function handleExportAsync() {
  exporting.value = true
  exportProgress.value = 0
  currentTypeName.value = ''
  currentIndex.value = 0
  progressMessage.value = '准备导出...'

  try {
    const params = {
      scope: localExportMode.value === 'cascade' ? 'cascade' : 'single',
      filters: {}
    }

    let effectiveObjectType = props.objectType

    if (props.multiTypeMode && selectedMultiTypes.value.length > 0) {
      params.scope = 'selected'
      params.selected_types = [...selectedMultiTypes.value]
      effectiveObjectType = selectedMultiTypes.value[0]
    } else if (localExportMode.value === 'cascade') {
      params.selected_types = selectedCascadeFields.value
    }

    if (withFilters.value && hasFilters.value) {
      params.filters = JSON.parse(JSON.stringify(props.filters))
    }

    if (props.sortInfo?.prop) {
      const order = props.sortInfo.order === 'ascending' ? '' : '-'
      params.ordering = `${order}${props.sortInfo.prop}`
    } else if (props.defaultSort?.prop) {
      const order = props.defaultSort.order === 'ascending' ? '' : '-'
      params.ordering = `${order}${props.defaultSort.prop}`
    }

    if (exportScope.value === 'current') {
      params.page = 1
      params.page_size = props.currentCount
    }

    params.options = {
      include_hierarchy_path: localOptions.value.includeHierarchyPath,
      include_hierarchy_ids: localOptions.value.includeHierarchyIds,
      protect_sheet: localOptions.value.protectSheet,
      mark_readonly: localOptions.value.markReadonly,
      include_operation_mode: true
    }

    const { boService } = await import('@/services/boService')
    const startResult = await boService.exportDataAsync(effectiveObjectType, params)

    if (!startResult.success) {
      ElMessage.error(startResult.message || '启动导出任务失败')
      exporting.value = false
      return
    }

    const taskId = startResult.data.task_id
    await pollExportProgress(taskId, boService)
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || '未知错误'))
    exporting.value = false
  }
}

async function pollExportProgress(taskId, boService) {
  const poll = async () => {
    try {
      const statusRes = await boService.getExportStatus(taskId)

      if (statusRes.success && statusRes.data) {
        const data = statusRes.data
        exportProgress.value = data.progress || 0
        currentTypeName.value = data.current_type_name || ''
        currentIndex.value = data.current_index || 0
        totalTypes.value = data.total_types || 0
        progressMessage.value = data.message || ''

        if (data.status === 'completed') {
          exporting.value = false
          exportProgress.value = 100
          
          if (data.result?.download_url) {
            const filename = `export_${new Date().toISOString().slice(0, 10)}.xlsx`
            await boService.downloadExportFile(data.result.download_url, filename)
            
            const count = data.result.total_rows || 0
            ElMessage.success(`导出成功，共 ${count} 条数据`)
            emit('success', { count, result: data.result })
            handleClose()
          }
        } else if (data.status === 'failed') {
          exporting.value = false
          ElMessage.error(data.error || '导出失败')
        } else {
          setTimeout(poll, 1000)
        }
      } else {
        setTimeout(poll, 1000)
      }
    } catch (e) {
      console.error('[ExportDialog] 轮询状态失败:', e)
      setTimeout(poll, 1000)
    }
  }
  poll()
}

function handleClose() {
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped lang="scss">
@import '@/styles/mixins.scss';

.export-dialog-content {
  padding: var(--spacing-md) 0;
}

.export-info {
  margin-bottom: var(--spacing-lg);

  p {
    margin: 0 0 var(--spacing-xs);
  }

  strong {
    color: var(--yonyou-orange-600, #ea580c);
  }
}

.tip {
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-base, 14px);
}

.multi-type-section {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__label {
    margin-bottom: var(--spacing-sm);
    font-size: var(--el-font-size-small, 12px);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);
  }
}

.multi-type-checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-bg-color, #fff);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  font-size: var(--el-font-size-base, 14px);

  input[type="checkbox"] {
    margin: 0;
  }
}

.hint {
  margin-left: var(--spacing-sm);
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-base, 14px);
}

.export-mode {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__label {
    margin-bottom: var(--spacing-sm);
    font-size: var(--el-font-size-small, 12px);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__options {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }
}

.cascade-selection {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__label {
    margin-bottom: var(--spacing-sm);
    font-size: var(--el-font-size-small, 12px);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);
  }
}

.cascade-checkbox {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-bg-color, #fff);
  border-radius: var(--radius-sm, 4px);
}

.cascade-from {
  margin-left: var(--spacing-xs);
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #909399);
}

.export-options {
  :deep(.el-form-item__label) {
    float: none;
    line-height: 24px;
  }

  :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }

  &__items {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--spacing-sm);
  }
}

.export-progress {
  margin: var(--spacing-lg) 0;
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__type {
    margin: var(--spacing-sm) 0 0;
    font-size: var(--el-font-size-base, 14px);
    color: var(--el-text-color-regular, #606266);

    strong {
      color: var(--yonyou-orange-600, #ea580c);
    }
  }

  &__percent {
    margin: var(--spacing-xs) 0 0;
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
  }
}
</style>
