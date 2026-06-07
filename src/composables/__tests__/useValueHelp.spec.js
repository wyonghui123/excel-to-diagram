/**
 * useValueHelp.spec.js - 值帮助 Composable 测试
 *
 * 测试核心功能：
 * 1. loadOptions - 加载选项
 * 2. loadOptionsDebounced - 防抖加载
 * 3. resolveDisplay - 解析显示值
 * 4. validateInput - 输入验证
 * 5. getFilterParams - 参数绑定解析
 * 6. isBindingSatisfied - 必填绑定检查
 * 7. sourceType/sourceId 计算
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

vi.mock('@/services/boService', () => ({
  default: {
    searchValueHelp: vi.fn(),
    resolveValueHelp: vi.fn(),
  }
}))

import boService from '@/services/boService'
import { useValueHelp } from '@/composables/useValueHelp'

describe('useValueHelp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const { optionsList, loading, error, displayValue, sourceType, sourceId } = useValueHelp({})
      expect(optionsList.value).toEqual([])
      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(displayValue.value).toBe('')
      expect(sourceType.value).toBe('enum')
      expect(sourceId.value).toBe('')
    })

    it('computes sourceType from config', () => {
      const { sourceType } = useValueHelp({
        source: { type: 'bo', target_bo: 'role' },
      })
      expect(sourceType.value).toBe('bo')
    })

    it('computes sourceId for enum type', () => {
      const { sourceId } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status_type' },
      })
      expect(sourceId.value).toBe('status_type')
    })

    it('computes sourceId for bo type', () => {
      const { sourceId } = useValueHelp({
        source: { type: 'bo', target_bo: 'role' },
      })
      expect(sourceId.value).toBe('role')
    })

    it('computes sourceId for custom type', () => {
      const { sourceId } = useValueHelp({
        source: { type: 'custom', endpoint: '/api/custom/values' },
      })
      expect(sourceId.value).toBe('/api/custom/values')
    })
  })

  describe('loadOptions', () => {
    it('loads options successfully', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: true,
        data: {
          data: [
            { value: 'active', label: 'Active' },
            { value: 'inactive', label: 'Inactive' },
          ],
        },
      })

      const { loadOptions, optionsList } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await loadOptions('act')

      expect(boService.searchValueHelp).toHaveBeenCalledWith('enum', 'status', expect.objectContaining({
        search: 'act',
      }))
      expect(optionsList.value).toHaveLength(2)
    })

    it('respects min_search_length', async () => {
      const { loadOptions } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
        behavior: { min_search_length: 3 },
      })

      await loadOptions('ab')

      expect(boService.searchValueHelp).not.toHaveBeenCalled()
    })

    it('skips when no sourceId', async () => {
      const { loadOptions } = useValueHelp({})

      await loadOptions('test')

      expect(boService.searchValueHelp).not.toHaveBeenCalled()
    })

    it('handles error response', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: false,
        message: 'Not found',
      })

      const { loadOptions, error } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await loadOptions()

      expect(error.value).toBe('Not found')
    })

    it('handles exception', async () => {
      boService.searchValueHelp.mockRejectedValue(new Error('Network error'))

      const { loadOptions, error } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await loadOptions()

      expect(error.value).toBe('Network error')
    })

    it('passes search_fields and sort', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: true,
        data: { data: [] },
      })

      const { loadOptions } = useValueHelp({
        source: { type: 'bo', target_bo: 'role' },
        behavior: { search_fields: ['name', 'code'] },
        presentation: { sort_by: [{ field: 'name', direction: 'asc' }] },
      })

      await loadOptions()

      expect(boService.searchValueHelp).toHaveBeenCalledWith('bo', 'role', expect.objectContaining({
        search_fields: 'name,code',
        sort: 'name:asc',
      }))
    })
  })

  describe('loadOptionsDebounced', () => {
    it('debounces loadOptions call', () => {
      const { loadOptionsDebounced } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      loadOptionsDebounced('test')
      loadOptionsDebounced('test2')

      expect(boService.searchValueHelp).not.toHaveBeenCalled()

      vi.advanceTimersByTime(300)

      expect(boService.searchValueHelp).toHaveBeenCalledTimes(1)
    })

    it('uses custom debounce time', () => {
      const { loadOptionsDebounced } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
        behavior: { debounce_ms: 500 },
      })

      loadOptionsDebounced('test')

      vi.advanceTimersByTime(300)
      expect(boService.searchValueHelp).not.toHaveBeenCalled()

      vi.advanceTimersByTime(200)
      expect(boService.searchValueHelp).toHaveBeenCalledTimes(1)
    })
  })

  describe('resolveDisplay', () => {
    it('resolves display value successfully', async () => {
      boService.resolveValueHelp.mockResolvedValue({
        success: true,
        data: { display: 'Active Status' },
      })

      const { resolveDisplay, displayValue } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await resolveDisplay('active')

      expect(displayValue.value).toBe('Active Status')
    })

    it('falls back to string value on failure', async () => {
      boService.resolveValueHelp.mockResolvedValue({
        success: false,
      })

      const { resolveDisplay, displayValue } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await resolveDisplay('active')

      expect(displayValue.value).toBe('active')
    })

    it('handles null/undefined value', async () => {
      const { resolveDisplay, displayValue } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await resolveDisplay(null)

      expect(displayValue.value).toBe('')
    })

    it('handles zero value', async () => {
      boService.resolveValueHelp.mockResolvedValue({
        success: true,
        data: { display: 'Zero' },
      })

      const { resolveDisplay, displayValue } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })

      await resolveDisplay(0)

      expect(displayValue.value).toBe('Zero')
    })

    it('falls back when no sourceId', async () => {
      const { resolveDisplay, displayValue } = useValueHelp({})

      await resolveDisplay('test')

      expect(displayValue.value).toBe('test')
    })
  })

  describe('validateInput', () => {
    it('returns true when no validation config', () => {
      const { validateInput } = useValueHelp({})
      expect(validateInput('anything')).toBe(true)
    })

    it('returns true when binding_strength is loose', () => {
      const { validateInput } = useValueHelp({
        behavior: { validation: true, binding_strength: 'loose' },
      })
      expect(validateInput('anything')).toBe(true)
    })

    it('returns true when options list is empty', () => {
      const { validateInput } = useValueHelp({
        behavior: { validation: true },
      })
      expect(validateInput('anything')).toBe(true)
    })

    it('validates against options list', () => {
      const { validateInput, optionsList } = useValueHelp({
        behavior: { validation: true },
      })
      optionsList.value = [
        { value: 'active', label: 'Active' },
        { value: 'inactive', label: 'Inactive' },
      ]

      expect(validateInput('active')).toBe(true)
      expect(validateInput('unknown')).toBe(false)
    })
  })

  describe('getFilterParams', () => {
    it('returns empty object when no bindings', () => {
      const { getFilterParams } = useValueHelp({})
      expect(getFilterParams()).toEqual({})
    })

    it('resolves constant bindings', () => {
      const { getFilterParams } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'category', constant: 'system' },
          ],
        },
      })

      expect(getFilterParams()).toEqual({ category: 'system' })
    })

    it('resolves local_field bindings', () => {
      const { getFilterParams } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'parent_id', local_field: 'group_id' },
          ],
        },
      })

      expect(getFilterParams({ group_id: 42 })).toEqual({ parent_id: 42 })
    })

    it('skips local_field binding when form value is undefined', () => {
      const { getFilterParams } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'parent_id', local_field: 'group_id' },
          ],
        },
      })

      expect(getFilterParams({})).toEqual({})
    })

    it('handles mixed bindings', () => {
      const { getFilterParams } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'category', constant: 'system' },
            { target_field: 'parent_id', local_field: 'group_id' },
          ],
        },
      })

      expect(getFilterParams({ group_id: 5 })).toEqual({
        category: 'system',
        parent_id: 5,
      })
    })
  })

  describe('isBindingSatisfied', () => {
    it('returns true when no bindings', () => {
      const { isBindingSatisfied } = useValueHelp({})
      expect(isBindingSatisfied()).toBe(true)
    })

    it('returns true when required binding has value', () => {
      const { isBindingSatisfied } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'parent_id', local_field: 'group_id', required: true },
          ],
        },
      })

      expect(isBindingSatisfied({ group_id: 5 })).toBe(true)
    })

    it('returns false when required binding is missing', () => {
      const { isBindingSatisfied } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'parent_id', local_field: 'group_id', required: true },
          ],
        },
      })

      expect(isBindingSatisfied({})).toBe(false)
    })

    it('returns true when required binding has constant', () => {
      const { isBindingSatisfied } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'category', constant: 'system', required: true },
          ],
        },
      })

      expect(isBindingSatisfied({})).toBe(true)
    })

    it('returns true for non-required bindings', () => {
      const { isBindingSatisfied } = useValueHelp({
        behavior: {
          parameter_bindings: [
            { target_field: 'parent_id', local_field: 'group_id', required: false },
          ],
        },
      })

      expect(isBindingSatisfied({})).toBe(true)
    })
  })
})
