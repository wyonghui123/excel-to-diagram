import { getColors, assignColorsToGroups, getLinkColor } from './useMermaidColors.js'
import { useBlockDiagramStyle, BLOCK_DIAGRAM_STYLES } from '../style/useBlockDiagramStyle.js'
import { useBlockDiagramSyntax, DIAGRAM_TYPES } from './useBlockDiagramSyntax.js'
import { routeLayout } from '../layouts/index.js'
import { checkDepth, checkCycle, createVisitedSet } from '../../../services/groupModel/safetyUtils.js'
import { DataFlowLogger } from '../../../services/groupModel/dataFlowLogger.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'
import { getArrowSyntax, sanitizeLabel } from './_shared/arrowHelper.js'

function sortVirtualContainersBySize(containers) {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  return [...containers].sort((a, b) => {
    const aSize = a.nodes?.length || 0
    const bSize = b.nodes?.length || 0
    return bSize - aSize
  })
}

function calculateContainerConnectionDensity(containers, links) {
  if (!containers || containers.length === 0 || !links || links.length === 0) {
    return new Map()
  }
  
  const densityMap = new Map()
  
  containers.forEach(container => {
    const nodeSet = new Set(container.nodes || [])
    let internalConnections = 0
    let externalConnections = 0
    
    links.forEach(link => {
      const sourceInContainer = nodeSet.has(link.source)
      const targetInContainer = nodeSet.has(link.target)
      
      if (sourceInContainer && targetInContainer) {
        internalConnections++
      } else if (sourceInContainer || targetInContainer) {
        externalConnections++
      }
    })
    
    densityMap.set(container.id, {
      internal: internalConnections,
      external: externalConnections,
      total: internalConnections + externalConnections
    })
  })
  
  return densityMap
}

function sortVirtualContainersByConnection(containers, links) {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  if (!links || links.length === 0) {
    return [...containers]
  }
  
  const densityMap = calculateContainerConnectionDensity(containers, links)
  
  const containerConnections = new Map()
  containers.forEach(container => {
    const nodeSet = new Set(container.nodes || [])
    const connectedContainers = new Set()
    
    links.forEach(link => {
      const sourceInContainer = nodeSet.has(link.source)
      const targetInContainer = nodeSet.has(link.target)
      
      if (sourceInContainer && !targetInContainer) {
        containers.forEach(other => {
          if (other.id !== container.id && other.nodes?.includes(link.target)) {
            connectedContainers.add(other.id)
          }
        })
      } else if (!sourceInContainer && targetInContainer) {
        containers.forEach(other => {
          if (other.id !== container.id && other.nodes?.includes(link.source)) {
            connectedContainers.add(other.id)
          }
        })
      }
    })
    
    containerConnections.set(container.id, connectedContainers)
  })
  
  const sorted = []
  const remaining = [...containers]
  
  let maxConnections = 0
  let startContainer = remaining[0]
  remaining.forEach(container => {
    const connections = containerConnections.get(container.id)?.size || 0
    if (connections > maxConnections) {
      maxConnections = connections
      startContainer = container
    }
  })
  
  sorted.push(startContainer)
  const remainingIdx = remaining.findIndex(c => c.id === startContainer.id)
  remaining.splice(remainingIdx, 1)
  
  while (remaining.length > 0) {
    const lastContainer = sorted[sorted.length - 1]
    const lastConnections = containerConnections.get(lastContainer.id) || new Set()
    
    let bestNext = null
    let bestScore = -1
    
    remaining.forEach(container => {
      if (lastConnections.has(container.id)) {
        const density = densityMap.get(container.id)
        const score = density ? density.total : 0
        if (score > bestScore) {
          bestScore = score
          bestNext = container
        }
      }
    })
    
    if (!bestNext) {
      let maxDensity = -1
      remaining.forEach(container => {
        const density = densityMap.get(container.id)
        const total = density ? density.total : 0
        if (total > maxDensity) {
          maxDensity = total
          bestNext = container
        }
      })
    }
    
    if (bestNext) {
      sorted.push(bestNext)
      const idx = remaining.findIndex(c => c.id === bestNext.id)
      remaining.splice(idx, 1)
    } else {
      sorted.push(remaining.shift())
    }
  }
  
  return sorted
}

function calculateContainerScores(containers, links, weights = { size: 0.4, connection: 0.6 }) {
  if (!containers || containers.length === 0) {
    return new Map()
  }
  
  const scores = new Map()
  
  const maxNodes = Math.max(...containers.map(c => c.nodes?.length || 0), 1)
  
  const densityMap = calculateContainerConnectionDensity(containers, links)
  const maxDensity = Math.max(...Array.from(densityMap.values()).map(d => d.total), 1)
  
  containers.forEach(container => {
    const sizeScore = (container.nodes?.length || 0) / maxNodes
    
    const density = densityMap.get(container.id) || { total: 0 }
    const connectionScore = density.total / maxDensity
    
    const combinedScore = (sizeScore * weights.size) + (connectionScore * weights.connection)
    
    scores.set(container.id, {
      size: sizeScore,
      connection: connectionScore,
      combined: combinedScore
    })
  })
  
  return scores
}

function sortVirtualContainers(containers, links, strategy = 'combined') {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  switch (strategy) {
    case 'size':
      return sortVirtualContainersBySize(containers)
    
    case 'connection':
      return sortVirtualContainersByConnection(containers, links)
    
    case 'combined':
    default:
      const scores = calculateContainerScores(containers, links)
      return [...containers].sort((a, b) => {
        const scoreA = scores.get(a.id)?.combined || 0
        const scoreB = scores.get(b.id)?.combined || 0
        return scoreB - scoreA
      })
  }
}

function collectContainers(group, allContainers, visited = null, depth = 0) {
  if (!group) return
  
  if (!checkDepth(depth, 'BusinessObjectSyntax.collectContainers')) {
    return
  }
  
  if (!visited) {
    visited = createVisitedSet()
  }
  
  if (group.id && checkCycle(group.id, visited, 'BusinessObjectSyntax.collectContainers')) {
    return
  }
  
  if (group.containers && group.containers.length > 0) {
    group.containers.forEach(c => {
      if (c.nodes && c.nodes.length > 0) {
        c._containerLevel = depth + 1
        allContainers.push(c)
      }
    })
  }
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => collectContainers(child, allContainers, visited, depth + 1))
  }
}

function buildVirtualContainers(groups, moduleGroups, businessObjectNodes, nodeNameToIdMap = new Map(), nodeCodeToIdMap = new Map(), titleMap = {}) {
  const usedModules = new Set()
  
  function processGroup(group, visited = null, depth = 0) {
    if (!group) return

    if (!checkDepth(depth, 'BusinessObjectSyntax.processGroup')) {
      return
    }

    group._containerLevel = depth

    if (!visited) {
      visited = createVisitedSet()
    }

    if (group.id && checkCycle(group.id, visited, 'BusinessObjectSyntax.processGroup')) {
      return
    }
    
    // 使用 titleMap 更新 title（支持多种匹配方式）
    let matchedTitle = titleMap[group.id] || titleMap[group.elementCode] || titleMap[group.title]
    if (matchedTitle) {
      group.title = matchedTitle
    }
    
    // 如果分组被禁用，不创建 virtualContainer（避免生成多余的子图容器）
    const isGroupEnabled = group.enabled !== false
    if (!isGroupEnabled) {
      // 清除 directNodes 和 containers，避免后续生成子图
      group.directNodes = []
      group.containers = []
    }
    
    if (group.directNodes && group.directNodes.length > 0) {
      const convertedNodeIds = group.directNodes.map(nodeId => {
        if (typeof nodeId === 'object') {
          return nodeId.id || nodeId.code || nodeId.name || nodeId
        }
        return nodeNameToIdMap.get(nodeId) || nodeCodeToIdMap.get(nodeId) || nodeId
      }).filter(id => id != null)

      if (convertedNodeIds.length > 0) {
        const virtualContainer = {
          id: `${group.id}_direct`,
          name: group.title,
          fullTitle: group.title,
          nodes: convertedNodeIds,
          _groupId: group.id,
          _groupTitle: group.title,
          _isDirectNodesContainer: true,
          _containerLevel: depth + 1
        }

        if (!group.containers) {
          group.containers = []
        }
        group.containers.push(virtualContainer)
        group.directNodes = []
      }
    }

    if (group.containers && group.containers.length > 0) {
      group.containers.forEach((containerRef) => {
        containerRef._containerLevel = depth + 1
        
        // 使用 titleMap 更新容器标题
        const containerMatchedTitle = titleMap[containerRef.id] || titleMap[containerRef.elementCode] || titleMap[containerRef.name]
        if (containerMatchedTitle) {
          containerRef.fullTitle = containerMatchedTitle
        }
        
        if (containerRef.nodes && containerRef.nodes.length > 0) {
          const convertedNodes = containerRef.nodes.map(nodeId => {
            const mermaidId = nodeNameToIdMap.get(nodeId) || nodeCodeToIdMap.get(nodeId)
            if (mermaidId) {
              return mermaidId
            }
            return nodeId
          }).filter(id => id != null)
          
          containerRef.nodes = convertedNodes
          return
        }

        const moduleName = containerRef.name || containerRef.fullTitle
        let matchedNodes = []
        let matchedKey = moduleName

        let moduleGroup = moduleGroups.get(moduleName)

        if (moduleGroup) {
          matchedNodes = moduleGroup.nodes

          if (moduleGroup.info && moduleGroup.info.type === 'subDomain') {
            for (const [key, grp] of moduleGroups.entries()) {
              if (grp.info && grp.info.parent === moduleName) {
                matchedNodes = matchedNodes.concat(grp.nodes)
              }
            }
          }
        }

        if (matchedNodes.length === 0 && containerRef.fullTitle) {
          const parts = containerRef.fullTitle.split(' / ')
          const extractedName = parts.length > 1 ? parts[parts.length - 1] : parts[0]
          moduleGroup = moduleGroups.get(extractedName)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = extractedName
          }
        }

        if (matchedNodes.length === 0 && containerRef.id) {
          moduleGroup = moduleGroups.get(containerRef.id)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = containerRef.id
          }
        }

        if (matchedNodes.length === 0 && containerRef.name) {
          moduleGroup = moduleGroups.get(containerRef.name)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = containerRef.name
          }
        }

        if (matchedNodes.length === 0) {
          const allMatchingGroups = []
          for (const [key, grp] of moduleGroups.entries()) {
            if (grp.info && grp.info.subDomain === moduleName) {
              allMatchingGroups.push({ key, nodes: grp.nodes })
            }
          }
          if (allMatchingGroups.length > 0) {
            matchedNodes = allMatchingGroups.flatMap(g => g.nodes)
          }
        }

        if (matchedNodes.length > 0 && !usedModules.has(matchedKey)) {
          usedModules.add(matchedKey)
          containerRef.nodes = matchedNodes.map(n => n.id)
        }
      })
    }

    if (group.children && group.children.length > 0) {
      group.children.forEach(childGroup => {
        processGroup(childGroup, visited, depth + 1)
      })
    }
  }

  groups.forEach(group => processGroup(group))

  return groups
}

export function useBusinessObjectSyntax() {
  const { getContainerStyle, getLinkStyle, getNodeStyle, generateClassDefs } = useBlockDiagramStyle()
  const { preCalculateNodeSizes } = useBlockDiagramSyntax()

  const generateMermaidCode = (data, relationDescriptions, layoutEngine = 'dagre', layoutType = 'grouped', layoutControlConfig = null) => {
    if (!data || !data.nodes || !data.links) {
      return 'graph TD\n  A[No Data]'
    }

    preCalculateNodeSizes(data, DIAGRAM_TYPES.BUSINESS_OBJECT)

    const effectiveLayoutControlConfig = layoutControlConfig

    const overallDirection = effectiveLayoutControlConfig?.overallDirection || 'LR'

    // ELK布局使用与配置一致的方向，不再反�?    // ELK的elk.direction配置会控制实际布局方向
    let actualDirection = overallDirection

    let graphKeyword
    let elkInitDirective = ''
    if (layoutEngine === 'elk') {
      graphKeyword = `flowchart-elk ${actualDirection}`
      // ELK配置通过mermaid.initialize传递，不需要在代码中重复配�?      elkInitDirective = ''
    } else {
      graphKeyword = `flowchart ${actualDirection}`
    }
    
    let mermaidCode = elkInitDirective + graphKeyword + '\n'
    const nodeCodeToIdMap = new Map()
    const nodeNameToIdMap = new Map()
    const nodeIdToCodeMap = new Map()
    // [v33 关键修复] nodeId → node name 映射, 用于 tooltip 显示源/目标节点名
    // 之前 relationDescriptions 存的是 link.sourceName (可能 undefined),
    // 导致 tooltip 中 "源 → 目标" 节点名为空
    const nodeIdToNameMap = new Map()
    let nodeId = 1

    const objectToModuleMap = new Map()
    
    // 首先从顶�?businessObjects 数组获取服务模块信息
    const boServiceModuleMap = new Map()
    if (data.businessObjects) {
      data.businessObjects.forEach(bo => {
        if (bo.code || bo.name) {
          boServiceModuleMap.set(bo.code || bo.name, {
            serviceModule: bo.serviceModule,
            serviceModuleName: bo.serviceModuleName
          })
        }
      })
    }
    
    if (data.domainProducts) {
      data.domainProducts.forEach(domain => {
        if (domain.businessObjects) {
          domain.businessObjects.forEach(bo => {
            const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
            objectToModuleMap.set(bo.code || bo.name, {
              type: 'domain',
              name: domain.name,
              code: domain.code,
              serviceModule: smInfo.serviceModule || bo.serviceModule,
              serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
            })
          })
        }
        if (domain.modules) {
          domain.modules.forEach(module => {
            if (module.businessObjects) {
              module.businessObjects.forEach(bo => {
                const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
                objectToModuleMap.set(bo.code || bo.name, {
                  type: 'module',
                  name: module.name,
                  code: module.code,
                  parent: domain.name,
                  serviceModule: smInfo.serviceModule || bo.serviceModule,
                  serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
                })
              })
            }
            if (module.submodules) {
              module.submodules.forEach(submodule => {
                if (submodule.businessObjects) {
                  submodule.businessObjects.forEach(bo => {
                    const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
                    objectToModuleMap.set(bo.code || bo.name, {
                      type: 'submodule',
                      name: submodule.name,
                      code: submodule.code,
                      parent: module.name,
                      grandparent: domain.name,
                      serviceModule: smInfo.serviceModule || bo.serviceModule,
                      serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
                    })
                  })
                }
              })
            }
          })
        }
      })
    }

    const moduleGroups = new Map()

    const businessObjectNodes = data.nodes.filter(node => node.category === 'object')

    businessObjectNodes.forEach(node => {
      const id = `N${nodeId++}`
      const originalName = node.originalName || node.name
      const nodeCode = node.code

      if (nodeCode) {
        nodeCodeToIdMap.set(nodeCode, id)
      }
      nodeNameToIdMap.set(originalName, id)
      nodeIdToCodeMap.set(id, nodeCode || originalName)
      // [v33 关键修复] 记录 id → 节点名, 用于 tooltip 回查
      nodeIdToNameMap.set(id, originalName)

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
            subDomain: moduleInfo.parent,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        } else if (moduleInfo.type === 'module') {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'module',
            name: moduleInfo.name,
            parent: moduleInfo.parent,
            domain: moduleInfo.parent,
            subDomain: moduleInfo.name,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        } else {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'domain',
            name: moduleInfo.name,
            domain: moduleInfo.name,
            subDomain: moduleInfo.name,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        }

        if (!moduleGroups.has(groupKey)) {
          moduleGroups.set(groupKey, {
            info: groupInfo,
            nodes: []
          })
        }
        moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
      } else {
        if (node.subDomain) {
          const groupKey = node.subDomain
          if (!moduleGroups.has(groupKey)) {
            moduleGroups.set(groupKey, {
              info: { name: groupKey, type: 'subDomain', domain: node.domain || groupKey, subDomain: groupKey },
              nodes: []
            })
          }
          moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
        } else {
          const groupKey = '其他'
          if (!moduleGroups.has(groupKey)) {
            moduleGroups.set(groupKey, {
              info: { name: '其他', type: 'unknown', domain: '其他', subDomain: '其他' },
              nodes: []
            })
          }
          moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
        }
      }
    })

    const colorGroupBy = data.colorGroupBy || 'domain'

    const colors = getColors(data.colorScheme)

    const uniqueGroups = new Set()
    moduleGroups.forEach((group) => {
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
      } else if (colorGroupBy === 'subDomain') {
        groupKey = group.info.subDomain
      } else {
        groupKey = group.info.domain
      }
      uniqueGroups.add(groupKey)
    })

    const colorMap = assignColorsToGroups(new Set(uniqueGroups), colors, data.customColors || {})

    const subDomainGroups = new Map()
    moduleGroups.forEach((group, groupName) => {
      const subDomain = group.info.subDomain || '其他'
      if (!subDomainGroups.has(subDomain)) {
        subDomainGroups.set(subDomain, [])
      }
      subDomainGroups.get(subDomain).push({ groupName, group })
    })

    const sortedSubDomains = Array.from(subDomainGroups.keys()).sort((a, b) => {
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
    const centerScopeBoCodes = data.centerScope || []
    const centerScopeHighlight = data.centerScopeHighlight !== false  // 默认�?true
    const centerScopeColor = data.centerScopeColor || '#EDEDED'
    const centerColorMap = {
      'gray': '#808080',
      '#1890FF': '#1890FF',
      '#52C41A': '#52C41A',
      '#FAAD14': '#FAAD14',
      '#722ED1': '#722ED1'
    }
    const centerColor = centerColorMap[centerScopeColor] || centerScopeColor

    optimizedGroups.forEach((group) => {
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
      } else if (colorGroupBy === 'subDomain') {
        groupKey = group.info.subDomain
      } else {
        groupKey = group.info.domain
      }
      const groupColor = colorMap.get(groupKey)
      // 如果 groupColor 不存在，使用第一个颜色作为默�?      const defaultColor = colors[0]
      group.nodes.forEach(node => {
        const nodeCode = node.code || node.name
        // 只有�?centerScopeHighlight �?true 时，才对中心范围节点特殊处理
        if (centerScopeHighlight && centerScopeBoCodes.includes(nodeCode)) {
          nodeColorMap.set(node.id, centerColor)
        } else {
          nodeColorMap.set(node.id, groupColor || defaultColor)
        }
      })
    })

    if (effectiveLayoutControlConfig?.enabled && effectiveLayoutControlConfig?.groups?.length > 0) {
      const titleMap = data?.groupControlTitleMap || {}
      const virtualGroups = buildVirtualContainers(
        effectiveLayoutControlConfig.groups,
        moduleGroups,
        businessObjectNodes,
        nodeNameToIdMap,
        nodeCodeToIdMap,
        titleMap
      )
      
      DataFlowLogger.BusinessObjectSyntax.buildVirtualContainers(
        virtualGroups,
        virtualGroups
      )

      const allContainers = []
      virtualGroups.forEach(g => collectContainers(g, allContainers))
      
      const sortingStrategy = effectiveLayoutControlConfig?.containerSortingStrategy || 'combined'
      
      if (sortingStrategy !== 'none' && allContainers.length > 1) {
        const processedLinks = []
        data.links.forEach(link => {
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

          if (sourceId && targetId) {
            processedLinks.push({ source: sourceId, target: targetId })
          }
        })
        
        const sortedContainers = sortVirtualContainers(allContainers, processedLinks, sortingStrategy)
        
        function applyContainerSorting(groups, sortedContainers) {
          const sortedIds = new Set(sortedContainers.map(c => c.id))
          
          groups.forEach(group => {
            if (group.containers && group.containers.length > 0) {
              const sortedGroupContainers = []
              sortedContainers.forEach(sortedContainer => {
                const found = group.containers.find(c => c.id === sortedContainer.id)
                if (found) {
                  sortedGroupContainers.push(found)
                }
              })
              group.containers.forEach(c => {
                if (!sortedIds.has(c.id)) {
                  sortedGroupContainers.push(c)
                }
              })
              group.containers = sortedGroupContainers
            }
            
            if (group.children && group.children.length > 0) {
              applyContainerSorting(group.children, sortedContainers)
            }
          })
        }
        
        applyContainerSorting(virtualGroups, sortedContainers)
      }

      if (allContainers.length > 0) {
        const nodeMap = new Map()
        
        businessObjectNodes.forEach(node => {
          const key = node.originalName || node.name
          const id = nodeNameToIdMap.get(key)
          const nodeData = {
            id: id,
            name: node.originalName || node.name,
            code: node.code
          }
          if (id) {
            nodeMap.set(id, nodeData)
          }
        })

        moduleGroups.forEach((group, groupKey) => {
          group.nodes.forEach(node => {
            if (node.id && !nodeMap.has(node.id)) {
              nodeMap.set(node.id, {
                id: node.id,
                name: node.name || node.originalName || node.id,
                code: node.code || node.nodeCode
              })
            }
          })
        })

        const definedNodes = new Set()

        // 提前处理 links 数据，用�?ELK 自动分组
        const processedLinks = []
        data.links.forEach(link => {
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

          if (sourceId && targetId) {
            processedLinks.push({ source: sourceId, target: targetId })
          }
        })

        const layoutCode = routeLayout(allContainers, {
          layoutType: 'grouped',
          layoutEngine,
          nodeMap,
          definedNodes,
          layoutControlConfig: {
            ...effectiveLayoutControlConfig,
            groups: virtualGroups
          },
          overallDirection: actualDirection,
          links: processedLinks
        })

        if (layoutCode) {
          mermaidCode += layoutCode

          businessObjectNodes.forEach(node => {
            const key = node.originalName || node.name
            const id = nodeNameToIdMap.get(key)
            if (id && !definedNodes.has(id)) {
              // v21: use " · " separator (single-line), rect auto-calculates width
              const displayText = node.code ? `${node.name} · (${node.code})` : node.name
              mermaidCode += `  ${id}["${displayText}"]:::node\n`
              definedNodes.add(id)
            }
          })
        } else {
          virtualGroups.forEach(group => {
            mermaidCode += generateGroupMermaid(group, nodeMap, definedNodes, actualDirection)
          })
        }

        const nodeColorMappings = []
        const textColor = data.nodeTextColor || '#000000'
        businessObjectNodes.forEach(node => {
          // 优先使用 code 查找 id，避免同名不同编码的对象冲突
          const nodeCode = node.code
          const id = nodeCode ? nodeCodeToIdMap.get(nodeCode) : nodeNameToIdMap.get(node.originalName || node.name)
          const nodeColor = nodeColorMap.get(id)
          mermaidCode += `  style ${id} ${getNodeStyle(nodeColor || '#FF9AA2', textColor)}\n`
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

          if (sourceId && targetId) {
            const sourceColor = nodeColorMap.get(sourceId)
            const targetColor = nodeColorMap.get(targetId)

            // 判断源和目标是否在中心范围内
            const linkSourceCode = link.sourceCode || link.sourceName
            const linkTargetCode = link.targetCode || link.targetName
            // 只有 centerScopeHighlight 为 true 时，才使用 centerScopeBoCodes 判断
            const isSourceCenter = centerScopeHighlight && centerScopeBoCodes.includes(linkSourceCode)
            const isTargetCenter = centerScopeHighlight && centerScopeBoCodes.includes(linkTargetCode)

            // 新的颜色规则�?            // 1. 如果源和目标中有一个非中心范围的节点，则采用该节点颜色
            // 2. 如果两个都是非中心范围则采用黑色
            // 3. 如果两个都是中心范围则采用该节点颜色
            let linkColor
            if (!isSourceCenter && !isTargetCenter) {
              // 两个都是非中心范�?-> 黑色
              linkColor = '#000000'
            } else if (isSourceCenter && isTargetCenter) {
              // 两个都是中心范围 -> 采用源节点颜色（或目标节点颜色）
              linkColor = sourceColor || targetColor || '#333333'
            } else {
              // 一个中心，一个非中心 -> 采用非中心节点的颜色
              linkColor = isSourceCenter ? targetColor : sourceColor
            }

            // 关键修复 v26: mermaid 11 对 link label "|" 内空字符串或带特殊字符 ("\\n, |) 报 "Syntax error in text"
            // 1) 替换 | → /
            // 2) 替换换行 → 空格
            // [v39 关系线标题修复] 3) 优先用 code (关系实例编码 e.g. "ORDER-USER-01"),
            //    fallback 到 relationCode (关系类型编码 e.g. "DEPENDS_ON"),
            //    再 fallback 到 relationDesc (描述)
            // 4) 如果全都空或纯空白, 输出无 label 的 link
            const rawCode = (link.code && String(link.code).trim())
              ? link.code
              : (link.relationCode && String(link.relationCode).trim())
                ? link.relationCode
                : (link.relationDesc && String(link.relationDesc).trim())
                  ? link.relationDesc
                  : ''
            let safeCode = ''
            if (rawCode) {
              safeCode = String(rawCode)
                .replace(/\|/g, '/')
                .replace(/[\r\n]+/g, ' ')
                .replace(/"/g, "'")
                .trim()
            }
            const labelPart = safeCode ? `|"${safeCode}"|` : ''
            mermaidCode += getArrowSyntax(sourceId, targetId, safeCode, link)

            mermaidCode += `  linkStyle ${index} ${getLinkStyle(linkColor)}\n`

            linkColorMappings.push({
              index: index,
              sourceId: sourceId,
              targetId: targetId,
              color: linkColor
            })

            if (relationDescriptions) {
              // [v33 关键修复] 从 sourceId/targetId 反查节点名, 确保 tooltip 显示正确
              // 之前直接用 link.sourceName/targetName, 业务数据可能只有 sourceCode/targetCode
              // 没有 sourceName/targetName, 导致 tooltip 显示空
              const resolvedSourceName = nodeIdToNameMap.get(sourceId) || link.sourceName || ''
              const resolvedTargetName = nodeIdToNameMap.get(targetId) || link.targetName || ''
              // [v39 关系线标题修复] relationCode 优先用 link.code (实例编码), fallback 到 link.relationCode
              // 这样 tooltip 的第一行也显示"关系编码"而不是"关系类型编码"
              const resolvedRelationCode = link.code || link.relationCode || ''
              relationDescriptions.push({
                sourceName: resolvedSourceName,
                targetName: resolvedTargetName,
                source: sourceId,
                target: targetId,
                relationCode: resolvedRelationCode,
                label: resolvedRelationCode,
                relationDesc: link.relationDesc || '',
                // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code)
                relationType: link.relationType || '',
                // [v34 双向支持] 关系方向 (推/拉/双向)
                relationDirection: link.relationDirection || '',
                annotationContent: link.annotationContent || '',
                annotationCategory: link.annotationCategory || 'info',
                sourceCode: link.sourceCode,
                targetCode: link.targetCode
              })
            }
          }
        })

        mermaidCode += generateClassDefs()

        return {
          mermaidCode,
          nodeColorMappings,
          linkColorMappings
        }
      }
    }

    let subgraphId = 1
    
    const subgraphDirection = actualDirection === 'TB' ? 'LR' : 'TB'
    
    const reversedGroups = Array.from(optimizedGroups.entries()).reverse()
    let groupIndex = 0
    reversedGroups.forEach(([groupName, group]) => {
      const subId = `SG${groupIndex + 1}`
      groupIndex++

      const allNodesCenter = group.nodes.every(n => n.isCenter)
      const centerMark = allNodesCenter ? '◆' : ''
      let subgraphTitle
      if (group.info.type === 'submodule') {
        subgraphTitle = `${centerMark}${groupName}\\n(${group.info.grandparent}/${group.info.parent})`
      } else if (group.info.type === 'module') {
        subgraphTitle = `${centerMark}${groupName}\\n(${group.info.parent})`
      } else {
        subgraphTitle = centerMark + groupName
      }

      const groupColor = colorMap.get(groupName) || BLOCK_DIAGRAM_STYLES.container.fill

      mermaidCode += `  subgraph ${subId}["${subgraphTitle}"]\n`
      mermaidCode += `    direction ${subgraphDirection}\n`

      group.nodes.forEach(node => {
        const centerMark = node.isCenter ? '◆' : ''
        // 关键修复 v21：mermaid 11 不支持 ["...\n..."] 换行语法（只支持 <br/>）
        // 改成 " · " 单行分隔符，避免 <br/> 换行 + max-width 切第二行问题
        const displayText = node.code ? `${centerMark}${node.name || node.originalName} · (${node.code})` : centerMark + (node.name || node.originalName)
        mermaidCode += `    ${node.id}["${displayText}"]:::node\n`
      })

      mermaidCode += `  end\n`

      mermaidCode += `  style ${subId} ${getContainerStyle(groupColor)}\n`
    })

    const nodeColorMappings = []
    businessObjectNodes.forEach(node => {
      // 优先使用 code 查找 id，避免同名不同编码的对象冲突
      const nodeCode = node.code
      const id = nodeCode ? nodeCodeToIdMap.get(nodeCode) : nodeNameToIdMap.get(node.originalName || node.name)
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

      if (sourceId && targetId) {
        const sourceColor = nodeColorMap.get(sourceId)
        const targetColor = nodeColorMap.get(targetId)

        let sourceGroupKey = '', targetGroupKey = ''
        sortedGroups.forEach((group) => {
          if (group.nodes.some(n => n.id === sourceId)) {
            if (colorGroupBy === 'serviceModule') {
              sourceGroupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
            } else if (colorGroupBy === 'subDomain') {
              sourceGroupKey = group.info.subDomain
            } else {
              sourceGroupKey = group.info.domain
            }
          }
          if (group.nodes.some(n => n.id === targetId)) {
            if (colorGroupBy === 'serviceModule') {
              targetGroupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
            } else if (colorGroupBy === 'subDomain') {
              targetGroupKey = group.info.subDomain
            } else {
              targetGroupKey = group.info.domain
            }
          }
        })

        const linkColor = getLinkColor(sourceGroupKey, targetGroupKey, sourceColor, targetColor)

        // 关键修复 v26: 见上 (line 886) 的 mermaid label 特殊字符处理
        // [v39 关系线标题修复] 优先 code → relationCode → relationDesc (与上面 line 895 保持一致)
        const rawCode2 = (link.code && String(link.code).trim())
          ? link.code
          : (link.relationCode && String(link.relationCode).trim())
            ? link.relationCode
            : (link.relationDesc && String(link.relationDesc).trim())
              ? link.relationDesc
              : ''
        let safeCode2 = ''
        if (rawCode2) {
          safeCode2 = String(rawCode2)
            .replace(/\|/g, '/')
            .replace(/[\r\n]+/g, ' ')
            .replace(/"/g, "'")
            .trim()
        }
        const labelPart2 = safeCode2 ? `|"${safeCode2}"|` : ''
        mermaidCode += getArrowSyntax(sourceId, targetId, safeCode2, link)

        mermaidCode += `  linkStyle ${index} ${getLinkStyle(linkColor)}\n`

        linkColorMappings.push({
          index: index,
          sourceId: sourceId,
          targetId: targetId,
          color: linkColor
        })

        if (relationDescriptions) {
          // [v33 关键修复] 从 sourceId/targetId 反查节点名, 确保 tooltip 显示正确
          const resolvedSourceName = nodeIdToNameMap.get(sourceId) || link.sourceName || ''
          const resolvedTargetName = nodeIdToNameMap.get(targetId) || link.targetName || ''
          // [v39 关系线标题修复] relationCode 优先用 link.code (实例编码), fallback 到 link.relationCode
          const resolvedRelationCode = link.code || link.relationCode || ''
          relationDescriptions.push({
            sourceName: resolvedSourceName,
            targetName: resolvedTargetName,
            source: sourceId,
            target: targetId,
            relationCode: resolvedRelationCode,
            label: resolvedRelationCode,
            relationDesc: link.relationDesc || '',
            // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code)
            relationType: link.relationType || '',
            // [v34 双向支持] 关系方向 (推/拉/双向)
            relationDirection: link.relationDirection || '',
            annotationContent: link.annotationContent || '',
            annotationCategory: link.annotationCategory || 'info',
            sourceCode: link.sourceCode,
            targetCode: link.targetCode
          })
        }
      }
    })

    mermaidCode += generateClassDefs()

    return {
      mermaidCode,
      nodeColorMappings,
      linkColorMappings
    }
  }

  return {
    generateMermaidCode
  }
}

function generateGroupMermaid(group, nodeMap, definedNodes, actualDirection) {
  let code = ''
  const groupId = `G_${group.id.replace(/[^a-zA-Z0-9]/g, '_')}`
  const groupTitle = group.title || 'Group'
  const groupEnabled = group.enabled !== false

  if (!groupEnabled) {
    // 对于禁用的分组，只处理子元素（已提升），不处理自身的 containers
    if (group.children && group.children.length > 0) {
      group.children.forEach(child => {
        code += generateGroupMermaid(child, nodeMap, definedNodes, actualDirection)
      })
    }
    // 注意：禁用的分组不应该有 containers（已�?buildVirtualContainers 中清除）
    if (group.containers && group.containers.length > 0) {
      group.containers.forEach((container, idx) => {
        if (container.nodes && container.nodes.length > 0) {
          const containerEnabled = container.enabled !== false
          if (containerEnabled) {
            const containerId = `${groupId}_C${idx + 1}`
            const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')
            code += `  subgraph ${containerId}["${containerTitle}"]\n`
            code += `    direction ${actualDirection === 'TB' ? 'LR' : 'TB'}\n`
            
            container.nodes.forEach(nodeId => {
              const node = nodeMap.get(nodeId)
              if (node && !definedNodes.has(nodeId)) {
                const displayText = node.code ? `${node.name} · (${node.code})` : node.name
                code += `    ${nodeId}["${displayText}"]\n`
                definedNodes.add(nodeId)
              }
            })
            
            code += `  end\n`
          } else {
            container.nodes.forEach(nodeId => {
              const node = nodeMap.get(nodeId)
              if (node && !definedNodes.has(nodeId)) {
                const displayText = node.code ? `${node.name} · (${node.code})` : node.name
                code += `  ${nodeId}["${displayText}"]\n`
                definedNodes.add(nodeId)
              }
            })
          }
        }
      })
    }
    return code
  }

  code += `  subgraph ${groupId}["${groupTitle}"]\n`
  code += `    direction ${actualDirection === 'TB' ? 'LR' : 'TB'}\n`

  if (group.children && group.children.length > 0) {
    group.children.forEach(child => {
      code += generateGroupMermaid(child, nodeMap, definedNodes, actualDirection)
    })
  }

  if (group.containers && group.containers.length > 0) {
    group.containers.forEach((container, idx) => {
      if (container._isDirectNodesContainer) {
        if (container.nodes && container.nodes.length > 0) {
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = node.code ? `${node.name} · (${node.code})` : node.name
              code += `    ${nodeId}["${displayText}"]\n`
              definedNodes.add(nodeId)
            }
          })
        }
        return
      }
      
      if (container.nodes && container.nodes.length > 0) {
        const containerEnabled = container.enabled !== false
        if (containerEnabled) {
          const containerId = `${groupId}_C${idx + 1}`
          const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')
          code += `    subgraph ${containerId}["${containerTitle}"]\n`
          code += `      direction ${actualDirection === 'TB' ? 'LR' : 'TB'}\n`
          
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = node.code ? `${node.name} · (${node.code})` : node.name
              code += `      ${nodeId}["${displayText}"]\n`
              definedNodes.add(nodeId)
            }
          })
          
          code += `    end\n`
        } else {
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = node.code ? `${node.name} · (${node.code})` : node.name
              code += `    ${nodeId}["${displayText}"]\n`
              definedNodes.add(nodeId)
            }
          })
        }
      }
    })
  }

  code += `  end\n`

  return code
}
