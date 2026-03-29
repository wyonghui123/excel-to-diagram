import {
  useDiagramStrategy,
  useBlockDiagramRenderer,
  useMermaidSyntax,
  useBehaviorExecutor,
  useDiagramStyle,
  useSizeCalculator,
  BlockDiagramData,
  DiagramNode,
  DiagramLink,
  DiagramContainer
} from './index'

export function useBlockDiagram() {
  const strategyManager = useDiagramStrategy()
  const renderer = useBlockDiagramRenderer()
  const syntax = useMermaidSyntax()
  const behavior = useBehaviorExecutor()
  const style = useDiagramStyle()
  const sizeCalculator = useSizeCalculator()

  strategyManager.initializeDefaultStrategies()

  const renderBusinessObject = async (container, rawData) => {
    const strategy = strategyManager.get('business-object')
    return await renderer.render(container, rawData, strategy)
  }

  const renderServiceModule = async (container, rawData) => {
    const strategy = strategyManager.get('service-module')
    return await renderer.render(container, rawData, strategy)
  }

  const render = async (container, rawData, diagramType) => {
    const strategy = strategyManager.get(diagramType)
    if (!strategy) {
      throw new Error(`Unknown diagram type: ${diagramType}`)
    }
    return await renderer.render(container, rawData, strategy)
  }

  const registerStrategy = (type, strategy) => {
    strategyManager.register(type, strategy)
  }

  const getStrategy = (type) => {
    return strategyManager.get(type)
  }

  const update = async (container, data, strategy, changes) => {
    return await renderer.update(container, data, strategy, changes)
  }

  const destroy = (container) => {
    renderer.destroy(container)
  }

  return {
    render,
    renderBusinessObject,
    renderServiceModule,
    registerStrategy,
    getStrategy,
    update,
    destroy,
    strategyManager,
    renderer,
    syntax,
    behavior,
    style,
    sizeCalculator
  }
}

export const blockDiagram = useBlockDiagram()

export {
  useDiagramStrategy,
  useBlockDiagramRenderer,
  useMermaidSyntax,
  useBehaviorExecutor,
  useDiagramStyle,
  useSizeCalculator,
  BlockDiagramData,
  DiagramNode,
  DiagramLink,
  DiagramContainer
}
