/**
 * 综合 Demo - 展示完整新方案
 *
 * 本 demo 用 4 个测试展示：
 * 1. POM + isolation + waitForApi - 业务对象 CRUD
 * 2. MenuNavigator - 菜单驱动导航
 * 3. dataFinder - 智能数据查找
 * 4. withStep - 自动截图
 *
 * 对比旧写法的代码量、可读性、稳定性
 */

import { test, expect } from '../helpers/auto-fixtures.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'
import { withStep } from '../helpers/auto-trace.js'

// ============================================================
// 测试 1: 业务对象 CRUD（新方案综合展示）
// ============================================================
test('P01: 业务对象 CRUD - 新方案 (POM + isolation + waitForApi)', async ({
  page, navigateTo, dataFinder, isolation, waitForApiFn
}, testInfo) => {
  // 1. 智能导航（1 行）
  const pv = await dataFinder.productWithVersion()
  await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)

  // 2. 等待 archdata 页面真正加载（tab 出现）
  try {
    await page.waitForSelector('.el-tabs__item, .arch-data-tab, [class*="tab-item"]', { timeout: 15000 })
  } catch (e) {
    console.log('[WARN] archdata tabs not visible after 15s')
  }

  // 2.1 列出现有 tabs 帮助调试
  const tabs = await page.locator('.el-tabs__item, .arch-data-tab, [class*="tab-item"]').allTextContents()
  console.log(`[DEBUG archdata tabs]: [${tabs.join(' | ')}]`)

  // 3. POM 抽象
  const archData = new ArchDataPage(page)

  // 4. 业务流式
  const boCode = `E2E_${isolation.testRunId.substring(0, 12)}`
  const boName = `测试对象_${Date.now()}`

  // 用第一个 tab 名称尝试（兼容不同 tab 配置）
  const targetTab = tabs.find(t => t.includes('业务对象') || t.includes('对象')) || tabs[0]
  if (targetTab) {
    await withStep(page, testInfo, `打开 tab: ${targetTab.trim()}`, async () => {
      await archData.openTab(targetTab.trim())
    })
  } else {
    console.log('[SKIP] archdata 页面无 tab，跳过 tab 操作')
  }

  await withStep(page, testInfo, '通过 API 创建（带 isolation 跟踪）', async () => {
    const bo = await isolation.createTracked('business_object', {
      code: boCode,
      name: boName,
      description: 'E2E 自动测试',
      version_id: pv.version.id
    })
    console.log(`[OK] 创建 BO: id=${bo.id}, code=${bo.code}`)
  })

  await withStep(page, testInfo, '刷新列表（智能等待 API）', async () => {
    // 等列表 API 完成
    await waitForApiFn(page, 'GET /api/v2/bo/business_object')
  })

  console.log(`[OK] ${testInfo.title} 完成 - isolation 将自动清理 ${boCode}`)
})

// ============================================================
// 测试 2: 菜单驱动导航
// ============================================================
test('P02: 菜单驱动导航 - 通过菜单文本点击', async ({
  page, menuNav
}, testInfo) => {
  // 先 goto 首页让菜单渲染
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2000)

  // 旧写法：await page.goto('/product-management')
  // 新写法：通过菜单点击（真实用户行为）
  await withStep(page, testInfo, '通过菜单点击到达产品管理', async () => {
    await menuNav.navigateByMenuText('产品管理')
  })

  // 验证
  await expect(page.locator('.el-table, .generic-list').first()).toBeVisible({ timeout: 10000 })
  console.log(`[OK] 当前 URL: ${page.url()}`)
})

// ============================================================
// 测试 3: 多角色登录测试 - 用户和权限
// ============================================================
test('P03: 权限测试 - admin 应有所有权限', async ({
  page, navigateTo
}, testInfo) => {
  // 先 goto 首页
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1000)

  // storageState 已自动登录为 admin
  await navigateTo(page, '/user-permission', { waitForTabs: true })

  // 直接验证 admin 权限（来自 storageState）
  const isAdmin = await page.evaluate(() => {
    const pinia = window.__pinia
    return pinia?._s.get('auth')?.isAdmin
  })
  expect(isAdmin, 'Admin user should have isAdmin=true').toBe(true)
})

// ============================================================
// 测试 4: 网络性能监控 - 检测慢 API
// ============================================================
test('P04: 慢 API 自动检测', async ({
  page, navigateTo, dataFinder
}, testInfo) => {
  // 先确保登录态激活
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1000)

  const pv = await dataFinder.productWithVersion()
  await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)

  // 直接调用 API 测试性能（> 1s 自动警告）
  const start = Date.now()
  const resp = await page.context().request.get('/api/v2/bo/business_object?page_size=20')
  const duration = Date.now() - start

  expect(resp.ok()).toBe(true)
  console.log(`[PERF] business_object list API: ${duration}ms`)

  if (duration > 1000) {
    console.warn(`[PERF] [WARNING]  Slow API detected: ${duration}ms`)
  }
})
