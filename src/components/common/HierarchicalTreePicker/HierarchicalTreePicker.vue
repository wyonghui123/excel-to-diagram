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

    <!-- 工具栏 (仅多选显示全选/清空) -->
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

    <!-- 树主体 -->
    <div class="htp-tree-container">
      <div v-if="loading" class="htp-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <el-tree
        v-else-if="treeData.length > 0"
        ref="treeRef"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        :show-checkbox="multiple"
        check-strictly
        check-on-click-node
        :highlight-current="true"
        :current-node-key="!multiple ? String(currentId || '') : undefined"
        :default-expanded-keys="defaultExpandedKeys"
        :default-checked-keys="multiple ? initialCheckedKeys : undefined"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        @check="onCheckMultiple"
        @node-click="onNodeClickSingle"
      >
        <template #default="{ data }">
          <span class="htp-node">
            <el-icon v-if="getNodeIcon(data.type)" :size="14">
              <component :is="getNodeIcon(data.type)" />
            </el-icon>
            <span class="htp-node-label" :title="data.name">{{ data.name }}</span>
            <span v-if="showCount && data.child_count > 0" class="htp-node-count">
              ({{ data.child_count }})
            </span>
          </span>
        </template>
      </el-tree>
      <div v-else class="htp-empty">
        <el-empty :description="searchQuery ? '无匹配数据' : '暂无数据'" :image-size="60" />
      </div>
    </div>

    <!-- 多选：已选 chips 区 -->
    <div v-if="multiple" class="htp-selected-bar">
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

    <!-- 底部按钮 -->
    <div class="htp-actions">
      <el-button @click="handleCancel">取消</el-button>
      <el-button v-if="multiple" :disabled="checkedIds.length === 0" @click="handleClear">清除</el-button>
      <el-button type="primary" :disabled="!canConfirm" @click="handleConfirm">
        确定{{ multiple ? ` (${checkedIds.length})` : '' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * [FIX 2026-07-22] 层级值帮助 picker
 *
 * 单选/多选通用, 通过 multiple prop 切换:
 *   - multiple=true:  checkbox + chips + 确定(N)
 *   - multiple=false: click 选中 + 高亮 + 确定
 *
 * 数据源: /api/v2/bo/management_dimension/<dimensionId>/tree
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { Search, Loading, Fold, Expand, Refresh } from '@element-plus/icons-vue'
import { getNodeIcon } from './iconMap'

const props = defineProps({
  // 必填: 维度 ID
  dimensionId: { type: String, required: true },

  // 可选: 层级配置 (用于在 missing 时给 warning)
  hierarchyConfig: { type: Object, default: null },

  // 已有选中 (编辑态回填):
  //   - 多选: number[]
  //   - 单选: number | null
  checkedIds: { type: [Array, Number], default: () => [] },

  // 单选/多选
  multiple: { type: Boolean, default: true },

  // 节点右侧显示 child_count 标注
  showCount: { type: Boolean, default: true },

  // 顶栏搜索框
  showSearch: { type: Boolean, default: true },

  // 工具栏
  showToolbar: { type: Boolean, default: true },

  // 父级 filter (如 dim=domain 时 version_id=5)
  filterParams: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['confirm', 'cancel', 'check-change'])

// ── 警告缺失 hierarchyConfig ──
if (!props.hierarchyConfig) {
  console.warn('[HierarchicalTreePicker] hierarchyConfig is required')
}

// ── State ──
const treeRef = ref(null)
const treeData = ref([])
const loading = ref(false)
const totalCount = ref(0)
const searchQuery = ref('')
const debouncedSearch = ref('')
const checkedIds = ref([])
const currentId = ref(null)
const defaultExpandedKeys = ref([])
const allExpanded = ref(false)

const treeProps = { label: 'name', children: 'children' }

const initialCheckedKeys = computed(() => {
  if (!props.checkedIds) return []
  return Array.isArray(props.checkedIds)
    ? props.checkedIds.map(String)
    : [String(props.checkedIds)]
})

const canConfirm = computed(() => {
  if (props.multiple) return checkedIds.value.length > 0
  return currentId.value != null
})

// ── 扁平数组 → 嵌套树 ──
function buildNestedTree(flat) {
  const byId = new Map()
  const roots = []
  for (const n of flat) byId.set(n.id, { ...n, children: [] })
  for (const n of flat) {
    const node = byId.get(n.id)
    if (n.parent_id == null) {
      roots.push(node)
    } else {
      const parent = byId.get(n.parent_id)
      if (parent) parent.children.push(node)
      // dangling parent 忽略 (不会出现)
    }
  }
  return roots
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
    treeData.value = buildNestedTree(json.data || [])
    totalCount.value = json.total || 0
  } catch (e) {
    console.error('[HierarchicalTreePicker] load failed:', e)
    treeData.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
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
  if (val) {
    const matchedIds = collectMatchedIds(val)
    defaultExpandedKeys.value = collectParentKeys(matchedIds)
  } else {
    defaultExpandedKeys.value = []
  }
})

function collectMatchedIds(query) {
  const q = query.toLowerCase()
  const result = []
  function walk(nodes) {
    for (const n of nodes) {
      if ((n.name || '').toLowerCase().includes(q) || (n.code || '').toLowerCase().includes(q)) {
        result.push(n.id)
      }
      if (n.children) walk(n.children)
    }
  }
  walk(treeData.value)
  return result
}

function collectParentKeys(matchedIds) {
  const byId = new Map()
  function index(nodes) {
    for (const n of nodes) {
      byId.set(n.id, n)
      if (n.children) index(n.children)
    }
  }
  index(treeData.value)

  const result = new Set()
  for (const id of matchedIds) {
    let cur = byId.get(id)
    while (cur) {
      result.add(String(cur.id))
      if (cur.parent_id == null) break
      cur = byId.get(cur.parent_id)
    }
  }
  return [...result]
}

function filterNodeMethod(value, data) {
  if (!value) return true
  return (data.name || '').toLowerCase().includes(value.toLowerCase())
}

// ── 多选事件 ──
function onCheckMultiple(checkedInfo) {
  const allChecked = [
    ...(checkedInfo.checkedKeys || []),
    ...(checkedInfo.halfCheckedKeys || []),
  ].map(k => Number(k))
  checkedIds.value = allChecked
  emit('check-change', { ids: checkedIds.value, nodes: checkedInfo.checkedNodes || [] })
}

// ── 单选事件 ──
function onNodeClickSingle(node) {
  if (!node) return
  if (currentId.value === node.id) {
    currentId.value = null
  } else {
    currentId.value = node.id
  }
}

// ── chips 移除 ──
function removeChecked(id) {
  checkedIds.value = checkedIds.value.filter(x => x !== id)
  nextTick(() => {
    treeRef.value?.setCheckedKeys(checkedIds.value.map(String), false)
  })
}

// ── 工具栏 ──
function toggleExpandAll() {
  allExpanded.value = !allExpanded.value
  if (allExpanded.value) {
    defaultExpandedKeys.value = collectAllIds(treeData.value).map(String)
  } else {
    defaultExpandedKeys.value = []
  }
}

function collectAllIds(nodes) {
  const result = []
  function walk(arr) {
    for (const n of arr) {
      result.push(n.id)
      if (n.children) walk(n.children)
    }
  }
  walk(nodes)
  return result
}

function handleClear() {
  checkedIds.value = []
  if (props.multiple) {
    nextTick(() => treeRef.value?.setCheckedKeys([], false))
  } else {
    currentId.value = null
  }
}

// ── 工具: 通过 id 找树节点 ──
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

// ── confirm / cancel ──
function handleConfirm() {
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

function handleCancel() {
  emit('cancel')
}

// ── 生命周期 ──
onMounted(async () => {
  await loadTreeData()
  if (props.checkedIds) {
    if (props.multiple) {
      await nextTick()
      treeRef.value?.setCheckedKeys(initialCheckedKeys.value, false)
      checkedIds.value = initialCheckedKeys.value.map(Number)
    } else {
      currentId.value = Array.isArray(props.checkedIds)
        ? props.checkedIds[0]
        : props.checkedIds
    }
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
.htp-node-label { font-size: 13px; }
.htp-node-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 4px;
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
.htp-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>