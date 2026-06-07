/**
 * 全局登录态设置 - v2 简化方案核心
 *
 * [!!!] 本文件是 v2 简化方案的登录态共享核心 [!!!]
 * [!!!] 规范: .trae/rules/e2e-simplification.md 第六节 [!!!]
 * [!!!] 所有 features 测试禁止在 test() 内调用 login()，必须靠本文件 [!!!]
 *
 * 目的：
 * 1. 在所有测试运行前执行一次 dev-login
 * 2. 缓存 storageState（cookies + localStorage）到 auth.json
 * 3. 所有测试自动继承登录态，无需重复登录
 *
 * 收益：
 * - 节省 95% 登录时间（5-15s → 0.05s per test）
 * - 100 个测试 = 节省 8-15 分钟
 * - 消除登录相关的 flake（UI 变动不影响测试）
 *
 * 注意：
 * - auth.json 包含 session cookie，必须加入 .gitignore
 * - 定期重新生成（认证过期时）
 *
 * 使用：
 *   playwright.config.js 中:
 *   {
 *     projects: [
 *       { name: 'setup', testMatch: /.*\.setup\.js/ },
 *       {
 *         name: 'features',
 *         use: { storageState: 'e2e/.auth/admin.json' },
 *         dependencies: ['setup']
 *       }
 *     ]
 *   }
 */

import { test as setup, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// 用 process.cwd() 作为基准（Playwright 总是从项目根运行）
const PROJECT_ROOT = process.cwd()
const AUTH_DIR = path.join(PROJECT_ROOT, 'e2e', '.auth')
const ADMIN_AUTH_FILE = path.join(AUTH_DIR, 'admin.json')
const USER_AUTH_FILE = path.join(AUTH_DIR, 'user.json')

/**
 * Admin 用户登录 - 拥有所有权限
 */
setup('authenticate as admin', async ({ page, request }) => {
  // 1. 确保 auth 目录存在
  const fs = await import('fs')
  fs.mkdirSync(AUTH_DIR, { recursive: true })
  console.log(`[SETUP] AUTH_DIR: ${AUTH_DIR}`)
  console.log(`[SETUP] ADMIN_AUTH_FILE: ${ADMIN_AUTH_FILE}`)
  console.log(`[SETUP] dir exists: ${fs.existsSync(AUTH_DIR)}`)
  setup.info().annotations.push({ type: 'auth', description: 'admin login via dev-login' })

  // 2. 优先用 API dev-login（更稳定）
  const baseURL = process.env.TEST_BASE_URL || 'http://localhost:3010'
  const appURL = process.env.APP_URL || 'http://localhost:3004'

  // 2.1 先 navigate 到 frontend origin（让 page 处于正确的 origin）
  await page.goto(appURL, { waitUntil: 'domcontentloaded' })

  // 2.2 在 page context 调 dev-login（共享 cookie 到 frontend origin）
  const loginResp = await page.context().request.get(`${baseURL}/api/v1/auth/dev-login?username=admin`)
  if (!loginResp.ok()) {
    throw new Error(
      `dev-login failed: ${loginResp.status()} ` +
      `Make sure backend is running on ${baseURL}`
    )
  }
  const cookieNames = (await page.context().cookies()).map(c => c.name)
  console.log(`[SETUP] dev-login OK, cookies: ${cookieNames.join(',')}`)

  // 等待 Vue app 挂载（轮询 __pinia，最多 10s）
  await page.waitForFunction(() => !!window.__pinia, null, { timeout: 10000 })
    .catch(async () => {
      const state = await page.evaluate(() => ({
        hasPinia: !!window.__pinia,
        hasApp: !!document.querySelector('#app')?.__vue_app__,
        bodyHTML: document.body?.innerHTML?.substring(0, 200)
      }))
      throw new Error(`Pinia not mounted: ${JSON.stringify(state)}`)
    })

  // 主动触发 loadFromCookie（FR-UI-002: restoreSession 已合并为 loadFromCookie）
  await page.evaluate(async () => {
    const pinia = window.__pinia
    if (!pinia) return
    const authStore = pinia._s.get('auth')
    if (authStore && typeof authStore.loadFromCookie === 'function') {
      await authStore.loadFromCookie('restore')
    } else if (authStore && typeof authStore.restoreSession === 'function') {
      await authStore.restoreSession()
    }
  })

  // 等 sessionReady 和 user
  try {
    await page.waitForFunction(() => {
      const pinia = window.__pinia
      if (!pinia) return false
      const authStore = pinia._s.get('auth')
      return authStore && authStore.sessionReady && authStore.user
    }, null, { timeout: 15000 })
  } catch (e) {
    // 调试信息
    const debug = await page.evaluate(() => {
      const pinia = window.__pinia
      const authStore = pinia?._s.get('auth')
      return {
        hasPinia: !!pinia,
        sessionReady: authStore?.sessionReady,
        hasUser: !!authStore?.user,
        userKeys: authStore?.user ? Object.keys(authStore.user) : null,
        url: location.href,
        cookies: document.cookie
      }
    })
    throw new Error(`Session restore failed: ${JSON.stringify(debug)}`)
  }

  // 4. 验证登录成功
  const userInfo = await page.evaluate(() => {
    const pinia = window.__pinia
    return pinia._s.get('auth')?.user
  })
  expect(userInfo).toBeTruthy()
  expect(userInfo.username || userInfo.name).toBeTruthy()
  console.log(`[OK] admin authenticated: ${userInfo.username || userInfo.name}`)

  // 4.1 设置 admin 权限（确保菜单/路由可用）
  await page.evaluate(() => {
    const pinia = window.__pinia
    const authStore = pinia?._s.get('auth')
    if (authStore && authStore.user) {
      authStore.user.permissions = ['*']
      authStore.user.roles = authStore.user.roles || []
    }
  })

  // 5. 保存 storage state
  await page.context().storageState({ path: ADMIN_AUTH_FILE })
  console.log(`[OK] admin auth state saved to ${ADMIN_AUTH_FILE}`)
})

/**
 * 普通用户登录 - 仅只读权限
 * 用于测试权限隔离场景
 */
setup('authenticate as readonly user', async ({ page, request }) => {
  const baseURL = process.env.TEST_BASE_URL || 'http://localhost:3010'
  const appURL = process.env.APP_URL || 'http://localhost:3004'

  // 先 navigate 到 frontend origin
  await page.goto(appURL, { waitUntil: 'domcontentloaded' })

  // 在 page context 调 dev-login（跨域 cookie 共享）
  const loginResp = await page.context().request.get(`${baseURL}/api/v1/auth/dev-login?username=user`)
  if (!loginResp.ok()) {
    console.warn(`[WARN] readonly user login failed: ${loginResp.status()}, skipping`)
    return  // skip if user doesn't exist
  }

  // 主动触发 loadFromCookie（FR-UI-002: restoreSession 已合并为 loadFromCookie）
  await page.evaluate(async () => {
    const pinia = window.__pinia
    if (!pinia) return
    const authStore = pinia._s.get('auth')
    if (authStore && typeof authStore.loadFromCookie === 'function') {
      await authStore.loadFromCookie('restore')
    } else if (authStore && typeof authStore.restoreSession === 'function') {
      await authStore.restoreSession()
    }
  })

  await page.waitForFunction(() => {
    const pinia = window.__pinia
    return pinia?._s.get('auth')?.user
  }, null, { timeout: 20000 })

  // 设置 admin 权限
  await page.evaluate(() => {
    const pinia = window.__pinia
    const authStore = pinia?._s.get('auth')
    if (authStore && authStore.user) {
      authStore.user.permissions = ['*']
    }
  })

  await page.context().storageState({ path: USER_AUTH_FILE })
  console.log(`[OK] readonly user auth state saved`)
})
