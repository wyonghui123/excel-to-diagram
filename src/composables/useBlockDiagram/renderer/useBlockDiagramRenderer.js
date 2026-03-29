import mermaid from 'mermaid'
import { useMermaidSyntax } from '../syntax'
import { useBehaviorExecutor } from '../behavior'
import { useDiagramStyle } from '../style'
import { useSizeCalculator } from '../layout'

export function useBlockDiagramRenderer() {
  const { generateCode } = useMermaidSyntax()
  const { execute: executeBehavior } = useBehaviorExecutor()
  const { apply: applyStyles } = useDiagramStyle()
  const { calculateNodeSize, calculateContainerSize } = useSizeCalculator()

  const render = async (container, rawData, strategy) => {
    if (!container || !rawData) {
      throw new Error('Container and raw data are required')
    }

    const transformedData = strategy.transformer.transform(rawData)

    preCalculateSizes(transformedData, strategy)

    const mermaidCode = generateCode(transformedData, strategy)

    const mermaidConfig = strategy.getMermaidConfig()
    mermaid.initialize(mermaidConfig)

    const uniqueId = `diagram-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    container.innerHTML = ''
    container.removeAttribute('data-processed')

    const { svg } = await mermaid.render(uniqueId, mermaidCode, container)

    const svgElement = container.querySelector('svg')
    if (svgElement) {
      applyStyles(svgElement, transformedData, strategy)

      const elements = extractElements(svgElement, transformedData)
      executeBehavior(strategy.behaviorConfig, elements, transformedData)

      return {
        svg: svgElement,
        data: transformedData,
        elements
      }
    }

    return null
  }

  const preCalculateSizes = (data, strategy) => {
    data.nodeSizes = new Map()
    data.containerSizes = new Map()

    const sizeConfig = strategy.sizeConfig

    data.nodes.forEach(node => {
      const size = calculateNodeSize(node, sizeConfig)
      data.nodeSizes.set(node.id, size)
    })

    if (data.containers) {
      data.containers.forEach(container => {
        const containerNodes = container.nodes.map(nodeId =>
          data.nodes.find(n => n.id === nodeId)
        ).filter(Boolean)

        const containerSize = calculateContainerSize(containerNodes, sizeConfig)
        data.containerSizes.set(container.id, containerSize)
      })
    }
  }

  const extractElements = (svg, data) => {
    const paths = []
    const labels = []
    const containers = []
    const nodes = []

    const pathMap = new Map()
    const labelMap = new Map()

    const edgePaths = svg.querySelectorAll('.edgePath')
    edgePaths.forEach(edgePath => {
      const path = edgePath.querySelector('path')
      if (path) {
        paths.push(path)

        const edgeId = edgePath.id || ''
        const link = data.links?.find(l => edgeId.includes(l.id) || edgeId.includes(`${l.source}-${l.target}`))
        if (link) {
          pathMap.set(path, link)
          pathMap.set(link, path)
        }
      }
    })

    const edgeLabels = svg.querySelectorAll('.edgeLabel')
    edgeLabels.forEach(edgeLabel => {
      labels.push(edgeLabel)

      const labelId = edgeLabel.id || ''
      const link = data.links?.find(l => labelId.includes(l.id) || labelId.includes(`${l.source}-${l.target}`))
      if (link) {
        labelMap.set(edgeLabel, link)
        labelMap.set(link, edgeLabel)
      }
    })

    const clusters = svg.querySelectorAll('.cluster')
    clusters.forEach(cluster => {
      containers.push(cluster)
    })

    const nodeElements = svg.querySelectorAll('.node')
    nodeElements.forEach(nodeEl => {
      nodes.push(nodeEl)
    })

    return {
      svg,
      paths,
      labels,
      containers,
      nodes,
      pathMap,
      labelMap
    }
  }

  const update = async (container, data, strategy, changes) => {
    if (!changes || changes.length === 0) return

    const svg = container.querySelector('svg')
    if (!svg) return

    changes.forEach(change => {
      switch (change.type) {
        case 'node':
          updateNode(svg, data, change)
          break
        case 'link':
          updateLink(svg, data, change)
          break
        case 'container':
          updateContainer(svg, data, change)
          break
        case 'style':
          applyStyles(svg, data, strategy)
          break
      }
    })
  }

  const updateNode = (svg, data, change) => {
    const node = svg.querySelector(`#${change.id}`) || svg.querySelector(`[id*="${change.id}"]`)
    if (!node) return

    if (change.style) {
      const rect = node.querySelector('rect, polygon')
      if (rect) {
        Object.assign(rect.style, change.style)
      }
    }

    if (change.size) {
      const rect = node.querySelector('rect, polygon')
      if (rect) {
        rect.style.width = `${change.size.width}px`
        rect.style.height = `${change.size.height}px`
      }
    }
  }

  const updateLink = (svg, data, change) => {
    const link = svg.querySelector(`#${change.id}`) || svg.querySelector(`[id*="${change.id}"]`)
    if (!link) return

    const path = link.querySelector('path')
    if (!path) return

    if (change.style) {
      Object.assign(path.style, change.style)
    }
  }

  const updateContainer = (svg, data, change) => {
    const container = svg.querySelector(`#${change.id}`) || svg.querySelector(`[id*="${change.id}"]`)
    if (!container) return

    const rect = container.querySelector('rect')
    if (!rect) return

    if (change.style) {
      Object.assign(rect.style, change.style)
    }
  }

  const destroy = (container) => {
    const svg = container?.querySelector('svg')
    if (svg) {
      svg.remove()
    }

    const tooltip = document.getElementById('mermaid-tooltip')
    if (tooltip) {
      tooltip.remove()
    }
  }

  return {
    render,
    update,
    destroy,
    preCalculateSizes,
    extractElements,
    updateNode,
    updateLink,
    updateContainer
  }
}

export const blockDiagramRenderer = useBlockDiagramRenderer()
