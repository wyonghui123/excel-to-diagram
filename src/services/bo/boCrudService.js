import { BOBaseService } from '@/services/bo/boBaseService'

let _coordinator = null

export function setRefreshCoordinator(coordinator) {
  _coordinator = coordinator
}

export class BOCrudService extends BOBaseService {
  async create(objectType, data) {
    const result = await this._request('POST', `/bo/${objectType}`, { body: data })
    if (result.success) {
      this._clearListCache(objectType)
      _coordinator?.refreshAll()
    }
    return result
  }

  async read(objectType, id, options = {}) {
    const cacheKey = this._getCacheKey(objectType, 'read', id)
    if (!options.forceRefresh) {
      const cached = this._getCached(cacheKey)
      if (cached) return cached
    }

    const result = await this._request('GET', `/bo/${objectType}/${id}`)
    if (result.success) {
      this._setCache(cacheKey, result)
    }
    return result
  }

  async query(objectType, params = {}) {
    const cacheKey = this._getCacheKey(objectType, 'query', this._stableStringify(params))
    const cached = this._getCached(cacheKey)
    if (cached) {
      return cached
    }

    const normalizedParams = this._normalizeParams(params)

    const queryStr = new URLSearchParams(
      Object.entries(normalizedParams)
        .filter(([_, v]) => v !== undefined && v !== null && v !== '')
        .map(([k, v]) => [k, String(v)])
    ).toString()

    const path = queryStr ? `/bo/${objectType}?${queryStr}` : `/bo/${objectType}`

    let result = await this._request('GET', path)

    if (result.success) {
      this._setCache(cacheKey, result)
    } else {
      console.warn(`[boService] query failed:`, result.message || 'no message')
    }
    return result
  }

  async update(objectType, id, data) {
    const result = await this._request('PUT', `/bo/${objectType}/${id}`, { body: data })
    if (result.success) {
      this._clearRecordCache(objectType, id)
      _coordinator?.refreshAll()
    }
    return result
  }

  async delete(objectType, id) {
    const result = await this._request('DELETE', `/bo/${objectType}/${id}`)
    if (result.success) {
      this._clearRecordCache(objectType, id)
      _coordinator?.refreshAll()
    }
    return result
  }

  async executeAction(objectType, id, actionName, params = {}) {
    const result = await this._request('POST', `/bo/${objectType}/${id}/actions/${actionName}`, { body: params })
    if (result.success) {
      this._clearListCache(objectType)
    }
    return result
  }

  async deepInsert(objectType, parent, children = {}, options = {}) {
    const result = await this._request('POST', `/bo/${objectType}/deep`, {
      body: { parent, children, options }
    })

    if (!result.success && result.error_code === 'TRANSACTION_ROLLBACK') {
      console.warn('[DeepInsert] Transaction rolled back:', result.data?.failed_at, result.data?.reason)
    }

    if (result.success) {
      this._clearListCache(objectType)
    }
    return result
  }

  async batchCreate(objectType, items) {
    const result = await this._request('POST', `/bo/${objectType}/batch`, { body: { items } })
    if (result.success) {
      this._clearListCache(objectType)
    }
    return result
  }

  async batchDelete(objectType, ids) {
    const result = await this._request('POST', `/bo/${objectType}/batch-delete`, { body: { ids } })
    if (result.success) {
      this._clearListCache(objectType)
    }
    return result
  }

  async suggestKeyTemplateCode(objectType, fieldValues = {}, parentParams = {}) {
    return this._request('POST', `/key-template/preview/${objectType}`, {
      body: {
        field_values: fieldValues,
        parent_params: parentParams,
        generate: false
      }
    })
  }
}
