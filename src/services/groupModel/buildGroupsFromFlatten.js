/**
 * buildGroupsFromFlatten - 从扁平数据构建 Group 树
 *
 * [来源] 7/31 13:04 Trae History: -35658d4d/ZQZJ.js (Phase 5/6)
 * [契约] 见 chart-data-flow-and-interaction-upgrade.md §5.10.2 ①
 *
 * 与 buildGroupModelFromArchitecture 的区别：
 *   - buildGroupModelFromArchitecture 接收 domainProducts (已经是 Group 形态)
 *   - buildGroupsFromFlatten 接收扁平结构 (domains/subDomains/serviceModules/businessObjects 数组)
 *   - 跳过 buildDomainProducts 中间产物 (Layer 2)
 */
import { GroupType, createGroup } from './types.js'

export function buildGroupsFromFlatten(flattenData, chartType) {
  if (!flattenData || !chartType) return []

  const { domains = [], subDomains = [], serviceModules = [], businessObjects = [] } = flattenData

  // 过滤有效数据
  if (!Array.isArray(domains) || !Array.isArray(businessObjects)) return []

  const businessObjectChart = chartType === ChartType.BUSINESS_OBJECT

  // 构建索引 (按 code 去重)
  const domainByCode = new Map()
  const subDomainByCode = new Map()
  const serviceModuleByCode = new Map()
  const boByCode = new Map()

  domains.forEach(d => { if (d?.code) domainByCode.set(d.code, d) })
  subDomains.forEach(sd => { if (sd?.code && !subDomainByCode.has(sd.code)) subDomainByCode.set(sd.code, sd) })
  serviceModules.forEach(sm => { if (sm?.code && !serviceModuleByCode.has(sm.code)) serviceModuleByCode.set(sm.code, sm) })
  businessObjects.forEach(bo => { if (bo?.code && !boByCode.has(bo.code)) boByCode.set(bo.code, bo) })

  // 决定 sub_domain_id / domain_id 关联键（flattenData 用 id，previewData 用 code）
  // 同时构建 sd→domain 映射（支持 id 和 code 两种键）
  const sdToDomainKey = new Map()
  subDomains.forEach(sd => {
    if (sd?.code) {
      if (sd.domain_id !== undefined) sdToDomainKey.set(sd.code, { kind: 'id', value: sd.domain_id })
      else if (sd.domain_code) sdToDomainKey.set(sd.code, { kind: 'code', value: sd.domain_code })
    }
  })

  const smToSubDomainKey = new Map()
  serviceModules.forEach(sm => {
    if (sm?.code) {
      if (sm.sub_domain_id !== undefined) smToSubDomainKey.set(sm.code, { kind: 'id', value: sm.sub_domain_id })
      else if (sm.sub_domain_code) smToSubDomainKey.set(sm.code, { kind: 'code', value: sm.sub_domain_code })
    }
  })

  const boToServiceModuleKey = new Map()
  businessObjects.forEach(bo => {
    if (bo?.code) {
      if (bo.service_module_id !== undefined) boToServiceModuleKey.set(bo.code, { kind: 'id', value: bo.service_module_id })
      else if (bo.service_module_code) boToServiceModuleKey.set(bo.code, { kind: 'code', value: bo.service_module_code })
    }
  })

  // 构建 id→code 查找表
  const sdIdToCode = new Map()
  subDomains.forEach(sd => { if (sd?.id !== undefined && sd?.code) sdIdToCode.set(sd.id, sd.code) })

  const smIdToCode = new Map()
  serviceModules.forEach(sm => { if (sm?.id !== undefined && sm?.code) smIdToCode.set(sm.id, sm.code) })

  // 判断 SM 是否有有效 BO（businessObject 图专用）
  const smHasBO = new Map()
  if (businessObjectChart) {
    businessObjects.forEach(bo => {
      const key = boToServiceModuleKey.get(bo.code)
      if (!key) return
      const smCode = key.kind === 'id' ? smIdToCode.get(key.value) : key.value
      if (smCode) smHasBO.set(smCode, true)
    })
  }

  // 判断 subDomain 是否有有效 SM
  const sdHasSM = new Map()
  if (businessObjectChart) {
    serviceModules.forEach(sm => {
      if (!sm?.code) return
      if (!smHasBO.has(sm.code)) return
      const key = smToSubDomainKey.get(sm.code)
      if (!key) return
      const sdCode = key.kind === 'id' ? sdIdToCode.get(key.value) : key.value
      if (sdCode) sdHasSM.set(sdCode, true)
    })
  }

  // 判断 domain 是否有有效 subDomain
  const dHasSD = new Map()
  if (businessObjectChart) {
    subDomains.forEach(sd => {
      if (!sd?.code) return
      if (!sdHasSM.has(sd.code)) return
      const key = sdToDomainKey.get(sd.code)
      if (!key) return
      const dCode = key.kind === 'id' ? (() => {
        for (const d of domains) if (d.id === key.value) return d.code
        return null
      })() : key.value
      if (dCode) dHasSD.set(dCode, true)
    })
  }

  // 构建 Group 树
  // 顺序: domain → subDomain → serviceModule → businessObject
  const result = []

  domains.forEach(domain => {
    if (!domain?.code) return
    // businessObject 图：过滤无 BO 的 domain
    if (businessObjectChart && !dHasSD.has(domain.code)) return

    const dChildren = []
    const dContainers = []

    // 找该 domain 下的 subDomains
    const ownedSubDomains = subDomains.filter(sd => {
      if (!sd?.code) return false
      if (businessObjectChart && !sdHasSM.has(sd.code)) return false
      const key = sdToDomainKey.get(sd.code)
      if (!key) return false
      if (key.kind === 'id') return key.value === domain.id
      return key.value === domain.code
    })

    ownedSubDomains.forEach(sd => {
      const sdChildren = []
      const sdContainers = []

      // 找该 sd 下的 serviceModules
      const ownedSMs = serviceModules.filter(sm => {
        if (!sm?.code) return false
        if (businessObjectChart && !smHasBO.has(sm.code)) return false
        const key = smToSubDomainKey.get(sm.code)
        if (!key) return false
        if (key.kind === 'id') return key.value === sd.id
        return key.value === sd.code
      })

      ownedSMs.forEach(sm => {
        const smChildren = []
        const smContainers = []

        // 找该 SM 下的 businessObjects（用 boByCode 去重，保留首个）
        const ownedBOs = []
        const seenBOCodes = new Set()
        businessObjects.forEach(bo => {
          if (!bo?.code || seenBOCodes.has(bo.code)) return
          const key = boToServiceModuleKey.get(bo.code)
          if (!key) return
          if (key.kind === 'id') {
            if (key.value !== sm.id) return
          } else {
            if (key.value !== sm.code) return
          }
          seenBOCodes.add(bo.code)
          ownedBOs.push(bo)
        })

        // businessObject 图：BO 作为 children
        if (businessObjectChart) {
          ownedBOs.forEach(bo => {
            const boGroup = createGroup({
              type: GroupType.BUSINESS_OBJECT,
              title: bo.name || bo.code,
              elementRef: {
                type: GroupType.BUSINESS_OBJECT,
                code: bo.code,
                name: bo.name,
                id: bo.id,
                parentCode: sm.code
              },
              children: []
            })
            smChildren.push(boGroup)
          })
        } else {
          // serviceModule 图：SM 是末端节点，本身不放 BO
          // SM 仍可能有子结构，按 GroupModel 兼容设计放 containers
        }

        const smGroup = createGroup({
          type: GroupType.SERVICE_MODULE,
          title: sm.name || sm.code,
          elementRef: {
            type: GroupType.SERVICE_MODULE,
            code: sm.code,
            name: sm.name,
            id: sm.id,
            parentCode: sd.code
          },
          children: smChildren,
          containers: smContainers
        })

        // serviceModule 图：SM 放 containers
        if (!businessObjectChart) {
          sdContainers.push(smGroup)
        } else {
          sdChildren.push(smGroup)
        }
      })

      const sdGroup = createGroup({
        type: GroupType.SUB_DOMAIN,
        title: sd.name || sd.code,
        elementRef: {
          type: GroupType.SUB_DOMAIN,
          code: sd.code,
          name: sd.name,
          id: sd.id,
          parentCode: domain.code
        },
        children: sdChildren,
        containers: sdContainers
      })
      dChildren.push(sdGroup)
    })

    const dGroup = createGroup({
      type: GroupType.DOMAIN,
      title: domain.name || domain.code,
      elementRef: {
        type: GroupType.DOMAIN,
        code: domain.code,
        name: domain.name,
        id: domain.id
      },
      children: dChildren,
      containers: dContainers
    })
    result.push(dGroup)
  })

  // 建立 parentId 链路
  const setParent = (groups, parent) => {
    groups.forEach(g => {
      g.parentId = parent ? parent.id : null
      setParent(g.children, g)
      setParent(g.containers, g)
    })
  }
  setParent(result, null)

  return result
}
