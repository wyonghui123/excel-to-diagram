/**
 * hierarchyTree/index.js - 统一架构管道装配 + 分层缓存
 *
 * [spec 4.4] 分层数据管道：
 *   L0 preview → L1 buildHierarchyTree → L2 projectTree → L3 colorize → L4 syntax 生成 mermaidCode → L5 mermaid.run
 *
 * 分层缓存策略（配置变化只触发最小重建路径）：
 *   - L1 树缓存: key = versionId + scopeHash（scope 变才重建）
 *   - L2 投影缓存: key = tree 对象引用 + terminal（chartType 变 / 树重建才重算）
 *     [FIX 2026-08-02] 用 WeakMap 以 tree 对象身份作 key，避免 scope 变化导致
 *     L1 重建后仍命中旧的投影缓存（tree.id 固定为 'P_ROOT'，字符串 key 会失效）。
 *   - L3/L4 无缓存（纯函数 / 每次生成，成本低）
 */

import { buildHierarchyTree } from './buildHierarchyTree.js'
import { projectTree, GLOBAL_TERMINALS } from './projectTree.js'

export { buildHierarchyTree } from './buildHierarchyTree.js'
export { projectTree, GLOBAL_TERMINALS } from './projectTree.js'
export { colorize } from './colorize.js'
export { deriveLayoutGroups } from './layoutGroupsDeriver.js'

export function createHierarchyPipeline() {
  let treeCache = null
  let treeKey = ''
  const projectionCache = new WeakMap()   // tree 对象 → { terminalKey, result }

  return {
    getTree({ preview, versionId, scopeHash }) {
      const key = `${versionId}:${scopeHash}`
      if (treeCache && treeKey === key) return treeCache
      treeKey = key
      treeCache = buildHierarchyTree({ preview })
      return treeCache
    },
    project({ treeData, terminal }) {
      const terminalKey = terminal?.name || String(terminal)
      const entry = projectionCache.get(treeData?.tree)
      if (entry && entry.terminalKey === terminalKey) return entry.result
      const result = projectTree(treeData, { terminalResolver: terminal })
      projectionCache.set(treeData?.tree, { terminalKey, result })
      return result
    },
  }
}
