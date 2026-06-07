import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { boService } from '@/services/boService'

const NAV_STATE_KEY = '_nav_source_state'

export function useAssociationNavigation() {
  const router = useRouter()
  const route = useRoute()

  const navigationSource = ref(null)

  function parseNavigationParams() {
    const sourceType = route.query._nav_source_type
    const sourceIds = route.query._nav_source_ids
    const assocName = route.query._nav_assoc_name
    const sourceNames = route.query._nav_source_names

    if (!sourceType || !sourceIds) {
      navigationSource.value = null
      return null
    }

    navigationSource.value = {
      sourceType,
      sourceIds: sourceIds.split(',').map(Number),
      associationName: assocName,
      sourceNames: sourceNames ? sourceNames.split(',') : []
    }

    return navigationSource.value
  }

  function _saveSourceState(objectType, selectedIds, filterValues, sortInfo, pagination, scrollPosition) {
    const state = {
      path: route.fullPath,
      query: { ...route.query },
      scrollPosition: scrollPosition || 0,
      selectedIds: Array.from(selectedIds),
      filters: { ...filterValues },
      sort: sortInfo ? { ...sortInfo } : null,
      pagination: {
        current: pagination?.current || 1,
        pageSize: pagination?.pageSize || 20
      },
      timestamp: Date.now()
    }
    sessionStorage.setItem(`${NAV_STATE_KEY}_${objectType}`, JSON.stringify(state))
  }

  function _restoreSourceState(objectType) {
    const key = `${NAV_STATE_KEY}_${objectType}`
    const stored = sessionStorage.getItem(key)
    if (!stored) return null
    try {
      return JSON.parse(stored)
    } catch {
      return null
    }
  }

  function _clearSourceState(objectType) {
    sessionStorage.removeItem(`${NAV_STATE_KEY}_${objectType}`)
  }

  async function navigateToAssociation(association, selectedIds, objectType, options = {}) {
    const ids = Array.from(selectedIds)
    const targetEntity = association.target_entity || association.target_type

    let sourceNames = []
    try {
      const result = await boService.query(objectType, {
        id__in: ids.join(','),
        page_size: 100
      })
      if (result.success && result.data?.items) {
        sourceNames = result.data.items.map(item =>
          item.name || item.display_name || item.code || `#${item.id}`
        )
      }
    } catch (e) {
      sourceNames = ids.map(id => `#${id}`)
    }

    if (options.saveState !== false) {
      _saveSourceState(
        objectType,
        selectedIds,
        options.filterValues || {},
        options.sortInfo || null,
        options.pagination || null,
        options.scrollPosition || 0
      )
    }

    const routePathMap = {
      'user': '/user-permission/users',
      'role': '/user-permission/roles',
      'permission': '/user-permission/permissions',
      'user_group': '/user-permission/groups',
      'enum_type': '/business-config/enums',
      'enum_value': '/business-config/enums',
    }

    const basePath = routePathMap[targetEntity] || `/${targetEntity.replace(/_/g, '-')}`

    const query = {
      _nav_source_type: objectType,
      _nav_source_ids: ids.join(','),
      _nav_source_names: sourceNames.join(','),
      _nav_assoc_name: association.name,
    }

    if (options.context === 'dialog') {
      query._nav_context = 'dialog'
    }

    router.push({ path: basePath, query })
  }

  function navigateBack() {
    if (!navigationSource.value) return

    const state = _restoreSourceState(navigationSource.value.sourceType)
    if (state) {
      router.push({ path: state.path, query: state.query })
      return true
    }

    const routePathMap = {
      'role': '/user-permission/roles',
      'user_group': '/user-permission/groups',
      'user': '/user-permission/users',
      'enum_type': '/business-config/enums',
    }
    const basePath = routePathMap[navigationSource.value.sourceType]
    if (basePath) {
      router.push(basePath)
      return true
    }

    router.back()
    return true
  }

  function isNavigationTarget() {
    return !!(route.query._nav_source_type && route.query._nav_source_ids)
  }

  function getNavigationFilterParam() {
    if (!navigationSource.value) return {}
    const { sourceType, sourceIds } = navigationSource.value
    return {
      [`${sourceType}_id__in`]: sourceIds.join(',')
    }
  }

  const routePathMap = {
    'user': '/user-permission/users',
    'role': '/user-permission/roles',
    'permission': '/user-permission/permissions',
    'user_group': '/user-permission/groups',
    'enum_type': '/business-config/enums',
    'enum_value': '/business-config/enums',
    'domain': '/data/domains',
    'sub_domain': '/data/subdomains',
    'service_module': '/data/service-modules',
    'business_object': '/data/business-objects',
    'product': '/product-version/products',
    'version': '/product-version/versions',
  }

  function getRoutePath(objectType) {
    return routePathMap[objectType] || `/${objectType.replace(/_/g, '-')}`
  }

  return {
    navigationSource,
    parseNavigationParams,
    navigateToAssociation,
    navigateBack,
    isNavigationTarget,
    getNavigationFilterParam,
    getRoutePath,
    saveSourceState: _saveSourceState,
    restoreSourceState: _restoreSourceState,
    clearSourceState: _clearSourceState,
  }
}
