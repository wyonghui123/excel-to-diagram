import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { useMenuCache } from '@/composables/useMetaCache'
import { resolveRoutePath } from '@/utils/routeTemplate'

const PAGE_TYPE_COMPONENTS = {
  object_list: () => import('@/views/GenericObjectList.vue'),
  object_detail: () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
}

const STATIC_ROUTE_NAMES = new Set([
  'landing', 'login', 'theme-preview', 'diagram', 'config',
  'test', 'component-comparison', 'navigation-test',
  'ObjectDetail', 'ObjectDetailCreate', 'RoleDetail',
  'AccountSettings', 'RolePermissionCenter', 'RolePermissionDetail',
  'system-admin', 'ArchDataManagement',
  'task-management', 'task-definitions', 'task-queues', 'task-executions', 'ai-async-tasks'
])

const STATIC_ROUTE_PATHS = new Set([
  '/dev/theme-preview', '/diagram', '/config', '/test',
  '/component-comparison', '/dev/navigation-test', '/account',
  '/detail/', '/system-admin', '/role/',
  '/system/role-permission/', '/system/role-detail/',
  '/system/task-management', '/system/task-definitions',
  '/system/task-queues', '/system/task-executions', '/system/ai-async-tasks',
])

let _routesRegistered = false
let _registeredPathKeys = new Set()

function _resolveComponent(menu) {
  const component = PAGE_TYPE_COMPONENTS[menu.page_type]
  if (component) return component

  if (menu.page_type === 'custom_page') {
    console.warn(
      `[DynamicRoutes] menu "${menu.menu_code}" page_type=custom_page requires a static route ` +
      `in router/index.js. No dynamic route will be registered — page will be blank.`
    )
    return null
  }
  console.warn(
    `[DynamicRoutes] unknown page_type "${menu.page_type}" for menu "${menu.menu_code}", ` +
    `falling back to object_list`
  )
  return PAGE_TYPE_COMPONENTS.object_list
}

function _buildProps(menu) {
  const props = {}

  if (menu.page_type === 'object_list') {
    if (menu.primary_object_type) {
      props.objectType = menu.primary_object_type
    }
  }

  if (menu.page_type === 'multi_object_hub') {
    props.group = menu.menu_code
  }

  if (menu.object_types && menu.object_types.length > 0) {
    props.objectTypes = menu.object_types
  }

  if (menu.page_config && typeof menu.page_config === 'object' && Object.keys(menu.page_config).length > 0) {
    props.pageConfig = menu.page_config
  }

  return Object.keys(props).length > 0 ? props : undefined
}

function _isStaticRoute(name, path) {
  if (name && STATIC_ROUTE_NAMES.has(name)) return true
  if (path) {
    for (const staticPath of STATIC_ROUTE_PATHS) {
      if (path.startsWith(staticPath)) return true
    }
  }
  return false
}

function _registerRoute(router, menu) {
  const component = _resolveComponent(menu)
  if (!component) {
    console.log(`[DynamicRoutes] SKIP ${menu.menu_code}: no component (page_type=${menu.page_type})`)
    return false
  }

  const path = resolveRoutePath(menu)

  if (_isStaticRoute(menu.menu_code, path)) {
    console.log(`[DynamicRoutes] SKIP ${menu.menu_code}: static route (path=${path})`)
    return false
  }

  const pathKey = `${path}|${menu.menu_code}`
  if (_registeredPathKeys.has(pathKey)) {
    console.log(`[DynamicRoutes] SKIP ${menu.menu_code}: already registered pathKey`)
    return false
  }

  const name = menu.menu_code

  if (router.hasRoute(name)) {
    console.log(`[DynamicRoutes] skip duplicate: ${name} (already registered)`)
    _registeredPathKeys.add(pathKey)
    return false
  }

  console.log(`[DynamicRoutes] REGISTER ${menu.menu_code}: path=${path}, page_type=${menu.page_type}`)

  const route = {
    path,
    name,
    component,
    meta: {
      title: menu.menu_name || menu.menu_code,
      requiresAuth: true,
      requiredPermissions: menu.required_permissions || [],
      requiredAny: menu.required_any_permission || false,
      dataPermissionHint: menu.data_permission_hint || null,
      pageType: menu.page_type || null,
      primaryObjectType: menu.primary_object_type || null,
    },
  }

  const props = _buildProps(menu)
  if (props) {
    route.props = props
  }

  router.addRoute(route)
  _registeredPathKeys.add(pathKey)
  return true
}

export async function generateDynamicRoutes(router) {
  if (_routesRegistered) return

  const { accessibleMenus, loadMenuPermissions } = useMenuPermissions()
  const menuCache = useMenuCache()

  let menus = []
  try {
    await loadMenuPermissions()
    menus = accessibleMenus.value || []

    console.log('[DynamicRoutes] accessibleMenus:', menus.length, menus.map(m => m.menu_code))

    if (menus.length > 0) {
      const menuCacheForStore = useMenuCache()
      const cached = menuCacheForStore.getCache()
      menuCacheForStore.setCache(menus, cached?.version || null)
    }
  } catch (e) {
    console.warn('[DynamicRoutes] api load failed, using cache:', e)
    const cached = menuCache.getCache()
    menus = cached?.data || []
  }

  let count = 0
  for (const menu of menus) {
    if (!menu.menu_code || menu.menu_code === 'dashboard') continue

    const flatMenus = [menu]
    if (menu.children && menu.children.length > 0) {
      flatMenus.push(...menu.children.filter(c => c.menu_code !== 'dashboard'))
    }

    console.log(`[DynamicRoutes] processing ${menu.menu_code}, children: ${menu.children?.length || 0}, flatMenus: ${flatMenus.length}`)

    for (const m of flatMenus) {
      if (_registerRoute(router, m)) count++
    }
  }

  _routesRegistered = true
  console.log(`[DynamicRoutes] registered ${count} dynamic routes`)
  return count
}

export function isDynamicRouteRegistered() {
  return _routesRegistered && _registeredPathKeys.size > 0
}

export function resetDynamicRoutes() {
  _routesRegistered = false
  _registeredPathKeys = new Set()
}
