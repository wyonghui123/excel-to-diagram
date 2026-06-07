/**
 * MermaidGenerator - 从 GroupModel 生成 Mermaid 代码
 * 
 * 职责：
 * 1. 将 GroupModel 转换为 Mermaid 语法
 * 2. 处理分组嵌套和样式
 * 3. 管理节点定义和连接
 */

import { isTerminalGroup } from './types.js'

export class MermaidGenerator {
  /**
   * @param {GroupModel} groupModel - 分组模型
   * @param {Object} options - 配置选项
   */
  constructor(groupModel, options = {}) {
    this.model = groupModel
    this.options = {
      chartType: options.chartType || 'BUSINESS_OBJECT',
      direction: options.direction || 'TB',
      ...options
    }
    this.definedNodes = new Set()
    this.styleLines = []
  }

  /**
   * 格式化容器标题，在长标题中添加换行符
   * @param {string} title - 原始标题
   * @param {number} maxLength - 每行最大字符数
   * @returns {string} 格式化后的标题
   */
  formatContainerTitle(title, maxLength = 12) {
    if (!title || title.length <= maxLength) {
      return title
    }
    
    // 如果标题包含 "父 / 子" 格式（如 "制造云 / 销售运营计划"），在斜杠处换行
    // 使用实际换行符，Mermaid markdown 字符串支持
    if (title.includes(' / ')) {
      return title.replace(/\s*\/\s*/g, '\n')
    }
    
    // 如果标题包含括号，在括号前换行
    const bracketMatch = title.match(/^(.+?)(\s*[（(].+[）)])$/)
    if (bracketMatch) {
      const mainPart = bracketMatch[1].trim()
      const bracketPart = bracketMatch[2].trim()
      return `${mainPart}\n${bracketPart}`
    }
    
    // 默认按长度换行
    const lines = []
    let currentLine = ''
    
    for (const char of title) {
      if (currentLine.length >= maxLength && char !== ' ') {
        lines.push(currentLine)
        currentLine = char
      } else {
        currentLine += char
      }
    }
    
    if (currentLine) {
      lines.push(currentLine)
    }
    
    return lines.join('\n')
  }

  /**
   * 生成完整的 Mermaid 代码
   * @returns {string}
   */
  generate() {
    const flattened = this.model.getFlattenedGroups()
    
    let code = `flowchart-elk ${this.options.direction}\n\n`
    code += '%% 分组布局\n'
    
    // 生成每个分组的代码
    for (const group of flattened) {
      const groupCode = this.generateGroup(group, 0)
      if (groupCode) {
        code += groupCode
      }
    }
    
    // 添加样式定义
    if (this.styleLines.length > 0) {
      code += '\n%% 样式定义\n'
      code += this.styleLines.join('\n') + '\n'
    }
    
    return code
  }

  /**
   * 生成分组代码
   * @param {Object} group - 分组对象
   * @param {number} depth - 嵌套深度
   * @returns {string}
   */
  generateGroup(group, depth = 0) {
    const isEnabled = group.layout?.enabled !== false
    const isTerminal = isTerminalGroup(group, this.options.chartType)
    
    // 如果分组被禁用且不是终端节点，不生成代码（子元素已被提升）
    if (!isEnabled && !isTerminal) {
      return ''
    }
    
    // 如果终端分组被禁用，不生成代码（子元素已被提升或该分组本身不应显示）
    if (!isEnabled && isTerminal) {
      return ''
    }
    
    const indent = '  '.repeat(depth)
    const groupId = `G_${group.id.replace(/[^a-zA-Z0-9]/g, '_')}`
    const displayTitle = this.model.getDisplayTitle(group.id)
    
    let code = ''
    
    if (isTerminal) {
      // 终端分组：直接生成节点
      code += this.generateTerminalNodes(group, indent)
    } else {
      // 非终端分组：生成 subgraph
      code += `${indent}subgraph ${groupId}["${displayTitle}"]\n`
      code += `${indent}  direction ${group.layout?.direction || 'TB'}\n`
      
      // 生成直接节点
      if (group.directNodes && group.directNodes.length > 0) {
        code += this.generateDirectNodes(group.directNodes, indent + '  ')
      }
      
      // 生成子容器
      if (group.containers && group.containers.length > 0) {
        for (let i = 0; i < group.containers.length; i++) {
          const containerCode = this.generateContainer(
            group.containers[i], 
            `${groupId}_C${i + 1}`,
            depth + 1
          )
          if (containerCode) {
            code += containerCode
          }
        }
      }
      
      // 生成子分组
      if (group.children && group.children.length > 0) {
        for (const child of group.children) {
          const childCode = this.generateGroup(child, depth + 1)
          if (childCode) {
            code += childCode
          }
        }
      }
      
      code += `${indent}end\n`
    }
    
    // 添加样式
    if (group.layout?.style) {
      this.addStyle(groupId, group.layout.style)
    }
    
    return code
  }

  /**
   * 生成容器代码
   * @param {Object} container - 容器对象
   * @param {string} containerId - 容器 ID
   * @param {number} depth - 嵌套深度
   * @returns {string}
   */
  generateContainer(container, containerId, depth) {
    if (!container.nodes || container.nodes.length === 0) {
      return ''
    }
    
    const isEnabled = container.enabled !== false
    if (!isEnabled) {
      // 容器被禁用，直接生成节点
      return this.generateDirectNodes(container.nodes, '  '.repeat(depth))
    }
    
    const indent = '  '.repeat(depth)
    const rawTitle = container.fullTitle || container.name || 'Container'
    const displayTitle = this.formatContainerTitle(rawTitle)
    
    let code = `${indent}subgraph ${containerId}["${displayTitle}"]\n`
    code += `${indent}  direction ${container.direction || 'TB'}\n`
    
    for (const nodeId of container.nodes) {
      if (!this.definedNodes.has(nodeId)) {
        const node = this.getNodeData(nodeId)
        if (node) {
          const displayText = node.code 
            ? `${node.name}\\n(${node.code})`
            : node.name
          code += `${indent}  ${nodeId}["${displayText}"]\n`
          this.definedNodes.add(nodeId)
        }
      }
    }
    
    code += `${indent}end\n`
    
    return code
  }

  /**
   * 生成终端分组的节点
   * @param {Object} group - 终端分组
   * @param {string} indent - 缩进
   * @returns {string}
   */
  generateTerminalNodes(group, indent) {
    let code = ''
    
    // 终端分组的节点存储在 elementRef 或 nodes 中
    const nodes = group.nodes || (group.elementRef ? [group.elementRef] : [])
    
    for (const node of nodes) {
      const nodeId = node.id || node.code || node.name
      if (!this.definedNodes.has(nodeId)) {
        const displayText = node.code
          ? `${node.name}\\n(${node.code})`
          : node.name
        code += `${indent}${nodeId}["${displayText}"]\n`
        this.definedNodes.add(nodeId)
      }
    }
    
    return code
  }

  /**
   * 生成直接节点
   * @param {Array} nodeIds - 节点 ID 数组
   * @param {string} indent - 缩进
   * @returns {string}
   */
  generateDirectNodes(nodeIds, indent) {
    let code = ''
    
    for (const nodeId of nodeIds) {
      if (!this.definedNodes.has(nodeId)) {
        const node = this.getNodeData(nodeId)
        if (node) {
          const displayText = node.code
            ? `${node.name}\\n(${node.code})`
            : node.name
          code += `${indent}${nodeId}["${displayText}"]\n`
          this.definedNodes.add(nodeId)
        }
      }
    }
    
    return code
  }

  /**
   * 获取节点数据
   * @param {string} nodeId - 节点 ID
   * @returns {Object|null}
   */
  getNodeData(nodeId) {
    // 从 options.nodeMap 或 model 中获取节点数据
    if (this.options.nodeMap && this.options.nodeMap.has(nodeId)) {
      return this.options.nodeMap.get(nodeId)
    }
    
    // 从 GroupModel 的 groups 中查找
    for (const group of this.model.groups.values()) {
      if (group.nodes) {
        const node = group.nodes.find(n => 
          (n.id || n.code || n.name) === nodeId
        )
        if (node) return node
      }
    }
    
    return null
  }

  /**
   * 添加样式定义
   * @param {string} elementId - 元素 ID
   * @param {Object} style - 样式对象
   */
  addStyle(elementId, style) {
    const styleProps = []
    
    if (style.fill) styleProps.push(`fill:${style.fill}`)
    if (style.stroke) styleProps.push(`stroke:${style.stroke}`)
    if (style.strokeWidth) styleProps.push(`stroke-width:${style.strokeWidth}px`)
    if (style.strokeDasharray) styleProps.push(`stroke-dasharray:${style.strokeDasharray}`)
    
    if (styleProps.length > 0) {
      this.styleLines.push(`style ${elementId} ${styleProps.join(',')}`)
    }
  }

  /**
   * 重置生成器状态
   */
  reset() {
    this.definedNodes.clear()
    this.styleLines = []
  }
}

export default MermaidGenerator
