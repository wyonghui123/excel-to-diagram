import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { validateDetailRoute } from './detailRouteGuard'
import { objectTypeService } from '@/services/objectTypeService'
import { generateDynamicRoutes, isDynamicRouteRegistered } from './dynamicRoutes'
import { buildStaticRoutes, countRoutes } from './helpers'
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

const routes = buildStaticRoutes({
  // [FR-018] 生产环境不加载 dev 路由
  includeDev: import.meta.env.DEV
})

// [FR-018] 启动期打印路由数量,验证模块化后无遗漏
const routeCount = countRoutes(routes)
logger.debug(`[Router] ${routeCount} static routes registered`)

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

  // [v32] 自动识别"从架构数据图表返回架构数据管理"导航
  //   场景: 用户点 tab bar 的"架构数据管理"tab 从 chart tab 切回
  //   之前只有 chart tab 内的"上一步"按钮 (onNavPrev) 会设置 returningFromDiagram flag
  //   tab bar 切回不会触发 onNavPrev, 导致管理页 onMounted 看不到 flag, 走 fresh 路径, 选择被清空
  //   修复: 在 router 层自动检测这种导航并设置 flag (因为导航本身语义就是"从 chart 返回 management")
  // [FIX v3.19] 扩展: 任何从 archdata 离开的导航 (例如点 tab 进入详情页 / 工作台 / 账户),
  //   在切回 archdata 时也要保留选择 + 触发数据刷新
  if (from.path === '/archdata-chart' && to.path === '/system/archdata') {
    sessionStorage.setItem('returningFromDiagram', 'true')
  } else if (from.path === '/system/archdata' && to.path !== '/system/archdata') {
    // 用户从 archdata 离开去其他页面, 切回时需要恢复
    sessionStorage.setItem('returningFromDiagram', 'true')
  }

  const tabLabel = to.meta.isDetailRoute ? getDetailTabLabel(to) : (to.meta.title || to.name)
  // [FR-016] 非详情页 label 来自 meta.title,是静态的;详情页 label 需要业务数据,是动态的
  const isDynamicLabel = !!to.meta.isDetailRoute

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
        dynamicLabel: isDynamicLabel,
        meta: { ...to.meta, sourceTabId }
      })
    } else {
      // [FIX] 非详情页也打开新 tab (保留源 tab),不再 close+replace 做 inplace 导航
      const sourceTabId = tabStore.activeTabId || from.path
      tabStore.openTab({
        id: to.path,
        label: tabLabel,
        path: to.fullPath,
        dynamicLabel: isDynamicLabel,
        meta: { ...to.meta, sourceTabId }
      })
    }
  }

  next()
})

export async function initDynamicRoutes() {
  await generateDynamicRoutes(router)
}

export default router
