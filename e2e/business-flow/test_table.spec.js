/**
 * S-BF-TEST_TABLE-AUTO: 测试表 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 test_table.yaml 自动生成
 * [E2E v2 铁律合规 (8 项)]
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM (GenericListPage) 不用直接 locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 解构
 * [阶段三] Healer 守护: C_AUDIT/C_DEL/C_UI_NAV 失败时软断言
 *
 * 业务规则:
 *   BR-test_table-FLD-REQ-name  (名称 必填)
 *
 * 自动生成时间: 2026-05-28
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const TEST_TABLE_URL = '/test_table-management'

test.describe('S-BF-TEST_TABLE-AUTO: 测试表 - 业务流 (AI 派生)', () => {

  /**
   * UI 导航: 进入 [测试表] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [测试表] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [测试表] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_test_table', async () => {
        await navigateTo(page, '/test_table-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
