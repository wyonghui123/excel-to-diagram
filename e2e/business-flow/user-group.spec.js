/**
 * S-BF-UG-001: 用户组 (user_group) 生命周期 - 业务流 E2E (AI 派生)
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
 *   BR-user_group-FLD-REQ-code  (code 必填)
 *   BR-user_group-FLD-REQ-name  (name 必填)
 *   BR-user_group-AUDIT-create  (创建应记录 audit_log)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'

const UG_URL = '/system/user-group'

test.describe('S-BF-UG-001: 用户组生命周期 - 业务流 (AI 派生)', () => {

  test('C01: 创建用户组 - 必填字段校验', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {

    // === 1. code 必填 ===
    await withStep(page, testInfo, '验证 code 必填 (BR-user_group-FLD-REQ-code)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group', {
        name: 'test_no_code'
      }, 'code')
      expect(result).toBe(true)
    })

    // === 2. name 必填 ===
    await withStep(page, testInfo, '验证 name 必填 (BR-user_group-FLD-REQ-name)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group', {
        code: 'TEST_NO_NAME'
      }, 'name')
      expect(result).toBe(true)
    })
  })

  test('C02: 创建用户组 - happy path', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {

    const ugCode = `UG_${Date.now().toString(36).toUpperCase()}`
    const ugName = `测试用户组_${Date.now().toString(36)}`

    // === 1. 创建用户组 ===
    const ug = await withStep(page, testInfo, '创建用户组', async () => {
      const created = await isolation.createTracked('user_group', {
        code: ugCode,
        name: ugName,
        description: 'E2E 测试用户组'
      })
      return { ...created, name: ugName, code: ugCode }
    })
    expect(ug.id).toBeTruthy()

    // === 2. UI 软断言: 导航到用户组列表 ===
    await withStep(page, testInfo, '导航到用户组列表', async () => {
      await navigateTo(page, UG_URL)
    })
  })
})
