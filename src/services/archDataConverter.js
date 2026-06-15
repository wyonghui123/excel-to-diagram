/* global URLSearchParams */
import { apiV2 } from '@/utils/httpClient'

/**
 * 从后端 architecture/preview 聚合 API 获取完整树结构数据
 * 替代原先 5 次独立 API 调用 (4×boService.query + 1×fetchRelationships)
 * @param {number|string} versionId
 * @param {Object} hierarchyFilter - { domain_id, sub_domain_id, service_module_id, business_object_id }
 * @returns {Object} { domains, subDomains, serviceModules, businessObjects, relationships, centerScope }
 */
async function fetchPreviewData(versionId, hierarchyFilter = {}) {
  const params = new URLSearchParams()
  if (versionId) params.set('version_id', versionId)

  // 将 hierarchyFilter 中的 ID 数组转为逗号分隔字符串
  const domainIds = hierarchyFilter.domain_id || hierarchyFilter.domainIds
  const subDomainIds = hierarchyFilter.sub_domain_id || hierarchyFilter.subDomainIds
  const serviceModuleIds = hierarchyFilter.service_module_id || hierarchyFilter.serviceModuleIds
  const businessObjectIds = hierarchyFilter.business_object_id || hierarchyFilter.businessObjectIds

  if (domainIds && domainIds.length > 0) params.set('domain_ids', domainIds.join(','))
  if (subDomainIds && subDomainIds.length > 0) params.set('sub_domain_ids', subDomainIds.join(','))
  if (serviceModuleIds && serviceModuleIds.length > 0) params.set('service_module_ids', serviceModuleIds.join(','))
  if (businessObjectIds && businessObjectIds.length > 0) params.set('business_object_ids', businessObjectIds.join(','))

  const result = await apiV2.get(`/bo/architecture/preview?${params.toString()}`)
  if (!result.success) {
    throw new Error(result.message || 'Failed to fetch architecture preview')
  }

  const data = result.data
  return {
    domains: data.domains || [],
    subDomains: data.sub_domains || [],
    serviceModules: data.service_modules || [],
    businessObjects: data.business_objects || [],
    relationships: data.relationships || [],
    centerScope: data.center_scope || []
  }
}

function buildDomainProducts(domains, subDomains, serviceModules, businessObjects) {
  const subDomainMap = new Map()
  const serviceModuleMap = new Map()
  const smCodeMap = new Map()

  for (const sd of subDomains) {
    if (!subDomainMap.has(sd.domain_id)) {
      subDomainMap.set(sd.domain_id, [])
    }
    subDomainMap.get(sd.domain_id).push(sd)
  }

  for (const sm of serviceModules) {
    if (!serviceModuleMap.has(sm.sub_domain_id)) {
      serviceModuleMap.set(sm.sub_domain_id, [])
    }
    serviceModuleMap.get(sm.sub_domain_id).push(sm)
    smCodeMap.set(sm.id, sm.code)
  }

  const boByServiceModule = new Map()
  for (const bo of businessObjects) {
    if (!boByServiceModule.has(bo.service_module_id)) {
      boByServiceModule.set(bo.service_module_id, [])
    }
    const smCode = smCodeMap.get(bo.service_module_id) || ''
    boByServiceModule.get(bo.service_module_id).push({
      name: bo.name,
      code: bo.code,
      domain: bo.domain_name || '',
      subDomain: bo.sub_domain_name || '',
      serviceModule: smCode,
      serviceModuleName: bo.service_module_name || '',
      domainId: bo.domain_id,
      subDomainId: bo.sub_domain_id,
      serviceModuleId: bo.service_module_id,
      annotationContent: bo.annotation_content || bo.annotationContent || '',
      annotationCategory: bo.annotation_category || bo.annotationCategory || 'info'
    })
  }

  const domainProducts = domains.map(domain => {
    const domainSubDomains = subDomainMap.get(domain.id) || []

    return {
      name: domain.name,
      code: domain.code || domain.name,
      modules: domainSubDomains.map(subDomain => {
        const subDomainSMs = serviceModuleMap.get(subDomain.id) || []

        return {
          name: subDomain.name,
          code: subDomain.code || subDomain.name,
          submodules: subDomainSMs.map(sm => {
            const smBOs = boByServiceModule.get(sm.id) || []

            return {
              name: sm.name,
              code: sm.code || sm.name,
              businessObjects: smBOs
            }
          })
        }
      })
    }
  })

  return domainProducts
}

function buildServiceModules(serviceModules, businessObjects) {
  return serviceModules.map(sm => {
    const smBOs = businessObjects.filter(bo => bo.service_module_id === sm.id)

    return {
      id: sm.id,
      name: sm.name,
      code: sm.code || sm.name,
      subDomain: sm.sub_domain_name || '',
      subDomainId: sm.sub_domain_id,
      domain: sm.domain_name || '',
      domainId: sm.domain_id,
      businessObjects: smBOs.map(bo => bo.code)
    }
  })
}

function buildRelationships(rawRelationships) {
  return rawRelationships.map(rel => ({
    id: rel.id,
    // [v39 关系线标题] 关系实例编码 (e.g. "ORDER-USER-01"), 与"关系类型编码" relation_code 区分
    // 之前 label 误用 relation_code (类型编码 DEPENDS_ON), 用户期望看到 关系编码 (实例编码)
    code: rel.code || '',
    relationType: rel.relation_type || rel.relationType || '',
    relationTypeName: rel.relation_type_name || rel.relationTypeName || '',
    relationTypeNameEn: rel.relation_type_name_en || rel.relationTypeNameEn || '',
    relationDirection: rel.relation_direction || rel.relationDirection || null,
    relationCode: rel.relation_code || rel.relationCode || '',
    sourceCode: rel.source_code || rel.sourceCode,
    targetCode: rel.target_code || rel.targetCode,
    // [v34 双向支持] 同时回填 sourceName/targetName (兼容 API 返回的 snake_case 字段)
    // 之前 buildDiagramData.buildLinks 读 rel.sourceName/targetName 都是 undefined
    // → diagramData.links[i].source/target/sourceName/targetName 都是 undefined
    // 不会影响 mermaid 渲染 (useBusinessObjectSyntax 用 sourceCode 查 nodeCodeToIdMap),
    // 但会让 E2E 调试 / 下游消费方困惑
    sourceName: rel.source_bo_name || rel.sourceName || rel.source_name || '',
    targetName: rel.target_bo_name || rel.targetName || rel.target_name || '',
    sourceId: rel.source_bo_id || rel.sourceId || null,
    targetId: rel.target_bo_id || rel.targetId || null,
    relationDesc: rel.relation_desc || rel.relationDesc || '',
    annotationContent: rel.annotation_content || rel.annotationContent || '',
    annotationCategory: rel.annotation_category || rel.annotationCategory || 'info',
    // 后端分类结果（scope_type + category_type 下沉到后端计算）
    scopeType: rel.scope_type || null,
    categoryType: rel.category_type || null
  }))
}

/**
 * 构建预览数据（使用后端 architecture/preview 聚合 API）
 * 5 次独立 API 调用 → 1 次聚合 API 调用
 */
export async function buildPreviewDataFromArchData(api, versionId, hierarchyFilter) {
  const { domains, subDomains, serviceModules, businessObjects, relationships, centerScope } = await fetchPreviewData(versionId, hierarchyFilter)

  const domainProducts = buildDomainProducts(domains, subDomains, serviceModules, businessObjects)
  const serviceModulesData = buildServiceModules(serviceModules, businessObjects)
  const relationshipsData = buildRelationships(relationships)

  const smCodeMap = new Map()
  serviceModules.forEach(sm => {
    smCodeMap.set(sm.id, sm.code)
  })

  const businessObjectsData = businessObjects.map(bo => {
    const smCode = smCodeMap.get(bo.service_module_id) || ''
    return {
      name: bo.name,
      code: bo.code,
      domain: bo.domain_name || '',
      subDomain: bo.sub_domain_name || '',
      serviceModule: smCode,
      serviceModuleName: bo.service_module_name || '',
      domainId: bo.domain_id,
      subDomainId: bo.sub_domain_id,
      serviceModuleId: bo.service_module_id,
      annotationContent: bo.annotation_content || bo.annotationContent || '',
      annotationCategory: bo.annotation_category || bo.annotationCategory || 'info'
    }
  })

  const allServiceModulesData = buildServiceModules(serviceModules, businessObjects)
  const allDomainProducts = buildDomainProducts(domains, subDomains, serviceModules, businessObjects)

  return {
    domainProducts,
    businessObjects: businessObjectsData,
    serviceModules: serviceModulesData,
    allDomainProducts,
    allBusinessObjects: businessObjectsData,
    allServiceModules: allServiceModulesData,
    relationships: relationshipsData,
    centerScope: centerScope
  }
}

/**
 * 计算中心范围（使用后端 architecture/preview API 返回的 center_scope）
 * 不再重复调用 fetchTreeData
 */
export async function convertToCenterScope(api, versionId, hierarchyFilter) {
  const { centerScope } = await fetchPreviewData(versionId, hierarchyFilter)
  return centerScope
}

export function convertToRelationNodeIds(relationTypeFilter) {
  if (!relationTypeFilter || !Array.isArray(relationTypeFilter)) {
    return []
  }

  const nodeIds = []

  for (const filter of relationTypeFilter) {
    if (typeof filter === 'string') {
      nodeIds.push(filter)
    } else if (filter && typeof filter === 'object' && filter.id) {
      nodeIds.push(filter.id)
    } else if (filter && typeof filter === 'object' && filter.scopeType && filter.categoryType) {
      const id = filter.level
        ? `${filter.scopeType}-${filter.categoryType}-${filter.level}-${filter.name}`
        : `${filter.scopeType}-${filter.categoryType}`
      nodeIds.push(id)
    }
    // 关键修复：filter 是 null/undefined 时跳过（之前会抛 TypeError: Cannot read properties of null (reading 'id')）
    // typeof null === 'object'，会进入第一个 typeof === 'object' 分支并读 filter.id → 报错
  }

  return [...new Set(nodeIds)]
}
