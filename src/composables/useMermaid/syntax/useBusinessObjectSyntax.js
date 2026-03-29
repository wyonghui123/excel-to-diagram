import { getColors, assignColorsToGroups, getLinkColor } from './useMermaidColors.js'
import { useBlockDiagramStyle, BLOCK_DIAGRAM_STYLES } from '../style/useBlockDiagramStyle.js'
import { useBlockDiagramSyntax, DIAGRAM_TYPES } from './useBlockDiagramSyntax.js'

export function useBusinessObjectSyntax() {
  const { getContainerStyle, getLinkStyle, getNodeStyle, generateClassDefs } = useBlockDiagramStyle()
  const { preCalculateNodeSizes } = useBlockDiagramSyntax()

  const generateMermaidCode = (data, relationDescriptions, layoutEngine = 'dagre', layoutType = 'grouped', layoutControlConfig = null) => {
    if (!data || !data.nodes || !data.links) {
      return 'graph TD\n  A[No Data]'
    }

    preCalculateNodeSizes(data, DIAGRAM_TYPES.BUSINESS_OBJECT)

    const overallDirection = layoutControlConfig?.overallDirection || 'TB'
    
    let graphKeyword
    if (layoutEngine === 'elk') {
      graphKeyword = `flowchart-elk ${overallDirection}`
    } else {
      graphKeyword = `flowchart ${overallDirection}`
    }
    
    console.log('[useBusinessObjectSyntax] graphKeyword:', graphKeyword, 'overallDirection:', overallDirection)
    
    let mermaidCode = graphKeyword + '\n'
    const nodeCodeToIdMap = new Map()
    const nodeNameToIdMap = new Map()
    const nodeIdToCodeMap = new Map()
    let nodeId = 1

    const objectToModuleMap = new Map()
    if (data.domainProducts) {
      data.domainProducts.forEach(domain => {
        if (domain.businessObjects) {
          domain.businessObjects.forEach(bo => {
            objectToModuleMap.set(bo.code || bo.name, {
              type: 'domain',
              name: domain.name,
              code: domain.code
            })
          })
        }
        if (domain.modules) {
          domain.modules.forEach(module => {
            if (module.businessObjects) {
              module.businessObjects.forEach(bo => {
                objectToModuleMap.set(bo.code || bo.name, {
                  type: 'module',
                  name: module.name,
                  code: module.code,
                  parent: domain.name
                })
              })
            }
            if (module.submodules) {
              module.submodules.forEach(submodule => {
                if (submodule.businessObjects) {
                  submodule.businessObjects.forEach(bo => {
                    objectToModuleMap.set(bo.code || bo.name, {
                      type: 'submodule',
                      name: submodule.name,
                      code: submodule.code,
                      parent: module.name,
                      grandparent: domain.name
                    })
                  })
                }
              })
            }
          })
        }
      })
    }

    console.log('业务对象到模块映射:', Array.from(objectToModuleMap.entries()))

    const moduleGroups = new Map()

    let centerSubDomain = data.centerDomain
    let centerDomain = null
    if (!centerSubDomain && data.domainProducts) {
      const firstDomain = data.domainProducts[0]
      centerDomain = firstDomain ? firstDomain.name : null
      if (firstDomain && firstDomain.modules && firstDomain.modules.length > 0) {
        centerSubDomain = firstDomain.modules[0].name
      } else {
        centerSubDomain = centerDomain
      }
    } else if (centerSubDomain && data.domainProducts) {
      for (const domain of data.domainProducts) {
        if (domain.modules && domain.modules.some(m => m.name === centerSubDomain)) {
          centerDomain = domain.name
          break
        }
      }
      if (!centerDomain) {
        centerDomain = data.domainProducts[0] ? data.domainProducts[0].name : null
      }
    }
    console.log('中心子领域:', centerSubDomain, '中心领域:', centerDomain)

    const businessObjectNodes = data.nodes.filter(node => node.category === 'object')

    businessObjectNodes.forEach(node => {
      const id = `N${nodeId++}`
      const originalName = node.originalName || node.name
      const nodeCode = node.code

      console.log(`Mermaid节点 [ID:${id}] 名称:${originalName} 编码:${nodeCode}`)

      if (nodeCode) {
        nodeCodeToIdMap.set(nodeCode, id)
      }
      nodeNameToIdMap.set(originalName, id)
      nodeIdToCodeMap.set(id, nodeCode || originalName)

      const moduleInfo = objectToModuleMap.get(nodeCode) || objectToModuleMap.get(originalName)

      if (moduleInfo) {
        let groupKey, groupInfo
        if (moduleInfo.type === 'submodule') {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'submodule',
            name: moduleInfo.name,
            parent: moduleInfo.parent,
            grandparent: moduleInfo.grandparent,
            domain: moduleInfo.grandparent,
            subDomain: moduleInfo.parent
          }
        } else if (moduleInfo.type === 'module') {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'module',
            name: moduleInfo.name,
            parent: moduleInfo.parent,
            domain: moduleInfo.parent,
            subDomain: moduleInfo.name
          }
        } else {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'domain',
            name: moduleInfo.name,
            domain: moduleInfo.name,
            subDomain: moduleInfo.name
          }
        }

        if (!moduleGroups.has(groupKey)) {
          moduleGroups.set(groupKey, {
            info: groupInfo,
            nodes: []
          })
        }
        console.log('存储节点到分组:', { groupKey, id, originalName, nodeCode })
        moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode })
      } else {
        const groupKey = '其他'
        if (!moduleGroups.has(groupKey)) {
          moduleGroups.set(groupKey, {
            info: { name: '其他', type: 'unknown', domain: '其他', subDomain: '其他' },
            nodes: []
          })
        }
        console.log('存储节点到其他分组:', { groupKey, id, originalName, nodeCode })
        moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode })
      }
    })

    const colorGroupBy = data.colorGroupBy || 'domain'

    const centerDomainColor = data.centerDomainColor || '#D9D9D9'

    const colors = getColors(data.colorScheme)

    const uniqueGroups = new Set()
    moduleGroups.forEach((group) => {
      const groupKey = colorGroupBy === 'subDomain' ? group.info.subDomain : group.info.domain
      uniqueGroups.add(groupKey)
    })

    const centerGroupKey = colorGroupBy === 'subDomain' ? centerSubDomain : centerDomain
    console.log('业务对象图着色配置:', {
      centerSubDomain,
      centerDomain,
      centerDomainColor,
      colorGroupBy,
      centerGroupKey,
      totalGroups: moduleGroups.size,
      uniqueGroups: Array.from(uniqueGroups)
    })

    const colorMap = assignColorsToGroups(new Set(uniqueGroups), centerGroupKey, centerDomainColor, colors)

    const subDomainGroups = new Map()
    moduleGroups.forEach((group, groupName) => {
      const subDomain = group.info.subDomain || '其他'
      if (!subDomainGroups.has(subDomain)) {
        subDomainGroups.set(subDomain, [])
      }
      subDomainGroups.get(subDomain).push({ groupName, group })
    })

    const sortedSubDomains = Array.from(subDomainGroups.keys()).sort((a, b) => {
      if (a === centerSubDomain) return -1
      if (b === centerSubDomain) return 1
      return a.localeCompare(b, 'zh-CN')
    })

    const sortedGroups = new Map()
    sortedSubDomains.forEach(subDomain => {
      const groups = subDomainGroups.get(subDomain)
      groups.sort((a, b) => a.groupName.localeCompare(b.groupName, 'zh-CN'))
      groups.forEach(({ groupName, group }) => {
        sortedGroups.set(groupName, group)
      })
    })

    const optimizedGroups = sortedGroups

    const nodeColorMap = new Map()
    optimizedGroups.forEach((group) => {
      const groupKey = colorGroupBy === 'subDomain' ? group.info.subDomain : group.info.domain
      const groupColor = colorMap.get(groupKey)
      group.nodes.forEach(node => {
        nodeColorMap.set(node.id, groupColor)
      })
    })

    let subgraphId = 1
    
    /**
     * subgraph 内部方向说明
     * 根据整体方向决定 subgraph 内部的节点排列方式：
     * - 整体方向 TB（垂直排列）：subgraph 内部 LR（节点水平排列）
     * - 整体方向 LR（水平排列）：subgraph 内部 TB（节点垂直排列）
     */
    const subgraphDirection = overallDirection === 'TB' ? 'LR' : 'TB'
    
    console.log('[useBusinessObjectSyntax] Subgraph direction:', subgraphDirection, 'overallDirection:', overallDirection)
    
    optimizedGroups.forEach((group, groupName) => {
      const subId = `SG${subgraphId++}`
      let subgraphTitle
      if (group.info.type === 'submodule') {
        subgraphTitle = `${groupName}\\n(${group.info.grandparent}/${group.info.parent})`
      } else if (group.info.type === 'module') {
        subgraphTitle = `${groupName}\\n(${group.info.parent})`
      } else {
        subgraphTitle = groupName
      }

      mermaidCode += `  subgraph ${subId}["${subgraphTitle}"]\n`
      mermaidCode += `    direction ${subgraphDirection}\n`

      group.nodes.forEach(node => {
        const displayText = node.nodeCode ? `${node.originalName}\\n(${node.nodeCode})` : node.originalName
        mermaidCode += `    ${node.id}["${displayText}"]:::node\n`
      })

      mermaidCode += `  end\n`

      mermaidCode += `  style ${subId} ${getContainerStyle()}\n`
    })

    const nodeColorMappings = []
    businessObjectNodes.forEach(node => {
      const key = node.originalName || node.name
      const id = nodeNameToIdMap.get(key)
      const nodeColor = nodeColorMap.get(id) || '#FF9AA2'
      mermaidCode += `  style ${id} ${getNodeStyle(nodeColor)}\n`
      nodeColorMappings.push({ nodeId: id, color: nodeColor, nodeCode: node.code, nodeName: node.originalName || node.name })
    })

    const businessObjectLinks = data.links.filter(link => {
      let found = false
      if (link.sourceCode && link.targetCode) {
        found = nodeCodeToIdMap.has(link.sourceCode) && nodeCodeToIdMap.has(link.targetCode)
      }
      if (!found) {
        found = nodeNameToIdMap.has(link.sourceName) && nodeNameToIdMap.has(link.targetName)
      }
      return found
    })

    const linkColorMappings = []
    businessObjectLinks.forEach((link, index) => {
      console.log(`处理Mermaid连线:`, link)

      let sourceId = null
      let targetId = null

      if (link.sourceCode) {
        sourceId = nodeCodeToIdMap.get(link.sourceCode)
      }
      if (link.targetCode) {
        targetId = nodeCodeToIdMap.get(link.targetCode)
      }

      if (!sourceId) {
        sourceId = nodeNameToIdMap.get(link.sourceName)
      }
      if (!targetId) {
        targetId = nodeNameToIdMap.get(link.targetName)
      }

      console.log(`  找到的节点: source=${sourceId} target=${targetId}`)

      if (sourceId && targetId) {
        const sourceColor = nodeColorMap.get(sourceId)
        const targetColor = nodeColorMap.get(targetId)

        let sourceGroupKey = '', targetGroupKey = ''
        sortedGroups.forEach((group) => {
          if (group.nodes.some(n => n.id === sourceId)) {
            sourceGroupKey = colorGroupBy === 'subDomain' ? group.info.subDomain : group.info.domain
          }
          if (group.nodes.some(n => n.id === targetId)) {
            targetGroupKey = colorGroupBy === 'subDomain' ? group.info.subDomain : group.info.domain
          }
        })

        const linkColor = getLinkColor(sourceGroupKey, targetGroupKey, centerGroupKey, sourceColor, targetColor)

        mermaidCode += `  ${sourceId} -->|"${link.relationCode}"| ${targetId}\n`

        mermaidCode += `  linkStyle ${index} ${getLinkStyle(linkColor)}\n`

        linkColorMappings.push({
          index: index,
          sourceId: sourceId,
          targetId: targetId,
          color: linkColor
        })

        if (relationDescriptions) {
          relationDescriptions.push({
            sourceName: link.sourceName,
            targetName: link.targetName,
            source: sourceId,
            target: targetId,
            relationCode: link.relationCode,
            label: link.relationCode,
            relationDesc: link.relationDesc || '',
            sourceCode: link.sourceCode,
            targetCode: link.targetCode
          })
        }

        console.log(`✓ Mermaid连线添加成功: ${sourceId}->${targetId}`)
      }
    })

    mermaidCode += generateClassDefs()

    return mermaidCode
  }

  return {
    generateMermaidCode
  }
}
