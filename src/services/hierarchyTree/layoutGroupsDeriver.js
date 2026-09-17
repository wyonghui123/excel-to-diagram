/**
 * layoutGroupsDeriver - 从投影容器树派生 layoutControlConfig.groups
 *
 * [spec 4.2.4] 取代 buildServiceModuleGroupsFromDomainProducts 的独立生成：
 * 保证 groups 与 containers 归属严格一致，消除 resolveGroupContainers 名称匹配。
 *
 * 输出形状被 routeLayout/groupedLayout 消费（spec 4.2.4 执行记录 2026-08-02）：
 *   - domain  (groupType='domain',  direction='LR') → children: [subDomain]
 *   - subDomain (groupType='subDomain', direction='TB') → directNodes: [SM code]
 * 叶子容器 (nodeIds) 转 directNodes 而非 containers: groupedLayout 会把 directNodes
 * 渲染为 subgraph 内直接节点, 若放 containers 则 SM 终端不匹配真实容器被跳过或
 * 包一层 SM subgraph → 复现"同一 SM 既容器又节点"重复渲染。
 */

import { GroupType } from '../groupModel/types.js'

const STYLE_BY_LAYER = {
  [GroupType.DOMAIN]: { fill: '#f5f5f5', stroke: '#333333', strokeWidth: 2, strokeDasharray: '' },
  [GroupType.SUB_DOMAIN]: { fill: '#ffffff', stroke: '#666666', strokeWidth: 2, strokeDasharray: '' },
  [GroupType.SERVICE_MODULE]: { fill: '#ffffff', stroke: '#666666', strokeWidth: 1, strokeDasharray: '' },
}

export function deriveLayoutGroups(containers) {
  const groups = []
  for (const container of containers || []) {
    const group = convertContainer(container)
    if (group) groups.push(group)
  }
  return groups
}

function convertContainer(c) {
  if (!c) return null
  const hasChildren = c.children && c.children.length > 0
  const group = {
    id: c.id,
    title: c.name,
    elementCode: c.code,
    groupType: c.layer === GroupType.DOMAIN ? 'domain'
      : c.layer === GroupType.SUB_DOMAIN ? 'subDomain'
      : c.layer === GroupType.SERVICE_MODULE ? 'serviceModule' : 'custom',
    direction: c.layer === GroupType.DOMAIN ? 'LR' : 'TB',
    visible: true,
    enabled: true,
    style: STYLE_BY_LAYER[c.layer] || { fill: '#ffffff', stroke: '#666666', strokeWidth: 1, strokeDasharray: '' },
    containers: [],
    children: [],
    parentId: null,
  }
  if (hasChildren) {
    for (const child of c.children) {
      const childGroup = convertContainer(child)
      if (childGroup) {
        childGroup.parentId = group.id
        group.children.push(childGroup)
      }
    }
  }
  // 叶子容器: nodeIds 直接作为 directNodes（routeLayout 渲染为 subgraph 内直接节点,
  // 不再包一层 SM subgraph → 消除"同一 SM 既容器又节点"重复渲染）
  if (c.nodeIds?.length) {
    group.directNodes = [...c.nodeIds]
  }
  return group
}
