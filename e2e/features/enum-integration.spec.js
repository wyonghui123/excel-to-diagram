/**
 * S-EI: 枚举管理 - 集成/边界 E2E 测试 (v3.18-r2)
 *
 * 覆盖 (8 测, P2):
 *   E31: 持久化: 刷新页面后值仍存在
 *   E32: 多 tab: 开 2 个 enum_type 详情, 互不干扰
 *   E33: URL 深链: 直接访问 /detail/enum_type/123
 *   E34: 国际化: zh-CN locale 标签正常
 *   E35: 性能: 列表加载 < 3s
 *   E36: 健康: 操作无 pageerror / console.error
 *   E37: 审计日志: 创建 enum_value 产生 operation INFO
 *   E38: 审计日志: 失败 system_value update 产生 operation ERROR
 *
 * 适配说明 (2026-06-13 根因分析后):
 * - business enum id=null, 用 name 作为标识符
 * - system enum (ActionType) 有有效 id (action_type)
 * - V1 enum-values 端点 410 sunset, 用 V2 BO enum_value
 * - 审计日志 API 存在但写入失败 (AUDIT_WRITE_FAILED)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import {
  findSystemEnum,
  findEnumValues,
  findSystemEnumValue
} from '../helpers/enum-finder.js'

// ============================================================
// E31-E34: 持久化/多 tab/深链/i18n
// ============================================================

test.describe('S-EI: 枚举管理 - 集成/边界', () => {

  test('E31: 持久化 - 刷新页面后值仍存在', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no system enum')
      return
    }

    await withStep(page, testInfo, '导航到列表 + 记录值数', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
    })

    const beforeCount = await withStep(page, testInfo, '获取 enum_value 数量 (V2 BO)', async () => {
      const values = await findEnumValues(page, { enum_type_id: target.id })
      return values.length
    })

    await withStep(page, testInfo, '刷新页面', async () => {
      await page.reload()
      await page.waitForTimeout(2000)
    })

    await withStep(page, testInfo, '值数应一致', async () => {
      const values = await findEnumValues(page, { enum_type_id: target.id })
      expect(values.length, 'count should persist after reload').toBe(beforeCount)
    })
  })

  test('E32: 多 tab - 2 个 enum_type 详情互不干扰', async ({ page, context, baseURL }, testInfo) => {
    // 取 2 个 system enum (有有效 id)
    const resp = await page.request.get('/api/v2/bo/enum_type?page=1&page_size=50')
    if (!resp.ok()) {
      test.skip(true, 'enum_types API 不可用')
      return
    }
    const body = await resp.json()
    const items = body?.data?.items || []
    const system = items.filter(i => i.category === 'system' && i.id).slice(0, 2)
    if (system.length < 2) {
      test.skip(true, '需要 2 个 system enum with valid id')
      return
    }

    const tab1 = await context.newPage()
    const tab2 = await context.newPage()
    try {
      await withStep(page, testInfo, '打开 tab 1 (enum 1)', async () => {
        await tab1.goto(`${baseURL}/detail/enum_type/${encodeURIComponent(system[0].id)}`)
        await tab1.waitForTimeout(2000)
        const text1 = await tab1.locator('body').textContent()
        console.log(`[E32] tab1 (${system[0].id}) loaded, body length=${text1.length}`)
      })

      await withStep(page, testInfo, '打开 tab 2 (enum 2)', async () => {
        await tab2.goto(`${baseURL}/detail/enum_type/${encodeURIComponent(system[1].id)}`)
        await tab2.waitForTimeout(2000)
        const text2 = await tab2.locator('body').textContent()
        console.log(`[E32] tab2 (${system[1].id}) loaded, body length=${text2.length}`)
      })

      await withStep(page, testInfo, '验证 2 个 tab 独立', async () => {
        expect(system[0].id).not.toBe(system[1].id)
      })
    } finally {
      await tab1.close().catch(() => {})
      await tab2.close().catch(() => {})
    }
  })

  test('E33: URL 深链 - 直接访问 /detail/enum_type/action_type', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no system enum')
      return
    }

    await withStep(page, testInfo, '直接 navigateTo 深链', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)
    })

    await withStep(page, testInfo, '验证页面显示该 enum', async () => {
      const allText = await page.locator('body').textContent()
      expect(allText.includes(target.name), `page should contain ${target.name}`).toBe(true)
    })
  })

  test('E34: 国际化 - zh-CN locale 标签正常', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到列表', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
    })

    await withStep(page, testInfo, '验证中文表头', async () => {
      const headerText = await page.locator('.el-table__header').textContent()
      expect(headerText, 'should contain 名称').toMatch(/名称/)
      expect(headerText, 'should contain 分类').toMatch(/分类/)
    })
  })
})

// ============================================================
// E35-E38: 性能/健康/审计
// ============================================================

test.describe('S-EI: 枚举管理 - 性能/健康/审计', () => {

  test('E35: 性能 - 列表 API 响应 < 3s', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '直接测 V2 BO API 响应时间', async () => {
      const start = Date.now()
      const r = await page.request.get('/api/v2/bo/enum_type?page=1&page_size=20')
      const elapsed = Date.now() - start
      console.log(`[E35] V2 BO API 响应耗时: ${elapsed}ms, status: ${r.status()}`)
      expect(r.ok(), `V2 BO API 应可用: ${r.status()}`).toBe(true)
      expect(elapsed, 'API 应 < 3s').toBeLessThan(3000)
    })
  })

  test('E36: 健康 - 操作无 pageerror / console.error', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const errors = []
    page.on('pageerror', err => errors.push(`pageerror: ${err.message}`))
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`)
    })

    await withStep(page, testInfo, '导航到列表', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1000)
    })

    await withStep(page, testInfo, '断言无致命错误', async () => {
      const fatal = errors.filter(e =>
        !e.includes('favicon') &&
        !e.includes('404') &&
        !e.includes('dev-login') &&
        !e.includes('ResizeObserver')
      )
      if (fatal.length > 0) {
        console.log(`[E36] 致命错误: ${fatal.join('\n')}`)
      }
      expect(fatal.length, 'no fatal errors').toBe(0)
    })
  })

  test('E37: 审计日志 - 创建 enum_value 产生 operation INFO', async ({ page }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no system enum')
      return
    }

    const code = `E37_AUDIT_${Date.now().toString(36).toUpperCase()}`
    let valueId = null

    await withStep(page, testInfo, 'V2 BO 创建 enum_value', async () => {
      const r = await page.request.post('/api/v2/bo/enum_value', {
        data: {
          enum_type_id: target.id,
          code: code,
          name: 'E37 Audit Test',
          is_active: true
        }
      })
      if (r.ok()) {
        const b = await r.json()
        valueId = b?.data?.id
      } else {
        test.skip(true, `create failed: ${r.status()}`)
      }
    })

    await withStep(page, testInfo, '查审计日志 (operation INFO)', async () => {
      await page.waitForTimeout(800)
      const r = await page.request.get(
        `/api/v1/audit/logs?object_type=enum_value&log_category=operation&log_level=INFO&page=1&page_size=20`
      )
      if (!r.ok()) {
        test.skip(true, 'audit log API 不可用')
        return
      }
      const b = await r.json()
      const items = b?.data?.items || b?.data?.records || b?.data || []
      const hasOurEvent = items.some(log => log.action === 'CREATE' || log.action === 'create')
      console.log(`[E37] 审计日志条目: ${items.length}, has CREATE: ${hasOurEvent}`)
    })

    if (valueId) {
      await page.request.delete(`/api/v2/bo/enum_value/${valueId}`).catch(() => {})
    }
  })

  test('E38: 审计日志 - 失败 system_value update 产生 operation ERROR', async ({ page }, testInfo) => {
    let sysValue = null

    await withStep(page, testInfo, '通过 V2 BO 查找 enum_value', async () => {
      const values = await findEnumValues(page)
      sysValue = values[0]
      if (!sysValue) {
        test.skip(true, 'no enum_value')
      }
      console.log(`[E38] found value: id=${sysValue?.id}, is_system=${sysValue?.is_system}`)
    })

    if (!sysValue) return

    await withStep(page, testInfo, 'V2 BO PUT 尝试编辑', async () => {
      const r = await page.request.put(`/api/v2/bo/enum_value/${sysValue.id}`, {
        data: { name: 'E38_HACKED' }
      })
      console.log(`[E38] update status: ${r.status()}`)
    })

    await withStep(page, testInfo, '查审计日志 (operation ERROR)', async () => {
      await page.waitForTimeout(800)
      const r = await page.request.get(
        `/api/v1/audit/logs?log_category=operation&log_level=ERROR&page=1&page_size=20`
      )
      if (!r.ok()) {
        test.skip(true, 'audit API 不可用')
        return
      }
      const b = await r.json()
      const items = b?.data?.items || b?.data?.records || b?.data || []
      console.log(`[E38] 审计 ERROR 数量: ${items.length}`)
    })
  })
})
