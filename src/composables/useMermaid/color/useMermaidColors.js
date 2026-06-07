import { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR } from '@/constants/diagram'

export { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR }

export function useMermaidColors() {

  const getColorScheme = (schemeName) => {
    return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
  }

  const buildColorMap = (nodeColorMappings, objectToModuleMap, colorGroupBy, colorSchemes, customColors = {}) => {
    const colors = colorSchemes
    const colorMap = new Map()
    const uniqueGroups = new Set()

    console.log('[buildColorMap] customColors received:', customColors)

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
        uniqueGroups.add(groupKey)
      }
    })

    let colorIndex = 0
    uniqueGroups.forEach(group => {
      console.log('[buildColorMap] group:', group, 'customColors[group]:', customColors[group])
      if (customColors[group]) {
        colorMap.set(group, customColors[group])
      } else {
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
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
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

  const updateLinkColors = (svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap) => {
    linkColorMappings.forEach(mapping => {
      const sourceModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.sourceId)?.nodeCode)
      const targetModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.targetId)?.nodeCode)

      if (sourceModule && targetModule) {
        let sourceGroupKey, targetGroupKey
        if (colorGroupBy === 'serviceModule') {
          sourceGroupKey = sourceModule.serviceModuleName || sourceModule.serviceModule
          targetGroupKey = targetModule.serviceModuleName || targetModule.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          sourceGroupKey = sourceModule.subDomain
          targetGroupKey = targetModule.subDomain
        } else {
          sourceGroupKey = sourceModule.domain
          targetGroupKey = targetModule.domain
        }

        const newColor = colorMap.get(sourceGroupKey) || colorMap.get(targetGroupKey) || DEFAULT_LINK_COLOR

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
    colorGroupBy
  ) => {
    if (!svg) return false

    const currentColorGroupBy = colorGroupBy
    const colorSchemes = getColorScheme(data.colorScheme)

    const colorMap = buildColorMap(
      nodeColorMappings,
      objectToModuleMap,
      currentColorGroupBy,
      colorSchemes,
      data.customColors || {}
    )

    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap)

    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap)

    return true
  }

  return {
    COLOR_SCHEMES,
    DEFAULT_COLOR,
    DEFAULT_LINK_COLOR,
    getColorScheme,
    buildColorMap,
    updateNodeColors,
    updateLinkColors,
    updateColorsOnly
  }
}
