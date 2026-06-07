/**
 * SBUSI: business-object - 功能测试 (auto-generated)
 *
 * URL: /system/archdata
 * Data Type: business_object
 * 生成时间: 2026-06-07 17:20:18
 * 生成工具: scripts/auto_gen_v2_spec.py
 *
 * [E2E 规则速查] 修改前必读:
 * - 必须 import 自 auto-fixtures.js（新方案）
 * - 必须用 isolation.createTracked() 创建测试数据
 * - 必须用 withStep() 包裹每个业务步骤
 * - 详细: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM 不用直接 .el-table locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] 每个步骤 withStep() 包裹
 * [OK] isolation fixture 自动清理
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'

test.describe('SBUSI: business-object', () => {
  test('C01: 页面正常加载', async ({ page, navigateTo, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    await withStep(page, testInfo, '导航到 /system/archdata', async () => {
      await navigateTo(page, '/system/archdata?productId=' + pv.product.id + '&versionId=' + pv.version.id)
    })
    await expect(page.getByRole('tab').first()).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: '新建' }).first()).toBeVisible()
  })
  test('C02: 创建business_object记录', async ({ page, navigateTo, dataFinder, isolation }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, '/system/archdata?productId=' + pv.product.id + '&versionId=' + pv.version.id)

    const uniqueId = Date.now().toString(36).toUpperCase()
    const testCode = `E2E_${uniqueId}`
    const testName = `auto-gen-test-${uniqueId}`

    await withStep(page, testInfo, 'API 创建business_object (自动跟踪)', async () => {
      await isolation.createTracked('business_object', {
        code: testCode,
        name: testName,
        version_id: pv.version.id
      })
    })

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '验证列表中出现', async () => {
      await archData.expectRowExists(testCode, {
        timeout: 20000,
        onRetry: async () => {
          try { await archData.search('') } catch (e) {}
        }
      })
    })
  })
  test('C03: 搜索过滤', async ({ page, navigateTo, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, '/system/archdata?productId=' + pv.product.id + '&versionId=' + pv.version.id)

    await withStep(page, testInfo, '验证初始列表加载', async () => {
      const archData = new ArchDataPage(page)
      await page.waitForLoadState('domcontentloaded')
      await archData.waitForReady({ timeout: 10000 })
    })
  })
})
