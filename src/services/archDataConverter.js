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
  // [FIX 2026-06-29 v2] 把后端 snake_case 字段转成驼峰
  //   之前直接透传 snake_case (annotation_contents), 但下游代码用驼峰
  //   (annotationContents) → 字段找不到 → annotationList.length = 0
  const normalizeAnnotation = (item) => ({
    ...item,
    annotationContents: item.annotation_contents || item.annotationContents || [],
    annotationCategories: item.annotation_categories || item.annotationCategories || []
  })
  return {
    domains: data.domains || [],
    subDomains: data.sub_domains || [],
    serviceModules: (data.service_modules || []).map(normalizeAnnotation),
    businessObjects: (data.business_objects || []).map(normalizeAnnotation),
    relationships: (data.relationships || []).map(normalizeAnnotation),
    centerScope: data.center_scope || []
  }
}

function buildDomainProducts(domains, subDomains, serviceModules, businessObjects) {
  const subDomainMap = new Map()
  const serviceModuleMap = new Map()
  const smCodeMap = new Map()
  const smNameMap = new Map()
  const sdNameMap = new Map()
  const dNameMap = new Map()

  for (const sd of subDomains) {
    if (!subDomainMap.has(sd.domain_id)) {
      subDomainMap.set(sd.domain_id, [])
    }
    subDomainMap.get(sd.domain_id).push(sd)
    sdNameMap.set(sd.id, sd.name)
    dNameMap.set(sd.domain_id, '')
  }

  for (const sm of serviceModules) {
    if (!serviceModuleMap.has(sm.sub_domain_id)) {
      serviceModuleMap.set(sm.sub_domain_id, [])
    }
    serviceModuleMap.get(sm.sub_domain_id).push(sm)
    smCodeMap.set(sm.id, sm.code)
    smNameMap.set(sm.id, sm.name)
  }

  for (const d of domains) {
    dNameMap.set(d.id, d.name)
  }

  const boByServiceModule = new Map()
  for (const bo of businessObjects) {
    if (!boByServiceModule.has(bo.service_module_id)) {
      boByServiceModule.set(bo.service_module_id, [])
    }
    const smId = bo.service_module_id
    const smCode = smCodeMap.get(smId) || ''
    const smName = smNameMap.get(smId) || ''

    let sdId = bo.sub_domain_id
    let sdName = bo.sub_domain_name
    let dId = bo.domain_id
    let dName = bo.domain_name

    if (!sdName || !dName) {
      for (const sd of subDomains) {
        if (serviceModuleMap.get(sd.id)?.some(sm => sm.id === smId)) {
          sdId = sd.id
          sdName = sd.name
          dId = sd.domain_id
          dName = dNameMap.get(dId) || ''
          break
        }
      }
    }

    boByServiceModule.get(smId).push({
      name: bo.name,
      code: bo.code,
      domain: dName || '',
      subDomain: sdName || '',
      serviceModule: smCode,
      serviceModuleName: smName,
      domainId: dId,
      subDomainId: sdId,
      serviceModuleId: smId,
      // [FIX 2026-06-29] 后端返回的是数组 (annotation_contents, annotation_categories)
      //   而不是之前拼接的字符串 (annotation_content, annotation_category)
      //   单条时也是数组形式 [content], 多条时 [c1, c2, c3]
      //   这样前端 useAnnotation.parseAnnotationsFromData 可以逐条渲染
      annotationContents: bo.annotation_contents || [],
      annotationCategories: bo.annotation_categories || []
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

function buildServiceModules(serviceModules, businessObjects, subDomains, domains) {
  // [BUG-V033 修复 2026-06-29] 用 subDomains/domains 反查 name, 不依赖 sm.sub_domain_name/domain_name 冗余列
  // V863 历史 SM.sub_domain_name/domain_name 都是 NULL (trigger 只维护新 INSERT)
  const sdMap = new Map((subDomains || []).map(sd => [sd.id, sd]))
  const dMap = new Map((domains || []).map(d => [d.id, d]))

  return serviceModules.map(sm => {
    const smBOs = businessObjects.filter(bo => bo.service_module_id === sm.id)
    const sd = sdMap.get(sm.sub_domain_id)
    const domainId = sm.domain_id || sd?.domain_id
    const d = dMap.get(domainId)

    return {
      id: sm.id,
      name: sm.name,
      code: sm.code || sm.name,
      subDomain: sd?.name || sm.sub_domain_name || '',
      subDomainId: sm.sub_domain_id,
      domain: d?.name || sm.domain_name || '',
      domainId,
      businessObjects: smBOs.map(bo => bo.code),
      // [FIX 2026-06-29] 后端返回 annotation_contents/categories 数组
      // 不传 annotationContents 数组, useAnnotation.parseAnnotationsFromData 就不会渲染
      annotationContents: sm.annotation_contents || [],
      annotationCategories: sm.annotation_categories || []
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
    // [FIX 2026-06-29] 改为数组形式, 后端返回 annotation_contents/categories
    annotationContents: rel.annotation_contents || [],
    annotationCategories: rel.annotation_categories || [],
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
  const serviceModulesData = buildServiceModules(serviceModules, businessObjects, subDomains, domains)
  const relationshipsData = buildRelationships(relationships)

  // [BUG-V033 修复 2026-06-29] 反查 name 映射, 不依赖 BO 的冗余列 (*_name 列 V863 全 NULL)
  // 之前 businessObjectsData 直接读 bo.domain_name/sub_domain_name/service_module_name,
  // 这些列只在 INSERT 时由 trigger 维护, 历史 2850 条 BO 全是 NULL,
  // 导致前端 availableSubDomains/Domains 因 falsy 过滤返回空数组,
  // availableServiceModules fallback 到编码 (INV) 而非中文名 (库存管理).
  const smCodeMap = new Map()
  const smNameMap = new Map()
  serviceModules.forEach(sm => {
    smCodeMap.set(sm.id, sm.code)
    smNameMap.set(sm.id, sm.name)
  })
  const sdMap = new Map(subDomains.map(sd => [sd.id, sd]))
  const dMap = new Map(domains.map(d => [d.id, d]))

  const businessObjectsData = businessObjects.map(bo => {
    const smId = bo.service_module_id
    const smCode = smCodeMap.get(smId) || ''
    const smName = smNameMap.get(smId) || ''

    // BO.sub_domain_id 可能为 NULL, 通过 smId 反查 sd
    let sdId = bo.sub_domain_id
    let sdName = bo.sub_domain_name
    let dId = bo.domain_id
    let dName = bo.domain_name

    if (!sdName || !dName || !sdId) {
      // 通过 service_module_id 找它所属的 sub_domain
      const matchedSm = serviceModules.find(s => s.id === smId)
      const matchedSdId = matchedSm?.sub_domain_id
      const sd = matchedSdId ? sdMap.get(matchedSdId) : null
      if (sd) {
        sdId = sd.id
        sdName = sd.name
        dId = sd.domain_id
        dName = dMap.get(dId)?.name || ''
      }
    } else if (sdName && !dName) {
      // 有 sdName 但没 dName, 通过 sdId 反查
      const sd = sdMap.get(sdId)
      if (sd) {
        dId = sd.domain_id
        dName = dMap.get(dId)?.name || ''
      }
    }

    return {
      name: bo.name,
      code: bo.code,
      domain: dName || '',
      subDomain: sdName || '',
      serviceModule: smCode,
      serviceModuleName: smName,
      domainId: dId,
      subDomainId: sdId,
      serviceModuleId: smId,
      // [FIX 2026-06-29] 改为数组形式
      annotationContents: bo.annotation_contents || [],
      annotationCategories: bo.annotation_categories || []
    }
  })

  const allServiceModulesData = buildServiceModules(serviceModules, businessObjects, subDomains, domains)
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
