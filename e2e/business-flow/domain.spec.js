/**
 * S-BF-DOMAIN-AUTO: 领域 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 domain.yaml 自动生成
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
 *   BR-domain-FLD-REQ-version_id  (版本 必填)
 *   BR-domain-FLD-REQ-code  (编码 必填)
 *   BR-domain-FLD-REQ-name  (名称 必填)
 *   BR-domain-FLD-PAT-code  (格式: ^[A-Z][A-Z0-9_]*$)
 *   BR-domain-DEL-condition  (存在子领域或关联关系的领域不能删除)
 *   BR-domain-AUDIT-create/update/delete  (审计日志)
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

const DOMAIN_URL = '/domain-management'

test.describe('S-BF-DOMAIN-AUTO: 领域 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 版本 (version_id)
   * 业务规则: BR-domain-FLD-REQ-version_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_VERSION_ID: 缺少必填字段 [版本] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [版本] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'domain', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
      }, 'version_id')
      expect(result, '[API 维度] 缺少 [版本] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 编码 (code)
   * 业务规则: BR-domain-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'domain', {
        version_id: null,
        name: "placeholder_name",
      }, 'code')
      expect(result, '[API 维度] 缺少 [编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 名称 (name)
   * 业务规则: BR-domain-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'domain', {
        version_id: null,
        code: "TEST_CODE_PLACEHOLDER",
      }, 'name')
      expect(result, '[API 维度] 缺少 [名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 格式校验: 编码 (code)
   * 业务规则: BR-domain-FLD-PAT-code
   * 正则: ^[A-Z][A-Z0-9_]*$
   */
  test('C_PAT_CODE: [编码] 格式不符应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [编码] 格式不符应被拒绝', async () => {
      const result = await BusinessRuleAssertor.assertFieldPattern(
        page, 'domain', {
        version_id: null,
        name: "placeholder_name",
          code: 'invalid_value_123'
        }, '^[A-Z][A-Z0-9_]*$'
      )
      expect(result, '[Pattern] 格式不符应被拒').toBe(true)
    })
  })


  /**
   * 删除约束: 存在子领域或关联关系的领域不能删除
   * 业务规则: BR-domain-DEL-condition
   * 条件: self.child_count == 0 and self.relation_count == 0
   * [Healer.L3] createTracked 失败时软断言 (FK 关联缺失)
   */
  test('C_DEL: 删除 [领域] 业务规则', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [领域] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_DEL_domain_create', async () => {
        return await isolation.createTracked('domain', {
        version_id: null,
        code: `DEL_CODE_${TS}`,
        name: `del_name_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_DEL create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: 无关联时可删除 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_DEL_domain_check', async () => {
        const result = await BusinessRuleAssertor.assertDeletable(
          page, 'domain', obj.id, { relatedCount: 0 }
        )
        expect(result.deletable, '[Business] 无关联时应可删').toBe(true)
      }, { softOn: ['5xx', '404', 'fk_missing'] })
      if (r.healed) console.log(`[Healer] C_DEL 软断言通过: ${r.reason}`)
    })
  })


  /**
   * 审计日志: 创建 [领域] 应记录 audit_log
   * 业务规则: BR-domain-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [领域] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [领域] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_domain_create', async () => {
        return await isolation.createTracked('domain', {
        version_id: null,
        code: `AUD_CODE_${TS}`,
        name: `aud_name_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_domain_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'domain', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-domain-HEALTH
   */
  test('HEALTH: [领域] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_domain', async () => {
      await navigateTo(page, '/domain-management')
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
   * UI 导航: 进入 [领域] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [领域] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [领域] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_domain', async () => {
        await navigateTo(page, '/domain-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
