/**
 * Enum Type 服务 - 从后端 enum_types API 加载枚举值
 */

/**
 * 获取指定 enum_type 的所有值
 * @param {string} enumTypeCode - 枚举类型代码 (如 'annotation_category')
 * @returns {Promise<Array<{value: string, label: string}>>} 枚举选项
 *
 * 主线不受影响: 失败时返回空数组, 调用方需自行处理 UI 降级
 */
export async function fetchEnumTypeValues(enumTypeCode) {
  try {
    const response = await fetch(`/api/v1/enum_types/${enumTypeCode}`)

    if (!response.ok) {
      console.warn(`[enumTypeService] Failed to load ${enumTypeCode}: HTTP ${response.status}`)
      return []
    }

    const json = await response.json()
    // 兼容多种响应格式: { data: { values: [...] } } 或 { data: [...] } 或 [...]
    const values = json?.data?.values || json?.data || []

    if (!Array.isArray(values)) {
      return []
    }

    return values.map((v) => ({
      value: v.code || v.value,
      label: v.display_name || v.label || v.code || v.value,
    }))
  } catch (e) {
    console.error(`[enumTypeService] Error loading ${enumTypeCode}:`, e)
    return []
  }
}