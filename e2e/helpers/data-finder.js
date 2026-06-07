/**
 * 智能数据查找器 - 替换 test-data.js
 *
 * 解决的核心问题：
 * - 硬编码产品/版本 ID（数据变化后测试失败）
 * - 反复手动查找"有数据的产品"
 * - 找数据 vs 测试逻辑混杂
 *
 * 方案：
 * - 提供分层 API：智能找 > 自动建 > 明确失败
 * - 缓存查询结果（同一测试内不重复查）
 * - 优先用 fresh data（避免被其他测试污染）
 *
 * 行业最佳实践：
 * - Data Factories：动态创建/查找测试数据
 * - Fixture-based：与测试框架解耦
 * - Lazy Loading：只在需要时查询
 */

import { generateTestId } from './test-data.js'

// ============================================================
// 查询缓存（每测试内）
// ============================================================
const cache = new Map()

function getCached(key, factory) {
  if (!cache.has(key)) {
    cache.set(key, factory())
  }
  return cache.get(key)
}

function clearCache() {
  cache.clear()
}

// ============================================================
// 通用 API 调用
// ============================================================
async function apiCall(page, method, url, data) {
  // 用 page.context().request 共享 context cookie（跨域 API 也能带 cookie）
  const resp = await page.context().request.fetch(url, {
    method,
    data,
    headers: { 'Content-Type': 'application/json' }
  })
  if (!resp.ok()) {
    const text = await resp.text()
    throw new Error(`API ${method} ${url} failed: ${resp.status()} ${text}`)
  }
  return resp.json()
}

const apiGet = (page, url) => apiCall(page, 'GET', url)
const apiPost = (page, url, data) => apiCall(page, 'POST', url, data)
const apiPut = (page, url, data) => apiCall(page, 'PUT', url, data)
const apiDelete = (page, url) => apiCall(page, 'DELETE', url)

// ============================================================
// 提取分页数据（兼容多种后端格式）
// 优先级：标准字段（items/records/rows/list）→ 任意数组字段
// 注意：响应 data 形如 {filters: [...], items: [...], page, total}
//      必须先取标准字段，否则 filters 会被误识别为数据
// ============================================================
function extractItems(json) {
  if (!json) return []
  if (Array.isArray(json)) return json

  // 优先从 data 中提取（标准 API 响应格式）
  const data = json.data !== undefined ? json.data : json

  if (data && typeof data === 'object') {
    // 1. 优先标准字段
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.records)) return data.records
    if (Array.isArray(data.rows)) return rows_to_items(data.rows)
    if (Array.isArray(data.list)) return data.list
    if (Array.isArray(data.data)) return data.data
    // 2. 兜底：找第一个看起来像数据数组的字段（长度 > 0 且不是 filters）
    for (const [key, value] of Object.entries(data)) {
      if (Array.isArray(value) && key !== 'filters' && key !== 'columns' && key !== 'sorts') {
        return value
      }
    }
  }
  return []
}

function rows_to_items(rows) {
  return rows  // 占位
}

// ============================================================
// 业务数据查找器
// ============================================================

/**
 * 智能查找有版本的产品
 *
 * 策略：
 * 1. 查询所有产品
 * 2. 过滤出 is_active=true 的
 * 3. 对每个产品查询其版本
 * 4. 返回第一个有版本的产品
 * 5. 如果都失败，自动创建一个 + 一个版本
 */
export async function findOrCreateProductWithVersion(page, options = {}) {
  const { minVersions = 1, createIfNone = true } = options

  const cacheKey = `productWithVersion:${minVersions}`
  return getCached(cacheKey, async () => {
    // 1. 尝试查找现有
    const products = extractItems(await apiGet(page, '/api/v2/bo/product?page_size=100'))
    const activeProducts = products.filter(p => p.is_active !== false)

    for (const product of activeProducts) {
      try {
        const versionsData = await apiGet(page, `/api/v2/bo/version?product_id=${product.id}&page_size=100`)
        const versions = extractItems(versionsData)
        if (versions.length >= minVersions) {
          return {
            product,
            version: versions[0],
            versions,
            source: 'existing'
          }
        }
      } catch (e) {
        // 跳过此产品
        continue
      }
    }

    // 2. 没有合适的产品，自动创建
    if (createIfNone) {
      console.log('[data-finder] No suitable product found, creating one...')
      return await createProductWithVersion(page)
    }

    throw new Error(
      `No product with >=${minVersions} versions found. ` +
      `Available: ${products.length} products, none with versions. ` +
      `Pass { createIfNone: true } to auto-create.`
    )
  })
}

/**
 * 创建一个产品 + 一个版本（确保测试有数据）
 */
export async function createProductWithVersion(page) {
  const testId = generateTestId('e2e')

  // 1. 创建产品（不传 id，让后端生成）
  const productResp = await apiPost(page, '/api/v2/bo/product', {
    code: testId.toUpperCase(),
    name: `测试产品_${testId}`,
    description: 'Auto-created by E2E data-finder',
    is_active: true
  })
  const product = productResp.data || productResp
  if (!product.id) {
    throw new Error(`Failed to create product: ${JSON.stringify(productResp)}`)
  }

  // 2. 创建版本
  const versionResp = await apiPost(page, '/api/v2/bo/version', {
    product_id: product.id,
    code: 'V1',
    name: '版本 1.0',
    description: 'Auto-created by E2E data-finder',
    is_active: true
  })
  const version = versionResp.data || versionResp

  return {
    product,
    version,
    versions: [version],
    source: 'created',
    testId
  }
}

/**
 * 智能查找有权限的角色
 */
export async function findOrCreateRoleWithPermissions(page, options = {}) {
  const { minPermissions = 1, createIfNone = false } = options

  return getCached(`roleWithPerms:${minPermissions}`, async () => {
    const roles = extractItems(await apiGet(page, '/api/v1/roles'))

    for (const role of roles) {
      try {
        const permsData = await apiGet(page, `/api/v1/roles/${role.id}/permissions`)
        const perms = extractItems(permsData)
        if (perms.length >= minPermissions) {
          return { role, permissions: perms, source: 'existing' }
        }
      } catch (e) {
        continue
      }
    }

    if (createIfNone) {
      // 角色创建涉及菜单关联，复杂场景不自动创建
      throw new Error('Auto-create role not implemented')
    }

    throw new Error(`No role with >=${minPermissions} permissions found`)
  })
}

/**
 * 智能查找用户组
 */
export async function findOrCreateUserGroup(page, options = {}) {
  const { minMembers = 0, createIfNone = false } = options

  return getCached(`userGroup:${minMembers}`, async () => {
    const groups = extractItems(await apiGet(page, '/api/v2/bo/user_group?page_size=100'))

    for (const group of groups) {
      if ((group.member_count || 0) >= minMembers) {
        return { group, source: 'existing' }
      }
    }

    if (createIfNone) {
      const testId = generateTestId('e2e_ug')
      const groupResp = await apiPost(page, '/api/v2/bo/user_group', {
        id: testId,
        code: testId.toUpperCase(),
        name: `测试用户组_${testId}`,
        description: 'Auto-created by E2E data-finder',
        is_active: true
      })
      const group = groupResp.data || groupResp
      return { group, source: 'created', testId }
    }

    throw new Error(`No user group with >=${minMembers} members found`)
  })
}

/**
 * 智能查找业务对象
 */
export async function findOrCreateBusinessObject(page, options = {}) {
  const { type = null, createIfNone = false } = options

  return getCached(`businessObject:${type}`, async () => {
    const params = type ? `?type=${type}&page_size=100` : '?page_size=100'
    const objects = extractItems(await apiGet(page, `/api/v2/bo/business_object${params}`))

    if (objects.length > 0) {
      return { objects, source: 'existing' }
    }

    if (createIfNone) {
      const testId = generateTestId('e2e_bo')
      const boResp = await apiPost(page, '/api/v2/bo/business_object', {
        code: testId.toUpperCase(),
        name: `测试业务对象_${testId}`,
        type: type || 'business_object',
        description: 'Auto-created by E2E data-finder'
      })
      const bo = boResp.data || boResp
      return { objects: [bo], source: 'created', testId }
    }

    throw new Error(`No business object found (type=${type})`)
  })
}

// ============================================================
// 数据清理（afterEach 用）
// ============================================================
export async function cleanupTestArtifacts(page, testIds) {
  if (!testIds || testIds.length === 0) return
  for (const id of testIds) {
    try {
      await apiDelete(page, `/api/v2/bo/version/${id}`)
    } catch (e) { /* ignore */ }
    try {
      await apiDelete(page, `/api/v2/bo/product/${id}`)
    } catch (e) { /* ignore */ }
  }
}

export { clearCache }
