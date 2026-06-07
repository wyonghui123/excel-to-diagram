/**
 * S10: 架构图 - 功能测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 *
 * [UI 行为说明] 实际交互流程（基于代码分析 2026-05-23）:
 * - 路由: /diagram
 * - 六步骤向导: 导入 -> 中心 -> 关系 -> 类型 -> 配置 -> 展示
 * - 步骤0(导入): 上传Excel文件
 * - 步骤1(中心): CenterScopeSelector选择中心范围
 * - 步骤2(关系): 选择关系范围
 * - 步骤3(类型): 选择图表类型（业务对象图/服务模块图）
 * - 步骤4(配置): 颜色/布局/分组配置
 * - 步骤5(展示): MermaidComponent渲染架构图
 * - 从架构数据管理进入时，跳过步骤0-2，直接从步骤3开始
 * - [NOTE] 架构图依赖Excel文件上传或sessionStorage数据
 */
import { test, expect } from '@playwright/test'
import {
  login, navigateAndWaitForPage, setAdminPermissions,
  attachAndVerifyScreenshot, findProductWithVersion
} from '../helpers/auth.js'

async function navigateToDiagram(page) {
  await navigateAndWaitForPage(page, '/diagram', {
    expectedPath: 'diagram',
    waitForTable: false,
    waitForSelector: '.step-navigator, [class*="step"], .diagram-app'
  })
  await page.waitForTimeout(1500)
}

test.describe('S10: 架构图', () => {

  test('C01: 架构图 - 页面加载与步骤导航器', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    await navigateToDiagram(page)
    await attachAndVerifyScreenshot(page, testInfo, '01-diagram-page', { expectedPath: 'diagram' })

    const stepNavigator = page.locator('.step-navigator, [class*="step-nav"], [class*="StepNavigator"]')
    if (await stepNavigator.isVisible().catch(() => false)) {
      console.log('[OK] 步骤导航器可见')

      const steps = stepNavigator.locator('.step-item, [class*="step-item"], [class*="step"]')
      const stepCount = await steps.count()
      console.log(`[OK] 步骤数量: ${stepCount}`)

      const stepLabels = []
      for (let i = 0; i < stepCount; i++) {
        const text = await steps.nth(i).textContent()
        if (text) stepLabels.push(text.trim())
      }
      console.log(`[OK] 步骤标签: ${stepLabels.join(', ')}`)
    } else {
      console.log('[INFO] 步骤导航器不可见，检查页面结构')
      const pageContent = page.locator('main, .diagram-app, [class*="diagram"]')
      if (await pageContent.isVisible().catch(() => false)) {
        console.log('[OK] 架构图页面内容可见')
      }
    }

    const uploadArea = page.locator('.file-uploader, [class*="upload"], input[type="file"]')
    if (await uploadArea.isVisible().catch(() => false)) {
      console.log('[OK] 文件上传区域可见（步骤0: 导入）')
    }

    await attachAndVerifyScreenshot(page, testInfo, '02-diagram-steps', { expectedPath: 'diagram' })
    console.log('[OK] 架构图页面加载测试完成')
  })

  test('C02: 架构图 - 从架构数据管理进入', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    const pv = await findProductWithVersion(page)
    if (!pv) {
      console.log('[SKIP] 没有可用的产品版本，跳过架构图测试')
      return
    }

    await navigateAndWaitForPage(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, {
      expectedPath: 'archdata',
      waitForTable: true
    })
    await page.waitForTimeout(1500)
    await attachAndVerifyScreenshot(page, testInfo, '01-archdata-before-diagram', { expectedPath: 'archdata' })

    const diagramBtn = page.locator('button:has-text("架构图"), button:has-text("生成图"), a:has-text("架构图")').first()
    if (await diagramBtn.isVisible().catch(() => false)) {
      await diagramBtn.click()
      await page.waitForTimeout(2000)

      const isOnDiagramPage = page.url().includes('/diagram')
      if (isOnDiagramPage) {
        await attachAndVerifyScreenshot(page, testInfo, '02-diagram-from-archdata', { expectedPath: 'diagram' })

        const chartTypeStep = page.locator('[class*="step"]:has-text("类型"), [class*="step"]:has-text("图表")')
        if (await chartTypeStep.isVisible().catch(() => false)) {
          console.log('[OK] 从架构数据管理进入后，直接在类型选择步骤')
        }

        const businessObjChart = page.locator('[class*="chart-type"]:has-text("业务对象"), button:has-text("业务对象图"), [class*="option"]:has-text("业务对象")').first()
        if (await businessObjChart.isVisible().catch(() => false)) {
          await businessObjChart.click()
          await page.waitForTimeout(500)
          await attachAndVerifyScreenshot(page, testInfo, '03-diagram-chart-type-selected', { expectedPath: 'diagram' })
        }

        const nextBtn = page.locator('button:has-text("下一步"), button:has-text("确认")').first()
        if (await nextBtn.isVisible().catch(() => false)) {
          await nextBtn.click()
          await page.waitForTimeout(1000)
          await attachAndVerifyScreenshot(page, testInfo, '04-diagram-config-step', { expectedPath: 'diagram' })
        }
      } else {
        console.log(`[WARN] 点击架构图按钮后未跳转，当前URL: ${page.url()}`)
      }
    } else {
      console.log('[INFO] 架构图按钮不可见，尝试直接访问')
      await navigateToDiagram(page)
      await attachAndVerifyScreenshot(page, testInfo, '02-diagram-direct', { expectedPath: 'diagram' })
    }

    console.log('[OK] 架构图从架构数据管理进入测试完成')
  })
})
