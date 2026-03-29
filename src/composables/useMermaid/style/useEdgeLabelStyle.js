/**
 * useEdgeLabelStyle.js - 通用的 EdgeLabel 样式处理模块
 * 
 * 统一处理业务对象图和服务模块图的 edgeLabel 样式
 * 
 * 设计原则：
 * 1. 核心样式统一（背景、文字、字体等）
 * 2. 装饰元素处理统一（隐藏 Mermaid 默认装饰）
 * 3. 交互状态个性化（选中、悬停等状态保留差异）
 */

export const EDGE_LABEL_COMMON_STYLES = {
  // 文字样式
  textColor: '#333333',
  fontSize: '12px',
  fontWeight: 'normal',
  fontFamily: 'Arial, sans-serif',
  
  // 背景样式
  backgroundColor: 'transparent',
  backgroundOpacity: 0,
  
  // 边框样式
  border: 'none',
  borderRadius: 0,
  
  // 间距
  padding: 0,
  margin: 0,
  
  // 其他
  whiteSpace: 'nowrap',
  lineHeight: '1.5'
}

export function useEdgeLabelStyle() {
  /**
   * 获取统一的 CSS 类定义（用于 Mermaid 语法中的 classDef）
   */
  const getCommonClassDefs = () => {
    return `edgeLabel fill:none,stroke:none,stroke-width:0,color:${EDGE_LABEL_COMMON_STYLES.textColor},font-size:${EDGE_LABEL_COMMON_STYLES.fontSize},font-weight:${EDGE_LABEL_COMMON_STYLES.fontWeight}`
  }

  /**
   * ✅ 纯 CSS 方案：不再需要 JavaScript 应用样式
   * 所有 edgeLabel 样式由 CSS .edge-label-clean 类统一管理
   */
  // const applyCommonStyles = (svg) => { ... }

  /**
   * ✅ 纯 CSS 方案：不再需要 JavaScript 创建白色背景
   * 所有 edgeLabel 背景样式由 CSS .edge-label-clean 类统一管理
   */
  // const createWhiteBackground = (label, labelCenterX, labelCenterY, width, height) => { ... }

  /**
   * ✅ 纯 CSS 方案：不再需要 JavaScript 隐藏装饰元素
   * 所有装饰元素隐藏由 CSS .edge-label-clean 类统一处理
   */
  // const hideDecorativeElements = (label) => { ... }

  /**
   * 获取 businessObject 特有的样式覆盖
   */
  const getBusinessObjectOverrides = () => {
    return `
      /* 业务对象图 - labelBkg 白色背景 */
      .mermaid-content.businessObject :deep(.labelBkg),
      .mermaid-content.businessObject :deep(.labelBkg *) {
        fill: #ffffff !important;
        fill-opacity: 1 !important;
        background: #ffffff !important;
        background-color: #ffffff !important;
        stroke: none !important;
        color: #333 !important;
      }
      
      .mermaid-content.businessObject :deep(.labelBkg) {
        display: inline-block !important;
        line-height: 1.2 !important;
        padding: 2px 6px !important;
        margin: 0 !important;
      }
      
      .mermaid-content.businessObject :deep(.labelBkg p) {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
      }
      
      .mermaid-content.businessObject :deep(.labelBkg span) {
        display: inline !important;
        background: transparent !important;
        background-color: transparent !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
      }
    `
  }

  /**
   * 服务模块图不再需要特殊覆盖，使用通用样式即可
   * 交互状态统一采用业务对象图的简单逻辑（点击显示关系说明）
   */
  const getServiceModuleOverrides = () => {
    return `
      /* 服务模块图与业务对象图样式完全一致，无需额外覆盖 */
    `
  }

  /**
   * 生成完整的 edgeLabel 样式（通用 + 个性化）
   */
  const generateCompleteStyles = (diagramType) => {
    let styles = `
      /* ===== 通用 EdgeLabel 样式 ===== */
      .mermaid-content :deep(.edgeLabel),
      .mermaid-content :deep(.edgeLabel *),
      .mermaid-content :deep(.edgeLabel > *),
      .mermaid-content :deep(.edgeLabel div),
      .mermaid-content :deep(.edgeLabel span),
      .mermaid-content :deep(.edgeLabel .label),
      .mermaid-content :deep(.edgeLabel foreignObject),
      .mermaid-content :deep(.edgeLabel foreignObject > div),
      .mermaid-content :deep(.edgeLabel foreignObject > span) {
        background-color: transparent !important;
        background: transparent !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        font-size: ${EDGE_LABEL_COMMON_STYLES.fontSize} !important;
        font-weight: ${EDGE_LABEL_COMMON_STYLES.fontWeight} !important;
        color: ${EDGE_LABEL_COMMON_STYLES.textColor} !important;
        border: none !important;
        box-shadow: none !important;
      }
      
      /* 隐藏 SVG 装饰元素 */
      .mermaid-content :deep(.edgeLabel path),
      .mermaid-content :deep(.edgeLabel rect:not([data-label-bg])),
      .mermaid-content :deep(.edgeLabel polygon),
      .mermaid-content :deep(.edgeLabel polyline),
      .mermaid-content :deep(.edgeLabel circle),
      .mermaid-content :deep(.edgeLabel ellipse) {
        fill: transparent !important;
        stroke: none !important;
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
      }
      
      /* foreignObject 样式 */
      .mermaid-content :deep(.edgeLabel foreignObject) {
        background: transparent !important;
        background-color: transparent !important;
        overflow: visible !important;
      }
      
      /* 文字样式 */
      .mermaid-content :deep(.edgeLabel text),
      .mermaid-content :deep(.edgeLabel textPath) {
        fill: ${EDGE_LABEL_COMMON_STYLES.textColor} !important;
        font-size: ${EDGE_LABEL_COMMON_STYLES.fontSize} !important;
        font-weight: ${EDGE_LABEL_COMMON_STYLES.fontWeight} !important;
        font-family: ${EDGE_LABEL_COMMON_STYLES.fontFamily} !important;
        stroke: none !important;
      }
    `

    // 添加个性化覆盖
    if (diagramType === 'businessObject') {
      styles += getBusinessObjectOverrides()
    } else if (diagramType === 'serviceModule') {
      styles += getServiceModuleOverrides()
    }

    return styles
  }

  return {
    EDGE_LABEL_COMMON_STYLES,
    getCommonClassDefs,
    // ✅ 纯 CSS 方案：不再需要这些 JavaScript 函数
    // applyCommonStyles,
    // createWhiteBackground,
    // hideDecorativeElements,
    getBusinessObjectOverrides,
    getServiceModuleOverrides,
    generateCompleteStyles
  }
}
