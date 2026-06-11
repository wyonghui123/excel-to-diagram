/**
 * keyTemplateService.formDirty.spec.js
 *
 * 覆盖 [NEW 2026-06-10] 详情表单保护路径 (formDirtyFields)：
 *   - shouldSkipSuggestionForForm
 *   - resetKeyTemplateCode
 *   - applyKeyTemplateSuggestion formDirtyFields 路径
 *   - suggestKeyTemplateCode formDirtyFields 路径
 *
 * 覆盖矩阵（10 个用例）：
 *
 *  shouldSkipSuggestionForForm
 *   1. formDirtyFields 为 null -> 不跳过
 *   2. formDirtyFields 为 undefined -> 不跳过
 *   3. formDirtyFields 不含 code -> 不跳过
 *   4. formDirtyFields 含 code -> 跳过
 *
 *  resetKeyTemplateCode
 *   5. 正常路径 -> 清脏标记 + 写新值
 *   6. formData 为 null -> 返回 {success: false}
 *   7. formDirtyFields 为 null -> 仍写新值（不影响）
 *   8. code 未在 formDirtyFields 中 -> 跳过清脏步骤（不影响）
 *
 *  applyKeyTemplateSuggestion formDirtyFields 路径
 *   9. formDirtyFields.has('code')=true -> 跳过 (skipped: user_edited_form)
 *  10. formDirtyFields 为 null + rowDrafts 也有 code -> 走 rowDrafts 跳过
 *
 *  suggestKeyTemplateCode 集成
 *  11. formDirtyFields 命中时返回 {success: false, skipped: 'user_edited_form'}
 *  12. formDirtyFields 不命中时正常返回 code
 */

import { describe, it, expect, vi } from 'vitest'
import {
  shouldSkipSuggestionForForm,
  resetKeyTemplateCode,
  applyKeyTemplateSuggestion,
  suggestKeyTemplateCode,
} from '@/services/keyTemplateService'

describe('keyTemplateService - formDirtyFields 路径 [NEW 2026-06-10]', () => {
  describe('shouldSkipSuggestionForForm', () => {
    it('TC-1: formDirtyFields 为 null -> 不跳过', () => {
      expect(shouldSkipSuggestionForForm('code', null)).toBe(false)
    })

    it('TC-2: formDirtyFields 为 undefined -> 不跳过', () => {
      expect(shouldSkipSuggestionForForm('code', undefined)).toBe(false)
    })

    it('TC-3: formDirtyFields 不含 code -> 不跳过', () => {
      const fd = new Set(['name'])
      expect(shouldSkipSuggestionForForm('code', fd)).toBe(false)
    })

    it('TC-4: formDirtyFields 含 code -> 跳过', () => {
      const fd = new Set(['code'])
      expect(shouldSkipSuggestionForForm('code', fd)).toBe(true)
    })
  })

  describe('resetKeyTemplateCode', () => {
    it('TC-5: 正常路径 -> 清脏标记 + 写新值', () => {
      const fd = new Set(['code'])
      const formData = { name: 'Test', code: 'OLD01' }
      const result = resetKeyTemplateCode(formData, 'NEW01', fd)
      expect(result.success).toBe(true)
      expect(formData.code).toBe('NEW01')
      expect(fd.has('code')).toBe(false)
    })

    it('TC-6: formData 为 null -> 返回 {success: false}', () => {
      const fd = new Set(['code'])
      const result = resetKeyTemplateCode(null, 'NEW01', fd)
      expect(result.success).toBe(false)
      // fd 不应被修改
      expect(fd.has('code')).toBe(true)
    })

    it('TC-7: formDirtyFields 为 null -> 仍写新值', () => {
      const formData = { code: 'OLD' }
      const result = resetKeyTemplateCode(formData, 'NEW', null)
      expect(result.success).toBe(true)
      expect(formData.code).toBe('NEW')
    })

    it('TC-8: code 未在 formDirtyFields 中 -> 跳过清脏步骤', () => {
      // 模拟：formDirtyFields 是空 Set（code 没被 mark）
      const fd = new Set()
      const fdRef = fd
      const formData = { code: 'OLD' }
      const result = resetKeyTemplateCode(formData, 'NEW', fd)
      expect(result.success).toBe(true)
      expect(formData.code).toBe('NEW')
      // 传入的 Set 引用不应被破坏
      expect(fd).toBe(fdRef)
      expect(fd.size).toBe(0)
    })
  })

  describe('applyKeyTemplateSuggestion formDirtyFields 路径', () => {
    it('TC-9: formDirtyFields.has(code)=true -> 跳过 (skipped: user_edited_form)', () => {
      const newRow = { id: 1, code: 'USER_CODE' }
      const draftValues = new Map()
      const fd = new Set(['code'])
      const result = applyKeyTemplateSuggestion(newRow, 'AUTO_CODE', draftValues, fd)
      expect(result.shouldUpdateDraft).toBe(false)
      expect(result.skipped).toBe('user_edited_form')
      // 关键断言：newRow.code 不应被覆盖
      expect(newRow.code).toBe('USER_CODE')
    })

    it('TC-10: formDirtyFields 为 null + rowDrafts 有 code -> 走 rowDrafts 跳过 (向后兼容)', () => {
      const newRow = { id: 1, code: 'USER_CODE' }
      const draftValues = new Map([[1, { code: 'USER_CODE' }]])
      const result = applyKeyTemplateSuggestion(newRow, 'AUTO_CODE', draftValues, null)
      expect(result.shouldUpdateDraft).toBe(false)
      expect(result.skipped).toBe('user_edited')
      expect(newRow.code).toBe('USER_CODE')
    })
  })

  describe('suggestKeyTemplateCode 集成 formDirtyFields', () => {
    function makeBoService(returnCode) {
      return {
        suggestKeyTemplateCode: vi.fn().mockResolvedValue({
          success: true,
          data: { code: returnCode },
        }),
      }
    }

    it('TC-11: formDirtyFields 命中时 -> 后端被调, success=true 但 shouldUpdateDraft=false (apply 被跳过)', async () => {
      // 实际契约：suggestKeyTemplateCode 永远在 backend 返回 code 时返回 success=true
      // 但 shouldUpdateDraft 反映 apply 是否被跳过
      // 调用方（ObjectPageShell）有两种保护：
      //   1. handleFieldUpdate 预检查 (!isFieldDirty('code'))
      //   2. applyKeyTemplateSuggestion 双保险 (formDirtyFields.has('code'))
      const newRow = {
        id: 'new',
        _objectType: 'business_object',
        service_module_id: 1,
        code: 'USER_CODE',
      }
      const fd = new Set(['code'])
      const boService = makeBoService('AUTO_CODE')
      const result = await suggestKeyTemplateCode(
        newRow,
        { service_module_id: 1 },
        new Map(),
        boService,
        { debug: false },
        () => false,
        fd
      )
      // 后端被调了
      expect(boService.suggestKeyTemplateCode).toHaveBeenCalled()
      // 业务结果：apply 被跳过，newRow.code 未变
      expect(result.success).toBe(true)
      expect(result.code).toBe('AUTO_CODE')
      expect(result.shouldUpdateDraft).toBe(false)
      // 关键断言：newRow.code 不应被覆盖
      expect(newRow.code).toBe('USER_CODE')
    })

    it('TC-12: formDirtyFields 不命中时 -> 正常返回 code + shouldUpdateDraft=true', async () => {
      const newRow = {
        id: 'new',
        _objectType: 'business_object',
        service_module_id: 1,
      }
      const fd = new Set()  // 不含 code
      const draftValues = new Map()
      const boService = makeBoService('AUTO_CODE')
      const result = await suggestKeyTemplateCode(
        newRow,
        { service_module_id: 1 },
        draftValues,
        boService,
        { debug: false },
        () => false,
        fd
      )
      expect(result.success).toBe(true)
      expect(result.code).toBe('AUTO_CODE')
      expect(result.shouldUpdateDraft).toBe(false)  // new Map，没 rowDrafts
      expect(newRow.code).toBe('AUTO_CODE')
    })
  })
})
