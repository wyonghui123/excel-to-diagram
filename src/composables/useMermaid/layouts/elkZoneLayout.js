import { sortContainersByPosition } from './positionUtils.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'
import { filterEnabledContainers } from './containerFilter.js'

export function generateZoneLayout(containers, positions = [], layoutEngine = 'elk', zoneRowCount = 3, nodeMap, definedNodes) {
  // [v32 修复 2026-06-13] 4 layout 统一: 预过滤 disabled 容器
  // 注意: positions 数组使用原始 index, 需要建立 enabled→原始 index 映射
  const originalContainers = containers
  const enabledContainers = filterEnabledContainers(containers)
  if (!enabledContainers || enabledContainers.length === 0) {
    return ''
  }

  const rows = zoneRowCount || 3
  let mermaid = `\n%% 分区布局 - ${rows}行\n`

  const rowMap = new Map()

  if (positions && positions.length > 0 && positions[0]?.row !== undefined) {
    positions.forEach(pos => {
      if (pos && pos.row !== undefined) {
        const containerIndices = pos.containers || (pos.container !== undefined ? [pos.container] : [])
        const rowContainers = containerIndices
          .map(idx => ({ container: originalContainers[idx], originalIdx: idx }))
          .filter(item => item.container && item.container.enabled !== false)
        if (rowContainers.length > 0) {
          rowMap.set(pos.row, rowContainers)
        }
      }
    })
  }

  if (rowMap.size === 0) {
    const containersPerRow = Math.ceil(enabledContainers.length / rows)
    for (let r = 0; r < rows; r++) {
      const rowContainers = []
      for (let c = 0; c < containersPerRow; c++) {
        const enabledIdx = r * containersPerRow + c
        if (enabledContainers[enabledIdx]) {
          // 找 enabled container 在 originalContainers 中的位置 (用作 stable id)
          const originalIdx = originalContainers.indexOf(enabledContainers[enabledIdx])
          rowContainers.push({ container: enabledContainers[enabledIdx], originalIdx: originalIdx >= 0 ? originalIdx : enabledIdx })
        }
      }
      if (rowContainers.length > 0) {
        rowMap.set(r, rowContainers)
      }
    }
  }

  const sortedRows = [...rowMap.keys()].sort((a, b) => a - b)
  
  const styleLines = []

  const rowFirstNodes = []
  const rowLastNodes = []

  for (const r of sortedRows) {
    const rowContainers = rowMap.get(r) || []
    if (rowContainers.length === 0) continue

    mermaid += `subgraph Row${r}["第${r + 1}行"]\n`
    mermaid += 'direction LR\n'

    rowContainers.forEach(({ container, originalIdx }) => {
      const containerId = `C${originalIdx + 1}`
      const rawContainerName = container.fullTitle || container.name || 'Container'
      const containerName = formatContainerTitle(rawContainerName)
      mermaid += `  subgraph ${containerId}["${containerName}"]\n`
      
      if (container.nodes && container.nodes.length > 0 && nodeMap) {
        container.nodes.forEach(nodeId => {
          const node = nodeMap.get(nodeId)
          if (node) {
            if (definedNodes && !definedNodes.has(node.id)) {
              const nodeLabel = `${node.name}\\n(${node.code})`
              mermaid += `    ${nodeId}["${nodeLabel}"]:::node\n`
              definedNodes.add(node.id)
            } else {
              mermaid += `    ${nodeId}\n`
            }
          }
        })
      }
      mermaid += '  end\n'
      styleLines.push(`style ${containerId} fill:#ffffff,stroke:#666666,stroke-width:2px`)
    })

    mermaid += 'end\n'
    styleLines.push(`style Row${r} fill:#f5f5f5,stroke:#999999,stroke-width:1px,stroke-dasharray: 5 5`)
    
    const firstContainer = rowContainers[0]
    const lastContainer = rowContainers[rowContainers.length - 1]
    if (firstContainer?.container?.nodes?.length > 0) {
      rowFirstNodes.push(firstContainer.container.nodes[0])
    }
    if (lastContainer?.container?.nodes?.length > 0) {
      rowLastNodes.push(lastContainer.container.nodes[lastContainer.container.nodes.length - 1])
    }
  }

  if (styleLines.length > 0) {
    mermaid += '\n'
    styleLines.forEach(line => {
      mermaid += `${line}\n`
    })
  }

  return mermaid
}