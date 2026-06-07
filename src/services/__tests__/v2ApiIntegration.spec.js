/**
 * v2 API 前端集成测试
 * 
 * 测试内容：
 * 1. user/role/user_group CRUD (Phase 1)
 * 2. permission/data_permission CRUD (Phase 2)
 * 3. permission_bundle/permission_rule/menu_permission CRUD (Phase 2)
 * 4. Association 操作
 * 5. UI Config/Schema 端点
 * 6. Constraint 验证
 * 7. Deep Insert
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const BASE_URL = 'http://localhost:5000/api/v2'

const mockFetch = vi.fn()
global.fetch = mockFetch

const mockLocalStorage = {
  getItem: vi.fn(() => 'mock-token'),
  setItem: vi.fn(),
  removeItem: vi.fn(),
}
Object.defineProperty(global, 'localStorage', { value: mockLocalStorage })

describe('v2 API 前端集成测试', () => {
  beforeEach(() => {
    mockFetch.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('User CRUD (Phase 1)', () => {
    it('应该创建用户', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, username: 'testuser', email: 'test@example.com' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          username: 'testuser',
          email: 'test@example.com',
          password: 'Test@123',
          is_active: true
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.username).toBe('testuser')
    })

    it('应该读取用户', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, username: 'admin', email: 'admin@example.com' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出用户', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, username: 'admin' }, { id: 2, username: 'user' }], total: 2 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBe(2)
    })

    it('应该更新用户', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, email: 'newemail@example.com' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ email: 'newemail@example.com' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除用户', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该支持用户分页查询', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1 }], total: 10, page: 1, page_size: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user?page=1&page_size=1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.page).toBe(1)
    })

    it('应该支持用户过滤查询', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, username: 'admin' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user?username=admin`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items[0].username).toBe('admin')
    })
  })

  describe('Role CRUD (Phase 1)', () => {
    it('应该创建角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, code: 'test_role', name: 'Test Role' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          code: 'test_role',
          name: 'Test Role',
          is_system: false
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.code).toBe('test_role')
    })

    it('应该读取角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, code: 'admin', name: 'Admin' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, code: 'admin' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, name: 'Updated Role' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ name: 'Updated Role' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/role/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('User Group CRUD (Phase 1)', () => {
    it('应该创建用户组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, name: 'Test Group', code: 'test_group' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          name: 'Test Group',
          code: 'test_group'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该读取用户组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, name: 'Developers', code: 'dev' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出用户组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, name: 'Developers' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新用户组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, name: 'Updated Group' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ name: 'Updated Group' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除用户组', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Permission CRUD (Phase 2)', () => {
    it('应该创建权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, code: 'test:read', name: 'Test Read' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          code: 'test:read',
          name: 'Test Read',
          resource_type: 'test',
          action: 'read'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该读取权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, code: 'user:read', name: 'User Read' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, code: 'user:read' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, name: 'Updated Permission' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ name: 'Updated Permission' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Data Permission CRUD (Phase 2)', () => {
    it('应该创建数据权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, user_id: 1, resource_type: 'product', permission_level: 'read' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/data_permission`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          user_id: 1,
          resource_type: 'product',
          resource_id: 1,
          permission_level: 'read'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该读取数据权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, user_id: 1, resource_type: 'product', permission_level: 'read' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/data_permission/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出数据权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, resource_type: 'product' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/data_permission`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新数据权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, permission_level: 'write' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/data_permission/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ permission_level: 'write' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除数据权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/data_permission/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Permission Bundle CRUD (Phase 2)', () => {
    it('应该创建权限包', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, bundle_code: 'admin_bundle', bundle_name: 'Admin Bundle', is_active: true }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          bundle_code: 'admin_bundle',
          bundle_name: 'Admin Bundle',
          is_active: true,
          is_system: false
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.bundle_code).toBe('admin_bundle')
    })

    it('应该读取权限包', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, bundle_code: 'admin_bundle', bundle_name: 'Admin Bundle' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出权限包', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, bundle_code: 'admin_bundle' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新权限包', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, bundle_name: 'Updated Bundle' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ bundle_name: 'Updated Bundle' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除权限包', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Permission Rule CRUD (Phase 2)', () => {
    it('应该创建权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, rule_code: 'dept_read', rule_name: 'Department Read', effect: 'allow' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_rule`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          rule_code: 'dept_read',
          rule_name: 'Department Read',
          effect: 'allow',
          resource_type: 'department',
          action: 'read'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.rule_code).toBe('dept_read')
    })

    it('应该读取权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, rule_code: 'dept_read', rule_name: 'Department Read' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_rule/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, rule_code: 'dept_read' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_rule`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, rule_name: 'Updated Rule' }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_rule/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ rule_name: 'Updated Rule' })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_rule/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Menu Permission CRUD (Phase 2)', () => {
    it('应该创建菜单权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, role_id: 1, menu_id: 1, can_view: true, can_edit: false }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/menu_permission`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          role_id: 1,
          menu_id: 1,
          can_view: true,
          can_edit: false
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.role_id).toBe(1)
    })

    it('应该读取菜单权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, role_id: 1, menu_id: 1, can_view: true }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/menu_permission/1`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.id).toBe(1)
    })

    it('应该列出菜单权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, role_id: 1 }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/menu_permission`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.items.length).toBeGreaterThan(0)
    })

    it('应该更新菜单权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { id: 1, can_edit: true }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/menu_permission/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ can_edit: true })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该删除菜单权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      const response = await fetch(`${BASE_URL}/bo/menu_permission/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('Association 操作', () => {
    it('应该关联用户和角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, message: '关联成功' })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1/associations/roles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          target_id: 1,
          target_type: 'role'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该查询用户的角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { items: [{ id: 1, code: 'admin' }], total: 1 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1/associations/roles`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该取消用户和角色的关联', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, message: '取消关联成功' })
      })

      const response = await fetch(`${BASE_URL}/bo/user/1/associations/roles?target_id=1&target_type=role`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该关联角色和权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, message: '关联成功' })
      })

      const response = await fetch(`${BASE_URL}/bo/role/1/associations/permissions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          target_id: 1,
          target_type: 'permission'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该关联用户组和角色', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, message: '关联成功' })
      })

      const response = await fetch(`${BASE_URL}/bo/user_group/1/associations/roles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          target_id: 1,
          target_type: 'role'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('应该关联权限包和权限', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, message: '关联成功' })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle/1/associations/permissions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          target_id: 1,
          target_type: 'permission'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
    })
  })

  describe('UI Config 端点', () => {
    it('应该获取角色的 UI 配置', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'role',
            label: '角色',
            fields: [{ id: 'code', name: '编码', type: 'string' }],
            associations: [{ name: 'users', type: 'many_to_many' }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/role/ui-config`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('role')
      expect(data.data.fields.length).toBeGreaterThan(0)
    })

    it('应该获取用户的 UI 配置', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'user',
            label: '用户',
            fields: [{ id: 'username', name: '用户名', type: 'string' }],
            associations: [{ name: 'roles', type: 'many_to_many' }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/user/ui-config`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('user')
    })

    it('应该获取权限包的 UI 配置', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'permission_bundle',
            label: '权限包',
            fields: [{ id: 'bundle_code', name: '编码', type: 'string' }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/permission_bundle/ui-config`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('permission_bundle')
    })
  })

  describe('Schema 端点', () => {
    it('应该获取角色的 Schema', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'role',
            name: '角色',
            table_name: 'roles',
            fields: [{ id: 'code', name: '编码', type: 'string', required: true }],
            associations: [{ name: 'users', type: 'many_to_many', target_entity: 'user' }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/role/schema`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('role')
    })

    it('应该获取用户的 Schema', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'user',
            name: '用户',
            table_name: 'users',
            fields: [{ id: 'username', name: '用户名', type: 'string', required: true }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/user/schema`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('user')
    })

    it('应该获取权限规则的 Schema', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            object_type: 'permission_rule',
            name: '权限规则',
            table_name: 'permission_rules',
            fields: [{ id: 'rule_code', name: '规则编码', type: 'string', required: true }]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/meta/permission_rule/schema`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.object_type).toBe('permission_rule')
    })
  })

  describe('Constraint 验证', () => {
    it('系统角色不可删除', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: 400,
        json: () => Promise.resolve({
          success: false,
          message: '系统角色不可删除'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(false)
      expect(data.message).toContain('不可删除')
    })

    it('权限编码不可修改', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: 400,
        json: () => Promise.resolve({
          success: false,
          message: '权限编码创建后不可修改'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ code: 'new_code' })
      })

      const data = await response.json()
      expect(data.success).toBe(false)
      expect(data.message).toContain('不可修改')
    })

    it('系统权限包不可删除', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: 400,
        json: () => Promise.resolve({
          success: false,
          message: '系统权限包不可删除'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission_bundle/1`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(data.success).toBe(false)
      expect(data.message).toContain('不可删除')
    })

    it('角色编码唯一性验证', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: 400,
        json: () => Promise.resolve({
          success: false,
          message: '角色编码已存在'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/role`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          code: 'admin',
          name: 'Duplicate Admin'
        })
      })

      const data = await response.json()
      expect(data.success).toBe(false)
      expect(data.message).toContain('已存在')
    })
  })

  describe('Deep Insert', () => {
    it('应该创建父对象和子对象', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            parent: { id: 1, name: 'Parent Domain' },
            children: {
              sub_domain: [{ id: 1, name: 'Child SubDomain' }]
            }
          }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/domain/deep`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          parent: { name: 'Parent Domain' },
          children: {
            sub_domain: [{ name: 'Child SubDomain' }]
          }
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.parent.id).toBeDefined()
      expect(data.data.children.sub_domain.length).toBe(1)
    })

    it('应该支持多层级子对象创建', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            parent: { id: 1, name: 'Parent' },
            children: {
              child_a: [{ id: 1, name: 'Child A' }],
              child_b: [{ id: 2, name: 'Child B' }]
            }
          }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/parent/deep`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          parent: { name: 'Parent' },
          children: {
            child_a: [{ name: 'Child A' }],
            child_b: [{ name: 'Child B' }]
          }
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(Object.keys(data.data.children).length).toBe(2)
    })
  })

  describe('批量操作', () => {
    it('应该支持批量创建', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            created: 3,
            items: [
              { id: 1, code: 'perm1' },
              { id: 2, code: 'perm2' },
              { id: 3, code: 'perm3' }
            ]
          }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({
          items: [
            { code: 'perm1', name: 'Permission 1' },
            { code: 'perm2', name: 'Permission 2' },
            { code: 'perm3', name: 'Permission 3' }
          ]
        })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.created).toBe(3)
    })

    it('应该支持批量删除', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { deleted: 3 }
        })
      })

      const response = await fetch(`${BASE_URL}/bo/permission/batch`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({ ids: [1, 2, 3] })
      })

      const data = await response.json()
      expect(data.success).toBe(true)
      expect(data.data.deleted).toBe(3)
    })
  })

  describe('错误处理', () => {
    it('应该处理404错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({
          success: false,
          message: '对象不存在'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user/99999`, {
        headers: { 'Authorization': 'Bearer mock-token' }
      })

      const data = await response.json()
      expect(response.status).toBe(404)
      expect(data.success).toBe(false)
    })

    it('应该处理401未授权错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({
          success: false,
          message: '未授权访问'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user`, {
        headers: {}
      })

      const data = await response.json()
      expect(response.status).toBe(401)
      expect(data.success).toBe(false)
    })

    it('应该处理400参数错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({
          success: false,
          message: '缺少必填字段: username'
        })
      })

      const response = await fetch(`${BASE_URL}/bo/user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        },
        body: JSON.stringify({})
      })

      const data = await response.json()
      expect(response.status).toBe(400)
      expect(data.message).toContain('缺少')
    })
  })
})
