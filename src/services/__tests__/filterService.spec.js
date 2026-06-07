import { describe, it, expect } from 'vitest'
import {
  isInternalProp,
  formatDate,
  inferFilterType,
  normalizeFilterType,
  generateFiltersFromFields,
  transformFilters,
  backfillColumnFilterType,
  getDefaultFilterValues,
  addFilterParam,
  buildFilterQueryParams,
  mergeFilters
} from '@/services/filterService'

describe('isInternalProp', () => {
  it('should return true for Vue internal props', () => {
    expect(isInternalProp('__v_isRef')).toBe(true)
    expect(isInternalProp('__v_isReactive')).toBe(true)
    expect(isInternalProp('fn')).toBe(true)
    expect(isInternalProp('dep')).toBe(true)
    expect(isInternalProp('deps')).toBe(true)
  })

  it('should return false for normal keys', () => {
    expect(isInternalProp('name')).toBe(false)
    expect(isInternalProp('id')).toBe(false)
    expect(isInternalProp('version_id')).toBe(false)
    expect(isInternalProp('email')).toBe(false)
  })
})

describe('formatDate', () => {
  it('should format Date to string with time', () => {
    const d = new Date('2026-05-18T10:30:00')
    const result = formatDate(d, false)
    expect(result).toBe('2026-05-18 10:30:00')
  })

  it('should format Date to end-of-day when isEndTime', () => {
    const d = new Date('2026-05-18T10:30:00')
    const result = formatDate(d, true)
    expect(result).toBe('2026-05-18 23:59:59')
  })

  it('should handle string date with time part', () => {
    expect(formatDate('2026-05-18 15:30:00')).toBe('2026-05-18 15:30:00')
  })

  it('should append 00:00:00 for date-only string', () => {
    expect(formatDate('2026-05-18')).toBe('2026-05-18 00:00:00')
  })

  it('should append 23:59:59 for date-only string with isEndTime', () => {
    expect(formatDate('2026-05-18', true)).toBe('2026-05-18 23:59:59')
  })

  it('should return empty string for falsy values', () => {
    expect(formatDate(null)).toBe('')
    expect(formatDate(undefined)).toBe('')
    expect(formatDate('')).toBe('')
  })
})

describe('inferFilterType', () => {
  it('should return date-range for datetime fields', () => {
    expect(inferFilterType({ type: 'datetime' })).toBe('date-range')
    expect(inferFilterType({ type: 'timestamp' })).toBe('date-range')
    expect(inferFilterType({ type: 'date' })).toBe('date-range')
    expect(inferFilterType({ type: 'text', format: 'datetime' })).toBe('date-range')
  })

  it('should return select for fields with options', () => {
    expect(inferFilterType({ type: 'text', options: [{ value: 'a', label: 'A' }] })).toBe('select')
  })

  it('should return select for enum types', () => {
    expect(inferFilterType({ type: 'enum' })).toBe('select')
  })

  it('should return select for badge/tag/radio widgets', () => {
    expect(inferFilterType({ type: 'text', widget: 'badge' })).toBe('select')
    expect(inferFilterType({ type: 'text', widget: 'tag' })).toBe('select')
    expect(inferFilterType({ type: 'text', widget: 'radio' })).toBe('select')
  })

  it('should return number-range for numeric types', () => {
    expect(inferFilterType({ type: 'integer' })).toBe('number-range')
    expect(inferFilterType({ type: 'number' })).toBe('number-range')
    expect(inferFilterType({ type: 'float' })).toBe('number-range')
  })

  it('should default to search', () => {
    expect(inferFilterType({ type: 'text' })).toBe('search')
    expect(inferFilterType({ type: 'string' })).toBe('search')
  })
})

describe('normalizeFilterType', () => {
  it('should normalize date range variants', () => {
    expect(normalizeFilterType('date_range')).toBe('date-range')
    expect(normalizeFilterType('daterange')).toBe('date-range')
    expect(normalizeFilterType('datetime-range')).toBe('date-range')
  })

  it('should normalize number range variants', () => {
    expect(normalizeFilterType('number_range')).toBe('number-range')
    expect(normalizeFilterType('numberrange')).toBe('number-range')
  })

  it('should normalize multi-select variants', () => {
    expect(normalizeFilterType('multi-select')).toBe('multi-select')
    expect(normalizeFilterType('multiselect')).toBe('multi-select')
  })

  it('should pass through already normalized types', () => {
    expect(normalizeFilterType('search')).toBe('search')
    expect(normalizeFilterType('select')).toBe('select')
  })

  it('should default to search for unknown types', () => {
    expect(normalizeFilterType('')).toBe('search')
    expect(normalizeFilterType(null)).toBe('search')
    expect(normalizeFilterType('unknown')).toBe('search')
  })
})

describe('generateFiltersFromFields', () => {
  const fields = [
    {
      key: 'name', type: 'string', label: '名称',
      filterable: true, field: 'name'
    },
    {
      key: 'created_at', type: 'datetime', label: '创建时间',
      filterable: true, field: 'created_at'
    },
    {
      key: 'status', type: 'enum', label: '状态',
      filterable: true, filter_options: [
        { value: 'active', label: '激活' },
        { value: 'inactive', label: '未激活' }
      ]
    },
    {
      key: 'count', type: 'integer', label: '数量',
      filterable: true
    },
    {
      key: 'hidden_field', type: 'text', label: '隐藏',
      filterable: false
    }
  ]

  it('should generate correct filter config for each type', () => {
    const result = generateFiltersFromFields(fields)
    expect(result).toHaveLength(4)

    const nameFilter = result.find(f => f.key === 'name')
    expect(nameFilter.type).toBe('text')

    const dateFilter = result.find(f => f.key === 'created_at')
    expect(dateFilter.type).toBe('datetime-range')

    const statusFilter = result.find(f => f.key === 'status')
    expect(statusFilter.type).toBe('select')
    expect(statusFilter.options.length).toBeGreaterThan(2)

    const countFilter = result.find(f => f.key === 'count')
    expect(countFilter.type).toBe('number-range')
  })

  it('should exclude non-filterable fields', () => {
    const result = generateFiltersFromFields(fields)
    const hiddenField = result.find(f => f.key === 'hidden_field')
    expect(hiddenField).toBeUndefined()
  })

  it('should use field_display_names from metaConfig', () => {
    const metaConfig = { field_display_names: { name: '自定义名称' } }
    const result = generateFiltersFromFields(fields, metaConfig)
    const nameFilter = result.find(f => f.key === 'name')
    expect(nameFilter.label).toBe('自定义名称')
  })

  it('should return empty array for empty input', () => {
    expect(generateFiltersFromFields([])).toEqual([])
    expect(generateFiltersFromFields(null)).toEqual([])
  })
})

describe('transformFilters', () => {
  const yamlFilters = [
    { key: 'status', label: '状态', type: 'select', options: [{ value: 'active', label: '激活' }] }
  ]

  it('should convert yaml filters to FilterBar format', () => {
    const result = transformFilters(yamlFilters)
    const statusFilter = result.find(f => f.key === 'status')
    expect(statusFilter).toBeDefined()
    expect(statusFilter.label).toBe('状态')
    expect(statusFilter.type).toBe('select')
    expect(statusFilter.clearable).toBe(true)
  })

  it('should merge with auto-generated fields from tableColumns', () => {
    const metaConfig = {
      list: {
        tableColumns: [
          { key: 'name', type: 'string', filterable: true }
        ]
      }
    }
    const result = transformFilters(yamlFilters, metaConfig)
    expect(result.length).toBeGreaterThanOrEqual(2)
  })

  it('should return auto-generated when no explicit filters', () => {
    const metaConfig = {
      list: {
        tableColumns: [
          { key: 'email', type: 'string', filterable: true }
        ]
      }
    }
    const result = transformFilters(null, metaConfig)
    expect(result.length).toBe(1)
    expect(result[0].key).toBe('email')
  })
})

describe('backfillColumnFilterType', () => {
  it('should set filter_type from backend filters', () => {
    const columns = [
      { prop: 'name', type: 'text' },
      { prop: 'created_at', type: 'text' }
    ]
    const rawFilters = [
      { key: 'name', type: 'search' },
      { key: 'created_at', type: 'date-range' }
    ]
    backfillColumnFilterType(columns, rawFilters)
    expect(columns[0].filter_type).toBeUndefined()
    expect(columns[1].filter_type).toBe('date-range')
  })

  it('should populate filter_options from backend', () => {
    const columns = [{ prop: 'status', type: 'text' }]
    const rawFilters = [
      { key: 'status', type: 'select', options: [{ value: 'active', label: '激活' }] }
    ]
    backfillColumnFilterType(columns, rawFilters)
    expect(columns[0].filter_options).toBeDefined()
  })

  it('should infer type when not provided by backend', () => {
    const columns = [{ prop: 'count', type: 'integer' }]
    backfillColumnFilterType(columns, [])
    expect(columns[0].filter_type).toBe('number-range')
  })

  it('should not modify if columns is empty', () => {
    expect(() => backfillColumnFilterType([], [])).not.toThrow()
  })
})

describe('getDefaultFilterValues', () => {
  it('should extract default values from filter fields', () => {
    const fields = [
      { key: 'status', defaultValue: 'active' },
      { key: 'name', defaultValue: '' },
      { key: 'type', defaultValue: 'user' }
    ]
    const result = getDefaultFilterValues(fields)
    expect(result).toEqual({ status: 'active', type: 'user' })
  })

  it('should return empty object for empty fields', () => {
    expect(getDefaultFilterValues([])).toEqual({})
  })
})

describe('addFilterParam', () => {
  const columns = [
    { prop: 'name', type: 'text' },
    { prop: 'count', type: 'integer' },
    { prop: 'created_at', type: 'datetime' },
    { prop: 'category_id', type: 'integer' },
    { prop: 'status', type: 'enum', filter_type: 'select' }
  ]
  const filterFields = []

  it('should skip empty values', () => {
    const params = {}
    addFilterParam(params, 'name', '', columns, filterFields)
    addFilterParam(params, 'name', null, columns, filterFields)
    expect(params).toEqual({})
  })

  it('should use LIKE for text fields', () => {
    const params = {}
    addFilterParam(params, 'name', 'test', columns, filterFields)
    expect(params.name__like).toBe('%test%')
  })

  it('should use exact match for ID fields', () => {
    const params = {}
    addFilterParam(params, 'category_id', 5, columns, filterFields)
    expect(params.category_id).toBe('5')
  })

  it('should handle date range arrays', () => {
    const params = {}
    addFilterParam(params, 'created_at', ['2026-01-01', '2026-05-18'], columns, filterFields)
    expect(params.created_at_start).toBeDefined()
    expect(params.created_at_end).toBeDefined()
  })

  it('should handle number range arrays', () => {
    // 注：源码使用 `__gte` / `__lte` 后缀（不是 `_min` / `_max`）
    // 同时要求 filter_type === 'number-range' 且 fieldType 为数字类型
    // 直接构造一个完整的 number-range 字段定义（filter_type 必须是 number-range）
    const numberRangeColumns = [
      { prop: 'count', type: 'integer', filter_type: 'number-range' }
    ]
    const params = {}
    addFilterParam(params, 'count', [10, 100], numberRangeColumns, filterFields)
    expect(params.count__gte).toBe('10')
    expect(params.count__lte).toBe('100')
  })

  it('should handle multi-select arrays', () => {
    const params = {}
    addFilterParam(params, 'status', ['active', 'pending'], columns, filterFields)
    expect(params.status__in).toBe('active,pending')
  })

  it('should handle keyword special key', () => {
    const params = {}
    addFilterParam(params, 'keyword', 'searchtext', columns, filterFields)
    expect(params.search).toBe('searchtext')
  })

  it('should pass through keys with __ operator suffix', () => {
    const params = {}
    addFilterParam(params, 'name__like', '%test%', columns, filterFields)
    expect(params.name__like).toBe('%test%')
  })

  it('should use LIKE for text type numeric strings', () => {
    const params = {}
    addFilterParam(params, 'name', '123abc', columns, filterFields)
    expect(params.name__like).toBe('%123abc%')
  })
})

describe('buildFilterQueryParams', () => {
  const columns = [
    { prop: 'name', type: 'text' },
    { prop: 'created_at', type: 'datetime' }
  ]

  it('should build basic pagination params', () => {
    const result = buildFilterQueryParams({
      page: 1,
      pageSize: 20,
      columns
    })
    expect(result.page).toBe(1)
    expect(result.page_size).toBe(20)
  })

  it('should include keyword search', () => {
    const result = buildFilterQueryParams({
      page: 1, pageSize: 20, columns,
      keyword: 'hello'
    })
    expect(result.keyword).toBe('hello')
  })

  it('should process filterValues and headerFilterValues', () => {
    const result = buildFilterQueryParams({
      page: 1, pageSize: 20, columns,
      filterValues: { name: 'test' },
      headerFilterValues: {}
    })
    expect(result.name__like).toBe('%test%')
  })

  it('should include sort ordering', () => {
    const result = buildFilterQueryParams({
      page: 1, pageSize: 20, columns,
      sortProp: 'created_at',
      sortOrder: 'descending'
    })
    expect(result.ordering).toBe('-created_at')
  })

  it('should filter out Vue internal props', () => {
    const result = buildFilterQueryParams({
      page: 1, pageSize: 20, columns,
      filterValues: { name: 'test', __v_isRef: true, fn: 'x' },
      headerFilterValues: {}
    })
    expect(result.__v_isRef).toBeUndefined()
    expect(result.fn).toBeUndefined()
    expect(result.name__like).toBe('%test%')
  })

  it('should merge extra params', () => {
    const result = buildFilterQueryParams({
      page: 1, pageSize: 20, columns,
      extraParams: { workspace_id: 99 }
    })
    expect(result.workspace_id).toBe(99)
  })
})

describe('mergeFilters', () => {
  it('should merge multiple filter sources (skip null/empty)', () => {
    const result = mergeFilters(
      { name: 'test', status: '' },
      { status: 'active', count: 10 },
      { count: null }
    )
    expect(result).toEqual({ name: 'test', status: 'active', count: 10 })
  })

  it('should handle empty/undefined sources', () => {
    const result = mergeFilters(null, { a: 1 }, undefined)
    expect(result).toEqual({ a: 1 })
  })

  it('should return empty for no sources', () => {
    expect(mergeFilters()).toEqual({})
  })
})
