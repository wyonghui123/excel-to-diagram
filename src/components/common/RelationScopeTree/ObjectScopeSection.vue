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
            @node-expand="onNodeExpand"
            @node-collapse="onNodeCollapse"
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
const isAllExpanded = ref(false)

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
  const allKeys = scopeToNodeKeys(treeData.value, props.scopeIds)
  // [FIX 2026-06-30] 只返回叶子节点 key, 避免 :default-checked-keys 含父节点 key
  //   导致 el-tree 重建时 (loadTreeData silent 模式 sameStructure=false)
  //   在 check-strictly=false 下父节点 checked → 向下级联勾选整个子树
  return collectLeafKeys(allKeys, treeData.value)
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

function handleToggleExpandAll() {
  if (isAllExpanded.value) {
    handleCollapseAll()
  } else {
    handleExpandAll()
  }
  isAllExpanded.value = !isAllExpanded.value
}

function handleSelectAll() {
  if (USE_FILTERSOURCE) {
    const scope = collectAllScope(treeData.value)
    emit('scope-change', scope)
    return
  }

  if (!treeRef.value) return
  const allKeys = collectAllKeys(treeData.value)
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

/**
 * [FIX 2026-06-30] 从 keys 中收集叶子节点 key
 *   - key 对应叶子节点 (无 children): 直接保留
 *   - key 对应父节点 (有 children): 直接跳过 (不保留, 不推导)
 *
 * 用于 setCheckedKeys 前过滤, 避免父节点 key 被 setCheckedKeys 后
 * 在 check-strictly=false 下向下级联勾选整个子树。
 *
 * 为什么不推导父节点的子节点 key?
 *   - 用户勾选叶子节点时, el-tree 向上传播会让父节点 checked, checkedNodes 含父节点,
 *     但父节点 checked 是向上传播的副作用, 不应触发向下级联。
 *     collectLeafKeys 过滤掉父节点 key, setCheckedKeys 只设置叶子, el-tree 自动向上传播
 *     处理父节点三态 (indeterminate/checked), 不会向下级联。
 *   - 用户勾选父节点时, el-tree 内部已向下级联勾选所有子节点, checkedNodes 已含所有子节点,
 *     emit scope 已含所有子节点 id, scopeToNodeKeys 返回所有叶子 key,
 *     collectLeafKeys 保留这些叶子 key, setCheckedKeys 设置所有叶子, 视觉上整个子树 checked。
 *
 * @param {Array<string>} keys - 待过滤的 node key 数组 (可能含父节点 key)
 * @param {Array} nodes - treeData
 * @returns {Array<string>} 只含叶子节点的 key 数组
 */
function collectLeafKeys(keys, nodes) {
  if (!nodes?.length || !keys?.length) return []
  const keySet = new Set(keys)
  const leafKeys = []
  function walk(nodeList) {
    for (const node of nodeList) {
      if (!node.children || node.children.length === 0) {
        if (keySet.has(node.id)) leafKeys.push(node.id)
      } else {
        walk(node.children)
      }
    }
  }
  walk(nodes)
  return leafKeys
}

/**
 * [BUG-V034 修复 2026-06-29] 计算"初始展开 keys":
 *   - 默认情况下, 不展开任何节点 (UX: 大树 1 级节点可能 500+, 全展开会卡)
 *   - 仅展开选中节点的"路径" (从选中节点往上找 parent 直到 root)
 *   - 不展开 bo 叶子节点 (避免 2850 BO 全展开卡顿)
 *
 * @param {Array} nodes - treeData
 * @param {Array} selectedKeys - 当前 el-tree checked keys
 * @returns {Array<string>} initial expanded keys
 */
function collectInitialExpandedKeys(nodes, selectedKeys) {
  if (!nodes?.length) return []

  const keys = new Set()
  const selectedSet = new Set(selectedKeys || [])

  // 选中节点路径: 从选中节点往上找 parent 直到 root, 沿途所有节点都加入
  function findPathToRoot(targetId) {
    const path = []
    function walk(n, ancestors) {
      if (n.id === targetId) {
        path.push(...ancestors.map(a => a.id))
        path.push(n.id)
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
  selectedSet.forEach(sk => {
    findPathToRoot(sk).forEach(k => keys.add(k))
  })

  // 仅保留可展开的节点 (有 children 的父节点)
  const result = []
  function filterExpandable(n) {
    if (keys.has(n.id) && n.children?.length) {
      result.push(n.id)
    }
    n.children?.forEach(filterExpandable)
  }
  filterExpandable({ id: '__root__', children: nodes })

  return result
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

  const businessObjectNodes = checkedInfo.checkedNodes.filter(node => node.type === 'business_object')
  nextTick(() => {
    checkedBoIds.value = businessObjectNodes.map(node => node.data?.originalId || node.id)
  })

  emitTypedScopeChange()
}

const checkedBoIds = ref([])
const guard = createScopeGuard()
const trace = createTrace('ObjectScopeSection')

/**
 * [BUG-V034 v3 修复 2026-06-29] 跨 :data 重建持久化用户展开状态
 * 通过 el-tree @node-expand / @node-collapse 事件持续追踪,
 * installStoreSetDataHook 在 setData 内部读取并恢复展开。
 * 参见 RelationScopeSection.vue 同名实现 (该组件已用同样方案修复 BUG-V034)
 */
const userExpandedKeys = ref(new Set())
function onNodeExpand(data) {
  if (data?.id != null) userExpandedKeys.value.add(String(data.id))
}
function onNodeCollapse(data) {
  if (data?.id != null) userExpandedKeys.value.delete(String(data.id))
}

// 当 scopeIds 从 [A,B] 变到 [B] 时，需要显式调用 setCheckedKeys 同步树状态
// guard.enter/exit 紧贴 setCheckedKeys，消除 nextTick 窗口期用户点击被忽略的竞态
watch(objectCheckedNodeKeys, (newKeys) => {
  if (!USE_FILTERSOURCE) return
  nextTick(async () => {
    if (!treeRef.value) return
    guard.enter()
    // [FIX 2026-06-30] 只 setCheckedKeys 叶子节点, 避免父节点 checked 向下级联勾选整个子树
    //   之前 setCheckedKeys 含父节点 key (如 'd_1'), 在 check-strictly=false 下
    //   父节点 checked → 向下级联 → 整个供应链云子树被勾选
    //   现在只 setCheckedKeys 叶子节点, el-tree 自动向上传播处理父节点状态 (indeterminate/checked)
    //   若 newKeys 含父节点 key, collectLeafKeys 会推导其所有叶子子节点 key
    const leafKeys = collectLeafKeys(newKeys || [], treeData.value)
    treeRef.value.setCheckedKeys(leafKeys)
    trace.log('watch→setCheckedKeys', { leafCount: leafKeys.length, totalKeys: (newKeys || []).length })
    // 等 el-tree 内部把 setCheckedKeys 触发的 @check 事件派发完，再退出保护区
    // (el-tree 的 check emit 是同步的, 但事件监听器可能在微任务中处理; 多 nextTick 保险)
    await nextTick()
    await nextTick()
    guard.exit()
  })
})

/**
 * 安装 el-tree store.setData 钩子，跨 :data 重建恢复用户展开状态。
 *
 * 解决问题 (BUG-V034 v3): 用户手动展开节点后, 任何触发 treeData 重建的操作
 * (silent reload, setCheckedKeys 等) 都会调用 store.setData → 重置 node.expanded → 用户展开丢失。
 *
 * 实现思路：
 * 1) 拦截 store.setData，从旧 store 抓取所有 expanded=true 的节点 key
 * 2) 合并 userExpandedKeys (通过 @node-expand/@node-collapse 跨重建持久化)
 * 3) 调用原 setData 重建 store
 * 4) 在 nextTick 中用 node.expand() 恢复展开 (el-tree 2.15+ 没有 setExpandedKeys)
 */
let storeSetDataHooked = false
function installStoreSetDataHook() {
  if (storeSetDataHooked) return
  if (!treeRef.value?.store) return
  const store = treeRef.value.store
  const origSetData = store.setData.bind(store)
  store.setData = function (newData) {
    // 1) 抓取当前 store 中所有"用户展开过的节点 key"
    const savedExpandedKeys = []
    const oldNodesMap = treeRef.value?.store?.nodesMap
    if (oldNodesMap) {
      for (const [key, node] of Object.entries(oldNodesMap)) {
        if (node.expanded) savedExpandedKeys.push(key)
      }
    }
    // 合并 userExpandedKeys（@node-expand/@node-collapse 跨重建持久化）
    const allSavedExpanded = [...new Set([...savedExpandedKeys, ...userExpandedKeys.value])]

    // 2) 执行原 setData → 重建 store.nodesMap
    const result = origSetData(newData)

    // 3) 收集新树的所有有效 data.id
    const allDataIds = new Set()
    const collectIds = (nodes) => {
      for (const n of (nodes || [])) {
        if (n.id != null) allDataIds.add(String(n.id))
        if (n.children) collectIds(n.children)
      }
    }
    collectIds(newData)

    // 4) 过滤出在新树中仍有效的 keys
    const validExpanded = allSavedExpanded.filter(k => allDataIds.has(String(k)))

    // 5) 在 nextTick 中恢复展开
    if (validExpanded.length > 0) {
      nextTick(() => {
        const newStore = treeRef.value?.store
        if (newStore?.nodesMap) {
          for (const key of validExpanded) {
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

// 一旦 treeRef 可用就安装钩子, 拦截 store.setData 跨数据重建恢复展开状态
watch(treeRef, (val) => {
  if (val) {
    installStoreSetDataHook()
  }
})

function emitTypedScopeChange(_checkedNodes) {
  if (!treeRef.value) {
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
    isAllExpanded.value = false
    return
  }

  if (!silent) loading.value = true
  if (!silent) isAllExpanded.value = false
  try {
    // [BUG-V028 修复 2026-06-29] 不再拉全量 BO 客户端聚合
    // 原因: /api/v2/bo/<type> 受 MAX_USER_PAGE_SIZE=500 限制, V863 实际 2850 BO 被截断为 500,
    //       导致 233/277 (84%) SM count 错显示 0
    // 修复: service_module API 已通过 computation_service._batch_count_children 自动填充 child_count
    //       (见 meta/services/computation_service.py:208), 直接用 sm.child_count 即可
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
    //
    // [FIX 2026-06-30] 去掉 !USE_FILTERSOURCE 条件, 让 sameStructure 短路保护对所有模式生效
    //   之前 USE_FILTERSOURCE=true 时跳过短路保护, 每次勾选都重建 treeData → 树收起
    //   现在结构不变时直接 return, 保留 checked + 展开状态
    if (silent && treeRef.value) {
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
          return
        }

        // 树结构变化 (新增/删除节点), 需要重建但要恢复已选状态
        // [FIX 2026-06-30] guard.enter() 提前到 treeData.value=newTree 之前,
        //   防止 el-tree 重建时 :default-checked-keys 触发 @check 事件,
        //   handleBoCheck 在 guard 之外 emit scope-change 污染 scopeIds
        guard.enter()
        treeData.value = newTree
        // [BUG-V034 修复 2026-06-29] 不再 defaultExpandedKeys = allKeys (全部展开),
        // 改为只展开 root 节点 + 当前已选节点路径, 避免 2850 BO 节点全展开导致的卡顿
        defaultExpandedKeys.value = collectInitialExpandedKeys(newTree, currentCheckedKeys)

        // 等待 el-tree store 重建完成 (多次 nextTick 确保)
        await nextTick()
        await nextTick()
        // [FIX 2026-06-30] 只 setCheckedKeys 叶子节点, 避免父节点 checked 向下级联
        const leafCheckedKeys = collectLeafKeys(currentCheckedKeys, newTree)
        treeRef.value.setCheckedKeys(leafCheckedKeys)
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

    // [BUG-V034 修复 2026-06-29] 首次加载只展开 root + 已选路径, 不展开全部
    defaultExpandedKeys.value = collectInitialExpandedKeys(tree, [])

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
  // [BUG-V028 修复 2026-06-29] 不再拉全量 BO 客户端聚合
  // 原因: /api/v2/bo/business_object 受 MAX_USER_PAGE_SIZE=500 限制, V863 实际 2850 BO 被截断为 500,
  //       导致 233/277 (84%) SM count 错显示 0
  // 修复: service_module API 已通过 computation_service._batch_count_children 自动填充 child_count
  //       (见 meta/services/computation_service.py:208), 直接用 sm.child_count 即可
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
    let domainBoCount = 0
    const subDomainNodes = []

    for (const subDomain of domainSubDomains) {
      const moduleList = serviceModuleMap.get(subDomain.id) || []
      let subDomainBoCount = 0
      const serviceModuleNodes = []

      for (const module of moduleList) {
        // [BUG-V028 修复] 使用 service_module API 自动填充的 child_count (见 yaml service_module.yaml:669)
        // 原实现: boCountBySm.get(module.id) || 0 (受 500 cap 影响, 84% 错显示 0)
        const boCount = module.child_count || 0
        subDomainBoCount += boCount
        serviceModuleNodes.push({
          id: `sm_${module.id}`,
          originalId: module.id,
          name: module.name,
          code: module.code,
          type: 'service_module',
          count: boCount, // v39: 模块内 BO 数量 (从 child_count 计算字段读取)
          children: []
        })
      }

      domainBoCount += subDomainBoCount
      subDomainNodes.push({
        id: `s_${subDomain.id}`,
        originalId: subDomain.id,
        name: subDomain.name,
        code: subDomain.code,
        type: 'sub_domain',
        count: subDomainBoCount, // v39: 子域内 BO 总数
        children: serviceModuleNodes
      })
    }

    return {
      id: `d_${domain.id}`,
      originalId: domain.id,
      name: domain.name,
      code: domain.code,
      type: 'domain',
      count: domainBoCount, // v39: 域内 BO 总数
      children: subDomainNodes
    }
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
  if (loading.value) return
  if (!treeData.value.length) return
  if (!treeRef.value) return
  if (!newBoIds?.length) return
  const currentKeys = treeRef.value.getCheckedKeys?.() || []
  const needsUpdate = newBoIds.length !== currentKeys.length ||
    !newBoIds.every(id => currentKeys.includes(id))
  if (!needsUpdate) return
  checkedBoIds.value = [...newBoIds]
  guard.enter()
  await nextTick()
  treeRef.value.setCheckedKeys(newBoIds)
  await nextTick()
  guard.exit()
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
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}

.oss-toolbar :deep(.el-button) {
  margin-left: 0 !important;
}

.oss-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}

.oss-toolbar :deep(.el-icon) {
  margin-right: 2px;
}

.oss-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}

:deep(.collapsible-panel__content) {
  overflow-x: hidden;
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
