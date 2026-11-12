/**
 * 响应式 E2E 定位助手
 *
 * 背景: MetaListPage 在窄屏 (<= 768px, 与 src/composables/useBreakpoints.js 一致)
 * 用卡片列表 `.meta-card-list > article.meta-card` 替代 `.el-table`；
 * MultiObjectManagementPage 的左侧范围树在窄屏默认折叠。
 *
 * 用例应通过本助手定位"列表"，而不是写死 .el-table，才能同时跑桌面 / 手机两套 project。
 */

const MOBILE_MAX_WIDTH = 768

/** 当前是否窄屏（按视口宽度判断，与 useBreakpoints 的 isMobile 一致） */
export function isMobileViewport(page) {
  const size = page.viewportSize()
  return !!size && size.width <= MOBILE_MAX_WIDTH
}

/** 列表行定位器：手机端卡片 / 桌面端表格行，二者互斥 */
export function listRows(page) {
  if (isMobileViewport(page)) return page.locator('.meta-card:visible')
  return page.locator('.el-table__body tr:visible')
}

/** 列表容器定位器：手机端卡片列表 / 桌面端表格体（避开详情页其它子表） */
export function listContainer(page) {
  if (isMobileViewport(page)) return page.locator('.meta-card-list:visible').first()
  return page.locator('.el-table__body:visible').first()
}

/** 列表整体文本（用于 contains 断言，兼容卡片/表格） */
export async function listText(page) {
  const container = listContainer(page)
  await container.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
  return (await container.textContent().catch(() => '')) || ''
}

/** 等列表出现（卡片或表格）。详情页可能同时存在隐藏子表，只等"可见"的那个 */
export async function waitForList(page, timeout = 10000) {
  const target = isMobileViewport(page)
    ? page.locator('.meta-card-list:visible')
    : page.locator('.el-table:visible')
  await target.first().waitFor({ state: 'visible', timeout })
}

/**
 * 窄屏下展开左侧范围树（桌面端已展开则不动）。
 * 依赖 MasterDetailLayout 的折叠按钮 `.master-detail-layout__collapse-btn`。
 */
export async function expandScopeSidebar(page) {
  const layout = page.locator('.master-detail-layout').first()
  if (!(await layout.count())) return false
  const collapsed = await layout.evaluate(el => el.classList.contains('master-detail-layout--collapsed'))
  if (!collapsed) return true
  const btn = page.locator('.master-detail-layout__collapse-btn').first()
  await btn.click({ timeout: 5000 })
  await page.waitForTimeout(300)
  return true
}

/** 卡片模式下列标题文本（卡片没有表头，用标签名断言） */
export function cardLabels(page) {
  return page.locator('.meta-card__label:visible')
}
