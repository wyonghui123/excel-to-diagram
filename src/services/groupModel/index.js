/**
 * GroupModel 模块入口
 * 
 * 提供新旧模型的兼容层，通过 feature flag 控制
 */

import { GroupModel } from './GroupModel.js'
import { MermaidGenerator } from './MermaidGenerator.js'
import { mergeUserLayoutConfig as legacyMergeUserLayoutConfig } from './configMerger.js'
import { flattenDisabledGroups as legacyFlattenDisabledGroups } from './groupFlattener.js'

// 重新导出架构处理器函数
export {
  buildGroupModelFromArchitecture,
  buildNodeIdMap,
  filterGroupModelByScope,
  extractTerminalGroups
} from './architectureProcessor.js'

// 重新导出类型定义
export {
  GroupType,
  createGroup,
  findGroupByElementCode,
  isTerminalGroup
} from './types.js'

// 重新导出图表类型配置
export {
  ChartType,
  ChartTypeConfig,
  getChartTypeConfig
} from './chartTypeConfig.js'

// Feature flag：是否使用新的 GroupModel
// 可以通过环境变量或运行时配置控制
export const USE_NEW_GROUP_MODEL = import.meta.env?.VITE_USE_NEW_GROUP_MODEL === 'true' || 
                                    window.__USE_NEW_GROUP_MODEL__ === true ||
                                    true // 默认启用新模型

/**
 * 创建分组模型（兼容层）
 * @param {Array} architectureGroups - 架构生成的分组
 * @param {Object} userConfig - 用户布局配置
 * @param {Object} options - 配置选项
 * @returns {GroupModel|Array}
 */
export function createGroupModel(architectureGroups, userConfig, options = {}) {
  if (USE_NEW_GROUP_MODEL) {
    console.log('[GroupModel] Using new GroupModel')
    return GroupModel.fromUserConfig(architectureGroups, userConfig)
  }
  
  console.log('[GroupModel] Using legacy group model')
  // 旧逻辑：返回合并后的数组
  return legacyMergeUserLayoutConfig(architectureGroups, userConfig)
}

/**
 * 获取扁平化的分组（兼容层）
 * @param {GroupModel|Array} modelOrGroups - GroupModel 实例或分组数组
 * @param {string} chartType - 图表类型
 * @returns {Array}
 */
export function getFlattenedGroups(modelOrGroups, chartType) {
  if (USE_NEW_GROUP_MODEL && modelOrGroups instanceof GroupModel) {
    return modelOrGroups.getFlattenedGroups()
  }
  
  // 旧逻辑
  return legacyFlattenDisabledGroups(modelOrGroups, chartType)
}

/**
 * 转换为 Mermaid 配置（兼容层）
 * @param {GroupModel|Array} modelOrGroups - GroupModel 实例或分组数组
 * @param {string} chartType - 图表类型
 * @returns {Object}
 */
export function toMermaidConfig(modelOrGroups, chartType) {
  if (USE_NEW_GROUP_MODEL && modelOrGroups instanceof GroupModel) {
    return modelOrGroups.toMermaidConfig()
  }
  
  // 旧逻辑不再支持
  console.warn('[toMermaidConfig] Legacy mode not supported, please use GroupModel')
  return { enabled: false, groups: [] }
}

/**
 * 获取显示标题（兼容层）
 * @param {GroupModel|Object} modelOrGroup - GroupModel 实例或分组对象
 * @param {string} groupId - 分组 ID（使用新模型时）
 * @returns {string}
 */
export function getDisplayTitle(modelOrGroup, groupId) {
  if (USE_NEW_GROUP_MODEL && modelOrGroup instanceof GroupModel) {
    return modelOrGroup.getDisplayTitle(groupId)
  }
  
  // 旧逻辑：直接返回标题
  return modelOrGroup.title
}

// 导出 GroupModel 类
export { GroupModel, MermaidGenerator }

// 导出旧函数（用于逐步迁移）
export { legacyMergeUserLayoutConfig, legacyFlattenDisabledGroups }

// 导出 mergeUserLayoutConfig（供 useDiagramData 使用）
export { mergeUserLayoutConfig } from './configMerger.js'

// 导出统一渲染模块
export { enrichGroupModel } from './enrichGroupModel.js'
export { ColorCalculator } from './ColorCalculator.js'
export { UnifiedRenderer } from './UnifiedRenderer.js'
