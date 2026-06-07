/**
 * GroupModel - 统一分组模型
 * 管理分组的层级结构、启用状态和扁平化处理
 */

import { isTerminalGroup } from './types.js'
import { DataFlowLogger } from './dataFlowLogger.js'
import { MAX_RECURSION_DEPTH, checkDepth, checkCycle, createVisitedSet } from './safetyUtils.js'

export class GroupModel {
  constructor(groups, options = {}) {
    this.groups = new Map()
    this.rootIds = []
    this.options = options
    this._flattenedCache = null
    this._mermaidConfigCache = null

    this.buildIndex(groups)
  }

  static fromUserConfig(architectureGroups, userConfig, chartType) {
    const model = new GroupModel(architectureGroups, { chartType })

    if (userConfig?.groups) {
      DataFlowLogger.GroupModel.fromUserConfig(userConfig, architectureGroups.length)

      function mergeUserGroupRecursive(userGroup) {
        model.mergeUserGroup(userGroup)
        if (userGroup.children && userGroup.children.length > 0) {
          for (const childUserGroup of userGroup.children) {
            mergeUserGroupRecursive(childUserGroup)
          }
        }
      }

      for (const userGroup of userConfig.groups) {
        mergeUserGroupRecursive(userGroup)
      }

    } else {
    }

    return model
  }

  buildIndex(groups, parentId = null, visited = null, depth = 0) {
    if (!checkDepth(depth, 'GroupModel.buildIndex')) {
      return
    }
    
    if (!visited) {
      visited = createVisitedSet()
    }
    
    for (const group of groups) {
      if (checkCycle(group.id, visited, 'GroupModel.buildIndex')) {
        continue
      }
      
      const node = {
        ...group,
        parentId,
        children: group.children ? [] : undefined,
        // 保留原始 containers 内容，而不是设置为空数组
        containers: group.containers ? [...group.containers] : undefined,
        _cachedDisabledPath: null
      }
      
      this.groups.set(group.id, node)
      
      if (parentId === null) {
        this.rootIds.push(group.id)
      } else {
        const parent = this.groups.get(parentId)
        if (parent) {
          parent.children.push(group.id)
        }
      }
      
      if (group.children && group.children.length > 0) {
        this.buildIndex(group.children, group.id, visited, depth + 1)
      }
      
      // 处理 containers（终端节点，如 SM 或 BO）
      if (group.containers && group.containers.length > 0) {
        for (const container of group.containers) {
          if (checkCycle(container.id, visited, 'GroupModel.buildIndex.containers')) {
            continue
          }
          const containerNode = {
            ...container,
            parentId: group.id,
            _cachedDisabledPath: null
          }
          this.groups.set(container.id, containerNode)
        }
      }
    }
  }

  mergeUserGroup(userGroup) {
    let group = this.groups.get(userGroup.id)

    if (!group && userGroup.elementCode) {
      for (const g of this.groups.values()) {
        if (g.elementRef?.code === userGroup.elementCode) {
          group = g
          break
        }
      }
    }

    if (!group && userGroup.title) {
      for (const g of this.groups.values()) {
        if (g.title === userGroup.title) {
          group = g
          break
        }
      }
    }

    if (!group) {
      return
    }

    if (userGroup.layout) {
      group.layout = {
        ...group.layout,
        ...userGroup.layout,
        style: {
          ...group.layout?.style,
          ...userGroup.layout?.style
        }
      }
    }

    if (userGroup.enabled !== undefined) {
      if (!group.layout) {
        group.layout = {}
      }
      group.layout.enabled = userGroup.enabled
    }

    // 处理 containers 属性
    if (userGroup.containers && userGroup.containers.length > 0) {
      group.containers = userGroup.containers
    }

    this._flattenedCache = null
    this._mermaidConfigCache = null
  }

  getById(id) {
    return this.groups.get(id) || null
  }

  getChildren(parentId) {
    const parent = this.groups.get(parentId)
    if (!parent || !parent.children) return []
    return parent.children.map(id => this.groups.get(id)).filter(Boolean)
  }

  getRootGroups() {
    return this.rootIds.map(id => this.groups.get(id)).filter(Boolean)
  }

  isEnabled(groupId) {
    const group = this.groups.get(groupId)
    const result = group ? group.layout?.enabled !== false : true
    return result
  }

  getDisabledAncestorPath(groupId) {
    const group = this.groups.get(groupId)
    if (!group) return []
    
    if (group._cachedDisabledPath !== null) {
      return group._cachedDisabledPath
    }

    const path = []
    const visited = createVisitedSet()
    let currentId = group.parentId
    let depth = 0
    
    while (currentId) {
      if (!checkDepth(depth, 'GroupModel.getDisabledAncestorPath')) {
        break
      }
      
      if (checkCycle(currentId, visited, 'GroupModel.getDisabledAncestorPath')) {
        break
      }
      
      const parent = this.groups.get(currentId)
      if (!parent) break
      
      if (parent.layout?.enabled === false) {
        path.unshift(parent.title)
      }
      
      currentId = parent.parentId
      depth++
    }
    
    group._cachedDisabledPath = path
    return path
  }

  getDisplayTitle(groupId) {
    const group = this.groups.get(groupId)
    if (!group) return ''
    
    const disabledPath = this.getDisabledAncestorPath(groupId)
    if (disabledPath.length === 0) {
      return group.title
    }
    
    return `${group.title}（${disabledPath.join(' / ')}）`
  }

  getFlattenedGroups() {
    if (this._flattenedCache) {
      return this._flattenedCache
    }

    const result = []
    const processed = new Set()

    const processGroup = (groupId, disabledAncestorPath = [], depth = 0) => {
    if (!checkDepth(depth, 'GroupModel.getFlattenedGroups')) {
      return
    }

    if (processed.has(groupId)) {
      return
    }
    processed.add(groupId)

    const group = this.groups.get(groupId)
    if (!group) {
      return
    }

    const isEnabled = this.isEnabled(groupId)
    const isTerminal = isTerminalGroup(group, this.options.chartType)
    
    const indent = '  '.repeat(depth)

      const inheritedDisabledPath = disabledAncestorPath.length > 0 ? disabledAncestorPath : null
      const effectiveDisabledPath = !isEnabled ? [...disabledAncestorPath, group.title] : disabledAncestorPath

      // 如果有 disabled 祖先，当前分组也应该标记为 disabled
      const shouldDisplayAsDisabled = inheritedDisabledPath !== null && isEnabled

      if (!isEnabled) {
        if (isTerminal) {
          const entry = {
            ...group,
            _disabledAncestorPath: effectiveDisabledPath
          }
          result.push(entry)
          return
        }

        if (group.children) {
          for (const childId of group.children) {
            processGroup(childId, effectiveDisabledPath, depth + 1)
          }
        }
        return
      }

      // 如果有 disabled 祖先的非末端分组，设置 enabled: false，并递归处理子节点
      // 注意：这个分组会被提升到根级别，所以它的子分组不应该继承 disabled 路径
      if (shouldDisplayAsDisabled && !isTerminal) {
        const entry = {
          ...group,
          _disabledAncestorPath: inheritedDisabledPath,
          enabled: false,
          children: []
        }
        result.push(entry)

        // 处理 children（非终端子分组）
        // 子节点不应该继承 disabled 路径，因为父分组已经显示了路径
        if (group.children) {
          for (const childId of group.children) {
            const childResult = processGroup(childId, [], depth + 1)
            if (childResult) {
              entry.children.push(childResult)
            }
          }
        }

        // 处理 containers（终端节点）- 不设置 _disabledAncestorPath
        if (group.containers) {
          for (const container of group.containers) {
            const containerEntry = {
              ...container,
              _disabledAncestorPath: undefined
            }
            entry.children.push(containerEntry)
          }
        }

        return entry
      }

      if (isTerminal) {
        const entry = {
          ...group,
          _disabledAncestorPath: inheritedDisabledPath ? effectiveDisabledPath : undefined
        }
        result.push(entry)
        return entry  // 返回 entry 以便父分组可以引用
      }

      const newGroup = {
        ...group,
        children: [],
        _disabledAncestorPath: inheritedDisabledPath ? effectiveDisabledPath : undefined
      }

      if (group.children) {
        for (const childId of group.children) {
          const child = this.groups.get(childId)
          if (!child) continue

          const childIsEnabled = this.isEnabled(childId)

          if (!childIsEnabled) {
            const childNewPath = [...effectiveDisabledPath, child.title]
            if (child.children) {
              for (const grandChildId of child.children) {
                processGroup(grandChildId, childNewPath, depth + 1)
              }
            }
          } else {
            const childResult = processGroup(childId, effectiveDisabledPath, depth + 1)
            if (childResult) {
              newGroup.children.push(childResult)
            }
          }
        }
      }

      // 处理 containers（终端节点）- 需要设置 _disabledAncestorPath
      if (group.containers) {
        for (const container of group.containers) {
          const containerEntry = {
            ...container,
            _disabledAncestorPath: inheritedDisabledPath ? effectiveDisabledPath : undefined
          }
          newGroup.children.push(containerEntry)
        }
      }

      result.push(newGroup)
      return newGroup
    }

    for (const rootId of this.rootIds) {
      processGroup(rootId)
    }

    this._flattenedCache = result
    return result
  }

  toMermaidConfig() {
    // 强制清除缓存以便调试
    if (this._mermaidConfigCache) {
      this._mermaidConfigCache = null
    }
    
    const titleMap = {}
    const groups = []

    // 使用 getFlattenedGroups 获取处理后的分组（包含 _disabledAncestorPath）
    const flattened = this.getFlattenedGroups()
    // 创建 ID 到扁平化分组的映射
    const flattenedMap = new Map()
    flattened.forEach(g => {
      flattenedMap.set(g.id, g)
    })

    const convertGroup = (group, disabledAncestorPath = [], depth = 0) => {
      if (!group) {
        return null
      }
      
      if (!checkDepth(depth, 'GroupModel.toMermaidConfig')) {
        return null
      }
      
      const isTerminal = isTerminalGroup(group, this.options.chartType)
      const isEnabled = this.isEnabled(group.id)
      
      // 判断是否有 disabled 祖先（从参数传入的，不是当前分组）
      const hasDisabledAncestor = disabledAncestorPath.length > 0

      // 只有当分组本身被禁用时，才将标题添加到路径
      // 被提升的分组（有 disabled 祖先）虽然会显示，但不应该添加路径到子分组
      const currentDisabledPath = !isEnabled
        ? [...disabledAncestorPath, group.title]
        : []
      
      // 使用扁平化分组中的 _disabledAncestorPath（如果存在）
      // 但只对有 disabled 祖先但本身启用的分组使用，对被禁用的分组不使用
      const flattenedGroup = flattenedMap.get(group.id)
      // effectiveDisabledPath 只在以下情况使用：
      // 1. 分组本身被禁用 (isEnabled=false)
      // 2. 分组有 disabled 祖先但本身启用 (hasDisabledAncestor=true && isEnabled=true)
      // 这种情况不应该显示路径，所以 effectiveDisabledPath 应该为空
      const effectiveDisabledPath = (hasDisabledAncestor && isEnabled)
        ? []  // 有 disabled 祖先但本身启用，不显示路径
        : (isEnabled ? [] : (flattenedGroup?._disabledAncestorPath || disabledAncestorPath))
      
      const displayTitle = effectiveDisabledPath.length > 0
        ? `${group.title}（${effectiveDisabledPath.join(' / ')}）`
        : group.title
      
      const legacyGroup = {
        id: group.id,
        type: group.type,
        elementCode: group.elementRef?.code || group.elementCode,
        name: group.title,
        title: displayTitle,
        fullTitle: displayTitle,
        direction: group.layout?.direction || 'TB',
        visible: group.layout?.visible !== false,
        // 如果有 disabled 祖先，分组应该显示（标题包含路径信息），enabled 保持自己的状态
        // 只有当分组本身被禁用且没有 disabled 祖先时，才返回 null
        enabled: isEnabled,
        style: group.layout?.style || {},
        // 保留 disabled 祖先路径，用于 hasGroupContent 判断是否是被提升的分组
        _disabledAncestorPath: flattenedGroup?._disabledAncestorPath || (hasDisabledAncestor ? disabledAncestorPath : undefined)
      }
      
      // 如果分组本身被禁用（!isEnabled）且没有被提升（!hasDisabledAncestor），返回 null
      // 如果分组被提升（有 disabled 祖先），应该显示
      if (!isEnabled && !hasDisabledAncestor) {
        return null
      }

      // 如果分组本身被禁用但被提升，显示标题时应该显示 disabled 祖先路径
      if (!isEnabled && hasDisabledAncestor) {
      }

      // 如果分组被禁用且有 disabled 祖先，提升到根级别时应该显示
      if (!isEnabled && hasDisabledAncestor) {
      }

      if (!isTerminal && group.children && group.children.length > 0) {
        const containers = []
        
        for (const childId of group.children) {
          // childId 可能是字符串 ID 或分组对象
          const child = typeof childId === 'string' ? this.groups.get(childId) : childId
          if (!child) {
            continue
          }
          
          const childIsTerminal = isTerminalGroup(child, this.options.chartType)
          const hasCode = child.elementRef?.code || child.elementCode
          
          if (!childIsTerminal && hasCode) {
            // 传递当前分组的 disabled 路径给子分组
            const childConfig = convertGroup(child, currentDisabledPath, depth + 1)
            if (childConfig) {
              containers.push(childConfig)
            } else {
            }
          } else {
          }
        }

        if (containers.length > 0) {
          legacyGroup.containers = containers
        }
        
        // 不再设置 legacyGroup.children，因为 containers 已经包含了嵌套结构
        // legacyGroup.children 会导致 hasGroupContent 和 generateGroupCode 重复处理
      }

      if (group.containers && group.containers.length > 0) {
        if (!isEnabled) {
        } else if (this.options.chartType === 'serviceModule' && group.type === 'SUB_DOMAIN') {
        } else {
          if (effectiveDisabledPath.length > 0) {
            group.containers.forEach(container => {
              const containerDisplayTitle = `${container.name || container.title}（${effectiveDisabledPath.join(' / ')}）`
              titleMap[container.id] = containerDisplayTitle
              if (container.elementCode) {
                titleMap[container.elementCode] = containerDisplayTitle
              }
              if (container.name) {
                titleMap[container.name] = containerDisplayTitle
              }
            })
          }
          
          if (!legacyGroup.containers) {
            legacyGroup.containers = []
          }
          legacyGroup.containers.push(...group.containers)
        }
      }

      return legacyGroup
    }

    // 直接从 rootIds 开始构建，而不是从 flattened
    for (const rootId of this.rootIds) {
      const group = this.groups.get(rootId)
      if (group) {
        const config = convertGroup(group)
        if (config) {
          groups.push(config)
        } else {
          // 如果分组被禁用，将它的子分组和 containers 提升到根级别
          
          // 首先提升 children（子分组）
          if (group.children && group.children.length > 0) {
            for (const childId of group.children) {
              const child = this.groups.get(childId)
              if (child) {
                const childConfig = convertGroup(child, [group.title])
                if (childConfig) {
                  groups.push(childConfig)
                } else {
                }
              } else {
              }
            }
          }
          
          // 其次提升 containers（终端节点）- 注意：SM图中Domain没有containers（在SubDomain上），这段对SM图无效
          if (group.containers && group.containers.length > 0) {
            for (const container of group.containers) {
              const containerLegacyGroup = {
                id: container.id,
                type: container.type,
                elementCode: container.elementRef?.code || container.elementCode,
                name: container.title || container.name,
                title: container.title || container.name,
                fullTitle: container.title || container.name,
                enabled: true,
                style: container.layout?.style || {}
              }
              groups.push(containerLegacyGroup)
            }
          }
        }
      }
    }
    
    // 构建 titleMap（从所有分组中）
    flattened.forEach(g => {
      if (g._disabledAncestorPath?.length > 0) {
        const displayTitle = `${g.title}（${g._disabledAncestorPath.join(' / ')}）`
        titleMap[g.id] = displayTitle
        if (g.elementRef?.code) {
          titleMap[g.elementRef.code] = displayTitle
        }
      }
    })

    const config = {
      enabled: true,
      groups,
      titleMap
    }

    this._mermaidConfigCache = config
    return config
  }

  updateEnabled(groupId, enabled) {
    const group = this.groups.get(groupId)
    if (!group) {
      return
    }

    if (!group.layout) {
      group.layout = {}
    }
    group.layout.enabled = enabled

    this._flattenedCache = null
    this._mermaidConfigCache = null
  }

  updateLayout(groupId, layout) {
    const group = this.groups.get(groupId)
    if (!group) return

    group.layout = {
      ...group.layout,
      ...layout,
      style: {
        ...group.layout?.style,
        ...layout.style
      }
    }

    this._flattenedCache = null
    this._mermaidConfigCache = null
  }

  clearCache() {
    this._flattenedCache = null
    this._mermaidConfigCache = null
  }
}
