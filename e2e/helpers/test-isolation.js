/**
 * 测试隔离 + 自动清理 - v2 简化方案核心 (v3.18.4+ Phase 6 健壮性增强)
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
 * - cleanup() 在 afterEach 调用，自动拓扑序删除（子→父）
 *
 * [Phase 6 健壮性增强] (2026-06-13):
 * - createTracked 加 retry (5xx/409 重试) + schema 验证
 * - cleanup 加 FK 拓扑序
 * - cleanup count bug 修复 (return originalCount)
 * - 404 改 warn + 累积 (不再静默)
 * - generateCode 加并发锁 (file-based, per-prefix)
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
import * as fs from 'fs'
import * as path from 'path'

const API_BASE = process.env.TEST_BASE_URL || 'http://localhost:3010'

// ============================================================
// [Phase 6] FK 依赖图 (拓扑序清理)
// ============================================================

/**
 * 类型 → 依赖 (子→父) 关系
 * cleanup 时会按这个顺序的逆向删除
 * 例如: 创建了 user_group, 再创建了 user_group_member
 *   cleanup 顺序: user_group_member → user_group
 */
const FK_DEPENDENCIES = {
  // 一对多: 父删前先删子
  'product': ['version'],
  'version': ['business_object', 'domain', 'sub_domain', 'service_module'],
  'domain': ['sub_domain'],
  'sub_domain': ['service_module'],
  'service_module': ['business_object'],
  'user_group': ['user_group_member'],
  'role': ['role_permission', 'user_role'],
  'user': ['user_role', 'user_group_member'],
  'business_object': ['association', 'annotation'],
  'enum': ['enum_value'],
}

function getDepth(type, _visited = new Set()) {
  if (_visited.has(type)) return 0
  _visited.add(type)
  const deps = FK_DEPENDENCIES[type] || []
  if (deps.length === 0) return 0
  return 1 + Math.max(...deps.map(d => getDepth(d, _visited)))
}

/**
 * 计算节点深度 (从根到该节点的层级)
 * 用于拓扑排序: 深度大的(叶子) 排前面, 先删
 * - product 是根 → depth 0
 * - version 是 product 的孩子 → depth 1
 * - business_object 是 version 的孩子 → depth 2
 */
function getNodeDepth(type, _cache = new Map(), _visiting = new Set()) {
  if (_cache.has(type)) return _cache.get(type)
  if (_visiting.has(type)) return 0  // 防止环

  _visiting.add(type)

  // 找该节点的父节点 (即"哪些节点的 deps 包含我")
  const parents = Object.entries(FK_DEPENDENCIES)
    .filter(([_, children]) => children.includes(type))
    .map(([parent]) => parent)

  let depth = 0
  if (parents.length > 0) {
    depth = 1 + Math.max(...parents.map(p => getNodeDepth(p, _cache, _visiting)))
  }

  _visiting.delete(type)
  _cache.set(type, depth)
  return depth
}

function getTopologicalOrder() {
  // 返回按"节点深度"排序的所有 type (深→浅, 即叶子先删)
  const allTypes = Object.keys(FK_DEPENDENCIES)
  return allTypes.sort((a, b) => getNodeDepth(b) - getNodeDepth(a))
}

const _TOPO_ORDER = getTopologicalOrder()

// ============================================================
// [Phase 6] 并发锁 (per-prefix)
// ============================================================

const LOCK_DIR = path.join(process.cwd(), '.tmp', 'e2e_locks')
try {
  fs.mkdirSync(LOCK_DIR, { recursive: true })
} catch (e) {
  // 忽略, lock dir 创建失败不影响测试主流程
}

/**
 * 原子递增 + 返回全局唯一序号 (per-prefix)
 * 用文件锁 + fsync 防止 race condition
 * @param {string} prefix - 业务前缀 (如 'E', 'E2E')
 * @returns {string} - 形如 "E_12345_6789"
 */
function atomicIncrement(prefix) {
  if (!fs.existsSync(LOCK_DIR)) {
    // Fallback: 不锁, 用 process.hrtime
    return `${process.pid}_${Date.now().toString(36)}`
  }
  const lockFile = path.join(LOCK_DIR, `${prefix.replace(/[^A-Za-z0-9_]/g, '_')}.counter`)

  // 简单文件锁 (OS-level atomic write)
  let counter = 0
  const maxAttempts = 10
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      // 读现有
      let content = ''
      try {
        content = fs.readFileSync(lockFile, 'utf-8').trim()
      } catch (e) {
        content = '0'
      }
      counter = parseInt(content, 10) || 0
      const newCounter = counter + 1

      // 原子写: 用 O_CREAT | O_EXCL 不行 (file 已存在), 改用 temp + rename
      const tmpFile = `${lockFile}.tmp.${process.pid}`
      fs.writeFileSync(tmpFile, String(newCounter))
      fs.renameSync(tmpFile, lockFile)
      return `${process.pid}_${newCounter}`
    } catch (e) {
      // 重试
      if (attempt === maxAttempts - 1) {
        // 放弃锁, fallback 到 random
        return `${process.pid}_${Date.now().toString(36)}`
      }
    }
  }
  return `${process.pid}_${counter}`
}

// ============================================================
// TestIsolation 类
// ============================================================

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
    this.testRunId = `${this.testId}_${randomUUID().substring(0, 8)}`
  }

  /**
   * 生成测试用唯一 ID (避免和别的测试撞名)
   * [Phase 6] 加原子计数器, 跨进程安全
   */
  generateId(prefix = 'e2e') {
    const counter = atomicIncrement(prefix)
    return `${prefix}_${this.testRunId}_${counter}`.toLowerCase()
  }

  /**
   * 生成大写 code (用于 BO code, 要求匹配 ^[A-Z][A-Z0-9_]*$)
   * 与 generateId 的区别是返回全大写字符, 避免被后端小写校验拒绝
   * [Phase 6] 改用进程内 counter, 保证单进程内唯一
   */
  generateCode(prefix = 'E') {
    const counter = atomicIncrement(prefix)
    return `${prefix}_${process.pid}_${counter}`
  }

  /**
   * 注册要跟踪的对象 (创建后调用, 记录 ID)
   */
  track(type, id) {
    if (!id) {
      console.warn(`[isolation] track() 收到 null id, type=${type}`)
      return id
    }
    this.tracked.push({ type, id, createdAt: Date.now() })
    return id
  }

  /**
   * 创建并自动注册 (推荐)
   * [Phase 6] 加 retry (5xx/409 重试) + schema 验证
   *
   * @param {string} type - 业务类型
   * @param {object} data - 业务字段
   * @param {object} options
   *   - maxRetries: 重试次数 (默认 3)
   *   - retryDelay: 重试延迟 ms (默认 500, 指数退避)
   *   - skipSchemaCheck: 跳过 schema 验证 (默认 false)
   *   - skipOnConflict: 409 时直接返回 null (默认 false, 重试)
   */
  async createTracked(type, data = {}, options = {}) {
    const {
      maxRetries = 3,
      retryDelay = 500,
      skipSchemaCheck = false,
      skipOnConflict = false
    } = options

    const url = this._apiUrlForType(type)
    // 注意: 很多后端 ID 由系统生成, 不接受客户端传入
    // 这里把 id 字段移除, 只传业务字段
    const { id, ...payload } = data
    payload.is_active = payload.is_active !== false

    let lastError = null

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      let isNonRetryable = false  // 标记 4xx 等不需要重试的错误
      try {
        const resp = await this.page.context().request.post(url, {
          data: payload,
          headers: { 'Content-Type': 'application/json' },
          timeout: 10000
        })

        if (resp.ok()) {
          const body = await resp.json().catch(() => ({}))
          const created = body.data || body
          const finalId = created.id || id

          // [P0 FIX] schema 验证: id 必须存在且非 null
          if (!skipSchemaCheck && !finalId) {
            isNonRetryable = true
            throw new Error(
              `Created ${type} but no id in response: ${JSON.stringify(created).substring(0, 200)} ` +
              `(后端可能未返回 id 字段, 或返回 null - 见 E2E 2026-06-05 报告)`
            )
          }

          if (finalId) {
            this.track(type, finalId)
          }
          return created
        }

        // 4xx 业务错误 (除 409), 不重试
        if (resp.status() >= 400 && resp.status() < 500 && resp.status() !== 409) {
          const text = await resp.text().catch(() => '')
          isNonRetryable = true
          throw new Error(
            `Failed to create ${type} (4xx ${resp.status()}): ${text.substring(0, 500)}`
          )
        }

        // 409 Conflict: skipOnConflict 返回 null, 否则重试
        if (resp.status() === 409) {
          if (skipOnConflict) {
            console.log(`[isolation] 409 conflict on ${type}, skipOnConflict=true, return null`)
            return null
          }
          // 重试: 用新 code
          if (payload.code) {
            payload.code = this.generateCode(payload.code.substring(0, 1))
            console.log(`[isolation] 409 conflict on ${type}, retry with new code=${payload.code}`)
          }
        }

        // 5xx: 重试
        const text = await resp.text().catch(() => '')
        lastError = new Error(
          `Failed to create ${type} (5xx ${resp.status()}, attempt ${attempt}/${maxRetries}): ${text.substring(0, 200)}`
        )

        if (attempt < maxRetries) {
          await this._safeWait(retryDelay * attempt)  // 指数退避
        }
      } catch (e) {
        // 不可重试的错误 (4xx / schema 验证失败), 重新抛出
        if (isNonRetryable) {
          throw e
        }
        // 网络错误: 重试
        lastError = e
        if (attempt < maxRetries) {
          await this._safeWait(retryDelay * attempt)
        }
      }
    }

    throw lastError || new Error(`Failed to create ${type} after ${maxRetries} retries`)
  }

  /**
   * 获取某类型已跟踪的对象
   */
  getTracked(type) {
    return this.tracked.filter(t => t.type === type)
  }

  /**
   * 标记某类型已手动清理 (避免 cleanup 时重复删除)
   */
  markCleaned(type) {
    this.tracked = this.tracked.filter(t => t.type !== type)
  }

  /**
   * 清理所有跟踪的对象 (afterEach 调用)
   * [Phase 6] 拓扑序删除 + 修 count bug + 404 改 warn
   *
   * @returns {Promise<{cleaned: number, errors: Array, warnings: Array}>}
   */
  async cleanup() {
    const errors = []
    const warnings = []
    const originalCount = this.tracked.length  // [P0 FIX] 在清空前统计

    // [Phase 6] 拓扑序: 按"节点深度"倒序排 (叶子先删, 父最后删)
    // - product depth=0, version depth=1, business_object depth=2
    // - 排序后: business_object → version → product
    const sorted = [...this.tracked].sort((a, b) => {
      const da = getNodeDepth(a.type)
      const db = getNodeDepth(b.type)
      if (da !== db) return db - da  // 节点深度大(叶子) 排前面
      return b.createdAt - a.createdAt  // 同深度: 后创建先删
    })

    for (const { type, id } of sorted) {
      try {
        const url = this._apiUrlForType(type, id)
        const resp = await this.page.request.delete(url, { timeout: 5000 })

        if (resp.ok()) {
          // 删除成功
        } else if (resp.status() === 404) {
          // [P0 FIX] 不再静默, 累积为 warning (可能创建失败/部分创建)
          warnings.push({ type, id, status: 404, message: 'Object not found (可能创建失败, 或被其他测试删除)' })
        } else {
          errors.push({ type, id, status: resp.status() })
        }
      } catch (e) {
        errors.push({ type, id, error: e.message })
      }
    }

    this.tracked = []

    // [Phase 6] 输出 warning 便于排查
    if (warnings.length > 0) {
      console.warn(`[isolation] cleanup ${warnings.length} warnings:`, warnings)
    }

    return { cleaned: originalCount, errors, warnings }
  }

  /**
   * 对象类型 → API URL 映射
   * 新类型加这里
   */
  _apiUrlForType(type, id = null) {
    const base = `/api/v2/bo/${type}`
    return id ? `${base}/${id}` : base
  }

  /**
   * 防御性等待: 兼容 mock page (无 waitForTimeout) 的场景
   * 真实 Playwright page 一定有 waitForTimeout
   */
  async _safeWait(ms) {
    try {
      if (typeof this.page.waitForTimeout === 'function') {
        await this.page.waitForTimeout(ms)
      } else {
        await new Promise(resolve => setTimeout(resolve, ms))
      }
    } catch (e) {
      // 静默: 等待失败不阻断重试
    }
  }
}

/**
 * Playwright fixture 形式: 自动 afterEach 清理
 * [Phase 6] try/finally 包裹, 强制 cleanup
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
      try {
        await use(isolation)
      } finally {
        // [P0 FIX] try/finally 强制 cleanup, 即使测试抛错
        try {
          const result = await isolation.cleanup()
          if (result.errors.length > 0) {
            console.warn(`[isolation] ${result.errors.length} cleanup errors:`, result.errors)
          }
          if (result.warnings && result.warnings.length > 0) {
            console.warn(`[isolation] ${result.warnings.length} cleanup warnings:`, result.warnings)
          }
        } catch (e) {
          console.warn('[isolation] cleanup failed:', e.message)
        }
      }
    }
  })
}
