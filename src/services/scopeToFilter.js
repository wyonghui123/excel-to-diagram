/**
 * scopeToFilter.js - scopeIds → filter 转换工具集
 *
 * 所属模块：架构数据管理页（嵌入式图表视图数据流）
 *
 * 提供三个纯函数，把 useMultiObjectPage 持有的 scopeIds (reactive)
 * 转换成下游组件/接口需要的 filter 格式：
 *   1. buildHierarchyFilterFromScope: scopeIds → fetchPreviewData hierarchyFilter
 *      (用于 7/30 之前 useReactiveRenderer 路线 + 懒加载降级链路)
 *   2. buildAnnotationFilterFromScope: scopeIds → 备注类型过滤数组
 *      (用于 EmbeddedChartView 7/31 22:31 大重构版 annotationConfig.annoCategoryFilter)
 *   3. buildRelationFilterFromScope: scopeIds → 关系范围过滤
 *
 * 契约来源：chart-data-flow-and-interaction-upgrade.md §5.3
 * 重建日期：2026-08-01 (Phase 6 restore)
 * 注: Trae History 中从未实际写过此文件 (Trae 内部开发过程中一直缺失)
 */
import { stripIdPrefix } from './archDataConverter.js'

/**
 * 把 scopeIds 转换成 fetchPreviewData 所需的 hierarchyFilter
 *
 * @param {Object} scopeIds - useMultiObjectPage.scopeIds
 * @returns {Object} hierarchyFilter = {
 *   domain_id: [...], sub_domain_id: [...],
 *   service_module_id: [...], business_object_id: [...]
 * }
 */
export function buildHierarchyFilterFromScope(scopeIds) {
  if (!scopeIds) return {}

  // 使用 effective（包含父级联动的有效范围），不用 selected
  // effective 已在 useMultiObjectPage.handleScopeChange 中正确计算
  const filter = {}

  // [FIX 2026-08-14] 剥离树节点 ID 前缀 (d_/s_/sm_/bo_), 防止 prefixed ID
  //   经懒加载降级链路 (useChartPreview.fallbackToLazyLoad) 进入 preview 请求导致后端 500
  const stripArr = (arr) => (Array.isArray(arr) ? arr.map(stripIdPrefix) : arr)

  if (scopeIds.domain?.effective?.length) {
    filter.domain_id = stripArr(scopeIds.domain.effective)
  }
  if (scopeIds.sub_domain?.effective?.length) {
    filter.sub_domain_id = stripArr(scopeIds.sub_domain.effective)
  }
  if (scopeIds.service_module?.effective?.length) {
    filter.service_module_id = stripArr(scopeIds.service_module.effective)
  }
  if (scopeIds.business_object?.effective?.length) {
    filter.business_object_id = stripArr(scopeIds.business_object.effective)
  }

  return filter
}

/**
 * 把 scopeIds 转换成"备注类型"过滤（globalFilters.annotation_category）
 *
 * @param {Object} scopeIds
 * @returns {Array<string>} annotation_category 值数组
 */
export function buildAnnotationFilterFromScope(scopeIds) {
  return scopeIds?.globalFilters?.annotation_category || []
}

/**
 * 把 scopeIds 转换成"关系范围"过滤（relationExtra）
 *
 * @param {Object} scopeIds
 * @returns {Object|null} 关系过滤条件，scopeIds 未设时返回 null
 */
export function buildRelationFilterFromScope(scopeIds) {
  if (!scopeIds?.relationExtra) return null
  const re = scopeIds.relationExtra
  if (!re.relationCodes?.length && !re.categoryTypes?.length) return null
  return {
    relationCodes: [...re.relationCodes],
    relationIds: [...re.relationIds],
    categoryTypes: [...re.categoryTypes],
    filterRelationCodes: [...re.filterRelationCodes]
  }
}
