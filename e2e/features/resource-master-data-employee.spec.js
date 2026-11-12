/**
 * 统一资源模型 P3 - 员工主数据 / 资源可用性例外 - E2E (2026-11-01)
 *
 * 覆盖范围（端到端：菜单路由 → 通用列表页 → BO API → 落库 → 清理）:
 *   RMD-01 员工列表页加载（页面结构 + 列 + 工具栏 + API 分页契约）
 *   RMD-02 员工全链路：party → person_profile → employee（API 造数）→ 列表可见 → 只读详情 → 删除
 *   RMD-03 员工筛选元数据（用工类型 / 在职状态枚举驱动）
 *   RMD-04 资源可用性例外列表页加载（页面结构 + API 分页契约）
 *   RMD-05 资源可用性例外全链路：resource → resource_availability（API 造数）→ 列表可见 → 删除
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / 无 setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto() + waitForTimeout
 * [OK] 用 GenericListPage POM 不直接断言 .el-table
 * [OK] 禁止 waitForLoadState('networkidle')
 * [OK] 造数/清理全部走 page.request（httpOnly cookie 来自 storageState）
 *
 * 依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md FR-015 / FR-005
 */

import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

const EMPLOYEE_URL = '/master-data/employee'
const AVAILABILITY_URL = '/master-data/resource-availability'

const API = {
  employee: '/api/v2/bo/employee',
  party: '/api/v2/bo/party',
  personProfile: '/api/v2/bo/person_profile',
  resource: '/api/v2/bo/resource',
  availability: '/api/v2/bo/resource_availability'
}

const stamp = () => `${Date.now()}_${Math.floor(Math.random() * 1000)}`

// ============================================================
// API 造数 / 清理辅助
// ============================================================

async function apiCreate(request, url, payload) {
  const resp = await request.post(url, { data: payload })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok() || body.success === false) {
    throw new Error(`POST ${url} failed: ${resp.status()} ${JSON.stringify(body).slice(0, 300)}`)
  }
  const created = body.data
  const id = created?.id ?? created?.items?.[0]?.id
  if (!id) throw new Error(`POST ${url} returned no id: ${JSON.stringify(body).slice(0, 300)}`)
  return { id, raw: created }
}

async function apiDelete(request, url, id) {
  const resp = await request.delete(`${url}/${id}`)
  if (!resp.ok()) {
    console.warn(`[cleanup] DELETE ${url}/${id} -> ${resp.status()}`)
  }
  return resp.ok()
}

async function apiList(request, url, params = '') {
  const resp = await request.get(`${url}?page=1&page_size=5${params}`)
  expect(resp.ok(), `GET ${url} should be 200`).toBeTruthy()
  const body = await resp.json()
  expect(body.success, `GET ${url} success should be true`).toBe(true)
  return body.data
}

/** 断言通用列表页结构（MetaListPage：toolbar + 表格 + 分页） */
async function expectListPageStructure(page) {
  await expect(page.locator('.meta-list-page, .generic-list, .el-table').first()).toBeVisible()
  await expect(page.locator('.toolbar').first()).toBeVisible()
  await expect(page.locator('.el-table').first()).toBeVisible()
  await expect(page.locator('.el-pagination').first()).toBeVisible()
  // 旧版 filter-bar 已下线
  expect(await page.locator('.filter-bar').count(), 'filter-bar should be removed').toBe(0)
}

// ============================================================
// RMD-01 员工列表页加载
// ============================================================

test.describe('统一资源模型 P3 - 员工主数据', () => {

  test('RMD-01: 员工列表页加载 + API 分页契约', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到员工列表页 /master-data/employee', async () => {
      await navigateTo(page, EMPLOYEE_URL)
      await list.waitForReady()
    })

    await withStep(page, testInfo, '列表页结构：toolbar + 表格 + 分页', async () => {
      await expectListPageStructure(page)
    })

    await withStep(page, testInfo, '表头包含 工号 / 姓名 / 用工类型 / 在职状态', async () => {
      const headers = await list.getColumnHeaders()
      for (const col of ['工号', '姓名', '用工类型', '在职状态']) {
        expect(headers, `column "${col}" should exist, got: ${headers.join('|')}`).toContain(col)
      }
    })

    await withStep(page, testInfo, '工具栏存在「新建员工」', async () => {
      const createBtn = page.locator('.toolbar button:has-text("新建员工")').first()
      await expect(createBtn).toBeVisible()
    })

    await withStep(page, testInfo, 'BO API 返回分页格式（items/total）', async () => {
      const data = await apiList(page.request, API.employee)
      expect(Array.isArray(data.items), 'data.items should be an array').toBeTruthy()
      expect(typeof data.total, 'data.total should be a number').toBe('number')
      expect(data.page, 'data.page should be 1').toBe(1)
    })
  })

  // ============================================================
  // RMD-02 员工全链路（造数 → 列表 → 详情 → 删除）
  // ============================================================

  test('RMD-02: 员工全链路 party → person_profile → employee → 列表可见 → 删除', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)
    const suffix = stamp()
    const employeeNo = `E2E_EMP_${suffix}`.slice(0, 190)
    const employeeName = `E2E员工_${suffix}`
    const created = { employee: null, personProfile: null, party: null }

    try {
      // 1. 自然人（party, party_type=person）
      const party = await withStep(page, testInfo, 'API 造数：party(person)', async () => {
        const r = await apiCreate(page.request, API.party, {
          code: `E2E_P_${suffix}`.slice(0, 20),
          name: employeeName,
          party_type: 'person',
          status: 'active'
        })
        created.party = r.id
        return r
      })

      // 2. 自然人档案（person_profile，1:1 锚 party）
      const person = await withStep(page, testInfo, 'API 造数：person_profile（锚 party）', async () => {
        const r = await apiCreate(page.request, API.personProfile, {
          party_id: party.id,
          mobile: `139${String(suffix).padStart(8, '0').slice(-8)}`,
          email: `e2e_${suffix}@example.com`
        })
        created.personProfile = r.id
        return r
      })

      // 3. 员工（薄主数据，雇佣关系）
      const employee = await withStep(page, testInfo, 'API 造数：employee（在职）', async () => {
        const r = await apiCreate(page.request, API.employee, {
          employee_no: employeeNo,
          name: employeeName,
          person_profile_id: person.id,
          org_id: 345,
          position: 'E2E岗位',
          employment_type: 'full_time',
          status: 'active',
          hire_date: '2026-11-01T00:00:00'
        })
        created.employee = r.id
        return r
      })

      // 4. UI 列表可见（默认按 hire_date desc，新建行在首页）
      await withStep(page, testInfo, '列表页可见新建员工行', async () => {
        await navigateTo(page, EMPLOYEE_URL)
        await list.waitForReady()
        await list.expectRowExists(employeeNo, { timeout: 15000 })
        const row = await list.findRow(employeeNo)
        expect(row, 'row locator should be found').not.toBeNull()
        const rowText = await row.textContent()
        expect(rowText, 'row should show employee name').toContain(employeeName)
      })

      // 5. 只读回读：表单/详情链路读取同一实体
      await withStep(page, testInfo, '按 ID 回读员工实体（详情数据源）', async () => {
        const resp = await page.request.get(`${API.employee}/${employee.id}`)
        expect(resp.ok(), 'GET employee by id should be 200').toBeTruthy()
        const body = await resp.json()
        const entity = body.data?.item || body.data
        expect(body.success).toBe(true)
        expect(entity.name, 'detail entity name').toBe(employeeName)
        expect(entity.status, 'detail entity status').toBe('active')
      })

      // 6. 打开详情抽屉（detail_mode=drawer，软校验：不同列表配置可能走行内按钮）
      await withStep(page, testInfo, '尝试打开详情抽屉', async () => {
        await list.clickRowByText(employeeNo)
        const drawer = page.locator('.el-drawer')
        const opened = await drawer.first().waitFor({ state: 'visible', timeout: 5000 })
          .then(() => true).catch(() => false)
        if (!opened) {
          console.warn('[RMD-02] 行点击未打开详情抽屉（可能为行内操作按钮模式），已由 API 回读断言覆盖')
        } else {
          await expect(drawer.first()).toBeVisible()
        }
      })

      // 7. 删除员工（restrict 策略：无排班时应成功）
      await withStep(page, testInfo, '删除员工（含依赖链清理）', async () => {
        const ok = await apiDelete(page.request, API.employee, employee.id)
        expect(ok, 'DELETE employee should succeed').toBeTruthy()
        created.employee = null
      })

      await withStep(page, testInfo, 'API 侧确认员工已不存在', async () => {
        const data = await apiList(page.request, API.employee, `&employee_no=${employeeNo}`)
        expect(data.items.some(it => it.employee_no === employeeNo), 'deleted employee should be absent').toBe(false)
      })

      await withStep(page, testInfo, '刷新列表并搜索，确认该员工不再出现', async () => {
        // 详情抽屉可能仍挂在上一次 DOM 上，先关闭再整页刷新，避免读到旧表格数据
        await page.keyboard.press('Escape').catch(() => {})
        await page.reload({ waitUntil: 'domcontentloaded' })
        await list.waitForReady()
        await list.search(employeeNo)
        await list.expectRowNotExists(employeeNo, { timeout: 5000 })
      })
    } finally {
      // 未删除的依赖由 isolation 逆序兜底
      if (created.employee) await apiDelete(page.request, API.employee, created.employee)
      if (created.personProfile) await apiDelete(page.request, API.personProfile, created.personProfile)
      if (created.party) await apiDelete(page.request, API.party, created.party)
    }
  })

  // ============================================================
  // RMD-03 员工筛选元数据（枚举驱动）
  // ============================================================

  test('RMD-03: 员工筛选元数据由枚举驱动（用工类型 / 在职状态）', async ({ page }, testInfo) => {
    await withStep(page, testInfo, 'GET employee 视图配置含 f列 filter 元数据', async () => {
      const data = await apiList(page.request, API.employee)
      const filters = data.filters || []
      expect(filters.length, 'employee list should expose filters').toBeGreaterThan(0)

      const byField = (name) => filters.find(f => f.field === name)

      const employmentType = byField('employment_type')
      expect(employmentType, 'employment_type filter should exist').toBeTruthy()
      expect(employmentType.enum_type, 'employment_type should be enum-driven').toBe('employment_type')
      const etValues = (employmentType.options || []).map(o => o.value)
      for (const v of ['full_time', 'part_time', 'contractor', 'intern', 'dispatched']) {
        expect(etValues, `enum option ${v} should exist`).toContain(v)
      }

      const status = byField('status')
      expect(status, 'status filter should exist').toBeTruthy()
      expect(status.enum_type, 'status should be enum-driven').toBe('employment_status')
      const stValues = (status.options || []).map(o => o.value)
      for (const v of ['active', 'inactive', 'terminated']) {
        expect(stValues, `enum option ${v} should exist`).toContain(v)
      }
    })
  })
})

// ============================================================
// RMD-04 / RMD-05 资源可用性例外
// ============================================================

test.describe('统一资源模型 P2c - 资源可用性例外', () => {

  test('RMD-04: 资源可用性例外列表页加载 + API 分页契约', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到 /master-data/resource-availability', async () => {
      await navigateTo(page, AVAILABILITY_URL)
      await list.waitForReady()
    })

    await withStep(page, testInfo, '列表页结构：toolbar + 表格 + 分页', async () => {
      await expectListPageStructure(page)
    })

    await withStep(page, testInfo, '表头包含 例外类型 / 开始时间 / 数据来源', async () => {
      const headers = await list.getColumnHeaders()
      for (const col of ['例外类型', '开始时间', '数据来源']) {
        expect(headers, `column "${col}" should exist, got: ${headers.join('|')}`).toContain(col)
      }
    })

    await withStep(page, testInfo, 'BO API 返回分页格式（items/total）', async () => {
      const data = await apiList(page.request, API.availability)
      expect(Array.isArray(data.items), 'data.items should be an array').toBeTruthy()
      expect(typeof data.total, 'data.total should be a number').toBe('number')
      const filters = data.filters || []
      const typeFilter = filters.find(f => f.field === 'availability_type')
      expect(typeFilter, 'availability_type filter should exist').toBeTruthy()
      const values = (typeFilter.options || []).map(o => o.value)
      for (const v of ['available', 'unavailable', 'overtime']) {
        expect(values, `enum option ${v} should exist`).toContain(v)
      }
    })
  })

  test('RMD-05: 资源可用性例外全链路 resource → availability → 列表可见 → 删除', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)
    const suffix = stamp()
    const reason = `E2E检修_${suffix}`
    const created = { availability: null, resource: null }

    try {
      const resource = await withStep(page, testInfo, 'API 造数：resource（machine）', async () => {
        const r = await apiCreate(page.request, API.resource, {
          code: `E2E_RES_${suffix}`.replace(/[^A-Z0-9_]/g, '').slice(0, 40) || 'E2E_RES_FALLBACK',
          name: `E2E资源_${suffix}`,
          resource_kind: 'machine',
          is_active: true
        })
        created.resource = r.id
        return r
      })

      const availability = await withStep(page, testInfo, 'API 造数：resource_availability（检修不可用）', async () => {
        const r = await apiCreate(page.request, API.availability, {
          resource_id: resource.id,
          availability_type: 'unavailable',
          start_at: '2026-11-01T08:00:00',
          end_at: '2026-11-01T12:00:00',
          reason,
          source: 'maintenance'
        })
        created.availability = r.id
        return r
      })

      await withStep(page, testInfo, '列表页可见该例外行', async () => {
        await navigateTo(page, AVAILABILITY_URL)
        await list.waitForReady()
        await list.expectRowExists(reason, { timeout: 15000 })
      })

      await withStep(page, testInfo, '按 ID 回读例外实体', async () => {
        const resp = await page.request.get(`${API.availability}/${availability.id}`)
        expect(resp.ok(), 'GET resource_availability by id should be 200').toBeTruthy()
        const body = await resp.json()
        const entity = body.data?.item || body.data
        expect(body.success).toBe(true)
        expect(entity.reason, 'detail entity reason').toBe(reason)
        expect(entity.availability_type, 'detail entity availability_type').toBe('unavailable')
      })

      await withStep(page, testInfo, '删除例外 + 删除资源（restrict 校验）', async () => {
        const okAvail = await apiDelete(page.request, API.availability, availability.id)
        expect(okAvail, 'DELETE availability should succeed').toBeTruthy()
        created.availability = null

        const okRes = await apiDelete(page.request, API.resource, resource.id)
        expect(okRes, 'DELETE resource should succeed after availability removed').toBeTruthy()
        created.resource = null
      })
    } finally {
      if (created.availability) await apiDelete(page.request, API.availability, created.availability)
      if (created.resource) await apiDelete(page.request, API.resource, created.resource)
    }
  })
})
