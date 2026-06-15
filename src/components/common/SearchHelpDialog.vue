<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="720px"
    @update:model-value="$emit('update:visible', $event)"
    @open="handleOpen"
    @keydown="handleKeyDown"
  >
    <div class="search-help-dialog">
      <!-- 最近使用区域 -->
      <div v-if="recentItems.length > 0 && !dialogSearchQuery" class="recent-section">
        <div class="recent-header">
          <el-icon><Clock /></el-icon>
          <span>最近使用</span>
        </div>
        <div class="recent-items">
          <div
            v-for="item in recentItems"
            :key="item.value"
            :class="['recent-item', { selected: isRecentSelected(item) }]"
            @click="handleRecentClick(item)"
          >
            <span class="recent-item-display">{{ item.display }}</span>
            <span v-if="item.code" class="recent-item-code">({{ item.code }})</span>
            <el-icon v-if="isRecentSelected(item)" class="check-icon"><Check /></el-icon>
          </div>
        </div>
      </div>

      <!-- 搜索栏（flattree_flat 模式） -->
      <div v-if="displayMode === 'flat' || displayMode === 'tree_flat'" class="vh-search-bar">
        <el-input
          ref="searchInputRef"
          v-model="dialogSearchQuery"
          placeholder="输入关键词实时搜索..."
          :prefix-icon="Search"
          clearable
          @input="handleDialogSearchInput"
          @clear="handleDialogSearchClear"
        />
      </div>

      <!-- 搜索栏（tree 模式） -->
      <div v-if="displayMode === 'tree'" class="vh-search-bar">
        <el-input
          v-model="dialogSearchQuery"
          placeholder="搜索..."
          :prefix-icon="Search"
          clearable
          @input="handleSearch"
        />
      </div>

      <MetaListPage
        ref="metaListRef"
        v-if="displayMode === 'flat' || displayMode === 'tree_flat'"
        :object-type="source.target_bo || source.enum_type_id || 'unknown'"
        :display-mode="'dialog'"
        :hide-toolbar="true"
        :columns-override="columnsForMeta"
        :row-key="'value'"
        :options="metaListOptions"
        :enable-detail="false"
        :enable-auto-crud="false"
        class="vh-meta-list"
        @selection-change="handleSelectionChange"
        @row-click="handleMetaRowClick"
        @row-dblclick="handleMetaRowDblClick"
      />

      <el-tree
        v-else-if="displayMode === 'tree'"
        :data="treeData"
        :props="treeProps"
        :default-expand-level="expandLevel"
        node-key="value"
        highlight-current
        @node-click="handleTreeNodeClick"
        :load="loadTreeNode"
        lazy
      >
        <template #default="{ node, data }">
          <span>{{ data.display }}</span>
        </template>
      </el-tree>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <!-- 多选模式保留确定按钮；单选模式通过点击双击Enter 直接确认 -->
      <el-button v-if="multiple" type="primary" @click="handleConfirm" :disabled="!canConfirm">
        确定 ({{ internalSelectedItems.length }})
      </el-button>
      <el-button v-else-if="currentSingleItem" type="primary" @click="handleConfirm">
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Search, Clock, Check, InfoFilled } from '@element-plus/icons-vue'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'
import boService from '@/services/boService'

const props = defineProps({
  visible: { type: Boolean, default: false },
  valueHelpConfig: { type: Object, required: true },
  multiple: { type: Boolean, default: false },
  selectedValue: { type: [String, Number, Array], default: '' },
  customFetcher: { type: Function, default: null },
})

const emit = defineEmits(['update:visible', 'confirm'])

const searchQuery = ref('')
const dialogSearchQuery = ref('')
// 内部选择状态
const internalSelectedItems = ref([])
const currentSingleItem = ref(null)
const metaListRef = ref(null)
const searchInputRef = ref(null)
const recentItems = ref([])

// 监听外部传入的 selectedValue 变化，更新已选择项目（用于 Delta 场景）
watch(() => props.selectedValue, (newVal) => {
  if (newVal && Array.isArray(newVal) && newVal.length > 0) {
    // 外部传入了已选择的 IDs，初始化 internalSelectedItems
    // 如果 internalSelectedItems 中已有更完整的信息，保留它们
    const existingValues = new Set(internalSelectedItems.value.map(item => item.value))
    const newIds = newVal.filter(id => !existingValues.has(id))
    if (newIds.length > 0 || internalSelectedItems.value.length !== newVal.length) {
      // 有新的 ID，或者数量不一致，更新 internalSelectedItems
      internalSelectedItems.value = newVal.map(id => {
        const existing = internalSelectedItems.value.find(item => item.value === id)
        return existing || { value: id, display: String(id), code: '' }
      })
    }
  } else if ((!newVal || (Array.isArray(newVal) && newVal.length === 0)) && internalSelectedItems.value.length > 0) {
    // 外部清空了选择，同步清空 internalSelectedItems
    internalSelectedItems.value = []
  }
}, { deep: false })

// 监听外部传入的 externalSelectedItems（完整对象），用于 Delta 场景
watch(() => props.externalSelectedItems, (newVal) => {
  console.log('[SearchHelpDialog] externalSelectedItems changed:', newVal)
  if (newVal && Array.isArray(newVal) && newVal.length > 0) {
    // 外部传入了已选择的完整对象，直接使用
    internalSelectedItems.value = [...newVal]
    console.log('[SearchHelpDialog] internalSelectedItems updated to:', internalSelectedItems.value)
  } else if ((!newVal || newVal.length === 0) && internalSelectedItems.value.length > 0) {
    // 外部清空了，同步清空 internalSelectedItems
    internalSelectedItems.value = []
  }
}, { deep: true })

const source = computed(() => props.valueHelpConfig?.source || {})
const presentation = computed(() => props.valueHelpConfig?.presentation || {})
const behavior = computed(() => props.valueHelpConfig?.behavior || {})

const dialogTitle = computed(() => {
  const srcType = source.value.type
  if (srcType === 'enum') return '选择枚举值'
  if (srcType === 'bo') return '选择数据'
  return '选择值'
})

const displayMode = computed(() => presentation.value.display_mode || 'flat')
const displayColumns = computed(() => presentation.value.display_columns || [])
const columnsForMeta = computed(() => {
  return displayColumns.value.map(col => ({
    field: col.field,
    label: col.label,
    width: col.width
  }))
})
const pageSize = computed(() => {
  const val = presentation.value.page_size
  // 强制最大 15 条/页
  if (val && val > 0 && val <= 15) return val
  return 15
})
const total = ref(0)

const sourceId = ref('')

const sourceConfigParams = computed(() => {
  const src = source.value
  const params = {}
  if (src.value_field) params.value_field = src.value_field
  if (src.display_field) params.display_field = src.display_field
  if (src.code_field) params.code_field = src.code_field
  if (src.value_filter && Object.keys(src.value_filter).length > 0) {
    params.value_filter = src.value_filter
  }
  if (src.hierarchy && Object.keys(src.hierarchy).length > 0) {
    params.hierarchy = src.hierarchy
  }
  return params
})

// 对话框搜索关键词（直接被 fetcher 读取）
const dialogSearchKeyword = ref('')

const valueHelpFetcher = (params) => {
  const { page, sort } = params || {}
  const queryParams = {
    page: page || 1,
    pageSize: pageSize.value,
    ...sourceConfigParams.value
  }
  const searchKeyword = dialogSearchKeyword.value || ''
  if (searchKeyword) queryParams.search = searchKeyword
  if (sort) queryParams.sort = sort

  return boService.searchValueHelp(
    sourceType.value,
    sourceId.value,
    queryParams
  ).then(res => {
    const rawData = res.data?.data || []
    return {
      success: true,
      data: {
        items: rawData.map(item => ({
          ...item,
          id: item.value
        })),
        total: res.data?.total || rawData.length
      }
    }
  })
}

const effectiveFetcher = computed(() => {
  const baseFetcher = props.customFetcher || valueHelpFetcher
  // 包装 fetcher：统一注入搜索词，确保 customFetcher 也能收到搜索参数
  if (!props.customFetcher) return baseFetcher

  return (params) => {
    const searchKeyword = dialogSearchKeyword.value || ''
    return baseFetcher({ ...params, keyword: searchKeyword })
  }
})

const metaListOptions = computed(() => ({
  autoLoad: true,
  pageSize: pageSize.value,
  pageSizes: [15, 30, 50, 100],
  fetcher: effectiveFetcher.value
}))

const sourceType = ref('')

// ===== 最近使用功能 =====
const RECENT_MAX_ITEMS = 3
const recentKey = computed(() => `recent_value_help_${sourceId.value}`)

function getRecentItems() {
  try {
    const stored = localStorage.getItem(recentKey.value)
    return stored ? JSON.parse(stored) : []
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to get recent items:', e)
    return []
  }
}

function saveRecentItem(item) {
  try {
    const recent = getRecentItems()
    const filtered = recent.filter(r => r.value !== item.value)
    const updated = [item, ...filtered].slice(0, RECENT_MAX_ITEMS)
    localStorage.setItem(recentKey.value, JSON.stringify(updated))
    recentItems.value = updated
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to save recent item:', e)
  }
}

function loadRecentItems() {
  recentItems.value = getRecentItems()
}

watch(() => source.value, (src) => {
  if (src?.type === 'enum') {
    sourceType.value = 'enum'
    sourceId.value = src.enum_type_id || ''
  } else if (src?.type === 'bo') {
    sourceType.value = 'bo'
    sourceId.value = src.target_bo || ''
  } else if (src?.type === 'custom') {
    sourceType.value = 'custom'
    sourceId.value = src.endpoint || ''
  }
}, { immediate: true })
const expandLevel = computed(() => source.value.hierarchy?.expand_level || 2)
const valueField = computed(() => source.value.value_field || 'value')

const treeData = computed(() => {
  if (displayMode.value !== 'tree') return []
  return buildTree([])
})

const treeProps = computed(() => ({
  label: 'display',
  children: 'children',
  isLeaf: (data) => !data.children || data.children.length === 0,
}))

const canConfirm = computed(() => {
  if (props.multiple) return internalSelectedItems.value.length > 0
  return currentSingleItem.value !== null
})

function buildTree(items) {
  const map = {}
  const roots = []
  for (const item of items) {
    map[item.value] = { ...item, children: [] }
  }
  for (const item of items) {
    const parentId = item.extra?.parent_id
    if (parentId && map[parentId]) {
      map[parentId].children.push(map[item.value])
    } else {
      roots.push(map[item.value])
    }
  }
  return roots
}

// ===== 同步已选项目 =====
function syncSelectedItemsFromMetaList() {
  // 优先使用 props.externalSelectedItems（完整对象）
  if (props.externalSelectedItems && Array.isArray(props.externalSelectedItems) && props.externalSelectedItems.length > 0) {
    internalSelectedItems.value = [...props.externalSelectedItems]
    return
  }
  
  // 回退：使用 props.selectedValue（ID 数组）
  // 注意：当只有 ID 没有 display 时，MetaListPage 需要根据 ID 请求显示名称
  if (props.selectedValue && Array.isArray(props.selectedValue) && props.selectedValue.length > 0) {
    internalSelectedItems.value = props.selectedValue.map(id => ({
      value: id,
      display: String(id),
      code: ''
    }))
    // 如果只有 ID，需要异步加载显示名称
    if (internalSelectedItems.value.length > 0 && props.selectedValue.length > 0) {
      loadDisplayNamesForSelectedItems(props.selectedValue)
    }
  }
}

// 异步加载选中项的显示名称
async function loadDisplayNamesForSelectedItems(ids) {
  if (!ids || ids.length === 0) return
  try {
    const response = await boService.searchValueHelp(
      sourceType.value,
      sourceId.value,
      { 
        page: 1, 
        pageSize: ids.length,
        filters: { id__in: ids.join(',') }
      }
    )
    const items = response.data?.data || response.data || []
    if (items.length > 0) {
      // 合并显示名称
      items.forEach(item => {
        const found = internalSelectedItems.value.find(s => s.value === item.value || s.value === item.id)
        if (found) {
          found.display = item.display || item.name || item.username || item.code || String(item.value || item.id)
          found.code = item.code || ''
        }
      })
    }
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to load display names:', e)
  }
}

// ===== 打开/重置 =====
function handleOpen() {
  searchQuery.value = ''
  dialogSearchQuery.value = ''
  dialogSearchKeyword.value = ''
  
  // 立即同步已选项目（不能依赖 setTimeout 延迟）
  syncSelectedItemsFromMetaList()
  
  currentSingleItem.value = null
  loadRecentItems()
  
  // 延迟聚焦：el-dialog 有打开动画(约300ms)，nextTick 太早
  setTimeout(() => {
    if (searchInputRef.value?.focus) {
      searchInputRef.value.focus()
    }
    if (metaListRef.value?.refresh) {
      metaListRef.value.refresh()
    }
  }, 350)
}

// ===== 实时搜索 (C2) =====
let searchTimer = null
function handleSearch(query) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    searchQuery.value = query
  }, behavior.value.debounce_ms || 300)
}

function handleDialogSearchInput(query) {
  // C2: 实时搜索 - 输入即搜（debounce 300ms）
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    dialogSearchKeyword.value = query || ''
    if (metaListRef.value) {
      metaListRef.value.loadList()
    }
  }, 300)
}

function handleDialogSearchClear() {
  dialogSearchQuery.value = ''
  dialogSearchKeyword.value = ''
  if (metaListRef.value) {
    metaListRef.value.loadList()
  }
}

// 监听搜索框清空（用户删除文字时自动恢复列表）
watch(dialogSearchQuery, (newVal) => {
  if (newVal === '' && dialogSearchKeyword.value !== '') {
    dialogSearchKeyword.value = ''
    if (metaListRef.value) {
      metaListRef.value.loadList()
    }
  }
})

// ===== 行选择 & 确认逻辑 =====

/** 从原始行数据提取标准化项 */
function normalizeItem(row) {
  const value = row.value != null ? row.value : row.id
  const display = row.display || row.name || row.username || row.code || String(value)
  return {
    value,
    display,
    code: row.code || '',
    raw: row
  }
}

/**
 * C1 + C3: 单选模式下的行点击/双击处理
 * - 单击: 高亮选中（给用户反悔机会）
 * - 双击: 立即确认并关闭
 */
function handleMetaRowClick({ row }) {
  if (props.multiple) return
  // C1: 单击仅高亮选中
  currentSingleItem.value = normalizeItem(row)
}

function handleMetaRowDblClick({ row }) {
  if (props.multiple) return
  // C3: 双击立即确认并关闭
  const item = normalizeItem(row)
  currentSingleItem.value = item
  saveRecentItem(item)
  emit('update:visible', false)
  emit('confirm', item)
}

/** 最近使用项点击 */
function handleRecentClick(item) {
  if (props.multiple) {
    const index = internalSelectedItems.value.findIndex(s => s.value === item.value)
    if (index > -1) {
      internalSelectedItems.value.splice(index, 1)
    } else {
      internalSelectedItems.value.push(item)
    }
  } else {
    // 最近使用单击即确认
    currentSingleItem.value = item
    saveRecentItem(item)
    emit('update:visible', false)
    emit('confirm', item)
  }
}

function isRecentSelected(item) {
  if (props.multiple) {
    return internalSelectedItems.value.some(s => s.value === item.value)
  }
  return currentSingleItem.value?.value === item.value
}

function handleSelectionChange(selection) {
  // 使用与 normalizeItem 相同的逻辑处理多种字段名
  internalSelectedItems.value = selection.map(s => {
    const value = s.value != null ? s.value : s.id
    return {
      value: value,
      display: s.display || s.name || s.username || s.title || s.label || s.code || String(value),
      code: s.code || '',
    }
  })
  if (!props.multiple && selection.length > 0) {
    const first = selection[0]
    currentSingleItem.value = normalizeItem(first)
  }
}

function handleTreeNodeClick(data) {
  if (props.multiple) return
  currentSingleItem.value = {
    value: data.value,
    display: data.display,
    code: data.code,
  }
}

// ===== C4: 键盘导航 =====
function handleKeyDown(e) {
  // Enter: 确认当前选中项
  if (e.key === 'Enter' && !e.isComposing) {
    if (!props.multiple && currentSingleItem.value) {
      e.preventDefault()
      saveRecentItem(currentSingleItem.value)
      emit('update:visible', false)
      emit('confirm', currentSingleItem.value)
    } else if (props.multiple && internalSelectedItems.value.length > 0) {
      e.preventDefault()
      handleConfirm()
    }
  }
  // Esc: 关闭弹窗
  if (e.key === 'Escape') {
    emit('update:visible', false)
  }
}

// ===== Tree 异步加载 =====
async function loadTreeNode(node, resolve) {
  const isRoot = node.level === 0
  const parentField = props.valueHelpConfig?.source?.hierarchy?.parent_field || 'parent_id'

  const params = {
    page: 1,
    pageSize: isRoot ? 100 : 50,
    ...sourceConfigParams.value
  }

  if (!isRoot && node.data) {
    const parentValue = node.data.value != null ? node.data.value : node.data.id
    params.filters = { [parentField]: parentValue }
  } else if (isRoot) {
    params.filters = { [parentField]: null }
  }

  try {
    const response = await boService.searchValueHelp(sourceType.value, sourceId.value, params)
    const items = response.data?.data || response.data || []

    const treeNodes = items.map(item => {
      const value = item.value != null ? item.value : (item[source.value_field || 'value'] != null ? item[source.value_field || 'value'] : item.id)
      const display = item.display || item[source.display_field || 'name'] || item.name || value

      return {
        value: value,
        label: display,
        display: display,
        code: item.code || '',
        data: item,
        leaf: node.level >= 2
      }
    })

    resolve(treeNodes)
  } catch (err) {
    console.error('[SearchHelpDialog] loadTreeNode failed:', err)
    resolve([])
  }
}

function removeSelectedItem(item) {
  // 从内部选择状态中移除
  internalSelectedItems.value = internalSelectedItems.value.filter(i => i.value !== item.value)
  // 同步取消表格中的勾选状态
  if (metaListRef.value?.tableRef) {
    const tableData = metaListRef.value.data || []
    const row = tableData.find(r => (r.value ?? r.id) === item.value)
    if (row) {
      metaListRef.value.tableRef.toggleRowSelection(row, false)
    }
  }
}

function handleConfirm() {
  if (props.multiple) {
    internalSelectedItems.value.forEach(item => saveRecentItem(item))
    emit('confirm', internalSelectedItems.value)
  } else {
    if (currentSingleItem.value) saveRecentItem(currentSingleItem.value)
    emit('confirm', currentSingleItem.value)
  }
  emit('update:visible', false)
}
</script>

<style scoped>
.search-help-dialog {
  padding: 0;
  display: flex;
  flex-direction: column;
}
.vh-search-bar {
  margin-bottom: 12px;
}
.vh-meta-list {
  flex: 1;
  min-height: 0;
  max-height: 500px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 让 MetaListPage 在 dialog 内自适应高度，分页可正常显示 */
.vh-meta-list :deep(.meta-list-page) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 限制 el-table 高度，给分页预留空间 */
.vh-meta-list :deep(.el-table) {
  flex: 1;
  min-height: 0;
}

.vh-meta-list :deep(.table-section) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.vh-meta-list :deep(.table-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* 分页区域在 dialog 内正常显示 */
.vh-meta-list :deep(.pagination-wrapper) {
  flex-shrink: 0;
  padding: var(--spacing-sm) 0;
  border-top: 1px solid var(--el-border-color-lighter);
}
.vh-selected-tags {
  margin-top: 12px;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-lighter);
}
.vh-selected-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}

/* 单选操作提示 */
.vh-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.vh-hint .el-icon {
  font-size: 14px;
  color: var(--el-color-primary);
}

/* 最近使用区域 */
.recent-section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.recent-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}

.recent-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
}

.recent-item:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.recent-item.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.recent-item-display {
  color: var(--el-text-color-primary);
}

.recent-item-code {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.check-icon {
  color: var(--el-color-primary);
  margin-left: 4px;
}

.mt-highlight {
  background-color: var(--yonyou-orange-100, #FFF7ED);
  color: var(--yonyou-orange-800, #C2410C);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}
</style>
