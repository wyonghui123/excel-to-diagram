/**
 * [TEMP DIAGNOSTIC] 导出图表设置面板运行态 - 用后即删
 */
import { test, expect } from '@playwright/test'
import { navigateAndWaitForPage, setAdminPermissions } from '../helpers/auth.js'
import { findOrCreateBusinessObjectHierarchy } from '../helpers/data-finder.js'

test('DIAG: dump panel + store + chart state', async ({ page }, testInfo) => {
  test.setTimeout(150000)
  const hier = await findOrCreateBusinessObjectHierarchy(page, { scopeNamePrefix: 'E2E_DIAG' })
  // 取 domainId（findOrCreate 可能不返回，直接查）
  let domainId = hier.domainId
  if (!domainId) {
    const domResp = await page.request.get(`/api/v2/bo/domain?version_id=${hier.version.id}&page_size=100`)
    const domJson = await domResp.json().catch(() => ({}))
    console.log('DOMAIN RESP', JSON.stringify(domJson).slice(0, 500))
    const doms = Array.isArray(domJson) ? domJson : (domJson.data?.items || domJson.data?.records || domJson.data?.list || domJson.data || domJson.items || [])
    domainId = doms[0]?.id
  }
  console.log('PRODUCT', hier.product.id, 'VERSION', hier.version.id, 'DOMAIN', domainId)
  await navigateAndWaitForPage(page,
    `/system/archdata?productId=${hier.product.id}&versionId=${hier.version.id}`,
    { expectedPath: 'archdata', waitForTable: true })
  await setAdminPermissions(page)
  const chartBtn = page.locator('.gt-btn-chart-toggle:has-text("图表展示")')
  await chartBtn.waitFor({ state: 'visible', timeout: 45000 })
  // 设置 scope
  await page.waitForFunction(() => !!(window.__archPage?.scopeIds?.domain && window.__archPage.versionContext), null, { timeout: 20000 }).catch(() => {})
  for (let i = 0; i < 10; i++) {
    if (await chartBtn.isEnabled().catch(() => false)) break
    await page.evaluate(({ domainId, versionId }) => {
      const m = window.__archPage
      if (!m) return
      if (m.versionContext?.selectedVersionId?.value === null) m.versionContext.selectedVersionId.value = versionId
      if (m.scopeIds?.domain) { m.scopeIds.domain.selected = [domainId]; m.scopeIds.domain.effective = [domainId] }
    }, { domainId, versionId: hier.version.id })
    await page.waitForTimeout(500)
  }
  await chartBtn.click()
  await page.locator('.mermaid-container svg').first().waitFor({ state: 'visible', timeout: 30000 }).catch(() => {})
  await page.waitForTimeout(2500)

  // 展开面板
  await page.locator('.rst-panel-layout').first().waitFor({ state: 'visible', timeout: 30000 }).catch(() => {})
  const expandBtn = page.locator('.lcp-toolbar button:has-text("全部展开")')
  if (await expandBtn.isVisible().catch(() => false)) await expandBtn.click()
  await page.waitForTimeout(800)
  // 再点击 header 展开（若收起）
  const rowsVisible = await page.locator('.lgn-row').first().isVisible().catch(() => false)
  if (!rowsVisible) {
    const hdr = page.locator('.rst-panel-layout .collapsible-panel__header').first()
    if (await hdr.isVisible().catch(() => false)) { await hdr.click(); await page.waitForTimeout(400) }
  }
  await page.waitForTimeout(400)

  const dump = await page.evaluate(() => {
    const out = { rows: [], leaves: [], customColors: null, centerScope: null, centerScopeColor: null, centerScopeHighlight: null, colorGroupBy: null, colorScheme: null }
    document.querySelectorAll('.lgn-row').forEach((row, i) => {
      const title = row.querySelector('.lgn-title-text')?.textContent?.trim()
      const badge = row.querySelector('.lgn-type-badge')?.textContent?.trim() || ''
      const isCenter = row.querySelector('.lgn-title-text.is-center') ? true : false
      const eyeBtn = row.querySelector('.lgn-eye')
      const eyeTitle = eyeBtn?.getAttribute('title') || ''
      const colorTitle = row.querySelector('.lgn-color-picker')?.getAttribute('title') || ''
      const colorVal = row.querySelector('.el-color-picker__color-inner')?.getAttribute('style') || ''
      out.rows.push({ i, title, badge, isCenter, eyeTitle, colorTitle, colorVal })
    })
    document.querySelectorAll('.lgn-container-leaf').forEach((leaf, i) => {
      const name = leaf.querySelector('.leaf-name')?.textContent?.trim()
      const disabled = leaf.classList.contains('leaf-disabled')
      const toggleTitle = leaf.querySelector('.lgn-leaf-toggle')?.getAttribute('title') || ''
      out.leaves.push({ i, name, disabled, toggleTitle })
    })
    const p = window.__archPage
    const store = p?.__diagStore
    return out
  })
  console.log('=== ROWS ===')
  dump.rows.forEach(r => console.log(JSON.stringify(r)))
  console.log('=== LEAVES ===')
  dump.leaves.forEach(l => console.log(JSON.stringify(l)))

  // 从 store 读状态 - 通过 window.__archPage.chartConfig
  const cfg = await page.evaluate(() => {
    const p = window.__archPage
    return {
      colorGroupBy: p?.chartConfig?.colorGroupBy,
      colorScheme: p?.chartConfig?.colorScheme,
      centerScopeHighlight: p?.chartConfig?.centerScopeHighlight
    }
  })
  console.log('=== CHART CFG ===', JSON.stringify(cfg))

  // 尝试从 store 拿 customColors / centerScope
  const storeDump = await page.evaluate(() => {
    try {
      const p = window.__archPage
      // 尝试从 debugLayout 或 diag 拿
      return { diag: !!window.__archPage?.diagramData, layoutDebug: !!window.__archPage?.debugLayout }
    } catch (e) { return { err: e.message } }
  })
  console.log('=== STORE PROBE ===', JSON.stringify(storeDump))

  const fills = await page.evaluate(() => {
    const s = new Set()
    document.querySelectorAll('svg[class*="mermaid"] g.node rect, svg[id^="mermaid"] g.node rect').forEach(r => {
      const { fill } = window.getComputedStyle(r)
      if (fill && fill !== 'rgb(255, 255, 255)' && fill !== 'transparent' && fill !== 'none') s.add(fill)
    })
    return Array.from(s)
  })
  console.log('=== NODE FILLS ===', JSON.stringify(fills))
  const cluster = await page.locator('.mermaid-container svg g.cluster').count()
  const node = await page.locator('.mermaid-container svg g.node').count()
  console.log('=== CLUSTER ===', cluster, 'NODE', node)
})