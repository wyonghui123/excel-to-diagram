import { sortContainersByPosition } from './positionUtils.js'

/**
 * 生成引导式网格布局的 Mermaid 语法
 * @param {Array} containers - 容器列表
 * @param {number} rows - 行数
 * @param {number} cols - 列数
 * @param {Array} positions - 位置映射（可选）
 * @returns {string} - Mermaid 语法
 */
export function generateGridLayout(containers, rows, cols, positions = []) {
  const sortedContainers = sortContainersByPosition(containers, positions)

  let mermaid = '\n%% 引导式网格布局\n'

  // 样式定义
  mermaid += 'classDef rowStyle fill:none,stroke:none\n'
  mermaid += 'classDef anchorStyle fill:none,stroke:none\n'
  mermaid += 'classDef subgraphStyle fill:none,stroke:#33333320, rx:8, ry:8\n\n'

  // 创建行子图
  for (let r = 0; r < rows; r++) {
    mermaid += `subgraph Row${r} [" "]\n`
    mermaid += 'direction LR\n'

    for (let c = 0; c < cols; c++) {
      const idx = r * cols + c
      const container = sortedContainers[idx]

      if (container) {
        mermaid += `subgraph C${container.id || idx}["${container.name || container.fullTitle || 'Container'}"]\n`

        if (container.nodes && Array.isArray(container.nodes)) {
          container.nodes.forEach(nodeId => {
            mermaid += `${nodeId}\n`
          })
        }

        mermaid += 'end\n'
      } else {
        // 空位：添加不可见占位节点
        mermaid += `Empty${idx}(( ))\n`
      }

      // 同行容器之间用不可见边连接，引导水平布局
      if (c < cols - 1) {
        if (sortedContainers[idx] && sortedContainers[idx + 1]) {
          mermaid += `${sortedContainers[idx].id || idx} ~~~ ${sortedContainers[idx + 1]?.id || (idx + 1)}\n`
        }
      }
    }

    mermaid += 'end\n'
    mermaid += `class Row${r} rowStyle\n\n`
  }

  // 行之间的连接，引导垂直布局
  for (let r = 0; r < rows - 1; r++) {
    const currentRowFirstIdx = r * cols
    const nextRowFirstIdx = (r + 1) * cols
    const currentFirst = sortedContainers[currentRowFirstIdx]
    const nextFirst = sortedContainers[nextRowFirstIdx]

    if (currentFirst && nextFirst) {
      mermaid += `${currentFirst.id || currentRowFirstIdx} -.-> ${nextFirst.id || nextRowFirstIdx}\n`
    }
  }

  // 隐藏空位节点样式
  mermaid += '\nclass '
  for (let i = 0; i < rows * cols; i++) {
    if (!sortedContainers[i]) {
      mermaid += `Empty${i},`
    }
  }
  mermaid = mermaid.slice(0, -1) + ' anchorStyle\n'

  return mermaid
}