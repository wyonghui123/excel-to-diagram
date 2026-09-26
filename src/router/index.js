import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { validateDetailRoute } from './detailRouteGuard'
import { objectTypeService } from '@/services/objectTypeService'
import { generateDynamicRoutes, isDynamicRouteRegistered, resetDynamicRoutes } from './dynamicRoutes'
import { useMenuPermissions } from '@/composables/useMenuPermissions'
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

// [FIX 2026-09-26] 部署后旧 chunk 失效自愈 (根治"部署后点菜单 tab 空白, 必须手动 F5"):
//   部署会整目录替换 frontend_dist_files/, 旧哈希 chunk 从服务器消失。部署前打开的
//   页面内存里仍持旧 chunk 清单, 点菜单 → 动态 import 旧 URL → 失败 → 导航中断 →
//   tab 空白。自愈: 识别 chunk 加载失败后自动整页刷新 (sessionStorage 时间戳防循环),
//   刷新后 index.html(no-cache) 带回新清单, 直接落到目标路由, 用户无感。
//   服务端配套: unified_18081.py/unified_server.py 对缺失资源返回 404 (不再把
//   index.html 当 200 返回), 保证本 handler 能可靠拿到失败信号。
router.onError((error, to) => {
  const msg = String((error && (error.message || error)) || '')
  if (!/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(msg)) {
    return
  }
  const KEY = '__chunkFailReloadAt__'
  const last = Number(sessionStorage.getItem(KEY) || 0)
  if (Date.now() - last < 10000) {
    logger.warn('[Router] chunk 加载失败且 10s 内已自愈过, 跳过自动刷新', msg)
    return
  }
  sessionStorage.setItem(KEY, String(Date.now()))
  logger.warn('[Router] 检测到旧 chunk 失效 (部署后), 自动刷新页面:', msg)
  window.location.assign(to && to.fullPath ? to.fullPath : window.location.href)
})

router.beforeEach(async (to, from, next) => {
  // [FIX 2026-09-06] 硬刷新动态路由页空白修复:
  //   app.use(router) 的 install 期导航发生在动态路由注册之前, 刷新 /permission-set-management
  //   等动态页时 to.matched=[] 的导航已就位; 此处注册完路由后必须重试一次导航,
  //   否则 matched=[] 的原始导航被 next() 放行 → router-view 无匹配组件 → 页面空白。
  //   仅在"首轮注册 + 原导航未匹配 + 现在能解析到"三个条件同时成立时重试, 无死循环:
  //   重试后 isDynamicRouteRegistered()=true 不再进入本分支; 真正未知路径 resolve 仍为空也跳过。
  if (!isDynamicRouteRegistered()) {
    await generateDynamicRoutes(router)
  }

  // [FIX 2026-09-26] 深链解析失败自愈 (根治"硬刷新动态页整页空白 + No match warn"):
  //   场景: 硬刷新 /permission-set-management, 安装期导航先于 session 恢复,
  //   generateDynamicRoutes 可能走未登录分支吃到 stale menuCache (useMetaCache 的
  //   user_id 校验在 expectedUserId=null 时被跳过) 的旧菜单集 → 目标路径不在其中
  //   → resolve 无匹配 → 原逻辑直接放行 → 整页空白; 且旧菜单已注册 (size>0),
  //   真实菜单到达后永远无法补注册 (死锁)。
  //   自愈: reset + 重新注册一次 (此时 auth 已恢复, 会拿到真实菜单), 解析成功则重试导航;
  //   sessionStorage 时间戳防循环 (真未知路径 10s 内只自愈一次)。
  if (to.matched.length === 0 && router.resolve(to.fullPath).matched.length === 0) {
    const HEAL_KEY = '__dynRouteHealAt__'
    if (Date.now() - Number(sessionStorage.getItem(HEAL_KEY) || 0) > 10000) {
      sessionStorage.setItem(HEAL_KEY, String(Date.now()))
      logger.warn('[Router] 深链路由未匹配, 重置动态路由后重试:', to.fullPath)
      resetDynamicRoutes()
      // [FIX 2026-09-26] 同时 reset 菜单模块级状态: 否则 loadMenuPermissions 因
      //   _menusLoaded/_loadedForUserId 短路, 自愈重跑时仍返回导致失配的旧菜单集。
      useMenuPermissions().reset()
      await generateDynamicRoutes(router)
      if (router.resolve(to.fullPath).matched.length > 0) {
        return next({ ...to, replace: true })
      }
    }
  } else if (to.matched.length === 0 && router.resolve(to.fullPath).matched.length > 0) {
    // [FIX 2026-09-06] 首轮注册完成, 原导航 (matched=[]) 现在能解析到 → 重试一次
    return next({ ...to, replace: true })
  }

  // [FIX 2026-09-26] 未登录深链空白修复 (staging 实测):
  //   无会话深链 /user-management → 菜单 API 401 → 动态路由注册 0 条 → 目标路由
  //   永远 unmatched; 而 unmatched 路由没有 meta.requiresAuth, 下方登录检查整块
  //   跳过 → next() 放行 → 头部裸条+整页空白, URL 不变、不跳登录页。
  //   (网关按 IP 注入 token 的环境会掩盖此问题 — 仅无注入的真实客户端复现。)
  //   修复: 自愈后仍无法解析且未登录 → 重定向首页登录, 携带 redirect 回跳参数
  //   (与下方 requiresAuth 未登录分支及 LoginPage.vue L82 消费端同约定)。
  if (to.matched.length === 0 && router.resolve(to.fullPath).matched.length === 0) {
    const authStore = useAuthStore()
    if (!authStore.isLoggedIn) {
      logger.warn('[Router] 未登录访问未匹配路由, 重定向登录:', to.fullPath)
      return next({ path: '/', query: { redirect: to.fullPath, reason: 'not_logged_in' } })
    }
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

    // [FIX P3 2026-06-30] URL ?help= 携带帮助中心参数时, 跳过登录校验
    //   帮助中心是公开内容 (scenario.json 是静态资源), 未登录也可访问
    if (to.query.help) {
      next()
      return
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
    // [FIX 2026-06-20] Hub 页使用稳定的 baseTabPath 作为 Tab ID,避免子 Tab 切换产生重复 Tab
    const tabId = to.meta.baseTabPath || to.path
    const existingTab = tabStore.tabs.find(t => t.id === tabId)

    if (existingTab) {
      // [FIX 2026-06-20] 复用 openTab 同步更新 path/label,确保 Hub 子 Tab 切换后 Tab 链接正确
      tabStore.openTab({
        id: tabId,
        label: tabLabel,
        path: to.fullPath,
        dynamicLabel: isDynamicLabel
      })
    } else if (to.meta.isDetailRoute) {
      const sourceTabId = tabStore.activeTabId || from.path
      tabStore.openTab({
        id: tabId,
        label: tabLabel,
        path: to.fullPath,
        dynamicLabel: isDynamicLabel,
        meta: { ...to.meta, sourceTabId }
      })
    } else {
      // [FIX] 非详情页也打开新 tab (保留源 tab),不再 close+replace 做 inplace 导航
      const sourceTabId = tabStore.activeTabId || from.path
      tabStore.openTab({
        id: tabId,
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
