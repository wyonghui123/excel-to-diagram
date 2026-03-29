/**
 * serviceModuleDiagramBuilder - 服务模块图数据构建服务
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

// 布局模板类型
export const LAYOUT_TEMPLATES = {
  DEFAULT: 'default',           // 默认：中心子领域居中放置
  GRID: 'grid',                 // 网格：多行多列方正布局
  HORIZONTAL: 'horizontal',     // 水平：从左到右排列
  VERTICAL: 'vertical'          // 垂直：从上到下排列
};

// 颜色组合配置
const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
  warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
  cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
  business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
  nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
};

/**
 * 构建服务模块图数据
 * @param {Object} params - 参数对象
 * @param {Array} params.serviceModules - 服务模块数组
 * @param {Array} params.serviceModuleRelationships - 服务模块关系数组
 * @param {Array} params.domainProducts - 领域产品数据
 * @param {String} params.centerSubDomain - 中心子领域
 * @param {String} params.centerSubDomainColor - 中心子领域颜色
 * @param {String} params.colorGroupBy - 颜色分组方式 ('domain' | 'subDomain')
 * @param {String} params.colorScheme - 配色方案
 * @param {String} params.serviceModuleTextColor - 服务模块标题文字颜色
 * @returns {Object} 图表数据
 */
export function buildServiceModuleDiagramData({
  serviceModules,
  serviceModuleRelationships,
  domainProducts,
  centerSubDomain = '',
  centerSubDomainColor = '#D9D9D9',
  colorGroupBy = 'subDomain',
  colorScheme = 'default',
  serviceModuleTextColor = 'black',
  layoutTemplate = LAYOUT_TEMPLATES.DEFAULT
}) {
  // 获取颜色方案
  const colors = COLOR_SCHEMES[colorScheme] || COLOR_SCHEMES.default;

  // 构建子领域到领域的映射
  const subDomainToDomain = {};
  domainProducts?.forEach(domain => {
    domain.modules?.forEach(subDomain => {
      subDomainToDomain[subDomain.name] = domain.name;
    });
  });

  // 确定实际的中心子领域（如果未指定则使用第一个）
  const uniqueSubDomains = [...new Set(serviceModules.map(sm => sm.subDomain))];
  const actualCenterSubDomain = centerSubDomain || uniqueSubDomains[0] || '';

  // 构建子领域到颜色的映射
  const subDomainColors = {};
  const domainColors = {};

  if (colorGroupBy === 'subDomain') {
    // 按子领域分组颜色
    uniqueSubDomains.forEach((subDomain, index) => {
      if (subDomain === actualCenterSubDomain) {
        subDomainColors[subDomain] = centerSubDomainColor;
      } else {
        subDomainColors[subDomain] = colors[index % colors.length];
      }
    });
  } else {
    // 按领域分组颜色
    const uniqueDomains = [...new Set(serviceModules.map(sm => sm.domain))];
    uniqueDomains.forEach((domain, index) => {
      domainColors[domain] = colors[index % colors.length];
    });
    // 子领域继承领域颜色
    serviceModules.forEach(sm => {
      if (sm.subDomain === actualCenterSubDomain) {
        subDomainColors[sm.subDomain] = centerSubDomainColor;
      } else {
        subDomainColors[sm.subDomain] = domainColors[sm.domain];
      }
    });
  }

  // 构建节点（服务模块）
  const nodes = serviceModules.map((sm, index) => ({
    id: sm.code,
    name: sm.name,
    code: sm.code,
    domain: sm.domain,
    subDomain: sm.subDomain,
    color: subDomainColors[sm.subDomain] || colors[0],
    textColor: serviceModuleTextColor,
    annotationCategory: sm.annotationCategory || 'info',
    annotationContent: sm.annotationContent || ''
  }));

  // 构建连线（服务模块关系）
  const links = serviceModuleRelationships.map(rel => ({
    source: rel.sourceServiceModuleCode,
    target: rel.targetServiceModuleCode,
    label: rel.serviceRelationshipCode,
    tooltip: `关系编码: ${rel.serviceRelationshipCode}\n业务对象关系: ${rel.businessObjectRelationshipCodes?.join(', ')}`,
    annotationCategory: rel.annotationCategory || 'info',
    annotationContent: rel.annotationContent || ''
  }));

  // 构建容器（子领域）- 容器默认白色背景
  const containers = {};
  const containerOrder = [];
  serviceModules.forEach(sm => {
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
    containers[sm.subDomain].nodes.push(sm.code);
  });

  // 按照添加顺序获取容器数组
  const containerArray = containerOrder.map(id => containers[id]);
  console.log('[serviceModuleDiagramBuilder] containerArray before sort:', containerArray.map((c, i) => `${i}: ${c.name}`))
  
  const sortedContainers = sortContainersByTemplate(
    containerArray,
    actualCenterSubDomain,
    layoutTemplate
  );
  console.log('[serviceModuleDiagramBuilder] sortedContainers after sort:', sortedContainers.map((c, i) => `${i}: ${c.name}`))

  return {
    nodes,
    links,
    containers: sortedContainers,
    centerSubDomain: actualCenterSubDomain,
    centerSubDomainColor,
    colorGroupBy,
    colorScheme,
    serviceModuleTextColor,
    layoutTemplate
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
