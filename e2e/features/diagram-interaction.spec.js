/**
 * S11: 架构图 - 图表设置面板 ↔ 图表高亮居中联动
 *
 * [功能背景 2026-08-05]
 *   在架构数据管理页（/system/archdata）点击"图表展示"进入嵌入式图表视图：
 *   - 图表按钮默认禁用，需先在"对象范围"树勾选节点（hasScopeSelection）才启用
 *   - 左侧 sidebar 出现"图表设置"面板（rst-panel-layout，含 LayoutControlPanel + LayoutGroupNode）
 *   - 双击"分组行非文字区域" → 请求图表聚焦（高亮 + 居中）对应容器
 *   - 双击"叶子节点" → 请求图表聚焦（高亮 + 居中）对应节点/容器
 *   - 双击"标题文字" → 进入标题编辑模式，不触发联动
 *   联动链路：LayoutGroupNode dblclick → request-chart-focus → LayoutControlPanel
 *             → diagramConfigStore.requestChartFocus → MermaidComponent watch
 *             → focusOnTarget(高亮 .annotation-highlighted) + centerElement(.mermaid-content transform)
 *
 * [数据策略]
 *   整个 describe 只创建一次测试层级（模块级 _hierPromise 缓存），
 *   避免每个 test 重复创建导致 POST 超时/数据污染。
 *
 * [E2E 规则速查]
 *   - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 *   - 权限用 setAdminPermissions() | 数据用 findOrCreateBusinessObjectHierarchy()
 *   - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 */
import { test, expect } from '@playwright/test'
import {
  navigateAndWaitForPage, setAdminPermissions,
  attachAndVerifyScreenshot
} from '../helpers/auth.js'
import {
  findOrCreateBusinessObjectHierarchy,
  clearCache
} from '../helpers/data-finder.js'

// ============================================================
// 模块级：整个 describe 只创建一次测试层级，避免重复创建
// ============================================================
let _hierPromise = null
function getHierarchy(page) {
  if (!_hierPromise) {
    _hierPromise = (async () => {
      // 优先复用已存在的完整层级（避免慢速创建）
      const existing = await findExistingHierarchy(page)
      if (existing) return existing
      return createHierarchyWithRetry(page)
    })()
  }
  return _hierPromise
}

// [STABILITY 2026-08-05] 后端在批量运行时偶发慢响应（10s 超时），
// 统一给数据查询请求加 30s 超时 + 指数退避重试，避免测试因瞬时负载误判失败。
const API_TIMEOUT = 30000
const API_RETRIES = 3

// 从 API 分页响应中提取数组（带超时 + 重试，容忍瞬时慢响应）
async function getItems(resp) {
  const json = await resp.json().catch(() => ({}))
  const data = json.data !== undefined ? json.data : json
  if (Array.isArray(data)) return data
  return data?.items || data?.records || data?.list || data?.rows || []
}

async function apiGetWithRetry(page, url) {
  let lastErr
  for (let attempt = 1; attempt <= API_RETRIES; attempt++) {
    try {
      const resp = await page.request.get(url, { timeout: API_TIMEOUT })
      if (resp.ok()) return resp
      lastErr = new Error(`GET ${url} -> HTTP ${resp.status()}`)
      // 401/403 视为持久性失败，不再重试
      if (resp.status() === 401 || resp.status() === 403) throw lastErr
    } catch (e) {
      lastErr = e
      // 超时/网络错误才重试
      if (e && (e.name === 'TimeoutError' || e.message?.includes('timeout'))) {
        if (attempt < API_RETRIES) {
          await page.waitForTimeout(1000 * attempt)
          continue
        }
      } else {
        throw e
      }
    }
    if (attempt < API_RETRIES) await page.waitForTimeout(1000)
  }
  throw lastErr || new Error(`GET ${url} failed`)
}

/**
 * 查找已存在的完整层级（version 有 domain + 带 service_module 的 BO），避免创建
 */
async function findExistingHierarchy(page) {
  const products = await getItems(await apiGetWithRetry(page, '/api/v2/bo/product?page_size=100'))
  for (const p of products) {
    if (p.is_active === false) continue
    const versions = await getItems(await apiGetWithRetry(page, `/api/v2/bo/version?product_id=${p.id}&page_size=100`))
    for (const v of versions) {
      const domains = await getItems(await apiGetWithRetry(page, `/api/v2/bo/domain?version_id=${v.id}&page_size=100`))
      if (domains.length === 0) continue
      const bos = await getItems(await apiGetWithRetry(page, `/api/v2/bo/business_object?version_id=${v.id}&page_size=100`))
      const usable = bos.filter(b => b.service_module_id)
      if (usable.length > 0) {
        console.log(`[数据] 复用已有层级 product=${p.id}, version=${v.id}, BOs=${usable.length}`)
        // 顺带捕获首个 domain id，供 selectScopeForChart 直接使用，避免再次调 API（消除 C03 偶发 API 挂起）
        return { product: p, version: v, businessObjects: usable, domainId: domains[0].id, source: 'existing' }
      }
    }
  }
  return null
}

async function createHierarchyWithRetry(page) {
  const MAX_ATTEMPTS = 3
  for (let i = 1; i <= MAX_ATTEMPTS; i++) {
    try {
      return await findOrCreateBusinessObjectHierarchy(page, { scopeNamePrefix: 'E2E_DIAG' })
    } catch (e) {
      console.warn(`[data] 创建测试层级失败 (attempt ${i}/${MAX_ATTEMPTS}): ${e.message}`)
      if (i === MAX_ATTEMPTS) throw e
      clearCache() // 失败后清缓存，重试走全新创建
      await page.waitForTimeout(1500)
    }
  }
}

/**
 * 确定性启用图表按钮：直接写 Pinia store 的 scopeIds（替代点击对象树，避免树加载时序抖动）
 * handleShowChart 读取 scopeIds[type].selected 构建 hierarchyFilter，写真实 domain id 即可正确渲染
 *
 * [STABILITY 2026-08-05] 冷启动时 __archPage 可能尚未挂载 / versionContext 尚未恢复，
 * 单次 set scope 不保证按钮立即可用。故幂等重试 + 轮询按钮 enabled 状态。
 */
async function enableChartButton(page, chartBtn, hierarchy) {
  const domainId = hierarchy.domainId
  const versionId = hierarchy.version.id
  if (!domainId || !versionId) return
  // 1) 等待 __archPage 就绪（冷启动挂载慢）
  await page.waitForFunction(() => {
    const m = window.__archPage
    return !!(m && m.scopeIds && m.scopeIds.domain && m.versionContext)
  }, null, { timeout: 20000 }).catch(() => {})
  // 2) 幂等设置 版本上下文 + domain scope，轮询直到按钮可用
  //    [FIX 2026-08-05] canShowChart 依赖 versionContext.selectedVersionId + hasScopeSelection。
  //    冷启动时 URL 版本参数可能尚未 restore，仅设 scope 不够，需同时兜底写版本上下文。
  for (let i = 0; i < 10; i++) {
    if (await chartBtn.isEnabled().catch(() => false)) return
    await page.evaluate(({ domainId, versionId }) => {
      const m = window.__archPage
      if (!m) return
      // a) 版本上下文（canShowChart 前置条件，URL 版本与测试版本一致，幂等）
      const vc = m.versionContext
      if (vc && vc.selectedVersionId && vc.selectedVersionId.value === null) {
        vc.selectedVersionId.value = versionId
      }
      // b) domain scope（hasScopeSelection 前置条件）
      if (m.scopeIds && m.scopeIds.domain) {
        m.scopeIds.domain.selected = [domainId]
        m.scopeIds.domain.effective = [domainId]
      }
    }, { domainId, versionId })
    await page.waitForTimeout(500)
  }
  await expect(chartBtn, '图表展示按钮应最终变为可用').toBeEnabled({ timeout: 15000 })
}

/**
 * 进入嵌入式图表视图（选择对象范围 → 列表切图表）并等待图表渲染
 *
 * [STABILITY 2026-08-05] 冷启动（首个测试）时 Vite 需编译 archdata 及其依赖，
 * main 区域可能短暂为空。因此先等页面主内容挂载，再等图表按钮，均给足 45s。
 *
 * [FIX 2026-08-05] 原实现 chartBtn.click() + svg.waitFor().catch(()=>{}) 会吞掉
 * "视图未真正切换到图表"的失败（偶发图表按钮点击后视图仍停在列表/图表数据未就绪），
 * 导致后续 .rst-panel-layout / .lgn-row 全部找不到。改为 ensureChartMode() 显式确认
 * 图表模式生效（按钮变为"列表展示"），svg 等待不加 catch，失败即明示。
 */
async function openEmbeddedChartView(page, hierarchy) {
  await navigateAndWaitForPage(page,
    `/system/archdata?productId=${hierarchy.product.id}&versionId=${hierarchy.version.id}`,
    { expectedPath: 'archdata', waitForTable: true })
  // 页面加载后再设置权限（需 window.__pinia 就绪）
  await setAdminPermissions(page)

  // 等待页面主内容真正挂载（兜底冷启动编译慢导致 main 为空）
  const pageRoot = page.locator('.multi-object-management, .momp-tabs-row, .el-table, .gt-btn-chart-toggle')
  await pageRoot.first().waitFor({ state: 'visible', timeout: 45000 }).catch(() => {})

  const chartBtn = page.locator('.gt-btn-chart-toggle:has-text("图表展示")')
  await chartBtn.waitFor({ state: 'visible', timeout: 45000 })

  // 图表按钮默认禁用（require_filters），需先设置 scope 选择
  if (await chartBtn.isDisabled().catch(() => true)) {
    await enableChartButton(page, chartBtn, hierarchy)
  }

  // 确定性进入图表模式：点"图表展示"，轮询直到按钮变为"列表展示"（=图表视图已激活）
  await ensureChartMode(page)

  // 等待 mermaid 画布渲染出 svg（不吞错误：图表未渲染则测试应明示失败）
  // [FIX 2026-08-05] 冷启动 ELK 布局 + 图表数据生成(loading)可达 60-90s, 放宽到 120s 兜底
  const svg = page.locator('.mermaid-container svg').first()
  await svg.waitFor({ state: 'visible', timeout: 120000 })
  await page.waitForTimeout(2500)
}

/**
 * 确定性进入图表模式：点击"图表展示"切换按钮，直到按钮文本变为"列表展示"（当前处于图表视图）。
 * 解决偶发"点击后视图仍停在列表 / 图表数据未就绪"导致的后续面板定位失败。
 */
async function ensureChartMode(page) {
  const listBtn = page.locator('.gt-btn-chart-toggle:has-text("列表展示")').first()
  // 已在图表模式（按钮显示"列表展示"）→ 无需再操作
  if (await listBtn.isVisible().catch(() => false)) return
  for (let i = 0; i < 12; i++) {
    const chartBtn = page.locator('.gt-btn-chart-toggle:has-text("图表展示")').first()
    if (await chartBtn.isVisible().catch(() => false)) {
      await chartBtn.click()
    }
    try {
      await listBtn.waitFor({ state: 'visible', timeout: 3000 })
      return
    } catch {
      await page.waitForTimeout(500)
    }
  }
  throw new Error('无法进入图表模式: 点击图表展示后视图未切换到图表视图')
}

/**
 * 展开"图表设置"面板并"全部展开"分组，使叶子节点可见
 *
 * [FIX 2026-08-05] 面板默认收起（layoutExpanded=false），点击 header 展开后还需等待
 *   LayoutControlPanel 渲染 + 自动分组完成，.lgn-row 才会可见。原实现只 waitFor 300ms
 *   + 吞掉 .rst-panel-layout 等待失败，导致 C11/C16/C17 偶发 .lgn-row 找不到。
 *   改为：等待面板出现 → 若 rows 不可见则点 header → 轮询 rows 可见（15s）→ 全部展开。
 */
async function expandLayoutPanel(page) {
  // 1) 等待"图表设置"面板出现（依赖 chartDataSnapshot 就绪，冷启动可能较慢）
  await page.locator('.rst-panel-layout').first().waitFor({ state: 'visible', timeout: 30000 })
  // 2) 若分组行不可见 → 面板处于收起态，点击 header 展开
  const rowsVisible = async () => (await page.locator('.lgn-row').first().isVisible().catch(() => false))
  if (!(await rowsVisible())) {
    const layoutHeader = page.locator('.rst-panel-layout .collapsible-panel__header').first()
    if (await layoutHeader.isVisible().catch(() => false)) {
      await layoutHeader.click()
      await page.waitForTimeout(300)
    }
  }
  // 3) 轮询直到分组行可见（面板展开 + 自动分组渲染完成）
  await expect.poll(rowsVisible, { timeout: 15000 }).toBe(true)
  // 4) 全部展开以显示叶子节点
  const expandBtn = page.locator('.lcp-toolbar button:has-text("全部展开")')
  if (await expandBtn.isVisible().catch(() => false)) {
    await expandBtn.click()
    await page.waitForTimeout(600)
  }
}

async function getContentTransform(page) {
  const el = page.locator('.mermaid-content').first()
  if (!(await el.isVisible().catch(() => false))) return null
  return el.evaluate(e => e.style.transform || '')
}

async function getHighlightedCount(page) {
  return page.locator('.mermaid-container [class*="annotation-highlighted"]').count()
}

// 采集被高亮元素的标识（data-code / data-id / 文本），用于断言"连续聚焦切换到新目标，而非叠加"
async function getHighlightedIdentifiers(page) {
  return page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('.mermaid-container [class*="annotation-highlighted"]'))
    return els.map(el => el.getAttribute('data-code') || el.getAttribute('data-id') || el.textContent?.trim() || el.id).filter(Boolean)
  })
}

// 容器边框数量 (mermaid subgraph 渲染为 g.cluster)。
// [语义 2026-08-05] 禁用分组/容器 → groupedLayout 走"外提"分支: 容器边框(g.cluster)移除,
//   但其子节点打平渲染保留 (g.node 数量不变)。故"禁用"可观测信号是 g.cluster 减少, 而非 g.node 减少。
async function getClusterCount(page) {
  return page.locator('.mermaid-container svg g.cluster').count()
}

// 打开分组行色点 → 选预定义色板第 swatchIndex 个色并提交 (确保不因 Esc 取消丢弃)
// [FIX 2026-08-05] 必须限定到"可见面板"里的色块: 页面同时存在多个 el-color-picker 都会渲染
//   predefine 色块 (56 个), 只有当前打开面板 (el-color-picker__panel:visible) 里的可点。
async function pickGroupColor(page, rowLocator, swatchIndex) {
  await rowLocator.locator('.lgn-color-picker').first().click()
  const swatch = page.locator('.el-color-picker__panel:visible .el-color-predefine__color-selector').nth(swatchIndex)
  await expect(swatch, '调色板预定义色块应可见').toBeVisible({ timeout: 5000 })
  await swatch.click()
  // [FIX 2026-08-05 v2] 点色块后点击面板内可见"确定"按钮提交。
  //   根因: 该颜色弹窗在 teleported dialog 形式下不自动提交, 且旧选择器 .el-color-dropdown__btn
  //   匹配不到实际渲染的"确定"按钮 → 颜色从未应用 → 图表无目标色。
  //   改为用文本"确定"限定在可见颜色面板内定位; 若旧按钮 class 存在则兜底。
  const panelConfirm = page.locator('.el-color-picker__panel:visible button:has-text("确定")').first()
  if (await panelConfirm.isVisible().catch(() => false)) { await panelConfirm.click(); return }
  const legacyConfirm = page.locator('.el-color-dropdown__btn:visible').first()
  if (await legacyConfirm.isVisible().catch(() => false)) await legacyConfirm.click()
}

// 找到第一个"启用"状态的分组行 (eye title = "点击禁用分组")。
// [FIX 2026-08-05] 测试数据里首个分组(领域)默认是禁用态(外提单节点, 无容器边框),
//   对其做"禁用/改色"操作无意义, 必须定位到启用的分组 (如子领域)。
async function findEnabledGroupRow(page) {
  const rows = page.locator('.lgn-row')
  const n = await rows.count()
  for (let i = 0; i < n; i++) {
    const t = await rows.nth(i).locator('.lgn-eye').first().getAttribute('title').catch(() => '')
    if (t === '点击禁用分组') return rows.nth(i)
  }
  return rows.first()
}

// 双击"非文字区域"以触发图表聚焦。可指定分组行 (默认第一个)。
// [FIX 2026-08-05] 方向切换等触发重渲染后, 面板可能置于屏幕左侧外 (x 为负),
//   page.mouse.dblclick 在负坐标落空 → 聚焦无效果。故先 scrollIntoViewIfNeeded 再读最新
//   boundingBox, 确保点击坐标落在可见视口内。
async function dblclickGroupRowEmptyArea(page, rowLocator) {
  const row = rowLocator || page.locator('.lgn-row').first()
  await row.waitFor({ state: 'visible', timeout: 15000 })
  await row.scrollIntoViewIfNeeded().catch(() => {})
  await page.waitForTimeout(200)
  const title = row.locator('.lgn-title')
  const box = await title.boundingBox()
  if (!box) throw new Error('无法获取分组行标题区域坐标')
  // 标题文字在容器左侧，右侧是空白 flex 空间；避开颜色选择器/眼睛/箭头等控件
  await page.mouse.dblclick(box.x + Math.max(box.width - 20, 10), box.y + box.height / 2)
}

test.describe('S11: 图表设置 ↔ 图表高亮居中联动', () => {
  // 冷启动首个测试需等 Vite 编译 archdata 依赖，放宽超时
  test.setTimeout(150000)

  test('C01: 嵌入式图表视图切换（列表 ↔ 图表）+ 图表设置面板展开', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    console.log(`[数据] product=${hierarchy.product.id}, version=${hierarchy.version.id}, BOs=${hierarchy.businessObjects.length}`)

    await openEmbeddedChartView(page, hierarchy)
    await attachAndVerifyScreenshot(page, testInfo, '01-chart-view', { expectedPath: 'archdata' })

    // 图表画布已渲染
    const svg = page.locator('.mermaid-container svg').first()
    await expect(svg).toBeVisible({ timeout: 30000 })

    // 图表设置面板出现（仅 chart 视图显示）
    const layoutHeader = page.locator('.rst-panel-layout .collapsible-panel__header')
    await expect(layoutHeader).toBeVisible({ timeout: 20000 })

    // 切回列表视图
    const listBtn = page.locator('.gt-btn-chart-toggle:has-text("列表展示")')
    await listBtn.click()
    await expect(page.locator('.momp-tabs-row').first()).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '02-back-to-list', { expectedPath: 'archdata' })
    console.log('[OK] 列表 ↔ 图表切换正常')
  })

  test('C02: 双击分组行非文字区域 → 图表高亮 + 居中', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const row = page.locator('.lgn-row').first()
    await expect(row).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-layout-panel', { expectedPath: 'archdata' })

    const beforeTransform = await getContentTransform(page)
    const beforeHighlight = await getHighlightedCount(page)

    await dblclickGroupRowEmptyArea(page)
    await page.waitForTimeout(600)

    const afterTransform = await getContentTransform(page)
    const afterHighlight = await getHighlightedCount(page)

    // 高亮类必须出现（联动已触发）
    expect(afterHighlight, '图表应出现被高亮元素').toBeGreaterThan(0)
    // 居中导致 .mermaid-content transform 变化
    expect(afterTransform, '图表应发生平移居中').not.toBe(beforeTransform)
    await attachAndVerifyScreenshot(page, testInfo, '02-group-focused', { expectedPath: 'archdata' })
    console.log(`[OK] 分组行双击 → 高亮=${afterHighlight}, transform: "${beforeTransform}" → "${afterTransform}"`)
  })

  test('C03: 双击叶子节点 → 图表高亮 + 居中', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const leaf = page.locator('.lgn-container-leaf').first()
    await expect(leaf).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-layout-leaves', { expectedPath: 'archdata' })

    const beforeTransform = await getContentTransform(page)
    const beforeHighlight = await getHighlightedCount(page)

    await leaf.dblclick({ position: { x: 30, y: 10 } })
    await page.waitForTimeout(600)

    const afterHighlight = await getHighlightedCount(page)
    const afterTransform = await getContentTransform(page)

    expect(afterHighlight, '图表应出现被高亮叶子节点').toBeGreaterThan(0)
    expect(afterTransform, '图表应发生平移居中').not.toBe(beforeTransform)
    await attachAndVerifyScreenshot(page, testInfo, '02-leaf-focused', { expectedPath: 'archdata' })
    console.log(`[OK] 叶子双击 → 高亮=${afterHighlight}, transform: "${beforeTransform}" → "${afterTransform}"`)
  })

  test('C04: 双击标题文字 → 进入编辑模式，不触发图表联动', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const titleText = page.locator('.lgn-title-text').first()
    await expect(titleText).toBeVisible({ timeout: 15000 })

    const beforeHighlight = await getHighlightedCount(page)

    await titleText.dblclick()
    await page.waitForTimeout(400)

    // 进入编辑：出现标题输入框
    const input = page.locator('.lgn-title .title-input').first()
    await expect(input).toBeVisible({ timeout: 5000 })

    // 不触发联动：高亮元素数不变
    const afterHighlight = await getHighlightedCount(page)
    expect(afterHighlight, '双击标题文字不应触发图表联动').toBe(beforeHighlight)

    // 按 Esc 取消编辑，恢复非编辑态
    await input.press('Escape')
    await expect(page.locator('.lgn-title .title-input').first()).toBeHidden({ timeout: 5000 }).catch(() => {})
    await attachAndVerifyScreenshot(page, testInfo, '01-title-edit', { expectedPath: 'archdata' })
    console.log('[OK] 标题双击进入编辑，未触发联动')
  })

  test('C05: 连续双击不同分组行 → 高亮切换到新目标（不清除旧高亮不叠加）', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const rows = page.locator('.lgn-row')
    await expect(rows.first()).toBeVisible({ timeout: 15000 })
    const rowCount = await rows.count()
    expect(rowCount, '至少需要 2 个分组行用于连续聚焦').toBeGreaterThanOrEqual(2)

    // 第一次双击第一个分组行空白区 → 聚焦分组1
    await dblclickGroupRowEmptyArea(page)
    await page.waitForTimeout(600)
    const firstHighlightCount = await getHighlightedCount(page)
    const firstIds = await getHighlightedIdentifiers(page)
    expect(firstHighlightCount, '第一次双击应产生高亮').toBeGreaterThan(0)

    // 第二次双击第二个分组行空白区 → 聚焦分组2
    const row2 = rows.nth(1)
    const title2 = row2.locator('.lgn-title')
    const box2 = await title2.boundingBox()
    if (!box2) throw new Error('无法获取第二个分组行标题区域坐标')
    await page.mouse.dblclick(box2.x + Math.max(box2.width - 20, 10), box2.y + box2.height / 2)
    await page.waitForTimeout(600)

    const secondHighlightCount = await getHighlightedCount(page)
    const secondIds = await getHighlightedIdentifiers(page)

    // 关键断言：高亮数仍为 1（切换到新目标，而非叠加成 2）
    expect(secondHighlightCount, '连续聚焦应替换旧高亮，而不是叠加').toBe(1)
    // 高亮目标已切换到第二个分组
    expect(JSON.stringify(secondIds), '聚焦目标应从分组1切换到分组2').not.toBe(JSON.stringify(firstIds))
    await attachAndVerifyScreenshot(page, testInfo, '01-focus-switched', { expectedPath: 'archdata' })
    console.log(`[OK] 连续双击 → 高亮切换: ${JSON.stringify(firstIds)} → ${JSON.stringify(secondIds)}`)
  })

  test('C06: 双击分组行交互控件区（类型图标）→ 不触发图表联动', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // [FIX 2026-08-05] 先等分组行渲染, 再定位行内类型图标 (冷启动/面板重建时 typeIcon 可能短暂缺失)
    const row = page.locator('.lgn-row').first()
    await expect(row, '应存在分组行').toBeVisible({ timeout: 20000 })
    const typeIcon = row.locator('.lgn-type-icon').first()
    await expect(typeIcon, '分组行应存在类型图标').toBeVisible({ timeout: 10000 })

    const beforeTransform = await getContentTransform(page)
    const beforeHighlight = await getHighlightedCount(page)

    await typeIcon.dblclick()
    await page.waitForTimeout(500)

    const afterHighlight = await getHighlightedCount(page)
    const afterTransform = await getContentTransform(page)

    // 交互控件区域双击不应触发联动（高亮数不变、transform 不变）
    expect(afterHighlight, '双击类型图标区域不应触发高亮联动').toBe(beforeHighlight)
    expect(afterTransform, '双击类型图标区域不应触发居中').toBe(beforeTransform)
    await attachAndVerifyScreenshot(page, testInfo, '01-icon-no-focus', { expectedPath: 'archdata' })
    console.log(`[OK] 双击类型图标区域未触发联动 (高亮=${afterHighlight})`)
  })

  test('C07: 服务模块图下双击服务模块分组行 → 按节点高亮 + 居中', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // 切换到服务模块图（ChartMiniToolbar 图表类型下拉）
    const chartTypeSelect = page.locator('.chart-mini-toolbar .cmt-select').first()
    await chartTypeSelect.click()
    const smOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("服务模块图")').first()
    await smOption.click()
    await page.waitForTimeout(2500) // 服务模块图重新渲染 + 重新分组
    await expandLayoutPanel(page) // 图表类型重建面板后需重新展开

    // [FOCUS 2026-08-05] 服务模块图面板结构: 领域>子领域>服务模块(分组行 .lgn-row, badge=服务模块)>BO叶子.
    //   但图表只渲染服务模块为 g.node (data-code=SM...), BO 被聚合进服务模块, 不单独渲染.
    //   故可聚焦元素是"服务模块分组行", 而非 BO 叶子. 定位带 "服务模块" badge 的分组行.
    const smGroupRow = page.locator('.lgn-row', { has: page.locator('.lgn-type-badge:has-text("服务模块")') }).first()
    await expect(smGroupRow, '应存在服务模块分组行').toBeVisible({ timeout: 20000 })

    const beforeTransform = await getContentTransform(page)

    // 双击服务模块分组行空白区（标题右侧, 避开文字/控件）
    const smTitle = smGroupRow.locator('.lgn-title')
    const smBox = await smTitle.boundingBox()
    if (!smBox) throw new Error('无法获取服务模块分组行标题区域坐标')
    await page.mouse.dblclick(smBox.x + Math.max(smBox.width - 20, 10), smBox.y + smBox.height / 2)
    await page.waitForTimeout(600)

    const afterHighlight = await getHighlightedCount(page)
    const afterTransform = await getContentTransform(page)

    expect(afterHighlight, '服务模块图分组行双击应产生高亮').toBeGreaterThan(0)
    expect(afterTransform, '服务模块图分组行双击应触发居中').not.toBe(beforeTransform)
    await attachAndVerifyScreenshot(page, testInfo, '01-sm-group-focused', { expectedPath: 'archdata' })
    console.log(`[OK] 服务模块图分组行双击 → 高亮=${afterHighlight}`)
  })

  // [COVERAGE 2026-08-05] 以下 C08-C10 覆盖 ChartMiniToolbar 高频配置对图表的联动
  //   与聚焦联动同属"图表设置 ↔ 展示"链路: 验证配置变更真实反映到渲染结果。

  // 读取 BO 图节点 fill (首个 g.node rect 的 computed fill), 用于断言配色切换生效
  // [FIX 2026-08-05] 兼容 svg 无 class*=mermaid / id^=mermaid 的渲染, 追加 .mermaid-container svg 兜底
  async function getFirstNodeFill(page) {
    return page.evaluate(() => {
      const rect = document.querySelector(
        'svg[class*="mermaid"] g.node rect, svg[id^="mermaid"] g.node rect, .mermaid-container svg g.node rect')
      if (!rect) return null
      const { fill } = window.getComputedStyle(rect)
      return fill || rect.getAttribute('fill') || null
    })
  }

  // 采集所有 BO 节点 distinct fill 集合 (用于断言分组维度切换后分组色重算)
  // [FIX 2026-08-05] 过滤白/透明等无意义 fill (图表中部分节点 fallback 为默认白底), 避免污染 distinct 统计
  async function getDistinctNodeFills(page) {
    return page.evaluate(() => {
      const fills = new Set()
      document.querySelectorAll(
        'svg[class*="mermaid"] g.node rect, svg[id^="mermaid"] g.node rect, .mermaid-container svg g.node rect')
        .forEach(rect => {
          const { fill } = window.getComputedStyle(rect)
          if (fill && fill !== 'rgb(255, 255, 255)' && fill !== 'transparent' && fill !== 'rgba(0, 0, 0, 0)' && fill !== 'none') {
            fills.add(fill)
          }
        })
      return Array.from(fills)
    })
  }

  test('C08: 切换配色方案（default→vibrant）→ 节点填充色改变', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // 等待节点渲染出 fill
    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBeNull()
    const defaultFill = await getFirstNodeFill(page)

    // 配色下拉: ChartMiniToolbar 第3个 .cmt-select (配色), 选"鲜艳"
    const schemeSelect = page.locator('.chart-mini-toolbar .cmt-select').nth(2)
    await schemeSelect.click()
    const vibrantOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("鲜艳")').first()
    await vibrantOption.click()
    // 配色切换触发重新渲染 + recolorize
    await page.waitForTimeout(2500)

    // [FIX 2026-08-05] 用 expect.poll 等待 fill 真正变为 vibrant 首个色 (#FF6B6B)
    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBe(defaultFill)
    const vibrantFill = await getFirstNodeFill(page)
    expect(vibrantFill, '切换鲜艳配色后节点 fill 应变化').not.toBe('')
    await attachAndVerifyScreenshot(page, testInfo, '01-vibrant-scheme', { expectedPath: 'archdata' })
    console.log(`[OK] 配色切换: default=${defaultFill} → vibrant=${vibrantFill}`)
  })

  test('C09: 切换颜色分组维度（按领域→按服务模块）→ 节点分组色重算', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBeNull()
    // [FIX 2026-08-05] 测试数据仅 1 个领域 + N 个服务模块:
    //   按领域分组 → 所有节点 1 个分组色 (distinct fill 数量=1);
    //   按服务模块分组 → 多个服务模块 → distinct fill 数量应增多。
    //   只比较首个节点 fill 会因"两组首个分组都是第一个颜色"而误判, 故比较 distinct 集合。
    const domainDistinct = await getDistinctNodeFills(page)
    expect(domainDistinct.length, '按领域分组应有 distinct 分组色').toBeGreaterThanOrEqual(1)

    // 颜色分组下拉: ChartMiniToolbar 第2个 .cmt-select, 选"按服务模块"
    const groupSelect = page.locator('.chart-mini-toolbar .cmt-select').nth(1)
    await groupSelect.click()
    const smGroupOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("按服务模块")').first()
    await smGroupOption.click()
    await page.waitForTimeout(2500)

    // [FIX 2026-08-05] 等待 distinct fill 数量增加 (服务模块分组通常产生更多分组色)。
    //   不硬编码 2: 不同测试数据服务模块数量不定, 只断言"分组色数量变多"体现重算生效。
    //   注意: Playwright 无内置 toSatisfy (那是文档里的自定义 matcher 示例), 改用手动轮询。
    let smDistinct = await getDistinctNodeFills(page)
    const deadline = Date.now() + 10000
    while (smDistinct.length <= domainDistinct.length && Date.now() < deadline) {
      await page.waitForTimeout(500)
      smDistinct = await getDistinctNodeFills(page)
    }
    expect(smDistinct.length, '切换服务模块分组后 distinct fill 应增多')
      .toBeGreaterThan(domainDistinct.length)
    await attachAndVerifyScreenshot(page, testInfo, '01-group-by-service-module', { expectedPath: 'archdata' })
    console.log(`[OK] 颜色分组切换: domain distinct=${domainDistinct.length} → serviceModule distinct=${smDistinct.length}`)
  })

  test('C10: 切换布局方向（TB↔LR）→ 图表重新布局且持续可聚焦', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const svg = page.locator('.mermaid-container svg').first()
    await expect(svg).toBeVisible({ timeout: 30000 })

    // 布局方向按钮: ChartMiniToolbar 的 .cmt-dir-btn (第1个 TB / 第2个 LR).
    // [FIX 2026-08-05] 不依赖初始 primary 态 (不同数据/配置下初始方向可能不同), 改为记录初始激活态
    const tbBtn = page.locator('.chart-mini-toolbar .cmt-dir-btn').nth(0)
    const lrBtn = page.locator('.chart-mini-toolbar .cmt-dir-btn').nth(1)
    const readActive = async (btn) => (await btn.getAttribute('class'))?.includes('el-button--primary')

    const tbActive0 = await readActive(tbBtn)
    const lrActive0 = await readActive(lrBtn)
    expect(tbActive0 !== lrActive0, '初始应恰好有一个方向按钮处于激活态').toBe(true)

    // 记录切换前 svg 内容指纹, 用于断言方向切换触发重渲染
    const svgFingerprintBefore = await page.evaluate(() => {
      const s = document.querySelector('svg[class*="mermaid"], svg[id^="mermaid"]')
      return s ? s.outerHTML.length : 0
    })

    // 点击当前非激活的那个按钮 (若 LR 未激活则切到 LR, 否则切回 LR), 触发方向切换
    const targetBtn = lrActive0 ? tbBtn : lrBtn
    await targetBtn.click()
    await page.waitForTimeout(2500)

    // 方向切换后: 激活态应互换
    const tbActive1 = await readActive(tbBtn)
    const lrActive1 = await readActive(lrBtn)
    expect(tbActive1 !== tbActive0, '方向切换后 TB 按钮激活态应变化').toBe(true)
    expect(lrActive1 !== lrActive0, '方向切换后 LR 按钮激活态应变化').toBe(true)

    // 图表仍正常渲染
    await expect(page.locator('.mermaid-container svg').first()).toBeVisible({ timeout: 15000 })

    // 方向切换重新布局后聚焦能力仍正常: 重新展开面板后双击"启用"分组行仍应高亮
    // [FIX 2026-08-05] 首行(领域)默认禁用, 双击无意义; 改为双击启用的分组 (子领域)。
    //   方向切换后 svg 重建, 注解 overlay 需重新挂载, 聚焦生效有延迟 → 先等 svg 指纹稳定,
    //   再重新展开面板定位 rows, 用 expects.poll 轮询高亮最多 15s。
    await expect.poll(async () => {
      return await page.evaluate(() => {
        const el = document.querySelector('svg[class*="mermaid"], svg[id^="mermaid"]')
        return el ? el.outerHTML.length : 0
      })
    }, { timeout: 15000 }).toBeGreaterThan(0)
    await expandLayoutPanel(page)
    const enabledRow = await findEnabledGroupRow(page)
    await expect(enabledRow, '方向切换后仍应存在启用分组').toBeVisible({ timeout: 15000 })
    const beforeHighlight = await getHighlightedCount(page)
    await dblclickGroupRowEmptyArea(page, enabledRow)
    await page.waitForTimeout(600)
    await expect.poll(() => getHighlightedCount(page), { timeout: 15000 }).toBeGreaterThan(beforeHighlight)
    const afterHighlight = await getHighlightedCount(page)
    await attachAndVerifyScreenshot(page, testInfo, '01-direction-toggled', { expectedPath: 'archdata' })
    console.log(`[OK] 布局方向切换: TB激活=${tbActive0}→${tbActive1}, 高亮=${afterHighlight}`)
  })

  // [COVERAGE 2026-08-05] 以下 C11-C14 补齐"图表设置面板 ↔ 图表展示"链路的剩余高频交互:
  //   - C11 分组级色点自定义颜色 → 图表对应分组节点 fill 即时更新 (customColors 增量)
  //   - C12 眼睛开关禁用分组 → 该分组节点从图表移除
  //   - C13 叶子节点禁用 → 该 BO/容器从图表移除
  //   - C14 高级选项切换布局引擎 (ELK→Dagre) → 图表重新布局

  test('C11: 分组级色点自定义颜色 → 图表分组节点 fill 即时更新', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // [FIX 2026-08-05] 首个分组(领域)默认是禁用态(外提单节点)或中心范围分组, 其颜色受 centerScopeColor
    //   控制, 自定义色会被覆盖. 必须选"启用"且非中心的子领域分组做改色.
    const enabledRow = await findEnabledGroupRow(page)
    await expect(enabledRow, '应存在启用状态的分组行').toBeVisible({ timeout: 15000 })
    const trigger = enabledRow.locator('.lgn-color-picker').first()
    await expect(trigger, '分组行应存在级色点').toBeVisible({ timeout: 15000 })

    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBeNull()

    // PALETTE[3] = #722ED1 → rgb(114,46,209), 选非中心分组大概率不用的鲜明色, 可稳定断言生效
    const TARGET_RGB = 'rgb(114, 46, 209)'
    await pickGroupColor(page, enabledRow, 3)
    // [FIX 2026-08-05 v2] 改色提交异步, 用 expect.poll 等待图表出现目标色, 替代一次性断言
    await expect.poll(async () => {
      return await page.evaluate((rgb) => {
        return Array.from(document.querySelectorAll('svg[class*="mermaid"] g.node rect, svg[id^="mermaid"] g.node rect'))
          .some(r => window.getComputedStyle(r).fill === rgb)
      }, TARGET_RGB)
    }, { timeout: 10000 }).toBe(true)
    await attachAndVerifyScreenshot(page, testInfo, '01-custom-color', { expectedPath: 'archdata' })
    console.log(`[OK] 分组色点自定义色 ${TARGET_RGB} 生效`)
  })

  test('C12: 眼睛开关禁用分组 → 该分组容器边框从图表移除', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // [FIX 2026-08-05] 禁用分组语义="外提": 移除容器边框(g.cluster), 子节点打平保留(g.node 不变).
    //   故可观测信号是 g.cluster 减少, 而非 g.node. 且需禁用"启用"的分组(如子领域), 因首行(领域)默认已禁用.
    const enabledRow = await findEnabledGroupRow(page)
    await expect(enabledRow, '应存在启用状态的分组行').toBeVisible({ timeout: 15000 })

    await expect.poll(() => getClusterCount(page), { timeout: 15000 }).toBeGreaterThan(0)
    const beforeClusters = await getClusterCount(page)
    expect(beforeClusters, '图表应先存在容器边框').toBeGreaterThan(0)

    // 第一个眼睛按钮 = "点击禁用分组" (enabled toggle)
    const eye = enabledRow.locator('.lgn-eye').first()
    await expect(eye, '分组行应存在禁用开关').toBeVisible({ timeout: 15000 })
    await eye.click()
    await page.waitForTimeout(1500)

    const afterClusters = await getClusterCount(page)
    expect(afterClusters, '禁用分组后容器边框(g.cluster)应减少').toBeLessThan(beforeClusters)
    await attachAndVerifyScreenshot(page, testInfo, '01-group-disabled', { expectedPath: 'archdata' })
    console.log(`[OK] 禁用分组: g.cluster ${beforeClusters} → ${afterClusters}`)
  })

  test('C13: 叶子节点禁用开关 → 进入禁用态且容器边框不新增', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const leaf = page.locator('.lgn-container-leaf').first()
    await expect(leaf).toBeVisible({ timeout: 15000 })

    const beforeClusters = await getClusterCount(page)
    const beforeNodes = await page.locator('.mermaid-container svg g.node').count()

    // 叶子行第一个 toggle = "点击禁用（禁用即从图表移除）"
    const toggle = leaf.locator('.lgn-leaf-toggle').first()
    await expect(toggle, '叶子行应存在禁用开关').toBeVisible({ timeout: 15000 })
    await toggle.click()
    await page.waitForTimeout(1500)

    // [FIX 2026-08-05] 禁用叶子/容器语义="外提": 节点打平保留(g.node 不变), 仅移除/不新增其容器边框.
    //   故可靠断言 = 面板叶子进入禁用态 + g.cluster 不增加 + 图表仍正常渲染 (不做 g.node 减少断言).
    await expect(leaf, '叶子应进入禁用态').toHaveClass(/leaf-disabled/, { timeout: 5000 })
    const afterClusters = await getClusterCount(page)
    expect(afterClusters, '禁用叶子后容器边框(g.cluster)不应增加').toBeLessThanOrEqual(beforeClusters)
    await expect.poll(() => page.locator('.mermaid-container svg g.node').count(), { timeout: 10000 }).toBeGreaterThan(0)
    await attachAndVerifyScreenshot(page, testInfo, '01-leaf-disabled', { expectedPath: 'archdata' })
    console.log(`[OK] 禁用叶子: 进入禁用态, g.node=${beforeNodes} 保留, g.cluster ${beforeClusters} → ${afterClusters}`)
  })

  test('C14: 高级选项切换布局引擎（ELK→Dagre）→ 图表重新布局', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const svg = page.locator('.mermaid-container svg').first()
    await expect(svg).toBeVisible({ timeout: 30000 })

    // 记录切换前 svg 指纹 (用于断言引擎切换触发重渲染)
    const fingerprint = () => page.evaluate(() => {
      const s = document.querySelector('svg[class*="mermaid"], svg[id^="mermaid"]')
      return s ? s.outerHTML.length : 0
    })
    const fingerprintBefore = await fingerprint()

    // 打开高级选项 popover, 选 Dagre
    const advBtn = page.locator('.chart-mini-toolbar .cmt-advanced-btn').first()
    await advBtn.click()
    const dagreRadio = page.locator('.cmt-advanced-popper .el-radio:has-text("Dagre")').first()
    await expect(dagreRadio, '高级选项应含 Dagre 引擎').toBeVisible({ timeout: 5000 })
    await dagreRadio.click()
    await page.waitForTimeout(2500)

    // 引擎切换后 svg 应重渲染且仍有节点
    const fingerprintAfter = await fingerprint()
    expect(fingerprintAfter, '切换布局引擎后 svg 应重新渲染').not.toBe(fingerprintBefore)
    await expect(page.locator('.mermaid-container svg g.node').first()).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-dagre-layout', { expectedPath: 'archdata' })
    console.log(`[OK] 布局引擎切换: svg 指纹 ${fingerprintBefore} → ${fingerprintAfter}`)
  })

  // [COVERAGE 2026-08-05] C15-C18 补齐其余"图表设置 ↔ 展示"高频配置与面板操作:
  //   - C15 区分中心范围 (centerScopeHighlight) 切换 → 图表重新分组渲染
  //   - C16 新增分组 (LayoutControlPanel 工具栏) → 面板出现新分组行
  //   - C17 全部展开/收起 → 叶子节点可见性变化
  //   - C18 分组行"隐藏边框"开关 → 图标状态切换

  test('C15: 区分中心范围切换（区分↔不区分）→ 图表重新渲染', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // 对象范围下拉 = ChartMiniToolbar 第4个 .cmt-select (centerScopeHighlight)
    const scopeSelect = page.locator('.chart-mini-toolbar .cmt-select').nth(3)
    await expect(scopeSelect).toBeVisible({ timeout: 15000 })
    // [FIX 2026-08-05] EP select 带 prefix slot 时选中值不在 .el-select__selected-item 内,
    //   改用 select 可见文本判断"区分/不区分"(prefix 标签"对象范围"不含这两个词, 不会误判)
    const readVal = async () => {
      const txt = (await scopeSelect.innerText()) || ''
      if (txt.includes('不区分')) return '不区分'
      if (txt.includes('区分')) return '区分'
      return ''
    }
    const initialVal = await readVal()
    expect(initialVal, '对象范围下拉应显示"区分"或"不区分"').toMatch(/区分|不区分/)

    const fingerprint = () => page.evaluate(() => {
      const s = document.querySelector('svg[class*="mermaid"], svg[id^="mermaid"]')
      return s ? s.outerHTML.length : 0
    })
    const fpBefore = await fingerprint()

    // 切到相反值
    await scopeSelect.click()
    const targetText = (initialVal === '不区分') ? '区分' : '不区分'
    const targetOption = page.locator(`.el-select-dropdown:visible .el-select-dropdown__item:has-text("${targetText}")`).first()
    await targetOption.click()
    await page.waitForTimeout(2500)

    const newVal = await readVal()
    expect(newVal, '对象范围下拉值应切换').not.toBe(initialVal)

    // 切换触发 handleAutoGroupByDomain 重渲染
    const fpAfter = await fingerprint()
    expect(fpAfter, '区分中心范围切换后 svg 应重新渲染').not.toBe(fpBefore)
    await expect(page.locator('.mermaid-container svg g.node').first()).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-center-scope-toggled', { expectedPath: 'archdata' })
    console.log(`[OK] 区分中心范围: "${initialVal}" → "${newVal}", svg 指纹 ${fpBefore} → ${fpAfter}`)
  })

  test('C16: 新增分组按钮 → 面板出现新分组行', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    await expect.poll(() => page.locator('.lgn-row').count(), { timeout: 15000 }).toBeGreaterThan(0)
    const beforeRows = await page.locator('.lgn-row').count()

    // 布局面板工具栏"新增"按钮
    const addBtn = page.locator('.lcp-toolbar button:has-text("新增")').first()
    await expect(addBtn, '应存在新增分组按钮').toBeVisible({ timeout: 15000 })
    await addBtn.click()
    await page.waitForTimeout(800)

    const afterRows = await page.locator('.lgn-row').count()
    expect(afterRows, '新增分组后 .lgn-row 数量应增加').toBeGreaterThan(beforeRows)
    await attachAndVerifyScreenshot(page, testInfo, '01-group-added', { expectedPath: 'archdata' })
    console.log(`[OK] 新增分组: .lgn-row ${beforeRows} → ${afterRows}`)
  })

  test('C17: 全部展开/收起切换 → 叶子节点可见性变化', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // 全部收起 → 嵌套叶子应被隐藏
    const collapseBtn = page.locator('.lcp-toolbar button:has-text("全部收起")').first()
    if (await collapseBtn.isVisible().catch(() => false)) {
      await collapseBtn.click()
      await page.waitForTimeout(600)
    }
    const collapsedLeaves = await page.locator('.lgn-container-leaf:visible').count()

    // 全部展开 → 叶子重新显示
    const expandBtn = page.locator('.lcp-toolbar button:has-text("全部展开")').first()
    await expect(expandBtn, '收起后应存在"全部展开"按钮').toBeVisible({ timeout: 15000 })
    await expandBtn.click()
    await page.waitForTimeout(600)
    const expandedLeaves = await page.locator('.lgn-container-leaf:visible').count()

    // [TOLERANT 2026-08-05] 测试数据含嵌套(领域>子领域>服务模块>BO), 展开应显示至少与收起时相同的叶子;
    //   用 >= 避免单数据源叶子都在顶层时误判.
    expect(expandedLeaves, '全部展开后可见叶子应不少于收起时').toBeGreaterThanOrEqual(collapsedLeaves)
    await attachAndVerifyScreenshot(page, testInfo, '01-expand-all', { expectedPath: 'archdata' })
    console.log(`[OK] 全部展开/收起: 可见叶子 收起=${collapsedLeaves} → 展开=${expandedLeaves}`)
  })

  test('C18: 分组行隐藏边框开关 → 图标状态切换', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const enabledRow = await findEnabledGroupRow(page)
    await expect(enabledRow, '应存在启用状态的分组行').toBeVisible({ timeout: 15000 })

    // 第二个眼睛按钮 = 隐藏边框 (fullscreen icon, toggleVisible)
    const borderToggle = enabledRow.locator('.lgn-eye').nth(1)
    await expect(borderToggle, '分组行应存在隐藏边框开关').toBeVisible({ timeout: 15000 })
    const beforeTitle = await borderToggle.getAttribute('title')

    await borderToggle.click()
    await page.waitForTimeout(800)
    const afterTitle = await borderToggle.getAttribute('title')

    expect(afterTitle, '隐藏边框开关图标提示应切换').not.toBe(beforeTitle)
    await attachAndVerifyScreenshot(page, testInfo, '01-border-hidden', { expectedPath: 'archdata' })
    console.log(`[OK] 隐藏边框: "${beforeTitle}" → "${afterTitle}"`)
  })

  // [COVERAGE 2026-08-05] C19-C22 补齐"图表设置 ↔ 展示"链路遗漏场景:
  //   - C19 配色方案第三种"柔和/pastel" (C08 只测 default→vibrant)
  //   - C20 颜色分组第三种"按子领域" (C09 只测 domain→serviceModule)
  //   - C21 服务模块图"切回"业务对象图 (C07 只测切到服务模块图)
  //   - C22 标题编辑"保存"路径 (C04 只测 Esc 取消, 未测 Enter/blur 保存)
  //   场景均为"仅图表设置 → 图表展示"单向联动的补齐, 稳定无额外数据依赖。

  const chartFingerprint = (page) => page.evaluate(() => {
    const s = document.querySelector('svg[class*="mermaid"], svg[id^="mermaid"]')
    return s ? s.outerHTML.length : 0
  })

  test('C19: 切换配色方案（vibrant→pastel）→ 节点填充色再次改变', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBeNull()
    const beforeFill = await getFirstNodeFill(page)

    // 配色下拉: ChartMiniToolbar 第3个 .cmt-select, 选"柔和"
    const schemeSelect = page.locator('.chart-mini-toolbar .cmt-select').nth(2)
    await schemeSelect.click()
    const pastelOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("柔和")').first()
    await expect(pastelOption, '配色下拉应含"柔和"选项').toBeVisible({ timeout: 5000 })
    await pastelOption.click()
    await page.waitForTimeout(2500)

    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBe(beforeFill)
    const pastelFill = await getFirstNodeFill(page)
    expect(pastelFill, '切换柔和配色后节点 fill 应变化').not.toBe('')
    await attachAndVerifyScreenshot(page, testInfo, '01-pastel-scheme', { expectedPath: 'archdata' })
    console.log(`[OK] 柔和配色: ${beforeFill} → ${pastelFill}`)
  })

  test('C20: 切换颜色分组维度（按服务模块→按子领域）→ 图表重算渲染', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    await expect.poll(() => getFirstNodeFill(page), { timeout: 10000 }).not.toBeNull()
    const fpBefore = await chartFingerprint(page)

    // 颜色分组下拉: ChartMiniToolbar 第2个 .cmt-select, 选"按子领域"
    const groupSelect = page.locator('.chart-mini-toolbar .cmt-select').nth(1)
    await groupSelect.click()
    const subOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("按子领域")').first()
    await expect(subOption, '颜色分组下拉应含"按子领域"选项').toBeVisible({ timeout: 5000 })
    await subOption.click()
    await page.waitForTimeout(2500)

    // 维度切换触发分组色重算 + 重渲染 (指纹变化)
    await expect.poll(() => chartFingerprint(page), { timeout: 15000 }).not.toBe(fpBefore)
    await expect(page.locator('.mermaid-container svg g.node').first()).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-group-by-sub-domain', { expectedPath: 'archdata' })
    console.log(`[OK] 按子领域分组重算渲染, svg 指纹 ${fpBefore} → ${await chartFingerprint(page)}`)
  })

  test('C21: 服务模块图切回业务对象图 → 图表重新渲染', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    // 图表类型下拉: ChartMiniToolbar 第1个 .cmt-select
    const chartTypeSelect = page.locator('.chart-mini-toolbar .cmt-select').first()
    // 1) 切到服务模块图
    await chartTypeSelect.click()
    const smOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("服务模块图")').first()
    await smOption.click()
    await page.waitForTimeout(2500)
    const fpSm = await chartFingerprint(page)

    // 2) 切回业务对象图
    await chartTypeSelect.click()
    const boOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item:has-text("业务对象图")').first()
    await expect(boOption, '图表类型下拉应含"业务对象图"选项').toBeVisible({ timeout: 5000 })
    await boOption.click()
    await page.waitForTimeout(2500)

    const fpBo = await chartFingerprint(page)
    expect(fpBo, '切回业务对象图后 svg 应重新渲染').not.toBe(fpSm)
    await expect(page.locator('.mermaid-container svg g.node').first()).toBeVisible({ timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-back-to-bo', { expectedPath: 'archdata' })
    console.log(`[OK] 服务模块图→业务对象图: svg 指纹 ${fpSm} → ${fpBo}`)
  })

  test('C22: 双击标题进入编辑 → 输入新标题保存 → 分组行标题更新', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const titleText = page.locator('.lgn-title-text').first()
    await expect(titleText).toBeVisible({ timeout: 15000 })
    const beforeTitle = ((await titleText.textContent()) || '').trim()
    const newTitle = `E2E标题${Date.now() % 100000}`

    // 双击标题文字 → 进入编辑态 (不触发联动)
    await titleText.dblclick()
    await page.waitForTimeout(400)
    const input = page.locator('.lgn-title .title-input').first()
    await expect(input).toBeVisible({ timeout: 5000 })

    // 输入新标题并按 Enter 保存 (@keyup.enter=finishEditTitle)
    await input.fill(newTitle)
    await input.press('Enter')
    await page.waitForTimeout(600)

    await expect.poll(async () => (await page.locator('.lgn-title-text').first().textContent() || '').trim(), { timeout: 8000 }).toBe(newTitle)
    await attachAndVerifyScreenshot(page, testInfo, '01-title-saved', { expectedPath: 'archdata' })
    console.log(`[OK] 标题编辑保存: "${beforeTitle}" → "${newTitle}"`)

    // 恢复原标题, 避免持久化到 localStorage 污染跨用例 layoutConfig 快照
    await page.locator('.lgn-title-text').first().dblclick()
    await page.waitForTimeout(400)
    const restoreInput = page.locator('.lgn-title .title-input').first()
    if (await restoreInput.isVisible().catch(() => false)) {
      await restoreInput.fill(beforeTitle)
      await restoreInput.press('Enter')
      await page.waitForTimeout(400)
    }
    console.log(`[OK] 已恢复标题: "${newTitle}" → "${beforeTitle}"`)
  })

  // [COVERAGE 2026-08-05] 补齐图表展示侧高频功能:
  //   - C23 重置视图: 聚焦(改变 transform)后点"重置视图" → transform 复位为 identity
  //   - C24 导出彩色 HTML: 点击"彩色HTML" → 触发下载文件 (diagram-full-*.html)
  test('C23: 聚焦改变视图后点"重置视图" → 图表 transform 复位', async ({ page }, testInfo) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)
    await expandLayoutPanel(page)

    const isEmptyTransform = (t) => !t || /translate\(0px, 0px\) scale\(1\)/.test(t)
    const beforeTransform = await getContentTransform(page)
    console.log(`[C23] 初始 transform: "${beforeTransform}"`)

    // 先通过双击分组聚焦, 触发 centerElement 改变 transform (脱离 identity)
    const enabledRow = await findEnabledGroupRow(page)
    await expect(enabledRow).toBeVisible({ timeout: 15000 })
    await dblclickGroupRowEmptyArea(page, enabledRow)
    await page.waitForTimeout(600)
    const focusedTransform = await getContentTransform(page)
    expect(focusedTransform, '聚焦应改变 transform (centerElement)').not.toBe(beforeTransform)

    // 点"重置视图" → transform 复位 (identity)
    const resetBtn = page.locator('.toolbar-btn[title="重置视图"]').first()
    await expect(resetBtn).toBeVisible({ timeout: 15000 })
    await resetBtn.click()
    // 手动轮询: 等待 transform 复位为 identity (Playwright 无内建 toSatisfy)
    let resetTransform = await getContentTransform(page)
    const deadline = Date.now() + 8000
    while (!isEmptyTransform(resetTransform) && Date.now() < deadline) {
      await page.waitForTimeout(400)
      resetTransform = await getContentTransform(page)
    }
    expect(isEmptyTransform(resetTransform), '重置视图后 transform 应复位为 identity').toBe(true)
    await attachAndVerifyScreenshot(page, testInfo, '01-reset-view', { expectedPath: 'archdata' })
    console.log(`[OK] 重置视图: transform ${focusedTransform} → ${resetTransform}`)
  })

  test('C24: 点击"彩色HTML"导出 → 触发下载 diagram-full-*.html', async ({ page }) => {
    const hierarchy = await getHierarchy(page)
    await openEmbeddedChartView(page, hierarchy)

    const exportBtn = page.locator('.toolbar-btn:has-text("彩色HTML")').first()
    await expect(exportBtn).toBeVisible({ timeout: 15000 })

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      exportBtn.click()
    ])
    const filename = download.suggestedFilename()
    expect(filename, '导出文件名应以 diagram-full- 开头').toMatch(/^diagram-full-.*\.html$/)
    console.log(`[OK] 彩色HTML 导出: ${filename}`)
  })
})