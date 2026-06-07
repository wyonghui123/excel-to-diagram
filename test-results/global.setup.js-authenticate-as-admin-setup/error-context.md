# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: helpers\global.setup.js >> authenticate as admin
- Location: e2e\helpers\global.setup.js:52:1

# Error details

```
Error: Pinia not mounted: {"hasPinia":false,"hasApp":false,"bodyHTML":"\n    <div id=\"app\"></div>\n    <script type=\"module\" src=\"/src/main.js?t=1780845324695\"></script>\n  \n"}
```

# Test source

```ts
  1   | /**
  2   |  * 全局登录态设置 - v2 简化方案核心
  3   |  *
  4   |  * [!!!] 本文件是 v2 简化方案的登录态共享核心 [!!!]
  5   |  * [!!!] 规范: .trae/rules/e2e-simplification.md 第六节 [!!!]
  6   |  * [!!!] 所有 features 测试禁止在 test() 内调用 login()，必须靠本文件 [!!!]
  7   |  *
  8   |  * 目的：
  9   |  * 1. 在所有测试运行前执行一次 dev-login
  10  |  * 2. 缓存 storageState（cookies + localStorage）到 auth.json
  11  |  * 3. 所有测试自动继承登录态，无需重复登录
  12  |  *
  13  |  * 收益：
  14  |  * - 节省 95% 登录时间（5-15s → 0.05s per test）
  15  |  * - 100 个测试 = 节省 8-15 分钟
  16  |  * - 消除登录相关的 flake（UI 变动不影响测试）
  17  |  *
  18  |  * 注意：
  19  |  * - auth.json 包含 session cookie，必须加入 .gitignore
  20  |  * - 定期重新生成（认证过期时）
  21  |  *
  22  |  * 使用：
  23  |  *   playwright.config.js 中:
  24  |  *   {
  25  |  *     projects: [
  26  |  *       { name: 'setup', testMatch: /.*\.setup\.js/ },
  27  |  *       {
  28  |  *         name: 'features',
  29  |  *         use: { storageState: 'e2e/.auth/admin.json' },
  30  |  *         dependencies: ['setup']
  31  |  *       }
  32  |  *     ]
  33  |  *   }
  34  |  */
  35  | 
  36  | import { test as setup, expect } from '@playwright/test'
  37  | import path from 'path'
  38  | import { fileURLToPath } from 'url'
  39  | 
  40  | const __filename = fileURLToPath(import.meta.url)
  41  | const __dirname = path.dirname(__filename)
  42  | 
  43  | // 用 process.cwd() 作为基准（Playwright 总是从项目根运行）
  44  | const PROJECT_ROOT = process.cwd()
  45  | const AUTH_DIR = path.join(PROJECT_ROOT, 'e2e', '.auth')
  46  | const ADMIN_AUTH_FILE = path.join(AUTH_DIR, 'admin.json')
  47  | const USER_AUTH_FILE = path.join(AUTH_DIR, 'user.json')
  48  | 
  49  | /**
  50  |  * Admin 用户登录 - 拥有所有权限
  51  |  */
  52  | setup('authenticate as admin', async ({ page, request }) => {
  53  |   // 1. 确保 auth 目录存在
  54  |   const fs = await import('fs')
  55  |   fs.mkdirSync(AUTH_DIR, { recursive: true })
  56  |   console.log(`[SETUP] AUTH_DIR: ${AUTH_DIR}`)
  57  |   console.log(`[SETUP] ADMIN_AUTH_FILE: ${ADMIN_AUTH_FILE}`)
  58  |   console.log(`[SETUP] dir exists: ${fs.existsSync(AUTH_DIR)}`)
  59  |   setup.info().annotations.push({ type: 'auth', description: 'admin login via dev-login' })
  60  | 
  61  |   // 2. 优先用 API dev-login（更稳定）
  62  |   const baseURL = process.env.TEST_BASE_URL || 'http://localhost:3010'
  63  |   const appURL = process.env.APP_URL || 'http://localhost:3004'
  64  | 
  65  |   // 2.1 先 navigate 到 frontend origin（让 page 处于正确的 origin）
  66  |   await page.goto(appURL, { waitUntil: 'domcontentloaded' })
  67  | 
  68  |   // 2.2 在 page context 调 dev-login（共享 cookie 到 frontend origin）
  69  |   const loginResp = await page.context().request.get(`${baseURL}/api/v1/auth/dev-login?username=admin`)
  70  |   if (!loginResp.ok()) {
  71  |     throw new Error(
  72  |       `dev-login failed: ${loginResp.status()} ` +
  73  |       `Make sure backend is running on ${baseURL}`
  74  |     )
  75  |   }
  76  |   const cookieNames = (await page.context().cookies()).map(c => c.name)
  77  |   console.log(`[SETUP] dev-login OK, cookies: ${cookieNames.join(',')}`)
  78  | 
  79  |   // 等待 Vue app 挂载（轮询 __pinia，最多 10s）
  80  |   await page.waitForFunction(() => !!window.__pinia, null, { timeout: 10000 })
  81  |     .catch(async () => {
  82  |       const state = await page.evaluate(() => ({
  83  |         hasPinia: !!window.__pinia,
  84  |         hasApp: !!document.querySelector('#app')?.__vue_app__,
  85  |         bodyHTML: document.body?.innerHTML?.substring(0, 200)
  86  |       }))
> 87  |       throw new Error(`Pinia not mounted: ${JSON.stringify(state)}`)
      |             ^ Error: Pinia not mounted: {"hasPinia":false,"hasApp":false,"bodyHTML":"\n    <div id=\"app\"></div>\n    <script type=\"module\" src=\"/src/main.js?t=1780845324695\"></script>\n  \n"}
  88  |     })
  89  | 
  90  |   // 主动触发 loadFromCookie（FR-UI-002: restoreSession 已合并为 loadFromCookie）
  91  |   await page.evaluate(async () => {
  92  |     const pinia = window.__pinia
  93  |     if (!pinia) return
  94  |     const authStore = pinia._s.get('auth')
  95  |     if (authStore && typeof authStore.loadFromCookie === 'function') {
  96  |       await authStore.loadFromCookie('restore')
  97  |     } else if (authStore && typeof authStore.restoreSession === 'function') {
  98  |       await authStore.restoreSession()
  99  |     }
  100 |   })
  101 | 
  102 |   // 等 sessionReady 和 user
  103 |   try {
  104 |     await page.waitForFunction(() => {
  105 |       const pinia = window.__pinia
  106 |       if (!pinia) return false
  107 |       const authStore = pinia._s.get('auth')
  108 |       return authStore && authStore.sessionReady && authStore.user
  109 |     }, null, { timeout: 15000 })
  110 |   } catch (e) {
  111 |     // 调试信息
  112 |     const debug = await page.evaluate(() => {
  113 |       const pinia = window.__pinia
  114 |       const authStore = pinia?._s.get('auth')
  115 |       return {
  116 |         hasPinia: !!pinia,
  117 |         sessionReady: authStore?.sessionReady,
  118 |         hasUser: !!authStore?.user,
  119 |         userKeys: authStore?.user ? Object.keys(authStore.user) : null,
  120 |         url: location.href,
  121 |         cookies: document.cookie
  122 |       }
  123 |     })
  124 |     throw new Error(`Session restore failed: ${JSON.stringify(debug)}`)
  125 |   }
  126 | 
  127 |   // 4. 验证登录成功
  128 |   const userInfo = await page.evaluate(() => {
  129 |     const pinia = window.__pinia
  130 |     return pinia._s.get('auth')?.user
  131 |   })
  132 |   expect(userInfo).toBeTruthy()
  133 |   expect(userInfo.username || userInfo.name).toBeTruthy()
  134 |   console.log(`[OK] admin authenticated: ${userInfo.username || userInfo.name}`)
  135 | 
  136 |   // 4.1 设置 admin 权限（确保菜单/路由可用）
  137 |   await page.evaluate(() => {
  138 |     const pinia = window.__pinia
  139 |     const authStore = pinia?._s.get('auth')
  140 |     if (authStore && authStore.user) {
  141 |       authStore.user.permissions = ['*']
  142 |       authStore.user.roles = authStore.user.roles || []
  143 |     }
  144 |   })
  145 | 
  146 |   // 5. 保存 storage state
  147 |   await page.context().storageState({ path: ADMIN_AUTH_FILE })
  148 |   console.log(`[OK] admin auth state saved to ${ADMIN_AUTH_FILE}`)
  149 | })
  150 | 
  151 | /**
  152 |  * 普通用户登录 - 仅只读权限
  153 |  * 用于测试权限隔离场景
  154 |  */
  155 | setup('authenticate as readonly user', async ({ page, request }) => {
  156 |   const baseURL = process.env.TEST_BASE_URL || 'http://localhost:3010'
  157 |   const appURL = process.env.APP_URL || 'http://localhost:3004'
  158 | 
  159 |   // 先 navigate 到 frontend origin
  160 |   await page.goto(appURL, { waitUntil: 'domcontentloaded' })
  161 | 
  162 |   // 在 page context 调 dev-login（跨域 cookie 共享）
  163 |   const loginResp = await page.context().request.get(`${baseURL}/api/v1/auth/dev-login?username=user`)
  164 |   if (!loginResp.ok()) {
  165 |     console.warn(`[WARN] readonly user login failed: ${loginResp.status()}, skipping`)
  166 |     return  // skip if user doesn't exist
  167 |   }
  168 | 
  169 |   // 主动触发 loadFromCookie（FR-UI-002: restoreSession 已合并为 loadFromCookie）
  170 |   await page.evaluate(async () => {
  171 |     const pinia = window.__pinia
  172 |     if (!pinia) return
  173 |     const authStore = pinia._s.get('auth')
  174 |     if (authStore && typeof authStore.loadFromCookie === 'function') {
  175 |       await authStore.loadFromCookie('restore')
  176 |     } else if (authStore && typeof authStore.restoreSession === 'function') {
  177 |       await authStore.restoreSession()
  178 |     }
  179 |   })
  180 | 
  181 |   await page.waitForFunction(() => {
  182 |     const pinia = window.__pinia
  183 |     return pinia?._s.get('auth')?.user
  184 |   }, null, { timeout: 20000 })
  185 | 
  186 |   // 设置 admin 权限
  187 |   await page.evaluate(() => {
```