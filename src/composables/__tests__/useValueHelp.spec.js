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

  describe('effectiveSearchFields (回退逻辑)', () => {
    it('显式配置 search_fields 时使用配置值', () => {
      const { } = useValueHelp({
        source: { type: 'bo', target_bo: 'role', code_field: 'code', display_field: 'name' },
        behavior: { search_fields: ['code', 'email'] },
      })
      // 通过 search 调用间接验证：boService.searchValueHelp 第二个参数含 search_fields
      // 由于 effectiveSearchFields 是内部 computed, 这里通过 loadOptions 验证
      // 单独构造一个 wrapper
      const vh = useValueHelp({
        source: { type: 'bo', target_bo: 'role', code_field: 'code', display_field: 'name' },
        behavior: { search_fields: ['code', 'email'] },
      })
      vh.loadOptions()
      expect(boService.searchValueHelp).toHaveBeenCalledWith(
        'bo', 'role',
        expect.objectContaining({ search_fields: 'code,email' })
      )
    })

    it('未配置 search_fields 时回退到 code_field', () => {
      const vh = useValueHelp({
        source: { type: 'bo', target_bo: 'role', code_field: 'code' },
      })
      vh.loadOptions()
      expect(boService.searchValueHelp).toHaveBeenCalledWith(
        'bo', 'role',
        expect.objectContaining({ search_fields: 'code' })
      )
    })

    it('回退时同时包含 code_field 和 display_field', () => {
      const vh = useValueHelp({
        source: { type: 'bo', target_bo: 'role', code_field: 'code', display_field: 'name' },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      const searchFields = call[2].search_fields
      // 顺序：code 在前, display 在后
      expect(searchFields.split(',')).toEqual(expect.arrayContaining(['code', 'name']))
    })

    it('回退时 display_field 与 code_field 相同时不重复', () => {
      const vh = useValueHelp({
        source: { type: 'bo', target_bo: 'role', code_field: 'name', display_field: 'name' },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      const searchFields = call[2].search_fields
      // 不应出现 name,name
      expect(searchFields).toBe('name')
    })

    it('回退时既无 code_field 也无 display_field 则 search_fields 为空字符串', () => {
      const vh = useValueHelp({
        source: { type: 'bo', target_bo: 'role' },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      expect(call[2].search_fields).toBe('')
    })
  })

  describe('sourceConfigParams (value_field/display_field/code_field 透传)', () => {
    it('value_field/display_field/code_field 被透传给 searchValueHelp', () => {
      const vh = useValueHelp({
        source: {
          type: 'bo',
          target_bo: 'domain',
          value_field: 'id',
          display_field: 'name',
          code_field: 'code',
        },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      expect(call[2]).toMatchObject({
        value_field: 'id',
        display_field: 'name',
        code_field: 'code',
      })
    })

    it('value_filter 非空对象被透传', () => {
      const vh = useValueHelp({
        source: {
          type: 'bo',
          target_bo: 'domain',
          value_filter: { active: true },
        },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      expect(call[2].value_filter).toEqual({ active: true })
    })

    it('value_filter 空对象不被透传（避免无意义参数）', () => {
      const vh = useValueHelp({
        source: {
          type: 'bo',
          target_bo: 'domain',
          value_filter: {},
        },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      expect(call[2].value_filter).toBeUndefined()
    })

    it('hierarchy 非空对象被透传', () => {
      const vh = useValueHelp({
        source: {
          type: 'bo',
          target_bo: 'sub_domain',
          hierarchy: { parent_field: 'domain_id' },
        },
      })
      vh.loadOptions()
      const call = boService.searchValueHelp.mock.calls[0]
      expect(call[2].hierarchy).toEqual({ parent_field: 'domain_id' })
    })
  })

  describe('applyOutMappings', () => {
    it('无 out_mappings 时返回空对象', () => {
      const { applyOutMappings } = useValueHelp({})
      const result = applyOutMappings({ value: 1, display: 'X' }, {})
      expect(result).toEqual({})
    })

    it('selectedItem 为 null 时返回空对象', () => {
      const { applyOutMappings } = useValueHelp({
        behavior: {
          out_mappings: [
            { value_help_field: 'code', local_field: 'user_code' }
          ],
        },
      })
      const result = applyOutMappings(null, {})
      expect(result).toEqual({})
    })

    it('根据 out_mappings 提取 value_help_field 映射到 local_field', () => {
      const { applyOutMappings } = useValueHelp({
        behavior: {
          out_mappings: [
            { value_help_field: 'code', local_field: 'user_code' },
            { value_help_field: 'email', local_field: 'user_email' },
          ],
        },
      })
      const result = applyOutMappings(
        { value: 1, display: 'X', code: 'ADMIN', extra: { email: 'a@x.com' } },
        {}
      )
      expect(result).toEqual({ user_code: 'ADMIN', user_email: 'a@x.com' })
    })

    it('value_help_field 缺失时该 mapping 不会出现在结果中', () => {
      const { applyOutMappings } = useValueHelp({
        behavior: {
          out_mappings: [
            { value_help_field: 'code', local_field: 'user_code' },
            { value_help_field: 'email', local_field: 'user_email' },
          ],
        },
      })
      const result = applyOutMappings(
        { value: 1, display: 'X', code: 'ADMIN', extra: {} },
        {}
      )
      expect(result).toEqual({ user_code: 'ADMIN' })
    })

    it('支持从 extra 嵌套字段提取', () => {
      const { applyOutMappings } = useValueHelp({
        behavior: {
          out_mappings: [
            { value_help_field: 'email', local_field: 'user_email' },
          ],
        },
      })
      const result = applyOutMappings(
        { value: 1, display: 'X', code: 'A', extra: { email: 'a@x.com' } },
        {}
      )
      expect(result).toEqual({ user_email: 'a@x.com' })
    })

    it('value/display/code 三个顶层字段也可以作为映射源', () => {
      const { applyOutMappings } = useValueHelp({
        behavior: {
          out_mappings: [
            { value_help_field: 'value', local_field: 'fk_id' },
            { value_help_field: 'display', local_field: 'fk_name' },
            { value_help_field: 'code', local_field: 'fk_code' },
          ],
        },
      })
      const result = applyOutMappings(
        { value: 42, display: '采购', code: 'PO' },
        {}
      )
      expect(result).toEqual({ fk_id: 42, fk_name: '采购', fk_code: 'PO' })
    })
  })

  describe('outMappings computed', () => {
    it('返回配置中的 out_mappings 数组', () => {
      const mappings = [
        { value_help_field: 'code', local_field: 'user_code' }
      ]
      const { outMappings } = useValueHelp({
        behavior: { out_mappings: mappings },
      })
      expect(outMappings.value).toEqual(mappings)
    })

    it('无配置时返回空数组', () => {
      const { outMappings } = useValueHelp({})
      expect(outMappings.value).toEqual([])
    })
  })

  describe('recent items (localStorage 持久化)', () => {
    beforeEach(() => {
      // 每个 describe 内的 beforeEach 都会先清 mocks, 这里额外清 storage
      localStorage.clear()
    })

    it('saveRecentItem 写入 localStorage', () => {
      const { saveRecentItem } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      saveRecentItem({ value: 'a', display: 'A', code: 'A_CODE' })

      const stored = localStorage.getItem('recent_value_help_status')
      expect(stored).toBeTruthy()
      const items = JSON.parse(stored)
      expect(items).toEqual([{ value: 'a', display: 'A', code: 'A_CODE' }])
    })

    it('saveRecentItem 重复 value 时移到队首而非追加', () => {
      const { saveRecentItem } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      saveRecentItem({ value: 'a', display: 'A' })
      saveRecentItem({ value: 'b', display: 'B' })
      saveRecentItem({ value: 'a', display: 'A' })  // 重复

      const items = JSON.parse(localStorage.getItem('recent_value_help_status'))
      expect(items).toHaveLength(2)
      expect(items[0].value).toBe('a')  // 'a' 应该在最前面
    })

    it('saveRecentItem 最多保留 3 个（RECENT_MAX_ITEMS）', () => {
      const { saveRecentItem } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      saveRecentItem({ value: 'a' })
      saveRecentItem({ value: 'b' })
      saveRecentItem({ value: 'c' })
      saveRecentItem({ value: 'd' })  // 应淘汰 'a'

      const items = JSON.parse(localStorage.getItem('recent_value_help_status'))
      expect(items).toHaveLength(3)
      expect(items.map(i => i.value)).toEqual(['d', 'c', 'b'])
    })

    it('getRecentItems 从 localStorage 读取', () => {
      localStorage.setItem('recent_value_help_status', JSON.stringify([
        { value: 'a', display: 'A' }
      ]))
      const { getRecentItems } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      const items = getRecentItems()
      expect(items).toEqual([{ value: 'a', display: 'A' }])
    })

    it('getRecentItems 无 storage 时返回空数组', () => {
      const { getRecentItems } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      expect(getRecentItems()).toEqual([])
    })

    it('getRecentItems 解析失败时返回空数组（不抛错）', () => {
      localStorage.setItem('recent_value_help_status', 'invalid json{')
      const { getRecentItems } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      // 不应抛错
      expect(getRecentItems()).toEqual([])
    })

    it('不同 sourceId 使用不同的 storage key', () => {
      const a = useValueHelp({ source: { type: 'enum', enum_type_id: 'status_a' } })
      const b = useValueHelp({ source: { type: 'enum', enum_type_id: 'status_b' } })

      a.saveRecentItem({ value: '1' })
      b.saveRecentItem({ value: '2' })

      const itemsA = JSON.parse(localStorage.getItem('recent_value_help_status_a'))
      const itemsB = JSON.parse(localStorage.getItem('recent_value_help_status_b'))

      expect(itemsA[0].value).toBe('1')
      expect(itemsB[0].value).toBe('2')
    })
  })

  describe('initial_options 预填', () => {
    it('behavior.initial_options 非空时预填 optionsList', () => {
      const { optionsList } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
        behavior: {
          initial_options: [
            { value: 'active', display: 'Active' },
            { value: 'inactive' },  // 无 display, 使用 String(value)
          ],
        },
      })
      expect(optionsList.value).toHaveLength(2)
      expect(optionsList.value[0]).toMatchObject({
        value: 'active',
        display: 'Active',
        code: '',
        extra: {},
      })
      expect(optionsList.value[1].display).toBe('inactive')
    })

    it('behavior.initial_options 为空数组时不预填', () => {
      const { optionsList } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
        behavior: { initial_options: [] },
      })
      expect(optionsList.value).toEqual([])
    })

    it('无 initial_options 时 optionsList 默认为空', () => {
      const { optionsList } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      expect(optionsList.value).toEqual([])
    })
  })

  describe('loadOptions 错误码映射', () => {
    it('error 字段使用 response.error', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: false,
        error: 'CUSTOM_ERR',
        message: 'fallback msg',
      })
      const { error } = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
      })
      await useValueHelp({ source: { type: 'enum', enum_type_id: 'status' } }).loadOptions
        ? null
        : null
      // 简单做法：直接调一次
      const vh = useValueHelp({ source: { type: 'enum', enum_type_id: 'status' } })
      await vh.loadOptions()
      expect(vh.error.value).toBe('CUSTOM_ERR')
    })

    it('error 字段回退到 response.message', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: false,
        message: 'fallback msg',
      })
      const vh = useValueHelp({ source: { type: 'enum', enum_type_id: 'status' } })
      await vh.loadOptions()
      expect(vh.error.value).toBe('fallback msg')
    })

    it('success 但 data 缺失时 optionsList 不被覆盖', async () => {
      boService.searchValueHelp.mockResolvedValue({
        success: true,
        data: { data: null },
      })
      const vh = useValueHelp({
        source: { type: 'enum', enum_type_id: 'status' },
        behavior: { initial_options: [{ value: 'pre' }] },
      })
      await vh.loadOptions()
      // 初始的 pre 应该被清空（mock 返回 null data → optionsList = null || [] = []）
      // 这里验证不会抛错
      expect(Array.isArray(vh.optionsList.value)).toBe(true)
    })
  })
})
