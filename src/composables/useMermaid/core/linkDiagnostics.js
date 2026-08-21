/**
 * linkDiagnostics — 折叠连线编码流失排查探针 (dev-only)
 * =================================================================
 *
 * [目的] 排查"折叠后连线标签显示名称而非编码"类问题时, 需要核对编码在
 *   前序模型(domainProducts) → 布局分组树(remapGroups) → 重映射连线(remapped)
 *   三段是否一致携带。该探针一次性捕获三段快照, 供 E2E / 脚本读取。
 *
 * [为什么独立成模块] 避免把探针逻辑内联在 useBusinessObjectSyntax 的渲染热路径,
 *   污染生产代码。模块内部用 import.meta.env.DEV 短路, 生产构建零业务开销
 *   (仅一次函数调用, dead-code 由 Vite 处理 import.meta.env.DEV 分支)。
 *
 * [读取入口] window.__archPage.mermaid.linkDiag
 *   {
 *     domainProducts: [{ level, code?, name?, elementCode?, title?, modules?/submodules?/children?/containers? }],
 *     remapGroups:    [...同上...],
 *     linkSamples:    [{ sourceCode, targetCode, code, label }],
 *     remapped:       [{ sourceCode, targetCode, code, label, sourceName, targetName }]
 *   }
 */
const ENABLED = import.meta.env.DEV

function collectHierarchy(items, level = 0) {
  return (items || []).map(g => {
    const node = { level }
    if (g?.code != null) node.code = g.code
    if (g?.name != null) node.name = g.name
    if (g?.elementCode != null) node.elementCode = g.elementCode
    if (g?.title != null) node.title = g.title
    if (g?.modules?.length) node.modules = collectHierarchy(g.modules, level + 1)
    if (g?.submodules?.length) node.submodules = collectHierarchy(g.submodules, level + 1)
    if (g?.children?.length) node.children = collectHierarchy(g.children, level + 1)
    if (g?.containers?.length) node.containers = collectHierarchy(g.containers, level + 1)
    return node
  })
}

/**
 * 记录折叠连线三段编码快照
 * @param {Object} p
 * @param {Array}  p.domainProducts  前序模型 (领域/子领域/服务模块层级)
 * @param {Array}  p.remapGroups     布局分组树 (重映射快照, 渲染权威来源)
 * @param {Array}  p.links           原始连线
 * @param {Array}  p.remappedLinks   重映射后连线
 */
export function recordLinkDiag({ domainProducts, remapGroups, links, remappedLinks }) {
  if (!ENABLED || typeof window === 'undefined') return
  try {
    window.__archPage = window.__archPage || {}
    window.__archPage.mermaid = window.__archPage.mermaid || {}
    window.__archPage.mermaid.linkDiag = {
      ts: Date.now(),
      domainProducts: collectHierarchy(domainProducts),
      remapGroups: collectHierarchy(remapGroups),
      linkSamples: (links || []).slice(0, 50).map(l => ({
        sourceCode: l.sourceCode, targetCode: l.targetCode, code: l.code, label: l.label
      })),
      remapped: (remappedLinks || []).slice(0, 80).map(l => ({
        sourceCode: l.sourceCode, targetCode: l.targetCode, code: l.code, label: l.label,
        sourceName: l.sourceName, targetName: l.targetName,
        sourceLevel: l.sourceLevel, targetLevel: l.targetLevel
      }))
    }
  } catch (e) { /* noop */ }
}