/**
 * collectHiddenState.js - 增量隐藏的"隐藏集合"计算 (纯函数)
 * ====================================================================
 * [目的] 把 MermaidComponent.updateVisibilityOnly 的隐藏集合收集逻辑抽成纯函数,
 *   便于单元测试 (回归保护 2026-08-14 ELK 系统分组误判为用户隐藏 bug).
 *
 * 返回 { hiddenNodeCodes, hiddenContainerCodes, hiddenCollapseIds }:
 *   - hiddenNodeCodes:  需 display:none 的 BO/叶子 code
 *   - hiddenContainerCodes: 需 display:none 的容器 code (g.cluster)
 *   - hiddenCollapseIds: 需 display:none 的聚合节点 id (COLLAPSE_<id>)
 *
 * [关键语义]
 *   - ELK 系统自动分组 (_elkGroup=inner/boundary) 的 visible=false 是"无边框盒但节点渲染"
 *     语义, **不是用户隐藏**, 不得收集其 BO 后代 (否则隐藏任意分组会把其下 BO 全隐藏且无法恢复).
 *   - [HIDE 2026-08-22] 用户隐藏分组 (visible=false, 且非 ELK 系统分组) 时, 除隐藏容器框外,
 *     还**递归收集其子孙叶节点编码** → 末端节点整体隐藏. 背景: mermaid SVG 中叶节点 g.node
 *     与容器 g.cluster 是 DOM 兄弟 (非父子), display/visibility 作用于容器不会连带隐藏叶节点.
 *   - [HIDE 2026-09-03] 递归时除收集 g.directNodes 外, 还收集当前节点的 g.nodes 字段
 *     (subDomain/serviceModule 容器同时含 nodes=BO 编码 + children=子节点, 旧实现漏收集).
 *   - isScopeProtected(g): 对象范围内要素及其祖先链不因父分组隐藏而被隐藏 (组件注入).
 */
import { upliftNodeId } from '../layouts/upliftDerivation.js'

export function isElkSystemAuto(g) {
  return !!g && g.groupType === 'custom' && (g._elkGroup === 'inner' || g._elkGroup === 'boundary')
}

function collectLeafNodes(leaf, set) {
  if (typeof leaf === 'string') { set.add(leaf); return }
  if (!leaf || typeof leaf !== 'object') return
  if (leaf.code) set.add(leaf.code)
  else if (leaf.elementCode) set.add(leaf.elementCode)
  else if (leaf.name) set.add(leaf.name)
  // [FIX 2026-08-19] BO 虚拟叶容器 (isVirtual=true) 存 nodes=[业务编码],
  //   之前只读 code/elementCode/name/directNodes → 单个 BO 叶隐藏时收集不到
  //   任何编码 → updateVisibilityOnly 无效果 (用户反馈 BO 隐藏无效).
  ;(leaf.nodes || []).forEach((n) => {
    if (typeof n === 'string') set.add(n)
    else if (n && typeof n === 'object') set.add(n.code || n.name)
  })
  ;(leaf.directNodes || []).forEach((n) => {
    if (typeof n === 'string') set.add(n)
    else if (n && typeof n === 'object') set.add(n.code || n.name)
  })
}

/**
 * [HIDE 2026-08-22] 递归收集分组的**子孙叶节点**编码到 set.
 *   用于"用户隐藏分组 → 末端节点一并隐藏": mermaid SVG 中叶节点 g.node 与容器 g.cluster
 *   是 DOM 兄弟 (非父子), display/visibility 作用于容器不会连带隐藏叶节点, 必须逐个收集.
 *   尊重对象范围保护: isScopeProtected 命中的子树 (范围内服务模块/祖先分组) 整棵跳过,
 *   不收集其下 BO (保证"范围内要素不因父分组隐藏而隐藏").
 *
 *   [HIDE 2026-09-03] 收集范围扩展: 同时读 g.nodes 字段 (subDomain/serviceModule 容器
 *     同时含 nodes=[BO编码] 和 children=子节点, 旧实现漏收集该层 BO 编码).
 *
 *   [FIX BUG-V033 2026-09-03] 父分组隐藏后, 子分组 (subDomain/serviceModule) 的容器框
 *   也需级联隐藏. 旧实现仅把子节点的 BO 编码加入 hiddenNodeCodes, 但子节点自己的 g.cluster
 *   (容器框) 未进 hiddenContainerCodes → MermaidComponent 中 svg.querySelectorAll('g.cluster')
 *   的 display 仍为 '' → 用户看到"父分组隐藏了, 子容器框还在"的现象. 修复: 递归时同步把
 *   每个子分组的 code 加入 hiddenContainerCodes (与 hiddenNodeCodes 平行收集).
 *
 *   [FIX BUG-V034 2026-09-03] 展开到子领域/服务模块时, 子分组被"上提"为 COLLAPSE_<id>
 *   聚合节点 (group._uplift=true, 见 upliftDerivation.js), 渲染成 g.node 而非 g.cluster.
 *   父隐藏后, 上提子节点的隐藏需走 hiddenCollapseIds (MermaidComponent:1713-1718)
 *   而非 hiddenContainerCodes (后者只对 g.cluster 生效). 修复: 递归时检查 ch._uplift,
 *   上提节点 add COLLAPSE_<id> 到 hiddenCollapseIds, 跳过 hiddenContainerCodes.
 */
function collectDescendantNodeCodes(g, set, isScopeProtected, hiddenContainerCodes, hiddenCollapseIds) {
  if (!g || typeof g !== 'object') return
  ;(g.nodes || []).forEach((n) => {
    if (typeof n === 'string') set.add(n)
    else if (n && typeof n === 'object' && (n.code || n.name)) set.add(n.code || n.name)
  })
  ;(g.directNodes || []).forEach((n) => {
    if (!isScopeProtected(n)) collectLeafNodes(n, set)
  })
  ;(g.containers || []).forEach((c) => {
    if (!c || typeof c !== 'object' || isScopeProtected(c)) return
    // [FIX BUG-V033] 子容器 (含 BO 虚拟叶容器) 的容器框级联隐藏
    //   但 ELK 系统分组 (_elkGroup=inner/boundary) 不是"用户隐藏", 其 visible=false
    //   是"无边框盒但节点渲染"语义, 不得收集其容器 code (与主流程 isElkSystemAuto 短路一致)
    if (!isElkSystemAuto(c)) {
      const cCode = c.elementCode || c.id
      if (cCode && hiddenContainerCodes) hiddenContainerCodes.add(cCode)
    }
    const hasNested = (c.children && c.children.length > 0) || (c.containers && c.containers.length > 0)
    if (hasNested) collectDescendantNodeCodes(c, set, isScopeProtected, hiddenContainerCodes, hiddenCollapseIds)
    else collectLeafNodes(c, set)
  })
  ;(g.children || []).forEach((ch) => {
    if (!ch || typeof ch !== 'object' || isScopeProtected(ch)) return
    // [FIX BUG-V033] 子孙分组 (subDomain/serviceModule) 的容器框级联隐藏
    //   ELK 系统分组同样跳过 (非用户隐藏, 其下 BO 已由 collectLeafNodes 处理)
    if (isElkSystemAuto(ch)) {
      // ELK 子孙: 不收集容器 code, 但仍递归 (其 BO 需进入 hiddenNodeCodes)
      collectDescendantNodeCodes(ch, set, isScopeProtected, hiddenContainerCodes, hiddenCollapseIds)
      return
    }
    if (ch._uplift === true) {
      // [FIX BUG-V034 2026-09-03] 上提节点: 渲染成 COLLAPSE_<id> 聚合节点 (g.node),
      //   隐藏需走 hiddenCollapseIds. 不要 add 到 hiddenContainerCodes (无 g.cluster).
      if (ch.id && hiddenCollapseIds) hiddenCollapseIds.add(upliftNodeId(ch))
    } else {
      const chCode = ch.elementCode || ch.id
      if (chCode && hiddenContainerCodes) hiddenContainerCodes.add(chCode)
    }
    collectDescendantNodeCodes(ch, set, isScopeProtected, hiddenContainerCodes, hiddenCollapseIds)
  })
}

/**
 * 分组子树是否"有可见内容" (空容器判定).
 * [ELK-GROUP 2026-08-14] ELK 系统分组虽 visible=false 但实际渲染节点, 视为有内容.
 * [HIDE 2026-08-19] 分组隐藏新语义: visible=false 只隐藏该分组容器框, 子孙仍渲染,
 *   故空容器判定不再因 g.visible === false 短路 (否则隐藏子领域后, 父领域被判为空
 *   而整体隐藏 → 容器框级联消失).
 */
export function hasVisibleContent(g) {
  if (!g || typeof g !== 'object') return false
  if (g.directNodes && g.directNodes.length > 0) return true
  if (Array.isArray(g.containers)) {
    for (const c of g.containers) {
      if (!c || typeof c !== 'object') continue
      if (c.visible === false) continue
      if ((c.nodes && c.nodes.length > 0)
        || c.elementRef?.code != null
        || c.elementCode != null
        || c.name != null) return true
    }
  }
  if (Array.isArray(g.children)) {
    for (const ch of g.children) {
      if (isElkSystemAuto(ch)) return true
      if (hasVisibleContent(ch)) return true
    }
  }
  return false
}

/**
 * 计算隐藏集合. 输入: 当前分组树 + 对象范围保护判定函数.
 * @param {Array} groups - 分组树 (layoutControlConfig.groups)
 * @param {Object} opts
 * @param {Function} opts.isScopeProtected - (g)=>boolean, 范围内要素/祖先受保护
 * @returns {{hiddenNodeCodes:Set, hiddenContainerCodes:Set, hiddenCollapseIds:Set}}
 */
export function collectHiddenState(groups, { isScopeProtected = () => false } = {}) {
  const hiddenNodeCodes = new Set()
  const hiddenContainerCodes = new Set()
  const hiddenCollapseIds = new Set()

  const walk = (list) => {
    ;(list || []).forEach((g) => {
      if (!g || typeof g !== 'object') return
      // [HIDE 2026-08-19][HIDE 2026-08-22] 分组隐藏语义: 隐藏该分组**容器框** + **子孙叶节点**
      //   (末端节点整体隐藏, 保留空位不重排). 非"禁用" (禁用是整棵子树打平上浮到父级).
      //   因此: ① 对用户隐藏分组, 除容器编码外, 再递归收集其子孙叶节点编码 (见 collectDescendantNodeCodes);
      //       ② 排除 ELK 系统分组 (isElkSystemAuto): 其 visible=false 是"无边框盒但节点渲染"
      //          语义, 非用户隐藏, 不得收集其 BO (回归 2026-08-14: 否则隐藏任意分组会把其下 BO 全隐藏);
      //       ③ 仍受对象范围保护: 范围内要素 (isScopeProtected 子树) 不因父分组隐藏而隐藏.
      const shouldHide = (g.visible === false)
      if (shouldHide) {
        // [FIX BUG-V033 2026-09-03] ELK 系统分组自身 visible=false 是"无边框盒但节点渲染"语义,
        //   不得把其 code 加入 hiddenContainerCodes (与 collectDescendantNodeCodes 内 ELK 短路一致)
        // [FIX BUG-V034 2026-09-03] 自身被上提 (_uplift=true) 时: 只渲染为 COLLAPSE_<id>
        //   聚合节点, 无 g.cluster. 隐藏走 hiddenCollapseIds, 不走 hiddenContainerCodes.
        if (!isElkSystemAuto(g) && g._uplift !== true) {
          const code = g.elementCode || g.id
          if (code) hiddenContainerCodes.add(code)
        }
        if (g.id) hiddenCollapseIds.add(upliftNodeId(g))
        if (!isElkSystemAuto(g)) {
          // [FIX BUG-V033 2026-09-03] 传 hiddenContainerCodes, 递归同步收集中间容器框
          // [FIX BUG-V034 2026-09-03] 递归同步收集中间上提节点到 hiddenCollapseIds
          collectDescendantNodeCodes(g, hiddenNodeCodes, isScopeProtected, hiddenContainerCodes, hiddenCollapseIds)
        }
      }
      // 叶子容器单独隐藏 (BO 叶 visible=false → 隐藏该节点); 范围内叶子容器受保护
      if (Array.isArray(g.containers)) {
        g.containers.forEach((c) => {
          if (c && typeof c === 'object' && c.visible === false && !isScopeProtected(c)) {
            collectLeafNodes(c, hiddenNodeCodes)
          }
        })
      }
      walk(g.children)
      walk(g.containers)
    })
  }
  walk(groups)

  // 空容器隐藏: 分组可见但整棵子树内容全被隐藏 → 渲染为空盒, 一并隐藏其 g.cluster
  //   (上提/折叠分组渲染为 COLLAPSE 聚合节点, 由 hiddenCollapseIds 管理, 不受本段影响)
  //   [FIX 2026-08-19 修订] 空分组(含 custom)已由 computeUplift 统一上提为聚合节点
  //   (_uplift=true, 走 hiddenCollapseIds 路径), 不再渲染空容器, 无需 custom 豁免.
  const collectEmptyGroupContainers = (list) => {
    ;(list || []).forEach((g) => {
      if (!g || typeof g !== 'object') return
      if (g.visible !== false && g._uplift !== true && !hasVisibleContent(g)) {
        const code = g.elementCode || g.id
        if (code) hiddenContainerCodes.add(code)
      }
      collectEmptyGroupContainers(g.children)
    })
  }
  collectEmptyGroupContainers(groups)

  return { hiddenNodeCodes, hiddenContainerCodes, hiddenCollapseIds }
}
