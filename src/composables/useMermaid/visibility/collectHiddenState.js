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
 *   - isScopeProtected(g): 对象范围内要素及其祖先链不因父分组隐藏而被隐藏 (组件注入).
 */
import { upliftNodeId } from '../layouts/upliftDerivation.js'

export function isElkSystemAuto(g) {
  return !!g && (g._elkGroup === 'inner' || g._elkGroup === 'boundary')
}

function collectLeafNodes(leaf, set) {
  if (typeof leaf === 'string') { set.add(leaf); return }
  if (!leaf || typeof leaf !== 'object') return
  if (leaf.code) set.add(leaf.code)
  else if (leaf.elementCode) set.add(leaf.elementCode)
  else if (leaf.name) set.add(leaf.name)
  ;(leaf.directNodes || []).forEach((n) => {
    if (typeof n === 'string') set.add(n)
    else if (n && typeof n === 'object') set.add(n.code || n.name)
  })
}

function collectGroupNodes(g, set) {
  ;(g.containers || []).forEach((c) => collectLeafNodes(c, set))
  ;(g.directNodes || []).forEach((n) => {
    if (typeof n === 'string') set.add(n)
    else if (n && typeof n === 'object') set.add(n.code || n.name)
  })
  ;(g.children || []).forEach((ch) => collectGroupNodes(ch, set))
}

// 隐藏父分组(如领域)时, 其子孙分组的 容器code 与 聚合节点id 一并加入隐藏集合
function collectDescendantGroupIds(g, containerCodes, collapseIds) {
  ;(g.children || []).forEach((ch) => {
    if (!ch || typeof ch !== 'object') return
    const code = ch.elementCode || ch.id
    if (code) containerCodes.add(code)
    if (ch.id) collapseIds.add(upliftNodeId(ch))
    collectDescendantGroupIds(ch, containerCodes, collapseIds)
  })
  ;(g.containers || []).forEach((c) => {
    if (!c || typeof c !== 'object') return
    const code = c.elementCode || c.id
    if (code) containerCodes.add(code)
    if (c.id) collapseIds.add(upliftNodeId(c))
    collectDescendantGroupIds(c, containerCodes, collapseIds)
  })
}

/**
 * 分组子树是否"有可见内容" (空容器判定).
 * [ELK-GROUP 2026-08-14] ELK 系统分组虽 visible=false 但实际渲染节点, 视为有内容.
 */
export function hasVisibleContent(g) {
  if (!g || typeof g !== 'object') return false
  if (g.visible === false) return false
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

  const walk = (list, inheritedHidden) => {
    ;(list || []).forEach((g) => {
      if (!g || typeof g !== 'object') return
      // [ELK-GROUP 2026-08-14] ELK 系统分组 visible=false 不算用户隐藏 (无边框盒语义)
      const effectiveHidden = inheritedHidden || (g.visible === false && !isElkSystemAuto(g))
      const shouldHide = effectiveHidden && !isScopeProtected(g)
      if (shouldHide) {
        const code = g.elementCode || g.id
        if (code) hiddenContainerCodes.add(code)
        if (g.id) hiddenCollapseIds.add(upliftNodeId(g))
        collectGroupNodes(g, hiddenNodeCodes)
        collectDescendantGroupIds(g, hiddenContainerCodes, hiddenCollapseIds)
      }
      // 叶子容器单独隐藏 (visible=false); 范围内叶子容器受保护
      if (Array.isArray(g.containers)) {
        g.containers.forEach((c) => {
          if (c && typeof c === 'object' && c.visible === false && !isScopeProtected(c)) {
            collectLeafNodes(c, hiddenNodeCodes)
          }
        })
      }
      walk(g.children, effectiveHidden)
      walk(g.containers, effectiveHidden)
    })
  }
  walk(groups, false)

  // 空容器隐藏: 分组可见但整棵子树内容全被隐藏 → 渲染为空盒, 一并隐藏其 g.cluster
  //   (上提/折叠分组渲染为 COLLAPSE 聚合节点, 由 hiddenCollapseIds 管理, 不受本段影响)
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
