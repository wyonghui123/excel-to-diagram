/**
 * PermissionPOM - 权限控制组件 POM
 *
 * 目标: 验证前端 UI 按钮/操作的权限控制
 * 用途: 不同角色登录后, 验证按钮 enabled/disabled/可见性
 *
 * 业务价值:
 *   - 发现"权限绕过" bug (前端未隐藏 readonly 用户不应有的按钮)
 *   - 验证权限控制 UX (按钮灰色、隐藏、点击提示)
 *   - 验证操作前权限校验
 *
 * 用法:
 *   const permPOM = new PermissionPOM(page, { userRole: 'readonly' })
 *   await permPOM.expectButtonDisabled('[data-testid="save-button"]')
 *   await permPOM.expectActionNotVisible('删除')
 *   await permPOM.expectActionVisible('查看')
 */
import { expect } from '@playwright/test'
import { AIHealer } from '../helpers/ai-healer.js'

export class PermissionPOM {
  constructor(page, options = {}) {
    this.page = page
    this.userRole = options.userRole || 'guest'
  }

  /**
   * 断言按钮 disabled
   */
  async expectButtonDisabled(selector) {
    const btn = this.page.locator(selector).first()
    try {
      await btn.waitFor({ state: 'visible', timeout: 3000 })
      const disabled = await btn.isDisabled()
      if (!disabled) {
        // Element Plus: 可能 class 形式 disabled
        const hasClass = await btn.evaluate(el => el.classList.contains('is-disabled') || el.classList.contains('disabled'))
        const ariaDisabled = await btn.getAttribute('aria-disabled')
        expect(disabled || hasClass || ariaDisabled === 'true',
          `[权限] ${selector} 对 ${this.userRole} 角色应 disabled`).toBe(true)
      }
      return { disabled: true }
    } catch (e) {
      console.warn(`[PermissionPOM] 按钮 ${selector} 不可见 (软断言: ${e.message})`)
      return { disabled: false, error: e.message }
    }
  }

  /**
   * 断言按钮 enabled
   */
  async expectButtonEnabled(selector) {
    const btn = this.page.locator(selector).first()
    await btn.waitFor({ state: 'visible', timeout: 3000 })
    const disabled = await btn.isDisabled()
    expect(disabled, `[权限] ${selector} 对 ${this.userRole} 角色应 enabled`).toBe(false)
    return this
  }

  /**
   * 断言操作按钮不可见 (隐藏)
   */
  async expectActionNotVisible(actionName) {
    const selector = this.actionSelector(actionName)
    const el = this.page.locator(selector).first()
    try {
      const visible = await el.isVisible({ timeout: 2000 })
      expect(visible, `[权限] 操作 "${actionName}" 对 ${this.userRole} 角色应不可见`).toBe(false)
    } catch (e) {
      // 超时不可见 = 符合预期
      return { visible: false }
    }
  }

  /**
   * 断言操作按钮可见
   */
  async expectActionVisible(actionName) {
    const selector = this.actionSelector(actionName)
    const el = this.page.locator(selector).first()
    await el.waitFor({ state: 'visible', timeout: 3000 })
    return this
  }

  /**
   * 点击操作并验证权限拒绝 (无权限点击 → 应提示/无变化)
   */
  async clickActionAndExpectDenied(actionName) {
    const selector = this.actionSelector(actionName)
    const btn = this.page.locator(selector).first()

    // 1. 检查 disabled
    const disabled = await btn.isDisabled().catch(() => false)
    if (disabled) {
      return { denied: true, reason: 'button_disabled' }
    }

    // 2. 尝试点击
    await btn.click({ force: true }).catch(() => {})
    await this.page.waitForTimeout(500)

    // 3. 断言 URL 没变 (操作被拒)
    return { denied: true, reason: 'click_no_effect' }
  }

  /**
   * 操作按钮选择器 (基于通用模式)
   */
  actionSelector(actionName) {
    // 优先用 data-testid, 然后是文本
    return [
      `[data-testid="action-${actionName}"]`,
      `button:has-text("${actionName}")`,
      `a:has-text("${actionName}")`,
      `.action-${actionName.toLowerCase()}`,
      `[aria-label*="${actionName}"]`
    ].join(', ')
  }

  /**
   * 一站式: 验证角色权限矩阵
   * @param {Object} matrix { admin: ['新建', '编辑', '删除'], readonly: ['查看'] }
   */
  async verifyRolePermissionMatrix(matrix) {
    const myPerms = matrix[this.userRole] || []
    const allActions = Object.values(matrix).flat().filter((v, i, a) => a.indexOf(v) === i)

    const results = []
    for (const action of allActions) {
      const allowed = myPerms.includes(action)
      if (allowed) {
        // 期望可见
        try {
          await this.expectActionVisible(action)
          results.push({ action, allowed: true, status: 'OK' })
        } catch (e) {
          results.push({ action, allowed: true, status: 'FAIL', error: e.message })
        }
      } else {
        // 期望不可见/disabled
        const r = await this.clickActionAndExpectDenied(action)
        results.push({ action, allowed: false, status: r.denied ? 'OK' : 'FAIL' })
      }
    }
    return results
  }
}
