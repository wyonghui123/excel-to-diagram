/**
 * S-MERMAID-DRAG: 架构图 - Mermaid 图表拖动/缩放/全屏 E2E 测试
 *
 * 目的：诊断 mermaid 图表拖动不工作的问题
 * 覆盖：
 *   C01 滚轮缩放 - 验证 scale 变化
 *   C02 拖动平移 - 验证 translate 变化
 *   C03 全屏切换 - 验证 fullscreen API 成功
 *   C04 全屏中拖动 - 验证 fullscreen 模式下拖动仍可用
 *
 * 必读: .trae/rules/e2e-testing.md
 *
 * 特殊说明：本测试通过 window.__diagramApp 注入 mock diagramData + 跳到 step 5
 *  window.__diagramApp 由 src/views/AADiagramApp/index.vue onMounted 在 dev 环境暴露
 *  跳过 6 步流程的 0-4 步（导入/中心/关系/类型/配置），直接到 step 5（展示）
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

// 最小 mock diagramData（与 buildDiagramData 输出结构一致）
const MOCK_DIAGRAM_DATA = {
  nodes: [
    { id: 'BO_A', name: 'BO_A', originalName: 'BO_A', code: 'BO_A', category: 'object', domain: 'D1', subDomain: 'SD1', serviceModule: 'SM1', serviceModuleName: 'SM1', isCenter: false, annotationCategory: 'info', annotationContent: '' },
    { id: 'BO_B', name: 'BO_B', originalName: 'BO_B', code: 'BO_B', category: 'object', domain: 'D1', subDomain: 'SD1', serviceModule: 'SM1', serviceModuleName: 'SM1', isCenter: false, annotationCategory: 'info', annotationContent: '' },
    { id: 'BO_C', name: 'BO_C', originalName: 'BO_C', code: 'BO_C', category: 'object', domain: 'D2', subDomain: 'SD2', serviceModule: 'SM2', serviceModuleName: 'SM2', isCenter: false, annotationCategory: 'info', annotationContent: '' },
    { id: 'BO_D', name: 'BO_D', originalName: 'BO_D', code: 'BO_D', category: 'object', domain: 'D2', subDomain: 'SD2', serviceModule: 'SM2', serviceModuleName: 'SM2', isCenter: false, annotationCategory: 'info', annotationContent: '' },
    { id: 'BO_E', name: 'BO_E', originalName: 'BO_E', code: 'BO_E', category: 'object', domain: 'D3', subDomain: 'SD3', serviceModule: 'SM3', serviceModuleName: 'SM3', isCenter: false, annotationCategory: 'info', annotationContent: '' }
  ],
  links: [
    { source: 'BO_A', target: 'BO_B', sourceName: 'BO_A', targetName: 'BO_B', sourceCode: 'BO_A', targetCode: 'BO_B', relationCode: 'R1', relationDesc: '关联', annotationCategory: 'info', annotationContent: '' },
    { source: 'BO_B', target: 'BO_C', sourceName: 'BO_B', targetName: 'BO_C', sourceCode: 'BO_B', targetCode: 'BO_C', relationCode: 'R2', relationDesc: '依赖', annotationCategory: 'info', annotationContent: '' },
    { source: 'BO_C', target: 'BO_D', sourceName: 'BO_C', targetName: 'BO_D', sourceCode: 'BO_C', targetCode: 'BO_D', relationCode: 'R3', relationDesc: '组合', annotationCategory: 'info', annotationContent: '' },
    { source: 'BO_D', target: 'BO_E', sourceName: 'BO_D', targetName: 'BO_E', sourceCode: 'BO_D', targetCode: 'BO_E', relationCode: 'R4', relationDesc: '聚合', annotationCategory: 'info', annotationContent: '' }
  ],
  domainProducts: [],
  serviceModules: [],
  colorGroupBy: 'domain',
  colorScheme: 'default',
  nodeTextColor: 'black',
  centerScopeColor: '#EDEDED',
  centerScope: [],
  layoutTemplate: 'default',
  customColors: {},
  hideLinkLabelTails: false,
  layoutControlConfig: null,
  groupControlTitleMap: null,
  centerScopeHighlight: true
}

test.describe('S-MERMAID-DRAG: Mermaid 图表交互', () => {
  test('C01-C04: 缩放/拖动/全屏 综合诊断', async ({ page, navigateTo }, testInfo) => {
    // 收集 console 日志
    const consoleLogs = []
    page.on('console', (msg) => {
      const text = msg.text()
      if (
        text.includes('[drag]') ||
        text.includes('[toggleMaximize]') ||
        text.includes('[setupCanvasLayout]') ||
        text.includes('[autoFitDiagram]') ||
        text.includes('[AADiagramApp]') ||
        text.includes('[mermaid]') ||
        text.includes('error') ||
        text.includes('Error') ||
        text.includes('Failed')
      ) {
        consoleLogs.push(`[${msg.type()}] ${text}`)
      }
    })
    page.on('pageerror', (err) => {
      consoleLogs.push(`[pageerror] ${err.message}`)
    })

    // 1. 导航到 /diagram
    await withStep(page, testInfo, '导航到 /diagram 页面', async () => {
      await navigateTo(page, '/diagram', {
        waitForTable: false,
        waitForSelector: '.aa-diagram-app, .step-navigator, [class*="StepNavigator"]'
      })
    })

    // 2. 等待 window.__diagramApp 可用（新版本 mounted 钩子）
    await withStep(page, testInfo, '等待 window.__diagramApp 暴露', async () => {
      await page.waitForFunction(() => !!window.__diagramApp, null, { timeout: 15000 })
      const info = await page.evaluate(() => {
        const app = window.__diagramApp
        return {
          hasDiagramData: !!app.diagramData,
          currentStep: app.currentStep?.value,
          hasGoToStep: typeof app.goToStep === 'function',
          hasGenerateDiagram: typeof app.generateDiagram === 'function',
          hasInit: typeof app.initFromArchDataManager === 'function'
        }
      })
      console.log(`[OK] window.__diagramApp 已暴露: ${JSON.stringify(info)}`)
      expect(info.hasGoToStep).toBe(true)
    })

    // 3. 注入 mock diagramData + 跳到 step 5（展示）
    await withStep(page, testInfo, '注入 mock diagramData 并跳到 step 5（展示）', async () => {
      const result = await page.evaluate((data) => {
        const app = window.__diagramApp
        if (!app) return { ok: false, error: 'window.__diagramApp is null' }
        // chartType 不显式注入，让 StepDisplay 用 default 'businessObject'
        // （之前 app.chartType.value = 'businessObject' 没生效，因为 chartType 是 computed readonly）
        // 注入 mock diagramData
        app.diagramData.value = data
        // canGoToStep 检查 index <= currentStep+1 || completedSteps.has(index)
        // 连续 nextStep 5 次，从 0 跳到 5
        for (let i = 0; i < 5; i++) {
          app.nextStep()
        }
        return {
          ok: true,
          currentStep: app.currentStep.value,
          hasDiagramData: !!app.diagramData.value,
          chartType: app.chartType?.value
        }
      }, MOCK_DIAGRAM_DATA)
      console.log(`[OK] 注入结果: ${JSON.stringify(result)}`)
      expect(result.ok).toBe(true)
      expect(result.currentStep).toBe(5)
      expect(result.hasDiagramData).toBe(true)
    })

    // 4. 等待 mermaid SVG 渲染
    await withStep(page, testInfo, '等待 mermaid SVG 渲染', async () => {
      const svg = page.locator('.mermaid-container svg, .mermaid-content svg, pre.mermaid svg').first()
      try {
        await svg.waitFor({ state: 'visible', timeout: 20000 })
        const box = await svg.boundingBox()
        console.log(`[OK] mermaid SVG 渲染: ${box?.width}x${box?.height}`)
      } catch (e) {
        console.log(`[WARN] mermaid SVG 渲染超时: ${e.message}`)
        await page.screenshot({ path: 'playwright-report/diag-mermaid-no-svg.png', fullPage: true })
        throw new Error('mermaid SVG 渲染失败')
      }
    })

    // 4.5 关键修复 v19：page.reload() 强制重载让所有 useInteraction 重新加载
    // HMR 替换模块后老 Vue instance 仍用老 addZoomAndPan 闭包，isDragging 状态隔离
    // 强制 reload 让所有 addZoomAndPan 用最新代码
    await withStep(page, testInfo, 'page.reload 强制重载', async () => {
      await page.reload()
      await page.waitForFunction(() => !!window.__diagramApp, null, { timeout: 15000 })
      // 重新注入 mock data 并跳到 step 5
      await page.evaluate((data) => {
        const app = window.__diagramApp
        app.diagramData.value = data
        for (let i = 0; i < 5; i++) {
          app.nextStep()
        }
      }, MOCK_DIAGRAM_DATA)
      // 重新等待 mermaid 渲染
      await page.waitForTimeout(2000)
    })

    // 5. 等待 layout 完成
    await page.waitForTimeout(1000)

    // ============ C01: 滚轮缩放 ============
    let c01Pass = false
    await withStep(page, testInfo, 'C01: 滚轮缩放测试', async () => {
      const initialTransform = await page.evaluate(() => {
        const content = document.querySelector('.mermaid-content')
        return content ? window.getComputedStyle(content).transform : 'none'
      })
      console.log(`[C01] 初始 transform: ${initialTransform}`)

      const svg = page.locator('.mermaid-container svg').first()
      const box = await svg.boundingBox()
      if (!box) {
        console.log('[C01] svg boundingBox 为空，跳过')
        return
      }
      const cx = box.x + box.width / 2
      const cy = box.y + box.height / 2

      await page.mouse.move(cx, cy)
      await page.mouse.wheel(0, -100)
      await page.waitForTimeout(400)

      const afterZoomTransform = await page.evaluate(() => {
        const content = document.querySelector('.mermaid-content')
        return content ? window.getComputedStyle(content).transform : 'none'
      })
      console.log(`[C01] 滚轮后 transform: ${afterZoomTransform}`)

      c01Pass = afterZoomTransform !== initialTransform
      if (c01Pass) {
        console.log('[C01-PASS] 滚轮缩放成功，transform 已变化')
      } else {
        console.log('[C01-FAIL] 滚轮后 transform 未变化（缩放不工作）')
      }
    })

    // 6. 重置 transform
    await withStep(page, testInfo, '重置 transform（双击 mermaid）', async () => {
      await page.locator('.mermaid-container').first().dblclick()
      await page.waitForTimeout(400)
    })

    // ============ C02: 拖动平移 ============
    let c02Pass = false
    await withStep(page, testInfo, 'C02: 拖动平移测试', async () => {
      const initialTransform = await page.evaluate(() => {
        const content = document.querySelector('.mermaid-content')
        return content ? window.getComputedStyle(content).transform : 'none'
      })
      console.log(`[C02] 拖动前 transform: ${initialTransform}`)

      const svg = page.locator('.mermaid-container svg').first()
      const box = await svg.boundingBox()
      if (!box) {
        console.log('[C02] svg boundingBox 为空，跳过')
        return
      }
      const startX = box.x + box.width / 2
      const startY = box.y + box.height / 2

      // 关键修复 v17：用 dispatchEvent 派发事件，绕开 Playwright mouse.move 不触发 mousemove 的问题
      // Playwright 的 page.mouse.move 在某些场景下（如 fullscreen 切换后）不触发 mousemove 事件
      // 直接 dispatch MouseEvent 到元素，强制触发所有 listener
      await page.evaluate(({ startX, startY }) => {
        const container = document.querySelector('.mermaid-container')
        if (!container) return { error: 'no container' }
        const target = document.elementFromPoint(startX, startY) || container
        // 1) mousedown
        target.dispatchEvent(new MouseEvent('mousedown', {
          clientX: startX, clientY: startY, button: 0, bubbles: true, cancelable: true
        }))
        // 2) mousemove (10 步)
        for (let i = 1; i <= 10; i++) {
          const x = startX + (200 * i / 10)
          const y = startY + (100 * i / 10)
          window.dispatchEvent(new MouseEvent('mousemove', {
            clientX: x, clientY: y, button: 0, bubbles: true
          }))
        }
        // 3) mouseup
        window.dispatchEvent(new MouseEvent('mouseup', {
          clientX: startX + 200, clientY: startY + 100, button: 0, bubbles: true
        }))
        return { ok: true }
      }, { startX, startY })
      await page.waitForTimeout(400)

      const afterDragTransform = await page.evaluate(() => {
        const content = document.querySelector('.mermaid-content')
        return content ? window.getComputedStyle(content).transform : 'none'
      })
      console.log(`[C02] 拖动后 transform: ${afterDragTransform}`)

      c02Pass = afterDragTransform !== initialTransform
      if (c02Pass) {
        console.log('[C02-PASS] 拖动成功，transform 已变化')
      } else {
        console.log('[C02-FAIL] 拖动后 transform 未变化（拖动不工作）')
      }
    })

    // 7. 重置
    await page.locator('.mermaid-container').first().dblclick()
    await page.waitForTimeout(400)

    // ============ C03: 全屏切换 ============
    let c03Pass = false
    let isFullscreen = false
    await withStep(page, testInfo, 'C03: 全屏切换测试', async () => {
      const fullscreenBtn = page.locator('button[title*="全屏"], button[title*="全屏查看"]').first()
      if (!await fullscreenBtn.isVisible().catch(() => false)) {
        console.log('[C03] 全屏按钮不可见')
        return
      }

      await fullscreenBtn.click()
      await page.waitForTimeout(1500)

      isFullscreen = await page.evaluate(() => !!document.fullscreenElement)
      console.log(`[C03] document.fullscreenElement: ${isFullscreen}`)
      c03Pass = isFullscreen
      if (isFullscreen) {
        console.log('[C03-PASS] 全屏成功')
        await page.screenshot({ path: 'playwright-report/diag-fullscreen-on.png' })
      } else {
        console.log('[C03-FAIL] 全屏未生效')
        await page.screenshot({ path: 'playwright-report/diag-fullscreen-failed.png' })
      }
    })

    // ============ C04: 全屏中拖动 ============
    let c04Pass = false
    if (isFullscreen) {
      await withStep(page, testInfo, 'C04: 全屏中拖动测试', async () => {
        await page.waitForTimeout(500)

        const initialTransform = await page.evaluate(() => {
          const content = document.querySelector('.mermaid-content')
          return content ? window.getComputedStyle(content).transform : 'none'
        })
        console.log(`[C04] 全屏拖动前 transform: ${initialTransform}`)

        const viewport = page.viewportSize()
        const startX = viewport.width / 2
        const startY = viewport.height / 2

        await page.mouse.move(startX, startY)
        await page.mouse.down()
        await page.waitForTimeout(150)
        await page.mouse.move(startX + 200, startY + 100, { steps: 10 })
        await page.waitForTimeout(150)
        await page.mouse.up()
        await page.waitForTimeout(400)

        const afterDragTransform = await page.evaluate(() => {
          const content = document.querySelector('.mermaid-content')
          return content ? window.getComputedStyle(content).transform : 'none'
        })
        console.log(`[C04] 全屏拖动后 transform: ${afterDragTransform}`)

        c04Pass = afterDragTransform !== initialTransform
        await page.screenshot({ path: 'playwright-report/diag-fullscreen-after-drag.png' })
        if (c04Pass) {
          console.log('[C04-PASS] 全屏中拖动成功')
        } else {
          console.log('[C04-FAIL] 全屏中拖动未生效')
        }
      })

      // 退出全屏
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)
    }

    // ============ 输出所有 console 日志 ============
    await withStep(page, testInfo, '汇总 console 日志', async () => {
      console.log('========== CONSOLE LOG SUMMARY ==========')
      consoleLogs.forEach(log => console.log(log))
      console.log('========== END ==========')

      await testInfo.attach('console-logs.txt', {
        body: consoleLogs.join('\n'),
        contentType: 'text/plain'
      })
    })

    // 8. 总结报告
    console.log(`\n========== DIAGNOSIS RESULT ==========`)
    console.log(`C01 滚轮缩放: ${c01Pass ? 'PASS' : 'FAIL'}`)
    console.log(`C02 拖动平移: ${c02Pass ? 'PASS' : 'FAIL'}`)
    console.log(`C03 全屏切换: ${c03Pass ? 'PASS' : 'FAIL'}`)
    console.log(`C04 全屏中拖动: ${c04Pass ? 'PASS' : isFullscreen ? 'FAIL' : 'SKIP (fullscreen failed)'}`)
    console.log(`====================================\n`)

    // 截图保存最终状态
    await page.screenshot({ path: 'playwright-report/diag-mermaid-final.png', fullPage: true })
  })
})
