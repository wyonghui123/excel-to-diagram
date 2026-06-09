/**
 * 测试隔离 + 自动清理 - v2 简化方案核心
 *
 * [!!!] 本文件是 v2 简化方案的 isolation 核心 [!!!]
 * [!!!] 规范: .trae/rules/e2e-simplification.md 第五节 [!!!]
 * [!!!] 所有 features 测试必须用 isolation.createTracked()，禁止 Date.now() 命名 + 不清理 [!!!]
 *
 * 解决的核心问题：
 * - E2E_xxx_xxxxx 这种 Date.now() 命名的测试数据用完不清理
 * - 跑 100 轮测试后，列表里有几百个垃圾数据
 * - 下一个测试可能误选到上次的数据
 *
 * 方案：
 * - 每测试 UUID 命名（不是 Date.now()）
 * - track() 注册要清理的对象
 * - cleanup() 在 afterEach 调用，自动逆序删除
 *
 * 用法：
 *
 *   test('xxx', async ({ page }, testInfo) => {
 *     const isolation = new TestIsolation(page, testInfo)
 *     isolation.useFixture(autoFixtures)
 *
 *     // 创建测试数据
 *     const bo = await isolation.createTracked('business_object', { code: 'E2E_TEST', name: '测试对象' })
 *
 *     // 测试逻辑...
 *
 *     // 不用手动清理，afterEach 自动调用
 *   })
 */

import { randomUUID } from 'crypto'

const API_BASE = process.env.TEST_BASE_URL || 'http://localhost:3010'

export class TestIsolation {
  /**
   * @param {Page} page
   * @param {TestInfo} testInfo
   */
  constructor(page, testInfo) {
    this.page = page
    this.testInfo = testInfo
    this.tracked = []  // [{ type, id, createdAt }]
    this.testId = testInfo.title.replace(/[^a-zA-Z0-9_]/g, '_').substring(0, 30)
    this.testRunId = `${this.testId}_${Date.now()}_${randomUUID().substring(0, 6)}`
  }

  /**
   * 生成测试用唯一 ID（避免和别的测试撞名）
   */
  generateId(prefix = 'e2e') {
    return `${prefix}_${this.testRunId}`.toLowerCase()
  }

  /**
   * 生成大写 code（用于 BO code，要求匹配 ^[A-Z][A-Z0-9_]*$）
   * 与 generateId 的区别是返回全大写字符，避免被后端小写校验拒绝
   */
  generateCode(prefix = 'E') {
    const upper = this.testRunId.toUpperCase().replace(/-/g, '_')
    return `${prefix}_${upper}`
  }

  /**
   * 注册要跟踪的对象（创建后调用，记录 ID）
   */
  track(type, id) {
    this.tracked.push({ type, id, createdAt: Date.now() })
    return id
  }

  /**
   * 创建并自动注册（推荐）
   */
  async createTracked(type, data = {}) {
    const url = this._apiUrlForType(type)
    // 注意：很多后端 ID 由系统生成，不接受客户端传入
    // 这里把 id 字段移除，只传业务字段
    const { id, ...payload } = data
    payload.is_active = payload.is_active !== false

    const resp = await this.page.context().request.post(url, {
      data: payload,
      headers: { 'Content-Type': 'application/json' }
    })

    if (!resp.ok()) {
      const text = await resp.text().catch(() => '')
      throw new Error(`Failed to create ${type}: ${resp.status()} ${text}`)
    }

    const body = await resp.json().catch(() => ({}))
    const created = body.data || body
    const finalId = created.id || id
    if (finalId) {
      this.track(type, finalId)
    }
    return created
  }

  /**
   * 获取某类型已跟踪的对象
   * @param {string} type
   * @returns {Array<{type, id, createdAt}>}
   */
  getTracked(type) {
    return this.tracked.filter(t => t.type === type)
  }

  /**
   * 标记某类型已手动清理（避免 cleanup 时重复删除）
   * @param {string} type
   */
  markCleaned(type) {
    this.tracked = this.tracked.filter(t => t.type !== type)
  }

  /**
   * 清理所有跟踪的对象（afterEach 调用）
   * 逆序删除（先删子再删父），失败的忽略
   */
  async cleanup() {
    const errors = []
    // 逆序：后创建先删除
    for (let i = this.tracked.length - 1; i >= 0; i--) {
      const { type, id } = this.tracked[i]
      try {
        const url = this._apiUrlForType(type, id)
        const resp = await this.page.request.delete(url, { timeout: 5000 })
        if (!resp.ok() && resp.status() !== 404) {
          errors.push({ type, id, status: resp.status() })
        }
      } catch (e) {
        errors.push({ type, id, error: e.message })
      }
    }
    this.tracked = []
    return { cleaned: this.tracked.length, errors }
  }

  /**
   * 对象类型 → API URL 映射
   * 新类型加这里
   */
  _apiUrlForType(type, id = null) {
    const base = `/api/v2/bo/${type}`
    return id ? `${base}/${id}` : base
  }
}

/**
 * Playwright fixture 形式：自动 afterEach 清理
 *
 * @example
 * import { test } from '../helpers/auto-fixtures.js'
 * test('xxx', async ({ page, isolation, dataFinder }, testInfo) => {
 *   const bo = await isolation.createTracked('business_object', { code: 'E2E_X' })
 * })
 */
export function attachIsolationFixtures(baseTest) {
  return baseTest.extend({
    isolation: async ({ page }, use, testInfo) => {
      const isolation = new TestIsolation(page, testInfo)
      await use(isolation)
      // afterEach：自动清理
      try {
        const result = await isolation.cleanup()
        if (result.errors.length > 0) {
          console.warn(`[isolation] ${result.errors.length} cleanup errors:`, result.errors)
        }
      } catch (e) {
        console.warn('[isolation] cleanup failed:', e.message)
      }
    }
  })
}
