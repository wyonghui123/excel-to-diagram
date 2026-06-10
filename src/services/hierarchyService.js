/**
 * hierarchyService - 层级元数据查询 + 过滤构建 + API 调用
 *
 * FR-UI-010: 收敛层级相关纯函数和 API 调用，消除 useMultiObjectPage / useHierarchyTypes /
 * hierarchyFilterBuilder / boHierarchyService 中的重复逻辑。
 *
 * 三层职责:
 *   1. 纯函数 — 层级元数据查询（getLabel / getParentType / getFKField / isHierarchyType 等）
 *   2. 纯函数 — 过滤参数构建（buildHierarchyFilterParams / buildRelationshipFilterParams 等）
 *   3. API    — 层级相关 HTTP 调用（fetchHierarchyConfig / getHierarchyTree / getObjectPath）
 *
 * @module services/hierarchyService
 */

import { apiV1, apiV2 } from '@/utils/httpClient'

// ============================================================================
// 1. 纯函数 — 层级元数据查询
// ============================================================================

/**
 * 非层级类型的标签回退
 * @private
 */
const NON_HIERARCHY_LABELS = { relationship: '关联关系' }

/**
 * 非层级类型的图标回退
 * @private
 */
const NON_HIERARCHY_ICONS = { relationship: 'Connection' }

/**
 * 获取对象类型的显示标签
 * @param {Array} levels - 层级配置数组（来自 useHierarchyTypes.levels）
 * @param {string} type - 对象类型
 * @returns {string}
 */
export function getLabel(levels, type) {
  const level = levels.find(l => (l.object_type || l.object) === type)
  return level?.label || level?.display_name || NON_HIERARCHY_LABELS[type] || type
}

/**
 * 获取对象类型的图标
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 对象类型
 * @returns {string}
 */
export function getIcon(levels, type) {
  const level = levels.find(l => (l.object_type || l.object) === type)
  return level?.icon || NON_HIERARCHY_ICONS[type] || 'Document'
}

/**
 * 获取子对象类型
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 当前对象类型
 * @returns {string|null}
 */
export function getChildType(levels, type) {
  const idx = levels.findIndex(l => (l.object_type || l.object) === type)
  if (idx < 0 || idx >= levels.length - 1) return null
  return levels[idx + 1]?.object_type || levels[idx + 1]?.object || null
}

/**
 * 获取父对象类型
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 当前对象类型
 * @returns {string|null}
 */
export function getParentType(levels, type) {
  const idx = levels.findIndex(l => (l.object_type || l.object) === type)
  if (idx <= 0) return null
  return levels[idx - 1]?.object_type || levels[idx - 1]?.object || null
}

/**
 * 获取层级索引
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 对象类型
 * @returns {number} 索引（0-based），未找到返回 -1
 */
export function getLevelIndex(levels, type) {
  return levels.findIndex(l => (l.object_type || l.object) === type)
}

/**
 * 推导 FK 字段名（合并原 getFKField + hierarchyFilterBuilder.getFilterParam）
 *
 * 约定: FK = parentType + '_id'
 * 例: business_object → service_module → FK = 'service_module_id'
 *
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 当前对象类型
 * @returns {string|null} FK 字段名，无父级时返回 null
 */
export function getFKField(levels, type) {
  const parent = getParentType(levels, type)
  if (!parent) return null
  return `${parent}_id`
}

/**
 * 判断是否为层级对象类型
 *
 * 层级类型 = domain 及以下（index >= 2）
 * product/version 由 versionContext 管理，不属于层级树
 *
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 对象类型
 * @returns {boolean}
 */
export function isHierarchyType(levels, type) {
  const idx = getLevelIndex(levels, type)
  return idx >= 2
}

/**
 * 判断是否有子级
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 对象类型
 * @returns {boolean}
 */
export function hasChildren(levels, type) {
  const level = levels.find(l => (l.object_type || l.object) === type)
  return !!level?.children_field
}

/**
 * 获取两个类型之间的所有中间类型
 * @param {Array} levels - 层级配置数组
 * @param {string} fromType - 起始类型
 * @param {string} toType - 结束类型
 * @returns {string[]}
 */
export function getTypesBetween(levels, fromType, toType) {
  const fromIdx = getLevelIndex(levels, fromType)
  const toIdx = getLevelIndex(levels, toType)
  if (fromIdx < 0 || toIdx < 0 || fromIdx >= toIdx) return []
  return levels.slice(fromIdx + 1, toIdx + 1).map(l => l.object_type || l.object)
}

/**
 * 获取层级深度（0-based）
 * @param {Array} levels - 层级配置数组
 * @param {string} type - 对象类型
 * @returns {number}
 */
export function getHierarchyDepth(levels, type) {
  return getLevelIndex(levels, type)
}

/**
 * 查找层级配置
 * @param {Array} levels - 层级配置数组
 * @param {string} objectType - 对象类型
 * @returns {Object|undefined}
 */
export function findLevel(levels, objectType) {
  return levels.find(l => (l.object_type || l.object) === objectType)
}

/**
 * 获取 kind（entity / association / null）
 * @param {Array} levels - 层级配置数组
 * @param {string} objectType - 对象类型
 * @returns {string|null}
 */
export function getKind(levels, objectType) {
  return findLevel(levels, objectType)?.kind || null
}

/**
 * 判断是否为实体类型
 * @param {Array} levels - 层级配置数组
 * @param {string} objectType - 对象类型
 * @returns {boolean}
 */
export function isEntity(levels, objectType) {
  return getKind(levels, objectType) === 'entity'
}

/**
 * 判断是否为关联类型
 * @param {Array} levels - 层级配置数组
 * @param {string} objectType - 对象类型
 * @returns {boolean}
 */
export function isAssociation(levels, objectType) {
  return getKind(levels, objectType) === 'association'
}

/**
 * 获取过滤映射配置
 * @param {Array} levels - 层级配置数组
 * @param {string} objectType - 对象类型
 * @returns {Array}
 */
export function getFilterMappings(levels, objectType) {
  return findLevel(levels, objectType)?.filter_mappings || []
}

// ============================================================================
// 2. 纯函数 — 过滤参数构建
// ============================================================================

/**
 * 构建层级过滤参数
 *
 * 过滤优先级:
 *   1. typeScope.selected → id__in（直接选中）
 *   2. typeScope.effective → id__in（树计算的有效范围）
 *   3. parentScope → {parentType}_id__in（父级 FK 回退）
 *
 * @param {Object} options
 * @param {Array} options.levels - 层级配置数组
 * @param {Object} options.scopeIds - 作用域 ID 映射
 * @param {string} options.objectType - 当前对象类型
 * @returns {Object} 过滤参数对象
 */
export function buildHierarchyFilterParams({ levels, scopeIds, objectType }) {
  const filters = {}
  const typeScope = scopeIds[objectType]
  if (!typeScope) return filters

  // 直接选区 / 有效选区
  if (typeScope.selected.length > 0) {
    filters.id__in = typeScope.selected.join(',')
  } else if (typeScope.effective.length > 0) {
    filters.id__in = typeScope.effective.join(',')
  }

  // 父级 FK 回退
  const parentType = getParentType(levels, objectType)
  if (parentType && scopeIds[parentType]) {
    const parentScope = scopeIds[parentType]
    const parentIds = parentScope.selected.length > 0
      ? parentScope.selected
      : parentScope.effective.length > 0
        ? parentScope.effective
        : []
    if (parentIds.length > 0) {
      const fkField = getFKField(levels, objectType)
      if (fkField) {
        filters[`${fkField}__in`] = parentIds.join(',')
      }
    }
  }

  return filters
}

/**
 * 构建关系过滤参数（回退逻辑，当 hierarchyTypes 不提供 filter_mappings 时使用）
 *
 * [FIX v3.18] 优先使用 relationIds（精确 ID 过滤），避免与 relation_code__in 产生
 * AND 语义冲突导致跨域记录（id=29, relation_code=''）被错误排除。
 * 此函数在 'relationship' 不在 levels 中（isAssociation=false）时被 _buildRelationshipFilters 调用。
 *
 * @param {Object} relationExtra - scopeIds.relationExtra
 * @returns {Object} 过滤参数对象
 */
export function buildRelationshipFilterParams(relationExtra) {
  const filters = {}

  // 优先使用 relationIds（精确 ID 过滤）
  if (relationExtra.relationIds?.length > 0) {
    filters.id__in = relationExtra.relationIds.join(',')
    return filters
  }

  if (relationExtra.relationCodes.length > 0) {
    filters.relation_code__in = relationExtra.relationCodes.join(',')
  }
  if (relationExtra.categoryTypes.length > 0) {
    filters.category_types__in = relationExtra.categoryTypes.join(',')
  }
  if (relationExtra.filterRelationCodes.length > 0) {
    const existing = filters.relation_code__in ? filters.relation_code__in.split(',') : []
    const combined = existing.length > 0
      ? existing.filter(r => relationExtra.filterRelationCodes.includes(r))
      : relationExtra.filterRelationCodes
    if (combined.length > 0) {
      filters.relation_code__in = combined.join(',')
    } else {
      delete filters.relation_code__in
    }
  }

  return filters
}

/**
 * 构建关联过滤参数（association 专用，元数据驱动）
 *
 * @param {Object} options
 * @param {Array} options.levels - 层级配置数组
 * @param {Object} options.scopeIds - 作用域 ID 映射
 * @param {Object} options.relationExtra - scopeIds.relationExtra
 * @returns {Object} 过滤参数对象
 */
export function buildAssociationFilterParams({ levels, scopeIds, relationExtra }) {
  const filters = {}
  const mappings = getFilterMappings(levels, 'relationship')

  // 优先使用 relationIds（精确 ID 过滤）
  if (relationExtra.relationIds?.length > 0) {
    filters.id__in = relationExtra.relationIds.join(',')
  } else if (mappings.length === 0) {
    // 无 filter_mappings 时回退到关系过滤
    return buildRelationshipFilterParams(relationExtra)
  } else {
    // 按 priority 排序后处理 selected/effective 触发器
    const sorted = [...mappings].sort((a, b) => (a.priority || 99) - (b.priority || 99))
    for (const mapping of sorted) {
      if (mapping.trigger === 'selected' || mapping.trigger === 'effective') {
        let key
        if (mapping.filter_field === 'relation_code') {
          key = 'relationCodes'
        } else if (mapping.filter_field === 'category_types') {
          key = 'categoryTypes'
        }
        if (key && relationExtra[key]?.length > 0) {
          filters[`${mapping.filter_field}__in`] = relationExtra[key].join(',')
        }
      }
    }
  }

  // source_bo_id / target_bo_id 过滤
  const sourceMapping = mappings.find(m => m.filter_field === 'source_bo_id')
  const targetMapping = mappings.find(m => m.filter_field === 'target_bo_id')

  if (sourceMapping?.trigger === 'entity_scope') {
    const sourceEntity = findLevel(levels, 'relationship')?.source_entity
    if (sourceEntity && scopeIds[sourceEntity]) {
      const scope = scopeIds[sourceEntity]
      const ids = scope.selected.length > 0 ? scope.selected : scope.effective
      if (ids.length > 0) {
        filters.source_bo_id__in = ids.join(',')
      }
    }
  }
  if (targetMapping?.trigger === 'entity_scope') {
    const targetEntity = findLevel(levels, 'relationship')?.target_entity
    if (targetEntity && scopeIds[targetEntity]) {
      const scope = scopeIds[targetEntity]
      const ids = scope.selected.length > 0 ? scope.selected : scope.effective
      if (ids.length > 0) {
        filters.target_bo_id__in = ids.join(',')
      }
    }
  }

  return filters
}

// ============================================================================
// 3. API 函数 — 层级相关 HTTP 调用
// ============================================================================

let _cachedConfig = null

/**
 * 获取层级配置（替代 hierarchyFilterBuilder.fetchHierarchyConfig）
 *
 * @param {boolean} [forceRefresh=false] - 强制刷新缓存
 * @returns {Promise<Object>} 层级配置
 */
export async function fetchHierarchyConfig(forceRefresh = false) {
  if (_cachedConfig && !forceRefresh) {
    return _cachedConfig
  }

  try {
    const result = await apiV1.get('/meta/hierarchies/config')
    if (result.success) {
      _cachedConfig = result.data
      return _cachedConfig
    }
  } catch (e) {
    console.warn('[hierarchyService] Failed to fetch hierarchy config, using fallback')
  }

  return getFallbackConfig()
}

/**
 * 获取回退层级配置
 * @returns {Object}
 */
export function getFallbackConfig() {
  return {
    dimensions: ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object'],
    hierarchy_levels: {
      product:         { level: 0, object: 'product',         parent_object: null,             filter_param: null,                ui: { icon: 'inventory_2', color: '#9C27B0' } },
      version:         { level: 1, object: 'version',         parent_object: 'product',        filter_param: 'product_id',        ui: { icon: 'tag',         color: '#FF9800' } },
      domain:          { level: 2, object: 'domain',          parent_object: 'version',        filter_param: 'version_id',        ui: { icon: 'business',    color: '#4CAF50' } },
      sub_domain:      { level: 3, object: 'sub_domain',      parent_object: 'domain',         filter_param: 'domain_id',         ui: { icon: 'account_tree',color: '#2196F3' } },
      service_module:  { level: 4, object: 'service_module',  parent_object: 'sub_domain',     filter_param: 'sub_domain_id',     ui: { icon: 'widgets',     color: '#FF9800' } },
      business_object: { level: 5, object: 'business_object', parent_object: 'service_module', filter_param: 'service_module_id', ui: { icon: 'description', color: '#9C27B0' } }
    }
  }
}

/**
 * 获取层级树（替代 BOHierarchyService.getHierarchyTree）
 *
 * @param {string} rootType - 根对象类型
 * @param {Object} [params={}] - 查询参数
 * @param {number} [params.version_id] - 版本 ID
 * @param {boolean} [params.include_counts] - 是否包含计数
 * @param {number} [params.max_depth] - 最大深度
 * @returns {Promise<Object>}
 */
export async function getHierarchyTree(rootType, params = {}) {
  const queryParams = new URLSearchParams()
  if (params.version_id) queryParams.set('version_id', String(params.version_id))
  if (params.include_counts !== undefined) queryParams.set('include_counts', String(params.include_counts))
  if (params.max_depth !== undefined) queryParams.set('max_depth', String(params.max_depth))

  const queryStr = queryParams.toString()
  const path = `/meta/hierarchy/tree${queryStr ? '?' + queryStr : ''}`

  return apiV2.get(path)
}

/**
 * 获取子对象数量（替代 BOHierarchyService.getChildCount）
 *
 * @param {string} objectType - 对象类型
 * @param {number|string} id - 对象 ID
 * @param {Object} [params={}] - 查询参数
 * @param {string} [params.child_type] - 子对象类型
 * @returns {Promise<Object>}
 */
export async function getChildCount(objectType, id, params = {}) {
  const queryParams = new URLSearchParams()
  if (params.child_type) queryParams.set('child_type', params.child_type)

  const queryStr = queryParams.toString()
  const path = `/bo/${objectType}/${id}/child-count${queryStr ? '?' + queryStr : ''}`

  return apiV2.get(path)
}

/**
 * 获取对象路径（替代 BOHierarchyService.getObjectPath）
 *
 * @param {string} objectType - 对象类型
 * @param {number|string} id - 对象 ID
 * @returns {Promise<Object>}
 */
export async function getObjectPath(objectType, id) {
  return apiV2.get(`/meta/hierarchy/path/${objectType}/${id}`)
}

// ============================================================================
// 4. 树遍历工具函数（从 hierarchyFilterBuilder 提取）
// ============================================================================

/**
 * 收集节点的所有后代 ID
 * @param {Object} node - 树节点
 * @returns {Array<number|string>}
 */
export function getDescendantIds(node) {
  const ids = []
  if (node.children) {
    for (const child of node.children) {
      ids.push(child.id)
      ids.push(...getDescendantIds(child))
    }
  }
  return ids
}

/**
 * 按类型收集选中 ID（含后代）
 *
 * @param {Array} nodes - 树节点列表
 * @param {Set} checkedSet - 选中的节点 ID 集合
 * @param {string} targetType - 目标节点类型
 * @returns {Array}
 */
export function collectIdsByTypeWithDescendants(nodes, checkedSet, targetType) {
  const ids = []

  function traverse(nodeList, hasCheckedAncestor) {
    for (const node of nodeList) {
      const isCurrentChecked = checkedSet.has(node.id)
      const shouldInclude = hasCheckedAncestor || isCurrentChecked

      if (node.type === targetType && shouldInclude) {
        ids.push(node.objectId || node.id)
      }

      if (node.children) {
        traverse(node.children, shouldInclude)
      }
    }
  }

  traverse(nodes, false)
  return [...new Set(ids)]
}

/**
 * 收集祖先 ID（元数据驱动，替代硬编码 dimensionToParentType）
 *
 * @param {Array} levels - 层级配置数组
 * @param {string} dimension - 当前维度
 * @param {Array<string>} checkedIds - 选中的节点 ID 列表
 * @param {Array} treeData - 树数据
 * @returns {Array<number>}
 */
export function collectAncestorIds(levels, dimension, checkedIds, treeData) {
  const checkedSet = new Set(checkedIds)

  // 元数据驱动推导父类型，替代硬编码映射
  const parentType = getParentType(levels, dimension)
  if (!parentType) return []

  const ids = []

  function traverse(nodes, parentInfo = {}) {
    for (const node of nodes) {
      // 动态构建父信息链
      const nodeInfo = {}
      for (const level of levels) {
        const levelType = level.object_type || level.object
        nodeInfo[levelType] = node.type === levelType ? node : parentInfo[levelType]
      }

      if (checkedSet.has(node.id)) {
        const targetNode = nodeInfo[parentType]
        if (targetNode) {
          ids.push(targetNode.objectId || targetNode.id)
        }
      }

      if (node.children) {
        traverse(node.children, nodeInfo)
      }
    }
  }

  traverse(treeData)
  return [...new Set(ids)]
}
