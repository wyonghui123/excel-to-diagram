/**
 * containerStats.js - 容器统计 (业务对象数量 + 内部关系数量)
 * ====================================================================
 * [目的] 把 attachContainerStatTooltips (useSvgStyle) 的统计逻辑抽成纯函数,
 *   供悬停 tooltip 与单元测试复用, 避免 DOM 耦合影响可测试性.
 *
 * 计数口径: 基于"当前图表实际展示的 BO / 关系" (与 diagramData.nodes/links 对齐).
 *   内部关系定义: source 与 target 均落在该容器子树内的关系 (两端都在内部).
 *
 * 数据来源:
 *   - diagramData.containers (统一管道容器树, 叶子 nodeIds = BO code)
 *   - 兜底 layoutGroups       (deriveLayoutGroups 产物, 叶子 directNodes = BO code)
 */
export function computeContainerStats(diagramData, layoutGroups = null) {
  if (!diagramData) return new Map()

  const containers = diagramData.containers
  const groups = (Array.isArray(layoutGroups) && layoutGroups.length > 0)
    ? layoutGroups
    : diagramData.layoutControlConfig?.groups
  const treeList = (Array.isArray(containers) && containers.length > 0)
    ? containers
    : (Array.isArray(groups) && groups.length > 0 ? groups : null)
  if (!treeList) return new Map()

  const leafField = (Array.isArray(containers) && containers.length > 0) ? 'nodeIds' : 'directNodes'

  // 1) 容器 code → 子树内 BO code 集合 (递归收集叶子)
  const boSetByContainer = new Map()
  const walk = (item) => {
    if (!item || typeof item !== 'object') return new Set()
    const set = new Set()
    const leaf = item[leafField]
    if (Array.isArray(leaf)) leaf.forEach((c) => { if (c != null) set.add(String(c)) })
    ;(item.children || []).forEach((child) => walk(child).forEach((c) => set.add(c)))
    if (item.code != null) boSetByContainer.set(String(item.code), set)
    return set
  }
  treeList.forEach(walk)
  if (boSetByContainer.size === 0) return new Map()

  // 2) 当前展示中的 BO code 集合
  const displayedBoCodes = new Set()
  ;(diagramData.nodes || []).forEach((n) => { if (n && n.code != null) displayedBoCodes.add(String(n.code)) })

  // 3) 逐容器统计 (基于展示内容)
  const links = diagramData.links || []
  const statByCode = new Map()
  boSetByContainer.forEach((boSet, code) => {
    let boCount = 0
    boSet.forEach((c) => { if (displayedBoCodes.has(c)) boCount++ })
    let relCount = 0
    if (boCount > 0) {
      for (const link of links) {
        const s = link.sourceCode != null ? String(link.sourceCode) : (link.source != null ? String(link.source) : '')
        const t = link.targetCode != null ? String(link.targetCode) : (link.target != null ? String(link.target) : '')
        if (boSet.has(s) && boSet.has(t)) relCount++
      }
    }
    statByCode.set(code, { boCount, relCount })
  })
  return statByCode
}
