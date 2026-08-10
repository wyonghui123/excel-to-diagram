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
    /**
     * @deprecated 2026-08-08 不再区分「业务对象图 / 服务模块图」。
     *   固定为 'businessObject'（嵌入式 Mermaid 图表），serviceModule 值已废弃，
     *   仅作为图表内「展开层级 / 颜色分组维度」，不再是独立图表模式。
     */
    chartType: 'businessObject',
    colorScheme: 'default',
    colorGroupBy: 'domain',
    centerScopeHighlight: true,
    annotationCategoryFilter: [],
    layoutEngine: 'elk',
    // [DIR 2026-08-07] 布局方向默认垂直 (TB), 与 store/useLayoutControl 默认一致
    direction: 'TB',
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
