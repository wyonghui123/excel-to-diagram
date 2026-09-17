/**
 * contextMenuItems.js - 图表右键菜单项构建 (纯函数)
 * ====================================================================
 * [目的] 把 MermaidComponent 里的菜单项构建抽成纯函数, 便于单元测试与回归保护.
 *
 * [结构约定 2026-08-14 用户确认]
 *   - 对象菜单: 折叠/展开 (核心操作) 放首位, 分隔线后为「关系高亮」(第二组)
 *   - 全局菜单: 小分组标题「展开层级」+ 4 个一级展开项
 */

export function buildContextMenuItems(group) {
  const gtype = (group.groupType || '').toLowerCase()
  if (gtype === 'domain') {
    return [
      { key: 'collapse', label: '折叠' },
      { key: 'expandSub', label: '展开到子领域' },
      { key: 'expandSM', label: '展开到服务模块' },
      { key: 'expandBO', label: '展开到业务对象' },
      { divider: true },
      { key: 'highlightRelations', label: '关系高亮' },
    ]
  }
  if (gtype === 'servicemodule' || gtype === 'service_module') {
    return [
      { key: 'collapse', label: '折叠' },
      { key: 'expandBO', label: '展开到业务对象' },
      { divider: true },
      { key: 'highlightRelations', label: '关系高亮' },
    ]
  }
  if (gtype === 'subdomain' || gtype === 'sub_domain') {
    return [
      { key: 'collapse', label: '折叠' },
      { key: 'expandSM', label: '展开到服务模块' },
      { key: 'expandBO', label: '展开到业务对象' },
      { divider: true },
      { key: 'highlightRelations', label: '关系高亮' },
    ]
  }
  if (gtype === 'businessobject' || gtype === 'business_object' || gtype === 'bo') {
    // 业务对象节点: 仅提供"关系高亮" (BO 无折叠/展开子层级)
    return [{ key: 'highlightRelations', label: '关系高亮' }]
  }
  // 自定义等其他类型: 不展示菜单
  return []
}

export function buildGlobalExpandItems() {
  // 空白区域右键: 全局"展开层级"菜单 (替代 GlobalToolbar 展开层级下拉)
  return [
    { header: '展开层级' },
    { key: 'expandGlobal:domain', label: '展开到领域' },
    { key: 'expandGlobal:subDomain', label: '展开到子领域' },
    { key: 'expandGlobal:serviceModule', label: '展开到服务模块' },
    { key: 'expandGlobal:businessObject', label: '展开到业务对象' },
  ]
}
