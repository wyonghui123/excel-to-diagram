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
  // [FIX 2026-06-13] 必须传 visibility='private' - schema 要求必填,否则后端拒
  const productResp = await apiPost(page, '/api/v2/bo/product', {
    code: testId.toUpperCase(),
    name: `测试产品_${testId}`,
    description: 'Auto-created by E2E data-finder',
    is_active: true,
    visibility: 'private'
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

/**
 * 确保 version 里有完整的层级（domain/sub_domain/service_module）+ ≥4 个 BO
 * 返回 { product, version, businessObjects, hierarchy?, source }
 */
export async function findOrCreateBusinessObjectHierarchy(page, options = {}) {
  const { minBos = 4, scopeNamePrefix = 'E2E_RSS', createIfNone = true } = options
  return getCached(`boHierarchy:${minBos}:${scopeNamePrefix}`, async () => {
    const pv = await findOrCreateProductWithVersion(page, { createIfNone })
    const versionId = pv.version.id

    // 1. 查现有 BOs
    const resp = await page.request.get(`/api/v2/bo/business_object?version_id=${versionId}&page_size=100`)
    const body = await resp.json().catch(() => ({}))
    const bos = body.data?.items || body.data || []

    // 2. 查 service_modules（带层级的）
    const usable = bos.filter(b => b.service_module_id)
    if (usable.length >= minBos) {
      return { product: pv.product, version: pv.version, businessObjects: usable, source: 'existing' }
    }

    if (!createIfNone) {
      throw new Error(`Not enough BOs with hierarchy (have ${usable.length}/${minBos})`)
    }

    // 3. 重建层级
    const tag = `RSS${Math.random().toString(36).slice(2, 8).toUpperCase()}`

    const domainResp = await page.request.post('/api/v2/bo/domain', {
      data: { code: `D${tag}`, name: `域${tag}`, version_id: versionId }
    })
    const domainBody = await domainResp.json()
    if (!domainBody.success) throw new Error(`create domain failed: ${JSON.stringify(domainBody)}`)
    const domain = domainBody.data

    const subDomainResp = await page.request.post('/api/v2/bo/sub_domain', {
      data: { code: `SD${tag}`, name: `子域${tag}`, domain_id: domain.id, version_id: versionId }
    })
    const subDomainBody = await subDomainResp.json()
    if (!subDomainBody.success) throw new Error(`create sub_domain failed: ${JSON.stringify(subDomainBody)}`)
    const subDomain = subDomainBody.data

    const sm1Resp = await page.request.post('/api/v2/bo/service_module', {
      data: { code: `SM1${tag}`, name: `模块1${tag}`, sub_domain_id: subDomain.id, version_id: versionId }
    })
    const sm1Body = await sm1Resp.json()
    if (!sm1Body.success) throw new Error(`create service_module1 failed: ${JSON.stringify(sm1Body)}`)
    const sm1 = sm1Body.data

    const sm2Resp = await page.request.post('/api/v2/bo/service_module', {
      data: { code: `SM2${tag}`, name: `模块2${tag}`, sub_domain_id: subDomain.id, version_id: versionId }
    })
    const sm2Body = await sm2Resp.json()
    if (!sm2Body.success) throw new Error(`create service_module2 failed: ${JSON.stringify(sm2Body)}`)
    const sm2 = sm2Body.data

    const createdBos = []
    for (let i = 0; i < Math.max(minBos, 4); i++) {
      const boResp = await page.request.post('/api/v2/bo/business_object', {
        data: {
          code: `BO${tag}${i}`,
          name: `对象${i}${tag}`,
          service_module_id: i < 2 ? sm1.id : sm2.id,
          version_id: versionId
        }
      })
      const boBody = await boResp.json()
      if (!boBody.success) throw new Error(`create BO ${i} failed: ${JSON.stringify(boBody)}`)
      createdBos.push(boBody.data)
    }

    return {
      product: pv.product, version: pv.version,
      businessObjects: createdBos,
      hierarchy: { domain, subDomain, serviceModules: [sm1, sm2] },
      source: 'created'
    }
  })
}

/**
 * 在已有版本里创建多条关系（同服务模块 + 跨服务模块）
 * 返回 { relationships, versionId, product, version }
 */
export async function ensureRelationships(page, options = {}) {
  const { minCount = 3, createIfNone = true, hierarchy } = options
  return getCached(`relationships:${minCount}`, async () => {
    const hier = hierarchy || await findOrCreateBusinessObjectHierarchy(page, { createIfNone })
    const versionId = hier.version.id
    const bos = hier.businessObjects
    const sm1 = bos.filter(b => b.service_module_id === hier.hierarchy?.serviceModules?.[0]?.id)
    const sm2 = bos.filter(b => b.service_module_id === hier.hierarchy?.serviceModules?.[1]?.id)

    const created = []
    // 同服务模块
    if (sm1.length >= 2) {
      const r = await page.request.post('/api/v2/bo/relationship', {
        data: {
          relation_code: 'INTERNAL_CALL',
          relation_desc: `E2E_RSS_intra_${Date.now()}`,
          version_id: versionId,
          source_bo_id: sm1[0].id, target_bo_id: sm1[1].id
        }
      })
      const rb = await r.json()
      if (rb.success) created.push(rb.data)
    }
    // 跨服务模块
    if (sm1[0] && sm2[0]) {
      const r = await page.request.post('/api/v2/bo/relationship', {
        data: {
          relation_code: 'INTERNAL_CALL',
          relation_desc: `E2E_RSS_inter_${Date.now()}`,
          version_id: versionId,
          source_bo_id: sm1[0].id, target_bo_id: sm2[0].id
        }
      })
      const rb = await r.json()
      if (rb.success) created.push(rb.data)
    }
    return { relationships: created, versionId, product: hier.product, version: hier.version }
  })
}

// ============================================================
// 数据清理（afterEach 用）
// ============================================================
export { clearCache }

// [Phase 6 清理] 删除 dead code: cleanupTestArtifacts
// 原因: 无 spec 使用, 已被 isolation.createTracked + cleanup 拓扑序取代
// 旧位置: 第 405-415 行
