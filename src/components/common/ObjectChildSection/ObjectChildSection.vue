<template>
  <div class="object-child-section" :class="{ 'object-child-section--collapsed': !expanded }">
    <div class="ocs-header" @click="toggleExpanded">
      <div class="ocs-header-left">
        <el-icon v-if="displayMode === 'expandable'" class="ocs-expand-icon" :class="{ 'ocs-expand-icon--expanded': expanded }">
          <ArrowRight />
        </el-icon>
        <span class="ocs-title">{{ computedTitle }}</span>
        <span class="ocs-count">({{ pagination.total }})</span>
      </div>
      <div class="ocs-header-right" @click.stop>
        <slot name="header-actions" :parent-detail="parentDetail" />
        <el-button
          v-if="showCreate && useMetaListMode"
          type="primary"
          size="small"
          @click="handleCreate"
        >
          <el-icon><Plus /></el-icon>
          {{ createLabel }}
        </el-button>
      </div>
    </div>

    <div v-show="expanded" class="ocs-content">
      <div v-if="loading" class="ocs-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <div v-else-if="error" class="ocs-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ error }}</span>
        <el-button size="small" @click="handleRefresh">重试</el-button>
      </div>

      <div v-else-if="!hasData && !useMetaListMode" class="ocs-empty">
        <el-icon><Folder /></el-icon>
        <span>暂无数据</span>
        <el-button v-if="showCreate" size="small" type="primary" @click="handleCreate">
          新增
        </el-button>
      </div>

      <!-- ========== MetaListPage 模式（支持 inline-edit, batch 等高级功能） ========== -->
      <div v-if="useMetaListMode" class="ocs-metalist-wrapper">
        <MetaListPage
          ref="metaListRef"
          :object-type="childObjectType"
          :options="metaListOptions"
          :initial-filters="computedInitialFilters"
          :enable-detail="enableDetail"
          :enable-auto-crud="enableAutoCrud"
          :row-mutability="effectiveRowMutability"
          :initial-filters-view-only="true"
          @create="handleMetaListCreate"
          @edit="handleMetaListEdit"
          @delete="handleMetaListDelete"
          @action="handleMetaListAction"
          @data-loaded="handleDataLoaded"
        />
      </div>

      <!-- ========== 简单表格模式 ========== -->
      <div v-else-if="hasData" class="ocs-table-wrapper">
        <el-table
          :data="data"
          :stripe="stripe"
          :border="border"
          :size="tableSize"
          :show-header="showHeader"
          :row-key="rowKey"
          @row-click="handleRowClick"
          style="width: 100%"
        >
          <el-table-column
            v-for="col in visibleColumns"
            :key="col.key || col.field"
            :prop="col.key || col.field"
            :label="col.label || col.title"
            :width="col.width"
            :min-width="col.minWidth"
            :fixed="col.fixed"
            :align="col.align || 'left'"
            :sortable="col.sortable"
          >
            <template #default="{ row }">
              <slot :name="'cell-' + (col.key || col.field)" :row="row" :column="col">
                <component
                  :is="getCellComponent(col)"
                  :row="row"
                  :column="col"
                  :value="row[col.key || col.field]"
                />
              </slot>
            </template>
          </el-table-column>

          <el-table-column
            v-if="showActions"
            :label="'操作'"
            :width="actionsWidth"
            :fixed="actionsFixed"
            align="center"
          >
            <template #default="{ row }">
              <div class="ocs-row-actions">
                <slot name="row-actions" :row="row">
                  <el-button
                    v-for="action in getRowActions(row)"
                    :key="action.key"
                    :type="getActionType(action)"
                    :size="actionSize"
                    :disabled="!isActionVisible(action, row)"
                    @click.stop="handleAction(action, row)"
                  >
                    {{ action.label }}
                  </el-button>
                </slot>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="showPagination && pagination.total > 0" class="ocs-pagination">
          <el-pagination
            v-model:current-page="pagination.current"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[5, 10, 20, 50]"
            :total="pagination.total"
            layout="total, sizes, prev, pager, next"
            background
            small
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>

      <!-- 简单模式下的新增按钮 -->
      <div v-if="showCreate && !useMetaListMode && hasData" class="ocs-create-btn-row">
        <el-button type="primary" size="small" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          {{ createLabel }}
        </el-button>
      </div>
    </div>

    <DetailPage
      v-model="detailVisible"
      :object-type="childObjectType"
      :id="currentRecordId"
      :readonly="detailReadonly"
      :title="detailTitle"
      @close="handleDetailClose"
      @success="handleDetailSuccess"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, provide, inject } from 'vue'
import { Plus, ArrowRight, Loading, WarningFilled, Folder } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useParentChild } from '@/composables/useParentChild'
import { evaluateCondition } from '@/utils/safeExpression'
import DetailPage from '@/components/common/DetailPage/DetailPage.vue'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'

const props = defineProps({
  parentObjectType: { type: String, required: true },
  childObjectType: { type: String, required: true },
  parentId: { type: [String, Number], required: true },
  config: {
    type: Object,
    default: () => ({})
  },
  title: { type: String, default: '' },
  createLabel: { type: String, default: '新增' },
  showCreate: { type: Boolean, default: true },
  showActions: { type: Boolean, default: true },
  actionsWidth: { type: [String, Number], default: 150 },
  actionsFixed: { type: String, default: 'right' },
  actionSize: { type: String, default: 'small' },
  stripe: { type: Boolean, default: true },
  border: { type: Boolean, default: false },
  tableSize: { type: String, default: 'default' },
  showHeader: { type: Boolean, default: true },
  showPagination: { type: Boolean, default: true },
  rowKey: { type: String, default: 'id' },
  displayMode: {
    type: String,
    default: 'expandable',
    validator: (val) => ['always', 'expandable'].includes(val)
  },
  autoLoad: { type: Boolean, default: true },
  pageSize: { type: Number, default: 10 },
  useMetaList: {
    type: Boolean,
    default: false,
    description: '是否使用 MetaListPage 模式（支持 inline-edit, batch 等高级功能）'
  },
  enableDetail: {
    type: Boolean,
    default: true,
    description: '启用详情弹窗'
  },
  enableAutoCrud: {
    type: Boolean,
    default: true,
    description: '启用自动 CRUD'
  },
  rowMutability: {
    type: String,
    default: null,
    validator: (v) => [null, 'locked', 'extensible', 'fully_editable'].includes(v)
  },
  toolbarActions: {
    type: Array,
    default: () => [],
    description: '工具栏操作按钮配置'
  }
})

const emit = defineEmits([
  'create',
  'edit',
  'delete',
  'row-click',
  'action',
  'refresh',
  'success',
  'change',
  'data-loaded'
])

const metaListRef = ref(null)
const expanded = ref(props.displayMode === 'always')
const detailVisible = ref(false)
const currentRecordId = ref(null)
const detailReadonly = ref(false)
const detailTitle = ref('')

const {
  childList,
  childLoading,
  childError,
  childPagination,
  childMeta,
  parentDetail,
  parentIdField,
  createChild,
  updateChild,
  deleteChild,
  loadChildList,
  refreshChildList,
  discoverParentAssociation
} = useParentChild(props.parentObjectType, props.childObjectType, {
  parentId: props.parentId,
  autoLoadParent: false,
  autoLoadChild: !props.useMetaList
})

const loading = computed(() => props.useMetaList ? false : childLoading.value)
const error = computed(() => props.useMetaList ? null : childError.value)
const data = computed(() => childList.value)
const hasData = computed(() => props.useMetaList ? true : (data.value && data.value.length > 0))

const useMetaListMode = computed(() => props.useMetaList)

const pagination = computed({
  get: () => props.useMetaList ? { total: 0, current: 1, pageSize: props.pageSize } : childPagination.value,
  set: (val) => {
    if (!props.useMetaList) {
      childPagination.value.current = val.current
      childPagination.value.pageSize = val.pageSize
    }
  }
})

const computedTitle = computed(() => {
  if (props.title) return props.title
  if (childMeta.value?.label) return childMeta.value.label
  return props.childObjectType
})

const computedInitialFilters = computed(() => ({
  [parentIdField.value]: props.parentId
}))

const metaListOptions = computed(() => ({
  autoLoad: props.autoLoad,
  pageSize: props.pageSize,
  mode: 'element-plus',
  toolbarActions: props.toolbarActions
}))

const effectiveRowMutability = computed(() => {
  if (props.rowMutability) return props.rowMutability
  if (props.config?.rowMutability) return props.config.rowMutability
  return null
})

const visibleColumns = computed(() => {
  if (props.config.columns && props.config.columns.length > 0) {
    return props.config.columns
  }
  
  if (childMeta.value?.list?.columns) {
    return childMeta.value.list.columns.filter(col => 
      col.visible !== false && col.default_visible !== false
    ).slice(0, 5)
  }
  
  return [
    { key: 'name', label: '名称', minWidth: 120 },
    { key: 'code', label: '编码', minWidth: 100 },
    { key: 'status', label: '状态', width: 100 }
  ]
})

const defaultActions = computed(() => [
  { key: 'edit', label: '编辑', type: 'text' },
  { key: 'delete', label: '删除', type: 'text', danger: true }
])

function getRowActions(row) {
  if (props.config.actions && props.config.actions.length > 0) {
    return props.config.actions
  }
  if (slotHasContent('row-actions')) {
    return []
  }
  return defaultActions.value
}

function slotHasContent(name) {
  return false
}

function isActionVisible(action, row) {
  if (action.condition) {
    return evaluateCondition(action.condition, row, 'row')
  }
  
  if (action.key === 'delete' && row.is_system) {
    return false
  }
  
  return true
}

function getActionType(action) {
  if (action.danger || action.key === 'delete') {
    return 'danger'
  }
  if (action.type === 'primary') {
    return 'primary'
  }
  return 'text'
}

function getCellComponent(col) {
  if (col.widget === 'badge') {
    return 'span'
  }
  if (col.format === 'datetime') {
    return 'span'
  }
  return 'span'
}

function toggleExpanded() {
  if (props.displayMode === 'expandable') {
    expanded.value = !expanded.value
  }
}

function handleCreate() {
  currentRecordId.value = null
  detailReadonly.value = false
  detailTitle.value = `${props.createLabel} - ${parentDetail.value?.name || ''}`
  detailVisible.value = true
  emit('create')
}

function handleMetaListCreate() {
  emit('create')
}

function handleMetaListEdit(row) {
  emit('edit', row)
}

function handleMetaListDelete(row) {
  emit('delete', row)
}

function handleMetaListAction({ action, row }) {
  emit('action', { action, row })
}

function handleDataLoaded(data) {
  emit('data-loaded', data)
}

function handleRowClick(row) {
  emit('row-click', row)
}

async function handleAction(action, row) {
  if (action.key === 'edit' || action.key === 'update') {
    currentRecordId.value = row[props.rowKey] || row.id
    detailReadonly.value = false
    detailTitle.value = `编辑 - ${row.name || row.code || ''}`
    detailVisible.value = true
    emit('edit', row)
  } else if (action.key === 'delete') {
    try {
      await ElMessageBox.confirm(
        `确定要删除 "${row.name || row.code || '该记录'}" 吗？`,
        '确认删除',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      
      const result = await deleteChild(row[props.rowKey] || row.id)
      
      if (result.success) {
        ElMessage.success('删除成功')
        emit('delete', row)
        emit('success', { type: 'delete', row })
      } else {
        ElMessage.error(result.message || '删除失败')
      }
    } catch (e) {
      if (e !== 'cancel') {
        ElMessage.error(e.message || '删除失败')
      }
    }
  } else {
    emit('action', { action, row })
  }
}

function handlePageChange(page) {
  loadChildList()
  emit('change', { type: 'page', page })
}

function handlePageSizeChange(size) {
  loadChildList()
  emit('change', { type: 'pageSize', pageSize: size })
}

function handleRefresh() {
  if (useMetaListMode.value) {
    metaListRef.value?.refresh?.()
  } else {
    loadChildList()
  }
  emit('refresh')
}

function handleDetailClose() {
  detailVisible.value = false
  currentRecordId.value = null
}

async function handleDetailSuccess({ type, data: resultData }) {
  detailVisible.value = false
  currentRecordId.value = null
  if (!useMetaListMode.value) {
    await loadChildList()
  }
  emit('success', { type, data: resultData })
}

function expand() {
  if (props.displayMode === 'expandable') {
    expanded.value = true
  }
}

function collapse() {
  if (props.displayMode === 'expandable') {
    expanded.value = false
  }
}

async function refresh() {
  await handleRefresh()
}

function reload() {
  return handleRefresh()
}

defineExpose({
  expand,
  collapse,
  refresh,
  reload,
  loadChildList,
  metaListRef
})

watch(() => props.parentId, (newId) => {
  if (newId && !useMetaListMode.value) {
    loadChildList()
  }
}, { immediate: true })

onMounted(async () => {
  await discoverParentAssociation()
})
</script>

<style scoped>
.object-child-section {
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  background: var(--el-bg-color);
  margin-bottom: 16px;
  margin-left: 0;
  margin-right: 0;
}

.object-child-section--collapsed .ocs-header {
  border-bottom: none;
}

.ocs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid var(--el-border-color-light);
}

.ocs-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ocs-expand-icon {
  transition: transform 0.2s;
  color: var(--el-text-color-secondary);
}

.ocs-expand-icon--expanded {
  transform: rotate(90deg);
}

.ocs-title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.ocs-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.ocs-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ocs-content {
  padding: 0;
}

.ocs-loading,
.ocs-error,
.ocs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  gap: 8px;
  color: var(--el-text-color-secondary);
}

.ocs-error {
  color: var(--el-color-danger);
}

.ocs-table-wrapper {
  overflow-x: auto;
}

.ocs-metalist-wrapper {
  padding: 0;
}

.ocs-row-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.ocs-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-light);
}

.ocs-create-btn-row {
  display: flex;
  justify-content: flex-start;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
