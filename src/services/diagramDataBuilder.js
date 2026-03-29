/**
 * diagramDataBuilder - 图表数据构建服务
 *
 * 所属模块：图表渲染
 * 主要功能：
 *   - 构建Mermaid语法定义
 *   - 提供布局模板（默认/网格/水平/垂直）
 *   - 生成节点和连线数据
 *   - 处理颜色分组逻辑
 *
 * 核心接口：
 *   - buildNodes(): 构建节点数据
 *   - buildLinks(): 构建连线数据
 *   - generateMermaidCode(): 生成完整Mermaid语法
 *
 * @see MermaidComponent.vue - 图表渲染组件
 */

// 布局模板类型
export const LAYOUT_TEMPLATES = {
  DEFAULT: 'default',           // 默认：中心子领域居中放置
  GRID: 'grid',                 // 网格：多行多列方正布局
  HORIZONTAL: 'horizontal',     // 水平：从左到右排列
  VERTICAL: 'vertical'          // 垂直：从上到下排列
};

/**
 * 构建节点数据
 * @param {Array} businessObjects - 业务对象数组
 * @returns {Array} 节点数组
 */
export function buildNodes(businessObjects) {
  return businessObjects.map(bo => ({
    id: bo.name,
    name: bo.name,
    originalName: bo.name,
    code: bo.code,
    category: 'object',
    domain: bo.domain,
    subDomain: bo.subDomain,
    serviceModule: bo.serviceModule,
    annotationCategory: bo.annotationCategory || 'info',
    annotationContent: bo.annotationContent || ''
  }));
}

/**
 * 构建连线数据
 * @param {Array} relationships - 关系数组
 * @returns {Array} 连线数组
 */
export function buildLinks(relationships) {
  return relationships.map(rel => ({
    source: rel.sourceName,
    target: rel.targetName,
    sourceName: rel.sourceName,
    targetName: rel.targetName,
    sourceCode: rel.sourceCode,
    targetCode: rel.targetCode,
    relationCode: rel.relationCode,
    relationDesc: rel.relationDesc,
    annotationCategory: rel.annotationCategory || 'info',
    annotationContent: rel.annotationContent || ''
  }));
}

/**
 * 构建图表数据
 * @param {Object} params - 参数对象
 * @param {Array} params.businessObjects - 业务对象数组
 * @param {Array} params.relationships - 关系数组
 * @param {Array} params.domainProducts - 领域产品数组
 * @param {string} params.centerDomain - 中心子领域
 * @param {string} params.colorGroupBy - 颜色分组方式 ('domain' 或 'subDomain')
 * @param {string} params.centerDomainColor - 中心子领域颜色
 * @param {string} params.colorScheme - 颜色组合方案
 * @param {string} params.textColor - 业务对象标题文字颜色
 * @param {string} params.layoutTemplate - 布局模板
 * @returns {Object} 图表数据对象
 */
export function buildDiagramData({
  businessObjects,
  relationships,
  domainProducts,
  serviceModules,
  centerDomain = '',
  colorGroupBy = 'domain',
  centerDomainColor = '#D9D9D9',
  colorScheme = 'default',
  textColor = 'black',
  layoutTemplate = LAYOUT_TEMPLATES.DEFAULT
}) {
  const nodes = buildNodes(businessObjects);
  const links = buildLinks(relationships);

  return {
    nodes,
    links,
    domainProducts,
    serviceModules,
    centerDomain,
    colorGroupBy,
    centerDomainColor,
    colorScheme,
    textColor,
    layoutTemplate
  };
}
