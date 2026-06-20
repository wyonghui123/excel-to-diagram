/**
 * mockData.js - Mock Data Templates for Unit Tests
 *
 * Usage:
 *   import { mockUser, mockProduct, mockVersion, mockResponse, mockPaginatedResponse } from '@/test/fixtures/mockData'
 *
 *   // In test
 *   global.fetch.mockResolvedValueOnce(mockResponse(mockUser()))
 */

// =============================================================================
// User Mock Data
// =============================================================================

export function mockUser(overrides = {}) {
  return {
    id: 1,
    username: 'test_user_1',
    display_name: 'Test User 1',
    email: 'test1@example.com',
    role: 'user',
    roles: ['user'],
    permissions: ['*'],
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

export function mockAdminUser(overrides = {}) {
  return mockUser({
    id: 99,
    username: 'admin_user',
    display_name: 'Admin User',
    role: 'admin',
    roles: ['admin'],
    permissions: ['*'],
    ...overrides
  })
}

// =============================================================================
// Product Mock Data
// =============================================================================

export function mockProduct(overrides = {}) {
  return {
    id: 1,
    name: 'Test Product',
    code: 'test_product',
    status: 'active',
    version: '1.0.0',
    description: 'Test product description',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

export function mockVersion(overrides = {}) {
  return {
    id: 1,
    product_id: 1,
    name: 'V1.0.0',
    code: 'v1_0_0',
    status: 'active',
    version_number: '1.0.0',
    release_date: '2026-01-01',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

// =============================================================================
// Business Object Mock Data
// =============================================================================

export function mockBusinessObject(overrides = {}) {
  return {
    id: 1,
    name: 'Test Business Object',
    code: 'test_bo',
    service_module_id: 1,
    version_id: 1,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

export function mockDomain(overrides = {}) {
  return {
    id: 1,
    name: 'Test Domain',
    code: 'test_domain',
    version_id: 1,
    description: 'Test domain description',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

export function mockSubDomain(overrides = {}) {
  return {
    id: 1,
    name: 'Test SubDomain',
    code: 'test_subdomain',
    domain_id: 1,
    version_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

export function mockServiceModule(overrides = {}) {
  return {
    id: 1,
    name: 'Test Service Module',
    code: 'test_sm',
    sub_domain_id: 1,
    version_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  }
}

// =============================================================================
// Response Helpers
// =============================================================================

export function mockResponse(data, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(data)
  }
}

export function mockSuccessResponse(data) {
  return mockResponse({ success: true, data })
}

export function mockErrorResponse(message, status = 400) {
  return mockResponse({ success: false, message }, false, status)
}

export function mockPaginatedResponse(items, total = null, page = 1, pageSize = 20) {
  return mockSuccessResponse({
    items,
    total: total ?? items.length,
    page,
    page_size: pageSize
  })
}

// =============================================================================
// API Mock Data for common endpoints
// =============================================================================

export function mockApiResponses() {
  return {
    user: mockSuccessResponse(mockUser()),
    userList: mockPaginatedResponse([mockUser(), mockAdminUser()]),
    product: mockSuccessResponse(mockProduct()),
    productList: mockPaginatedResponse([mockProduct()]),
    version: mockSuccessResponse(mockVersion()),
    versionList: mockPaginatedResponse([mockVersion()]),
    domain: mockSuccessResponse(mockDomain()),
    domainList: mockPaginatedResponse([mockDomain()]),
    subDomain: mockSuccessResponse(mockSubDomain()),
    subDomainList: mockPaginatedResponse([mockSubDomain()]),
    serviceModule: mockSuccessResponse(mockServiceModule()),
    serviceModuleList: mockPaginatedResponse([mockServiceModule()]),
    businessObject: mockSuccessResponse(mockBusinessObject()),
    businessObjectList: mockPaginatedResponse([mockBusinessObject()]),
  }
}
