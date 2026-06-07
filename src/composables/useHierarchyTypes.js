/**
 * useHierarchyTypes - Hierarchy Types Metadata Management
 *
 * @description Manages hierarchy type configuration including labels, icons, level order, etc.
 *   纯查询逻辑已委托给 hierarchyService（FR-UI-010），本 composable 仅保留响应式封装。
 * @example
 * const types = useHierarchyTypes()
 * types.getLabel('domain')  // 'domain'
 * types.getChildType('domain')  // 'sub_domain'
 * types.getLevelIndex('sub_domain')  // 1
 */
import { ref, computed, inject } from 'vue'
import * as hierarchyService from '@/services/hierarchyService'

const NON_HIERARCHY_LABELS = {
  relationship: '关联关系'
}

const NON_HIERARCHY_ICONS = {
  relationship: 'Connection'
}

/**
 * 最小回退配置（仅结构性字段，不含 label/icon/children_field）
 *
 * 当 metaObject 未被注入时使用。所有 UI 增强信息（label、icon、children_field）
 * 由 YAML 单一事实源提供，不在此重复。
 */
const MINIMAL_FALLBACK_CONFIG = {
  levels: [
    { object_type: 'product', display_name: '产品', label: '产品', is_anchor: false, children_field: 'versions', kind: 'entity' },
    { object_type: 'version', display_name: '版本', label: '版本', is_anchor: false, children_field: 'domains', kind: 'entity' },
    { object_type: 'domain', display_name: '领域', label: '领域', is_anchor: true, children_field: 'sub_domains', kind: 'entity' },
    { object_type: 'sub_domain', display_name: '子领域', label: '子领域', is_anchor: false, children_field: 'service_modules', kind: 'entity' },
    { object_type: 'service_module', display_name: '服务模块', label: '服务模块', is_anchor: false, children_field: 'business_objects', kind: 'entity' },
    { object_type: 'business_object', display_name: '业务对象', label: '业务对象', is_anchor: false, kind: 'entity' }
  ],
  root_type: 'product',
  anchor_type: 'domain'
}

export function useHierarchyTypes(options = {}) {
  const {
    metaObjectKey = 'metaObject'
  } = options

  // inject 在非 setup 上下文中返回 undefined，需要安全回退
  const metaObject = inject(metaObjectKey, ref({ hierarchies: [] })) || ref({ hierarchies: [] })

  const config = computed(() => {
    if (metaObject.value?.hierarchies?.[0]?.levels) {
      const h = metaObject.value.hierarchies[0]
      return {
        levels: h.levels,
        root_type: h.root_type || MINIMAL_FALLBACK_CONFIG.root_type,
        anchor_type: h.anchor_type || MINIMAL_FALLBACK_CONFIG.anchor_type,
        context_levels: h.context_levels || [],
        filter_dependencies: h.filter_dependencies || []
      }
    }
    return {
      ...MINIMAL_FALLBACK_CONFIG,
      context_levels: [],
      filter_dependencies: []
    }
  })

  const levels = computed(() => {
    return (config.value.levels || []).map(level => ({
      ...level,
      object_type: level.object_type || level.object
    }))
  })

  const typeLabelMap = computed(() => {
    const map = {}
    levels.value.forEach(level => {
      map[level.object_type] = level.label || level.display_name || level.object_type
    })
    return map
  })

  const typeIconMap = computed(() => {
    const map = {}
    levels.value.forEach(level => {
      map[level.object_type] = level.icon || 'Document'
    })
    return map
  })

  const childFieldMap = computed(() => {
    const map = {}
    levels.value.forEach(level => {
      map[level.object_type] = level.children_field
    })
    return map
  })

  const typeIndexMap = computed(() => {
    const map = {}
    levels.value.forEach((level, index) => {
      map[level.object_type] = index
    })
    return map
  })

  const rootType = computed(() => config.value.root_type)

  const anchorType = computed(() => config.value.anchor_type)

  const anchorTypes = computed(() => {
    return levels.value
      .filter(l => l.is_anchor)
      .map(l => l.object_type)
  })

  const selectableTypes = computed(() => {
    return levels.value
      .filter(l => l.is_anchor || !l.children_field)
      .map(l => l.object_type)
  })

  function getLabel(type) {
    return hierarchyService.getLabel(levels.value, type)
  }

  function getIcon(type) {
    return hierarchyService.getIcon(levels.value, type)
  }

  function getChildField(type) {
    return childFieldMap.value[type]
  }

  function getChildType(type) {
    return hierarchyService.getChildType(levels.value, type)
  }

  function getParentType(type) {
    return hierarchyService.getParentType(levels.value, type)
  }

  function getLevelIndex(type) {
    return hierarchyService.getLevelIndex(levels.value, type)
  }

  function hasChildren(type) {
    return hierarchyService.hasChildren(levels.value, type)
  }

  function isRootType(type) {
    return type === rootType.value
  }

  function isAnchorType(type) {
    return anchorTypes.value.includes(type)
  }

  function isSelectableType(type) {
    return selectableTypes.value.includes(type)
  }

  function getTypesBetween(fromType, toType) {
    return hierarchyService.getTypesBetween(levels.value, fromType, toType)
  }

  function findLevel(objectType) {
    return hierarchyService.findLevel(levels.value, objectType)
  }

  function getKind(objectType) {
    return hierarchyService.getKind(levels.value, objectType)
  }

  function getRelationType(objectType) {
    const level = findLevel(objectType)
    return level?.relation_type || null
  }

  function getFilterMappings(objectType) {
    return hierarchyService.getFilterMappings(levels.value, objectType)
  }

  function getContextLevels() {
    return config.value.context_levels || []
  }

  function getFilterDependencies() {
    return config.value.filter_dependencies || []
  }

  function isEntity(objectType) {
    return hierarchyService.isEntity(levels.value, objectType)
  }

  function isAssociation(objectType) {
    return hierarchyService.isAssociation(levels.value, objectType)
  }

  return {
    levels,
    config,
    rootType,
    anchorType,
    anchorTypes,
    selectableTypes,
    typeLabelMap,
    typeIconMap,
    childFieldMap,
    typeIndexMap,
    getLabel,
    getIcon,
    getChildField,
    getChildType,
    getParentType,
    getLevelIndex,
    hasChildren,
    isRootType,
    isAnchorType,
    isSelectableType,
    getTypesBetween,
    findLevel,
    getKind,
    getRelationType,
    getFilterMappings,
    getContextLevels,
    getFilterDependencies,
    isEntity,
    isAssociation
  }
}
