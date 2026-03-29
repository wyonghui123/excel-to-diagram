import { BaseTransformer } from './useDataTransformer'
import {
  DiagramNode,
  DiagramLink,
  DiagramContainer,
  BlockDiagramData,
  ColorConfig,
  LayoutConfig,
  SizeConfig,
  NodeType,
  ContainerType
} from '../model'

export class BusinessObjectTransformer extends BaseTransformer {
  constructor() {
    super({
      name: 'business-object',
      description: '业务对象图数据转换器'
    })
  }

  transform(rawData) {
    const nodes = this.extractNodes(rawData)
    const links = this.extractLinks(rawData)
    const containers = this.extractContainers(rawData)
    const colorConfig = this.createColorConfig(rawData)
    const layoutConfig = this.createLayoutConfig(rawData)
    const sizeConfig = this.createSizeConfig(rawData)

    return new BlockDiagramData({
      nodes,
      links,
      containers,
      colorConfig,
      layoutConfig,
      sizeConfig
    })
  }

  extractNodes(rawData) {
    const nodes = []
    const nodeIdMap = new Map()
    let nodeIdCounter = 1

    if (!rawData.nodes) {
      return nodes
    }

    const businessObjectNodes = rawData.nodes.filter(node => node.category === 'object')

    const objectToModuleMap = this.buildObjectToModuleMap(rawData)

    businessObjectNodes.forEach(node => {
      const id = `N${nodeIdCounter++}`
      const originalName = node.originalName || node.name
      const nodeCode = node.code

      const moduleInfo = objectToModuleMap.get(nodeCode) || objectToModuleMap.get(originalName)

      const diagramNode = new DiagramNode({
        id,
        name: originalName,
        code: nodeCode || '',
        type: NodeType.BUSINESS_OBJECT,
        domain: moduleInfo?.domain || '',
        subDomain: moduleInfo?.subDomain || '',
        metadata: {
          originalData: node,
          moduleInfo
        }
      })

      nodes.push(diagramNode)
      nodeIdMap.set(nodeCode || originalName, id)
    })

    this.nodeIdMap = nodeIdMap
    return nodes
  }

  buildObjectToModuleMap(rawData) {
    const map = new Map()

    if (!rawData.domainProducts) {
      return map
    }

    rawData.domainProducts.forEach(domain => {
      if (domain.businessObjects) {
        domain.businessObjects.forEach(bo => {
          map.set(bo.code || bo.name, {
            type: 'domain',
            name: domain.name,
            code: domain.code,
            domain: domain.name,
            subDomain: domain.name
          })
        })
      }

      if (domain.modules) {
        domain.modules.forEach(module => {
          if (module.businessObjects) {
            module.businessObjects.forEach(bo => {
              map.set(bo.code || bo.name, {
                type: 'module',
                name: module.name,
                code: module.code,
                parent: domain.name,
                domain: domain.name,
                subDomain: module.name
              })
            })
          }

          if (module.submodules) {
            module.submodules.forEach(submodule => {
              if (submodule.businessObjects) {
                submodule.businessObjects.forEach(bo => {
                  map.set(bo.code || bo.name, {
                    type: 'submodule',
                    name: submodule.name,
                    code: submodule.code,
                    parent: module.name,
                    grandparent: domain.name,
                    domain: domain.name,
                    subDomain: submodule.name
                  })
                })
              }
            })
          }
        })
      }
    })

    return map
  }

  extractLinks(rawData) {
    const links = []
    let linkIdCounter = 1

    if (!rawData.links || !this.nodeIdMap) {
      return links
    }

    rawData.links.forEach(link => {
      let sourceId = null
      let targetId = null

      if (link.sourceCode) {
        sourceId = this.nodeIdMap.get(link.sourceCode)
      }
      if (link.targetCode) {
        targetId = this.nodeIdMap.get(link.targetCode)
      }

      if (!sourceId) {
        sourceId = this.nodeIdMap.get(link.sourceName)
      }
      if (!targetId) {
        targetId = this.nodeIdMap.get(link.targetName)
      }

      if (sourceId && targetId) {
        links.push(new DiagramLink({
          id: `L${linkIdCounter++}`,
          source: sourceId,
          target: targetId,
          label: link.relationCode || '',
          relationCode: link.relationCode || '',
          description: link.relationDesc || '',
          metadata: {
            originalData: link
          }
        }))
      }
    })

    return links
  }

  extractContainers(rawData) {
    const containers = []
    const containerMap = new Map()
    let containerIdCounter = 1

    if (!this.nodeIdMap) {
      return containers
    }

    this.nodeIdMap.forEach((nodeId, key) => {
      const nodes = this.extractNodes(rawData)
      const node = nodes.find(n => n.id === nodeId)
      if (!node) return

      const groupKey = node.subDomain || node.domain || '其他'
      const groupInfo = {
        type: node.subDomain ? ContainerType.SUB_DOMAIN : ContainerType.DOMAIN,
        name: groupKey,
        domain: node.domain,
        subDomain: node.subDomain
      }

      if (!containerMap.has(groupKey)) {
        containerMap.set(groupKey, {
          id: `SG${containerIdCounter++}`,
          info: groupInfo,
          nodes: []
        })
      }

      containerMap.get(groupKey).nodes.push(nodeId)
    })

    const sortedContainers = this.sortContainers(containerMap, rawData)

    sortedContainers.forEach((container, key) => {
      let title = key
      if (container.info.type === ContainerType.SUB_DOMAIN && container.info.domain) {
        title = `${key}\\n(${container.info.domain})`
      }

      containers.push(new DiagramContainer({
        id: container.id,
        name: key,
        title,
        type: container.info.type,
        nodes: container.nodes,
        level: container.info.type === ContainerType.DOMAIN ? 0 : 1,
        metadata: {
          info: container.info
        }
      }))
    })

    return containers
  }

  sortContainers(containerMap, rawData) {
    const centerSubDomain = this.getCenterSubDomain(rawData)

    const sorted = new Map()
    const keys = Array.from(containerMap.keys()).sort((a, b) => {
      if (a === centerSubDomain) return -1
      if (b === centerSubDomain) return 1
      return a.localeCompare(b, 'zh-CN')
    })

    keys.forEach(key => {
      sorted.set(key, containerMap.get(key))
    })

    return sorted
  }

  getCenterSubDomain(rawData) {
    if (rawData.centerDomain) {
      return rawData.centerDomain
    }

    if (rawData.domainProducts && rawData.domainProducts.length > 0) {
      const firstDomain = rawData.domainProducts[0]
      if (firstDomain.modules && firstDomain.modules.length > 0) {
        return firstDomain.modules[0].name
      }
      return firstDomain.name
    }

    return null
  }

  createColorConfig(rawData) {
    const centerSubDomain = this.getCenterSubDomain(rawData)

    return new ColorConfig({
      groupBy: rawData.colorGroupBy || 'subDomain',
      scheme: rawData.colorScheme || 'default',
      centerKey: centerSubDomain || '',
      centerColor: rawData.centerDomainColor || '#D9D9D9',
      linkColorRule: 'nonCenter'
    })
  }

  createLayoutConfig(rawData) {
    return new LayoutConfig({
      direction: 'TB',
      nodeSpacing: 80,
      rankSpacing: 100,
      nodeWidth: 180,
      nodeHeight: 80,
      curve: 'basis',
      padding: 25
    })
  }

  createSizeConfig(rawData) {
    return new SizeConfig({
      strategy: 'content-based',
      fontSize: 18,
      charWidthRatio: 0.65,
      lineHeight: 28,
      padding: 20,
      minWidth: 180,
      minHeight: 80
    })
  }
}

export const businessObjectTransformer = new BusinessObjectTransformer()
