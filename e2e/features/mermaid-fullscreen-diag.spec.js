/**
 * S-MERMAID-FULLSCREEN-DIAG: 全屏后 tooltip / annotation 诊断
 */
import { test } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('S-MERMAID-FULLSCREEN-DIAG', () => {
  test('全屏 + hover + annotation 诊断', async ({ page, navigateTo }, testInfo) => {
    page.on('console', (msg) => {
      const t = msg.text()
      if (t.includes('fullscreen') || t.includes('toggleMaximize') || t.includes('[drag]') || t.includes('Vue warn') || t.includes('error') || t.includes('Error')) {
        console.log(`[BROWSER-${msg.type()}] ${t.substring(0, 300)}`)
      }
    })
    page.on('pageerror', (err) => {
      console.log(`[PAGE-ERROR] ${err.message}`)
    })

    await page.setViewportSize({ width: 1280, height: 720 })

    await withStep(page, testInfo, '导航 + 注入 + 跳 step 5', async () => {
      await navigateTo(page, '/archdata-chart', {
        waitForTable: false,
        waitForSelector: '.aa-diagram-app, .step-navigator'
      })
      await page.waitForFunction(() => !!window.__diagramApp, null, { timeout: 15000 })

      const MOCK = {
        nodes: [
          { id: 'BO_A', name: '采购申请单', code: 'BO_A', category: 'object', domain: '采购域', subDomain: '采购子域', serviceModule: 'SM_采购', serviceModuleName: 'SM_采购', isCenter: true, annotationContent: '采购申请单备注' },
          { id: 'BO_B', name: '采购订单', code: 'BO_B', category: 'object', domain: '采购域', subDomain: '采购子域', serviceModule: 'SM_采购', serviceModuleName: 'SM_采购', isCenter: false, annotationContent: '采购订单需要审批' },
          { id: 'BO_C', name: '供应商主数据', code: 'BO_C', category: 'object', domain: '采购域', subDomain: '供应商子域', serviceModule: 'SM_供应商', serviceModuleName: 'SM_供应商', isCenter: false, annotationContent: '供应商' }
        ],
        links: [
          { source: 'BO_A', target: 'BO_B', sourceName: '采购申请单', targetName: '采购订单', sourceCode: 'BO_A', targetCode: 'BO_B', relationCode: 'R001', relationDesc: '生成', annotationContent: '申请通过后生成订单' },
          { source: 'BO_B', target: 'BO_C', sourceName: '采购订单', targetName: '供应商主数据', sourceCode: 'BO_B', targetCode: 'BO_C', relationCode: 'R002', relationDesc: '关联供应商', annotationContent: '订单关联供应商' }
        ],
        serviceModules: [{ code: 'SM_采购', name: '采购模块', annotationContent: '负责采购流程' }],
        colorGroupBy: 'domain',
        colorScheme: 'default',
        centerScopeColor: '#EDEDED',
        centerScope: ['BO_A'],
        customColors: {},
        centerScopeHighlight: true,
        hideLinkLabelTails: false,
        textColor: 'black'
      }
      await page.evaluate((data) => {
        const app = window.__diagramApp
        app.diagramData.value = data
        for (let i = 0; i < 5; i++) app.nextStep()
      }, MOCK)

      // 关键：Vite HMR 不会让 mermaid 重新渲染
      // syntax 文件 (useBusinessObjectSyntax.js) 修改后必须 page.reload 强制重载
      await page.reload()
      await page.waitForFunction(() => !!window.__diagramApp, null, { timeout: 15000 })
      await page.evaluate((data) => {
        const app = window.__diagramApp
        app.diagramData.value = data
        for (let i = 0; i < 5; i++) app.nextStep()
      }, MOCK)

      await page.waitForSelector('.mermaid-content svg', { timeout: 15000 })
      await page.waitForTimeout(2000)
    })

    // 非全屏：检查 layout + edgeLabel 位置 + annotation panel
    await withStep(page, testInfo, '非全屏状态诊断', async () => {
      const layout = await page.evaluate(() => {
        const svg = document.querySelector('.mermaid-content svg')
        const edgeLabels = svg ? svg.querySelectorAll('.edgeLabel') : []
        const labelData = Array.from(edgeLabels).slice(0, 5).map((el) => {
          const r = el.getBoundingClientRect()
          return { text: el.textContent.trim(), x: r.x, y: r.y, w: r.width, h: r.height, transform: el.getAttribute('transform') }
        })
        const panel = document.querySelector('.annotation-dock-panel')
        const tooltipEl = document.getElementById('mermaid-tooltip')
        return {
          viewport: { w: window.innerWidth, h: window.innerHeight },
          svgRect: (() => { const r = svg.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })(),
          svgViewBox: svg.getAttribute('viewBox'),
          labelCount: edgeLabels.length,
          labels: labelData,
          hasPanel: !!panel,
          panelRect: panel ? (() => { const r = panel.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })() : null,
          panelStyle: panel ? { display: getComputedStyle(panel).display, visibility: getComputedStyle(panel).visibility } : null,
          tooltipExists: !!tooltipEl,
          tooltipParent: tooltipEl ? tooltipEl.parentElement.tagName : null,
          tooltipPosition: tooltipEl ? getComputedStyle(tooltipEl).position : null,
          tooltipZIndex: tooltipEl ? getComputedStyle(tooltipEl).zIndex : null
        }
      })
      console.log('========== NON-FULLSCREEN LAYOUT ==========')
      console.log(JSON.stringify(layout, null, 2))
    })

    // 全屏
    await withStep(page, testInfo, '点击全屏按钮', async () => {
      // 找全屏按钮 - mermaid-component 的 toolbar 里有最大化按钮
      const maxBtn = page.locator('.mermaid-container .toolbar-btn').first()
      const cnt = await maxBtn.count()
      console.log(`[fullscreen] max button count: ${cnt}`)
      if (cnt > 0) {
        await maxBtn.click()
      } else {
        // 兜底：通过 window.__diagramApp 触发全屏（如果暴露了）
        await page.evaluate(() => {
          // 直接调 mermaid-container 的全屏
          const el = document.querySelector('.mermaid-container')
          if (el && el.requestFullscreen) el.requestFullscreen()
        })
      }
      await page.waitForTimeout(1500)
    })

    // 全屏后 hover edgeLabel
    await withStep(page, testInfo, '全屏后 hover edgeLabel', async () => {
      const layout = await page.evaluate(() => {
        const svg = document.querySelector('.mermaid-content svg')
        const edgeLabels = svg ? svg.querySelectorAll('.edgeLabel') : []
        const labelData = Array.from(edgeLabels).slice(0, 5).map((el) => {
          const r = el.getBoundingClientRect()
          return { text: el.textContent.trim(), x: r.x, y: r.y, w: r.width, h: r.height }
        })
        const panel = document.querySelector('.annotation-dock-panel')
        return {
          viewport: { w: window.innerWidth, h: window.innerHeight },
          isFullscreen: !!document.fullscreenElement,
          fullscreenEl: document.fullscreenElement ? document.fullscreenElement.className : null,
          svgRect: (() => { const r = svg.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })(),
          labels: labelData,
          hasPanel: !!panel,
          panelRect: panel ? (() => { const r = panel.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })() : null
        }
      })
      console.log('========== FULLSCREEN LAYOUT ==========')
      console.log(JSON.stringify(layout, null, 2))

      // 真实 hover
      if (layout.labels.length > 0) {
        const lbl = layout.labels[0]
        if (lbl.w > 0 && lbl.h > 0 && lbl.y >= 0 && lbl.y < layout.viewport.h) {
          const cx = lbl.x + lbl.w / 2
          const cy = lbl.y + lbl.h / 2
          console.log(`[fullscreen-hover] hovering at (${cx}, ${cy})`)
          await page.mouse.move(cx, cy, { steps: 5 })
          await page.waitForTimeout(800)
          const tooltipState = await page.evaluate(() => {
            const t = document.getElementById('mermaid-tooltip')
            return {
              visibility: t ? t.style.visibility : null,
              computedVisibility: t ? getComputedStyle(t).visibility : null,
              display: t ? getComputedStyle(t).display : null,
              text: t ? t.textContent.substring(0, 100) : null,
              left: t ? t.style.left : null,
              top: t ? t.style.top : null
            }
          })
          console.log(`[fullscreen-hover] tooltip state: ${JSON.stringify(tooltipState)}`)
        }
      }
    })

    // 退出全屏
    await withStep(page, testInfo, '退出全屏', async () => {
      await page.evaluate(() => {
        if (document.exitFullscreen) document.exitFullscreen()
      })
      await page.waitForTimeout(500)
    })

    await page.screenshot({ path: 'playwright-report/diag-fullscreen.png', fullPage: true })
  })
})