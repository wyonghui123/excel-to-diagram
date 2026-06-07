/**
 * useWorkspaceFilter - 工作区过滤数据流管理
 *
 * 统一管理:
 * 1. 版本上下文 (useVersionContext)
 * 2. 层级钻取状态 (useHierarchyList)
 * 3. 过滤条件合并
 *
 * @example
 * const filter = useWorkspaceFilter({
 *   objectType: 'domain',
 *   metaObject: metaObjectRef
 * })
 *
 * // 获取合并后的过滤条件(用于 MetaListPage)
 * console.log(filter.combinedFilters.value)
 * // { version_id: 1, domain_id: 5 }
 *
 * // 获取当前对象类型(可能随钻取变化)
 * console.log(filter.currentObjectType.value)
 * // 'sub_domain'
 */
import { computed, inject, ref } from 'vue'
import { useVersionContext } from './useVersionContext'
import { useHierarchyList } from './useHierarchyList'

export function useWorkspaceFilter(options = {}) {
  const {
    objectType = 'domain',
    metaObject = null,
    autoLoad = true
  } = options

  // 版本上下文
  const versionContext = useVersionContext({
    autoLoadProducts: autoLoad,
    autoRestore: autoLoad
  })

  // 层级钻取状态
  const hierarchy = useHierarchyList({
    objectType,
    versionId: computed(() => versionContext.selectedVersionId.value)
  })

  // 当前对象类型(可能随钻取变化)
  const currentObjectType = computed(() => hierarchy.currentType.value)

  /**
   * 从 YAML hierarchies 配置获取父过滤字段映射
   * 例如: { domain: 'version_id', sub_domain: 'domain_id', ... }
   */
  const parentFilterFieldMap = computed(() => {
    const meta = metaObject?.value
    const levels = meta?.hierarchies?.[0]?.levels || []
    const map = {}

    levels.forEach((level, index) => {
      const objType = level.object_type
      if (index === 0) {
        // 根级别使用 root_filter 字段
        map[objType] = meta?.hierarchies?.[0]?.root_filter || 'version_id'
      } else {
        // 非根级别使用 children_field 转换
        // children_field: 'sub_domains' → filter_field: 'domain_id'
        map[objType] = level.children_field?.replace(/_ids?$/, '_id') || `${objType}_id`
      }
    })

    return map
  })

  /**
   * 当前对象类型的父过滤字段
   * 例如: currentType='sub_domain' → 'domain_id'
   */
  const currentParentFilterField = computed(() => {
    return parentFilterFieldMap.value[hierarchy.currentType.value]
  })

  /**
   * 合并后的过滤条件
   * 组合版本上下文 + 父对象过滤
   */
  const combinedFilters = computed(() => {
    const filters = {}

    // 1. 版本上下文过滤(顶层)
    if (versionContext.selectedVersionId.value) {
      filters.version_id = versionContext.selectedVersionId.value
    }

    // 2. 父对象过滤(中间层)
    if (hierarchy.parentId.value) {
      const filterField = currentParentFilterField.value
      if (filterField) {
        filters[filterField] = hierarchy.parentId.value
      }
    }

    return filters
  })

  /**
   * 获取特定对象类型的过滤条件
   * 用于钻入子对象时构建新的过滤
   */
  function getFiltersForType(targetType, parentId) {
    const filters = {}

    if (versionContext.selectedVersionId.value) {
      filters.version_id = versionContext.selectedVersionId.value
    }

    const filterField = parentFilterFieldMap.value[targetType]
    if (filterField && parentId) {
      filters[filterField] = parentId
    }

    return filters
  }

  /**
   * 获取子对象类型
   * 基于当前对象类型返回子类型
   */
  const childObjectType = computed(() => {
    const meta = metaObject?.value
    const levels = meta?.hierarchies?.[0]?.levels || []
    const currentIndex = levels.findIndex(l => l.object_type === hierarchy.currentType.value)

    if (currentIndex >= 0 && currentIndex < levels.length - 1) {
      return levels[currentIndex + 1].object_type
    }
    return null
  })

  /**
   * 获取当前层级是否有子对象
   */
  const hasChildren = computed(() => {
    return hierarchy.hasChildren.value
  })

  /**
   * 版本切换处理
   */
  function handleVersionChange(context) {
    versionContext.selectVersion(context)
    hierarchy.reset()
  }

  /**
   * 节点选择处理
   */
  function handleNodeSelect(node) {
    hierarchy.drillIn(node.type, node.id, node.name)
  }

  /**
   * 面包屑导航处理
   */
  function handleBreadcrumbNavigate(index) {
    hierarchy.goTo(index)
  }

  /**
   * 重置处理
   */
  function handleReset() {
    hierarchy.reset()
  }

  /**
   * 钻入到子对象
   */
  function drillIntoChild(childId, childName) {
    const targetType = childObjectType.value
    if (targetType) {
      hierarchy.drillIn(targetType, childId, childName)
    }
  }

  return {
    // 版本上下文
    versionContext,
    contextFilters: versionContext.contextFilters,
    selectedVersionId: versionContext.selectedVersionId,
    selectedVersion: versionContext.selectedVersion,
    hasContext: versionContext.hasContext,

    // 层级钻取
    hierarchy,
    path: hierarchy.path,
    currentType: hierarchy.currentType,
    parentId: hierarchy.parentId,
    isDrilling: hierarchy.isDrilling,
    separator: hierarchy.separator,
    childObjectType,
    hasChildren,

    // 过滤字段映射
    parentFilterFieldMap,
    currentParentFilterField,

    // 合并后的过滤条件
    combinedFilters,

    // 当前对象类型
    currentObjectType,

    // 方法
    getFiltersForType,
    handleVersionChange,
    handleNodeSelect,
    handleBreadcrumbNavigate,
    handleReset,
    drillIntoChild,
    drillIn: hierarchy.drillIn,
    goTo: hierarchy.goTo,
    reset: hierarchy.reset
  }
}
