import { sortContainersByPosition } from './positionUtils.js'

export function generateLinearLayout(containers, positions = [], direction = 'horizontal', nodeMap, definedNodes) {
  if (!containers || containers.length === 0) {
    return ''
  }

  const sortedContainers = sortContainersByPosition(containers, positions)

  let mermaid = `\n%% 线性布局 - ${direction === 'horizontal' ? '水平' : '垂直'}\n`

  sortedContainers.forEach((container, idx) => {
    if (container) {
      const containerId = `C${idx + 1}`
      const containerName = container.fullTitle || container.name || 'Container'
      mermaid += `subgraph ${containerId}["${containerName}"]\n`
      
      if (container.nodes && container.nodes.length > 0 && nodeMap) {
        container.nodes.forEach(nodeId => {
          const node = nodeMap.get(nodeId)
          if (node) {
            if (definedNodes && !definedNodes.has(node.id)) {
              const nodeLabel = `${node.name}\\n(${node.code})`
              mermaid += `  ${nodeId}["${nodeLabel}"]:::node\n`
              definedNodes.add(node.id)
            } else {
              mermaid += `  ${nodeId}\n`
            }
          }
        })
      }
      mermaid += 'end\n'
      mermaid += `style ${containerId} fill:#ffffff,stroke:#666666,stroke-width:2px\n`
    }
  })

  return mermaid
}
