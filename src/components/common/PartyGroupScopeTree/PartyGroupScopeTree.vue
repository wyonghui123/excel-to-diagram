<template>
  <div class="party-group-scope-tree">
    <div v-if="showSearch" class="pgst-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索业务伙伴组（编码/名称）"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="pgst-toolbar">
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

    <div class="pgst-tree-container">
      <div v-if="loading" class="pgst-loading">
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
          <span class="pgst-node">
            <el-icon class="pgst-node-icon" :size="14"><FolderOpened /></el-icon>
            <span class="pgst-node-label" :title="data.name">{{ data.name }}</span>
            <span v-if="data.code" class="pgst-node-code">{{ data.code }}</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="pgst-empty">
        <el-empty description="暂无业务伙伴组数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * PartyGroupScopeTree — 业务伙伴组范围树（MOMP 注入的 scope 树组件，供业务伙伴管理页使用）
 *
 * 契约与 OrgScopeTree / ItemGroupScopeTree 一致，MOMP 侧无需特殊处理：
 *   - props.scopeIds: MOMP 传入 page.scopeIds，读 scopeIds['party_group'] = {selected, effective}
 *     （'party_group' 本身就是 PartyManagement 的 objectTypes 成员, 是合法键）
 *   - emit 'scope-change': { partyGroupIds, effectivePartyGroupIds }
 *   - expose clear / handleSelectAll（兼容 MOMP scopeTreeRef 调用）
 *
 * 与 ItemGroupScopeTree 的差异仅在对象与键名（party_group + 业务伙伴组文案）：
 *   party_group 同样是 parent_id 自引用的纯层级分类，量级小（单次 page_size=500
 *   足够），不搬 OrgScopeTree 的循环分页与展开态持久化 hook（理由同 ItemGroupScopeTree）。
 *
 * [注明] 本项目左树勾选到"过滤业务伙伴"是两段桥接 —— party 不直挂 group，
 *   分组关系在关系层 party_relations.group_id（伙伴侧 party2_id）。桥接查询在
 *   PartyManagement.vue 的 watcher 内执行，本组件只负责 emit 勾选集合。
 */
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import { Search, Loading, Expand, Fold, Select, CircleClose, RefreshRight, FolderOpened } from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { createScopeGuard } from '@/composables/scopeGuard'

const props = defineProps({
  showSearch: { type: Boolean, default: true },
  // scopeIds 由 MOMP 传入, 结构 scopeIds['party_group'] = { selected, effective }
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
//  数据加载：扁平 party_group → parent_id 组装树
// ============================================================
async function loadTreeData() {
  loading.value = true
  try {
    const result = await boService.query('party_group', { page_size: 500 })
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
    console.error('[PartyGroupScopeTree] Failed to load party_group tree:', error)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

function buildTree(items) {
  const byId = new Map()
  items.forEach(g => byId.set(g.id, {
    id: g.id,
    originalId: g.id,
    name: g.name,
    code: g.code,
    parentId: g.parent_id,
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
//  scope 计算：{ partyGroupIds, effectivePartyGroupIds }
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
    partyGroupIds: checkedIds,
    effectivePartyGroupIds: [...effective]
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
  // 键与 PartyManagement 的 scopeAdapter 写入键对齐 (scopeIds['party_group'])。
  const scope = props.scopeIds?.['party_group']
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
      // 有子节点且自身或其父被选中 → 展开，避免深树默认全折叠时看不到选中项
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
  emit('scope-change', { partyGroupIds: [], effectivePartyGroupIds: [] })
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
.party-group-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.pgst-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.pgst-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.pgst-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.pgst-toolbar :deep(.el-icon) { margin-right: 2px; }
.pgst-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.pgst-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.pgst-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}
.pgst-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.pgst-node-code {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.pgst-loading,
.pgst-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.pgst-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>