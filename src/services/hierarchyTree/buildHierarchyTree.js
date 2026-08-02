/**
 * buildHierarchyTree - L1 统一架构树构建
 *
 * [spec 4.2.1] 从 preview 数据构建与图表类型无关的五层树：
 *   PRODUCT → DOMAIN → SUB_DOMAIN → SERVICE_MODULE → BUSINESS_OBJECT
 * 数据来源: preview.domainProducts（领域 → 子领域 → 服务模块 → 业务对象 的天然层级）。
 * link 数据单独返回，端点引用原始架构元素 elementRef.id（跨层稳定，不受粒度影响）。
 */

import { GroupType, createGroupId } from '../groupModel/types.js'

const LAYERS = {
  DOMAIN: GroupType.DOMAIN,
  SUB_DOMAIN: GroupType.SUB_DOMAIN,
  SERVICE_MODULE: GroupType.SERVICE_MODULE,
  BUSINESS_OBJECT: GroupType.BUSINESS_OBJECT,
}

function makeNode(layerType, code, name, elementRef, parent) {
  return {
    id: createGroupId(layerType, code),
    layer: layerType,
    code,
    name,
    elementRef,
    children: [],
    parent,
  }
}

/**
 * 构建统一架构树
 * @param {Object} preview - architecture preview 数据 { domainProducts, relationships }
 * @returns {{ tree: Object, elementRefIndex: Map, links: Array }}
 */
export function buildHierarchyTree({ preview }) {
  const elementRefIndex = new Map()
  const root = {
    id: 'P_ROOT', layer: 'PRODUCT', code: 'ROOT', name: '产品',
    elementRef: null, children: [], parent: null,
  }
  const domains = preview?.domainProducts || []

  for (const domain of domains) {
    const dNode = makeNode(
      LAYERS.DOMAIN, domain.code || domain.name, domain.name,
      { type: LAYERS.DOMAIN, id: domain.id ?? domain.code, code: domain.code, name: domain.name },
      root,
    )
    root.children.push(dNode)
    for (const sd of domain.modules || []) {
      const sdNode = makeNode(
        LAYERS.SUB_DOMAIN, sd.code || sd.name, sd.name,
        { type: LAYERS.SUB_DOMAIN, id: sd.id ?? sd.code, code: sd.code, name: sd.name },
        dNode,
      )
      dNode.children.push(sdNode)
      for (const sm of sd.submodules || []) {
        const smNode = makeNode(
          LAYERS.SERVICE_MODULE, sm.code || sm.name, sm.name,
          { type: LAYERS.SERVICE_MODULE, id: sm.id ?? sm.code, code: sm.code, name: sm.name },
          sdNode,
        )
        sdNode.children.push(smNode)
        for (const bo of sm.businessObjects || []) {
          const boNode = makeNode(
            LAYERS.BUSINESS_OBJECT, bo.code, bo.name,
            { type: LAYERS.BUSINESS_OBJECT, id: bo.id ?? bo.code, code: bo.code, name: bo.name },
            smNode,
          )
          smNode.children.push(boNode)
          elementRefIndex.set(boNode.elementRef.id, boNode)
        }
        elementRefIndex.set(smNode.elementRef.id, smNode)
      }
      elementRefIndex.set(sdNode.elementRef.id, sdNode)
    }
    elementRefIndex.set(dNode.elementRef.id, dNode)
  }

  const links = (preview?.relationships || []).map(rel => ({
    id: rel.id,
    source: rel.source_bo_id,
    target: rel.target_bo_id,
    code: rel.relation_code,
    label: rel.relation_code,
  }))

  return { tree: root, elementRefIndex, links }
}
