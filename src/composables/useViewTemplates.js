import { GroupType } from '@/services/groupModel/types.js'

/**
 * 视图模板 + 子树多态操作 (FR-005, 2026-08-05, v2.1)
 *
 * 三个预设模板, 一键应用到 layoutControlConfig.groups:
 * - allEnabled(全部启用):        所有分组/节点 enabled=true
 * - onlyServiceModules(仅服务模块): 展开所有分组, 隐藏所有 BO 叶节点, 保留服务模块
 *
 * 多态操作 (替代显式折叠, 由 enabled 自动上提推导):
 * - setSubtreeEnabled(group, enabled):  级联启用/禁用 自身+全部子孙
 * - collapseToNode(group):              自身启用, 全部子孙禁用 → 自身自动上提为节点
 * - showDescendantsOnly(group):         自身禁用, 全部子孙启用 → 自身隐藏, 子孙上浮显示
 *
 * BO 图与 SM 图的 groups 结构不同:
 * - BO 图 (buildBusinessObjectGroups):  domain → subDomain → serviceModule → [BO 叶 container]
 *   BO 叶 container 标记 isVirtual=true, groupType='custom', elementRef.type=BUSINESS_OBJECT
 * - SM 图 (buildServiceModuleGroupsFromDomainProducts): domain → subDomain → SM container
 *   SM container 的 groupType='serviceModule', elementRef.type=SERVICE_MODULE
 *
 * "仅服务模块"对 BO 图有效 (隐藏 BO 节点, 保留服务模块分组);
 * 对 SM 图本身已是"仅服务模块"视图, 应用后无副作用 (SM 容器不会被隐藏).
 */

/** 判断容器/分组是否为 BO 叶节点 (需要被 onlyServiceModules 隐藏) */
export function isBusinessObjectLeaf(item) {
  if (!item || typeof item !== 'object') return false
  // 服务模块容器 (SM 图终端 / BO 图 serviceModule 分组) → 保留
  if (item.groupType === 'serviceModule') return false
  if (item.elementRef?.type === GroupType.SERVICE_MODULE) return false
  // BO 叶节点: 虚拟容器 (单个 BO 节点)
  if (item.isVirtual === true) return true
  if (item.elementRef?.type === GroupType.BUSINESS_OBJECT) return true
  // 有子树的 (还不是叶) → 保留
  const hasSubTree = (item.children && item.children.length > 0) ||
                     (item.containers && item.containers.length > 0)
  if (hasSubTree) return false
  // 无子树的终端容器: 非 serviceModule 即视为 BO 叶
  return item.elementCode != null
}

/** 递归遍历 groups 树 */
function walk(items, fn) {
  if (!Array.isArray(items)) return
  for (const item of items) {
    if (!item) continue
    fn(item)
    if (item.children && item.children.length > 0) walk(item.children, fn)
    if (item.containers && item.containers.length > 0) walk(item.containers, fn)
  }
}

/**
 * 应用视图模板 (原地修改 groups)
 * @param {Array} groups 分组树
 * @param {string} template 'allEnabled' | 'onlyServiceModules'
 * @returns {number} 应用模板的节点数
 */
export function applyViewTemplate(groups, template) {
  if (!Array.isArray(groups) || groups.length === 0) return 0
  let applied = 0

  if (template === 'allEnabled') {
    walk(groups, item => {
      if (item.enabled !== true) { item.enabled = true; applied++ }
    })
  } else if (template === 'onlyServiceModules') {
    walk(groups, item => {
      // BO 叶节点隐藏, 其余保留
      const shouldHide = isBusinessObjectLeaf(item)
      if (item.enabled !== !shouldHide) { item.enabled = !shouldHide; applied++ }
    })
  }

  return applied
}

/**
 * [UPLIFT 2026-08-05] 级联设置子树 enabled (自身 + 全部子孙).
 * @param {Object} group 分组对象 (原地修改)
 * @param {boolean} enabled 目标启用状态
 * @returns {number} 实际发生状态变化的节点数
 */
export function setSubtreeEnabled(group, enabled) {
  if (!group || typeof group !== 'object') return 0
  let count = 0
  if (group.enabled !== enabled) { group.enabled = enabled; count++ }
  const descendants = [...(group.children || []), ...(group.containers || [])]
  for (const d of descendants) {
    count += setSubtreeEnabled(d, enabled)
  }
  return count
}

/**
 * [UPLIFT 2026-08-05] 折叠为节点: 自身启用, 全部子孙禁用 → 自身无可见子孙 → 自动上提为节点.
 * 等价于旧"折叠(子孙一并折叠)".
 * @param {Object} group 分组对象 (原地修改)
 * @returns {number} 实际发生状态变化的节点数
 */
export function collapseToNode(group) {
  if (!group || typeof group !== 'object') return 0
  let count = 0
  if (group.enabled !== true) { group.enabled = true; count++ }
  const descendants = [...(group.children || []), ...(group.containers || [])]
  for (const d of descendants) {
    count += setSubtreeEnabled(d, false)
  }
  return count
}

/**
 * [UPLIFT 2026-08-05] 仅显示子孙: 自身禁用, 全部子孙启用 → 自身隐藏, 子孙上浮显示.
 * 保留"保持自身禁用但启用全部子孙"的快捷能力.
 * @param {Object} group 分组对象 (原地修改)
 * @returns {number} 实际发生状态变化的节点数
 */
export function showDescendantsOnly(group) {
  if (!group || typeof group !== 'object') return 0
  let count = 0
  if (group.enabled !== false) { group.enabled = false; count++ }
  const descendants = [...(group.children || []), ...(group.containers || [])]
  for (const d of descendants) {
    count += setSubtreeEnabled(d, true)
  }
  return count
}