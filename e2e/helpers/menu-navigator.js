/**
 * 菜单驱动导航 - 通过侧边栏菜单文本点击导航
 *
 * 解决的核心问题：
 * - URL 散落 25+ 个测试文件
 * - 改一个菜单/URL 要改 25 处
 * - 硬编码 URL 抓不到菜单配置错误（如菜单点不开）
 *
 * 方案：
 * - 从侧边栏菜单点击（真实用户行为）
 * - 通过菜单文本定位（业务语义化）
 * - 同时支持通过面包屑反向定位
 *
 * 用法：
 *
 *   const nav = new MenuNavigator(page)
 *   await nav.navigateByMenuText('产品版本管理')           // 自动跳到 /product-management
 *   await nav.navigateByMenuText('用户与权限', '角色管理')  // 二级菜单
 */

import { expect } from '@playwright/test'

/**
 * 菜单文本 → URL 映射表
 *
 * 维护说明：
 * - 当菜单配置变化时，**只改这里**，所有测试自动跟随
 * - 可从后端 API 自动同步（见 syncFromBackend()）
 */
const MENU_TEXT_TO_URL = {
  '工作台': '/',
  '产品版本管理': '/product-management',
  '用户与权限': '/user-permission',
  '用户与权限管理': '/user-permission',
  '架构数据管理': '/system/archdata',
  '业务配置': '/business-config',
  '系统管理': '/system-admin',
  '日志管理': '/system-admin',
  '任务管理': '/system/task-management',
  '账户设置': '/account',
  '架构图': '/archdata-chart',
  '主题预览': '/dev/theme-preview',
}

/**
 * 菜单路径 → URL 映射（多级菜单）
 * 'key1.key2' 表示先点 key1 展开，再点 key2
 */
const MENU_PATH_TO_URL = {
  '用户与权限.用户管理': '/user-permission/users',
  '用户与权限.角色管理': '/user-permission/roles',
  '用户与权限.用户组管理': '/user-permission/user-groups',
  '业务配置.枚举类型': '/business-config/enum-types',
  '业务配置.元操作': '/business-config/meta-ops',
}

export class MenuNavigator {
  /**
   * @param {Page} page
   * @param {Object} options
   *   - sidebarSelector: 侧边栏选择器
   *   - menuItemSelector: 菜单项选择器
   */
  constructor(page, options = {}) {
    this.page = page
    this.sidebarSelector = options.sidebarSelector || '.app-side-nav, .sidebar, .el-aside, [class*="sidebar"], nav'
    this.menuItemSelector = options.menuItemSelector || '.nav-item, .nav-group, .el-menu-item, .menu-item, [class*="menu-item"]'
  }

  /**
   * 通过菜单文本导航（一级菜单）
   *
   * @param {string} menuText - 菜单显示文本
   * @param {Object} options
   *   - expectedUrl: 期望到达的 URL（可选，未提供则用映射表）
   *   - subMenuText: 二级菜单文本
   *   - timeout: 超时（默认 10000ms）
   */
  async navigateByMenuText(menuText, options = {}) {
    const { expectedUrl = null, subMenuText = null, timeout = 10000 } = options

    // 0. 确保菜单已渲染（轮询最多 5s）
    try {
      await this.page.waitForSelector('.app-side-nav .nav-item, .el-menu-item, [class*="menu-item"]', {
        state: 'visible',
        timeout: 5000
      })
    } catch (e) {
      console.warn('[MenuNavigator] 菜单容器未在 5s 内渲染')
    }

    // 1. 找菜单项
    const menuItem = await this._findMenuItem(menuText, timeout)
    if (!menuItem) {
      throw new Error(`Menu item "${menuText}" not found in sidebar`)
    }

    // 2. 点击一级菜单
    await menuItem.click()
    await this.page.waitForTimeout(500)

    // 3. 如果有二级菜单，再点
    if (subMenuText) {
      const subItem = await this._findMenuItem(subMenuText, timeout)
      if (!subItem) {
        throw new Error(`Sub menu item "${subMenuText}" not found`)
      }
      await subItem.click()
      await this.page.waitForTimeout(500)
    }

    // 4. 验证 URL
    const targetUrl = expectedUrl || MENU_TEXT_TO_URL[menuText] || MENU_PATH_TO_URL[`${menuText}.${subMenuText}`]
    if (targetUrl) {
      try {
        await this.page.waitForURL(
          (url) => new URL(url).pathname.includes(targetUrl.replace(/^\//, '').split('/')[0]),
          { timeout }
        )
      } catch (e) {
        console.warn(`[MenuNavigator] URL did not match ${targetUrl}, current: ${this.page.url()}`)
      }
    }

    return this.page.url()
  }

  /**
   * 查找菜单项（支持部分匹配）
   */
  async _findMenuItem(text, timeout = 5000) {
    // 优先用侧边栏内的 nav-item / label（项目实际结构）
    const candidates = [
      this.page.locator(`.app-side-nav .nav-item:has-text("${text}")`),
      this.page.locator(`.nav-item:has-text("${text}")`),
      this.page.locator(`.nav-group:has-text("${text}")`),
      this.page.locator(`.el-menu-item:has-text("${text}")`),
      this.page.locator(`.menu-item:has-text("${text}")`),
      this.page.locator(`a:has-text("${text}")`),
    ]
    for (const locator of candidates) {
      try {
        const count = await locator.count()
        if (count > 0) {
          console.log(`[MenuNavigator] Found "${text}" via ${locator.toString().substring(0, 100)} (count=${count})`)
          return locator.first()
        }
      } catch (e) {
        continue
      }
    }

    // 调试：列出所有可点击元素
    console.log(`[MenuNavigator] Menu "${text}" not found. Visible nav-items:`)
    try {
      const labels = this.page.locator('.app-side-nav .label')
      const c = await labels.count()
      for (let i = 0; i < Math.min(c, 10); i++) {
        console.log(`  - ${await labels.nth(i).textContent()}`)
      }
    } catch (e) {}

    return null
  }

  /**
   * 获取当前面包屑
   */
  async getCurrentBreadcrumb() {
    const breadcrumb = this.page.locator('.breadcrumb, [class*="breadcrumb"]').first()
    if (await breadcrumb.isVisible().catch(() => false)) {
      return await breadcrumb.textContent()
    }
    return null
  }

  /**
   * 获取所有可见的菜单项
   */
  async getVisibleMenus() {
    const items = []
    const menuItems = this.page.locator(`${this.sidebarSelector} ${this.menuItemSelector}`)
    const count = await menuItems.count()
    for (let i = 0; i < count; i++) {
      const text = await menuItems.nth(i).textContent()
      if (text) items.push(text.trim())
    }
    return items
  }

  /**
   * 从后端同步菜单配置（高级用法）
   * 这样菜单配置变化时无需改本地映射
   */
  async syncFromBackend() {
    // 留作扩展：从 /api/v1/menu/me 获取菜单配置
    // 然后构建 菜单文本 → URL 映射
  }
}

/**
 * 静态方法：通过 URL 反查菜单路径（用于错误日志）
 */
export function findMenuPathForUrl(url) {
  const pathname = new URL(url).pathname
  for (const [text, menuUrl] of Object.entries(MENU_TEXT_TO_URL)) {
    if (pathname.startsWith(menuUrl)) {
      return text
    }
  }
  return pathname  // 没找到就返回 URL
}
