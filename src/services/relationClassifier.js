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
      if (bo) {
        // [v1.1.15 修复] BO 列表 (/api/v2/bo/business_object) 返回的字段是 snake_case
        //   (domain_id/sub_domain_id/service_module_id), 但 classifyRelation/buildScopeNode
        //   用 camelCase (domainId/subDomainId/serviceModuleId) 访问, 导致全 undefined,
        //   关系被错归 SAME_MODULE 或被 srcDomainId==null 跳过, 树为空.
        // 修复: 从 map 中找到的 BO 加上 camelCase 别名, 兼容旧 classifyRelation 逻辑.
        return {
          ...bo,
          id: bo.id,
          code: bo.code,
          name: bo.name ?? bo.display_name,
          domainId: bo.domainId ?? bo.domain_id,
          subDomainId: bo.subDomainId ?? bo.sub_domain_id,
          serviceModuleId: bo.serviceModuleId ?? bo.service_module_id,
          domain: bo.domain ?? bo.domain_name,
          subDomain: bo.subDomain ?? bo.sub_domain_name,
          serviceModule: bo.serviceModule ?? bo.service_module_name,
          serviceModuleName: bo.serviceModuleName ?? bo.service_module_name
        }
      }
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

  // [perf-2026-06-29] 单次遍历合并: 原代码先 forEach 解析 srcBo/tgtBo (mutate rel._sourceBo/_targetBo),
  //   再 forEach 分类统计. 两次遍历 5634 rel × 2 = 11268 次循环, 但中间无副作用.
  //   合并为 1 次遍历, 对每条 rel: 解析 → mutate → 过滤 → 分类 → 统计. 行为等价.
  //   关键不变量: mutate 永远在过滤前完成, 下游消费者仍能读取 _sourceBo/_targetBo.

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
    // [perf-2026-06-29] 单次遍历: 解析 + mutate (保留原第 1 次遍历行为, 下游消费者依赖 _sourceBo/_targetBo)
    const srcBo = getBoInfo(rel, 'source')
    const tgtBo = getBoInfo(rel, 'target')
    rel._sourceBo = srcBo
    rel._targetBo = tgtBo

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

    // 关键修复 v26：scope 节点也聚合子节点的 relationIds
    const allChildIds = new Set()
    children.forEach(child => {
      if (child.relationIds && child.relationIds.length > 0) {
        child.relationIds.forEach(id => allChildIds.add(id))
      }
    })

    return {
      id: scopeType,
      name,
      scopeType,
      count: totalCount,
      children,
      relationIds: Array.from(allChildIds)
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
      children: [],
      // 关键修复 v26：所有层级节点都聚合 relationIds，便于上溯过滤
      relationIds: []
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

    // 关键修复 v26：聚合子节点 relationIds 列表供上层节点使用
    const allChildIds = new Set()
    node.children.forEach(child => {
      if (child.relationIds && child.relationIds.length > 0) {
        child.relationIds.forEach(id => allChildIds.add(id))
      }
    })
    node.relationIds = Array.from(allChildIds)

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

  // 关键修复 v32: 优先采用后端分类结果 (archDataConverter.js line 143-144 把
  // rel.scope_type / rel.category_type 映射到 rel.scopeType / rel.categoryType)
  // 后端在 architecture/preview API 已基于后端 center_scope 算过 scope_type/category_type
  // 后端给的值更权威 (跟 management 页 buildRelationScopeTree 一致),
  // 不优先采用会导致 management 页 1+4=5 vs 图表页 1+6=7 的统计差异
  if (relation.scopeType) {
    return {
      scopeType: relation.scopeType,
      categoryType: relation.categoryType || CategoryType.CROSS_DOMAIN  // 兜底
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
  // 三分法: 范围内 / 跨域 / 范围外 (v29)
  const scopeType = (sourceInScope && targetInScope)
    ? ScopeType.INTERNAL
    : (sourceInScope || targetInScope)
      ? ScopeType.CROSS_BOUNDARY
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
  };

  // 遍历所有关系，进行分类统计
  // 关键修复 v26：按 rel.id 去重（每条关系都是 unique record），
  // 之前按 relationCode 去重会导致：
  //   1. 同一 type 的多条关系只算 1 个（如 4 条 CONTAINS 只显示 1 个）
  //   2. relationCode 为空的关系被 !rel.relationCode 过滤掉
  // 这导致架构管理显示 29 关系、chart 页面只显示 21 关系，统计口径不一致
  const seenIds = new Set()
  const uniqueRelations = relations.filter(rel => {
    const id = rel.id ?? rel.relationCode
    if (id == null || seenIds.has(id)) return false
    seenIds.add(id)
    return true
  })

  uniqueRelations.forEach(relation => {
    // 跳过自环关系
    if (relation.sourceCode === relation.targetCode) {
      return;
    }

    // 关键修复 v32: 不再硬过滤 EXTERNAL 关系
    // 一律交给 classifyRelationByCodes 处理 (它优先采用后端 scopeType/categoryType)
    // EXTERNAL 关系 (src/tgt 都不在 centerScope) 也入 tree 归到 EXTERNAL scope,
    // 这样 getSelectedRelationIds 才能选中 EXTERNAL scope 节点下的关系
    // 与 management 页"范围内 (5) + 范围内与外部 (8) + 范围外" 三段式对齐
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
      // 关键修复 v32: sourceBO/targetBO 缺失时 (后端 hierarchyFilter 没返回外部 BO),
      // SAME_MODULE stats 没有 domains 字段, 需先补一个, 避免 page crash
      const fallbackKey = '_external_';
      if (!stats.domains) {
        stats.domains = {};
      }
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
  // [V1.2.8 修复] 添加 CROSS_BOUNDARY 节点，否则跨域关系不出现在树中，用户无法选中
  const tree = [
    buildCategoryScopeNode(ScopeType.INTERNAL, '中心范围内对象关系', categoryStats[ScopeType.INTERNAL]),
    buildCategoryScopeNode(ScopeType.CROSS_BOUNDARY, '中心范围与外部对象关系', categoryStats[ScopeType.CROSS_BOUNDARY]),
    buildCategoryScopeNode(ScopeType.EXTERNAL, '范围外对象关系', categoryStats[ScopeType.EXTERNAL])
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

  // 关键修复 v26：scope 节点也聚合子节点 relationIds
  const allChildIds = new Set();
  const allChildCodes = new Set();
  children.forEach(child => {
    if (child.relationIds && child.relationIds.length > 0) {
      child.relationIds.forEach(id => allChildIds.add(id));
    }
    // [V1.2.8 修复] 聚合 relationCodes
    if (child.relationCodes && child.relationCodes.length > 0) {
      child.relationCodes.forEach(code => allChildCodes.add(code));
    }
  });

  return {
    id: scopeType,
    name,
    scopeType,
    count: totalCount,
    children,
    relationIds: Array.from(allChildIds),
    relationCodes: Array.from(allChildCodes)
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
    children: [],
    // 关键修复 v26：所有层级节点都聚合 relationIds，便于上溯过滤
    relationIds: [],
    // [V1.2.8 修复] 聚合所有子节点的 relationCodes，便于 findNodeIdsForCodes 匹配
    relationCodes: []
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
        relationCodes: moduleData.relations.map(r => r.relationCode),
        // 关键修复 v26：module 子节点带 relationIds（按 rel.id）
        relationIds: moduleData.relations.map(r => r.id).filter(Boolean)
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
        children: [],
        relationIds: [],
        // [V1.2.8 修复] 聚合 relationCodes
        relationCodes: []
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
            children: [],
            relationIds: [],
            // [V1.2.8 修复] 聚合 relationCodes
            relationCodes: []
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
                relationCodes: moduleData.relations.map(r => r.relationCode),
                // 关键修复 v26：module 子节点带 relationIds（按 rel.id）
                relationIds: moduleData.relations.map(r => r.id).filter(Boolean)
              });
            });
            subDomainNode.childCount = subDomainNode.children.length;
            // 关键修复 v26: subDomainNode 聚合其子 module 节点的 relationIds
            const allSubChildIds = new Set();
            const allSubChildCodes = new Set();
            subDomainNode.children.forEach(child => {
              if (child.relationIds && child.relationIds.length > 0) {
                child.relationIds.forEach(id => allSubChildIds.add(id));
              }
              // [V1.2.8 修复] 聚合 relationCodes
              if (child.relationCodes && child.relationCodes.length > 0) {
                child.relationCodes.forEach(code => allSubChildCodes.add(code));
              }
            });
            subDomainNode.relationIds = Array.from(allSubChildIds);
            subDomainNode.relationCodes = Array.from(allSubChildCodes);
          }

          domainNode.children.push(subDomainNode);
        });
        // 关键修复 v26: domainNode 聚合其子 subDomain 节点的 relationIds
        const allDomainChildIds = new Set();
        const allDomainChildCodes = new Set();
        domainNode.children.forEach(child => {
          if (child.relationIds && child.relationIds.length > 0) {
            child.relationIds.forEach(id => allDomainChildIds.add(id));
          }
          // [V1.2.8 修复] 聚合 relationCodes
          if (child.relationCodes && child.relationCodes.length > 0) {
            child.relationCodes.forEach(code => allDomainChildCodes.add(code));
          }
        });
        domainNode.relationIds = Array.from(allDomainChildIds);
        domainNode.relationCodes = Array.from(allDomainChildCodes);
        domainNode.childCount = domainNode.children.length;
      }
      // 注意：所有外部关系类型现在都有完整的层级结构（领域->子领域->服务模块）
      // 所以不需要在领域节点直接包含关系编码

      node.children.push(domainNode);
    });
    node.childCount = node.children.length;
  }

  // 关键修复 v26：聚合子节点 relationIds 列表供上层节点使用
  const allChildIds = new Set();
  const allChildCodes = new Set();
  node.children.forEach(child => {
    if (child.relationIds && child.relationIds.length > 0) {
      child.relationIds.forEach(id => allChildIds.add(id));
    }
    // [V1.2.8 修复] 聚合子节点 relationCodes
    if (child.relationCodes && child.relationCodes.length > 0) {
      child.relationCodes.forEach(code => allChildCodes.add(code));
    }
  });
  node.relationIds = Array.from(allChildIds);
  node.relationCodes = Array.from(allChildCodes);

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

/**
 * 获取选中的关系 ID 数组（按关系记录 ID 去重，而不是按关系类型编码）
 * 关键修复 v26：解决 chart 页面显示关系数比架构管理少 8 个的问题
 * - 之前 getSelectedRelationCodes 按 relationCode（关系类型）去重：
 *   4 条 CONTAINS 关系只算 1 个，1 条空 relationCode 被过滤掉 → 21 个
 * - 现在按 rel.id（关系记录 ID）去重：每条关系都是 unique → 29 个
 * @param {Array<Object>} relationCategoryTree - 关系分类树
 * @param {Array<string>} selectedNodeIds - 选中的节点ID数组
 * @returns {Array<number|string>} 选中的关系记录 ID 数组（去重）
 */
export function getSelectedRelationIds(relationCategoryTree, selectedNodeIds) {
  const relationIds = new Set();

  function collectRelationIdsFromNode(node) {
    const ids = [];
    // 同 module 节点直接带 relationIds（line 345/405）
    if (node.relationIds && node.relationIds.length > 0) {
      ids.push(...node.relationIds);
    }
    // 兼容：只带 relationCodes 的老节点，逐一加 code 进 set（fallback）
    if (node.relationCodes && node.relationCodes.length > 0 && (!node.relationIds || node.relationIds.length === 0)) {
      node.relationCodes.forEach(c => ids.push(c));
    }
    if (node.children && node.children.length > 0) {
      node.children.forEach(child => {
        ids.push(...collectRelationIdsFromNode(child));
      });
    }
    return ids;
  }

  function traverseNode(node) {
    if (selectedNodeIds.includes(node.id)) {
      collectRelationIdsFromNode(node).forEach(id => relationIds.add(id));
    }
    if (node.children && node.children.length > 0) {
      node.children.forEach(child => traverseNode(child));
    }
  }

  if (!Array.isArray(relationCategoryTree) || relationCategoryTree.length === 0) {
    return [];
  }

  relationCategoryTree.forEach(rootNode => traverseNode(rootNode));

  return Array.from(relationIds);
}
