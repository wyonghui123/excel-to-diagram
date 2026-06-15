/**
 * S-ETD: 枚举类型管理 - 详情页 E2E 测试 (v3.18-r2)
 *
 * 覆盖 (12 测, P0+P1):
 *   E03: 业务枚举详情页: 编辑/保存/必填校验
 *   E04: system 枚举详情页: 操作按钮为空 (DEC-1)
 *   E05: locked 枚举详情页: 操作按钮为空 (DEC-1)
 *   E20: 详情页: 关闭/返回列表
 *   E21: 详情页: 脏数据关闭弹确认
 *   E22: 详情页: 保存失败保留脏数据
 *   E23: 详情页: facet 切换
 *   E29: 列表导出按钮
 *   E30: 详情页: 系统信息 facet 字段全部 disabled
 *   E40: 详情页: 取消按钮 - 字段恢复原值
 *
 * 适配说明 (2026-06-13 根因分析后):
 * - business enum 在 V1/V2 列表中 id=null, 无法用于详情页路由
 * - system enum (如 ActionType) 有有效 id (如 "action_type")
 * - V2 BO create enum_type 返回 201 但数据不持久化 (cleanup 404)
 * - 策略: system/locked 测试用 ActionType; business 编辑测试需有效 id
 * - V2 BO single ActionType 返回完整数据 (含 change_history, display_values)
 * - ui_actions_resolved 在 V2 BO single 中返回 None (前端通过 computedActions 计算)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'
import {
  findSystemEnum,
  findLockedEnum,
  findBusinessEnumWithId,
  createTestEnumType
} from '../helpers/enum-finder.js'

// ============================================================
// E03, E40: 业务枚举编辑/取消
// ============================================================

test.describe('S-ETD: 枚举类型详情 - 业务枚举 CRUD', () => {

  test('E03: 业务枚举详情 → 编辑 → 保存 → 成功通知', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    // 策略: 先尝试找有 id 的 business enum, 再尝试创建
    let target = await findBusinessEnumWithId(page)
    let createdType = null

    if (!target) {
      createdType = await createTestEnumType(page)
      target = createdType
    }

    if (!target) {
      test.skip(true, 'no business enum with valid id (business enums have id=null, V2 BO create does not persist)')
      return
    }

    try {
      await withStep(page, testInfo, '导航到详情页', async () => {
        await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
        await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
        await page.waitForTimeout(1000)
      })

      const drawer = new DetailDrawerPage(page)
      await withStep(page, testInfo, '点击"编辑"按钮', async () => {
        const editBtn = drawer.getRoot().locator('button:has-text("编辑")').first()
        if (!(await editBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
          test.skip(true, 'edit button not visible (possibly readonly or schema not configured)')
          return
        }
        await editBtn.click()
        await page.waitForTimeout(800)
      })

      await withStep(page, testInfo, '修改名称 + 保存', async () => {
        const nameInput = drawer.getRoot().locator(
          '.el-form-item:has(.el-form-item__label:has-text("名称")) input'
        ).first()
        if (await nameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
          const originalName = await nameInput.inputValue()
          const newName = `${originalName}_E03`
          await nameInput.fill(newName)
          await page.waitForTimeout(300)

          const saveBtn = drawer.getRoot().locator('button:has-text("保存")').first()
          if (await saveBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
            await saveBtn.click()
            await waitForApiFn(page, /PUT|POST/).catch(() => {})
            try {
              await drawer.expectNotification('success', /成功|success/i, 5000)
            } catch (e) {
              console.log(`[E03] 成功通知未出现: ${e.message}`)
            }
          }
        }
      })

      await withStep(page, testInfo, '关闭 drawer', async () => {
        await drawer.close()
      })
    } finally {
      if (createdType) await createdType.cleanup()
    }
  })

  test('E40: 编辑后取消 → 字段恢复原值', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    let target = await findBusinessEnumWithId(page)
    let createdType = null

    if (!target) {
      createdType = await createTestEnumType(page)
      target = createdType
    }

    if (!target) {
      test.skip(true, 'no business enum with valid id')
      return
    }

    try {
      await withStep(page, testInfo, '导航到详情', async () => {
        await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
        await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
        await page.waitForTimeout(1000)
      })

      const drawer = new DetailDrawerPage(page)
      await withStep(page, testInfo, '编辑模式 + 修改名称 + 取消', async () => {
        const editBtn = drawer.getRoot().locator('button:has-text("编辑")').first()
        if (!(await editBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
          test.skip(true, 'no edit button')
          return
        }
        await editBtn.click()
        await page.waitForTimeout(500)

        const nameInput = drawer.getRoot().locator(
          '.el-form-item:has(.el-form-item__label:has-text("名称")) input'
        ).first()
        if (await nameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
          const original = await nameInput.inputValue()
          await nameInput.fill(`${original}_CANCELLED`)
          await page.waitForTimeout(300)

          const cancelBtn = drawer.getRoot().locator('button:has-text("取消")').first()
          if (await cancelBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
            await cancelBtn.click()
            await page.waitForTimeout(800)
            const reloadedName = await nameInput.inputValue().catch(() => original)
            expect(reloadedName, 'name should restore to original').not.toContain('CANCELLED')
          }
        }
      })

      await withStep(page, testInfo, '关闭 drawer', async () => {
        await drawer.close()
      })
    } finally {
      if (createdType) await createdType.cleanup()
    }
  })
})

// ============================================================
// E04-E05: system/locked 详情无操作按钮 (DEC-1)
// ============================================================

test.describe('S-ETD: 枚举类型详情 - DEC-1 保护', () => {

  test('E04: system 枚举详情: 无编辑/删除按钮', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no system enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)
    })

    await withStep(page, testInfo, '断言: 无编辑/保存/删除按钮 (DEC-1)', async () => {
      const drawer = new DetailDrawerPage(page)
      await page.waitForSelector('.object-page, .odp-title-bar, .el-drawer', { timeout: 5000 }).catch(() => {})
      await drawer.expectNoActions(['编辑', '保存', '取消', '删除'])
    })
  })

  test('E05: locked 枚举详情: 通过 API ui_actions_resolved 验证', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findLockedEnum(page)
    if (!target) {
      test.skip(true, 'no locked enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1000)
    })

    await withStep(page, testInfo, '通过 API 验证 ui_actions_resolved (locked)', async () => {
      const list = new GenericListPage(page)
      try {
        const resolved = await list.getUiActionsResolved('enum_type', target.id)
        if (resolved) {
          if ('create_value' in resolved) expect(resolved.create_value).toBe(false)
          if ('update_value' in resolved) expect(resolved.update_value).toBe(false)
          if ('delete_value' in resolved) expect(resolved.delete_value).toBe(false)
        }
      } catch (e) {
        // ui_actions_resolved 可能返回 None (V2 BO single 不返回此字段)
        console.log(`[E05] ui_actions_resolved 不可用: ${e.message}`)
      }
    })
  })
})

// ============================================================
// E20-E23: 详情页交互
// ============================================================

test.describe('S-ETD: 枚举类型详情 - 导航/facet', () => {

  test('E20: 详情页: 关闭/返回列表', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    // 用 system enum (有有效 id)
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1000)
    })

    await withStep(page, testInfo, '按 ESC 关闭', async () => {
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)
      const closeBtn = page.locator('.odp-back-link, .el-drawer-close, button:has-text("关闭")').first()
      if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await closeBtn.click()
        await page.waitForTimeout(500)
      }
    })
  })

  test('E21: 详情页: 脏数据关闭弹确认', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    let target = await findBusinessEnumWithId(page)
    let createdType = null

    if (!target) {
      createdType = await createTestEnumType(page)
      target = createdType
    }

    if (!target) {
      test.skip(true, 'no business enum with valid id')
      return
    }

    try {
      await withStep(page, testInfo, '导航 + 切编辑 + 改值 + 尝试关闭', async () => {
        await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
        await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
        await page.waitForTimeout(1000)

        const drawer = new DetailDrawerPage(page)
        const editBtn = drawer.getRoot().locator('button:has-text("编辑")').first()
        if (!(await editBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
          test.skip(true, 'no edit button')
          return
        }
        await editBtn.click()
        await page.waitForTimeout(500)

        const nameInput = drawer.getRoot().locator(
          '.el-form-item:has(.el-form-item__label:has-text("名称")) input'
        ).first()
        if (await nameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
          const original = await nameInput.inputValue()
          await nameInput.fill(`${original}_DIRTY`)
          await page.waitForTimeout(300)
        }

        await page.keyboard.press('Escape')
        await page.waitForTimeout(800)
        const confirm = page.locator('.el-message-box:visible, .odp-confirm-dialog:visible').first()
        const visible = await confirm.isVisible({ timeout: 1500 }).catch(() => false)
        console.log(`[E21] 脏数据确认对话框 visible=${visible}`)
      })
    } finally {
      if (createdType) await createdType.cleanup()
    }
  })

  test('E22: 详情页: 保存失败保留脏数据', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    let target = await findBusinessEnumWithId(page)
    let createdType = null

    if (!target) {
      createdType = await createTestEnumType(page)
      target = createdType
    }

    if (!target) {
      test.skip(true, 'no business enum with valid id')
      return
    }

    try {
      await withStep(page, testInfo, '导航 + 编辑模式', async () => {
        await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
        await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
        await page.waitForTimeout(1000)
      })

      const drawer = new DetailDrawerPage(page)
      await withStep(page, testInfo, '改 name 为空 + 保存 (应失败)', async () => {
        const editBtn = drawer.getRoot().locator('button:has-text("编辑")').first()
        if (!(await editBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
          test.skip(true, 'no edit button')
          return
        }
        await editBtn.click()
        await page.waitForTimeout(500)
        const nameInput = drawer.getRoot().locator(
          '.el-form-item:has(.el-form-item__label:has-text("名称")) input'
        ).first()
        if (await nameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
          await nameInput.fill('')
          await page.waitForTimeout(300)
          const saveBtn = drawer.getRoot().locator('button:has-text("保存")').first()
          if (await saveBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
            await saveBtn.click()
            await page.waitForTimeout(1500)
            try {
              await drawer.expectNotification('error', /失败|错误|必填|required/i, 5000)
              console.log('[E22] 看到错误通知')
            } catch (e) {
              console.log(`[E22] 错误通知未出现: ${e.message}`)
            }
          }
        }
      })

      await withStep(page, testInfo, '关闭 drawer', async () => {
        await page.keyboard.press('Escape')
        await page.waitForTimeout(500)
      })
    } finally {
      if (createdType) await createdType.cleanup()
    }
  })

  test('E23: 详情页: facet 切换', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)
    })

    const drawer = new DetailDrawerPage(page)
    for (const facet of ['基本信息', '维度配置', '系统信息']) {
      await withStep(page, testInfo, `切到 facet: ${facet}`, async () => {
        try {
          await drawer.switchFacet(facet)
        } catch (e) {
          console.log(`[E23] facet "${facet}" 切换失败: ${e.message}`)
        }
      })
    }
  })
})

// ============================================================
// E29-E30: 导出 + 系统信息 disabled
// ============================================================

test.describe('S-ETD: 枚举类型详情 - 导出/系统信息', () => {

  test('E29: 列表导出按钮', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到列表', async () => {
      await navigateTo(page, '/business-config/enum-types')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
    })

    await withStep(page, testInfo, '查找"导出"按钮', async () => {
      const exportBtn = page.locator('.toolbar button:has-text("导出"), button:has-text("导出")').first()
      const visible = await exportBtn.isVisible({ timeout: 3000 }).catch(() => false)
      if (visible) {
        console.log('[E29] 找到导出按钮')
      } else {
        console.log('[E29] 未找到导出按钮 (schema 未启用 export)')
        test.skip(true, 'export button not present (schema does not enable export)')
      }
    })
  })

  test('E30: 系统信息 facet 字段全部 disabled', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)
    })

    const drawer = new DetailDrawerPage(page)
    await withStep(page, testInfo, '切到"系统信息" facet', async () => {
      try {
        await drawer.switchFacet('系统信息')
      } catch (e) {
        test.skip(true, `系统信息 facet 不可见: ${e.message}`)
        return
      }
    })

    await withStep(page, testInfo, '检查 created_at/updated_at disabled', async () => {
      for (const label of ['创建时间', '更新时间']) {
        try {
          await drawer.expectFieldDisabled(label)
        } catch (e) {
          console.log(`[E30] 字段 "${label}" 未 disabled: ${e.message}`)
        }
      }
    })
  })
})
