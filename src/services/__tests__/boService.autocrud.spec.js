/**
 * boService.autocrud.spec.js - MetaListPage enableAutoCrud    
 *
 * AddMemberDialog / GroupFormDialog / UserFormDialog  
 * boService / BaseService  CRUD   
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

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

function createListResponse(items, total = 0) {
  return createMockResponse({
    success: true,
    data: { items, total: total || items.length, page: 1, page_size: 10 }
  })
}

describe('BOService AutoCRUD (MetaListPage enableAutoCrud)', () => {
  let boService

  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const module = await import('@/services/boService')
    boService = module.default
    if (boService.cache) {
      boService.cache.clear()
    }
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe(' (MetaListPage  AddMemberDialog)', () => {
    const USER_GROUP_OBJECT = 'user_group'

    describe(' - create', () => {
      it(' (GroupFormDialog )', async () => {
        const mockData = { name: 'New Group', description: 'Test group' }
        const createdData = { id: 10, ...mockData, created_at: new Date().toISOString() }

        global.fetch.mockResolvedValue(createSuccessResponse(createdData))

        const result = await boService.create(USER_GROUP_OBJECT, mockData)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/${USER_GROUP_OBJECT}`,
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify(mockData)
          })
        )
        expect(result.success).toBe(true)
        expect(result.data.id).toBe(10)
        expect(result.data.name).toBe('New Group')
      })

      it('', async () => {
        global.fetch.mockResolvedValue(createErrorResponse('Name is required'))

        const result = await boService.create(USER_GROUP_OBJECT, { name: '' })

        expect(result.success).toBe(false)
        expect(result.message).toContain('required')
      })
    })

    describe(' - update', () => {
      it(' (GroupFormDialog )', async () => {
        const updateData = { name: 'Updated Group', description: 'Updated desc' }
        const updatedData = { id: 10, ...updateData, updated_at: new Date().toISOString() }

        global.fetch.mockResolvedValue(createSuccessResponse(updatedData))

        const result = await boService.update(USER_GROUP_OBJECT, 10, updateData)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/${USER_GROUP_OBJECT}/10`,
          expect.objectContaining({
            method: 'PUT',
            body: JSON.stringify(updateData)
          })
        )
        expect(result.success).toBe(true)
        expect(result.data.name).toBe('Updated Group')
      })
    })

    describe(' - delete', () => {
      it('MetaListPage ', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ id: 10, deleted: true }))

        const result = await boService.delete(USER_GROUP_OBJECT, 10)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/${USER_GROUP_OBJECT}/10`,
          expect.objectContaining({
            method: 'DELETE'
          })
        )
        expect(result.success).toBe(true)
      })
    })

    describe(' - query', () => {
      it('boService.query  ', async () => {
        const mockItems = [
          { id: 1, name: 'Group A', description: 'Desc A' },
          { id: 2, name: 'Group B', description: 'Desc B' }
        ]

        global.fetch.mockResolvedValue(createListResponse(mockItems))

        const result = await boService.query(USER_GROUP_OBJECT, { page: 1, page_size: 10 })

        expect(global.fetch).toHaveBeenCalled()
        expect(result.success).toBe(true)
        expect(result.data.items).toHaveLength(2)
        expect(result.data.total).toBe(2)
      })
    })
  })

  describe(' (MetaListPage  UserFormDialog)', () => {
    const USER_OBJECT = 'user'

    describe(' - create', () => {
      it('', async () => {
        const mockData = { username: 'newuser', password: 'Test123456', email: 'new@test.com' }
        const createdData = { id: 20, username: 'newuser', email: 'new@test.com' }

        global.fetch.mockResolvedValue(createSuccessResponse(createdData))

        const result = await boService.create(USER_OBJECT, mockData)

        expect(global.fetch).toHaveBeenCalledWith(
          `${API_BASE_V2}/bo/${USER_OBJECT}`,
          expect.objectContaining({ method: 'POST' })
        )
        expect(result.success).toBe(true)
        expect(result.data.username).toBe('newuser')
      })
    })

    describe(' - update', () => {
      it('', async () => {
        const updateData = { username: 'existinguser', email: 'updated@test.com' }
        const updatedData = { id: 20, ...updateData }

        global.fetch.mockResolvedValue(createSuccessResponse(updatedData))

        const result = await boService.update(USER_OBJECT, 20, updateData)

        expect(result.success).toBe(true)
        expect(result.data.email).toBe('updated@test.com')
      })
    })

    describe(' - delete', () => {
      it('', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ id: 20, deleted: true }))

        const result = await boService.delete(USER_OBJECT, 20)

        expect(result.success).toBe(true)
      })
    })

    describe(' - query', () => {
      it('boService.query  ', async () => {
        const mockItems = [
          { id: 1, username: 'admin', email: 'admin@test.com' },
          { id: 2, username: 'user1', email: 'user1@test.com' }
        ]

        global.fetch.mockResolvedValue(createListResponse(mockItems))

        const result = await boService.query(USER_OBJECT, { page: 1, page_size: 10 })

        expect(result.success).toBe(true)
        expect(result.data.items).toHaveLength(2)
      })
    })
  })

  describe(' (MetaListPage  AddMemberDialog)', () => {
    const USER_GROUP_MEMBER_OBJ = 'user_group_member'

    describe(' - add member (N-M)', () => {
      it('N-M  add', async () => {
        const memberData = { user_group_id: 10, user_id: 20 }
        const createdData = { id: 30, ...memberData }

        global.fetch.mockResolvedValue(createSuccessResponse(createdData))

        const result = await boService.create(USER_GROUP_MEMBER_OBJ, memberData)

        expect(result.success).toBe(true)
        expect(result.data.user_group_id).toBe(10)
        expect(result.data.user_id).toBe(20)
      })
    })

    describe(' - remove member (N-M)', () => {
      it('N-M  remove', async () => {
        global.fetch.mockResolvedValue(createSuccessResponse({ id: 30, deleted: true }))

        const result = await boService.delete(USER_GROUP_MEMBER_OBJ, 30)

        expect(result.success).toBe(true)
      })
    })
  })

  describe('', () => {
    it('boService CRUD  ', () => {
      expect(boService).toBeDefined()
      expect(typeof boService.create).toBe('function')
      expect(typeof boService.read).toBe('function')
      expect(typeof boService.update).toBe('function')
      expect(typeof boService.delete).toBe('function')
      expect(typeof boService.query).toBe('function')
    })

    it('query  ', async () => {
      const mockItems = [{ id: 1, name: 'Test' }]
      global.fetch.mockResolvedValue(createListResponse(mockItems, 1))
      const result = await boService.query('user', { page: 1, page_size: 10 })
      expect(result.success).toBe(true)
      expect(result.data.items.length).toBeGreaterThanOrEqual(1)
    })
  })
})
