/**
 * productFactory.js - Product & Version Test Data Factory
 *
 * Usage:
 *   import { createProduct, createVersion, setupProductWithVersion } from '@/test/factories/productFactory'
 *
 *   // Unit test
 *   const mockProduct = createProduct()
 *
 *   // E2E test
 *   const pv = await setupProductWithVersion(api)
 *   // ... test ...
 *   await cleanupProductWithVersion(pv, api)
 */

const COUNTER = { value: 0 }

function nextId() {
  COUNTER.value += 1
  return COUNTER.value
}

function randomStr(n = 4) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  for (let i = 0; i < n; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return result
}

export function createProduct(overrides = {}) {
  const id = nextId()
  const ts = Date.now()
  return {
    id,
    name: `Test Product ${id}_${ts}`,
    code: `test_product_${id}_${ts}_${randomStr()}`,
    status: 'active',
    version: '1.0.0',
    description: `Auto-generated test product ${id}`,
    ...overrides
  }
}

export function createVersion(overrides = {}) {
  const id = nextId()
  const ts = Date.now()
  return {
    id,
    name: `V1.0_${ts}_${randomStr()}`,
    code: `v1_0_${ts}_${randomStr()}`,
    status: 'active',
    version_number: '1.0.0',
    release_date: new Date().toISOString().split('T')[0],
    ...overrides
  }
}

export async function createProductViaApi(api, overrides = {}) {
  const product = createProduct(overrides)
  const resp = await api.post('/api/v2/bo/product', {
    data: product,
    headers: { 'Content-Type': 'application/json' }
  })

  if (!resp.ok()) {
    throw new Error(`Failed to create product: ${resp.status()} ${await resp.text()}`)
  }

  const json = await resp.json()
  return { ...product, id: json.data?.id || product.id }
}

export async function createVersionViaApi(api, productId, overrides = {}) {
  const version = createVersion({ product_id: productId, ...overrides })
  const resp = await api.post('/api/v2/bo/version', {
    data: version,
    headers: { 'Content-Type': 'application/json' }
  })

  if (!resp.ok()) {
    throw new Error(`Failed to create version: ${resp.status()} ${await resp.text()}`)
  }

  const json = await resp.json()
  return { ...version, id: json.data?.id || version.id }
}

/**
 * Setup product with version - main entry point for E2E tests
 * @param {object} api - Playwright API request object
 * @param {object} overrides - Optional overrides for product
 * @returns {Promise<{product: object, version: object}>}
 */
export async function setupProductWithVersion(api, overrides = {}) {
  const product = await createProductViaApi(api, overrides)
  const version = await createVersionViaApi(api, product.id)
  return { product, version }
}

/**
 * Cleanup product with version
 * @param {object} pv - { product, version }
 * @param {object} api - Playwright API request object
 */
export async function cleanupProductWithVersion(pv, api) {
  if (!pv || !api) return
  try {
    if (pv.version?.id) {
      await api.delete(`/api/v2/bo/version/${pv.version.id}`)
    }
  } catch (e) {
    console.warn(`[cleanupProductWithVersion] Failed to cleanup version ${pv.version?.id}:`, e.message)
  }
  try {
    if (pv.product?.id) {
      await api.delete(`/api/v2/bo/product/${pv.product.id}`)
    }
  } catch (e) {
    console.warn(`[cleanupProductWithVersion] Failed to cleanup product ${pv.product?.id}:`, e.message)
  }
}

export function buildProductResponse(product) {
  return {
    success: true,
    data: product
  }
}

export function buildVersionResponse(version) {
  return {
    success: true,
    data: version
  }
}

export function buildPaginatedResponse(items, total = null) {
  return {
    success: true,
    data: {
      items: items,
      total: total ?? items.length,
      page: 1,
      page_size: 20
    }
  }
}
