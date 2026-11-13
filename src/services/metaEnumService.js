/**
 * 统一元数据服务（B2）
 *
 * 前端不再维护枚举/标签副本，一律从后端 `/api/v2/meta/*` 下发：
 * - getEnum(name)                  枚举（permission_level / task_status / hierarchy_level ...）
 * - getPermissionMatrixSchema()    权限矩阵分组 schema（group_labels / group_actions_map ...）
 * - getPermissionMeta()            权限元数据（resource/action/dimension 标签）
 */

import { apiV2 } from '@/utils/httpClient'
import { logger } from '@/utils/logger'

const enumCache = new Map()
const enumInflight = new Map()
let matrixSchemaPromise = null

async function fetchData(url, options) {
  const r = await apiV2.get(url, options)
  if (r?.success === false) {
    const message = r.message || '元数据下发失败'
    throw new Error(message)
  }
  return r?.data
}

function normalizeItems(raw) {
  if (Array.isArray(raw)) return raw
  return raw?.items || []
}

/**
 * 批量获取枚举项（单次 batch 请求，已缓存的 name 不再请求）
 * @param {string[]} names 枚举名列表
 * @returns {Promise<Object<string, Array>>} { name: items }，未知 name 为 []
 */
export async function getEnumBatch(names) {
  const unique = [
    ...new Set(
      (Array.isArray(names) ? names : [])
        .map(name => (typeof name === 'string' ? name.trim() : ''))
        .filter(Boolean)
    )
  ]
  if (!unique.length) return {}

  const result = {}
  for (const name of unique) {
    if (enumCache.has(name)) result[name] = enumCache.get(name)
  }

  // name 级 inflight 合并：已被其他批次覆盖的 name 直接等待，只有完全无人
  // 在途的 name 才发起新 batch，避免不同 name 集合的并发调用重复请求。
  const missing = unique.filter(name => !enumCache.has(name))
  const inFlight = missing.filter(name => enumInflight.has(name))
  const toFetch = missing.filter(name => !enumInflight.has(name))

  const waits = inFlight.map(name => enumInflight.get(name)).filter(Boolean)

  if (toFetch.length) {
    const promise = fetchData('/meta/enums/batch', { params: { names: toFetch.join(',') } })
      .then(data => {
        for (const name of toFetch) {
          enumCache.set(name, normalizeItems(data?.[name]))
        }
      })
      .catch(err => {
        logger.warn(`[metaEnumService] 批量枚举下发失败: ${toFetch.join(',')}`, err)
        throw err
      })
      .finally(() => {
        for (const name of toFetch) enumInflight.delete(name)
      })
    for (const name of toFetch) enumInflight.set(name, promise)
    waits.push(promise)
  }

  if (waits.length) await Promise.all(waits)

  for (const name of unique) result[name] = enumCache.get(name) || []
  return result
}

/**
 * 获取枚举项（fail-closed：后端未返回即抛错，不再回退到前端猜测值）
 * 底层统一走 batch 端点
 * @param {string} name 枚举名，如 permission_level
 * @returns {Promise<Array<{value: string, label: string, level?: number}>>}
 */
export async function getEnum(name) {
  if (enumCache.has(name)) return enumCache.get(name)
  if (enumInflight.has(name)) {
    // 等待同批 batch 完成（失败时同样抛错）
    await enumInflight.get(name)
    return enumCache.get(name) || []
  }
  const batch = await getEnumBatch([name])
  return batch[name] || []
}

/**
 * 权限矩阵分组 schema（进程内缓存）
 */
export function getPermissionMatrixSchema() {
  if (!matrixSchemaPromise) {
    matrixSchemaPromise = fetchData('/meta/permission-matrix-schema')
      .catch(err => {
        logger.warn('[metaEnumService] 权限矩阵 schema 下发失败', err)
        matrixSchemaPromise = null
        throw err
      })
  }
  return matrixSchemaPromise
}

/**
 * 权限元数据（与 /bo/permission_dimension/meta 同源）
 */
export function getPermissionMeta() {
  return fetchData('/meta/permission-meta')
}

/** 清空缓存（仅测试使用） */
export function _resetMetaCache() {
  enumCache.clear()
  enumInflight.clear()
  matrixSchemaPromise = null
}