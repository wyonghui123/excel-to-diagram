/**
 * 详情抽屉 POM - 适用于所有 ObjectDetailPage 的 el-drawer
 *
 * 用法对比：
 *
 * 【旧写法】每测试 5-10 行
 *   const detailDrawer = page.locator('.el-drawer.open')
 *   const editBtn = detailDrawer.locator('.op-actions button:has-text("编辑")').first()
 *   await editBtn.waitFor({ state: 'visible', timeout: 5000 })
 *   await editBtn.click()
 *   await page.waitForTimeout(1500)
 *   // 找输入框...
 *   const nameInput = page.locator('.el-drawer.open .el-input__inner[placeholder="请输入名称"]').first()
 *   await nameInput.fill(newName)
 *   // 找保存按钮
 *   const saveBtn = page.locator('.el-drawer.open .op-actions button:has-text("保存")').first()
 *   await saveBtn.click()
 *   // 等结果消息
 *
 * 【新写法】业务流式
 *   const drawer = new DetailDrawerPage(page)
 *   await drawer.open()
 *   await drawer.clickEdit()
 *   await drawer.fillFieldByLabel('名称', newName)
 *   await drawer.clickSave()
 *   await drawer.expectSuccessMessage()
 */

import { expect } from '@playwright/test'

export class DetailDrawerPage {
  /**
   * @param {Page} page
   * @param {Object} options
   *   - drawerSelector: drawer 选择器（默认 .el-drawer.open）
   *   - actionsSelector: 操作区选择器（默认 .op-actions）
   */
  constructor(page, options = {}) {
    this.page = page
    this.drawerSelector = options.drawerSelector || '.el-drawer.open'
    this.actionsSelector = options.actionsSelector || '.op-actions'
  }

  /**
   * 等待 drawer 打开
   */
  async waitForOpen(timeout = 10000) {
    const drawer = this.page.locator(this.drawerSelector)
    await drawer.waitFor({ state: 'visible', timeout })
    return this
  }

  /**
   * 获取 drawer 根元素
   */
  getRoot() {
    return this.page.locator(this.drawerSelector)
  }

  /**
   * 切换到指定 tab
   */
  async switchTab(tabName) {
    const tab = this.getRoot().locator(`.anchor-tab:has-text("${tabName}"), .el-tabs__item:has-text("${tabName}")`).first()
    await tab.waitFor({ state: 'visible', timeout: 5000 })
    await tab.click()
    await this.page.waitForTimeout(400)
    return this
  }

  /**
   * 点击 "编辑" 按钮
   */
  async clickEdit() {
    const btn = this.getRoot().locator(`${this.actionsSelector} button:has-text("编辑")`).first()
    await btn.waitFor({ state: 'visible', timeout: 5000 })
    await btn.click()
    // 等编辑模式加载
    await this.page.waitForTimeout(600)
    return this
  }

  /**
   * 点击 "保存" 按钮
   */
  async clickSave() {
    const btn = this.getRoot().locator(`${this.actionsSelector} button:has-text("保存")`).first()
    await btn.waitFor({ state: 'visible', timeout: 5000 })
    await btn.click()
    return this
  }

  /**
   * 点击 "删除" 按钮
   */
  async clickDelete() {
    const btn = this.getRoot().locator(`${this.actionsSelector} button:has-text("删除")`).first()
    await btn.waitFor({ state: 'visible', timeout: 5000 })
    await btn.click()
    return this
  }

  /**
   * 确认删除（在弹出的确认框中点"确定"）
   */
  async confirmDelete() {
    const dialog = this.page.locator('.el-message-box, .el-dialog:visible').first()
    await dialog.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})

    let confirmBtn = dialog.locator('button:has-text("确定")').first()
    if (!(await confirmBtn.isVisible().catch(() => false))) {
      confirmBtn = dialog.locator('button.el-button--primary').first()
    }
    await confirmBtn.click()
    return this
  }

  /**
   * 关闭 drawer（按 ESC）
   */
  async close() {
    await this.page.keyboard.press('Escape')
    await this.page.waitForTimeout(300)
    // 兜底：JS 强制移除
    await this.page.evaluate(() => {
      document.querySelectorAll('.el-overlay').forEach(o => {
        o.classList.add('is-hidden')
        o.style.display = 'none'
      })
    }).catch(() => {})
    return this
  }

  /**
   * 通过 label 填写字段（自动找 input/textarea/select）
   *
   * @param {string} label - 字段 label（如 "名称"、"编码"）
   * @param {string} value - 要填的值
   */
  async fillFieldByLabel(label, value) {
    // 尝试多种选择器策略
    const strategies = [
      // 1. label + 紧邻 input
      `:has-text("${label}") >> xpath=following::input[1]`,
      // 2. label 文本 + 同一 form-item 内的 input
      `.el-form-item:has(.el-form-item__label:has-text("${label}")) input`,
      `.el-form-item:has(.el-form-item__label:has-text("${label}")) textarea`,
      // 3. 通过 placeholder 模糊匹配
      `input[placeholder*="${label}"]`,
    ]

    for (const sel of strategies) {
      const input = this.page.locator(sel).first()
      if (await input.isVisible({ timeout: 1000 }).catch(() => false)) {
        await input.fill(value)
        return this
      }
    }

    throw new Error(`Field with label "${label}" not found`)
  }

  /**
   * 通过 label 选择下拉项
   */
  async selectFieldByLabel(label, optionText) {
    // 点击 select 触发器
    const trigger = this.page.locator(
      `.el-form-item:has(.el-form-item__label:has-text("${label}")) .el-select`
    ).first()
    await trigger.click()
    await this.page.waitForTimeout(300)
    // 选择下拉项
    const option = this.page.locator(`.el-select-dropdown:visible .el-select-dropdown__item:has-text("${optionText}")`).first()
    await option.click()
    return this
  }

  /**
   * 断言成功消息出现
   */
  async expectSuccessMessage(timeout = 8000) {
    const success = this.page.locator('.notification-success, .el-message--success').first()
    await success.waitFor({ state: 'visible', timeout })
    const text = await success.textContent().catch(() => '')
    console.log(`[OK] 成功消息: ${text}`)
    return this
  }

  /**
   * 断言错误消息出现
   */
  async expectErrorMessage(timeout = 8000) {
    const error = this.page.locator('.notification-error, .el-message--error').first()
    await error.waitFor({ state: 'visible', timeout })
    const text = await error.textContent().catch(() => '')
    console.log(`[OK] 错误消息: ${text}`)
    return this
  }

  /**
   * 断言 drawer 关闭
   */
  async expectClosed(timeout = 5000) {
    const drawer = this.getRoot()
    await drawer.waitFor({ state: 'hidden', timeout }).catch(() => {})
    return this
  }

  /**
   * 获取 drawer 中所有 facet/card
   */
  async getFacets() {
    return this.getRoot().locator('.app-card').count()
  }

  /**
   * 断言 drawer 显示指定文本
   */
  async expectContainsText(text) {
    const drawerText = await this.getRoot().textContent()
    expect(drawerText, `Drawer should contain text "${text}"`).toContain(text)
    return this
  }
}
