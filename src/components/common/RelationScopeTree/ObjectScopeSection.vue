<template>
  <div class="oss-root">
    <div v-if="showSearch" class="oss-search">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索业务对象"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="oss-toolbar">
      <AppButton variant="text" size="sm" @click="handleExpandAll">
        <el-icon :size="14"><Expand /></el-icon>
        展开全部
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleCollapseAll">
        <el-icon :size="14"><Fold /></el-icon>
        收起全部
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleSelectAll">
        <el-icon :size="14"><Select /></el-icon>
        全选
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleClear">
        <el-icon :size="14"><CircleClose /></el-icon>
        清空
      </AppButton>
    </div>

    <div class="oss-tree-container">
      <div v-if="loading" class="oss-loading">
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
            @check="handleBoCheck"
          >
        <template #default="{ data }">
          <span class="oss-node">
            <el-icon v-if="getNodeIcon(data)" class="oss-node-icon" :size="14">
              <component :is="getNodeIcon(data)" />
            </el-icon>
            <span class="oss-node-label" data-testid="oss-tree-label" :title="data.name">{{ data.name }}</span>
            <span v-if="data.count > 0" class="oss-node-count">({{ data.count }})</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="oss-empty">
        <el-empty description="暂无数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, onMounted, nextTick, shallowRef } from 'vue'
import { Search, Loading, Folder, FolderOpened, Document, Box, Expand, Fold, Select, CircleClose } from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { useScopeTreeState, treeNodesToScope, scopeToNodeKeys } from '@/composables/useScopeTreeState'
import { createTrace } from '@/utils/trace'
import { createScopeGuard } from '@/composables/scopeGuard'

const USE_FILTERSOURCE = import.meta.env.VITE_FEATURE_SCOPETREE_FILTERSOURCE !== 'false'

const props = defineProps({
  versionId: {
    type: Number,
    required: true
  },
  showSearch: {
    type: Boolean,
    default: true
  },
  initialBoIds: {
    type: Array,
    default: () => []
  },
  scopeIds: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['scope-change', 'load'])

const treeRef = shallowRef(null)
const treeData = shallowRef([])
const loading = ref(false)
const searchQuery = ref('')
const defaultExpandedKeys = shallowRef([])
const treeKey = ref(1)

const metaObject = inject('metaObject', ref(null))

const DEFAULT_HIERARCHY_CONFIG = {
  levels: [
    { object_type: 'domain', children_field: 'sub_domains', icon: 'Folder' },
    { object_type: 'sub_domain', children_field: 'service_modules', icon: 'FolderOpened' },
    { object_type: 'service_module', children_field: 'business_objects', icon: 'Document' },
    { object_type: 'business_object', children_field: null, icon: 'Box' }
  ],
  root_type: 'domain',
  root_filter: 'version_id'
}

const hierarchyConfig = computed(() => {
  return metaObject.value?.hierarchies?.[0] || DEFAULT_HIERARCHY_CONFIG
})

const rootType = computed(() => hierarchyConfig.value.root_type || 'domain')

const iconMap = computed(() => {
  const map = {}
  const levels = hierarchyConfig.value.levels || []
  levels.forEach(level => {
    map[level.object_type] = level.icon || getDefaultIcon(level.object_type)
  })
  return map
})

function getDefaultIcon(type) {
  const defaultIcons = {
    domain: 'Folder',
    sub_domain: 'FolderOpened',
    service_module: 'Document',
    business_object: 'Box'
  }
  return defaultIcons[type] || 'Document'
}

const treeProps = computed(() => ({
  label: 'name',
  children: 'children'
}))

const objectCheckedNodeKeys = computed(() => {
  return scopeToNodeKeys(treeData.value, props.scopeIds)
})

function getNodeIcon(data) {
  if (!data) return null
  const iconName = iconMap.value[data.type]
  const iconComponentMap = {
    Folder,
    FolderOpened,
    Document,
    Box
  }
  return iconComponentMap[iconName] || Document
}

function handleSearch(query) {
  treeRef.value?.filter(query)
}

function filterNodeMethod(value, data) {
  if (!value) return true
  return data.name?.toLowerCase().includes(value.toLowerCase())
}

function handleExpandAll() {
  expandAll(treeData.value, defaultExpandedKeys.value)
  if (!treeRef.value?.store) return
  const nodesMap = treeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.childNodes && node.childNodes.length > 0) {
      node.expanded = true
    }
  })
}

function expandAll(nodes, keys) {
  if (!nodes || !Array.isArray(nodes)) return
  nodes.forEach(node => {
    if (node.children && node.children.length > 0) {
      if (!keys.includes(node.id)) {
        keys.push(node.id)
      }
      expandAll(node.children, keys)
    }
  })
  defaultExpandedKeys.value = [...keys]
}

function handleCollapseAll() {
  defaultExpandedKeys.value = []
  if (!treeRef.value?.store) return
  const nodesMap = treeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.expanded) {
      node.expanded = false
    }
  })
}

function handleSelectAll() {
  if (USE_FILTERSOURCE) {
    const scope = collectAllScope(treeData.value)
    emit('scope-change', scope)
    return
  }

  if (!treeRef.value) return
  const allKeys = collectAllKeys(treeData.value)
  console.log('[ObjectScopeSection] handleSelectAll - allKeys:', allKeys)
  treeRef.value.setCheckedKeys(allKeys)
  emitTypedScopeChange()
}

function collectAllKeys(nodes) {
  const keys = []
  nodes.forEach(node => {
    keys.push(node.id)
    if (node.children && node.children.length > 0) {
      keys.push(...collectAllKeys(node.children))
    }
  })
  return keys
}

function collectAllScope(nodes) {
  const domainIds = []
  const subDomainIds = []
  const serviceModuleIds = []

  function walk(n) {
    for (const node of n) {
      if (node.type === 'domain') domainIds.push(node.originalId || node.id)
      else if (node.type === 'sub_domain') subDomainIds.push(node.originalId || node.id)
      else if (node.type === 'service_module') serviceModuleIds.push(node.originalId || node.id)
      if (node.children?.length) walk(node.children)
    }
  }
  walk(nodes)
  return { boIds: [], domainIds, subDomainIds, serviceModuleIds }
}

function handleClear() {
  if (USE_FILTERSOURCE) {
    emit('scope-change', { boIds: [], domainIds: [], subDomainIds: [], serviceModuleIds: [] })
    return
  }

  treeRef.value?.setCheckedKeys([])
  checkedBoIds.value = []
  emit('scope-change', { boIds: [], domainIds: [], subDomainIds: [], serviceModuleIds: [] })
}

function handleBoCheck(data, checkedInfo) {
  if (USE_FILTERSOURCE) {
    // 防止 watch → setCheckedKeys → @check 循环
    if (guard.active()) return
    const scope = treeNodesToScope(checkedInfo.checkedNodes)
    trace.log('handleBoCheck→emit', { boCount: scope.boIds?.length || 0 })
    emit('scope-change', scope)
    return
  }

  if (guard.active()) return

  console.log('[ObjectScopeSection] handleBoCheck:', {
    clickedNode: { id: data.id, originalId: data.originalId, name: data.name, type: data.type },
    checkedKeys: checkedInfo.checkedKeys,
    halfCheckedKeys: checkedInfo.halfCheckedKeys,
    checkedNodes: checkedInfo.checkedNodes.map(n => ({ id: n.id, originalId: n.data?.originalId, name: n.name, type: n.type })),
    halfCheckedNodes: (checkedInfo.halfCheckedNodes || []).map(n => ({ id: n.id, originalId: n.data?.originalId, name: n.name, type: n.type }))
  })

  const businessObjectNodes = checkedInfo.checkedNodes.filter(node => node.type === 'business_object')
  nextTick(() => {
    checkedBoIds.value = businessObjectNodes.map(node => node.data?.originalId || node.id)
  })

  emitTypedScopeChange()
}

const checkedBoIds = ref([])
const guard = createScopeGuard()
const trace = createTrace('ObjectScopeSection')

// 当 scopeIds 从 [A,B] 变到 [B] 时，需要显式调用 setCheckedKeys 同步树状态
// guard.enter/exit 紧贴 setCheckedKeys，消除 nextTick 窗口期用户点击被忽略的竞态
watch(objectCheckedNodeKeys, (newKeys) => {
  if (!USE_FILTERSOURCE) return
  nextTick(() => {
    if (!treeRef.value) return
    guard.enter()
    treeRef.value.setCheckedKeys(newKeys || [])
    guard.exit()
    trace.log('watch→setCheckedKeys', { keyCount: (newKeys || []).length })
  })
})

function emitTypedScopeChange(_checkedNodes) {
  if (!treeRef.value) {
    console.log('[ObjectScopeSection] emitTypedScopeChange: treeRef is null, skip')
    return
  }

  // 父子联动模式下, 需要合并: 全选节点 (checkedNodes) + 半选节点 (halfCheckedNodes)
  // 因为父节点 domain/sub_domain/service_module 全选时在 checkedNodes, 部分选时在 halfCheckedNodes
  const checkedNodes = treeRef.value.getCheckedNodes?.(false, false) || []
  const halfCheckedNodes = treeRef.value.getHalfCheckedNodes?.() || []

  // 合并并按 id 去重 (父子联动时, 父和子可能都出现)
  const nodeMap = new Map()
  checkedNodes.forEach(node => nodeMap.set(node.id, node))
  halfCheckedNodes.forEach(node => nodeMap.set(node.id, node))
  const allNodes = Array.from(nodeMap.values())

  console.log('[ObjectScopeSection] emitTypedScopeChange:', {
    checkedCount: checkedNodes.length,
    halfCheckedCount: halfCheckedNodes.length,
    allNodesCount: allNodes.length,
    allNodes: allNodes.map(n => ({ id: n.id, originalId: n.data?.originalId, name: n.name, type: n.type }))
  })

  const domainIds = []
  const subDomainIds = []
  const serviceModuleIds = []
  const businessObjectIds = []

  allNodes.forEach(node => {
    const nodeId = node.data?.originalId || node.id
    if (node.type === 'domain') domainIds.push(nodeId)
    else if (node.type === 'sub_domain') subDomainIds.push(nodeId)
    else if (node.type === 'service_module') serviceModuleIds.push(nodeId)
    else if (node.type === 'business_object') businessObjectIds.push(nodeId)
  })

  setTimeout(() => {
    emit('scope-change', {
      boIds: businessObjectIds,
      domainIds,
      subDomainIds,
      serviceModuleIds
    })
  }, 0)
}

async function loadTreeData(options = {}) {
  const { silent = false } = options
  if (!props.versionId) {
    treeData.value = []
    loading.value = false
    return
  }

  if (!silent) loading.value = true
  try {
    const [domainResult, subDomainResult, serviceModuleResult] = await Promise.all([
      boService.query('domain', { version_id: props.versionId, page_size: 1000 }),
      boService.query('sub_domain', { version_id: props.versionId, page_size: 1000 }),
      boService.query('service_module', { version_id: props.versionId, page_size: 5000 })
    ])

    const domains = domainResult.data?.items || domainResult.data || []
    const subDomains = subDomainResult.data?.items || subDomainResult.data || []
    const serviceModules = serviceModuleResult.data?.items || serviceModuleResult.data || []

    // === 修复核心: silent 模式下保留用户已选状态，避免 el-tree store 重建导致 checked 丢失 ===
    // 根因: 上游 watch(combinedFilters) → coordinator.refreshAll() → scopeTree.refresh()
    //       → loadTreeData({ silent: true }) → treeData.value = newArray → el-tree watch(props.data)
    //       → store.setData → 重建所有 Node, checked 状态被重置
    // 
    // 使用 :default-checked-keys 后，store.setData 内部 _initDefaultCheckedNodes() 会自动从 prop 恢复
    // FR-001: 不再需要手动 save/restore
    if (silent && treeRef.value && !USE_FILTERSOURCE) {
      const currentCheckedKeys = treeRef.value.getCheckedKeys?.() || []
      const currentCheckedNodes = treeRef.value.getCheckedNodes?.() || []
      const hasSelection = currentCheckedKeys.length > 0

      if (hasSelection) {
        const oldKeys = collectAllKeys(treeData.value)
        const newTree = buildHierarchyTree(domains, subDomains, serviceModules)
        const newKeys = collectAllKeys(newTree)
        const sameStructure =
          oldKeys.length === newKeys.length &&
          oldKeys.every(k => newKeys.includes(k))

        if (sameStructure) {
          // 树结构未变化, 无需重建 store, 保留用户已选状态
          console.log('[ObjectScopeSection] loadTreeData: silent refresh, structure unchanged, keep selection')
          return
        }

        // 树结构变化 (新增/删除节点), 需要重建但要恢复已选状态
        console.log('[ObjectScopeSection] loadTreeData: silent refresh, structure changed, preserving selection',
          currentCheckedKeys.length, 'keys')
        treeData.value = newTree
        const allKeys = collectAllKeys(newTree)
        defaultExpandedKeys.value = allKeys

        // 等待 el-tree store 重建完成 (多次 nextTick 确保)
        await nextTick()
        await nextTick()
        guard.enter()
        treeRef.value.setCheckedKeys(currentCheckedKeys)
        // 等待 setCheckedKeys 触发的 @check 事件被处理完
        await nextTick()
        await nextTick()
        await nextTick()
        guard.exit()
        return
      }
    }

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    treeData.value = tree

    const allKeys = collectAllKeys(tree)
    defaultExpandedKeys.value = allKeys

    emit('load', treeData.value)
  } catch (error) {
    console.error('[ObjectScopeSection] Failed to load tree:', error)
    treeData.value = []
  } finally {
    if (!silent) loading.value = false
  }

  if (props.initialBoIds?.length) {
    checkedBoIds.value = [...props.initialBoIds]
    guard.enter()
    await nextTick()
    await nextTick()
    treeRef.value?.setCheckedKeys(props.initialBoIds)
    await nextTick()
    guard.exit()
  }
}

function buildHierarchyTree(domains, subDomains, serviceModules) {
  const subDomainMap = new Map()
  const serviceModuleMap = new Map()

  for (const sd of subDomains) {
    const list = subDomainMap.get(sd.domain_id) || []
    list.push(sd)
    subDomainMap.set(sd.domain_id, list)
  }

  for (const sm of serviceModules) {
    const list = serviceModuleMap.get(sm.sub_domain_id) || []
    list.push(sm)
    serviceModuleMap.set(sm.sub_domain_id, list)
  }

  return domains.map(domain => {
    const domainSubDomains = subDomainMap.get(domain.id) || []
    const domainNode = {
      id: `d_${domain.id}`,
      originalId: domain.id,
      name: domain.name,
      code: domain.code,
      type: 'domain',
      count: domainSubDomains.length,
      children: []
    }

    for (const subDomain of domainSubDomains) {
      const moduleList = serviceModuleMap.get(subDomain.id) || []
      const subDomainNode = {
        id: `s_${subDomain.id}`,
        originalId: subDomain.id,
        name: subDomain.name,
        code: subDomain.code,
        type: 'sub_domain',
        count: moduleList.length,
        children: []
      }

      for (const module of moduleList) {
        subDomainNode.children.push({
          id: `sm_${module.id}`,
          originalId: module.id,
          name: module.name,
          code: module.code,
          type: 'service_module',
          count: 0,
          children: []
        })
      }

      domainNode.children.push(subDomainNode)
    }

    return domainNode
  })
}

function getCheckedBoIds() {
  if (USE_FILTERSOURCE) {
    return props.scopeIds?.business_object?.selected?.length > 0
      ? props.scopeIds.business_object.selected
      : (props.scopeIds?.business_object?.effective || [])
  }
  return checkedBoIds.value
}

watch(() => props.versionId, (newVal) => {
  if (newVal) {
    loadTreeData()
  }
}, { immediate: true })

watch(() => props.initialBoIds, async (newBoIds) => {
  if (USE_FILTERSOURCE) return
  console.log('[ObjectScopeSection] Watcher: initialBoIds changed', {
    newBoIds,
    loading: loading.value,
    treeDataLength: treeData.value.length,
    hasTreeRef: !!treeRef.value
  })
  if (loading.value) return
  if (!treeData.value.length) return
  if (!treeRef.value) return
  if (!newBoIds?.length) return
  const currentKeys = treeRef.value.getCheckedKeys?.() || []
  const needsUpdate = newBoIds.length !== currentKeys.length ||
    !newBoIds.every(id => currentKeys.includes(id))
  console.log('[ObjectScopeSection] Watcher: needsUpdate?', {
    currentKeys,
    needsUpdate,
    reason: newBoIds.length !== currentKeys.length ? 'length mismatch' : 'different ids'
  })
  if (!needsUpdate) return
  checkedBoIds.value = [...newBoIds]
  guard.enter()
  await nextTick()
  console.log('[ObjectScopeSection] Watcher: calling setCheckedKeys', newBoIds)
  treeRef.value.setCheckedKeys(newBoIds)
  await nextTick()
  guard.exit()
  console.log('[ObjectScopeSection] Watcher: after setCheckedKeys',
    treeRef.value?.getCheckedKeys?.())
}, { deep: true })

defineExpose({
  getCheckedBoIds,
  clear: handleClear,
  loadTreeData,
  // [TEST-ONLY] 暴露内部状态供 Playwright 测试诊断
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
.oss-root {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.oss-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}

.oss-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
}

.oss-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 2px 4px;
}

.oss-tree-container {
  flex: 1;
  min-height: 150px;
  overflow: auto;
  padding: var(--spacing-xs) 0;
}

.oss-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}

.oss-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}

.oss-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.oss-node-count {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.oss-loading,
.oss-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}

.oss-loading {
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
}

:deep(.el-tree-node__content) {
  height: 32px;
  padding-right: var(--spacing-sm);
}

:deep(.el-tree-node__label) {
  font-size: var(--font-size-sm);
}

:deep(.el-checkbox) {
  margin-right: var(--spacing-sm);
}
</style>
