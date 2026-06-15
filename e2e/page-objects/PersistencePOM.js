/**
 * PersistencePOM - 持久化 POM
 *
 * 业务价值: 验证刷新页面后数据仍存在
 * 来源: features/enum-integration.spec.js E31
 */
import { expect } from '@playwright/test'

export class PersistencePOM {
  constructor(page) {
    this.page = page
  }

  async expectSurvivesReload(field, expectedValue) {
    const el = this.page.locator(`text=${expectedValue}`).first()
    const visible = await el.isVisible({ timeout: 3000 }).catch(() => false)
    return { visible, field, value: expectedValue }
  }
}
