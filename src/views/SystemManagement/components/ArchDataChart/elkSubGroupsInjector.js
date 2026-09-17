// [ELK-GROUP 2026-08-12] 把面板树"无关系/有关系"系统自动分组(_elkGroup=inner/boundary)
//   注入到渲染树的服务模块下, 使面板切换真正驱动图表分组 (接入渲染).
//   - 渲染树 (deriveLayoutGroups) 服务模块仅存扁平 directNodes (BO 编码), 不含 ELK 子分组
//     → 面板 enabled/visible 切换在图表上无任何区别 (用户反馈的 bug).
//   - 面板树 (buildBusinessObjectGroups) 服务模块 children 含 ELK 子分组, 其 containers 记录了
//     每个 BO 归属于"无关系(inner)"/"有关系(boundary)".
//   注入结果: 服务模块的 BO 叶子按面板 ELK 分类拆分为两个子分组, 携带面板最新 enabled/visible.
//   纯函数, 就地修改 mergedGroups, 返回它.
export function injectElkSubGroups(mergedGroups, panelGroups) {
  if (!Array.isArray(panelGroups) || panelGroups.length === 0) return mergedGroups
  // 收集面板树中每个服务模块的 ELK 子分组 (smCode -> { inner, boundary })
  const elkBySmCode = new Map()
  function collectPanel(items) {
    for (const g of items || []) {
      if (!g) continue
      if (g.groupType === 'serviceModule' && g.elementCode) {
        const elkChildren = (g.children || []).filter(c => c && (c._elkGroup === 'inner' || c._elkGroup === 'boundary'))
        if (elkChildren.length > 0) {
          const entry = { inner: null, boundary: null }
          for (const ec of elkChildren) entry[ec._elkGroup] = ec
          elkBySmCode.set(g.elementCode, entry)
        }
      }
      collectPanel(g.children)
    }
  }
  collectPanel(panelGroups)
  if (elkBySmCode.size === 0) return mergedGroups

  function injectIntoSm(sm) {
    const entry = elkBySmCode.get(sm.elementCode)
    if (!entry) return
    const children = []
    for (const elkType of ['inner', 'boundary']) {
      const ec = entry[elkType]
      if (!ec) continue
      // 收集该 ELK 子分组覆盖的 BO 编码.
      //   兼容两种形态: 面板格式 (containers[].nodes) 与渲染格式 (directNodes,
      //   由 setExpandLevel/executeGlobalExpand 经 updateLayoutControlConfig 写回 store 后产生).
      const codes = []
      for (const c of ec.containers || []) {
        if (c && Array.isArray(c.nodes)) codes.push(...c.nodes)
      }
      if (Array.isArray(ec.directNodes)) codes.push(...ec.directNodes)
      children.push({
        id: ec.id || `${sm.elementCode}_${elkType}`,
        title: ec.title || (elkType === 'inner' ? '无关系' : '有关系'),
        elementCode: ec.elementCode || `${sm.elementCode}_${elkType}`,
        groupType: 'custom',
        _elkGroup: elkType,
        enabled: ec.enabled !== false,
        visible: ec.visible !== false,
        style: ec.style || {},
        direction: ec.direction || 'TB',
        directNodes: codes,
        containers: [],
        children: [],
        parentId: sm.id
      })
    }
    if (children.length === 0) return
    // 移除被 ELK 子分组覆盖的 BO 叶子, 未覆盖的保留在原 directNodes (防御: 面板与投影编码不一致时不丢节点)
    const covered = new Set()
    children.forEach(ch => (ch.directNodes || []).forEach(n => covered.add(n)))
    sm.directNodes = (sm.directNodes || []).filter(n => !covered.has(n))
    // [CUSTOM-COLOR 2026-08-19] 保留 SM 下非 ELK 的孩子(用户在同一服务模块下新建的自定义分组),
    //   只在前面注入 ELK 子分组, 不覆盖 children. 原 `sm.children = children` 会把用户新建分组整体覆盖掉
    //   → 若 SM 下已有"无关系/有关系"兄弟容器, 新增的自定义分组不展示 (用户反馈的 bug).
    const nonElkChildren = (sm.children || []).filter(c => !c || !(c._elkGroup === 'inner' || c._elkGroup === 'boundary'))
    sm.children = [...children, ...nonElkChildren]
  }

  function walk(groups) {
    for (const g of groups || []) {
      if (!g) continue
      if (g.groupType === 'serviceModule') injectIntoSm(g)
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(mergedGroups)
  return mergedGroups
}
