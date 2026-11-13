/**
 * useBatchActions - 批量动作可用性求值（T13-6）
 *
 * 行/批量动作的 enabled/reason 由后端 `POST /bo/<object_type>/actions/evaluate`
 * 权威判定，本 composable 只负责：
 * - 同一 50ms 窗口内的请求按「记录 id × 动作」合并为一次调用
 * - 请求未返回期间一律 `{ enabled:false, reason:'pending' }`（fail-closed）
 * - 请求失败/返回失败时整批 `{ enabled:false, reason:'evaluate_failed' }`
 * - 结果缓存到 reactive Map，键为 `id:action`
 *
 * 红线：不本地求值 permission / condition，不新增重复 service 方法。
 */

/* eslint-disable max-lines-per-function -- 合并窗口/在途集合共享同一批闭包 state，拆分需大量参数透传，反而降低可读性 */

import { reactive, unref } from 'vue'
import { boService } from '@/services/boService'
import { logger } from '@/utils/logger'

// 请求合并窗口（毫秒）：窗口内到达的 (id, action) 合并成一次请求
const BATCH_WINDOW_MS = 50
// 后端约定：ids 为空时按对象级动作返回，桶键为 `_object`
const OBJECT_BUCKET = '_object'

const REASON_PENDING = 'pending'
const REASON_EVALUATE_FAILED = 'evaluate_failed'
const REASON_UNSUPPORTED = 'unsupported'

function disabled(reason) {
  return { enabled: false, reason, required_permission: '' }
}

/**
 * @param {string|import('vue').Ref<string>} objectTypeRef 对象类型（字符串或 ref）
 */
export function useBatchActions(objectTypeRef) {
  // 'id:action' -> { enabled, reason, required_permission }
  const results = reactive(new Map())
  // 待发送队列：'id:action' -> { id, actionId }
  const queued = new Map()
  // 正在请求中的记录 id（字符串），期间该 id 的所有动作都返回 pending
  const inflight = new Set()
  // actionId -> 最近一次动作声明（取 permission / condition）
  const actionDefs = new Map()
  let timer = null

  function currentObjectType() {
    return unref(objectTypeRef) || ''
  }

  function actionIdOf(action) {
    if (typeof action === 'string') return action.trim().toLowerCase()
    if (!action) return ''
    return String(action.id || action.key || '').trim().toLowerCase()
  }

  function cacheKey(id, actionId) {
    return `${String(id)}:${actionId}`
  }

  function normalize(verdict) {
    if (!verdict || typeof verdict !== 'object') {
      // 后端未给 verdict（不可识别/遗漏）→ 按未求值 fail-closed
      return disabled(REASON_UNSUPPORTED)
    }
    return {
      enabled: verdict.enabled === true,
      reason: verdict.reason || '',
      required_permission: verdict.required_permission || ''
    }
  }

  /**
   * 把 (id, action) 放入 50ms 合并窗口；已有缓存/在途则忽略。
   * @returns {boolean} 是否进入队列
   */
  function request(id, action) {
    const actionId = actionIdOf(action)
    if (id === undefined || id === null || !actionId || !currentObjectType()) return false
    if (action && typeof action === 'object') actionDefs.set(actionId, action)
    const key = cacheKey(id, actionId)
    if (results.has(key)) return false
    if (inflight.has(String(id)) || queued.has(key)) return false
    queued.set(key, { id, actionId })
    if (timer === null) timer = setTimeout(flush, BATCH_WINDOW_MS)
    return true
  }

  /**
   * 读取动作可用性：命中缓存返回结果，否则排队并返回 pending。
   */
  function getAction(id, action) {
    const actionId = actionIdOf(action)
    if (id === undefined || id === null || !actionId) return disabled(REASON_UNSUPPORTED)
    const cached = results.get(cacheKey(id, actionId))
    if (cached) return cached
    request(id, action)
    return disabled(REASON_PENDING)
  }

  async function flush() {
    timer = null
    const objectType = currentObjectType()
    const entries = [...queued.values()]
    queued.clear()
    if (!objectType || !entries.length) return

    const rowIds = []
    for (const entry of entries) {
      const rid = String(entry.id)
      if (!rowIds.includes(rid)) rowIds.push(rid)
    }
    rowIds.forEach(rid => inflight.add(rid))

    const actionIds = []
    for (const entry of entries) {
      if (!actionIds.includes(entry.actionId)) actionIds.push(entry.actionId)
    }
    const actions = actionIds.map(actionId => {
      const def = actionDefs.get(actionId) || {}
      return {
        id: actionId,
        permission: def.permission || '',
        condition: def.condition || ''
      }
    })
    // 对象级动作桶键不能当记录 id 发送，后端以空 ids 表示对象级求值
    const ids = rowIds.filter(rid => rid !== OBJECT_BUCKET)

    try {
      const res = await boService.evaluateActions(objectType, ids, actions)
      if (!res || !res.success || !res.data || typeof res.data !== 'object') {
        throw new Error((res && res.message) || REASON_EVALUATE_FAILED)
      }
      for (const entry of entries) {
        const bucket = res.data[String(entry.id)] || {}
        results.set(cacheKey(entry.id, entry.actionId), normalize(bucket[entry.actionId]))
      }
    } catch (err) {
      // 整批 fail-closed：不得残留任何可点按钮
      logger.error('[useBatchActions] actions/evaluate 失败，本批动作 fail-closed:', err)
      for (const entry of entries) {
        results.set(cacheKey(entry.id, entry.actionId), disabled(REASON_EVALUATE_FAILED))
      }
    } finally {
      rowIds.forEach(rid => inflight.delete(rid))
    }
  }

  /**
   * 清空缓存与待发送队列（切换对象/记录集合时调用）。
   */
  function clear() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
    results.clear()
    queued.clear()
    inflight.clear()
    actionDefs.clear()
  }

  return { results, request, getAction, clear }
}

export default useBatchActions