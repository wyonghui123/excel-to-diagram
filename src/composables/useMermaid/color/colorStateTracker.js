/**
 * 颜色状态追踪器 (colorStateTracker)
 *
 * 解决的问题：deep watch 下"原地修改导致 oldVal === newVal，颜色字段变化
 * 无法被 oldVal diff 识别"。
 *
 * 背景：区分/不区分业务对象 (centerScopeHighlight) 等颜色字段，为避免触发
 * layoutControlConfig computed 重算导致用户手动折叠状态丢失，采用"原地修改
 * props.diagramData.xxx"（对象引用不变）。但 MermaidComponent 用 deep watch
 * (`() => props.diagramData`)，原地修改时回调里 oldVal === newVal（同一引用），
 * 基于 oldVal 的比较恒为 false → 颜色变化判断失效 → 恒走全量 renderMermaid()，
 * 而非 updateColorsOnly 增量变色。
 *
 * 方案：所有颜色字段统一用本 tracker 维护的"最近一次渲染值(last*)快照"做对比，
 * 而非失效的 oldVal。tracker 在每次渲染 (renderMermaid / updateColorsOnly) 结束时
 * 通过 snapshot() 刷新快照。这样未来任何颜色字段改为原地修改都安全。
 */
export function createColorStateTracker(initial = {}) {
  let state = {
    colorGroupBy: initial.colorGroupBy ?? 'domain',
    colorScheme: initial.colorScheme ?? null,
    centerScopeHighlight: initial.centerScopeHighlight ?? null,
    customColors: initial.customColors ? { ...initial.customColors } : null
  }

  /** 检测颜色字段相对最近一次快照是否有变化（只读，不更新快照）。 */
  function changed(data) {
    const d = data || {}
    const str = (v) => (v === undefined || v === null ? null : (typeof v === 'object' ? JSON.stringify(v) : v))
    const current = {
      colorGroupBy: d.colorGroupBy ?? 'domain',
      colorScheme: str(d.colorScheme),
      centerScopeHighlight: str(d.centerScopeHighlight),
      customColors: d.customColors ? JSON.stringify(d.customColors) : null
    }
    const last = {
      colorGroupBy: state.colorGroupBy,
      colorScheme: str(state.colorScheme),
      centerScopeHighlight: str(state.centerScopeHighlight),
      customColors: state.customColors ? JSON.stringify(state.customColors) : null
    }
    return {
      colorGroupBy: current.colorGroupBy !== last.colorGroupBy,
      colorScheme: current.colorScheme !== last.colorScheme,
      centerScopeHighlight: current.centerScopeHighlight !== last.centerScopeHighlight,
      customColors: current.customColors !== last.customColors
    }
  }

  /** 将当前 data 的颜色字段快照为"最近一次值"，供下一轮 changed() 对比。 */
  function snapshot(data) {
    const d = data || {}
    state.colorGroupBy = d.colorGroupBy ?? 'domain'
    state.colorScheme = d.colorScheme ?? null
    state.centerScopeHighlight = d.centerScopeHighlight ?? null
    state.customColors = d.customColors ? { ...d.customColors } : null
  }

  /** 是否有任一颜色字段变化（changed() 结果的便捷聚合）。 */
  function anyChanged(data) {
    const c = changed(data)
    return c.colorGroupBy || c.colorScheme || c.centerScopeHighlight || c.customColors
  }

  return { changed, snapshot, anyChanged, get state() { return state } }
}
