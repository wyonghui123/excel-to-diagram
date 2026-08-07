/**
 * layoutMergeLogic - 布局面板编辑 → 渲染分组树的合并逻辑（纯函数）
 * =================================================================
 *
 * [目的] 把 EmbeddedChartView.layoutControlConfig 里的合并步骤抽成纯函数模块，
 *   便于单元测试（毫秒级、可精确断言），避免每次修复都只能靠 E2E 慢速验证。
 *
 * 合并链路（EmbeddedChartView.layoutControlConfig 调用顺序）：
 *   1. applyGroupStates          - 透传 enabled/visible 状态（layoutPanelAdapter.js 已有）
 *   2. applyContainerMembership  - 重建叶子归属（追随面板拖拽移动）
 *   3. applyGroupTitlesAndOrder  - 覆盖重命名标题 + 按面板顺序重排
 *
 * 本模块只含步骤 2、3（纯数据，无组件依赖）。
 */

// [MOVE 2026-08-04] 把用户在布局面板的"拖拽节点/容器到另一分组"的结构变更同步到渲染。
//   unified.groups（deriveLayoutGroups 派生）的叶子归属来自投影容器树，不反映用户在面板的
//   拖拽移动（把容器从分组 A 拖到分组 B）。本函数按叶子 code 匹配，重建每个分组的叶子
//   （directNodes / containers）归属，追随面板树结构 → 图表基于新的树结构生成。
//   注意：必须在 applyGroupStates 之后调用，且需在 applyGroupTitlesAndOrder 之前调用。
//   两种叶子存储形态：
//     - directNodes 分组（如 SM 图 SD 存 SM code、BO 图 SM 存 BO code）：叶子是 node code，
//       用面板容器 code 重建，保持渲染形态（不包一层子图，避免"同一容器既容器又节点"重复）。
//     - containers 分组：叶子是容器对象，用面板容器对象（含节点数据），避免把 code 当原始字符串
//       塞进 containers 导致空容器"不包住子节点"。
export function applyContainerMembership(mergedGroups, userGroups) {
  if (!Array.isArray(userGroups) || userGroups.length === 0) return

  function leafCode(c) {
    if (typeof c === 'string') return c
    return c.elementCode || c.elementRef?.code || c.code || c.id
  }

  function walk(mergedItems, userItems) {
    if (!Array.isArray(mergedItems) || !Array.isArray(userItems)) return
    for (const u of userItems) {
      const key = u.elementCode || u.id
      const m = mergedItems.find(x => (x.elementCode || x.id) === key)
      if (!m) continue

      // 重建该分组的叶子归属（追随面板：拖拽移动后叶子出现在新分组，不再出现在旧分组）
      // [FIX 2026-08-04] 面板分组可能把叶子放在 children 里的子分组（如 BO 图的 ELK
      //   无外部关系/有外部关系），此时 u.containers 为空但叶子并未消失，不能据此清空
      //   合并树的 directNodes（否则容器"不包住子节点"）。仅当 u.containers 确有叶子时
      //   才重建；仅当分组既无叶子也无子分组时才真正为空（拖走最后一个叶子）。
      if (Array.isArray(u.containers)) {
        if (u.containers.length > 0) {
          if (Array.isArray(m.directNodes)) {
            // 该分组用 directNodes 存叶子 → 用面板容器 code 重建
            m.directNodes = u.containers.map(uc => leafCode(uc)).filter(Boolean)
            m.containers = []
          } else {
            // 该分组用 containers 存叶子 → 用面板容器对象（含节点数据），保持其包裹子节点
            m.containers = u.containers.map(uc => uc)
          }
        } else if (!Array.isArray(u.children) || u.children.length === 0) {
          // 面板分组既无叶子容器也无子分组 → 真正为空 → 清空合并树叶子（拖走最后一个叶子）
          if (Array.isArray(m.directNodes)) m.directNodes = []
          else m.containers = []
        }
      }

      if (Array.isArray(u.children) && Array.isArray(m.children)) {
        walk(m.children, u.children)
      }
    }
  }
  walk(mergedGroups, userGroups)
}

// [FIX 2026-08-04] 把用户在布局面板的编辑（重命名标题 / 拖拽排序）合并到渲染用的 unified groups。
//   unified.groups（deriveLayoutGroups 派生）结构正确（D→SD→containers），但 title 与顺序不反映
//   面板编辑。本函数按 elementCode 深度匹配，覆盖 title，并按面板顺序重排每一层 children。
//   enabled/visible 已由 applyGroupStates 单独处理，这里只处理 title + 顺序。
export function applyGroupTitlesAndOrder(mergedGroups, userGroups) {
  if (!Array.isArray(userGroups) || userGroups.length === 0) return

  function walk(mergedItems, userItems) {
    if (!Array.isArray(mergedItems) || !Array.isArray(userItems)) return

    // 覆盖 title（按 elementCode 深度匹配）
    for (const u of userItems) {
      const key = u.elementCode || u.id
      if (!key || u.title == null) continue
      const target = mergedItems.find(m => (m.elementCode || m.id) === key)
      if (target && target.title !== u.title) {
        // [FIX 2026-08-04] 标记用户手动重命名，供 MermaidComponent 的 titleMap 覆盖跳过，
        //   否则 groupControlTitleMap（来自原始数据名）会把重命名标题还原成旧名。
        target.title = u.title
        target._userRenamed = true
      }
    }

    // 按面板顺序重排当前层
    const orderMap = new Map()
    userItems.forEach((u, i) => orderMap.set(u.elementCode || u.id, i))
    mergedItems.sort((a, b) => {
      const oa = orderMap.get(a.elementCode || a.id)
      const ob = orderMap.get(b.elementCode || b.id)
      if (oa === undefined && ob === undefined) return 0
      if (oa === undefined) return 1
      if (ob === undefined) return -1
      return oa - ob
    })

    // [REORDER 2026-08-04] 同步群组内叶子容器顺序（面板拖拽重排容器后反映到图表）
    for (const u of userItems) {
      const key = u.elementCode || u.id
      if (!key || !Array.isArray(u.containers) || u.containers.length === 0) continue
      const target = mergedItems.find(m => (m.elementCode || m.id) === key)
      if (!target || !Array.isArray(target.containers) || target.containers.length === 0) continue
      const cOrder = new Map()
      u.containers.forEach((c, i) => cOrder.set(c.id || c.elementCode || c.code, i))
      target.containers.sort((a, b) => {
        const oa = cOrder.get(a.id || a.elementCode || a.code)
        const ob = cOrder.get(b.id || b.elementCode || b.code)
        if (oa === undefined && ob === undefined) return 0
        if (oa === undefined) return 1
        if (ob === undefined) return -1
        return oa - ob
      })
    }

    // 递归子层级
    for (const m of mergedItems) {
      const u = userItems.find(x => (x.elementCode || x.id) === (m.elementCode || m.id))
      if (u && u.children && u.children.length > 0 && m.children && m.children.length > 0) {
        walk(m.children, u.children)
      }
    }
  }

  walk(mergedGroups, userGroups)
}