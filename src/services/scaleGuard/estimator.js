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
 * @param {string} [opts.expandGroupId] 假设额外展开该分组 (用于"展开交互"前置预估)
 * @returns {{nodes:number, relations:number, visibleBoSet:Set}}
 */
export function estimateVisible(groups, links, opts = {}) {
  const expandGroupId = opts.expandGroupId || null
  const visibleBoSet = new Set()
  let nodes = 0

  function walk(list) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g || typeof g !== 'object') continue
      const forceExpand = expandGroupId != null && (g.id === expandGroupId || g.elementCode === expandGroupId)
      const collapsed = forceExpand ? false : (g.collapsed === true)
      if (collapsed) {
        nodes += 1 // 聚合节点
        continue // 不深入折叠子树
      }
      for (const code of leafCodesOf(g)) {
        visibleBoSet.add(code)
        nodes += 1
      }
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(groups)

  let relations = 0
  for (const l of links || []) {
    const s = codeOf(l.sourceCode != null ? l.sourceCode : l.source)
    const t = codeOf(l.targetCode != null ? l.targetCode : l.target)
    if (s && t && visibleBoSet.has(s) && visibleBoSet.has(t)) relations++
  }
  return { nodes, relations, visibleBoSet }
}

/** 展开指定折叠分组后的预估可见数 */
export function estimateExpand(groups, links, groupId) {
  return estimateVisible(groups, links, { expandGroupId: groupId })
}
