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
import { createHierarchyPipeline, GLOBAL_TERMINALS, sharedHierarchyPipeline } from './hierarchyTree/index.js'
import { colorize } from './hierarchyTree/colorize.js'
import { deriveLayoutGroups } from './hierarchyTree/layoutGroupsDeriver.js'

export { LAYOUT_TEMPLATES }

// [Task 10 2026-08-02] 管道单例: 与 serviceModuleDiagramBuilder 共享同一 L1 树缓存 (spec 4.4)。
// 仅在传入 versionId/scopeHash 时启用缓存; 测试/旧路径不传时新建实例避免跨用例缓存串扰。
const hierarchyPipeline = sharedHierarchyPipeline

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
    // [FIX 2026-06-29 v3] 复数数组形式 - 兼容单数/复数字段
    //   后端返回 annotation_contents/categories (snake_case 数组)
    //   archDataConverter.normalizeAnnotation 转换 annotationContents/Categories (驼峰数组)
    //   之前用单数 annotationCategory/annotationContent (字符串), pushAnnotation 找不到数组 → 不渲染
    annotationContents: bo.annotationContents || bo.annotation_contents || [],
    annotationCategories: bo.annotationCategories || bo.annotation_categories || [],
    // 保留单数字段以兼容其他代码
    annotationCategory: bo.annotationCategories?.[0] || bo.annotation_category || bo.annotationCategory || 'info',
    annotationContent: bo.annotationContents?.[0] || bo.annotation_content || bo.annotationContent || ''
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
    // [FIX 2026-06-29 v3] 复数数组形式 - 兼容单数/复数字段
    //   详见 buildNodes 注释
    annotationContents: rel.annotationContents || rel.annotation_contents || [],
    annotationCategories: rel.annotationCategories || rel.annotation_categories || [],
    // 保留单数字段以兼容其他代码
    annotationCategory: rel.annotationCategories?.[0] || rel.annotation_category || rel.annotationCategory || 'info',
    annotationContent: rel.annotationContents?.[0] || rel.annotation_content || rel.annotationContent || '',
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
  centerScopeHighlight = true,
  // [Task 10 2026-08-02] 统一管道参数 (spec 4.2): preview 传入且 chartType=businessObject 时走管道
  preview = null,
  chartType = '',
  versionId = 0,
  scopeHash = ''
}) {
  // [Task 10 2026-08-02] 统一管道分支 (spec 4.2): BO 末端投影。
  // 投影产出 BO 节点 + SM/子领域/领域嵌套容器; nodes/containers/links 全部派生自同一棵架构树,
  // 容器层级由树固定派生 (D→SD→SM→BO), 消除旧路径 groupModel 独立生成 + 名称匹配的错乱隐患。
  if (preview && chartType === 'businessObject') {
    const pipeline = (versionId || scopeHash) ? hierarchyPipeline : createHierarchyPipeline()
    const treeData = pipeline.getTree({ preview, versionId, scopeHash })
    const projection = pipeline.project({ treeData, terminal: GLOBAL_TERMINALS.businessObject })

    // L3 着色 (中心范围 = centerScope BO codes; isCenter 由 colorize 统一计算)
    const { nodes: coloredNodes, groupColorMap } = colorize(projection.nodes, projection.containers, {
      colorGroupBy, colorScheme, centerSubDomain: '', centerSubDomainColor: centerScopeColor,
      customColors, centerServiceModuleCodes: centerScope?.length ? centerScope : null,
      centerScopeHighlight, nodeTextColor,
    })

    // 补充 BO 语法层 (useBusinessObjectSyntax) 契约字段:
    //   category/originalName/name/serviceModule/annotation* — 由 businessObjects 全量对象回查补全
    const boByCode = new Map()
    ;(businessObjects || []).forEach(bo => {
      if (bo?.code != null && !boByCode.has(bo.code)) boByCode.set(bo.code, bo)
    })
    const nodes = coloredNodes.map(n => {
      const bo = boByCode.get(n.code)
      const name = bo?.name || n.name || n.code
      return {
        ...n,
        category: 'object',
        name,
        originalName: name,
        serviceModule: bo?.serviceModule,
        serviceModuleName: bo?.serviceModuleName,
        isCenter: !!n.isCenter,
        annotationContents: bo?.annotationContents || bo?.annotation_contents || n.annotationContents || [],
        annotationCategories: bo?.annotationCategories || bo?.annotation_categories || n.annotationCategories || [],
        annotationCategory: bo?.annotationCategories?.[0] || bo?.annotation_category || 'info',
        annotationContent: bo?.annotationContents?.[0] || bo?.annotation_content || ''
      }
    })

    // links: 投影器已把端点重映射为 BO code 级; 补充关系元数据 (label/注释/双向) 供语法层消费
    const relMap = new Map((relationships || []).map(r => [`${r.sourceCode}->${r.targetCode}`, r]))
    const links = projection.links.map(l => {
      const rel = relMap.get(`${l.source}->${l.target}`)
      const srcBo = boByCode.get(l.source)
      const tgtBo = boByCode.get(l.target)
      return {
        source: l.source, target: l.target,
        sourceCode: l.source, targetCode: l.target,
        sourceName: srcBo?.name || '', targetName: tgtBo?.name || '',
        // [v39] 关系实例编码优先, 与旧 buildLinks 一致
        code: rel?.code || l.label || '',
        relationCode: rel?.relationCode || '',
        relationDesc: rel?.relationDesc || '',
        annotationContents: rel?.annotationContents || [],
        annotationCategories: rel?.annotationCategories || [],
        annotationCategory: rel?.annotationCategories?.[0] || rel?.annotation_category || 'info',
        annotationContent: rel?.annotationContents?.[0] || rel?.annotation_content || '',
        relationType: rel?.relationType || '',
        relationDirection: rel?.relationDirection || null,
        label: l.label || rel?.code || ''
      }
    }).filter(l => nodes.some(n => n.id === l.source) && nodes.some(n => n.id === l.target))

    // groups 由同一容器树派生 (spec 4.2.4); groupType 标记供 EmbeddedChartView 识别管道产物
    const unifiedLayoutConfig = {
      enabled: true,
      overallDirection: layoutControlConfig?.overallDirection || 'TB',
      groups: deriveLayoutGroups(projection.containers),
    }

    return {
      nodes,
      links,
      containers: projection.containers,
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
      layoutControlConfig: unifiedLayoutConfig,
      groupControlTitleMap: layoutControlConfig?.titleMap || {},
      centerScopeHighlight,
      groupColorMap                    // [FIX 2026-08-05] 与图表同源的分组色映射
    }
  }

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
