<template>
  <div class="menu-permission-matrix" :class="{ 'mpm--readonly': !props.editing, 'mpm--editing': props.editing }">
    <!-- [v35 2026-08-27] 菜单文本搜索：按 display_name / menu_code 实时过滤（无需按精确 group） -->
    <div v-if="!loading && menus.length > 0" class="mpm-search-bar">
      <AppInput
        v-model="searchKeyword"
        size="sm"
        placeholder="搜索菜单名称 / 编码"
        clearable
      />
      <span class="mpm-search-meta">
        {{ filteredMenus.length }} / {{ menus.length }} 项
      </span>
    </div>

    <div v-if="loading" class="loading-state">
      <div style="color:var(--color-text-quaternary, #bfbfbf)">[加载中... menusLength={{ modelValue.length }} loading={{ loading }}]</div>
    </div>

    <div v-else-if="filteredMenus.length === 0" class="empty-state">
      <el-empty :description="emptyDescription" />
    </div>

    <div v-else class="menu-list">
      <!-- [Phase 5] 树形菜单视图（扁平 v-for，按 depth 缩进） -->
      <div
        v-for="node in flatTree"
        :key="node.menu.menu_code"
        :class="['menu-card', 'menu-tree-node', {
          'is-assigned': isAssigned(node.menu.menu_code),
          'is-partial': isPartial(node.menu.menu_code),
          'is-selected': props.selectedMenuCode === node.menu.menu_code,
          'is-folder': node.children.length > 0,
        }]"
        :style="{ paddingLeft: `${12 + node.depth * 16}px` }"
        @click="handleSelectMenu(node.menu)"
      >
        <div class="menu-card-header">
          <!-- 折叠/展开箭头（仅父节点显示 ▶） -->
          <span
            v-if="node.children.length > 0"
            class="expand-toggle"
            :class="{ expanded: isExpanded(node.menu.menu_code) }"
            @click.stop="toggleExpand(node.menu.menu_code)"
          >▶</span>
          <span v-else class="expand-toggle leaf">·</span>

          <input
            type="checkbox"
            :checked="isAssigned(node.menu.menu_code)"
            :indeterminate="isPartial(node.menu.menu_code)"
            :disabled="!props.editing"
            @change="handleToggleMenu(node.menu)"
            @click.stop
          />
          <div class="menu-title-area">
            <span class="menu-name">{{ node.menu.display_name }}</span>
            <!-- [2026-08-30 只读态] 菜单来源权限集（来源 ps 集合，仿资源矩阵「来源：」标签） -->
            <span
              v-if="!props.editing && node.menu.source_ps_names?.length"
              class="menu-source"
            >
              <el-tooltip
                :content="`来源权限集：${node.menu.source_ps_names.join('、')}`"
                placement="top"
                :teleported="true"
              >
                <span class="menu-source-label">来源：{{ node.menu.source_ps_names.join('、') }}</span>
              </el-tooltip>
            </span>
          </div>

          <div class="menu-badges">
            <span
              v-if="node.menu.required_permissions?.length"
              :class="['badge', 'badge-capability', { 'badge-all-granted': allCapsGranted(node.menu) }]"
            >
              {{ grantedCapCount(node.menu) }}/{{ node.menu.required_permissions.length }} 权限
            </span>
            <span v-if="node.menu.has_data_scope" class="badge badge-scope">有数据范围</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch } from 'vue'
// [2026-08-28 重构清理] 数据模型 interface 收敛到 permissionConstants.ts（单一事实源）；
// 分组状态重算复用 useMenuPermission 的 recalcBoGroupStatus（原双份实现去重）
import { type Menu } from '../constants/permissionConstants'
import { recalcBoGroupStatus } from '../composables/useMenuPermission'

const props = defineProps<{
  modelValue: Menu[]
  loading?: boolean
  /** [Phase 3] 当前选中菜单的 menu_code（父组件控制高亮） */
  selectedMenuCode?: string
  /** [v44 2026-08-27] 浏览/编辑态（true=可交互, false=全 disabled） */
  editing?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [menus: Menu[]]
  'change': [menus: Menu[]]
  /** [Phase 3] 选中菜单（联动右侧 ResourceActionMatrix 展示该菜单关联的资源） */
  'select-menu': [menu: Menu]
}>()

function handleSelectMenu(menu: Menu) {
  emit('select-menu', menu)
}

// [Phase 5 FIX] ref<Set> + version 计数器
//   Vue3 中 reactive(Set) 在某些情况下不触发依赖更新（已知坑）
//   解决：用 ref 持有 Set + ref 计数器，每次 toggle 让 version+1 强制 flatTree 重算
//   语义：collapsedMenus 包含 code = 该节点被收起（子项不展开）
const collapsedMenus = ref(new Set<string>())
const expandVersion = ref(0)
// [Phase 6 2026-08-25 FIX] 父子联动修复
//   历史 bug：之前用 `{ ...m, _partial: false }` 给每个 menu 创建副本，
//   触发 handleToggleMenu 时改的是副本的 assigned，
//   menuTree 重算后修改丢失 → 勾选/反选不联动。
//   修复：直接引用原始 menu 对象，三态（assigned / partial / none）改为外部 Map 存储。
//
//   [v32 2026-08-27] 升级三态 Map: 原 partialMap: Map<code, boolean> 只存 partial
//     新 stateMap:    Map<code, 'assigned'|'partial'|'none'>
//     原因: 父节点 "所有子都分配" 时菜单视图态应是 assigned（视觉一致），
//     但不能回写原始 menu.assigned（会污染 props 引用）。
//     全部派生到外部 Map，模板 :checked / :indeterminate 都从这里读。
type MenuState = 'assigned' | 'partial' | 'none'
const stateMap = ref<Map<string, MenuState>>(new Map())
const partialVersion = ref(0)

function getMenuState(menuCode: string): MenuState {
  void partialVersion.value
  return stateMap.value.get(menuCode) || 'none'
}

function isPartial(menuCode: string): boolean {
  return getMenuState(menuCode) === 'partial'
}

// [FIX v44 2026-08-27] findNodeByCode 提到顶层，让 isAssigned 与 handleToggleMenu 共用
function findNodeByCode(nodes: MenuTreeNode[], code: string): MenuTreeNode | null {
  for (const n of nodes) {
    if (n.menu.menu_code === code) return n
    const found = findNodeByCode(n.children, code)
    if (found) return found
  }
  return null
}

function isAssigned(menuCode: string): boolean {
  const s = getMenuState(menuCode)
  // 叶子节点仍以原始 menu.assigned 为准（外部可能直接改它），
  // 父节点（隐式或非叶子）以派生 state 为准。
  // 简化处理：stateMap 有值就用 stateMap，否则按 menu.assigned 兜底。
  if (s !== 'none') return s === 'assigned'
  const node = findNodeByCode(menuTree.value, menuCode)
  if (node && node.children.length === 0) return node.menu.assigned
  return false
}

// [Phase 5] 树节点类型：menu + 子节点数组 + 缩进深度
interface MenuTreeNode {
  menu: Menu
  children: MenuTreeNode[]
  depth: number
  /** 是否为隐式父节点（数据库不存在，是 menu_path 推出来的容器） */
  implicit?: boolean
}

const menus = toRef(props, 'modelValue')

// [v35 2026-08-27] 菜单文本搜索关键字（按 display_name / menu_code 实时过滤）
const searchKeyword = ref('')

/** 按文本搜索过滤菜单 */
const filteredMenus = computed(() => {
  let list = menus.value || []
  const kw = searchKeyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((m) =>
      (m.display_name || '').toLowerCase().includes(kw)
      || (m.menu_code || '').toLowerCase().includes(kw),
    )
  }
  return list
})

/** [v35 2026-08-27] 空状态文案：区分"搜索无结果"与"暂无菜单" */
const emptyDescription = computed(() => {
  if (searchKeyword.value.trim()) return `未找到匹配"${searchKeyword.value.trim()}"的菜单`
  return '暂无菜单权限配置'
})

/** [Phase 5] 构建菜单树（按 parent_menu 嵌套；缺失则按 menu_path 段数降级）
 *   优先使用菜单数据中的 parent_menu 字段（最可靠，由菜单定义直接给出）
 *   fallback：parent_menu 缺失时，按 menu_path 的倒数第二段匹配父菜单的 menu_path
 *   最终 fallback：路径前缀未匹配到已知父菜单时，注入「隐式父菜单」占位节点
 *   [FIX 2026-08-25] 节点 menu 直接引用原始 menu（不复制），
 *     这样 handleToggleMenu 修改的就是 props.modelValue 里的同一对象。
 */
const menuTree = computed<MenuTreeNode[]>(() => {
  // [v60 2026-08-27] 修复「Maximum recursive updates exceeded」死循环：
  //   此前本 computed 开头读 partialVersion、结尾写 partialVersion++（还在 computed 内
  //   写 stateMap）—— 在自身依赖里写自己 → render → 重算 → 无限递归。
  //   现在本 computed 变为纯函数（只构树）；三态推导移到下方 watch 后置执行。
  const list = filteredMenus.value || []
  const nodeMap = new Map<string, MenuTreeNode>()

  // [Phase 5 兜底] 注入隐式父菜单：当前已知菜单的「容器」节点（数据库里可能 is_active=0/被过滤）
  const IMPLICIT_PARENTS: Record<string, { menu_code: string; display_name: string; menu_path: string; parent_menu?: string; assigned: boolean }> = {
    system: { menu_code: 'system', display_name: '系统管理', menu_path: '/system', assigned: false },
    product: { menu_code: 'product', display_name: '产品管理', menu_path: '/product', assigned: false },
    business: { menu_code: 'business', display_name: '业务配置', menu_path: '/business', assigned: false },
  }
  Object.entries(IMPLICIT_PARENTS).forEach(([code, meta]) => {
    if (!nodeMap.has(code)) {
      // 隐式父菜单只在菜单树里展示，不会写入 props.modelValue
      // 用一份独立对象，不影响原始 menu 数组
      nodeMap.set(code, {
        menu: { ...meta, required_permissions: [], is_implicit: true } as any,
        children: [],
        depth: 0,
        implicit: true,
      })
    }
  })

  // 第一遍：创建节点 —— 直接引用原始 menu 对象（不再浅拷贝）
  list.forEach((m) => {
    if (m && m.menu_code) {
      nodeMap.set(m.menu_code, { menu: m, children: [], depth: 0 })
    }
  })

  // 辅助：通过 menu_path 段数降级找父菜单
  function findParentByPath(menu: any): any | null {
    const path = String(menu.menu_path || '').replace(/^\/+|\/+$/g, '')
    const segments = path.split('/').filter(Boolean)
    if (segments.length <= 1) return null // 根菜单无父
    const parentPath = segments.slice(0, -1).join('/')
    return list.find((pm) => {
      const pp = String(pm.menu_path || '').replace(/^\/+|\/+$/g, '')
      return pp === parentPath
    }) || null
  }

  // 辅助：通过 menu_path 第一段推断隐式父菜单
  function findImplicitParent(menu: any): any | null {
    const path = String(menu.menu_path || '').replace(/^\/+|\/+$/g, '')
    const segments = path.split('/').filter(Boolean)
    if (segments.length <= 1) return null
    const firstSeg = segments[0]
    if (IMPLICIT_PARENTS[firstSeg]) {
      return nodeMap.get(firstSeg) || null
    }
    return null
  }

  // 辅助：找父菜单（链式向上找 parent of parent）
  function findParent(menu: any): any | null {
    // 1) 优先 parent_menu（链式回溯）
    let cur = menu
    let depth = 0
    while (cur && depth < 5) {
      if (cur.parent_menu && nodeMap.has(cur.parent_menu)) {
        return list.find((pm) => pm.menu_code === cur.parent_menu) || nodeMap.get(cur.parent_menu)!.menu
      }
      // 没父菜单的，自己去按路径找
      break
    }
    // 2) fallback: 按 menu_path 段数
    const byPath = findParentByPath(menu)
    if (byPath) return byPath
    // 3) fallback: 隐式父菜单
    return findImplicitParent(menu)
  }

  // 第二遍：建立父子关系
  const roots: MenuTreeNode[] = []
  list.forEach((m) => {
    if (!m || !m.menu_code) return
    const parent = findParent(m)
    if (parent && parent.menu_code && nodeMap.has(parent.menu_code)) {
      const parentNode = nodeMap.get(parent.menu_code)!
      if (!parentNode.children.find((c) => c.menu.menu_code === m.menu_code)) {
        parentNode.children.push(nodeMap.get(m.menu_code)!)
      }
    } else {
      const node = nodeMap.get(m.menu_code)!
      if (!roots.find((r) => r.menu.menu_code === m.menu_code)) {
        roots.push(node)
      }
    }
  })

  // 收集所有菜单 code（包含隐式父菜单），把有 children 但未列入 roots 的也加进去
  const allCodes = new Set<string>()
  function collectCodes(nodes: MenuTreeNode[]) {
    nodes.forEach((n) => {
      allCodes.add(n.menu.menu_code)
      collectCodes(n.children)
    })
  }
  collectCodes(roots)
  nodeMap.forEach((node, code) => {
    if (!allCodes.has(code) && node.children.length > 0) {
      roots.push(node)
    }
  })

  // 计算 depth + 递归
  function setDepth(nodes: MenuTreeNode[], depth: number) {
    nodes.forEach((n) => {
      n.depth = depth
      setDepth(n.children, depth + 1)
    })
  }
  setDepth(roots, 0)

  // [v60 2026-08-27] 三态推导移出 computed（原在此处内联 calcPartial + stateMap 写入 +
  //   partialVersion++，导致 computed 自依赖递归）。改为 watch 后置副作用，见下方。
  return roots
})

// [v60 2026-08-27] 三态推导（assigned / partial / none）—— 后置副作用，不在 computed 内
//   - assigned: checkbox 显示勾（所有后代都分配 或 叶子菜单自身被分配）
//   - partial:  checkbox 显示 indeterminate（部分后代已分配）
//   - none:     checkbox 空
//   触发源：menuTree 结构变化 或 任意菜单 assigned 翻转（扁平列表序列化签名）
function calcPartial(nodes: MenuTreeNode[]) {
  nodes.forEach((n) => {
    // 后序：先算 children
    calcPartial(n.children)
    // 叶子节点：以原始 menu.assigned 为准（外部直接控制）
    if (n.children.length === 0) {
      stateMap.value.set(n.menu.menu_code, n.menu.assigned ? 'assigned' : 'none')
      return
    }
    // 父节点：派生三态（不污染原始 menu）
    const allAssigned = n.children.every((c) => {
      const cs = stateMap.value.get(c.menu.menu_code)
      // 子节点的派生态若是 assigned/partial 都算"已分配"
      return cs === 'assigned' || c.menu.assigned
    })
    const anyAssigned = n.children.some((c) => {
      const cs = stateMap.value.get(c.menu.menu_code)
      return cs === 'assigned' || cs === 'partial' || c.menu.assigned
    })
    let state: MenuState
    if (allAssigned) state = 'assigned'
    else if (anyAssigned) state = 'partial'
    else state = 'none'
    stateMap.value.set(n.menu.menu_code, state)
  })
}

watch(
  [
    menuTree,
    // assigned 翻转签名（modelValue 为扁平列表，覆盖全部叶子节点）
    () => (props.modelValue || []).map((m) => `${m.menu_code}:${m.assigned ? 1 : 0}`).join('|'),
  ],
  () => {
    stateMap.value = new Map()
    calcPartial(menuTree.value || [])
    // 触发依赖 partialVersion 的视图刷新
    partialVersion.value++
  },
  { immediate: true, deep: false },
)

/** [Phase 5] 扁平化菜单树（DFS，根节点默认全部展开，折叠状态由 collapsedMenus 控制）
 *  - 依赖 expandVersion 让 collapsedMenus 变更时 computed 重算
 *  - 默认展开：所有有 children 的节点都展开（用户体验：直接看到完整菜单）
 *  - 折叠：collapsedMenus 包含 code 时，**该节点及其所有后代都不显示**
 */
const flatTree = computed<MenuTreeNode[]>(() => {
  // 读取 expandVersion 让 Vue 建立依赖
  const _v = expandVersion.value
  const out: MenuTreeNode[] = []
  function dfs(nodes: MenuTreeNode[]) {
    nodes.forEach((n) => {
      // 先输出自己
      out.push(n)
      // 默认展开；只有当本节点在「收起」集合里才不递归 children
      if (n.children.length > 0 && !collapsedMenus.value.has(n.menu.menu_code)) {
        dfs(n.children)
      }
    })
  }
  const tree = menuTree.value || []
  dfs(tree)
  void _v
  return out
})

function isExpanded(code: string): boolean {
  // 父节点默认展开，叶子节点无展开状态
  return !collapsedMenus.value.has(code)
}

function toggleExpand(code: string) {
  // [v44 2026-08-27] 浏览态：展开/收起 是只读辅助，保留可用
  if (collapsedMenus.value.has(code)) {
    collapsedMenus.value.delete(code)
  } else {
    collapsedMenus.value.add(code)
  }
  // 触发 flatTree 重算
  expandVersion.value++
}

function handleToggleMenu(menu: Menu) {
  // [v44 2026-08-27] 浏览态：理论 disabled 已阻断，这里再加防御性 guard
  if (!props.editing) return
  const target = !menu.assigned

  // [Phase 6 2026-08-25 FIX] 父子联动：勾选父节点时，所有后代自动跟随
  //   - menuTree 现在直接引用原始 menu（不再浅拷贝），
  //     所以 setRecursive 修改 node.menu.assigned = target
  //     实际上就是在修改 props.modelValue[i].assigned，响应式自动更新。
  //   - 不强制修改祖先的 assigned（祖先由 calcPartial 三态呈现）
  //   - 隐式父菜单（system/product/business）是 menuTree 内部的副本，
  //     修改它的 assigned 不影响 props，但下次 menuTree 重算时会自动重置为 false，
  //     由 calcPartial 根据后代状态重新派生三态 — 这是正确的预期行为。
  // [v70 2026-08-28] 权限联动同步（exclude 优先）：
  //   - 勾选菜单：用户显式排除(exclude)的权限保持排除，不再被静默覆盖为 auto
  //   - 取消菜单：exclude 标记保留（granted 本就是 false），勾回菜单时继续生效
  //   - 分组/独立动作状态按 required_permissions 实际值重算，不能全置 true
  function applyMenuPermSync(m: Menu, assigned: boolean) {
    m.required_permissions?.forEach(p => {
      if (p.source === 'exclude') return
      p.granted = assigned
      p.source = assigned ? (p.source === 'include' ? 'include' : 'auto') : ''
    })
    const boIds = new Set((m.bo_permission_groups || []).map(bg => bg.bo_id))
    boIds.forEach(boId => {
      recalcBoGroupStatus(m, boId)
      const boGroup = m.bo_permission_groups?.find(g => g.bo_id === boId)
      boGroup?.standalone?.forEach(sp => {
        const perm = m.required_permissions?.find(p => p.code === `${boId}:${sp.action}`)
        if (perm) {
          sp.granted = perm.granted
          sp.source = perm.source
        }
      })
    })
  }

  function setRecursive(node: MenuTreeNode, assigned: boolean) {
    node.menu.assigned = assigned
    applyMenuPermSync(node.menu, assigned)
    // 后代联动
    node.children.forEach((c) => setRecursive(c, assigned))
  }

  // [FIX v44 2026-08-27] findNodeByCode 已提升为顶层函数（line ~197），此处直接复用
  const targetNode = findNodeByCode(menuTree.value, menu.menu_code)
  if (!targetNode) {
    // [兜底] menuTree 未包含（极端情况）：仅翻转自身，保持旧行为
    menu.assigned = target
    emit('change', menus.value)
    return
  }

  // 自动展开被勾选的节点（UX 优化）
  if (target) {
    collapsedMenus.value.delete(menu.menu_code)
    expandVersion.value++
  }

  setRecursive(targetNode, target)

  // [FIX 2026-08-25] 触发 menuTree 重算（修改 menu.assigned 不一定触发 computed 依赖）
  partialVersion.value++

  // 通知父组件 v-model 更新（emit update 触发父组件重新构建 menus 数组，
  // menuTree 自然重算 —— 因为现在 menu 是原始引用，
  // 重算后菜单的 assigned 已经是 target 值，不会丢修改）。
  emit('update:modelValue', menus.value)
  emit('change', menus.value)
}

function allCapsGranted(menu: Menu) {
  return menu.required_permissions?.every(p => p.granted)
}

function grantedCapCount(menu: Menu) {
  if (!menu.required_permissions) return 0
  return menu.required_permissions.filter(p => p.granted).length
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.menu-permission-matrix {
  /* [v38 2026-08-27] 顶部空白压缩：父级 .app-card__body padding-top 已清零，
     这里不需任何负 margin。flex gap 控制搜索栏和列表的间距。 */
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

/* [v35 2026-08-27] 菜单搜索栏：紧凑，输入框 + "N / M 项" 计数 */
.mpm-search-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 0; /* [v37] 取消底部 margin，上下间距由 menu-permission-matrix 的 gap 控制 */
}
.mpm-search-bar .mpm-search-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  /* [v71 2026-08-28] 对齐 UI 规范: 移除 monospace(中文等宽突兀), 统一系统字体栈 */
  white-space: nowrap;
}
.mpm-search-bar :deep(.app-input) {
  flex: 1 1 auto;
}

.loading-state,
.empty-state {
  padding: var(--spacing-lg);
  text-align: center;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.menu-card {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
  overflow: hidden;

  &:hover {
    border-color: var(--color-border);
  }

  &.is-assigned {
    border-left: 3px solid var(--color-text-quaternary, #bfbfbf);
    background: var(--color-bg-spotlight, #fafafa);
  }

  &.is-selected {
    border-color: var(--yonyou-blue-500, #3b82f6);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
  }

  &.is-folder {
    background: var(--color-bg-elevated, #fafafa);
  }
}

/* [Phase 5] 树节点展开箭头 */
.expand-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 10px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  user-select: none;
  transition: transform 0.15s ease;

  &.expanded {
    transform: rotate(90deg);
  }
  &.leaf {
    color: var(--color-text-tertiary);
    opacity: 0.4;
    cursor: default;
  }
}

.menu-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);

  input[type='checkbox'] {
    width: 16px;
    height: 16px;
    /* [v70 2026-08-28] 与右侧资源矩阵 el-checkbox 风格一致: 用 Element Plus 主色（品牌橙） */
    accent-color: var(--el-color-primary, #ea580c);
    cursor: pointer;
    flex-shrink: 0;
  }
}

.menu-title-area {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
  cursor: pointer;
}

.menu-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.menu-source {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 240px;
  cursor: default;
}
.menu-source-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-badges {
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.badge {
  /* [v71 2026-08-28] 对齐 UI 规范: 10px 低于令牌最小字号, 改用 --font-size-xs(12px) */
  font-size: var(--font-size-xs);
  padding: 0 var(--spacing-xs);
  border-radius: 9px;
  font-weight: 500;
  line-height: 18px;
  white-space: nowrap;

  &.badge-capability {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);

    /* [v68 2026-08-28] 黑白灰简洁配色: 全部授予不再用绿色高亮, 改为深灰加粗区分 */
    &.badge-all-granted {
      background: var(--color-bg-tertiary, #f0f0f0);
      color: var(--color-text-primary, #262626);
      font-weight: 600;
    }
  }

  &.badge-scope {
    background: var(--color-bg-secondary);
    color: var(--color-text-tertiary);
  }
}

/* [2026-08-28 重构清理] 旧交互（动作分组按钮 / 详细权限列表 / 数据范围内联 /
   源标签）已迁移至 ResourceActionMatrix，对应样式随死代码一并删除 */

/* [FIX v62 2026-08-28] 浏览态视觉：
 *   旧实现对 disabled checkbox 一律 opacity: 0.55 + 卡片整体 opacity: 0.85,
 *   导致已勾选 vs 未勾选的视觉差异几乎消失（都是灰色小方块），
 *   用户保存后切回浏览态，看到所有菜单都像「已勾」，误以为「又自动勾上」。
 *   修复：
 *     - checkbox 始终保持高对比度（不调低 opacity）
 *     - 已勾选菜单：菜单名加粗 + 强调色
 *     - 未勾选菜单：菜单名弱化 + 灰色
 *     - 移除卡片整体 opacity（避免视觉降级过度）
 */
.menu-permission-matrix.mpm--readonly {
  .menu-card {
    cursor: default;

    &:hover {
      background: var(--color-bg-container, #fff);
      box-shadow: none;
    }

    /* [FIX v62] disabled checkbox 保持高对比度，不削弱勾选/未勾选差异 */
    input[type='checkbox']:disabled {
      cursor: not-allowed;
      /* 不再设 opacity: 0.55 —— 保留浏览器原生 disabled 但不被「二次淡」 */
    }

    /* [FIX v62] 已分配菜单：菜单名加粗 + 强调色 */
    &.is-assigned {
      .menu-name {
        color: var(--color-text-primary, #262626);
        font-weight: 600;
      }
    }

    /* [FIX v62] 未分配菜单：菜单名弱化 + 灰色 */
    &:not(.is-assigned):not(.is-partial):not(.is-folder) {
      .menu-name {
        color: var(--color-text-tertiary, #8c8c8c);
        font-weight: 400;
      }
      /* 弱化整体视觉权重 */
      .menu-badges {
        opacity: 0.5;
      }
    }
  }
}

.menu-permission-matrix.mpm--editing {
  .menu-card {
    input[type='checkbox']:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }
  }
}
</style>
