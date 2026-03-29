export const DEFAULT_SIZE_CONFIG = {
  minWidth: 180,
  minHeight: 80,
  fontSize: 18,
  charWidthRatio: 0.65,
  lineHeight: 26,
  padding: 20,
  titleHeight: 40,
  titlePadding: 10
}

export function useDynamicSizeConfig() {
  const calculateTextDimensions = (text, config = DEFAULT_SIZE_CONFIG) => {
    const lines = text.split('\n')
    const maxLineLength = Math.max(...lines.map(line => line.length))

    const charWidth = config.fontSize * config.charWidthRatio
    const textWidth = maxLineLength * charWidth
    const textHeight = lines.length * config.lineHeight

    return {
      textWidth,
      textHeight,
      maxLineLength,
      lineCount: lines.length
    }
  }

  const calculateNodeSize = (nodeText, config = DEFAULT_SIZE_CONFIG) => {
    const { textWidth, textHeight } = calculateTextDimensions(nodeText, config)

    const width = Math.max(config.minWidth, textWidth + config.padding * 2)
    const height = Math.max(config.minHeight, textHeight + config.padding * 2)

    return {
      width: Math.ceil(width),
      height: Math.ceil(height)
    }
  }

  const calculateMaxNodeSize = (nodes, getNodeText, config = DEFAULT_SIZE_CONFIG) => {
    let maxWidth = config.minWidth
    let maxHeight = config.minHeight

    nodes.forEach(node => {
      const text = getNodeText(node)
      const size = calculateNodeSize(text, config)
      maxWidth = Math.max(maxWidth, size.width)
      maxHeight = Math.max(maxHeight, size.height)
    })

    return {
      width: Math.ceil(maxWidth),
      height: Math.ceil(maxHeight)
    }
  }

  const calculateContainerSize = (title, nodeCount, nodeSize, config = DEFAULT_SIZE_CONFIG) => {
    const titleWidth = title.length * config.fontSize * config.charWidthRatio
    const titleHeight = config.titleHeight

    const nodesPerRow = Math.max(1, Math.floor(800 / nodeSize.width))
    const rows = Math.ceil(nodeCount / nodesPerRow)

    const contentWidth = Math.min(nodesPerRow, nodeCount) * nodeSize.width
    const contentHeight = rows * nodeSize.height

    return {
      width: Math.max(contentWidth, titleWidth) + config.padding * 2,
      height: contentHeight + titleHeight + config.padding * 2
    }
  }

  const mergeWithDefault = (customConfig) => {
    return {
      ...DEFAULT_SIZE_CONFIG,
      ...customConfig
    }
  }

  return {
    DEFAULT_SIZE_CONFIG,
    calculateTextDimensions,
    calculateNodeSize,
    calculateMaxNodeSize,
    calculateContainerSize,
    mergeWithDefault
  }
}
