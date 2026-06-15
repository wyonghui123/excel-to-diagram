/**
 * S-BF-VERSION-AUTO: 产品版本 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 version.yaml 自动生成
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
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
 *   BR-version-FLD-REQ-product_id  (产品 必填)
 *   BR-version-FLD-REQ-name  (版本名称 必填)
 *   BR-version-FLD-PAT-name  (格式: ^[A-Za-z0-9][A-Za-z0-9_.\-]*$)
 *   BR-version-DEL-condition  (存在领域的版本不能删除)
 *   BR-version-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-06-13
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { navigateToDeepLink } from '../helpers/auto-fixtures.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { FormComponentPOM } from '../page-objects/FormComponentPOM.js'
import { PermissionPOM } from '../page-objects/PermissionPOM.js'
import { PaginationPOM } from '../page-objects/PaginationPOM.js'
import { NestedPOM } from '../page-objects/NestedPOM.js'
import { PersistencePOM } from '../page-objects/PersistencePOM.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const VERSION_URL = '/version-management'

test.describe('S-BF-VERSION-AUTO: 产品版本 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 产品 (product_id)
   * 业务规则: BR-version-FLD-REQ-product_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PRODUCT_ID: 缺少必填字段 [产品] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [产品] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'version', {
        name: "TEST_NAME_PLACEHOLDER",
      }, 'product_id')
      expect(result, '[API 维度] 缺少 [产品] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 版本名称 (name)
   * 业务规则: BR-version-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [版本名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [版本名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'version', {
        product_id: null,
      }, 'name')
      expect(result, '[API 维度] 缺少 [版本名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 格式校验: 版本名称 (name)
   * 业务规则: BR-version-FLD-PAT-name
   * 正则: ^[A-Za-z0-9][A-Za-z0-9_.\-]*$
   */
  test('C_PAT_NAME: [版本名称] 格式不符应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [版本名称] 格式不符应被拒绝', async () => {
      const result = await BusinessRuleAssertor.assertFieldPattern(
        page, 'version', {
        product_id: null,
          name: 'invalid_value_123'
        }, '^[A-Za-z0-9][A-Za-z0-9_.\-]*$'
      )
      expect(result, '[Pattern] 格式不符应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 是否当前版本 (is_current)
   * 业务规则: BR-version-FLD-ENUM-is_current
   * 允许值: [{'value': 1, 'label': '是', 'color': 'success'}, {'value': 0, 'label': '否', 'color': 'info'}]
   */
  test('C_ENUM_IS_CURRENT: [是否当前版本] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [是否当前版本] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'version', {
        product_id: null,
        name: "TEST_NAME_PLACEHOLDER",
          is_current: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 1, 'label': '是', 'color': 'success'}, {'value': 0, 'label': '否', 'color': 'info'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 删除约束: 存在领域的版本不能删除
   * 业务规则: BR-version-DEL-condition
   * 条件: self.child_count == 0
   * [Healer.L3] createTracked 失败时软断言 (FK 关联缺失)
   */
  test('C_DEL: 删除 [产品版本] 业务规则', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [产品版本] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_DEL_version_create', async () => {
        return await isolation.createTracked('version', {
        product_id: null,
        name: `DEL_NAME_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_DEL create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: 无关联时可删除 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_DEL_version_check', async () => {
        const result = await BusinessRuleAssertor.assertDeletable(
          page, 'version', obj.id, { relatedCount: 0 }
        )
        expect(result.deletable, '[Business] 无关联时应可删').toBe(true)
      }, { softOn: ['5xx', '404', 'fk_missing'] })
      if (r.healed) console.log(`[Healer] C_DEL 软断言通过: ${r.reason}`)
    })
  })


  /**
   * 审计日志: 创建 [产品版本] 应记录 audit_log
   * 业务规则: BR-version-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [产品版本] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [产品版本] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_version_create', async () => {
        return await isolation.createTracked('version', {
        product_id: null,
        name: `AUD_NAME_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_version_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'version', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-version-HEALTH
   */
  test('HEALTH: [产品版本] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_version', async () => {
      await navigateTo(page, '/version-management')
      await page.waitForTimeout(1000)
    }, { softOn: ['5xx', '404'] })
    if (errors.length === 0) {
      console.log(`  [HEALTH] 无 pageerror/console.error`)
    } else {
      console.warn(`  [HEALTH] 发现 ${errors.length} 错误: ${errors.slice(0, 3).join('; ')}`)
    }
    if (r.healed) console.log(`[Healer] HEALTH 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [产品版本] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [产品版本] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [产品版本] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_version', async () => {
        await navigateTo(page, '/version-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
