/**
 * 统一枚举加载服务
 *
 * 参考 SAP Fiori Elements Value Help 机制
 * 统一处理枚举类型加载、缓存、错误处理
 *
 * Phase 4 增强：支持双通道访问模式
 * - 高速读取通道：GET /api/v1/enums/{type}/options (L1缓存优先)
 * - 标准管理通道：GET /api/v1/enum-types/{id}/values (完整数据)
 *
 * FR-UI-TestFix-1: HTTP 调用迁移到 httpClient（消除直调 fetch，违反 C2 约束）
 *
 * @module services/enumService
 */

import { apiV1 } from '@/utils/httpClient'

/**
 * @typedef {Object} EnumOption
 * @property {string} value - 枚举值代码
 * @property {string} label - 枚举值显示名称
 * @property {string} [code] - 原始代码字段（向后兼容）
 * @property {string} [name] - 原始名称字段（向后兼容）
 */

/**
 * @typedef {Object} EnumServiceOptions
 * @property {Object} headers - 请求头
 * @property {boolean} cache - 是否缓存（默认 true）
 * @property {boolean} throwError - 是否抛出错误（默认 true）
 * @property {boolean} useHighSpeedEndpoint - 是否使用高速端点（默认 true）
 * @property {Object} filter - 额外过滤条件
 */

/**
 * 统一枚举加载服务
 */
const EnumService = {

  // 缓存存储（L1 内存缓存）
  _cache: new Map(),

  /**
   * 缓存超时时间（毫秒），默认 5 分钟
   */
  _cacheTimeout: 5 * 60 * 1000,

  /**
   * 最大缓存条目数（LRU 淘汰策略）
   */
  _maxCacheSize: 100,

  /**
   * 加载枚举选项（双通道访问）
   *
   * 默认使用高速端点，自动降级到标准端点
   *
   * @param {string} enumTypeId - 枚举类型 ID
   * @param {EnumServiceOptions} options - 加载选项
   * @returns {Promise<EnumOption[]>} 枚举选项数组
   * @throws {Error} 枚举类型 ID 无效或 API 调用失败
   *
   * @example
   * // 使用高速端点（默认）
   * const options = await EnumService.loadOptions('annotation_category');
   *
   * // 使用标准管理端点
   * const options = await EnumService.loadOptions('annotation_category', {
   *   useHighSpeedEndpoint: false
   * });
   */
  async loadOptions(enumTypeId, options = {}) {
    const {
      headers = {},
      cache = true,
      throwError = true,
      useHighSpeedEndpoint = true,
      filter = {}
    } = options;

    if (!enumTypeId) {
      const error = new Error('[EnumService] enumTypeId is required');
      if (throwError) throw error;
      console.error(error.message);
      return [];
    }

    // 检查缓存
    if (cache && this._cache.has(enumTypeId)) {
      const cached = this._cache.get(enumTypeId);
      if (Date.now() - cached.timestamp < this._cacheTimeout) {
        console.log(`[EnumService] Cache HIT for: ${enumTypeId}`);
        return cached.data;
      }
      this._cache.delete(enumTypeId);
    }

    try {
      let result;

      if (useHighSpeedEndpoint) {
        // 尝试高速端点
        result = await this._loadFromHighSpeedEndpoint(enumTypeId, headers, filter);

        if (!result.success && result.status === 404) {
          // 高速端点不可用，降级到标准端点
          console.warn(`[EnumService] High-speed endpoint not available, falling back to standard endpoint for: ${enumTypeId}`);
          result = await this._loadFromStandardEndpoint(enumTypeId, headers, filter);
        }
      } else {
        // 直接使用标准端点
        result = await this._loadFromStandardEndpoint(enumTypeId, headers, filter);
      }

      if (!result.success) {
        const error = new Error(
          `[EnumService] Failed to load enum ${enumTypeId}: ${result.message}`
        );
        if (throwError) throw error;
        console.error(error.message);
        return [];
      }

      const values = this._normalizeEnumValues(result.data?.data || []);

      if (cache) {
        this._addToCache(enumTypeId, values);
      }

      return values;

    } catch (error) {
      const err = error instanceof Error
        ? error
        : new Error(`[EnumService] Failed to load enum ${enumTypeId}`);

      if (throwError) throw err;
      console.error(err.message);
      return [];
    }
  },

  /**
   * 从高速端点加载枚举选项
   *
   * @param {string} enumTypeId - 枚举类型 ID
   * @param {Object} headers - 请求头
   * @param {Object} filter - 过滤条件
   * @returns {Promise<Object>} API 响应结果
   * @private
   */
  async _loadFromHighSpeedEndpoint(enumTypeId, headers, filter = {}) {
    const params = new URLSearchParams({
      is_active: 'true',
      pageSize: '1000',
      ...filter
    });

    const path = `/enums/${enumTypeId}/options?${params.toString()}`;

    // httpClient 返回 { success, data, message, httpStatus, traceId }
    // 此函数需要向后兼容：result.data 应包含原 response body（含 data 数组）
    const result = await apiV1.get(path, { headers });
    return {
      success: result.success,
      status: result.httpStatus,
      message: result.message,
      // 包装为旧接口期望的 { data: { data: [...] } } 形式
      data: { data: result.data, success: result.success, message: result.message }
    };
  },

  /**
   * 从标准管理端点加载枚举选项
   *
   * @param {string} enumTypeId - 枚举类型 ID
   * @param {Object} headers - 请求头
   * @param {Object} filter - 过滤条件
   * @returns {Promise<Object>} API 响应结果
   * @private
   */
  async _loadFromStandardEndpoint(enumTypeId, headers, filter = {}) {
    const params = new URLSearchParams({
      is_active: 'true',
      pageSize: '1000',
      ...filter
    });

    const path = `/enum-types/${enumTypeId}/values?${params.toString()}`;

    // httpClient 返回 { success, data, message, httpStatus, traceId }
    const result = await apiV1.get(path, { headers });
    return {
      success: result.success,
      status: result.httpStatus,
      message: result.message,
      // 包装为旧接口期望的 { data: { data: [...] } } 形式
      data: { data: result.data, success: result.success, message: result.message }
    };
  },
  
  /**
   * 规范化枚举值格式
   *
   * 将 API 返回的各种格式统一转换为 {value, label} 格式
   * 同时保留原始字段以支持向后兼容
   *
   * @param {Array} rawValues - 原始枚举值数组
   * @returns {EnumOption[]} 规范化后的枚举选项
   * @private
   *
   * @example
   * const normalized = EnumService._normalizeEnumValues([
   *   {code: 'important', name: 'IMPORTANT'},
   *   {value: 'warning', label: 'WARNING'}
   * ]);
   * // [{value: 'important', label: 'IMPORTANT', code: 'important', name: 'IMPORTANT'}, ...]
   */
  _normalizeEnumValues(rawValues) {
    if (!Array.isArray(rawValues)) {
      console.warn('[EnumService] Expected array, got:', typeof rawValues);
      return [];
    }

    return rawValues.map(v => ({
      value: v.code || v.value || '',
      label: v.name || v.label || '',
      // 保留原始字段以支持向后兼容
      code: v.code || v.value || '',
      name: v.name || v.label || ''
    }));
  },

  /**
   * 添加到缓存（带 LRU 淘汰策略）
   *
   * @param {string} enumTypeId - 枚举类型 ID
   * @param {EnumOption[]} values - 枚举选项数组
   * @private
   */
  _addToCache(enumTypeId, values) {
    // LRU 淘汰策略：如果超过最大缓存大小，删除最旧的条目
    if (this._cache.size >= this._maxCacheSize && !this._cache.has(enumTypeId)) {
      const oldestKey = this._cache.keys().next().value;
      this._cache.delete(oldestKey);
      console.log(`[EnumService] LRU eviction: removed ${oldestKey}`);
    }

    this._cache.set(enumTypeId, {
      data: values,
      timestamp: Date.now()
    });
    console.log(`[EnumService] Cached ${values.length} options for: ${enumTypeId}`);
  },
  
  /**
   * 清除所有缓存
   */
  clearCache() {
    const size = this._cache.size;
    this._cache.clear();
  },

  /**
   * 清除指定枚举的缓存
   *
   * @param {string} enumTypeId - 枚举类型 ID
   */
  clearCacheFor(enumTypeId) {
    if (this._cache.has(enumTypeId)) {
      this._cache.delete(enumTypeId);
      console.log(`[EnumService] Cache cleared for: ${enumTypeId}`);
    }
  },

  /**
   * 预加载多个枚举（使用高速端点）
   *
   * @param {string[]} enumTypeIds - 枚举类型 ID 数组
   * @param {EnumServiceOptions} options - 加载选项
   * @returns {Promise<Map<string, EnumOption[]>>} 枚举选项映射
   *
   * @example
   * const optionsMap = await EnumService.preload([
   *   'annotation_category',
   *   'relation_type'
   * ]);
   * console.log(optionsMap.get('annotation_category'));
   */
  async preload(enumTypeIds, options = {}) {
    if (!Array.isArray(enumTypeIds) || enumTypeIds.length === 0) {
      console.warn('[EnumService] preload: enumTypeIds must be a non-empty array');
      return new Map();
    }

    // 使用高速端点进行批量预加载
    const preloadOptions = {
      ...options,
      useHighSpeedEndpoint: true,
      cache: true
    };

    const results = await Promise.all(
      enumTypeIds.map(id => this.loadOptions(id, preloadOptions))
    );

    const optionsMap = new Map();
    enumTypeIds.forEach((id, index) => {
      optionsMap.set(id, results[index]);
    });

    console.log(`[EnumService] Preloaded ${enumTypeIds.length} enums`);
    return optionsMap;
  },
  
  /**
   * 获取缓存状态（包含性能指标）
   *
   * @returns {Object} 缓存状态信息
   */
  getCacheStatus() {
    const entries = [];
    let hitCount = 0;
    let missCount = 0;
    let expiredCount = 0;

    this._cache.forEach((value, key) => {
      const age = Date.now() - value.timestamp;
      const expired = age > this._cacheTimeout;

      entries.push({
        enumTypeId: key,
        size: value.data.length,
        age,
        ageFormatted: this._formatAge(age),
        expired
      });

      if (expired) {
        expiredCount++;
      } else {
        hitCount++;
      }
    });

    missCount = this._maxCacheSize - this._cache.size;

    return {
      total: this._cache.size,
      maxSize: this._maxCacheSize,
      utilization: `${((this._cache.size / this._maxCacheSize) * 100).toFixed(1)}%`,
      hitRate: this._cache.size > 0 ? `${((hitCount / (hitCount + missCount)) * 100).toFixed(1)}%` : 'N/A',
      entries,
      performance: {
        hitCount,
        missCount,
        expiredCount,
        averageAge: entries.length > 0
          ? Math.round(entries.reduce((sum, e) => sum + e.age, 0) / entries.length)
          : 0
      }
    };
  },

  /**
   * 格式化缓存年龄
   *
   * @param {number} ageMs - 年龄（毫秒）
   * @returns {string} 格式化的年龄字符串
   * @private
   */
  _formatAge(ageMs) {
    const seconds = Math.floor(ageMs / 1000);
    const minutes = Math.floor(seconds / 60);

    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    }
    return `${seconds}s`;
  },

  /**
   * 设置缓存超时时间
   *
   * @param {number} timeout - 超时时间（毫秒）
   */
  setCacheTimeout(timeout) {
    this._cacheTimeout = timeout;
  },

  /**
   * 设置最大缓存大小
   *
   * @param {number} maxSize - 最大缓存条目数
   */
  setMaxCacheSize(maxSize) {
    this._maxCacheSize = maxSize;
  },

  // ========== 性能监控 ==========

  /**
   * 性能统计计数器
   */
  _stats: {
    totalRequests: 0,
    cacheHits: 0,
    cacheMisses: 0,
    highSpeedEndpointHits: 0,
    standardEndpointFallbacks: 0,
    errors: 0
  },

  /**
   * 获取性能统计信息
   *
   * @returns {Object} 性能统计
   */
  getPerformanceStats() {
    const { totalRequests, cacheHits, cacheMisses } = this._stats;

    return {
      ...this._stats,
      cacheHitRate: totalRequests > 0
        ? `${((cacheHits / (cacheHits + cacheMisses)) * 100).toFixed(2)}%`
        : 'N/A',
      endpointUsage: {
        highSpeed: this._stats.highSpeedEndpointHits,
        standardFallback: this._stats.standardEndpointFallbacks
      }
    };
  },

  /**
   * 重置性能统计
   */
  resetPerformanceStats() {
    this._stats = {
      totalRequests: 0,
      cacheHits: 0,
      cacheMisses: 0,
      highSpeedEndpointHits: 0,
      standardEndpointFallbacks: 0,
      errors: 0
    };
  }
};

export default EnumService;
export { EnumService };
