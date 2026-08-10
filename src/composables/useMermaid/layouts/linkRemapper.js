/**
 * 连线重映射工具 (FR-003 / FR-004, 2026-08-05)
 *
 * 上提语义: 分组 enabled 且无任何可见子孙时, 自动上提为单个聚合节点 (COLLAPSE_<id>),
 * 其子孙不被渲染. 指向被上提子孙的连线端点需重映射到"最近可见祖先"
 * (即最近的上提聚合节点), 使图表连线始终连通可见节点.
 *
 * 触发条件由上提推导 (upliftDerivation.computeUplift) 决定, 取代显式 collapsed.
 *
 * 聚合节点编码规则需与 groupedLayout.js / upliftDerivation.js 保持一致:
 *   COLLAPSE_<groupId.sanitized>
 */
import { computeUplift, upliftNodeId } from './upliftDerivation.js'

/**
 * 分组类型 → 层级深度 (与 LayoutControlPanel.groupTypeLevel 一致).
 * 领域=0 / 子领域=1 / 服务模块=2; 其余 (custom/未识别) 视为最细(BO 级)=3.
 */
function groupTypeLevel(groupType) {
  if (groupType === 'domain') return 0
  if (groupType === 'subDomain') return 1
  if (groupType === 'serviceModule') return 2
  return 3
}

/**
 * 从分组树构建 "名称 → elementCode" 映射.
 * 分组树 (layoutControlConfig.groups) 是渲染的权威来源, 领域/子领域/服务模块分组带 elementCode.
 * 用于弥补 domainProducts 在某些数据 (Excel 导入) 中领域/子领域缺 code 字段的问题.
 * @param {Array} groups 分组树
 * @returns {Map<string,string>} name → code
 */
function buildNameToCodeMap(groups) {
  const map = new Map()
  function walk(groupList) {
    if (!groupList) return
    for (const g of groupList) {
      if (!g || typeof g !== 'object') continue
      const code = g.elementCode ?? g.elementRef?.code
      if (code != null) {
        if (g.title) map.set(String(g.title), String(code))
        if (g.name) map.set(String(g.name), String(code))
      }
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(groups)
  return map
}

/**
 * 从 domainProducts 构建 "BO 编码 → 祖先链" 映射.
 * 每个 BO 记录其 domain/subDomain/serviceModule 的 {code, name}, 供关系颗粒度取用.
 * domainProducts 结构: [{code,name, modules:[{code,name, submodules:[{code,name, businessObjects:[{code,name}]}]}]}]
 *
 * [FIX 2026-08-06] 领域/子领域在 Excel 导入数据中无 code 字段 (只有 name), 直接读 domainProducts 会
 *   把名称当编码 (dCode = code ?? name = name), 导致折叠到领域/子领域时连线标签显示名称而非编码.
 *   故编码优先取分组树 nameToCodeMap (基于 elementCode, 渲染权威来源), 回退到 domainProducts.code/name.
 *
 * @param {Array} domainProducts 领域产品树
 * @param {Map<string,string>|null} nameToCodeMap 名称→编码 (来自分组树 elementCode)
 * @returns {Map<string,{domain,subDomain,serviceModule,boName}>}
 */
function buildAncestorMapFromDomainProducts(domainProducts, nameToCodeMap = null) {
  const ancestorMap = new Map()
  if (!domainProducts) return ancestorMap
  for (const domain of domainProducts) {
    if (!domain || typeof domain !== 'object') continue
    const dName = domain.name ?? domain.code ?? ''
    const dCode = nameToCodeMap?.get(dName) || domain.code || dName
    for (const sd of domain.modules || []) {
      if (!sd || typeof sd !== 'object') continue
      const sdName = sd.name ?? sd.code ?? ''
      const sdCode = nameToCodeMap?.get(sdName) || sd.code || sdName
      for (const sm of sd.submodules || []) {
        if (!sm || typeof sm !== 'object') continue
        const smName = sm.name ?? sm.code ?? ''
        const smCode = nameToCodeMap?.get(smName) || sm.code || smName
        for (const bo of sm.businessObjects || []) {
          if (!bo || bo.code == null) continue
          const key = String(bo.code)
          if (!ancestorMap.has(key)) {
            ancestorMap.set(key, {
              domain: { code: dCode, name: dName },
              subDomain: { code: sdCode, name: sdName },
              serviceModule: { code: smCode, name: smName },
              boName: bo.name || ''
            })
          }
        }
      }
    }
  }
  return ancestorMap
}

/**
 * 构建 "聚合节点编码 (COLLAPSE_<id>) → {level, code, name}" 映射.
 * 用于判定折叠端点 (COLLAPSE_<id>) 的显示层级, 从而决定关系颗粒度.
 * serviceModule 可能是 containers 节点, 需一并遍历.
 * @param {Array} groups 分组树
 * @returns {Map<string,{level:number,code:string,name:string}>}
 */
function buildCollapseInfoMap(groups) {
  const map = new Map()
  if (!groups || !groups.length) return map
  const uplift = computeUplift(groups)
  function walk(groupList) {
    if (!groupList) return
    for (const group of groupList) {
      if (!group || typeof group !== 'object') continue
      if (uplift.has(group.id)) {
        map.set(upliftNodeId(group), {
          level: groupTypeLevel(group.groupType),
          code: group.elementCode ?? group.elementRef?.code ?? group.id,
          name: group.title ?? group.name ?? group.id
        })
      }
      walk(group.children)
      walk(group.containers)
    }
  }
  walk(groups)
  return map
}

/**
 * 取某 BO 在指定颗粒度层级上的祖先 {code,name}.
 * level<0 处理为 0; level 0/1/2 取 domain/subDomain/serviceModule; level 3 取 BO 本身.
 * @param {Object|null} ancestor 祖先链 (buildAncestorMapFromDomainProducts 产物)
 * @param {number} level 颗粒度层级
 * @param {string} boCode 原始 BO 编码 (level 3 用)
 * @returns {{code:string,name:string}|null}
 */
function resolveAncestor(ancestor, level, boCode) {
  if (level <= 0) return ancestor?.domain || null
  if (level === 1) return ancestor?.subDomain || null
  if (level === 2) return ancestor?.serviceModule || null
  return { code: boCode, name: ancestor?.boName || boCode }
}

/**
 * 收集分组全部后代叶子编码 (directNodes + 容器 nodes + 容器编码 + 嵌套容器 + 递归 children),
 * 用于上提分组: 其全部后代都被隐藏, 端点需重映射到该上提聚合节点.
 * @param {Object} group 分组对象
 * @param {Set<string>} out 输出集合 (原地累积)
 */
function collectAllNodeCodes(group, out) {
  if (group.directNodes && group.directNodes.length) {
    group.directNodes.forEach(n => {
      const code = typeof n === 'object' ? (n.id || n.code || n.name) : n
      if (code != null) out.add(String(code))
    })
  }
  if (group.containers && group.containers.length) {
    group.containers.forEach(c => {
      if (!c || typeof c !== 'object') return
      if (c.nodes && c.nodes.length) {
        c.nodes.forEach(n => {
          const code = typeof n === 'object' ? (n.id || n.code || n.name) : n
          if (code != null) out.add(String(code))
        })
      }
      if (c.elementRef?.code != null) out.add(String(c.elementRef.code))
      if (c.elementCode != null) out.add(String(c.elementCode))
      if (c.containers && c.containers.length) {
        c.containers.forEach(nested => {
          if (nested && typeof nested === 'object') {
            if (nested.nodes && nested.nodes.length) {
              nested.nodes.forEach(n => {
                const code = typeof n === 'object' ? (n.id || n.code || n.name) : n
                if (code != null) out.add(String(code))
              })
            }
            if (nested.elementRef?.code != null) out.add(String(nested.elementRef.code))
            if (nested.elementCode != null) out.add(String(nested.elementCode))
          }
        })
      }
    })
  }
  if (group.children && group.children.length) {
    group.children.forEach(child => collectAllNodeCodes(child, out))
  }
}

/**
 * 构建"子节点编码 → 最近上提祖先聚合节点编码"映射
 * @param {Array} groups 分组树 (layoutControlConfig.groups)
 * @returns {Map<string,string>}
 */
export function buildUpliftAncestorMap(groups) {
  const map = new Map()
  const uplift = computeUplift(groups)

  function walk(groupList, upliftStack) {
    if (!groupList || !groupList.length) return
    for (const group of groupList) {
      if (!group) continue
      const isUplift = uplift.has(group.id)
      const nextStack = isUplift ? [...upliftStack, upliftNodeId(group)] : upliftStack
      // 最近上提祖先 = 栈顶 (最深)
      const nearest = nextStack[nextStack.length - 1]
      if (nearest) {
        const codes = new Set()
        collectAllNodeCodes(group, codes)
        codes.forEach(code => {
          if (!map.has(code)) map.set(code, nearest)
        })
      }
      if (group.children && group.children.length) {
        walk(group.children, nextStack)
      }
    }
  }

  walk(groups, [])
  return map
}

/**
 * 将连线的 source/target 端点重映射到最近可见祖先.
 * 保留原始关系元数据字段 (label/relationCode/annotation* 等), 仅改写端点编码.
 * 若两端重映射到同一聚合节点 (自环), 丢弃该连线.
 *
 * [GRANULARITY 2026-08-06] 关系颗粒度: 当至少一端被重映射为聚合节点 (COLLAPSE_<id>) 时,
 *   按"取两端较细层级"规则 (granularity = max(两端显示层级)) 重算连线编码(label)与两端名称:
 *   - label/code = 源祖先Code + "-" + 目标祖先Code
 *   - sourceName/targetName = 源/目标在颗粒度层级的祖先名称
 *   两端都是可见 BO 的连线 (未重映射) 保持原编码不变.
 *
 * @param {Array} links 连线数组 (含 sourceCode/targetCode 或 source/target)
 * @param {Array} groups 分组树
 * @param {Array} domainProducts 领域产品树 (用于构建 BO 祖先链, 传空则跳过颗粒度调整)
 * @returns {Array} 重映射后的连线数组
 */
export function remapLinksToVisibleAncestors(links, groups, domainProducts) {
  if (!links || !links.length) return links
  if (!groups || !groups.length) return links

  const map = buildUpliftAncestorMap(groups)
  const collapseInfoMap = buildCollapseInfoMap(groups)
  const nameToCodeMap = buildNameToCodeMap(groups)
  const ancestorMap = buildAncestorMapFromDomainProducts(domainProducts, nameToCodeMap)
  if (map.size === 0) return links

  const result = []
  for (const link of links) {
    const origSrc = link.sourceCode != null ? String(link.sourceCode) : (link.source != null ? String(link.source) : '')
    const origTgt = link.targetCode != null ? String(link.targetCode) : (link.target != null ? String(link.target) : '')
    if (!origSrc || !origTgt) {
      result.push(link)
      continue
    }
    const newSrc = map.get(origSrc) || origSrc
    const newTgt = map.get(origTgt) || origTgt
    if (newSrc === newTgt) continue // 两端折叠进同一聚合节点 → 自环, 丢弃

    let remapped = {
      ...link,
      source: newSrc,
      target: newTgt,
      sourceCode: newSrc,
      targetCode: newTgt
    }

    // [GRANULARITY 2026-08-06] 仅当端点确实被重映射 (至少一端为聚合节点) 时调整颗粒度.
    //   二次重映射 (两端已是 COLLAPSE_<id>, map 查不到) 不会进入此分支, 保证幂等.
    // [OPT 2026-08-06] 透传 sourceLevel/targetLevel 供 tooltip 判断"高层级说明行"是否隐藏.
    const srcLevel = collapseInfoMap.get(newSrc)?.level ?? 3
    const tgtLevel = collapseInfoMap.get(newTgt)?.level ?? 3
    remapped = { ...remapped, sourceLevel: srcLevel, targetLevel: tgtLevel }

    if (newSrc !== origSrc || newTgt !== origTgt) {
      const granularity = Math.max(srcLevel, tgtLevel) // 取两端较细(更深)层级
      const srcResolved = resolveAncestor(ancestorMap.get(origSrc), granularity, origSrc)
      const tgtResolved = resolveAncestor(ancestorMap.get(origTgt), granularity, origTgt)
      if (srcResolved?.code && tgtResolved?.code) {
        const newLabel = `${srcResolved.code}-${tgtResolved.code}`
        remapped = {
          ...remapped,
          label: newLabel,
          code: newLabel,
          sourceName: srcResolved.name ?? '',
          targetName: tgtResolved.name ?? ''
        }
      }
    }

    result.push(remapped)
  }
  return result
}

/**
 * [FUSE 2026-08-06] 关系连线融合 (去重 + 双向合并).
 *
 * 折叠后多条 BO 关系可能重映射到同一"可见节点对" (源+目标相同), 产生重复连线;
 * 同一节点对也可能同时存在 源->目标 与 目标->源 两条单向连线.
 * 用户定义的关系连线融合语义:
 *   - 相同 (源, 目标) 对 → 只保留一条连线
 *   - 若同时存在 源->目标 和 目标->源 → 合并为一条双向连线 (A <-> B)
 *
 * 融合以"无序节点对"为键: [source, target] 排序后归一化, 方向相反视为同一对.
 * 保留组内首条连线作为代表; 若组内出现相反方向 (或任一子连线明确双向),
 * 对代表标记 relationDirection='BIDIRECTIONAL' (由 getArrowSyntax 渲染 <-->).
 *
 * @param {Array} links 重映射后的连线数组 (含 sourceCode/targetCode 或 source/target)
 * @returns {Array} 融合后的连线数组
 */
export function fuseLinks(links) {
  if (!links || !links.length) return links
  const groups = new Map() // key -> { members, hasReverse, src, tgt }
  const order = [] // 保持首次出现顺序
  for (const link of links) {
    const src = link.sourceCode != null ? String(link.sourceCode) : (link.source != null ? String(link.source) : '')
    const tgt = link.targetCode != null ? String(link.targetCode) : (link.target != null ? String(link.target) : '')
    if (!src || !tgt) continue
    const key = [src, tgt].sort().join('\u0001')
    if (!groups.has(key)) {
      groups.set(key, { members: [], hasReverse: false, src, tgt })
      order.push(key)
    }
    const g = groups.get(key)
    g.members.push(link)
    // 反向检测: 当前 link 方向与代表方向相反, 或任一子连线明确双向 → 融合为双向
    if (src !== g.src || tgt !== g.tgt) {
      g.hasReverse = true
    } else if (link.relationDirection === 'BIDIRECTIONAL' || link.relationDirection === '双向') {
      g.hasReverse = true
    }
  }
  return order.map(key => {
    const g = groups.get(key)
    const rep = g.members[0]
    let out = { ...rep }
    if (g.hasReverse) {
      out.relationDirection = 'BIDIRECTIONAL'
    }
    // [FUSE 2026-08-09] 一个连线背后对应多个关系时, 携带全部关系元数据到 childRelations,
    //   供 BO 图 tooltip 列示 (关系编码/名称/描述/方向/类型).
    //   场景: ①方向相反融合为双向 (A->B + B->A) ②同源目标但关系编码不同 (A-B-01 + A-B-02).
    //   useBlockDiagramSyntax 透传 link.childRelations, useTooltip.formatTooltipText 逐条列示.
    //   relationCode 为空时回退到 code/label (= 源-目标, 与 useBlockDiagramSyntax 的 label 一致),
    //   保证每条子关系的"关系编码"行非空.
    if (g.members.length > 1) {
      out.childRelations = g.members.map(m => ({
        ...m,
        relationCode: m.relationCode || m.code || m.label || ''
      }))
    }
    return out
  })
}