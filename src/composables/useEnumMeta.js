/**
 * useEnumMeta.js - 枚举加载 / 缓存 / 并发去重（T13-3）
 *
 * 模块级 cache + inflight；缓存项与 ui-meta 的 schema_version 对齐，
 * 版本变化即重取。值统一用 String(value) 归一，保证 0 / false 能命中。
 */

import { ref } from 'vue'
import * as metaEnumService from '@/services/metaEnumService'
import { logger } from '@/utils/logger'

const cache = new Map()   // name -> { schemaVersion, items, byValue }
const inflight = new Map()

export function useEnumMeta() {
  const loading = ref(false)

  async function load(name, schemaVersion) {
    if (!name) return null
    const key = String(name)
    const hit = cache.get(key)
    if (hit && hit.schemaVersion === schemaVersion) return hit
    if (inflight.has(key)) return inflight.get(key)

    loading.value = true
    const promise = metaEnumService.getEnum(key)
      .then(items => {
        const entry = {
          schemaVersion,
          items: items || [],
          byValue: new Map((items || []).map(i => [String(i.value), i]))
        }
        cache.set(key, entry)
        return entry
      })
      .finally(() => {
        inflight.delete(key)
        loading.value = false
      })

    inflight.set(key, promise)
    return promise
  }

  function getItem(name, value) {
    if (!name) return null
    return cache.get(String(name))?.byValue.get(String(value)) || null
  }

  function getItems(name) {
    if (!name) return []
    return cache.get(String(name))?.items || []
  }

  return { load, getItem, getItems, loading }
}

/**
 * 批量预加载枚举（一次 batch 请求），写入模块级缓存
 * 失败 fail-soft：仅 warn，不抛出，不影响页面渲染
 * @param {string[]} enumTypes 枚举名列表
 * @returns {Promise<Object<string, Array>>} { name: items }
 */
export async function preloadEnums(enumTypes) {
  const names = [
    ...new Set(
      (Array.isArray(enumTypes) ? enumTypes : [])
        .map(name => (typeof name === 'string' ? name.trim() : ''))
        .filter(Boolean)
    )
  ]
  if (!names.length) return {}

  const result = {}
  try {
    const batch = await metaEnumService.getEnumBatch(names)
    for (const name of names) {
      const items = batch?.[name] || []
      cache.set(String(name), {
        schemaVersion: undefined,
        items,
        byValue: new Map(items.map(i => [String(i.value), i]))
      })
      result[name] = items
    }
  } catch (err) {
    logger.warn('[useEnumMeta] 枚举预加载失败', err)
  }
  return result
}

/** 清空模块级缓存（仅测试使用） */
export function _resetEnumMetaCache() {
  cache.clear()
  inflight.clear()
}