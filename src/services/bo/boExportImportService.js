import { BOBaseService } from '@/services/bo/boBaseService'
import { downloadBlob } from '@/utils/httpClient'

export class BOExportImportService extends BOBaseService {
  /**
   * 将完整 URL 路径转换为 _request 可用的相对路径
   * 服务端返回的 download_url 包含 /api/v1 前缀，_request 会自动添加
   */
  _toRelativePath(fullPath) {
    return fullPath.replace(/^\/api\/v[12]/, '')
  }

  // [NEW v3.20 2026-06-19] 从后端 download_url 提取文件 basename
  // 后端 export_data 已返回包含 objectname 的 file_name (如 架构数据_20260619_xxx.xlsx)
  _filenameFromUrl(downloadUrl, fallback) {
    if (!downloadUrl) return fallback
    try {
      const cleanUrl = downloadUrl.split('?')[0].split('#')[0]
      const lastSlash = cleanUrl.lastIndexOf('/')
      return decodeURIComponent(cleanUrl.substring(lastSlash + 1)) || fallback
    } catch (e) {
      return fallback
    }
  }

  async downloadTemplate(objectType, params = {}) {
    const types = params.selected_types || [objectType]

    const requestBody = {
      object_type: objectType,
      scope: 'template',
      selected_types: types,
      options: {
        include_hierarchy_path: false,
        include_hierarchy_ids: true,
        include_operation_mode: true,
        protect_sheet: false,
        include_readonly: true,
        include_annotations: false,
        include_child_objects: false
      }
    }
    if (params.menu_code) requestBody.menu_code = params.menu_code

    const result = await this._request('POST', '/export', { body: requestBody, version: 1 })

    if (result.success && result.data?.download_url) {
      const downloadPath = this._toRelativePath(result.data.download_url)
      const downloadResult = await this._request('GET', downloadPath, { responseType: 'blob', version: 1 })
      if (!downloadResult.success) return { success: false, message: '下载模板失败' }
      // [CHG v3.20 2026-06-19] 用后端生成的文件名 (基于 objectname + 时间戳)
      const filename = this._filenameFromUrl(result.data.download_url, 'import_template.xlsx')
      downloadBlob(downloadResult.data, filename)
      return { success: true }
    }

    return result
  }

  async previewImport(objectType, file, options = {}) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', 'preview')
    formData.append('conflict_strategy', options.conflictStrategy || 'upsert')
    // [FIX 2026-06-16 BMRD] preview 也必须传 context, 否则后端 validate_sheets
    // 不会跳过 product_code/version_code 必填验证
    if (options.version_id) formData.append('version_id', options.version_id)
    if (options.product_id) formData.append('product_id', options.product_id)
    if (options.cascade_fields?.length) {
      formData.append('cascade_fields', JSON.stringify(options.cascade_fields))
    }

    return this._request('POST', '/import', { body: formData, version: 1 })
  }

  async exportData(objectType, params = {}) {
    const requestBody = {
      object_type: objectType,
      scope: params.scope || 'single',
      filters: params.filters || {},
      options: {
        include_hierarchy_path: true,
        include_hierarchy_ids: true,
        include_metadata_sheet: true,
        protect_sheet: false,
        ...(params.options || {})
      }
    }

    if (params.selected_types?.length) {
      requestBody.selected_types = params.selected_types
    }

    // [NEW v3.20 2026-06-19] 透传 menu_code (arch-data → 后端走"架构数据"前缀)
    if (params.menu_code) {
      requestBody.menu_code = params.menu_code
    }

    if (params.ordering) {
      const isDesc = params.ordering.startsWith('-')
      requestBody.sort_by = isDesc ? params.ordering.substring(1) : params.ordering
      requestBody.sort_order = isDesc ? 'desc' : 'asc'
    }

    if (params.page !== undefined && params.page_size !== undefined) {
      requestBody.page = params.page
      requestBody.page_size = params.page_size
    }

    if (params.fields) {
      requestBody.options.fields = params.fields.split(',')
    }

    const result = await this._request('POST', '/export', { body: requestBody, version: 1 })

    if (result.success && result.data?.download_url) {
      const downloadPath = this._toRelativePath(result.data.download_url)

      const downloadResult = await this._request('GET', downloadPath, { responseType: 'blob', version: 1 })

      if (!downloadResult.success) {
        return { success: false, message: '下载文件失败' }
      }

      // [CHG v3.20 2026-06-19] 用后端基于 objectname 拼的文件名, 替代前端硬编码 ${objectType}_export_${date}.xlsx
      const filename = this._filenameFromUrl(result.data.download_url, `${objectType}_export.xlsx`)
      downloadBlob(downloadResult.data, filename)

      return { success: true, total_rows: result.data.total_rows }
    }

    return result
  }

  async exportDataAsync(objectType, params = {}) {
    const requestBody = {
      object_type: objectType,
      scope: params.scope || 'single',
      filters: params.filters || {},
      options: {
        include_hierarchy_path: true,
        include_hierarchy_ids: true,
        include_metadata_sheet: true,
        protect_sheet: false,
        ...(params.options || {})
      }
    }

    if (params.selected_types?.length) {
      requestBody.selected_types = params.selected_types
    }

    // [NEW v3.20 2026-06-19] 透传 menu_code
    if (params.menu_code) {
      requestBody.menu_code = params.menu_code
    }

    if (params.ordering) {
      const isDesc = params.ordering.startsWith('-')
      requestBody.sort_by = isDesc ? params.ordering.substring(1) : params.ordering
      requestBody.sort_order = isDesc ? 'desc' : 'asc'
    }

    if (params.page !== undefined && params.page_size !== undefined) {
      requestBody.page = params.page
      requestBody.page_size = params.page_size
    }

    return this._request('POST', '/export/async', { body: requestBody, version: 1 })
  }

  async getExportStatus(taskId) {
    return this._request('GET', `/export/status/${taskId}`, { version: 1 })
  }

  async downloadExportFile(downloadUrl, filename) {
    const downloadPath = this._toRelativePath(downloadUrl)
    const downloadResult = await this._request('GET', downloadPath, { responseType: 'blob', version: 1 })

    if (!downloadResult.success) {
      return { success: false, message: '下载文件失败' }
    }

    downloadBlob(downloadResult.data, filename || 'export.xlsx')
    return { success: true }
  }

  async importData(objectType, file, options = {}) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', 'execute')
    formData.append('conflict_strategy', options.conflictStrategy || 'upsert')

    if (options.validate) formData.append('validate', 'true')
    if (options.skipErrors) formData.append('skip_errors', 'true')
    if (options.updateExisting) formData.append('update_existing', 'true')

    return this._request('POST', '/import', { body: formData, version: 1 })
  }

  async importDataAsync(file, conflictStrategy = 'upsert', context = {}) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('conflict_strategy', conflictStrategy)
    if (context.version_id) formData.append('version_id', context.version_id)
    if (context.product_id) formData.append('product_id', context.product_id)
    if (context.cascade_fields?.length) {
      formData.append('cascade_fields', JSON.stringify(context.cascade_fields))
    }

    return this._request('POST', '/import/async', { body: formData, version: 1 })
  }

  async getImportStatus(taskId) {
    return this._request('GET', `/import/status/${taskId}`, { version: 1 })
  }
}
