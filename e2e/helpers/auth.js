/**
 * E2E 测试辅助函数库
 *
 * [CRITICAL] E2E 测试核心规则（修改/新增测试用例前必读）:
 * ─────────────────────────────────────────────────────────
 * 1. 禁止 waitForLoadState('networkidle') - SPA 中会永久卡死
 *    -> 用 domcontentloaded + 元素等待
 * 2. 截图用 testInfo.attach() - 不用 screenshot:'on'（会截到首页）
 *    -> 用 attachAndVerifyScreenshot() 或 attachScreenshot()
 * 3. 导航用 navigateAndWaitForPage() - 不用 page.goto() + waitForTimeout
 * 4. 登录用 dev-login API（GET /api/v1/auth/dev-login?username=admin）
 *    -> 不再使用 UI 表单登录（慢且不稳定）
 *    -> dev-login 设置 httpOnly cookie，page.request 自动携带
 * 5. playwright.config.js 每个 project 必须指定 testDir
 * 6. 测试终端与 dev server 终端分离（5个终端限制）
 * 7. Element Plus 下拉选项用 :visible 约束（DOM 始终存在）
 * 8. API 请求必须带 Authorization header（page.request 不共享浏览器认证）
 * 9. 报告查看: npx playwright show-report --port 9326
 * 10. 运行前: node scripts/e2e-precheck.js 确认服务就绪
 * ──────────── 运行操作规范 ────────────
 * 11. 终端管理: RunCommand 始终指定 target_terminal='new'
 *     -> 绝不在 dev server 终端运行测试（会杀掉服务）
 * 12. Bug修复后重跑: 加 --retries=0（否则可能被 skip）
 * 13. 截图验证三步法:
 *     步骤1: Get-ChildItem playwright-report\data *.png -> 全部非0KB
 *     步骤2: 在报告页执行 HEAD 请求 -> 全部 HTTP 200
 *     步骤3: 肉眼抽查 >=3 个测试的截图
 * ─────────────────────────────────────────────────────────
 * 详细规则: .trae/rules/e2e-testing.md（E2E 测试单一事实源）
 * Spec 文档: .trae/specs/e2e-test-system-spec.md
 */
export async function login(page) {
  const baseUrl = process.env.TEST_BASE_URL || 'http://localhost:3010'
  const appUrl = process.env.APP_URL || 'http://localhost:3004'

  const resp = await page.request.get(`${baseUrl}/api/v1/auth/dev-login?username=admin`)
  if (!resp.ok()) {
    throw new Error(`dev-login failed: ${resp.status()} ${await resp.text()}`)
  }

  await page.goto(appUrl, { waitUntil: 'domcontentloaded' })

  await page.waitForFunction(() => {
    const pinia = window.__pinia
    if (!pinia) return false
    const authStore = pinia._s.get('auth')
    if (!authStore) return false
    return authStore.sessionReady && authStore.user
  }, null, { timeout: 15000 }).catch(() => {
    console.warn('[auth] SPA session restore timed out, proceeding with waitForLoginOverlay fallback')
    page.locator('.sidebar, .app-tab, [role="tablist"]').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
  })

  await waitForLoginOverlay(page)
}

export async function waitForLoginOverlay(page) {
  try {
    await page.locator('.login-overlay').waitFor({ state: 'hidden', timeout: 10000 })
  } catch (e) {}
}

export async function getAuthToken(page) {
  const cookies = await page.context().cookies()
  const authCookie = cookies.find(c => c.name === 'auth_token')
  return authCookie?.value || null
}

export async function getAuthHeaders(page) {
  const token = await getAuthToken(page)
  return token ? { 'Authorization': `Bearer ${token}` } : {}
}

export async function getPaginatedData(page, url) {
  const resp = await page.request.get(url)
  if (!resp.ok()) return []
  const json = await resp.json()
  return json.data?.items || json.data?.records || json.data?.list || json.data?.rows || (Array.isArray(json.data) ? json.data : [])
}

export async function findProductWithVersion(page) {
  const products = await getPaginatedData(page, '/api/v2/bo/product')
  for (const p of products) {
    const versions = await getPaginatedData(page, `/api/v2/bo/version?product_id=${p.id}`)
    if (versions.length > 0) {
      return { product: p, version: versions[0] }
    }
  }
  return null
}

export async function apiGet(page, url) {
  return await page.request.get(url)
}

export async function apiPost(page, url, data) {
  return await page.request.post(url, { data })
}

export async function apiPut(page, url, data) {
  return await page.request.put(url, { data })
}

export async function apiDelete(page, url) {
  return await page.request.delete(url)
}

export async function waitForPageReady(page, options = {}) {
  const {
    waitForTable = true,
    waitForTabs = false,
    expectedPath = null,
    waitForSelector = null,
    timeout = 15000
  } = options

  await page.waitForLoadState('domcontentloaded')
  await waitForLoginOverlay(page)

  if (expectedPath) {
    try {
      await page.waitForURL(url => {
        try {
          return new URL(url).pathname.includes(expectedPath)
        } catch { return false }
      }, { timeout: 10000 })
    } catch (e) {
      console.log(`[warn] URL did not match expected ${expectedPath}, current: ${page.url()}`)
    }
  }

  if (waitForTabs) {
    const tabSelectors = ['.generic-tab-container', '.el-tabs', '.el-tabs__header', '[role="tablist"]']
    for (const sel of tabSelectors) {
      try {
        await page.locator(sel).first().waitFor({ state: 'visible', timeout: 5000 })
        console.log(`[ok] Found tab container: ${sel}`)
        break
      } catch (e) {}
    }
  }

  if (waitForTable) {
    const tableSelectors = ['.el-table', '.el-table__body', 'table', '.generic-list']
    let tableFound = false
    for (const sel of tableSelectors) {
      try {
        await page.locator(sel).first().waitFor({ state: 'visible', timeout: Math.floor(timeout / tableSelectors.length) })
        tableFound = true
        console.log(`[ok] Found table: ${sel}`)
        break
      } catch (e) {}
    }
    if (!tableFound) {
      const emptyText = page.locator('text=暂无数据').first()
      if (await emptyText.isVisible().catch(() => false)) {
        console.log('[warn] Table shows "No Data"')
      }
    }
  }

  if (waitForSelector) {
    try {
      await page.locator(waitForSelector).first().waitFor({ state: 'visible', timeout })
    } catch (e) {
      console.log(`[warn] Selector '${waitForSelector}' not found`)
    }
  }

  return true
}

export async function navigateToAndWait(page, url, options = {}) {
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  const path = new URL(url, 'http://localhost').pathname.split('/')[1]
  const mergedOptions = { expectedPath: path || url, ...options }
  await waitForPageReady(page, mergedOptions)
}

export async function navigateAndWaitForPage(page, url, options = {}) {
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  const path = new URL(url, 'http://localhost').pathname.split('/')[1]
  const mergedOptions = { expectedPath: path || url, ...options }
  await waitForPageReady(page, mergedOptions)
}

export async function setAdminPermissions(page) {
  await page.evaluate(() => {
    if (window.__pinia) {
      const authStore = window.__pinia._s.get('auth')
      if (authStore && authStore.user) {
        authStore.user.permissions = ['*']
        authStore.user.roles = authStore.user.roles || []
      }
    }
  })
}

export async function attachScreenshot(page, testInfo, name) {
  const screenshot = await page.screenshot({ fullPage: true })
  await testInfo.attach(name, {
    body: screenshot,
    contentType: 'image/png'
  })
}

export async function attachAndVerifyScreenshot(page, testInfo, name, options = {}) {
  const { expectedPath = null, expectedTitle = null, verifyNotHomepage = true } = options

  const currentUrl = page.url()
  const pageTitle = await page.title()

  let screenshot
  try {
    screenshot = await page.screenshot({ fullPage: true })
  } catch (e) {
    console.warn(`[截图警告] ${name}: 截图失败 (${e.message?.substring(0, 80)}), 尝试非全页截图`)
    try {
      screenshot = await page.screenshot({ fullPage: false })
    } catch (e2) {
      console.warn(`[截图警告] ${name}: 非全页截图也失败，跳过截图`)
      return { url: currentUrl, title: pageTitle, issues: ['截图失败'] }
    }
  }
  await testInfo.attach(name, {
    body: screenshot,
    contentType: 'image/png'
  })

  const issues = []

  if (verifyNotHomepage) {
    const isOnLogin = currentUrl.includes('/login') || await page.locator('#username').isVisible().catch(() => false)
    if (isOnLogin) {
      issues.push(`截图 "${name}" 时页面在登录页，可能导航失败`)
    }

    const hasLoginOverlay = await page.locator('.login-overlay').isVisible().catch(() => false)
    if (hasLoginOverlay) {
      issues.push(`截图 "${name}" 时登录遮罩层仍可见`)
    }
  }

  if (expectedPath) {
    const urlObj = new URL(currentUrl)
    if (!urlObj.pathname.includes(expectedPath)) {
      issues.push(`截图 "${name}" 时期望路径含 "${expectedPath}"，实际路径为 "${urlObj.pathname}"`)
    }
  }

  if (expectedTitle) {
    if (!pageTitle.includes(expectedTitle)) {
      issues.push(`截图 "${name}" 时期望标题含 "${expectedTitle}"，实际标题为 "${pageTitle}"`)
    }
  }

  if (issues.length > 0) {
    console.warn(`[截图验证] ${name}: ${issues.join('; ')}`)
  } else {
    console.log(`[截图验证] ${name}: OK (URL: ${currentUrl})`)
  }

  return { url: currentUrl, title: pageTitle, issues }
}

// ============================================================================
// 健康检查辅助函数（可观测性 v3）
// ============================================================================

/**
 * 等待页面健康状态稳定
 * @param {Page} page
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<{healthy: boolean, summary: string}>}
 */
export async function waitForHealthy(page, timeout = 5000) {
  const startTime = Date.now()

  while (Date.now() - startTime < timeout) {
    const health = await checkPageHealth(page)
    if (health.healthy) {
      return health
    }
    await page.waitForTimeout(200)
  }

  return await checkPageHealth(page)
}

/**
 * 检查页面健康状态（聚合四层错误）
 * @param {Page} page
 * @returns {Promise<{healthy: boolean, summary: string, details: object}>}
 */
export async function checkPageHealth(page) {
  const details = {
    appErrors: [],
    consoleErrors: [],
    pageErrors: [],
    crashed: false
  }

  // Layer 1: Vue app errors
  try {
    const appErrors = await page.evaluate(() => window.__appErrors || [])
    details.appErrors = appErrors.slice(-5) // 只取最近5条
  } catch (e) {}

  // Layer 2: Console errors (通过 inject_helpers.js)
  try {
    const consoleErrors = await page.evaluate(() => window.__consoleErrors || [])
    details.consoleErrors = consoleErrors.slice(-5)
  } catch (e) {}

  // Layer 3: Playwright pageerror
  try {
    const pageErrors = await page.evaluate(() => window.__pageErrors || [])
    details.pageErrors = pageErrors.slice(-5)
  } catch (e) {}

  // Layer 4: Check for crash
  try {
    details.crashed = await page.evaluate(() => document.readyState === 'loading' && document.body === null)
  } catch (e) {}

  // 汇总判断
  const hasErrors = details.appErrors.length > 0 ||
                    details.consoleErrors.length > 0 ||
                    details.pageErrors.length > 0 ||
                    details.crashed

  if (details.crashed) {
    return {
      healthy: false,
      summary: 'Page has crashed',
      details
    }
  }

  if (details.appErrors.length > 0) {
    return {
      healthy: false,
      summary: `Vue app errors: ${details.appErrors[0].message || details.appErrors[0]}`,
      details
    }
  }

  if (details.consoleErrors.length > 0) {
    return {
      healthy: false,
      summary: `Console errors: ${details.consoleErrors[0].message || details.consoleErrors[0]}`,
      details
    }
  }

  if (details.pageErrors.length > 0) {
    return {
      healthy: false,
      summary: `Page errors: ${details.pageErrors[0].message || details.pageErrors[0]}`,
      details
    }
  }

  return { healthy: true, summary: 'OK', details }
}

/**
 * 断言页面健康，不健康抛出错误
 * @param {Page} page
 * @param {string} context - 上下文信息（用于错误消息）
 */
export async function assertHealthy(page, context = '') {
  const health = await checkPageHealth(page)
  if (!health.healthy) {
    const msg = context ? `[${context}] Page unhealthy: ${health.summary}` : `Page unhealthy: ${health.summary}`
    throw new Error(msg)
  }
}

/**
 * 等待元素稳定（替代盲等 waitForTimeout）
 * @param {Page} page
 * @param {string} selector - 要监控的元素选择器
 * @param {number} maxWait - 最大等待时间（毫秒）
 * @returns {Promise<boolean>}
 */
export async function waitForStable(page, selector, maxWait = 10000) {
  const startTime = Date.now()
  let previousState = null

  while (Date.now() - startTime < maxWait) {
    try {
      const currentState = await page.evaluate((sel) => {
        const el = document.querySelector(sel)
        if (!el) return null
        return {
          childCount: el.children.length,
          textContent: el.textContent?.substring(0, 100)
        }
      }, selector)

      if (currentState === null) {
        await page.waitForTimeout(200)
        continue
      }

      if (previousState !== null &&
          currentState.childCount === previousState.childCount &&
          currentState.textContent === previousState.textContent) {
        // 状态稳定了
        return true
      }

      previousState = currentState
      await page.waitForTimeout(300)
    } catch (e) {
      await page.waitForTimeout(200)
    }
  }

  return false // 超时
}

/**
 * 等待 DOM 元素存在（不要求可见，用于隐藏元素）
 * @param {Page} page
 * @param {string} selector - 选择器
 * @param {number} timeout - 超时时间
 */
export async function waitForDomExists(page, selector, timeout = 15000) {
  return page.waitForFunction(
    (sel) => document.querySelectorAll(sel).length > 0,
    selector,
    { timeout }
  )
}
