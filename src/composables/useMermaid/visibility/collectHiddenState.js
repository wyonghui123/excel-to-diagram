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
      // [HIDE 2026-08-19] 分组隐藏新语义: visible=false 只隐藏该分组**容器框**,
      //   子节点 (directNodes/containers/children) 继续展示 (是"隐藏", 非"禁用").
      //   因此: ① 不再收集子孙 (原 collectGroupNodes/collectDescendantGroupIds 移除);
      //       ② 不再向子孙传播 inheritedHidden (每个分组独立判断自身 visible);
      //       ③ 不再受对象范围保护阻断 (隐藏容器框不隐藏任何范围内元素);
      //       ④ 不再排除 _elkGroup 标记分组: 服务模块等真实分组可能被 ELK 渲染
      //          产物污染 _elkGroup 标记, 旧逻辑把它们当"系统自动分组"跳过 → 隐藏无效.
      //          新语义无级联, 原"防止级联隐藏 ELK 分组 BO"的目的已不存在, 故移除.
      const shouldHide = (g.visible === false)
      if (shouldHide) {
        const code = g.elementCode || g.id
        if (code) hiddenContainerCodes.add(code)
        if (g.id) hiddenCollapseIds.add(upliftNodeId(g))
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
