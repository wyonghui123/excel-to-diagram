/**
 * permissionService 单元测试
 *
 * 覆盖：
 *  - 纯函数：getPermissionLevelType / getPermissionLevelLabel / getResourceLabel / getDimensionName
 *  - 常量完整性：PERMISSION_LEVELS / RESOURCE_LABELS / DIMENSION_PARENT_MAP
 *  - API 函数：loadRoles / loadRole / loadDimensions / loadPermissionRules / savePermissionRules
 *  - API 函数：calculateImpact / loadUnifiedPermissions / searchUsers
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  PERMISSION_LEVELS,
  RESOURCE_LABELS,
  DIMENSION_PARENT_MAP,
  getPermissionLevelType,
  getPermissionLevelLabel,
  getResourceLabel,
  getDimensionName,
  loadRoles,
  loadRole,
  loadDimensions,
  loadPermissionRules,
  savePermissionRules,
  calculateImpact,
  loadUnifiedPermissions,
  searchUsers,
} from '../permissionService.js'

// vi.hoisted 让 mock 函数引用在 import 之前就创建
const mocks = vi.hoisted(() => ({
  apiV1Get: vi.fn(),
  apiV1Post: vi.fn(),
  apiV1Put: vi.fn(),
  apiV1Delete: vi.fn(),
  apiV1Patch: vi.fn(),
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: mocks.apiV1Get,
    post: mocks.apiV1Post,
    put: mocks.apiV1Put,
    delete: mocks.apiV1Delete,
    patch: mocks.apiV1Patch,
  },
}))

// 工具：构造 httpClient 标准响应
function okResp(data) {
  return {
    success: true,
    data,
    message: '',
    httpStatus: 200,
    traceId: 'trace-test',
  }
}

describe('permissionService', () => {
  beforeEach(() => {
    mocks.apiV1Get.mockReset()
    mocks.apiV1Post.mockReset()
    mocks.apiV1Put.mockReset()
    mocks.apiV1Delete.mockReset()
    mocks.apiV1Patch.mockReset()
  })

  // ==================== 常量完整性 ====================

  describe('PERMISSION_LEVELS', () => {
    it('应包含 none/read/write/admin/manage 五个级别', () => {
      expect(Object.keys(PERMISSION_LEVELS)).toEqual(
        expect.arrayContaining(['none', 'read', 'write', 'admin', 'manage'])
      )
      expect(Object.keys(PERMISSION_LEVELS)).toHaveLength(5)
    })

    it('每个级别应有 label 和 type 字段', () => {
      for (const [, val] of Object.entries(PERMISSION_LEVELS)) {
        expect(val).toHaveProperty('label')
        expect(val).toHaveProperty('type')
        expect(typeof val.label).toBe('string')
        expect(typeof val.type).toBe('string')
      }
    })
  })

  describe('RESOURCE_LABELS', () => {
    it('应包含 domain/sub_domain/service_module/business_object/product/version/relationship/annotation', () => {
      expect(Object.keys(RESOURCE_LABELS)).toEqual(
        expect.arrayContaining([
          'domain', 'sub_domain', 'service_module', 'business_object',
          'product', 'version', 'relationship', 'annotation',
        ])
      )
      expect(Object.keys(RESOURCE_LABELS)).toHaveLength(8)
    })
  })

  describe('DIMENSION_PARENT_MAP', () => {
    it('product 无父级，version 父级为 product，domain 父级为 version，sub_domain 父级为 domain', () => {
      expect(DIMENSION_PARENT_MAP.product).toBeNull()
      expect(DIMENSION_PARENT_MAP.version).toBe('product')
      expect(DIMENSION_PARENT_MAP.domain).toBe('version')
      expect(DIMENSION_PARENT_MAP.sub_domain).toBe('domain')
    })
  })

  // ==================== 纯函数 ====================

  describe('getPermissionLevelType', () => {
    it('应返回对应级别的 type 值', () => {
      expect(getPermissionLevelType('none')).toBe('info')
      expect(getPermissionLevelType('read')).toBe('')
      expect(getPermissionLevelType('write')).toBe('warning')
      expect(getPermissionLevelType('admin')).toBe('success')
      expect(getPermissionLevelType('manage')).toBe('success')
    })

    it('未知级别应返回空字符串', () => {
      expect(getPermissionLevelType('unknown')).toBe('')
      expect(getPermissionLevelType('')).toBe('')
      expect(getPermissionLevelType(undefined)).toBe('')
    })
  })

  describe('getPermissionLevelLabel', () => {
    it('应返回对应级别的中文标签', () => {
      expect(getPermissionLevelLabel('none')).toBe('无权限')
      expect(getPermissionLevelLabel('read')).toBe('只读')
      expect(getPermissionLevelLabel('write')).toBe('可编辑')
      expect(getPermissionLevelLabel('admin')).toBe('完全管理')
      expect(getPermissionLevelLabel('manage')).toBe('管理')
    })

    it('未知级别应原样返回 level 字符串', () => {
      expect(getPermissionLevelLabel('custom')).toBe('custom')
      expect(getPermissionLevelLabel('')).toBe('')
    })
  })

  describe('getResourceLabel', () => {
    it('应返回对应资源类型的中文标签', () => {
      expect(getResourceLabel('domain')).toBe('领域')
      expect(getResourceLabel('sub_domain')).toBe('子领域')
      expect(getResourceLabel('service_module')).toBe('服务模块')
      expect(getResourceLabel('business_object')).toBe('业务对象')
      expect(getResourceLabel('product')).toBe('产品')
    })

    it('未知资源类型应原样返回', () => {
      expect(getResourceLabel('unknown_type')).toBe('unknown_type')
    })
  })

  describe('getDimensionName', () => {
    const dimensions = [
      { code: 'product', name: '产品' },
      { code: 'domain', name: '领域' },
      { id: 'sub_domain', name: '子领域' },
    ]

    it('应通过 code 匹配返回维度中文名', () => {
      expect(getDimensionName(dimensions, 'product')).toBe('产品')
      expect(getDimensionName(dimensions, 'domain')).toBe('领域')
    })

    it('应通过 id 匹配返回维度中文名', () => {
      expect(getDimensionName(dimensions, 'sub_domain')).toBe('子领域')
    })

    it('无匹配时应降级到 getResourceLabel', () => {
      expect(getDimensionName(dimensions, 'version')).toBe('版本')
    })

    it('空维度列表时应降级到 getResourceLabel', () => {
      expect(getDimensionName([], 'domain')).toBe('领域')
    })
  })

  // ==================== API 函数 ====================

  describe('loadRoles', () => {
    it('应调用 GET /roles 并返回成功响应', async () => {
      const rolesData = [{ id: 1, name: 'admin' }, { id: 2, name: 'viewer' }]
      mocks.apiV1Get.mockResolvedValueOnce(okResp(rolesData))

      const result = await loadRoles()

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/roles', { params: {} })
      expect(result.success).toBe(true)
      expect(result.data).toEqual(rolesData)
    })

    it('响应无 success 字段时应包装为 { data } 返回', async () => {
      const rawResp = { data: [{ id: 1 }] }
      mocks.apiV1Get.mockResolvedValueOnce(rawResp)

      const result = await loadRoles()

      expect(result).toEqual({ data: [{ id: 1 }] })
    })

    it('应传递 params 参数', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp([]))

      await loadRoles({ page: 2, page_size: 10 })

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/roles', { params: { page: 2, page_size: 10 } })
    })
  })

  describe('loadRole', () => {
    it('应调用 GET /roles/:roleId', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp({ id: 1, name: 'admin' }))

      const result = await loadRole(1)

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/roles/1')
      expect(result.success).toBe(true)
    })
  })

  describe('loadDimensions', () => {
    it('应调用 GET /management-dimensions 并传递 params', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp([{ id: 1, code: 'product' }]))

      const result = await loadDimensions({ page: 1 })

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/management-dimensions', { params: { page: 1 } })
      expect(result.success).toBe(true)
    })
  })

  describe('loadPermissionRules', () => {
    it('应调用 GET /roles/:roleId/permission-rules', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp([{ id: 10, role_id: 1 }]))

      const result = await loadPermissionRules(1, { page: 1 })

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/roles/1/permission-rules', { params: { page: 1 } })
      expect(result.success).toBe(true)
    })
  })

  describe('savePermissionRules', () => {
    it('mode=create 时应调用 POST /roles/:roleId/permission-rules', async () => {
      const rule = { resource_type: 'domain', permission_level: 'read' }
      mocks.apiV1Post.mockResolvedValueOnce(okResp(rule))

      const result = await savePermissionRules(1, rule, 'create')

      expect(mocks.apiV1Post).toHaveBeenCalledWith('/roles/1/permission-rules', rule)
      expect(result.success).toBe(true)
    })

    it('mode=update 且有 rule.id 时应调用 PUT /roles/:roleId/permission-rules/:ruleId', async () => {
      const rule = { id: 10, resource_type: 'domain', permission_level: 'write' }
      mocks.apiV1Put.mockResolvedValueOnce(okResp(rule))

      const result = await savePermissionRules(1, rule, 'update')

      expect(mocks.apiV1Put).toHaveBeenCalledWith('/roles/1/permission-rules/10', rule)
      expect(result.success).toBe(true)
    })

    it('mode=batch 时应调用 POST /roles/:roleId/permission-rules/batch', async () => {
      const rules = [{ resource_type: 'domain' }, { resource_type: 'product' }]
      mocks.apiV1Post.mockResolvedValueOnce(okResp(rules))

      const result = await savePermissionRules(1, rules, 'batch')

      expect(mocks.apiV1Post).toHaveBeenCalledWith('/roles/1/permission-rules/batch', rules)
      expect(result.success).toBe(true)
    })

    it('默认 mode 为 create', async () => {
      const rule = { resource_type: 'domain' }
      mocks.apiV1Post.mockResolvedValueOnce(okResp(rule))

      await savePermissionRules(1, rule)

      expect(mocks.apiV1Post).toHaveBeenCalledWith('/roles/1/permission-rules', rule)
    })
  })

  describe('calculateImpact', () => {
    it('应调用 POST /roles/:roleId/calculate-impact', async () => {
      const rule = { resource_type: 'domain', permission_level: 'write' }
      mocks.apiV1Post.mockResolvedValueOnce(okResp({ affected_count: 5 }))

      const result = await calculateImpact(1, rule)

      expect(mocks.apiV1Post).toHaveBeenCalledWith('/roles/1/calculate-impact', rule)
      expect(result.success).toBe(true)
    })
  })

  describe('loadUnifiedPermissions', () => {
    it('应调用 GET /roles/:roleId/unified-permissions', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp({ menus: [], scopes: [] }))

      const result = await loadUnifiedPermissions(1)

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/roles/1/unified-permissions')
      expect(result.success).toBe(true)
    })
  })

  describe('searchUsers', () => {
    it('应调用 GET /users 并传递 keyword 和默认 page_size=20', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp([{ id: 1, username: 'alice' }]))

      const result = await searchUsers('alice')

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/users', {
        params: { keyword: 'alice', page_size: 20 },
      })
      expect(result.success).toBe(true)
    })

    it('应合并额外 params', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp([]))

      await searchUsers('bob', { page: 2 })

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/users', {
        params: { keyword: 'bob', page_size: 20, page: 2 },
      })
    })
  })
})
