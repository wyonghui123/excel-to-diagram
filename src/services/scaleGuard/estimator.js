/**
 * scaleGuard/estimator - 可见数预估器 (纯函数, 无 Vue/mermaid 依赖)
 *
 * 输入分组树(含 collapsed 状态) + 关系数组, 估算"渲染后将出现在图上的":
 *   nodes     - 可见节点数: 折叠分组=1个聚合节点; 展开分组的 directNodes=叶子节点; 递归子分组
 *   relations - 可见关系数: 两端 BO 都可见的关系才计 (关系数为主指标)
 *
 * 分组节点形态: { id, elementCode?, groupType?, collapsed, children[], containers[], directNodes[] }
 * links 形态:   { sourceCode, targetCode } (兼容 source/target)
 */
import { groupLevelOf } from '../expandLevel.js'

export function codeOf(nodeOrStr) {
  if (nodeOrStr == null) return ''
  if (typeof nodeOrStr === 'object') return nodeOrStr.code || nodeOrStr.id || nodeOrStr.name || ''
  return String(nodeOrStr)
}

export function leafCodesOf(node) {
  return (node.directNodes || []).map(codeOf).filter(Boolean)
}

/**
 * 估算可见节点/关系数。
 * @param {Array} groups 分组树顶层数组
 * @param {Array} links  关系数组 (含 sourceCode/targetCode 或 source/target)
 * @param {Object} [opts]
 * @param {string} [opts.expandGroupId]     假设额外展开该分组 (用于"展开交互"前置预估)
 * @param {number} [opts.expandGroupLevel]  展开目标层级 (0=领域/1=子领域/2=服务模块/99=全展开,
 *                                          与 expandSubtreeToLevel 语义一致: 目标层及更深折叠)
 * @returns {{nodes:number, relations:number, visibleBoSet:Set}}
 */
export function estimateVisible(groups, links, opts = {}) {
  const expandGroupId = opts.expandGroupId || null
  const expandGroupLevel = opts.expandGroupLevel != null ? opts.expandGroupLevel : null
  const visibleBoSet = new Set()
  let nodes = 0

  function walk(list, insideForceExpand) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g || typeof g !== 'object') continue
      const isTarget = expandGroupId != null && (g.id === expandGroupId || g.elementCode === expandGroupId)
      const forceExpand = isTarget
      let collapsed = g.collapsed === true
      if (forceExpand) {
        collapsed = false // 目标分组自身展开
      } else if (insideForceExpand && expandGroupLevel != null) {
        // 目标子树内: 按展开目标层级折叠 (目标层及更深 → 聚合节点)
        collapsed = groupLevelOf(g) >= expandGroupLevel
      }
      if (collapsed) {
        nodes += 1 // 聚合节点
        continue // 不深入折叠子树
      }
      for (const code of leafCodesOf(g)) {
        visibleBoSet.add(code)
        nodes += 1
      }
      walk(g.children, insideForceExpand || forceExpand)
      walk(g.containers, insideForceExpand || forceExpand)
    }
  }
  walk(groups, false)

  let relations = 0
  for (const l of links || []) {
    const s = codeOf(l.sourceCode != null ? l.sourceCode : l.source)
    const t = codeOf(l.targetCode != null ? l.targetCode : l.target)
    if (s && t && visibleBoSet.has(s) && visibleBoSet.has(t)) relations++
  }
  return { nodes, relations, visibleBoSet }
}

/**
 * 展开指定折叠分组到目标层级后的预估可见数。
 * @param {Array} groups 分组树
 * @param {Array} links  关系数组
 * @param {string} groupId 目标分组 id 或 elementCode
 * @param {number} level 目标层级 (0/1/2/99)
 */
export function estimateExpand(groups, links, groupId, level) {
  return estimateVisible(groups, links, { expandGroupId: groupId, expandGroupLevel: level })
}
