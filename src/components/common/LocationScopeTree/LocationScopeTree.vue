<template>
  <div class="location-scope-tree">
    <div v-if="showSearch" class="lst-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索位置（编码/名称）"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="lst-toolbar">
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

    <div class="lst-tree-container">
      <div v-if="loading" class="lst-loading">
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
          <span class="lst-node">
            <el-icon class="lst-node-icon" :size="14"><LocationIcon /></el-icon>
            <span class="lst-node-label" :title="data.name">{{ data.name }}</span>
            <el-tag
              v-if="data.locationType"
              class="lst-node-type"
              size="small"
              :type="typeTagOf(data.locationType)"
              disable-transitions
            >{{ typeLabelOf(data.locationType) }}</el-tag>
            <span v-if="data.code" class="lst-node-code">{{ data.code }}</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="lst-empty">
        <el-empty description="暂无位置数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * LocationScopeTree — 位置范围树（MOMP 注入的 scope 树组件，供位置管理页使用）
 *
 * 契约与 ItemGroupScopeTree / OrgScopeTree 一致，MOMP 侧无需特殊处理：
 *   - props.scopeIds: MOMP 传入 page.scopeIds，读 scopeIds['location'] = {selected, effective}
 *     （键必须与 LocationManagement 的 objectTypes 一致）
 *   - emit 'scope-change': { locationIds, effectiveLocationIds }
 *   - expose clear / loadTreeData / handleSelectAll（兼容 MOMP scopeTreeRef 调用）
 *
 * 与 ItemGroupScopeTree 的差异：
 *   1. 位置是四类混合树（site 场地 / warehouse 仓库 / zone 区域 / bin 库位），
 *      层级合法性由后端校验（warehouse 只能挂 site、bin 只能挂 warehouse…）。
 *      树上直接标类型标签，避免用户在错误的层勾选后产生"过滤结果为什么是空"的困惑。
 *   2. 位置量级中等（site+warehouse+zone+bin 通常千级以内），仍用单次 page_size=500
 *      拉全量 + 客户端组树；若将来超过 500 需要改循环分页（参照 OrgScopeTree）。
 */
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import {
  Search, Loading, Expand, Fold, Select, CircleClose, RefreshRight, Location as LocationIcon
} from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { createScopeGuard } from '@/composables/scopeGuard'

const props = defineProps({
  showSearch: { type: Boolean, default: true },
  // scopeIds 由 MOMP 传入, 结构 scopeIds['location'] = { selected, effective }
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

// location_type 枚举 → 中文标签 / 标签色（与 location.yaml enum_values 对齐）
const TYPE_LABELS = {
  site: '场地',
  warehouse: '仓库',
  zone: '区域',
  bin: '库位'
}
const TYPE_TAGS = {
  site: 'primary',
  warehouse: 'success',
  zone: 'warning',
  bin: 'info'
}
function typeLabelOf(type) {
  return TYPE_LABELS[type] || type || ''
}
function typeTagOf(type) {
  return TYPE_TAGS[type] || 'info'
}

// ============================================================
//  数据加载：扁平 location → parent_id 组装树
// ============================================================
async function loadTreeData() {
  loading.value = true
  try {
    const result = await boService.query('location', { page_size: 500 })
    const data = result.data || result
    const items = data.items || (Array.isArray(data) ? data : [])
    const tree = buildTree(items)
    const currentChecked = treeRef.value?.getCheckedKeys?.() || []
    treeData.value = tree
    treeKey.value++
    // 保留刷新前的勾选与展开态
    if (currentChecked.length) {
      await nextTick()
      treeRef.value?.setCheckedKeys(currentChecked.filter(
        k => collectAllKeys(tree).some(x => String(x) === String(k))))
    }
    expandedKeys.value = collectExpandableKeys(tree, currentChecked)
    emit('load', treeData.value)
  } catch (error) {
    console.error('[LocationScopeTree] Failed to load location tree:', error)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

function buildTree(items) {
  const byId = new Map()
  items.forEach(l => byId.set(l.id, {
    id: l.id,
    originalId: l.id,
    name: l.name,
    code: l.code,
    locationType: l.location_type,
    parentId: l.parent_id,
    children: []
  }))
  const roots = []
  for (const node of byId.values()) {
    const parent = node.parentId != null ? byId.get(node.parentId) : null
    // 父存在且非自身 → 挂父；否则视为根（悬空/自环 parent_id 兜底）
    if (parent && parent.id !== node.id) parent.children.push(node)
    else roots.push(node)
  }
  return roots
}

// ============================================================
//  scope 计算：{ locationIds, effectiveLocationIds }
// ============================================================
function emitScopeChange() {
  if (!treeRef.value) return
  const checkedNodes = treeRef.value.getCheckedNodes?.(false, false) || []
  const checkedIds = checkedNodes.map(n => n.data?.originalId ?? n.data?.id ?? n.id)
  // check-strictly=false 时父节点选中已含子孙，这里再兜底补一层确保 effective 完整
  const effective = new Set(checkedIds)
  checkedIds.forEach(id => {
    collectDescendantIds(findById(treeData.value, id)).forEach(d => effective.add(d))
  })
  emit('scope-change', {
    locationIds: checkedIds,
    effectiveLocationIds: [...effective]
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
  // 键与 LocationManagement 的 objectTypes 对齐 (scopeIds['location'])
  const scope = props.scopeIds?.['location']
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
  emit('scope-change', { locationIds: [], effectiveLocationIds: [] })
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
.location-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.lst-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.lst-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.lst-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.lst-toolbar :deep(.el-icon) { margin-right: 2px; }
.lst-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.lst-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.lst-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}
.lst-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.lst-node-type {
  flex-shrink: 0;
  transform: scale(0.9);
  transform-origin: right center;
}
.lst-node-code {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.lst-loading,
.lst-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.lst-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>
