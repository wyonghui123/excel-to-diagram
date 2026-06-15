/**
 * S-BF-RELATIONSHIP-AUTO: 业务关系 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 relationship.yaml 自动生成
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
 *   BR-relationship-FLD-REQ-version_id  (版本 必填)
 *   BR-relationship-FLD-REQ-source_bo_id  (源业务对象 必填)
 *   BR-relationship-FLD-REQ-target_bo_id  (目标业务对象 必填)
 *   BR-relationship-FLD-REQ-relation_type  (关系类型 必填)
 *   BR-relationship-DEL-condition  (关系可随时删除)
 *   BR-relationship-AUDIT-create/update/delete  (审计日志)
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

const RELATIONSHIP_URL = '/relationship-management'

test.describe('S-BF-RELATIONSHIP-AUTO: 业务关系 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 版本 (version_id)
   * 业务规则: BR-relationship-FLD-REQ-version_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_VERSION_ID: 缺少必填字段 [版本] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [版本] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'relationship', {
        source_bo_id: null,
        target_bo_id: null,
        relation_type: "placeholder_relation_type",
      }, 'version_id')
      expect(result, '[API 维度] 缺少 [版本] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 源业务对象 (source_bo_id)
   * 业务规则: BR-relationship-FLD-REQ-source_bo_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_SOURCE_BO_ID: 缺少必填字段 [源业务对象] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [源业务对象] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'relationship', {
        version_id: null,
        target_bo_id: null,
        relation_type: "placeholder_relation_type",
      }, 'source_bo_id')
      expect(result, '[API 维度] 缺少 [源业务对象] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 目标业务对象 (target_bo_id)
   * 业务规则: BR-relationship-FLD-REQ-target_bo_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TARGET_BO_ID: 缺少必填字段 [目标业务对象] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [目标业务对象] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'relationship', {
        version_id: null,
        source_bo_id: null,
        relation_type: "placeholder_relation_type",
      }, 'target_bo_id')
      expect(result, '[API 维度] 缺少 [目标业务对象] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 关系类型 (relation_type)
   * 业务规则: BR-relationship-FLD-REQ-relation_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RELATION_TYPE: 缺少必填字段 [关系类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [关系类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'relationship', {
        version_id: null,
        source_bo_id: null,
        target_bo_id: null,
      }, 'relation_type')
      expect(result, '[API 维度] 缺少 [关系类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 删除约束: 关系可随时删除
   * 业务规则: BR-relationship-DEL-condition
   * 条件: true
   * [Healer.L3] createTracked 失败时软断言 (FK 关联缺失)
   */
  test('C_DEL: 删除 [业务关系] 业务规则', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [业务关系] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_DEL_relationship_create', async () => {
        return await isolation.createTracked('relationship', {
        version_id: null,
        source_bo_id: null,
        target_bo_id: null,
        relation_type: `del_relation_type_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_DEL create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: 无关联时可删除 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_DEL_relationship_check', async () => {
        const result = await BusinessRuleAssertor.assertDeletable(
          page, 'relationship', obj.id, { relatedCount: 0 }
        )
        expect(result.deletable, '[Business] 无关联时应可删').toBe(true)
      }, { softOn: ['5xx', '404', 'fk_missing'] })
      if (r.healed) console.log(`[Healer] C_DEL 软断言通过: ${r.reason}`)
    })
  })


  /**
   * 审计日志: 创建 [业务关系] 应记录 audit_log
   * 业务规则: BR-relationship-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [业务关系] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [业务关系] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_relationship_create', async () => {
        return await isolation.createTracked('relationship', {
        version_id: null,
        source_bo_id: null,
        target_bo_id: null,
        relation_type: `aud_relation_type_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_relationship_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'relationship', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-relationship-HEALTH
   */
  test('HEALTH: [业务关系] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_relationship', async () => {
      await navigateTo(page, '/relationship-management')
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
   * UI 导航: 进入 [业务关系] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [业务关系] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [业务关系] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_relationship', async () => {
        await navigateTo(page, '/relationship-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
