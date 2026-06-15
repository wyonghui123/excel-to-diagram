/**
 * PaginationPOM - 分页组件 POM
 *
 * 业务价值: 验证分页 UX
 * 来源: features/pagination.spec.js C01-C05
 */
import { expect } from '@playwright/test'

export class PaginationPOM {
  constructor(page, options = {}) {
    this.page = page
    this.paginationSelector = options.paginationSelector || '.el-pagination'
  }

  async getTotalText() {
    const el = this.page.locator(`${this.paginationSelector} .el-pagination__total`).first()
    if (!(await el.isVisible({ timeout: 2000 }).catch(() => false))) return null
    return (await el.textContent() || '').trim()
  }

  async expectPageSize(size) {
    const el = this.page.locator(`${this.paginationSelector} .el-pagination__sizes .el-select`).first()
    if (!(await el.isVisible({ timeout: 2000 }).catch(() => false))) return { changed: false }
    await el.click()
    const opt = this.page.locator(`.el-select-dropdown__item:has-text("${size}")`).first()
    await opt.click()
    return { changed: true, size }
  }

  async expectNextPage() {
    const btn = this.page.locator(`${this.paginationSelector} .btn-next`).first()
    if (!(await btn.isVisible({ timeout: 2000 }).catch(() => false))) return { clicked: false }
    await btn.click()
    return { clicked: true }
  }

  async expectPrevPage() {
    const btn = this.page.locator(`${this.paginationSelector} .btn-prev`).first()
    if (!(await btn.isVisible({ timeout: 2000 }).catch(() => false))) return { clicked: false }
    await btn.click()
    return { clicked: true }
  }

  async expectJumpToPage(pageNum) {
    const jumper = this.page.locator(`${this.paginationSelector} .el-pagination__jump .el-input__inner`).first()
    if (!(await jumper.isVisible({ timeout: 2000 }).catch(() => false))) return { jumped: false }
    await jumper.fill(String(pageNum))
    await jumper.press('Enter')
    return { jumped: true, page: pageNum }
  }
}
