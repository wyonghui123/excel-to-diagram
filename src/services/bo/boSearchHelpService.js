import { BOBaseService } from '@/services/bo/boBaseService'

export class BOSearchHelpService extends BOBaseService {
  async searchValueHelp(sourceType, sourceId, params = {}) {
    const queryParams = new URLSearchParams()
    if (params.search) queryParams.set('search', params.search)
    if (params.search_fields) queryParams.set('search_fields', params.search_fields)
    if (params.page) queryParams.set('page', params.page)
    if (params.pageSize) queryParams.set('page_size', params.pageSize)
    if (params.sort) queryParams.set('sort', params.sort)
    if (params.filters) {
      Object.entries(params.filters).forEach(([key, value]) => {
        if (value === null || value === undefined) {
          queryParams.set(`filters[${key}]`, 'null')
        } else {
          queryParams.set(`filters[${key}]`, value)
        }
      })
    }
    if (params.value_field) queryParams.set('value_field', params.value_field)
    if (params.display_field) queryParams.set('display_field', params.display_field)
    if (params.code_field) queryParams.set('code_field', params.code_field)
    if (params.value_filter && Object.keys(params.value_filter).length > 0) {
      queryParams.set('value_filter', JSON.stringify(params.value_filter))
    }
    if (params.hierarchy && Object.keys(params.hierarchy).length > 0) {
      queryParams.set('hierarchy', JSON.stringify(params.hierarchy))
    }
    // [V1.2.1 2026-06-16] 传递 apply_target_permissions 参数
    // 跨域关系创建的级联字段 ValueHelp 需要跳过 dim scope 过滤
    if (params.apply_target_permissions !== undefined) {
      queryParams.set('apply_target_permissions', String(params.apply_target_permissions))
    }

    const path = `/value-help/${sourceType}/${sourceId}?${queryParams.toString()}`
    return this._request('GET', path)
  }

  async resolveValueHelp(sourceType, sourceId, value, params = {}) {
    const queryParams = new URLSearchParams()
    queryParams.set('value', value)
    if (params.value_field) queryParams.set('value_field', params.value_field)
    if (params.display_field) queryParams.set('display_field', params.display_field)
    if (params.code_field) queryParams.set('code_field', params.code_field)

    const path = `/value-help/${sourceType}/${sourceId}/resolve?${queryParams.toString()}`
    return this._request('GET', path)
  }
}
