/**
 * Playwright 自动 Fixtures - v2 简化方案核心入口
 *
 * [!!!] 本文件是 v2 简化方案的核心，修改前必读 [!!!]
 * [!!!] 规范: .trae/rules/e2e-simplification.md [!!!]
 * [!!!] 所有 features 测试必须 import 自本文件，不是 @playwright/test [!!!]
 *
 * 解决的核心问题：
 * 1. 每个测试都要重复写 `login + setAdminPermissions + navigateTo + waitForStable`
 * 2. 硬编码 waitForTimeout(1500) - 浪费 1.5 秒/测试
 * 3. 数据查找逻辑和测试逻辑混在一起
 * 4. 跨测试的状态共享困难
 *
 * 方案：
 * 1. 提供 autoAuthedPage fixture - 自动注入登录态
 * 2. 提供 dataFinder fixture - 智能数据查找
 * 3. 提供 navigateTo 函数 - 智能导航（替代 goto + waitForTimeout）
 * 4. 提供 pageReady 断言 - 智能等待稳定 + 健康检查
 *
 * 用法对比：
 *
 * 【旧写法】每个测试 6 行样板
 *   test('xxx', async ({ page }) => {
 *     await login(page)
 *     await setAdminPermissions(page)
 *     await navigateAndWaitForPage(page, '/product-management', { waitForTable: true })
 *     await page.waitForTimeout(1500)  // [X] 硬编码
 *     // ... 测试逻辑
 *   })
 *
 * 【新写法】1 行初始化
 *   test('xxx', async ({ page, dataFinder }) => {
 *     await navigateTo(page, '/product-management')
 *     const { product, version } = await dataFinder.productWithVersion()
 *     // ... 测试逻辑
 *   })
 */

import { test as base, expect } from '@playwright/test'
import { assertHealthy, waitForStable } from './auth.js'
import * as dataFinder from './data-finder.js'
import { clearCache as clearDataFinderCache } from './data-finder.js'
import { TestIsolation, attachIsolationFixtures } from './test-isolation.js'
import { MenuNavigator, findMenuPathForUrl } from './menu-navigator.js'
import { waitForApi, mockApi } from './network-waiter.js'

// ============================================================
// 智能导航 - 替代 page.goto + waitForTimeout
// ============================================================

/**
 * 智能导航到指定路径
 *
 * 自动完成：
 * 1. SPA 内部路由切换（不刷新页面）
 * 2. 等待页面就绪（表格/tabs/选择器）
 * 3. 等待 versionContext 恢复（如果 URL 含 productId/versionId）
 * 4. 等待稳定（无 pending 请求 + DOM 不变）
 * 5. 健康检查（无 pageerror/console.error）
 *
 * @param {Page} page - Playwright Page
 * @param {string} targetPath - 目标路径，如 '/product-management'
 * @param {Object} options - 配置
 *   - waitForTable: 等待表格出现（默认 true）
 *   - waitForTabs: 等待 tabs 出现（默认 false，自动根据 URL 启用）
 *   - waitForSelector: 等待指定选择器
 *   - skipHealthCheck: 跳过健康检查（默认 false）
 *   - stableTimeout: 稳定等待超时（默认 5000ms）
 *   - contextTimeout: 等待 versionContext 恢复超时（默认 8000ms）
 */
export async function navigateToDeepLink(page, schemaId, id) {
  const base = process.env.APP_URL || 'http://localhost:3004'
  const url = `${base}/${schemaId}-management/detail/${id}`
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  return { url, id }
}

export async function navigateTo(page, targetPath, options = {}) {
  const {
    waitForTable = true,
    waitForTabs = null,  // null = 自动根据 URL 决定
    waitForSelector = null,
    skipHealthCheck = false,
    stableTimeout = 5000,
    contextTimeout = 15000  // 整页刷新后等 versionContext 恢复，需要更多时间
  } = options

  // 1. 提取路径段用于 URL 验证
  const expectedPathSegment = targetPath.replace(/^\//, '').split('/')[0]

  // 解析 URL 中的 productId/versionId（决定是否需要等待上下文恢复）
  const url = new URL(targetPath, 'http://placeholder')
  const hasContextParams = url.searchParams.has('productId') || url.searchParams.has('versionId')

  // 2. SPA 内部导航（不触发整页刷新）
  // 例外：URL 含 productId/versionId 时，必须用 page.goto 整页刷新，
  // 因为 useVersionContext.restoreContext() 只在组件挂载时跑一次。
  // SPA 内部跳转不会重新挂载组件，context 无法恢复。
  const navigated = hasContextParams ? false : await page.evaluate(({ path }) => {
    // 方式 1: 通过 app.config.globalProperties.$router
    let app = document.querySelector('#app')?.__vue_app__
    let router = app?.config?.globalProperties?.$router

    // 方式 2: window 全局变量
    if (!router && window.$router) {
      router = window.$router
    }

    if (!router) {
      return false
    }
    router.push(path)
    return true
  }, { path: targetPath })

  // 兜底：如果 router 不可用，或 URL 含 context params（必须整页刷新），用 page.goto
  if (!navigated) {
    const reason = hasContextParams
      ? 'URL contains productId/versionId (requires full reload for versionContext restore)'
      : 'Vue router not found'
    console.log(`[navigateTo] Using page.goto (${reason})`)
    await page.goto(targetPath, { waitUntil: 'domcontentloaded' })
  }

  // 3. 等待 URL 更新
  try {
    await page.waitForURL(url => {
      try {
        return new URL(url).pathname.includes(expectedPathSegment)
      } catch {
        return false
      }
    }, { timeout: 5000 })
  } catch (e) {
    console.warn(`[navigateTo] URL did not match ${expectedPathSegment}, current: ${page.url()}`)
  }

  // 3.5 等待 versionContext 恢复（如果 URL 含 productId/versionId）
  // 这是关键步骤：useVersionContext.restoreContext() 会异步读取 URL
  // 并自动调用 selectProduct/selectVersion，需要等它完成后 tabs/表格才可见
  // 注意：useVersionContext 是 module-level singleton，不是 pinia store
  // 必须通过 DOM 状态判断（empty sidebar 消失 + tabs 出现）
  if (hasContextParams) {
    try {
      await page.waitForFunction(
        () => {
          // 条件 1: "请先选择版本" 提示消失
          const emptySidebar = document.querySelector('.momp-empty-sidebar')
          if (emptySidebar && emptySidebar.offsetParent !== null) {
            return false  // 还显示空状态
          }

          // 条件 2: el-tabs 出现
          const tabs = document.querySelectorAll('.el-tabs__item')
          if (tabs.length === 0) {
            return false
          }

          // 条件 3: 表格区域不为空
          const tableBody = document.querySelector('.el-table__body')
          if (!tableBody) {
            return false
          }

          return true
        },
        null,
        { timeout: contextTimeout }
      )
    } catch (e) {
      console.warn(`[navigateTo] versionContext restore timeout after ${contextTimeout}ms, current state:`)
      const state = await page.evaluate(() => ({
        hasEmptySidebar: !!document.querySelector('.momp-empty-sidebar'),
        tabCount: document.querySelectorAll('.el-tabs__item').length,
        hasTable: !!document.querySelector('.el-table'),
        url: location.href
      })).catch(() => ({}))
      console.warn(`[navigateTo]   state: ${JSON.stringify(state)}`)
      // 不抛出，降级为"有 tabs 出现即可"
    }
  }

  // 4. 等待页面就绪
  const readyPromises = []

  // 自动决定是否等待 tabs
  const shouldWaitForTabs = waitForTabs !== null
    ? waitForTabs
    : hasContextParams  // 有 context params 时等待 tabs 出现

  if (shouldWaitForTabs) {
    readyPromises.push(
      page.locator('.el-tabs__item, .generic-tab-container .tab-item')
        .first()
        .waitFor({ state: 'visible', timeout: 8000 })
        .catch(() => {})
    )
  }

  if (waitForTable) {
    const tableSelectors = ['.el-table', '.el-table__body', 'table', '.generic-list']
    Promise.any(
      tableSelectors.map(sel =>
        page.locator(sel).first().waitFor({ state: 'visible', timeout: 5000 })
      )
    ).catch(() => {
      console.log('[navigateTo] No table found, continuing')
    })
  }

  if (waitForSelector) {
    readyPromises.push(
      page.locator(waitForSelector)
        .first()
        .waitFor({ state: 'visible', timeout: 8000 })
        .catch(() => {})
    )
  }

  await Promise.all(readyPromises).catch(() => {})

  // 5. 等待稳定（智能替代 waitForTimeout）
  await waitForStable(page, 'body', stableTimeout).catch(() => {
    // 稳定超时不一定意味着失败，仅警告
    console.log(`[navigateTo] page did not stabilize in ${stableTimeout}ms`)
  })

  // 6. 健康检查
  if (!skipHealthCheck) {
    await assertHealthy(page, `navigateTo(${targetPath})`).catch(err => {
      throw new Error(`Page unhealthy after navigation: ${err.message}`)
    })
  }

  return page
}

// ============================================================
// 自定义 Fixtures
// ============================================================

/**
 * 扩展的 test fixture：
 * - page: 已自动登录（来自 storageState）
 * - dataFinder: 智能数据查找（带缓存）
 * - navigateTo: 智能导航函数
 * - isolation: 测试隔离 + 自动清理
 * - menuNav: 菜单驱动导航
 * - waitForApi: API 智能等待
 */
export const test = base.extend({
  // dataFinder fixture - 提供智能数据查找
  dataFinder: async ({ page, baseURL }, use) => {
    // 创建绑定到此 page 的 dataFinder
    const bound = {
      productWithVersion: (opts) => dataFinder.findOrCreateProductWithVersion(page, opts),
      createProductWithVersion: () => dataFinder.createProductWithVersion(page),
      roleWithPermissions: (opts) => dataFinder.findOrCreateRoleWithPermissions(page, opts),
      userGroup: (opts) => dataFinder.findOrCreateUserGroup(page, opts),
      businessObject: (opts) => dataFinder.findOrCreateBusinessObject(page, opts),
      businessObjectHierarchy: (opts) => dataFinder.findOrCreateBusinessObjectHierarchy(page, opts),
      ensureRelationships: (opts) => dataFinder.ensureRelationships(page, opts)
    }
    await use(bound)
  },

  // navigateTo fixture - 注入到测试上下文
  navigateTo: async ({}, use) => {
    await use(navigateTo)
  },

  // isolation fixture - 测试隔离 + 自动清理
  isolation: async ({ page }, use, testInfo) => {
    const iso = new TestIsolation(page, testInfo)
    await use(iso)
    // afterEach: 自动清理 (try/finally 强制)
    try {
      const result = await iso.cleanup()
      if (result.errors.length > 0) {
        console.warn(`[isolation] ${result.errors.length} cleanup errors`)
      }
    } catch (e) {
      console.warn('[isolation] cleanup failed:', e.message)
    } finally {
      // [Phase 6] 清 data-finder 缓存, 避免下一次测试拿到脏数据
      try {
        clearDataFinderCache()
      } catch (e) {
        console.warn('[isolation] clearDataFinderCache failed:', e.message)
      }
    }
  },

  // menuNav fixture - 菜单驱动导航
  menuNav: async ({ page }, use) => {
    await use(new MenuNavigator(page))
  },

  // waitForApi fixture - 智能等待 API
  waitForApiFn: async ({}, use) => {
    await use(waitForApi)
  }
})

export { expect }

// ============================================================
// 健康检查快捷方式
// ============================================================

/**
 * 在每个操作前快速检查健康
 */
export async function quickHealthCheck(page, context = '') {
  await assertHealthy(page, context)
}

// ============================================================
// 一站式测试模板
// ============================================================

/**
 * 标准 E2E 测试模板
 *
 * @example
 * test('产品列表加载', async ({ page, dataFinder, navigateTo }) => {
 *   await navigateTo(page, '/product-management')
 *   const { product } = await dataFinder.productWithVersion()
 *   // ... 测试逻辑
 * })
 */
export const standardTest = test
export const standardExpect = expect
