/**
 * scaleGuard/guard - 阈值判定 + 文案 (纯函数)
 * 可见关系数为主指标, 可见节点数为辅; 任一超线即升级。
 */
export const LEVELS = ['ok', 'soft', 'hard']

export function classify({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  if (relations > (c.hardRels || Infinity) || nodes > (c.hardNodes || Infinity)) return 'hard'
  if (relations > (c.softRels || Infinity) || nodes > (c.softNodes || Infinity)) return 'soft'
  return 'ok'
}

export function buildEntryMessages({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  const n = (v) => v == null ? '?' : v
  return {
    soft: `当前图含 ${n(relations)} 关系 / ${n(nodes)} 节点, 超出推荐可读范围(约 ${c.softRels} 关系)。建议缩小对象范围或折叠到服务模块层。`,
    hard: `所选范围过大 (约 ${n(relations)} 关系 / ${n(nodes)} 节点), 渲染会明显卡顿。请选择: ① 折叠到服务模块层展示 ② 返回缩小对象范围。`
  }
}

export function buildExpandMessages({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  const n = (v) => v == null ? '?' : v
  return {
    soft: `展开后可见关系将达 ${n(relations)} / 节点 ${n(nodes)}, 可能影响阅读; 已折叠分支可用右键折叠。`,
    hard: `展开将导致约 ${n(relations)} 关系渲染, 可能明显卡顿; 请先折叠其他分支或缩小对象范围。`
  }
}
