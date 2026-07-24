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
      <!-- 最近使用区域 (排除已选) -->
      <div v-if="filteredRecentItems.length > 0 && !dialogSearchQuery" class="recent-section">
        <div class="recent-header">
          <el-icon><Clock /></el-icon>
          <span>最近使用</span>
        </div>
        <div class="recent-items">
          <div
            v-for="item in filteredRecentItems"
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

      <!-- 搜索栏（flat / tree_flat 模式） -->
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

      <HierarchicalTreePicker
        v-else-if="displayMode === 'tree'"
        ref="treePickerRef"
        :dimension-id="source.target_bo || ''"
        :checked-ids="props.selectedValue"
        :multiple="multiple"
        @confirm="handleTreePickerConfirm"
        @cancel="handleTreePickerCancel"
        @check-change="handleTreeCheckChange"
      />
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <!-- [UX-FIX 2026-07-23-R2] tree 模式多选: 用 internalSelectedItems 同步 (由 check-change 触发) -->
      <el-button
        v-if="multiple"
        type="primary"
        @click="handleConfirm"
        :disabled="!canConfirm"
      >
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
import HierarchicalTreePicker from '@/components/common/HierarchicalTreePicker'
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
const treePickerRef = ref(null)  // [UX-FIX 2026-07-23] tree 模式 ref
const recentItems = ref([])

// 监听外部传入的 selectedValue 变化，更新已选择项目（用于 Delta 场景）
// [FIX 2026-07-24-R19] tree 模式: 不在此处同步, 由 HierarchicalTreePicker @check-change 驱动
//   原因: 同 syncSelectedItemsFromMetaList, 避免 internalSelectedItems 与树勾选不同步
watch(() => props.selectedValue, (newVal) => {
  // tree 模式: 跳过, 由 handleTreeCheckChange 驱动
  if (displayMode.value === 'tree') return

  if (newVal && Array.isArray(newVal) && newVal.length > 0) {
    // 外部传入了已选择的 IDs，初始化 internalSelectedItems
    const existingValues = new Set(internalSelectedItems.value.map(item => item.value))
    const newIds = newVal.filter(id => !existingValues.has(id))
    if (newIds.length > 0 || internalSelectedItems.value.length !== newVal.length) {
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

// [FIX 2026-07-24-R19] 弹窗标题: "选择数据" → "选择XX" (如选择子领域)
//   dimensionId 到中文名映射 (与后端 management_dimension 一致)
const DIMENSION_LABEL_MAP = {
  product: '产品',
  version: '版本',
  domain: '领域',
  sub_domain: '子领域',
}

const dialogTitle = computed(() => {
  const srcType = source.value.type
  if (srcType === 'enum') return '选择枚举值'
  if (srcType === 'bo') {
    const targetBo = source.value.target_bo
    const label = DIMENSION_LABEL_MAP[targetBo]
    if (label) return `选择${label}`
    return '选择数据'
  }
  return '选择值'
})

const displayMode = computed(() => presentation.value.display_mode || 'flat')
const displayColumns = computed(() => presentation.value.display_columns || [])

// [REFACTOR 2026-07-22] 元数据驱动: 层级配置由后端从 hierarchies.yaml 读取,
//   经 /tree 响应 (hierarchy_meta) 透传给 HierarchicalTreePicker.
//   此处不再 hardcode 4 层 chain.

// [FIX 2026-07-22] HierarchicalTreePicker confirm: 单选/多选统一处理
function handleTreePickerConfirm(payload) {
  if (payload.type === 'single') {
    // 单选: emit 单个 id (跟原 flat 模式一致)
    emit('confirm', payload.id)
  } else {
    // [UX-FIX 2026-07-23] 多选 tree: emit 标准 items shape (跟 flat 模式一致)
    // payload.nodes 是 [{ id, name, type, ancestorPath }, ...]
    // [FIX 2026-07-23-R8] emit display=name (非路径), 让 DimensionScopePanel 优先用 item.name
    const items = (payload.nodes || []).map(n => ({
      value: n.id,
      display: n.name,
      code: '',
      name: n.name,
    }))
    emit('confirm', items)
  }
  emit('update:visible', false)
}

function handleTreePickerCancel() {
  emit('update:visible', false)
}

// [UX-FIX 2026-07-23] tree 模式勾选变化 -> 同步 internalSelectedItems
//   让 dialog 的 canConfirm / 底部 chips / 确定按钮的 count 都能正确响应
// [UX-FIX 2026-07-23-R2] 不再 guard displayMode — 即使 tree_flat 也会触发, 安全
// [FIX 2026-07-23-R12] 从 nodes 提取 name, 避免标签显示 ID
function handleTreeCheckChange({ ids, nodes }) {
  const nodeMap = new Map((nodes || []).map(n => [n.id, n]))
  internalSelectedItems.value = ids.map(id => {
    const existing = internalSelectedItems.value.find(s => s.value === id)
    if (existing && existing.name) return existing
    const node = nodeMap.get(id)
    const name = node?.name || ''
    return { value: id, display: name || String(id), code: node?.type || '', name }
  })
}

const columnsForMeta = computed(() => {
  return displayColumns.value.map(col => ({
    field: col.field,
    label: col.label,
    width: col.width,
    sortable: true,
    filterable: true
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
  // buildFilterQueryParams 产出: { page, page_size, keyword, ordering, domain_code__like, ... }
  // value help API 期望: { page, pageSize, search, sort, filters[field]=value }
  // 需要做格式转换
  const { page, sort, pageSize: _ps, page_size, keyword, ordering, ...restParams } = params || {}
  const queryParams = {
    page: page || 1,
    pageSize: pageSize.value,
    ...sourceConfigParams.value
  }
  // 关键词搜索：dialogSearchKeyword 优先，fallback 到 buildFilterQueryParams 的 keyword
  const searchKeyword = dialogSearchKeyword.value || keyword || ''
  if (searchKeyword) queryParams.search = searchKeyword
  // 排序：ordering (Django style) → sort (value help style)
  // ordering=-domain_code → sort=domain_code:desc
  // ordering=domain_code  → sort=domain_code:asc
  if (ordering) {
    const isDesc = ordering.startsWith('-')
    const sortField = isDesc ? ordering.slice(1) : ordering
    queryParams.sort = `${sortField}:${isDesc ? 'desc' : 'asc'}`
  } else if (sort) {
    queryParams.sort = sort
  }
  // 列头过滤：__like/__in/__gte/__lte → filters[field__suffix]=value
  // 保留 __like/__in/__gte/__lte 后缀，后端 BoValueHelpProvider 会解析
  // __like → LIKE '%value%' (模糊匹配)
  // __in  → IN (val1,val2) (多选)
  // __gte/__lte → >= / <= (范围)
  const skipKeys = ['value_field', 'display_field', 'code_field', 'value_filter', 'hierarchy', 'apply_target_permissions']
  const filters = {}
  for (const [key, value] of Object.entries(restParams)) {
    if (skipKeys.includes(key)) continue
    if (value === undefined || value === null || value === '') continue
    // 直接保留 key（含 __like/__in/__gte/__lte 后缀）
    filters[key] = value
  }
  if (Object.keys(filters).length > 0) {
    queryParams.filters = filters
  }

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
  // [FIX 2026-07-24-R19] "最近使用"补全真实 name
  //   原因: 旧版本保存的 item.display 可能是 String(value) (ID fallback)
  //   方案: 检测 display === String(value) 的 item, 异步拉取真名并更新 localStorage + recentItems
  warmupRecentItemNames()
}

// [R19] 异步补全"最近使用"项的真实名称 (参考 DimensionScopePanel.warmupNameCache 思路)
async function warmupRecentItemNames() {
  const needWarmup = recentItems.value.filter(
    item => !item.display || item.display === String(item.value)
  )
  if (needWarmup.length === 0) return

  try {
    // 复用 valueHelpFetcher 拉取 (按 id 批量查询)
    const ids = needWarmup.map(item => item.value)
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
    const nameMap = new Map()
    for (const it of items) {
      const id = it.value != null ? it.value : it.id
      const name = it.display || it.name || it.username || it.code || ''
      if (name) nameMap.set(id, { display: name, code: it.code || '' })
    }

    // 更新 recentItems + localStorage
    let changed = false
    const updated = recentItems.value.map(item => {
      const found = nameMap.get(item.value)
      if (found && (!item.display || item.display === String(item.value))) {
        changed = true
        return { ...item, display: found.display, code: found.code }
      }
      return item
    })
    if (changed) {
      recentItems.value = updated
      try {
        localStorage.setItem(recentKey.value, JSON.stringify(updated))
      } catch (e) {
        console.warn('[SearchHelpDialog] Failed to persist warmed recent items:', e)
      }
    }
  } catch (e) {
    console.warn('[SearchHelpDialog] warmupRecentItemNames failed:', e)
  }
}

// [UX-FIX 2026-07-23-R4] 最近使用排除已选 (避免用户重复选)
const filteredRecentItems = computed(() => {
  const selected = new Set()
  // multi mode: selectedValue 是 array
  if (Array.isArray(props.selectedValue)) {
    props.selectedValue.forEach(id => selected.add(id))
  } else if (props.selectedValue != null) {
    selected.add(props.selectedValue)
  }
  // externalSelectedItems: 完整对象
  if (Array.isArray(props.externalSelectedItems)) {
    props.externalSelectedItems.forEach(it => {
      if (it?.value != null) selected.add(it.value)
    })
  }
  // internalSelectedItems 也算
  internalSelectedItems.value.forEach(it => {
    if (it?.value != null) selected.add(it.value)
  })
  return recentItems.value.filter(item => !selected.has(item.value))
})

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
  // [FIX 2026-07-24-R19] tree 模式: 不预设 internalSelectedItems
  //   原因: tree 模式下由 HierarchicalTreePicker 的 @check-change 驱动 internalSelectedItems
  //         如果预设了, 但树中对应节点被剪枝/不存在, 会导致:
  //         - 按钮显示"确定(N)" (internalSelectedItems 有值)
  //         - 但树中无勾选 (节点不存在)
  //         - 用户看不到勾选, 以为没选, 但按钮显示有1项 → 困惑
  //   方案: tree 模式下清空, 等 setCheckedKeys 触发 @check → handleTreeCheckChange 同步
  //         如果树中有已选节点, setCheckedKeys 会触发 @check, internalSelectedItems 被正确设置
  //         如果树中没有已选节点, internalSelectedItems 保持空, 按钮显示"确定(0)" — 与树同步
  if (displayMode.value === 'tree') {
    internalSelectedItems.value = []
    return
  }

  // flat 模式: 优先使用 props.externalSelectedItems（完整对象）
  if (props.externalSelectedItems && Array.isArray(props.externalSelectedItems) && props.externalSelectedItems.length > 0) {
    internalSelectedItems.value = [...props.externalSelectedItems]
    return
  }

  // flat 模式回退：使用 props.selectedValue（ID 数组）
  if (props.selectedValue && Array.isArray(props.selectedValue) && props.selectedValue.length > 0) {
    internalSelectedItems.value = props.selectedValue.map(id => ({
      value: id,
      display: String(id),
      code: ''
    }))
    if (internalSelectedItems.value.length > 0 && props.selectedValue.length > 0) {
      loadDisplayNamesForSelectedItems(props.selectedValue)
    }
    return
  }

  // flat 模式: selectedValue 为空时清理
  internalSelectedItems.value = []
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

  // [FIX 2026-07-24-R19] tree 模式: 弹窗每次打开都主动重载树数据
  //   原因: el-dialog 关闭时 HierarchicalTreePicker 被销毁, treeData 状态丢失
  //         重新打开时 onMounted 会触发, 但有时序问题 (可能晚于 dialog open 动画)
  //         主动调用确保数据加载, 解决"第二次打开空白"问题
  if (displayMode.value === 'tree') {
    nextTick(() => {
      if (treePickerRef.value?.loadTreeData) {
        treePickerRef.value.loadTreeData()
      }
    })
  }

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
      // [FIX] 搜索时重置分页到第1页，避免翻页后搜索结果为空
      if (metaListRef.value.pagination) {
        metaListRef.value.pagination.current = 1
      }
      metaListRef.value.loadList()
    }
  }, 300)
}

function handleDialogSearchClear() {
  dialogSearchQuery.value = ''
  dialogSearchKeyword.value = ''
  if (metaListRef.value) {
    if (metaListRef.value.pagination) {
      metaListRef.value.pagination.current = 1
    }
    metaListRef.value.loadList()
  }
}

// 监听搜索框清空（用户删除文字时自动恢复列表）
watch(dialogSearchQuery, (newVal) => {
  if (newVal === '' && dialogSearchKeyword.value !== '') {
    dialogSearchKeyword.value = ''
    if (metaListRef.value) {
      if (metaListRef.value.pagination) {
        metaListRef.value.pagination.current = 1
      }
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
