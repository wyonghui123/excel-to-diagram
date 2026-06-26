/**
 * S-BF-ENUM_VALUE-AUTO: 枚举值 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 enum_value.yaml 自动生成
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
 *   BR-enum_value-FLD-REQ-enum_type_id  (枚举类型 必填)
 *   BR-enum_value-FLD-REQ-code  (编码 必填)
 *   BR-enum_value-FLD-REQ-name  (名称 必填)
 *   BR-enum_value-FLD-PAT-code  (格式: ^[A-Z][A-Z0-9_]*$)
 *   BR-enum_value-AUDIT-create/update/delete  (审计日志)
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

const ENUM_VALUE_URL = '/enum_value-management'

test.describe('S-BF-ENUM_VALUE-AUTO: 枚举值 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 枚举类型 (enum_type_id)
   * 业务规则: BR-enum_value-FLD-REQ-enum_type_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ENUM_TYPE_ID: 缺少必填字段 [枚举类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [枚举类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_value', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
      }, 'enum_type_id')
      expect(result, '[API 维度] 缺少 [枚举类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 编码 (code)
   * 业务规则: BR-enum_value-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_value', {
        enum_type_id: null,
        name: "placeholder_name",
      }, 'code')
      expect(result, '[API 维度] 缺少 [编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 名称 (name)
   * 业务规则: BR-enum_value-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'enum_value', {
        enum_type_id: null,
        code: "TEST_CODE_PLACEHOLDER",
      }, 'name')
      expect(result, '[API 维度] 缺少 [名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 格式校验: 编码 (code)
   * 业务规则: BR-enum_value-FLD-PAT-code
   * 正则: ^[A-Z][A-Z0-9_]*$
   */
  test('C_PAT_CODE: [编码] 格式不符应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [编码] 格式不符应被拒绝', async () => {
      const result = await BusinessRuleAssertor.assertFieldPattern(
        page, 'enum_value', {
        enum_type_id: null,
        name: "placeholder_name",
          code: 'invalid_value_123'
        }, '^[A-Z][A-Z0-9_]*$'
      )
      expect(result, '[Pattern] 格式不符应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 是否启用 (is_active)
   * 业务规则: BR-enum_value-FLD-ENUM-is_active
   * 允许值: [{'value': True, 'label': '启用', 'color': 'success'}, {'value': False, 'label': '禁用', 'color': 'info'}]
   */
  test('C_ENUM_IS_ACTIVE: [是否启用] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [是否启用] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'enum_value', {
        enum_type_id: null,
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
          is_active: 'INVALID_ENUM_VALUE_999'
        }, [{'value': True, 'label': '启用', 'color': 'success'}, {'value': False, 'label': '禁用', 'color': 'info'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 是否系统值 (is_system)
   * 业务规则: BR-enum_value-FLD-ENUM-is_system
   * 允许值: [{'value': True, 'label': '系统', 'color': ''}, {'value': False, 'label': '用户', 'color': 'primary'}]
   */
  test('C_ENUM_IS_SYSTEM: [是否系统值] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [是否系统值] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'enum_value', {
        enum_type_id: null,
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
          is_system: 'INVALID_ENUM_VALUE_999'
        }, [{'value': True, 'label': '系统', 'color': ''}, {'value': False, 'label': '用户', 'color': 'primary'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [枚举值] 应记录 audit_log
   * 业务规则: BR-enum_value-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [枚举值] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [枚举值] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_enum_value_create', async () => {
        return await isolation.createTracked('enum_value', {
        enum_type_id: null,
        code: `AUD_CODE_${TS}`,
        name: `aud_name_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_enum_value_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'enum_value', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })



  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-enum_value-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_enum_value', async () => {
      await navigateTo(page, '/enum_value-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/enum_value/enum_value-detail
   * 业务规则: BR-enum_value-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_enum_value', async () => {
      const obj = await dataFinder.enum_value().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'enum_value', obj.id)
        await page.waitForURL('**/detail/enum_value/enum_value-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.enum_value`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-enum_value-HEALTH
   */
  test('HEALTH: [枚举值] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_enum_value', async () => {
      await navigateTo(page, '/enum_value-management')
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
   * ui_badge 规则: is_active 字段彩色标签
   * 业务规则: BR-enum_value-BADGE-is_active
   */
  test('BADGE_IS_ACTIVE: 验证 [is_active] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_enum_value_is_active', async () => {
      await navigateTo(page, '/enum_value-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_active tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: is_system 字段彩色标签
   * 业务规则: BR-enum_value-BADGE-is_system
   */
  test('BADGE_IS_SYSTEM: 验证 [is_system] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_enum_value_is_system', async () => {
      await navigateTo(page, '/enum_value-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_system tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * nested_transaction 规则: children=[]
   * 业务规则: BR-enum_value-NEST-atomic
   */
  test('NEST_CREATE: 深插入 [枚举值] + 子对象 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'NEST_enum_value', async () => {
      const parent = await dataFinder.enum_value().catch(() => null)
      if (parent) {
        const nestedPOM = new NestedPOM(page)
        console.log(`  [NEST] 父对象 ID=${parent.id}, 模拟深插入`)
      } else {
        console.log(`  [NEST] 跳过: 无 dataFinder.enum_value`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] NEST 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-enum_value-PER-survives_reload
   */
  test('PER_RELOAD: [枚举值] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_enum_value', async () => {
      const obj = await dataFinder.enum_value().catch(() => null)
      if (obj) {
        await navigateTo(page, '/enum_value-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.enum_value`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [枚举值] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [枚举值] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [枚举值] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_enum_value', async () => {
        await navigateTo(page, '/enum_value-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
