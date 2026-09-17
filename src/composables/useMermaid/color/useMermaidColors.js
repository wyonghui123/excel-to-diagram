import { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR } from '@/constants/diagram'

export { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR }

export function useMermaidColors() {

  const getColorScheme = (schemeName) => {
    return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
  }

  const buildColorMap = (nodeColorMappings, objectToModuleMap, colorGroupBy, colorSchemes, customColors = {}) => {
    const colors = colorSchemes
    const uniqueGroups = new Set()

    console.log('[buildColorMap] customColors received:', customColors)

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
        uniqueGroups.add(groupKey)
      }
    })

    // [FIX 2026-08-11] 用位置索引分配默认色 (见 buildColorMapByIndex), 避免自定义色推移后续分组.
    return buildColorMapByIndex(uniqueGroups, colors, customColors)
  }

  // [FIX 2026-08-11 colorIndex-drift] 位置索引分配默认色 (与 assignColorsToGroups 同规则).
  //   旧实现 colorIndex 跳过自定义色分组 → 改某分组自定义色会推移后续分组默认色索引.
  //   buildColorMap 与 buildColorMapFromNodes 是增量变色路径 (updateColorsOnly 用),
  //   必须与全量渲染路径 (assignColorsToGroups) 用同一分配规则, 否则切换颜色后
  //   增量路径算出的颜色与全量路径不一致 → 视觉色漂移.
  const buildColorMapByIndex = (uniqueGroups, colors, customColors = {}) => {
    const colorMap = new Map()
    Array.from(uniqueGroups).forEach((group, idx) => {
      colorMap.set(group, customColors[group] || colors[idx % colors.length])
    })
    return colorMap
  }

  /**
   * [FOLD 2026-08-09] 折叠视图下从全量 BO 节点构建颜色映射。
   *
   * 背景: 折叠视图 (领域/子领域/服务模块折叠为聚合节点) 时, syntax 层不产生
   *   nodeColorMappings (空数组), 原 buildColorMap 依赖它 → colorMap 为空 →
   *   updateCollapseNodeColors 全灰 + buildColorLegendData 无映射色。
   * 本函数直接遍历 diagramData.nodes (折叠视图下仍含全量 BO 节点, 带
   *   domain/subDomain/serviceModuleName 字段), 按 colorGroupBy 推导分组键,
   *   与 buildColorLegendData / updateCollapseNodeColors 的取色键同源。
   *
   * @param {Array} nodes - diagramData.nodes (全量 BO 节点)
   * @param {string} colorGroupBy - domain | subDomain | serviceModule
   * @param {Object} colorSchemes - COLOR_SCHEMES[colorScheme]
   * @param {Object} customColors - 用户自定义颜色 { groupKey: color }
   * @param {Map|null} objectToModuleMap - 可选. 供分组键推导优先取 (与全量渲染路径同源),
   *   缺失时回退 node 自身字段 (见下方 key 推导, 与 useBusinessObjectSyntax 的 colorMap 一致).
   * @returns {Map<string,string>} groupKey -> color
   */
  const buildColorMapFromNodes = (nodes, colorGroupBy, colorSchemes, customColors = {}, objectToModuleMap = null) => {
    const uniqueGroups = new Set()
    ;(nodes || []).forEach(node => {
      const selfModule = (objectToModuleMap && objectToModuleMap.get(node.code || node.name)) || {}
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = selfModule.serviceModuleName || selfModule.serviceModule || node.serviceModuleName || node.serviceModule || node.name
      } else if (colorGroupBy === 'subDomain') {
        groupKey = selfModule.subDomain || node.subDomain
      } else {
        groupKey = selfModule.domain || node.domain
      }
      if (groupKey) uniqueGroups.add(groupKey)
    })
    // [FIX 2026-08-11] 位置索引分配默认色 (与 buildColorMap/assignColorsToGroups 同规则)
    return buildColorMapByIndex(uniqueGroups, colorSchemes, customColors)
  }

  const updateNodeColors = (svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, options = {}) => {
    // [FIX 2026-08-02 v5] 回到原方案: 区分中心范围时, 中心节点 fill = centerScopeColor (指定的颜色)
    //   v2 曾改为"分组色 + 粗虚线边框", 用户反馈虚线区分不明显, 改回用颜色区分。
    //   非中心节点仍用分组色 (切换颜色分组/配色时联动变色)。
    const centerScopeHighlight = options.centerScopeHighlight !== false  // 默认 true
    const centerScopeSet = new Set(options.centerScope || [])
    const centerScopeColor = options.centerScopeColor || '#808080'

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
        const isCenter = centerScopeHighlight && (centerScopeSet.has(mapping.nodeCode) || centerScopeSet.has(mapping.nodeName))
        const groupColor = colorMap.get(groupKey) || DEFAULT_COLOR
        // [v5] 中心节点 fill 用指定颜色 centerScopeColor, 非中心节点用分组色
        const newColor = isCenter ? centerScopeColor : groupColor

        // [FIX 2026-07-31] Mermaid 11.13.0 SVG g.node 元素的 id 格式为 `flowchart-{nodeId}-{counter}`
        // (例如 mapping.nodeId='N40' → SVG id='flowchart-N40-37')，旧的 `#${nodeId}` 选择器无法匹配。
        // 用属性前缀选择器 `g.node[id^="flowchart-{nodeId}-"]` 兼容 mermaid v11+ 格式。
        // [FIX 2026-07-31 v2] useSvgProcessor.addNodeCodeAttributes 把 BO code 写到 `data-code` 属性
        //   (不是 `data-id`!), 之前选择器 `[data-id="..."]` 用错了属性名 → 切换 colorGroupBy 时
        //   只 fallback 命中, 仍可能漏匹配某些节点。改用 `[data-code="BO_CODE"]` 精准命中。
        //   保留 mermaid id 前缀兜底以兼容未设置 data-code 的场景。
        const nodeElement = svg.querySelector(
          `#${mapping.nodeId} rect, [data-code="${mapping.nodeCode}"] rect, [data-id="${mapping.nodeId}"] rect, g.node[id^="flowchart-${mapping.nodeId}-"] rect`
        )
        if (nodeElement) {
          // [FIX 2026-08-02] 先清除初始渲染 renderMermaid 留下的 `fill ... !important` 内联样式
          //   (旧版 renderMermaid 对中心范围节点用 style.setProperty('fill', csColor, 'important')),
          //   否则切 centerScopeHighlight=false 后 !important 会压制这里的新 fill, 视觉不更新。
          nodeElement.style.removeProperty('fill')
          nodeElement.setAttribute('fill', newColor)
          // [FIX 2026-08-02 v4] 必须用 !important 设置内联 fill:
          //   mermaid 语法层 `classDef default fill:#fafafa` 会生成 SVG 内部 CSS (如 `.default > rect { fill:#fafafa !important }`),
          //   且节点 class 含 "default"。普通 style.fill (无 !important) 会被该 classDef 的 !important 规则压制
          //   → computedStyle 变 #fafafa 灰白 (用户看到"切色后节点全灰", 连线正常因为 linkStyle 无此压制)。
          //   初始渲染可见是因为 mermaid style 指令自带 !important (style="fill:#... !important")。
          //   这里用 setProperty(..., 'important') 与初始渲染对齐, 保证视觉更新。
          nodeElement.style.setProperty('fill', newColor, 'important')

          // [FIX 2026-08-02 v5] 边框统一恢复默认 (去掉中心范围的粗虚线边框方案)
          nodeElement.style.removeProperty('stroke')
          nodeElement.style.removeProperty('stroke-width')
          nodeElement.style.removeProperty('stroke-dasharray')
          nodeElement.setAttribute('stroke', '#333333')
          nodeElement.setAttribute('stroke-width', '2')
          nodeElement.removeAttribute('stroke-dasharray')
        }

        // 图例按分组色记录 (中心节点仅视觉 fill 被 centerScopeColor 覆盖, 分组色不随中心变灰)
        mapping.color = groupColor
      }
    })
  }

  // [FIX 2026-08-11 容器连线增量变色] 解析连线端点的分组色与中心状态。
  //   旧 updateLinkColors 只处理 BO 端点 (nodeColorMappings + objectToModuleMap)，
  //   折叠/上提容器连线端点 (COLLAPSE_<id>) 解析不到 → 改分组色后容器连线不变色
  //   (用户反馈: 改供应链云色后 供应链计划→采购供应 连线不联动)。
  //   现通过 collapseNodeMap (COLLAPSE_<id> → 分组上下文) 解析容器端点，与
  //   updateCollapseNodeColors 同源 (colorMap + centerScopeMarkers)。
  const resolveEndpointColor = (
    endpointId,
    nodeColorMappings,
    objectToModuleMap,
    colorGroupBy,
    colorMap,
    options,
    collapseNodeMap,
    centerScopeMarkers
  ) => {
    const centerScopeHighlight = options.centerScopeHighlight !== false
    const centerScopeSet = new Set(options.centerScope || [])

    // 容器/聚合端点 (COLLAPSE_<id>)
    const collapseCtx = collapseNodeMap?.get(endpointId)
    if (collapseCtx) {
      let groupKey
      if (colorGroupBy === 'serviceModule') groupKey = collapseCtx.serviceModuleName
      else if (colorGroupBy === 'subDomain') groupKey = collapseCtx.subDomainName
      else groupKey = collapseCtx.domainName
      const color = groupKey ? colorMap.get(groupKey) : undefined
      let isCenter = false
      if (centerScopeHighlight) {
        const m = centerScopeMarkers || {}
        if (collapseCtx.groupType === 'serviceModule') {
          isCenter = !!m.serviceModules?.has(collapseCtx.serviceModuleName)
            || !!m.serviceModules?.has(collapseCtx.code)
        } else if (collapseCtx.groupType === 'subDomain') {
          isCenter = m.subDomains?.get(collapseCtx.subDomainName) === true
            || m.subDomains?.get(collapseCtx.code) === true
        } else if (collapseCtx.groupType === 'domain') {
          isCenter = m.domains?.get(collapseCtx.domainName) === true
            || m.domains?.get(collapseCtx.code) === true
        }
      }
      return { groupKey, color, isCenter, resolved: true }
    }

    // BO 端点
    const mapping = nodeColorMappings.find(n => n.nodeId === endpointId)
    const module = mapping ? objectToModuleMap.get(mapping.nodeCode) : undefined
    if (module) {
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = module.serviceModuleName || module.serviceModule
      } else if (colorGroupBy === 'subDomain') {
        groupKey = module.subDomain
      } else {
        groupKey = module.domain
      }
      const color = groupKey ? colorMap.get(groupKey) : undefined
      const isCenter = centerScopeHighlight
        && (centerScopeSet.has(mapping.nodeCode) || centerScopeSet.has(mapping.nodeName))
      return { groupKey, color, isCenter, resolved: true }
    }

    return null
  }

  const updateLinkColors = (svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, options = {}) => {
    // [FIX 2026-08-02 v6] 增量更新连线颜色也遵循中心范围规则 (与语法层生成一致):
    //   双中心 -> centerScopeColor 灰 / 一中心一非中心 -> 非中心色 / 双非中心(或不区分) -> 黑色
    // [FIX 2026-08-11] 支持容器/聚合连线端点 (COLLAPSE_<id>), 见 resolveEndpointColor.
    const centerScopeColor = options.centerScopeColor || '#808080'
    const collapseNodeMap = options.collapseNodeMap
    const centerScopeMarkers = options.centerScopeMarkers

    linkColorMappings.forEach(mapping => {
      const source = resolveEndpointColor(
        mapping.sourceId, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap,
        options, collapseNodeMap, centerScopeMarkers
      )
      const target = resolveEndpointColor(
        mapping.targetId, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap,
        options, collapseNodeMap, centerScopeMarkers
      )

      if (source && target) {
        const sourceGroupColor = source.color
        const targetGroupColor = target.color
        const isSourceCenter = source.isCenter
        const isTargetCenter = target.isCenter

        let newColor
        if (isSourceCenter && isTargetCenter) {
          newColor = centerScopeColor
        } else if (isSourceCenter) {
          newColor = targetGroupColor || sourceGroupColor || DEFAULT_LINK_COLOR
        } else if (isTargetCenter) {
          newColor = sourceGroupColor || targetGroupColor || DEFAULT_LINK_COLOR
        } else {
          newColor = '#000000'
        }

        // [FIX 2026-07-31] Mermaid 11.13.0 把 edge path 直接放在 g.edgePaths 下，不再用 g.edgePath 包裹
        // 旧选择器 `.flowchart-link path, .edgePath path` 返回 0 个元素。
        // 增加 `.edgePaths > path` 兼容 mermaid v11+ (路径作为 edgePaths 直接子元素)。
        const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path, .edgePaths > path')
        if (paths[mapping.index]) {
          paths[mapping.index].setAttribute('stroke', newColor)
          paths[mapping.index].style.stroke = newColor
        }

        mapping.color = newColor
      }
    })
  }

  const updateColorsOnly = (
    svg,
    nodeColorMappings,
    linkColorMappings,
    objectToModuleMap,
    data,
    colorGroupBy
  ) => {
    if (!svg) return false

    const currentColorGroupBy = colorGroupBy
    const colorSchemes = getColorScheme(data.colorScheme)

    const colorMap = buildColorMap(
      nodeColorMappings,
      objectToModuleMap,
      currentColorGroupBy,
      colorSchemes,
      data.customColors || {}
    )

    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap, {
      centerScopeHighlight: data.centerScopeHighlight,
      centerScope: data.centerScope || [],
      centerScopeColor: data.centerScopeColor || '#808080'
    })

    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap, {
      centerScopeHighlight: data.centerScopeHighlight,
      centerScope: data.centerScope || [],
      centerScopeColor: data.centerScopeColor || '#808080'
    })

    return true
  }

  // [INC 2026-08-09] 增量更新「折叠视图」的折叠节点颜色。
  //   折叠视图: 领域/子领域/服务模块折叠为 COLLAPSE_<id> 聚合节点 (g.node.collapseNode,
  //   带 data-container-code), nodeColorMappings 为空, 原 updateNodeColors 无法着色 →
  //   切换 colorGroupBy 时 MermaidComponent.updateColorsOnly 只能 return false → 回退
  //   renderMermaid 全量重载 (闪 loading + 重置展开态)。
  //   本函数基于「分组上下文 (domainName/subDomainName/serviceModuleName) + groupColorMap
  //   (与图表同源)」, 按当前 colorGroupBy 重算每个折叠节点颜色, 直接改 SVG rect fill,
  //   实现增量更新, 与语法层 applyUpliftNodeColors 取色规则一致:
  //   - 中心范围折叠节点 → centerScopeColor
  //   - 否则按 colorGroupBy 取分组 key → groupColorMap[key]
  //   - 取不到 (折叠层级 > 颜色分组层级, 如"按服务模块"折叠了子领域) → 中性灰 #fafafa (同 classDef default)
  const updateCollapseNodeColors = (svg, collapseContextMap, colorGroupBy, colorMap, options = {}) => {
    if (!svg) return
    const centerScopeHighlight = options.centerScopeHighlight !== false // 默认 true
    const centerScopeColor = options.centerScopeColor || '#808080'
    const centerScopeMarkers = options.centerScopeMarkers || {}

    svg.querySelectorAll('g.node[id*="COLLAPSE_"], g.node.collapseNode').forEach((el) => {
      const code = el.getAttribute('data-container-code')
      if (!code) return
      // [FIX 2026-08-12 同码歧义] 从聚合节点 id 解析层级 (COLLAPSE_SD_xxx=子领域聚合,
      //   COLLAPSE_SM_xxx=服务模块聚合, COLLAPSE_D_xxx=领域聚合), 优先按 code::groupType
      //   复合键取上下文 (构建端 MermaidComponent.walkGroups 同规则)。旧实现用 code 单一键,
      //   同码子领域/服务模块 (销售SM↔服务管理SM / 内部交易ITTF↔服务模块ITTF) 互相覆盖:
      //   按服务模块分组时子领域聚合节点显示服务模块色(应为中性灰), 按领域分组时取到错误领域色。
      //   解析不到层级时回退纯 code 条目 (构建端保留首个同码条目, 不覆盖)。
      const elId = el.getAttribute('id') || ''
      const gtMatch = elId.match(/COLLAPSE_(D|SD|SM)_/)
      let wantGt = ''
      if (gtMatch) {
        const p = gtMatch[1]
        if (p === 'D') wantGt = 'domain'
        else if (p === 'SD') wantGt = 'subdomain'
        else if (p === 'SM') wantGt = 'servicemodule'
      }
      const ctx = wantGt
        ? (collapseContextMap.get(`${code}::${wantGt}`) || collapseContextMap.get(String(code)))
        : collapseContextMap.get(String(code))
      if (!ctx) return
      const rect = el.querySelector('rect')
      if (!rect) return

      // [CUSTOM-COLOR 2026-08-19] 用户自定义分组 (groupType=custom 且非 ELK 系统自动分组)
      //   的聚合节点保留面板配置色 (group.style), 不被 colorGroupBy/中心范围覆盖.
      //   根因: 用户把自定义分组拖入某领域下后, 其折叠聚合节点被按 colorGroupBy 取所属领域色
      //   (如供应链云蓝), 覆盖了面板设置色 (如黄色, 用户反馈"图表与设置不一致").
      //   与语法层 applyUpliftNodeColors 的处理保持同规则 (自同色 + skip).
      //   注意: ELK 系统分组 (无关系/有关系, 同为 custom 但带 _elkGroup) 不是用户自定义分组,
      //   维持原 colorGroupBy 覆盖逻辑.
      if (ctx.groupType === 'custom' && !(ctx._elkGroup === 'inner' || ctx._elkGroup === 'boundary')) {
        // 面板色不存在时(理论不应发生, 自定义分组必有 style.fill)回退中性灰
        rect.style.setProperty('fill', ctx.customFill || '#fafafa', 'important')
        return
      }

      // 中心范围判定 (与 useGroupDisplay 中心判定一致, 按折叠节点层级查对应 markers)
      // [FIX 2026-08-09 v3] subDomains/domains 标记的 value 是布尔 (hasCenter),
      //   且【所有】分组都会写入 map (markers.subDomains.set(name, hasCenter) /
      //   markers.domains.set(name, hasCenter)). 用 .has() 只查 key 是否存在 →
      //   返回 true 与 value 无关 → 所有子领域/领域都被误判为中心范围 → 折叠节点全染 centerScopeColor.
      //   必须 .get()===true 校验布尔值. serviceModules 只写入中心范围 SM (value 恒 true), .has() 无碍.
      // [PARTIAL-CENTER 2026-08-15] 折叠节点中心判定升级为「完全/部分包含对象范围」:
      //   - fully (该分组所有 BO 都在对象范围) → centerScopeColor (旧行为)
      //   - 部分包含 (既有对象范围内又有范围外元素) → 中性灰 (新规则)
      //   fullyXxx 标记由 useDiagramData.updateCenterScopeMarkers 填充
      //   (fullyServiceModules/fullySubDomains/fullyDomains).
      let isCenter = false
      let fullyCenter = false
      if (centerScopeHighlight) {
        if (ctx.groupType === 'serviceModule') {
          isCenter = !!centerScopeMarkers.serviceModules?.has(ctx.serviceModuleName)
            || !!centerScopeMarkers.serviceModules?.has(code)
          fullyCenter = centerScopeMarkers.fullyServiceModules?.get(ctx.serviceModuleName) === true
            || centerScopeMarkers.fullyServiceModules?.get(code) === true
        } else if (ctx.groupType === 'subDomain') {
          isCenter = centerScopeMarkers.subDomains?.get(ctx.subDomainName) === true
            || centerScopeMarkers.subDomains?.get(code) === true
          fullyCenter = centerScopeMarkers.fullySubDomains?.get(ctx.subDomainName) === true
            || centerScopeMarkers.fullySubDomains?.get(code) === true
        } else if (ctx.groupType === 'domain') {
          isCenter = centerScopeMarkers.domains?.get(ctx.domainName) === true
            || centerScopeMarkers.domains?.get(code) === true
          fullyCenter = centerScopeMarkers.fullyDomains?.get(ctx.domainName) === true
            || centerScopeMarkers.fullyDomains?.get(code) === true
        }
      }
      // 完全包含对象范围 → centerScopeColor
      if (isCenter && fullyCenter) {
        rect.style.setProperty('fill', centerScopeColor, 'important')
        return
      }
      // 部分包含对象范围 (范围内 + 范围外混合) → 中性灰, 与"折叠层级 > 分组层级"中性语义一致
      //   (聚合节点代表多种状态, 不宜用单一颜色表达)
      if (isCenter && !fullyCenter) {
        rect.style.setProperty('fill', '#fafafa', 'important')
        return
      }

      // [FOLD-COLOR 2026-08-12 显式层级规则] 聚合节点层级 < 颜色分组层级 (折叠更粗, 分组更细)
      //   → 聚合节点包含多个颜色组, 应显示中性灰, 而非取单一分组色。
      //   旧实现只靠 colorMap.get(key) 命中与否判断中性, 同码同名场景会误命中:
      //   子领域"内部交易"(title=内部交易) 与服务模块"内部交易"同名, key=ctx.title
      //   → colorMap.get("内部交易") 命中服务模块分组色 → 显示彩色而非中性。
      //   (层级数值: domain=0, subDomain=1, serviceModule=2, 见 services/expandLevel.js groupTypeLevel)
      const levelOf = (t) => (t === 'domain' ? 0 : t === 'subDomain' ? 1 : t === 'serviceModule' ? 2 : -1)
      const nodeLevel = levelOf(ctx.groupType)
      const groupLevel = levelOf(colorGroupBy)
      if (nodeLevel >= 0 && groupLevel >= 0 && nodeLevel < groupLevel) {
        rect.style.setProperty('fill', '#fafafa', 'important')
        return
      }

      let key
      if (colorGroupBy === 'serviceModule') key = ctx.serviceModuleName || ctx.title
      else if (colorGroupBy === 'subDomain') key = ctx.subDomainName || ctx.title
      else key = ctx.domainName || ctx.title

      // [FIX 2026-08-09] colorMap 键须与全量渲染/展开增量一致 (serviceModuleName/domain/subDomain),
      //   不能直接用 colorize 的 groupColorMap (其 serviceModule 键是 BO 的 name, 键不一致 → 折叠节点全灰)。
      //   colorMap 为 Map 或普通对象, 兼容两者.
      const getColor = (m, k) => (m && typeof m.get === 'function' ? m.get(k) : m?.[k])
      const color = (key && getColor(colorMap, key)) || '#fafafa'
      rect.style.setProperty('fill', color, 'important')
    })
  }

  return {
    COLOR_SCHEMES,
    DEFAULT_COLOR,
    DEFAULT_LINK_COLOR,
    getColorScheme,
    buildColorMap,
    buildColorMapFromNodes,
    updateNodeColors,
    updateLinkColors,
    updateColorsOnly,
    updateCollapseNodeColors
  }
}
