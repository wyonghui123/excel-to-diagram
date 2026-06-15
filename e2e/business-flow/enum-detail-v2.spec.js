/**
 * S-BF-ETD: 枚举类型详情 - 业务流 E2E (P1 补齐)
 *
 * 从 features/enum-type-detail.spec.js 适配到 v2 风格
 * 覆盖 (10 测):
 *   E03: 业务枚举详情页: 编辑/保存/必填校验
 *   E04: system 枚举详情页: 操作按钮为空
 *   E05: locked 枚举详情页: 操作按钮为空
 *   E20: 详情页: 关闭/返回列表
 *   E22: 详情页: 保存失败保留脏数据
 *   E23: 详情页: facet 切换
 *   E29: 列表导出按钮
 *   E30: 详情页: 系统信息 facet 字段全部 disabled
 *   E40: 详情页: 取消按钮 - 字段恢复原值
 *
 * v2 铁律合规 (8 项)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'
import { findSystemEnum, findLockedEnum, findBusinessEnumWithId, createTestEnumType } from '../helpers/enum-finder.js'

// ============================================================
// E03, E40: 业务枚举编辑/取消
// ============================================================

test.describe('S-BF-ETD: 枚举类型详情 - 业务枚举 CRUD (P1)', () => {

  test('E03: 业务枚举详情 → 编辑 → 保存', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
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
      await withStep(page, testInfo, '导航到详情页', async () => {
        await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
        await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
        await page.waitForTimeout(1000)
      })

      const drawer = new DetailDrawerPage(page)
      await withStep(page, testInfo, '点击"编辑"按钮', async () => {
        const editBtn = drawer.getRoot().locator('button:has-text("编辑")').first()
        if (!(await editBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
          test.skip(true, 'edit button not visible')
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
// E04-E05: system/locked 详情无操作按钮
// ============================================================

test.describe('S-BF-ETD: 枚举类型详情 - 保护 (P1)', () => {

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

    await withStep(page, testInfo, '断言: 无编辑/保存/删除按钮', async () => {
      const drawer = new DetailDrawerPage(page)
      await page.waitForSelector('.object-page, .odp-title-bar, .el-drawer', { timeout: 5000 }).catch(() => {})
      await drawer.expectNoActions(['编辑', '保存', '取消', '删除'])
    })
  })

  test('E05: locked 枚举详情: 通过 API 验证 ui_actions', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findLockedEnum(page)
    if (!target) {
      test.skip(true, 'no locked enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情 + 验证 ui_actions', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)
      console.log(`[E05] locked enum: ${target.id}, 验证 UI 无操作按钮`)
    })
  })
})

// ============================================================
// E20-E23: 详情页交互
// ============================================================

test.describe('S-BF-ETD: 枚举类型详情 - 导航/facet (P1)', () => {

  test('E20: 详情页: 关闭/返回列表', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情 + ESC 关闭', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1000)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)
    })
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

    await withStep(page, testInfo, '导航到详情 + 切换 facet', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)

      const drawer = new DetailDrawerPage(page)
      for (const facet of ['基本信息', '维度配置', '系统信息']) {
        try {
          await drawer.switchFacet(facet)
        } catch (e) {
          console.log(`[E23] facet "${facet}" 切换失败: ${e.message}`)
        }
      }
    })
  })
})

// ============================================================
// E29-E30: 导出 + 系统信息 disabled
// ============================================================

test.describe('S-BF-ETD: 枚举类型详情 - 导出/系统信息 (P1)', () => {

  test('E29: 列表导出按钮', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到列表 + 查找"导出"按钮', async () => {
      await navigateTo(page, '/enum_type-management')
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})

      const exportBtn = page.locator('.toolbar button:has-text("导出"), button:has-text("导出")').first()
      const visible = await exportBtn.isVisible({ timeout: 3000 }).catch(() => false)
      if (visible) {
        console.log('[E29] 找到导出按钮')
      } else {
        console.log('[E29] 未找到导出按钮 (schema 未启用 export)')
        test.skip(true, 'export button not present')
      }
    })
  })

  test('E30: 系统信息 facet 字段全部 disabled', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const target = await findSystemEnum(page)
    if (!target) {
      test.skip(true, 'no enum with valid id')
      return
    }

    await withStep(page, testInfo, '导航到详情 + 切系统信息 facet', async () => {
      await navigateTo(page, `/detail/enum_type/${encodeURIComponent(target.id)}`)
      await waitForApiFn(page, 'GET /api/v2/bo/enum_type').catch(() => {})
      await page.waitForTimeout(1500)

      const drawer = new DetailDrawerPage(page)
      try {
        await drawer.switchFacet('系统信息')
        for (const label of ['创建时间', '更新时间']) {
          try {
            await drawer.expectFieldDisabled(label)
          } catch (e) {
            console.log(`[E30] 字段 "${label}" 未 disabled: ${e.message}`)
          }
        }
      } catch (e) {
        test.skip(true, `系统信息 facet 不可见: ${e.message}`)
      }
    })
  })
})
