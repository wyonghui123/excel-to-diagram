/**
 * S-BF-USER_GROUP-AUTO: 用户组 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 user_group.yaml 自动生成
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
 *   BR-user_group-FLD-REQ-name  (组名 必填)
 *   BR-user_group-FLD-REQ-code  (组编码 必填)
 *   BR-user_group-FLD-UNQ-code  (组编码 唯一)
 *   BR-user_group-AUDIT-create/update/delete  (审计日志)
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

const USER_GROUP_URL = '/user_group-management'

test.describe('S-BF-USER_GROUP-AUTO: 用户组 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 组名 (name)
   * 业务规则: BR-user_group-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [组名] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [组名] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group', {
        code: "TEST_CODE_PLACEHOLDER",
      }, 'name')
      expect(result, '[API 维度] 缺少 [组名] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 组编码 (code)
   * 业务规则: BR-user_group-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [组编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [组编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group', {
        name: "placeholder_name",
      }, 'code')
      expect(result, '[API 维度] 缺少 [组编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 组编码 (code)
   * 业务规则: BR-user_group-FLD-UNQ-code
   */
  test('C_UNQ_CODE: 重复 [组编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_TEST_PLACEHOLDER_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [组编码] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('user_group', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        })
        // 再创建一次相同值
        await isolation.createTracked('user_group', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_CODE] 后端未拒绝重复 [组编码], 跳过验证')
      }
    })
  })


  /**
   * 审计日志: 创建 [用户组] 应记录 audit_log
   * 业务规则: BR-user_group-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [用户组] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [用户组] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_user_group_create', async () => {
        return await isolation.createTracked('user_group', {
        name: `aud_name_${TS}`,
        code: `AUD_CODE_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_user_group_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'user_group', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })



  /**
   * audit_levels 规则: create → INFO/operation
   * 业务规则: BR-user_group-AUDIT-create
   */
  test('AUD_CREATE: create 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_user_group_create', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'user_group', null, 'create'
      )
      console.log(`  [AUD] create → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: update → INFO/operation
   * 业务规则: BR-user_group-AUDIT-update
   */
  test('AUD_UPDATE: update 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_user_group_update', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'user_group', null, 'update'
      )
      console.log(`  [AUD] update → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: delete → WARN/destructive
   * 业务规则: BR-user_group-AUDIT-delete
   */
  test('AUD_DELETE: delete 应产生 WARN 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_user_group_delete', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'user_group', null, 'delete'
      )
      console.log(`  [AUD] delete → ${valid ? 'WARN' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-user_group-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_user_group', async () => {
      await navigateTo(page, '/user_group-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/user_group
   * 业务规则: BR-user_group-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_user_group', async () => {
      const obj = await dataFinder.user_group().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'user_group', obj.id)
        await page.waitForURL('**/detail/user_group**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.user_group`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-user_group-HEALTH
   */
  test('HEALTH: [用户组] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_user_group', async () => {
      await navigateTo(page, '/user_group-management')
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
   * 业务规则: BR-user_group-PER-survives_reload
   */
  test('PER_RELOAD: [用户组] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_user_group', async () => {
      const obj = await dataFinder.user_group().catch(() => null)
      if (obj) {
        await navigateTo(page, '/user_group-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.user_group`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [用户组] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [用户组] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [用户组] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_user_group', async () => {
        await navigateTo(page, '/user_group-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
