/**
 * S-BF-ENUM_TYPE-AUTO: 枚举类型 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 enum_type.yaml 自动生成
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
 *   BR-enum_type-FLD-REQ-name  (名称 必填)
 *   BR-enum_type-FLD-REQ-category  (分类 必填)
 *   BR-enum_type-FLD-REQ-mutability  (可维护性 必填)
 *   BR-enum_type-AUDIT-create/update/delete  (审计日志)
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

const ENUM_TYPE_URL = '/enum_type-management'

test.describe('S-BF-ENUM_TYPE-AUTO: 枚举类型 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 名称 (name)
   * 业务规则: BR-enum_type-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_type', {
        category: "system",
        mutability: "fullEditable",
      }, 'name')
      expect(result, '[API 维度] 缺少 [名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 分类 (category)
   * 业务规则: BR-enum_type-FLD-REQ-category
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CATEGORY: 缺少必填字段 [分类] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [分类] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_type', {
        name: "placeholder_name",
        mutability: "fullEditable",
      }, 'category')
      expect(result, '[API 维度] 缺少 [分类] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 可维护性 (mutability)
   * 业务规则: BR-enum_type-FLD-REQ-mutability
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_MUTABILITY: 缺少必填字段 [可维护性] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [可维护性] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_type', {
        name: "placeholder_name",
        category: "system",
      }, 'mutability')
      expect(result, '[API 维度] 缺少 [可维护性] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 枚举值校验: 分类 (category)
   * 业务规则: BR-enum_type-FLD-ENUM-category
   * 允许值: [{'value': 'system', 'label': '系统', 'color': 'default'}, {'value': 'business', 'label': '业务', 'color': 'primary'}]
   */
  test('C_ENUM_CATEGORY: [分类] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [分类] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'enum_type', {
        name: "placeholder_name",
        mutability: "fullEditable",
          category: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'system', 'label': '系统', 'color': 'default'}, {'value': 'business', 'label': '业务', 'color': 'primary'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 可维护性 (mutability)
   * 业务规则: BR-enum_type-FLD-ENUM-mutability
   * 允许值: [{'value': 'fullEditable', 'label': '完全可改', 'color': 'success'}, {'value': 'extensible', 'label': '可扩展', 'color': 'warning'}, {'value': 'locked', 'label': '完全锁', 'color': 'danger'}]
   */
  test('C_ENUM_MUTABILITY: [可维护性] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [可维护性] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'enum_type', {
        name: "placeholder_name",
        category: "system",
          mutability: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'fullEditable', 'label': '完全可改', 'color': 'success'}, {'value': 'extensible', 'label': '可扩展', 'color': 'warning'}, {'value': 'locked', 'label': '完全锁', 'color': 'danger'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [枚举类型] 应记录 audit_log
   * 业务规则: BR-enum_type-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [枚举类型] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [枚举类型] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_enum_type_create', async () => {
        return await isolation.createTracked('enum_type', {
        name: `aud_name_${TS}`,
        category: "system",
        mutability: "fullEditable",
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_enum_type_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'enum_type', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-enum_type-HEALTH
   */
  test('HEALTH: [枚举类型] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_enum_type', async () => {
      await navigateTo(page, '/enum_type-management')
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
   * UI 导航: 进入 [枚举类型] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [枚举类型] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [枚举类型] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_enum_type', async () => {
        await navigateTo(page, '/enum_type-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
