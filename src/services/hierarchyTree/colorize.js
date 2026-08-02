/**
 * colorize - L3 着色纯函数
 *
 * [spec 4.2.3] 与投影解耦：颜色变化（colorScheme/colorGroupBy/自定义色）只触发 L3/L4，
 * 不重建 L1 树与 L2 投影。逻辑自 serviceModuleDiagramBuilder.js buildServiceModuleDiagramData
 * 的 subDomainColors/domainColors/serviceModuleColors 段抽取（L167-241）。
 *
 * 约定（[FIX 2026-08-02] 与 BO 图一致）：
 *   - 中心模块 fill 用分组色（联动变色），边框由语法层按 isCenter 加粗虚线区分；
 *     不再用 centerScopeColor 覆盖成灰色。
 */

import { COLOR_SCHEMES } from '@/constants/diagram'

export function colorize(nodes, containers, {
  colorGroupBy = 'subDomain',
  colorScheme = 'default',
  centerSubDomain = '',
  centerSubDomainColor = '#D9D9D9',
  customColors = {},
  centerServiceModuleCodes = null,
  centerScopeHighlight = true,
  nodeTextColor = 'black',
}) {
  const colors = COLOR_SCHEMES[colorScheme] || COLOR_SCHEMES.default

  const subDomainColors = {}
  const domainColors = {}
  const serviceModuleColors = {}
  const uniqueSubDomains = [...new Set(nodes.map(n => n.subDomain))]
  const actualCenter = centerSubDomain || uniqueSubDomains[0] || ''

  if (colorGroupBy === 'serviceModule') {
    nodes.forEach((n, i) => { serviceModuleColors[n.name] = customColors[n.name] || colors[i % colors.length] })
  } else if (colorGroupBy === 'subDomain') {
    uniqueSubDomains.forEach((sd, i) => {
      subDomainColors[sd] = sd === actualCenter ? centerSubDomainColor : (customColors[sd] || colors[i % colors.length])
    })
  } else {
    const uniqueDomains = [...new Set(nodes.map(n => n.domain))]
    uniqueDomains.forEach((d, i) => { domainColors[d] = customColors[d] || colors[i % colors.length] })
    nodes.forEach(n => { subDomainColors[n.subDomain] = domainColors[n.domain] })
  }

  const centerCodes = centerServiceModuleCodes
    ? new Set(centerServiceModuleCodes)
    : new Set(nodes.filter(n => n.isCenter || n.subDomain === actualCenter).map(n => n.code))

  const outNodes = nodes.map((n, i) => {
    let baseColor
    if (colorGroupBy === 'serviceModule') baseColor = serviceModuleColors[n.name] || colors[i % colors.length]
    else if (colorGroupBy === 'subDomain') baseColor = subDomainColors[n.subDomain] || colors[0]
    else baseColor = domainColors[n.domain] || colors[0]
    return {
      ...n,
      color: baseColor,                                   // 中心模块用分组色，边框由 syntax 层区分
      textColor: nodeTextColor,
      isCenter: centerScopeHighlight && centerCodes.has(n.code),
    }
  })

  return { nodes: outNodes, containers }
}
