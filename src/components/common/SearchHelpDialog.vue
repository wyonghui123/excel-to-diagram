<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="720px"
    @update:model-value="$emit('update:visible', $event)"
    @open="handleOpen"
    @keydown="handleKeyDown"
  >
    <div class="search-help-dialog">
      <!-- [Spec 20 v4 字段即模式] FK 字段: 双 Tab (showModeTabs);
           self-ref code 字段: bizkey_only 无 Tab 直接业务键列表;
           self-ref id 字段: 仅实例树。Tab label/hint/列定义读 source.bizkey 配置 -->
      <el-tabs
        v-if="showModeTabs"
        v-model="activeTab"
        class="vh-mode-tabs"
      >
        <el-tab-pane label="仅此实例" name="instance" />
        <el-tab-pane :label="bizkeyTabLabel" name="bizkey" />
      </el-tabs>

      <template v-if="!showBizkeyContent">
      <!-- [Spec 20 v5 L2 对偶 hint] 实例锚定解释 — 与业务键 hint 镜像同构 (对比学习建立心智):
           文案可经 source.instance_hint 覆盖, 缺省为父对象中立通用句式 -->
      <div v-if="source.type === 'bo'" class="vh-bizkey-hint vh-instance-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ instanceHintText }}</span>
      </div>

      <!-- Recent items section, excluded selected -->
      <div v-if="filteredRecentItems.length > 0 && !dialogSearchQuery" class="recent-section">
        <div class="recent-header">
          <el-icon><Clock /></el-icon>
          <span>最近使用</span>
        </div>
        <div class="recent-items">
          <div
            v-for="item in filteredRecentItems"
            :key="item.value"
            :class="['recent-item', { selected: isRecentSelected(item) }]"
            @click="handleRecentClick(item)"
          >
            <span class="recent-item-display">{{ item.display }}</span>
            <span v-if="item.code" class="recent-item-code">({{ item.code }})</span>
            <el-icon v-if="isRecentSelected(item)" class="check-icon"><Check /></el-icon>
          </div>
        </div>
      </div>

      <!-- Search bar for flat and tree_flat mode -->
      <div v-if="displayMode === 'flat' || displayMode === 'tree_flat'" class="vh-search-bar">
        <el-input
          ref="searchInputRef"
          v-model="dialogSearchQuery"
          placeholder="输入关键词实时搜索..."
          :prefix-icon="Search"
          clearable
          @input="handleDialogSearchInput"
          @clear="handleDialogSearchClear"
        />
      </div>

      <MetaListPage
        ref="metaListRef"
        v-if="displayMode === 'flat' || displayMode === 'tree_flat'"
        :object-type="source.target_bo || source.enum_type_id || 'unknown'"
        :display-mode="'dialog'"
        :hide-toolbar="true"
        :columns-override="columnsForMeta"
        :row-key="'value'"
        :options="metaListOptions"
        :enable-detail="false"
        :enable-auto-crud="false"
        class="vh-meta-list"
        @selection-change="handleSelectionChange"
        @row-click="handleMetaRowClick"
        @row-dblclick="handleMetaRowDblClick"
      />

      <!-- [FIX 2026-09-05 父组织树状 SearchHelp] 通用层级树 (自引用 BO, 如 org.parent_id):
           source.hierarchy.enabled 且非维度链 BO → 通用 buildTree (value-help 全量 + extra.parent_id 组树) -->
      <div v-else-if="displayMode === 'tree' && useGenericTree" class="vh-generic-tree">
        <el-input
          v-model="genericSearchQuery"
          placeholder="输入名称或编码搜索..."
          :prefix-icon="Search"
          clearable
          class="vh-generic-tree-search"
        />
        <div v-if="genericTreeLoading" class="vh-generic-tree-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
        <el-tree
          v-else-if="genericTreeData.length > 0"
          ref="genericTreeRef"
          :data="genericTreeData"
          :props="{ label: 'display', children: 'children' }"
          node-key="value"
          :show-checkbox="multiple"
          check-strictly
          :expand-on-click-node="false"
          :highlight-current="!multiple"
          :filter-node-method="filterGenericNode"
          @node-click="handleGenericNodeClick"
          @check="handleGenericCheck"
        >
          <template #default="{ data }">
            <span
              class="vh-generic-node"
              @dblclick="handleGenericNodeDblClick(data)"
            >
              <span class="vh-generic-node-label">{{ data.display }}</span>
              <span v-if="data.code" class="vh-generic-node-code">{{ data.code }}</span>
            </span>
          </template>
        </el-tree>
        <el-empty v-else description="暂无数据" :image-size="60" />
      </div>

      <HierarchicalTreePicker
        v-else-if="displayMode === 'tree'"
        ref="treePickerRef"
        :dimension-id="source.target_bo || ''"
        :checked-ids="props.selectedValue"
        :multiple="multiple"
        :filter-params="props.treeFilterParams"
        @confirm="handleTreePickerConfirm"
        @cancel="handleTreePickerCancel"
        @check-change="handleTreeCheckChange"
      />
      </template>

      <!-- [Spec 20 v2] 业务键 Tab: code 列表 + 实时命中数，0 命中红色警示；hint·列定义读 source.bizkey -->
      <div v-else class="vh-bizkey">
        <div class="vh-bizkey-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ bizkeyHint }}</span>
        </div>
        <el-input
          v-model="bizkeySearch"
          placeholder="搜索业务键编码..."
          :prefix-icon="Search"
          clearable
          class="vh-bizkey-search"
          @input="handleBizkeySearchInput"
        />
        <el-table
          ref="bizkeyTableRef"
          v-loading="bizkeyLoading"
          :data="bizkeyCodes"
          row-key="code"
          height="340"
          size="small"
          :highlight-current-row="!multiple"
          class="vh-bizkey-table"
          @selection-change="handleBizkeySelectionChange"
          @current-change="handleBizkeyCurrentChange"
          @row-dblclick="handleBizkeyRowDblClick"
        >
          <el-table-column v-if="multiple" type="selection" width="42" reserve-selection />
          <el-table-column
            v-for="col in bizkeyColumns"
            :key="col.key"
            :prop="col.key"
            :label="col.label"
            :width="col.width"
            :min-width="col.minWidth"
            :align="col.align"
            show-overflow-tooltip
          >
            <template v-if="col.key === 'resolved_count'" #default="{ row }">
              <span :class="['vh-bizkey-count', { 'vh-bizkey-count--zero': !row.resolved_count }]">
                {{ row.resolved_count ?? 0 }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="bizkeyPage"
          v-model:page-size="bizkeyPageSize"
          small
          layout="total, sizes, prev, pager, next"
          :page-sizes="[15, 30, 50, 100]"
          :total="bizkeyTotal"
          class="vh-bizkey-pagination"
          @current-change="loadBizkeyCodes"
          @size-change="handleBizkeySizeChange"
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <!-- [UX-FIX 2026-07-23-R2] tree multi-select: sync via internalSelectedItems driven by check-change -->
      <el-button
        v-if="multiple"
        type="primary"
        @click="handleConfirm"
        :disabled="!canConfirm"
      >
        确定 ({{ confirmCount }})
      </el-button>
      <el-button v-else-if="confirmSingleAvailable" type="primary" @click="handleConfirm">
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Search, Clock, Check, InfoFilled, Loading } from '@element-plus/icons-vue'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'
import HierarchicalTreePicker from '@/components/common/HierarchicalTreePicker'
import boService from '@/services/boService'
import { loadDimensionCodes, getResourceLabel } from '@/services/permissionService'

const props = defineProps({
  visible: { type: Boolean, default: false },
  valueHelpConfig: { type: Object, required: true },
  multiple: { type: Boolean, default: false },
  selectedValue: { type: [String, Number, Array], default: '' },
  customFetcher: { type: Function, default: null },
  // [R21 2026-07-24] tree 模式的过滤参数 (如 version_id, 由 ValueHelpField 注入)
  treeFilterParams: { type: Object, default: () => ({}) },
  // [FIX 2026-09-05 父组织树状 SearchHelp] 防环: 需要从树中剪掉的记录 id (自身+子孙),
  //   编辑态由 ValueHelpField 依 behavior.exclude_self 传入
  excludeIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:visible', 'confirm'])

const searchQuery = ref('')
const dialogSearchQuery = ref('')
// 内部选择状态
const internalSelectedItems = ref([])
const currentSingleItem = ref(null)
const metaListRef = ref(null)
const searchInputRef = ref(null)
const treePickerRef = ref(null)  // [UX-FIX 2026-07-23] tree mode ref
const recentItems = ref([])

// 监听外部传入的 selectedValue 变化，更新已选择项目（用于 Delta 场景）
// [FIX 2026-07-24-R19] tree 模式: 不在此处同步, 由 HierarchicalTreePicker @check-change 驱动
//   原因: 同 syncSelectedItemsFromMetaList, 避免 internalSelectedItems 与树勾选不同步
watch(() => props.selectedValue, (newVal) => {
  // tree 模式: 跳过, 由 handleTreeCheckChange 驱动
  if (displayMode.value === 'tree') return

  if (newVal && Array.isArray(newVal) && newVal.length > 0) {
    // 外部传入了已选择的 IDs，初始化 internalSelectedItems
    const existingValues = new Set(internalSelectedItems.value.map(item => item.value))
    const newIds = newVal.filter(id => !existingValues.has(id))
    if (newIds.length > 0 || internalSelectedItems.value.length !== newVal.length) {
      internalSelectedItems.value = newVal.map(id => {
        const existing = internalSelectedItems.value.find(item => item.value === id)
        return existing || { value: id, display: String(id), code: '' }
      })
    }
  } else if ((!newVal || (Array.isArray(newVal) && newVal.length === 0)) && internalSelectedItems.value.length > 0) {
    // 外部清空了选择，同步清空 internalSelectedItems
    internalSelectedItems.value = []
  }
}, { deep: false })

// 监听外部传入的 externalSelectedItems（完整对象），用于 Delta 场景
watch(() => props.externalSelectedItems, (newVal) => {
  if (newVal && Array.isArray(newVal) && newVal.length > 0) {
    // 外部传入了已选择的完整对象，直接使用
    internalSelectedItems.value = [...newVal]
  } else if ((!newVal || newVal.length === 0) && internalSelectedItems.value.length > 0) {
    // 外部清空了，同步清空 internalSelectedItems
    internalSelectedItems.value = []
  }
}, { deep: true })

const source = computed(() => props.valueHelpConfig?.source || {})
const presentation = computed(() => props.valueHelpConfig?.presentation || {})
const behavior = computed(() => props.valueHelpConfig?.behavior || {})

// [FIX 2026-07-24-R19] 弹窗标题: "选择数据" → "选择XX" (如选择子领域)
//   [FIX 2026-09-16-R24] 元数据驱动：移除硬编码 DIMENSION_LABEL_MAP (5 BO 名),
//   改用 permissionService.getResourceLabel (后端 /permission_dimension/meta 优先,
//   fallback 常量 RESOURCE_LABELS, 未知 key 原样返回)
const dialogTitle = computed(() => {
  const srcType = source.value.type
  if (srcType === 'enum') return '选择枚举值'
  if (srcType === 'bo') {
    const targetBo = source.value.target_bo
    if (targetBo) return `选择${getResourceLabel(targetBo)}`
    return '选择数据'
  }
  return '选择值'
})

const displayMode = computed(() => presentation.value.display_mode || 'flat')
const displayColumns = computed(() => presentation.value.display_columns || [])

// ============================================================
// [FIX 2026-09-05 父组织树状 SearchHelp] 通用层级树 (自引用 BO)
// ============================================================
// display_mode=tree 原本只有一条路径: HierarchicalTreePicker, 其数据源/节点结构
// 硬编码为 permission_dimension 维度链 (/api/v2/bo/permission_dimension/{dim}/tree,
// rootType='product', 节点需 type/unique_key 字段, 仅叶子可选)。
// 自引用层级 BO (如 org.parent_id) 走通用路径: value-help 全量拉取 +
// extra.parent_id 组树 (后端 BoValueHelpProvider 在 hierarchy.enabled 时已返回)。
const DIMENSION_TREE_BOS = new Set(['product', 'version', 'domain', 'sub_domain', 'service_module'])

const useGenericTree = computed(() => {
  if (displayMode.value !== 'tree') return false
  const src = source.value
  if (src?.type !== 'bo' || !src?.hierarchy?.enabled) return false
  return !DIMENSION_TREE_BOS.has(src.target_bo)
})

const genericTreeRef = ref(null)
const genericTreeLoading = ref(false)
const genericItems = ref([])
const genericSearchQuery = ref('')

/** 扁平 value-help 行 → 嵌套树 (extra.parent_id 组装; 悬空父/自引用 → 根, 同 OrgScopeTree 语义) */
function buildGenericTree(items) {
  const byValue = new Map()
  const nodes = items.map(item => ({ ...item, children: [] }))
  nodes.forEach(n => byValue.set(String(n.value), n))
  const roots = []
  for (const node of nodes) {
    const pid = node.extra?.parent_id
    const parent = pid != null ? byValue.get(String(pid)) : null
    if (parent && parent !== node) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

/** 防环剪枝: 排除 excludeIds (当前记录自身) 及其全部子孙整枝 */
function pruneGenericTree(nodes, excluded) {
  const result = []
  for (const n of nodes) {
    if (excluded.has(String(n.value))) continue
    result.push({ ...n, children: pruneGenericTree(n.children, excluded) })
  }
  return result
}

const genericTreeData = computed(() => {
  const excluded = new Set((props.excludeIds || []).map(String))
  return pruneGenericTree(buildGenericTree(genericItems.value), excluded)
})

/** 全量拉取: value-help 无独立树端点, 循环分页拉全
 *  (后端 bo_api MAX_USER_PAGE_SIZE=500, orgs 900+ 行; 参照 OrgScopeTree 2026-09-04 修复) */
async function loadGenericTreeData() {
  if (genericTreeLoading.value) return
  genericTreeLoading.value = true
  try {
    const PAGE_SIZE = 500
    const MAX_PAGES = 40
    const all = []
    // [FIX 2026-09-05] total 不可作退出判据: value-help 链路 (BOEngine→QueryService.skip_count)
    // 的 total 语义是"当页行数"而非"匹配总数" (实测 page1 total=500, page2 total=459)。
    // 唯一可靠的结束条件: 当页行数 < PAGE_SIZE。
    for (let page = 1; page <= MAX_PAGES; page++) {
      const resp = await boService.searchValueHelp(sourceType.value, sourceId.value, {
        page,
        pageSize: PAGE_SIZE,
        ...sourceConfigParams.value,
      })
      const rows = resp.data?.data || resp.data || []
      all.push(...rows)
      if (rows.length < PAGE_SIZE) break
    }
    genericItems.value = all
    await nextTick()
    syncGenericTreeSelection()
  } catch (e) {
    console.error('[SearchHelpDialog] generic tree load failed:', e)
    genericItems.value = []
  } finally {
    genericTreeLoading.value = false
  }
}

/** 已选回显: 单选 → currentSingleItem + setCurrentKey; 多选 → setCheckedKeys */
function syncGenericTreeSelection() {
  if (props.multiple) {
    const ids = Array.isArray(props.selectedValue)
      ? props.selectedValue
      : (props.selectedValue != null && props.selectedValue !== '' ? [props.selectedValue] : [])
    if (ids.length > 0) {
      const known = new Set(genericItems.value.map(i => String(i.value)))
      const valid = ids.filter(id => known.has(String(id))).map(Number)
      genericTreeRef.value?.setCheckedKeys(valid, false)
      handleGenericCheck()
    }
    return
  }
  const sv = props.selectedValue
  if (sv == null || sv === '') return
  const item = genericItems.value.find(i => String(i.value) === String(sv))
  if (item) {
    currentSingleItem.value = {
      value: item.value,
      display: item.display || item.name || String(item.value),
      code: item.code || '',
      name: item.display || item.name || '',
    }
    nextTick(() => genericTreeRef.value?.setCurrentKey(item.value))
  }
}

/** 客户端过滤 (el-tree 自动保留匹配节点的祖先链) */
function filterGenericNode(value, data) {
  const q = (value || '').trim().toLowerCase()
  if (!q) return true
  const label = String(data.display || '').toLowerCase()
  const code = String(data.code || '').toLowerCase()
  return label.includes(q) || code.includes(q)
}

watch(genericSearchQuery, (val) => {
  genericTreeRef.value?.filter(val)
})

/** 单选: 点击节点仅高亮, 确认走底部按钮 (与 flat 模式单击语义一致) */
function handleGenericNodeClick(data) {
  if (props.multiple) return
  currentSingleItem.value = {
    value: data.value,
    display: data.display || data.name || String(data.value),
    code: data.code || '',
    name: data.display || data.name || '',
  }
}

/** 单选: 双击节点 = 选中 + 确认 (与表格 row-dblclick / 维度树双击语义一致)
 *  显式先 set currentSingleItem 再走 handleConfirm, 保证 emit 标准 selection
 *  对象且 saveRecentItem 生效, 不绕过确认路径 (参见 R24 注释的教训) */
function handleGenericNodeDblClick(data) {
  if (props.multiple) return
  handleGenericNodeClick(data)
  handleConfirm()
}

/** 多选: check-strictly 独立勾选 → 同步 internalSelectedItems */
function handleGenericCheck() {
  if (!props.multiple) return
  const nodes = genericTreeRef.value?.getCheckedNodes(false, false) || []
  internalSelectedItems.value = nodes.map(n => ({
    value: n.value,
    display: n.display || n.name || String(n.value),
    code: n.code || '',
    name: n.display || n.name || '',
  }))
}

// [REFACTOR 2026-07-22] 元数据驱动: 层级配置由后端从 hierarchies.yaml 读取,
//   经 /tree 响应 (hierarchy_meta) 透传给 HierarchicalTreePicker.
//   此处不再 hardcode 4 层 chain.

// [FIX 2026-07-22] HierarchicalTreePicker confirm: 单选/多选统一处理
// [R24 2026-07-24] 单选分支: emit 标准 selection 对象 (跟 flat 模式一致)
//   修复: 原 emit payload.id 是原始数字, ValueHelpField.handleDialogConfirm 期望 {value, display}
//         第二次选择时 currentSingleItem 已被 handleOpen 清空, 若走 confirm 按钮分支 OK,
//         但若走 dblclick 分支 (onNodeDblClickSingle) 没经过 handleConfirm, 必须 emit 标准对象
function handleTreePickerConfirm(payload) {
  if (payload.type === 'single') {
    // [R24] 单选: 优先用 payload.node 构造标准 selection 对象
    //   payload 可能带 node 字段 (双击), 也可能只带 id (键盘 Enter 触发)
    const node = payload.node
    const item = node ? {
      value: node.id,
      display: node.name || String(node.id),
      code: node.code || '',
      name: node.name || '',
    } : {
      value: payload.id,
      display: String(payload.id),
      code: '',
      name: '',
    }
    emit('confirm', item)
  } else {
    // [UX-FIX 2026-07-23] 多选 tree: emit 标准 items shape (跟 flat 模式一致)
    // payload.nodes 是 [{ id, name, type, ancestorPath }, ...]
    // [FIX 2026-07-23-R8] emit display=name (非路径), 让 DimensionScopePanel 优先用 item.name
    const items = (payload.nodes || []).map(n => ({
      value: n.id,
      display: n.name,
      code: '',
      name: n.name,
    }))
    emit('confirm', items)
  }
  emit('update:visible', false)
}

function handleTreePickerCancel() {
  emit('update:visible', false)
}

// [UX-FIX 2026-07-23] tree 模式勾选变化 -> 同步 internalSelectedItems
//   让 dialog 的 canConfirm / 底部 chips / 确定按钮的 count 都能正确响应
// [UX-FIX 2026-07-23-R2] 不再 guard displayMode — 即使 tree_flat 也会触发, 安全
// [FIX 2026-07-23-R12] 从 nodes 提取 name, 避免标签显示 ID
// [R21 2026-07-24] 单选模式: 同步 currentSingleItem, 让"确认选择"按钮能显示
function handleTreeCheckChange({ ids, nodes }) {
  const nodeMap = new Map((nodes || []).map(n => [n.id, n]))
  internalSelectedItems.value = ids.map(id => {
    const existing = internalSelectedItems.value.find(s => s.value === id)
    if (existing && existing.name) return existing
    const node = nodeMap.get(id)
    const name = node?.name || ''
    return { value: id, display: name || String(id), code: node?.type || '', name }
  })
  // [R21] 单选模式: 同步 currentSingleItem
  if (!props.multiple) {
    if (ids.length > 0) {
      const node = nodeMap.get(ids[0])
      currentSingleItem.value = {
        value: ids[0],
        display: node?.name || String(ids[0]),
        code: node?.code || '',
        name: node?.name || '',
      }
    } else {
      currentSingleItem.value = null
    }
  }
}

const columnsForMeta = computed(() => {
  return displayColumns.value.map(col => ({
    field: col.field,
    label: col.label,
    width: col.width,
    sortable: true,
    filterable: true
  }))
})
const pageSize = computed(() => {
  const val = presentation.value.page_size
  // 强制最大 15 条/页
  if (val && val > 0 && val <= 15) return val
  return 15
})
const total = ref(0)

const sourceId = ref('')

const sourceConfigParams = computed(() => {
  const src = source.value
  const params = {}
  if (src.value_field) params.value_field = src.value_field
  if (src.display_field) params.display_field = src.display_field
  if (src.code_field) params.code_field = src.code_field
  if (src.value_filter && Object.keys(src.value_filter).length > 0) {
    params.value_filter = src.value_filter
  }
  if (src.hierarchy && Object.keys(src.hierarchy).length > 0) {
    params.hierarchy = src.hierarchy
  }
  return params
})

// 对话框搜索关键词（直接被 fetcher 读取）
const dialogSearchKeyword = ref('')

const valueHelpFetcher = (params) => {
  // buildFilterQueryParams 产出: { page, page_size, keyword, ordering, domain_code__like, ... }
  // value help API 期望: { page, pageSize, search, sort, filters[field]=value }
  // 需要做格式转换
  const { page, sort, pageSize: _ps, page_size, keyword, ordering, ...restParams } = params || {}
  const queryParams = {
    page: page || 1,
    pageSize: pageSize.value,
    ...sourceConfigParams.value
  }
  // 关键词搜索：dialogSearchKeyword 优先，fallback 到 buildFilterQueryParams 的 keyword
  const searchKeyword = dialogSearchKeyword.value || keyword || ''
  if (searchKeyword) queryParams.search = searchKeyword
  // 排序：ordering (Django style) → sort (value help style)
  // ordering=-domain_code → sort=domain_code:desc
  // ordering=domain_code  → sort=domain_code:asc
  if (ordering) {
    const isDesc = ordering.startsWith('-')
    const sortField = isDesc ? ordering.slice(1) : ordering
    queryParams.sort = `${sortField}:${isDesc ? 'desc' : 'asc'}`
  } else if (sort) {
    queryParams.sort = sort
  }
  // 列头过滤：__like/__in/__gte/__lte → filters[field__suffix]=value
  // 保留 __like/__in/__gte/__lte 后缀，后端 BoValueHelpProvider 会解析
  // __like → LIKE '%value%' (模糊匹配)
  // __in  → IN (val1,val2) (多选)
  // __gte/__lte → >= / <= (范围)
  const skipKeys = ['value_field', 'display_field', 'code_field', 'value_filter', 'hierarchy', 'apply_target_permissions']
  const filters = {}
  for (const [key, value] of Object.entries(restParams)) {
    if (skipKeys.includes(key)) continue
    if (value === undefined || value === null || value === '') continue
    // 直接保留 key（含 __like/__in/__gte/__lte 后缀）
    filters[key] = value
  }
  if (Object.keys(filters).length > 0) {
    queryParams.filters = filters
  }

  return boService.searchValueHelp(
    sourceType.value,
    sourceId.value,
    queryParams
  ).then(res => {
    const rawData = res.data?.data || []
    return {
      success: true,
      data: {
        items: rawData.map(item => ({
          ...item,
          id: item.value
        })),
        total: res.data?.total || rawData.length
      }
    }
  })
}

const effectiveFetcher = computed(() => {
  const baseFetcher = props.customFetcher || valueHelpFetcher
  // 包装 fetcher：统一注入搜索词，确保 customFetcher 也能收到搜索参数
  if (!props.customFetcher) return baseFetcher

  return (params) => {
    const searchKeyword = dialogSearchKeyword.value || ''
    return baseFetcher({ ...params, keyword: searchKeyword })
  }
})

const metaListOptions = computed(() => ({
  autoLoad: true,
  pageSize: pageSize.value,
  pageSizes: [15, 30, 50, 100],
  fetcher: effectiveFetcher.value
}))

const sourceType = ref('')

// ===== 最近使用功能 =====
const RECENT_MAX_ITEMS = 3
const recentKey = computed(() => `recent_value_help_${sourceId.value}`)

function getRecentItems() {
  try {
    const stored = localStorage.getItem(recentKey.value)
    return stored ? JSON.parse(stored) : []
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to get recent items:', e)
    return []
  }
}

function saveRecentItem(item) {
  try {
    const recent = getRecentItems()
    const filtered = recent.filter(r => r.value !== item.value)
    const updated = [item, ...filtered].slice(0, RECENT_MAX_ITEMS)
    localStorage.setItem(recentKey.value, JSON.stringify(updated))
    recentItems.value = updated
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to save recent item:', e)
  }
}

function loadRecentItems() {
  recentItems.value = getRecentItems()
  // [FIX 2026-07-24-R19] "最近使用"补全真实 name
  //   原因: 旧版本保存的 item.display 可能是 String(value) (ID fallback)
  //   方案: 检测 display === String(value) 的 item, 异步拉取真名并更新 localStorage + recentItems
  warmupRecentItemNames()
}

// [R19] 异步补全"最近使用"项的真实名称 (参考 DimensionScopePanel.warmupNameCache 思路)
async function warmupRecentItemNames() {
  const needWarmup = recentItems.value.filter(
    item => !item.display || item.display === String(item.value)
  )
  if (needWarmup.length === 0) return

  try {
    // 复用 valueHelpFetcher 拉取 (按 id 批量查询)
    const ids = needWarmup.map(item => item.value)
    const response = await boService.searchValueHelp(
      sourceType.value,
      sourceId.value,
      {
        page: 1,
        pageSize: ids.length,
        filters: { id__in: ids.join(',') }
      }
    )
    const items = response.data?.data || response.data || []
    const nameMap = new Map()
    for (const it of items) {
      const id = it.value != null ? it.value : it.id
      const name = it.display || it.name || it.username || it.code || ''
      if (name) nameMap.set(id, { display: name, code: it.code || '' })
    }

    // 更新 recentItems + localStorage
    let changed = false
    const updated = recentItems.value.map(item => {
      const found = nameMap.get(item.value)
      if (found && (!item.display || item.display === String(item.value))) {
        changed = true
        return { ...item, display: found.display, code: found.code }
      }
      return item
    })
    if (changed) {
      recentItems.value = updated
      try {
        localStorage.setItem(recentKey.value, JSON.stringify(updated))
      } catch (e) {
        console.warn('[SearchHelpDialog] Failed to persist warmed recent items:', e)
      }
    }
  } catch (e) {
    console.warn('[SearchHelpDialog] warmupRecentItemNames failed:', e)
  }
}

// [UX-FIX 2026-07-23-R4] 最近使用排除已选 (避免用户重复选)
const filteredRecentItems = computed(() => {
  const selected = new Set()
  // multi mode: selectedValue 是 array
  if (Array.isArray(props.selectedValue)) {
    props.selectedValue.forEach(id => selected.add(id))
  } else if (props.selectedValue != null) {
    selected.add(props.selectedValue)
  }
  // externalSelectedItems: 完整对象
  if (Array.isArray(props.externalSelectedItems)) {
    props.externalSelectedItems.forEach(it => {
      if (it?.value != null) selected.add(it.value)
    })
  }
  // internalSelectedItems 也算
  internalSelectedItems.value.forEach(it => {
    if (it?.value != null) selected.add(it.value)
  })
  return recentItems.value.filter(item => !selected.has(item.value))
})

watch(() => source.value, (src) => {
  if (src?.type === 'enum') {
    sourceType.value = 'enum'
    sourceId.value = src.enum_type_id || ''
  } else if (src?.type === 'bo') {
    sourceType.value = 'bo'
    sourceId.value = src.target_bo || ''
  } else if (src?.type === 'custom') {
    sourceType.value = 'custom'
    sourceId.value = src.endpoint || ''
  }
}, { immediate: true })
const expandLevel = computed(() => source.value.hierarchy?.expand_level || 2)
const valueField = computed(() => source.value.value_field || 'value')

const treeData = computed(() => {
  if (displayMode.value !== 'tree') return []
  return buildTree([])
})

const treeProps = computed(() => ({
  label: 'display',
  children: 'children',
  isLeaf: (data) => !data.children || data.children.length === 0,
}))

const canConfirm = computed(() => {
  // [Spec 20 v4] bizkey 内容 (Tab 或 bizkey_only): 按激活模式取对应选择状态
  if (showBizkeyContent.value) {
    return props.multiple
      ? bizkeySelectedItems.value.length > 0
      : bizkeySingleItem.value !== null
  }
  if (props.multiple) return internalSelectedItems.value.length > 0
  return currentSingleItem.value !== null
})

// footer 按钮的 tab 感知派生 (计数 / 单选确认按钮可见性)
const confirmCount = computed(() => {
  if (showBizkeyContent.value) {
    return props.multiple ? bizkeySelectedItems.value.length : (bizkeySingleItem.value ? 1 : 0)
  }
  return internalSelectedItems.value.length
})
const confirmSingleAvailable = computed(() => {
  if (showBizkeyContent.value) return bizkeySingleItem.value !== null
  return currentSingleItem.value !== null
})

function buildTree(items) {
  const map = {}
  const roots = []
  for (const item of items) {
    map[item.value] = { ...item, children: [] }
  }
  for (const item of items) {
    const parentId = item.extra?.parent_id
    if (parentId && map[parentId]) {
      map[parentId].children.push(map[item.value])
    } else {
      roots.push(map[item.value])
    }
  }
  return roots
}

// ===== 同步已选项目 =====
function syncSelectedItemsFromMetaList() {
  // [FIX 2026-07-24-R19] tree 模式: 不预设 internalSelectedItems
  //   原因: tree 模式下由 HierarchicalTreePicker 的 @check-change 驱动 internalSelectedItems
  //         如果预设了, 但树中对应节点被剪枝/不存在, 会导致:
  //         - 按钮显示"确定(N)" (internalSelectedItems 有值)
  //         - 但树中无勾选 (节点不存在)
  //         - 用户看不到勾选, 以为没选, 但按钮显示有1项 → 困惑
  //   方案: tree 模式下清空, 等 setCheckedKeys 触发 @check → handleTreeCheckChange 同步
  //         如果树中有已选节点, setCheckedKeys 会触发 @check, internalSelectedItems 被正确设置
  //         如果树中没有已选节点, internalSelectedItems 保持空, 按钮显示"确定(0)" — 与树同步
  if (displayMode.value === 'tree') {
    internalSelectedItems.value = []
    return
  }

  // flat 模式: 优先使用 props.externalSelectedItems（完整对象）
  if (props.externalSelectedItems && Array.isArray(props.externalSelectedItems) && props.externalSelectedItems.length > 0) {
    internalSelectedItems.value = [...props.externalSelectedItems]
    return
  }

  // flat 模式回退：使用 props.selectedValue（ID 数组）
  if (props.selectedValue && Array.isArray(props.selectedValue) && props.selectedValue.length > 0) {
    internalSelectedItems.value = props.selectedValue.map(id => ({
      value: id,
      display: String(id),
      code: ''
    }))
    if (internalSelectedItems.value.length > 0 && props.selectedValue.length > 0) {
      loadDisplayNamesForSelectedItems(props.selectedValue)
    }
    return
  }

  // flat 模式: selectedValue 为空时清理
  internalSelectedItems.value = []
}

// 异步加载选中项的显示名称
async function loadDisplayNamesForSelectedItems(ids) {
  if (!ids || ids.length === 0) return
  try {
    const response = await boService.searchValueHelp(
      sourceType.value,
      sourceId.value,
      { 
        page: 1, 
        pageSize: ids.length,
        filters: { id__in: ids.join(',') }
      }
    )
    const items = response.data?.data || response.data || []
    if (items.length > 0) {
      // 合并显示名称
      items.forEach(item => {
        const found = internalSelectedItems.value.find(s => s.value === item.value || s.value === item.id)
        if (found) {
          found.display = item.display || item.name || item.username || item.code || String(item.value || item.id)
          found.code = item.code || ''
        }
      })
    }
  } catch (e) {
    console.warn('[SearchHelpDialog] Failed to load display names:', e)
  }
}

// ===== [Spec 20 v3 2026-09-12] 业务键 Tab (Rule Builder FK picker, 父对象无关) =====
// 门控: source.bizkey.enabled=true (rule-helpers 仅对层级维度 FK 启用) 且
//   后端 /codes enabled=true (DIM_SCOPE_BIZKEY_ENABLED)。Tab label 动态渲染:
//   显式覆盖 > 「跨{parent_label}·业务键」(后端返回, domain→跨版本/version→跨产品)
//   > 中性回落「按业务键」。其他调用方 (ValueHelpField 等) 未传 bizkey.enabled,
//   Tab 永不出现。
const BIZKEY_PAGE_SIZES = [15, 30, 50, 100]   // [FIX 2026-09-12] 分页补每页数量切换
const bizkeyPageSize = ref(15)
const activeTab = ref('instance')
const bizkeyBackendEnabled = ref(true)
const bizkeyTableRef = ref(null)
const bizkeyLoading = ref(false)
const bizkeyCodes = ref([])
const bizkeyTotal = ref(0)
const bizkeySearch = ref('')
const bizkeyPage = ref(1)
const bizkeyParentLabel = ref(null)   // 后端 /codes parent_label (domain→版本, version→产品)
const bizkeySelectedItems = ref([])   // multiple: 已选 code 项 (reserve-selection 跨页保留)
const bizkeySingleItem = ref(null)    // single: 当前高亮行

// [Spec 20 v3] source.bizkey 是配置对象, 缺字段时回落动态/中性默认 (零侵入后向兼容)
const bizkeyConfig = computed(() => source.value.bizkey || {})
const bizkeyEnabled = computed(() => bizkeyConfig.value.enabled === true)
const bizkeyTabLabel = computed(() => {
  // 显式覆盖 (调用方) > 动态「跨{父对象}·业务键」 > 中性「按业务键」
  if (bizkeyConfig.value.tab_label) return bizkeyConfig.value.tab_label
  if (bizkeyParentLabel.value) return `跨${bizkeyParentLabel.value}·业务键`
  return '按业务键'
})
const bizkeyHint = computed(
  () => bizkeyConfig.value.hint || '业务键锚定：同一编码可对应多个实例，新增实例自动纳入规则。'
)

// [Spec 20 v5 L2 对偶 hint] 实例锚定解释 — 与业务键 hint 镜像同构:
//   同一句式模板下「固定指向 vs 自动覆盖」对照, 用户读完两条即完成心智建模。
//   可经 source.instance_hint 覆盖; 缺省父对象中立, 不绑定任何维度叙事。
const instanceHintText = computed(
  () => source.value.instance_hint || '实例锚定：仅匹配当前所选实例，新增不自动纳入。'
)
const bizkeyColumns = computed(() => {
  const cols = bizkeyConfig.value.columns
  if (Array.isArray(cols) && cols.length > 0) return cols
  return [
    { key: 'code', label: '业务键', width: 150 },
    { key: 'sample_name', label: '示例名称', minWidth: 140 },
    { key: 'resolved_count', label: '命中实例', width: 90, align: 'center' },
  ]
})
const isBizkeyTab = computed(
  () => showModeTabs.value && activeTab.value === 'bizkey'
)
// [Spec 20 v4 字段即模式] bizkey_only (self-ref code 字段): 无 Tab 直接业务键内容,
//   后端开关关闭时回落实例列表; FK 字段走双 Tab (showModeTabs)。
const bizkeyOnly = computed(() => bizkeyConfig.value.bizkey_only === true)
const showModeTabs = computed(
  () => bizkeyEnabled.value && bizkeyBackendEnabled.value && !bizkeyOnly.value
)
const showBizkeyContent = computed(
  () => isBizkeyTab.value || (bizkeyOnly.value && bizkeyBackendEnabled.value)
)

/** code 行 → 标准 selection 项 (value=code, 附 bizkey/resolvedCount 供规则行 tag 展示) */
function bizkeyItemFromRow(row) {
  return {
    value: row.code,
    display: row.code,
    name: row.sample_name || row.code,
    code: row.code,
    bizkey: true,
    resolvedCount: row.resolved_count ?? 0,
  }
}

/** 每页数量切换: 重置页码为 1 后重查 */
function handleBizkeySizeChange(size) {
  bizkeyPageSize.value = size
  bizkeyPage.value = 1
  loadBizkeyCodes()
}

async function loadBizkeyCodes() {
  if (bizkeyLoading.value) return
  bizkeyLoading.value = true
  try {
    const resp = await loadDimensionCodes(sourceId.value, {
      search: bizkeySearch.value || '',
      page: bizkeyPage.value,
      page_size: bizkeyPageSize.value,
    })
    const data = resp?.data || {}
    if (data.enabled === false) {
      // 后端开关关闭 → 隐藏 Tab 并回落「仅此实例」(双重门控)
      bizkeyBackendEnabled.value = false
      activeTab.value = 'instance'
      return
    }
    // [Spec 20 v3] 动态 Tab 标签数据源: domain→「跨版本」/ version→「跨产品」/ 无父→「按业务键」
    bizkeyParentLabel.value = data.parent_label ?? null
    bizkeyCodes.value = data.codes || []
    bizkeyTotal.value = data.pagination?.total_count || bizkeyCodes.value.length
    syncBizkeyPreselection()
  } catch (e) {
    console.error('[SearchHelpDialog] loadDimensionCodes failed:', e)
    bizkeyCodes.value = []
    bizkeyTotal.value = 0
  } finally {
    bizkeyLoading.value = false
  }
}

/** 回显: selectedValue 中的非数字 token 视为业务键 code, 在当前页勾选/高亮 */
function syncBizkeyPreselection() {
  const sv = Array.isArray(props.selectedValue)
    ? props.selectedValue
    : (props.selectedValue != null && props.selectedValue !== '' ? [props.selectedValue] : [])
  const codeSet = new Set(sv.map(String).filter((v) => v !== '' && !/^-?\d+$/.test(v)))
  if (codeSet.size === 0) return
  nextTick(() => {
    if (props.multiple) {
      for (const row of bizkeyCodes.value) {
        if (codeSet.has(String(row.code))) bizkeyTableRef.value?.toggleRowSelection(row, true)
      }
    } else {
      const row = bizkeyCodes.value.find((r) => codeSet.has(String(r.code)))
      if (row) {
        bizkeySingleItem.value = bizkeyItemFromRow(row)
        bizkeyTableRef.value?.setCurrentRow(row)
      }
    }
  })
}

let bizkeySearchTimer = null
function handleBizkeySearchInput() {
  if (bizkeySearchTimer) clearTimeout(bizkeySearchTimer)
  bizkeySearchTimer = setTimeout(() => {
    bizkeyPage.value = 1
    loadBizkeyCodes()
  }, 300)
}

function handleBizkeySelectionChange(selection) {
  if (!props.multiple) return
  bizkeySelectedItems.value = (selection || []).map(bizkeyItemFromRow)
}

function handleBizkeyCurrentChange(row) {
  if (props.multiple) return
  bizkeySingleItem.value = row ? bizkeyItemFromRow(row) : null
}

function handleBizkeyRowDblClick(row) {
  if (props.multiple) return
  bizkeySingleItem.value = bizkeyItemFromRow(row)
  handleConfirm()
}

// ===== 打开/重置 =====
function handleOpen() {
  searchQuery.value = ''
  dialogSearchQuery.value = ''
  dialogSearchKeyword.value = ''

  // [Spec 20 Task 9-B] bizkey Tab 状态复位 + 预检后端开关 (enabled=false 时隐藏 Tab)
  activeTab.value = 'instance'
  bizkeyBackendEnabled.value = true
  bizkeySearch.value = ''
  bizkeyPage.value = 1
  bizkeySelectedItems.value = []
  bizkeySingleItem.value = null
  if (bizkeyEnabled.value) loadBizkeyCodes()

  // 立即同步已选项目（不能依赖 setTimeout 延迟）
  syncSelectedItemsFromMetaList()

  currentSingleItem.value = null
  loadRecentItems()

  // [FIX 2026-07-24-R19] tree 模式: 弹窗每次打开都主动重载树数据
  //   原因: el-dialog 关闭时 HierarchicalTreePicker 被销毁, treeData 状态丢失
  //         重新打开时 onMounted 会触发, 但有时序问题 (可能晚于 dialog open 动画)
  //         主动调用确保数据加载, 解决"第二次打开空白"问题
  // [FIX 2026-09-05] 通用层级树: 同样每次打开重载 (走 value-help 全量)
  if (displayMode.value === 'tree') {
    if (useGenericTree.value) {
      genericSearchQuery.value = ''
      loadGenericTreeData()
    } else {
      nextTick(() => {
        if (treePickerRef.value?.loadTreeData) {
          treePickerRef.value.loadTreeData()
        }
      })
    }
  }

  // 延迟聚焦：el-dialog 有打开动画(约300ms)，nextTick 太早
  setTimeout(() => {
    if (searchInputRef.value?.focus) {
      searchInputRef.value.focus()
    }
    if (metaListRef.value?.refresh) {
      metaListRef.value.refresh()
    }
  }, 350)
}

// ===== 实时搜索 (C2) =====
let searchTimer = null
function handleSearch(query) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    searchQuery.value = query
  }, behavior.value.debounce_ms || 300)
}

function handleDialogSearchInput(query) {
  // C2: 实时搜索 - 输入即搜（debounce 300ms）
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    dialogSearchKeyword.value = query || ''
    if (metaListRef.value) {
      // [FIX] 搜索时重置分页到第1页，避免翻页后搜索结果为空
      if (metaListRef.value.pagination) {
        metaListRef.value.pagination.current = 1
      }
      metaListRef.value.loadList()
    }
  }, 300)
}

function handleDialogSearchClear() {
  dialogSearchQuery.value = ''
  dialogSearchKeyword.value = ''
  if (metaListRef.value) {
    if (metaListRef.value.pagination) {
      metaListRef.value.pagination.current = 1
    }
    metaListRef.value.loadList()
  }
}

// 监听搜索框清空（用户删除文字时自动恢复列表）
watch(dialogSearchQuery, (newVal) => {
  if (newVal === '' && dialogSearchKeyword.value !== '') {
    dialogSearchKeyword.value = ''
    if (metaListRef.value) {
      if (metaListRef.value.pagination) {
        metaListRef.value.pagination.current = 1
      }
      metaListRef.value.loadList()
    }
  }
})

// ===== 行选择 & 确认逻辑 =====

/** 从原始行数据提取标准化项 */
function normalizeItem(row) {
  const value = row.value != null ? row.value : row.id
  const display = row.display || row.name || row.username || row.code || String(value)
  return {
    value,
    display,
    code: row.code || '',
    raw: row
  }
}

/**
 * C1 + C3: 单选模式下的行点击/双击处理
 * - 单击: 高亮选中（给用户反悔机会）
 * - 双击: 立即确认并关闭
 */
function handleMetaRowClick({ row }) {
  if (props.multiple) return
  // C1: 单击仅高亮选中
  currentSingleItem.value = normalizeItem(row)
}

function handleMetaRowDblClick({ row }) {
  if (props.multiple) return
  // C3: 双击立即确认并关闭
  const item = normalizeItem(row)
  currentSingleItem.value = item
  saveRecentItem(item)
  emit('update:visible', false)
  emit('confirm', item)
}

/** 最近使用项点击 */
function handleRecentClick(item) {
  if (props.multiple) {
    const index = internalSelectedItems.value.findIndex(s => s.value === item.value)
    if (index > -1) {
      internalSelectedItems.value.splice(index, 1)
    } else {
      internalSelectedItems.value.push(item)
    }
  } else {
    // 最近使用单击即确认
    currentSingleItem.value = item
    saveRecentItem(item)
    emit('update:visible', false)
    emit('confirm', item)
  }
}

function isRecentSelected(item) {
  if (props.multiple) {
    return internalSelectedItems.value.some(s => s.value === item.value)
  }
  return currentSingleItem.value?.value === item.value
}

function handleSelectionChange(selection) {
  // 使用与 normalizeItem 相同的逻辑处理多种字段名
  internalSelectedItems.value = selection.map(s => {
    const value = s.value != null ? s.value : s.id
    return {
      value: value,
      display: s.display || s.name || s.username || s.title || s.label || s.code || String(value),
      code: s.code || '',
    }
  })
  if (!props.multiple && selection.length > 0) {
    const first = selection[0]
    currentSingleItem.value = normalizeItem(first)
  }
}

function handleTreeNodeClick(data) {
  if (props.multiple) return
  currentSingleItem.value = {
    value: data.value,
    display: data.display,
    code: data.code,
  }
}

// ===== C4: 键盘导航 =====
function handleKeyDown(e) {
  // Enter: 确认当前选中项
  if (e.key === 'Enter' && !e.isComposing) {
    // [Spec 20 v4] bizkey 内容 (Tab 或 bizkey_only): 同样的 Enter 确认语义
    if (showBizkeyContent.value) {
      e.preventDefault()
      if ((props.multiple && bizkeySelectedItems.value.length > 0) ||
          (!props.multiple && bizkeySingleItem.value)) {
        handleConfirm()
      }
      return
    }
    if (!props.multiple && currentSingleItem.value) {
      e.preventDefault()
      saveRecentItem(currentSingleItem.value)
      emit('update:visible', false)
      emit('confirm', currentSingleItem.value)
    } else if (props.multiple && internalSelectedItems.value.length > 0) {
      e.preventDefault()
      handleConfirm()
    }
  }
  // Esc: 关闭弹窗
  if (e.key === 'Escape') {
    emit('update:visible', false)
  }
}

// ===== Tree 异步加载 =====
async function loadTreeNode(node, resolve) {
  const isRoot = node.level === 0
  const parentField = props.valueHelpConfig?.source?.hierarchy?.parent_field || 'parent_id'

  const params = {
    page: 1,
    pageSize: isRoot ? 100 : 50,
    ...sourceConfigParams.value
  }

  if (!isRoot && node.data) {
    const parentValue = node.data.value != null ? node.data.value : node.data.id
    params.filters = { [parentField]: parentValue }
  } else if (isRoot) {
    params.filters = { [parentField]: null }
  }

  try {
    const response = await boService.searchValueHelp(sourceType.value, sourceId.value, params)
    const items = response.data?.data || response.data || []

    const treeNodes = items.map(item => {
      const value = item.value != null ? item.value : (item[source.value_field || 'value'] != null ? item[source.value_field || 'value'] : item.id)
      const display = item.display || item[source.display_field || 'name'] || item.name || value

      return {
        value: value,
        label: display,
        display: display,
        code: item.code || '',
        data: item,
        leaf: node.level >= 2
      }
    })

    resolve(treeNodes)
  } catch (err) {
    console.error('[SearchHelpDialog] loadTreeNode failed:', err)
    resolve([])
  }
}

function removeSelectedItem(item) {
  // 从内部选择状态中移除
  internalSelectedItems.value = internalSelectedItems.value.filter(i => i.value !== item.value)
  // 同步取消表格中的勾选状态
  if (metaListRef.value?.tableRef) {
    const tableData = metaListRef.value.data || []
    const row = tableData.find(r => (r.value ?? r.id) === item.value)
    if (row) {
      metaListRef.value.tableRef.toggleRowSelection(row, false)
    }
  }
}

function handleConfirm() {
  // [Spec 20 v4] bizkey 内容 (Tab 或 bizkey_only): emit code 项 (value=code + bizkey/resolvedCount),
  //   不写「最近使用」(recent 语义为具体实例, code 混入会误导)
  if (showBizkeyContent.value) {
    if (props.multiple) {
      if (bizkeySelectedItems.value.length === 0) return
      emit('confirm', bizkeySelectedItems.value)
    } else {
      if (!bizkeySingleItem.value) return
      emit('confirm', bizkeySingleItem.value)
    }
    emit('update:visible', false)
    return
  }
  if (props.multiple) {
    internalSelectedItems.value.forEach(item => saveRecentItem(item))
    emit('confirm', internalSelectedItems.value)
  } else {
    if (currentSingleItem.value) saveRecentItem(currentSingleItem.value)
    emit('confirm', currentSingleItem.value)
  }
  emit('update:visible', false)
}
</script>

<style scoped>
.search-help-dialog {
  padding: 0;
  display: flex;
  flex-direction: column;
}
.vh-search-bar {
  margin-bottom: 12px;
}

/* [Spec 20 Task 9-B] 跨版本·业务键 Tab */
.vh-mode-tabs {
  margin-bottom: 10px;
}
.vh-mode-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.vh-bizkey {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vh-bizkey-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
/* [Spec 20 v5 L2] 实例锚定对偶 hint: 复用 bizkey hint 样式, 补与后续内容区的间距 */
.vh-instance-hint {
  margin-bottom: 8px;
}
.vh-bizkey-hint .el-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}
.vh-bizkey-table :deep(.el-table__empty-text) {
  font-size: 12px;
}
.vh-bizkey-count {
  color: var(--el-text-color-secondary);
}
.vh-bizkey-count--zero {
  color: var(--el-color-danger);
  font-weight: 600;
}
.vh-bizkey-pagination {
  justify-content: flex-end;
}


/* [FIX 2026-09-05 父组织树状 SearchHelp] 通用层级树 */
.vh-generic-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vh-generic-tree-search {
  flex-shrink: 0;
}
.vh-generic-tree :deep(.el-tree) {
  flex: 1;
  min-height: 200px;
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 4px;
}
.vh-generic-tree-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}
.vh-generic-node {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}
.vh-generic-node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vh-generic-node-code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.vh-meta-list {
  flex: 1;
  min-height: 0;
  max-height: 500px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 让 MetaListPage 在 dialog 内自适应高度，分页可正常显示 */
.vh-meta-list :deep(.meta-list-page) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 限制 el-table 高度，给分页预留空间 */
.vh-meta-list :deep(.el-table) {
  flex: 1;
  min-height: 0;
}

.vh-meta-list :deep(.table-section) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.vh-meta-list :deep(.table-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* 分页区域在 dialog 内正常显示 */
.vh-meta-list :deep(.pagination-wrapper) {
  flex-shrink: 0;
  padding: var(--spacing-sm) 0;
  border-top: 1px solid var(--el-border-color-lighter);
}
.vh-selected-tags {
  margin-top: 12px;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-lighter);
}
.vh-selected-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}

/* 单选操作提示 */
.vh-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.vh-hint .el-icon {
  font-size: 14px;
  color: var(--el-color-primary);
}

/* Recent items section */
.recent-section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.recent-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}

.recent-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
}

.recent-item:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.recent-item.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.recent-item-display {
  color: var(--el-text-color-primary);
}

.recent-item-code {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.check-icon {
  color: var(--el-color-primary);
  margin-left: 4px;
}

.mt-highlight {
  background-color: var(--yonyou-orange-100, #FFF7ED);
  color: var(--yonyou-orange-800, #C2410C);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}
</style>
