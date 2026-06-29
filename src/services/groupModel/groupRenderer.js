/**
 * 分组模型渲染器
 * 
 * 从统一分组模型生成 Mermaid 代码
 * 
 * 核心逻辑：
 * 1. 遍历分组树，生成嵌套 subgraph
 * 2. 末端分组渲染为节点
 * 3. 关系数据独立处理
 */

import { GroupType, isTerminalGroup, traverseGroups } from './types.js'
import { ChartType, getChartTypeConfig } from './chartTypeConfig.js'

/**
 * 渲染分组模型为 Mermaid 代码
 * 
 * @param {Array} groups - 分组模型数组
 * @param {Object} options - 渲染选项
 * @param {string} options.chartType - 图表类型
 * @param {string} options.direction - 整体方向
 * @param {string} options.engine - 布局引擎 ('dagre' | 'elk')
 * @param {Array} options.relationships - 关系数据
 * @param {Map} options.nodeIdMap - 节点ID映射 (code -> mermaidId)
 * @returns {Object} { mermaidCode, styleLines, nodeColorMappings }
 */
export function renderGroupModelToMermaid(groups, options = {}) {
  const {
    chartType = ChartType.BUSINESS_OBJECT,
    direction = 'LR',
    engine = 'dagre',
    relationships = [],
    nodeIdMap = { codeToIdMap: new Map(), nameToIdMap: new Map(), idToCodeMap: new Map() },
    colorMap = new Map(),
    defaultNodeColor = '#FF9AA2'
  } = options

  const config = getChartTypeConfig(chartType)
  const definedNodes = new Set()
  const styleLines = []
  const nodeColorMappings = []

  // ELK布局使用与配置一致的方向，不再反转
  // ELK的elk.direction配置会控制实际布局方向
  let actualDirection = direction

  let graphKeyword
  if (engine === 'elk') {
    graphKeyword = `flowchart-elk ${actualDirection}`
  } else {
    graphKeyword = `flowchart ${actualDirection}`
  }

  let mermaidCode = graphKeyword + '\n'

  function renderGroup(group, depth = 0) {
    const indent = '  '.repeat(depth)
    const isTerminal = config.terminalTypes.includes(group.type)

    if (isTerminal) {
      return renderTerminalNode(group, indent, definedNodes, nodeColorMappings, colorMap, defaultNodeColor)
    }

    if (!group.layout.visible) {
      return ''
    }

    const hasContent = hasGroupContent(group, config)
    if (!hasContent) {
      return ''
    }

    let code = ''
    const groupId = sanitizeId(group.id)
    const groupTitle = group.title

    code += `${indent}subgraph ${groupId}["${groupTitle}"]\n`
    
    const subDirection = group.layout.direction || actualDirection
    code += `${indent}  direction ${subDirection}\n`

    if (group._assignedNodes && group._assignedNodes.length > 0) {
      group._assignedNodes.forEach(nodeId => {
        if (!definedNodes.has(nodeId)) {
          const nodeCode = nodeIdMap.idToCodeMap.get(nodeId) || nodeId
          const displayText = nodeCode !== nodeId ? `${nodeId}\\n(${nodeCode})` : nodeId
          code += `${indent}  ${nodeId}["${displayText}"]\n`
          definedNodes.add(nodeId)
        }
      })
    }

    if (group.children && group.children.length > 0) {
      const reversedChildren = [...group.children].reverse()
      reversedChildren.forEach(child => {
        code += renderGroup(child, depth + 1)
      })
    }

    code += `${indent}end\n`

    const styleCode = renderGroupStyle(group, groupId)
    if (styleCode) {
      styleLines.push(styleCode)
    }

    return code
  }

  const reversedGroups = [...groups].reverse()
  reversedGroups.forEach(group => {
    mermaidCode += renderGroup(group)
  })

  if (relationships.length > 0) {
    mermaidCode += renderRelationships(relationships, nodeIdMap, definedNodes)
  }

  styleLines.forEach(line => {
    mermaidCode += line
  })

  return {
    mermaidCode,
    styleLines,
    nodeColorMappings,
    definedNodes
  }
}

function renderTerminalNode(group, indent, definedNodes, nodeColorMappings, colorMap, defaultNodeColor) {
  if (definedNodes.has(group.id)) {
    return ''
  }

  let code = ''
  const displayText = group.elementRef?.code 
    ? `${group.title}\\n(${group.elementRef.code})`
    : group.title

  code += `${indent}${group.id}["${displayText}"]\n`
  definedNodes.add(group.id)

  const nodeColor = colorMap.get(group.elementRef?.code) || 
                    colorMap.get(group.id) || 
                    defaultNodeColor
  nodeColorMappings.push({
    nodeId: group.id,
    color: nodeColor,
    nodeCode: group.elementRef?.code,
    nodeName: group.title
  })

  return code
}

function hasGroupContent(group, config) {
  if (group._assignedNodes && group._assignedNodes.length > 0) {
    return true
  }

  if (group.children && group.children.length > 0) {
    return group.children.some(child => {
      if (config.terminalTypes.includes(child.type)) {
        return true
      }
      return hasGroupContent(child, config)
    })
  }

  return false
}

function sanitizeId(id) {
  return String(id).replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]/g, '_')
}

function renderGroupStyle(group, groupId) {
  if (!group.layout.visible) {
    return `style ${groupId} fill:none,stroke:none\n`
  }

  const style = group.layout.style || {}
  const fill = style.fill || '#f5f5f5'
  const stroke = style.stroke || '#333333'
  const strokeWidth = style.strokeWidth !== undefined ? style.strokeWidth : 1
  const strokeDasharray = style.strokeDasharray || ''

  let styleCode = `style ${groupId} fill:${fill},stroke:${stroke},stroke-width:${strokeWidth}px`

  if (strokeDasharray) {
    styleCode += `,stroke-dasharray:${strokeDasharray}`
  }

  styleCode += '\n'

  return styleCode
}

function renderRelationships(relationships, nodeIdMap, definedNodes) {
  let code = ''

  relationships.forEach((rel, index) => {
    let sourceId = null
    let targetId = null

    if (rel.sourceCode) {
      sourceId = nodeIdMap.codeToIdMap.get(rel.sourceCode)
    }
    if (rel.targetCode) {
      targetId = nodeIdMap.codeToIdMap.get(rel.targetCode)
    }

    if (!sourceId && rel.sourceName) {
      sourceId = nodeIdMap.nameToIdMap.get(rel.sourceName)
    }
    if (!targetId && rel.targetName) {
      targetId = nodeIdMap.nameToIdMap.get(rel.targetName)
    }

    if (sourceId && targetId) {
      const label = rel.relationCode || ''
      code += `  ${sourceId} -->|"${label}"| ${targetId}\n`
    }
  })

  return code
}

/**
 * 渲染节点样式
 */
export function renderNodeStyles(nodeColorMappings) {
  let code = ''

  nodeColorMappings.forEach(({ nodeId, color }) => {
    code += `  style ${nodeId} fill:${color},stroke:#333,stroke-width:1px\n`
  })

  return code
}

/**
 * 生成 classDef 样式定义
 */
export function generateClassDefs() {
  return `  classDef node fill:#fafafa,stroke:#666,stroke-width:1px,color:#333
  classDef container fill:#f0f0f0,stroke:#999,stroke-width:2px,color:#333
`
}

/**
 * 从分组模型提取所有节点信息
 */
export function extractNodesFromGroups(groups, chartType) {
  const config = getChartTypeConfig(chartType)
  const nodes = []

  traverseGroups(groups, (group) => {
    if (config.terminalTypes.includes(group.type)) {
      nodes.push({
        id: group.id,
        title: group.title,
        code: group.elementRef?.code,
        type: group.type
      })
    }
  })

  return nodes
}
