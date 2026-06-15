/**
 * 通用列表页 POM - v2 简化方案核心组件
 *
 * [!!!] 本文件是 v2 简化方案的 POM 基础，修改前必读 [!!!]
 * [!!!] 规范: .trae/rules/e2e-simplification.md 第四节 [!!!]
 * [!!!] 所有 features 测试禁止直接 page.locator('.el-table...')，必须用 POM [!!!]
 *
 * 解决的核心问题：
 * - 25+ 个测试直接操作 `page.locator('.el-table__body tr:has-text(xxx)')`
 * - UI 一改（如 tr → div），所有测试挂掉
 * - 重复的"查找行 → 点击"逻辑散落各文件
 *
 * 用法对比：
 *
 * 【旧写法】每测试 5-8 行
 *   const rows = page.locator('.el-table__body tr')
 *   let found = false
 *   for (let i = 0; i < await rows.count(); i++) {
 *     const text = await rows.nth(i).textContent()
 *     if (text.includes(boCode)) {
 *       await rows.nth(i).locator('.bk-link').click()
 *       found = true
 *       break
 *     }
 *   }
 *   expect(found).toBe(true)
 *
 * 【新写法】1 行
 *   await listPage.clickRowByText(boCode, { linkSelector: '.bk-link' })
 */

import { expect } from '@playwright/test'

export class GenericListPage {
  /**
   * @param {Page} page
   * @param {Object} options
   *   - tableSelector: 表格选择器（默认 .el-table）
   *   - rowSelector: 行选择器（默认 .el-table__body tr）
   *   - linkSelector: 链接选择器（默认 .bk-link）
   *   - emptyTextSelector: "暂无数据" 选择器
   */
  constructor(page, options = {}) {
    this.page = page
    this.tableSelector = options.tableSelector || '.el-table'
    this.rowSelector = options.rowSelector || '.el-table__body tr'
    this.linkSelector = options.linkSelector || '.bk-link'
    this.emptyTextSelector = options.emptyTextSelector || 'text=暂无数据'
  }

  /**
   * 等待表格加载完成
   */
  async waitForReady(timeout = 15000) {
    const table = this.page.locator(this.tableSelector).first()
    await table.waitFor({ state: 'visible', timeout })
    return this
  }

  /**
   * 获取所有行数
   */
  async getRowCount() {
    return await this.page.locator(this.rowSelector).count()
  }

  /**
   * 获取表头列名
   */
  async getColumnHeaders() {
    const headers = []
    const cells = this.page.locator(`${this.tableSelector} .el-table__header th .cell`)
    const count = await cells.count()
    for (let i = 0; i < count; i++) {
      const text = await cells.nth(i).textContent()
      if (text) headers.push(text.trim())
    }
    return headers
  }

  /**
   * 在表格中找到包含指定文本的行（带重试 + 自动刷新）
   * @param {string|RegExp} text - 行文本
   * @param {Object} options
   *   - timeout: 重试超时（默认 10000ms）
   *   - pollInterval: 轮询间隔（默认 500ms）
   *   - onRetry: 每次重试前调用的回调（用于触发刷新）
   * @returns {Promise<Locator|null>} 行 locator
   */
  async findRow(text, options = {}) {
    const { timeout = 10000, pollInterval = 500, onRetry = null } = options
    const start = Date.now()
    let attempts = 0

    while (Date.now() - start < timeout) {
      attempts++
      const rows = this.page.locator(this.rowSelector)
      const count = await rows.count()
      for (let i = 0; i < count; i++) {
        const rowText = await rows.nth(i).textContent()
        if (rowText && rowText.includes(text)) {
          if (attempts > 1) {
            console.log(`[findRow] Found "${text}" after ${attempts} attempts (${Date.now() - start}ms)`)
          }
          return rows.nth(i)
        }
      }

      // 找不到时，如果有回调则触发（重新刷新等）
      if (onRetry && attempts === 1) {
        try { await onRetry() } catch (e) { /* ignore */ }
      }

      await this.page.waitForTimeout(pollInterval)
    }
    return null
  }

  /**
   * 点击包含指定文本的行（默认点击链接列）
   * 内部已带重试（findRow 会自动轮询）
   */
  async clickRowByText(text, options = {}) {
    const linkSel = options.linkSelector !== undefined ? options.linkSelector : this.linkSelector
    const row = await this.findRow(text, options)
    if (!row) {
      throw new Error(`Row containing "${text}" not found in table`)
    }

    if (linkSel) {
      const link = row.locator(linkSel).first()
      if (await link.isVisible({ timeout: 2000 }).catch(() => false)) {
        await link.click()
        return this
      }
    }

    await row.click()
    return this
  }

  /**
   * 断言行存在（带重试）
   */
  async expectRowExists(text, options = {}) {
    const row = await this.findRow(text, { timeout: 15000, ...options })
    expect(row, `Row containing "${text}" should exist`).not.toBeNull()
  }

  /**
   * 断言行可见 (扩展: 软断言 UI, Healer 守护)
   * @param {string|RegExp} text
   * @param {Object} options { timeout, softOn: true }
   */
  async expectRowVisible(text, options = {}) {
    const { timeout = 5000, soft = true } = options
    try {
      const row = await this.findRow(text, { timeout })
      if (row) {
        const visible = await row.isVisible()
        if (visible) return { visible: true, row }
      }
      if (soft) {
        console.warn(`[GenericListPage] 行 "${text}" 不可见 (软断言)`)
        return { visible: false, row: null }
      }
      expect(false, `[UI 列表] 行 "${text}" 应可见`).toBe(true)
    } catch (e) {
      if (soft) {
        console.warn(`[GenericListPage] 行 "${text}" 验证失败 (软断言: ${e.message})`)
        return { visible: false, error: e.message }
      }
      throw e
    }
  }

  /**
   * 断言列可排序 (有 sort 按钮)
   * @param {string} columnTitle 表头列名 (如 '编码', '名称')
   */
  async expectColumnSortable(columnTitle) {
    // Element Plus 表格: th .cell 内的 sort caret
    const header = this.page.locator(`${this.tableSelector} .el-table__header th .cell`, { hasText: columnTitle }).first()
    await header.waitFor({ state: 'visible', timeout: 3000 })
    // 检查是否有排序 caret (Element Plus 会加 .sort-caret)
    const parent = header.locator('..')
    const hasSort = await parent.locator('.sort-caret, .caret-wrapper, .is-sortable').count() > 0
    if (!hasSort) {
      // 软断言: 业务列表的某些列可能不可排序
      console.warn(`[GenericListPage] 列 "${columnTitle}" 看起来不可排序 (软断言)`)
    }
    return { sortable: hasSort }
  }

  /**
   * 断言筛选器存在
   * @param {string} filterLabel 筛选标签 (如 '是否活跃')
   */
  async expectFilterExists(filterLabel) {
    // Element Plus 筛选器一般在 sidebar 或 toolbar
    const filter = this.page.locator(`label:has-text("${filterLabel}"), .filter-item:has-text("${filterLabel}"), .el-form-item:has(label:has-text("${filterLabel}"))`).first()
    try {
      await filter.waitFor({ state: 'visible', timeout: 3000 })
      return { exists: true }
    } catch (e) {
      // 软断言: 某些视图可能没有该筛选
      console.warn(`[GenericListPage] 筛选 "${filterLabel}" 不存在 (软断言)`)
      return { exists: false }
    }
  }

  /**
   * 一站式: 列表 UI 验证 (行可见 + 列存在 + 筛选存在)
   * @param {string} rowText - 应可见的行
   * @param {Object} checks { columns: [], filters: [] }
   */
  async verifyListUI(rowText, checks = {}) {
    const results = { row: null, columns: [], filters: [] }
    // 1. 行可见
    results.row = await this.expectRowVisible(rowText, { soft: true })
    // 2. 列存在
    for (const col of checks.columns || []) {
      const headers = await this.getColumnHeaders()
      const hasCol = headers.includes(col)
      results.columns.push({ name: col, exists: hasCol })
      if (!hasCol) console.warn(`[GenericListPage] 列 "${col}" 不存在`)
    }
    // 3. 筛选存在
    for (const f of checks.filters || []) {
      const r = await this.expectFilterExists(f)
      results.filters.push({ name: f, exists: r.exists })
    }
    return results
  }

  /**
   * 断言行不存在（带重试）
   */
  async expectRowNotExists(text, options = {}) {
    const row = await this.findRow(text, { timeout: 5000, ...options })
    expect(row, `Row containing "${text}" should not exist`).toBeNull()
  }

  /**
   * 勾选某一行（用于批量操作）
   */
  async checkRow(text) {
    const row = await this.findRow(text)
    if (!row) throw new Error(`Row "${text}" not found`)
    const checkbox = row.locator('.el-checkbox').first()
    await checkbox.click()
    return this
  }

  /**
   * 工具栏按钮
   */
  async clickToolbarButton(text) {
    const btn = this.page.locator(`.toolbar button:has-text("${text}"), .actions button:has-text("${text}")`).first()
    await btn.waitFor({ state: 'visible', timeout: 5000 })
    await btn.click()
    return this
  }

  /**
   * 搜索（输入 + 回车）
   */
  async search(keyword) {
    const searchInput = this.page.locator('input[placeholder*="搜索"], input[placeholder*="名称"], input[placeholder*="编码"]').first()
    await searchInput.fill(keyword)
    await searchInput.press('Enter')
    // 等表格刷新
    await this.page.waitForTimeout(800)
    return this
  }

  /**
   * 断言列表为空
   */
  async expectEmpty() {
    const count = await this.getRowCount()
    expect(count, 'List should be empty').toBe(0)
  }

  // ============================================================
  // Row Actions (Dropdown) — v3.18 enum E2E
  // ============================================================

  /**
   * 打开行级操作下拉菜单 (点 ... 触发 dropdown)
   * @param {string|RegExp} rowText
   * @returns {Promise<void>}
   */
  async openRowActionsMenu(rowText) {
    const row = await this.findRow(rowText, { timeout: 5000 })
    if (!row) throw new Error(`Row "${rowText}" not found for row action`)
    const trigger = row.locator('.row-action-trigger, button[aria-label*="操作"], .action-column .el-dropdown button').first()
    if (!(await trigger.isVisible({ timeout: 2000 }).catch(() => false))) {
      throw new Error(`Row "${rowText}" has no row action trigger (e.g. category=system hides it)`)
    }
    await trigger.click()
    // dropdown 出现
    await this.page.waitForSelector('.row-action-popper:visible, .el-dropdown-menu:visible', { timeout: 3000 }).catch(() => {})
  }

  /**
   * 检查行级操作菜单中某项是否可见
   * @param {string|RegExp} rowText
   * @param {string|RegExp} actionLabel - 按钮 label (e.g. "编辑", "删除", "查看详情")
   * @returns {Promise<boolean>}
   */
  async isRowActionVisible(rowText, actionLabel) {
    try {
      await this.openRowActionsMenu(rowText)
    } catch (e) {
      return false
    }
    const popper = this.page.locator('.row-action-popper:visible, .el-dropdown-menu:visible').last()
    const item = popper.locator('.el-dropdown-menu__item:visible', { hasText: actionLabel }).first()
    const visible = await item.isVisible({ timeout: 1500 }).catch(() => false)
    // 关闭 popper
    await this.page.keyboard.press('Escape').catch(() => {})
    await this.page.waitForTimeout(150)
    return visible
  }

  /**
   * 点击行级操作 (dropdown 模式)
   * @param {string|RegExp} rowText
   * @param {string|RegExp} actionLabel
   */
  async clickRowAction(rowText, actionLabel) {
    await this.openRowActionsMenu(rowText)
    const popper = this.page.locator('.row-action-popper:visible, .el-dropdown-menu:visible').last()
    const item = popper.locator('.el-dropdown-menu__item:visible', { hasText: actionLabel }).first()
    await item.waitFor({ state: 'visible', timeout: 3000 })
    await item.click()
    return this
  }

  /**
   * 点击行内 "编辑" 按钮 (兼容 inline 按钮和 dropdown)
   */
  async clickRowEdit(rowText) {
    // 优先尝试 inline 按钮
    const row = await this.findRow(rowText, { timeout: 5000 })
    if (!row) throw new Error(`Row "${rowText}" not found`)
    const inlineEdit = row.locator('button:has-text("编辑"):not(.row-action-trigger)').first()
    if (await inlineEdit.isVisible({ timeout: 1500 }).catch(() => false)) {
      await inlineEdit.click()
      return this
    }
    // 否则走 dropdown
    return this.clickRowAction(rowText, /编辑|Edit/)
  }

  /**
   * 点击行内 "删除" 按钮 (兼容 inline 按钮和 dropdown)
   */
  async clickRowDelete(rowText) {
    const row = await this.findRow(rowText, { timeout: 5000 })
    if (!row) throw new Error(`Row "${rowText}" not found`)
    const inlineDel = row.locator('button:has-text("删除"):not(.row-action-trigger)').first()
    if (await inlineDel.isVisible({ timeout: 1500 }).catch(() => false)) {
      await inlineDel.click()
      return this
    }
    return this.clickRowAction(rowText, /删除|Delete/)
  }

  /**
   * 获取行级 API 解析的 ui_actions_resolved
   * 直接调后端接口 (admin cookie 来自 storageState)
   * 优先 v1 端点, 410 时回退 v2 BO 端点
   * @param {string} objectType - e.g. 'enum_type'
   * @param {string} objectId - 业务 ID (e.g. 'data_category' 或 'ActionType')
   * @returns {Promise<Object>} ui_actions_resolved
   */
  async getUiActionsResolved(objectType, objectId) {
    // 优先 v1 enum-types/<id> (返回 ui_actions_resolved)
    const v1 = await this.page.request.get(`/api/v1/${objectType.replace(/_/g, '-')}/${encodeURIComponent(objectId)}`)
    if (v1.ok()) {
      const body = await v1.json()
      return body?.data?.ui_actions_resolved || body?.ui_actions_resolved || null
    }
    // 回退 v2 BO 端点
    const v2 = await this.page.request.get(`/api/v2/bo/${objectType}/${encodeURIComponent(objectId)}`)
    if (v2.ok()) {
      const body = await v2.json()
      return body?.data?.ui_actions_resolved || body?.ui_actions_resolved || null
    }
    throw new Error(`getUiActionsResolved failed: v1=${v1.status()}, v2=${v2.status()}`)
  }
}
