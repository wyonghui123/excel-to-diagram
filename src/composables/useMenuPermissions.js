import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { apiV1, apiV2 } from '@/utils/httpClient'
import { useMetaCache } from '@/composables/useMetaCache'

const menuPermissions = ref([])
const loading = ref(false)
const error = ref(null)
const _menusLoaded = ref(false)
const _serverLeafMenus = ref(null)
const _serverObjectTypeRouteMap = ref(null)

export function useMenuPermissions() {
  const authStore = useAuthStore()
  const menuCache = useMetaCache('menuCache')
  const accessibleMenus = computed(() => menuPermissions.value)

  const flatMenus = computed(() => {
    const menus = menuPermissions.value
    if (!menus || !menus.length) return []
    const result = []
    function flatten(items) {
      for (const item of items) {
        result.push(item)
        if (item.children && item.children.length) {
          flatten(item.children)
        }
      }
    }
    flatten(menus)
    return result
  })

  const leafMenus = computed(() => {
    // Prefer server-computed leaf_menus
    if (_serverLeafMenus.value) return _serverLeafMenus.value
    // Fallback: compute on frontend
    const hubParents = new Set()
    const parentMenus = new Set()
    for (const m of flatMenus.value) {
      if (m.page_type === 'multi_object_hub') {
        hubParents.add(m.menu_code)
      }
      if (m.children && m.children.length > 0) {
        parentMenus.add(m.menu_code)
      }
    }
    return flatMenus.value.filter(m => {
      if (!m.menu_code || m.menu_code === 'dashboard') return false
      if (!m.menu_path) return false
      if (parentMenus.has(m.menu_code)) return false
      if (m.parent_menu && hubParents.has(m.parent_menu)) return false
      return true
    })
  })

  const objectTypeRouteMap = computed(() => {
    // Prefer server-computed object_type_route_map
    if (_serverObjectTypeRouteMap.value) return _serverObjectTypeRouteMap.value
    // Fallback: compute on frontend
    const map = {}
    const menus = menuPermissions.value
    if (!menus || !menus.length) return map

    function traverse(nodes, parentPath) {
      for (const node of nodes) {
        if (node.primary_object_type) {
          map[node.primary_object_type] = node.menu_path || parentPath || `/${node.menu_code}`
        }
        if (node.children && node.children.length) {
          traverse(node.children, node.menu_path || parentPath || `/${node.menu_code}`)
        }
      }
    }
    traverse(menus, '')
    return map
  })

  const _loadFromApi = async () => {
    const result = await apiV1.get('/menu-permission/visible')
    if (!result.success) throw new Error(result.message || `HTTP error`)
    const data = result.data ?? {}
    // Store server-computed fields if available
    if (data.leaf_menus) {
      _serverLeafMenus.value = data.leaf_menus
    }
    if (data.object_type_route_map) {
      _serverObjectTypeRouteMap.value = data.object_type_route_map
    }
    const menus = data.menus ?? []
    return menus
  }

  const _fetchSchemaVersion = async () => {
    try {
      const result = await apiV2.get('/meta/schema-version')
      if (result.success) {
        return result.data?.schema_version || null
      }
    } catch {}
    return null
  }

  const loadMenuPermissions = async () => {
    if (_menusLoaded.value && menuPermissions.value.length > 0) return

    loading.value = true
    error.value = null

    // 等待 session ready（修复竞态条件）
    if (!authStore.sessionReady) {
      await new Promise(resolve => {
        const check = () => {
          if (authStore.sessionReady) resolve()
          else setTimeout(check, 50)
        }
        check()
        setTimeout(resolve, 5000) // 5秒超时
      })
    }

    try {
      if (!authStore.isLoggedIn) {
        const cached = menuCache.getCache()
        const cachedData = cached?.data
        menuPermissions.value = (cachedData && !_isHomeOnlyFallback(cachedData)) ? cachedData : _homeOnlyFallback()
        loading.value = false
        return
      }
    } catch {
    }

    try {
      const schemaVersion = await _fetchSchemaVersion()
      const cached = menuCache.getCache(schemaVersion)
      if (cached?.data && cached.data.length > 0 && !_isHomeOnlyFallback(cached.data)) {
        menuPermissions.value = cached.data
        _menusLoaded.value = true
        loading.value = false
        return
      }
      if (_isHomeOnlyFallback(cached?.data)) {
        menuCache.clearCache()
      }

      const menus = await _loadFromApi()
      menuCache.setCache(menus, schemaVersion)
      menuPermissions.value = menus
      _menusLoaded.value = true
    } catch (err) {
      console.error('[MenuPermissions] API failed, trying cache:', err.message)
      const cached = menuCache.getCache()
      if (cached?.data && !_isHomeOnlyFallback(cached.data)) {
        menuPermissions.value = cached.data
      } else {
        menuPermissions.value = _homeOnlyFallback()
      }
      error.value = err.message
    }
    loading.value = false
  }

  function _isHomeOnlyFallback(menus) {
    return menus && menus.length === 1 && menus[0]?.menu_code === 'home'
  }

  const _homeOnlyFallback = () => [{
    menu_code: 'home',
    menu_name: '\u9996\u9875',
    menu_path: '/',
    icon: 'Home',
    color: 'warm-orange',
    description: '',
    page_type: 'custom_page',
    sort_order: 0,
    children: []
  }]

  const checkMenuVisibility = async (menuCode) => {
    try {
      const result = await apiV1.get(`/menu-permission/menus/${menuCode}`)
      if (result.success) {
        return !!(result.data?.visible)
      }
    } catch (err) {
      console.error(`Failed to check menu visibility for ${menuCode}:`, err)
    }
    return true
  }

  const getPermissionReport = async () => {
    try {
      const result = await apiV1.get('/menu-permission/menus/report')
      if (result.success) {
        return result.data
      }
    } catch (err) {
      console.error('Failed to get permission report:', err)
    }
    return null
  }

  const reset = () => {
    _menusLoaded.value = false
    menuPermissions.value = []
    error.value = null
    _serverLeafMenus.value = null
    _serverObjectTypeRouteMap.value = null
  }

  return {
    menuPermissions,
    accessibleMenus,
    flatMenus,
    leafMenus,
    objectTypeRouteMap,
    loading,
    error,
    loadMenuPermissions,
    checkMenuVisibility,
    getPermissionReport,
    reset,
  }
}
