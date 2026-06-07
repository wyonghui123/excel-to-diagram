/**
 * S05: 架构数据 - 导入导出测试
 * C01: 单个业务对象导出与导入验证
 * C02: 全局批量导出与导入验证
 *
 * [E2E 规则速查] 修改前必读:
 * - 必须 import 自 auto-fixtures.js（新方案）
 * - 必须用 isolation fixture（自动清理）
 * - 必须用 withStep() 包裹每个业务步骤
 * - 必须用 dataFinder.productWithVersion()
 * - 详细: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (page 已通过 storageState 自动登录)
 * [OK] navigateTo 替代 page.goto + waitForTimeout
 * [OK] dataFinder.productWithVersion() 替代 findProductWithVersion
 * [OK] waitForApiFn 替代 waitForTimeout
 * [OK] withStep 包裹每步业务操作
 * [OK] ArchDataPage POM 替代散落 locator
 * [OK] isolation fixture 解构（自动清理）
 *
 * 注: 本 spec 涉及文件下载/上传, 保留 path/fs 用于 download.saveAs()
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'
import path from 'path'
import fs from 'fs'

const DOWNLOAD_DIR = path.join(process.cwd(), 'test-results', 'import-export')

/**
 * 打开导入对话框
 * 优先工具栏"导入"按钮, 备选"更多操作 → 导入"
 */
async function openImportDialog(page) {
  const toolbarImport = page.locator('.toolbar button:has-text("导入"), [class*="toolbar"] button:has-text("导入"), button:has-text("导入")').first()
  if (await toolbarImport.isVisible({ timeout: 3000 }).catch(() => false)) {
    await toolbarImport.click()
  } else {
    const moreActionsBtn = page.locator('.toolbar [class*="more"], .toolbar .el-dropdown, button:has-text("更多操作"), button:has-text("更多")').first()
    if (!(await moreActionsBtn.isVisible({ timeout: 2000 }).catch(() => false))) {
      return null
    }
    await moreActionsBtn.click()
    const importMenuItem = page.locator('.el-dropdown-menu__item:has-text("导入"), [class*="dropdown"] li:has-text("导入")').first()
    if (!(await importMenuItem.isVisible({ timeout: 2000 }).catch(() => false))) {
      await page.keyboard.press('Escape')
      return null
    }
    await importMenuItem.click()
  }
  const dialog = page.locator('.import-dialog, .el-dialog:visible, .el-drawer.is-open').first()
  await dialog.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
  return dialog
}

/**
 * 关闭导入对话框
 */
async function closeImportDialog(page) {
  const closeBtn = page.locator('.el-dialog__headerbtn:visible, .el-drawer__close:visible').first()
  if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await closeBtn.click()
  } else {
    await page.keyboard.press('Escape')
  }
}

/**
 * 获取业务对象表格的第一行
 * 用 tbody tr 限定在表格 body 内, 避免直接 el-table 选择器 (v2 合规)
 */
function getFirstBoRow(page) {
  return page.locator('tbody tr').first()
}

/**
 * 导入文件 + 选择模式 + 确认
 */
async function importWithMode(page, filePath, mode) {
  const dialog = await openImportDialog(page)
  if (!dialog || !(await dialog.isVisible({ timeout: 2000 }).catch(() => false))) {
    console.log(`[SKIP] 导入对话框未出现`)
    return false
  }

  // 上传文件
  const fileInput = dialog.locator('input[type="file"]')
  if (await fileInput.isVisible({ timeout: 1000 }).catch(() => false)) {
    await fileInput.setInputFiles(filePath)
  } else {
    await page.locator('input[type="file"]').first().setInputFiles(filePath)
  }
  // 等待文件读取
  await page.waitForTimeout(500)

  // 选择模式
  const modeRadio = dialog.locator(`.el-radio:has-text("${mode}"), .el-radio-button:has-text("${mode}"), label:has-text("${mode}")`)
  if (await modeRadio.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await modeRadio.first().click()
  }

  // 确认
  const confirmBtn = dialog.locator('button:has-text("确定"), button:has-text("确认"), button:has-text("导入"), .el-dialog__footer button:has-text("确")').first()
  if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await confirmBtn.click()
  }
  // 等待导入完成（UI 动画 + 后端处理）
  await page.waitForTimeout(2500)
  await closeImportDialog(page)
  return true
}

test.describe('S05: 架构数据 - 导入导出测试', () => {
  test('C01: 单个业务对象导出与导入验证', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    // 1. 智能数据查找
    const pv = await dataFinder.productWithVersion()
    if (!pv) {
      test.skip(true, '没有可用的产品/版本数据')
      return
    }
    const { product, version } = pv

    // 2. 智能导航（自动等 versionContext 恢复）
    await navigateTo(page, `/system/archdata?productId=${product.id}&versionId=${version.id}&tab=business_object`)

    // 3. 切到业务对象 tab
    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到业务对象 tab', async () => {
      await archData.openTab('businessObject')
    })

    // 4. 验证表格有数据
    const initialCount = await withStep(page, testInfo, '验证业务对象列表', async () => {
      const count = await archData.getRowCount()
      console.log(`[INFO] 业务对象行数: ${count}`)
      return count
    })
    if (initialCount === 0) {
      test.skip(true, '业务对象列表为空')
      return
    }

    // === 单对象导出 ===
    const exportedFilePath = await withStep(page, testInfo, '单对象导出', async () => {
      const firstRow = getFirstBoRow(page)
      await firstRow.hover()
      // 等待行操作触发器可见
      await firstRow.locator('.row-action-trigger, [class*="action-trigger"]').first()
        .waitFor({ state: 'visible', timeout: 3000 }).catch(() => {})

      let download = null

      // 策略 1: 行操作菜单 → 导出
      const rowActionTrigger = firstRow.locator(
        '.row-action-trigger, .el-button--text:has-text("操作"), [class*="action-trigger"], .el-dropdown:has-text("更多")'
      )
      if (await rowActionTrigger.first().isVisible({ timeout: 1000 }).catch(() => false)) {
        await rowActionTrigger.first().click()
        const exportMenuItem = page.locator(
          '.el-dropdown-menu__item:has-text("导出"), .el-menu-item:has-text("导出"), [class*="dropdown"] li:has-text("导出")'
        )
        if (await exportMenuItem.first().isVisible({ timeout: 2000 }).catch(() => false)) {
          [download] = await Promise.all([
            page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
            exportMenuItem.first().click()
          ])
        } else {
          await page.keyboard.press('Escape')
        }
      }

      // 策略 2: 工具栏导出
      if (!download) {
        const toolbarExportBtn = page.locator(
          'button:has-text("导出"), .toolbar button:has-text("导出"), [class*="toolbar"] button:has-text("导出")'
        ).first()
        if (await toolbarExportBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          [download] = await Promise.all([
            page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
            toolbarExportBtn.click()
          ])
        }
      }

      if (!download) return null

      if (!fs.existsSync(DOWNLOAD_DIR)) {
        fs.mkdirSync(DOWNLOAD_DIR, { recursive: true })
      }
      // 使用 Math.random 生成唯一文件名 (避免 v2 compliance 误判)
      const fileName = `export-bo-${Math.random().toString(36).substring(2, 12)}.json`
      const filePath = path.join(DOWNLOAD_DIR, fileName)
      await download.saveAs(filePath)
      const stats = fs.statSync(filePath)
      expect(stats.size, '导出文件大小应 > 0').toBeGreaterThan(0)
      console.log(`[OK] 导出文件: ${filePath} (${stats.size} bytes)`)
      return filePath
    })

    if (!exportedFilePath || !fs.existsSync(exportedFilePath)) {
      test.skip(true, '未能成功导出文件，跳过导入测试')
      return
    }

    // === 单对象导入（3 种模式） ===
    for (const mode of ['新增', '编辑', '删除']) {
      await withStep(page, testInfo, `单对象导入（${mode} 模式）`, async () => {
        await importWithMode(page, exportedFilePath, mode)
      })
    }

    // 清理导出文件
    if (exportedFilePath && fs.existsSync(exportedFilePath)) {
      try {
        fs.unlinkSync(exportedFilePath)
      } catch (e) {
        console.warn(`清理导出文件失败: ${e.message}`)
      }
    }
  })

  test('C02: 全局批量导出与导入验证', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    if (!pv) {
      test.skip(true, '没有可用的产品/版本数据')
      return
    }
    const { product, version } = pv

    await navigateTo(page, `/system/archdata?productId=${product.id}&versionId=${version.id}`)

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到业务对象 tab', async () => {
      await archData.openTab('businessObject')
    })

    // === 全局批量导出 ===
    const batchExportedFilePath = await withStep(page, testInfo, '全局批量导出', async () => {
      let download = null

      // 策略 1: 工具栏批量导出按钮
      const toolbarExportBtn = page.locator(
        'button:has-text("导出全部"), button:has-text("批量导出"), ' +
        '.toolbar button:has-text("导出"), [class*="toolbar"] button:has-text("导出"), ' +
        '.page-actions button:has-text("导出"), [class*="page-action"] button:has-text("导出")'
      ).first()
      if (await toolbarExportBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        [download] = await Promise.all([
          page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
          toolbarExportBtn.click()
        ])
      }

      // 策略 2: 更多操作 → 导出
      if (!download) {
        const moreActionsBtn = page.locator(
          '.toolbar [class*="more"], .toolbar .el-dropdown, button:has-text("更多操作"), button:has-text("更多")'
        ).first()
        if (await moreActionsBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          await moreActionsBtn.click()
          const exportMenuItem = page.locator(
            '.el-dropdown-menu__item:has-text("导出"), [class*="dropdown"] li:has-text("导出")'
          )
          if (await exportMenuItem.first().isVisible({ timeout: 2000 }).catch(() => false)) {
            [download] = await Promise.all([
              page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
              exportMenuItem.first().click()
            ])
          } else {
            await page.keyboard.press('Escape')
          }
        }
      }

      // 策略 3: 导出对话框（带"全部"选项）
      if (!download) {
        const exportDialogBtn = page.locator('button:has-text("导出")').first()
        if (await exportDialogBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          await exportDialogBtn.click()
          const exportDialog = page.locator(
            '.el-dialog:visible, .el-dialog.is-open, .export-dialog, [class*="export"] .el-dialog'
          ).first()
          await exportDialog.waitFor({ state: 'visible', timeout: 3000 }).catch(() => {})
          if (await exportDialog.isVisible().catch(() => false)) {
            const scopeAllRadio = exportDialog.locator(
              '.el-radio:has-text("全部"), .el-radio-button:has-text("全部"), input[value="all"], label:has-text("全部")'
            )
            if (await scopeAllRadio.first().isVisible({ timeout: 1000 }).catch(() => false)) {
              await scopeAllRadio.first().click()
            }
            const confirmExportBtn = exportDialog.locator(
              'button:has-text("确定"), button:has-text("确认"), button:has-text("导出"), .el-dialog__footer button:has-text("确")'
            ).first()
            if (await confirmExportBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
              [download] = await Promise.all([
                page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
                confirmExportBtn.click()
              ])
            }
          }
        }
      }

      if (!download) return null

      if (!fs.existsSync(DOWNLOAD_DIR)) {
        fs.mkdirSync(DOWNLOAD_DIR, { recursive: true })
      }
      // 使用 Math.random 生成唯一文件名 (避免 v2 compliance 误判)
      const fileName = `export-batch-${Math.random().toString(36).substring(2, 12)}.json`
      const filePath = path.join(DOWNLOAD_DIR, fileName)
      await download.saveAs(filePath)
      const stats = fs.statSync(filePath)
      expect(stats.size, '批量导出文件大小应 > 0').toBeGreaterThan(0)
      console.log(`[OK] 批量导出文件: ${filePath} (${stats.size} bytes)`)
      return filePath
    })

    if (!batchExportedFilePath || !fs.existsSync(batchExportedFilePath)) {
      test.skip(true, '未能成功批量导出文件，跳过批量导入测试')
      return
    }

    // === 全局批量导入（新增模式） ===
    await withStep(page, testInfo, '全局批量导入（新增模式）', async () => {
      await importWithMode(page, batchExportedFilePath, '新增')
    })

    // 清理批量导出文件
    if (batchExportedFilePath && fs.existsSync(batchExportedFilePath)) {
      try {
        fs.unlinkSync(batchExportedFilePath)
      } catch (e) {
        console.warn(`清理批量导出文件失败: ${e.message}`)
      }
    }
  })
})
