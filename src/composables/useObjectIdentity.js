/**
 * 对象标识 Composable
 * 
 * 提供对象标识查询和缓存能力
 * 支持单个查询、批量查询和格式化输出
 */

import { ref, computed } from 'vue'

import { apiV1 } from '@/utils/httpClient'

export function useObjectIdentity() {
  const identityCache = ref(new Map())
  const loading = ref(false)
  const error = ref(null)
  
  /**
   * 获取单个对象的完整身份标识
   * 
   * @param {string} objectType - 对象类型
   * @param {number|string} objectId - 对象 ID
   * @param {object} options - 选项
   * @param {string} options.format - 输出格式 ('full', 'short', 'minimal', 'technical', 'detailed')
   * @param {boolean} options.includeTechnical - 是否包含技术信息
   * @param {boolean} options.useCache - 是否使用缓存（默认 true）
   * @returns {Promise<object>} 身份标识对象
   */
  async function getIdentity(objectType, objectId, options = {}) {
    const {
      format = 'full',
      includeTechnical = false,
      useCache = true
    } = options
    
    const cacheKey = `${objectType}:${objectId}:${format}:${includeTechnical}`
    
    if (useCache && identityCache.value.has(cacheKey)) {
      return identityCache.value.get(cacheKey)
    }
    
    loading.value = true
    error.value = null
    
    try {
      const params = new URLSearchParams({
        object_type: objectType,
        object_id: String(objectId),
        format,
        include_technical: String(includeTechnical)
      })
      
      const result = await apiV1.get(`/identity?${params}`)

      if (!result.success) {
        throw new Error(result.message || 'Failed to get identity')
      }

      if (useCache) {
        identityCache.value.set(cacheKey, result.data)
      }

      return result.data
      
    } catch (err) {
      error.value = err.message
      console.error('Failed to get identity:', err)
      throw err
      
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 批量获取对象标识
   * 
   * @param {array} requests - 请求列表 [{object_type, object_id}, ...]
   * @param {object} options - 选项
   * @param {string} options.format - 输出格式
   * @param {boolean} options.includeTechnical - 是否包含技术信息
   * @param {boolean} options.useCache - 是否使用缓存
   * @returns {Promise<map>} 映射字典 Map<key, identity>
   */
  async function batchGetIdentities(requests, options = {}) {
    const {
      format = 'full',
      includeTechnical = false,
      useCache = true
    } = options
    
    const uncachedRequests = []
    const cachedResults = new Map()
    
    if (useCache) {
      for (const req of requests) {
        const cacheKey = `${req.object_type}:${req.object_id}:${format}:${includeTechnical}`
        
        if (identityCache.value.has(cacheKey)) {
          cachedResults.set(cacheKey, identityCache.value.get(cacheKey))
        } else {
          uncachedRequests.push(req)
        }
      }
    } else {
      uncachedRequests.push(...requests)
    }
    
    if (uncachedRequests.length === 0) {
      return cachedResults
    }
    
    loading.value = true
    error.value = null
    
    try {
      const result = await apiV1.post('/identity/batch', {
        requests: uncachedRequests,
        format,
        include_technical: includeTechnical
      })

      if (!result.success) {
        throw new Error(result.message || 'Failed to get batch identities')
      }

      const results = new Map(cachedResults)

      for (const [key, value] of Object.entries(result.data)) {
        const match = key.match(/\((\w+),\s*(\d+)\)/)
        if (match) {
          const [, objectType, objectId] = match
          const cacheKey = `${objectType}:${objectId}:${format}:${includeTechnical}`
          
          results.set(cacheKey, value)
          
          if (useCache) {
            identityCache.value.set(cacheKey, value)
          }
        }
      }
      
      return results
      
    } catch (err) {
      error.value = err.message
      console.error('Failed to get batch identities:', err)
      throw err
      
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 获取格式化的对象标识字符串
   * 
   * @param {string} objectType - 对象类型
   * @param {number|string} objectId - 对象 ID
   * @param {string} format - 输出格式
   * @returns {Promise<string>} 格式化的标识字符串
   */
  async function getFormattedIdentity(objectType, objectId, format = 'short') {
    loading.value = true
    error.value = null
    
    try {
      const params = new URLSearchParams({
        object_type: objectType,
        object_id: String(objectId),
        format
      })
      
      const result = await apiV1.get(`/identity/formatted?${params}`)

      if (!result.success) {
        throw new Error(result.message || 'Failed to get formatted identity')
      }

      return result.data.formatted
      
    } catch (err) {
      error.value = err.message
      console.error('Failed to get formatted identity:', err)
      throw err
      
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 清空缓存
   */
  function clearCache() {
    identityCache.value.clear()
  }
  
  /**
   * 清空服务端缓存
   */
  async function clearServerCache() {
    try {
      const result = await apiV1.post('/identity/cache/clear')

      if (!result.success) {
        throw new Error(result.message || 'Failed to clear server cache')
      }

      clearCache()

      return result
      
    } catch (err) {
      error.value = err.message
      console.error('Failed to clear server cache:', err)
      throw err
    }
  }
  
  /**
   * 获取缓存大小
   */
  const cacheSize = computed(() => identityCache.value.size)
  
  return {
    getIdentity,
    batchGetIdentities,
    getFormattedIdentity,
    clearCache,
    clearServerCache,
    loading,
    error,
    cacheSize
  }
}
