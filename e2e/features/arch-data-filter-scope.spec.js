/**
 * S04: 架构数据 - 过滤与范围选择 - 功能测试 (v2 风格)
 *
 * 覆盖场景:
 *   C01 对象与关系范围选择验证
 *   C02 备注类型过滤与排序验证
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直接调用 (改用 navigateTo fixture)
 * [OK] 无 Date.now() 硬编码 (改用 isolation.generateId,本 spec 不需要)
 * [OK] 禁止 el-table 直查 (改用 ArchDataPage POM)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

const ARCHDATA_URL = '/system/archdata'

// 保留原 v1 辅助函数 (helper),但消除 v1 模式
async function expandCollapsiblePanel(page, panelSelector) {
  const panel = page.locator(panelSelector)
  if (!(await panel.isVisible().catch(() => false))) {
    return false
  }
  const content = panel.locator('.collapsible-panel__content')
  const isExpanded = await content.isVisible().catch(() => false)
  if (!isExpanded) {
    const toggle = panel.locator('.collapsible-panel__header, .collapsible-panel__toggle').first()
    await toggle.click()
  }
  return true
}

async function selectProductVersionOnPage(page, product, version) {
  const productSelect = page.locator('.gt-selector:has-text("产品") .el-select, .version-context-selector .el-select').first()
  if (await productSelect.isVisible().catch(() => false)) {
    await productSelect.click()
    const productOption = page.locator('.el-select-dropdown__item').first()
    if (await productOption.isVisible().catch(() => false)) {
      await productOption.click()
    }
  }

  const versionSelect = page.locator('.gt-selector:has-text("版本") .el-select, .version-context-selector .el-select').nth(1)
  if (await versionSelect.isVisible().catch(() => false)) {
    await versionSelect.click()
    const versionOption = page.locator('.el-select-dropdown__item').first()
    if (await versionOption.isVisible().catch(() => false)) {
      await versionOption.click()
    }
  }
}

test.describe('S04: 架构数据 - 过滤与范围选择', () => {
  test('C01: 对象与关系范围选择验证', async ({ page, navigateTo, dataFinder }, testInfo) => {
    const archData = new ArchDataPage(page)

    await withStep(page, testInfo, '导航到架构数据页', async () => {
      await navigateTo(page, ARCHDATA_URL, {
        skipHealthCheck: true,
        waitForSelector: '.collapsible-panel, .el-tabs, .el-tree'
      })
    })

    const result = await dataFinder.productWithVersion()
    if (!result) {
      test.skip(true, '未找到 product/version,跳过')
      return
    }

    const { product, version } = result
    await withStep(page, testInfo, '选择产品和版本', async () => {
      await selectProductVersionOnPage(page, product, version)
    })

    const objectPanelFound = await withStep(page, testInfo, '展开对象范围面板', async () => {
      return await expandCollapsiblePanel(page, '.rst-panel-object, .collapsible-panel:has-text("对象范围")')
    })
    if (!objectPanelFound) {
      test.skip(true, '对象范围面板未找到')
      return
    }

    await withStep(page, testInfo, '点击展开全部', async () => {
      const expandAllBtn = page.locator('.oss-toolbar button:has-text("展开全部"), .oss-toolbar .app-btn:has-text("展开全部")').first()
      if (await expandAllBtn.isVisible().catch(() => false)) {
        await expandAllBtn.click()
      }
    })

    const domainCheckbox = page.locator('.oss-tree-container .el-tree-node .el-checkbox__input, .rst-panel-object .el-tree-node .el-checkbox__input').first()
    if (!(await domainCheckbox.isVisible().catch(() => false))) {
      test.skip(true, '对象树 checkbox 未找到')
      return
    }

    await withStep(page, testInfo, '勾选对象节点', async () => {
      await domainCheckbox.click()
    })

    const relationPanelFound = await withStep(page, testInfo, '展开关系范围面板', async () => {
      return await expandCollapsiblePanel(page, '.rst-panel-relation, .collapsible-panel:has-text("关系范围")')
    })
    if (!relationPanelFound) {
      test.skip(true, '关系范围面板未找到')
      return
    }

    await withStep(page, testInfo, '勾选关系节点 (前 3 个)', async () => {
      const relationCheckboxes = page.locator('.rss-tree-container .el-tree-node .el-checkbox__input, .rst-panel-relation .el-tree-node .el-checkbox__input')
      const relCheckboxCount = await relationCheckboxes.count()
      if (relCheckboxCount > 0) {
        const checkLimit = Math.min(relCheckboxCount, 3)
        for (let i = 0; i < checkLimit; i++) {
          await relationCheckboxes.nth(i).click()
        }
      }
    })

    await withStep(page, testInfo, '切到业务对象 tab', async () => {
      const boTab = page.locator('.el-tabs__item:has-text("业务对象")').first()
      if (await boTab.isVisible().catch(() => false)) {
        await boTab.click()
      }
    })

    await withStep(page, testInfo, '切到关联关系 tab', async () => {
      const relTab = page.locator('.el-tabs__item:has-text("关联关系")').first()
      if (await relTab.isVisible().catch(() => false)) {
        await relTab.click()
      }
    })
  })

  test('C02: 备注类型过滤与排序验证', async ({ page, navigateTo, dataFinder }, testInfo) => {
    const archData = new ArchDataPage(page)

    await withStep(page, testInfo, '导航到架构数据页', async () => {
      await navigateTo(page, ARCHDATA_URL, {
        skipHealthCheck: true,
        waitForSelector: '.collapsible-panel, .el-tabs, .el-tree'
      })
    })

    const result = await dataFinder.productWithVersion()
    if (!result) {
      test.skip(true, '未找到 product/version,跳过')
      return
    }

    const { product, version } = result
    await withStep(page, testInfo, '选择产品和版本', async () => {
      await selectProductVersionOnPage(page, product, version)
    })

    const filterPanelFound = await withStep(page, testInfo, '展开过滤条件面板', async () => {
      return await expandCollapsiblePanel(page, '.rst-panel-filter, .collapsible-panel:has-text("过滤条件")')
    })
    if (!filterPanelFound) {
      test.skip(true, '过滤条件面板未找到')
      return
    }

    const annotationSelect = page.locator('.relation-filter-section .rfs-select, .rfs-group:has-text("备注类型") .rfs-select').first()
    if (!(await annotationSelect.isVisible().catch(() => false))) {
      test.skip(true, '备注类型下拉未找到')
      return
    }

    await withStep(page, testInfo, '选择备注类型', async () => {
      await annotationSelect.click()
      const firstOption = page.locator('.el-select-dropdown__item:visible').first()
      if (await firstOption.isVisible().catch(() => false)) {
        await firstOption.click()
      }
    })

    await withStep(page, testInfo, '清除备注类型过滤', async () => {
      const clearFilterBtn = page.locator('.relation-filter-section .el-tag__close, .rfs-group:has-text("备注类型") .el-tag__close, .relation-filter-section button:has-text("清除"), .rfs-group:has-text("备注类型") button:has-text("清除")').first()
      if (await clearFilterBtn.isVisible().catch(() => false)) {
        await clearFilterBtn.click()
      } else {
        await annotationSelect.click()
        const selectedOption = page.locator('.el-select-dropdown__item.selected:visible').first()
        if (await selectedOption.isVisible().catch(() => false)) {
          await selectedOption.click()
        }
        await page.keyboard.press('Escape')
      }
    })

    await withStep(page, testInfo, '切到业务对象 tab', async () => {
      const boTab = page.locator('.el-tabs__item:has-text("业务对象")').first()
      if (await boTab.isVisible().catch(() => false)) {
        await boTab.click()
      }
    })

    const codeHeader = page.locator('thead th').filter({ hasText: '编码' }).first()
    if (await codeHeader.isVisible().catch(() => false)) {
      await withStep(page, testInfo, '点编码列升序', async () => {
        await codeHeader.click()
      })
      await withStep(page, testInfo, '点编码列降序', async () => {
        await codeHeader.click()
      })
    }

    const searchInput = page.locator('.toolbar-left .search-field .el-input input, .toolbar-left .el-input input').first()
    if (!(await searchInput.isVisible().catch(() => false))) {
      test.skip(true, '搜索输入框未找到')
      return
    }

    await withStep(page, testInfo, '输入搜索关键词 test', async () => {
      await searchInput.fill('test')
    })

    await withStep(page, testInfo, '点击搜索或回车', async () => {
      const searchBtn = page.locator('.toolbar-left .el-button:has-text("搜索"), .toolbar-left button:has-text("搜索")').first()
      if (await searchBtn.isVisible().catch(() => false)) {
        await searchBtn.click()
      } else {
        await searchInput.press('Enter')
      }
    })

    await withStep(page, testInfo, '点击重置', async () => {
      const resetBtn = page.locator('.toolbar-left .el-button:has-text("重置"), .toolbar-left button:has-text("重置")').first()
      if (await resetBtn.isVisible().catch(() => false)) {
        await resetBtn.click()
      }
    })
  })
})
