/**
 * 校验错误归一化（spec-error-warning-framework FR-005）。
 *
 * 后端统一错误信封中的 `errors[]` 形如：
 *   { field_id, field_name, rule, message, error_code, i18n_key, params }
 *
 * 前端需要两件事：
 *   1. 按字段定位（field_id 与表单 key 一致）→ 字段级高亮 + 文案；
 *   2. 去重后的消息列表 → 汇总提示（toast / 面板）。
 *
 * 兼容旧式 `details[]`（无 field_id 时退回 field_name），并忽略空项。
 */

function _pick(item, ...keys) {
  for (const key of keys) {
    const value = item?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return ''
}

/**
 * @param {object|null} result - boService 返回的 { success, message, errors?, details? }
 * @returns {{ fieldErrors: Record<string, string>, messages: string[] }}
 */
export function normalizeValidationErrors(result) {
  const raw = Array.isArray(result?.errors) && result.errors.length > 0
    ? result.errors
    : (Array.isArray(result?.details) ? result.details : [])

  const fieldErrors = {}
  const messages = []
  const seen = new Set()

  for (const item of raw) {
    if (!item || typeof item !== 'object') continue

    const fieldKey = String(_pick(item, 'field_id', 'fieldId', 'field_name', 'fieldName'))
    const text = String(_pick(item, 'message', 'msg'))
    if (!text) continue

    const dedupeKey = `${fieldKey}|${_pick(item, 'rule')}|${text}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)

    if (fieldKey && !fieldErrors[fieldKey]) {
      fieldErrors[fieldKey] = text
    }
    if (!messages.includes(text)) messages.push(text)
  }

  return { fieldErrors, messages }
}

export default normalizeValidationErrors