/**
 * layoutMergeLogic.spec - 布局面板编辑 → 渲染树合并逻辑的单元测试
 *
 * 覆盖两类合并（EmbeddedChartView.layoutControlConfig 的步骤 2/3）：
 *   - applyContainerMembership   : 拖拽移动后重建叶子归属（directNodes / containers 双形态）
 *   - applyGroupTitlesAndOrder   : 重命名标题 + 面板顺序重排 + 群组内容器重排
 *
 * [为什么补这些测试] 合并逻辑是最复杂、最易反复回归的地方（刚修过 ELK 子分组场景），
 *   只能靠 E2E 断言"容器是否包住子节点"太慢。这里用纯函数 + 结构断言，毫秒级精确回归。
 */
import { describe, it, expect } from 'vitest'
import { applyContainerMembership, applyGroupTitlesAndOrder } from '../layoutMergeLogic.js'

describe('applyContainerMembership', () => {
  it('directNodes 分组: 用面板容器 code 重建叶子归属（拖走的叶子消失）', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', directNodes: ['SM1', 'SM2', 'SM3'], containers: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [], children: [
        { elementCode: 'SD1', groupType: 'subDomain', containers: [{ elementCode: 'SM1' }, { elementCode: 'SM3' }], children: [] }
      ] }
    ]
    applyContainerMembership(merged, user)
    expect(merged[0].children[0].directNodes).toEqual(['SM1', 'SM3'])
    expect(merged[0].children[0].containers).toEqual([])
  })

  it('containers 分组: 用面板容器对象（含节点数据）保持包裹子节点', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', containers: [
        { id: 'BO1', name: 'a' }, { id: 'BO2', name: 'b' }
      ], children: [] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [
        { id: 'BO2', name: 'b2', nodes: ['BO2'] }, { id: 'BO1', name: 'a1', nodes: ['BO1'] }
      ], children: [] }
    ]
    applyContainerMembership(merged, user)
    // 用面板容器对象（含 nodes 数据），且顺序追随面板
    expect(merged[0].containers.map(c => c.id)).toEqual(['BO2', 'BO1'])
    expect(merged[0].containers[0].nodes).toEqual(['BO2'])
  })

  it('ELK 子分组场景: 面板 containers 空但有 children → 不清空合并树 directNodes（容器仍包住子节点）', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', directNodes: ['SM1', 'SM2'], containers: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [], children: [
        { elementCode: 'SD1', groupType: 'subDomain', containers: [], children: [
          { elementCode: 'ELK_ext', containers: [{ elementCode: 'SM1' }], children: [] },
          { elementCode: 'ELK_int', containers: [{ elementCode: 'SM2' }], children: [] }
        ] }
      ] }
    ]
    applyContainerMembership(merged, user)
    // 关键回归: 不能因 SD1.containers 为空就清掉 directNodes
    expect(merged[0].children[0].directNodes).toEqual(['SM1', 'SM2'])
  })

  it('拖走最后叶子: 面板分组既无叶子也无子分组 → 清空合并树叶子', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', directNodes: ['SM1'], containers: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [], children: [
        { elementCode: 'SD1', groupType: 'subDomain', containers: [], children: [] }
      ] }
    ]
    applyContainerMembership(merged, user)
    expect(merged[0].children[0].directNodes).toEqual([])
  })

  it('拖拽移动到新分组: 叶子出现在新分组, 且从旧分组移除', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', directNodes: ['SM1', 'SM2'], containers: [] },
        { elementCode: 'SD2', groupType: 'subDomain', directNodes: ['SM3'], containers: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [], children: [
        { elementCode: 'SD1', groupType: 'subDomain', containers: [{ elementCode: 'SM1' }], children: [] },
        { elementCode: 'SD2', groupType: 'subDomain', containers: [{ elementCode: 'SM2' }, { elementCode: 'SM3' }], children: [] }
      ] }
    ]
    applyContainerMembership(merged, user)
    const [sd1, sd2] = merged[0].children
    expect(sd1.directNodes).toEqual(['SM1'])
    expect(sd2.directNodes).toEqual(['SM2', 'SM3'])
  })

  it('userGroups 为空时不做任何修改', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', directNodes: ['SM1'], containers: [] }
      ] }
    ]
    const snapshot = JSON.parse(JSON.stringify(merged))
    applyContainerMembership(merged, null)
    applyContainerMembership(merged, [])
    expect(merged).toEqual(snapshot)
  })
})

describe('applyGroupTitlesAndOrder', () => {
  it('重命名标题 + 标记 _userRenamed', () => {
    const merged = [
      { elementCode: 'D1', title: '旧域名', groupType: 'domain', children: [
        { elementCode: 'SD1', title: '旧子域', groupType: 'subDomain', containers: [], children: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', title: '新域名', groupType: 'domain', children: [
        { elementCode: 'SD1', title: '新子域', groupType: 'subDomain', containers: [], children: [] }
      ] }
    ]
    applyGroupTitlesAndOrder(merged, user)
    expect(merged[0].title).toBe('新域名')
    expect(merged[0]._userRenamed).toBe(true)
    expect(merged[0].children[0].title).toBe('新子域')
    expect(merged[0].children[0]._userRenamed).toBe(true)
  })

  it('按面板顺序重排当前层 children', () => {
    const merged = [
      { elementCode: 'D1', title: 'd', groupType: 'domain', children: [
        { elementCode: 'SD1', groupType: 'subDomain', containers: [], children: [] },
        { elementCode: 'SD2', groupType: 'subDomain', containers: [], children: [] }
      ] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', children: [
        { elementCode: 'SD2', groupType: 'subDomain', containers: [], children: [] },
        { elementCode: 'SD1', groupType: 'subDomain', containers: [], children: [] }
      ] }
    ]
    applyGroupTitlesAndOrder(merged, user)
    expect(merged[0].children.map(c => c.elementCode)).toEqual(['SD2', 'SD1'])
  })

  it('群组内叶子容器顺序重排（面板拖拽重排容器）', () => {
    const merged = [
      { elementCode: 'D1', groupType: 'domain', containers: [
        { id: 'BO1', name: 'B1' }, { id: 'BO2', name: 'B2' }
      ], children: [] }
    ]
    const user = [
      { elementCode: 'D1', groupType: 'domain', containers: [
        { id: 'BO2', name: 'B2' }, { id: 'BO1', name: 'B1' }
      ], children: [] }
    ]
    applyGroupTitlesAndOrder(merged, user)
    expect(merged[0].containers.map(c => c.id)).toEqual(['BO2', 'BO1'])
  })

  it('userGroups 为空时不做任何修改', () => {
    const merged = [{ elementCode: 'D1', title: 't', groupType: 'domain', children: [] }]
    const snapshot = JSON.parse(JSON.stringify(merged))
    applyGroupTitlesAndOrder(merged, null)
    applyGroupTitlesAndOrder(merged, [])
    expect(merged).toEqual(snapshot)
  })
})