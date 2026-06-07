import { ref } from 'vue'

import { apiV1 } from '@/utils/httpClient'
import { downloadBlob } from '@/utils/httpClient'

export function useImportExportApi() {
  const loading = ref(false)
  const error = ref(null)

  async function request(url, options = {}) {
    const { method = 'GET', body = null } = options

    let result
    if (method === 'POST') {
      result = await apiV1.post(url, { body })
    } else {
      result = await apiV1.get(url)
    }

    if (!result.success) {
      const err = new Error(result.message || 'HTTP Error')
      err.status = result.httpStatus
      throw err
    }

    return result.data
  }

  async function get(url) {
    return request(url, { method: 'GET' })
  }

  async function post(url, body) {
    return request(url, { method: 'POST', body })
  }

  const importData = async (file, mode = 'preview', conflictStrategy = 'upsert', context = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)
    formData.append('conflict_strategy', conflictStrategy)

    if (context) {
      Object.keys(context).forEach(key => {
        if (context[key] !== undefined && context[key] !== null) {
          formData.append(key, context[key])
        }
      })
    }

    const result = await apiV1.post('/import', { body: formData })

    if (!result.success) {
      const err = new Error(result.message || 'HTTP Error')
      err.status = result.httpStatus
      throw err
    }

    return result.data || result
  }

  const importDataAsync = async (file, conflictStrategy = 'upsert', context = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('conflict_strategy', conflictStrategy)

    if (context) {
      Object.keys(context).forEach(key => {
        if (context[key] !== undefined && context[key] !== null) {
          formData.append(key, context[key])
        }
      })
    }

    const result = await apiV1.post('/import/async', { body: formData })

    if (!result.success) {
      const err = new Error(result.message || 'HTTP Error')
      err.status = result.httpStatus
      throw err
    }

    return result.data || result
  }

  const getImportStatus = async (taskId) => {
    return get('/import/status/' + taskId)
  }

  const downloadImportTemplate = async (objectType, context = {}) => {
    let path = `/import/template/${objectType}`
    const params = []

    if (context) {
      Object.keys(context).forEach(key => {
        if (context[key] !== undefined && context[key] !== null) {
          params.push(key + '=' + encodeURIComponent(context[key]))
        }
      })
    }

    if (params.length > 0) {
      path += '?' + params.join('&')
    }

    const result = await apiV1.download(path)

    if (!result.success) {
      throw new Error('下载模板失败: ' + (result.message || 'unknown'))
    }

    downloadBlob(result.data, objectType + '_template.xlsx')
  }

  const getImportExportConfig = async (objectType) => {
    return get('/import-export/config/' + objectType)
  }

  const exportData = async (objectType, options = {}) => {
    const params = {
      object_type: objectType,
      ...options,
    }

    return post('/export', params)
  }

  return {
    loading,
    error,
    importData,
    importDataAsync,
    getImportStatus,
    downloadImportTemplate,
    getImportExportConfig,
    exportData,
  }
}
