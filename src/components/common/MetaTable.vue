<template>
  <div class="meta-table">
    <!-- 批量操作工具栏 -->
    <div v-if="selectedRows.length > 0 && batchActions.length > 0" class="mt-batch-toolbar">
      <span class="mt-batch-count">已选择 {{ selectedRows.length }} 项</span>
      <div class="mt-batch-actions">
        <button
          v-for="action in batchActions"
          :key="action.key"
          class="mt-batch-btn"
          :class="`mt-batch-btn--${action.variant || 'default'}`"
          @click="handleBatchAction(action)"
        >
          {{ action.label }}
        </button>
      </div>
    </div>

    <div v-if="showHeader && ($slots.toolbar || searchPlaceholder)" class="mt-header">
      <div class="mt-query">
        <div v-if="searchPlaceholder" class="mt-search">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="7" cy="7" r="4.5"/>
            <path d="M11 11L14 14"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            class="mt-search-input"
            :placeholder="searchPlaceholder"
          />
        </div>
        <div v-if="$slots.toolbar" class="mt-toolbar-slot">
          <slot name="toolbar"></slot>
        </div>
      </div>
      <div v-if="actions && actions.length" class="mt-actions">
        <button
          v-for="action in headerActions"
          :key="action.key"
          class="mt-action-btn"
          :class="`mt-action-btn--${action.variant || 'primary'}`"
          @click="$emit('action', { key: action.key, type: 'header' })"
        >
          <span v-if="action.icon" v-html="action.icon"></span>
          {{ action.label }}
        </button>
      </div>
    </div>

    <div class="mt-body">
      <div v-if="loading" class="mt-loading">
        <div class="mt-spinner"></div>
        <span>加载中...</span>
      </div>
      <div v-else-if="displayData.length === 0" class="mt-empty">
        <EmptyState
          :type="searchQuery ? 'search' : emptyType"
          :title="searchQuery ? '无匹配数据' : emptyTitle"
          :description="searchQuery ? '尝试更换搜索关键词' : emptyDescription"
        />
      </div>
      <div v-else class="mt-table-wrap">
        <table
          class="mt-table"
          role="grid"
          :aria-label="ariaLabel"
          :aria-rowcount="ariaRowCount"
          :aria-colcount="ariaColCount"
        >
          <thead>
            <tr>
              <th v-if="selectable" class="mt-th mt-th--checkbox">
                <label class="mt-checkbox">
                  <input
                    type="checkbox"
                    :checked="isAllSelected"
                    :indeterminate.prop="isIndeterminate"
                    @change="handleSelectAll"
                  />
                  <span class="mt-checkbox-box"></span>
                </label>
              </th>
              <th
                v-for="col in visibleColumns"
                :key="col.key"
                class="mt-th"
                :class="[`mt-col--${col.key}`, { 'mt-th--sortable': col.sortable }]"
                :style="{ minWidth: col.width, width: col.width }"
                :aria-sort="getAriaSort(col)"
                @click="col.sortable ? handleSort(col.key) : null"
              >
                <span class="mt-th-label">{{ col.label }}</span>
                <span v-if="col.sortable" class="mt-sort-icon">
                  <svg viewBox="0 0 12 12" width="10" height="10" :class="{ 'mt-sort-active': sortKey === col.key }">
                    <path d="M6 2L9 5H3z" fill="currentColor" :opacity="sortKey === col.key && sortOrder === 'asc' ? 1 : 0.3"/>
                    <path d="M6 10L3 7H9z" fill="currentColor" :opacity="sortKey === col.key && sortOrder === 'desc' ? 1 : 0.3"/>
                  </svg>
                </span>
              </th>
              <th v-if="hasActions" class="mt-th mt-th--actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in displayData"
              :key="getRowKey(row) || index"
              class="mt-row"
              :class="{
                'mt-row--stripe': stripe,
                'mt-row--selected': selectable && isSelected(row)
              }"
              :aria-selected="selectable ? isSelected(row) : undefined"
              @click="$emit('row-click', row)"
            >
              <td v-if="selectable" class="mt-td mt-td--checkbox">
                <label class="mt-checkbox">
                  <input
                    type="checkbox"
                    :checked="isSelected(row)"
                    @change="handleSelectRow(row)"
                  />
                  <span class="mt-checkbox-box"></span>
                </label>
              </td>
              <td
                v-for="col in visibleColumns"
                :key="col.key"
                class="mt-td"
                :class="`mt-col--${col.key}`"
              >
                <template v-if="col.slot">
                  <slot :name="`cell-${col.key}`" :row="row" :value="resolveValue(row, col.key)" />
                </template>
                <template v-else-if="col.type === 'status'">
                  <span class="mt-status" :class="`mt-status--${resolveStatusStyle(row, col.key)}`">
                    {{ resolveStatusLabel(row, col.key, col) }}
                  </span>
                </template>
                <template v-else-if="col.type === 'tag'">
                  <span class="mt-tag" :class="`mt-tag--${resolveTagStyle(row, col.key, col)}`">
                    {{ resolveTagLabel(row, col.key, col) }}
                  </span>
                </template>
                <template v-else-if="col.type === 'time'">
                  <span class="mt-time">{{ formatTime(resolveValue(row, col.key)) }}</span>
                </template>
                <template v-else-if="col.type === 'ellipsis'">
                  <span class="mt-ellipsis" :title="resolveValue(row, col.key)" v-html="highlightText(resolveValue(row, col.key) || '-', searchQuery)"></span>
                </template>
                <template v-else-if="col.type === 'value_help'">
                  <span v-html="highlightText(resolveValueHelpDisplay(row, col), searchQuery)"></span>
                </template>
                <template v-else>
                  <span v-html="highlightText(resolveValue(row, col.key) ?? '-', searchQuery)"></span>
                </template>
              </td>
              <td v-if="hasActions" class="mt-td mt-td--actions">
                <div class="mt-cell-actions">
                  <button
                    v-for="action in rowActions"
                    :key="action.key"
                    class="mt-link-btn"
                    :class="`mt-link-btn--${action.variant || 'default'}`"
                    @click="$emit('action', { key: action.key, type: 'row', row })"
                  >{{ action.label }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="showPagination && displayData.length > 0" class="mt-pagination">
        <span class="mt-pagination-total">共 {{ totalItems }} 条</span>
        
        <template v-if="pagination">
          <div class="mt-pagination-pages">
            <button
              class="mt-pagination-btn"
              :disabled="currentPage === 1"
              @click="handlePageChange(1)"
              title="首页"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path d="M11.5 2L6 7.5L11.5 13L12.5 12L8 7.5L12.5 3L11.5 2Z"/>
                <path d="M7.5 2L2 7.5L7.5 13L8.5 12L4 7.5L8.5 3L7.5 2Z"/>
              </svg>
            </button>
            <button
              class="mt-pagination-btn"
              :disabled="currentPage === 1"
              @click="handlePageChange(currentPage - 1)"
              title="上一页"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path d="M10.5 2L5 7.5L10.5 13L11.5 12L7 7.5L11.5 3L10.5 2Z"/>
              </svg>
            </button>
            
            <template v-for="(page, index) in pageList" :key="page.current || page.pageNum || page || index">
              <span v-if="page === '...'" class="mt-pagination-ellipsis">...</span>
              <button
                v-else
                class="mt-pagination-btn"
                :class="{ 'mt-pagination-btn--active': page === currentPage }"
                @click="handlePageChange(page)"
              >{{ page }}</button>
            </template>
            
            <button
              class="mt-pagination-btn"
              :disabled="currentPage === totalPages"
              @click="handlePageChange(currentPage + 1)"
              title="下一页"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path d="M5.5 2L11 7.5L5.5 13L4.5 12L9 7.5L4.5 3L5.5 2Z"/>
              </svg>
            </button>
            <button
              class="mt-pagination-btn"
              :disabled="currentPage === totalPages"
              @click="handlePageChange(totalPages)"
              title="末页"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path d="M4.5 2L10 7.5L4.5 13L3.5 12L8 7.5L3.5 3L4.5 2Z"/>
                <path d="M8.5 2L14 7.5L8.5 13L7.5 12L12 7.5L7.5 3L8.5 2Z"/>
              </svg>
            </button>
          </div>
          
          <div v-if="showSizeChanger" class="mt-pagination-size">
            <select
              class="mt-pagination-select"
              :value="pageSize"
              @change="handlePageSizeChange"
            >
              <option v-for="size in pageSizeOptions" :key="size" :value="size">
                {{ size }} 条/页
              </option>
            </select>
          </div>
          
          <div v-if="showQuickJumper" class="mt-pagination-jumper">
            <span>跳至</span>
            <input
              v-model.number="jumpPage"
              type="number"
              class="mt-pagination-jumper-input"
              :min="1"
              :max="totalPages"
              @keyup.enter="handleJumpPage"
            />
            <span>页</span>
          </div>
        </template>
      </div>
    </div>

    <!-- 导入对话框 -->
    <ImportDialog
      v-model:visible="showImportDialog"
      :object-type="objectType"
      :context="context"
      @success="handleImportSuccess"
      @close="showImportDialog = false"
    />

    <!-- 导出对话框 -->
    <ExportDialog
      v-model:visible="showExportDialog"
      :object-type="objectType"
      :fields="exportFields"
      :filters="exportFilters"
      :sort-info="sortInfo"
      :default-sort="defaultSort"
      :context="context"
      @success="handleExportSuccess"
      @close="showExportDialog = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, reactive } from 'vue'
import EmptyState from './EmptyState.vue'
import ImportDialog from './ImportDialog'
import ExportDialog from './ExportDialog'
import { boService } from '@/services/boService.js'

const props = defineProps({
  columns: {
    type: Array,
    required: true,
    validator: (val) => val.every(col => col.key)
  },
  data: {
    type: Array,
    default: () => []
  },
  actions: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  idKey: {
    type: String,
    default: 'id'
  },
  searchPlaceholder: {
    type: String,
    default: '搜索...'
  },
  searchFields: {
    type: Array,
    default: null
  },
  showHeader: {
    type: Boolean,
    default: true
  },
  showPagination: {
    type: Boolean,
    default: true
  },
  stripe: {
    type: Boolean,
    default: true
  },
  emptyType: {
    type: String,
    default: 'folder'
  },
  emptyTitle: {
    type: String,
    default: '暂无数据'
  },
  emptyDescription: {
    type: String,
    default: '点击上方按钮新增数据'
  },
  selectable: {
    type: Boolean,
    default: false
  },
  selectedKeys: {
    type: Array,
    default: () => []
  },
  rowKey: {
    type: String,
    default: 'id'
  },
  pagination: {
    type: Object,
    default: null
  },
  ariaLabel: {
    type: String,
    default: ''
  },
  batchActions: {
    type: Array,
    default: () => []
  },
  objectType: {
    type: String,
    default: ''
  },
  context: {
    type: Object,
    default: () => ({})
  },
  exportFields: {
    type: Array,
    default: () => []
  },
  currentFilters: {
    type: Object,
    default: () => ({})
  },
  exportFilters: {
    type: Object,
    default: () => ({})
  },
  sortInfo: {
    type: Object,
    default: () => ({ prop: null, order: null })
  },
  defaultSort: {
    type: Object,
    default: () => ({ field: 'updated_at', order: 'desc' })
  }
})

const emit = defineEmits(['action', 'selection-change', 'page-change', 'page-size-change', 'row-click', 'search', 'batch-action', 'refresh'])

const selectedRows = ref([])

const searchQuery = ref('')
const sortKey = ref('')
const sortOrder = ref('')
const showImportDialog = ref(false)
const showExportDialog = ref(false)

// 高亮匹配文本
function highlightText(text, keyword) {
  if (!keyword || !text) return text
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="mt-highlight">$1</mark>')
}

// 监听搜索输入，触发搜索事件
watch(searchQuery, (newVal) => {
  emit('search', newVal)
})

const visibleColumns = computed(() => props.columns.filter(col => col.visible !== false && col.default_visible !== false))

const hasActions = computed(() => props.actions && props.actions.length > 0)

const ariaLabel = computed(() => props.ariaLabel || '数据表格')

const ariaRowCount = computed(() => totalItems.value + 1)

const ariaColCount = computed(() => {
  let count = visibleColumns.value.length
  if (props.selectable) count += 1
  if (hasActions.value) count += 1
  return count
})

function getAriaSort(col) {
  if (!col.sortable) return undefined
  if (sortKey.value !== col.key) return undefined
  return sortOrder.value === 'asc' ? 'ascending' : 'descending'
}

const headerActions = computed(() => props.actions.filter(a => a.position === 'header' || !a.position))
const rowActions = computed(() => props.actions.filter(a => a.position === 'row'))

const filteredData = computed(() => {
  if (!searchQuery.value) return props.data
  const query = searchQuery.value.toLowerCase()
  const fields = props.searchFields || props.columns.filter(c => c.searchable !== false).map(c => c.key)
  return props.data.filter(row =>
    fields.some(key => {
      const val = resolveValue(row, key)
      return val != null && String(val).toLowerCase().includes(query)
    })
  )
})

const sortedData = computed(() => {
  if (!sortKey.value) return filteredData.value
  return [...filteredData.value].sort((a, b) => {
    const av = resolveValue(a, sortKey.value)
    const bv = resolveValue(b, sortKey.value)
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = String(av).localeCompare(String(bv), 'zh-CN')
    return sortOrder.value === 'desc' ? -cmp : cmp
  })
})

const displayData = computed(() => sortedData.value)

function getRowKey(row) {
  return row[props.rowKey] ?? row[props.idKey]
}

function isSelected(row) {
  const key = getRowKey(row)
  return props.selectedKeys.includes(key)
}

const isAllSelected = computed(() => {
  if (displayData.value.length === 0) return false
  return displayData.value.every(row => isSelected(row))
})

const isIndeterminate = computed(() => {
  if (displayData.value.length === 0) return false
  const selectedCount = displayData.value.filter(row => isSelected(row)).length
  return selectedCount > 0 && selectedCount < displayData.value.length
})

function handleSelectRow(row) {
  const key = getRowKey(row)
  const newKeys = isSelected(row)
    ? props.selectedKeys.filter(k => k !== key)
    : [...props.selectedKeys, key]
  emitSelectionChange(newKeys)
}

function handleSelectAll() {
  if (isAllSelected.value) {
    const currentKeys = displayData.value.map(row => getRowKey(row))
    const newKeys = props.selectedKeys.filter(k => !currentKeys.includes(k))
    emitSelectionChange(newKeys)
  } else {
    const currentKeys = displayData.value.map(row => getRowKey(row))
    const newKeys = [...new Set([...props.selectedKeys, ...currentKeys])]
    emitSelectionChange(newKeys)
  }
}

function emitSelectionChange(keys) {
  const rows = props.data.filter(row => keys.includes(getRowKey(row)))
  selectedRows.value = rows
  emit('selection-change', rows)
}

function resolveValue(row, key) {
  return key.includes('.') ? key.split('.').reduce((o, k) => o?.[k], row) : row[key]
}

const vhDisplayCache = reactive({})

function resolveValueHelpDisplay(row, col) {
  const rawValue = resolveValue(row, col.key)
  if (!rawValue && rawValue !== 0) return '-'
  const cacheKey = `${col.key}:${rawValue}`
  if (vhDisplayCache[cacheKey]) return vhDisplayCache[cacheKey]
  const displayField = col.displayField || `${col.key}_display`
  const displayFromRow = row[displayField]
  if (displayFromRow) {
    vhDisplayCache[cacheKey] = displayFromRow
    return displayFromRow
  }
  const nameField = `${col.key.replace(/_id$/, '')}_name`
  if (row[nameField]) {
    vhDisplayCache[cacheKey] = row[nameField]
    return row[nameField]
  }
  resolveVhDisplayAsync(col, rawValue)
  return String(rawValue)
}

async function resolveVhDisplayAsync(col, value) {
  const cacheKey = `${col.key}:${value}`
  if (vhDisplayCache[cacheKey]) return

  const vhConfig = col.valueHelpConfig
  if (!vhConfig?.source) return

  let sourceType = vhConfig.source.type
  let sourceId = ''
  if (sourceType === 'enum') {
    sourceId = vhConfig.source.enum_type_id || ''
  } else if (sourceType === 'bo') {
    sourceId = vhConfig.source.target_bo || ''
  } else if (sourceType === 'custom') {
    sourceId = vhConfig.source.endpoint || ''
  }
  if (!sourceId) return

  try {
    const response = await boService.resolveValueHelp(sourceType, sourceId, value)
    if (response.success && response.data?.display) {
      vhDisplayCache[cacheKey] = response.data.display
    }
  } catch (e) {
    // ignore
  }
}

function handleSort(key) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
}

function resolveStatusStyle(row, key) {
  const val = resolveValue(row, key)
  const col = props.columns.find(c => c.key === key)
  if (col?.statusMap) {
    const mapped = col.statusMap[val]
    return typeof mapped === 'string' ? mapped : (mapped?.style || 'default')
  }
  return val === 'active' || val === true || val === 1 ? 'active' : 'inactive'
}

function resolveStatusLabel(row, key, col) {
  const val = resolveValue(row, key)
  if (col?.statusMap) {
    const mapped = col.statusMap[val]
    return typeof mapped === 'string' ? val : (mapped?.label || val)
  }
  return val === 'active' || val === true || val === 1 ? '启用' : '停用'
}

function resolveTagStyle(row, key, col) {
  const val = resolveValue(row, key)
  if (col?.tagMap) {
    const mapped = col?.tagMap[val]
    return typeof mapped === 'string' ? mapped : (mapped?.style || 'default')
  }
  return 'default'
}

function handleBatchAction(action) {
  if (action.key === 'export') {
    showExportDialog.value = true
  } else if (action.key === 'import') {
    showImportDialog.value = true
  } else {
    emit('batch-action', { action, rows: selectedRows.value })
  }
}

function handleImportSuccess() {
  emit('refresh')
}

function handleExportSuccess() {
  // 导出成功
}

function resolveTagLabel(row, key, col) {
  const val = resolveValue(row, key)
  if (col?.tagMap) {
    const mapped = col?.tagMap[val]
    return typeof mapped === 'string' ? val : (mapped?.label ?? String(val))
  }
  return val ?? ''
}

function formatTime(timestamp) {
  if (!timestamp) return '-'
  const d = new Date(timestamp)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

const pageSizeOptions = computed(() => {
  return props.pagination?.pageSizeOptions || [10, 20, 50, 100]
})

const showSizeChanger = computed(() => {
  return props.pagination?.showSizeChanger !== false
})

const showQuickJumper = computed(() => {
  return props.pagination?.showQuickJumper === true
})

const currentPage = computed(() => {
  return props.pagination?.current || 1
})

const pageSize = computed(() => {
  return props.pagination?.pageSize || 10
})

const totalItems = computed(() => {
  return props.pagination?.total ?? filteredData.value.length
})

const totalPages = computed(() => {
  return Math.ceil(totalItems.value / pageSize.value) || 1
})

const pageList = computed(() => {
  const pages = []
  const current = currentPage.value
  const total = totalPages.value
  
  if (total <= 7) {
    for (let i = 1; i <= total; i++) {
      pages.push(i)
    }
  } else {
    if (current <= 4) {
      for (let i = 1; i <= 5; i++) {
        pages.push(i)
      }
      pages.push('...')
      pages.push(total)
    } else if (current >= total - 3) {
      pages.push(1)
      pages.push('...')
      for (let i = total - 4; i <= total; i++) {
        pages.push(i)
      }
    } else {
      pages.push(1)
      pages.push('...')
      for (let i = current - 1; i <= current + 1; i++) {
        pages.push(i)
      }
      pages.push('...')
      pages.push(total)
    }
  }
  
  return pages
})

const jumpPage = ref('')

function handlePageChange(page) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return
  emit('page-change', page)
}

function handlePageSizeChange(e) {
  const newSize = parseInt(e.target.value, 10)
  emit('page-size-change', newSize)
}

function handleJumpPage() {
  const page = parseInt(jumpPage.value, 10)
  if (page >= 1 && page <= totalPages.value) {
    handlePageChange(page)
    jumpPage.value = ''
  }
}
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.meta-table {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.mt-header {
  @include flex-between;
  margin-bottom: var(--spacing-md);
  gap: var(--spacing-md);
  flex-shrink: 0;
}

.mt-batch-toolbar {
  @include flex-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
  flex-shrink: 0;
}

.mt-batch-count {
  font-size: var(--font-size-md);
  color: var(--color-primary);
  font-weight: 500;
}

.mt-batch-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.mt-batch-btn {
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  
  &:hover {
    background: var(--color-bg-spotlight);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  
  &--danger {
    background: var(--color-error-bg);
    border-color: var(--color-error-border);
    color: var(--color-error);
    
    &:hover {
      background: var(--color-error);
      border-color: var(--color-error);
      color: white;
    }
  }
  
  &--secondary {
    background: var(--color-bg-primary);
    border-color: var(--color-border);
    color: var(--color-text-secondary);
    
    &:hover {
      background: var(--color-bg-spotlight);
      border-color: var(--color-primary);
      color: var(--color-primary);
    }
  }
}

.mt-query {
  flex: 1;
  max-width: 320px;
}

.mt-search {
  position: relative;
  display: flex;
  align-items: center;

  svg {
    position: absolute;
    left: var(--spacing-sm);
    color: var(--color-text-placeholder);
    pointer-events: none;
  }
}

.mt-search-input {
  width: 100%;
  height: var(--input-height-md);
  padding: 0 var(--spacing-md) 0 calc(var(--spacing-sm) + 22px);
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  outline: none;
  transition: var(--transition-normal);

  &::placeholder {
    color: var(--color-text-placeholder);
  }

  &:hover {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }
}

.mt-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.mt-action-btn {
  @include button-base;
  font-size: var(--font-size-sm);

  &--primary { @include button-primary; }
  &--secondary { @include button-secondary; }
}

.mt-body {
  flex: 1;
  overflow-y: auto;
  @include scrollbar;
  min-height: 200px;
}

.mt-loading {
  @include flex-center;
  padding: var(--spacing-xxl);
  gap: var(--spacing-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-md);
}

.mt-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: mt-spin 0.6s linear infinite;
}

@keyframes mt-spin {
  to { transform: rotate(360deg); }
}

.mt-empty {
  @include flex-center;
  padding: var(--spacing-xxl);
}

.mt-table-wrap {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.mt-highlight {
  background-color: var(--yonyou-orange-100, #FFF7ED);
  color: var(--yonyou-orange-800, #C2410C);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: var(--font-weight-semibold, 600);
}

.mt-table {
  width: 100%;
  border-collapse: collapse;

  th, td {
    padding: var(--spacing-sm) var(--spacing-md);
    text-align: left;
    border-bottom: 1px solid var(--color-border-secondary);
    font-size: var(--font-size-md);
  }

  th {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
    font-weight: var(--font-weight-medium);
    white-space: nowrap;
    user-select: none;
  }

  .mt-th--sortable {
    cursor: pointer;
    transition: color var(--transition-fast);

    &:hover {
      color: var(--color-text-primary);

      .mt-sort-icon {
        opacity: 1;
      }
    }
  }

  .mt-th-label {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }

  .mt-sort-icon {
    display: inline-flex;
    opacity: 0;
    transition: opacity var(--transition-fast);
    color: var(--color-text-tertiary);
  }

  .mt-sort-active {
    opacity: 1;
    color: var(--color-primary);
  }
}

.mt-row {
  transition: background var(--transition-fast);

  &:hover {
    background: var(--color-bg-secondary);
  }

  &--stripe:nth-child(even) {
    background: #fafbfc;
  }

  &:hover.mt-row--stripe:nth-child(even) {
    background: var(--color-bg-secondary);
  }

  &--selected {
    background: var(--color-primary-bg) !important;
  }
}

.mt-th--checkbox,
.mt-td--checkbox {
  width: 40px;
  min-width: 40px;
  padding: var(--spacing-sm) !important;
  text-align: center;
}

.mt-checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;

  input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;

    &:checked + .mt-checkbox-box {
      background: var(--color-primary);
      border-color: var(--color-primary);

      &::after {
        opacity: 1;
        transform: rotate(45deg) scale(1);
      }
    }

    &:indeterminate + .mt-checkbox-box {
      background: var(--color-primary);
      border-color: var(--color-primary);

      &::after {
        opacity: 1;
        transform: rotate(90deg) scale(1);
        width: 8px;
        height: 8px;
        border: none;
        background: white;
        border-radius: 1px;
        top: 3px;
        left: 3px;
      }
    }

    &:focus + .mt-checkbox-box {
      box-shadow: 0 0 0 2px var(--color-primary-bg);
    }
  }

  &-box {
    position: relative;
    width: 16px;
    height: 16px;
    background: var(--color-bg-base);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    transition: var(--transition-fast);

    &::after {
      content: '';
      position: absolute;
      top: 2px;
      left: 5px;
      width: 4px;
      height: 8px;
      border: 2px solid white;
      border-top: none;
      border-left: none;
      opacity: 0;
      transform: rotate(45deg) scale(0);
      transition: var(--transition-fast);
    }

    &:hover {
      border-color: var(--color-primary);
    }
  }
}

.mt-td--actions {
  white-space: nowrap;
}

.mt-cell-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.mt-link-btn {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-xs);
  font-family: var(--font-family);
  color: var(--color-primary);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-fast);

  &:hover {
    background: var(--color-primary-bg);
  }

  &--default {
    color: var(--color-text-2);

    &:hover {
      background: var(--color-fill-1);
    }
  }

  &--primary {
    color: var(--color-primary);

    &:hover {
      background: var(--color-primary-bg);
    }
  }

  &--text {
    color: var(--color-text-2, #4e5969);

    &:hover {
      background: var(--color-fill-1, #f7f8fa);
      color: var(--color-text-1, #1d2129);
    }
  }

  &--danger {
    color: var(--color-error, #f53f3f);

    &:hover {
      background: var(--color-error-bg, #ffece8);
    }
  }

  &--warning {
    color: var(--color-warning, #ff7d00);

    &:hover {
      background: var(--color-warning-bg, #fff1e6);
    }
  }

  &--success {
    color: var(--color-success, #00b42a);

    &:hover {
      background: var(--color-success-bg, #e8ffea);
    }
  }
}

.mt-status {
  display: inline-flex;
  align-items: center;
  height: var(--tag-height-sm);
  padding: 0 var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  line-height: 1;

  &--active {
    background: var(--color-success-bg);
    color: var(--color-success);
    border: 1px solid var(--color-success-border);
  }

  &--inactive {
    background: var(--color-bg-tertiary);
    color: var(--color-text-tertiary);
    border: 1px solid var(--color-border);
  }

  &--warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
    border: 1px solid var(--color-warning-border);
  }

  &--info {
    background: var(--color-info-bg);
    color: var(--color-info);
    border: 1px solid var(--color-info-border);
  }
}

.mt-tag {
  display: inline-flex;
  align-items: center;
  height: var(--tag-height-sm);
  padding: 0 var(--spacing-sm);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  line-height: 1;

  &--primary {
    background: var(--color-primary-bg);
    color: var(--color-primary);
  }

  &--success {
    background: var(--color-success-bg);
    color: var(--color-success);
  }

  &--warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }

  &--danger {
    background: var(--color-error-bg);
    color: var(--color-error);
  }

  &--default {
    background: var(--color-bg-tertiary);
    color: var(--color-text-secondary);
  }
}

.mt-time {
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.mt-ellipsis {
  @include text-ellipsis;
  max-width: 240px;
  display: inline-block;
}

.mt-pagination {
  @include flex-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border-secondary);
  background: var(--color-bg-primary);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.mt-pagination-total {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.mt-pagination-pages {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.mt-pagination-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 var(--spacing-xs);
  font-size: var(--font-size-xs);
  font-family: var(--font-family);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-fast);
  user-select: none;

  &:hover:not(:disabled) {
    color: var(--color-primary);
    border-color: var(--color-primary);
  }

  &:disabled {
    color: var(--color-text-disabled);
    background: var(--color-bg-disabled);
    cursor: not-allowed;
  }

  &--active {
    color: var(--color-primary);
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
  }
}

.mt-pagination-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.mt-pagination-size {
  display: flex;
  align-items: center;
}

.mt-pagination-select {
  height: 28px;
  padding: 0 var(--spacing-sm);
  padding-right: var(--spacing-lg);
  font-size: var(--font-size-xs);
  font-family: var(--font-family);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  outline: none;
  transition: var(--transition-fast);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23999'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 4px center;
  background-size: 12px;

  &:hover {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }
}

.mt-pagination-jumper {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.mt-pagination-jumper-input {
  width: 48px;
  height: 28px;
  padding: 0 var(--spacing-xs);
  font-size: var(--font-size-xs);
  font-family: var(--font-family);
  color: var(--color-text-primary);
  text-align: center;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: var(--transition-fast);
  -moz-appearance: textfield;

  &::-webkit-outer-spin-button,
  &::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }

  &:hover {
    border-color: var(--color-primary);
  }

  &:focus {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-focus);
  }
}
</style>
