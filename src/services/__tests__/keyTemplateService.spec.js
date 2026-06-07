/**
 * keyTemplateService.spec.js - 键模板推导 service 单测
 *
 * 覆盖矩阵（15 个用例）：
 * 1. extractParentParams: 仅有 filterValues
 * 2. extractParentParams: 仅有 newRow
 * 3. extractParentParams: 合并 + 不覆盖
 * 4. extractParentParams: 跳过 Vue 内部
 * 5. extractParentParams: 跳过 _ 开头
 * 6. extractParentParams: 跳过 id
 * 7. hasInvalidParentId: 'new'
 * 8. hasInvalidParentId: ''
 * 9. hasInvalidParentId: null
 * 10. hasInvalidParentId: undefined
 * 11. hasInvalidParentId: 正常
 * 12. applyKeyTemplateSuggestion: 有 drafts
 * 13. applyKeyTemplateSuggestion: 无 drafts
 * 14. suggestKeyTemplateCode: 完整流程
 * 15. suggestKeyTemplateCode: 失败处理
 */

import { describe, it, expect, vi } from 'vitest'
import {
  extractParentParams,
  hasInvalidParentId,
  applyKeyTemplateSuggestion,
  suggestKeyTemplateCode,
} from '@/services/keyTemplateService'

describe('keyTemplateService', () => {
  describe('extractParentParams', () => {
    it('TC-1: 仅有 filterValues', () => {
      const result = extractParentParams({ user_id: 1 }, {}, () => false)
      expect(result).toEqual({ user_id: 1 })
    })

    it('TC-2: 仅有 newRow', () => {
      const result = extractParentParams({}, { order_id: 5 }, () => false)
      expect(result).toEqual({ order_id: 5 })
    })

    it('TC-3: 合并 + 不覆盖（filterValues 优先）', () => {
      const result = extractParentParams(
        { user_id: 1 },
        { user_id: 999, order_id: 5 },
        () => false
      )
      expect(result).toEqual({ user_id: 1, order_id: 5 })
    })

    it('TC-4: 跳过 Vue 内部 prop', () => {
      const isVueInternal = (key) => key.startsWith('$') || key.startsWith('_')
      const result = extractParentParams({ $el: 1, _v: 2, user_id: 3 }, {}, isVueInternal)
      expect(result).toEqual({ user_id: 3 })
    })

    it('TC-5: newRow 跳过 _ 开头', () => {
      const result = extractParentParams({}, { _id: 1, _foo: 'x' }, () => false)
      expect(result).toEqual({})
    })

    it('TC-6: 跳过 id 字段', () => {
      const result = extractParentParams({ id: 1, user_id: 2 }, {}, () => false)
      expect(result).toEqual({ user_id: 2 })
    })
  })

  describe('hasInvalidParentId', () => {
    it('TC-7: "new" 无效', () => {
      expect(hasInvalidParentId({ user_id: 'new' })).toBe(true)
    })

    it('TC-8: "" 无效', () => {
      expect(hasInvalidParentId({ user_id: '' })).toBe(true)
    })

    it('TC-9: null 无效', () => {
      expect(hasInvalidParentId({ user_id: null })).toBe(true)
    })

    it('TC-10: undefined 无效', () => {
      expect(hasInvalidParentId({ user_id: undefined })).toBe(true)
    })

    it('TC-11: 正常数字有效', () => {
      expect(hasInvalidParentId({ user_id: 1 })).toBe(false)
    })
  })

  describe('applyKeyTemplateSuggestion', () => {
    it('TC-12: 有 draftValues 时返回 shouldUpdateDraft=true', () => {
      const newRow = { id: 1 }
      const drafts = new Map([[1, { name: 'x' }]])
      const result = applyKeyTemplateSuggestion(newRow, 'NEW_CODE', drafts)
      expect(newRow.code).toBe('NEW_CODE')
      expect(newRow._initialValues.code).toBe('NEW_CODE')
      expect(drafts.get(1).code).toBe('NEW_CODE')
      expect(result.shouldUpdateDraft).toBe(true)
    })

    it('TC-13: 无 draftValues 时返回 shouldUpdateDraft=false', () => {
      const newRow = { id: 1 }
      const drafts = new Map()
      const result = applyKeyTemplateSuggestion(newRow, 'NEW_CODE', drafts)
      expect(newRow.code).toBe('NEW_CODE')
      expect(result.shouldUpdateDraft).toBe(false)
    })
  })

  describe('suggestKeyTemplateCode (主入口)', () => {
    it('TC-14: 完整成功流程', async () => {
      const newRow = { id: 1, user_id: 5, _objectType: 'order' }
      const filterValues = { user_id: 5 }
      const draftValues = new Map()
      const boService = {
        suggestKeyTemplateCode: vi.fn().mockResolvedValue({
          success: true,
          data: { code: 'AUTO_CODE_001' },
        }),
      }
      const config = { debug: false }
      const isVueInternalProp = () => false

      const result = await suggestKeyTemplateCode(
        newRow, filterValues, draftValues, boService, config, isVueInternalProp
      )
      expect(result.success).toBe(true)
      expect(result.code).toBe('AUTO_CODE_001')
      expect(boService.suggestKeyTemplateCode).toHaveBeenCalledWith('order', {}, { user_id: 5 })
    })

    it('TC-15: 失败时返回 error', async () => {
      const newRow = { id: 1, user_id: 5, _objectType: 'order' }
      const boService = {
        suggestKeyTemplateCode: vi.fn().mockRejectedValue(new Error('Network error')),
      }
      const config = { debug: false }
      const result = await suggestKeyTemplateCode(
        newRow, { user_id: 5 }, new Map(), boService, config, () => false
      )
      expect(result.success).toBe(false)
      expect(result.error).toBeInstanceOf(Error)
      expect(result.error.message).toBe('Network error')
    })

    // === P3-Branch: 覆盖率补强（Branch 80.76% → 90%） ===

    it('TC-16 (Branch L49): filterValues=null + newRow=null 时跳过（no_parent）', async () => {
      // branch: Object.keys(filterValues || {}) + Object.keys(newRow || {}) 兜底分支
      const boService = {
        suggestKeyTemplateCode: vi.fn(),
      }
      const result = await suggestKeyTemplateCode(
        null, null, new Map(), boService, {}, () => false
      )
      // filterValues=null + newRow=null → parentParams={} → skipped='no_parent'
      expect(result.skipped).toBe('no_parent')
      expect(boService.suggestKeyTemplateCode).not.toHaveBeenCalled()
    })

    it('TC-17 (Branch L162): 后端 success=true 但 data.code 为空时 skipped=no_code', async () => {
      // branch: return { success: false, skipped: 'no_code' }
      const newRow = { id: 1, user_id: 5, _objectType: 'order' }
      const boService = {
        suggestKeyTemplateCode: vi.fn().mockResolvedValue({ success: true, data: {} }),
      }
      const result = await suggestKeyTemplateCode(
        newRow, { user_id: 5 }, new Map(), boService, {}, () => false
      )
      expect(result.success).toBe(false)
      expect(result.skipped).toBe('no_code')
    })

    it('TC-18 (Branch L164-166): debug=true + 抛错时 console.warn 被调用', async () => {
      // branch: if (config.debug) { console.warn(...) }
      const newRow = { id: 1, user_id: 5, _objectType: 'order' }
      const boService = {
        suggestKeyTemplateCode: vi.fn().mockRejectedValue(new Error('Network error')),
      }
      const config = { debug: true }
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const result = await suggestKeyTemplateCode(
        newRow, { user_id: 5 }, new Map(), boService, config, () => false
      )
      expect(result.success).toBe(false)
      expect(consoleWarnSpy).toHaveBeenCalled()
      expect(consoleWarnSpy.mock.calls[0][0]).toContain('keyTemplateService')
      consoleWarnSpy.mockRestore()
    })
  })
})
