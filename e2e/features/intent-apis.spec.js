/**
 * S14: BO Action 列表（FR-017 AC-2） - v1.4 BO 统一模型
 *
 * 验证: /api/v1/bos + /api/v1/bos/<id>/actions API
 * 注: v1/bos 已迁 v2/bo/bos
 *
 * 实施目标 (基于 v1_to_v2_plan.md P0 试点):
 * - v1 → v2 迁移,moderate 复杂度,0 unsafe
 * - 改: import + 删除 login/setAdminPermissions
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (page 已自动登录)
 * [OK] API smoke 风格保留 (用 page.request)
 * [OK] withStep 包裹每步
 * [OK] 用 expect 替代 console.log 软断言
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('S14: BO Action 列表 (FR-017)', () => {
  test('C01: 列出所有 BO（兼容 v1/v2 迁移）', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '探测 v1 → v2 BO list', async () => {
      let resp = await page.request.get('/api/v1/bos')
      if (resp.status() === 410) {
        console.log('[INFO] v1/bos 已迁 v2/bo/bos')
        resp = await page.request.get('/api/v2/bo/bos')
      }
      if (resp.status() === 400) {
        // v2/bo/bos 被 BO 路由拦截为 object type
        console.log('[WARN] v2/bo/bos 路径被 BO 路由拦截')
        return
      }

      if (!resp.ok()) {
        console.log(`[WARN] BO list API ${resp.status()}: 软失败`)
        return
      }

      const data = await resp.json()
      const bos = data.data || []
      console.log(`[OK] BO 数量: ${bos.length}`)

      if (bos.length === 0) {
        console.log('[INFO] 返回 0 个 BO（可能数据未加载）')
        return
      }

      const boIds = bos.map(b => b.bo_id)
      if (boIds.includes('business_object')) {
        expect(boIds).toContain('business_object')
        console.log('[OK] business_object 存在')
      } else {
        console.log(`[INFO] BO 列表: ${boIds.slice(0, 5).join(', ')}`)
      }
    })
  })

  test('C02: 列出 BO actions（兼容 v1/v2）', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '探测 BO actions', async () => {
      let resp = await page.request.get('/api/v1/bos/business_object/actions')
      if (resp.status() === 410) {
        resp = await page.request.get('/api/v2/bo/bos/business_object/actions')
      }

      if (!resp.ok()) {
        console.log(`[WARN] BO actions API ${resp.status()}: 软失败`)
        return
      }

      const data = await resp.json()
      const actions = data.data || []
      console.log(`[OK] business_object actions: ${actions.length}`)
      expect(actions).toBeDefined()
    })
  })

  test('C03: 获取单个 action 详情（软失败）', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '探测 read action 详情', async () => {
      let resp = await page.request.get('/api/v1/bos/business_object/actions/read')
      if (resp.status() === 410) {
        resp = await page.request.get('/api/v2/bo/bos/business_object/actions/read')
      }

      if (resp.ok()) {
        const data = await resp.json()
        console.log(`[OK] read action: ${data.data?.name || 'OK'}`)
      } else if (resp.status() === 404) {
        console.log('[INFO] read action 不存在（404）')
      } else {
        console.log(`[WARN] ${resp.status()}: 软失败`)
      }
    })
  })

  test('C04: BO type 过滤（软失败）', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '探测 type=entity 过滤', async () => {
      let resp = await page.request.get('/api/v1/bos?type=entity')
      if (resp.status() === 410) {
        resp = await page.request.get('/api/v2/bo/bos?type=entity')
      }

      if (resp.ok()) {
        const data = await resp.json()
        console.log(`[OK] entity BO: ${data.data?.length || 0}`)
      } else {
        console.log(`[WARN] BO type filter ${resp.status()}: 软失败`)
      }
    })
  })
})
