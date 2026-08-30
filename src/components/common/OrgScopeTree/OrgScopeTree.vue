<template>
  <div class="org-scope-tree">
    <div v-if="showSearch" class="ost-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索组织（编码/名称）"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="ost-toolbar">
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
      <AppButton variant="text" size="sm" @click="handleRefresh" :disabled="loading || refreshing">
        <el-icon :size="14" :class="{ 'is-loading': refreshing }"><RefreshRight /></el-icon>
        刷新
      </AppButton>
    </div>

    <div class="ost-tree-container">
      <div v-if="loading" class="ost-loading">
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        show-checkbox
        :check-strictly="false"
        :default-expand-all="false"
        :default-expanded-keys="defaultExpandedKeys"
        :default-checked-keys="objectCheckedNodeKeys"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        :indent="16"
        :key="treeKey"
        @check="handleCheck"
        @node-expand="onNodeExpand"
        @node-collapse="onNodeCollapse"
      >
        <template #default="{ data }">
          <span class="ost-node">
            <el-icon class="ost-node-icon" :size="14"><OfficeBuilding /></el-icon>
            <span class="ost-node-label" :title="data.name">{{ data.name }}</span>
            <span v-if="data.code" class="ost-node-code">{{ data.code }}</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="ost-empty">
        <el-empty description="暂无组织数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * OrgScopeTree — 组织范围树（MOMP 注入的 scope 树组件，供组织管理页使用）
 *
 * [MOMP 通用化 2026-08-30] 组件本体零 MOMP/archdata 硬编码：
 *   - 数据源：user_group（单类型平面列表，parent_id 自引用 → 客户端组装树）
 *   - node-key=id（无前缀），show-checkbox + check-strictly=false 级联多选
 *   - emit 'scope-change'：{ orgIds, effectiveOrgIds }（effective = 选中 ∪ 子孙）
 *   - 暴露 selectByCode / selectAll / clear / _test.treeData 兼容 MOMP scopeTreeRef 约定
 */
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import { Search, Loading, Expand, Fold, Select, CircleClose, RefreshRight, OfficeBuilding } from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { createScopeGuard } from '@/composables/scopeGuard'

const props = defineProps({
  showSearch: { type: Boolean, default: true },
  // [MOMP 通用化] scopeIds 由 MOMP 传入（page.scopeIds），结构 scopeIds['user_group']={selected,effective}
  scopeIds: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['scope-change', 'load'])

const treeRef = shallowRef(null)
const treeData = shallowRef([])
const loading = ref(false)
const refreshing = ref(false)
const searchQuery = ref('')
const defaultExpandedKeys = shallowRef([])
const treeKey = ref(1)
const isAllExpanded = ref(false)
const guard = createScopeGuard()

const treeProps = computed(() => ({ label: 'name', children: 'children' }))

// ============================================================
//  数据加载：扁平 user_group → parent_id 组装树
// ============================================================
async function loadTreeData(options = {}) {
  const { silent = false } = options
  if (!silent) loading.value = true
  if (!silent) isAllExpanded.value = false
  try {
    const result = await boService.query('user_group', { page_size: 5000 })
    const items = result.data?.items || result.data || []
    const tree = buildOrgTree(items)

    // silent 模式保留已选/展开状态
    if (silent && treeRef.value) {
      const currentCheckedKeys = treeRef.value.getCheckedKeys?.() || []
      if (currentCheckedKeys.length > 0) {
        const oldKeys = collectAllKeys(treeData.value)
        const newKeys = collectAllKeys(tree)
        const sameStructure =
          oldKeys.length === newKeys.length &&
          oldKeys.every(k => newKeys.includes(k))
        if (sameStructure) return
        guard.enter()
        treeData.value = tree
        defaultExpandedKeys.value = collectInitialExpandedKeys(tree, currentCheckedKeys)
        await nextTick(); await nextTick()
        treeRef.value.setCheckedKeys(currentCheckedKeys)
        await nextTick(); await nextTick(); await nextTick()
        guard.exit()
        return
      }
    }

    treeData.value = tree
    defaultExpandedKeys.value = collectInitialExpandedKeys(tree, [])
    emit('load', treeData.value)
  } catch (error) {
    console.error('[OrgScopeTree] Failed to load org tree:', error)
    treeData.value = []
  } finally {
    if (!silent) loading.value = false
  }
}

function buildOrgTree(items) {
  const byId = new Map()
  items.forEach(org => byId.set(org.id, {
    id: org.id,
    originalId: org.id,
    name: org.name,
    code: org.code,
    type: 'user_group',
    parentId: org.parent_id,
    children: []
  }))
  const roots = []
  for (const node of byId.values()) {
    const pid = node.parentId
    const parent = pid != null ? byId.get(pid) : null
    // 父节点存在且非自身 → 挂到父；否则视为根（自身/悬空 parent_id → 根）
    if (parent && parent.id !== node.id) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

// ============================================================
//  scope 计算：{ orgIds, effectiveOrgIds }
// ============================================================
function emitScopeChange() {
  if (!treeRef.value) return
  const checkedNodes = treeRef.value.getCheckedNodes?.(false, false) || []
  const checkedIds = checkedNodes.map(n => n.data?.originalId ?? n.data?.id ?? n.id)
  // effective = 选中 ∪ 子孙（级联模式下 checkedNode 已含全选父节点的子孙，这里兜底补一层）
  const effectiveIds = new Set(checkedIds)
  checkedIds.forEach(id => {
    const node = findById(treeData.value, id)
    collectDescendantIds(node).forEach(d => effectiveIds.add(d))
  })
  emit('scope-change', {
    orgIds: checkedIds,
    effectiveOrgIds: [...effectiveIds]
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
  function walk(n) {
    for (const c of n?.children || []) {
      ids.push(c.originalId ?? c.id)
      walk(c)
    }
  }
  walk(node)
  return ids
}

function handleCheck() {
  if (guard.active()) return
  emitScopeChange()
}

// ============================================================
//  反向同步：scopeIds 变化 → setCheckedKeys 恢复勾选
// ============================================================
const objectCheckedNodeKeys = computed(() => {
  const scope = props.scopeIds?.['user_group']
  const ids = (scope?.selected && scope.selected.length > 0 ? scope.selected : (scope?.effective || []))
  if (!ids?.length) return []
  return collectLeafMatchingKeys(treeData.value, ids)
})

function collectLeafMatchingKeys(nodes, ids) {
  const idSet = new Set(ids.map(String))
  const keys = []
  function walk(list) {
    for (const n of list) {
      if (idSet.has(String(n.originalId ?? n.id))) keys.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return keys
}

watch(objectCheckedNodeKeys, (newKeys) => {
  nextTick(async () => {
    if (!treeRef.value) return
    guard.enter()
    treeRef.value.setCheckedKeys(newKeys)
    await nextTick(); await nextTick()
    guard.exit()
  })
})

// ============================================================
//  展开状态持久化（跨 :data 重建）
// ============================================================
const userExpandedKeys = ref(new Set())
function onNodeExpand(data) {
  if (data?.id != null) userExpandedKeys.value.add(String(data.id))
}
function onNodeCollapse(data) {
  if (data?.id != null) userExpandedKeys.value.delete(String(data.id))
}

let storeSetDataHooked = false
function installStoreSetDataHook() {
  if (storeSetDataHooked) return
  if (!treeRef.value?.store) return
  const store = treeRef.value.store
  const origSetData = store.setData.bind(store)
  store.setData = function (newData) {
    const savedExpandedKeys = []
    const oldNodesMap = treeRef.value?.store?.nodesMap
    if (oldNodesMap) {
      for (const [key, node] of Object.entries(oldNodesMap)) {
        if (node.expanded) savedExpandedKeys.push(key)
      }
    }
    const allSaved = [...new Set([...savedExpandedKeys, ...userExpandedKeys.value])]
    const result = origSetData(newData)
    const allDataIds = new Set()
    const collect = (nodes) => {
      for (const n of (nodes || [])) {
        if (n.id != null) allDataIds.add(String(n.id))
        if (n.children) collect(n.children)
      }
    }
    collect(newData)
    const valid = allSaved.filter(k => allDataIds.has(String(k)))
    if (valid.length > 0) {
      nextTick(() => {
        const newStore = treeRef.value?.store
        if (newStore?.nodesMap) {
          for (const key of valid) {
            const node = newStore.nodesMap[key]
            if (node && !node.isLeaf && typeof node.expand === 'function' && !node.expanded) {
              node.expand()
            }
          }
        }
      })
    }
    return result
  }
  storeSetDataHooked = true
}

watch(treeRef, (val) => {
  if (val) installStoreSetDataHook()
})

// ============================================================
//  工具栏：展开/折叠 / 全选 / 清空 / 刷新 / 搜索
// ============================================================
function handleSearch(query) {
  treeRef.value?.filter(query)
}
function filterNodeMethod(value, data) {
  if (!value) return true
  const kw = value.toLowerCase()
  return (data.name?.toLowerCase().includes(kw)) || (data.code?.toLowerCase().includes(kw))
}

function collectAllKeys(nodes) {
  const keys = []
  nodes.forEach(node => {
    keys.push(node.id)
    if (node.children?.length) keys.push(...collectAllKeys(node.children))
  })
  return keys
}

function handleExpandAll() {
  const keys = []
  expandInto(treeData.value, keys)
  defaultExpandedKeys.value = [...keys]
  if (!treeRef.value?.store) return
  const nodesMap = treeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.childNodes?.length) node.expanded = true
  })
}
function expandInto(nodes, keys) {
  nodes?.forEach(node => {
    if (node.children?.length) {
      if (!keys.includes(node.id)) keys.push(node.id)
      expandInto(node.children, keys)
    }
  })
}
function handleCollapseAll() {
  defaultExpandedKeys.value = []
  if (!treeRef.value?.store) return
  const nodesMap = treeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => { if (node.expanded) node.expanded = false })
}
function handleToggleExpandAll() {
  if (isAllExpanded.value) handleCollapseAll()
  else handleExpandAll()
  isAllExpanded.value = !isAllExpanded.value
}

async function handleSelectAll() {
  if (!treeRef.value) return
  for (let i = 0; i < 100; i++) {
    if (treeData.value.length > 0) break
    await new Promise(r => setTimeout(r, 200))
  }
  if (treeData.value.length === 0) return
  const allKeys = collectAllKeys(treeData.value)
  guard.enter()
  treeRef.value.setCheckedKeys(allKeys)
  await nextTick(); await nextTick()
  guard.exit()
  emitScopeChange()
}

async function handleClear() {
  guard.enter()
  treeRef.value?.setCheckedKeys([])
  await nextTick(); await nextTick()
  guard.exit()
  emit('scope-change', { orgIds: [], effectiveOrgIds: [] })
}

async function handleRefresh() {
  if (loading.value || refreshing.value) return
  refreshing.value = true
  try { await loadTreeData({ silent: true }) } finally { refreshing.value = false }
}

// ============================================================
//  初始展开 key（仅选中路径，防大组织树卡顿）
// ============================================================
function collectInitialExpandedKeys(nodes, selectedKeys) {
  if (!nodes?.length) return []
  const keys = new Set()
  const selectedSet = new Set((selectedKeys || []).map(String))
  function findPathToRoot(targetId) {
    const path = []
    function walk(n, ancestors) {
      if (String(n.id) === String(targetId)) {
        path.push(...ancestors.map(a => a.id), n.id)
        return true
      }
      if (n.children?.length) {
        for (const c of n.children) {
          if (walk(c, [...ancestors, n])) return true
        }
      }
      return false
    }
    walk({ id: '__root__', children: nodes }, [])
    return path
  }
  selectedSet.forEach(sk => findPathToRoot(sk).forEach(k => keys.add(k)))
  const result = []
  function filterExpandable(n) {
    if (keys.has(n.id) && n.children?.length) result.push(n.id)
    n.children?.forEach(filterExpandable)
  }
  filterExpandable({ id: '__root__', children: nodes })
  return result
}

// ============================================================
//  selectByCode（兼容 MOMP shortcut：code 匹配组织，选择自身及其子孙）
// ============================================================
function findNodeByCode(nodes, code) {
  for (const n of nodes || []) {
    if (n.code === code) return n
    if (n.children?.length) {
      const found = findNodeByCode(n.children, code)
      if (found) return found
    }
  }
  return null
}
function collectDescendantLeafIds(node) {
  const ids = []
  function walk(n) {
    if (!n.children || n.children.length === 0) { ids.push(n.originalId ?? n.id); return }
    n.children.forEach(c => walk(c))
  }
  walk(node)
  return ids
}
async function selectByCode(code) {
  if (!code || !treeRef.value) return false
  for (let i = 0; i < 100; i++) {
    if (treeData.value.length > 0) break
    await new Promise(r => setTimeout(r, 200))
  }
  if (treeData.value.length === 0) return false
  const node = findNodeByCode(treeData.value, code)
  if (!node) return false
  const leafIds = collectDescendantLeafIds(node)
  if (!leafIds.length) return false
  guard.enter()
  treeRef.value.setCheckedKeys(node.children?.length ? leafIds : [node.id])
  await nextTick(); await nextTick()
  guard.exit()
  emitScopeChange()
  return true
}

onMounted(() => { loadTreeData() })

defineExpose({
  clear: handleClear,
  loadTreeData,
  handleSelectAll,
  selectByCode,
  _test: {
    get treeData() { return treeData.value },
    get loading() { return loading.value },
    get nodeCount() { return treeData.value?.length || 0 },
    get checkedKeys() { return treeRef.value?.getCheckedKeys?.() || [] },
    get checkedNodeCount() { return treeRef.value?.getCheckedNodes?.(false, false)?.length || 0 }
  }
})
</script>

<style scoped>
.org-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ost-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.ost-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.ost-toolbar :deep(.el-button) { margin-left: 0 !important; }
.ost-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.ost-toolbar :deep(.el-icon) { margin-right: 2px; }
.ost-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.ost-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.ost-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}
.ost-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.ost-node-code {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.ost-loading,
.ost-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.ost-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>