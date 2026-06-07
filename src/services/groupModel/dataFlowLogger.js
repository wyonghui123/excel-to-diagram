/**
 * 数据流日志工具
 * 用于追踪分组控制的数据流，支持按模块开关日志
 */

const LOG_CONFIG = {
  GroupModel: false,
  DiagramData: false,
  BusinessObjectSyntax: false,
  GroupLayout: false
}

const COLORS = {
  GroupModel: '#4CAF50',
  DiagramData: '#2196F3',
  BusinessObjectSyntax: '#FF9800',
  GroupLayout: '#9C27B0'
}

function formatGroups(groups) {
  if (!groups || !Array.isArray(groups)) return '[]'
  return groups.map(g => ({
    title: g.title,
    enabled: g.enabled,
    containers: g.containers?.length || 0,
    children: g.children?.length || 0
  }))
}

function formatGroup(group) {
  if (!group) return 'null'
  return {
    id: group.id,
    title: group.title,
    enabled: group.enabled,
    _disabledAncestorPath: group._disabledAncestorPath
  }
}

export const DataFlowLogger = {
  GroupModel: {
    log(action, data) {
      if (!LOG_CONFIG.GroupModel) return
      const color = COLORS.GroupModel
      console.log(`%c[GroupModel] ${action}`, `color: ${color}; font-weight: bold`, data)
    },

    fromUserConfig(userConfig, groupCount) {
      this.log('fromUserConfig', {
        userGroups: userConfig?.groups?.length || 0,
        architectureGroups: groupCount
      })
    },

    mergeUserGroup(groupId, title, enabled) {
      this.log('mergeUserGroup', { groupId, title, enabled })
    },

    getFlattenedGroups(groups) {
      this.log('getFlattenedGroups', {
        count: groups.length,
        groups: formatGroups(groups)
      })
    },

    toMermaidConfig(config) {
      this.log('toMermaidConfig', {
        enabled: config.enabled,
        groupsCount: config.groups.length,
        groups: formatGroups(config.groups)
      })
    }
  },

  DiagramData: {
    log(action, data) {
      if (!LOG_CONFIG.DiagramData) return
      const color = COLORS.DiagramData
      console.log(`%c[DiagramData] ${action}`, `color: ${color}; font-weight: bold`, data)
    },

    generateDiagram(useNewModel, layoutConfig) {
      this.log('generateDiagram', {
        useNewModel,
        groupsCount: layoutConfig?.groups?.length || 0
      })
    },

    buildDiagramData(layoutConfig) {
      this.log('buildDiagramData', {
        groupsCount: layoutConfig?.groups?.length || 0
      })
    }
  },

  BusinessObjectSyntax: {
    log(action, data) {
      if (!LOG_CONFIG.BusinessObjectSyntax) return
      const color = COLORS.BusinessObjectSyntax
      console.log(`%c[BusinessObjectSyntax] ${action}`, `color: ${color}; font-weight: bold`, data)
    },

    receivedConfig(config) {
      this.log('receivedConfig', {
        enabled: config?.enabled,
        groupsCount: config?.groups?.length || 0,
        groups: formatGroups(config?.groups)
      })
    },

    buildVirtualContainers(inputGroups, outputGroups) {
      this.log('buildVirtualContainers', {
        inputCount: inputGroups.length,
        outputCount: outputGroups.length,
        input: formatGroups(inputGroups),
        output: formatGroups(outputGroups)
      })
    },

    routeLayout(groups, containersCount) {
      this.log('routeLayout', {
        groupsCount: groups.length,
        containersCount,
        groups: formatGroups(groups)
      })
    }
  },

  GroupLayout: {
    log(action, data) {
      if (!LOG_CONFIG.GroupLayout) return
      const color = COLORS.GroupLayout
      console.log(`%c[GroupLayout] ${action}`, `color: ${color}; font-weight: bold`, data)
    },

    generateGroupedLayout(groups, containersCount) {
      this.log('generateGroupedLayout', {
        groupsCount: groups.length,
        containersCount,
        groups: formatGroups(groups)
      })
    },

    generateGroupCode(group, depth) {
      this.log('generateGroupCode', {
        title: group.title,
        enabled: group.enabled,
        depth,
        containers: group.containers?.length || 0,
        children: group.children?.length || 0
      })
    }
  },

  enable(module) {
    if (module && LOG_CONFIG.hasOwnProperty(module)) {
      LOG_CONFIG[module] = true
    } else if (!module) {
      Object.keys(LOG_CONFIG).forEach(k => LOG_CONFIG[k] = true)
    }
  },

  disable(module) {
    if (module && LOG_CONFIG.hasOwnProperty(module)) {
      LOG_CONFIG[module] = false
    } else if (!module) {
      Object.keys(LOG_CONFIG).forEach(k => LOG_CONFIG[k] = false)
    }
  },

  status() {
    console.log('[DataFlowLogger] Status:', LOG_CONFIG)
  }
}

if (typeof window !== 'undefined') {
  window.DataFlowLogger = DataFlowLogger
}
