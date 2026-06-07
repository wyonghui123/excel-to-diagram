/**
 * archDataConverter 单元测试
 * 目标覆盖率: 95%+
 * 测试迁移到 architecture/preview API 后的行为
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  buildPreviewDataFromArchData,
  convertToCenterScope,
  convertToRelationNodeIds
} from '../archDataConverter.js'

// Mock httpClient.apiV2
const mockApiV2Get = vi.fn()
vi.mock('@/utils/httpClient', () => ({
  apiV2: {
    get: (...args) => mockApiV2Get(...args)
  }
}))

function makePreviewResponse(overrides = {}) {
  return {
    success: true,
    data: {
      domains: overrides.domains || [],
      sub_domains: overrides.sub_domains || [],
      service_modules: overrides.service_modules || [],
      business_objects: overrides.business_objects || [],
      relationships: overrides.relationships || [],
      center_scope: overrides.center_scope || []
    }
  }
}

describe('archDataConverter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockApiV2Get.mockReset()
    mockApiV2Get.mockResolvedValue(makePreviewResponse())
  })

  describe('buildPreviewDataFromArchData', () => {
    it('应该调用 architecture/preview API', async () => {
      await buildPreviewDataFromArchData(null, 1, {})
      expect(mockApiV2Get).toHaveBeenCalledTimes(1)
      const url = mockApiV2Get.mock.calls[0][0]
      expect(url).toContain('/bo/architecture/preview')
      expect(url).toContain('version_id=1')
    })

    it('应该返回完整的架构数据结构', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse({
        domains: [{ id: 1, name: 'Domain1', code: 'D1' }],
        sub_domains: [{ id: 10, name: 'SD1', code: 'SD1', domain_id: 1 }],
        service_modules: [{ id: 100, name: 'SM1', code: 'SM1', sub_domain_id: 10 }],
        business_objects: [{ id: 1000, name: 'BO1', code: 'BO1', service_module_id: 100, domain_id: 1, sub_domain_id: 10, domain_name: 'Domain1', sub_domain_name: 'SD1', service_module_name: 'SM1' }],
        relationships: [{ id: 5000, source_code: 'BO1', target_code: 'BO2', relation_code: 'REL1', scope_type: 'internal', category_type: 'cross-domain' }],
        center_scope: ['BO1']
      }))

      const result = await buildPreviewDataFromArchData(null, 1, {})
      expect(result).toHaveProperty('domainProducts')
      expect(result).toHaveProperty('businessObjects')
      expect(result).toHaveProperty('serviceModules')
      expect(result).toHaveProperty('allDomainProducts')
      expect(result).toHaveProperty('allBusinessObjects')
      expect(result).toHaveProperty('allServiceModules')
      expect(result).toHaveProperty('relationships')
      expect(result).toHaveProperty('centerScope')
      expect(result.centerScope).toEqual(['BO1'])
    })

    it('应该保留后端返回的 scopeType 和 categoryType', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse({
        relationships: [{
          id: 1,
          source_code: 'A',
          target_code: 'B',
          relation_code: 'R1',
          scope_type: 'internal',
          category_type: 'cross-domain'
        }]
      }))

      const result = await buildPreviewDataFromArchData(null, 1, {})
      expect(result.relationships[0].scopeType).toBe('internal')
      expect(result.relationships[0].categoryType).toBe('cross-domain')
    })

    it('应该传递 hierarchyFilter 参数', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse())
      await buildPreviewDataFromArchData(null, 1, { domain_id: [1, 2] })
      const url = mockApiV2Get.mock.calls[0][0]
      expect(url).toContain('domain_ids=1%2C2')
    })

    it('API 失败应该抛出错误', async () => {
      mockApiV2Get.mockResolvedValue({ success: false, message: 'Server error' })
      await expect(buildPreviewDataFromArchData(null, 1, {})).rejects.toThrow('Server error')
    })

    it('空层级过滤应该返回空数组', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse())
      const result = await buildPreviewDataFromArchData(null, 1, {})
      expect(Array.isArray(result.domainProducts)).toBe(true)
      expect(Array.isArray(result.businessObjects)).toBe(true)
      expect(Array.isArray(result.serviceModules)).toBe(true)
    })
  })

  describe('convertToCenterScope', () => {
    it('应该调用 architecture/preview API 并返回 center_scope', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse({
        center_scope: ['BO1', 'BO2']
      }))
      const result = await convertToCenterScope(null, 1, {})
      expect(result).toEqual(['BO1', 'BO2'])
    })

    it('空 center_scope 应该返回空数组', async () => {
      mockApiV2Get.mockResolvedValue(makePreviewResponse())
      const result = await convertToCenterScope(null, 1, {})
      expect(result).toEqual([])
    })
  })

  describe('convertToRelationNodeIds', () => {
    it('空输入应该返回空数组', () => {
      expect(convertToRelationNodeIds(null)).toEqual([])
      expect(convertToRelationNodeIds([])).toEqual([])
      expect(convertToRelationNodeIds(undefined)).toEqual([])
    })

    it('字符串数组应该直接返回', () => {
      const filter = ['node1', 'node2']
      const result = convertToRelationNodeIds(filter)
      expect(result).toEqual(['node1', 'node2'])
    })

    it('对象数组应该提取 id', () => {
      const filter = [{ id: 'node1' }, { id: 'node2' }]
      const result = convertToRelationNodeIds(filter)
      expect(result).toEqual(['node1', 'node2'])
    })

    it('scopeType + categoryType 对象应该生成组合ID', () => {
      const filter = [{
        scopeType: 'domain',
        categoryType: 'product',
        level: 1,
        name: 'test'
      }]
      const result = convertToRelationNodeIds(filter)
      expect(result).toEqual(['domain-product-1-test'])
    })

    it('scopeType + categoryType 无 level 应该生成简化ID', () => {
      const filter = [{
        scopeType: 'domain',
        categoryType: 'product'
      }]
      const result = convertToRelationNodeIds(filter)
      expect(result).toEqual(['domain-product'])
    })

    it('应该去重', () => {
      const filter = ['node1', 'node1', 'node2']
      const result = convertToRelationNodeIds(filter)
      expect(result).toEqual(['node1', 'node2'])
    })

    it('混合类型输入应该正确处理', () => {
      const filter = [
        'string-node',
        { id: 'object-node' },
        { scopeType: 'type', categoryType: 'cat', level: 1, name: 'mixed' }
      ]
      const result = convertToRelationNodeIds(filter)
      expect(result).toContain('string-node')
      expect(result).toContain('object-node')
      expect(result).toContain('type-cat-1-mixed')
    })
  })
})
