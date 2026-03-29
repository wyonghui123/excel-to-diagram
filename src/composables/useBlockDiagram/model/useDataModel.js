export const NodeType = {
  BUSINESS_OBJECT: 'business-object',
  SERVICE_MODULE: 'service-module'
}

export const ContainerType = {
  DOMAIN: 'domain',
  MODULE: 'module',
  SUB_MODULE: 'submodule',
  SUB_DOMAIN: 'subdomain'
}

export const LinkType = {
  RELATION: 'relation',
  DEPENDENCY: 'dependency',
  ASSOCIATION: 'association'
}

export class DiagramNode {
  constructor(options = {}) {
    this.id = options.id || ''
    this.name = options.name || ''
    this.code = options.code || ''
    this.type = options.type || NodeType.BUSINESS_OBJECT
    this.domain = options.domain || ''
    this.subDomain = options.subDomain || ''
    this.metadata = options.metadata || {}
  }

  getDisplayLabel() {
    if (this.code) {
      return `${this.name}\n${this.code}`
    }
    return this.name
  }

  getGroupKey(groupBy = 'domain') {
    if (groupBy === 'subDomain') {
      return this.subDomain || this.domain
    }
    return this.domain
  }

  toJSON() {
    return {
      id: this.id,
      name: this.name,
      code: this.code,
      type: this.type,
      domain: this.domain,
      subDomain: this.subDomain,
      metadata: this.metadata
    }
  }

  static fromJSON(json) {
    return new DiagramNode(json)
  }
}

export class DiagramLink {
  constructor(options = {}) {
    this.id = options.id || ''
    this.source = options.source || ''
    this.target = options.target || ''
    this.label = options.label || ''
    this.type = options.type || LinkType.RELATION
    this.relationCode = options.relationCode || ''
    this.description = options.description || ''
    this.metadata = options.metadata || {}
  }

  getDisplayLabel() {
    return this.label || this.relationCode || ''
  }

  toJSON() {
    return {
      id: this.id,
      source: this.source,
      target: this.target,
      label: this.label,
      type: this.type,
      relationCode: this.relationCode,
      description: this.description,
      metadata: this.metadata
    }
  }

  static fromJSON(json) {
    return new DiagramLink(json)
  }
}

export class DiagramContainer {
  constructor(options = {}) {
    this.id = options.id || ''
    this.name = options.name || ''
    this.title = options.title || ''
    this.type = options.type || ContainerType.DOMAIN
    this.nodes = options.nodes || []
    this.parent = options.parent || null
    this.level = options.level || 0
    this.metadata = options.metadata || {}
  }

  addNode(nodeId) {
    if (!this.nodes.includes(nodeId)) {
      this.nodes.push(nodeId)
    }
  }

  removeNode(nodeId) {
    const index = this.nodes.indexOf(nodeId)
    if (index > -1) {
      this.nodes.splice(index, 1)
    }
  }

  getDisplayTitle(format = 'simple', template = '{parent}/{name}') {
    if (format === 'hierarchical' && this.parent) {
      return template
        .replace('{parent}', this.parent)
        .replace('{name}', this.name)
    }
    return this.title || this.name
  }

  toJSON() {
    return {
      id: this.id,
      name: this.name,
      title: this.title,
      type: this.type,
      nodes: this.nodes,
      parent: this.parent,
      level: this.level,
      metadata: this.metadata
    }
  }

  static fromJSON(json) {
    return new DiagramContainer(json)
  }
}

export class ColorConfig {
  constructor(options = {}) {
    this.groupBy = options.groupBy || 'domain'
    this.scheme = options.scheme || 'default'
    this.centerKey = options.centerKey || ''
    this.centerColor = options.centerColor || '#D9D9D9'
    this.linkColorRule = options.linkColorRule || 'source'
    this.customColors = options.customColors || new Map()
  }

  toJSON() {
    return {
      groupBy: this.groupBy,
      scheme: this.scheme,
      centerKey: this.centerKey,
      centerColor: this.centerColor,
      linkColorRule: this.linkColorRule,
      customColors: Object.fromEntries(this.customColors)
    }
  }

  static fromJSON(json) {
    return new ColorConfig({
      ...json,
      customColors: new Map(Object.entries(json.customColors || {}))
    })
  }
}

export class LayoutConfig {
  constructor(options = {}) {
    this.direction = options.direction || 'TB'
    this.nodeSpacing = options.nodeSpacing || 80
    this.rankSpacing = options.rankSpacing || 100
    this.nodeWidth = options.nodeWidth || 180
    this.nodeHeight = options.nodeHeight || 80
    this.curve = options.curve || 'basis'
    this.padding = options.padding || 25
  }

  toMermaidConfig() {
    return {
      flowchart: {
        curve: this.curve,
        padding: this.padding,
        nodeSpacing: this.nodeSpacing,
        rankSpacing: this.rankSpacing,
        nodeWidth: this.nodeWidth,
        nodeHeight: this.nodeHeight,
        rankdir: this.direction
      }
    }
  }

  toJSON() {
    return {
      direction: this.direction,
      nodeSpacing: this.nodeSpacing,
      rankSpacing: this.rankSpacing,
      nodeWidth: this.nodeWidth,
      nodeHeight: this.nodeHeight,
      curve: this.curve,
      padding: this.padding
    }
  }

  static fromJSON(json) {
    return new LayoutConfig(json)
  }
}

export class SizeConfig {
  constructor(options = {}) {
    this.strategy = options.strategy || 'auto'
    this.fontSize = options.fontSize || 18
    this.charWidthRatio = options.charWidthRatio || 0.65
    this.lineHeight = options.lineHeight || 28
    this.padding = options.padding || 20
    this.minWidth = options.minWidth || 180
    this.minHeight = options.minHeight || 80
    this.fixedWidth = options.fixedWidth || null
    this.fixedHeight = options.fixedHeight || null
  }

  toJSON() {
    return {
      strategy: this.strategy,
      fontSize: this.fontSize,
      charWidthRatio: this.charWidthRatio,
      lineHeight: this.lineHeight,
      padding: this.padding,
      minWidth: this.minWidth,
      minHeight: this.minHeight,
      fixedWidth: this.fixedWidth,
      fixedHeight: this.fixedHeight
    }
  }

  static fromJSON(json) {
    return new SizeConfig(json)
  }
}

export class BlockDiagramData {
  constructor(options = {}) {
    this.nodes = options.nodes || []
    this.links = options.links || []
    this.containers = options.containers || []
    this.colorConfig = options.colorConfig || new ColorConfig()
    this.layoutConfig = options.layoutConfig || new LayoutConfig()
    this.sizeConfig = options.sizeConfig || new SizeConfig()
    this.nodeSizes = options.nodeSizes || new Map()
    this.nodeColors = options.nodeColors || new Map()
    this.linkColors = options.linkColors || new Map()
  }

  getNodeById(id) {
    return this.nodes.find(n => n.id === id)
  }

  getLinkById(id) {
    return this.links.find(l => l.id === id)
  }

  getContainerById(id) {
    return this.containers.find(c => c.id === id)
  }

  getNodesByContainer(containerId) {
    const container = this.getContainerById(containerId)
    if (!container) return []
    return container.nodes.map(nodeId => this.getNodeById(nodeId)).filter(Boolean)
  }

  getLinksByNode(nodeId) {
    return this.links.filter(l => l.source === nodeId || l.target === nodeId)
  }

  toJSON() {
    return {
      nodes: this.nodes.map(n => n.toJSON()),
      links: this.links.map(l => l.toJSON()),
      containers: this.containers.map(c => c.toJSON()),
      colorConfig: this.colorConfig.toJSON(),
      layoutConfig: this.layoutConfig.toJSON(),
      sizeConfig: this.sizeConfig.toJSON(),
      nodeSizes: Object.fromEntries(this.nodeSizes),
      nodeColors: Object.fromEntries(this.nodeColors),
      linkColors: Object.fromEntries(this.linkColors)
    }
  }

  static fromJSON(json) {
    return new BlockDiagramData({
      nodes: (json.nodes || []).map(n => DiagramNode.fromJSON(n)),
      links: (json.links || []).map(l => DiagramLink.fromJSON(l)),
      containers: (json.containers || []).map(c => DiagramContainer.fromJSON(c)),
      colorConfig: ColorConfig.fromJSON(json.colorConfig || {}),
      layoutConfig: LayoutConfig.fromJSON(json.layoutConfig || {}),
      sizeConfig: SizeConfig.fromJSON(json.sizeConfig || {}),
      nodeSizes: new Map(Object.entries(json.nodeSizes || {})),
      nodeColors: new Map(Object.entries(json.nodeColors || {})),
      linkColors: new Map(Object.entries(json.linkColors || {}))
    })
  }
}

export function createNode(options) {
  return new DiagramNode(options)
}

export function createLink(options) {
  return new DiagramLink(options)
}

export function createContainer(options) {
  return new DiagramContainer(options)
}

export function createDiagramData(options) {
  return new BlockDiagramData(options)
}
