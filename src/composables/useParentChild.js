/**
 * useParentChild - 父子关系 Composable
 * 
 * 封装父子关系的通用逻辑：
 * - 父对象详情加载
 * - 子对象列表管理（带上下文过滤）
 * - 子对象 CRUD 操作（自动注入 parent_id）
 * - 面包屑导航生成
 * - 基于 Association 的父子关系发现
 * 
 * 设计原则：
 * - 单一事实原则：通过 YAML 配置 + Association 定义驱动
 * - 自动注入 parent_id 到子对象的 CRUD 操作
 * - 支持多层级父子关系（祖父-父-子）
 */

import { ref, computed, watch, isRef } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import boService from '@/services/boService'
import metaService from '@/services/metaService'

export function useParentChild(parentObjectType, childObjectType, options = {}) {
  const {
    parentId = null,
    autoLoadParent = true,
    autoLoadChild = true,
    childListInDetail = true,
    associationName = null
  } = options

  const router = useRouter()
  const route = useRoute()

  const resolvedParentId = isRef(parentId) ? parentId : ref(parentId)

  const parentDetail = ref(null)
  const parentLoading = ref(false)
  const parentError = ref(null)
  const parentMeta = ref(null)

  const childList = ref([])
  const childLoading = ref(false)
  const childError = ref(null)
  const childPagination = ref({
    current: 1,
    pageSize: 10,
    total: 0
  })

  const childMeta = ref(null)

  const breadcrumbs = computed(() => {
    const crumbs = [
      {
        label: parentMeta.value?.label || parentObjectType,
        to: `/${parentObjectType}`
      }
    ]
    if (parentDetail.value) {
      crumbs.push({
        label: parentDetail.value.name || parentDetail.value.code || parentDetail.value.title || '详情'
      })
    }
    return crumbs
  })

  const childBreadcrumbs = computed(() => {
    const crumbs = [
      {
        label: parentMeta.value?.label || parentObjectType,
        to: `/${parentObjectType}`
      }
    ]
    if (parentDetail.value) {
      crumbs.push({
        label: parentDetail.value.name || parentDetail.value.code || parentDetail.value.title || '详情',
        to: `/${parentObjectType}/${resolvedParentId.value}`
      })
    }
    crumbs.push({
      label: childMeta.value?.label || childObjectType
    })
    return crumbs
  })

  const parentIdField = computed(() => `${parentObjectType}_id`)

  async function loadParentMeta() {
    try {
      const result = await metaService.getViewConfig(parentObjectType)
      if (result.success && result.data) {
        parentMeta.value = result.data
      }
    } catch (error) {
      console.error(`[useParentChild] 加载父对象元数据失败 (${parentObjectType}):`, error)
    }
  }

  async function loadChildMeta() {
    try {
      const result = await metaService.getViewConfig(childObjectType)
      if (result.success && result.data) {
        childMeta.value = result.data
      }
    } catch (error) {
      console.error(`[useParentChild] 加载子对象元数据失败 (${childObjectType}):`, error)
    }
  }

  async function loadParent() {
    if (!resolvedParentId.value) {
      parentDetail.value = null
      return
    }

    parentLoading.value = true
    parentError.value = null

    try {
      const result = await boService.read(parentObjectType, resolvedParentId.value)
      
      if (result.success) {
        parentDetail.value = result.data
      } else {
        parentError.value = result.message || '加载父对象详情失败'
      }
    } catch (error) {
      parentError.value = error.message || '加载父对象详情失败'
      console.error(`[useParentChild] 加载父对象详情失败 (${parentObjectType}/${resolvedParentId.value}):`, error)
    } finally {
      parentLoading.value = false
    }
  }

  async function loadChildList(extraParams = {}) {
    if (!resolvedParentId.value) {
      childList.value = []
      childPagination.value.total = 0
      return
    }

    childLoading.value = true
    childError.value = null

    try {
      const params = {
        page: childPagination.value.current,
        page_size: childPagination.value.pageSize,
        [parentIdField.value]: resolvedParentId.value,
        ...extraParams
      }

      const result = await boService.query(childObjectType, params)

      if (result.success) {
        const rawData = result.data
        
        if (rawData && rawData.items && Array.isArray(rawData.items)) {
          childList.value = rawData.items
          childPagination.value.total = rawData.total || rawData.items.length
        } else if (Array.isArray(rawData)) {
          childList.value = rawData
          childPagination.value.total = rawData.length
        } else {
          childList.value = []
          childPagination.value.total = 0
        }
      } else {
        childError.value = result.message || '加载子对象列表失败'
      }
    } catch (error) {
      childError.value = error.message || '加载子对象列表失败'
      console.error(`[useParentChild] 加载子对象列表失败 (${childObjectType}):`, error)
    } finally {
      childLoading.value = false
    }
  }

  async function createChild(data) {
    if (!resolvedParentId.value) {
      console.error('[useParentChild] 无法创建子对象：缺少 parent_id')
      return { success: false, message: '缺少父对象ID' }
    }

    try {
      const result = await boService.create(childObjectType, {
        ...data,
        [parentIdField.value]: resolvedParentId.value
      })

      if (result.success) {
        await loadChildList()
      }

      return result
    } catch (error) {
      console.error(`[useParentChild] 创建子对象失败 (${childObjectType}):`, error)
      return { success: false, message: error.message || '创建失败' }
    }
  }

  async function updateChild(id, data) {
    try {
      const result = await boService.update(childObjectType, id, data)

      if (result.success) {
        await loadChildList()
      }

      return result
    } catch (error) {
      console.error(`[useParentChild] 更新子对象失败 (${childObjectType}/${id}):`, error)
      return { success: false, message: error.message || '更新失败' }
    }
  }

  async function deleteChild(id) {
    try {
      const result = await boService.delete(childObjectType, id)

      if (result.success) {
        await loadChildList()
      }

      return result
    } catch (error) {
      console.error(`[useParentChild] 删除子对象失败 (${childObjectType}/${id}):`, error)
      return { success: false, message: error.message || '删除失败' }
    }
  }

  async function executeChildAction(id, actionName, params = {}) {
    try {
      const result = await boService.executeAction(childObjectType, id, actionName, params)

      if (result.success) {
        await loadChildList()
      }

      return result
    } catch (error) {
      console.error(`[useParentChild] 执行子对象操作失败 (${childObjectType}/${id}/${actionName}):`, error)
      return { success: false, message: error.message || '操作失败' }
    }
  }

  async function setCurrentVersion(versionId) {
    return executeChildAction(versionId, 'set_current')
  }

  function navigateToParentList() {
    router.push(`/${parentObjectType}`)
  }

  function navigateToParentDetail() {
    if (resolvedParentId.value) {
      router.push(`/${parentObjectType}/${resolvedParentId.value}`)
    }
  }

  function navigateToChildDetail(childId) {
    if (resolvedParentId.value) {
      router.push(`/${parentObjectType}/${resolvedParentId.value}/${childObjectType}/${childId}`)
    }
  }

  function handleChildPageChange(page) {
    childPagination.value.current = page
    loadChildList()
  }

  function handleChildPageSizeChange(size) {
    childPagination.value.pageSize = size
    childPagination.value.current = 1
    loadChildList()
  }

  async function refreshChildList() {
    await loadChildList()
  }

  async function refreshParent() {
    await loadParent()
  }

  async function refresh() {
    await Promise.all([refreshParent(), refreshChildList()])
  }

  async function discoverParentAssociation() {
    try {
      const parentMetaResult = await metaService.getViewConfig(childObjectType)
      
      if (parentMetaResult.success && parentMetaResult.data) {
        const associations = parentMetaResult.data.associations || []
        
        const parentAssoc = associations.find(assoc => {
          if (associationName) {
            return assoc.name === associationName || assoc.association === associationName
          }
          return assoc.target === parentObjectType || assoc.type === 'parent'
        })

        if (parentAssoc) {
          return {
            field: parentAssoc.field || parentAssoc.foreignKey || `${parentObjectType}_id`,
            name: parentAssoc.name || associationName,
            type: parentAssoc.type
          }
        }
      }
    } catch (error) {
      console.error('[useParentChild] 发现父子关联失败:', error)
    }
    
    return {
      field: `${parentObjectType}_id`,
      name: associationName,
      type: 'foreign_key'
    }
  }

  async function init() {
    await Promise.all([
      loadParentMeta(),
      loadChildMeta()
    ])

    const assocInfo = await discoverParentAssociation()
    
    if (autoLoadParent && resolvedParentId.value) {
      await loadParent()
    }

    if (autoLoadChild && resolvedParentId.value) {
      await loadChildList()
    }

    return assocInfo
  }

  watch(resolvedParentId, async (newId) => {
    if (newId) {
      if (autoLoadParent) {
        await loadParent()
      }
      if (autoLoadChild) {
        await loadChildList()
      }
    } else {
      parentDetail.value = null
      childList.value = []
      childPagination.value.total = 0
    }
  })

  return {
    parentObjectType,
    childObjectType,
    parentId: resolvedParentId,
    parentIdField,

    parentDetail,
    parentLoading,
    parentError,
    parentMeta,

    childList,
    childLoading,
    childError,
    childPagination,
    childMeta,

    breadcrumbs,
    childBreadcrumbs,

    loadParent,
    loadChildList,
    createChild,
    updateChild,
    deleteChild,
    executeChildAction,
    setCurrentVersion,

    navigateToParentList,
    navigateToParentDetail,
    navigateToChildDetail,

    handleChildPageChange,
    handleChildPageSizeChange,

    refreshChildList,
    refreshParent,
    refresh,

    discoverParentAssociation,
    init
  }
}

export default useParentChild
