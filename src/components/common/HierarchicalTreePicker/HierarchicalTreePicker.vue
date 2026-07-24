<template>
  <div class="htp-root">
    <!-- 顶栏搜索 -->
    <div v-if="showSearch" class="htp-search">
      <el-input
        v-model="searchQuery"
        :placeholder="`输入名称或编码搜索${totalCount ? `（共 ${totalCount} 条）` : ''}`"
        clearable
        size="default"
        @update:model-value="onSearchInput"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </div>

    <!-- 工具栏 -->
    <div v-if="showToolbar && multiple" class="htp-toolbar">
      <el-button text size="small" @click="toggleExpandAll">
        <el-icon><component :is="allExpanded ? Fold : Expand" /></el-icon>
        {{ allExpanded ? '收起' : '展开' }}
      </el-button>
      <el-button text size="small" :disabled="checkedIds.length === 0" @click="handleClear">清除</el-button>
      <el-button text size="small" :disabled="loading" @click="loadTreeData">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 树主体 (R3: 全部叶子平铺, 无父子层级) -->
    <div class="htp-tree-container">
      <div v-if="loading" class="htp-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <el-tree
        v-else-if="displayTreeData.length > 0"
        ref="treeRef"
        :data="displayTreeData"
        :props="extendedTreeProps"
        node-key="__tk"
        :show-checkbox="multiple"
        check-strictly
        :check-on-click-node="false"
        :highlight-current="true"
        :current-node-key="!multiple ? String(currentId || '') : undefined"
        :default-checked-keys="multiple ? initialCheckedKeys : undefined"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        @check="onCheckMultiple"
        @node-click="onNodeClickSingle"
      >
        <template #default="{ data }">
          <span :class="['htp-node', { 'htp-node-disabled': isExcludedNode(data) }]">
            <el-icon v-if="resolveIcon(data.icon)" :size="14">
              <component :is="resolveIcon(data.icon)" />
            </el-icon>
            <span class="htp-node-label" :title="data.name">{{ data.name }}</span>
            <span v-if="data.code" class="htp-node-code">{{ data.code }}</span>
            <el-tag v-if="isExcludedNode(data)" size="small" type="info" class="htp-node-tag">
              已选
            </el-tag>
          </span>
        </template>
      </el-tree>
      <div v-else class="htp-empty">
        <el-empty :description="searchQuery ? '无匹配数据' : '暂无数据'" :image-size="60" />
      </div>
    </div>

    <!-- 多选：已选 chips 区 -->
    <div v-if="multiple && showSelectedChips" class="htp-selected-bar">
      <span class="htp-selected-label">已选 ({{ checkedIds.length }}):</span>
      <div class="htp-chips">
        <el-tag
          v-for="id in checkedIds"
          :key="id"
          closable
          size="small"
          @close="removeChecked(id)"
        >
          {{ getNodeNameById(id) }}
        </el-tag>
        <span v-if="checkedIds.length === 0" class="htp-chips-empty">无</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * [FIX 2026-07-22] 层级值帮助 picker
 * [REFACTOR 2026-07-22] 元数据驱动: hierarchy_meta 从 API 响应读
 * [UX-FIX 2026-07-23] 6 项交互修复
 * [UX-FIX 2026-07-23-R2] 进一步修复: prune 父节点 + footer 单一路径
 * [UX-FIX 2026-07-23-R3] 用户实际期望: 选 sub_domain 时父/祖全不展示
 *   - displayTreeData 改为: 全部叶子平铺, label 用 data.name (不显示路径)
 * [UX-FIX 2026-07-23-R4] 进一步: 过滤掉已选叶子 (不展示, 不只是 disabled)
 *   顶部 code 字段单独显示 (如 "TEST15" / "TEST1212") 提供辨识
 *   - 不再保留任何父节点
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { Search, Loading, Fold, Expand, Refresh } from '@element-plus/icons-vue'
import { resolveIcon } from './iconMap'

const props = defineProps({
  dimensionId: { type: String, required: true },
  checkedIds: { type: [Array, Number], default: () => [] },
  excludeIds: { type: Array, default: () => [] },
  multiple: { type: Boolean, default: true },
  showSearch: { type: Boolean, default: true },
  showToolbar: { type: Boolean, default: true },
  showSelectedChips: { type: Boolean, default: false },
  onlyLeafSelectable: { type: Boolean, default: true },
  filterParams: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['confirm', 'cancel', 'check-change'])

// ── 状态 ──
const treeRef = ref(null)
const treeData = ref([])  // 原始后端数据 (含所有 4 层)
// [UX-FIX 2026-07-23-R3] 实际渲染数据: 全部叶子平铺 (无任何父节点)
// [UX-FIX 2026-07-23-R4] 进一步: 过滤掉已选叶子 (不展示, 不只是 disabled)
// [UX-FIX 2026-07-23-R7] 业务角度: 保留树形态, 递归剪掉"无 sub_domain 后代"的整枝
//   用户原始例子:
//     产品1
//       版本v1
//         领域a
//           子领域1
//           子领域2
//         领域b          ← 剪掉 (无 sub_domain)
//     产品2
//       版本v2
//         领域c        ← 剪掉 (无 sub_domain)
//   应展示:
//     产品1
//       版本v1
//         领域a
//           子领域1
//           子领域2
//   业务逻辑:
//     - 保留树形态 (用户要求"需要树")
//     - 递归: 节点有 sub_domain 后代 → 保留; 没 → 剪掉整枝
//     - 已选叶子: 从树中过滤掉 (R4)
// [FIX 2026-07-23-R13] 通用剪枝: 末端节点类型由 dimensionId 决定
//   product → 末端是 product, domain → 末端是 domain, sub_domain → 末端是 sub_domain
const displayTreeData = computed(() => {
  if (!props.onlyLeafSelectable) return treeData.value
  const excluded = allExcludedIds.value
  const targetDim = props.dimensionId
  function pruneToTargetLeaves(nodes) {
    const result = []
    for (const n of nodes) {
      if (!n.children || n.children.length === 0) {
        // 末端叶子: 仅保留目标维度类型 (由 dimensionId 决定)
        if (n.type === targetDim && !excluded.has(n.id)) {
          result.push({ ...n, children: [] })
        }
      } else {
        // 父节点: 递归
        const pruned = pruneToTargetLeaves(n.children)
        if (pruned.length > 0) {
          result.push({ ...n, children: pruned })
        }
      }
    }
    return result
  }
  return pruneToTargetLeaves(treeData.value)
})
const loading = ref(false)
const totalCount = ref(0)
const searchQuery = ref('')
const hierarchyMeta = ref({ root_type: null, levels: [], ui_config: {} })
const debouncedSearch = ref('')
const checkedIds = ref([])
const currentId = ref(null)
const defaultExpandedKeys = ref([])
const allExpanded = ref(false)

const treeProps = { label: 'name', children: 'children' }
const extendedTreeProps = computed(() => ({
  ...treeProps,
  disabled: (data) => isDisabledNode(data),
}))

const tkByTypeId = ref(new Map())
function buildTkIndex(roots) {
  const m = new Map()
  function walk(nodes) {
    for (const n of nodes) {
      m.set(`${n.type}:${n.id}`, n.__tk)
      if (n.children) walk(n.children)
    }
  }
  walk(roots)
  tkByTypeId.value = m
}

const allExcludedIds = computed(() => {
  const set = new Set()
  if (Array.isArray(props.excludeIds)) {
    props.excludeIds.forEach(id => set.add(id))
  }
  if (Array.isArray(props.checkedIds)) {
    props.checkedIds.forEach(id => set.add(id))
  } else if (props.checkedIds != null) {
    set.add(props.checkedIds)
  }
  return set
})

function isExcludedNode(data) {
  return allExcludedIds.value.has(data.id)
}

function isDisabledNode(data) {
  if (isExcludedNode(data)) return true
  if (props.onlyLeafSelectable && !isLeaf(data)) return true
  return false
}

function isLeaf(data) {
  return !data.children || data.children.length === 0
}

// [R19-FIX-v2] initialCheckedKeys 必须经过剪枝过滤, 否则被剪枝掉的已选节点
//   会让 setCheckedKeys 静默失败, 后续 validIds 计算错误
const initialCheckedKeys = computed(() => {
  if (!props.checkedIds) return []
  const ids = Array.isArray(props.checkedIds) ? props.checkedIds : [props.checkedIds]
  const allTks = ids.map(id => tkByTypeId.value.get(`${props.dimensionId}:${id}`)).filter(Boolean)
  // 过滤掉不在 displayTreeData (剪枝后) 中的 __tk
  const byTk = new Map()
  function walk(nodes) {
    for (const n of nodes) {
      byTk.set(n.__tk, n)
      if (n.children) walk(n.children)
    }
  }
  walk(displayTreeData.value)
  return allTks.filter(tk => byTk.has(tk))
})

const canConfirm = computed(() => {
  if (props.multiple) return checkedIds.value.length > 0
  return currentId.value != null
})

// ── 扁平数组 → 嵌套树 ──
let __tkCounter = 0
function nextTk() { return `tk_${++__tkCounter}` }

function buildNestedTree(flat, targetDim) {
  const nodes = flat.map(n => ({ ...n, __tk: nextTk(), children: [] }))
  const byUnique = new Map(nodes.map(n => [n.unique_key, n]))
  const roots = []

  // [FIX 2026-07-24-R18] 丢弃孤儿节点 + 严格根节点类型检查
  //   原因: 后端可能返回 parent_unique_key=null 的非 product 节点 (孤儿)
  //   旧逻辑 R14v2: parent_unique_key=null → 放到 roots (错误! 让 sub_domain "供应链云" 出现在顶级)
  //   新逻辑 R18:
  //     1. parent_unique_key=null 且 type='product' → 根节点 (正确)
  //     2. parent_unique_key=null 且 type!='product' → 孤儿, 丢弃
  //     3. parent_unique_key!=null 但 parent 不在列表中 → 孤儿, 丢弃
  //   效果: 顶级只剩 product, 不会出现 "供应链云" 等子节点
  const rootType = 'product'  // 层级链的根节点类型
  let orphanCount = 0
  let nonProductRootCount = 0
  for (const node of nodes) {
    if (node.parent_unique_key == null) {
      // 仅 product 可以是根节点; 其他类型 (sub_domain/domain/version) 的 null parent = 孤儿
      if (node.type === rootType) {
        roots.push(node)
      } else {
        nonProductRootCount++
        // 非 product 类型且 parent_unique_key=null → 丢弃 (孤儿)
      }
    } else {
      const parent = byUnique.get(node.parent_unique_key)
      if (parent) {
        parent.children.push(node)
      } else {
        orphanCount++
      }
      // 孤儿节点 (parent 不在列表中) → 直接丢弃
    }
  }
  // [DEBUG R18] 验证修复效果 (验证后删除)
  console.log('[R18-DEBUG]', {
    targetDim,
    flatCount: flat.length,
    nodesCount: nodes.length,
    rootsCount: roots.length,
    orphanCount,
    nonProductRootCount,
    rootTypes: roots.map(r => r.type),
    rootNames: roots.slice(0, 5).map(r => ({ name: r.name, type: r.type })),
  })
  return roots
}

// [UX-FIX 2026-07-23-R7] 收集所有 __tk (用于默认展开所有 group)
function collectAllKeys(nodes) {
  const result = []
  function walk(arr) {
    for (const n of arr) {
      result.push(n.__tk)
      if (n.children) walk(n.children)
    }
  }
  walk(nodes)
  return result
}

// ── 数据加载 ──
async function loadTreeData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (debouncedSearch.value) params.set('search', debouncedSearch.value)
    if (props.filterParams.version_id) {
      params.set('version_id', String(props.filterParams.version_id))
    }
    const url = `/api/v2/bo/management_dimension/${props.dimensionId}/tree?${params}`
    const resp = await fetch(url, { credentials: 'include' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const json = await resp.json()
    treeData.value = buildNestedTree(json.data || [], props.dimensionId)
    buildTkIndex(treeData.value)
    totalCount.value = json.total || 0
    if (json.hierarchy_meta) {
      hierarchyMeta.value = json.hierarchy_meta
    }
    // [UX-FIX 2026-07-24-R20] 默认仅展开根节点 (渐进披露, 非全展开)
    //   旧: collectAllKeys → 全展开 (大数据量时 DOM 卡顿, 用户视线跳跃)
    //   新: 只收集根节点 __tk → 仅展开第一级
    defaultExpandedKeys.value = displayTreeData.value.map(n => n.__tk)
  } catch (e) {
    console.error('[HierarchicalTreePicker] load failed:', e)
    treeData.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
  }
  // [R20] 默认展开行为: 搜索时全展开, 非搜索时仅展开根节点
  //   搜索后全展开: 用户搜索时期望快速看到匹配结果, 不需要手动逐级展开
  //   非搜索仅展开根: 遵循渐进披露, 避免大数据量 DOM 卡顿
  await nextTick()
  if (debouncedSearch.value) {
    expandAllNodes(displayTreeData.value)
  } else {
    expandRootNodesOnly(displayTreeData.value)
  }
  // [FIX R19] 数据重新加载后, 重新设置 checked 并同步父组件 internalSelectedItems
  //   原因: 第二次打开弹窗时 onMounted 不会再触发, 需在此处重新回显勾选
  await nextTick()
  syncCheckedState()
}

// [R19-FIX-v2] 同步 checked 状态: 用 displayTreeData (剪枝后) 建索引
//   真正修复"按钮显示确定(N)但树无勾选"问题
//   原因: 已选节点(如"供应链计划")被 displayTreeData 剪枝过滤掉, 但 validIds
//         仍使用 treeData.value 的索引, 返回已过滤的 id, 导致按钮误显示计数
//   方案: byTk 从 displayTreeData 建立, 过滤掉不在其中的 __tk
function syncCheckedState() {
  if (!props.multiple) return

  // [关键] 从 displayTreeData (剪枝后) 建索引 - 这是用户实际看到的树
  const byTk = new Map()
  function walk(nodes) {
    for (const n of nodes) {
      byTk.set(n.__tk, n)
      if (n.children) walk(n.children)
    }
  }
  walk(displayTreeData.value)

  // 过滤掉不在 displayTreeData 中的 __tk (被剪枝掉的已选节点)
  const validTks = (initialCheckedKeys.value || []).filter(tk => byTk.has(tk))
  treeRef.value?.setCheckedKeys(validTks, false)

  // validIds 只来自 displayTreeData, 确保按钮计数 = 树可见勾选数
  const validIds = validTks
    .map(tk => byTk.get(tk)?.id)
    .filter(id => id != null)
  checkedIds.value = validIds

  // 主动 emit check-change, 同步父组件 internalSelectedItems
  const emitNodes = validIds.map(id => {
    const tk = tkByTypeId.value.get(`${props.dimensionId}:${id}`)
    return byTk.get(tk) || { id, name: `#${id}`, type: '' }
  })
  emit('check-change', { ids: validIds, nodes: emitNodes })
}

// [R20] 仅展开根节点 (渐进披露, 非全展开)
function expandRootNodesOnly(nodes) {
  if (!treeRef.value || !nodes || nodes.length === 0) return
  for (const n of nodes) {
    const treeNode = treeRef.value.getNode(n.__tk)
    if (treeNode && n.children && n.children.length > 0) {
      treeNode.expanded = true
    }
    // 不递归子节点
  }
}

// [R19] 主动展开所有节点 (用于搜索后自动展开)
function expandAllNodes(nodes) {
  if (!treeRef.value || !nodes || nodes.length === 0) return
  for (const n of nodes) {
    const treeNode = treeRef.value.getNode(n.__tk)
    if (treeNode && n.children && n.children.length > 0) {
      treeNode.expanded = true
    }
    if (n.children) expandAllNodes(n.children)
  }
}

// ── 搜索防抖 ──
let searchTimer
function onSearchInput(val) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = val }, 300)
}

watch(debouncedSearch, async (val) => {
  await loadTreeData()
})

function filterNodeMethod(value, data) {
  if (!value) return true
  return (data.name || '').toLowerCase().includes(value.toLowerCase())
}

// ── 多选事件 ──
function onCheckMultiple(checkedInfo) {
  // [UX-FIX 2026-07-23-R3] 优先用 treeRef.getCheckedKeys() (el-tree 官方 API, 跨版本)
  // 失败时回退到 checkedInfo 解析
  const byTk = new Map()
  function walk(nodes) {
    for (const n of nodes) {
      byTk.set(n.__tk, n)
      if (n.children) walk(n.children)
    }
  }
  walk(displayTreeData.value)

  // 1) 官方 API (跨版本稳)
  let checkedTks = []
  if (treeRef.value && typeof treeRef.value.getCheckedKeys === 'function') {
    checkedTks = treeRef.value.getCheckedKeys() || []
  } else if (Array.isArray(checkedInfo)) {
    checkedTks = checkedInfo.map(n => n?.__tk).filter(Boolean)
  } else if (checkedInfo) {
    checkedTks = [
      ...(checkedInfo.checkedKeys || []),
      ...(checkedInfo.halfCheckedKeys || []),
    ]
  }

  const ids = checkedTks.map(tk => byTk.get(tk)?.id).filter(id => id != null)
  const filteredIds = ids.filter(id => !allExcludedIds.value.has(id))
  checkedIds.value = filteredIds

  // 同步 emit 完整 nodes (SearchHelpDialog 用)
  const emitNodes = filteredIds.map(id => {
    const tk = tkByTypeId.value.get(`${props.dimensionId}:${id}`)
    return byTk.get(tk) || { id, name: `#${id}`, type: '' }
  })
  emit('check-change', { ids: checkedIds.value, nodes: emitNodes })
}

// ── 单选事件 ──
function onNodeClickSingle(node) {
  if (!node) return
  if (isDisabledNode(node)) return
  if (currentId.value === node.id) {
    currentId.value = null
  } else {
    currentId.value = node.id
  }
}

function removeChecked(id) {
  checkedIds.value = checkedIds.value.filter(x => x !== id)
  nextTick(() => {
    const tks = checkedIds.value
      .map(i => tkByTypeId.value.get(`${props.dimensionId}:${i}`))
      .filter(Boolean)
    treeRef.value?.setCheckedKeys(tks, false)
  })
}

// [UX-FIX 2026-07-23] 真正控制当前展开/收起 (R3: 叶子无 children, 此函数基本无效)
function toggleExpandAll() {
  allExpanded.value = !allExpanded.value
  if (treeRef.value) {
    function setExpanded(nodes) {
      for (const n of nodes) {
        const node = treeRef.value.getNode(n.__tk)
        if (node) {
          node.expanded = allExpanded.value
        }
        if (n.children) setExpanded(n.children)
      }
    }
    setExpanded(displayTreeData.value)
  }
}

function handleClear() {
  checkedIds.value = []
  if (props.multiple) {
    nextTick(() => treeRef.value?.setCheckedKeys([], false))
  } else {
    currentId.value = null
  }
}

function findNodeById(id) {
  function walk(nodes) {
    for (const n of nodes) {
      if (n.id === id) return n
      if (n.children) {
        const r = walk(n.children)
        if (r) return r
      }
    }
    return null
  }
  return walk(treeData.value)
}

function buildAncestorPath(nodeId) {
  const node = findNodeById(nodeId)
  if (!node) return ''
  const byId = new Map()
  function index(arr) {
    for (const n of arr) {
      byId.set(n.id, n)
      if (n.children) index(n.children)
    }
  }
  index(treeData.value)

  const parts = []
  let cur = node
  while (cur) {
    parts.unshift(cur.name)
    if (cur.parent_id == null) break
    cur = byId.get(cur.parent_id)
  }
  return parts.join(' > ')
}

function getNodeNameById(id) {
  const node = findNodeById(id)
  if (!node) return `#${id}`
  return buildAncestorPath(id) || node.name
}

function confirm() {
  if (props.multiple) {
    const ids = [...checkedIds.value]
    const nodes = ids.map(id => {
      const n = findNodeById(id) || { id, name: `#${id}`, type: '' }
      return { id: n.id, name: n.name, type: n.type, ancestorPath: buildAncestorPath(id) }
    })
    emit('confirm', { type: 'multiple', ids, nodes })
  } else {
    const node = findNodeById(currentId.value)
    emit('confirm', {
      type: 'single',
      id: currentId.value,
      node: node ? {
        id: node.id,
        name: node.name,
        type: node.type,
        ancestorPath: buildAncestorPath(node.id),
      } : { id: currentId.value, name: '', type: '' },
    })
  }
}

function cancel() {
  emit('cancel')
}

// [FIX 2026-07-24-R19] 暴露 loadTreeData: 让父组件 (SearchHelpDialog) 在弹窗打开时主动重载
defineExpose({ confirm, cancel, getCheckedIds: () => [...checkedIds.value], loadTreeData })

// ── 生命周期 ──
onMounted(async () => {
  // loadTreeData 内部已调用 syncCheckedState (多选模式回显勾选 + emit check-change)
  await loadTreeData()
  // 单选模式: 设置 currentId (loadTreeData 的 syncCheckedState 只处理多选)
  if (props.checkedIds && !props.multiple) {
    currentId.value = Array.isArray(props.checkedIds)
      ? props.checkedIds[0]
      : props.checkedIds
  }
})
</script>

<style scoped>
.htp-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 400px;
}
.htp-search { flex: 0 0 auto; }
.htp-toolbar {
  display: flex;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.htp-tree-container {
  flex: 1 1 auto;
  min-height: 300px;
  max-height: 480px;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}
.htp-loading,
.htp-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 8px;
  color: var(--el-text-color-secondary);
}
.htp-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.htp-node-disabled {
  color: var(--el-text-color-placeholder);
  cursor: not-allowed;
}
.htp-node-label { font-size: 13px; }
.htp-node-code {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-family: monospace;
  margin-left: 6px;
  opacity: 0.7;
}
.htp-node-tag {
  margin-left: 6px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 11px;
}
:deep(.el-tree-node.is-disabled .el-tree-node__content) {
  cursor: not-allowed;
  color: var(--el-text-color-placeholder);
}
:deep(.el-tree-node.is-disabled .el-checkbox) {
  cursor: not-allowed;
}
.htp-selected-bar {
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  min-height: 40px;
}
.htp-selected-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}
.htp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.htp-chips-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
