/**
 * layoutGroupsDeriver - 从投影容器树派生 layoutControlConfig.groups
 *
 * [spec 4.2.4] 取代 buildServiceModuleGroupsFromDomainProducts 的独立生成：
 * 保证 groups 与 containers 归属严格一致，消除 resolveGroupContainers 名称匹配。
 *
 * 输出格式与 buildServiceModuleGroupsFromDomainProducts 对齐（LayoutControlPanel 期望）：
 *   - domain (groupType='domain', direction='LR') → children: [subDomain]
 *   - subDomain (groupType='subDomain', direction='TB') → containers: [SM 终端]
 *   - SM 终端 (groupType='serviceModule', id 带前缀, elementCode 无前缀)
 *
 * [FIX 2026-08-02] 终端类型不从 nodeId 前缀推断（投影器 nodeIds 是无前缀 code），
 * 而是从"容器层的下一层"推断：SUB_DOMAIN → SERVICE_MODULE，SERVICE_MODULE → BUSINESS_OBJECT。
 */

import { GroupType, createGroupId } from '../groupModel/types.js'

// 容器层 → 下一层（nodeIds 元素类型）
const LAYER_NEXT = {
  [GroupType.DOMAIN]: GroupType.SUB_DOMAIN,
  [GroupType.SUB_DOMAIN]: GroupType.SERVICE_MODULE,
  [GroupType.SERVICE_MODULE]: GroupType.BUSINESS_OBJECT,
}

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
  // 终端节点：nodeIds 元素类型 = 本容器层的下一层
  const terminalType = LAYER_NEXT[c.layer] || GroupType.BUSINESS_OBJECT
  const isSm = terminalType === GroupType.SERVICE_MODULE
  for (const nodeId of c.nodeIds || []) {
    group.containers.push({
      id: isSm ? createGroupId(GroupType.SERVICE_MODULE, nodeId) : nodeId,
      type: terminalType,
      title: nodeId,
      elementCode: nodeId,
      elementRef: { type: terminalType, code: nodeId, name: nodeId },
      parentId: group.id,
      groupType: isSm ? 'serviceModule' : 'custom',
      direction: 'TB',
      visible: true,
      enabled: true,
      style: { fill: '#ffffff', stroke: '#666666', strokeWidth: 1, strokeDasharray: '' },
      containers: [],
      children: [],
    })
  }
  return group
}
