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

  // ============================================================
  // Facet / Action 矩阵 (v3.18 enum E2E)
  // ============================================================

  /**
   * 切换 facet (e.g. "基本信息", "维度配置", "系统信息")
   * @param {string|RegExp} facetName
   */
  async switchFacet(facetName) {
    const drawer = this.getRoot()
    // 兼容: 标题 tab (.app-card-header) / 锚点 tab (.anchor-tab) / 标准 el-tabs
    const candidates = [
      `.app-card-header:has-text("${facetName}")`,
      `.anchor-tab:has-text("${facetName}")`,
      `.el-tabs__item:has-text("${facetName}")`,
      `.el-collapse-item__header:has-text("${facetName}")`,
      `.section-title:has-text("${facetName}")`
    ]
    for (const sel of candidates) {
      const tab = drawer.locator(sel).first()
      if (await tab.isVisible({ timeout: 1500 }).catch(() => false)) {
        await tab.click()
        await this.page.waitForTimeout(300)
        return this
      }
    }
    throw new Error(`Facet "${facetName}" not found in drawer`)
  }

  /**
   * 断言 drawer 中无任何 action 按钮 (用于 system/locked 场景)
   * @param {string[]} allowedLabels - 允许出现的按钮 (默认 [])
   */
  async expectNoActions(allowedLabels = []) {
    const drawer = this.getRoot()
    const allowed = new Set(allowedLabels)
    const actionBar = drawer.locator(this.actionsSelector).first()
    const exists = await actionBar.count()
    if (exists === 0) return this  // 没有 action bar → 通过

    const buttons = actionBar.locator('button')
    const cnt = await buttons.count()
    const visibleLabels = []
    for (let i = 0; i < cnt; i++) {
      const btn = buttons.nth(i)
      if (await btn.isVisible({ timeout: 500 }).catch(() => false)) {
        const txt = (await btn.textContent() || '').trim()
        if (txt) visibleLabels.push(txt)
      }
    }
    const unexpected = visibleLabels.filter(l => !allowed.has(l))
    expect(unexpected, `drawer 应无操作按钮, 但发现: ${unexpected.join(', ')}`).toEqual([])
    return this
  }

  /**
   * 断言字段被禁用 (label 找到对应 input, input/textarea/select disabled)
   */
  async expectFieldDisabled(label) {
    const drawer = this.getRoot()
    const formItem = drawer.locator(
      `.el-form-item:has(.el-form-item__label:has-text("${label}"))`
    ).first()
    await formItem.waitFor({ state: 'visible', timeout: 3000 })
    const input = formItem.locator('input, textarea').first()
    const exists = await input.count()
    if (exists > 0) {
      const disabled = await input.isDisabled()
      expect(disabled, `Field "${label}" should be disabled`).toBe(true)
    } else {
      // 选择型字段: el-select 整体 disabled
      const select = formItem.locator('.el-select').first()
      const exists2 = await select.count()
      if (exists2 > 0) {
        const cls = (await select.getAttribute('class') || '').split(/\s+/)
        expect(cls.some(c => c.includes('disabled')), `Select "${label}" should be disabled`).toBe(true)
      }
    }
    return this
  }

  /**
   * 等待成功/错误通知 (ElNotification / ElMessage)
   * @param {'success'|'error'|'warning'|'info'} type
   * @param {string|RegExp} textMatch
   * @param {number} timeout
   */
  async expectNotification(type, textMatch, timeout = 8000) {
    const sel = `.el-notification.${type}, .el-notification--${type}, .el-message--${type}`
    const notif = this.page.locator(sel).first()
    await notif.waitFor({ state: 'visible', timeout }).catch(async () => {
      // 兜底: 任意 notification/message
      const fallback = this.page.locator(`.el-notification:has-text("${textMatch}"), .el-message:has-text("${textMatch}")`).first()
      await fallback.waitFor({ state: 'visible', timeout: 2000 })
    })
    const txt = (await notif.textContent().catch(() => '')) || ''
    if (textMatch instanceof RegExp) {
      expect(txt, `Notification text should match ${textMatch}`).toMatch(textMatch)
    } else if (typeof textMatch === 'string') {
      expect(txt, `Notification should contain "${textMatch}"`).toContain(textMatch)
    }
    return this
  }

  /**
   * 等待通知消失 (防止脏数据)
   */
  async waitNotificationGone(timeout = 10000) {
    await this.page.locator('.el-notification, .el-message').first().waitFor({ state: 'hidden', timeout }).catch(() => {})
    return this
  }

  /**
   * 切换到"编辑"模式后, 获取表单所有字段 + 值
   * @returns {Promise<Array<{label: string, value: string, disabled: boolean}>>}
   */
  async getFormFields() {
    const drawer = this.getRoot()
    const items = drawer.locator('.el-form-item')
    const cnt = await items.count()
    const out = []
    for (let i = 0; i < cnt; i++) {
      const item = items.nth(i)
      const label = (await item.locator('.el-form-item__label').textContent() || '').trim()
      const input = item.locator('input, textarea').first()
      const select = item.locator('.el-select').first()
      let value = ''
      let disabled = false
      if (await input.count() > 0) {
        value = await input.inputValue().catch(() => '')
        disabled = await input.isDisabled()
      } else if (await select.count() > 0) {
        value = (await select.locator('.el-select__placeholder, input').first().textContent().catch(() => '')) || ''
        const cls = (await select.getAttribute('class') || '').split(/\s+/)
        disabled = cls.some(c => c.includes('disabled'))
      }
      if (label) out.push({ label, value, disabled })
    }
    return out
  }
}
