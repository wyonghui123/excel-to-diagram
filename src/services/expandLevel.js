/**
 * expandLevel - 展开层级共享工具
 *
 * 由 LayoutControlPanel（图表设置抽屉）与 ChartMiniToolbar（工具栏）共用，
 * 二者通过 diagramConfigStore.expandLevel 共享当前展开层级，保证两处下拉高亮一致。
 *
 * 语义（与 LayoutControlPanel 原 handleExpandToLevel 一致）：
 *   - 展开到领域: 领域折叠为聚合节点, 子领域及以下隐藏 → 只展示领域
 *   - 展开到子领域: 领域为容器, 子领域折叠为节点, 服务模块及以下隐藏
 *   - 展开到服务模块: 领域/子领域为容器, 服务模块折叠为节点, 业务对象隐藏
 *   - 展开到业务对象: 全部展开（最深即业务对象叶子, 不折叠）
 *   折叠规则: groupTypeLevel >= target.level 即折叠（目标层及更深）。
 */

// level 表示该层级在树中的深度档位:
//   domain=0, subDomain=1, serviceModule=2, 其余(BO 叶容器/自定义/虚拟层)=3
export const EXPAND_LEVELS = [
  { key: 'domain',        label: '展开到领域',     level: 0 },
  { key: 'subDomain',     label: '展开到子领域',   level: 1 },
  { key: 'serviceModule', label: '展开到服务模块', level: 2 },
  { key: 'businessObject',label: '展开到业务对象', level: 3 }
]

export function groupTypeLevel(groupType) {
  if (groupType === 'domain') return 0
  if (groupType === 'subDomain') return 1
  if (groupType === 'serviceModule') return 2
  return 3 // BO 叶容器 / custom / virtualLayer 等一律视为最深层
}

// [SCOPE 2026-08-07] 兼容两种分组结构读取层级：
//   - LayoutControlPanel 面板树用 groupType（小写 domain/subDomain/serviceModule）
//   - GroupModel.toMermaidConfig 渲染结构用 type（大写 DOMAIN/SUB_DOMAIN/SERVICE_MODULE）
//   [FIX 2026-08-09] type 值含下划线 (SUB_DOMAIN/SERVICE_MODULE), 需去除下划线再匹配,
//     否则 SERVICE_MODULE→'service_module' 永远落入最深层(3), 范围默认折叠会误折叠.
export function groupLevelOf(group) {
  if (!group || typeof group !== 'object') return 3
  const raw = group.groupType ? String(group.groupType) : (group.type ? String(group.type) : '')
  const t = raw.toLowerCase().replace(/_/g, '')
  if (t === 'domain') return 0
  if (t === 'subdomain') return 1
  if (t === 'servicemodule') return 2
  return 3 // BO 叶容器 / custom / virtualLayer / LAYOUT 等一律视为最深层
}

// [ELK-GROUP 2026-08-12] 识别"系统自动分组"(无关系/有关系, _elkGroup=inner/boundary).
//   它们是 ELK 布局的系统分组, 非用户可折叠层级, 展开/折叠时不应被折叠为聚合节点.
//   [FIX 2026-08-19] 须同时满足 groupType='custom': 面板树平铺模式(服务模块下仅"无关系"或
//   仅"有关系"节点)会把 _elkGroup 标在 serviceModule 分组上(groupType='serviceModule'),
//   此时它是正常服务模块层级, 应参与展开层级折叠; 若仅按 _elkGroup 判定会被误豁免 →
//   面板树不折叠而图表渲染折叠, 两者不一致 (用户反馈: 图表配置默认展开层级与实际不符).
function isElkSystemAuto(item) {
  return !!item && item.groupType === 'custom' && (item._elkGroup === 'inner' || item._elkGroup === 'boundary')
}

// [FIX 2026-08-19] 识别"用户自定义分组"(groupType='custom' 且非 ELK 系统自动分组).
//   用户在图表配置新建的分组预期渲染为容器框, 不应被展开层级自动折叠成聚合节点
//   (用户反馈"新建分组不渲染成容器": 默认展开到服务模块时 custom 按 level 3 被折叠).
//   ELK 系统自动分组同样 groupType='custom', 须排除 (已有 isElkSystemAuto 处理).
function isCustomUserGroup(item) {
  return !!item && item.groupType === 'custom' && !isElkSystemAuto(item)
}

// [SCOPE 2026-08-07] 判断分组子树是否包含任一对象范围编码（兼容 containers/children/directNodes 嵌套）。
export function isSubtreeInScope(group, codeSet) {
  if (!group || !codeSet || codeSet.size === 0) return false
  const selfCode = group.elementCode || group.id || group.name
  if (selfCode && codeSet.has(selfCode)) return true
  if (group.name && codeSet.has(group.name)) return true
  if (Array.isArray(group.containers)) {
    for (const c of group.containers) {
      if (typeof c !== 'object') continue
      const cc = c.elementCode || c.id || c.name
      if (cc && codeSet.has(cc)) return true
      if (isSubtreeInScope(c, codeSet)) return true
    }
  }
  if (Array.isArray(group.children)) {
    for (const ch of group.children) {
      if (typeof ch === 'object' && isSubtreeInScope(ch, codeSet)) return true
    }
  }
  if (Array.isArray(group.directNodes)) {
    for (const n of group.directNodes) {
      const nc = typeof n === 'object' ? (n.code || n.id || n.name) : n
      if (nc && codeSet.has(nc)) return true
    }
  }
  return false
}

/**
 * 展开到指定层级（钻取语义）：就地修改 items 中各分组的 collapsed。
 * @param {Array} items - 分组树顶层数组
 * @param {string} key - EXPAND_LEVELS 中的 key
 * @param {Object} [options] - 选项
 * @param {boolean} [options.resetVisible=false] - 是否重置用户图例隐藏(visible=false → true).
 *   仅"用户显式切换全局展开层级"的操作方(面板下拉/空白右键全局展开/调试 API)传 true,
 *   保持 2026-08-12 的旧规则; 渲染层每次重算/系统默认展开绝不重置, 否则用户主动隐藏
 *   (如隐藏外部领域云) 会在任何图表 reload 后丢失 (2026-08-14 用户反馈 bug).
 * @returns {{matched:number, collapsedCount:number}} 折叠分组计数 (用于可观测/验证)
 */
export function expandGroupsToLevel(items, key, options = {}) {
  const target = EXPAND_LEVELS.find((x) => x.key === key)
  if (!target || !Array.isArray(items)) return { matched: 0, collapsedCount: 0 }
  const expandAll = key === 'businessObject'
  // [VIS-RESET 2026-08-14] 门控: 默认 false (保留用户隐藏). 显式切换全局层级时传 true,
  //   重置图例/面板的 visible=false, 避免"折叠聚合后隐藏分组不显示、空容器残留" (2026-08-12 旧规则).
  //   注: ELK 布局系统自动分组(_elkGroup=inner/boundary, 如"无关系/有关系")
  //   默认 visible=false 是系统语义, 不属用户图例隐藏, 须跳过以免打乱内部布局.
  const resetVisible = options.resetVisible === true
  let collapsedCount = 0
  function setLevels(list) {
    if (!Array.isArray(list)) return
    for (const item of list) {
      if (!item || typeof item !== 'object') continue
      const isSystemAuto = item.groupType === 'custom' && (item._elkGroup === 'inner' || item._elkGroup === 'boundary')
      if (resetVisible) {
        if (item.visible === false && !isSystemAuto) item.visible = true
      }
      // [ELK-GROUP 2026-08-12] 系统自动分组(无关系/有关系)不参与折叠(非用户可折叠层级),
      //   始终保持容器形态, 由 enabled/visible 单独控制其盒子显示.
      // [FIX 2026-08-19] 用户自定义分组(groupType='custom')同样不被展开层级折叠:
      //   新建分组预期渲染为容器框 (groupTypeLevel('custom')=3 会按最深层被误折叠).
      const shouldCollapse = expandAll ? false : (isSystemAuto || isCustomUserGroup(item) ? false : (groupTypeLevel(item.groupType) >= target.level))
      if (item.collapsed !== shouldCollapse) item.collapsed = shouldCollapse
      if (shouldCollapse) collapsedCount++
      setLevels(item.children)
      setLevels(item.containers)
    }
  }
  setLevels(items)
  // [OBS 2026-08-08] 非"业务对象"展开却 0 折叠 → 分组树为空/groupType 层级不匹配,
  //   展开层级实际未生效(静默失败). 显式告警便于定位"展开到服务模块仍显示业务对象".
  if (collapsedCount === 0 && !expandAll) {
    console.warn(`[expandLevel] expandGroupsToLevel('${key}') 未折叠任何分组 (items=${items.length}), 检查分组树 groupType/层级`)
  }
  return { matched: collapsedCount, collapsedCount }
}

/**
 * 初始图表智能默认展开层级（按对象范围区分）：
 *   - 对象范围内的分组    → 展开到服务模块（serviceModule 及更深折叠为聚合节点）
 *   - 对象范围外的分组    → 展开到子领域（subDomain 及更深折叠为聚合节点）
 *
 * 就地修改 items 中各分组 collapsed。仅当存在对象范围（isInScope 非空）时生效，
 * 否则保持全展开（业务对象层级），与 store.expandLevel 默认一致。
 *
 * @param {Array} items - 分组树顶层数组
 * @param {Function} isInScope - (group) => boolean，判断分组子树是否属于对象范围
 * @returns {{matched:number, collapsedCount:number}} matched=范围内分组命中数, collapsedCount=折叠分组数
 */
export function applyDefaultExpandByScope(items, isInScope) {
  if (!Array.isArray(items)) return { matched: 0, collapsedCount: 0 }
  // [FIX 2026-08-09] 无范围判断函数 → 无对象范围 → 保持全展开, 不告警.
  //   之前 hasScope 早退把"范围内 0 命中"的告警变成死代码(永远不可达), 静默失败无法观测.
  if (typeof isInScope !== 'function') return { matched: 0, collapsedCount: 0 }
  const hasScope = items.some((g) => isInScope(g))
  // 有范围判断但整棵树无命中 → 范围编码与分组树不匹配(scopeCode 失败), 中止默认折叠并告警.
  //   调用方须仅在 centerScope 非空时才传入谓词, 避免空范围误告警(见各调用点).
  if (!hasScope) {
    console.warn(`[expandLevel] applyDefaultExpandByScope 未命中任何范围内分组 (items=${items.length}), 检查 isInScope/范围编码匹配`)
    return { matched: 0, collapsedCount: 0 }
  }
  let collapsedCount = 0
  let inScopeCount = 0
  function setLevels(list) {
    if (!Array.isArray(list)) return
    for (const item of list) {
      if (!item || typeof item !== 'object') continue
      // 对象范围内 targetLevel=2(服务模块)；范围外 targetLevel=1(子领域)
      const inScope = isInScope(item)
      if (inScope) inScopeCount++
      const targetLevel = inScope ? 2 : 1
      // [ELK-GROUP 2026-08-12] 系统自动分组(无关系/有关系)不参与范围折叠, 保持容器形态.
      // [FIX 2026-08-19] 用户自定义分组(groupType='custom')同样不被范围折叠:
      //   新建分组预期渲染为容器框.
      const shouldCollapse = (isElkSystemAuto(item) || isCustomUserGroup(item)) ? false : (groupLevelOf(item) >= targetLevel)
      if (item.collapsed !== shouldCollapse) item.collapsed = shouldCollapse
      if (shouldCollapse) collapsedCount++
      setLevels(item.children)
      setLevels(item.containers)
    }
  }
  setLevels(items)
  return { matched: inScopeCount, collapsedCount }
}

// [DEFAULT-LEVEL 2026-08-12] 系统默认展开层级（按分组数量自适应）:
//   图表初始展示时, 从粗到细找第一个"分组数 > 1"的层级作为默认展开层级:
//     >1 领域   → 展开到领域
//     否则 >1 子领域 → 展开到子领域
//     否则 >1 服务模块 → 展开到服务模块
//     否则     → 业务对象（全展开）
//   统计范围覆盖整棵分组树（递归 children/containers）。ELK 系统自动分组
//   （无关系/有关系, groupType=custom → level 3）不参与计数。
// @param {Array} items - 分组树顶层数组
// @returns {string} EXPAND_LEVELS 中的 key
export function computeDefaultExpandLevel(items) {
  if (!Array.isArray(items) || items.length === 0) return 'businessObject'
  let domain = 0
  let subDomain = 0
  let serviceModule = 0
  function walk(list) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g || typeof g !== 'object') continue
      const lvl = groupLevelOf(g)
      if (lvl === 0) domain++
      else if (lvl === 1) subDomain++
      else if (lvl === 2) serviceModule++
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(items)
  if (domain > 1) return 'domain'
  if (subDomain > 1) return 'subDomain'
  if (serviceModule > 1) return 'serviceModule'
  return 'businessObject'
}

// 应用系统默认展开层级: computeDefaultExpandLevel → expandGroupsToLevel (就地修改 collapsed).
// 仅作为"用户未显式选择展开层级"时的初始默认, 用户显式选择后由调用方切换到用户层级.
// @returns {{ level:string, collapsedCount:number }}
export function applyDefaultExpandByCount(items) {
  const level = computeDefaultExpandLevel(items)
  const r = expandGroupsToLevel(items, level)
  return { level, collapsedCount: r.collapsedCount }
}