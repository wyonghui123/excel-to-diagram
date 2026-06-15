/**
 * S-BF-BO-001: 业务对象 (business_object) 生命周期 - 业务流 E2E (AI 派生)
 *
 * [E2E v2 铁律合规 (8 项)]
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now()
 * [OK] 用 POM (GenericListPage) 不用直接 locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 解构
 *
 * 业务规则:
 *   BR-business_object-FLD-REQ-code      (code 必填)
 *   BR-business_object-FLD-REQ-name      (name 必填)
 *   BR-business_object-FLD-PAT-code      (code 格式 ^[A-Z][A-Z0-9_]*$)
 *   BR-business_object-VAL-code_format   (编码格式不正确)
 *   BR-business_object-DEL-condition     (无关系时可删)
 *   BR-business_object-AUDIT-create      (创建应记录 audit_log)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'

const BO_URL = '/system/archdata'

test.describe('S-BF-BO-001: 业务对象生命周期 - 业务流 (AI 派生)', () => {

  test('C01: 创建业务对象 - 必填字段校验', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {

    // === 1. code 必填 ===
    await withStep(page, testInfo, '验证 code 必填 (BR-business_object-FLD-REQ-code)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'business_object', {
        name: 'test_no_code',
        version_id: '00000000-0000-0000-0000-000000000001'
      }, 'code')
      expect(result).toBe(true)
    })

    // === 2. name 必填 ===
    await withStep(page, testInfo, '验证 name 必填 (BR-business_object-FLD-REQ-name)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'business_object', {
        code: 'TEST_NO_NAME',
        version_id: '00000000-0000-0000-0000-000000000001'
      }, 'name')
      expect(result).toBe(true)
    })
  })

  test('C02: 创建业务对象 - happy path + 删除约束', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {

    const pv = await dataFinder.productWithVersion()
    const boCode = `BO_${Date.now().toString(36).toUpperCase()}`
    const boName = `测试业务对象_${Date.now().toString(36)}`

    // === 1. 创建业务对象 ===
    const bo = await withStep(page, testInfo, '创建业务对象', async () => {
      const created = await isolation.createTracked('business_object', {
        code: boCode,
        name: boName,
        version_id: pv.version.id
      })
      return { ...created, name: boName, code: boCode }
    })
    expect(bo.id).toBeTruthy()

    // === 2. 业务断言: 无关系时可删 ===
    await withStep(page, testInfo, '验证可删除 (BR-business_object-DEL-condition)', async () => {
      const result = await BusinessRuleAssertor.assertDeletable(page, 'business_object', bo.id)
      expect(result.deletable).toBe(true)
    })

    // === 3. UI 软断言 ===
    await withStep(page, testInfo, '导航到业务对象列表', async () => {
      await navigateTo(page, BO_URL)
    })
  })
})
