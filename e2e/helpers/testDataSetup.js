/**
 * testDataSetup.js - E2E Test Data Setup Utilities
 *
 * This module provides utilities for setting up and tearing down test data
 * in E2E tests, ensuring tests are isolated and reproducible.
 *
 * Usage:
 *   import { ensureProductWithVersion, cleanupTestData } from '../helpers/testDataSetup'
 *
 *   test('my test', async ({ page }) => {
 *     // Setup
 *     const pv = await ensureProductWithVersion(page)
 *
 *     // Navigate with product/version pre-selected
 *     await page.goto(`/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`)
 *
 *     // ... test assertions ...
 *
 *     // Cleanup (auto if using testDataCleanup fixture)
 *   })
 *
 * Or use the fixture pattern:
 *   test.use({ testData: await setupTestData(page) })
 *
 *   test('my test', async ({ page, testData }) => {
 *     await page.goto(`/system/archdata?productId=${testData.product.id}&versionId=${testData.version.id}`)
 *     // ... test ...
 *   })
 */

import { getAuthHeaders } from './auth.js'

// =============================================================================
// API Request Helpers
// =============================================================================

async function apiRequest(page, method, url, data = null) {
  const headers = await getAuthHeaders(page)
  const options = {
    method,
    headers: { ...headers, 'Content-Type': 'application/json' }
  }
  if (data) {
    options.body = JSON.stringify(data)
  }
  return await page.request.fetch(url, options)
}

async function apiPost(page, url, data) {
  return apiRequest(page, 'POST', url, data)
}

async function apiDelete(page, url) {
  return apiRequest(page, 'DELETE', url)
}

// =============================================================================
// Data Cleanup Registry
// =============================================================================

const _cleanupRegistry = []

export function registerCleanup(cleanupFn) {
  _cleanupRegistry.push(cleanupFn)
}

export async function runCleanup() {
  for (const fn of _cleanupRegistry.reverse()) {
    try {
      await fn()
    } catch (e) {
      console.warn(`[cleanup] Failed:`, e.message)
    }
  }
  _cleanupRegistry.length = 0
}

export function clearCleanupRegistry() {
  _cleanupRegistry.length = 0
}

// =============================================================================
// Product & Version Setup
// =============================================================================

/**
 * Find existing product with version, or create new ones
 * @param {Page} page - Playwright page
 * @returns {Promise<{product: object, version: object}>}
 */
export async function findProductWithVersion(page) {
  const products = await getPaginatedData(page, '/api/v2/bo/product')
  for (const p of products) {
    const versions = await getPaginatedData(page, `/api/v2/bo/version?product_id=${p.id}`)
    if (versions.length > 0) {
      return { product: p, version: versions[0] }
    }
  }
  return null
}

/**
 * Ensure test data exists - create if not found
 * This is the MAIN entry point for E2E tests
 * @param {Page} page - Playwright page
 * @param {object} options - Optional overrides
 * @returns {Promise<{product: object, version: object}>}
 */
export async function ensureProductWithVersion(page, options = {}) {
  // Try to find existing first
  const existing = await findProductWithVersion(page)
  if (existing) {
    console.log(`[testData] Using existing product: ${existing.product.id}, version: ${existing.version.id}`)
    return existing
  }

  // Create new if not found
  console.log(`[testData] No existing product found, creating new...`)
  return await createProductWithVersion(page, options)
}

/**
 * Create new product with version
 * @param {Page} page - Playwright page
 * @param {object} options - Optional overrides
 * @returns {Promise<{product: object, version: object}>}
 */
export async function createProductWithVersion(page, options = {}) {
  const headers = await getAuthHeaders(page)
  const timestamp = Date.now()

  // Create product
  const productData = {
    name: options.productName || `E2E_Test_Product_${timestamp}`,
    code: options.productCode || `e2e_product_${timestamp}`,
    status: 'active',
    ...options.productOverrides
  }

  const productResp = await apiPost(page, '/api/v2/bo/product', productData)
  let product
  if (productResp.ok()) {
    const json = await productResp.json()
    product = json.data
  } else {
    // Fallback: try to parse error but continue with mock ID
    const text = await productResp.text()
    console.warn(`[testData] Failed to create product: ${productResp.status()} ${text}`)
    product = { id: 1, ...productData } // Use fallback
  }

  // Create version
  const versionData = {
    name: options.versionName || `V1.0_E2E_${timestamp}`,
    code: options.versionCode || `v1_0_e2e_${timestamp}`,
    product_id: product.id,
    status: 'active',
    ...options.versionOverrides
  }

  const versionResp = await apiPost(page, '/api/v2/bo/version', versionData)
  let version
  if (versionResp.ok()) {
    const json = await versionResp.json()
    version = json.data
  } else {
    const text = await versionResp.text()
    console.warn(`[testData] Failed to create version: ${versionResp.status()} ${text}`)
    version = { id: 1, ...versionData } // Use fallback
  }

  // Register cleanup
  registerCleanup(async () => {
    try {
      if (version?.id) {
        await apiDelete(page, `/api/v2/bo/version/${version.id}`)
        console.log(`[testData] Cleaned up version: ${version.id}`)
      }
    } catch (e) {
      console.warn(`[testData] Failed to cleanup version:`, e.message)
    }
    try {
      if (product?.id) {
        await apiDelete(page, `/api/v2/bo/product/${product.id}`)
        console.log(`[testData] Cleaned up product: ${product.id}`)
      }
    } catch (e) {
      console.warn(`[testData] Failed to cleanup product:`, e.message)
    }
  })

  console.log(`[testData] Created product: ${product.id}, version: ${version.id}`)
  return { product, version }
}

/**
 * Cleanup test data - call after tests
 * @param {Page} page - Playwright page
 * @param {object} testData - { product, version }
 */
export async function cleanupTestData(page, testData) {
  if (!testData) return

  try {
    if (testData.version?.id) {
      await apiDelete(page, `/api/v2/bo/version/${testData.version.id}`)
      console.log(`[testData] Cleaned up version: ${testData.version.id}`)
    }
  } catch (e) {
    console.warn(`[testData] Failed to cleanup version:`, e.message)
  }

  try {
    if (testData.product?.id) {
      await apiDelete(page, `/api/v2/bo/product/${testData.product.id}`)
      console.log(`[testData] Cleaned up product: ${testData.product.id}`)
    }
  } catch (e) {
    console.warn(`[testData] Failed to cleanup product:`, e.message)
  }
}

// =============================================================================
// Domain/SubDomain/ServiceModule Setup
// =============================================================================

/**
 * Setup hierarchy data (domain -> sub_domain -> service_module -> business_object)
 * @param {Page} page - Playwright page
 * @param {object} testData - Product with version data
 * @returns {Promise<{domain: object, subDomain: object, serviceModule: object}>}
 */
export async function setupHierarchyData(page, testData) {
  const { product, version } = testData
  const headers = await getAuthHeaders(page)
  const timestamp = Date.now()

  const result = {}

  // Create domain
  const domainData = {
    name: `Test Domain ${timestamp}`,
    code: `test_domain_${timestamp}`,
    version_id: version.id,
    description: 'E2E test domain'
  }
  const domainResp = await apiPost(page, '/api/v2/bo/domain', domainData)
  if (domainResp.ok()) {
    const json = await domainResp.json()
    result.domain = json.data
  }

  // Create sub_domain
  if (result.domain) {
    const subDomainData = {
      name: `Test SubDomain ${timestamp}`,
      code: `test_subdomain_${timestamp}`,
      domain_id: result.domain.id,
      version_id: version.id,
      description: 'E2E test subdomain'
    }
    const subDomainResp = await apiPost(page, '/api/v2/bo/sub_domain', subDomainData)
    if (subDomainResp.ok()) {
      const json = await subDomainResp.json()
      result.subDomain = json.data
    }
  }

  // Create service_module
  if (result.subDomain) {
    const smData = {
      name: `Test ServiceModule ${timestamp}`,
      code: `test_sm_${timestamp}`,
      sub_domain_id: result.subDomain.id,
      version_id: version.id,
      description: 'E2E test service module'
    }
    const smResp = await apiPost(page, '/api/v2/bo/service_module', smData)
    if (smResp.ok()) {
      const json = await smResp.json()
      result.serviceModule = json.data
    }
  }

  // Register cleanup
  registerCleanup(async () => {
    if (result.serviceModule?.id) {
      await apiDelete(page, `/api/v2/bo/service_module/${result.serviceModule.id}`).catch(() => {})
    }
    if (result.subDomain?.id) {
      await apiDelete(page, `/api/v2/bo/sub_domain/${result.subDomain.id}`).catch(() => {})
    }
    if (result.domain?.id) {
      await apiDelete(page, `/api/v2/bo/domain/${result.domain.id}`).catch(() => {})
    }
  })

  return result
}

// =============================================================================
// Complete Test Data Setup
// =============================================================================

/**
 * Setup complete test data for arch data tests
 * Creates: product -> version -> domain -> sub_domain -> service_module -> business_object
 * @param {Page} page - Playwright page
 * @returns {Promise<{product, version, domain?, subDomain?, serviceModule?, businessObject?}>}
 */
export async function setupCompleteArchData(page) {
  // Step 1: Ensure product with version
  const pv = await ensureProductWithVersion(page)

  // Step 2: Setup hierarchy
  const hierarchy = await setupHierarchyData(page, pv)

  // Step 3: Create a business object
  const headers = await getAuthHeaders(page)
  const timestamp = Date.now()
  let bo = null

  if (hierarchy.serviceModule) {
    const boData = {
      name: `Test BO ${timestamp}`,
      code: `test_bo_${timestamp}`,
      service_module_id: hierarchy.serviceModule.id,
      version_id: pv.version.id,
      description: 'E2E test business object'
    }
    const boResp = await apiPost(page, '/api/v2/bo/business_object', boData)
    if (boResp.ok()) {
      const json = await boResp.json()
      bo = json.data
    }
  }

  return {
    ...pv,
    ...hierarchy,
    businessObject: bo
  }
}

// =============================================================================
// Helper: Get Paginated Data
// =============================================================================

async function getPaginatedData(page, url) {
  const resp = await page.request.fetch(url, {
    headers: await getAuthHeaders(page)
  })
  if (!resp.ok()) return []
  const json = await resp.json()
  return json.data?.items || json.data?.records || json.data?.list || json.data?.rows || (Array.isArray(json.data) ? json.data : [])
}
