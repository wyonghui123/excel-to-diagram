/**
 * useHierarchyList - 层级钻取状态管理
 *
 * @description 管理面包屑导航和钻取状态，是层级钻取的核心状态管理器
 * @example
 * const hierarchy = useHierarchyList({
 *   objectType: 'domain',
 *   versionId: computed(() => store.selectedVersionId)
 * })
 *
 * hierarchy.drillIn('sub_domain', 5, '总账')
 * hierarchy.goTo(0)
 * hierarchy.reset()
 */
import { ref, computed, watch, inject } from 'vue'
import { boService } from '@/services/boService'

export function useHierarchyList(options = {}) {
  const {
    objectType = 'domain',
    versionId = null,
    pathSeparator,
    onPathChange = null,
    metaObject: externalMetaObject = null
  } = options

  const metaObject = externalMetaObject || inject('metaObject', ref(null))

  const DEFAULT_HIERARCHY_CONFIG = {
    levels: [
      { object_type: 'domain', children_field: 'sub_domains' },
      { object_type: 'sub_domain', children_field: 'service_modules' },
      { object_type: 'service_module', children_field: 'business_objects' },
      { object_type: 'business_object', children_field: null }
    ],
    root_type: 'domain',
    root_filter: 'version_id',
    path_separator: '›'
  }

  const hierarchyConfig = computed(() => {
    return metaObject.value?.hierarchies?.[0] || DEFAULT_HIERARCHY_CONFIG
  })

  const levels = computed(() => hierarchyConfig.value.levels || [])

  const path = ref([])
  const currentType = ref(objectType)
  const parentId = ref(null)
  const isDrilling = ref(false)

  const separator = computed(() => {
    return pathSeparator || hierarchyConfig.value.path_separator || '›'
  })

  const currentLevelIndex = computed(() => {
    return levels.value.findIndex(l => l.object_type === currentType.value)
  })

  const hasChildren = computed(() => {
    const idx = currentLevelIndex.value
    return idx >= 0 && idx < levels.value.length - 1
  })

  const childType = computed(() => {
    const idx = currentLevelIndex.value
    if (idx < 0 || idx >= levels.value.length - 1) return null
    return levels.value[idx + 1].object_type
  })

  /**
   * 钻入到子对象
   * @param {string} targetType - 目标对象类型
   * @param {number} targetId - 目标对象 ID
   * @param {string} targetName - 目标对象名称
   */
  function drillIn(targetType, targetId, targetName) {
    isDrilling.value = true

    path.value.push({
      type: targetType,
      id: targetId,
      name: targetName
    })

    currentType.value = targetType
    parentId.value = targetId

    if (onPathChange) {
      onPathChange(path.value)
    }

    isDrilling.value = false
  }

  /**
   * 从面包屑回退到指定层级
   * @param {number} index - 目标层级索引
   */
  function drillOut(index) {
    if (index < 0 || index >= path.value.length - 1) return

    isDrilling.value = true

    path.value = path.value.slice(0, index + 1)

    const targetNode = path.value[path.value.length - 1]
    currentType.value = targetNode.type
    parentId.value = targetNode.id

    if (onPathChange) {
      onPathChange(path.value)
    }

    isDrilling.value = false
  }

  /**
   * 钻取到指定层级（与 drillOut 相同）
   * @param {number} index - 目标层级索引
   */
  function goTo(index) {
    drillOut(index)
  }

  /**
   * 重置钻取状态
   */
  function reset() {
    path.value = []
    currentType.value = hierarchyConfig.value.root_type || 'domain'
    parentId.value = null
    isDrilling.value = false

    if (onPathChange) {
      onPathChange(path.value)
    }
  }

  /**
   * 构建完整路径（向上查询父对象）
   * @param {string} targetType - 目标对象类型
   * @param {number} targetId - 目标对象 ID
   * @returns {Promise<Array>} 路径节点列表
   */
  async function buildPath(targetType, targetId) {
    const result = []
    const levelsArr = levels.value

    let currentLevelType = targetType
    let currentId = targetId

    while (currentLevelType) {
      const levelIndex = levelsArr.findIndex(l => l.object_type === currentLevelType)
      if (levelIndex <= 0) break

      const parentLevel = levelsArr[levelIndex - 1]
      const parentType = parentLevel.object_type

      try {
        const response = await boService.read(parentType, currentId)
        if (response.success && response.data) {
          result.unshift({
            type: parentType,
            id: response.data.id,
            name: response.data.name
          })
          currentId = response.data.id
        } else {
          break
        }
      } catch {
        break
      }

      currentLevelType = parentType
    }

    return result
  }

  /**
   * 获取路径字符串
   * @param {string} [sep] - 分隔符，默认使用 separator
   * @returns {string} 路径字符串
   */
  function getPathString(sep) {
    const sepStr = sep || ` ${separator.value} `
    return path.value
      .map(node => node.name)
      .join(sepStr)
  }

  if (versionId) {
    watch(versionId, () => {
      reset()
    })
  }

  return {
    path,
    currentType,
    parentId,
    isDrilling,
    separator,
    hasChildren,
    childType,
    drillIn,
    drillOut,
    goTo,
    reset,
    buildPath,
    getPathString
  }
}
