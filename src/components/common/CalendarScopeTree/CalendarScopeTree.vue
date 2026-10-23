<template>
  <div class="calendar-scope-tree">
    <div v-if="showSearch" class="cst-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索日历（编码/名称）"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="cst-toolbar">
      <AppButton variant="text" size="sm" @click="handleToggleExpandAll">
        <el-icon :size="14">
          <component :is="isAllExpanded ? Fold : Expand" />
        </el-icon>
        {{ isAllExpanded ? '收起' : '展开' }}
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleSelectAll">
        <el-icon :size="14"><Select /></el-icon>
        全选
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleClear">
        <el-icon :size="14"><CircleClose /></el-icon>
        清空
      </AppButton>
      <AppButton variant="text" size="sm" :disabled="refreshing" @click="handleRefresh">
        <el-icon :size="14" :class="{ 'is-loading': refreshing }"><RefreshRight /></el-icon>
        刷新
      </AppButton>
    </div>

    <div class="cst-tree-container">
      <div v-if="loading" class="cst-loading">
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <el-tree
        v-else
        ref="treeRef"
        :key="treeKey"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        show-checkbox
        :check-strictly="false"
        :default-expand-all="false"
        :default-expanded-keys="expandedKeys"
        :default-checked-keys="checkedKeysFromScope"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        :indent="16"
        @check="handleCheck"
      >
        <template #default="{ data }">
          <span class="cst-node">
            <span class="cst-node-label" :title="data.name">{{ data.name }}</span>
            <el-tag
              class="cst-node-kind"
              size="small"
              :type="data.parentId == null ? 'primary' : 'info'"
              disable-transitions
            >{{ data.parentId == null ? '基准' : '派生' }}</el-tag>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="cst-empty">
        <el-empty description="暂无日历数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * CalendarScopeTree — 作业日历范围树（MOMP 注入的 scope 树组件，供作业日历管理页使用）
 *
 * 契约与 LocationScopeTree / RegionScopeTree 一致：
 *   - props.scopeIds: MOMP 传入 page.scopeIds，读 scopeIds['calendar'] = {selected, effective}
 *     （键必须与 CalendarManagement 的 objectTypes 对齐）
 *   - emit 'scope-change': { calendarIds, effectiveCalendarIds }
 *   - expose clear / loadTreeData / handleSelectAll（兼容 MOMP scopeTreeRef 调用）
 *
 * 日历是「基准 → 派生」自引用树（parent_calendar_id，一期至多一级），数据量小，
 * 单次 page_size=500 拉全量 + 客户端组树即可；节点标出「基准/派生」，
 * 因为树上两者名字风格相近（如「中国基准日历」「上海张江厂区日历」），
 * 仅靠缩进容易误判层级语义。
 */
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import {
  Search, Loading, Expand, Fold, Select, CircleClose, RefreshRight
} from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { createScopeGuard } from '@/composables/scopeGuard'

const props = defineProps({
  showSearch: { type: Boolean, default: true },
  scopeIds: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['scope-change', 'load'])

const treeRef = shallowRef(null)
const treeData = shallowRef([])
const loading = ref(false)
const refreshing = ref(false)
const searchQuery = ref('')
const expandedKeys = shallowRef([])
const treeKey = ref(1)
const isAllExpanded = ref(false)
const guard = createScopeGuard()

const treeProps = computed(() => ({ label: 'name', children: 'children' }))

// ============================================================
//  数据加载：扁平 calendar → parent_calendar_id 组装树（按 code 升序，基准日历在前）
// ============================================================
async function loadTreeData() {
  loading.value = true
  try {
    const result = await boService.query('calendar', { page_size: 500 })
    const data = result.data || result
    const items = data.items || (Array.isArray(data) ? data : [])
    const tree = buildTree(items)
    const currentChecked = treeRef.value?.getCheckedKeys?.() || []
    treeData.value = tree
    treeKey.value++
    if (currentChecked.length) {
      await nextTick()
      const allKeys = collectAllKeys(tree)
      treeRef.value?.setCheckedKeys(
        currentChecked.filter(k => allKeys.some(x => String(x) === String(k))))
    }
    expandedKeys.value = collectExpandableKeys(tree, currentChecked)
    emit('load', treeData.value)
  } catch (error) {
    console.error('[CalendarScopeTree] Failed to load calendar tree:', error)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

function buildTree(items) {
  const byId = new Map()
  items.forEach(c => byId.set(c.id, {
    id: c.id,
    originalId: c.id,
    name: c.name,
    code: c.code,
    parentId: c.parent_calendar_id,
    children: []
  }))
  const roots = []
  for (const node of byId.values()) {
    const parent = node.parentId != null ? byId.get(node.parentId) : null
    if (parent && parent.id !== node.id) parent.children.push(node)
    else roots.push(node)
  }
  const sortRec = (list) => {
    list.sort((a, b) => String(a.code || '').localeCompare(String(b.code || '')))
    list.forEach(n => sortRec(n.children))
  }
  sortRec(roots)
  return roots
}

// ============================================================
//  scope 计算：{ calendarIds, effectiveCalendarIds }
//  effective = 勾选 ∪ 全部子孙（勾中基准日历 → 派生厂区日历一并命中）
// ============================================================
function emitScopeChange() {
  if (!treeRef.value) return
  const checkedNodes = treeRef.value.getCheckedNodes?.(false, false) || []
  const checkedIds = checkedNodes.map(n => n.data?.originalId ?? n.data?.id ?? n.id)
  const effective = new Set(checkedIds)
  checkedIds.forEach(id => {
    collectDescendantIds(findById(treeData.value, id)).forEach(d => effective.add(d))
  })
  emit('scope-change', {
    calendarIds: checkedIds,
    effectiveCalendarIds: [...effective]
  })
}

function findById(nodes, id) {
  for (const n of nodes || []) {
    if (String(n.id) === String(id)) return n
    if (n.children?.length) {
      const found = findById(n.children, id)
      if (found) return found
    }
  }
  return null
}

function collectDescendantIds(node) {
  const ids = []
  ;(function walk(n) {
    for (const c of n?.children || []) {
      ids.push(c.originalId ?? c.id)
      walk(c)
    }
  })(node)
  return ids
}

function handleCheck() {
  if (guard.active()) return
  emitScopeChange()
}

// ============================================================
//  反向同步：scopeIds 变化 → setCheckedKeys 恢复勾选
// ============================================================
const checkedKeysFromScope = computed(() => {
  const scope = props.scopeIds?.['calendar']
  const ids = (scope?.selected?.length ? scope.selected : (scope?.effective || []))
  if (!ids?.length) return []
  const idSet = new Set(ids.map(String))
  const keys = []
  ;(function walk(list) {
    for (const n of list) {
      if (idSet.has(String(n.originalId ?? n.id))) keys.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  })(treeData.value)
  return keys
})

watch(checkedKeysFromScope, (newKeys) => {
  nextTick(async () => {
    if (!treeRef.value) return
    guard.enter()
    treeRef.value.setCheckedKeys(newKeys)
    await nextTick(); await nextTick()
    guard.exit()
  })
})

// ============================================================
//  工具栏
// ============================================================
function handleSearch(query) {
  treeRef.value?.filter(query)
}
function filterNodeMethod(value, data) {
  if (!value) return true
  const kw = String(value).toLowerCase()
  return (data.name?.toLowerCase().includes(kw)) || (data.code?.toLowerCase().includes(kw))
}

function collectAllKeys(nodes, acc = []) {
  for (const n of nodes || []) {
    acc.push(n.id)
    if (n.children?.length) collectAllKeys(n.children, acc)
  }
  return acc
}

function collectExpandableKeys(nodes, selectedKeys) {
  const selected = new Set((selectedKeys || []).map(String))
  const keys = []
  ;(function walk(list) {
    for (const n of list) {
      if (n.children?.length && selected.has(String(n.id))) keys.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  })(nodes)
  return keys
}

function setAllExpanded(expanded) {
  if (!treeRef.value?.store) return
  const nodesMap = treeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.childNodes?.length) node.expanded = expanded
  })
}
function handleExpandAll() {
  const keys = []
  ;(function walk(nodes) {
    for (const n of nodes) {
      if (n.children?.length) { keys.push(n.id); walk(n.children) }
    }
  })(treeData.value)
  expandedKeys.value = [...keys]
  setAllExpanded(true)
}
function handleCollapseAll() {
  expandedKeys.value = []
  setAllExpanded(false)
}
function handleToggleExpandAll() {
  if (isAllExpanded.value) handleCollapseAll()
  else handleExpandAll()
  isAllExpanded.value = !isAllExpanded.value
}

async function handleSelectAll() {
  if (treeData.value.length === 0) return
  guard.enter()
  treeRef.value.setCheckedKeys(collectAllKeys(treeData.value))
  await nextTick(); await nextTick()
  guard.exit()
  emitScopeChange()
}

async function handleClear() {
  guard.enter()
  treeRef.value?.setCheckedKeys([])
  await nextTick(); await nextTick()
  guard.exit()
  emit('scope-change', { calendarIds: [], effectiveCalendarIds: [] })
}

async function handleRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try { await loadTreeData() } finally { refreshing.value = false }
}

onMounted(() => { loadTreeData() })

defineExpose({
  clear: handleClear,
  loadTreeData,
  handleSelectAll,
  _test: {
    get treeData() { return treeData.value },
    get nodeCount() { return treeData.value?.length || 0 },
    get checkedKeys() { return treeRef.value?.getCheckedKeys?.() || [] }
  }
})
</script>

<style scoped>
.calendar-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.cst-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.cst-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.cst-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.cst-toolbar :deep(.el-icon) { margin-right: 2px; }
.cst-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.cst-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.cst-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.cst-node-kind {
  flex-shrink: 0;
  transform: scale(0.9);
  transform-origin: right center;
}
.cst-loading,
.cst-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.cst-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>
