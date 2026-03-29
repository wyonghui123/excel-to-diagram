/**
 * 解析网格尺寸
 * @param {string} layoutType - 布局类型，如 'grid-3x3'
 * @returns {{rows: number, cols: number}}
 */
export function parseGridSize(layoutType) {
  if (!layoutType || !layoutType.startsWith('grid-')) {
    return { rows: 0, cols: 0 }
  }

  const [rows, cols] = layoutType.replace('grid-', '').split('x').map(Number)
  return { rows: rows || 0, cols: cols || 0 }
}

/**
 * 生成网格标签（用于UI展示）
 * @param {number} rows - 行数
 * @param {number} cols - 列数
 * @returns {Array<{label: string, position: number}>}
 */
export function generateGridLabels(rows, cols) {
  const labels = []
  const rowLabels = rows === 1 ? [''] : (rows === 2 ? ['上', '下'] : (rows === 3 ? ['上', '中', '下'] : ['上', '中', '下', '底']))
  const colLabels = cols === 1 ? [''] : (cols === 2 ? ['左', '右'] : (cols === 3 ? ['左', '中', '右'] : ['左', '中', '右', '末']))

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      labels.push({
        label: rowLabels[r] + colLabels[c],
        position: r * cols + c
      })
    }
  }

  return labels
}

/**
 * 根据位置数组对容器进行排序
 * @param {Array} containers - 容器列表
 * @param {Array} positions - 位置映射数组
 * @returns {Array} - 排序后的容器数组
 */
export function sortContainersByPosition(containers, positions) {
  console.log('[sortContainersByPosition] containers:', containers?.length, 'positions:', positions?.length, JSON.stringify(positions))
  if (!containers || containers.length === 0) {
    console.log('[sortContainersByPosition] No containers, returning []')
    return []
  }
  
  if (!positions || positions.length === 0) {
    console.log('[sortContainersByPosition] No positions, returning containers copy:', containers.length)
    return [...containers]
  }

  const result = []

  containers.forEach((container, idx) => {
    let position = positions[idx]
    if (typeof position !== 'number') {
      position = idx
    }
    console.log(`[sortContainersByPosition] Container ${idx} -> position ${position}`)
    result[position] = container
  })

  console.log('[sortContainersByPosition] result before filter:', result)
  return result.filter(Boolean)
}

/**
 * 获取网格的格子总数
 * @param {string} layoutType
 * @returns {number}
 */
export function getGridTotalCells(layoutType) {
  const { rows, cols } = parseGridSize(layoutType)
  return rows * cols
}