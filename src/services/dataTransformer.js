/**
 * 数据转换服务
 * 负责将解析后的数据转换为预览数据和图表数据
 */

/**
 * 构建服务模块列表
 * @param {Map} serviceModuleMap - 服务模块映射
 * @returns {Array} 服务模块列表
 */
export function buildServiceModules(serviceModuleMap) {
  const serviceModules = [];
  serviceModuleMap.forEach((value, key) => {
    serviceModules.push({
      name: value.name,
      code: value.code,
      subDomain: value.subDomain,
      domain: value.domain,
      annotationCategory: value.annotationCategory || 'info',
      annotationContent: value.annotationContent || ''
    });
  });
  return serviceModules;
}

/**
 * 构建领域产品层级结构
 * 与Mermaid组件期望的结构一致
 * @param {Map} moduleHierarchy - 模块层级结构
 * @returns {Array} 领域产品数组
 */
export function buildDomainProducts(moduleHierarchy) {
  const domainProducts = [];
  moduleHierarchy.forEach((domainValue, domainKey) => {
    const domainObj = {
      name: domainKey,
      modules: []
    };
    domainValue.subDomains.forEach((subDomainValue, subDomainKey) => {
      const moduleObj = {
        name: subDomainKey,
        submodules: []  // 注意：Mermaid组件使用小写的submodules
      };
      // 转换服务模块数据格式
      subDomainValue.serviceModules.forEach(sm => {
        moduleObj.submodules.push({
          name: sm.name,
          code: sm.code,
          businessObjects: sm.businessObjects || []
        });
      });
      domainObj.modules.push(moduleObj);
    });
    domainProducts.push(domainObj);
  });
  return domainProducts;
}

/**
 * 构建预览数据
 * @param {Object} params - 参数对象
 * @param {Array} params.businessObjects - 业务对象数组
 * @param {Array} params.serviceModules - 服务模块数组
 * @param {Array} params.relationships - 关系数组
 * @param {Array} params.serviceModuleRelationships - 服务模块关系数组
 * @param {Array} params.domainProducts - 领域产品数组
 * @returns {Object} 预览数据对象
 */
export function buildPreviewData({
  businessObjects,
  serviceModules,
  relationships,
  serviceModuleRelationships,
  domainProducts
}) {
  return {
    businessObjects,
    serviceModules,
    relationships,
    serviceModuleRelationships,
    domainProducts
  };
}

/**
 * 提取所有子领域列表
 * @param {Array} domainProducts - 领域产品数组
 * @returns {Array} 子领域名称列表
 */
export function extractSubDomains(domainProducts) {
  const subDomains = new Set();
  if (domainProducts) {
    domainProducts.forEach(domain => {
      if (domain.modules) {
        domain.modules.forEach(module => {
          subDomains.add(module.name);
        });
      }
    });
  }
  return Array.from(subDomains);
}
