<template>
  <div class="region-scope-tree">
    <div v-if="showSearch" class="rst-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索区划（代码/名称）"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="rst-toolbar">
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

    <div class="rst-tree-container">
      <div v-if="loading" class="rst-loading">
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
          <span class="rst-node">
            <span class="rst-node-label" :title="data.name">{{ data.name }}</span>
            <el-tag
              v-if="data.level"
              class="rst-node-level"
              size="small"
              :type="levelTagOf(data.level)"
              disable-transitions
            >{{ levelLabelOf(data.level) }}</el-tag>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="rst-empty">
        <el-empty description="暂无区划数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * RegionScopeTree — 行政区划范围树（MOMP 注入的 scope 树组件，供行政区划管理页使用）
 *
 * 契约与 LocationScopeTree / ItemGroupScopeTree 一致：
 *   - props.scopeIds: MOMP 传入 page.scopeIds，读 scopeIds['region'] = {selected, effective}
 *     （键必须与 RegionManagement 的 objectTypes 对齐）
 *   - emit 'scope-change': { regionIds, effectiveRegionIds }
 *   - expose clear / loadTreeData / handleSelectAll（兼容 MOMP scopeTreeRef 调用）
 *
 * 行政区划是国/省/市/区四级自引用树（parent_id），数据量约 300 条，
 * 单次 page_size=500 拉全量 + 客户端组树即可；节点标出层级标签，
 * 避免在同一棵树上分不清「市」和「区」。
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

// level 枚举 → 中文标签 / 标签色（与 region.yaml enum_values 对齐）
const LEVEL_LABELS = {
  country: '国家',
  province: '省级',
  city: '地市',
  district: '区县'
}
const LEVEL_TAGS = {
  country: 'danger',
  province: 'warning',
  city: 'primary',
  district: 'success'
}
function levelLabelOf(level) {
  return LEVEL_LABELS[level] || level || ''
}
function levelTagOf(level) {
  return LEVEL_TAGS[level] || 'info'
}

// ============================================================
//  数据加载：扁平 region → parent_id 组装树（按 code 升序保持行政区划顺序）
// ============================================================
async function loadTreeData() {
  loading.value = true
  try {
    const result = await boService.query('region', { page_size: 500 })
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
    console.error('[RegionScopeTree] Failed to load region tree:', error)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

function buildTree(items) {
  const byId = new Map()
  items.forEach(r => byId.set(r.id, {
    id: r.id,
    originalId: r.id,
    name: r.name,
    code: r.code,
    level: r.level,
    parentId: r.parent_id,
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
//  scope 计算：{ regionIds, effectiveRegionIds }
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
    regionIds: checkedIds,
    effectiveRegionIds: [...effective]
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
  const scope = props.scopeIds?.['region']
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
  emit('scope-change', { regionIds: [], effectiveRegionIds: [] })
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
.region-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.rst-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.rst-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.rst-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.rst-toolbar :deep(.el-icon) { margin-right: 2px; }
.rst-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.rst-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.rst-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.rst-node-level {
  flex-shrink: 0;
  transform: scale(0.9);
  transform-origin: right center;
}
.rst-loading,
.rst-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.rst-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>
