/**
 * projectTree - L2 末端粒度投影器
 *
 * [spec 4.2.2] 只改变末端节点粒度，容器层级由树固定派生：
 *   - 末端粒度在领域层解析一次，沿子树向下传播（支持 per-domain 混合粒度，如
 *     供应链领域颗粒度到业务对象、财务领域下颗粒度到服务模块）
 *   - 折叠：末端层以下的子树折叠进最近末端节点（aggregated.count 聚合 BO 数）
 *   - 容器树：末端层之上的祖先链逐层生成嵌套容器（leaf 容器 nodeIds 列出显示节点）
 *   - link 重映射：端点 elementRef.id → 最近显示节点 id；悬空/自环/折叠重复 → 丢弃
 *
 * 输出契约（贯穿全管道，勿改）：
 *   nodes:      [{ id: code（无前缀）, layer, code, name, elementRef, domain, subDomain, aggregated: { count } }]
 *               domain/subDomain 为树上下文派生名称（L3 着色分组用）
 *   containers: 嵌套树 [{ id: 'D_..'|'SD_..'|'SM_..', layer, code, name, elementRef, children: [], nodeIds: [code] }]
 *   links:      [{ ...link, source: code, target: code }]（已去重）
 */

import { GroupType } from '../groupModel/types.js'

export const GLOBAL_TERMINALS = {
  businessObject: () => GroupType.BUSINESS_OBJECT,
  serviceModule: () => GroupType.SERVICE_MODULE,
  subDomain: () => GroupType.SUB_DOMAIN,
  domain: () => GroupType.DOMAIN,
}

export function projectTree({ tree, elementRefIndex, links }, { terminalResolver, options = {} }) {
  const terminalNodeOf = new Map()   // elementRef.id → 显示节点
  const displayNodes = []            // 末端节点（nodes 输出）

  function resolveTerminal(node) {
    if (node.layer === 'PRODUCT') return terminalResolver?.(null) || 'SERVICE_MODULE'
    return terminalResolver?.(node) || 'SERVICE_MODULE'
  }

  function countDescendants(node) {
    let n = 0
    ;(function dfs(x) {
      if (x.layer === GroupType.BUSINESS_OBJECT) n++
      for (const c of x.children || []) dfs(c)
    })(node)
    return n
  }

  // 把末端节点及其全部后代 elementRef.id 映射到同一显示节点（link 重映射依据）
  function registerTerminal(node, displayNode) {
    terminalNodeOf.set(node.elementRef.id, displayNode)
    ;(function dfs(x) {
      for (const c of x.children || []) {
        terminalNodeOf.set(c.elementRef.id, displayNode)
        dfs(c)
      }
    })(node)
  }

  // 末端层由 activeTerminal 决定；activeTerminal 仅在领域层解析一次后下传，
  // 避免 per-domain resolver 在子树内被再次求值导致粒度漂移。
  // context 沿树派生 domain/subDomain 名称（L3 着色分组需要，见 spec 4.2.2/4.2.3）。
  function walk(node, activeTerminal, context = {}) {
    const terminal = activeTerminal || resolveTerminal(node)
    if (node.layer === terminal) {
      const dn = {
        id: node.code, layer: node.layer, code: node.code, name: node.name,
        elementRef: node.elementRef, aggregated: { count: countDescendants(node) },
        domain: node.layer === 'DOMAIN' ? node.name : context.domain,
        subDomain: node.layer === 'SUB_DOMAIN' ? node.name : context.subDomain,
      }
      displayNodes.push(dn)
      registerTerminal(node, dn)
      return
    }
    const nextCtx = { ...context }
    if (node.layer === 'DOMAIN') nextCtx.domain = node.name
    else if (node.layer === 'SUB_DOMAIN') nextCtx.subDomain = node.name
    for (const child of node.children || []) walk(child, terminal, nextCtx)
  }

  // 末端层之上的祖先链逐层生成嵌套容器；leaf 容器的 nodeIds 列出其直接显示节点
  function buildContainers(node, terminalLayer) {
    if (!node.children || node.children.length === 0) return null
    if (node.layer === terminalLayer) return null  // 末端层自身不建容器
    const container = {
      id: node.id, layer: node.layer, code: node.code, name: node.name,
      elementRef: node.elementRef, children: [], nodeIds: [],
    }
    for (const child of node.children) {
      const childContainer = buildContainers(child, terminalLayer)
      if (childContainer) {
        container.children.push(childContainer)
      } else if (child.layer === terminalLayer) {
        container.nodeIds.push(child.code)   // 容器内节点 id = code
      } else if (child.layer === 'BUSINESS_OBJECT') {
        // BO 折叠进上层容器（SM 末端时）
        container.nodeIds.push(child.code)
      }
    }
    return container
  }

  const containers = []
  for (const domainNode of tree.children || []) {
    const term = resolveTerminal(domainNode)   // per-domain 粒度
    walk(domainNode, term)
    const c = buildContainers(domainNode, term)
    if (c) containers.push(c)
  }

  // link 重映射 + 折叠去重
  const outLinks = []
  const seen = new Set()                        // 多 BO 关系折叠到同一对显示节点 → 只保留一条
  for (const link of links || []) {
    const src = terminalNodeOf.get(link.source)
    const tgt = terminalNodeOf.get(link.target)
    if (!src || !tgt) continue            // 悬空端点 → 丢弃
    if (src.id === tgt.id) continue       // 折叠自环 → 丢弃
    const key = `${src.id}->${tgt.id}`
    if (seen.has(key)) continue           // 折叠去重
    seen.add(key)
    outLinks.push({ ...link, source: src.id, target: tgt.id })
  }

  return { nodes: displayNodes, containers, links: outLinks }
}
