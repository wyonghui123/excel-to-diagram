/**
 * useMetaList/utils.js - 纯工具函数（无 setup 依赖, 无副作用）
 *
 * v3.6 Phase 3.1 拆分：从 useMetaList.js 提取
 *   风险: 0 (纯函数, 无 Vue 依赖, 无 setup 上下文)
 *
 * 不包含:
 *   - handleError (留在 useMetaList/index.js, 因为它依赖 i18nT + ElMessage)
 *   - any 响应式状态
 *   - 任何 composable 依赖
 *
 * 公共 API (供外部组件 / 其他子模块引用):
 *   - formatDate (被 AuditLogManagement / SystemAdmin / InlineEditCell 使用)
 *   - truncateText (MetaList 模板)
 *   - getStatusTagType (MetaList 模板)
 */

import { dateFormatService } from '@/services/DateFormatService'

/**
 * 格式化日期时间
 * @param {*} value - 日期值 (Date / string / timestamp)
 * @param {String} format - 格式化模式 (保留参数, 实际由 dateFormatService 决定)
 * @returns {String} 格式化后的字符串, 失败返回 '-'
 */
export function formatDate(value, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!value) return '-'

  const date = new Date(value)
  if (isNaN(date.getTime())) return '-'

  try {
    return dateFormatService.format(date)
  } catch (e) {
    return '-'
  }
}

/**
 * 截断文本（用于 ellipsis 类型列）
 * @param {String} text - 原始文本
 * @param {Number} maxLength - 最大长度
 * @returns {String} 截断后的文本, 空值返回 '-'
 */
export function truncateText(text, maxLength = 20) {
  if (!text) return '-'
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

/**
 * 获取状态标签类型（用于 status/badge 类型的列）
 * Element Plus tag type: 'success' | 'info' | 'warning' | 'danger' | 'primary'
 * @param {*} status - 状态值
 * @param {Object} colorMap - 状态→颜色映射 (覆盖默认)
 * @returns {String} Element Plus tag type, 默认 'info'
 */
export function getStatusTagType(status, colorMap = {}) {
  const map = {
    active: 'success',
    inactive: 'info',
    locked: 'danger',
    enabled: 'success',
    disabled: 'info',
    ...colorMap
  }
  return map[status] || 'info'
}
