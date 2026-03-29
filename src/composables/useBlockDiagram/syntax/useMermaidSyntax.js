import { BlockDiagramData } from '../model'

export function useMermaidSyntax() {
  const generateCode = (data, strategy) => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return 'graph TD\n  A[No Data]'
    }

    let code = 'graph TD\n'

    code += generateClassDefs(strategy)
    code += generateContainers(data, strategy)
    code += generateLinks(data, strategy)
    code += generateStyles(data, strategy)

    return code
  }

  const generateClassDefs = (strategy) => {
    let code = ''
    code += '  classDef largeNode fill:#fff,stroke:#333,stroke-width:2px,rx:5,ry:5\n'
    code += '  classDef serviceModuleNode fill:#fff,stroke:#333,stroke-width:2px,rx:5,ry:5\n'
    return code
  }

  const generateContainers = (data, strategy) => {
    let code = ''

    if (!data.containers || data.containers.length === 0) {
      data.nodes.forEach(node => {
        const label = getNodeLabel(node)
        code += `  ${node.id}["${label}"]:::largeNode\n`
      })
      return code
    }

    data.containers.forEach(container => {
      const title = getContainerTitle(container, strategy)
      code += `  subgraph ${container.id}["${title}"]\n`

      container.nodes.forEach(nodeId => {
        const node = data.nodes.find(n => n.id === nodeId)
        if (node) {
          const label = getNodeLabel(node)
          code += `    ${node.id}["${label}"]:::largeNode\n`
        }
      })

      code += '  end\n'
      code += `  style ${container.id} fill:#ffffff,stroke:#333,stroke-width:2px\n`
    })

    const containerNodeIds = new Set()
    data.containers.forEach(container => {
      container.nodes.forEach(nodeId => containerNodeIds.add(nodeId))
    })

    data.nodes.forEach(node => {
      if (!containerNodeIds.has(node.id)) {
        const label = getNodeLabel(node)
        code += `  ${node.id}["${label}"]:::largeNode\n`
      }
    })

    return code
  }

  const generateLinks = (data, strategy) => {
    let code = ''

    if (!data.links) {
      return code
    }

    data.links.forEach(link => {
      const label = link.label || link.relationCode || ''
      code += `  ${link.source} -->|"${label}"| ${link.target}\n`
    })

    return code
  }

  const generateStyles = (data, strategy) => {
    let code = ''

    data.nodes.forEach(node => {
      const color = data.nodeColors?.get(node.id)
      if (color) {
        code += `  style ${node.id} fill:${color},stroke:#333,stroke-width:2px\n`
      }
    })

    return code
  }

  const getNodeLabel = (node) => {
    if (node.getDisplayLabel) {
      return node.getDisplayLabel()
    }
    if (node.code) {
      return `${node.name}\\n${node.code}`
    }
    return node.name
  }

  const getContainerTitle = (container, strategy) => {
    const format = strategy?.behaviorConfig?.container?.titleFormat || 'simple'
    const template = strategy?.behaviorConfig?.container?.hierarchicalTemplate || '{parent}/{name}'

    if (format === 'hierarchical' && container.parent) {
      return template
        .replace('{parent}', container.parent)
        .replace('{name}', container.name)
    }

    return container.title || container.name
  }

  const generateFullCode = (data, strategy) => {
    return generateCode(data, strategy)
  }

  return {
    generateCode,
    generateContainers,
    generateNodes: generateContainers,
    generateLinks,
    generateStyles,
    generateClassDefs,
    generateFullCode,
    getNodeLabel,
    getContainerTitle
  }
}

export const mermaidSyntax = useMermaidSyntax()
