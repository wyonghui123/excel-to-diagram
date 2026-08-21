/**
 * serviceModuleDiagramBuilder - 服务模块图数据构建服务
 *
 * @deprecated 服务模块图（serviceModule）已废弃（2026-08-08）
 *   - 业务层面已不再区分「业务对象图 / 服务模块图」两种图表模式
 *   - 唯一业务入口为 /system/archdata 嵌入式 Mermaid 图表（EmbeddedChartView → MermaidComponent）
 *   - 原「图表类型」下拉已被「展开层级」（expandLevel）取代；
 *     serviceModule 仅作为图表内的「展开层级 / 颜色分组维度」，不再是独立图表模式
 *   - chartType 配置固定为 'businessObject' 且 UI 无法切换，本文件渲染路径已无业务入口
 *   - 保留仅作历史参考，禁止作为新功能入口
 *
 * 所属模块：图表渲染
 * 主要功能：
 *   - 构建服务模块图的节点和连线数据
 *   - 处理服务模块间的层次关系
 *   - 提供多种布局模板
 *   - 管理颜色分配策略
 *
 * 与 diagramDataBuilder.js 的区别：
 *   - diagramDataBuilder: 业务对象图
 *   - serviceModuleDiagramBuilder: 服务模块图（更关注服务组件的层次结构）
 *
 * @see diagramDataBuilder.js - 业务对象图构建器
 */

import { LAYOUT_TEMPLATES, COLOR_SCHEMES } from '@/constants/diagram'
import { createHierarchyPipeline, GLOBAL_TERMINALS, sharedHierarchyPipeline } from './hierarchyTree/index.js'
import { colorize } from './hierarchyTree/colorize.js'
import { deriveLayoutGroups } from './hierarchyTree/layoutGroupsDeriver.js'

export { LAYOUT_TEMPLATES }

// [FIX 2026-08-02] 管道单例: L1 树 / L2 投影缓存跨 generateDiagram 调用生效 (spec 4.4)。
// [Task 10 2026-08-02] 改用 sharedHierarchyPipeline — BO/SM 图共享同一 L1 树缓存,
// 切换图表类型不重建架构树, 仅重算 L2 投影 (terminal 不同 → 缓存 key 不同, 无串扰)。
// 仅在传入 versionId/scopeHash 时启用缓存; 测试/旧路径不传时新建实例避免跨用例缓存串扰。
const hierarchyPipeline = sharedHierarchyPipeline

/**
 * 从分组配置中递归提取所有服务模块代码
 */
function extractServiceModuleCodesFromGroups(groups, collectedCodes = new Set()) {
  if (!groups || groups.length === 0) return collectedCodes

  for (const group of groups) {
    // DOMAIN 或 SUB_DOMAIN 分组：elementCode 是子领域代码，不是服务模块代码
    // 需要递归到 children（如果有的话）
    if (group.type === 'DOMAIN' || group.type === 'SUB_DOMAIN') {
      // 跳过，直接递归 children
      if (group.children && group.children.length > 0) {
        extractServiceModuleCodesFromGroups(group.children, collectedCodes)
      }
      // 对于 SUB_DOMAIN，继续递归（children 可能是更深层的分组）
      if (group.containers && group.containers.length > 0) {
        extractServiceModuleCodesFromGroups(group.containers, collectedCodes)
      }
      continue
    }

    // SERVICE_MODULE 分组：直接收集 elementCode
    if (group.type === 'SERVICE_MODULE') {
      if (group.elementCode) {
        collectedCodes.add(group.elementCode)
      } else if (group.id && group.id.startsWith('SM_')) {
        collectedCodes.add(group.id.substring(3))  // 去掉前缀
      } else if (group.id) {
        collectedCodes.add(group.id)
      }
      continue
    }

    // 其他类型（没有 type）：尝试从 containers 中提取
    if (group.containers && Array.isArray(group.containers)) {
      for (const container of group.containers) {
        if (typeof container === 'object' && container !== null) {
          if (container.type === 'SERVICE_MODULE') {
            if (container.elementCode) {
              collectedCodes.add(container.elementCode)
            } else if (container.id) {
              collectedCodes.add(container.id)
            }
          } else if (container.elementCode) {
            collectedCodes.add(container.elementCode)
          }
          if (container.nodes && Array.isArray(container.nodes)) {
            container.nodes.forEach(node => {
              if (typeof node === 'string') {
                collectedCodes.add(node)
              } else if (typeof node === 'object' && node.code) {
                collectedCodes.add(node.code)
              } else if (typeof node === 'object' && node.id) {
                collectedCodes.add(node.id)
              }
            })
          }
        } else if (typeof container === 'string') {
          collectedCodes.add(container)
        }
      }
    }
    if (group.children && group.children.length > 0) {
      extractServiceModuleCodesFromGroups(group.children, collectedCodes)
    }
  }

  return collectedCodes
}

/**
 * 构建服务模块图数据
 * @param {Object} params - 参数对象
 * @param {Array} params.serviceModules - 服务模块数组
 * @param {Array} params.serviceModuleRelationships - 服务模块关系数组
 * @param {Array} params.domainProducts - 领域产品数据
 * @param {String} params.centerSubDomain - 中心子领域
 * @param {String} params.centerSubDomainColor - 中心子领域颜色
 * @param {String} params.centerScopeColor - 中心范围服务模块颜色
 * @param {String} params.colorGroupBy - 颜色分组方式 ('domain' | 'subDomain')
 * @param {String} params.colorScheme - 配色方案
 * @param {String} params.nodeTextColor - 服务模块标题文字颜色
 * @param {Array} params.centerServiceModuleCodes - 中心范围服务模块编码数组
 * @param {Object} params.preview - 架构 preview 数据（统一管道分支: 传入则走 buildHierarchyTree→projectTree 管道）
 * @param {String} params.chartType - 图表类型（'serviceModule' 时启用统一管道分支）
 * @param {Number} params.versionId - 版本 ID（L1 树缓存 key 组成部分）
 * @param {String} params.scopeHash - scope 哈希（L1 树缓存 key 组成部分）
 * @returns {Object} 图表数据
 */
export function buildServiceModuleDiagramData({
  serviceModules,
  serviceModuleRelationships,
  domainProducts,
  centerSubDomain = '',
  centerSubDomainColor = '#D9D9D9',
  centerScopeColor = '#EDEDED',
  colorGroupBy = 'subDomain',
  colorScheme = 'default',
  nodeTextColor = 'black',
  layoutTemplate = LAYOUT_TEMPLATES.DEFAULT,
  customColors = {},
  hideLinkLabelTails = false,
  layoutControlConfig = null,
  groupControlTitleMap = {},
  centerServiceModuleCodes = null,
  centerScopeHighlight = true,
  preview = null,
  chartType = '',
  versionId = 0,
  scopeHash = ''
}) {
  // 获取颜色方案
  const colors = COLOR_SCHEMES[colorScheme] || COLOR_SCHEMES.default;

  // 如果有分组配置，从分组中提取服务模块代码
  let filteredServiceModules = serviceModules
  if (layoutControlConfig?.enabled && layoutControlConfig?.groups?.length > 0) {
    const groupSmCodes = extractServiceModuleCodesFromGroups(layoutControlConfig.groups)
    if (groupSmCodes.size > 0) {
      filteredServiceModules = serviceModules.filter(sm => groupSmCodes.has(sm.code))
    }
  }

  // 如果有分组配置，过滤服务模块关系
  let filteredRelationships = serviceModuleRelationships
  if (layoutControlConfig?.enabled && layoutControlConfig?.groups?.length > 0) {
    const groupSmCodes = extractServiceModuleCodesFromGroups(layoutControlConfig.groups)
    if (groupSmCodes.size > 0) {
      filteredRelationships = serviceModuleRelationships.filter(rel =>
        groupSmCodes.has(rel.sourceServiceModuleCode) && groupSmCodes.has(rel.targetServiceModuleCode)
      )
    }
  }

  // [FIX 2026-08-02] 统一管道分支（spec 4.2）：preview 传入且 chartType=serviceModule 时走管道。
  // 消除双数据源: nodes/containers/links 全部派生自同一棵架构树（L1 树 → L2 投影 → L3 着色），
  // 容器层级由树固定派生, 同一 SM 只出现一次（作为显示节点; 归属于子领域容器为正常层级, 不再作为 subgraph 容器重复出现）。
  if (preview && chartType === 'serviceModule') {
    // 缓存生效条件: 调用方提供了 versionId/scopeHash (真实链路); 否则新建实例避免串扰
    const pipeline = (versionId || scopeHash) ? hierarchyPipeline : createHierarchyPipeline()
    const treeData = pipeline.getTree({ preview, versionId, scopeHash })
    const projection = pipeline.project({ treeData, terminal: GLOBAL_TERMINALS.serviceModule })

    // L3 着色（投影节点自带 domain/subDomain, 由树上下文派生）
    const { nodes: coloredNodes, groupColorMap } = colorize(projection.nodes, projection.containers, {
      colorGroupBy, colorScheme, centerSubDomain, centerSubDomainColor, customColors,
      centerServiceModuleCodes, centerScopeHighlight, nodeTextColor,
    })

    // links: 投影器已把 BO 级关系折叠重映射为 SM code 级; 补充关系元数据 + 过滤悬空边
    const relMap = new Map((filteredRelationships || []).map(r =>
      [`${r.sourceServiceModuleCode}->${r.targetServiceModuleCode}`, r]))
    const links = projection.links
      .map(l => {
        const rel = relMap.get(`${l.source}->${l.target}`)
        return {
          source: l.source, target: l.target,
          label: l.label || rel?.serviceRelationshipCode || '',
          tooltip: rel ? `关系编码: ${rel.serviceRelationshipCode}\n业务对象关系: ${rel.businessObjectRelationshipCodes?.join(', ')}` : '',
          annotationContents: rel?.annotationContents || [],
          annotationCategories: rel?.annotationCategories || [],
          relationType: rel?.relationType || '',
          relationDirection: rel?.relationDirection || null,
          // [FIX 2026-08-03] 透传完整子关系数组, 供 useTooltip 展示"所有子关系 BO 对列表"
          childRelations: rel?.businessObjectRelationships || [],
        }
      })
      .filter(l => coloredNodes.some(n => n.id === l.source) && coloredNodes.some(n => n.id === l.target))

    // groups 由同一容器树派生 (spec 4.2.4): 取代 GroupModel 独立生成 + resolveGroupContainers 名称匹配。
    // enabled 恒为 true: 容器层级由树固定派生, 不再受用户自定义分组开关影响
    const unifiedLayoutConfig = {
      enabled: true,
      overallDirection: layoutControlConfig?.overallDirection || 'TB',
      groups: deriveLayoutGroups(projection.containers),
    }

    // [FIX 2026-08-02] 顶层补齐 centerScopeHighlight/centerScope 契约字段 (与 BO 图 builder 一致):
    //   - MermaidComponent watch 用 diagramData.centerScopeHighlight 变化判定增量路径,
    //     缺它 → 切换"区分中心范围"时 centerScopeHighlightChanged=false → 全量 renderMermaid() (用户感知"刷新图表区域")
    //   - updateColorsOnly.updateNodeColors 用 centerScope 集合判定中心节点 fill,
    //     缺它 → centerScopeSet 空 → 增量路径下中心节点不涂 centerScopeColor
    //   centerScope 取自 colorize 已烘焙的 isCenter 节点 (与 useServiceModuleSyntax 语法层判定严格一致)
    return {
      nodes: coloredNodes,
      links,
      containers: projection.containers,
      centerSubDomain: centerSubDomain || projection.nodes[0]?.subDomain || '',
      centerSubDomainColor, centerScopeColor, colorGroupBy, colorScheme,
      nodeTextColor, layoutTemplate, customColors, hideLinkLabelTails,
      layoutControlConfig: unifiedLayoutConfig,
      groupControlTitleMap,
      centerScopeHighlight: centerScopeHighlight !== false,
      centerScope: coloredNodes.filter(n => n.isCenter).map(n => n.code),
      groupColorMap,                    // [FIX 2026-08-05] 与图表同源的分组色映射
    }
  }

  // 构建子领域到领域的映射
  const subDomainToDomain = {};
  domainProducts?.forEach(domain => {
    domain.modules?.forEach(subDomain => {
      subDomainToDomain[subDomain.name] = domain.name;
    });
  });

  // 确定实际的中心子领域（如果未指定则使用第一个）
  const uniqueSubDomains = [...new Set(filteredServiceModules.map(sm => sm.subDomain))];
  const actualCenterSubDomain = centerSubDomain || uniqueSubDomains[0] || '';

  // 确定中心服务模块编码
  // 优先使用传入的 centerServiceModuleCodes（包含任何中心范围业务对象的服务模块）
  // 如果没有传入，则基于 isCenter 标记或 centerSubDomain 计算
  const finalCenterServiceModuleCodes = centerServiceModuleCodes
    ? new Set(centerServiceModuleCodes)
    : new Set(filteredServiceModules.filter(sm => sm.isCenter || sm.subDomain === actualCenterSubDomain).map(sm => sm.code))

  // 构建子领域到颜色的映射、领域到颜色的映射、服务模块到颜色的映射
  const subDomainColors = {};
  const domainColors = {};
  const serviceModuleColors = {};

  if (colorGroupBy === 'serviceModule') {
    // 按服务模块分组颜色
    filteredServiceModules.forEach((sm, index) => {
      serviceModuleColors[sm.name] = customColors[sm.name] || colors[index % colors.length];
    });
  } else if (colorGroupBy === 'subDomain') {
    // 按子领域分组颜色
    uniqueSubDomains.forEach((subDomain, index) => {
      if (subDomain === actualCenterSubDomain) {
        subDomainColors[subDomain] = centerSubDomainColor;
      } else {
        subDomainColors[subDomain] = customColors[subDomain] || colors[index % colors.length];
      }
    });
  } else {
    // 按领域分组颜色
    const uniqueDomains = [...new Set(filteredServiceModules.map(sm => sm.domain))];
    uniqueDomains.forEach((domain, index) => {
      domainColors[domain] = customColors[domain] || colors[index % colors.length];
    });
    // 子领域继承领域颜色（只有是中心子领域时才使用中心颜色）
    // 重要：只有当子领域本身就是中心子领域时才使用 centerSubDomainColor
    // 而不是根据 actualCenterSubDomain 来判断（这会导致整个子领域都变成中心颜色）
    filteredServiceModules.forEach(sm => {
      // [FIX 2026-08-02] 中心模块的子领域不再用 centerScopeColor 覆盖 (与 BO 图"分组色+特殊边框"一致)
      //   之前: 中心模块的子领域 subDomainColors = centerScopeColor → 按子领域分组时中心模块整片灰
      subDomainColors[sm.subDomain] = domainColors[sm.domain];
    });
  }

  // 构建节点（服务模块）
  // 如果是中心范围服务模块，使用 centerScopeColor；否则使用子领域/领域/服务模块颜色
  // 只有当 centerScopeHighlight 为 true 时，才对中心服务模块特殊处理
  const nodes = filteredServiceModules.map((sm, index) => {
    const isCenter = centerScopeHighlight && finalCenterServiceModuleCodes.has(sm.code)

    // 直接根据是否是中心服务模块来决定颜色
    // 不再依赖 subDomainColors[sm.subDomain]，因为它可能被其他服务模块覆盖
    let baseColor
    if (colorGroupBy === 'serviceModule') {
      baseColor = serviceModuleColors[sm.name] || colors[index % colors.length]
    } else if (colorGroupBy === 'subDomain') {
      baseColor = subDomainColors[sm.subDomain] || colors[0]
    } else {
      // 按领域分组：使用领域颜色
      baseColor = domainColors[sm.domain] || colors[0]
    }

    // [FIX 2026-08-02] 中心模块 fill 不再用 centerScopeColor 覆盖 (与 BO 图"分组色+特殊边框"一致)
    //   之前: isCenter 模块 fill=centerScopeColor (#808080 灰) → 中心模块占大比时整图灰蒙蒙,
    //   且切换配色/分组时语法层每次重建都重新赋灰 → 用户反馈"节点还是灰色的"。
    //   现在: 中心模块 fill 用分组色 (联动变色), 由 useServiceModuleSyntax 根据 isCenter 加粗虚线边框区分。
    const finalColor = baseColor

    return {
      id: sm.code,
      name: sm.name,
      code: sm.code,
      domain: sm.domain,
      subDomain: sm.subDomain,
      color: finalColor,
      textColor: nodeTextColor,
      // [FIX 2026-06-29] archDataConverter 输出复数数组 annotationContents/Categories
      //   单条时也是数组形式 [content], 多条时 [c1, c2, c3]
      //   这样 useAnnotation.parseAnnotationsFromData 可以逐条渲染
      annotationContents: sm.annotationContents || [],
      annotationCategories: sm.annotationCategories || [],
      isCenter: isCenter
    }
  })

  // 构建连线（服务模块关系）
  const links = filteredRelationships.map(rel => ({
    source: rel.sourceServiceModuleCode,
    target: rel.targetServiceModuleCode,
    label: rel.serviceRelationshipCode,
    tooltip: `关系编码: ${rel.serviceRelationshipCode}\n业务对象关系: ${rel.businessObjectRelationshipCodes?.join(', ')}`,
    // [FIX 2026-06-29] 复数数组形式
    annotationContents: rel.annotationContents || [],
    annotationCategories: rel.annotationCategories || [],
    // [v34 双向支持] 透传 relationType + relationDirection
    relationType: rel.relationType || '',
    relationDirection: rel.relationDirection || null,
    // [FIX 2026-08-03] 透传完整子关系数组, 供 useTooltip 展示"所有子关系 BO 对列表"
    childRelations: rel.businessObjectRelationships || []
  }));

  // 构建容器（子领域）- 容器默认白色背景
  const containers = {};
  const containerOrder = [];
  filteredServiceModules.forEach(sm => {
    if (!containers[sm.subDomain]) {
      const domainName = subDomainToDomain[sm.subDomain] || '';
      containers[sm.subDomain] = {
        id: sm.subDomain,
        name: sm.subDomain,
        domain: domainName,
        fullTitle: domainName ? `${domainName} / ${sm.subDomain}` : sm.subDomain,
        color: '#ffffff', // 容器默认白色背景
        nodes: []
      };
      containerOrder.push(sm.subDomain);
    }
    containers[sm.subDomain].nodes.push({
      id: sm.code,
      name: sm.name,
      code: sm.code
    });
  });

  // 按照添加顺序获取容器数组
  const containerArray = containerOrder.map(id => containers[id]);
  
  const sortedContainers = sortContainersByTemplate(
    containerArray,
    actualCenterSubDomain,
    layoutTemplate
  );

  return {
    nodes,
    links,
    containers: sortedContainers,
    centerSubDomain: actualCenterSubDomain,
    centerSubDomainColor,
    centerScopeColor,
    colorGroupBy,
    colorScheme,
    nodeTextColor,
    layoutTemplate,
    customColors,
    hideLinkLabelTails,
    layoutControlConfig,
    groupControlTitleMap,
    // [FIX 2026-08-02] 与统一管道分支一致: 补齐顶层契约字段 (watch 增量路径 + updateNodeColors 依赖)
    centerScopeHighlight: centerScopeHighlight !== false,
    centerScope: [...finalCenterServiceModuleCodes]
  };
}

/**
 * 根据布局模板对容器进行排序
 * @param {Array} containers - 容器数组
 * @param {String} centerSubDomain - 中心子领域
 * @param {String} template - 布局模板
 * @returns {Array} 排序后的容器数组
 */
function sortContainersByTemplate(containers, centerSubDomain, template) {
  if (!centerSubDomain || containers.length <= 1) {
    return containers;
  }

  // 找到中心子领域的索引
  const centerIndex = containers.findIndex(c => c.id === centerSubDomain);
  if (centerIndex === -1) {
    return containers;
  }

  // 移除中心子领域
  const centerContainer = containers.splice(centerIndex, 1)[0];

  let result;
  switch (template) {
    case LAYOUT_TEMPLATES.GRID:
      // 网格布局：将容器排列成多行，保持中心在视觉中心位置
      result = gridLayout(containers, centerContainer);
      break;
    case LAYOUT_TEMPLATES.HORIZONTAL:
      // 水平布局：中心在中间，左边一半，右边一半
      result = horizontalLayout(containers, centerContainer);
      break;
    case LAYOUT_TEMPLATES.VERTICAL:
      // 垂直布局：中心在中间，上边一半，下边一半
      result = verticalLayout(containers, centerContainer);
      break;
    case LAYOUT_TEMPLATES.DEFAULT:
    default:
      // 默认布局：保持原始顺序，中心容器放回原位
      containers.splice(centerIndex, 0, centerContainer);
      result = containers;
      break;
  }

  return result;
}

/**
 * 网格布局：将容器排列成接近正方形的网格，中心容器在中心位置
 */
function gridLayout(containers, centerContainer) {
  const count = containers.length + 1; // 包含中心
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);

  // 构建网格位置
  const grid = [];
  let idx = 0;
  for (let r = 0; r < rows && idx < count - 1; r++) {
    const row = [];
    for (let c = 0; c < cols && idx < count - 1; c++) {
      row.push(containers[idx++]);
    }
    // 填充空位
    while (row.length < cols) {
      row.push(null);
    }
    grid.push(row);
  }

  // 计算中心在网格中的位置
  const centerRow = Math.floor(rows / 2);
  const centerCol = Math.floor(cols / 2);

  // 将中心容器放入网格中心
  if (grid[centerRow] && grid[centerRow][centerCol] === null) {
    grid[centerRow][centerCol] = centerContainer;
  } else {
    // 如果中心位置已被占用，找最近的空位
    let placed = false;
    for (let r = 0; r < rows && !placed; r++) {
      for (let c = 0; c < cols && !placed; c++) {
        if (grid[r][c] === null) {
          grid[r][c] = centerContainer;
          placed = true;
        }
      }
    }
  }

  // 按行展平，去除 null
  const result = [];
  grid.forEach(row => {
    row.forEach(item => {
      if (item !== null) {
        result.push(item);
      }
    });
  });

  return result;
}

/**
 * 水平布局：中心在中间，左边一半，右边一半
 */
function horizontalLayout(containers, centerContainer) {
  const middleIndex = Math.floor(containers.length / 2);
  return [...containers.slice(0, middleIndex), centerContainer, ...containers.slice(middleIndex)];
}

/**
 * 垂直布局：中心在中间，上边一半，下边一半
 */
function verticalLayout(containers, centerContainer) {
  const middleIndex = Math.floor(containers.length / 2);
  return [...containers.slice(0, middleIndex), centerContainer, ...containers.slice(middleIndex)];
}

/**
 * 生成服务模块图的 Mermaid 代码
 * @param {Object} diagramData - 图表数据
 * @returns {String} Mermaid 代码
 */
export function generateServiceModuleMermaidCode(diagramData) {
  const { nodes, links, containers } = diagramData;

  let code = 'graph TD\n';

  // 定义样式类
  code += `    classDef default fill:#fafafa,stroke:#666,stroke-width:1px,color:#333\n`;
  code += `    classDef container fill:#f0f0f0,stroke:#999,stroke-width:2px,color:#333\n`;

  // 生成子图（容器）
  containers.forEach(container => {
    const containerId = container.id.replace(/[^a-zA-Z0-9]/g, '_');
    code += `    subgraph ${containerId}["${container.fullTitle}"]\n`;

    // 容器内的节点
    container.nodes.forEach(nodeId => {
      const node = nodes.find(n => n.id === nodeId);
      if (node) {
        const nodeLabel = `${node.name}<br/>${node.code}`;
        code += `        ${node.code}["${nodeLabel}"]\n`;
      }
    });

    code += `    end\n`;

    // 设置容器样式
    const fillColor = container.color;
    code += `    style ${containerId} fill:${fillColor},stroke:#666,stroke-width:2px\n`;
  });

  // 生成连线
  links.forEach((link, index) => {
    const linkId = `link${index}`;
    code += `    ${link.source} -->|"${link.label}"| ${link.target}\n`;
  });

  return code;
}
