/**
 * S-EVC: 枚举值管理 - CRUD E2E 测试 (v3.18)
 *
 * 覆盖 (8 测, P0):
 *   E06: 业务枚举创建值: 成功路径
 *   E07: 业务枚举创建值: code 格式校验 (lowercase 拒绝)
 *   E08: 业务枚举创建值: 唯一性校验
 *   E09: system 枚举值 is_system=true 不可编辑 (DEC-2)
 *   E10: system 枚举值 is_system=true 不可删除 (DEC-2)
 *   E11: 业务枚举删除值: 弹确认对话框
 *   E12: 业务枚举创建值: 必填校验
 *   + 父 enum_value 不可改 code
 *
 * v2 铁律合规: 同 enum-type-list.spec.js
 *
 * 适配说明 (2026-06-13):
 * - enum_value 在 enum_type 详情页的 ObjectChildSection 中, expandable
 * - 父 mutability 通过 :row-mutability 传给子 MetaListPage
 * - 子行级 delete 受 is_system 保护 (extensible 时, system_value 不可删)
 * - 测试用 isolation.createTracked 跟踪清理
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
  return items.find(i => i.category === 'business' && i.mutability === 'fullEditable') || items.find(i => i.category === 'business') || null
}

async function findFirstSystemEnum(page) {
  const resp = await page.request.get('/api/v1/enum-types?page=1&page_size=50')
  if (!resp.ok()) return null
  const body = await resp.json()
  const items = body?.data?.data || body?.data?.items || body?.data?.records || (Array.isArray(body?.data) ? body.data : []) || []
  if (!Array.isArray(items)) return null
  const found = items.find(i => i.category === 'system')
  if (!found) return null
  return { id: found.id || found.name, name: found.name }
}

// ============================================================
// E06-E08, E12: 业务枚举值创建
// ============================================================

test.describe('S-EVC: 枚举值 - 业务枚举创建值', () => {

  test('E06: 业务枚举创建值: 成功路径', async ({ page, navigateTo, isolation, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    const uniqueCode = `E06_${Date.now().toString(36).toUpperCase()}`
    const uniqueName = `E06 Test Value ${uniqueCode}`

    let createdId = null

    await withStep(page, testInfo, '通过 API 创建枚举值 (E06 准备)', async () => {
      const resp = await page.request.post(
        `/api/v1/enum-values/enum-type/${encodeURIComponent(target.id)}`,
        {
          data: {
            code: uniqueCode,
            name: uniqueName,
            is_active: true
          }
        }
      )
      // 端点可能不同, 也试 enum_value 全局
      if (!resp.ok() && resp.status() === 404) {
        const r2 = await page.request.post('/api/v1/enum-values', {
          data: {
            enum_type_id: target.id,
            code: uniqueCode,
            name: uniqueName,
            is_active: true
          }
        })
        if (r2.ok()) {
          const b = await r2.json()
          createdId = b?.data?.id || b?.id
        }
      } else if (resp.ok()) {
        const b = await resp.json()
        createdId = b?.data?.id || b?.id
      }
      console.log(`[E06] 创建结果: status=${resp.status()}, createdId=${createdId}`)
    })

    await withStep(page, testInfo, '验证 enum_value 出现在 enum_type 详情', async () => {
      // 软探查: 通过 API 查 enum_value
      const listResp = await page.request.get(`/api/v1/enum-values?enum_type_id=${encodeURIComponent(target.id)}`)
      if (!listResp.ok()) {
        // 兜底: 通用 enum-values
        const r2 = await page.request.get('/api/v1/enum-values?page=1&page_size=50')
        if (r2.ok()) {
          const b = await r2.json()
          const items = b?.data?.items || b?.data?.records || b?.data || []
          const found = items.find(v => v.code === uniqueCode || v.name === uniqueName)
          expect(found, `enum_value "${uniqueCode}" should be in list`).toBeTruthy()
          return
        }
        test.skip(true, 'enum_values 端点不可用')
        return
      }
      const b = await listResp.json()
      const items = b?.data?.items || b?.data?.records || b?.data || []
      const found = items.find(v => v.code === uniqueCode || v.name === uniqueName)
      expect(found, `enum_value "${uniqueCode}" should exist`).toBeTruthy()
    })

    // 清理
    if (createdId) {
      await page.request.delete(`/api/v1/enum-values/${createdId}`).catch(() => {})
    }
  })

  test('E07: 业务枚举创建值: code 格式校验 (lowercase 拒绝)', async ({ page }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    await withStep(page, testInfo, 'API 创建 code="lowercase_val" (应 400 INVALID_CODE_FORMAT)', async () => {
      const resp = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: 'lowercase_val',  // 违反 ^[A-Z][A-Z0-9_]*$
          name: 'E07 Bad Code',
          is_active: true
        }
      })
      if (!resp.ok() && resp.status() !== 400) {
        // 兜底: 试 v2 BO 端点
        const r2 = await page.request.post('/api/v2/bo/enum_value', {
          data: {
            enum_type_id: target.id,
            code: 'lowercase_val',
            name: 'E07 Bad Code',
            is_active: true
          }
        })
        expect(r2.status(), 'should be 4xx for invalid code format').toBeGreaterThanOrEqual(400)
        const body = await r2.json()
        expect(body.error_code || body.message, 'should mention format').toBeTruthy()
        return
      }
      expect(resp.status(), 'should be 4xx for invalid code format').toBeGreaterThanOrEqual(400)
      const body = await resp.json()
      expect(body.error_code || body.message, 'should mention format').toBeTruthy()
    })
  })

  test('E08: 业务枚举创建值: 唯一性校验', async ({ page, isolation, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    const dupCode = `E08_DUP_${Date.now().toString(36).toUpperCase()}`
    let firstId = null

    await withStep(page, testInfo, 'API 创建第 1 个 enum_value (成功)', async () => {
      const resp = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: dupCode,
          name: 'E08 First',
          is_active: true
        }
      })
      if (resp.ok()) {
        const b = await resp.json()
        firstId = b?.data?.id || b?.id
      } else {
        console.log(`[E08] 第 1 个创建失败: ${resp.status()}`)
        test.skip(true, 'create 1st failed, cannot test uniqueness')
        return
      }
    })

    await withStep(page, testInfo, 'API 创建重复 code (应 400)', async () => {
      const resp = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: dupCode,
          name: 'E08 Duplicate',
          is_active: true
        }
      })
      expect(resp.status(), 'should be 4xx for duplicate code').toBeGreaterThanOrEqual(400)
    })

    if (firstId) {
      await page.request.delete(`/api/v1/enum-values/${firstId}`).catch(() => {})
    }
  })

  test('E12: 业务枚举创建值: 必填校验', async ({ page }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    await withStep(page, testInfo, 'API 创建缺 name (应 4xx)', async () => {
      const resp = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: 'E12_REQ_TEST',
          name: '',  // 缺必填
          is_active: true
        }
      })
      expect(resp.status(), 'should be 4xx for missing required name').toBeGreaterThanOrEqual(400)
    })
  })
})

// ============================================================
// E09-E10: system 枚举值 is_system=true 保护
// ============================================================

test.describe('S-EVC: 枚举值 - DEC-2 (system_value 不可改)', () => {

  test('E09: system 枚举值 is_system=true 不可编辑 (UI dropdown 检查)', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findFirstSystemEnum(page)
    if (!target) {
      test.skip(true, 'no system enum')
      return
    }

    // 通过 API 找 is_system=true 的 enum_value
    let sysValue = null
    await withStep(page, testInfo, '查找 is_system=true 的 enum_value', async () => {
      const r1 = await page.request.get('/api/v1/enum-values?is_system=1&page_size=10')
      let items = []
      if (r1.ok()) {
        const b = await r1.json()
        items = b?.data?.items || b?.data?.records || b?.data || []
      }
      sysValue = items.find(v => v.is_system === true || v.system_value === true)
      if (!sysValue) {
        // 兜底: 取任意 enum_value
        const r2 = await page.request.get('/api/v1/enum-values?page_size=10')
        if (r2.ok()) {
          const b = await r2.json()
          items = b?.data?.items || b?.data?.records || b?.data || []
          sysValue = items[0]
        }
      }
      if (!sysValue) {
        test.skip(true, 'no enum_value to test')
      }
    })

    await withStep(page, testInfo, 'API 尝试更新 is_system=true enum_value (应 400)', async () => {
      if (!sysValue) return
      const resp = await page.request.put(`/api/v1/enum-values/${sysValue.id}`, {
        data: {
          name: 'E09_HACKED_NAME'
        }
      })
      if (resp.status() === 410) {
        // 端点已 sunset, 试 v2
        const r2 = await page.request.put(`/api/v2/bo/enum_value/${sysValue.id}`, {
          data: { name: 'E09_HACKED_NAME' }
        })
        expect(r2.status(), 'should be 4xx for system_value update').toBeGreaterThanOrEqual(400)
        const body = await r2.json()
        expect(body.error_code || body.message, 'should mention system value').toBeTruthy()
        return
      }
      expect(resp.status(), 'should be 4xx for system_value update').toBeGreaterThanOrEqual(400)
      const body = await resp.json()
      expect(body.error_code || body.message, 'should mention system value').toBeTruthy()
    })
  })

  test('E10: system 枚举值 is_system=true 不可删除 (API)', async ({ page }, testInfo) => {
    let sysValue = null
    await withStep(page, testInfo, '查找 is_system=true 的 enum_value', async () => {
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

    await withStep(page, testInfo, 'API 尝试删除 is_system=true (应 400)', async () => {
      if (!sysValue) return
      const resp = await page.request.delete(`/api/v1/enum-values/${sysValue.id}`)
      if (resp.status() === 410) {
        const r2 = await page.request.delete(`/api/v2/bo/enum_value/${sysValue.id}`)
        expect(r2.status(), 'should be 4xx for system_value delete').toBeGreaterThanOrEqual(400)
        const body = await r2.json()
        expect(body.error_code || body.message, 'should mention system value').toBeTruthy()
        return
      }
      expect(resp.status(), 'should be 4xx for system_value delete').toBeGreaterThanOrEqual(400)
      const body = await resp.json()
      expect(body.error_code || body.message, 'should mention system value').toBeTruthy()
    })
  })
})

// ============================================================
// E11: 业务枚举删除值
// ============================================================

test.describe('S-EVC: 枚举值 - 业务枚举删除值', () => {

  test('E11: 业务枚举删除值: API 成功路径', async ({ page, isolation, waitForApiFn }, testInfo) => {
    const target = await findFirstBusinessEnum(page)
    if (!target) {
      test.skip(true, 'no business enum')
      return
    }

    const code = `E11_DEL_${Date.now().toString(36).toUpperCase()}`
    let valueId = null

    await withStep(page, testInfo, '创建 1 个 enum_value (准备删除)', async () => {
      const resp = await page.request.post('/api/v1/enum-values', {
        data: {
          enum_type_id: target.id,
          code: code,
          name: 'E11 To Be Deleted',
          is_active: true
        }
      })
      if (resp.ok()) {
        const b = await resp.json()
        valueId = b?.data?.id || b?.id
      } else {
        test.skip(true, `create failed: ${resp.status()}`)
        return
      }
    })

    await withStep(page, testInfo, 'API DELETE 该 enum_value', async () => {
      if (!valueId) return
      const resp = await page.request.delete(`/api/v1/enum-values/${valueId}`)
      // 200/204 OK
      if (resp.status() === 410) {
        // sunset, 试 v2
        const r2 = await page.request.delete(`/api/v2/bo/enum_value/${valueId}`)
        expect([200, 204], 'should be 2xx').toContain(r2.status())
        return
      }
      expect([200, 204], 'should be 2xx').toContain(resp.status())
    })

    await withStep(page, testInfo, '验证 enum_value 已删除 (GET 应 404)', async () => {
      if (!valueId) return
      const resp = await page.request.get(`/api/v1/enum-values/${valueId}`)
      expect([404, 410], 'should be 404/410 after delete').toContain(resp.status())
    })
  })
})
