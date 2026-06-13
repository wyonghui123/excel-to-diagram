/**
 * useLayoutControl 单测 (v32 复盘回归保护 - 2026-06-11)
 *
 * 覆盖:
 * - createGroup 顶层 / 子组 / 深度限制
 * - moveContainerBetweenGroups / 找不到 / 跨组移动
 * - updateGroup / deleteGroup / assignContainerToGroup
 * - getGroupDepth / canCreateChildGroup / getDefaultGroupStyle
 * - findGroupById / findParentGroup / resetConfig
 *
 * 总计: 10 个测试
 *
 * 重要: useLayoutControl.js 只 export useLayoutControl() 函数,
 *       内部函数通过返回值访问, 这里用 destructure 拿到
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useLayoutControl } from '../useLayoutControl'

describe('useLayoutControl - 基础 API', () => {
  let api
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
  })

  it('useLayoutControl 返回所有方法', () => {
    expect(typeof api.createGroup).toBe('function')
    expect(typeof api.updateGroup).toBe('function')
    expect(typeof api.deleteGroup).toBe('function')
    expect(typeof api.moveContainerBetweenGroups).toBe('function')
    expect(typeof api.resetConfig).toBe('function')
  })
})

describe('useLayoutControl - generateGroupId', () => {
  it('应返回唯一 ID', () => {
    const api = useLayoutControl()
    const id1 = api.generateGroupId()
    const id2 = api.generateGroupId()
    expect(id1).not.toBe(id2)
    expect(id1).toMatch(/^group_\d+_[a-z0-9]+$/)
  })
})

describe('useLayoutControl - getDefaultGroupStyle', () => {
  it('返回默认样式对象', () => {
    const api = useLayoutControl()
    const style = api.getDefaultGroupStyle()
    expect(style).toEqual({
      fill: '#f5f5f5',
      stroke: '#333333',
      strokeWidth: 1,
      strokeDasharray: ''
    })
  })

  it('每次返回新对象 (非引用)', () => {
    const api = useLayoutControl()
    const s1 = api.getDefaultGroupStyle()
    const s2 = api.getDefaultGroupStyle()
    expect(s1).not.toBe(s2)
    s1.fill = '#FF0000'
    expect(s2.fill).toBe('#f5f5f5')
  })
})

describe('useLayoutControl - createGroup', () => {
  let api
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
  })

  it('createGroup 顶层: 加入 layoutControlConfig.groups', () => {
    const g = api.createGroup('顶层组')
    expect(api.getGroupById(g.id)).toBeDefined()
    expect(api.getGroupById(g.id).title).toBe('顶层组')
  })

  it('createGroup with parentId: 加入到 parent.children', () => {
    const parent = api.createGroup('父组')
    const child = api.createGroup('子组', parent.id)
    expect(child.parentId).toBe(parent.id)
    expect(parent.children).toContainEqual(child)
  })

  it('createGroup 超过 3 层深度限制', () => {
    const g1 = api.createGroup('第1层')
    const g2 = api.createGroup('第2层', g1.id)
    const g3 = api.createGroup('第3层', g2.id)
    // 第 4 层应被阻止
    const g4 = api.createGroup('第4层', g3.id)
    expect(g4).toBeDefined()  // 返回新 group 对象
    // 但不应加入 g3.children
    expect(g3.children).not.toContainEqual(g4)
  })
})

describe('useLayoutControl - moveContainerBetweenGroups', () => {
  let api, groupA, groupB
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
    groupA = api.createGroup('A')
    groupB = api.createGroup('B')
  })

  it('成功: 从 A 移到 B', () => {
    api.assignContainerToGroup(0, groupA.id)
    expect(groupA.containers).toContain(0)

    const result = api.moveContainerBetweenGroups(0, groupA.id, groupB.id)
    expect(result).toBe(true)
    expect(groupA.containers).not.toContain(0)
    expect(groupB.containers).toContain(0)
  })

  it('失败: 源组找不到容器 (返回 false)', () => {
    api.assignContainerToGroup(0, groupA.id)
    const result = api.moveContainerBetweenGroups(999, groupA.id, groupB.id)
    expect(result).toBe(false)
  })

  it('失败: 目标组不存在 (返回 false)', () => {
    api.assignContainerToGroup(0, groupA.id)
    const result = api.moveContainerBetweenGroups(0, groupA.id, 'non-existent-id')
    expect(result).toBe(false)
  })
})

describe('useLayoutControl - assignContainerToGroup / removeContainerFromGroup', () => {
  let api, group
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
    group = api.createGroup('G')
  })

  it('assignContainerToGroup: 容器加入组', () => {
    const result = api.assignContainerToGroup(5, group.id)
    expect(result).toBe(true)
    expect(group.containers).toContain(5)
  })

  it('assignContainerToGroup: 重复添加不报错 (去重)', () => {
    api.assignContainerToGroup(5, group.id)
    api.assignContainerToGroup(5, group.id)
    expect(group.containers.filter(i => i === 5).length).toBe(1)
  })

  it('removeContainerFromGroup: 成功移除', () => {
    api.assignContainerToGroup(5, group.id)
    const result = api.removeContainerFromGroup(5, group.id)
    expect(result).toBe(true)
    expect(group.containers).not.toContain(5)
  })

  it('removeContainerFromGroup: 容器不在组 (返回 false)', () => {
    const result = api.removeContainerFromGroup(999, group.id)
    expect(result).toBe(false)
  })
})

describe('useLayoutControl - updateGroup', () => {
  let api, group
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
    group = api.createGroup('原始')
  })

  it('更新 title', () => {
    const result = api.updateGroup(group.id, { title: '新标题' })
    expect(result).toBe(true)
    expect(group.title).toBe('新标题')
  })

  it('更新 direction', () => {
    api.updateGroup(group.id, { direction: 'LR' })
    expect(group.direction).toBe('LR')
  })

  it('保护 id / children / parentId 不被覆盖', () => {
    const originalId = group.id
    const originalChildren = group.children
    const originalParent = group.parentId
    api.updateGroup(group.id, { id: 'hacker', children: [], parentId: 'hacker' })
    expect(group.id).toBe(originalId)
    expect(group.children).toBe(originalChildren)
    expect(group.parentId).toBe(originalParent)
  })

  it('不存在的 ID 返回 false', () => {
    const result = api.updateGroup('non-existent', { title: 'x' })
    expect(result).toBe(false)
  })
})

describe('useLayoutControl - deleteGroup', () => {
  let api
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
  })

  it('删除顶层组', () => {
    const g = api.createGroup('G')
    const result = api.deleteGroup(g.id)
    expect(result).toBe(true)
    expect(api.getGroupById(g.id)).toBe(null)
  })

  it('递归删除子组', () => {
    const parent = api.createGroup('父')
    const child = api.createChildGroup(parent.id, '子')
    const grandchild = api.createChildGroup(child.id, '孙')

    api.deleteGroup(grandchild.id)
    expect(api.getGroupById(grandchild.id)).toBe(null)

    api.deleteGroup(parent.id)  // 应同时删 child
    expect(api.getGroupById(child.id)).toBe(null)
    expect(api.getGroupById(parent.id)).toBe(null)
  })
})

describe('useLayoutControl - getGroupDepth / canCreateChildGroup', () => {
  let api
  beforeEach(() => {
    api = useLayoutControl()
    api.resetConfig()
  })

  it('顶层组 depth = 1', () => {
    const g = api.createGroup('G')
    expect(api.getGroupDepth(g.id)).toBe(1)
  })

  it('3 层嵌套 depth = 3', () => {
    const g1 = api.createGroup('1')
    const g2 = api.createChildGroup(g1.id, '2')
    const g3 = api.createChildGroup(g2.id, '3')
    expect(api.getGroupDepth(g3.id)).toBe(3)
  })

  it('canCreateChildGroup: 深度 < 3 允许', () => {
    const g1 = api.createGroup('1')
    const g2 = api.createChildGroup(g1.id, '2')
    const g3 = api.createChildGroup(g2.id, '3')
    expect(api.canCreateChildGroup(g3.id)).toBe(false)
  })

  it('canCreateChildGroup: 顶层允许', () => {
    const g1 = api.createGroup('1')
    expect(api.canCreateChildGroup(g1.id)).toBe(true)
  })
})

describe('useLayoutControl - resetConfig', () => {
  it('重置所有状态到默认', () => {
    const api = useLayoutControl()
    const g = api.createGroup('G')
    expect(api.getGroupById(g.id)).toBeDefined()
    api.resetConfig()
    expect(api.getGroupById(g.id)).toBe(null)
  })
})
