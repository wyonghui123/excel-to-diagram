/**
 * API 智能等待 - 替代硬编码 waitForTimeout
 *
 * 解决的核心问题：
 * - waitForTimeout(1500) 是经验值 - 快了失败，慢了浪费时间
 * - 不知道当前在等什么 API
 * - 后端慢的时候直接超时
 *
 * 方案：
 * - waitForApi() - 等指定 API 响应完成
 * - trackApiPerformance() - 自动记录慢 API
 * - 失败时附带网络请求列表
 *
 * 用法：
 *
 *   // 触发操作
 *   await page.locator('button:has-text("保存")').click()
 *   // 等业务 API 完成（不再 waitForTimeout）
 *   const resp = await waitForApi(page, 'POST /api/v2/bo/business_object')
 *   expect(resp.status()).toBe(200)
 */

import { expect } from '@playwright/test'

const SLOW_API_THRESHOLD = 1000  // > 1s 警告

/**
 * 等指定 API 响应
 *
 * @param {Page} page
 * @param {string|RegExp|Function} matcher - API 匹配条件
 *   - 字符串: 'POST /api/v2/bo/business_object' 或 '/api/v2/bo/business_object'
 *   - RegExp: /\/api\/v2\/bo\/business_object/
 *   - Function: (resp) => resp.url().includes('xxx')
 * @param {Object} options
 *   - timeout: 超时（默认 10000ms）
 *   - status: 期望状态码（默认 2xx）
 * @returns {Promise<Response>}
 */
export async function waitForApi(page, matcher, options = {}) {
  const { timeout = 10000, status = null } = options

  let predicate
  let method = null
  let urlPattern = null

  if (typeof matcher === 'string') {
    const parts = matcher.split(' ')
    if (parts.length === 2) {
      method = parts[0].toUpperCase()
      urlPattern = parts[1]
    } else {
      urlPattern = matcher
    }
    predicate = (resp) => {
      if (urlPattern && !resp.url().includes(urlPattern)) return false
      if (method && resp.request().method() !== method) return false
      return true
    }
  } else if (matcher instanceof RegExp) {
    predicate = (resp) => matcher.test(resp.url())
  } else if (typeof matcher === 'function') {
    predicate = matcher
  } else {
    throw new Error('matcher must be string, RegExp, or function')
  }

  const start = Date.now()
  const resp = await page.waitForResponse(predicate, { timeout })
  const duration = Date.now() - start

  const req = resp.request()
  console.log(`[API] ${req.method()} ${resp.url().split('/api/')[1] || resp.url()} → ${resp.status()} (${duration}ms)`)

  if (duration > SLOW_API_THRESHOLD) {
    console.warn(`[API] [WARNING]  SLOW: ${duration}ms > ${SLOW_API_THRESHOLD}ms`)
  }

  if (status !== null) {
    expect(resp.status(), `Expected status ${status}, got ${resp.status()}`).toBe(status)
  } else if (!resp.ok() && resp.status() !== 304) {
    // 默认只警告，不抛错（让业务测试自己处理）
    console.warn(`[API] [WARNING]  ${resp.status()} ${resp.url()}`)
  }

  return resp
}

/**
 * 等多个 API 全部完成
 *
 * @param {Page} page
 * @param {Array<string>} matchers
 * @returns {Promise<Response[]>}
 */
export async function waitForApis(page, matchers) {
  return Promise.all(matchers.map(m => waitForApi(page, m)))
}

/**
 * 记录所有网络请求到数组（用于失败时回溯）
 */
export class NetworkRecorder {
  constructor(page) {
    this.page = page
    this.requests = []
    this._handler = null
  }

  start() {
    this._handler = (request) => {
      this.requests.push({
        method: request.method(),
        url: request.url(),
        timestamp: Date.now()
      })
    }
    this.page.on('request', this._handler)
  }

  stop() {
    if (this._handler) {
      this.page.off('request', this._handler)
      this._handler = null
    }
  }

  /**
   * 获取最近 N 秒内的请求
   */
  recent(seconds = 5) {
    const cutoff = Date.now() - seconds * 1000
    return this.requests.filter(r => r.timestamp >= cutoff)
  }
}

/**
 * 网络 Mock - 拦截指定 API 返回自定义数据
 *
 * 适用场景：
 * - 后端故障时仍能跑前端测试
 * - 模拟大数据量场景
 * - 模拟慢网络
 *
 * @example
 *   await mockApi(page, /\/api\/v2\/bo\/product/, {
 *     data: { items: [...], total: 1000 }
 *   })
 */
export async function mockApi(page, urlPattern, responseData, options = {}) {
  const { status = 200, delay = 0 } = options
  await page.route(urlPattern, async (route) => {
    if (delay > 0) {
      await new Promise(r => setTimeout(r, delay))
    }
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(responseData)
    })
  })
}

/**
 * 批量 Mock - 用于演示/性能测试
 */
export async function mockApis(page, mocks) {
  for (const [urlPattern, data] of Object.entries(mocks)) {
    await mockApi(page, urlPattern, data)
  }
}
