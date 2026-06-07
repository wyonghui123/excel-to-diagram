/**
 * 关系分类服务
 * 负责对业务对象关系进行分类和构建分类树结构
 */

import { createLogger } from '@/utils/logger'

const logger = createLogger('relationClassifier')

/**
 * 分类类型枚举
 */
export const CategoryType = {
  CROSS_DOMAIN: 'cross-domain',                         // 跨领域
  SAME_DOMAIN_CROSS_SUBDOMAIN: 'same-domain-cross-subdomain',  // 同领域跨子领域
  SAME_SUBDOMAIN_CROSS_MODULE: 'same-subdomain-cross-module',  // 同子领域跨服务模块
  SAME_MODULE: 'same-module'                            // 同服务模块
};

/**
 * 范围类型枚举
 */
export const ScopeType = {
  INTERNAL: 'internal',
  CROSS_BOUNDARY: 'cross-boundary',
  EXTERNAL: 'external'
};

/**
 * 分类单个关系
 * 优先使用后端返回的 scopeType/categoryType（后端已计算），fallback 到本地计算
 * @param {Object} rel - 关系对象（可能有 scopeType/categoryType，或需有 _sourceBo/_targetBo）
 * @param {Object} filterParams - { domainIds, subDomainIds, serviceModuleIds, businessObjectIds }
 * @param {Array<Object>} businessObjects - 业务对象列表
 * @returns {Object} { scopeType: string, categoryType: string }
 */
export function classifyRelation(rel, filterParams, businessObjects) { // eslint-disable-line no-unused-vars
  // 优先使用后端分类结果
  if (rel.scopeType && rel.categoryType) {
    return { scopeType: rel.scopeType, categoryType: rel.categoryType }
  }

  const srcBo = rel._sourceBo
  const tgtBo = rel._targetBo

  if (!srcBo || !tgtBo) return null

  if (srcBo.code === tgtBo.code) {
    return { scopeType: ScopeType.EXTERNAL, categoryType: CategoryType.CROSS_DOMAIN, filtered: true }
  }

  const srcDomainId = srcBo.domainId
  const tgtDomainId = tgtBo.domainId
  const srcSubDomainId = srcBo.subDomainId
  const tgtSubDomainId = tgtBo.subDomainId
  const srcModuleId = srcBo.serviceModuleId
  const tgtModuleId = tgtBo.serviceModuleId
  const srcBoId = srcBo.id
  const tgtBoId = tgtBo.id

  const { domainIds, subDomainIds, serviceModuleIds, businessObjectIds } = filterParams

  let srcInScope, tgtInScope

  if (businessObjectIds.length > 0) {
    srcInScope = businessObjectIds.includes(srcBoId)
    tgtInScope = businessObjectIds.includes(tgtBoId)
  } else if (serviceModuleIds.length > 0) {
    srcInScope = serviceModuleIds.includes(srcModuleId)
    tgtInScope = serviceModuleIds.includes(tgtModuleId)
  } else if (subDomainIds.length > 0) {
    srcInScope = subDomainIds.includes(srcSubDomainId)
    tgtInScope = subDomainIds.includes(tgtSubDomainId)
  } else if (domainIds.length > 0) {
    srcInScope = domainIds.includes(srcDomainId)
    tgtInScope = domainIds.includes(tgtDomainId)
  } else {
    srcInScope = true
    tgtInScope = true
  }

  const scopeType = (srcInScope && tgtInScope)
    ? ScopeType.INTERNAL
    : (srcInScope || tgtInScope)
      ? ScopeType.CROSS_BOUNDARY
      : ScopeType.EXTERNAL

  let categoryType
  if (srcDomainId !== tgtDomainId) {
    categoryType = CategoryType.CROSS_DOMAIN
  } else if (srcSubDomainId !== tgtSubDomainId) {
    categoryType = CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN
  } else if (srcModuleId !== tgtModuleId) {
    categoryType = CategoryType.SAME_SUBDOMAIN_CROSS_MODULE
  } else {
    categoryType = CategoryType.SAME_MODULE
  }

  if (scopeType !== ScopeType.INTERNAL && categoryType === CategoryType.SAME_MODULE) {
    if (srcSubDomainId !== tgtSubDomainId) {
      categoryType = CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN
    } else if (srcDomainId !== tgtDomainId) {
      categoryType = CategoryType.CROSS_DOMAIN
    }
  }

  return { scopeType, categoryType }
}

/**
 * 构建关系范围树结构（基于 filterParams）
 * @param {Object} filterParams - { domainIds, subDomainIds, serviceModuleIds, businessObjectIds }
 * @param {Array<Object>} allRelationships - 关系列表
 * @param {Array<Object>} businessObjects - 业务对象列表
 * @returns {Array<Object>} 关系范围树结构
 */
export function buildRelationScopeTree(filterParams, allRelationships, businessObjects) {
  if (!allRelationships || allRelationships.length === 0) return []

  const boByIdMap = new Map()
  const boByCodeMap = new Map()
  businessObjects.forEach(bo => {
    if (bo.id != null) boByIdMap.set(String(bo.id), bo)
    if (bo.code) boByCodeMap.set(String(bo.code), bo)
  })

  function getBoId(rel, side) {
    if (side === 'source') {
      return rel.sourceBoId || rel.source_bo_id
    } else {
      return rel.targetBoId || rel.target_bo_id
    }
  }

  function getBoCode(rel, side) {
    if (side === 'source') {
      return rel.sourceCode || rel.source_code
    } else {
      return rel.targetCode || rel.target_code
    }
  }

  function getBoInfo(rel, side) {
    const boId = getBoId(rel, side)
    const code = getBoCode(rel, side)

    if (boId != null) {
      const bo = boByIdMap.get(String(boId))
      if (bo) return bo
    }

    if (code) {
      const bo = boByCodeMap.get(String(code))
      if (bo) return bo
    }

    const prefix = side === 'source' ? 'source' : 'target'

    if (rel[prefix + '_domain_id'] != null || rel[prefix + '_code'] || code) {
      return {
        id: rel[prefix + '_bo_id'] || rel[prefix + 'BoId'],
        code: rel[prefix + '_code'] || rel[prefix + 'Code'] || '',
        name: rel[prefix + '_bo_name'] || rel[prefix + 'BoName'] || rel[prefix + '_code'] || '',
        domainId: rel[prefix + '_domain_id'] || rel[prefix + 'DomainId'],
        domain: rel[prefix + '_domain_name'] || rel[prefix + 'DomainName'] || '',
        subDomainId: rel[prefix + '_sub_domain_id'] || rel[prefix + 'SubDomainId'],
        subDomain: rel[prefix + '_sub_domain_name'] || rel[prefix + 'SubDomainName'] || '',
        serviceModuleId: rel[prefix + '_service_module_id'] || rel[prefix + 'ServiceModuleId'],
        serviceModule: rel[prefix + '_service_module_name'] || rel[prefix + 'ServiceModuleName'] || '',
        serviceModuleName: rel[prefix + '_service_module_name'] || rel[prefix + 'ServiceModuleName'] || ''
      }
    }

    return null
  }

  const seenIds = new Set()
  const uniqueRelations = allRelationships.filter(rel => {
    const id = rel.id ?? rel.relationCode ?? rel.relation_code
    if (id == null || seenIds.has(id)) return false
    seenIds.add(id)
    return true
  })

  uniqueRelations.forEach(rel => {
    const srcBo = getBoInfo(rel, 'source')
    const tgtBo = getBoInfo(rel, 'target')
    rel._sourceBo = srcBo
    rel._targetBo = tgtBo
  })

  const categoryStats = {
    [ScopeType.INTERNAL]: {
      [CategoryType.CROSS_DOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_MODULE]: { count: 0, relations: [], modules: {} }
    },
    [ScopeType.CROSS_BOUNDARY]: {
      [CategoryType.CROSS_DOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_MODULE]: { count: 0, relations: [], modules: {} }
    },
    [ScopeType.EXTERNAL]: {
      [CategoryType.CROSS_DOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_MODULE]: { count: 0, relations: [], modules: {} }
    }
  }

  uniqueRelations.forEach(rel => {
    const srcBo = rel._sourceBo
    const tgtBo = rel._targetBo

    // 树构建仍需 srcBo/tgtBo，后端分类结果不能替代层级信息
    if (!srcBo || !tgtBo) return
    if (srcBo.code === tgtBo.code) return

    const srcDomainId = srcBo.domainId
    const tgtDomainId = tgtBo.domainId
    if (srcDomainId == null || tgtDomainId == null) return

    const classification = classifyRelation(rel, filterParams, businessObjects)
    if (!classification || classification.filtered) return

    const { scopeType, categoryType } = classification

    const stats = categoryStats[scopeType][categoryType]

    stats.count++
    stats.relations.push(rel)

    if (categoryType === CategoryType.SAME_MODULE) {
      const moduleKey = [srcBo.serviceModuleId, tgtBo.serviceModuleId].sort().join('-')
      if (!stats.modules[moduleKey]) {
        stats.modules[moduleKey] = {
          name: moduleKey,
          count: 0,
          relations: [],
          sourceName: srcBo.serviceModuleName || srcBo.serviceModule || '未知模块',
          targetName: tgtBo.serviceModuleName || tgtBo.serviceModule || '未知模块'
        }
      }
      stats.modules[moduleKey].count++
      stats.modules[moduleKey].relations.push(rel)
    } else {
      const domainKey = [srcDomainId, tgtDomainId].sort().join('-')
      const srcDomainName = srcBo.domain || '未知领域'
      const tgtDomainName = tgtBo.domain || '未知领域'
      if (!stats.domains[domainKey]) {
        stats.domains[domainKey] = {
          name: domainKey,
          sourceName: srcDomainName,
          targetName: tgtDomainName,
          count: 0,
          subDomains: {},
          relations: []
        }
      }
      stats.domains[domainKey].count++
      stats.domains[domainKey].relations.push(rel)

      const subDomainKey = [srcBo.subDomainId, tgtBo.subDomainId].sort().join('-')
      const srcSubDomainName = srcBo.subDomain || '未知子域'
      const tgtSubDomainName = tgtBo.subDomain || '未知子域'
      if (!stats.domains[domainKey].subDomains[subDomainKey]) {
        stats.domains[domainKey].subDomains[subDomainKey] = {
          name: subDomainKey,
          sourceName: srcSubDomainName,
          targetName: tgtSubDomainName,
          count: 0,
          modules: {},
          relations: []
        }
      }
      stats.domains[domainKey].subDomains[subDomainKey].count++
      stats.domains[domainKey].subDomains[subDomainKey].relations.push(rel)

      const moduleKey = [srcBo.serviceModuleId, tgtBo.serviceModuleId].sort().join('-')
      if (!stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey]) {
        stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey] = {
          name: moduleKey,
          sourceName: srcBo.serviceModuleName || srcBo.serviceModule || '未知模块',
          targetName: tgtBo.serviceModuleName || tgtBo.serviceModule || '未知模块',
          count: 0,
          relations: []
        }
      }
      stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].count++
      stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].relations.push(rel)
    }
  })

  function buildScopeNode(scopeType, name, stats) {
    const categoryNames = {
      [CategoryType.CROSS_DOMAIN]: '跨领域',
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: '同领域跨子领域',
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: '同子领域跨服务模块',
      [CategoryType.SAME_MODULE]: '同服务模块'
    }

    const children = [
      buildCategoryNode(scopeType, CategoryType.CROSS_DOMAIN, categoryNames[CategoryType.CROSS_DOMAIN], stats[CategoryType.CROSS_DOMAIN]),
      buildCategoryNode(scopeType, CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN, categoryNames[CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN], stats[CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]),
      buildCategoryNode(scopeType, CategoryType.SAME_SUBDOMAIN_CROSS_MODULE, categoryNames[CategoryType.SAME_SUBDOMAIN_CROSS_MODULE], stats[CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]),
      buildCategoryNode(scopeType, CategoryType.SAME_MODULE, categoryNames[CategoryType.SAME_MODULE], stats[CategoryType.SAME_MODULE])
    ].filter(node => node.count > 0)

    const totalCount = children.reduce((sum, child) => sum + child.count, 0)

    return {
      id: scopeType,
      name,
      scopeType,
      count: totalCount,
      children
    }
  }

  function buildCategoryNode(scopeType, categoryType, name, stats) {
    const node = {
      id: `${scopeType}-${categoryType}`,
      name,
      scopeType,
      categoryType,
      count: 0,
      childCount: 0,
      children: []
    }

    if (categoryType === CategoryType.SAME_MODULE) {
      Object.values(stats.modules).forEach(moduleData => {
        const displayName = `${moduleData.sourceName}-${moduleData.targetName}`
        node.children.push({
          id: `${scopeType}-${categoryType}-module-${moduleData.name}`,
          name: displayName,
          scopeType,
          categoryType,
          level: 'module',
          count: moduleData.count,
          relationCodes: moduleData.relations.map(r => r.relation_code || r.relationCode),
          // [FIX] relationIds: 关系记录 ID 列表，用于精确过滤（relation_code 是类型编码，不唯一）
          relationIds: moduleData.relations.map(r => r.id).filter(Boolean),
          _relationScopes: moduleData.relations.map(r => ({
            src: {
              domainId: r._sourceBo?.domainId,
              subDomainId: r._sourceBo?.subDomainId,
              moduleId: r._sourceBo?.serviceModuleId,
              boId: r._sourceBo?.id
            },
            tgt: {
              domainId: r._targetBo?.domainId,
              subDomainId: r._targetBo?.subDomainId,
              moduleId: r._targetBo?.serviceModuleId,
              boId: r._targetBo?.id
            }
          }))
        })
        node.count += moduleData.count
      })
      node.childCount = node.children.length
    } else {
      Object.values(stats.domains).forEach(domainData => {
        if (!domainData.sourceName && !domainData.targetName) {
          return
        }
        const displayName = `${domainData.sourceName}-${domainData.targetName}`
        const domainNode = {
          id: `${scopeType}-${categoryType}-domain-${domainData.name}`,
          name: displayName,
          scopeType,
          categoryType,
          level: 'domain',
          count: domainData.count,
          childCount: 0,
          children: []
        }

        Object.values(domainData.subDomains).forEach(subDomainData => {
          const subDisplayName = `${subDomainData.sourceName}-${subDomainData.targetName}`
          const subDomainNode = {
            id: `${scopeType}-${categoryType}-subdomain-${subDomainData.name}`,
            name: subDisplayName,
            scopeType,
            categoryType,
            level: 'subDomain',
            count: subDomainData.count,
            childCount: 0,
            children: []
          }

          Object.values(subDomainData.modules).forEach(moduleData => {
            const moduleDisplayName = `${moduleData.sourceName}-${moduleData.targetName}`
            subDomainNode.children.push({
              id: `${scopeType}-${categoryType}-module-${moduleData.name}`,
              name: moduleDisplayName,
              scopeType,
              categoryType,
              level: 'module',
              count: moduleData.count,
              relationCodes: moduleData.relations.map(r => r.relation_code || r.relationCode),
          // [FIX] relationIds: 关系记录 ID 列表，用于精确过滤（relation_code 是类型编码，不唯一）
          relationIds: moduleData.relations.map(r => r.id).filter(Boolean),
              _relationScopes: moduleData.relations.map(r => ({
                src: {
                  domainId: r._sourceBo?.domainId,
                  subDomainId: r._sourceBo?.subDomainId,
                  moduleId: r._sourceBo?.serviceModuleId,
                  boId: r._sourceBo?.id
                },
                tgt: {
                  domainId: r._targetBo?.domainId,
                  subDomainId: r._targetBo?.subDomainId,
                  moduleId: r._targetBo?.serviceModuleId,
                  boId: r._targetBo?.id
                }
              }))
            })
          })
          subDomainNode.childCount = subDomainNode.children.length

          domainNode.children.push(subDomainNode)
        })
        domainNode.childCount = domainNode.children.length
        node.children.push(domainNode)
        node.count += domainData.count
      })
      node.childCount = node.children.length
    }

    return node
  }

  const tree = [
    buildScopeNode(ScopeType.INTERNAL, '范围内', categoryStats[ScopeType.INTERNAL]),
    buildScopeNode(ScopeType.CROSS_BOUNDARY, '范围内与外部', categoryStats[ScopeType.CROSS_BOUNDARY]),
    buildScopeNode(ScopeType.EXTERNAL, '范围外', categoryStats[ScopeType.EXTERNAL])
  ].filter(node => node.count > 0)

  return tree
}

/**
 * 基于 centerScope 编码数组的旧版分类逻辑（供 buildRelationCategoryTree 内部使用）
 * @param {Object} relation - 关系对象
 * @param {Array<string>} centerScope - 中心范围业务对象编码数组
 * @param {Array<Object>} businessObjects - 业务对象列表
 * @param {Map} boMap - 业务对象编码到业务对象的映射
 * @returns {Object} { scopeType: string, categoryType: string }
 */
function classifyRelationByCodes(relation, centerScope, businessObjects, boMap) {
  // 过滤自环关系
  if (relation.sourceCode === relation.targetCode) {
    return {
      scopeType: ScopeType.EXTERNAL,
      categoryType: CategoryType.CROSS_DOMAIN,
      filtered: true
    };
  }

  // 获取源和目标业务对象
  const sourceBO = boMap.get(relation.sourceCode);
  const targetBO = boMap.get(relation.targetCode);

  // 如果源或目标业务对象不存在，返回默认值
  if (!sourceBO || !targetBO) {
    return {
      scopeType: ScopeType.EXTERNAL,
      categoryType: CategoryType.CROSS_DOMAIN
    };
  }

  // 判断范围类型：源和目标是否都在中心范围内
  const sourceInScope = centerScope.includes(relation.sourceCode);
  const targetInScope = centerScope.includes(relation.targetCode);
  const scopeType = (sourceInScope && targetInScope)
    ? ScopeType.INTERNAL
    : ScopeType.EXTERNAL;

  // 判断分类类型：根据层级关系
  let categoryType;

  if (sourceBO.domain !== targetBO.domain) {
    categoryType = CategoryType.CROSS_DOMAIN;
  } else if (sourceBO.subDomain !== targetBO.subDomain) {
    categoryType = CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN;
  } else if (sourceBO.serviceModule !== targetBO.serviceModule) {
    categoryType = CategoryType.SAME_SUBDOMAIN_CROSS_MODULE;
  } else {
    categoryType = CategoryType.SAME_MODULE;
  }

  // 如果是外部关系但服务模块相同，需要按更高级别分类
  if (scopeType === ScopeType.EXTERNAL && categoryType === CategoryType.SAME_MODULE) {
    if (sourceBO.subDomain !== targetBO.subDomain) {
      categoryType = CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN;
    } else if (sourceBO.domain !== targetBO.domain) {
      categoryType = CategoryType.CROSS_DOMAIN;
    }
  }

  return {
    scopeType,
    categoryType
  };
}

/**
 * 构建关系分类树结构（旧版，基于 centerScope 编码数组）
 * @param {Array<Object>} relations - 关系列表
 * @param {Array<string>} centerScope - 中心范围业务对象编码数组
 * @param {Array<Object>} businessObjects - 业务对象列表
 * @returns {Array<Object>} 关系分类树结构
 */
export function buildRelationCategoryTree(relations, centerScope, businessObjects) {
  logger.debug('relations count:', relations?.length)
  logger.debug('centerScope length:', centerScope?.length)
  logger.debug('businessObjects count:', businessObjects?.length)

  // 创建业务对象编码到业务对象的映射
  const boMap = new Map();
  businessObjects.forEach(bo => {
    boMap.set(bo.code, bo);
  });

  // 初始化分类统计
  const categoryStats = {
    [ScopeType.INTERNAL]: {
      [CategoryType.CROSS_DOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_MODULE]: { count: 0, relations: [], modules: {} }
    },
    [ScopeType.EXTERNAL]: {
      [CategoryType.CROSS_DOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]: { count: 0, relations: [], domains: {} },
      [CategoryType.SAME_MODULE]: { count: 0, relations: [], modules: {} }
    }
  };

  // 遍历所有关系，进行分类统计
  // 先按 relationCode 去重，避免重复计数
  const seenCodes = new Set()
  const uniqueRelations = relations.filter(rel => {
    if (!rel.relationCode || seenCodes.has(rel.relationCode)) return false
    seenCodes.add(rel.relationCode)
    return true
  })

  uniqueRelations.forEach(relation => {
    // 跳过自环关系
    if (relation.sourceCode === relation.targetCode) {
      return;
    }

    // 判断源和目标是否在中心范围内
    const sourceInScope = centerScope.includes(relation.sourceCode);
    const targetInScope = centerScope.includes(relation.targetCode);

    // 如果源和目标都不在中心范围内，跳过此关系
    if (!sourceInScope && !targetInScope) {
      return;
    }

    const classification = classifyRelationByCodes(relation, centerScope, businessObjects, boMap);

    const { scopeType, categoryType } = classification;
    const stats = categoryStats[scopeType][categoryType];

    stats.count++;
    stats.relations.push(relation);

    // 根据分类类型构建层级结构
    const sourceBO = boMap.get(relation.sourceCode);
    const targetBO = boMap.get(relation.targetCode);

    if (sourceBO && targetBO) {
      if (categoryType === CategoryType.SAME_MODULE) {
        // 同服务模块：按服务模块分组（使用排序后的 key 避免方向影响）
        const modulePair = [sourceBO.serviceModule, targetBO.serviceModule].sort();
        const moduleKey = `${modulePair[0]}-${modulePair[1]}`;
        if (!stats.modules[moduleKey]) {
          stats.modules[moduleKey] = {
            name: moduleKey,
            count: 0,
            relations: [],
            sourceName: sourceBO.serviceModuleName || modulePair[0],
            targetName: targetBO.serviceModuleName || modulePair[1]
          };
        }
        stats.modules[moduleKey].count++;
        stats.modules[moduleKey].relations.push(relation);
      } else {
        // 其他类型：按领域/子领域分组，记录源和目标信息（不考虑方向）
        // 使用排序后的 key 确保方向不影响统计
        const domainPair = [sourceBO.domain, targetBO.domain].sort();
        const domainKey = `${domainPair[0]}-${domainPair[1]}`;
        if (!stats.domains[domainKey]) {
          stats.domains[domainKey] = {
            name: domainKey,
            sourceName: domainPair[0],
            targetName: domainPair[1],
            count: 0,
            subDomains: {},
            relations: []
          };
        }
        stats.domains[domainKey].count++;
        stats.domains[domainKey].relations.push(relation);

        // 跨领域：也需要按子领域和服务模块细分
        if (categoryType === CategoryType.CROSS_DOMAIN) {
          const subDomainPair = [sourceBO.subDomain, targetBO.subDomain].sort();
          const subDomainKey = `${subDomainPair[0]}-${subDomainPair[1]}`;
          if (!stats.domains[domainKey].subDomains[subDomainKey]) {
            stats.domains[domainKey].subDomains[subDomainKey] = {
              name: subDomainKey,
              sourceName: subDomainPair[0],
              targetName: subDomainPair[1],
              count: 0,
              modules: {},
              relations: []
            };
          }
          stats.domains[domainKey].subDomains[subDomainKey].count++;
          stats.domains[domainKey].subDomains[subDomainKey].relations.push(relation);

          // 跨领域也需要细分到服务模块级别
          const modulePair = [sourceBO.serviceModule, targetBO.serviceModule].sort();
          const moduleKey = `${modulePair[0]}-${modulePair[1]}`;
          if (!stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey]) {
            stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey] = {
              name: moduleKey,
              sourceName: sourceBO.serviceModuleName || sourceBO.serviceModule,
              targetName: targetBO.serviceModuleName || targetBO.serviceModule,
              count: 0,
              relations: []
            };
          }
          stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].count++;
          stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].relations.push(relation);
        }

        // 如果是跨子领域或跨服务模块，继续细分
        if (categoryType === CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN ||
            categoryType === CategoryType.SAME_SUBDOMAIN_CROSS_MODULE) {
          const subDomainPair = [sourceBO.subDomain, targetBO.subDomain].sort();
          const subDomainKey = `${subDomainPair[0]}-${subDomainPair[1]}`;
          if (!stats.domains[domainKey].subDomains[subDomainKey]) {
            stats.domains[domainKey].subDomains[subDomainKey] = {
              name: subDomainKey,
              sourceName: subDomainPair[0],
              targetName: subDomainPair[1],
              count: 0,
              modules: {},
              relations: []
            };
          }
          stats.domains[domainKey].subDomains[subDomainKey].count++;
          stats.domains[domainKey].subDomains[subDomainKey].relations.push(relation);

          // 同领域跨子领域和跨服务模块都需要细分到服务模块级别
          const modulePair = [sourceBO.serviceModule, targetBO.serviceModule].sort();
          const moduleKey = `${modulePair[0]}-${modulePair[1]}`;
          if (!stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey]) {
            stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey] = {
              name: moduleKey,
              sourceName: sourceBO.serviceModuleName || sourceBO.serviceModule,
              targetName: targetBO.serviceModuleName || targetBO.serviceModule,
              count: 0,
              relations: []
            };
          }
          stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].count++;
          stats.domains[domainKey].subDomains[subDomainKey].modules[moduleKey].relations.push(relation);
        }
      }
    } else {
      const fallbackKey = '_external_';
      if (!stats.domains[fallbackKey]) {
        stats.domains[fallbackKey] = {
          name: fallbackKey,
          sourceName: relation.sourceCode || 'external',
          targetName: relation.targetCode || 'external',
          count: 0,
          subDomains: {},
          relations: []
        };
      }
      stats.domains[fallbackKey].count++;
      stats.domains[fallbackKey].relations.push(relation);

      if (!stats.domains[fallbackKey].subDomains[fallbackKey]) {
        stats.domains[fallbackKey].subDomains[fallbackKey] = {
          name: fallbackKey,
          sourceName: relation.sourceCode || 'external',
          targetName: relation.targetCode || 'external',
          count: 0,
          modules: {},
          relations: []
        };
      }
      stats.domains[fallbackKey].subDomains[fallbackKey].count++;
      stats.domains[fallbackKey].subDomains[fallbackKey].relations.push(relation);

      const moduleFallbackKey = `${relation.sourceCode || 'ext'}-${relation.targetCode || 'ext'}`;
      if (!stats.domains[fallbackKey].subDomains[fallbackKey].modules[moduleFallbackKey]) {
        stats.domains[fallbackKey].subDomains[fallbackKey].modules[moduleFallbackKey] = {
          name: moduleFallbackKey,
          sourceName: relation.sourceCode || 'external',
          targetName: relation.targetCode || 'external',
          count: 0,
          relations: [],
          relationCodes: []
        };
      }
      stats.domains[fallbackKey].subDomains[fallbackKey].modules[moduleFallbackKey].count++;
      stats.domains[fallbackKey].subDomains[fallbackKey].modules[moduleFallbackKey].relations.push(relation);
      stats.domains[fallbackKey].subDomains[fallbackKey].modules[moduleFallbackKey].relationCodes.push(relation.relationCode);
    }
  });

  // 构建树结构
  const tree = [
    buildCategoryScopeNode(ScopeType.INTERNAL, '中心范围内对象关系', categoryStats[ScopeType.INTERNAL]),
    buildCategoryScopeNode(ScopeType.EXTERNAL, '中心范围与外部对象关系', categoryStats[ScopeType.EXTERNAL])
  ];

  return tree;
}

/**
 * 构建范围节点（供 buildRelationCategoryTree 使用）
 * @param {string} scopeType - 范围类型
 * @param {string} name - 节点名称
 * @param {Object} stats - 统计数据
 * @returns {Object} 范围节点
 */
function buildCategoryScopeNode(scopeType, name, stats) {
  const children = [
    buildCategoryCategoryNode(scopeType, CategoryType.CROSS_DOMAIN, '跨领域', stats[CategoryType.CROSS_DOMAIN]),
    buildCategoryCategoryNode(scopeType, CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN, '同领域跨子领域', stats[CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN]),
    buildCategoryCategoryNode(scopeType, CategoryType.SAME_SUBDOMAIN_CROSS_MODULE, '同子领域跨服务模块', stats[CategoryType.SAME_SUBDOMAIN_CROSS_MODULE]),
    buildCategoryCategoryNode(scopeType, CategoryType.SAME_MODULE, '同服务模块', stats[CategoryType.SAME_MODULE])
  ];

  const totalCount = children.reduce((sum, child) => sum + child.count, 0);

  return {
    id: scopeType,
    name,
    scopeType,
    count: totalCount,
    children
  };
}

/**
 * 构建分类节点（供 buildRelationCategoryTree 使用）
 * @param {string} scopeType - 范围类型
 * @param {string} categoryType - 分类类型
 * @param {string} name - 节点名称
 * @param {Object} stats - 统计数据
 * @returns {Object} 分类节点
 */
function buildCategoryCategoryNode(scopeType, categoryType, name, stats) {
  const node = {
    id: `${scopeType}-${categoryType}`,
    name,
    scopeType,
    categoryType,
    count: stats.count,
    childCount: 0,
    children: []
  };

  // 根据分类类型构建子节点
  if (categoryType === CategoryType.SAME_MODULE) {
    // 同服务模块：添加服务模块级节点
    Object.values(stats.modules).forEach(moduleData => {
      const displayName = `${moduleData.sourceName}-${moduleData.targetName}`;
      node.children.push({
        id: `${scopeType}-${categoryType}-module-${moduleData.name}`,
        name: displayName,
        scopeType,
        categoryType,
        level: 'module',
        count: moduleData.count,
        relationCodes: moduleData.relations.map(r => r.relationCode)
      });
    });
    node.childCount = node.children.length;
  } else {
    // 其他类型：添加领域级、子领域级、服务模块级节点
    Object.values(stats.domains).forEach(domainData => {
      const displayName = `${domainData.sourceName}-${domainData.targetName}`;
      const domainNode = {
        id: `${scopeType}-${categoryType}-domain-${domainData.name}`,
        name: displayName,
        scopeType,
        categoryType,
        level: 'domain',
        count: domainData.count,
        childCount: 0,
        children: []
      };

      // 跨领域、同领域跨子领域、同子领域跨服务模块都需要添加子领域级节点
      if (categoryType === CategoryType.CROSS_DOMAIN ||
          categoryType === CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN ||
          categoryType === CategoryType.SAME_SUBDOMAIN_CROSS_MODULE) {
        Object.values(domainData.subDomains).forEach(subDomainData => {
          const subDisplayName = `${subDomainData.sourceName}-${subDomainData.targetName}`;
          const subDomainNode = {
            id: `${scopeType}-${categoryType}-subdomain-${subDomainData.name}`,
            name: subDisplayName,
            scopeType,
            categoryType,
            level: 'subDomain',
            count: subDomainData.count,
            childCount: 0,
            children: []
          };

          // 跨领域、同领域跨子领域、同子领域跨服务模块都需要添加服务模块级节点
          if (categoryType === CategoryType.CROSS_DOMAIN ||
              categoryType === CategoryType.SAME_DOMAIN_CROSS_SUBDOMAIN ||
              categoryType === CategoryType.SAME_SUBDOMAIN_CROSS_MODULE) {
            Object.values(subDomainData.modules).forEach(moduleData => {
              const moduleDisplayName = `${moduleData.sourceName}-${moduleData.targetName}`;
              subDomainNode.children.push({
                id: `${scopeType}-${categoryType}-module-${moduleData.name}`,
                name: moduleDisplayName,
                scopeType,
                categoryType,
                level: 'module',
                count: moduleData.count,
                relationCodes: moduleData.relations.map(r => r.relationCode)
              });
            });
            subDomainNode.childCount = subDomainNode.children.length;
          }

          domainNode.children.push(subDomainNode);
        });
        domainNode.childCount = domainNode.children.length;
      }
      // 注意：所有外部关系类型现在都有完整的层级结构（领域->子领域->服务模块）
      // 所以不需要在领域节点直接包含关系编码

      node.children.push(domainNode);
    });
    node.childCount = node.children.length;
  }

  return node;
}

/**
 * 获取选中的关系编码数组
 * @param {Array<Object>} relationCategoryTree - 关系分类树
 * @param {Array<string>} selectedNodeIds - 选中的节点ID数组
 * @returns {Array<string>} 选中的关系编码数组
 */
export function getSelectedRelationCodes(relationCategoryTree, selectedNodeIds) {
  const relationCodes = new Set();

  function collectRelationCodesFromNode(node) {
    const codes = [];
    if (node.relationCodes && node.relationCodes.length > 0) {
      codes.push(...node.relationCodes);
    }
    if (node.children && node.children.length > 0) {
      node.children.forEach(child => {
        codes.push(...collectRelationCodesFromNode(child));
      });
    }
    return codes;
  }

  function traverseNode(node) {
    if (selectedNodeIds.includes(node.id)) {
      collectRelationCodesFromNode(node).forEach(code => relationCodes.add(code));
    }
    if (node.children && node.children.length > 0) {
      node.children.forEach(child => traverseNode(child));
    }
  }

  relationCategoryTree.forEach(rootNode => traverseNode(rootNode));

  return Array.from(relationCodes);
}
