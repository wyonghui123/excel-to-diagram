import { isTerminalGroup } from './types.js'

export class UnifiedRenderer {
  static render(groupModel, links, chartType, options = {}) {
    const flattenedGroups = groupModel.getFlattenedGroups()
    console.log('[UnifiedRenderer] flattenedGroups count:', flattenedGroups.length)
    flattenedGroups.forEach((g, i) => {
      console.log(`  [${i}] id=${g.id}, type=${g.type}, title=${g.title}, isTerminal=${isTerminalGroup(g, chartType)}, children=${JSON.stringify(g.children?.map(c => c.id || c))}, enabled=${g.enabled}, _disabledAncestorPath=${JSON.stringify(g._disabledAncestorPath)}`)
    })

    const codeToIdMap = new Map()
    flattenedGroups.forEach(group => {
      const code = group.elementRef?.code
      // 关键修复 v26: 只让终端节点 (BO/SM) 的 code 进入 codeToIdMap
      // 否则 SD_TEST600 (sub_domain) 和 BO_TEST600 (business_object) code 都是 "TEST600"
      // → 后注册的会覆盖先注册的 (SD 通常在前, 导致 link source 变成 SD_TEST600)
      if (code && isTerminalGroup(group, chartType)) {
        codeToIdMap.set(code, group.id)
      }
    })

    let code = options.layoutEngine === 'elk'
      ? 'flowchart-elk LR\n'
      : 'flowchart LR\n'

    const processedGroups = new Set()
    const childIds = new Set()
    flattenedGroups.forEach(g => {
      if (g.children && g.children.length > 0) {
        g.children.forEach(c => {
          if (c.id) childIds.add(c.id)
        })
      }
    })
    const rootGroups = flattenedGroups.filter(g => !childIds.has(g.id))
    console.log('[UnifiedRenderer] rootGroups count:', rootGroups.length)

    rootGroups.forEach(group => {
      if (!processedGroups.has(group.id)) {
        code += UnifiedRenderer.renderGroupFromFlattened(group, flattenedGroups, chartType, 0, processedGroups)
      }
    })

    links.forEach(link => {
      const sourceId = codeToIdMap.get(link.source) || link.source
      const targetId = codeToIdMap.get(link.target) || link.target
      if (sourceId && targetId) {
        // 关键修复 v26: label 中的特殊字符 ("|", 双引号, 换行) 会让 mermaid 11 报 "Syntax error in text"
        // 处理: 1) 替换 | → / 2) 替换换行 → 空格 3) 移除多余引号
        // 4) 如果 label 为空或纯空白, 仍输出不带 label 的 link
        let safeLabel = ''
        if (link.label && String(link.label).trim()) {
          safeLabel = String(link.label)
            .replace(/\|/g, '/')           // 避免与 mermaid label 语法冲突
            .replace(/[\r\n]+/g, ' ')      // 换行转空格
            .replace(/"/g, "'")            // 双引号转单引号
            .trim()
        }
        const labelPart = safeLabel ? `|${safeLabel}|` : ''
        code += `  ${sourceId} -->${labelPart} ${targetId}\n`
      }
    })

    processedGroups.clear()
    rootGroups.forEach(group => {
      if (!processedGroups.has(group.id)) {
        code += UnifiedRenderer.renderStylesFromFlattened(group, flattenedGroups, chartType, processedGroups)
      }
    })

    return code
  }

  static renderGroupFromFlattened(group, flattenedGroups, chartType, depth, processedGroups) {
    if (processedGroups.has(group.id)) {
      return ''
    }
    processedGroups.add(group.id)

    const isTerminal = isTerminalGroup(group, chartType)
    const indent = '  '.repeat(depth + 1)
    let code = ''

    const disabledPath = group._disabledAncestorPath
    const displayTitle = disabledPath && disabledPath.length > 0
      ? `${group.title}（${disabledPath.join(' / ')}）`
      : (group.title || group.elementRef?.name || group.id)

    console.log(`[UnifiedRenderer] renderGroup: id=${group.id}, type=${group.type}, isTerminal=${isTerminal}, title=${displayTitle}, children=${group.children?.length}, _disabledAncestorPath=${JSON.stringify(disabledPath)}`)

    if (isTerminal) {
      const displayCode = group.elementRef?.code ? `\\n(${group.elementRef.code})` : ''
      const centerMark = group.isCenter ? '◆ ' : ''
      code += `${indent}${group.id}["${centerMark}${group.title}${displayCode}"]\n`
    } else {
      code += `${indent}subgraph ${group.id}["${displayTitle}"]\n`
      code += `${indent}  direction ${group.layout?.direction || 'TB'}\n`

      if (group.children && group.children.length > 0) {
        const childrenMap = new Map()
        flattenedGroups.forEach(g => {
          childrenMap.set(g.id, g)
        })

        console.log(`[UnifiedRenderer] container ${group.id} has ${group.children.length} children`)

        group.children.forEach(childRef => {
          const child = childRef.id ? childRef : childrenMap.get(childRef)
          if (child) {
            // 检查 child 是否是终端节点（SM 或 BO）
            const childIsTerminal = isTerminalGroup(child, chartType)
            if (childIsTerminal) {
              // 终端节点直接渲染，不递归
              const childTitle = child.title || child.name || child.id
              const childCode = child.elementRef?.code || child.code || ''
              const displayCode = childCode ? `\\n(${childCode})` : ''
              const centerMark = child.isCenter ? '◆ ' : ''
              const childDisabledPath = child._disabledAncestorPath
              const childDisplayTitle = childDisabledPath && childDisabledPath.length > 0
                ? `${childTitle}（${childDisabledPath.join(' / ')}）`
                : childTitle
              console.log(`[UnifiedRenderer]   rendering child ${child.id} as terminal: ${childDisplayTitle}`)
              code += `${indent}  ${child.id}["${centerMark}${childDisplayTitle}${displayCode}"]\n`
            } else if (!processedGroups.has(child.id)) {
              console.log(`[UnifiedRenderer]   rendering child ${child.id}`)
              code += UnifiedRenderer.renderGroupFromFlattened(child, flattenedGroups, chartType, depth + 1, processedGroups)
            } else {
              console.log(`[UnifiedRenderer]   child ${child.id} already processed`)
            }
          } else {
            console.log(`[UnifiedRenderer]   child NOT FOUND:`, childRef)
          }
        })
      }

      // 渲染 containers（终端节点）- 兼容旧结构
      if (group.containers && group.containers.length > 0) {
        console.log(`[UnifiedRenderer] container ${group.id} has ${group.containers.length} containers`)
        group.containers.forEach(container => {
          const isContainerTerminal = isTerminalGroup(container, chartType)
          if (isContainerTerminal) {
            const containerTitle = container.title || container.name || container.id
            const containerCode = container.elementRef?.code || container.code || ''
            const displayCode = containerCode ? `\\n(${containerCode})` : ''
            const centerMark = container.isCenter ? '◆ ' : ''
            const containerDisabledPath = container._disabledAncestorPath
            const containerDisplayTitle = containerDisabledPath && containerDisabledPath.length > 0
              ? `${containerTitle}（${containerDisabledPath.join(' / ')}）`
              : containerTitle
            console.log(`[UnifiedRenderer]   rendering container ${container.id} as terminal: ${containerDisplayTitle}`)
            code += `${indent}  ${container.id}["${centerMark}${containerDisplayTitle}${displayCode}"]\n`
          }
        })
      } else if (!group.children || group.children.length === 0) {
        console.log(`[UnifiedRenderer] container ${group.id} has NO children and NO containers`)
      }

      code += `${indent}end\n`
    }

    return code
  }

  static renderStylesFromFlattened(group, flattenedGroups, chartType, processedGroups) {
    if (processedGroups.has(group.id)) {
      return ''
    }
    processedGroups.add(group.id)

    const isTerminal = isTerminalGroup(group, chartType)
    let code = ''

    if (isTerminal && group.color) {
      const textColor = group.textColor || 'black'
      code += `  style ${group.id} fill:${group.color},color:${textColor},stroke:${group.color}\n`
    } else if (!isTerminal) {
      if (group.color) {
        code += `  style ${group.id} fill:${group.color},stroke:#999,color:#333\n`
      }
      if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
        code += `  style ${group.id} stroke-dasharray:5 5,fill:#fafafa,stroke:#999\n`
      }
    }

    if (group.children && group.children.length > 0) {
      const childrenMap = new Map()
      flattenedGroups.forEach(g => {
        childrenMap.set(g.id, g)
      })

      group.children.forEach(childRef => {
        const child = childRef.id ? childRef : childrenMap.get(childRef)
        if (child && !processedGroups.has(child.id)) {
          code += UnifiedRenderer.renderStylesFromFlattened(child, flattenedGroups, chartType, processedGroups)
        }
      })
    }

    return code
  }
}
