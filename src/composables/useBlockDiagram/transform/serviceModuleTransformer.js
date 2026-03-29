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

export class ServiceModuleTransformer extends BaseTransformer {
  constructor() {
    super({
      name: 'service-module',
      description: '服务模块图数据转换器'
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

    if (!rawData.nodes) {
      return nodes
    }

    rawData.nodes.forEach(node => {
      nodes.push(new DiagramNode({
        id: node.id,
        name: node.name,
        code: node.code || '',
        type: NodeType.SERVICE_MODULE,
        domain: node.domain || '',
        subDomain: node.subDomain || '',
        metadata: {
          originalData: node,
          color: node.color
        }
      }))
    })

    return nodes
  }

  extractLinks(rawData) {
    const links = []

    if (!rawData.links) {
      return links
    }

    rawData.links.forEach((link, index) => {
      links.push(new DiagramLink({
        id: link.id || `L${index + 1}`,
        source: link.source,
        target: link.target,
        label: link.label || '',
        relationCode: link.label || '',
        description: link.description || '',
        metadata: {
          originalData: link
        }
      }))
    })

    return links
  }

  extractContainers(rawData) {
    const containers = []

    if (!rawData.containers) {
      return containers
    }

    rawData.containers.forEach((container, index) => {
      const containerId = `C${index + 1}`

      containers.push(new DiagramContainer({
        id: containerId,
        name: container.name || container.fullTitle,
        title: container.fullTitle || container.name,
        type: ContainerType.SUB_DOMAIN,
        nodes: container.nodes || [],
        level: 0,
        metadata: {
          originalData: container
        }
      }))
    })

    return containers
  }

  createColorConfig(rawData) {
    return new ColorConfig({
      groupBy: 'subDomain',
      scheme: rawData.colorScheme || 'default',
      centerKey: rawData.centerSubDomain || '',
      centerColor: '#D9D9D9',
      linkColorRule: 'nonCenter'
    })
  }

  createLayoutConfig(rawData) {
    return new LayoutConfig({
      direction: 'TB',
      nodeSpacing: 150,
      rankSpacing: 200,
      nodeWidth: 300,
      nodeHeight: 120,
      curve: 'basis',
      padding: 30
    })
  }

  createSizeConfig(rawData) {
    return new SizeConfig({
      strategy: 'fixed',
      fontSize: 18,
      charWidthRatio: 0.65,
      lineHeight: 28,
      padding: 20,
      minWidth: 300,
      minHeight: 120,
      fixedWidth: 300,
      fixedHeight: 120
    })
  }
}

export const serviceModuleTransformer = new ServiceModuleTransformer()
