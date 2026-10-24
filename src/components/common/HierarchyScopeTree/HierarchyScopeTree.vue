<template>
  <div class="hst">
    <div v-if="showSearch" class="hst-search">
      <AppInput
        v-model="searchQuery"
        :placeholder="searchPlaceholder"
        clearable
        size="sm"
        @update:model-value="handleSearch"
      >
        <template #prefix>
          <el-icon :size="14"><Search /></el-icon>
        </template>
      </AppInput>
    </div>

    <div class="hst-toolbar">
      <AppButton v-if="!flat" variant="text" size="sm" @click="handleToggleExpandAll">
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

    <div class="hst-tree-container">
      <div v-if="loading" class="hst-loading">
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
        :default-expand-all="flat"
        :default-expanded-keys="expandedKeys"
        :default-checked-keys="checkedKeysFromScope"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        :indent="flat ? 12 : 16"
        @check="handleCheck"
      >
        <template #default="{ data }">
          <span class="hst-node">
            <el-icon v-if="nodeIcon" class="hst-node-icon" :size="14">
              <component :is="nodeIcon" />
            </el-icon>
            <span class="hst-node-label" :title="data[labelField]">{{ data[labelField] }}</span>
            <el-tag
              v-if="badgeOf(data)"
              class="hst-node-badge"
              size="small"
              :type="badgeOf(data).type"
              disable-transitions
            >{{ badgeOf(data).label }}</el-tag>
            <span v-else-if="!badgeEnabled && data[codeField]" class="hst-node-code">{{ data[codeField] }}</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !treeData.length" class="hst-empty">
        <el-empty :description="emptyText" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * HierarchyScopeTree — 通用层级范围树（MOMP 注入的 scope 树组件）
 *
 * 收敛了物料组 / 业务伙伴组 / 行政区划 / 位置 / 作业日历 / 计量单位组 六份克隆实现，
 * 六者的契约完全一致，差异全部由 props 表达：
 *   - props.scopeIds: MOMP 传入 page.scopeIds，读 scopeIds[scopeKey]
 *     （未命中时回退 scopeIds[objectType]，兼容「过滤键 ≠ 对象名」的页面，
 *      如物料页 scopeKey='item' 而 objectType='item_group'）
 *   - emit 'scope-change': { [idsKey], [effectiveIdsKey], selectedIds, effectiveIds }
 *     同时携带页面自有的动态键与统一键：页面 scopeAdapter 读动态键，新页面可读统一键
 *   - emit 'load': 加载完成后的树数据（根数组 / 扁平数组）
 *   - expose clear / loadTreeData / handleSelectAll（兼容 MOMP scopeTreeRef 调用）
 *
 * 数据路径：boService.query(objectType, { page_size }) → 扁平列表 → 客户端按 parentField
 * 组树；flat=true 时跳过组树直接平铺（用于无 parent 字段的扁平分类，如计量单位组）。
 *
 * 勾选口径：el-tree check-strictly=false（父子联动），effective = 勾选 ∪ 全部子孙；
 * 扁平模式无子孙，effective 与 selected 同值。setCheckedKeys 回写统一走
 * createScopeGuard()，阻断 Element Plus 内部递归触发的 @check 回路。
 *
 * 与 RelationScopeTree 的边界：后者是关系分类树（形态不同），不并入本组件。
 * 原 OrgScopeTree（组织页专用壳）已于 2026-10-24 收敛进本组件：其独有的
 * 「循环分页拉全量」变成 paginateAll、「组织图标」变成 node_icon: office。
 */
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import {
  Search, Loading, Expand, Fold, Select, CircleClose, RefreshRight, FolderOpened
} from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { createScopeGuard } from '@/composables/scopeGuard'

const props = defineProps({
  // 查询的 BO 对象名，如 item_group / region / calendar
  objectType: { type: String, required: true },
  // 扁平列表的父字段；与 objectType 一起决定组树路径
  parentField: { type: String, default: 'parent_id' },
  // true = 不组树，直接平铺（无 parent 自引用的扁平分类）
  flat: { type: Boolean, default: false },
  // 读 scopeIds 的键（页面 objectTypes / filterStrategies 对齐的那个键）
  scopeKey: { type: String, required: true },
  // emit 携带的动态键名（页面 scopeAdapter 依赖，不可由 objectType 推导）
  idsKey: { type: String, required: true },
  effectiveIdsKey: { type: String, required: true },
  labelField: { type: String, default: 'name' },
  codeField: { type: String, default: 'code' },
  // 同级节点排序字段；空串 = 保持后端返回顺序（不做客户端排序）
  orderBy: { type: String, default: 'code' },
  pageSize: { type: Number, default: 500 },
  // true = 循环分页拉全量。后端 BO query 对 page_size 有硬上限（500 行），
  //   数据量超过一页时单次查询会静默截断（如 orgs 959 行），树缺节点。
  //   小表保持 false，避免多一次请求。
  paginateAll: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  searchPlaceholder: { type: String, default: '搜索（编码/名称）' },
  // 节点徽标：badgeField 取值 → badgeMap 映射；未配置则不渲染徽标、改渲染 code
  badgeField: { type: String, default: '' },
  badgeMap: { type: Object, default: () => ({}) },
  // 节点前缀图标；传 null 则不显示（如行政区划树 / 日历树）
  nodeIcon: { type: [Object, Function], default: () => FolderOpened },
  showSearch: { type: Boolean, default: true },
  // scopeIds 由 MOMP 传入, 结构 scopeIds[scopeKey] = { selected, effective }
  scopeIds: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['scope-change', 'load'])

// 徽标兜底键：field 为空 → ROOT，其余未命中 → FALLBACK
//   （日历树用 parentId 判「基准/派生」，只能靠这两个键表达）
const ROOT_BADGE_KEY = '__root__'
const FALLBACK_BADGE_KEY = '__fallback__'

const treeRef = shallowRef(null)
const treeData = shallowRef([])
const loading = ref(false)
const refreshing = ref(false)
const searchQuery = ref('')
const expandedKeys = shallowRef([])
const treeKey = ref(1)
const isAllExpanded = ref(false)
const guard = createScopeGuard()

const treeProps = computed(() => ({ label: props.labelField, children: 'children' }))
const badgeEnabled = computed(() => !!props.badgeField && Object.keys(props.badgeMap || {}).length > 0)

// ============================================================
//  徽标：badgeField 取值 → { label, type }
// ============================================================
function badgeOf(data) {
  if (!badgeEnabled.value) return null
  const raw = data?.[props.badgeField]
  const key = (raw === null || raw === undefined || raw === '') ? ROOT_BADGE_KEY : String(raw)
  const hit = props.badgeMap?.[key] ?? props.badgeMap?.[FALLBACK_BADGE_KEY]
  if (!hit) return null
  return { label: hit.label ?? '', type: hit.type || 'info' }
}

// ============================================================
//  数据加载：扁平列表 → 组树（flat 模式直接平铺）
// ============================================================
function normalizeNode(record) {
  // 展开原始记录：保留 level / location_type 等徽标字段，再统一 id/originalId
  return {
    ...record,
    id: record.id,
    originalId: record.id
  }
}

function buildTree(items) {
  const byId = new Map()
  items.forEach(record => {
    byId.set(record.id, {
      ...normalizeNode(record),
      parentId: record[props.parentField],
      children: []
    })
  })
  const roots = []
  for (const node of byId.values()) {
    const parent = node.parentId != null ? byId.get(node.parentId) : null
    // 父存在且非自身 → 挂父；否则视为根（悬空/自环 parent_id 兜底）
    if (parent && parent.id !== node.id) parent.children.push(node)
    else roots.push(node)
  }
  if (props.orderBy) {
    const sortRec = (list) => {
      list.sort((a, b) => String(a[props.orderBy] || '').localeCompare(String(b[props.orderBy] || '')))
      list.forEach(n => sortRec(n.children))
    }
    sortRec(roots)
  }
  return roots
}

// 单页查询（默认路径）：后端按 page_size 返回，超出一页即截断
async function queryOnePage() {
  const result = await boService.query(props.objectType, { page_size: props.pageSize })
  const data = result.data || result
  return data.items || (Array.isArray(data) ? data : [])
}

// 全量分页：page_size 受后端硬上限约束，超过一页的数据集必须逐页取，
//   取到不满页或凑满 total 即停；MAX_PAGES=40（20000 行）防死循环。
async function queryAllPages() {
  const MAX_PAGES = 40
  const all = []
  let total = null
  for (let page = 1; page <= MAX_PAGES; page++) {
    const result = await boService.query(props.objectType, { page, page_size: props.pageSize })
    const data = result.data || result
    const items = data.items || (Array.isArray(data) ? data : [])
    if (data.total != null) total = data.total
    all.push(...items)
    if (items.length < props.pageSize) break
    if (total != null && all.length >= total) break
  }
  return all
}

async function loadTreeData() {
  loading.value = true
  try {
    const items = props.paginateAll ? await queryAllPages() : await queryOnePage()
    // 保留刷新前的勾选与展开态（扁平模式无展开态，也不保留勾选）
    const currentChecked = props.flat ? [] : (treeRef.value?.getCheckedKeys?.() || [])
    const nextData = props.flat ? items.map(normalizeNode) : buildTree(items)
    treeData.value = nextData
    treeKey.value++
    if (currentChecked.length) {
      await nextTick()
      const allKeys = collectAllKeys(nextData)
      treeRef.value?.setCheckedKeys(
        currentChecked.filter(k => allKeys.some(x => String(x) === String(k))))
    }
    if (!props.flat) expandedKeys.value = collectExpandableKeys(nextData, currentChecked)
    emit('load', treeData.value)
  } catch (error) {
    console.error(`[HierarchyScopeTree:${props.objectType}] 加载失败:`, error)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

// ============================================================
//  scope 计算：{ [idsKey], [effectiveIdsKey], selectedIds, effectiveIds }
//  effective = 勾选 ∪ 全部子孙（扁平模式两者同值）
// ============================================================
function emitScopeChangePayload(checked, effective) {
  emit('scope-change', {
    [props.idsKey]: checked,
    [props.effectiveIdsKey]: effective,
    selectedIds: checked,
    effectiveIds: effective
  })
}

function emitScopeChange() {
  if (!treeRef.value) return
  const checkedNodes = treeRef.value.getCheckedNodes?.(false, false) || []
  const checkedIds = checkedNodes.map(n => n.data?.originalId ?? n.data?.id ?? n.id)
  // check-strictly=false 时父节点选中已含子孙，这里再兜底补一层确保 effective 完整
  const effective = new Set(checkedIds)
  if (!props.flat) {
    checkedIds.forEach(id => {
      collectDescendantIds(findById(treeData.value, id)).forEach(d => effective.add(d))
    })
  }
  emitScopeChangePayload(checkedIds, [...effective])
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
  // 优先读 scopeKey；未命中回退 objectType（过滤键与对象名不同名的页面）
  const scope = props.scopeIds?.[props.scopeKey] ?? props.scopeIds?.[props.objectType]
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
  return (data[props.labelField]?.toLowerCase().includes(kw))
    || (data[props.codeField]?.toLowerCase().includes(kw))
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
      // 有子节点且自身被选中 → 展开，避免深树默认全折叠时看不到选中项
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
  emitScopeChangePayload([], [])
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
.hst {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hst-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}
.hst-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.hst-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 0 2px;
  min-width: 0;
  white-space: nowrap;
  flex-shrink: 1;
}
.hst-toolbar :deep(.el-icon) { margin-right: 2px; }
.hst-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}
.hst-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}
.hst-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}
.hst-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}
.hst-node-code {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.hst-node-badge {
  flex-shrink: 0;
  transform: scale(0.9);
  transform-origin: right center;
}
.hst-loading,
.hst-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
}
.hst-loading { gap: var(--spacing-sm); font-size: var(--font-size-sm); }
</style>
