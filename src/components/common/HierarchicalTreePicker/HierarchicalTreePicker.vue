<template>
  <div class="htp-root">
    <!-- 顶栏搜索 -->
    <div v-if="showSearch" class="htp-search">
      <AppInput
        v-model="searchQuery"
        :placeholder="`输入名称或编码搜索${totalCount ? `（共 ${totalCount} 条）` : ''}`"
        clearable
        @update:model-value="onSearchInput"
      >
        <template #prefix><AppIcon name="search" /></template>
      </AppInput>
    </div>

    <!-- 工具栏 -->
    <div v-if="showToolbar" class="htp-toolbar">
      <!-- [R26 2026-07-24] 工具栏显示逻辑修复: 不再依赖 multiple
           历史 bug: v-if="showToolbar && multiple" 让单选模式下工具栏 (展开/收起/刷新/清除) 全部不可见
           新逻辑: 工具栏始终可见 (single 模式下去掉清除按钮, 因为没有勾选概念) -->
      <AppButton variant="text" size="sm" @click="toggleExpandAll">
        <AppIcon :name="allExpanded ? 'chevron-up' : 'chevron-down'" />
        {{ allExpanded ? '收起' : '展开' }}
      </AppButton>
      <AppButton v-if="multiple" variant="text" size="sm" :disabled="checkedIds.length === 0" @click="handleClear">清除</AppButton>
      <AppButton variant="text" size="sm" :disabled="loading" @click="loadTreeData">
        <AppIcon name="refresh" />
        刷新
      </AppButton>
    </div>

    <!-- 树主体 (R3: 全部叶子平铺, 无父子层级) -->
    <div class="htp-tree-container">
      <div v-if="loading" class="htp-loading">
        <AppIcon name="refresh" class="htp-loading-icon" />
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
          <el-tooltip
            v-if="!isTargetDimNode(data)"
            :content="getNodeTooltip(data)"
            placement="top"
            :show-after="400"
            :disabled="isExcludedNode(data)"
          >
            <span
              :class="['htp-node', 'htp-node-parent',
                { 'htp-node-disabled': isExcludedNode(data) }]"
              :data-tk="data.__tk"
            >
              <component
                v-if="resolveIcon(data.icon)"
                :is="resolveIcon(data.icon)"
                :size="14"
              />
              <span class="htp-node-label" :title="data.name">{{ data.name }}</span>
              <span v-if="data.code" class="htp-node-code">{{ data.code }}</span>
              <el-tag v-if="isExcludedNode(data)" size="small" type="info" class="htp-node-tag">
                已选
              </el-tag>
            </span>
          </el-tooltip>
          <span
            v-else
            :class="['htp-node', { 'htp-node-disabled': isExcludedNode(data) }]"
            :data-tk="data.__tk"
          >
            <component
              v-if="resolveIcon(data.icon)"
              :is="resolveIcon(data.icon)"
              :size="14"
            />
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
import { resolveIcon } from './iconMap'
import AppInput from '../AppInput/AppInput.vue'
import AppButton from '../AppButton/AppButton.vue'
import AppIcon from '../AppIcon/AppIcon.vue'

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
// [R25 2026-07-24] 手动双击检测: 记录上次点击的节点 + 时间戳
//   300ms 内同节点再次点击 → 视为双击
const lastClickInfo = ref(null)

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

// [R22 2026-07-24] 父节点 tooltip 文案 (按是否有 children 区分展开/收起)
//   行业标准 (WAI-ARIA TreeView): 父节点 = 展开/收起操作, 不是选中操作
//   提示用户 "这是分组节点, 点击仅展开/收起, 请选择叶子节点"
function getNodeTooltip(data) {
  if (!data) return ''
  if (isLeaf(data)) return data.name || ''
  // 父节点: 提示展开/收起语义
  const action = data.__expanded ? '收起' : '展开'
  return `${action}分组: ${data.name || ''}`
}

// [R22 2026-07-24] 父节点不可选 (交互修正: 树形选择器语义 = 仅选目标维度叶子)
//   行业标准 (SAP Fiori / WAI-ARIA TreeView / Ant Design TreeSelect):
//     - 父节点 = "分组壳", 仅展开/收起, 不可选中
//     - 叶子节点 = 唯一可选目标
//   原实现问题: 父节点可被点击选中 (currentId 直接 = node.id, 无类型判断),
//     用户被树形结构诱导, 误选领域/子领域
//   新规则: 当前 dimensionId 决定的"目标维度"节点才能被选中
//     例 dimensionId='service_module' → 只有 type='service_module' 节点可选
//     父节点 (product/version/domain/sub_domain) 全部 disabled
function isTargetDimNode(data) {
  return data && data.type === props.dimensionId
}

function isDisabledNode(data) {
  if (isExcludedNode(data)) return true
  // [R22] 类型校验: 仅目标维度节点可选 (父节点统一禁用)
  if (!isTargetDimNode(data)) return true
  // [R22 + 历史兼容] 仅叶子可选 (onlyLeafSelectable 时, 父节点不可点)
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

// [R28] 收集到指定层级的 __tk (用于 el-tree 的 default-expanded-keys)
//   level=1 → 仅根节点, level=2 → 根+子, level=3 → 根+子+孙...
function collectKeysToLevel(nodes, targetLevel, currentLevel = 1) {
  const result = []
  for (const n of nodes) {
    if (currentLevel <= targetLevel) {
      result.push(n.__tk)
    }
    if (n.children && currentLevel < targetLevel) {
      result.push(...collectKeysToLevel(n.children, targetLevel, currentLevel + 1))
    }
  }
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
    const url = `/api/v2/bo/permission_dimension/${props.dimensionId}/tree?${params}`
    const resp = await fetch(url, { credentials: 'include' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const json = await resp.json()
    treeData.value = buildNestedTree(json.data || [], props.dimensionId)
    buildTkIndex(treeData.value)
    totalCount.value = json.total || 0
    if (json.hierarchy_meta) {
      hierarchyMeta.value = json.hierarchy_meta
    }
    // [R28] defaultExpandedKeys: 按 default_expand_level 收集, 非仅根节点
    //   default_expand_level=2 → 收集 product + version 的 __tk
    const expandLevel = hierarchyMeta.value?.ui_config?.default_expand_level || 1
    defaultExpandedKeys.value = collectKeysToLevel(displayTreeData.value, expandLevel)
  } catch (e) {
    console.error('[HierarchicalTreePicker] load failed:', e)
    treeData.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
  }
  // [R28] 默认展开行为: 搜索时全展开, 非搜索时按 default_expand_level 展开
  //   搜索后全展开: 用户搜索时期望快速看到匹配结果, 不需要手动逐级展开
  //   非搜索按层级展开: 遵循 SAP InitialExpansionLevel 标准, 渐进披露
  //   default_expand_level=2 → 展开到领域层 (产品↘版本↘领域)
  await nextTick()
  if (debouncedSearch.value) {
    expandAllNodes(displayTreeData.value)
  } else {
    const expandLevel = getDefaultExpandLevel()
    expandToLevel(displayTreeData.value, expandLevel)
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

// [R20→R28] 基于元模型 default_expand_level 的智能展开 (遵循 SAP 标准)
//   SAP Fiori: UI.PresentationVariant.InitialExpansionLevel + GroupBy 联合控制
//   我们: hierarchyMeta.ui_config.default_expand_level 驱动展开深度
//   层级链: product(0) → version(1) → domain(2) → sub_domain(3) → service_module(4)
//   default_expand_level=2 → 展开到领域层 (产品↘版本↘领域), 用户最熟悉的分类维度
//   无配置时 fallback: 仅展开根节点 (渐进披露)
function expandToLevel(nodes, targetLevel, currentLevel = 0) {
  if (!treeRef.value || !nodes || nodes.length === 0) return
  for (const n of nodes) {
    const treeNode = treeRef.value.getNode(n.__tk)
    if (treeNode && n.children && n.children.length > 0) {
      if (currentLevel < targetLevel) {
        treeNode.expanded = true
        // 递归展开子节点 (层级+1)
        expandToLevel(n.children, targetLevel, currentLevel + 1)
      }
      // currentLevel >= targetLevel: 不展开, 遵循渐进披露
    }
  }
}

// [R28] 从 hierarchyMeta 读取 default_expand_level, fallback=1 (仅根节点)
function getDefaultExpandLevel() {
  const cfg = hierarchyMeta.value?.ui_config
  if (cfg && typeof cfg.default_expand_level === 'number' && cfg.default_expand_level > 0) {
    return cfg.default_expand_level
  }
  return 1 // fallback: 仅展开根节点
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
  // [R22 2026-07-24] 类型校验: 多选模式下也只保留目标维度节点
  //   防止用户通过 checkbox 误选父节点
  //   注意: el-tree 在父节点上的 checkbox 状态通常不应被展示
  //         (依赖 isDisabledNode 在 disabled 状态下不响应点击), 此处兜底
  const targetIds = filteredIds.filter(id => {
    const tk = tkByTypeId.value.get(`${props.dimensionId}:${id}`)
    const node = byTk.get(tk)
    return node && isTargetDimNode(node)
  })
  checkedIds.value = targetIds

  // 同步 emit 完整 nodes (SearchHelpDialog 用)
  // [R22] 使用 targetIds 保持 ids 和 nodes 一致 (避免按钮显示(1)但 chips 显示 0 的不一致)
  const emitNodes = targetIds.map(id => {
    const tk = tkByTypeId.value.get(`${props.dimensionId}:${id}`)
    return byTk.get(tk) || { id, name: `#${id}`, type: '' }
  })
  emit('check-change', { ids: checkedIds.value, nodes: emitNodes })
}

// ── 单选事件 ──
// [R22 2026-07-24] 父节点点击 = 仅展开/收起, 不选中
//   行业标准 (SAP Fiori / WAI-ARIA TreeView / Ant Design TreeSelect):
//     - 点击父节点 → 展开/收起 (不选中)
//     - 点击叶子节点 → 选中 (取消已选则取消选中)
function onNodeClickSingle(node) {
  if (!node) return
  // [R22] 父节点: 仅展开/收起, 不进入选中逻辑
  if (!isTargetDimNode(node)) {
    toggleNodeExpand(node)
    return
  }
  // [R25 2026-07-24] 叶子节点: 手动检测双击 (Element Plus el-tree 没有原生 node-dblclick)
  //   业务背景: 用户期望双击叶子节点 = 直接确认 (类似 file picker 双击打开/确认)
  //   检测规则: 300ms 内同一叶子节点连续两次点击 → 视为双击
  //   - 第一次 click: 选中 (emit check-change, 走标准选中流程)
  //   - 第二次 click (300ms 内, 同节点): 触发双击 (emit confirm + 关闭 dialog)
  const now = Date.now()
  const isDouble = lastClickInfo.value?.id === node.id && (now - lastClickInfo.value?.ts) < 300
  lastClickInfo.value = { id: node.id, ts: now }
  if (isDouble) {
    // 双击: 保持选中 + 触发 confirm (SearchHelpDialog 关闭)
    currentId.value = node.id
    // [R25 2026-07-24] 先 emit check-change 让 SearchHelpDialog 同步 currentSingleItem
    //   (handleConfirm 用 currentSingleItem.value 传给 ValueHelpField.handleDialogConfirm)
    //   再 emit confirm 走双击快速通道 (避免点"确认选择"按钮)
    emit('check-change', { ids: [node.id], nodes: [node] })
    emit('confirm', { type: 'single', id: node.id, node })
    return
  }
  // 叶子节点: 原选中逻辑
  if (currentId.value === node.id) {
    currentId.value = null
  } else {
    currentId.value = node.id
  }
  // [R21 2026-07-24] emit check-change 让 SearchHelpDialog 更新 currentSingleItem
  //   这样单选模式下"确认选择"按钮能正确显示/隐藏
  emit('check-change', { ids: currentId.value != null ? [currentId.value] : [], nodes: currentId.value != null ? [node] : [] })
}

// [R22 2026-07-24] 切换节点的展开/收起状态 (父节点点击行为)
function toggleNodeExpand(node) {
  if (!node || !treeRef.value) return
  if (!isLeaf(node)) {
    const treeNode = treeRef.value.getNode(node.__tk)
    if (treeNode) {
      treeNode.expanded = !treeNode.expanded
    }
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
      // [FIX 2026-08-24] id 冲突场景 (生产脏数据: 4 层 id 相同) 下,
      //   允许用 unique_key 精确命中目标节点, 避免 findNodeById 永远返回根节点
      if (n.id === id || n.unique_key === id) return n
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
  // [FIX 2026-08-24] 用 unique_key 链走父级 (与 buildNestedTree 的孤儿判定一致)
  //   旧实现走 parent_id: 生产脏数据 parent_id 在 4 层间相同, 链会坍塌/错指
  const byUnique = new Map()
  function index(arr) {
    for (const n of arr) {
      byUnique.set(n.unique_key, n)
      if (n.children) index(n.children)
    }
  }
  index(treeData.value)

  const parts = []
  let cur = node
  while (cur) {
    parts.unshift(cur.name)
    if (cur.parent_unique_key == null) break
    cur = byUnique.get(cur.parent_unique_key)
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
/* [P1-Base-04] AppIcon 替换 el-icon 后的 loading 旋转动画 (原 .el-icon.is-loading) */
:deep(.htp-loading-icon) {
  animation: htp-rotating 1.2s linear infinite;
}
@keyframes htp-rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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
/* [R22 2026-07-24] 父节点样式: 分组壳, 不可点选中, 加粗+默认 cursor */
.htp-node-parent {
  font-weight: 500;
  cursor: default;
  color: var(--el-text-color-regular);
}
.htp-node-parent .htp-node-label {
  font-weight: 500;
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
