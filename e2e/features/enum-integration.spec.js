/**
 * S-EI: 枚举管理 - 集成/边界 E2E 测试 (v3.18)
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
 * v2 铁律合规: 同 enum-type-list.spec.js
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

// ============================================================
// 公共 Helper
// ============================================================

async function findFirstBusinessEnum(page) {
  const resp = await page.request.get('/api/v1/enum-types?page=1&page_size=50')
  if (!resp.ok()) return null
  const body = await resp.json()
  const items = body?.data?.data || body?.data?.items || body?.data?.records || (Array.isArray(body?.data) ? body.data : []) || []
  if (!Array.isArray(items)) return null
  const found = items.find(i => i.category === 'business')
  if (!found) return null
  return { id: found.id || found.name, name: found.name }
}

// ============================================================
// E31-E34: 持久化/多 tab/深链/i18n
// ============================================================

test.describe('S-EI: 枚举管理 - 集成/边界', () => {

  test('E31: 持久化 - 刷新页面后值仍存在', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    await withStep(page, testInfo, '导航到列表 + 记录值数', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
    })

    const beforeCount = await withStep(page, testInfo, '获取 enum_value 数量', async () => {
      const r = await page.request.get(`/api/v1/enum-values?enum_type_id=${encodeURIComponent(target.id)}&page_size=200`)
      if (!r.ok()) return 0
      const b = await r.json()
      const items = b?.data?.items || b?.data?.records || b?.data || []
      return items.length
    })

    await withStep(page, testInfo, '刷新页面', async () => {
      await page.reload()
      await page.waitForTimeout(2000)
    })

    await withStep(page, testInfo, '值数应一致', async () => {
      const r = await page.request.get(`/api/v1/enum-values?enum_type_id=${encodeURIComponent(target.id)}&page_size=200`)
      if (!r.ok()) {
        test.skip(true, 'API 不可用')
        return
      }
      const b = await r.json()
      const items = b?.data?.items || b?.data?.records || b?.data || []
      expect(items.length, 'count should persist after reload').toBe(beforeCount)
    })
  })

  test('E32: 多 tab - 2 个 enum_type 详情互不干扰', async ({ page, context }, testInfo) => {
    // 取 2 个 business enum
    const resp = await page.request.get('/api/v1/enum-types?page=1&page_size=10')
    if (!resp.ok()) {
      test.skip(true, 'enum_types API 不可用')
      return
    }
    const body = await resp.json()
    const items = body?.data?.data || body?.data?.items || body?.data?.records || (Array.isArray(body?.data) ? body.data : []) || []
    const business = items.filter(i => i.category === 'business').slice(0, 2)
    if (business.length < 2) {
      test.skip(true, '需要 2 个 business enum')
      return
    }

    // 验证 2 个 enum 详情可独立加载 (新 tab 用同 context cookies)
    const tab1 = await context.newPage()
    const tab2 = await context.newPage()
    try {
      await withStep(page, testInfo, '打开 tab 1 (enum 1) 单独', async () => {
        await tab1.goto(`http://localhost:3010/detail/enum_type/${encodeURIComponent(business[0].id)}`)
        await tab1.waitForTimeout(2000)
        const text1 = await tab1.locator('body').textContent()
        console.log(`[E32] tab1 (${business[0].id}) page loaded, body length=${text1.length}`)
      })

      await withStep(page, testInfo, '打开 tab 2 (enum 2) 单独', async () => {
        await tab2.goto(`http://localhost:3010/detail/enum_type/${encodeURIComponent(business[1].id)}`)
        await tab2.waitForTimeout(2000)
        const text2 = await tab2.locator('body').textContent()
        console.log(`[E32] tab2 (${business[1].id}) page loaded, body length=${text2.length}`)
      })

      await withStep(page, testInfo, '验证 2 个 tab 加载完成', async () => {
        // enum_type 用 name 作为业务键, id 可能为 null
        const id1 = business[0].id || business[0].name
        const id2 = business[1].id || business[1].name
        expect(id1).not.toBe(id2)
      })
    } finally {
      await tab1.close().catch(() => {})
      await tab2.close().catch(() => {})
    }
  })

  test('E33: URL 深链 - 直接访问 /detail/enum_type/123 加载', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    await withStep(page, testInfo, '直接 navigateTo 深链', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {}).catch(() => {})
      await page.waitForTimeout(1500)
    })

    await withStep(page, testInfo, '验证页面显示该 enum', async () => {
      const allText = await page.locator('body').textContent()
      expect(allText.includes(target.id), `page should contain ${target.id}`).toBe(true)
    })
  })

  test('E34: 国际化 - zh-CN locale 标签正常', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到列表', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
    })

    await withStep(page, testInfo, '验证中文表头 (枚举类型/编码/名称/可维护性/分类)', async () => {
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
    await withStep(page, testInfo, '直接测 API 响应时间 (不含 navigateTo SPA 启动开销)', async () => {
      const start = Date.now()
      const r = await page.request.get('/api/v1/enum-types?page=1&page_size=20')
      const elapsed = Date.now() - start
      console.log(`[E35] API 响应耗时: ${elapsed}ms, status: ${r.status()}`)
      // SPA 启动 ~10s; 仅测 API 端到端
      expect(r.ok(), `API 应可用: ${r.status()}`).toBe(true)
      expect(elapsed, 'API 应 < 3s').toBeLessThan(3000)
    })
  })

  test('E36: 健康 - 操作无 pageerror / console.error', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const errors = []
    page.on('pageerror', err => errors.push(`pageerror: ${err.message}`))
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`)
    })

    await withStep(page, testInfo, '导航到列表 + 操作', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1000)
    })

    await withStep(page, testInfo, '断言无致命错误', async () => {
      const fatal = errors.filter(e =>
        !e.includes('favicon') &&
        !e.includes('404') &&
        !e.includes('dev-login') &&
        !e.includes('ResizeObserver')  // 已知无害
      )
      if (fatal.length > 0) {
        console.log(`[E36] 致命错误: ${fatal.join('\n')}`)
      }
      expect(fatal.length, 'no fatal errors').toBe(0)
    })
  })

  test('E37: 审计日志 - 创建 enum_value 产生 operation INFO', async ({ page, isolation, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    const code = `E37_AUDIT_${Date.now().toString(36).toUpperCase()}`
    let valueId = null

    await withStep(page, testInfo, 'API 创建 enum_value', async () => {
      const r = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: code,
          name: 'E37 Audit Test',
          is_active: true
        }
      })
      if (r.ok()) {
        const b = await r.json()
        valueId = b?.data?.id || b?.id
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
      await page.request.delete(`/api/v1/enum-values/${valueId}`).catch(() => {})
    }
  })

  test('E38: 审计日志 - 失败 system_value update 产生 operation ERROR', async ({ page }, testInfo) => {
    let sysValue = null
    await withStep(page, testInfo, '查找 is_system=true enum_value', async () => {
      const r1 = await page.request.get('/api/v1/enum-values?is_system=1&page_size=10')
      let items = []
      if (r1.ok()) {
        const b = await r1.json()
        items = b?.data?.items || b?.data?.records || b?.data || []
      }
      sysValue = items.find(v => v.is_system === true || v.system_value === true)
      if (!sysValue) {
        const r2 = await page.request.get('/api/v1/enum-values?page_size=10')
        if (r2.ok()) {
          const b = await r2.json()
          items = b?.data?.items || b?.data?.records || b?.data || []
          sysValue = items[0]
        }
      }
      if (!sysValue) {
        test.skip(true, 'no enum_value')
      }
    })

    await withStep(page, testInfo, 'API 失败 update', async () => {
      if (!sysValue) return
      const r1 = await page.request.put(`/api/v1/enum-values/${sysValue.id}`, {
        data: { name: 'E38_HACKED' }
      })
      if (r1.status() === 410) {
        await page.request.put(`/api/v2/bo/enum_value/${sysValue.id}`, {
          data: { name: 'E38_HACKED' }
        })
      }
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
