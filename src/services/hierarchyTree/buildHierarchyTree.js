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

// [FIX 2026-08-02] 同时按 id 与 code 索引: 真实 preview 的 BO 对象无 id 字段 (只有 code),
// 但关系 (buildRelationships) 的 sourceId/targetId 是数字 id; 双索引保证两种形状都能解析.
function indexNode(node, elementRefIndex) {
  const ref = node.elementRef
  if (ref?.id != null) elementRefIndex.set(ref.id, node)
  if (ref?.code != null && ref.code !== ref.id) elementRefIndex.set(ref.code, node)
}

// [FIX 2026-08-02] 端点解析: id 优先 (fixture: source_bo_id ↔ BO.id), code 兜底
// (真实 preview: sourceCode ↔ BO.code); 解析不到返回 null, 投影阶段作为悬空边丢弃.
function resolveLinkEndpoint(rel, side, elementRefIndex) {
  const id = rel[`${side}_bo_id`] ?? rel[`${side}Id`] ?? null
  const code = rel[`${side}_code`] ?? rel[`${side}Code`] ?? null
  const byId = id != null ? elementRefIndex.get(id) : null
  if (byId) return byId.elementRef.id
  const byCode = code != null ? elementRefIndex.get(code) : null
  if (byCode) return byCode.elementRef.id
  return null
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
    indexNode(dNode, elementRefIndex)
    for (const sd of domain.modules || []) {
      const sdNode = makeNode(
        LAYERS.SUB_DOMAIN, sd.code || sd.name, sd.name,
        { type: LAYERS.SUB_DOMAIN, id: sd.id ?? sd.code, code: sd.code, name: sd.name },
        dNode,
      )
      dNode.children.push(sdNode)
      indexNode(sdNode, elementRefIndex)
      for (const sm of sd.submodules || []) {
        const smNode = makeNode(
          LAYERS.SERVICE_MODULE, sm.code || sm.name, sm.name,
          { type: LAYERS.SERVICE_MODULE, id: sm.id ?? sm.code, code: sm.code, name: sm.name },
          sdNode,
        )
        sdNode.children.push(smNode)
        indexNode(smNode, elementRefIndex)
        for (const bo of sm.businessObjects || []) {
          // [FIX 2026-08-02] 兼容合成层级条目: businessObjects 可能是 code 字符串数组
          const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name || '')
          const boName = typeof bo === 'string' ? bo : (bo.name || bo.code || '')
          const boNode = makeNode(
            LAYERS.BUSINESS_OBJECT, boCode, boName,
            {
              type: LAYERS.BUSINESS_OBJECT,
              id: typeof bo === 'object' && bo != null ? (bo.id ?? boCode) : boCode,
              code: boCode,
              name: boName,
            },
            smNode,
          )
          smNode.children.push(boNode)
          indexNode(boNode, elementRefIndex)
        }
      }
    }
  }

  const links = (preview?.relationships || []).map(rel => ({
    id: rel.id,
    source: resolveLinkEndpoint(rel, 'source', elementRefIndex),
    target: resolveLinkEndpoint(rel, 'target', elementRefIndex),
    code: rel.relation_code ?? rel.relationCode ?? rel.code ?? '',
    label: rel.relation_code ?? rel.relationCode ?? rel.code ?? '',
  }))

  return { tree: root, elementRefIndex, links }
}
