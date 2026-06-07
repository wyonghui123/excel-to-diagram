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
}
