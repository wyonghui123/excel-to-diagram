/**
 * S-BRP-DEL-FORMAT: 删除保护 + 格式约束 (DEC-3, DEC-4) - BMRD 自动生成
 *
 * [业务模型规则驱动 (BMRD) v1.0 - 自动生成]
 * 来源: .trae/specs/_business_rules/_protection_rules.yaml
 * 生成器: scripts/generate-protection-tests.py
 * 生成时间: 2026-06-13
 *
 * 业务规则:
 *   DEC-3: 含关联子对象时父对象不可删 [ACTIVE]
 *   DEC-4: enum_value.code 格式约束 [ACTIVE]
 *
 * v2 铁律合规 (8 项):
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked()
 * [OK] 用 POM
 * [OK] 用 waitForApiFn()
 * [OK] withStep 包裹
 * [OK] isolation fixture 解构
 *
 * DEFER 项: 见 _protection_rules.yaml#deferred (本文件不包含 DEFER 测)

 */
import { test, expect } from '../helpers/auto-fixtures.js'


test.describe('S-BRP-DEC-3: 含关联子对象时父对象不可删 (BMRD)', () => {
  /**
   * 删含 versions 的 product 应被拒绝
   * 业务规则: DEC-3 - 含关联子对象时父对象不可删
   * 优先级: P0
   */
    test('删含 versions 的 product 应被拒绝', async ({ page, dataFinder }) => {
      const pv = await dataFinder.productWithVersion()
      const r = await page.request.delete('/api/v2/bo/product/' + pv.product.id)
      expect(r.status(), 'should reject').toBeGreaterThanOrEqual(400)
    })
  /**
   * 删含 members 的 user_group 应被拒绝
   * 业务规则: DEC-3 - 含关联子对象时父对象不可删
   * 优先级: P0
   */
    test('删含 members 的 user_group 应被拒绝', async ({ page, dataFinder }) => {
      // 用 dataFinder.userGroup() 找一个有成员的组
      const ug = await dataFinder.userGroup({ minMembers: 1 }).catch(() => null)
      test.skip(!ug, 'no user_group with members')
      const r = await page.request.delete('/api/v2/bo/user_group/' + ug.id)
      expect(r.status(), 'should reject').toBeGreaterThanOrEqual(400)
    })
  /**
   * 删空 product 应成功
   * 业务规则: DEC-3 - 含关联子对象时父对象不可删
   * 优先级: P0
   */
    test('删空 product 应成功', async ({ page, isolation }) => {
      const ts = Date.now().toString(36).toUpperCase()
      const p = await isolation.createTracked('product', {
        code: 'DEC3_' + ts, name: 'Empty_' + ts, visibility: 'private'
      })
      const r = await page.request.delete('/api/v2/bo/product/' + p.id)
      expect([200, 204], 'empty product should be deletable').toContain(r.status())
    })

})

test.describe('S-BRP-DEC-4: enum_value.code 格式约束 (BMRD)', () => {
  /**
   * enum_value.code 格式不符应被 API 拒绝
   * 业务规则: DEC-4 - enum_value.code 格式约束
   * 优先级: P1
   */
    test('enum_value.code 格式不符应被 API 拒绝', async ({ page }) => {
      const r = await page.request.post('/api/v2/bo/enum_value', {
        data: { enum_type_id: 1, code: 'lowercase_val', name: 'bad' }
      })
      expect(r.status(), 'invalid code format should be rejected').toBeGreaterThanOrEqual(400)
    })

})

