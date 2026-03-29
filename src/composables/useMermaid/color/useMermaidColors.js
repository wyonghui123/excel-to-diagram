export const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
  warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
  cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
  business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
  nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
}

export const DEFAULT_COLOR = '#FF9AA2'
export const DEFAULT_LINK_COLOR = '#333333'
export const CENTER_DOMAIN_COLOR = '#D9D9D9'

export function useMermaidColors() {

  const getColorScheme = (schemeName) => {
    return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
  }

  const buildColorMap = (nodeColorMappings, objectToModuleMap, colorGroupBy, colorSchemes, centerDomainColor, centerSubDomain, centerDomain) => {
    const colors = colorSchemes
    const colorMap = new Map()
    const uniqueGroups = new Set()

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        const groupKey = colorGroupBy === 'subDomain' ? moduleInfo.subDomain : moduleInfo.domain
        uniqueGroups.add(groupKey)
      }
    })

    const smCenterGroupKey = colorGroupBy === 'subDomain' ? centerSubDomain : centerDomain

    if (smCenterGroupKey && uniqueGroups.has(smCenterGroupKey)) {
      colorMap.set(smCenterGroupKey, centerDomainColor)
      uniqueGroups.delete(smCenterGroupKey)
    }

    let colorIndex = 0
    uniqueGroups.forEach(group => {
      if (!colorMap.has(group)) {
        colorMap.set(group, colors[colorIndex % colors.length])
        colorIndex++
      }
    })

    return colorMap
  }

  const updateNodeColors = (svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap) => {
    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        const groupKey = colorGroupBy === 'subDomain' ? moduleInfo.subDomain : moduleInfo.domain
        const newColor = colorMap.get(groupKey) || DEFAULT_COLOR

        const nodeElement = svg.querySelector(`#${mapping.nodeId} rect, [data-id="${mapping.nodeId}"] rect`)
        if (nodeElement) {
          nodeElement.setAttribute('fill', newColor)
          nodeElement.style.fill = newColor
        }

        mapping.color = newColor
      }
    })
  }

  const updateLinkColors = (svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, centerSubDomain, centerDomain) => {
    linkColorMappings.forEach(mapping => {
      const sourceModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.sourceId)?.nodeCode)
      const targetModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.targetId)?.nodeCode)

      if (sourceModule && targetModule) {
        const sourceGroupKey = colorGroupBy === 'subDomain' ? sourceModule.subDomain : sourceModule.domain
        const targetGroupKey = colorGroupBy === 'subDomain' ? targetModule.subDomain : targetModule.domain
        const centerGroupKey = colorGroupBy === 'subDomain' ? centerSubDomain : centerDomain

        const isSourceCenter = sourceGroupKey === centerGroupKey
        const isTargetCenter = targetGroupKey === centerGroupKey

        let newColor
        if (!isSourceCenter && isTargetCenter) {
          newColor = colorMap.get(sourceGroupKey)
        } else if (isSourceCenter && !isTargetCenter) {
          newColor = colorMap.get(targetGroupKey)
        } else {
          newColor = colorMap.get(sourceGroupKey) || colorMap.get(targetGroupKey) || DEFAULT_LINK_COLOR
        }

        const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path')
        if (paths[mapping.index]) {
          paths[mapping.index].setAttribute('stroke', newColor)
          paths[mapping.index].style.stroke = newColor
        }

        mapping.color = newColor
      }
    })
  }

  const updateColorsOnly = (
    svg,
    nodeColorMappings,
    linkColorMappings,
    objectToModuleMap,
    data,
    colorGroupBy,
    centerSubDomain,
    centerDomain
  ) => {
    if (!svg) return false

    const currentColorGroupBy = colorGroupBy
    const centerDomainColor = data.centerDomainColor || CENTER_DOMAIN_COLOR
    const colorSchemes = getColorScheme(data.colorScheme)

    const colorMap = buildColorMap(
      nodeColorMappings,
      objectToModuleMap,
      currentColorGroupBy,
      colorSchemes,
      centerDomainColor,
      centerSubDomain,
      centerDomain
    )

    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap)

    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap, centerSubDomain, centerDomain)

    return true
  }

  return {
    COLOR_SCHEMES,
    DEFAULT_COLOR,
    DEFAULT_LINK_COLOR,
    CENTER_DOMAIN_COLOR,
    getColorScheme,
    buildColorMap,
    updateNodeColors,
    updateLinkColors,
    updateColorsOnly
  }
}