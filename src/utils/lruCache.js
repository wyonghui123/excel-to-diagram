/**
 * LRU Cache - 带超时和最大条目限制的缓存
 */

export class LRUCache {
  constructor(maxSize = 100) {
    this.maxSize = maxSize
    this.cache = new Map()
  }

  get(key) {
    if (!this.cache.has(key)) return null
    const value = this.cache.get(key)
    if (Date.now() - value.timestamp < value.timeout) {
      this.cache.delete(key)
      this.cache.set(key, value)
      return value.data
    }
    this.cache.delete(key)
    return null
  }

  set(key, data, timeout = 5 * 60 * 1000) {
    if (this.cache.has(key)) {
      this.cache.delete(key)
    }
    this.cache.set(key, { data, timestamp: Date.now(), timeout })
    while (this.cache.size > this.maxSize) {
      const firstKey = this.cache.keys().next().value
      this.cache.delete(firstKey)
    }
  }

  delete(key) {
    this.cache.delete(key)
  }

  deleteByPrefix(prefix) {
    for (const key of this.cache.keys()) {
      if (key.startsWith(prefix)) {
        this.cache.delete(key)
      }
    }
  }

  clear() {
    this.cache.clear()
  }

  get size() {
    return this.cache.size
  }
}
