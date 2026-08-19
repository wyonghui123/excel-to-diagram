/**
 * 生成基于分组的布局代码
 * @param {Array} groups - 分组配置数组
 * @param {Array} containers - 容器数组（完整数据，包含 nodes）
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} overallDirection - 整体方向 ('TB' | 'LR' | 'BT' | 'RL')
 * @param {string} layoutEngine - 布局引擎 ('dagre' | 'elk')
 * @param {Array} links - 所有连线数据（用于 ELK 自动分组）
 * @returns {Object} { mermaidCode, styleLines }
 */
import { MAX_RECURSION_DEPTH, checkDepth, checkCycle, createVisitedSet } from '../../../services/groupModel/safetyUtils.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'
import { markUplift, hasShownDescendants } from './upliftDerivation.js'
import { extractOwnGroupName, collapseFormatMarker, getContainerMarkers, businessObjectLabel } from '../syntax/nodeLabelTemplate.js'

// [FIX 2026-08-06g] 上提自禁用父容器的子分组 → 父路径 registry (subgraphId → parentPath).
//   背景: 之前把父名称拼进容器标题 ("供应链计划（供应链云）"), formatContainerTitle 拆成两行,
//   与 ELK 布局"仅预留单行标签空间"冲突, 后处理下移内容又导致节点/子容器跑出容器盒, 方案废弃。
//   改为: 标题保持单行 (只显示自身名称), 父名称由 SVG 处理器转成 :hover tooltip 展示 ("父级：供应链云")。
//   模块级注册表在 generateGroupedLayout 每次调用时重置, processSvg 渲染后读取, 单图表场景安全。
const liftedParentRegistry = {}
function registerLiftedParent(subgraphId, parentPath) {
  liftedParentRegistry[subgraphId] = parentPath
}
export function getLiftedParentPathMap() {
  return { ...liftedParentRegistry }
}
function resetLiftedParentRegistry() {
  for (const key in liftedParentRegistry) delete liftedParentRegistry[key]
}

// [v1.1.15 回退] 颜色由用户/系统颜色配置控制, 不在样式表中硬编码
const LEVEL_STYLES = {
  1: { fill: '#f5f5f5', stroke: '#333333', strokeWidth: 1 },
  2: { fill: '#ffffff', stroke: '#333333', strokeWidth: 1 },
  3: { fill: '#f5f5f5', stroke: '#333333', strokeWidth: 1 },
  4: { fill: '#ffffff', stroke: '#333333', strokeWidth: 1 },
}

function getLevelStyle(level) {
  return LEVEL_STYLES[Math.min(level, 4)] || LEVEL_STYLES[4]
}

const getContainerLevelStyle = getLevelStyle
const getGroupLevelStyle = getLevelStyle

// [CUSTOM-COLOR 2026-08-19] 用户自定义分组(groupType='custom' 且非 ELK 系统自动分组)
//   使用面板配置的 group.style 着色 (fill/stroke/strokeWidth, getDefaultGroup 已带默认值,
//   之前被忽略). 容器(subgraph)与上提节点(COLLAPSE)都生效.
//   ELK 系统分组(_elkGroup)除外: 其 style 是 ELK 布局内部语义色, 不应在此应用.
function resolveCustomGroupColor(group) {
  if (!group) return null
  const isUserCustom = group.groupType === 'custom'
    && !(group._elkGroup === 'inner' || group._elkGroup === 'boundary')
  if (!isUserCustom || !group.style) return null
  const fill = group.style.fill
  const stroke = group.style.stroke || fill
  const strokeWidth = group.style.strokeWidth
  if (!fill) return null
  return { fill, stroke, strokeWidth, isCustom: true }
}

// [ELK-GROUP 2026-08-12] 识别"系统自动分组"(无关系/有关系, ELK 布局自动生成).
//   其 visible=false 表示"无边框但节点仍渲染"(ELK 布局语义), 与普通分组 visible=false
//   (隐藏整棵子树) 不同, 渲染时需特殊处理.
function isElkSystemAuto(group) {
  return !!group && (group._elkGroup === 'inner' || group._elkGroup === 'boundary')
}

// [ELK-FLAT 2026-08-14] 收集 ELK 系统自动分组渲染出的节点 id, **按分组**收集.
//   背景: ELK 分组 (inner/boundary) 内互不连通的节点会被 ELK 一字排开 (实测 INV boundary
//   27 节点单行 5447px / 58 节点单行 11737px), 撑乱整个服务模块. 故收集这些节点,
//   由调用方生成"布局辅助虚拟边" (透明不可见), 引导 ELK 把它们排成多列紧凑网格.
//   [ELK-SEM 2026-08-14] 按分组收集: 每个 ELK 分组 (inner/boundary) 单独一组,
//   虚拟边只在组内连接 (buildLayoutHelperEdges 逐组切片). 若全局混收, 切片会跨分组
//   连接不同 subgraph 内的节点 → 虚拟边跨容器 → 破坏 ELK 布局.
//   模块级状态在 generateGroupedLayout 每次调用时重置, 单图表场景安全.
let flatElkGroups = []
let elkCollectorStack = []
function resetFlatElkGroups() {
  flatElkGroups = []
  elkCollectorStack = []
}
// 开始收集一个 ELK 分组的节点 (该分组渲染期间压入栈, 结束后弹栈).
function beginElkCollector() {
  const collector = []
  elkCollectorStack.push(collector)
  flatElkGroups.push(collector)
}
function collectElkFlatNode(actualNodeId) {
  const top = elkCollectorStack[elkCollectorStack.length - 1]
  if (top) top.push(actualNodeId)
}
function endElkCollector() {
  elkCollectorStack.pop()
}
/**
 * 根据打平的 ELK 分组节点列表生成布局辅助虚拟边 (链式切片).
 * 每条链内节点按顺序两两相连 → ELK 将每条链视为独立连通分量 (component),
 * TB 方向下多个 component 横向并列 → 整体呈"多列×每列 N 行"的紧凑网格.
 * 链长 CHAIN_SIZE 决定列数与每列行数 (58 节点 / 12 ≈ 5 列 × 12 行).
 * [ELK-FLAT 2026-08-14] 导出以便单测直接验证链式切片行为.
 */
export function buildLayoutHelperEdges(nodeIds) {
  const edges = []
  if (!nodeIds || nodeIds.length < 2) return edges
  const CHAIN_SIZE = 12
  for (let i = 0; i < nodeIds.length; i += CHAIN_SIZE) {
    const chain = nodeIds.slice(i, i + CHAIN_SIZE)
    for (let j = 0; j < chain.length - 1; j++) {
      edges.push({ source: chain[j], target: chain[j + 1] })
    }
  }
  return edges
}

/**
 * [OPT 2026-08-06] 上提(脱离父容器)分组标题的祖先名称路径.
 * 仅当分组被上提为聚合节点 (脱离其父容器) 时返回祖先路径, 用于在标题中追加
 * "（祖父名称/父名称）" 以直观标识容器层级. 采用名称而非编码.
 * - submodule/subServiceModule (服务模块): 路径 = 领域/子领域 (grandparent/parent)
 * - module/subDomain        (子领域):     路径 = 领域 (parent)
 * - 其它 (领域/自定义):                    无上提祖先路径
 *
 * [FIX 2026-08-06] 优先用 group.info (BO 图路径已填充 type/grandparent/parent);
 *   布局分组 (layoutControlConfig.groups) 的 info 可能为 null, 此时回退用
 *   group.groupType + 祖先名链 (ancestorNames, 由 generateGroupCode 递归透传) 推导,
 *   保证上提容器标题始终能显示祖先名称路径.
 *
 * @param {Object} group 分组对象 (含 group.info / group.groupType)
 * @param {string[]} [ancestorNames] 祖先分组标题链 (根 → 直属父)
 * @returns {string} 祖先路径字符串 (如 "供应链云/供应链计划"), 无则返回 ''
 */
function buildUpliftAncestorPath(group, ancestorNames = []) {
  const info = group.info || {}
  if (info.type === 'submodule') {
    if (info.grandparent && info.parent) return `${info.grandparent}/${info.parent}`
    if (info.grandparent) return info.grandparent
    if (info.parent) return info.parent
    return ''
  }
  if (info.type === 'module') {
    return info.parent || ''
  }
  // [FIX 2026-08-06] info 缺失时回退: 从祖先链 + groupType 推导
  const names = ancestorNames || []
  const type = group.groupType
  if (type === 'serviceModule') {
    if (names.length >= 2) return `${names[names.length - 2]}/${names[names.length - 1]}`
    return names[names.length - 1] || ''
  }
  if (type === 'subDomain') {
    return names[names.length - 1] || ''
  }
  return ''
}

export function generateGroupedLayout(groups, containers, nodeMap, definedNodes, overallDirection = 'TB', layoutEngine = 'dagre', links = []) {
  if (!groups || groups.length === 0) {
    return { mermaidCode: '', styleLines: [] }
  }

  const styleLines = []
  let mermaidCode = '\n%% 分组布局\n'

  // [FIX 2026-08-06g] 每次生成前重置父路径 registry, 避免跨次渲染残留.
  resetLiftedParentRegistry()
  // [ELK-FLAT 2026-08-14] 每次生成前重置 ELK 分组节点收集, 避免跨次渲染残留.
  resetFlatElkGroups()

  // [UPLIFT 2026-08-05] 上提自动推导: 基于 enabled 标记 _uplift (enabled 且无可见子孙 → 聚合节点).
  markUplift(groups)

  const reversedGroups = [...groups].reverse()

  reversedGroups.forEach((group, index) => {
    const groupIndex = index + 1
    
    const result = generateGroupCode(group, containers, nodeMap, definedNodes, 0, groupIndex, createVisitedSet(), layoutEngine, links, 0, [])
    if (result.code) {
      mermaidCode += result.code
      styleLines.push(...result.styleLines)
    }
  })

  // [ELK-SEM 2026-08-14] 逐组生成虚拟边 (每组内链式连接), 合并为平铺数组.
  return { mermaidCode, styleLines, layoutHelperEdges: flatElkGroups.flatMap((group) => buildLayoutHelperEdges(group)) }
}

/**
 * 检查分组是否有内容
 */
function hasGroupContent(group, containers, visited = null, depth = 0) {
  if (!group) {
    return false
  }

  // [VIS 2026-08-07] 可见/隐藏: visible=false → 视为无内容, 父级据此不渲染空盒.
  //   与 generateGroupCode 顶部"visible=false 跳过整棵子树"保持一致.
  // [ELK-GROUP 2026-08-12] 系统自动分组(无关系/有关系)是例外: 其 visible=false
  //   表示"无边框但节点仍渲染"(ELK 布局语义), 不属用户隐藏, 仍视为有内容.
  if (group.visible === false && !isElkSystemAuto(group)) {
    return false
  }

  // [UPLIFT 2026-08-05] 上提即内容: 分组被标记 _uplift=true (enabled 且无可见子孙 →
  //   渲染为 COLLAPSE_<id> 聚合节点). 该标记由 generateGroupedLayout 顶部 markUplift 推导,
  //   必须在此视为"有内容", 否则空内容分组被剪除后, 父级 hasGroupContent 级联返回 false,
  //   导致"仅服务模块"模板下整个图塌缩为只输出 %% 分组布局 (无节点).
  if (group._uplift === true) {
    return true
  }
  
  // 对于 disabled 的分组，不显示（返回 false）
  // 但如果分组有 disabled 祖先路径（_disabledAncestorPath），说明它是被提升的，应该显示
  // [FIX 2026-08-19] disabled 分组对父级而言是否"有内容": 若其子孙仍会渲染
  //   (上浮打平到父级, 见 generateGroupCode 禁用分支), 则视为有内容.
  //   原逻辑恒返回 false → 父级 hasGroupContent 级联 false → 父级被整体跳过 →
  //   禁用子领域后整个图表塌缩 (所有 BO 顶层回填). 修复: 返回 hasShownDescendants.
  if (group.enabled === false) {
    if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
    } else {
      return hasShownDescendants(group)
    }
  }

  const groupEnabled = group.enabled !== false
  
  if (!checkDepth(depth, 'GroupLayout.hasGroupContent')) {
    return false
  }
  
  if (!visited) {
    visited = createVisitedSet()
  }
  
  if (group.id && checkCycle(group.id, visited, 'GroupLayout.hasGroupContent')) {
    return false
  }

  if (group.directNodes && group.directNodes.length > 0) {
    return true
  }

  if (group.containers && group.containers.length > 0) {
    const hasValidContainers = group.containers.some((containerData, idx) => {
      // 跳过 disabled 的容器
      const containerEnabled = containerData?.enabled !== false
      if (containerData?.enabled === false) {
        return false
      }
      if (typeof containerData === 'object' && containerData !== null) {
        if (containerData.nodes && containerData.nodes.length > 0) {
          return true
        }
        if (containerData.id || containerData.name || containerData.fullTitle) {
          return true
        }
      }
      const container = resolveContainer(containerData, containers)
      const result = container && container.nodes && container.nodes.length > 0
      return result
    })
    if (hasValidContainers) {
      return true
    }
  }

  if (group.children && group.children.length > 0) {
    const hasChildren = group.children.some((childId, idx) => {
      // childId 可能是字符串 ID 或分组对象
      const child = typeof childId === 'string' ? null : childId  // 字符串 ID 无法解析，暂时返回 false
      if (!child) {
        return false
      }
      return hasGroupContent(child, containers, visited, depth + 1)
    })
    if (hasChildren) {
      return true
    }
  }

  return false
}

/**
 * 生成单个分组的代码
 * @param {string} layoutEngine - 布局引擎 ('dagre' | 'elk')
 * @param {Array} links - 所有连线数据
 * @param {number} containerDepth - 容器嵌套层次（基于实际创建的 subgraph）
 */
function generateGroupCode(group, containers, nodeMap, definedNodes, depth = 0, groupIndex = 1, visited = null, layoutEngine = 'dagre', links = [], containerDepth = 0, ancestorNames = [], liftedFromDisabledParent = null) {
  const styleLines = []
  let code = ''

  // [v1.1.15 cleanup] 移除调试 console.log

  if (!group) {
    return { code, styleLines }
  }

  if (!checkDepth(depth, 'GroupLayout.generateGroupCode')) {
    return { code, styleLines }
  }

  if (!visited) {
    visited = createVisitedSet()
  }

  if (group.id && checkCycle(group.id, visited, 'GroupLayout.generateGroupCode')) {
    return { code, styleLines }
  }

  // [VIS 2026-08-07] 可见/隐藏: visible=false → 整棵子树不渲染 (增量隐藏, 留空位).
  //   旧实现 (下方 L372-397) 只把 subgraph 标题置空 "[ ]" 却仍渲染子节点/子容器,
  //   导致"隐藏父领域(如供应链云)"后其子领域(如销售)仍显示, 与面板
  //   "隐藏（含子孙）" 的级联语义不符. 此处直接跳过整棵子树, 子孙由
  //   setVisibleRecursive 已一并置为 false, 递归调用自然被此处拦截.
  // [ELK-GROUP 2026-08-12] 系统自动分组(无关系/有关系)是例外: 其 visible=false
  //   表示"无边框但节点仍渲染"(ELK 布局语义), 落到下方 enabled 分支渲染为无边框 subgraph,
  //   不隐藏整棵子树, 否则默认 hidden 状态下 BO 会全部消失.
  if (group.visible === false && !isElkSystemAuto(group)) {
    return { code, styleLines }
  }

  const hasContent = hasGroupContent(group, containers)
  const groupEnabled = group.enabled !== false

  // [FIX 2026-08-04] 禁用分组有 children/containers 时不能提前返回:
  //   hasGroupContent 对 disabled 分组恒返回 false (见上方 L63-68), 但 disabled 分支
  //   (下方 L170-250) 的职责正是"打平子元素到当前层级". 若在此提前返回, disabled 父域
  //   的 children (子领域) 会被完全跳过 → 禁用供应链云后子领域也消失.
  // 仅当 disabled 分组既无 directNodes 也无 children/containers 时才跳过.
  // [FIX 2026-08-19 修订] 空分组(含 custom)已由 computeUplift 统一上提为聚合节点,
  //   hasGroupContent 对 _uplift 短路返回 true, 不会走到此处 → 无需 custom 豁免.
  if (!hasContent && !group.directNodes) {
    const hasFlattenableContent = !groupEnabled &&
      ((group.children && group.children.length > 0) ||
       (group.containers && group.containers.length > 0))
    if (!hasFlattenableContent) {
      return { code, styleLines }
    }
  }

  const indent = '  '.repeat(depth)
  // 保留 Unicode 字符（包括中文），只替换特殊字符
  const safeId = group.id.replace(/[^\w\u4e00-\u9fff]/g, '_')
  const groupId = `G_${safeId}`
  // [FIX 2026-08-06g] 被禁用父容器打平提升的子分组, 标题保持单行 (只显示自身名称如 "供应链计划").
  //   父名称不再拼进标题 (原 "供应链计划（供应链云）" 会被 formatContainerTitle 拆成两行, 与 ELK
  //   单行预留空间冲突 → 后处理下移内容导致节点/子容器跑出容器盒)。父名称改由 :hover tooltip
  //   展示, 记录进 registry (subgraphId → 父title), SVG 处理器读取后挂 tooltip。
  const groupMarkers = getContainerMarkers(group.type || group.groupType)
  const baseTitle = formatContainerTitle(extractOwnGroupName(group.title) || 'Group')
  const groupTitle = groupMarkers
    ? `${groupMarkers[0]}${baseTitle}${groupMarkers[1]}`
    : baseTitle
  if (liftedFromDisabledParent) {
    registerLiftedParent(groupId, liftedFromDisabledParent)
  }

  // [UPLIFT 2026-08-05] 上提语义: 分组 enabled 且无任何可见子孙时, 自动上提为单个聚合节点,
  //   子孙 (directNodes/containers/children) 全部隐藏, 不创建 subgraph. 取代显式 collapsed.
  //   标记由 generateGroupedLayout 顶部 markUplift 推导写入 group._uplift.
  const groupUplift = group._uplift === true
  if (groupUplift) {
    const collapseId = `COLLAPSE_${safeId}`
    if (!definedNodes.has(collapseId)) {
      // [FIX 2026-08-06] 末端叶子(上提聚合节点)标题: 优先展示自身编码 (如 "库存优化\n（SNPIO）"),
      //   而非祖先路径。原因: (1) 长祖先路径 "（供应链云/供应链计划）…" 超出节点宽度会被
      //   相邻元素遮挡; (2) 子节点折叠后该元素成为终端叶子, 应展示自身编码以标识对象。
      //   若分组无编码 (elementCode/code 缺失, 如单测构造), 回退祖先路径。
      //   用 \n 转义 (mermaid 节点标签), 使多行文本正确换行且节点高度自适应.
      const ownCode = group.elementCode || group.code || ''
      const ancestorPath = buildUpliftAncestorPath(group, ancestorNames)
      // [TITLE 2026-08-09] 折叠节点标题: 领域/子领域/服务模块 名称置于标记内, 类型+编码置下方
      //   (如 "<供应链云>\n领域 SCM"、"<供应链计划>\n子领域 SCP"、"[需求计划]\n服务模块 DP").
      //   编码缺失时回退原有 "(编码)"/祖先路径 格式; 业务对象不经过此路径, 保持原样.
      const marker = collapseFormatMarker(group.type || group.groupType, ownCode, group.title || 'Group')
      const displayText = marker
        ? marker
        : ownCode
          ? `${group.title || 'Group'}\\n（${ownCode}）`
          : ancestorPath
            ? `${group.title || 'Group'}\\n（${ancestorPath}）…`
            // [FIX 2026-08-19] 空自定义分组自动上提的节点不带省略号: 空分组无可展开内容,
            //   "…" 是"折叠容器, 可展开"的暗示, 对空节点有误导. 仅显式折叠(collapsed=true)
            //   才保留 (此时表明确实有内容待展开). 系统分组走 marker 分支, 不落此兜底.
            : group.collapsed === true
              ? `${groupTitle}…`
              : `${groupTitle}`
      code += `${indent}${collapseId}["${displayText}"]:::collapseNode\n`
      definedNodes.add(collapseId)
      // [CUSTOM-COLOR 2026-08-19] 自定义分组上提节点用面板配置色 (style), 容器/节点同源
      const customColor = resolveCustomGroupColor(group)
      if (customColor) {
        code += `${indent}style ${collapseId} fill:${customColor.fill},stroke:${customColor.stroke}\n`
      }
    }
    return { code, styleLines }
  }

  // [ELK-GROUP 2026-08-14] ELK 系统分组 (无关系/有关系) 默认 visible=false 无边框.
  //   [ELK-SEM 2026-08-14] 语义对齐 (用户确认): enabled=true 的 ELK 分组**必须始终创建
  //   subgraph 容器**, visible=false 仅表示"容器在但无边框/无标题" (隐藏不影响容器渲染),
  //   不再复用 disabled 打平分支. 原实现 `!groupEnabled || (isElkAuto && visible===false)`
  //   把启用+隐藏的 ELK 分组与禁用走同一打平分支 → 容器被删除 → 视觉与禁用完全一致
  //   ("隐藏态污染启用" 用户反馈的 bug). 打平分支现在仅用于 enabled=false (禁用: 无容器).
  //   [ELK-FLAT 2026-08-14] 无边框 subgraph 内互不连通的节点会被 ELK 一字排开 (INV boundary
  //   27 节点单行 5447px / 58 节点单行 11737px), 故无论打平 (禁用) 还是 subgraph (启用)
  //   分支, 渲染 ELK 分组节点时都按分组收集节点 id, 由调用方生成透明虚拟边引导 ELK
  //   排成多列网格 (见 buildLayoutHelperEdges).
  const isElkAuto = isElkSystemAuto(group)
  if (!groupEnabled) {
    // 禁用的分组：不再创建 subgraph，直接渲染子元素到当前层级
    // 这样 ELK 布局时不会把它们当作一个分组容器来计算间距

    if (isElkAuto) beginElkCollector()
    const collectFlatNode = (actualNodeId) => {
      if (isElkAuto) collectElkFlatNode(actualNodeId)
    }

    if (group.directNodes && group.directNodes.length > 0 && nodeMap && nodeMap.size > 0) {
      const reversedNodes = [...group.directNodes].reverse()
      reversedNodes.forEach(nodeId => {
        const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
        if (!definedNodes.has(actualNodeId)) {
          const node = nodeMap.get(actualNodeId)
          if (node) {
            const displayText = businessObjectLabel(node)
            code += `${indent}${actualNodeId}["${displayText}"]\n`
            definedNodes.add(actualNodeId)
            collectFlatNode(actualNodeId)
          }
        }
      })
    }

    if (group.containers && group.containers.length > 0) {
      const reversedContainers = [...group.containers].reverse()
      reversedContainers.forEach((containerData, idx) => {
        if (containerData._isDirectNodesContainer) {
          if (containerData.nodes && containerData.nodes.length > 0) {
            containerData.nodes.forEach(nodeId => {
              const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
              if (!definedNodes.has(actualNodeId)) {
                const node = nodeMap.get(actualNodeId)
                if (node) {
                  const displayText = businessObjectLabel(node)
                  code += `${indent}${actualNodeId}["${displayText}"]\n`
                  definedNodes.add(actualNodeId)
                  collectFlatNode(actualNodeId)
                }
              }
            })
          }
          return
        }

        const container = resolveContainer(containerData, containers)
        if (!container) {
          return
        }
        if (container && container.nodes && container.nodes.length > 0) {
          // [PROVIDER 2026-08-04] 容器级可见/禁用：enabled=false 或 visible=false 时
          //   容器边框不显示，节点打平渲染（外提）。enabled 语义与既有行为一致。
          const containerEnabled = container.enabled !== false
          const containerVisible = container.visible !== false
          if (containerEnabled && containerVisible) {
            const containerId = `${groupId}_C${idx + 1}`
            const containerCode = generateContainerCode(container, idx, nodeMap, definedNodes, indent, containerId, layoutEngine, links, containerDepth + 1)
            code += containerCode
          } else {
            container.nodes.forEach(nodeId => {
              const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
              if (!definedNodes.has(actualNodeId)) {
                const node = nodeMap.get(actualNodeId)
                if (node) {
                  const displayText = businessObjectLabel(node)
                  code += `${indent}${actualNodeId}["${displayText}"]\n`
                  definedNodes.add(actualNodeId)
                  collectFlatNode(actualNodeId)
                }
              }
            })
          }
        }
      })
    }

    if (group.children && group.children.length > 0) {
      const reversedChildren = [...group.children].reverse()
      let childGroupIndex = groupIndex * 10
      reversedChildren.forEach((childGroup) => {
        childGroupIndex++
        // [FIX 2026-08-06] 父容器 disabled 时, 子分组被打平提升到当前层级.
        //   把被禁用父分组名 (group.title) 作为 liftedFromDisabledParent 传给子分组,
        //   使其 subgraph 标题追加父名称 (如 供应链计划 → "供应链计划（供应链云）").
        const childResult = generateGroupCode(childGroup, containers, nodeMap, definedNodes, depth, childGroupIndex, visited, layoutEngine, links, containerDepth, [...ancestorNames, group.title], group.title)
        if (childResult.code) {
          code += childResult.code
          styleLines.push(...childResult.styleLines)
        }
      })
    }

    if (isElkAuto) endElkCollector()
    return { code, styleLines }
  }

  // [ELK-SEM 2026-08-14] ELK 分组 (enabled=true) 进入 subgraph 分支: 开始收集组内节点
  //   (visible=false 无边框 subgraph 内节点需虚拟边防单行; visible=true 有边框同样收集,
  //   透明边仅增强约束, 无副作用).
  if (isElkAuto) beginElkCollector()

  if (group.visible === false) {
    code += `${indent}subgraph ${groupId}[ ]\n`
  } else {
    code += `${indent}subgraph ${groupId}["${groupTitle}"]\n`
  }

  let direction = group.direction || 'TB'
  code += `${indent}direction ${direction}\n`

  const isVisible = group.visible !== false
  const nextContainerDepth = isVisible ? containerDepth + 1 : containerDepth

  if (group.directNodes && group.directNodes.length > 0 && nodeMap && nodeMap.size > 0) {
    const reversedNodes = [...group.directNodes].reverse()
    reversedNodes.forEach(nodeId => {
      const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
      if (!definedNodes.has(actualNodeId)) {
        const node = nodeMap.get(actualNodeId)
        if (node) {
          const displayText = businessObjectLabel(node)
            code += `${indent}  ${actualNodeId}["${displayText}"]:::node\n`
          definedNodes.add(actualNodeId)
          if (isElkAuto) collectElkFlatNode(actualNodeId)
        }
      }
    })
  }

  if (group.containers && group.containers.length > 0) {
    const reversedContainers = [...group.containers].reverse()
    const containerCodes = []
    const containerNodePairs = [] // 保存每个容器的(第一个节点ID, 最后一个节点ID)

    reversedContainers.forEach((containerData, idx) => {
      if (containerData._isDirectNodesContainer) {
        if (containerData.nodes && containerData.nodes.length > 0) {
          let firstNode = null
          let lastNode = null
          containerData.nodes.forEach(nodeId => {
            const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
            if (!firstNode) firstNode = actualNodeId
            lastNode = actualNodeId
            if (!definedNodes.has(actualNodeId)) {
              const node = nodeMap.get(actualNodeId)
              if (node) {
                const displayText = businessObjectLabel(node)
                code += `${indent}  ${actualNodeId}["${displayText}"]\n`
                definedNodes.add(actualNodeId)
                if (isElkAuto) collectElkFlatNode(actualNodeId)
              }
            }
          })
          if (firstNode && lastNode) {
            containerNodePairs.push({ first: firstNode, last: lastNode })
          }
        }
        return
      }

      const container = resolveContainer(containerData, containers)

      // [v1.1.15 修复] BO 图表中 SubDomain 容器有 nested containers (SM) 但没有 nodes
      //   旧逻辑: resolveContainer 找不到 SubDomain (lookup table 只有 SM), 整个被 skip
      //   修复: 当 containerData 有 nested containers 时, 手动生成外层 wrapper + 递归处理嵌套容器
      //         避免调用完整 generateGroupCode 造成双重 wrapper
      if ((!container || !container.nodes || container.nodes.length === 0) &&
          containerData && typeof containerData === 'object' &&
          containerData.containers && containerData.containers.length > 0 &&
          !containerData._isDirectNodesContainer) {
        // 容器包含子容器但自身没有 BO 节点 (例如 SubDomain 包含 SM 但没有自己的 BO)
        // 手动生成外层 subgraph wrapper, 内部递归处理 nested containers
        const subGroupId = `G${groupIndex}_C${idx + 1}`
        const subDirection = containerData.direction || 'TB'
        const subIndent = indent
        const subInnerIndent = indent + '  '
        let innerCode = ''

        containerData.containers.forEach((nestedContainer, nIdx) => {
          const nestedResolved = resolveContainer(nestedContainer, containers)
          if (nestedResolved && nestedResolved.nodes && nestedResolved.nodes.length > 0) {
            if (nestedResolved.enabled === false) {
              // disabled 嵌套容器: 仅外提节点
              nestedResolved.nodes.forEach(nodeId => {
                const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
                if (!definedNodes.has(actualNodeId)) {
                  const node = nodeMap.get(actualNodeId)
                  if (node) {
                    const displayText = businessObjectLabel(node)
                    innerCode += `${subInnerIndent}${actualNodeId}["${displayText}"]\n`
                    definedNodes.add(actualNodeId)
                  }
                }
              })
            } else {
              const nestedId = `G${groupIndex * 10 + idx + 1}_C${nIdx + 1}`
              const nestedCode = generateContainerCode(nestedResolved, nIdx, nodeMap, definedNodes, subInnerIndent, nestedId, layoutEngine, links, nextContainerDepth + 2)
              innerCode += nestedCode
              // 嵌套容器的 first/last node pair (用于 edge 排序)
              const firstNodeId = nestedResolved.nodes[0]
              const firstNodeIdStr = typeof firstNodeId === 'string' ? firstNodeId : (firstNodeId.id || firstNodeId.code || firstNodeId.name)
              const lastNodeId = nestedResolved.nodes[nestedResolved.nodes.length - 1]
              const lastNodeIdStr = typeof lastNodeId === 'string' ? lastNodeId : (lastNodeId.id || lastNodeId.code || lastNodeId.name)
              containerNodePairs.push({ first: firstNodeIdStr, last: lastNodeIdStr })
            }
          }
        })

        // 用外层 wrapper 包装
        let wrappedSubCode = `${subIndent}subgraph ${subGroupId}["${containerData.title || containerData.name}"]\n${subIndent}  direction ${subDirection}\n`
        wrappedSubCode += innerCode
        wrappedSubCode += `${subIndent}end\n`
        containerCodes.push(wrappedSubCode)
        return
      }

      if (container && container.nodes && container.nodes.length > 0) {
        // [v32 修复 2026-06-13] 跳过 disabled 容器, 与 disabled group 分支行为一致
        // [LAYOUT 2026-08-04] 容器 visible=false 同样打平渲染 (不显示边框), 与 disabled 语义一致
        if (container.enabled === false || container.visible === false) {
          // disabled/不可见 容器: 不创建 subgraph, 仅外提节点
          container.nodes.forEach(nodeId => {
            const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
            if (!definedNodes.has(actualNodeId)) {
              const node = nodeMap.get(actualNodeId)
              if (node) {
                const displayText = businessObjectLabel(node)
                code += `${indent}  ${actualNodeId}["${displayText}"]\n`
                definedNodes.add(actualNodeId)
              }
            }
          })
          return
        }
        const containerId = `G${groupIndex}_C${idx + 1}`
        const containerCode = generateContainerCode(container, idx, nodeMap, definedNodes, indent, containerId, layoutEngine, links, nextContainerDepth + 1)
        containerCodes.push(containerCode)

        // 收集容器内的第一个和最后一个节点ID
        const firstNodeId = container.nodes[0]
        const firstNodeIdStr = typeof firstNodeId === 'string' ? firstNodeId : (firstNodeId.id || firstNodeId.code || firstNodeId.name)
        const lastNodeId = container.nodes[container.nodes.length - 1]
        const lastNodeIdStr = typeof lastNodeId === 'string' ? lastNodeId : (lastNodeId.id || lastNodeId.code || lastNodeId.name)
        containerNodePairs.push({ first: firstNodeIdStr, last: lastNodeIdStr })
      }
    })

    containerCodes.forEach(cc => {
      code += cc
    })
  }

  if (group.children && group.children.length > 0) {
    const reversedChildren = [...group.children].reverse()
    let childGroupIndex = groupIndex * 10
    reversedChildren.forEach((childGroup) => {
      childGroupIndex++
      const childResult = generateGroupCode(childGroup, containers, nodeMap, definedNodes, depth + 1, childGroupIndex, visited, layoutEngine, links, nextContainerDepth, [...ancestorNames, group.title])
      if (childResult.code) {
        code += childResult.code
        styleLines.push(...childResult.styleLines)
      }
    })
  }

  code += `${indent}end\n`

  const styleCode = generateGroupStyle(group, groupId, nextContainerDepth)
  styleLines.push(styleCode)

  // [ELK-SEM 2026-08-14] 结束本 ELK 分组的节点收集 (与上方 beginElkCollector 配对).
  if (isElkAuto) endElkCollector()

  return { code, styleLines }
}

/**
 * 解析容器数据
 */
function resolveContainer(containerData, containers) {
  if (typeof containerData === 'object' && containerData !== null) {
    if (containerData.nodes && containerData.nodes.length > 0) {
      return containerData
    }

    if (!containers || containers.length === 0) {
      return null
    }

    const found = containers.find(c => {
      const match = c.id === containerData.id ||
             (containerData.elementCode && c.elementCode === containerData.elementCode) ||
             c.name === containerData.name ||
             c.fullTitle === containerData.fullTitle ||
             (containerData.code && c.elementCode === containerData.code) ||
             (containerData.elementCode && c.code === containerData.elementCode)
      return match
    })
    
    if (found) {
      const result = { ...found }
      if (containerData.direction) {
        result.direction = containerData.direction
      }
      return result
    }
    return null
  }

  if (!containers || containers.length === 0) {
    return null
  }

  if (typeof containerData === 'number') {
    return containers[containerData] || null
  }

  if (typeof containerData === 'string') {
    return containers.find(c => c.id === containerData || c.name === containerData) || null
  }

  return null
}

/**
 * 生成容器 subgraph 代码
 * @param {Object} container - 容器对象
 * @param {number} index - 容器索引
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} indent - 缩进
 * @param {string} containerId - 容器ID
 * @param {string} layoutEngine - 布局引擎
 * @param {Array} links - 所有连线数据
 * @param {number} containerDepth - 容器嵌套层次
 */
function generateContainerCode(container, index, nodeMap, definedNodes, indent = '', containerId = null, layoutEngine = 'dagre', links = [], containerDepth = 1) {
  let code = ''

  // 虚拟容器直接渲染节点，不创建 subgraph
  if (container.isVirtual) {
    if (container.nodes && container.nodes.length > 0 && nodeMap && nodeMap.size > 0) {
      container.nodes.forEach(nodeData => {
        const nodeId = typeof nodeData === 'string' ? nodeData : (nodeData.id || nodeData.code || nodeData.name)
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = businessObjectLabel(node)
            code += `${indent}${nodeId}["${displayText}"]\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}${nodeId}\n`
        }
      })
    }
    return code
  }

  // [FOLD 2026-08-05] 容器级折叠 (FR-002): container collapsed=true 时折叠为单个聚合节点,
  //   隐藏其 nodes/containers, 不创建 subgraph.
  if (container.collapsed === true) {
    const colId = container.elementRef?.code
      ? `COLLAPSE_SM_${String(container.elementRef.code).replace(/[^\w\u4e00-\u9fff]/g, '_')}`
      : `COLLAPSE_C${index + 1}`
    if (definedNodes && !definedNodes.has(colId)) {
      // [TITLE 2026-08-09] 容器级折叠节点: 若识别出类型/编码则按层级类型附加标记标题
      //   (名称置标记内, 类型+编码置下方, 如 "[需求计划]\n服务模块 DP"),
      //   否则保留原标题格式 (末尾加省略号).
      const containerCode = container.elementRef?.code || container.code || ''
      const containerType = container.type || container.groupType || container.elementRef?.type
      const rawContainerTitle = container.fullTitle || container.name || container.title || 'Container'
      const simpleName = container.name || container.title || rawContainerTitle
      const marker = collapseFormatMarker(containerType, containerCode, simpleName)
      const colTitle = marker
        ? marker
        : `${formatContainerTitle(rawContainerTitle)}…`
      code += `${indent}${colId}["${colTitle}"]:::collapseNode\n`
      definedNodes.add(colId)
    }
    return code
  }

  const actualContainerId = containerId || `C${index + 1}`
  // 如果容器有 fullTitle（包含完整路径，如 "财务云 / 费控服务"），说明它是 disabled 域的容器
  // 使用 fullTitle 而不是 name，这样会显示完整路径
  const rawContainerName = container.fullTitle || container.name || container.title || 'Container'
  const containerName = formatContainerTitle(rawContainerName)
  
  code += `${indent}  subgraph ${actualContainerId}["${containerName}"]\n`

  // 注意：当容器内节点有外部连线时，此 direction 设置会被 ELK 忽略
  // 容器会继承父图的方向。这是 Mermaid + ELK 的已知限制。
  const containerDirection = container.direction || 'LR'
  code += `${indent}    direction ${containerDirection}\n`

  // 收集此容器中的有效节点ID
  const containerNodeIds = []
  if (container.nodes && container.nodes.length > 0 && nodeMap && nodeMap.size > 0) {
    container.nodes.forEach(nodeData => {
      const nodeId = typeof nodeData === 'string' ? nodeData : (nodeData.id || nodeData.code || nodeData.name)
      containerNodeIds.push(nodeId)
    })
  }

  // ELK 自动分组：将有/无外部连线的节点分离
  if (layoutEngine === 'elk' && links && links.length > 0 && containerNodeIds.length > 1) {
    const containerNodeSet = new Set(containerNodeIds)
    const nodesWithExternalLinks = new Set()
    
    for (const link of links) {
      const sourceInContainer = containerNodeSet.has(link.source)
      const targetInContainer = containerNodeSet.has(link.target)
      
      // 如果只有一个端点在当前容器，则该节点有外部连线
      if (sourceInContainer && !targetInContainer) {
        nodesWithExternalLinks.add(link.source)
      }
      if (targetInContainer && !sourceInContainer) {
        nodesWithExternalLinks.add(link.target)
      }
    }

    const innerNodes = containerNodeIds.filter(n => !nodesWithExternalLinks.has(n))
    const boundaryNodes = containerNodeIds.filter(n => nodesWithExternalLinks.has(n))

    // 只有当两组都有节点时才分离
    if (innerNodes.length > 0 && boundaryNodes.length > 0) {
      // 生成内部节点子容器（无外部连线，方向会被尊重）
      code += `${indent}    subgraph ${actualContainerId}_inner[" "]\n`
      code += `${indent}      direction ${containerDirection}\n`
      innerNodes.forEach(nodeId => {
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = businessObjectLabel(node)
            code += `${indent}      ${nodeId}["${displayText}"]:::node\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}      ${nodeId}\n`
        }
      })
      code += `${indent}    end\n`
      code += `${indent}    style ${actualContainerId}_inner fill:none,stroke:none\n`

      // 生成边界节点子容器（有外部连线）
      code += `${indent}    subgraph ${actualContainerId}_boundary[" "]\n`
      code += `${indent}      direction ${containerDirection}\n`
      boundaryNodes.forEach(nodeId => {
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = businessObjectLabel(node)
            code += `${indent}      ${nodeId}["${displayText}"]:::node\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}      ${nodeId}\n`
        }
      })
      code += `${indent}    end\n`
      code += `${indent}    style ${actualContainerId}_boundary fill:none,stroke:none\n`

      code += `${indent}  end\n`
      return code
    }
  }

  // 默认处理：不分离节点
  if (containerNodeIds.length > 0) {
    const reversedNodes = [...containerNodeIds].reverse()
    reversedNodes.forEach(nodeId => {
      if (definedNodes && !definedNodes.has(nodeId)) {
        const node = nodeMap.get(nodeId)
        if (node) {
          const displayText = businessObjectLabel(node)
          code += `${indent}    ${nodeId}["${displayText}"]:::node\n`
          definedNodes.add(nodeId)
        }
      } else if (definedNodes) {
        code += `${indent}    ${nodeId}\n`
      }
    })
  }

  code += `${indent}  end\n`

  const levelStyle = getContainerLevelStyle(containerDepth)
  code += `${indent}  style ${actualContainerId} fill:${levelStyle.fill},stroke:${levelStyle.stroke},stroke-width:${levelStyle.strokeWidth}\n`

  return code
}

/**
 * 生成分组样式代码
 * @param {Object} group - 分组对象
 * @param {string} groupId - 分组ID
 * @param {number} containerDepth - 容器嵌套层次
 */
function generateGroupStyle(group, groupId, containerDepth = 1) {
  // [FIX 2026-08-19] 用 group.visible === false 判断 (与 generateGroupCode 隐藏语义一致):
  //   原 `!group.visible` 会把 visible 未定义(undefined)的分组也当隐藏 → 着透明色,
  //   导致新建自定义分组容器无色/透明 (getDefaultGroup 虽设 visible:true, 但防御训练不可靠).
  if (group.visible === false) {
    return `style ${groupId} fill:none,stroke:none\n`
  }

  // [CUSTOM-COLOR 2026-08-19] 用户自定义分组用面板配置色 (resolveCustomGroupColor),
  //   优先于按层级 LEVEL_STYLES; 其余系统分组保持原逻辑不变.
  const custom = resolveCustomGroupColor(group)
  if (custom) {
    return `style ${groupId} fill:${custom.fill},stroke:${custom.stroke},stroke-width:${custom.strokeWidth || 2}\n`
  }

  const levelStyle = getGroupLevelStyle(containerDepth)
  const fill = levelStyle.fill
  const stroke = levelStyle.stroke
  const strokeWidth = levelStyle.strokeWidth

  return `style ${groupId} fill:${fill},stroke:${stroke},stroke-width:${strokeWidth}\n`
}
