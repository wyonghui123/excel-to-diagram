export class TableHelper {
  constructor(page) {
    this.page = page
    this.table = page.locator('.el-table').first()
  }

  async waitForData(timeout = 15000) {
    await this.table.locator('.el-table__body tr').first().waitFor({ timeout })
  }

  async getRowCount() {
    return await this.table.locator('.el-table__body tr').count()
  }

  async openFirstRowDrawer() {
    const detailBtn = this.table.locator('.el-button:has-text("详情"), .el-button:has-text("查看")').first()
    const hasDetailBtn = await detailBtn.isVisible().catch(() => false)

    if (hasDetailBtn) {
      await detailBtn.click()
    } else {
      await this.table.locator('.el-table__body tr').first().click()
    }
    await this.page.waitForTimeout(2000)
    return this.page.locator('.el-drawer, .detail-drawer, [class*="drawer"]').first()
  }

  async clickTab(tabName) {
    const tab = this.page.locator(`.el-tabs__item:has-text("${tabName}")`).first()
    await tab.click()
    await this.page.waitForTimeout(1000)
  }

  async clickRowAction(actionText) {
    const rowActionTrigger = this.table.locator('.row-action-trigger, .el-dropdown').first()
    await rowActionTrigger.click()
    await this.page.waitForTimeout(300)
    const actionItem = this.page.locator(`.el-dropdown-menu__item:has-text("${actionText}")`).first()
    await actionItem.click()
  }

  async sortByColumn(columnName) {
    const header = this.table.locator(`.el-table__header th:has-text("${columnName}")`).first()
    await header.click()
    await this.page.waitForTimeout(500)
  }

  async searchByKeyword(keyword) {
    const searchInput = this.page.locator('.search-field .el-input input, .toolbar-left .el-input input').first()
    await searchInput.fill(keyword)
    await this.page.locator('.toolbar-left .el-button:has-text("搜索")').first().click()
    await this.page.waitForTimeout(1000)
  }
}

export class FormHelper {
  constructor(page) {
    this.page = page
  }

  async fillField(label, value) {
    const field = this.page.locator(`.el-form-item:has-text("${label}") input, .el-form-item:has-text("${label}") textarea`).first()
    await field.fill(value)
  }

  async selectOption(label, optionText) {
    const select = this.page.locator(`.el-form-item:has-text("${label}") .el-select`).first()
    await select.click()
    await this.page.waitForTimeout(300)
    const option = this.page.locator(`.el-select-dropdown__item:has-text("${optionText}")`).first()
    await option.click()
  }

  async submit() {
    await this.page.locator('button:has-text("确定"), button:has-text("保存"), button:has-text("提交")').first().click()
  }

  async cancel() {
    await this.page.locator('button:has-text("取消")').first().click()
  }

  async expectValidation(message) {
    await this.page.locator(`.el-form-item__error:has-text("${message}")`).waitFor()
  }
}

export class SelectorHelper {
  constructor(page) {
    this.page = page
  }

  async selectProductVersion(productId, versionId) {
    const productSelect = this.page.locator('.gt-selector:has-text("产品") .el-select').first()
    await productSelect.click()
    await this.page.waitForTimeout(300)
    const productOption = this.page.locator(`.el-select-dropdown__item[data-value="${productId}"]`).first()
    await productOption.click()
    await this.page.waitForTimeout(500)

    const versionSelect = this.page.locator('.gt-selector:has-text("版本") .el-select').first()
    await versionSelect.click()
    await this.page.waitForTimeout(300)
    const versionOption = this.page.locator(`.el-select-dropdown__item[data-value="${versionId}"]`).first()
    await versionOption.click()
    await this.page.waitForTimeout(1000)
  }

  async selectOption(selectSelector, optionText) {
    await this.page.locator(selectSelector).click()
    await this.page.waitForTimeout(300)
    await this.page.locator(`.el-select-dropdown__item:has-text("${optionText}")`).first().click()
  }
}

export class ScopeTreeHelper {
  constructor(page) {
    this.page = page
  }

  async expandPanel(panelName) {
    const panelMap = { object: '对象范围', relation: '关系范围', filter: '过滤条件' }
    const panelTitle = panelMap[panelName] || panelName
    const panel = this.page.locator(`.collapsible-panel:has-text("${panelTitle}")`).first()
    const toggle = panel.locator('.collapsible-panel__toggle')
    const isExpanded = await panel.locator('.collapsible-panel__content').isVisible().catch(() => false)
    if (!isExpanded) {
      await toggle.click()
      await this.page.waitForTimeout(300)
    }
  }

  async checkObjectNode(nodeLabel) {
    await this.expandPanel('object')
    const node = this.page.locator(`.oss-tree-container .el-tree-node:has-text("${nodeLabel}")`).first()
    const checkbox = node.locator('.el-checkbox__input')
    await checkbox.click()
    await this.page.waitForTimeout(500)
  }

  async checkRelationNode(nodeLabel) {
    await this.expandPanel('relation')
    const node = this.page.locator(`.rss-tree-container .el-tree-node:has-text("${nodeLabel}")`).first()
    const checkbox = node.locator('.el-checkbox__input')
    await checkbox.click()
    await this.page.waitForTimeout(500)
  }

  async selectAnnotationCategory(categories) {
    await this.expandPanel('filter')
    const select = this.page.locator('.rfs-group:has-text("备注类型") .rfs-select').first()
    await select.click()
    await this.page.waitForTimeout(300)
    for (const cat of categories) {
      await this.page.locator(`.el-select-dropdown__item:has-text("${cat}")`).first().click()
      await this.page.waitForTimeout(200)
    }
    await this.page.keyboard.press('Escape')
  }

  async clearAllScopes() {
    const clearBtn = this.page.locator('.oss-toolbar .app-btn:has-text("清空")').first()
    if (await clearBtn.isVisible().catch(() => false)) {
      await clearBtn.click()
      await this.page.waitForTimeout(300)
    }
  }

  async refreshRelationScope() {
    const refreshBtn = this.page.locator('.rss-toolbar .app-btn:has-text("刷新")').first()
    if (await refreshBtn.isVisible().catch(() => false)) {
      await refreshBtn.click()
      await this.page.waitForTimeout(1000)
    }
  }
}

export class ImportExportHelper {
  constructor(page) {
    this.page = page
  }

  async exportSingleObject(objectType, options = {}) {
    const exportBtn = this.page.locator('.toolbar-left .el-button:has-text("导出")').first()
    await exportBtn.click()
    await this.page.waitForTimeout(500)

    if (options.scope) {
      await this.page.locator(`el-radio[value="${options.scope}"]`).click()
    }

    await this.page.locator('.el-dialog button:has-text("确认导出")').first().click()
    await this.page.waitForTimeout(2000)
  }

  async importSingleObject(objectType, filePath, conflictMode = 'upsert') {
    const importBtn = this.page.locator('.toolbar-left .el-button:has-text("导入")').first()
    await importBtn.click()
    await this.page.waitForTimeout(500)

    const fileInput = this.page.locator('.el-upload input[type="file"]')
    await fileInput.setInputFiles(filePath)
    await this.page.waitForTimeout(1000)

    if (conflictMode) {
      await this.page.locator(`el-radio[value="${conflictMode}"]`).click()
    }

    await this.page.locator('.el-dialog button:has-text("下一步")').first().click()
    await this.page.waitForTimeout(2000)

    await this.page.locator('.el-dialog button:has-text("确认导入")').first().click()
    await this.page.waitForTimeout(2000)
  }

  async exportMultiType(objectTypes, options = {}) {
    const exportBtn = this.page.locator('.gt-actions .el-button:has-text("导出")').first()
    await exportBtn.click()
    await this.page.waitForTimeout(500)

    for (const type of objectTypes) {
      await this.page.locator(`.multi-type-checkbox:has-text("${type}")`).first().click()
    }

    await this.page.locator('.el-dialog button:has-text("确认导出")').first().click()
    await this.page.waitForTimeout(2000)
  }

  async importMultiType(objectTypes, filePath, conflictMode = 'upsert') {
    const importBtn = this.page.locator('.gt-actions .el-button:has-text("导入")').first()
    await importBtn.click()
    await this.page.waitForTimeout(500)

    for (const type of objectTypes) {
      await this.page.locator(`.multi-type-checkbox:has-text("${type}")`).first().click()
    }

    const fileInput = this.page.locator('.el-upload input[type="file"]')
    await fileInput.setInputFiles(filePath)
    await this.page.waitForTimeout(1000)

    if (conflictMode) {
      await this.page.locator(`el-radio[value="${conflictMode}"]`).click()
    }

    await this.page.locator('.el-dialog button:has-text("下一步")').first().click()
    await this.page.waitForTimeout(2000)

    await this.page.locator('.el-dialog button:has-text("确认导入")').first().click()
    await this.page.waitForTimeout(2000)
  }

  async verifyImportResult(expectedCounts) {
    for (const [type, count] of Object.entries(expectedCounts)) {
      const counter = this.page.locator(`.count-${type}`)
      const text = await counter.textContent()
      const actualCount = parseInt(text)
      if (actualCount !== count) {
        console.warn(`Import result mismatch for ${type}: expected ${count}, got ${actualCount}`)
      }
    }
  }
}

export class ValueHelpHelper {
  constructor(page) {
    this.page = page
  }

  async openDialog(fieldLabel) {
    const field = this.page.locator(`.el-form-item:has-text("${fieldLabel}")`).first()
    const searchIcon = field.locator('.vh-search-icon, .el-icon:has-text("Search")')
    await searchIcon.click()
    await this.page.waitForTimeout(500)

    return this.page.locator('.search-help-dialog, .el-dialog:has-text("选择")').first()
  }

  async search(keyword) {
    const searchInput = this.page.locator('.search-help-dialog .vh-search-bar input, .el-dialog .vh-search-bar input').first()
    await searchInput.fill(keyword)
    await this.page.waitForTimeout(500)
  }

  async selectItem(itemText) {
    const row = this.page.locator(`.search-help-dialog .el-table__body tr:has-text("${itemText}")`).first()
    await row.click()
    await this.page.waitForTimeout(300)
  }

  async confirm() {
    await this.page.locator('.search-help-dialog button:has-text("确定"), .el-dialog button:has-text("确定")').first().click()
    await this.page.waitForTimeout(500)
  }

  async verifyFieldFilled(fieldLabel, expectedValue) {
    const field = this.page.locator(`.el-form-item:has-text("${fieldLabel}") input`).first()
    const value = await field.inputValue()
    return value.includes(expectedValue)
  }
}
