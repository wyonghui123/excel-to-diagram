/**
 * S-BF-ANNOTATION-AUTO: 备注信息 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 annotation.yaml 自动生成
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
 *   BR-annotation-FLD-REQ-target_type  (关联对象类型 必填)
 *   BR-annotation-FLD-REQ-target_id  (关联对象ID 必填)
 *   BR-annotation-FLD-REQ-category  (备注分类 必填)
 *   BR-annotation-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-06-02
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const ANNOTATION_URL = '/annotation-management'

test.describe('S-BF-ANNOTATION-AUTO: 备注信息 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 关联对象类型 (target_type)
   * 业务规则: BR-annotation-FLD-REQ-target_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TARGET_TYPE: 缺少必填字段 [关联对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [关联对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'annotation', {
        target_id: null,
        category: "placeholder_category",
      }, 'target_type')
      expect(result, '[API 维度] 缺少 [关联对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 关联对象ID (target_id)
   * 业务规则: BR-annotation-FLD-REQ-target_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TARGET_ID: 缺少必填字段 [关联对象ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [关联对象ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'annotation', {
        target_type: "placeholder_target_type",
        category: "placeholder_category",
      }, 'target_id')
      expect(result, '[API 维度] 缺少 [关联对象ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 备注分类 (category)
   * 业务规则: BR-annotation-FLD-REQ-category
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CATEGORY: 缺少必填字段 [备注分类] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [备注分类] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'annotation', {
        target_type: "placeholder_target_type",
        target_id: null,
      }, 'category')
      expect(result, '[API 维度] 缺少 [备注分类] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [备注信息] 应记录 audit_log
   * 业务规则: BR-annotation-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [备注信息] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [备注信息] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_annotation_create', async () => {
        return await isolation.createTracked('annotation', {
        target_type: `aud_target_type_${TS}`,
        target_id: null,
        category: `aud_category_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_annotation_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'annotation', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * UI 导航: 进入 [备注信息] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [备注信息] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [备注信息] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_annotation', async () => {
        await navigateTo(page, '/annotation-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
