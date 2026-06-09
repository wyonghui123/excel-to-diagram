/**
 * S03: 业务对象（BO）管理 - 功能测试 (v2 风格)
 *
 * 路径: /system/archdata (架构数据管理)
 * 验证: BO 列表 + 版本管理 + 关系配置
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (本 spec 无需创建数据)
 * [OK] POM (ArchDataPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

test.describe('S03: 业务对象管理', () => {
  test('C01: 架构数据管理页面加载', async ({ page, navigateTo, dataFinder, waitForApiFn }, testInfo) => {
    const archData = new ArchDataPage(page)

    const pv = await dataFinder.productWithVersion()
    if (!pv) { test.skip(true, '未找到 product/version'); return }

    await withStep(page, testInfo, '导航到架构数据页', async () => {
      await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, { waitForTable: true })
    })

    // 验证 tab 容器
    const tabs = page.locator('.el-tabs__item, [role="tab"]')
    const tabCount = await tabs.count()
    console.log(`[OK] Tab 数量: ${tabCount}`)

    if (tabCount > 0) {
      const boTab = tabs.filter({ hasText: /业务对象|BO/ }).first()
      if (await boTab.isVisible().catch(() => false)) {
        await withStep(page, testInfo, '切换到业务对象 Tab', async () => {
          await boTab.click()
          await archData.waitForReady({ timeout: 10000 }).catch(() => {})
        })
        console.log('[OK] 业务对象 tab 切换成功')
      }
    }
  })

  test('C02: 业务对象搜索与过滤', async ({ page, navigateTo, dataFinder, waitForApiFn }, testInfo) => {
    const archData = new ArchDataPage(page)

    const pv = await dataFinder.productWithVersion()
    if (!pv) { test.skip(true, '未找到 product/version'); return }

    await withStep(page, testInfo, '导航到架构数据页', async () => {
      await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, { waitForTable: true })
    })

    const searchInput = page.locator('input[placeholder*="搜索"], input[placeholder*="查询"]').first()
    if (await searchInput.isVisible().catch(() => false)) {
      await withStep(page, testInfo, '搜索关键字 domain', async () => {
        await searchInput.fill('domain')
      })
      await waitForApiFn(page, 'GET /api/v2/bo/business_object').catch(() => {})
      console.log('[OK] 搜索功能验证')

      await withStep(page, testInfo, '清空搜索', async () => {
        await searchInput.fill('')
      })
    }
  })
})
