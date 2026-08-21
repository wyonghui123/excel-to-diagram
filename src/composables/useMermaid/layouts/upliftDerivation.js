/**
 * 上提(Uplift)自动推导 (2026-08-05, v2.1)
 *
 * 取代显式 collapsed 字段: 只保留 enabled 两态, 渲染引擎据此自动推导"上提为节点".
 *
 * 语义:
 * - disabled (enabled === false)  → 自身隐藏; 子孙若启用则上浮显示 (既有打平行为)
 * - enabled 且无任何启用子孙(无可见内容) → 上提为单个聚合节点 (COLLAPSE_<id>, 有颜色)
 * - enabled 且有启用子孙 → 容器 (正常 subgraph)
 *
 * 上提节点复用现有聚合节点机制 (COLLAPSE_<id>), 使连线重映射 / 隐藏节点收集
 * 与既有折叠逻辑共用同一套代码, 仅把"触发条件"由 collapsed 改为上提推导.
 */

/** 分组 id 清洗为安全节点 id 片段 (与 groupedLayout 一致) */
export function sanitizeId(id) {
  return String(id).replace(/[^\w\u4e00-\u9fff]/g, '_')
}

/** 上提聚合节点编码 */
export function upliftNodeId(group) {
  return `COLLAPSE_${sanitizeId(group?.id)}`
}

/** 判断容器是否"可见内容"(考虑 enabled) */
function containerHasShownContent(c) {
  if (!c || typeof c !== 'object') return true
  if (c.enabled === false) return false
  if (c.nodes && c.nodes.length > 0) return true
  if (c.elementRef?.code != null) return true
  if (c.elementCode != null) return true
  if (c.name != null) return true
  if (c.containers && c.containers.some(containerHasShownContent)) return true
  return false
}

/**
 * 分组子树是否会产生至少一个"可见渲染元素" (节点/容器/上提节点), 对父级可见.
 * - enabled 分组: 无论如何都渲染 (无内容→上提节点, 有内容→容器), 故返回 true.
 * - disabled 分组: 自身不渲染, 但其 enabled 后代上浮打平到父级, 仅当有后代渲染时返回 true.
 *   (穿透 disabled 分组递归, 处理"上浮"语义)
 */
function subtreeRenders(group) {
  if (!group) return false
  if (group.enabled === false) return hasShownDescendants(group)
  return true
}

/**
 * 分组是否有"可见内容".
 * 注意: 不因 group.enabled === false 短路 —— disabled 分组的子孙上浮打平到父级,
 * 故其 enabled 后代仍算父级的可见内容 (递归穿透 disabled 分组).
 * [UPLIFT 2026-08-05 v2.2] 关键修复: 一个 enabled 子分组即使其自身无内容, 也会上提为
 * 聚合节点 (COLLAPSE_<id>) 渲染, 因此对父级是"可见内容". 旧逻辑用 hasShownDescendants(child)
 * 递归, enabled 且无内容的子分组被判为"无内容" → 导致其祖先也误判为无内容而错误上提
 * (仅服务模块模板下整个图塌缩成单个标题节点). 现改为 subtreeRenders: enabled 子分组恒视为内容.
 */
export function hasShownDescendants(group) {
  if (!group) return false
  if (group.directNodes && group.directNodes.some(n =>
    (typeof n === 'object' ? n.enabled !== false : true)
  )) return true
  if (group.containers && group.containers.length &&
    group.containers.some(containerHasShownContent)) return true
  if (group.children && group.children.some(subtreeRenders)) return true
  return false
}

/**
 * 计算"上提"分组集合 (groupId -> true).
 * 上提条件: enabled === true 且 (折叠 或 无可见子孙).
 * - collapsed === true (树折叠) → 强制上提为节点/容器折叠, 即使有启用子孙 (树折叠参与渲染).
 * - 无可见子孙 → 自动上提 (enabled 且空内容).
 * 上提后其子孙全部隐藏, 故不再递归标记 (避免嵌套上提冲突).
 */
export function computeUplift(groups) {
  const uplift = new Map()
  function walk(group) {
    if (!group) return
    // [FIX 2026-08-19 修订] 空分组统一上提为聚合节点 (无论 groupType):
    //   空内容的分组渲染成"空容器框"没有视觉意义, 收成一个节点更合理 (用户确认).
    //   8-19 曾让空自定义分组渲染空容器框, 经设计 review 改为"末端空白分组 → 节点".
    //   有可见内容(含 custom) 走下方容器逻辑; 显式折叠(collapsed=true) 仍上提.
    if (group.enabled !== false && (group.collapsed === true || !hasShownDescendants(group))) {
      uplift.set(group.id, true)
      return // 上提后子孙隐藏, 不再标记 (嵌套上提会与父上提冲突)
    }
    if (group.children && group.children.length) group.children.forEach(walk)
  }
  ;(groups || []).forEach(walk)
  return uplift
}

/**
 * 原地标记分组树的 _uplift 字段 (供 groupedLayout 渲染使用).
 * @param {Array} groups 分组树
 * @returns {Map<string,boolean>} 上提分组集合
 */
export function markUplift(groups) {
  const uplift = computeUplift(groups)
  function walk(group) {
    if (!group) return
    group._uplift = uplift.has(group.id)
    if (group.children && group.children.length) group.children.forEach(walk)
  }
  ;(groups || []).forEach(walk)
  return uplift
}