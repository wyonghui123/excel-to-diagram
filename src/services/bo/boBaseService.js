import { BaseService } from '@/services/baseService'

export class BOBaseService extends BaseService {
  _normalizeParams(params) {
    const result = { ...params }
    if ('pageSize' in result) {
      result.page_size = result.pageSize
      delete result.pageSize
    }
    return result
  }

  _stableStringify(obj) {
    if (obj === null || obj === undefined) return ''
    if (typeof obj !== 'object') return String(obj)
    const sorted = {}
    Object.keys(obj).sort().forEach(key => {
      sorted[key] = this._stableStringify(obj[key])
    })
    return JSON.stringify(sorted)
  }

  _clearRecordCache(objectType, recordId) {
    this.cache.delete(`${objectType}:read:${recordId}`)
    this.cache.delete(`${objectType}:read:${String(recordId)}`)
    this.cache.deleteByPrefix(`${objectType}:query:`)
    this.cache.deleteByPrefix(`${objectType}:assoc:`)
  }

  _clearListCache(objectType) {
    this.cache.deleteByPrefix(`${objectType}:query:`)
  }
}
