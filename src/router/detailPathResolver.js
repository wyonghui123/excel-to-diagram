/**
 * 详情页路由统一解析器（FR-007）
 *
 * 唯一职责：给定业务对象类型（可选 id），产出详情页路径。
 * 优先级：显式传入的 detail_path > metaConfig.list.detail_path > 默认 `/detail/<objectType>`。
 * 除本文件外，src/ 下不得再用「/detail/ + 变量」的方式手工拼接详情路径。
 */

import metaService from '@/services/metaService'

const DEFAULT_DETAIL_PREFIX = '/detail'

/**
 * 解析详情页基础路径（不含 id）。
 * @param {string} objectType 业务对象类型
 * @param {object} [options]
 * @param {string} [options.detailPath] 调用方已知的 detail_path（如已加载的 listConfig.detail_path）
 * @returns {string}
 */
export function resolveDetailBasePath(objectType, options = {}) {
  const explicitPath = options.detailPath
  if (explicitPath) return explicitPath

  const viewConfig = objectType ? metaService.getViewConfigSync(objectType) : null
  const configuredPath = viewConfig?.data?.list?.detail_path
  if (configuredPath) return configuredPath

  return `${DEFAULT_DETAIL_PREFIX}/${objectType}`
}

/**
 * 解析详情页完整路径。
 * @param {string} objectType 业务对象类型
 * @param {string|number} [id] 记录 id；为空时返回基础路径（如新建模式）
 * @param {object} [options] 同 resolveDetailBasePath
 * @returns {string}
 */
export function resolveDetailPath(objectType, id, options = {}) {
  const basePath = resolveDetailBasePath(objectType, options)
  if (id === undefined || id === null || id === '') return basePath
  return `${basePath}/${id}`
}

export default {
  resolveDetailBasePath,
  resolveDetailPath
}
