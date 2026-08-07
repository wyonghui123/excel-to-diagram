/**
 * [TEMP DIAGNOSTIC 2] 实测 C11/C12/C13 交互行为 - 用后即删
 */
import { test, expect } from '@playwright/test'
import { navigateAndWaitForPage, setAdminPermissions } from '../helpers/auth.js'
import { findOrCreateBusinessObjectHierarchy } from '../helpers/data-finder.js'

async function setup(page) {
  const hier = await findOrCreateBusinessObjectHierarchy(page, { scopeNamePrefix: 'E2E_DIAG' })
  let domainId = hier.domainId
  if (!domainId) {
    const domJson = await (await page.request.get(`/api/v2/bo/domain?version_id=${hier.version.id}&page_size=100`)).json()
    domainId = (domJson.data?.items || domJson.data || [])[0]?.id
  }
  await navigateAndWaitForPage(page,
    `/system/archdata?productId=${hier.product.id}&versionId=${hier.version.id}`,
    { expectedPath: 'archdata', waitForTable: true })
  await setAdminPermissions(page)
  const chartBtn = page.locator('.gt-btn-chart-toggle:has-text("图表展示")')
  await chartBtn.waitFor({ state: 'visible', timeout: 45000 })
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
  // 展开面板 (与 expandLayoutPanel 一致)
  await page.locator('.rst-panel-layout').first().waitFor({ state: 'visible', timeout: 30000 }).catch(() => {})
  const rowsVisible = await page.locator('.lgn-row').first().isVisible().catch(() => false)
  if (!rowsVisible) {
    const hdr = page.locator('.rst-panel-layout .collapsible-panel__header').first()
    if (await hdr.isVisible().catch(() => false)) { await hdr.click(); await page.waitForTimeout(300) }
  }
  // 点"全部展开"(文本可能为"全部收起"=已展开,则跳过; 两种情况都要确保展开)
  const allBtn = page.locator('.lcp-toolbar button').first()
  if (await allBtn.isVisible().catch(() => false)) {
    const txt = (await allBtn.textContent()) || ''
    if (txt.includes('展开')) { await allBtn.click(); await page.waitForTimeout(800) }
  }
  await page.waitForTimeout(500)
  return hier
}

const nodeFills = (page) => page.evaluate(() => {
  const s = new Set()
  document.querySelectorAll('svg[class*="mermaid"] g.node rect, svg[id^="mermaid"] g.node rect').forEach(r => {
    const { fill } = window.getComputedStyle(r)
    if (fill && fill !== 'rgb(255, 255, 255)' && fill !== 'transparent' && fill !== 'none') s.add(fill)
  })
  return Array.from(s)
})
const clusterCount = (page) => page.locator('.mermaid-container svg g.cluster').count()
const nodeCount = (page) => page.locator('.mermaid-container svg g.node').count()

test('DIAG2: color + disable behaviors', async ({ page }) => {
  test.setTimeout(180000)
  await setup(page)
  console.log('INIT clusters=', await clusterCount(page), 'nodes=', await nodeCount(page), 'fills=', JSON.stringify(await nodeFills(page)))

  const rows = page.locator('.lgn-row')
  const rowCount = await rows.count()
  console.log('ROW COUNT', rowCount)
  for (let i = 0; i < rowCount; i++) {
    const t = await rows.nth(i).locator('.lgn-title-text').textContent()
    const eye = await rows.nth(i).locator('.lgn-eye').first().getAttribute('title')
    console.log(`row[${i}] title="${t?.trim()}" eye="${eye}"`)
  }

  // ---- C11 test: 自定义 row[1] (子领域) 颜色 → 图表 fill 变化? ----
  console.log('--- C11: custom color on row[1] ---')
  await rows.nth(1).locator('.lgn-color-picker').first().click()
  await page.waitForTimeout(800)
  const swatches = page.locator('.el-color-picker__panel:visible .el-color-predefine__color-selector')
  const swatchCount = await swatches.count()
  console.log('VISIBLE SWATCH COUNT', swatchCount)
  if (swatchCount > 3) {
    await swatches.nth(3).click()
    const confirm = page.locator('.el-color-dropdown__btn, .el-color-picker__panel:visible .el-button').first()
    if (await confirm.isVisible().catch(() => false)) await confirm.click()
  }
  await page.waitForTimeout(1500)
  console.log('AFTER CUSTOM fills=', JSON.stringify(await nodeFills(page)))
  const row1dot = await rows.nth(1).locator('.el-color-picker__color-inner').getAttribute('style')
  console.log('row[1] color dot =', row1dot)

  // ---- C12 test: 禁用 row[1] (子领域, enabled) → cluster 变化? ----
  console.log('--- C12: disable row[1] ---')
  const bc = await clusterCount(page)
  await rows.nth(1).locator('.lgn-eye').first().click()
  await page.waitForTimeout(1500)
  console.log('AFTER DISABLE GROUP clusters=', await clusterCount(page), '(was', bc, ') nodes=', await nodeCount(page))

  // ---- C13 test: 禁用叶子 → node 变化? ----
  console.log('--- C13: leaf count + disable first leaf ---')
  const leaves = page.locator('.lgn-container-leaf')
  const lc = await leaves.count()
  console.log('LEAF COUNT', lc)
  if (lc > 0) {
    const bn = await nodeCount(page)
    await leaves.first().locator('.lgn-leaf-toggle').first().click()
    await page.waitForTimeout(1500)
    console.log('AFTER DISABLE LEAF nodes=', await nodeCount(page), '(was', bn, ')')
  }
})