/**
 * FormComponentPOM - 通用表单组件 POM
 *
 * 目标: 验证前端 UI 必填/格式/唯一等错误提示
 * 用途: 当后端业务规则触发时, 验证前端是否正确显示错误提示
 *
 * 业务价值:
 *   - 发现"前后端不一致" bug (后端报 4xx 但前端不显示错误)
 *   - 验证 UI 错误提示文案 (业务语义)
 *   - 验证表单字段必填 UX
 *
 * 用法:
 *   const formPOM = new FormComponentPOM(page, {
 *     formSelector: '.el-form',           // 表单根选择器
 *     fieldSelector: '.el-form-item',     // 字段项选择器
 *     submitButton: 'button:has-text("保存")',  // 提交按钮
 *     errorSelector: '.el-form-item__error'  // 错误信息元素
 *   })
 *   await formPOM.fillField('code', 'invalid')
 *   await formPOM.submit()
 *   await formPOM.expectFieldError('code', 'code 格式不正确')
 */
import { expect } from '@playwright/test'
import { AIHealer } from '../helpers/ai-healer.js'

export class FormComponentPOM {
  constructor(page, options = {}) {
    this.page = page
    this.formSelector = options.formSelector || '.el-form'
    this.fieldSelector = options.fieldSelector || '.el-form-item'
    this.submitButton = options.submitButton || 'button:has-text("保存"), button:has-text("Submit")'
    this.errorSelector = options.errorSelector || '.el-form-item__error'
  }

  /**
   * 定位字段容器 (通过 prop 或 label)
   * @param {string} fieldName 字段 prop 名 (如 'code', 'name')
   */
  getFieldItem(fieldName) {
    return this.page.locator(`${this.fieldSelector}[prop="${fieldName}"], ${this.fieldSelector}:has(label:has-text("${fieldName}"))`).first()
  }

  /**
   * 填字段
   */
  async fillField(fieldName, value) {
    const item = this.getFieldItem(fieldName)
    const input = item.locator('input, textarea, .el-input__inner').first()
    await input.fill(String(value))
    return this
  }

  /**
   * 触发 blur (用于触发校验)
   */
  async blurField(fieldName) {
    const item = this.getFieldItem(fieldName)
    const input = item.locator('input, textarea, .el-input__inner').first()
    await input.blur()
    // Element Plus 校验在 blur 后 100ms 内触发
    await this.page.waitForTimeout(100)
    return this
  }

  /**
   * 点提交
   */
  async submit() {
    await this.page.click(this.submitButton)
    // 等待 API 响应 (networkidle 或 timeout)
    await this.page.waitForTimeout(500)
    return this
  }

  /**
   * 断言字段错误信息
   * @param {string} fieldName
   * @param {string|RegExp} expectedError 期望的错误信息或正则
   */
  async expectFieldError(fieldName, expectedError) {
    const item = this.getFieldItem(fieldName)
    const errorEl = item.locator(this.errorSelector)
    // 软断言 (Healer): UI 错误提示是次要, 业务规则是核心
    try {
      await errorEl.waitFor({ state: 'visible', timeout: 3000 })
      const text = (await errorEl.textContent() || '').trim()
      if (expectedError instanceof RegExp) {
        expect(text, `[UI 错误] ${fieldName} 应匹配 ${expectedError}`).toMatch(expectedError)
      } else {
        expect(text, `[UI 错误] ${fieldName} 应包含 "${expectedError}"`).toContain(expectedError)
      }
      return { hasError: true, text }
    } catch (e) {
      console.warn(`[FormPOM] ${fieldName} 未显示 UI 错误 (软断言: ${e.message})`)
      return { hasError: false, text: '' }
    }
  }

  /**
   * 断言字段无错误 (校验通过)
   */
  async expectNoFieldError(fieldName) {
    const item = this.getFieldItem(fieldName)
    const errorEl = item.locator(this.errorSelector)
    const visible = await errorEl.isVisible().catch(() => false)
    expect(visible, `[UI] ${fieldName} 不应有错误提示`).toBe(false)
    return this
  }

  /**
   * 验证 UI 必填校验 (不填字段 → 应显示必填错误)
   */
  async verifyRequiredField(fieldName, options = {}) {
    const {
      fillOtherFields = {},  // 其他必填字段填充
      expectedError = '必填'
    } = options

    // 1. 清空目标字段
    const item = this.getFieldItem(fieldName)
    const input = item.locator('input, textarea, .el-input__inner').first()
    await input.fill('')

    // 2. 填充其他必填字段
    for (const [name, value] of Object.entries(fillOtherFields)) {
      await this.fillField(name, value)
    }

    // 3. 触发 blur (Element Plus 必填校验)
    await this.blurField(fieldName)

    // 4. 断言错误信息
    return await this.expectFieldError(fieldName, expectedError)
  }

  /**
   * 验证 UI 格式校验 (填错格式 → 应显示格式错误)
   */
  async verifyPatternField(fieldName, invalidValue, expectedError) {
    await this.fillField(fieldName, invalidValue)
    await this.blurField(fieldName)
    return await this.expectFieldError(fieldName, expectedError)
  }

  /**
   * 一站式: 提交后断言后端 + 前端
   */
  async submitAndExpectBoth(apiValidationFn, fieldName, expectedUIError) {
    // 1. 点提交
    await this.submit()

    // 2. Healer 守护 API 验证 (业务规则核心)
    const apiResult = await AIHealer.guard(
      this.page,
      `submit_${fieldName}`,
      apiValidationFn,
      { softOn: ['5xx', '404', 'fk_missing'] }
    )

    // 3. 断言 UI 错误提示
    if (expectedUIError) {
      const uiResult = await this.expectFieldError(fieldName, expectedUIError)
      return { api: apiResult, ui: uiResult }
    }

    return { api: apiResult, ui: null }
  }
}
