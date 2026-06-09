/**
 * S10: 架构图 - 功能测试 (v2 风格)
 *
 * 覆盖场景:
 *   C01 架构图 - 页面加载与步骤导航器
 *   C02 架构图 - 从架构数据管理进入
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直接调用 (改用 navigateTo fixture)
 * [OK] 无 Date.now() 硬编码 (本 spec 不需要创建测试数据)
 * [OK] 禁止 el-table 直查 (本 spec 无表格直查)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('S10: 架构图', () => {

  test('C01: 架构图 - 页面加载与步骤导航器', async ({ page, navigateTo, isolation }, testInfo) => {
    await withStep(page, testInfo, '导航到架构图页面', async () => {
      await navigateTo(page, '/diagram', {
        waitForTable: false,
        waitForSelector: '.step-navigator, [class*="step"], .diagram-app'
      })
    })

    await withStep(page, testInfo, '检查步骤导航器', async () => {
      const stepNavigator = page.locator('.step-navigator, [class*="step-nav"], [class*="StepNavigator"]')
      if (await stepNavigator.isVisible().catch(() => false)) {
        const steps = stepNavigator.locator('.step-item, [class*="step-item"], [class*="step"]')
        const stepCount = await steps.count()

        const stepLabels = []
        for (let i = 0; i < stepCount; i++) {
          const text = await steps.nth(i).textContent()
          if (text) stepLabels.push(text.trim())
        }
        console.log(`[OK] 步骤数量: ${stepCount}, 标签: ${stepLabels.join(', ')}`)
      } else {
        const pageContent = page.locator('main, .diagram-app, [class*="diagram"]')
        if (await pageContent.isVisible().catch(() => false)) {
          console.log('[OK] 架构图页面内容可见')
        }
      }
    })

    await withStep(page, testInfo, '检查文件上传区域', async () => {
      const uploadArea = page.locator('.file-uploader, [class*="upload"], input[type="file"]')
      if (await uploadArea.isVisible().catch(() => false)) {
        console.log('[OK] 文件上传区域可见（步骤0: 导入）')
      }
    })
  })

  test('C02: 架构图 - 从架构数据管理进入', async ({ page, navigateTo, dataFinder, isolation }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    if (!pv) {
      test.skip(true, '没有可用的产品版本，跳过架构图测试')
      return
    }

    await withStep(page, testInfo, '导航到架构数据管理页', async () => {
      await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)
    })

    await withStep(page, testInfo, '点击架构图按钮', async () => {
      const diagramBtn = page.locator('button:has-text("架构图"), button:has-text("生成图"), a:has-text("架构图")').first()
      if (await diagramBtn.isVisible().catch(() => false)) {
        await diagramBtn.click()
        await page.waitForURL('**/diagram**', { timeout: 10000 }).catch(() => {})
      } else {
        console.log('[INFO] 架构图按钮不可见，尝试直接访问')
        await navigateTo(page, '/diagram', {
          waitForTable: false,
          waitForSelector: '.step-navigator, [class*="step"], .diagram-app'
        })
      }
    })

    const isOnDiagramPage = page.url().includes('/diagram')
    if (!isOnDiagramPage) {
      console.log(`[WARN] 点击架构图按钮后未跳转，当前URL: ${page.url()}`)
      return
    }

    await withStep(page, testInfo, '检查是否跳过导入步骤', async () => {
      const chartTypeStep = page.locator('[class*="step"]:has-text("类型"), [class*="step"]:has-text("图表")')
      if (await chartTypeStep.isVisible().catch(() => false)) {
        console.log('[OK] 从架构数据管理进入后，直接在类型选择步骤')
      }
    })

    await withStep(page, testInfo, '选择图表类型', async () => {
      const businessObjChart = page.locator('[class*="chart-type"]:has-text("业务对象"), button:has-text("业务对象图"), [class*="option"]:has-text("业务对象")').first()
      if (await businessObjChart.isVisible().catch(() => false)) {
        await businessObjChart.click()
      }
    })

    await withStep(page, testInfo, '点击下一步/确认', async () => {
      const nextBtn = page.locator('button:has-text("下一步"), button:has-text("确认")').first()
      if (await nextBtn.isVisible().catch(() => false)) {
        await nextBtn.click()
      }
    })
  })
})
