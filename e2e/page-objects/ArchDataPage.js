/**
 * 架构数据管理页 POM - 封装 /system/archdata
 *
 * 这是业务复杂度最高的页面之一，包含 5 个 tab：
 * - 领域 / 子领域 / 服务模块 / 业务对象 / 关联关系
 *
 * 旧写法：每个测试 30+ 行
 * 新写法：业务流式描述
 *
 * @example
 * const archData = new ArchDataPage(page)
 * const pv = await dataFinder.productWithVersion()
 * await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)
 *
 * await archData.openTab('业务对象')
 * await archData.openDetailByCode(boCode)
 * const drawer = new DetailDrawerPage(page)
 * await drawer.clickEdit()
 * await drawer.fillFieldByLabel('名称', newName)
 * await drawer.clickSave()
 * await drawer.expectSuccessMessage()
 * await drawer.close()
 * await archData.expectRowNotExists(boCode)
 */

import { GenericListPage } from './GenericListPage.js'

export class ArchDataPage extends GenericListPage {
  constructor(page) {
    super(page, {
      tableSelector: '.arch-data-table .el-table, .el-table',
      rowSelector: '.el-table__body tr'
    })
    this.tabs = {
      domain: '领域',
      subDomain: '子领域',
      serviceModule: '服务模块',
      businessObject: '业务对象',
      relationship: '关联关系'
    }
  }

  /**
   * 打开指定 tab
   */
  async openTab(name) {
    const tabName = this.tabs[name] || name
    const tab = this.page.locator(`.el-tabs__item:has-text("${tabName}")`).first()
    await tab.waitFor({ state: 'visible', timeout: 10000 })
    await tab.click()
    // 等表格刷新
    await this.page.waitForTimeout(800)
    await this.waitForReady()
    return this
  }

  /**
   * 通过编码打开详情 drawer
   */
  async openDetailByCode(code) {
    await this.clickRowByText(code, { linkSelector: '.bk-link' })
    return this
  }

  /**
   * 通过工具栏"新建"打开创建 drawer
   */
  async clickNew() {
    await this.clickToolbarButton('新建')
    return this
  }

  // ========== 分页方法 (Pagination) ==========
  // Element UI el-pagination 通用方法

  /**
   * 获取分页器根元素
   */
  paginationRoot() {
    return this.page.locator('.el-pagination').first()
  }

  /**
   * 修改每页条数
   * @param {number|string} size 10/20/50/100
   */
  async changePageSize(size) {
    const pager = this.paginationRoot()
    if (!(await pager.isVisible({ timeout: 2000 }).catch(() => false))) {
      return this
    }
    // Element UI: .el-pagination__sizes .el-select
    const sizesSelect = pager.locator('.el-pagination__sizes').first()
    await sizesSelect.click()
    // 选项在下拉框里
    const option = this.page.locator('.el-select-dropdown__item').filter({ hasText: new RegExp(`^${size}/`) }).first()
    await option.click()
    return this
  }

  /**
   * 点击下一页
   */
  async nextPage() {
    const pager = this.paginationRoot()
    if (!(await pager.isVisible({ timeout: 2000 }).catch(() => false))) {
      return this
    }
    await pager.locator('.btn-next').first().click()
    return this
  }

  /**
   * 点击上一页
   */
  async prevPage() {
    const pager = this.paginationRoot()
    if (!(await pager.isVisible({ timeout: 2000 }).catch(() => false))) {
      return this
    }
    await pager.locator('.btn-prev').first().click()
    return this
  }

  /**
   * 跳转到指定页
   * @param {number} page 页码 (1-based)
   */
  async jumpToPage(page) {
    const pager = this.paginationRoot()
    if (!(await pager.isVisible({ timeout: 2000 }).catch(() => false))) {
      return this
    }
    const jumpInput = pager.locator('.el-pagination__jump input').first()
    await jumpInput.fill(String(page))
    await jumpInput.press('Enter')
    return this
  }

  /**
   * 获取总条数文本 (e.g., "共 100 条")
   */
  async getTotalText() {
    const pager = this.paginationRoot()
    if (!(await pager.isVisible({ timeout: 2000 }).catch(() => false))) {
      return ''
    }
    const total = pager.locator('.el-pagination__total').first()
    return (await total.textContent().catch(() => '')) || ''
  }
}
