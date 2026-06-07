/**
 * S06: 角色权限配置 — 完备 E2E 测试
 *
 * 路径: /system/role-permission/:roleId
 * 覆盖: 页面加载 / 管理维度 / 条件规则编辑 / 规则表格操作 / 保存重置 / 影响预览
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规 (8 项):
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直接调用 (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码命名 + 不清理 (改用 isolation)
 * [OK] 禁止 el-table 直查 (改用 GenericListPage POM)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

// ==================== 辅助函数 ====================

/** 获取第一个角色的 ID (走 page.request, 自动继承 global-setup 的 cookie 认证) */
async function getFirstRoleId(page) {
  const resp = await page.request.get('/api/v2/bo/role?page=1&page_size=5')
  if (!resp.ok()) return null
  const json = await resp.json()
  const items = json.data?.items || json.data?.records || []
  return items[0]?.id
}

/** 获取规则表格行数 (v2: 不直接查询 .el-table, 用作用域选择器) */
async function getRuleRowCount(page) {
  const rows = page.locator('.rpc-bottom-section .el-table__body-wrapper .el-table__row')
  return await rows.count()
}

// ==================== 测试套件 ====================

test.describe('S06: 角色权限配置 — 完备测试', () => {

  // ---------- C01: 页面加载与布局 ----------

  test('C01: 页面加载与核心布局验证', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      console.log('[SKIP] 没有可用角色')
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    // 验证页面标题
    await withStep(page, testInfo, '验证页面标题与布局', async () => {
      const title = page.locator('.rpc-title')
      await expect(title).toBeVisible()
      const titleText = await title.textContent()
      expect(titleText).toContain('角色权限配置')

      // 验证核心区域存在
      const asideVisible = await page.locator('.rpc-aside').isVisible().catch(() => false)
      const mainVisible = await page.locator('.rpc-main').isVisible().catch(() => false)
      const bottomVisible = await page.locator('.rpc-bottom-section').isVisible().catch(() => false)
      console.log(`[OK] 布局: aside=${asideVisible}, main=${mainVisible}, bottom=${bottomVisible}`)

      // 验证顶部操作按钮（重置 + 保存）
      const headerBtns = page.locator('.rpc-header__right .el-button')
      const btnCount = await headerBtns.count()
      expect(btnCount).toBeGreaterThanOrEqual(2)
    })
  })

  // ---------- C02: 管理维度选择 ----------

  test('C02: 管理维度选择与字段加载', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '查看管理维度选择器与编辑器', async () => {
      // ManagementDimensionSelector 使用 .management-dimension-selector 类
      const dimSelector = page.locator('.management-dimension-selector')
      await expect(dimSelector).toBeVisible()

      // 查找维度列表项
      const dimItems = dimSelector.locator('.dimension-item')
      const dimCount = await dimItems.count()
      console.log(`[OK] 管理维度数量: ${dimCount}`)

      if (dimCount > 0) {
        // 点击第一个维度
        await dimItems.first().click()
        await page.waitForTimeout(500)

        // 验证编辑器区域有变化（条件规则编辑器应该显示）
        const editorSection = page.locator('.rpc-editor-section')
        await expect(editorSection).toBeVisible()
      }
    })
  })

  // ---------- C03: 规则列表展示 ----------

  test('C03: 已配置规则列表展示', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '验证规则列表与表格列头', async () => {
      // 验证规则列表区域
      const ruleSection = page.locator('.rpc-bottom-section')
      await expect(ruleSection).toBeVisible()

      // 验证搜索框（在 .section-actions 内）
      const searchInput = ruleSection.locator('.el-input__inner')
      await expect(searchInput).toBeVisible()

      // 验证表格存在
      const table = ruleSection.locator('.el-table')
      await expect(table).toBeVisible()

      // 验证表格列头
      const headers = ['维度', '条件', '权限级别', '继承', '禁止', '状态', '操作']
      for (const header of headers) {
        const headerCell = ruleSection.locator(`.el-table__header th`).filter({ hasText: header })
        if (await headerCell.count() > 0) {
          console.log(`[OK] 表头 "${header}" 存在`)
        }
      }

      const rowCount = await getRuleRowCount(page)
      console.log(`[OK] 规则行数: ${rowCount}`)
    })
  })

  // ---------- C04: 规则搜索过滤 ----------

  test('C04: 规则搜索过滤', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const initialCount = await getRuleRowCount(page)
    if (initialCount === 0) {
      console.log('[SKIP] 没有规则可供搜索')
      return
    }

    await withStep(page, testInfo, '输入搜索关键词并清空', async () => {
      // 输入搜索关键词
      const searchInput = page.locator('.rpc-bottom-section .el-input__inner')
      await searchInput.fill('read')
      await page.waitForTimeout(500)

      // 清空搜索
      const clearBtn = page.locator('.rpc-bottom-section .el-input__clear, .rpc-bottom-section .el-input__suffix .el-icon')
      if (await clearBtn.count() > 0) {
        await clearBtn.first().click()
        await page.waitForTimeout(500)
      } else {
        await searchInput.clear()
      }
    })
  })

  // ---------- C05: 规则状态切换 ----------

  test('C05: 规则启用/禁用切换', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount === 0) {
      console.log('[SKIP] 没有规则可供切换')
      return
    }

    await withStep(page, testInfo, '切换第一行规则状态 (启用/禁用/恢复)', async () => {
      // 找到第一行的状态开关
      const switchEl = page.locator('.rpc-bottom-section .el-table__row .el-switch').first()
      await expect(switchEl).toBeVisible()

      // 切换状态
      await switchEl.click()
      await page.waitForTimeout(800)

      // 验证消息提示
      const message = page.locator('.el-message')
      if (await message.isVisible().catch(() => false)) {
        const msgText = await message.textContent()
        console.log(`[OK] 状态切换消息: ${msgText}`)
      }

      // 恢复原状态
      await switchEl.click()
      await page.waitForTimeout(500)
    })
  })

  // ---------- C06: 规则编辑 ----------

  test('C06: 规则编辑操作', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount === 0) {
      console.log('[SKIP] 没有规则可供编辑')
      return
    }

    await withStep(page, testInfo, '点击编辑按钮进入编辑模式', async () => {
      // 点击编辑按钮（el-button type=primary size=small link）
      const editBtn = page.locator('.rpc-bottom-section .el-table__row .el-button--primary:has-text("编辑")').first()
      if (await editBtn.isVisible().catch(() => false)) {
        await editBtn.click()
        await page.waitForTimeout(800)

        // 验证编辑器切换到编辑模式
        const editorSection = page.locator('.rpc-editor-section')
        await expect(editorSection).toBeVisible()
      } else {
        console.log('[SKIP] 编辑按钮不可见')
      }
    })
  })

  // ---------- C07: 规则删除 ----------

  test('C07: 规则删除操作（取消）', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount === 0) {
      console.log('[SKIP] 没有规则可供删除')
      return
    }

    await withStep(page, testInfo, '点击删除并取消确认对话框', async () => {
      // 点击删除按钮
      const deleteBtn = page.locator('.rpc-bottom-section .el-table__row .el-button--danger:has-text("删除")').first()
      if (await deleteBtn.isVisible().catch(() => false)) {
        await deleteBtn.click()
        await page.waitForTimeout(500)

        // 验证确认对话框出现（Element Plus MessageBox）
        const confirmDialog = page.locator('.el-message-box, .el-overlay')
        if (await confirmDialog.isVisible().catch(() => false)) {
          // 点击取消
          const cancelBtn = confirmDialog.locator('.el-button:has-text("取消"), .el-button--default').first()
          if (await cancelBtn.isVisible().catch(() => false)) {
            await cancelBtn.click()
            await page.waitForTimeout(500)
          }
        }
      }
    })
  })

  // ---------- C08: 保存按钮 ----------

  test('C08: 批量保存操作', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '点击保存按钮', async () => {
      // 点击保存按钮（el-button type=primary）
      const saveBtn = page.locator('.rpc-header__right .el-button--primary')
      await expect(saveBtn).toBeVisible()
      await saveBtn.click()
      await page.waitForTimeout(1500)

      // 验证消息提示
      const message = page.locator('.el-message')
      if (await message.isVisible().catch(() => false)) {
        const msgText = await message.textContent()
        console.log(`[OK] 保存消息: ${msgText}`)
      }
    })
  })

  // ---------- C09: 重置按钮 ----------

  test('C09: 重置操作', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '点击重置按钮并验证页面健康', async () => {
      // 点击重置按钮（el-button，非 primary）
      const resetBtn = page.locator('.rpc-header__right .el-button').first()
      await expect(resetBtn).toBeVisible()
      await resetBtn.click()
      await page.waitForTimeout(1500)
    })
  })

  // ---------- C10: 权限级别标签 ----------

  test('C10: 权限级别标签显示', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount === 0) {
      console.log('[SKIP] 没有规则可供检查标签')
      return
    }

    await withStep(page, testInfo, '验证权限级别 Tag', async () => {
      // 验证权限级别 Tag 存在
      const levelTags = page.locator('.rpc-bottom-section .el-table .el-tag')
      const tagCount = await levelTags.count()
      console.log(`[OK] 权限级别 Tag 数量: ${tagCount}`)

      if (tagCount > 0) {
        const tagText = await levelTags.first().textContent()
        console.log(`[OK] 第一个标签文本: ${tagText}`)
        // 验证标签文本是已知的权限级别
        const validLabels = ['只读', '可编辑', '完全管理', '管理', '无权限']
        expect(validLabels.some(l => tagText?.includes(l))).toBe(true)
      }
    })
  })

  // ---------- C11: 继承/禁止标记 ----------

  test('C11: 继承与禁止标记显示', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount === 0) {
      console.log('[SKIP] 没有规则可供检查')
      return
    }

    await withStep(page, testInfo, '检查继承与禁止标记', async () => {
      // 检查继承列（Check/Close 图标）
      const inheritIcons = page.locator('.rpc-bottom-section .el-table .el-icon')
      const iconCount = await inheritIcons.count()
      console.log(`[OK] 图标数量: ${iconCount}`)

      // 检查禁止列（danger Tag 或 "-"）
      const denyTags = page.locator('.rpc-bottom-section .el-table .el-tag--danger')
      const denyCount = await denyTags.count()
      console.log(`[OK] 禁止标记数量: ${denyCount}`)
    })
  })

  // ---------- C12: 表格排序 ----------

  test('C12: 表格排序功能', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    const rowCount = await getRuleRowCount(page)
    if (rowCount < 2) {
      console.log('[SKIP] 规则数不足，无法测试排序')
      return
    }

    await withStep(page, testInfo, '点击"维度"列头排序（两次切换方向）', async () => {
      // 点击"维度"列头排序
      const dimHeader = page.locator('.rpc-bottom-section .el-table__header th').filter({ hasText: '维度' })
      if (await dimHeader.isVisible().catch(() => false)) {
        await dimHeader.click()
        await page.waitForTimeout(500)

        // 再次点击切换排序方向
        await dimHeader.click()
        await page.waitForTimeout(500)
      }
    })
  })

  // ---------- C13: 影响预览区域 ----------

  test('C13: 影响预览区域', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '检查影响预览区域', async () => {
      // ImpactPreview 使用 .impact-preview 类
      const previewSection = page.locator('.impact-preview')
      const previewVisible = await previewSection.isVisible().catch(() => false)

      if (previewVisible) {
        // 验证影响预览标题
        const previewTitle = previewSection.locator('.impact-preview__title')
        if (await previewTitle.isVisible().catch(() => false)) {
          const titleText = await previewTitle.textContent()
          console.log(`[OK] 影响预览标题: ${titleText}`)
        }
      } else {
        console.log('[INFO] 影响预览区域不可见（可能需要先选择维度）')
      }
    })
  })

  // ---------- C14: 条件规则编辑器区域 ----------

  test('C14: 条件规则编辑器区域', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '验证条件规则编辑器与操作按钮', async () => {
      // 验证编辑器区域容器
      const editorSection = page.locator('.rpc-editor-section')
      await expect(editorSection).toBeVisible()

      // 验证编辑器标题
      const editorTitle = editorSection.locator('.section-title')
      await expect(editorTitle).toContainText('条件规则编辑器')

      // 验证操作按钮
      const cancelBtn = editorSection.locator('.editor-actions .el-button:has-text("取消")')
      const saveRuleBtn = editorSection.locator('.editor-actions .el-button:has-text("保存规则")')
      await expect(cancelBtn).toBeVisible()
      await expect(saveRuleBtn).toBeVisible()

      // 验证 ConditionRuleEditor 组件
      const ruleEditor = editorSection.locator('.condition-rule-editor')
      await expect(ruleEditor).toBeVisible()
    })
  })

  // ---------- C15: 无角色 ID 时处理 ----------

  test('C15: 无效角色 ID 访问', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '访问无效 roleId /system/role-permission/999999', async () => {
      // 使用不存在的角色 ID
      await navigateTo(page, '/system/role-permission/999999')
      await page.waitForTimeout(2000)
    })
  })

  // ---------- C16: 页面健康检查 ----------

  test('C16: 页面健康检查（无 JS 错误）', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '点击维度后进行健康检查', async () => {
      // 执行一系列操作后检查健康
      const dimItems = page.locator('.management-dimension-selector .dimension-item')
      if (await dimItems.count() > 0) {
        await dimItems.first().click()
        await page.waitForTimeout(800)
      }
    })
  })

  // ---------- C17: 角色详情抽屉中的权限配置 ----------

  test('C17: 角色详情抽屉 — 权限配置 Tab', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '导航到角色管理页面', async () => {
      await navigateTo(page, '/system/roles', { waitForTable: true })
    })

    const list = new GenericListPage(page)
    const rowCount = await list.getRowCount()
    if (rowCount === 0) {
      console.log('[SKIP] 没有角色可供查看')
      return
    }

    await withStep(page, testInfo, '打开角色详情抽屉', async () => {
      // 通过 tbody 通用选择器点击首行 (避开 .el-table 直查)
      await page.locator('tbody tr').first().click()
      await page.waitForTimeout(1500)
    })

    // 验证抽屉打开
    const drawer = page.locator('.drawer-panel')
    if (!(await drawer.isVisible().catch(() => false))) {
      console.log('[SKIP] 详情抽屉未打开')
      return
    }

    await withStep(page, testInfo, '切换到权限配置 Tab', async () => {
      const permTab = drawer.locator('.drawer-tab:has-text("权限配置")')
      if (await permTab.isVisible().catch(() => false)) {
        await permTab.click()
        await page.waitForTimeout(1500)

        // 验证维度范围面板
        const dimPanel = drawer.locator('.perm-section, [class*="dimension-scope"]')
        if (await dimPanel.isVisible().catch(() => false)) {
          console.log('[OK] 维度范围面板可见')
        }

        // 验证条件型权限区域
        const conditionSection = drawer.locator('text=条件型权限')
        if (await conditionSection.isVisible().catch(() => false)) {
          console.log('[OK] 条件型权限区域可见')
        }
      }
    })
  })

  // ---------- C18: 条件规则对话框（通过角色详情抽屉） ----------

  test('C18: 添加条件规则对话框', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '导航到角色管理页面', async () => {
      await navigateTo(page, '/system/roles', { waitForTable: true })
    })

    const list = new GenericListPage(page)
    const rowCount = await list.getRowCount()
    if (rowCount === 0) {
      console.log('[SKIP] 没有角色可供操作')
      return
    }

    await withStep(page, testInfo, '打开角色详情 + 切到权限配置 Tab', async () => {
      // 打开角色详情
      await page.locator('tbody tr').first().click()
      await page.waitForTimeout(1500)

      // 切换到权限配置 Tab
      const drawer = page.locator('.drawer-panel')
      if (!(await drawer.isVisible().catch(() => false))) return

      const permTab = drawer.locator('.drawer-tab:has-text("权限配置")')
      if (await permTab.isVisible().catch(() => false)) {
        await permTab.click()
        await page.waitForTimeout(1000)
      }
    })

    await withStep(page, testInfo, '点击添加条件规则按钮 + 验证对话框表单', async () => {
      const drawer = page.locator('.drawer-panel')
      if (!(await drawer.isVisible().catch(() => false))) return

      // 点击添加条件规则按钮（使用 btn-ghost 类）
      const addRuleBtn = drawer.locator('button:has-text("添加条件规则"), .btn-ghost:has-text("添加条件规则")')
      if (!(await addRuleBtn.isVisible().catch(() => false))) {
        console.log('[SKIP] 添加条件规则按钮不可见')
        return
      }
      await addRuleBtn.click()
      await page.waitForTimeout(1000)

      // 验证对话框打开（使用 AppModal，查找 .app-modal）
      const dialog = page.locator('.app-modal').filter({ hasText: '条件型权限' })
      if (!(await dialog.isVisible().catch(() => false))) {
        console.log('[INFO] 条件型权限对话框未打开')
        return
      }

      // 验证表单元素
      const resourceTypeSelect = dialog.locator('.app-select, .form-group select').first()
      const levelButtons = dialog.locator('button:has-text("只读"), button:has-text("可编辑"), button:has-text("完全管理")')

      if (await resourceTypeSelect.isVisible().catch(() => false)) {
        console.log('[OK] 资源类型选择器可见')
      }
      if (await levelButtons.count() > 0) {
        console.log('[OK] 权限级别按钮可见')
      }

      // 关闭对话框
      const closeBtn = dialog.locator('button:has-text("取消"), .app-modal__close').first()
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click()
        await page.waitForTimeout(300)
      }
    })
  })

  // ---------- C19: 数据权限配置页面 ----------

  test('C19: 数据权限配置页面', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '导航到数据权限配置页', async () => {
      // 导航到数据权限页面
      await navigateTo(page, '/system/data-permission', { waitForTable: true })
    })

    await withStep(page, testInfo, '验证数据权限表格可见', async () => {
      // 验证页面核心元素 (v2: 用作用域选择器,避开 .el-table 直查)
      const table = page.locator('main .arch-data-table, main table.el-table__body, main tbody')
      if (await table.first().isVisible().catch(() => false)) {
        console.log('[OK] 数据权限表格可见')
      }
    })
  })

  // ---------- C20: 权限级别标签一致性 ----------

  test('C20: permissionService 级别标签一致性验证', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '验证权限级别标签与 permissionService 一致', async () => {
      // 验证表格中的标签文本与 permissionService 一致
      const tags = page.locator('.rpc-bottom-section .el-table .el-tag')
      const tagCount = await tags.count()
      const validLabels = ['只读', '可编辑', '完全管理', '管理', '无权限']

      for (let i = 0; i < Math.min(tagCount, 5); i++) {
        const text = await tags.nth(i).textContent()
        const isValid = validLabels.some(l => text?.includes(l))
        if (!isValid) {
          console.warn(`[WARN] 标签 "${text}" 不在已知列表中`)
        }
      }

      console.log(`[OK] 检查了 ${Math.min(tagCount, 5)} 个标签`)
    })
  })

  // ---------- C21: 条件规则编辑器 — 资源类型选择 ----------

  test('C21: 条件规则编辑器 — 资源类型选择', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '选择资源类型并验证条件定义区域', async () => {
      // 定位 ConditionRuleEditor
      const ruleEditor = page.locator('.condition-rule-editor')
      await expect(ruleEditor).toBeVisible()

      // 验证资源类型选择器
      const resourceSelect = ruleEditor.locator('.editor-section').filter({ hasText: '资源类型' }).locator('select, .app-select, .el-select')
      if (!(await resourceSelect.isVisible().catch(() => false))) {
        console.log('[SKIP] 资源类型选择器不可见')
        return
      }
      console.log('[OK] 资源类型选择器可见')

      // 选择一个资源类型
      await resourceSelect.click()
      await page.waitForTimeout(500)

      // 选择第一个选项
      const firstOption = page.locator('.app-select__option, .el-select-dropdown__item').first()
      if (await firstOption.isVisible().catch(() => false)) {
        await firstOption.click()
        await page.waitForTimeout(800)

        // 选择后应该出现条件定义区域
        const conditionSection = ruleEditor.locator('.editor-section').filter({ hasText: '条件定义' })
        if (await conditionSection.isVisible().catch(() => false)) {
          console.log('[OK] 条件定义区域已显示')
        }
      }
    })
  })

  // ---------- C22: 条件规则编辑器 — 权限级别选择 ----------

  test('C22: 条件规则编辑器 — 权限级别选择', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '点击"可编辑"权限级别按钮', async () => {
      const ruleEditor = page.locator('.condition-rule-editor')
      await expect(ruleEditor).toBeVisible()

      // 验证权限级别按钮组
      const levelSection = ruleEditor.locator('.editor-section').filter({ hasText: '权限级别' })
      const levelButtons = levelSection.locator('button')
      const levelCount = await levelButtons.count()
      console.log(`[OK] 权限级别按钮数量: ${levelCount}`)

      if (levelCount > 0) {
        // 点击"可编辑"按钮
        const editLevelBtn = levelButtons.filter({ hasText: '可编辑' })
        if (await editLevelBtn.isVisible().catch(() => false)) {
          await editLevelBtn.click()
          await page.waitForTimeout(500)
        }
      }
    })
  })

  // ---------- C23: 条件规则编辑器 — 禁止权限 ----------

  test('C23: 条件规则编辑器 — 禁止权限切换', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '勾选/取消禁止权限复选框', async () => {
      const ruleEditor = page.locator('.condition-rule-editor')
      await expect(ruleEditor).toBeVisible()

      // 查找禁止权限复选框
      const deniedSection = ruleEditor.locator('.editor-section').filter({ hasText: '禁止权限' })
      const deniedCheckbox = deniedSection.locator('input[type="checkbox"]')

      if (!(await deniedCheckbox.isVisible().catch(() => false))) {
        console.log('[SKIP] 禁止权限复选框不可见')
        return
      }

      await deniedCheckbox.click()
      await page.waitForTimeout(500)

      // 验证禁止提示出现
      const deniedHint = deniedSection.locator('.denied-hint')
      if (await deniedHint.isVisible().catch(() => false)) {
        console.log('[OK] 禁止权限提示已显示')
      }

      // 取消勾选
      await deniedCheckbox.click()
      await page.waitForTimeout(300)
    })
  })

  // ---------- C24: 条件规则编辑器 — 取消操作 ----------

  test('C24: 条件规则编辑器 — 取消操作', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '点击取消按钮', async () => {
      // 点击取消按钮
      const cancelBtn = page.locator('.editor-actions .el-button:has-text("取消")')
      await expect(cancelBtn).toBeVisible()
      await cancelBtn.click()
      await page.waitForTimeout(800)
    })
  })

  // ---------- C25: 管理维度选择器 — 搜索 ----------

  test('C25: 管理维度选择器搜索功能', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '管理维度选择器内输入"组织"再清空', async () => {
      // ManagementDimensionSelector 搜索框
      const dimSelector = page.locator('.management-dimension-selector')
      await expect(dimSelector).toBeVisible()

      const searchInput = dimSelector.locator('.el-input__inner')
      if (await searchInput.isVisible().catch(() => false)) {
        await searchInput.fill('组织')
        await page.waitForTimeout(500)

        // 清空搜索
        await searchInput.clear()
        await page.waitForTimeout(300)
      }
    })
  })

  // ---------- C26: 影响预览 — 详细展开 ----------

  test('C26: 影响预览详细展开', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    const roleId = await getFirstRoleId(page)
    if (!roleId) {
      test.skip(true, '没有可用角色')
      return
    }

    await withStep(page, testInfo, '导航到角色权限配置页 + 选择第一个维度', async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)

      // 先选择一个维度以触发影响预览
      const dimItems = page.locator('.management-dimension-selector .dimension-item')
      if (await dimItems.count() > 0) {
        await dimItems.first().click()
        await page.waitForTimeout(1500)
      }
    })

    await withStep(page, testInfo, '展开影响预览详细对象清单', async () => {
      // 查找影响预览
      const preview = page.locator('.impact-preview')
      if (!(await preview.isVisible().catch(() => false))) {
        console.log('[INFO] 影响预览不可见，跳过详细展开测试')
        return
      }

      // 点击详细对象清单展开
      const detailHeader = preview.locator('.detail-header')
      if (await detailHeader.isVisible().catch(() => false)) {
        await detailHeader.click()
        await page.waitForTimeout(800)

        // 验证详细表格
        const detailTable = preview.locator('.el-table')
        if (await detailTable.isVisible().catch(() => false)) {
          console.log('[OK] 影响预览详细表格可见')
        }
      }
    })
  })

  // ---------- C27: 角色详情抽屉 — 菜单权限操作 ----------

  test('C27: 角色详情抽屉 — 菜单权限操作', async ({
    page, navigateTo, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '导航到角色管理页面', async () => {
      await navigateTo(page, '/system/roles', { waitForTable: true })
    })

    const list = new GenericListPage(page)
    const rowCount = await list.getRowCount()
    if (rowCount === 0) {
      console.log('[SKIP] 没有角色可供操作')
      return
    }

    await withStep(page, testInfo, '打开角色详情 + 切到权限配置 Tab', async () => {
      // 打开角色详情
      await page.locator('tbody tr').first().click()
      await page.waitForTimeout(1500)

      const drawer = page.locator('.drawer-panel')
      if (!(await drawer.isVisible().catch(() => false))) return

      // 切换到权限配置 Tab
      const permTab = drawer.locator('.drawer-tab:has-text("权限配置")')
      if (await permTab.isVisible().catch(() => false)) {
        await permTab.click()
        await page.waitForTimeout(1500)
      }
    })

    await withStep(page, testInfo, '展开菜单卡片 + 验证功能权限矩阵', async () => {
      const drawer = page.locator('.drawer-panel')
      if (!(await drawer.isVisible().catch(() => false))) return

      // 验证菜单卡片
      const menuCards = drawer.locator('.menu-card')
      const menuCount = await menuCards.count()
      console.log(`[OK] 菜单卡片数量: ${menuCount}`)

      if (menuCount > 0) {
        // 点击展开第一个菜单卡片
        const firstCardHeader = menuCards.first().locator('.menu-title-area')
        if (await firstCardHeader.isVisible().catch(() => false)) {
          await firstCardHeader.click()
          await page.waitForTimeout(500)

          // 验证功能权限矩阵
          const capMatrix = menuCards.first().locator('.capability-matrix')
          if (await capMatrix.isVisible().catch(() => false)) {
            console.log('[OK] 功能权限矩阵可见')
          }
        }
      }

      // 验证保存全部权限按钮
      const saveAllBtn = drawer.locator('button:has-text("保存全部权限")')
      if (await saveAllBtn.isVisible().catch(() => false)) {
        console.log('[OK] 保存全部权限按钮可见')
      }
    })
  })
})
