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
  getActionLabel,
  getDimensionName,
  can,
  loadPermissionMeta,
  invalidatePermissionMetaCache,
  loadPermissionMetaWithScope,
  ScopeCodeInvalidError,
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
  apiV2Get: vi.fn(),
  apiV2Post: vi.fn(),
  apiV2Put: vi.fn(),
  apiV2Delete: vi.fn(),
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: mocks.apiV1Get,
    post: mocks.apiV1Post,
    put: mocks.apiV1Put,
    delete: mocks.apiV1Delete,
    patch: mocks.apiV1Patch,
  },
  apiV2: {
    get: mocks.apiV2Get,
    post: mocks.apiV2Post,
    put: mocks.apiV2Put,
    delete: mocks.apiV2Delete,
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
    mocks.apiV2Get.mockReset()
    mocks.apiV2Post.mockReset()
    mocks.apiV2Put.mockReset()
    mocks.apiV2Delete.mockReset()
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
      // [Spec 19 M2-8] 追加 audit_log / org / user 三行（委托授权），共 11 项
      expect(Object.keys(RESOURCE_LABELS)).toHaveLength(11)
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
    it('应调用 GET /bo/permission_set 并返回成功响应', async () => {
      const rolesData = [{ id: 1, name: 'admin' }, { id: 2, name: 'viewer' }]
      mocks.apiV2Get.mockResolvedValueOnce(okResp(rolesData))

      const result = await loadRoles()

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_set', { params: {} })
      expect(result.success).toBe(true)
      expect(result.data).toEqual(rolesData)
    })

    it('响应无 success 字段时应包装为 { data } 返回', async () => {
      const rawResp = { data: [{ id: 1 }] }
      mocks.apiV2Get.mockResolvedValueOnce(rawResp)

      const result = await loadRoles()

      expect(result).toEqual({ data: [{ id: 1 }] })
    })

    it('应传递 params 参数', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp([]))

      await loadRoles({ page: 2, page_size: 10 })

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_set', { params: { page: 2, page_size: 10 } })
    })
  })

  describe('loadRole', () => {
    it('应调用 GET /bo/permission_set/:roleId', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp({ id: 1, name: 'admin' }))

      const result = await loadRole(1)

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_set/1')
      expect(result.success).toBe(true)
    })
  })

  describe('loadDimensions', () => {
    it('应调用 GET /bo/permission_dimension 并传递 params', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp([{ id: 1, code: 'product' }]))

      const result = await loadDimensions({ page: 1 })

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_dimension', { params: { page: 1 } })
      expect(result.success).toBe(true)
    })
  })

  describe('loadPermissionRules', () => {
    it('应调用 GET /permission-rules 并传递 permission_set_id 参数', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp([{ id: 10, permission_set_id: 1 }]))

      const result = await loadPermissionRules(1, { page: 1 })

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/permission-rules', { params: { permission_set_id: 1, page: 1 } })
      expect(result.success).toBe(true)
      expect(result.data.rules[0].id).toBe(10)
    })

    it('data.items 分页格式应归一化为 data.rules', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp({ items: [{ id: 11 }] }))

      const result = await loadPermissionRules(1)

      expect(result.data.rules[0].id).toBe(11)
    })
  })

  describe('savePermissionRules', () => {
    it('mode=create 时应 POST /permission-rules 并注入 permission_set_id', async () => {
      const rule = { resource_type: 'domain', permission_level: 'read' }
      mocks.apiV2Post.mockResolvedValueOnce(okResp(rule))

      const result = await savePermissionRules(1, rule, 'create')

      expect(mocks.apiV2Post).toHaveBeenCalledWith('/permission-rules', { ...rule, permission_set_id: 1 })
      expect(result.success).toBe(true)
    })

    it('mode=update 且有 rule.id 时应 PUT /permission-rules/:ruleId', async () => {
      const rule = { id: 10, resource_type: 'domain', permission_level: 'write' }
      mocks.apiV2Put.mockResolvedValueOnce(okResp(rule))

      const result = await savePermissionRules(1, rule, 'update')

      expect(mocks.apiV2Put).toHaveBeenCalledWith('/permission-rules/10', { ...rule, permission_set_id: 1 })
      expect(result.success).toBe(true)
    })

    it('mode=batch 时应按 id 逐条 PUT / 无 id 逐条 POST', async () => {
      const rules = { rules: [{ id: 1, resource_type: 'domain' }, { resource_type: 'product' }] }
      mocks.apiV2Put.mockResolvedValueOnce(okResp({ id: 1 }))
      mocks.apiV2Post.mockResolvedValueOnce(okResp({ id: 2 }))

      const result = await savePermissionRules(1, rules, 'batch')

      expect(mocks.apiV2Put).toHaveBeenCalledWith('/permission-rules/1', { id: 1, resource_type: 'domain', permission_set_id: 1 })
      expect(mocks.apiV2Post).toHaveBeenCalledWith('/permission-rules', { resource_type: 'product', permission_set_id: 1 })
      expect(result.success).toBe(true)
    })

    it('默认 mode 为 create', async () => {
      const rule = { resource_type: 'domain' }
      mocks.apiV2Post.mockResolvedValueOnce(okResp(rule))

      await savePermissionRules(1, rule)

      expect(mocks.apiV2Post).toHaveBeenCalledWith('/permission-rules', { ...rule, permission_set_id: 1 })
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
    it('应调用 GET /permission-sets/:roleId/unified-permissions', async () => {
      mocks.apiV1Get.mockResolvedValueOnce(okResp({ menus: [], scopes: [] }))

      const result = await loadUnifiedPermissions(1)

      expect(mocks.apiV1Get).toHaveBeenCalledWith('/permission-sets/1/unified-permissions')
      expect(result.success).toBe(true)
    })
  })

  describe('searchUsers', () => {
    it('应调用 GET /bo/user 并传递 keyword 和默认 page_size=20', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp([{ id: 1, username: 'alice' }]))

      const result = await searchUsers('alice')

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/user', {
        params: { keyword: 'alice', page_size: 20 },
      })
      expect(result.success).toBe(true)
    })

    it('应合并额外 params', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp([]))

      await searchUsers('bob', { page: 2 })

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/user', {
        params: { keyword: 'bob', page_size: 20, page: 2 },
      })
    })
  })

  // ==================== P1-Base-03: 元数据缓存 /meta（D3 修复） ====================

  describe('loadPermissionMeta（P1-Base-03）', () => {
    beforeEach(() => {
      invalidatePermissionMetaCache()
      mocks.apiV2Get.mockReset()
    })

    it('API 成功时返回 meta 且标签函数 metaCache 优先', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp({
        resource_type_labels: { domain: '领域X' },
        action_labels: { create: '新建' },
        permission_level_labels: { read: { label: '只读X' } },
      }))

      const meta = await loadPermissionMeta()

      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_dimension/meta')
      expect(meta.resource_type_labels.domain).toBe('领域X')
      // metaCache 优先于常量 fallback
      expect(getResourceLabel('domain')).toBe('领域X')
      expect(getActionLabel('create')).toBe('新建')
      expect(getPermissionLevelLabel('read')).toBe('只读X')
    })

    it('API 异常时返回 null，标签走常量 fallback 不白屏', async () => {
      mocks.apiV2Get.mockRejectedValueOnce(new Error('network down'))

      const meta = await loadPermissionMeta()

      expect(meta).toBeNull()
      expect(getResourceLabel('domain')).toBe('领域')
      expect(getActionLabel('create')).toBe('创建')
      expect(getPermissionLevelLabel('read')).toBe('只读')
    })

    it('响应 success=false 时返回 null', async () => {
      mocks.apiV2Get.mockResolvedValueOnce({ success: false, message: 'err' })

      const meta = await loadPermissionMeta()

      expect(meta).toBeNull()
    })

    it('invalidatePermissionMetaCache 清除缓存后重新请求', async () => {
      mocks.apiV2Get.mockResolvedValue(okResp({ resource_type_labels: { domain: '领域A' } }))

      await loadPermissionMeta()
      expect(mocks.apiV2Get).toHaveBeenCalledTimes(1)

      invalidatePermissionMetaCache()
      await loadPermissionMeta()
      expect(mocks.apiV2Get).toHaveBeenCalledTimes(2)
    })
  })

  describe('loadPermissionMetaWithScope（P1-Base-03 scopeCode 铁律）', () => {
    beforeEach(() => {
      mocks.apiV2Get.mockReset()
    })

    it('SCOPE_CODE_INVALID 时抛 ScopeCodeInvalidError 并带 available_scope_codes', async () => {
      mocks.apiV2Get.mockResolvedValueOnce({
        success: false,
        error: 'SCOPE_CODE_INVALID',
        message: '范围编码（scope_code）无效',
        available_scope_codes: ['SCP'],
      })

      await expect(
        loadPermissionMetaWithScope({ scope_code: 'XXX' })
      ).rejects.toMatchObject({
        name: 'ScopeCodeInvalidError',
        availableScopeCodes: ['SCP'],
      })
    })

    it('成功时原样返回响应', async () => {
      mocks.apiV2Get.mockResolvedValueOnce(okResp({}))

      const r = await loadPermissionMetaWithScope({ scope_code: 'SCP' })

      expect(r.success).toBe(true)
      expect(mocks.apiV2Get).toHaveBeenCalledWith('/bo/permission_dimension/meta', {
        params: { scope_code: 'SCP' },
      })
    })
  })

  // ==================== FR-009 权限判定统一入口 ====================

  describe('can（权限判定统一入口）', () => {
    // 极简 store 替身：避免单测里依赖 pinia / authStore
    function makeStore(granted = []) {
      return {
        hasPermission: vi.fn(code => granted.includes(code)),
      }
    }

    it('无任何权限码时默认放行', () => {
      const store = makeStore()
      expect(can(null, { authStore: store })).toBe(true)
      expect(can(undefined, {})).toBe(true)
      expect(store.hasPermission).not.toHaveBeenCalled()
    })

    it('无 authStore 时降级放行（兼容单测 / 非 setup 上下文）', () => {
      expect(can('export', { objectType: 'product' })).toBe(true)
      expect(can('export', { objectType: 'product', authStore: null })).toBe(true)
    })

    it('由 objectType + action 派生权限码', () => {
      const store = makeStore(['product:export'])

      expect(can('export', { objectType: 'product', authStore: store })).toBe(true)
      expect(store.hasPermission).toHaveBeenCalledWith('product:export')
    })

    it('action 原样使用，不做别名归一（read 不会变成 view）', () => {
      const store = makeStore(['product:view'])

      expect(can('read', { objectType: 'product', authStore: store })).toBe(false)
      expect(store.hasPermission).toHaveBeenCalledWith('product:read')
    })

    it('显式 permission 字符串优先于 objectType 派生', () => {
      const store = makeStore(['user:delete'])

      expect(can('export', { permission: 'user:delete', objectType: 'product', authStore: store })).toBe(true)
      expect(store.hasPermission).toHaveBeenCalledWith('user:delete')
      expect(store.hasPermission).not.toHaveBeenCalledWith('product:export')
    })

    it('permission 数组默认 any（任意一项满足即放行）', () => {
      const store = makeStore(['user:export'])

      expect(can(null, { permission: ['user:import', 'user:export'], authStore: store })).toBe(true)
      expect(store.hasPermission).toHaveBeenCalledTimes(2)
    })

    it('mode=all 时要求全部满足', () => {
      const store = makeStore(['user:import'])

      expect(can(null, { permission: ['user:import', 'user:export'], mode: 'all', authStore: store })).toBe(false)
      expect(store.hasPermission).toHaveBeenCalledTimes(2)
    })

    it('permission 为空数组时回退 objectType 派生', () => {
      const store = makeStore(['product:export'])

      expect(can('export', { permission: [], objectType: 'product', authStore: store })).toBe(true)
      expect(store.hasPermission).toHaveBeenCalledWith('product:export')
    })
  })
})
