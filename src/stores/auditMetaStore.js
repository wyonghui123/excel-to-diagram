/**
 * auditMetaStore - 审计日志元数据缓存
 *
 * [P1-A 2026-07-25] 替代 auditLogFormat.js 中的硬编码翻译表
 *   - ACTION_LABELS / ACTION_TAG_TYPES → 后端 /audit/meta/actions 单一事实源
 *   - 启动时调用 loadActions() 一次, 缓存到 store
 *   - 各页面通过 getActionLabel(action) / getActionTagType(action) 读取
 *
 * 降级策略:
 *   - 后端不可用或未加载时, 返回原值 (与 auditLogFormat.js fallback 一致)
 *   - 不阻塞页面渲染, 后台静默加载
 *
 * @module stores/auditMetaStore
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMetaActions } from '@/services/auditLogService'

export const useAuditMetaStore = defineStore('auditMeta', () => {
  // state
  const actions = ref([]) // [{value, label, color}]
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref(null)

  // getters
  const actionMap = computed(() => {
    const m = new Map()
    for (const a of actions.value) {
      m.set(a.value, a)
    }
    return m
  })

  const actionCount = computed(() => actions.value.length)

  // actions
  /**
   * 从后端加载 action 元数据
   * @param {Object} [options]
   * @param {boolean} [options.force=false] - 强制重新加载 (忽略缓存)
   * @returns {Promise<boolean>} 是否加载成功
   */
  async function loadActions({ force = false } = {}) {
    if (loaded.value && !force) return true
    if (loading.value) return false // 防并发

    loading.value = true
    error.value = null
    try {
      const res = await getMetaActions()
      if (res && res.success && Array.isArray(res.data)) {
        actions.value = res.data
        loaded.value = true
        return true
      }
      // 后端返回但格式异常, 不抛错, 保持空列表
      actions.value = []
      loaded.value = true
      return false
    } catch (e) {
      error.value = e?.message || String(e)
      // 失败时保持空列表, 调用方降级用原值
      actions.value = []
      loaded.value = true // 标记已尝试, 避免反复重试
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取 action 业务标签
   * @param {string} action - 后端 action 字段值
   * @returns {string} 业务标签, 未加载或未找到时返回原值
   */
  function getActionLabel(action) {
    if (!action) return ''
    const item = actionMap.value.get(action)
    return item?.label || action
  }

  /**
   * 获取 action 对应的 Element-Plus tag 类型 (颜色)
   *
   * 颜色规范化:
   *   - 后端 YAML 用 `default` 表示"无类型" (与 Element Plus `''` 等价)
   *   - 空字符串 / `default` / null → 返回 '' (Element Plus default 样式)
   *   - 其他原样返回 ('primary' | 'success' | 'info' | 'warning' | 'danger')
   *
   * @param {string} action
   * @returns {string} Element Plus tag type ('' | 'primary' | 'success' | 'info' | 'warning' | 'danger')
   */
  function getActionTagType(action) {
    if (!action) return ''
    const item = actionMap.value.get(action)
    const c = item?.color
    if (!c || c === 'default') return ''
    return c
  }

  /**
   * 获取所有 action 列表 (用于筛选 dropdown options)
   * @returns {Array<{value, label, color}>}
   */
  function getActionOptions() {
    return actions.value
  }

  /**
   * 重置 store (用于测试或登出)
   */
  function $reset() {
    actions.value = []
    loaded.value = false
    loading.value = false
    error.value = null
  }

  return {
    // state
    actions,
    loaded,
    loading,
    error,
    // getters
    actionMap,
    actionCount,
    // actions
    loadActions,
    getActionLabel,
    getActionTagType,
    getActionOptions,
    $reset,
  }
})
