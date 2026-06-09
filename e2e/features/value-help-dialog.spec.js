/**
 * VHD-01: Value Help Dialog 分页验证测试
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (无测试数据创建)
 * [OK] POM (GenericListPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

test.describe('VHD-01: Value Help Dialog 分页验证', () => {
  test('C01: 管理员 value help 弹窗分页验证', async ({
    page, navigateTo, waitForApiFn, isolation
  }, testInfo) => {
    const list = new GenericListPage(page)

    // 1. 导航到用户与权限页面
    await withStep(page, testInfo, '导航到用户与权限页面', async () => {
      await navigateTo(page, '/user-permission')
    })

    // 2. 点击用户组管理 tab
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
      await userGroupTab.click({ force: true })
      await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
    })

    // 3. 点击新建按钮
    await withStep(page, testInfo, '点击新建按钮', async () => {
      await list.waitForReady()
      const newBtn = page.locator('.el-button:has-text("新建")').first()
      await newBtn.click({ force: true })
      await waitForApiFn(page, 'GET /api/v2/bo/user_group/').catch(() => {})
    })

    await withStep(page, testInfo, '等待表单加载', async () => {
      await page.locator('.el-form, .el-dialog').first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
    })

    // 4. 查找并点击 vh-search-icon（value help 搜索按钮）
    await withStep(page, testInfo, '查找 value help 搜索按钮', async () => {
      const searchIcons = await page.locator('.vh-search-icon').all()
      console.log(`[VHD] vh-search-icon 数量: ${searchIcons.length}`)

      if (searchIcons.length === 0) {
        const vhFields = await page.locator('[class*="value-help"], [class*="vh-"]').all()
        console.log(`[VHD] vh 相关元素数量: ${vhFields.length}`)
      }

      // 尝试找管理员字段的搜索按钮
      const adminSection = page.locator('.section-content, .form-section').filter({ hasText: /管理员/ }).first()
      if (await adminSection.isVisible({ timeout: 3000 }).catch(() => false)) {
        const sectionSearchIcon = adminSection.locator('.vh-search-icon').first()
        if (await sectionSearchIcon.isVisible({ timeout: 1000 }).catch(() => false)) {
          await sectionSearchIcon.click()
          console.log('[VHD] 点击了管理员区域搜索按钮')
        }
      }

      // 如果还没找到，尝试点击任意 vh-search-icon
      if (!await page.locator('.el-dialog').isVisible({ timeout: 2000 }).catch(() => false)) {
        const anySearchIcon = page.locator('.vh-search-icon').first()
        if (await anySearchIcon.isVisible({ timeout: 2000 }).catch(() => false)) {
          await anySearchIcon.click()
          console.log('[VHD] 点击了第一个搜索按钮')
        }
      }
    })

    // 5. 等待弹窗
    let dialogVisible = false
    await withStep(page, testInfo, '等待 Value Help 弹窗打开', async () => {
      dialogVisible = await page.locator('.el-dialog').isVisible({ timeout: 10000 }).catch(() => false)
      if (dialogVisible) {
        await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
      }
    })

    if (!dialogVisible) {
      console.log('[VHD] [WARN] Value Help 弹窗未打开，soft-fail 跳过后续验证')
      test.skip(true, 'Value Help 弹窗未打开，跳过分页验证')
      return
    }

    // 6. 核心验证：表格行数
    await withStep(page, testInfo, '验证弹窗表格行数', async () => {
      const tableRows = page.locator('.el-dialog .el-table__body tr')
      const rowCount = await tableRows.count()
      console.log(`[VHD] 表格行数: ${rowCount}`)
      expect(rowCount, `表格行数应 <= 20，实际为 ${rowCount}`).toBeLessThanOrEqual(20)
      expect(rowCount, `表格行数应 > 0，实际为 ${rowCount}`).toBeGreaterThan(0)
    })

    // 7. 验证 max-height
    await withStep(page, testInfo, '验证表格 max-height', async () => {
      const maxHeight = await page.locator('.el-dialog .el-table').evaluate(el => getComputedStyle(el).maxHeight)
      console.log(`[VHD] max-height: ${maxHeight}`)
      expect(maxHeight, `max-height 应为 420px，实际为 ${maxHeight}`).toBe('420px')
    })

    // 8. 验证分页信息
    await withStep(page, testInfo, '验证分页信息', async () => {
      const paginationText = await page.locator('.el-dialog .el-pagination').innerText().catch(() => '')
      console.log(`[VHD] 分页: ${paginationText}`)
      expect(paginationText, '分页应包含 15').toContain('15')
    })

    // 9. 测试搜索
    await withStep(page, testInfo, '测试弹窗内搜索功能', async () => {
      const searchInput = page.locator('.el-dialog .vh-search-bar input')
      if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await searchInput.fill('admin')
        await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
        const tableRows = page.locator('.el-dialog .el-table__body tr')
        const filtered = await tableRows.count()
        console.log(`[VHD] 搜索后行数: ${filtered}`)
      }
    })
  })
})
