import { SizeConfig } from '../model'

export function useSizeCalculator() {
  const calculateNodeSize = (node, config) => {
    if (!config) {
      config = new SizeConfig()
    }

    switch (config.strategy) {
      case 'fixed':
        return calculateFixedSize(config)
      case 'content-based':
        return calculateContentBasedSize(node, config)
      case 'auto':
      default:
        return calculateAutoSize(node, config)
    }
  }

  const calculateFixedSize = (config) => {
    return {
      width: config.fixedWidth || config.minWidth || 180,
      height: config.fixedHeight || config.minHeight || 80
    }
  }

  const calculateContentBasedSize = (node, config) => {
    const { fontSize = 18, charWidthRatio = 0.65, lineHeight = 28, padding = 20, minWidth = 180, minHeight = 80 } = config

    const text = node.getDisplayLabel ? node.getDisplayLabel() : `${node.name}${node.code ? '\n' + node.code : ''}`
    const lines = text.split('\n')
    const maxLineLength = Math.max(...lines.map(line => line.length))

    const charWidth = fontSize * charWidthRatio
    const textWidth = maxLineLength * charWidth
    const textHeight = lines.length * lineHeight

    const width = Math.max(minWidth, textWidth + padding * 2)
    const height = Math.max(minHeight, textHeight + padding * 2)

    return { width, height }
  }

  const calculateAutoSize = (node, config) => {
    return calculateContentBasedSize(node, config)
  }

  const calculateAllNodeSizes = (nodes, config) => {
    const sizeMap = new Map()

    nodes.forEach(node => {
      const size = calculateNodeSize(node, config)
      sizeMap.set(node.id, size)
    })

    return sizeMap
  }

  const calculateContainerSize = (container, nodeSizes, nodePositions, config) => {
    const { padding = 30, titleHeight = 40, borderWidth = 2 } = config || {}

    let maxX = 0
    let maxY = 0

    container.nodes.forEach(nodeId => {
      const size = nodeSizes.get(nodeId)
      const pos = nodePositions ? nodePositions.get(nodeId) : null

      if (size) {
        const x = pos ? pos.x : 0
        const y = pos ? pos.y : 0
        maxX = Math.max(maxX, x + size.width)
        maxY = Math.max(maxY, y + size.height)
      }
    })

    return {
      width: maxX + padding * 2 + borderWidth * 2,
      height: maxY + padding * 2 + titleHeight + borderWidth * 2
    }
  }

  const calculateAllContainerSizes = (containers, nodeSizes, nodePositions, config) => {
    const sizeMap = new Map()

    containers.forEach(container => {
      const size = calculateContainerSize(container, nodeSizes, nodePositions, config)
      sizeMap.set(container.id, size)
    })

    return sizeMap
  }

  const estimateTextWidth = (text, fontSize = 18, charWidthRatio = 0.65) => {
    const charWidth = fontSize * charWidthRatio
    const lines = text.split('\n')
    const maxLineLength = Math.max(...lines.map(line => line.length))
    return maxLineLength * charWidth
  }

  const estimateTextHeight = (text, lineHeight = 28) => {
    const lines = text.split('\n')
    return lines.length * lineHeight
  }

  return {
    calculateNodeSize,
    calculateFixedSize,
    calculateContentBasedSize,
    calculateAutoSize,
    calculateAllNodeSizes,
    calculateContainerSize,
    calculateAllContainerSizes,
    estimateTextWidth,
    estimateTextHeight
  }
}

export const sizeCalculator = useSizeCalculator()
