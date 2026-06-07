/**
 * boService.spec.js - BO Service API 测试
 *
 * 测试核心功能：
 * 1. CRUD 操作: create/read/update/delete
 * 2. Association 操作: associate/dissociate/queryAssociations
 * 3. V2 Association API: queryAssociationsV2/countAssociationsV2/assignAssociationV2
 * 4. 批量操作: batchAssignAssociationsV2/batchUnassignAssociationsV2
 * 5. Deep Insert: retrieveWithAssociations/deepInsert/batchCreate
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const API_BASE_V2 = '/api/v2'

global.fetch = vi.fn()

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    isAuthenticated: true,
    getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
  })
}))

vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json' }),
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
}))

function createMockResponse(data, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(data)
  }
}

function createSuccessResponse(data) {
  return createMockResponse({ success: true, data })
}

function createErrorResponse(message, status = 400) {
  return createMockResponse({ success: false, message }, false, status)
}

describe('BOService API', () => {
  let boService
  let BaseService

  beforeEach(async () => {
    vi.clearAllMocks()

    const module = await import('@/services/boService')
    boService = module.default
    // boService.cache 是 BOService 自己的空 cache；
    // 实际缓存存在 BOCrudService 实例上
    if (boService.cache) {
      boService.cache.clear()
    }
    if (boService._crud?.cache) {
      boService._crud.cache.clear()
    }
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('CRUD Operations', () => {
    describe('create', () => {
      it('creates a new record successfully', async () => {
        const mockData = { name: 'Test User', email: 'test@example.com' }
        const createdData = { id: 1, ...mockData }

        global.fetch.mockResolvedValue(createSuccessResponse(createdData))

        const result = await boService.create('user', mockData)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user`,
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify(mockData)
          })
        )
        expect(result.success).toBe(true)
        expect(result.data).toEqual(createdData)
      })

      it('handles create failure', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Validation failed'))

        const result = await boService.create('user', { name: '' })

        expect(result.success).toBe(false)
        expect(result.message).toBe('Validation failed')
      })
    })

    describe('read', () => {
      it('reads a record by id', async () => {
        const mockData = { id: 1, name: 'Test User' }

        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        const result = await boService.read('user', 1)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1`,
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.success).toBe(true)
        expect(result.data).toEqual(mockData)
      })

      it('returns cached result on second call', async () => {
        const mockData = { id: 1, name: 'Test User' }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        await boService.read('user', 1)
        await boService.read('user', 1)

        expect(global.fetch).toHaveBeenCalledTimes(1)
      })

      it('handles read failure', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Not found', 404))

        const result = await boService.read('user', 999)

        expect(result.success).toBe(false)
      })
    })

    describe('query', () => {
      it('queries records with filters', async () => {
        const mockData = { items: [], total: 0 }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        const result = await boService.query('user', { status: 'active', page: 1 })

        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining(`${API_BASE_V2}/bo/user?`),
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.success).toBe(true)
      })

      it('queries records without filters', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ items: [], total: 0 }))

        await boService.query('user')

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user`,
          expect.objectContaining({ method: 'GET' })
        )
      })
    })

    describe('update', () => {
      it('updates a record successfully', async () => {
        const updateData = { name: 'Updated Name' }
        const updatedData = { id: 1, ...updateData }

        global.fetch.mockResolvedValue(createSuccessResponse(updatedData))

        const result = await boService.update('user', 1, updateData)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1`,
          expect.objectContaining({
            method: 'PUT',
            body: JSON.stringify(updateData)
          })
        )
        expect(result.success).toBe(true)
      })

      it('handles update failure', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Conflict'))

        const result = await boService.update('user', 1, { name: 'test' })

        expect(result.success).toBe(false)
      })
    })

    describe('delete', () => {
      it('deletes a record successfully', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({}))

        const result = await boService.delete('user', 1)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1`,
          expect.objectContaining({ method: 'DELETE' })
        )
        expect(result.success).toBe(true)
      })

      it('handles delete failure', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Cannot delete', 409))

        const result = await boService.delete('user', 1)

        expect(result.success).toBe(false)
      })
    })
  })

  describe('Association Operations (v1)', () => {
    describe('associate', () => {
      it('associates a record successfully', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({}))

        const result = await boService.associate('user', 1, 'roles', 5)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1/associations/roles`,
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ target_id: 5 })
          })
        )
        expect(result.success).toBe(true)
      })

      it('associates with targetType', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({}))

        await boService.associate('user', 1, 'permissions', 10, 'permission')

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1/associations/permissions`,
          expect.objectContaining({
            body: JSON.stringify({ target_id: 10, target_type: 'permission' })
          })
        )
      })
    })

    describe('dissociate', () => {
      it('dissociates a record successfully', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({}))

        const result = await boService.dissociate('user', 1, 'roles', 5)

        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining(`${API_BASE_V2}/bo/user/1/associations/roles?target_id=5`),
          expect.objectContaining({ method: 'DELETE' })
        )
        expect(result.success).toBe(true)
      })
    })

    describe('queryAssociations', () => {
      it('queries association data', async () => {
        const mockData = { items: [{ id: 1, name: 'Admin' }], total: 1 }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        const result = await boService.queryAssociations('user', 1, 'roles', { page: 1 })

        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining(`${API_BASE_V2}/bo/user/1/associations/roles`),
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.success).toBe(true)
        expect(result.data.items).toHaveLength(1)
      })

      it('returns cached result on second call', async () => {
        const mockData = { items: [{ id: 1 }], total: 1 }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        await boService.queryAssociations('user', 1, 'roles')
        await boService.queryAssociations('user', 1, 'roles')

        expect(global.fetch).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Association Operations (v2 - $associations)', () => {
    describe('queryAssociationsV2', () => {
      it('queries association data with $associations endpoint', async () => {
        const mockData = { items: [{ id: 1, name: 'Admin' }], total: 1 }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        const result = await boService.queryAssociationsV2('user', 1, 'roles', { page: 1 })

        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining(`${API_BASE_V2}/bo/user/1/$associations/roles`),
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.success).toBe(true)
      })
    })

    describe('countAssociationsV2', () => {
      it('counts association records', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ count: 5 }))

        const result = await boService.countAssociationsV2('user', 1, 'roles')

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1/$associations/roles/count`,
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.data.count).toBe(5)
      })
    })

    describe('assignAssociationV2', () => {
      it('assigns association with 204 response', async () => {
        global.fetch.mockResolvedValue({
          ok: true,
          status: 204,
          headers: new Headers()
        })

        const result = await boService.assignAssociationV2('user', 1, 'roles', { target_id: 5 })

        expect(result).toBe(true)
      })

      it('assigns association with JSON response', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ success: true }))

        const result = await boService.assignAssociationV2('user', 1, 'roles', { target_id: 5 })

        expect(result.success).toBe(true)
      })

      it('handles assign failure', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Already assigned'))

        const result = await boService.assignAssociationV2('user', 1, 'roles', { target_id: 5 })

        expect(result.success).toBe(false)
      })
    })

    describe('unassignAssociationV2', () => {
      it('unassigns association successfully', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ success: true }))

        const result = await boService.unassignAssociationV2('user', 1, 'roles', { target_id: 5 })

        expect(result.success).toBe(true)
      })
    })

    describe('batchAssignAssociationsV2', () => {
      it('batch assigns associations', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({
          results: [{ target_id: 1, success: true }]
        }))

        const result = await boService.batchAssignAssociationsV2('user', 1, 'roles', {
          target_ids: [1, 2, 3]
        })

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/user/1/$associations/roles/batch_assign`,
          expect.objectContaining({ method: 'POST' })
        )
        expect(result.success).toBe(true)
      })
    })

    describe('batchUnassignAssociationsV2', () => {
      it('batch unassigns associations', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({
          results: [{ target_id: 1, success: true }]
        }))

        const result = await boService.batchUnassignAssociationsV2('user', 1, 'roles', {
          target_ids: [1, 2, 3]
        })

        expect(result.success).toBe(true)
      })
    })
  })

  describe('Deep Insert Operations', () => {
    describe('retrieveWithAssociations', () => {
      it('retrieves with associations', async () => {
        const mockData = {
          id: 1,
          name: 'Test',
          roles: [{ id: 1, name: 'Admin' }]
        }
        global.fetch.mockResolvedValue(createSuccessResponse(mockData))

        const result = await boService.retrieveWithAssociations('user', 1, {
          associations: ['roles'],
          depth: 1
        })

        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining(`${API_BASE_V2}/bo/user/1/retrieve?`),
          expect.objectContaining({ method: 'GET' })
        )
        expect(result.success).toBe(true)
        expect(result.data.roles).toBeDefined()
      })
    })

    describe('deepInsert', () => {
      it('creates parent with children', async () => {
        const mockData = {
          parent: { name: 'Test' },
          children: { items: [{ name: 'Item 1' }] }
        }
        global.fetch.mockResolvedValue(createSuccessResponse({ id: 1, ...mockData }))

        const result = await boService.deepInsert('order', mockData.parent, mockData.children)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/order/deep`,
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ parent: mockData.parent, children: mockData.children, options: {} })
          })
        )
        expect(result.success).toBe(true)
      })
    })

    describe('batchCreate', () => {
      it('creates multiple records', async () => {
        const items = [{ name: 'Item 1' }, { name: 'Item 2' }]
        global.fetch.mockResolvedValue(createSuccessResponse({ created: 2 }))

        const result = await boService.batchCreate('item', items)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/item/batch`,
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ items })
          })
        )
        expect(result.success).toBe(true)
      })
    })
  })

  describe('executeAction', () => {
    it('executes a custom action', async () => {
      global.fetch.mockResolvedValue(createSuccessResponse({ result: 'completed' }))

      const result = await boService.executeAction('user', 1, 'activate', {})

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_V2}/bo/user/1/actions/activate`,
        expect.objectContaining({ method: 'POST' })
      )
      expect(result.success).toBe(true)
    })
  })
})
