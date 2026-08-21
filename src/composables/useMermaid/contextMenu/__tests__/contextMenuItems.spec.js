/**
 * contextMenuItems.spec.js - 右键菜单项结构
 * 回归保护: 2026-08-14 菜单结构优化 (用户确认)
 *   - 对象菜单: 折叠/展开放首位, 分隔线后「关系高亮」
 *   - 全局菜单: 小分组标题「展开层级」+ 4 个一级展开项
 */
import { describe, it, expect } from 'vitest'
import { buildContextMenuItems, buildGlobalExpandItems } from '../contextMenuItems.js'

describe('buildContextMenuItems (对象菜单)', () => {
  const keys = (items) => items.filter(i => i.key).map(i => i.key)

  it('领域: 折叠/展开在前, 关系高亮在分隔线后', () => {
    const items = buildContextMenuItems({ groupType: 'domain' })
    expect(keys(items)).toEqual([
      'collapse', 'expandSub', 'expandSM', 'expandBO', 'highlightRelations',
    ])
    // 关系高亮前必须有分隔线
    const idx = items.findIndex(i => i.key === 'highlightRelations')
    expect(items[idx - 1].divider).toBe(true)
  })

  it('子领域: 折叠/展开到服务模块/展开到业务对象在前', () => {
    const items = buildContextMenuItems({ groupType: 'subDomain' })
    expect(keys(items)).toEqual([
      'collapse', 'expandSM', 'expandBO', 'highlightRelations',
    ])
    expect(items[3].divider).toBe(true)
  })

  it('服务模块: 折叠/展开到业务对象在前', () => {
    const items = buildContextMenuItems({ groupType: 'service_module' })
    expect(keys(items)).toEqual([
      'collapse', 'expandBO', 'highlightRelations',
    ])
    expect(items[2].divider).toBe(true)
  })

  it('业务对象: 仅关系高亮', () => {
    expect(keys(buildContextMenuItems({ groupType: 'businessObject' }))).toEqual(['highlightRelations'])
  })

  it('未知类型: 空菜单', () => {
    expect(buildContextMenuItems({ groupType: 'custom' })).toEqual([])
  })
})

describe('buildGlobalExpandItems (全局菜单)', () => {
  const keys = (items) => items.filter(i => i.key).map(i => i.key)

  it('小分组标题 + 4 个一级展开项', () => {
    const items = buildGlobalExpandItems()
    expect(items[0]).toEqual({ header: '展开层级' })
    expect(keys(items)).toEqual([
      'expandGlobal:domain', 'expandGlobal:subDomain',
      'expandGlobal:serviceModule', 'expandGlobal:businessObject',
    ])
  })
})
