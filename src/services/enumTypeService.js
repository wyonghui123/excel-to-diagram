/**
 * Enum Type 服务 - 从后端 enum_types API 加载枚举值
 *
 * [FIX 2026-06-29] 改用项目现有 EnumService.loadOptions (RelationFilterSection 同款)
 *   原因: 自行实现的 fetch 调用与 RelationFilterSection 不一致,
 *         后端 enum_types 表里也确实没有 annotation_category 记录,
 *         EnumService 会自动降级到标准端点 + 缓存
 */

import EnumService from '@/services/enumService'

// [FIX 2026-06-29] EnumService 是对象字面量, 不是类 (enumService.js:38)
//   错误用法: new EnumService() → TypeError: EnumService is not a constructor
//   正确用法: 直接 import 后当对象调用 (RelationFilterSection 也是这样)

/**
 * 获取指定 enum_type 的所有值
 * @param {string} enumTypeCode - 枚举类型代码 (如 'annotation_category')
 * @returns {Promise<Array<{value: string, label: string}>>} 枚举选项
 *
 * 主线不受影响: 失败时返回空数组, 调用方需自行处理 UI 降级
 */
export async function fetchEnumTypeValues(enumTypeCode) {
  try {
    // [FIX 2026-06-29] 改用 EnumService.loadOptions
    //   - 与 RelationFilterSection 一致 (Vue 组件已经在用)
    //   - 自动降级 (高速端点 404 -> 标准端点)
    //   - 自动缓存
    //   - throwError=false 让失败时不抛异常, 而是返回空数组
    const items = await EnumService.loadOptions(enumTypeCode, {
      cache: true,
      throwError: false,
      useHighSpeedEndpoint: true,
    })

    if (!Array.isArray(items)) {
      return []
    }

    // EnumService._normalizeEnumValues 已统一格式为 {value, label, count}
    return items.map((v) => ({
      value: v.value || v.code,
      label: v.label || v.name || v.code,
    }))
  } catch (e) {
    console.error(`[enumTypeService] Error loading ${enumTypeCode}:`, e)
    return []
  }
}