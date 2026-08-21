let tooltipInstance = null

// [v39 枚举解析修复] 同步从 EnumService._cache 读出 enum options 转为 {code -> {code, label}} map
// 之前只读 window.__relationTypeEnumMap, 该变量在生产中无人设置 → 中文名永远不显示
// 关键: EnumService.loadOptions 会写入 _cache, RelationFilterSection 加载 relation_type
//       任何调用 loadOptions('direction') 的组件也会写入 direction 缓存
// [v40 修复] 改用静态 import EnumService, 不再走 dynamic import
// 原因: dynamic import 是 async, getEnumService() 返回 Promise
//       getEnumMap 是同步调用, 在 Promise resolve 前 _enumServiceRef.current 一直是 null
//       → tooltip 第一次 hover 时 EnumService 还没加载, L2 永远 miss
// 静态 import 同步解析, 模块加载完成 _enumServiceRef.current 立即可用
// [v40.3 修复] 之前的 `import EnumServiceModule from '@/services/enumService.js'` 在 Vite 下被当作 CJS
//   interop 处理, EnumServiceModule 直接是 EnumService 对象本身 (没有 default/named 包装)
//   修复: 改用 namespace import, 然后用 mod.default || mod (Vite 会把 default export 作为 'default' key)
import * as EnumServiceNS from '@/services/enumService.js'
import { useDiagnostics } from '../core/useDiagnostics.js'
import { isFeatureEnabled } from '@/utils/featureFlags.js'
const _enumServiceRef = {
  current: EnumServiceNS?.default || (EnumServiceNS?._cache ? EnumServiceNS : null)
}

// [v40.2 修复] _enumMapCache 缺失声明 → 第一次 hover 触发 ReferenceError
//   症状: 浏览器 console 报 "_enumMapCache is not defined"
//   原因: v40 重构时只改了 import 方式, 漏掉把 L1 缓存 Map 声明回来
const _enumMapCache = new Map()

async function getEnumService() {
  // [v40] 静态 import 后 EnumService 已同步可用, 此函数保留为 API 兼容
  return _enumServiceRef.current
}

function buildMapFromCache(cached) {
  if (!cached || !Array.isArray(cached.data)) return null
  const map = {}
  let hasAny = false
  for (const opt of cached.data) {
    const code = (opt && (opt.value || opt.code)) || ''
    if (!code) continue
    map[code] = {
      code,
      label: (opt && (opt.label || opt.name)) || ''
    }
    hasAny = true
  }
  return hasAny ? map : null
}

function getEnumMap(enumTypeId) {
  if (typeof enumTypeId !== 'string' || !enumTypeId) return null

  // L1: 内部缓存 (避免每次 hover 都遍历 cache)
  // 修复 v39: 只缓存从 EnumService._cache (生产) 读到的结果, 不缓存 window 兜底结果
  //   → 避免单测中 window.__relationTypeEnumMap 切换时, 旧 map 被错误复用
  if (_enumMapCache.has(enumTypeId)) {
    return _enumMapCache.get(enumTypeId)
  }

  let map = null
  let fromService = false

  // L2: 从 EnumService._cache 取 (RelationFilterSection 等组件已写入)
  // 注: EnumService 在 SPA 启动时已 import, _cache 是同步可读
  try {
    const svc = _enumServiceRef.current
    if (svc && svc._cache && svc._cache.has(enumTypeId)) {
      map = buildMapFromCache(svc._cache.get(enumTypeId))
      fromService = true
    }
  } catch (e) {
    // 静默 fallback
  }

  // L3: 兜底 - window.__relationTypeEnumMap / __relationDirectionEnumMap (向后兼容单测)
  if (!map && typeof window !== 'undefined') {
    const winMap = enumTypeId === 'relation_type'
      ? window.__relationTypeEnumMap
      : enumTypeId === 'direction'
        ? window.__relationDirectionEnumMap
        : null
    if (winMap && typeof winMap === 'object') {
      map = winMap
    }
  }

  // 修复 v39: 只缓存 EnumService 读到的结果, window 兜底结果不缓存
  //   - 生产: EnumService 加载完后, L2 命中并缓存, 后续 hover 直接命中 L1
  //   - 测试: window.__relationTypeEnumMap 切换时, L3 不缓存 → 每次重读最新 window 值
  if (fromService && map) {
    _enumMapCache.set(enumTypeId, map)
  }
  return map
}

// [v39 方向 enum 预加载] 异步预加载 direction / relation_type 枚举
// 在 addMouseOverTooltips 第一次调用时触发, fire-and-forget
// 第二次 hover 时缓存已就绪
// [v40 强化] 改为导出 preloadEnums() 给 MermaidComponent 主动调用
//   - 原因: 之前 fire-and-forget 时, 用户在第一次 hover 前 EnumService 还没加载完 → tooltip 仍显示 code
//   - 修复: MermaidComponent 在 diagramData 加载完后 await preloadEnums(), 后续 hover 一定命中缓存
let _enumPreloadTriggered = false
export async function preloadEnums() {
  if (typeof window === 'undefined') return
  _enumPreloadTriggered = true
  console.log('[v40.3 诊断] preloadEnums STARTED')

  try {
    const EnumService = await getEnumService()
    console.log('[v40.3 诊断] preloadEnums EnumService =', EnumService ? 'OK' : 'NULL', '_cache=', !!EnumService?._cache)
    if (!EnumService || !EnumService._cache) return
    if (!EnumService._cache.has('direction')) {
      console.log('[v40.3 诊断] preloadEnums loading direction...')
      const dirResult = await EnumService.loadOptions('direction', { cache: true, throwError: false })
      console.log('[v40.3 诊断] preloadEnums direction loaded:', dirResult?.length, 'options')
      _enumMapCache.delete('direction')
    }
    if (!EnumService._cache.has('relation_type')) {
      console.log('[v40.3 诊断] preloadEnums loading relation_type...')
      const typeResult = await EnumService.loadOptions('relation_type', { cache: true, throwError: false })
      console.log('[v40.3 诊断] preloadEnums relation_type loaded:', typeResult?.length, 'options')
      _enumMapCache.delete('relation_type')
    }
    console.log('[v40.3 诊断] preloadEnums DONE cacheSize=', EnumService._cache.size)
  } catch (e) {
    _enumPreloadTriggered = false  // 允许下次重试
    console.warn('[useTooltip.preloadEnums] failed:', e?.message || e)
  }
}

function triggerEnumPreload() {
  if (_enumPreloadTriggered) return
  if (typeof window === 'undefined') return
  // [v40 优化] 改为走 preloadEnums (Promise), 避免 fire-and-forget 早期 hover 失效
  preloadEnums()
}

export function useTooltip() {

  // [P0-A 2026-08-03] 接入 diag 埋点 — highlight/clear/match 失败时 recordStepMeta,
  //   之前 useTooltip 高亮完全无可观测信号, 与 annotationOverlay 的 .annotation-highlighted
  //   DOM 查询不对齐, "点了没反应" 类问题排查困难.
  // [P0-B 2026-08-03] 通过 diag.setHighlightState 暴露闭包内的 selectedElements 快照,
  //   window.__archPage.mermaid.highlight 一键读取.
  const diag = useDiagnostics()

  // [P1-B 2026-08-03] 拖动守卫: 跨 click 事件保留 mousedown 起点.
  //   用户拖动图表 (panning) 后浏览器仍 fire click 事件, 会误触发 clearHighlight 清掉高亮.
  //   与 annotationOverlay.onSvgClick 的 isDraggingState 守卫对齐 (那里用 mousedown/mousemove/mouseup).
  //   这里用更简单的位移判定: mousedown 记录起点, click 时位移 > 5px 视为拖动, 跳过 clear.
  let _mouseDownPos = null

  // [FIX 2026-08-10] 当前实例的 selectedElements 引用, 供 clearSelectionHighlight() 从组件外部
  //   清除"选择高亮". 背景: 关系高亮 (MermaidComponent) 与选择高亮 (本模块) 是两套独立机制,
  //   同一节点可同时被两者高亮. 若关系高亮把选择高亮样式误当作"原始样式"保存, 清除关系高亮时
  //   会把这些样式错误恢复 → 节点残留高亮. 暴露清除入口让关系高亮在应用前先清掉选择高亮.
  let _currentSelectedElements = null

  /**
   * [P0-B] 把 selectedElements (含 DOM 引用) 序列化为可观测快照, 同步到 diag.
   *   DOM 引用不暴露到 window (会泄漏 / 影响测试稳定性), 只暴露 code/id/text 等纯数据.
   */
  const _snapshotHighlight = (selectedElements) => {
    const snapNode = (el) => {
      if (!el) return null
      return {
        code: el.getAttribute ? (el.getAttribute('data-code') || null) : null,
        id: el.id || null,
        tag: el.tagName || null
      }
    }
    const snapPath = (p) => {
      if (!p) return null
      const d = (p.getAttribute && p.getAttribute('d')) || ''
      return {
        relationCode: (p.getAttribute && p.getAttribute('data-relation-code')) || null,
        dSnippet: d.substring(0, 50)
      }
    }
    const snapLabel = (l) => {
      if (!l) return null
      return { text: ((l.textContent || '')).trim().substring(0, 50) }
    }
    const snapshot = {
      hasHighlight: !!(selectedElements.path || selectedElements.label || selectedElements.sourceNode || selectedElements.targetNode),
      path: snapPath(selectedElements.path),
      label: snapLabel(selectedElements.label),
      sourceNode: snapNode(selectedElements.sourceNode),
      targetNode: snapNode(selectedElements.targetNode)
    }
    diag.setHighlightState(snapshot)
    return snapshot
  }

  const createTooltipElement = () => {
    let tooltip = document.getElementById('mermaid-tooltip')
    if (!tooltip) {
      tooltip = document.createElement('div')
      tooltip.id = 'mermaid-tooltip'
      tooltip.style.position = 'fixed'
      tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.85)'
      tooltip.style.color = 'white'
      tooltip.style.padding = '10px 14px'
      tooltip.style.borderRadius = '6px'
      tooltip.style.fontSize = '13px'
      tooltip.style.zIndex = '100000'
      tooltip.style.pointerEvents = 'none'
      tooltip.style.visibility = 'hidden'
      tooltip.style.whiteSpace = 'pre-line'
      tooltip.style.lineHeight = '1.5'
      tooltip.style.maxWidth = '300px'
      tooltip.style.wordWrap = 'break-word'
      tooltip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)'
      document.body.appendChild(tooltip)
    }
    tooltipInstance = tooltip
    return tooltip
  }

  const showTooltip = (tooltip, text, x, y) => {
    tooltip.textContent = text
    tooltip.style.visibility = 'visible'
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  const hideTooltip = (tooltip) => {
    tooltip.style.visibility = 'hidden'
  }

  const moveTooltip = (tooltip, x, y) => {
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code → 中文名)
  // [v39 双向支持增强] 关系方向 (direction 枚举) 也走相同解析逻辑
  // 导出供单测覆盖 (useTooltip.spec.js)
  // [FIX 2026-06-30] 新增 annotationFilter 参数:
  //   - undefined (未传): 走老逻辑, 用 relation.annotationContent (向后兼容单测)
  //   - [] (空数组, 用户未选类别): 不展示备注行
  //   - 非空数组: 只展示 relation.annotationContents 中 category 在 filter 内的备注
  // [FIX 2026-08-03] 新增 childRelations 支持:
  //   - SM 图关系聚合多条 BO 级子关系, childRelations 携带每条子关系完整元数据
  //   - 有 childRelations 时展示父关系概览 + 子关系列表; 否则走单关系老逻辑 (BO 图/单测兼容)

  // 关系类型 code → "中文名 (CODE)" 标签 (无枚举时显示原始 code)
  const _resolveTypeLabel = (relationType) => {
    if (!relationType) return ''
    const typeMap = getEnumMap('relation_type')
    if (typeMap) {
      const enumOption = typeMap[relationType]
      if (enumOption && enumOption.label) {
        return `${enumOption.label} (${relationType})`
      }
    }
    return relationType
  }

  // 关系方向 code → "中文 (CODE)" 标签 (无枚举时显示原始 code)
  const _resolveDirectionLabel = (relationDirection) => {
    if (!relationDirection) return ''
    const dirMap = getEnumMap('direction')
    if (dirMap) {
      const enumOption = dirMap[relationDirection]
      if (enumOption && enumOption.label) {
        return `${enumOption.label} (${relationDirection})`
      }
    }
    return relationDirection
  }

  // 备注行: 按 annotationFilter 过滤, 返回拼接后的字符串 (空则不展示)
  const _resolveAnnotationLine = (relation, annotationFilter) => {
    if (annotationFilter === undefined) {
      // 老逻辑: 单测路径, relation.annotationContent 是单字符串
      return relation.annotationContent || ''
    }
    if (Array.isArray(annotationFilter) && annotationFilter.length > 0) {
      // 过滤模式: 优先用复数数组, fallback 到单数字段
      const contents = relation.annotationContents
      const categories = relation.annotationCategories
      if (Array.isArray(contents) && contents.length > 0 && Array.isArray(categories)) {
        const matched = contents
          .map((c, idx) => ({ content: c, category: categories[idx] || 'info' }))
          .filter(item => item.content && item.category && annotationFilter.includes(item.category))
          .map(item => item.content)
        return matched.join('; ')
      }
      if (relation.annotationContent && relation.annotationCategory && annotationFilter.includes(relation.annotationCategory)) {
        return relation.annotationContent
      }
    }
    // annotationFilter === [] 或其它: 不展示
    return ''
  }

  // 格式化单个关系的完整文本块 (header + body), 可选缩进 (用于子关系列表)
  const _formatRelationBlock = (relation, annotationFilter, indent = '') => {
    const relationCode = relation.relationCode || ''
    const relationDesc = relation.relationDesc || '无关系说明'
    const sourceName = relation.sourceName || ''
    const targetName = relation.targetName || ''
    const relationType = relation.relationType || ''
    const relationDirection = relation.relationDirection || ''

    // 多行 desc 缩进: 把 desc 内部的换行也加上缩进, 保持子关系块对齐
    const indentedDesc = indent ? String(relationDesc).replace(/\n/g, `\n${indent}`) : relationDesc

    let text = `${indent}${relationCode}\n${indent}${sourceName} → ${targetName}`

    const typeLabel = _resolveTypeLabel(relationType)
    if (typeLabel) text += `\n${indent}类型: ${typeLabel}`

    const dirLabel = _resolveDirectionLabel(relationDirection)
    if (dirLabel) text += `\n${indent}方向: ${dirLabel}`

    // [OPT 2026-08-06] 高层级关系 (源/目标均为 domain/subDomain/serviceModule 级别, 即 level<=2)
    //   折叠到容器后, 关系说明对用户无意义 (例: "供应链云 → 供应链云, 关系说明: ..."), 故隐藏.
    //   仅当源与目标任一端为 BO (level===3) 时展示. childRelations (SM 子关系) 不受影响.
    //   feature flag: VITE_HIDE_HIGHLEVEL_DESC (默认 true)
    const hideHighLevelDesc = import.meta.env.VITE_HIDE_HIGHLEVEL_DESC !== 'false'
    const srcLevel = typeof relation.sourceLevel === 'number' ? relation.sourceLevel : 3
    const tgtLevel = typeof relation.targetLevel === 'number' ? relation.targetLevel : 3
    const hideDesc = hideHighLevelDesc && srcLevel <= 2 && tgtLevel <= 2
    if (!hideDesc) {
      text += `\n${indent}${indentedDesc}`
    }

    const annotationLine = _resolveAnnotationLine(relation, annotationFilter)
    if (annotationLine) text += `\n${indent}备注: ${annotationLine}`

    return text
  }

  const formatTooltipText = (relation, annotationFilter) => {
    if (!relation) return '无关系说明'

    const childRelations = Array.isArray(relation.childRelations) ? relation.childRelations : []

    // [AGG 2026-08-09] 领域/子领域/服务模块级别连线 (聚合) → 展示关系数量统计信息.
    //   判定: 任一端点为折叠容器 (sourceLevel/targetLevel <= 2, 即 domain/subDomain/serviceModule).
    //   聚合连线背后通常是多条 BO 级关系, 若逐条列示会很长 (几十上百条), 故只汇总"关系数量".
    //   [OPT 2026-08-09] 方向和类型等关系级属性只在 BO 级连线下的列示 (childRelations 列表) 中展示,
    //     聚合级别不展示 (对用户无意义, 例: "销售管理 → 外部对象管理, 方向: 推").
    //   BO 级连线 (两端 level===3) 不受影响, 仍走 childRelations 列表.
    const aggSrcLevel = typeof relation.sourceLevel === 'number' ? relation.sourceLevel : 3
    const aggTgtLevel = typeof relation.targetLevel === 'number' ? relation.targetLevel : 3
    const isAggregate = aggSrcLevel <= 2 || aggTgtLevel <= 2

    if (isAggregate) {
      const aggCode = relation.relationCode || ''
      const aggSource = relation.sourceName || ''
      const aggTarget = relation.targetName || ''
      const total = childRelations.length || 1
      let text = `${aggCode}\n${aggSource} → ${aggTarget}`
      text += `\n关系数量: 共 ${total} 条`
      return text
    }

    // [FIX 2026-08-03] SM 图: childRelations 非空时展示父关系概览 + 所有子关系列表
    //   (SM 下源和目标 BO 对的列表, 每条含 source/target/type/direction/desc/annotation)
    //   BO 图/单测: childRelations 缺失或空 → 走单关系老逻辑 (向后兼容)
    if (childRelations.length > 0) {
      const parentCode = relation.relationCode || ''
      const parentSource = relation.sourceName || ''
      const parentTarget = relation.targetName || ''
      let text = `${parentCode}\n${parentSource} → ${parentTarget}`
      text += `\n共 ${childRelations.length} 条子关系:`
      childRelations.forEach((child, idx) => {
        const block = _formatRelationBlock(child, annotationFilter, '    ')
        text += `\n\n[${idx + 1}] ${block}`
      })
      return text
    }

    return _formatRelationBlock(relation, annotationFilter)
  }

  const createSelectionState = () => {
    return {
      path: null,
      label: null,
      sourceNode: null,
      targetNode: null
    }
  }

  const clearHighlight = (selectedElements) => {
    // [P0-A] 记录清高亮前的状态 — 排查"高亮莫名消失"类问题
    const hadHighlight = !!(selectedElements.path || selectedElements.sourceNode || selectedElements.targetNode || selectedElements.label)
    if (hadHighlight) {
      diag.recordStepMeta('useTooltipClearHighlight', {
        hadPath: !!selectedElements.path,
        hadLabel: !!selectedElements.label,
        hadSource: !!selectedElements.sourceNode,
        hadTarget: !!selectedElements.targetNode
      })
    }

    if (selectedElements.path) {
      selectedElements.path.style.strokeWidth = '2px'
      selectedElements.path.style.removeProperty('filter')
      selectedElements.path = null
    }

    if (selectedElements.sourceNode) {
      const rect = selectedElements.sourceNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.sourceNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.sourceNode = null
    }

    if (selectedElements.targetNode) {
      const rect = selectedElements.targetNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.targetNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.targetNode = null
    }

    if (selectedElements.label) {
      selectedElements.label = null
    }

    // [P0-B] 同步空快照到 diag (window.__archPage.mermaid.highlight 反映 cleared 状态)
    if (hadHighlight) {
      _snapshotHighlight(selectedElements)
    }
  }

  const highlightNode = (svg, nodeId, type, selectedElements) => {
    let nodeElement = svg.querySelector(`#${nodeId}`)
    let matchStrategy = 'id-selector'

    if (!nodeElement) {
      const allNodes = svg.querySelectorAll('.node')
      // [P1-A 2026-08-03] 边界检查: 之前 node.id.includes(nodeId) 会让 PUM01 误匹配 PUM010
      //   (因为 "PUM010".includes("PUM01") === true). 改为:
      //   1) 精确 === 优先
      //   2) fallback 到边界正则 (^|[^a-zA-Z0-9])nodeId([^a-zA-Z0-9]|$),
      //      要求 nodeId 前后是非字母数字 (含 - _ 边界) 或字符串首尾.
      //      PUM010 的 "0" 是数字 → 不匹配, 正确排除.
      //   边界正则同时兼容 mermaid 11 自动加前缀 (flowchart-PUM01-1) 的 case.
      const escapedId = nodeId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const boundaryRe = new RegExp(`(^|[^a-zA-Z0-9])${escapedId}([^a-zA-Z0-9]|$)`)
      for (const node of allNodes) {
        if (node.id === nodeId) {
          nodeElement = node
          matchStrategy = 'id-exact'
          break
        }
        if (node.id && boundaryRe.test(node.id)) {
          nodeElement = node
          matchStrategy = 'id-boundary'
          break
        }
      }
    }

    if (!nodeElement) {
      nodeElement = svg.querySelector(`[data-id="${nodeId}"]`)
      if (nodeElement) matchStrategy = 'data-id'
    }

    if (nodeElement) {
      const nodeContainer = nodeElement.closest('.node') || nodeElement

      const rect = nodeContainer.querySelector('rect, polygon')
      if (rect) {
        rect.style.stroke = '#FF6B6B'
        rect.style.strokeWidth = '4px'
        rect.style.filter = 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
      }

      const label = nodeContainer.querySelector('.nodeLabel, text')
      if (label) {
        label.style.fontWeight = 'bold'
        label.style.fontSize = '16px'
      }

      if (type === 'source') {
        selectedElements.sourceNode = nodeContainer
      } else {
        selectedElements.targetNode = nodeContainer
      }
      // [P0-A] 命中埋点: 记录 nodeId + 匹配策略, 排查"高亮错节点"类问题
      diag.recordStepMeta('useTooltipHighlightNode', {
        nodeId, type, matchStrategy, found: true
      })
    } else {
      // [P0-A] 匹配失败埋点 — 排查"点 edge 但 source/target 没高亮"类问题
      diag.recordStepMeta('useTooltipHighlightNode', {
        nodeId, type, matchStrategy: 'none', found: false
      })
    }
  }

  /**
   * [X] 已移除：不再需要 JavaScript 设置背景
   * 所有 edgeLabel 背景样式由 CSS .edge-label-clean 类统一管理
   */
  // const setLabelBackground = (edgeLabels) => { ... }

  // 实例级状态：每个 useTooltip() 调用都有自己的清理列表
  let _cleanupFns = []
  let _currentSvg = null

  // 注册可清理的事件监听器
  const addListener = (element, event, handler, options) => {
    element.addEventListener(event, handler, options)
    _cleanupFns.push(() => element.removeEventListener(event, handler, options))
  }

  const matchPathsToRelations = (svg, labels, relationDescriptions) => {
    const pathToRelationMap = new Map()
    const relationCodeMap = new Map()

    relationDescriptions.forEach(relation => {
      if (relation.relationCode) {
        relationCodeMap.set(relation.relationCode, relation)
      }
    })

    // [FIX 2026-08-03] 缺口2: 记录未匹配的 label/relation, 供 e2e 断言 + 排查 tooltip 错配.
    //   之前 label 文本匹配 relationCodeMap 失败时静默跳过, tooltip 显示错关系无法排查.
    //   现在收集 unmatchedLabels, 若非空则 console.warn + recordStepMeta('matchPathsToRelations').
    const unmatchedLabels = []

    labels.forEach((label) => {
      const labelText = label.textContent || label.innerHTML
      const relation = relationCodeMap.get(labelText.trim())
      if (relation) {
        pathToRelationMap.set(label, relation)
      } else {
        unmatchedLabels.push((labelText || '').trim().substring(0, 40))
      }
    })

    const edgeContainers = Array.from(svg.querySelectorAll('.edgePath'))
    const directEdgePaths = Array.from(svg.querySelectorAll('path.flowchart-link'))
    const realEdgePaths = []

    edgeContainers.forEach((edgeContainer, edgeIndex) => {
      const path = edgeContainer.querySelector('path')
      if (path) {
        realEdgePaths.push({ path, index: edgeIndex })
      }
    })

    // [PERF 2026-08-13] Set 去重替代 some() 线性扫描 (O(path²)→O(path)).
    //   大图 602 path 时 some() 约 36 万次引用比较; Set.has O(1).
    //   feature flag: ff_perfProcessSvg=0 回退原 some() 逻辑.
    const seenPaths = isFeatureEnabled('perfProcessSvg')
      ? new Set(realEdgePaths.map(item => item.path))
      : null
    directEdgePaths.forEach((path, edgeIndex) => {
      const dup = seenPaths ? seenPaths.has(path) : realEdgePaths.some(item => item.path === path)
      if (!dup) {
        realEdgePaths.push({ path, index: edgeIndex + edgeContainers.length })
        if (seenPaths) seenPaths.add(path)
      }
    })

    // [FIX 2026-08-03] 缺口2: 位置 fallback 匹配诊断.
    //   之前用 idx < relationDescriptions.length 做位置匹配, 若顺序不一致会静默错配.
    //   现在记录 fallback 匹配数 + 多出的 path 数, e2e 可断言 fallbackCount 是否异常.
    const unmatchedPathCount = Math.max(0, realEdgePaths.length - relationDescriptions.length)
    const fallbackMatchCount = Math.min(realEdgePaths.length, relationDescriptions.length)
    realEdgePaths.forEach((edgePathInfo, idx) => {
      if (idx < relationDescriptions.length) {
        pathToRelationMap.set(edgePathInfo.path, relationDescriptions[idx])
      }
    })

    // 缺口2: 未匹配诊断写入 stepMeta (snapshot.links.matchStats 暴露)
    const matchStats = {
      totalLabels: labels.length,
      totalRelations: relationDescriptions.length,
      totalPaths: realEdgePaths.length,
      unmatchedLabelCount: unmatchedLabels.length,
      unmatchedLabels: unmatchedLabels.slice(0, 5),
      fallbackMatchCount,
      unmatchedPathCount
    }
    diag.recordStepMeta('matchPathsToRelations', matchStats)
    if (unmatchedLabels.length > 0) {
      console.warn('[useTooltip] matchPathsToRelations: %d labels 未匹配 relationCode (前5: %j)',
        unmatchedLabels.length, unmatchedLabels.slice(0, 5))
    }
    if (unmatchedPathCount > 0) {
      console.warn('[useTooltip] matchPathsToRelations: %d paths 无对应 relation (path 数 > relation 数)',
        unmatchedPathCount)
    }

    return { pathToRelationMap, realEdgePaths }
  }

  const getEdgeLabels = (svg) => {
    const allEdgeLabels = svg.querySelectorAll('.edgeLabel')
    return Array.from(allEdgeLabels).filter(el => el.getBBox)
  }

  const setupLabelEvents = (label, index, tooltip, relationDescriptions, pathToRelationMap, labels, selectedElements, svg, realEdgePaths, annotationFilter) => {
    const onEnter = (e) => {
      let tooltipText = '无关系说明'
      const labelText = label.textContent || label.innerHTML
      const relation = relationDescriptions.find(r => r.relationCode && r.relationCode.trim() === labelText.trim())
      if (relation) {
        tooltipText = formatTooltipText(relation, annotationFilter)
      }
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    }
    const onMove = (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    }
    const onLeave = () => {
      hideTooltip(tooltip)
    }
    const onClick = (e) => {
      // [FIX 2026-08-16] 拖拽后的 click 不触发连线选择高亮 (与 bindEdgeFocus / annotationOverlay 对齐):
      //   拖拽平移结束后鼠标恰好落在连线上, 浏览器会 fire click, 若不做守卫会误把当前高亮
      //   替换成连线选择高亮 (即"拖拽导致高亮被取消/改变").
      if (typeof window !== 'undefined' && window.__mermaidDrag && window.__mermaidDrag.wasDrag) return
      e.stopPropagation()
      clearHighlight(selectedElements)
      selectedElements.label = label

      const relation = pathToRelationMap.get(label)

      if (relation) {
        const correspondingPath = realEdgePaths.find((item) => item.path && pathToRelationMap.get(item.path) === relation)?.path

        if (correspondingPath) {
          selectedElements.path = correspondingPath
          correspondingPath.style.strokeWidth = '4px'
          correspondingPath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
        }
        // [FIX 2026-08-14] label 分支缺 highlightNode: 与委托路径一致, source/target 节点也要高亮
        highlightNode(svg, relation.source, 'source', selectedElements)
        highlightNode(svg, relation.target, 'target', selectedElements)
      }
      // [P0-A] 埋点 + [P0-B] 状态快照同步到 diag
      diag.recordStepMeta('useTooltipLabelClick', {
        hasRelation: !!relation,
        relationCode: relation?.relationCode || null,
        hasPath: !!selectedElements.path
      })
      _snapshotHighlight(selectedElements)
    }

    addListener(label, 'mouseenter', onEnter)
    addListener(label, 'mousemove', onMove)
    addListener(label, 'mouseleave', onLeave)
    addListener(label, 'click', onClick)
  }

  const setupPathEvents = (path, tooltip, pathToRelationMap, labels, selectedElements, svg, annotationFilter) => {
    const onEnter = (e) => {
      const relation = pathToRelationMap.get(path)
      const tooltipText = relation ? formatTooltipText(relation, annotationFilter) : '无关系说明'
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    }
    const onMove = (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    }
    const onLeave = () => {
      hideTooltip(tooltip)
    }
    const onClick = (e) => {
      // [FIX 2026-08-19] 与 setupLabelEvents.onClick 对齐: 拖拽后的 click 不触发连线选中。
      //   之前 path 分支缺 wasDrag 守卫, 拖拽平移结束鼠标落在连线上会误触发选中高亮。
      if (typeof window !== 'undefined' && window.__mermaidDrag && window.__mermaidDrag.wasDrag) return
      e.stopPropagation()

      selectedElements.path = null
      selectedElements.label = null
      selectedElements.sourceNode = null
      selectedElements.targetNode = null
      selectedElements.path = path

      const relation = pathToRelationMap.get(path)

      if (relation) {
        const relationCode = relation.relationCode
        const correspondingLabel = Array.from(labels).find((label) => {
          const labelText = label.textContent || label.innerHTML
          return labelText.trim() === relationCode
        })

        if (correspondingLabel) {
          selectedElements.label = correspondingLabel
        }

        highlightNode(svg, relation.source, 'source', selectedElements)
        highlightNode(svg, relation.target, 'target', selectedElements)
      }
      // [P0-A] 埋点 + [P0-B] 状态快照同步到 diag
      diag.recordStepMeta('useTooltipPathClick', {
        hasRelation: !!relation,
        relationCode: relation?.relationCode || null,
        source: relation?.source || null,
        target: relation?.target || null
      })
      _snapshotHighlight(selectedElements)
    }

    addListener(path, 'mouseenter', onEnter)
    addListener(path, 'mousemove', onMove)
    addListener(path, 'mouseleave', onLeave)
    addListener(path, 'click', onClick)
  }

  // [PERF 2026-08-13] 事件委托: 用 svg 上的 4 个监听器替代每条边/路径的 8 个独立监听器
  //   (大图 602 边 ≈ 4800 个 addEventListener → 4 个). mouseover/mouseout 冒泡 + closest 定位,
  //   用 lastHoverEl 追踪避免子元素冒泡重复 show, relatedTarget 判断真正离开.
  //   feature flag: ff_perfProcessSvg=0 回退 per-element 绑定.
  const setupDelegatedTooltipEvents = (svg, tooltip, pathToRelationMap, labels, selectedElements, realEdgePaths, annotationFilter) => {
    const labelSet = new Set(labels)
    let lastHoverEl = null

    const resolveTarget = (rawEl) => {
      if (!rawEl || !rawEl.closest) return null
      const labelEl = rawEl.closest('.edgeLabel')
      if (labelEl && labelSet.has(labelEl)) return { kind: 'label', labelEl, pathEl: null }
      // [FIX 2026-08-14] HTML label (foreignObject > div.labelBkg > span.edgeLabel) 与 SVG label
      //   (g.edgeLabels > g.edgeLabel) 成对存在. span 因 getBBox 抛 ERR 被 getEdgeLabels 过滤,
      //   不在 labelSet → 之前 resolveTarget 返回 null → 真实鼠标 hover/click 聚合连线 label 无反应
      //   (tooltip 不显示 + 无高亮). 向上找同组的 g.edgeLabel (labelSet 内), 复用其 relation 映射.
      if (labelEl && !labelSet.has(labelEl)) {
        const svgLabelEl = labelEl.closest('g.edgeLabel')
        if (svgLabelEl && labelSet.has(svgLabelEl)) {
          return { kind: 'label', labelEl: svgLabelEl, pathEl: null }
        }
      }
      let pathEl = null
      if (rawEl.tagName === 'path' && rawEl.classList && rawEl.classList.contains('flowchart-link')) {
        pathEl = rawEl
      } else {
        const ep = rawEl.closest('.edgePath')
        if (ep) pathEl = ep.querySelector('path')
      }
      if (pathEl) return { kind: 'path', labelEl: null, pathEl }
      return null
    }

    const onOver = (e) => {
      const t = resolveTarget(e.target)
      if (!t) return
      const hoverEl = t.labelEl || t.pathEl
      if (hoverEl === lastHoverEl) return  // 子元素冒泡重复触发, 跳过
      lastHoverEl = hoverEl
      if (t.kind === 'label') {
        const relation = pathToRelationMap.get(t.labelEl)
        if (relation) showTooltip(tooltip, formatTooltipText(relation, annotationFilter), e.clientX, e.clientY)
      } else {
        const relation = pathToRelationMap.get(t.pathEl)
        const text = relation ? formatTooltipText(relation, annotationFilter) : '无关系说明'
        showTooltip(tooltip, text, e.clientX, e.clientY)
      }
    }

    const onMove = (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    }

    const onOut = (e) => {
      const t = resolveTarget(e.target)
      if (!t) {
        // [FIX 2026-08-14] mouseout target 无法解析 (svg 空白 / 移出 svg / HTML label 未映射) 时
        //   也必须隐藏 tooltip, 否则 tooltip 残留 visible 并随 mousemove 一直跟随鼠标移动.
        if (lastHoverEl) {
          lastHoverEl = null
          hideTooltip(tooltip)
        }
        return
      }
      const hoverEl = t.labelEl || t.pathEl
      if (e.relatedTarget && hoverEl && hoverEl.contains(e.relatedTarget)) return  // 仍在目标内部, 不离开
      lastHoverEl = null
      hideTooltip(tooltip)
    }

    const onClick = (e) => {
      // [FIX 2026-08-16] 拖拽后的 click 不触发连线选择高亮 (与 setupLabelEvents 分支对齐)
      if (typeof window !== 'undefined' && window.__mermaidDrag && window.__mermaidDrag.wasDrag) return
      const t = resolveTarget(e.target)
      if (!t) return
      e.stopPropagation()
      if (t.kind === 'label') {
        clearHighlight(selectedElements)
        selectedElements.label = t.labelEl
        const relation = pathToRelationMap.get(t.labelEl)
        if (relation) {
          const correspondingPath = realEdgePaths.find((item) => item.path && pathToRelationMap.get(item.path) === relation)?.path
          if (correspondingPath) {
            selectedElements.path = correspondingPath
            correspondingPath.style.strokeWidth = '4px'
            correspondingPath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
          }
          // [FIX 2026-08-14] label 分支缺 highlightNode: 点击连线 (真实命中 label 元素) 时
          //   source/target 节点也要高亮, 与 path 分支行为一致.
          highlightNode(svg, relation.source, 'source', selectedElements)
          highlightNode(svg, relation.target, 'target', selectedElements)
        }
        diag.recordStepMeta('useTooltipLabelClick', {
          hasRelation: !!relation,
          relationCode: relation?.relationCode || null,
          hasPath: !!selectedElements.path
        })
        _snapshotHighlight(selectedElements)
      } else {
        selectedElements.path = null
        selectedElements.label = null
        selectedElements.sourceNode = null
        selectedElements.targetNode = null
        selectedElements.path = t.pathEl
        const relation = pathToRelationMap.get(t.pathEl)
        if (relation) {
          const relationCode = relation.relationCode
          const correspondingLabel = Array.from(labels).find((label) => {
            const labelText = label.textContent || label.innerHTML
            return labelText.trim() === relationCode
          })
          if (correspondingLabel) selectedElements.label = correspondingLabel
          highlightNode(svg, relation.source, 'source', selectedElements)
          highlightNode(svg, relation.target, 'target', selectedElements)
        }
        diag.recordStepMeta('useTooltipPathClick', {
          hasRelation: !!relation,
          relationCode: relation?.relationCode || null,
          source: relation?.source || null,
          target: relation?.target || null
        })
        _snapshotHighlight(selectedElements)
      }
    }

    addListener(svg, 'mouseover', onOver)
    addListener(svg, 'mousemove', onMove)
    addListener(svg, 'mouseout', onOut)
    addListener(svg, 'click', onClick)
  }

  const addTrailingDottedLines = (svg, labels, diagramType, hideTails = false, pathToRelationMap = null, realEdgePaths = null) => {
    if (diagramType !== 'businessObject' && diagramType !== 'serviceModule') return

    // [PERF 2026-08-13] ELK (hideTails=true) 下拖尾线本就该隐藏, 原实现仍对每条边执行
    //   getBBox/getBoundingClientRect (强制 reflow) + getTotalLength + 51 次 getPointAtLength
    //   (602 边 ≈ 3 万次 SVG 几何计算), 最后仅靠 CSS hide-tails 隐藏结果 → 纯浪费.
    //   早退后大图 process_svg 从 ~2.4s 显著下降. feature flag: ff_perfProcessSvg=0 可回退.
    if (isFeatureEnabled('perfProcessSvg') && hideTails) {
      return
    }

    // [FIX 2026-08-15 v4.5] 拖尾线起点直接解析 g.edgeLabel 的 transform translate.
    //   g.edgeLabel 是 g.edgeLabels 直接子级 (g.edgeLabels 无 transform), 其 transform
    //   translate(x,y) 就是标签中心在 svg 用户空间的坐标. 文字相对锚点偏移很小 (<8px), 足够
    //   表达"拖尾线属于该关系名称"的视觉关联.
    const parseTranslate = (t) => {
      if (!t) return null
      const m = t.match(/translate\(([-\d.]+)[ ,]+([-\d.]+)\)/)
      if (m) return { x: parseFloat(m[1]), y: parseFloat(m[2]) }
      const m2 = t.match(/matrix\(([^)]+)\)/)
      if (m2) {
        const v = m2[1].split(/[ ,]+/).map(Number)
        if (v.length >= 6) return { x: v[4], y: v[5] }
      }
      return null
    }

    // [FIX 2026-08-15 v4.7] 计算标签中心到对应 path 的最近点 (svg 用户空间).
    //   之前 dot 终点 (x2,y2) 只在 draw 时刻算一次: draw 时标签仍贴在源节点 → 最近点算到
    //   path 起点附近; 之后标签移到连线中点, observer 只同步了 x1,y1, dot 却留在旧位置 → dot 远离标题.
    //   现在 observer 每次随标签移动重算最近点, 同时更新 x2,y2 与 dot 标记, 保证 dot 始终在
    //   离标签最近的 path 位置上 (标签在 path 中点时 dot 与标题几乎重合).
    const computeNearestPathPoint = (path, labelX, labelY, curSvg) => {
      let pathLength = 0
      try { pathLength = path.getTotalLength() } catch (e) { return null }
      if (!pathLength) return null
      const toSvgPathPoint = (pt) => {
        try {
          const g = new DOMPoint(pt.x, pt.y).matrixTransform(path.getScreenCTM())
            .matrixTransform(curSvg.getScreenCTM().inverse())
          return { x: g.x, y: g.y }
        } catch (e) {
          return { x: pt.x, y: pt.y }
        }
      }
      const sampleCount = 50
      let nearestPoint = null
      let nearestDist = Infinity
      for (let i = 0; i <= sampleCount; i++) {
        const ratio = i / sampleCount
        const point = toSvgPathPoint(path.getPointAtLength(pathLength * ratio))
        const dist = Math.hypot(point.x - labelX, point.y - labelY)
        if (dist < nearestDist) {
          nearestDist = dist
          nearestPoint = point
        }
      }
      return nearestPoint
    }

    // [FIX 2026-08-15 v4.6] mermaid 对 edgeLabel transform 的定位是异步的, 且在大图上会持续
    //   数秒才稳定 (实测: 拖尾线 draw 时刻 transform 仍在源节点中心, 如 MFG 99,164; 数秒后
    //   才移到连线中点 415,201). 仅靠 setTimeout(2000) 延后一次不够, 之后标签继续移动会让
    //   拖尾线起点远离关系名称. 用 MutationObserver 监听 g.edgeLabel 的 transform 变化,
    //   标签每移动一次就同步更新对应拖尾线起点, 保证拖尾线始终紧贴关系名称文字.
    const edgeLabelsContainer = svg.querySelector('g.edgeLabels')
    if (edgeLabelsContainer && typeof MutationObserver !== 'undefined') {
      const pendingLabels = new Set()
      let flushScheduled = false
      const flushTailSync = () => {
        flushScheduled = false
        for (const label of pendingLabels) {
          const inner = label.querySelector('g.label')
          const lid = (inner && inner.getAttribute('data-id')) || label.getAttribute('data-id') || ''
          if (!lid) continue
          const curSvg = label.closest('svg') || svg
          const line = curSvg.querySelector(`line[data-trailing-line][data-label-id="${lid}"]`)
          if (!line) continue
          const c = parseTranslate(label.getAttribute('transform'))
          if (!c) continue
          // [v4.7] 同时重算最近点, 更新起点 + dot 终点, 让 dot 随标签移动到离标签最近的位置
          const path = curSvg.querySelector(`path.flowchart-link[id="${lid}"]`)
          const nearest = path ? computeNearestPathPoint(path, c.x, c.y, curSvg) : null
          line.setAttribute('x1', c.x.toFixed(2))
          line.setAttribute('y1', c.y.toFixed(2))
          if (nearest) {
            line.setAttribute('x2', nearest.x.toFixed(2))
            line.setAttribute('y2', nearest.y.toFixed(2))
            const marker = curSvg.querySelector(`circle[data-trailing-marker][data-label-id="${lid}"]`)
            if (marker) {
              marker.setAttribute('cx', nearest.x.toFixed(2))
              marker.setAttribute('cy', nearest.y.toFixed(2))
            }
          }
        }
        pendingLabels.clear()
      }
      const tailObserver = new MutationObserver((mutations) => {
        for (const m of mutations) {
          if (m.type !== 'attributes' || m.attributeName !== 'transform') continue
          const label = m.target
          if (label && label.classList && label.classList.contains('edgeLabel')) {
            pendingLabels.add(label)
          }
        }
        if (!flushScheduled && pendingLabels.size) {
          flushScheduled = true
          requestAnimationFrame(flushTailSync)
        }
      })
      tailObserver.observe(edgeLabelsContainer, {
        attributes: true, subtree: true, attributeFilter: ['transform']
      })
      _cleanupFns.push(() => tailObserver.disconnect())
    }

    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    labels.forEach((label, index) => {
      if (!label.getBBox) {
        console.warn(`标签 ${index} 不是 SVG 元素，跳过`);
        return
      }

      // [FIX 2026-08-15 v4.4] 拖尾线坐标必须等 mermaid 把 edge label 的 transform 定位到最终位置.
      //   根因: processSvg 在 mermaid.run() resolve 后立即执行, 但 mermaid 对 edgeLabel 的
      //   transform translate(x,y) 是异步定位的, 500ms 时上半段标签仍贴源节点 (起点算到源节点
      //   中心, 如 MFG 标签应 415,207 却得 99,164) → 拖尾线起点远离关系名称. 实测 2s 后 transform
      //   才稳定到最终位置. 故用 setTimeout(2000) 延后到标签定位完成后再测.
      //   [v4.3] 同时用 label.closest('svg') 重新取当前文档中的 svg (防重渲染后旧引用).
      setTimeout(() => {
        if (!label.isConnected) return
        const curSvg = label.closest('svg') || svg
        if (!curSvg) return
        const labelParent = label.parentElement
        const rootGroup = labelParent?.parentElement
        const allEdgePathsInRoot = rootGroup?.querySelectorAll('.edgePath path, path.flowchart-link')

      // [FIX 2026-08-15 v4.5] 拖尾线起点 = g.edgeLabel transform translate (parseTranslate 见函数顶部).
      //   draw 时若 transform 尚未稳定 (异步布局), v4.6 的 MutationObserver 会在标签移动后自动同步.
      let labelCenter = parseTranslate(label.getAttribute('transform'))
      // 兜底: g.label 的 bbox 中心 → svg 用户空间 (getScreenCTM, 含 CSS transform/autofit)
      if (!labelCenter) {
        try {
          const gLabel = label.querySelector('g.label')
          const el = gLabel || label
          const b = el.getBBox()
          const p = new DOMPoint(b.x + b.width / 2, b.y + b.height / 2)
            .matrixTransform(el.getScreenCTM())
            .matrixTransform(curSvg.getScreenCTM().inverse())
          labelCenter = { x: p.x, y: p.y }
        } catch (e) {
          console.warn(`标签 ${index} 无法定位中心, 跳过`)
          return
        }
      }
      const labelCenterX = labelCenter.x
      const labelCenterY = labelCenter.y
        // [OK] 纯 CSS 方案：添加 CSS 类，由 CSS 隐藏装饰元素
        label.classList.add('edge-label-clean')

      // [OK] 创建白色背景 rect
      // 使用 requestAnimationFrame 确保 Mermaid 渲染完成后再设置
      requestAnimationFrame(() => {
        // 获取 label 的位置和大小
        try {
          // [v40.4 修复] 之前用 label.getBBox() 拿到的是含 foreignObject overflow 的 bbox
          //   （如 185x24），比实际文字 (~70x11) 大 2.5x，导致白底过大
          //   修复: 用 foreignObject 的子 div 实际尺寸 + 4px 边距，刚好包住文字
          const fo = label.querySelector('foreignObject')
          if (!fo) return

          const innerLabelG = label.querySelector('g.label')
          // 实际内容尺寸: 优先取 fo 子 div 的 clientRect，否则用 fo 属性
          let contentW = 0
          let contentH = 0
          let scale = 1
          const foDiv = fo.querySelector('div')
          if (foDiv) {
            const rect = foDiv.getBoundingClientRect()
            // 转成 SVG 用户单位: 实际像素 / SVG 缩放比例
            const svgEl = label.closest('svg')
            if (svgEl) {
              const svgRect = svgEl.getBoundingClientRect()
              const viewBox = svgEl.viewBox?.baseVal
              if (viewBox && viewBox.width > 0) {
                scale = svgRect.width / viewBox.width
              }
            }
            contentW = rect.width / (scale || 1)
            contentH = rect.height / (scale || 1)
          }
          if (!contentW) contentW = parseFloat(fo.getAttribute('width')) || 100
          if (!contentH) contentH = parseFloat(fo.getAttribute('height')) || 24

          // 边距: 上下 1px, 左右 2px (CSS labelBkg padding 4px 8px 已由 CSS 处理, 这里只要少量)
          const padX = 2
          const padY = 1
          const bgW = contentW + padX * 2
          const bgH = contentH + padY * 2

          // 清除旧 bgRect (可能有多个)
          const oldRects = label.querySelectorAll('rect[data-bg-rect="true"]')
          oldRects.forEach(r => r.remove())

          // 创建 SVG rect 作为白色背景
          const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')

          // 把 bgRect 插到 g.label 下 (而不是 g.edgeLabel), 这样可以用 local (0,0) = fo 左上角
          if (innerLabelG) {
            // 删掉旧的
            const innerOld = innerLabelG.querySelectorAll('rect[data-bg-rect="true"]')
            innerOld.forEach(r => r.remove())
            bgRect.setAttribute('x', -padX)
            bgRect.setAttribute('y', -padY)
            bgRect.setAttribute('width', bgW)
            bgRect.setAttribute('height', bgH)
            bgRect.setAttribute('rx', '2')
            bgRect.setAttribute('ry', '2')
            bgRect.setAttribute('fill', '#ffffff')
            bgRect.setAttribute('fill-opacity', '1')
            bgRect.setAttribute('data-bg-rect', 'true')
            bgRect.style.setProperty('fill', '#ffffff', 'important')
            bgRect.style.setProperty('fill-opacity', '1', 'important')
            bgRect.style.setProperty('opacity', '1', 'important')
            bgRect.style.setProperty('display', 'block', 'important')
            bgRect.style.setProperty('visibility', 'visible', 'important')
            bgRect.style.setProperty('stroke', 'none', 'important')
            // 插到 innerLabelG 的最前面 (作为 background)
            const firstChild = innerLabelG.firstChild
            if (firstChild) {
              innerLabelG.insertBefore(bgRect, firstChild)
            } else {
              innerLabelG.appendChild(bgRect)
            }
          } else {
            // fallback: 插到 g.edgeLabel, 中心对齐
            bgRect.setAttribute('x', -bgW / 2)
            bgRect.setAttribute('y', -bgH / 2)
            bgRect.setAttribute('width', bgW)
            bgRect.setAttribute('height', bgH)
            bgRect.setAttribute('fill', '#ffffff')
            bgRect.setAttribute('fill-opacity', '1')
            bgRect.setAttribute('data-bg-rect', 'true')
            bgRect.style.setProperty('fill', '#ffffff', 'important')
            bgRect.style.setProperty('fill-opacity', '1', 'important')
            bgRect.style.setProperty('opacity', '1', 'important')
            bgRect.style.setProperty('display', 'block', 'important')
            bgRect.style.setProperty('visibility', 'visible', 'important')
            bgRect.style.setProperty('stroke', 'none', 'important')
            const firstChild = label.firstChild
            if (firstChild) {
              label.insertBefore(bgRect, firstChild)
            } else {
              label.appendChild(bgRect)
            }
          }
        } catch (e) {
          console.warn('创建背景 rect 失败:', e)
        }
      })

      // [FIX 2026-08-15 v4] 拖尾线 path 匹配: 用 data-id / id 属性直接匹配 label↔path.
      //   根因: 原 pathToRelationMap 的 path→relation 映射按索引 (idx < relationDescriptions.length)
      //   dagre 下 path 顺序 ≠ label 顺序 → 索引错位, 拖尾线连到错误边, 起点远离文字.
      //   SVG 结构: g.label[data-id="L_COLLAPSE_X_Y_0"] 与 path[id="L_COLLAPSE_X_Y_0"] 共享
      //   相同 data-id, 用此精确匹配, 无需经 relation 对象间接查找.
      let correspondingPath = null
      const labelDataId = label.querySelector('g.label')?.getAttribute('data-id')
      if (labelDataId) {
        correspondingPath = curSvg.querySelector(`path.flowchart-link[id="${labelDataId}"]`)
      }
      // 兜底: 映射不可用/未匹配时退回原索引匹配 (保持兼容)
      if (!correspondingPath && allEdgePathsInRoot && allEdgePathsInRoot.length > index) {
        correspondingPath = allEdgePathsInRoot[index]
      }

      if (!correspondingPath) {
        console.warn(`标签 ${index} 没有找到对应的连线path`)
        return
      }

      const pathLength = correspondingPath.getTotalLength()
      // [FIX 2026-08-15 v4] path 的 getPointAtLength 返回 path 局部坐标; dagre 下 path 是
      //   g.edgePaths 直接子级 (无 transform), 局部 = svg 用户空间. 保险起见仍经 getScreenCTM
      //   (含 CSS transform) 转 svg 用户空间, 与 labelCenter 同一坐标系比较; 无 transform 时
      //   path.getScreenCTM() 与 svg.getScreenCTM() 抵消, 结果不变. 不用 getCTM (缺 CSS 变换).
      const toSvgPathPoint = (pt) => {
        try {
          const p = new DOMPoint(pt.x, pt.y)
          const g = p.matrixTransform(correspondingPath.getScreenCTM())
            .matrixTransform(curSvg.getScreenCTM().inverse())
          return { x: g.x, y: g.y }
        } catch (e) {
          return { x: pt.x, y: pt.y }
        }
      }
      const startPoint = toSvgPathPoint(correspondingPath.getPointAtLength(0))
      const endPoint = toSvgPathPoint(correspondingPath.getPointAtLength(pathLength))

      const sampleCount = 50
      let nearestPoint = null
      let nearestDist = Infinity

      for (let i = 0; i <= sampleCount; i++) {
        const ratio = i / sampleCount
        const point = toSvgPathPoint(correspondingPath.getPointAtLength(pathLength * ratio))
        const dist = Math.hypot(point.x - labelCenterX, point.y - labelCenterY)
        if (dist < nearestDist) {
          nearestDist = dist
          nearestPoint = point
        }
      }

      const distToStart = Math.hypot(startPoint.x - labelCenterX, startPoint.y - labelCenterY)
      const distToEnd = Math.hypot(endPoint.x - labelCenterX, endPoint.y - labelCenterY)

      const useNearestPoint = nearestDist < Math.min(distToStart, distToEnd) ? nearestPoint : (distToStart < distToEnd ? startPoint : endPoint)

      const tailLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      tailLine.setAttribute('x1', labelCenterX.toFixed(2))
      tailLine.setAttribute('y1', labelCenterY.toFixed(2))
      tailLine.setAttribute('x2', useNearestPoint.x.toFixed(2))
      tailLine.setAttribute('y2', useNearestPoint.y.toFixed(2))
      tailLine.setAttribute('stroke', '#333333')
      tailLine.setAttribute('stroke-width', '1.5')
      tailLine.setAttribute('stroke-dasharray', '4,3')
      tailLine.setAttribute('opacity', '0.8')
      tailLine.setAttribute('data-trailing-line', 'true')
      tailLine.setAttribute('data-label-id', labelDataId || '')
      curSvg.appendChild(tailLine)

      const endMarker = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      endMarker.setAttribute('cx', useNearestPoint.x.toFixed(2))
      endMarker.setAttribute('cy', useNearestPoint.y.toFixed(2))
      endMarker.setAttribute('r', '3')
      endMarker.setAttribute('fill', '#333333')
      endMarker.setAttribute('opacity', '0.8')
      endMarker.setAttribute('data-trailing-marker', 'true')
      // [v4.7] dot 标记带 data-label-id, 供 MutationObserver 随标签移动同步更新位置
      endMarker.setAttribute('data-label-id', labelDataId || '')
      curSvg.appendChild(endMarker)
      }) // end setTimeout (坐标延迟到 transform 稳定后)
    })

    // 使用 CSS 类控制拖尾线显示/隐藏
    if (hideTails) {
      svg.classList.add('hide-tails')
    }
  }

  const addClickToClearHighlight = (svg, selectedElements) => {
    const onClick = (e) => {
      // [P1-B 2026-08-03] 拖动守卫: 与 annotationOverlay onSvgClick 的 isDraggingState 守卫对齐.
      //   之前: 用户拖动图表 (panning) 后浏览器仍 fire click 事件, 触发 clearHighlight 误清高亮.
      //   现在: mousedown 记录起点 (onMouseDown), click 时若位移 > 5px 视为拖动, 跳过 clear.
      //   阈值 5px 与常规 click 抖动留出余量, 不影响真实空白点击清高亮 (D5b 测试覆盖).
      if (_mouseDownPos) {
        const dx = e.clientX - _mouseDownPos.x
        const dy = e.clientY - _mouseDownPos.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        _mouseDownPos = null
        if (dist > 5) {
          diag.recordStepMeta('useTooltipClearSkip', {
            reason: 'drag', dist: Math.round(dist)
          })
          return
        }
      }
      const target = e.target
      const isNode = target.closest('.node')
      const isEdgePath = target.closest('.edgePath') || target.classList.contains('flowchart-link')
      const isEdgeLabel = target.closest('.edgeLabel')

      if (!isNode && !isEdgePath && !isEdgeLabel) {
        clearHighlight(selectedElements)
      }
    }
    const onMouseDown = (e) => {
      _mouseDownPos = { x: e.clientX, y: e.clientY }
    }
    // [FIX 2026-08-03] 监听器从 <svg> 改为外层 .draggable-area 容器
    //   之前绑 svg 时, 点击 svg 外部 (背景可拖拽区域) 事件不冒泡到 svg, clearHighlight 不触发
    //   用户报告: 点击背景/可拖拽区域, highlighted 元素不取消; 只有 svg 内点击才取消
    //   容器链 fallback 兼容单测 (svg 无 .draggable-area 祖先时退回 svg 自身)
    const container = svg.closest('.draggable-area') || svg.closest('.mermaid-content') || svg
    addListener(container, 'click', onClick)
    addListener(container, 'mousedown', onMouseDown)
  }

  const addMouseOverTooltips = (svg, relationDescriptions, diagramType, hideTails = false, annotationFilter = []) => {
    if (!svg) return

    // 先清理本实例上一次的监听器和装饰元素（不跨实例）
    cleanup()

    const tooltip = createTooltipElement()
    const selectedElements = createSelectionState()
    _currentSelectedElements = selectedElements
    const edgeLabels = getEdgeLabels(svg)
    _currentSvg = svg

    // [OK] 纯 CSS 方案：不再需要 JavaScript 设置背景
    // setLabelBackground(edgeLabels)

    const { pathToRelationMap, realEdgePaths } = matchPathsToRelations(svg, edgeLabels, relationDescriptions)

    // [PERF 2026-08-13] 事件委托路径 (替代 4800 独立监听器). feature flag 可回退.
    if (isFeatureEnabled('perfProcessSvg')) {
      setupDelegatedTooltipEvents(svg, tooltip, pathToRelationMap, edgeLabels, selectedElements, realEdgePaths, annotationFilter)
    } else {
      edgeLabels.forEach((label, index) => {
        setupLabelEvents(label, index, tooltip, relationDescriptions, pathToRelationMap, edgeLabels, selectedElements, svg, realEdgePaths, annotationFilter)
      })
      realEdgePaths.forEach((edgePathInfo) => {
        setupPathEvents(edgePathInfo.path, tooltip, pathToRelationMap, edgeLabels, selectedElements, svg, annotationFilter)
      })
    }

    addTrailingDottedLines(svg, edgeLabels, diagramType, hideTails, pathToRelationMap, realEdgePaths)

    addClickToClearHighlight(svg, selectedElements)
  }

  // [SIMPLE 2026-08-15] 增量刷新拖尾线(关系连线关联点): 关联点开关切换时调用,
  //   只增删现有 SVG 上的拖尾线元素, 不触发 mermaid.run 全量重绘.
  //   hideTails=true → 移除拖尾线; false → 移除旧线后按当前 edgeLabel 重绘.
  const refreshTrailingDottedLines = (svg, diagramType, hideTails = false) => {
      if (!svg) return
      svg.querySelectorAll('[data-trailing-line], [data-trailing-marker]').forEach(el => el.remove())
      if (hideTails || (diagramType !== 'businessObject' && diagramType !== 'serviceModule')) return
      const edgeLabels = getEdgeLabels(svg)
      addTrailingDottedLines(svg, edgeLabels, diagramType, false)
    }

    // 清理本实例注册的所有事件监听器 + 当前 svg 上的装饰元素
    // 不清理 tooltip DOM 元素（fullscreen 切换需要复用）
    // 不影响其他 MermaidComponent 实例
    const cleanup = () => {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns = []
    if (_currentSvg) {
      _currentSvg.querySelectorAll('[data-trailing-line], [data-trailing-marker]').forEach(el => el.remove())
    }
    _currentSvg = null
    _currentSelectedElements = null
    // [P0-B] 清理时同步重置 diag highlight 状态 — chartType 切换 / 组件卸载后,
    //   旧 selectedElements 闭包失效, diag._highlightState 不应再报告 hasHighlight=true.
    //   D10 测试断言 chartType 切换后 highlight 干净 (DOM + 状态双重断言).
    diag.setHighlightState(null)
    _mouseDownPos = null
  }

    // [FIX 2026-08-10] 从组件外部清除当前实例的"选择高亮" (关系高亮应用前调用),
    //   避免关系高亮把选择高亮样式误存为原始样式而在清除时错误恢复.
    const clearSelectionHighlight = () => {
      if (_currentSelectedElements) {
        clearHighlight(_currentSelectedElements)
      }
    }

  return {
    addMouseOverTooltips,
    refreshTrailingDottedLines,
    cleanup,
    clearSelectionHighlight,
    // [v34 双向支持] 导出供单测覆盖 (useTooltip.spec.js)
    formatTooltipText,
    // [P0-B 2026-08-03] 暴露 highlight 状态查询入口 (供 useDiagnostics → window.__archPage.mermaid.highlight)
    //   返回 { hasHighlight, path, label, sourceNode, targetNode } 纯数据快照, 不含 DOM 引用.
    getHighlightState: () => diag.getHighlightState()
  }
}