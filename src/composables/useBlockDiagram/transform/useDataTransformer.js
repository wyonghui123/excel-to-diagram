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

export function useDataTransformer() {
  const transformers = new Map()

  const register = (type, transformer) => {
    transformers.set(type, transformer)
  }

  const get = (type) => {
    return transformers.get(type)
  }

  const transform = (rawData, diagramType) => {
    const transformer = transformers.get(diagramType)
    if (!transformer) {
      console.warn(`未找到图表类型 "${diagramType}" 的转换器`)
      return new BlockDiagramData()
    }
    return transformer.transform(rawData)
  }

  return {
    register,
    get,
    transform
  }
}

export class BaseTransformer {
  constructor(config = {}) {
    this.config = config
  }

  transform(rawData) {
    throw new Error('transform() 必须由子类实现')
  }

  createNode(options) {
    return new DiagramNode(options)
  }

  createLink(options) {
    return new DiagramLink(options)
  }

  createContainer(options) {
    return new DiagramContainer(options)
  }

  createColorConfig(options) {
    return new ColorConfig(options)
  }

  createLayoutConfig(options) {
    return new LayoutConfig(options)
  }

  createSizeConfig(options) {
    return new SizeConfig(options)
  }

  generateId(prefix = 'N') {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }
}
