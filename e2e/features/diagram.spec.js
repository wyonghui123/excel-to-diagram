/**
 * S10: 架构图 - 功能测试
 *
 * @deprecated 2026-08-08 本用例整体废弃（skip）：
 *   - 原 /diagram 六步向导（导入→中心→关系→类型→配置→展示）+「业务对象图/服务模块图」图表类型选择
 *     已无业务入口（见 src/router/modules/business.js /archdata-chart @deprecated）
 *   - 业务层面不再区分「业务对象图 / 服务模块图」，图表展示统一为
 *     /system/archdata 嵌入式 Mermaid 图表（EmbeddedChartView → MermaidComponent）
 *   - 嵌入式图表的覆盖见 e2e/features/diagram-interaction.spec.js (S11)
 *   - 本文件保留仅作历史参考，禁止作为新功能入口；如需迁移请基于嵌入图表流程
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
  attachAndVerifyScreenshot, findProductWithVersion, ensureProductWithVersion, runCleanup
} from '../helpers/auth.js'

async function navigateToDiagram(page) {
  await navigateAndWaitForPage(page, '/diagram', {
    expectedPath: 'diagram',
    waitForTable: false,
    waitForSelector: '.step-navigator, [class*="step"], .diagram-app'
  })
  await page.waitForTimeout(1500)
}

// [DEPRECATED 2026-08-08] 老 /diagram 向导 + 业务对象图/服务模块图类型选择已废弃，整体 skip
test.describe.skip('S10: 架构图 (DEPRECATED - 老向导, 已废弃)', () => {

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

  test.afterEach(async () => {
    await runCleanup()
  })

  test('C02: 架构图 - 从架构数据管理进入', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    // [NEW v3.19] 使用 ensureProductWithVersion 确保测试数据存在
    const pv = await ensureProductWithVersion(page)
    console.log(`测试数据: product=${pv.product.id}, version=${pv.version.id}`)

    await navigateAndWaitForPage(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&mode=debug`, {
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
