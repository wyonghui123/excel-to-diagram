/**
 * detailPathResolver 单元测试（FR-007）
 *
 * 覆盖：显式 detail_path 优先、metaConfig.list.detail_path、默认规则、id 拼接。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/metaService', () => ({
  default: {
    getViewConfigSync: vi.fn()
  }
}))

import metaService from '@/services/metaService'
import { resolveDetailBasePath, resolveDetailPath } from '../detailPathResolver'

describe('detailPathResolver', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('resolveDetailBasePath', () => {
    it('优先使用显式传入的 detail_path', () => {
      metaService.getViewConfigSync.mockReturnValue({
        data: { list: { detail_path: '/detail/configured' } }
      })

      expect(resolveDetailBasePath('product', { detailPath: '/custom/product' }))
        .toBe('/custom/product')
    })

    it('使用 metaConfig.list.detail_path', () => {
      metaService.getViewConfigSync.mockReturnValue({
        data: { list: { detail_path: '/detail/product' } }
      })

      expect(resolveDetailBasePath('product')).toBe('/detail/product')
      expect(metaService.getViewConfigSync).toHaveBeenCalledWith('product')
    })

    it('未配置 detail_path 时回退默认规则', () => {
      metaService.getViewConfigSync.mockReturnValue({ data: { list: {} } })

      expect(resolveDetailBasePath('business_object')).toBe('/detail/business_object')
    })

    it('元数据缓存缺失时回退默认规则', () => {
      metaService.getViewConfigSync.mockReturnValue(undefined)

      expect(resolveDetailBasePath('user')).toBe('/detail/user')
    })
  })

  describe('resolveDetailPath', () => {
    it('拼接 id 生成完整详情路径', () => {
      metaService.getViewConfigSync.mockReturnValue({
        data: { list: { detail_path: '/detail/product' } }
      })

      expect(resolveDetailPath('product', 42)).toBe('/detail/product/42')
    })

    it('无 id 时返回基础路径（新建模式）', () => {
      expect(resolveDetailPath('product')).toBe('/detail/product')
      expect(resolveDetailPath('product', null)).toBe('/detail/product')
      expect(resolveDetailPath('product', '')).toBe('/detail/product')
    })
  })
})
