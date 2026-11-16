/**
 * useListPreferences - 列表个性化偏好（本地持久化）
 *
 * 契约见 docs/specs/spec-meta-driven-ui-2026-11-16.md §4.10。
 * - 存储键：meta-ui:list:<object_type>:<schema_version>
 * - 仅整页列表（displayMode === 'page'）启用；embedded / dialog 直接跳过
 * - 仓储异常（隐私模式 / 配额 / 非法 JSON）静默降级为默认值
 */
import { computed, ref, unref } from 'vue'

const STORAGE_PREFIX = 'meta-ui:list'
const MAX_PAGE_SIZE = 200

export function buildStorageKey(objectType, schemaVersion) {
  return `${STORAGE_PREFIX}:${objectType || ''}:${schemaVersion || ''}`
}

export function createDefaultPreferences() {
  return {
    columnOrder: [],
    hidden: [],
    width: {},
    pageSize: null,
    filters: { panel: {}, header: {} }
  }
}

function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function toStringArray(value) {
  if (!Array.isArray(value)) return []
  return [...new Set(value.filter(item => typeof item === 'string' && item))]
}

export function normalizePreferences(raw) {
  const result = createDefaultPreferences()
  if (!isPlainObject(raw)) return result

  result.columnOrder = toStringArray(raw.columnOrder)
  result.hidden = toStringArray(raw.hidden)

  if (isPlainObject(raw.width)) {
    for (const [prop, width] of Object.entries(raw.width)) {
      if (prop && Number.isFinite(width) && width > 0) {
        result.width[prop] = width
      }
    }
  }

  const size = Number(raw.pageSize)
  if (Number.isInteger(size) && size > 0 && size <= MAX_PAGE_SIZE) {
    result.pageSize = size
  }

  if (isPlainObject(raw.filters)) {
    if (isPlainObject(raw.filters.panel)) result.filters.panel = raw.filters.panel
    if (isPlainObject(raw.filters.header)) result.filters.header = raw.filters.header
  }

  return result
}

export function applyColumnOrder(columns, columnOrder) {
  if (!Array.isArray(columns) || columns.length === 0) return []
  if (!Array.isArray(columnOrder) || columnOrder.length === 0) return columns.slice()

  const remaining = new Map(columns.map(column => [column.prop, column]))
  const ordered = []
  for (const prop of columnOrder) {
    const column = remaining.get(prop)
    if (column) {
      ordered.push(column)
      remaining.delete(prop)
    }
  }
  // 未在偏好里出现的新列按元数据顺序追加末尾
  for (const column of columns) {
    if (remaining.has(column.prop)) ordered.push(column)
  }
  return ordered
}

export function filterHiddenColumns(columns, hidden) {
  if (!Array.isArray(columns)) return []
  if (!Array.isArray(hidden) || hidden.length === 0) return columns
  const hiddenSet = new Set(hidden)
  return columns.filter(column => !hiddenSet.has(column.prop))
}

export function resolvePageSize(saved, allowed, fallback) {
  if (!Number.isInteger(saved) || saved <= 0) return fallback
  if (Array.isArray(allowed) && allowed.length > 0) {
    const allowedNumbers = allowed.map(Number)
    if (!allowedNumbers.includes(saved)) return fallback
  }
  return saved
}

function getDefaultStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

/* eslint-disable max-lines-per-function -- prefs/storageKey 被 load/patch/persist 共享，拆分会引入大量参数透传 */
export function useListPreferences(options = {}) {
  const storage = options.storage ?? getDefaultStorage()
  const prefs = ref(createDefaultPreferences())

  const storageKey = computed(() => {
    if (unref(options.enabled) === false) return ''
    const objectType = unref(options.objectType)
    const schemaVersion = unref(options.schemaVersion)
    if (!objectType || !schemaVersion) return ''
    return buildStorageKey(objectType, schemaVersion)
  })

  let activeKey = ''

  function load() {
    const key = storageKey.value
    if (!key || key === activeKey) return null
    activeKey = key
    let restored = null
    try {
      const raw = storage?.getItem(key)
      if (raw) restored = normalizePreferences(JSON.parse(raw))
    } catch {
      restored = null
    }
    prefs.value = restored || createDefaultPreferences()
    return restored
  }

  function persist() {
    const key = storageKey.value
    if (!key || !storage) return
    try {
      storage.setItem(key, JSON.stringify(prefs.value))
    } catch {
      // 隐私模式 / 配额超限：静默降级，不影响列表
    }
  }

  function patch(partial) {
    prefs.value = normalizePreferences({ ...prefs.value, ...partial })
    persist()
  }

  return {
    prefs,
    storageKey,
    load,
    patch,
    persist,
    setColumnOrder: (columnOrder) => patch({ columnOrder }),
    setHidden: (hidden) => patch({ hidden }),
    setWidth: (prop, width) => patch({ width: { ...prefs.value.width, [prop]: width } }),
    setPageSize: (pageSize) => patch({ pageSize }),
    setFilters: (filters) => patch({ filters }),
    reset: () => {
      prefs.value = createDefaultPreferences()
      persist()
    }
  }
}
