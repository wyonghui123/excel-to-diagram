/**
 * 自动 step 跟踪 + 失败截图
 *
 * 解决的核心问题：
 * - 测试失败时只有 1 张最终截图，不知道哪步出错
 * - 排查失败要手动复现 + 跑多次
 * - 没有统一的 step 日志
 *
 * 方案：
 * - withStep() 包装每个业务步骤
 * - 失败时自动保存 "before" 和 "fail" 截图
 * - 控制台输出 [STEP] xxx START/OK/FAIL 标签
 *
 * 用法：
 *
 *   await withStep(page, testInfo, '创建业务对象', async () => {
 *     await isolation.createTracked('business_object', { code: 'E2E_X' })
 *   })
 *
 *   await withStep(page, testInfo, '打开详情', async () => {
 *     await archData.openDetailByCode('E2E_X')
 *   })
 */

import path from 'path'
import { promises as fs } from 'fs'

const TRACE_DIR = path.join(process.cwd(), 'e2e', 'traces')

/**
 * 确保 trace 目录存在
 */
async function ensureTraceDir() {
  try {
    await fs.mkdir(TRACE_DIR, { recursive: true })
  } catch (e) {}
}

/**
 * 安全截图（不会因为页面崩溃而失败）
 */
async function safeScreenshot(page, name) {
  try {
    return await page.screenshot({ fullPage: false })
  } catch (e) {
    return null
  }
}

/**
 * 包装业务步骤：自动截图 + 日志
 *
 * @param {Page} page
 * @param {TestInfo} testInfo
 * @param {string} stepName - 步骤名（中文友好）
 * @param {Function} fn - 步骤函数
 * @returns {Promise<any>} 步骤函数的返回值
 */
export async function withStep(page, testInfo, stepName, fn) {
  const startTime = Date.now()
  console.log(`\n[STEP] ▶ ${stepName}`)

  // step 前截图
  const beforeShot = await safeScreenshot(page, stepName)
  if (beforeShot) {
    try {
      await testInfo.attach(`${stepName}-before.png`, {
        body: beforeShot,
        contentType: 'image/png'
      })
    } catch (e) {}
  }

  try {
    const result = await fn()
    const duration = Date.now() - startTime
    console.log(`[STEP] [DECORATIVE] ${stepName} (${duration}ms)`)
    return result
  } catch (error) {
    const duration = Date.now() - startTime
    console.error(`[STEP] [DECORATIVE] ${stepName} FAILED (${duration}ms)`)
    console.error(`[STEP]   Error: ${error.message}`)

    // 失败时多角度截图
    const failShot = await safeScreenshot(page, `${stepName}-FAIL`)
    if (failShot) {
      try {
        await testInfo.attach(`${stepName}-FAIL.png`, {
          body: failShot,
          contentType: 'image/png'
        })
      } catch (e) {}
    }

    // 收集诊断信息
    const diagnostics = await collectDiagnostics(page)
    try {
      await testInfo.attach(`${stepName}-diagnostics.json`, {
        body: JSON.stringify(diagnostics, null, 2),
        contentType: 'application/json'
      })
    } catch (e) {}

    throw error
  }
}

/**
 * 收集页面诊断信息（用于失败排查）
 */
async function collectDiagnostics(page) {
  const diag = {
    timestamp: new Date().toISOString(),
    url: page.url(),
    title: await page.title().catch(() => null),
    visibleText: null,
    appErrors: [],
    consoleErrors: [],
    pendingRequests: 0
  }

  try {
    // 当前页面可见文本（前 500 字）
    diag.visibleText = await page.evaluate(() => {
      return document.body?.textContent?.substring(0, 500) || ''
    })
  } catch (e) {}

  try {
    diag.appErrors = await page.evaluate(() => window.__appErrors || [])
  } catch (e) {}

  try {
    diag.consoleErrors = await page.evaluate(() => window.__consoleErrors || [])
  } catch (e) {}

  return diag
}

/**
 * 创建测试追踪 fixture（在 testInfo 中记录所有 step 耗时）
 */
export class StepTracker {
  constructor() {
    this.steps = []
    this.startTime = Date.now()
  }

  record(name, duration, success, error = null) {
    this.steps.push({ name, duration, success, error, timestamp: Date.now() })
  }

  summary() {
    const total = Date.now() - this.startTime
    const passed = this.steps.filter(s => s.success).length
    const failed = this.steps.filter(s => !s.success).length
    return {
      totalDuration: total,
      totalSteps: this.steps.length,
      passed,
      failed,
      steps: this.steps
    }
  }
}
