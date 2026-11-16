/**
 * useListPreferences.spec.js - 列表个性化偏好（spec §4.10）
 *
 * 覆盖：键格式 / 非法值清洗 / 列序（未知列丢弃、新增列末尾）/ 隐藏过滤 /
 *       pageSize 白名单回退 / 存取往返 / 非法 JSON → null / schema_version 不串号。
 */

import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  buildStorageKey,
  createDefaultPreferences,
  normalizePreferences,
  applyColumnOrder,
  filterHiddenColumns,
  resolvePageSize,
  useListPreferences
} from '@/composables/useListPreferences'

function createMemoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
    _map: map
  }
}

const COLUMNS = [
  { prop: 'code', label: '编码' },
  { prop: 'name', label: '名称' },
  { prop: 'status', label: '状态' }
]

/* eslint-disable max-lines-per-function -- 测试 describe 块按场景分组，可读性 > 单函数行数 */
describe('useListPreferences', () => {
  it('buildStorageKey 包含对象类型与 schema_version', () => {
    expect(buildStorageKey('task_run', 'abc123')).toBe('meta-ui:list:task_run:abc123')
  })

  it('normalizePreferences: 非对象/非法值回退默认', () => {
    expect(normalizePreferences(null)).toEqual(createDefaultPreferences())
    expect(normalizePreferences('bad')).toEqual(createDefaultPreferences())

    const cleaned = normalizePreferences({
      columnOrder: ['name', 'name', 123, ''],
      hidden: ['status', 'status', null],
      width: { name: 160, bad: -1, zero: 0, nan: Number.NaN },
      pageSize: 0,
      filters: { panel: { status: 'failed' }, header: 'bad' }
    })
    expect(cleaned.columnOrder).toEqual(['name'])
    expect(cleaned.hidden).toEqual(['status'])
    expect(cleaned.width).toEqual({ name: 160 })
    expect(cleaned.pageSize).toBeNull()
    expect(cleaned.filters).toEqual({ panel: { status: 'failed' }, header: {} })
  })

  it('normalizePreferences: pageSize 上限 200', () => {
    expect(normalizePreferences({ pageSize: 50 }).pageSize).toBe(50)
    expect(normalizePreferences({ pageSize: 201 }).pageSize).toBeNull()
    expect(normalizePreferences({ pageSize: 12.5 }).pageSize).toBeNull()
  })

  it('applyColumnOrder: 未知列丢弃、新增列追加末尾', () => {
    const ordered = applyColumnOrder(COLUMNS, ['status', 'removed', 'code'])
    expect(ordered.map(c => c.prop)).toEqual(['status', 'code', 'name'])

    expect(applyColumnOrder(COLUMNS, []).map(c => c.prop)).toEqual(['code', 'name', 'status'])
    expect(applyColumnOrder([], ['code'])).toEqual([])
  })

  it('filterHiddenColumns: 空隐藏列表原样返回', () => {
    expect(filterHiddenColumns(COLUMNS, [])).toBe(COLUMNS)
    expect(filterHiddenColumns(COLUMNS, ['name']).map(c => c.prop)).toEqual(['code', 'status'])
    expect(filterHiddenColumns(null, ['name'])).toEqual([])
  })

  it('resolvePageSize: 不在白名单内回退默认', () => {
    expect(resolvePageSize(50, [10, 20, 50, 100], 20)).toBe(50)
    expect(resolvePageSize(30, [10, 20, 50, 100], 20)).toBe(20)
    expect(resolvePageSize(null, [10, 20], 20)).toBe(20)
    expect(resolvePageSize(30, [], 20)).toBe(30)
  })

  it('存取往返：保存后新实例可恢复', () => {
    const storage = createMemoryStorage()
    const first = useListPreferences({
      objectType: ref('task_run'),
      schemaVersion: ref('v1'),
      storage
    })
    expect(first.load()).toBeNull()
    first.patch({ columnOrder: ['name'], hidden: ['status'], pageSize: 50, width: { name: 180 } })

    const second = useListPreferences({
      objectType: ref('task_run'),
      schemaVersion: ref('v1'),
      storage
    })
    const restored = second.load()
    expect(restored.columnOrder).toEqual(['name'])
    expect(restored.hidden).toEqual(['status'])
    expect(restored.pageSize).toBe(50)
    expect(restored.width).toEqual({ name: 180 })
    expect(second.prefs.value.pageSize).toBe(50)
  })

  it('schema_version 变化不串号', () => {
    const storage = createMemoryStorage()
    const v1 = useListPreferences({ objectType: ref('task_run'), schemaVersion: ref('v1'), storage })
    v1.patch({ pageSize: 100 })

    const v2 = useListPreferences({ objectType: ref('task_run'), schemaVersion: ref('v2'), storage })
    expect(v2.load()).toBeNull()
    expect(v2.prefs.value.pageSize).toBeNull()
  })

  it('非法 JSON 或缺失键返回 null', () => {
    const storage = createMemoryStorage({
      [buildStorageKey('task_run', 'v1')]: '{not-json'
    })
    const prefs = useListPreferences({ objectType: ref('task_run'), schemaVersion: ref('v1'), storage })
    expect(prefs.load()).toBeNull()
    expect(prefs.prefs.value).toEqual(createDefaultPreferences())
  })

  it('enabled=false（embedded/dialog）不读不写', () => {
    const storage = createMemoryStorage({
      [buildStorageKey('task_run', 'v1')]: JSON.stringify({ pageSize: 100 })
    })
    const prefs = useListPreferences({
      objectType: ref('task_run'),
      schemaVersion: ref('v1'),
      enabled: ref(false),
      storage
    })
    expect(prefs.storageKey.value).toBe('')
    expect(prefs.load()).toBeNull()
    prefs.setPageSize(50)
    expect(storage._map.size).toBe(1)
  })
})
