import { sortContainersByPosition } from './positionUtils.js'

export function generateZoneLayout(containers, positions = [], layoutEngine = 'elk', zoneRowCount = 3, nodeMap, definedNodes) {
  console.log('[elkZoneLayout] containers:', containers?.map((c, i) => `${i}: ${c?.fullTitle || c?.name}`))
  console.log('[elkZoneLayout] positions:', JSON.stringify(positions))
  
  if (!containers || containers.length === 0) {
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
          .map(idx => ({ container: containers[idx], originalIdx: idx }))
          .filter(item => item.container)
        rowMap.set(pos.row, rowContainers)
      }
    })
  }
  
  if (rowMap.size === 0) {
    const containersPerRow = Math.ceil(containers.length / rows)
    for (let r = 0; r < rows; r++) {
      const rowContainers = []
      for (let c = 0; c < containersPerRow; c++) {
        const idx = r * containersPerRow + c
        if (containers[idx]) {
          rowContainers.push({ container: containers[idx], originalIdx: idx })
        }
      }
      if (rowContainers.length > 0) {
        rowMap.set(r, rowContainers)
      }
    }
  }

  console.log('[elkZoneLayout] rowMap:', [...rowMap.entries()].map(([r, items]) => 
    `Row${r}: ${items.map(i => i.container?.fullTitle || i.container?.name).join(', ')}`
  ))

  const sortedRows = [...rowMap.keys()].sort((a, b) => a - b)
  console.log('[elkZoneLayout] sortedRows:', sortedRows)
  
  const styleLines = []

  const rowFirstNodes = []
  const rowLastNodes = []

  for (const r of sortedRows) {
    const rowContainers = rowMap.get(r) || []
    if (rowContainers.length === 0) continue

    console.log(`[elkZoneLayout] Generating Row${r} with containers:`, rowContainers.map(i => i.container?.fullTitle || i.container?.name))

    mermaid += `subgraph Row${r}["第${r + 1}行"]\n`
    mermaid += 'direction LR\n'

    rowContainers.forEach(({ container, originalIdx }) => {
      const containerId = `C${originalIdx + 1}`
      const containerName = container.fullTitle || container.name || 'Container'
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
      console.log(`[elkZoneLayout] Row${r} firstNode:`, firstContainer.container.nodes[0])
    }
    if (lastContainer?.container?.nodes?.length > 0) {
      rowLastNodes.push(lastContainer.container.nodes[lastContainer.container.nodes.length - 1])
    }
  }

  console.log('[elkZoneLayout] rowFirstNodes:', rowFirstNodes)
  
  // 在 preserveModelOrder 模式下，不添加隐藏连接，让 ELK 按照子图定义顺序布局
  // for (let i = 0; i < rowFirstNodes.length - 1; i++) {
  //   console.log(`[elkZoneLayout] Force order: ${rowFirstNodes[i]} ~~~ ${rowFirstNodes[i + 1]}`)
  //   mermaid += `${rowFirstNodes[i]} ~~~ ${rowFirstNodes[i + 1]}\n`
  // }

  if (styleLines.length > 0) {
    mermaid += '\n'
    styleLines.forEach(line => {
      mermaid += `${line}\n`
    })
  }

  console.log('[elkZoneLayout] Final mermaid code:\n', mermaid)

  return mermaid
}
