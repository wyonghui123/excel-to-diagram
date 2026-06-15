/**
 * 元数据缓存 Composable
 * 
 * 用于缓存菜单、层级配置等元数据，支持离线模式
 * 
 * 缓存策略：
 * 1. API 成功时存储到 localStorage
 * 2. API 失败时从缓存恢复
 * 3. 缓存超过 TTL 时显示过期提示
 * 
 * 参考：Salesforce SmartStore、SaaS 缓存最佳实践
 */

import { ref, computed } from 'vue'
import { apiV1 } from '@/utils/httpClient'

const DEFAULT_TTL = 24 * 60 * 60 * 1000 // 24 小时

/**
 * @param {string} cacheKey - localStorage 键名
 * @param {number} ttl - 缓存过期时间（毫秒）
 */
export function useMetaCache(cacheKey, ttl = DEFAULT_TTL) {
  const data = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const fromCache = ref(false)
  const cacheExpired = ref(false)

  function getCache(expectedVersion = null, expectedUserId = null) {
    try {
      const raw = localStorage.getItem(cacheKey)
      if (!raw) return null

      const cached = JSON.parse(raw)
      const now = Date.now()

      if (cached.timestamp && (now - cached.timestamp > ttl)) {
        cacheExpired.value = true
        return null
      }

      if (expectedVersion && cached.version && cached.version !== expectedVersion) {
        cacheExpired.value = true
        return null
      }

      // [FIX 2026-06-14] user_id 维度: 切换用户后, 旧 user 的 cache 不应被新 user 复用
      // 场景: admin 登录 → 菜单 cache 写入 localStorage; admin 退出 → TEST333 登录
      //       旧 cache key "menuCache" 不含 user_id, TEST333 loadMenuPermissions 拿到 admin 的菜单
      //       → landing page 短暂显示"系统管理"card, refresh 后才正确
      // 修复: 写入时把 userId 存到 entry, 读取时比对, 不匹配则清空
      if (expectedUserId !== null && cached.userId !== undefined && cached.userId !== expectedUserId) {
        console.warn(
          `[useMetaCache] Cache "${cacheKey}" was for user_id=${cached.userId}, ` +
          `current user_id=${expectedUserId}, clearing stale cache.`
        )
        clearCache()
        return null
      }

      return cached
    } catch (e) {
      console.warn(`[useMetaCache] Failed to read cache "${cacheKey}":`, e)
      return null
    }
  }

  function setCache(newData, version = null, userId = null) {
    try {
      const cacheEntry = {
        data: newData,
        timestamp: Date.now(),
        version,
        userId
      }
      localStorage.setItem(cacheKey, JSON.stringify(cacheEntry))
    } catch (e) {
      console.warn(`[useMetaCache] Failed to write cache "${cacheKey}":`, e)
    }
  }

  function clearCache() {
    try {
      localStorage.removeItem(cacheKey)
    } catch (e) {
      console.warn(`[useMetaCache] Failed to clear cache "${cacheKey}":`, e)
    }
  }

  async function fetch(apiPath, options = {}) {
    const {
      forceRefresh = false,
      onSuccess = null,
      onError = null,
      version = null,
      expectedVersion = null
    } = options

    loading.value = true
    error.value = null
    fromCache.value = false

    if (!forceRefresh) {
      const cached = getCache(expectedVersion)
      if (cached && cached.data) {
        data.value = cached.data
        fromCache.value = true
        loading.value = false
        return { success: true, data: cached.data, fromCache: true }
      }
    }

    try {
      const result = await apiV1.get(apiPath)

      if (result.success && result.data) {
        data.value = result.data
        const cacheVersion = version || result.data?.schema_version || null
        setCache(result.data, cacheVersion)

        if (onSuccess) {
          onSuccess(result.data)
        }

        return { success: true, data: result.data, fromCache: false }
      } else {
        throw new Error(result.message || 'API returned unsuccessful')
      }
    } catch (e) {
      error.value = e
      console.warn(`[useMetaCache] API fetch failed for "${cacheKey}":`, e)

      const cached = getCache()
      if (cached && cached.data) {
        data.value = cached.data
        fromCache.value = true

        if (onError) {
          onError(e, cached.data)
        }

        return { success: true, data: cached.data, fromCache: true, error: e }
      }

      if (onError) {
        onError(e, null)
      }

      return { success: false, error: e, fromCache: false }
    } finally {
      loading.value = false
    }
  }

  const isOffline = computed(() => fromCache.value && error.value !== null)
  const hasData = computed(() => data.value !== null)
  const needsRefresh = computed(() => cacheExpired.value || (!data.value && error.value))

  return {
    data,
    loading,
    error,
    fromCache,
    cacheExpired,
    isOffline,
    hasData,
    needsRefresh,
    fetch,
    setCache,
    clearCache,
    getCache
  }
}

export function useMenuCache() {
  return useMetaCache('menuCache', DEFAULT_TTL)
}

export function useHierarchyConfigCache() {
  return useMetaCache('hierarchyConfigCache', DEFAULT_TTL)
}

export default useMetaCache
