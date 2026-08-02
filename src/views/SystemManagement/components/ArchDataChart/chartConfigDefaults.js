/**
 * [T1 2026-08-02] chartConfig 默认值统一工厂
 * ================================================================
 * 背景: 之前 RelationshipManagement / EmbeddedChartView fallback /
 *       ArchDataChartSwitcher 三处各写一份默认值, 字段漂移导致排查困难
 *       (已踩坑: Phase 1 fallback 字段对齐 layoutEngine→engine / preserveOrder)。
 * 用法: 三处统一 `reactive(createDefaultChartConfig())`, 修改默认值只需改本文件。
 */
export function createDefaultChartConfig() {
  return {
    chartType: 'businessObject',
    colorScheme: 'default',
    colorGroupBy: 'domain',
    centerScopeHighlight: true,
    annotationCategoryFilter: [],
    layoutEngine: 'elk',
    direction: 'TD',
    layoutControl: {
      enabled: true,
      layoutType: 'default',
      overallDirection: 'TB',
      engine: 'elk',
      preserveOrder: true,
      groups: []
    }
  }
}
