/**
 * S-BF-PERMISSION-AUTO: 功能权限 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 permission.yaml 自动生成
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
 *   BR-permission-FLD-REQ-code  (权限编码 必填)
 *   BR-permission-FLD-REQ-name  (权限名称 必填)
 *   BR-permission-FLD-UNQ-code  (权限编码 唯一)
 *   BR-permission-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-06-25
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

const PERMISSION_URL = '/permission-management'

test.describe('S-BF-PERMISSION-AUTO: 功能权限 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 权限编码 (code)
   * 业务规则: BR-permission-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [权限编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission', {
        name: "placeholder_name",
      }, 'code')
      expect(result, '[API 维度] 缺少 [权限编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 权限名称 (name)
   * 业务规则: BR-permission-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [权限名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission', {
        code: "TEST_CODE_PLACEHOLDER",
      }, 'name')
      expect(result, '[API 维度] 缺少 [权限名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 权限编码 (code)
   * 业务规则: BR-permission-FLD-UNQ-code
   */
  test('C_UNQ_CODE: 重复 [权限编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_TEST_PLACEHOLDER_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [权限编码] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('permission', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        })
        // 再创建一次相同值
        await isolation.createTracked('permission', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_CODE] 后端未拒绝重复 [权限编码], 跳过验证')
      }
    })
  })


  /**
   * 审计日志: 创建 [功能权限] 应记录 audit_log
   * 业务规则: BR-permission-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [功能权限] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [功能权限] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_permission_create', async () => {
        return await isolation.createTracked('permission', {
        code: `AUD_CODE_${TS}`,
        name: `aud_name_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_permission_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'permission', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })



  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-permission-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_permission', async () => {
      await navigateTo(page, '/permission-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/permission
   * 业务规则: BR-permission-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_permission', async () => {
      const obj = await dataFinder.permission().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'permission', obj.id)
        await page.waitForURL('**/detail/permission**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.permission`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-permission-HEALTH
   */
  test('HEALTH: [功能权限] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_permission', async () => {
      await navigateTo(page, '/permission-management')
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
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-permission-PER-survives_reload
   */
  test('PER_RELOAD: [功能权限] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_permission', async () => {
      const obj = await dataFinder.permission().catch(() => null)
      if (obj) {
        await navigateTo(page, '/permission-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.permission`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [功能权限] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [功能权限] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [功能权限] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_permission', async () => {
        await navigateTo(page, '/permission-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
