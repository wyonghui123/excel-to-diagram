import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { validateDetailRoute } from './detailRouteGuard'
import { objectTypeService } from '@/services/objectTypeService'
import { generateDynamicRoutes, isDynamicRouteRegistered } from './dynamicRoutes'
import { logger } from '@/utils/logger'

let objectTypeServiceInitialized = false

async function ensureObjectTypeServiceReady() {
  if (!objectTypeServiceInitialized) {
    await objectTypeService.init()
    objectTypeServiceInitialized = true
  }
}

function getDetailTabLabel(to) {
  const objectType = to.params.objectType
  const id = to.params.id

  logger.debug(`[getDetailTabLabel] objectType=${objectType}, id=${id}, isReady=${objectTypeService.isReady()}`)

  if (!objectTypeService.isReady()) {
    logger.debug('[getDetailTabLabel] Service not ready, using fallback label')
    if (!id) {
      return '新建对象'
    }
    return '对象详情'
  }

  if (!id) {
    const label = objectTypeService.getCreateLabel(objectType)
    logger.debug(`[getDetailTabLabel] Create label: ${label}`)
    return label
  }

  const label = objectTypeService.getDetailLabel(objectType)
  logger.debug(`[getDetailTabLabel] Detail label: ${label}`)
  return label
}

const routes = [
  {
    path: '/',
    name: 'landing',
    component: () => import('@/components/ArchWorkspaceNew.vue'),
    meta: { title: '工作台' }
  },
  {
    path: '/dev/theme-preview',
    name: 'theme-preview',
    component: () => import('@/views/dev/ThemePreview.vue'),
    meta: { title: '主题预览' }
  },
  {
    path: '/diagram',
    name: 'diagram',
    component: () => import('@/views/AADiagramApp/index.vue'),
    meta: { title: '架构图' }
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('@/components/ConfigApp.vue'),
    meta: { title: '配置' }
  },
  {
    path: '/data/:productId?/:versionId?',
    redirect: '/system/archdata'
  },
  {
    path: '/product-version',
    redirect: '/product-management'
  },
  // 静态路由作为兜底，确保动态路由失败时页面仍可正常显示
  {
    path: '/product-management',
    name: 'product-management',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'product' },
    meta: { title: '产品管理', requiresAuth: true }
  },
  {
    path: '/product/:id',
    redirect: to => `/detail/product/${to.params.id}`
  },
  // 静态路由作为兜底，确保动态路由失败时页面仍可正常显示
  {
    path: '/user-permission/:tab?',
    name: 'user-permission',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'user-permission' },
    meta: { title: '用户与权限管理', requiresAuth: true }
  },
  {
    path: '/system-admin',
    name: 'system-admin',
    component: () => import('@/views/SystemAdmin/index.vue'),
    meta: { title: '日志管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/business-config/enums/:id',
    redirect: to => `/detail/enum_type/${to.params.id}`
  },
  // 静态路由作为兜底，确保动态路由失败时页面仍可正常显示
  {
    path: '/business-config/:tab?',
    name: 'business-config',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'business-config' },
    meta: { title: '业务配置', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/role-permission/:roleId',
    name: 'RolePermissionCenter',
    component: () => import('@/views/SystemManagement/RolePermissionCenter.vue'),
    meta: { title: '角色权限配置', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/role-detail/:roleId',
    name: 'RolePermissionDetail',
    component: () => import('@/views/SystemManagement/RoleDetail.vue'),
    meta: { title: '角色详情', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/test',
    name: 'test',
    component: () => import('@/views/ComponentTest.vue'),
    meta: { title: '组件测试' }
  },
  {
    path: '/component-comparison',
    name: 'component-comparison',
    component: () => import('@/views/ComponentComparison.vue'),
    meta: { title: 'UI组件库对比' }
  },
  {
    path: '/dev/navigation-test',
    name: 'navigation-test',
    component: () => import('@/views/dev/NavigationTest.vue'),
    meta: { title: '导航系统测试' }
  },
  {
    path: '/detail/:objectType',
    name: 'ObjectDetailCreate',
    component: () => import('@/views/ObjectDetailPage.vue'),
    meta: {
      title: '新建对象',
      requiresAuth: true,
      objectTypeParam: 'objectType',
      isDetailRoute: true
    }
  },
  {
    path: '/detail/:objectType/:id',
    name: 'ObjectDetail',
    component: () => import('@/views/ObjectDetailPage.vue'),
    meta: {
      title: '对象详情',
      requiresAuth: true,
      objectTypeParam: 'objectType',
      isDetailRoute: true
    }
  },
  {
    path: '/role/:id',
    name: 'RoleDetail',
    component: () => import('@/views/SystemManagement/RoleDetail.vue'),
    meta: {
      title: '角色详情',
      requiresAuth: true,
      requiresAdmin: true
    }
  },
  // M18.6 架构数据管理路由
  {
    path: '/system/relationships',
    redirect: '/system/archdata'
  },
  {
    path: '/system/archdata',
    name: 'ArchDataManagement',
    component: () => import('@/views/SystemManagement/RelationshipManagement.vue'),
    meta: { title: '架构数据管理', requiresAuth: true }
  },
  {
    path: '/system/task-management',
    name: 'task-management',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'task-management' },
    meta: { title: '任务调度', requiresAuth: true }
  },
  {
    path: '/system/task-definitions',
    name: 'task-definitions',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'scheduled_task' },
    meta: { title: '任务定义', requiresAuth: true }
  },
  {
    path: '/system/task-queues',
    name: 'task-queues',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'task_queue' },
    meta: { title: '任务队列', requiresAuth: true }
  },
  {
    path: '/system/task-executions',
    name: 'task-executions',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'task_execution' },
    meta: { title: '执行记录', requiresAuth: true }
  },
  {
    path: '/system/ai-async-tasks',
    name: 'ai-async-tasks',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'ai_async_task' },
    meta: { title: 'AI异步任务', requiresAuth: true }
  },
  {
    path: '/account',
    name: 'AccountSettings',
    component: () => import('@/views/AccountSettings/index.vue'),
    meta: { title: '账户设置', requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  if (!isDynamicRouteRegistered()) {
    await generateDynamicRoutes(router)
  }

  document.title = to.meta.title ? `${to.meta.title} - ArchWorkspace` : 'ArchWorkspace'

  if (to.name === 'ObjectDetail') {
    const valid = await validateDetailRoute(to, from, next)
    if (!valid) return
  }

  if (to.meta.requiresAuth) {
    const authStore = useAuthStore()

    if (!authStore.sessionReady) {
      // [FR-012] 修复 timer 双重 resolve + 泄漏
      // - 用 Set 跟踪所有 timer ID
      // - resolve/reject 前清理所有 timer
      // - 超时 reject 而非 resolve (避免下游不一致)
      await new Promise((resolve, reject) => {
        const timerIds = new Set()
        const start = Date.now()
        const TIMEOUT_MS = 15000
        const POLL_MS = 50

        const cleanup = () => {
          timerIds.forEach(id => clearTimeout(id))
          timerIds.clear()
        }

        const check = () => {
          if (authStore.sessionReady) {
            cleanup()
            return resolve()
          }
          if (Date.now() - start > TIMEOUT_MS) {
            cleanup()
            logger.warn(`[RouterGuard] sessionReady wait timeout after ${TIMEOUT_MS}ms, redirecting to login`)
            return reject(new Error('Auth session timeout'))
          }
          const id = setTimeout(check, POLL_MS)
          timerIds.add(id)
        }
        check()
      }).catch(err => {
        // 超时: 跳转到首页并标记 reason
        logger.warn(`[RouterGuard] Auth session timeout: ${err.message}`)
        next({ path: '/', query: { redirect: to.fullPath, reason: 'session_timeout' } })
        // 阻止后续 next()
        return false
      })
      // [FR-012] 修复后,若已 next() 跳走则终止守卫
      if (!authStore.sessionReady) {
        return
      }
    }

    if (!authStore.isLoggedIn) {
      next({ path: '/', query: { redirect: to.fullPath, reason: 'not_logged_in' } })
      return
    }

    if (!authStore.user) {
      const success = await authStore.loadFromCookie('refresh')
      if (!success) {
        next({ path: '/', query: { redirect: to.fullPath, reason: 'token_expired' } })
        return
      }
    }

    if (to.meta.requiresAdmin && !authStore.isAdmin) {
      next({ path: '/', query: { reason: 'admin_required' } })
      return
    }

    if (to.meta.requiredPermissions && to.meta.requiredPermissions.length > 0) {
      const hasPermission = to.meta.requiredAny
        ? to.meta.requiredPermissions.some(p => authStore.hasPermission(p))
        : to.meta.requiredPermissions.every(p => authStore.hasPermission(p))
      if (!hasPermission) {
        logger.warn(
          `[RouterGuard] Permission denied for ${to.path}:`,
          `required=${to.meta.requiredPermissions}, any=${to.meta.requiredAny}`
        )
        next({ path: '/', query: { reason: 'permission_denied', path: to.path } })
        return
      }
    }

    if (to.meta.dataPermissionHint) {
      authStore.setActiveDataPermissionHint(to.meta.dataPermissionHint)
    }
  }

  if (to.meta.isDetailRoute) {
    await ensureObjectTypeServiceReady()
  }

  const tabStore = useTabStore()

  const tabLabel = to.meta.isDetailRoute ? getDetailTabLabel(to) : (to.meta.title || to.name)
  if (to.meta.openInNewTab !== false && to.name !== 'landing' && tabLabel) {
    const existingTab = tabStore.tabs.find(t => t.id === to.path)

    if (existingTab) {
      tabStore.switchTab(existingTab.id)
    } else if (to.meta.isDetailRoute) {
      const sourceTabId = tabStore.activeTabId || from.path
      tabStore.openTab({
        id: to.path,
        label: tabLabel,
        path: to.fullPath,
        meta: { ...to.meta, sourceTabId }
      })
    } else {
      const fromTab = tabStore.tabs.find(t => t.id === from.path)
      if (fromTab) {
        tabStore.closeTab(from.path)
        tabStore.openTab({
          id: to.path,
          label: tabLabel,
          path: to.fullPath,
          meta: { ...to.meta }
        })
        tabStore.switchTab(to.path)
      } else {
        const sourceTabId = tabStore.activeTabId
        tabStore.openTab({
          id: to.path,
          label: tabLabel,
          path: to.fullPath,
          meta: { ...to.meta, sourceTabId }
        })
      }
    }
  }

  next()
})

export async function initDynamicRoutes() {
  await generateDynamicRoutes(router)
}

export default router
