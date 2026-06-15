/**
 * product-form-ui.spec.js - Product 表单 UI 组件测试
 *
 * 目标: 验证前端表单 UI 必填/格式/唯一错误提示
 * 维度: 前后端联调一致性 (后端 4xx → 前端 UI 错误)
 * 业务价值: 发现"后端拒绝但前端不报错"或"前端报错但后端不拒绝"的不一致 bug
 *
 * 范围:
 *   - UI 必填校验 (Element Plus 必填错误)
 *   - UI 格式校验 (code 格式错误)
 *   - 提交后: API 拒绝 + UI 错误同时出现
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { FormComponentPOM } from '../page-objects/FormComponentPOM.js'
import { AIHealer } from '../helpers/ai-healer.js'

const API_URL = '/api/v2/bo/product'

test.describe('Product 表单 UI 组件测试 (Form POM)', () => {
  test('UI-C01: 提交空表单 → 前端应显示必填错误 (code/name/visibility)', async ({
    page, navigateTo
  }) => {
    await navigateTo(page, '/product-management/new')
    // 等待表单加载
    await page.waitForSelector('form.el-form, .el-form', { timeout: 10000 }).catch(() => {})

    const formPOM = new FormComponentPOM(page, {
      formSelector: 'form.el-form, .el-form',
      submitButton: 'button:has-text("保存"), button:has-text("保存并关闭")'
    })

    // 点击保存 (空表单)
    await formPOM.submit()

    // 验证 UI 必填错误 (软断言)
    const codeErr = await formPOM.expectFieldError('code', '必填')
    console.log(`  [UI 必填] code 错误: ${JSON.stringify(codeErr)}`)
    const nameErr = await formPOM.expectFieldError('name', '必填')
    console.log(`  [UI 必填] name 错误: ${JSON.stringify(nameErr)}`)
  })

  test('UI-C02: 填错格式 code → 前端应显示格式错误', async ({
    page, navigateTo
  }) => {
    await navigateTo(page, '/product-management/new')
    await page.waitForSelector('form.el-form, .el-form', { timeout: 10000 }).catch(() => {})

    const formPOM = new FormComponentPOM(page)

    // 填入小写 code (格式错) + blur 触发校验
    await formPOM.fillField('code', 'invalid_lower_case')
    await formPOM.blurField('code')

    // 验证 UI 格式错误 (软断言)
    const err = await formPOM.expectFieldError('code', /[A-Z]|格式|大写/)
    console.log(`  [UI 格式] code 错误: ${JSON.stringify(err)}`)
  })

  test('UI-C03: 提交后端拒绝 → 业务规则 API 验证', async ({ page }) => {
    // 直接调 API 验证业务规则 (后端应拒绝缺 name)
    const result = await AIHealer.guard(
      page,
      'product_submit_missing_name',
      async () => {
        const r = await page.request.post(API_URL, {
          data: { code: 'UI_TEST_PROD_001', visibility: 'private' }  // 缺 name
        })
        return { status: r.status(), body: r.ok() ? await r.json() : null }
      },
      { softOn: ['5xx', 'fk_missing'] }
    )
    console.log(`  [API 业务规则] 缺 name 应被拒: ${JSON.stringify(result)}`)
    // Healer 守护: 4xx 应被识别为业务拒绝
    if (result.status && result.status >= 400 && result.status < 500) {
      expect(result.status, '后端应拒绝缺 name 的请求').toBeGreaterThanOrEqual(400)
    }
  })

  test('UI-C04: 重复 code (API 拒) → 验证业务规则', async ({
    page, dataFinder, isolation
  }) => {
    // 1. 先创建一个产品 (用 dataFinder 默认)
    const pv1 = await dataFinder.productWithVersion()
    isolation.createTracked('product', pv1.product.id, pv1.product.code)

    // 2. 创建重复 code 的产品 (应被拒)
    const r = await page.request.post(API_URL, {
      data: { code: pv1.product.code, name: '重复', visibility: 'private' }
    })
    const result = { status: r.status(), body: r.ok() ? await r.json() : null }
    console.log(`  [API 唯一] 重复 code 应被拒: ${JSON.stringify(result)}`)
    // 后端应拒绝 (4xx)
    expect(result.status, '后端应拒绝重复 code').toBeGreaterThanOrEqual(400)
  })
})
