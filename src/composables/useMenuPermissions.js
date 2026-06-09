import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { apiV1, apiV2 } from '@/utils/httpClient'
import { useMetaCache } from '@/composables/useMetaCache'

const menuPermissions = ref([])
const loading = ref(false)
const error = ref(null)
const _menusLoaded = ref(false)
// [FIX v1.0.4 2026-06-09] 记录上次加载的用户 ID, 检测 user 切换时强制重新拉取
const _loadedForUserId = ref(null)
const _serverLeafMenus = ref(null)
const _serverObjectTypeRouteMap = ref(null)
// [FIX v1.0.4b 2026-06-09] lazy watcher 注册标志
let _watchRegistered = false

export function useMenuPermissions() {
  const authStore = useAuthStore()
  const menuCache = useMetaCache('menuCache')

  // [FIX v1.0.4 2026-06-09] 监听 user 变化, 切换用户时 reset
  //   修复场景: admin 登录看全菜单 → 退出登录 → TEST60 登录
  //             menuCache 和 module-level state 残留 admin 数据
  //             导致 TEST60 看到 admin 的菜单
  // [FIX v1.0.4b 2026-06-09] 必须用 function declaration 而非 const 箭头
  //   const 在函数体内不提升, 触发 TDZ 错误 "Cannot access 'reset' before initialization"
  //   把 watch 移到 reset 之后定义, 用闭包引用 (函数声明可提升)
  //   实际方案: 改用 watchEffect + 函数声明, 或 watch 注册移到文件末尾
  //   这里采用 lazy 注册: 在 loadMenuPermissions 第一次调用时再注册 watch
  //   这样避免 setup 时 TDZ 错误
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
    // [FIX v1.0.4b 2026-06-09] lazy 注册 user 切换 watcher
    //   必须在 reset 之后才能引用, 所以放在第一次调用 loadMenuPermissions 时
    //   借助模块级 _watchRegistered 标记避免重复注册
    if (!_watchRegistered) {
      _watchRegistered = true
      watch(
        () => authStore.user?.user_id ?? authStore.user?.id ?? null,
        (newUserId, oldUserId) => {
          if (oldUserId !== null && newUserId !== oldUserId) {
            // 用户切换: 清空 menu state 和缓存
            reset()
            menuCache.clearCache()
            _loadedForUserId.value = null
          }
        }
      )
    }
    const currentUserId = authStore.user?.user_id ?? authStore.user?.id ?? null
    // [FIX v1.0.4 2026-06-09] 检查 _loadedForUserId 而非 _menusLoaded
    //   原 bug: module-level _menusLoaded 一旦为 true 永不重置
    //   新版: 按 user_id 区分, 切换用户时强制重新拉取
    if (_menusLoaded.value && _loadedForUserId.value === currentUserId && menuPermissions.value.length > 0) return

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
        _loadedForUserId.value = currentUserId
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
      _loadedForUserId.value = currentUserId
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
    _loadedForUserId.value = null  // [FIX v1.0.4] 也重置 user_id
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
