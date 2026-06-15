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

import { LAYOUT_TEMPLATES } from '@/constants/diagram'

export { LAYOUT_TEMPLATES }

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
    serviceModuleName: bo.serviceModuleName,
    isCenter: bo.isCenter || false,
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
    // [v39 关系线标题] 关系实例编码 (e.g. "ORDER-USER-01")
    // 之前 mermaid label 误用 relationCode (类型编码), 现优先用 code
    code: rel.code || '',
    relationCode: rel.relationCode,
    relationDesc: rel.relationDesc,
    annotationCategory: rel.annotationCategory || 'info',
    annotationContent: rel.annotationContent || '',
    // [v34 双向支持] 透传 relationType + relationDirection, 供箭头生成和 tooltip 使用
    relationType: rel.relationType || '',
    relationDirection: rel.relationDirection || null
  }));
}

/**
 * 构建图表数据
 * @param {Object} params - 参数对象
 * @param {Array} params.businessObjects - 业务对象数组
 * @param {Array} params.relationships - 关系数组
 * @param {Array} params.domainProducts - 领域产品数组
 * @param {string} params.colorGroupBy - 颜色分组方式 ('domain' 或 'subDomain')
 * @param {string} params.colorScheme - 颜色组合方案
 * @param {string} params.nodeTextColor - 业务对象标题文字颜色
 * @param {string} params.centerScopeColor - 中心范围业务对象背景颜色
 * @param {string} params.layoutTemplate - 布局模板
 * @returns {Object} 图表数据对象
 */
export function buildDiagramData({
  businessObjects,
  relationships,
  domainProducts,
  serviceModules,
  colorGroupBy = 'domain',
  colorScheme = 'default',
  nodeTextColor = 'black',
  centerScopeColor = '#EDEDED',
  layoutTemplate = LAYOUT_TEMPLATES.DEFAULT,
  customColors = {},
  hideLinkLabelTails = false,
  layoutControlConfig = null,
  centerScope = [],
  centerScopeHighlight = true
}) {
  const nodes = buildNodes(businessObjects);
  const links = buildLinks(relationships);

  return {
    nodes,
    links,
    domainProducts,
    serviceModules,
    colorGroupBy,
    colorScheme,
    nodeTextColor,
    centerScopeColor,
    centerScope,
    layoutTemplate,
    customColors,
    hideLinkLabelTails,
    layoutControlConfig,
    groupControlTitleMap: layoutControlConfig?.titleMap,
    centerScopeHighlight
  };
}
