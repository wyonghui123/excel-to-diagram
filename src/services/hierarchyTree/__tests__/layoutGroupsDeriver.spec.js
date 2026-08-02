import { describe, it, expect } from 'vitest'
import { deriveLayoutGroups } from '../layoutGroupsDeriver.js'

const containers = [
  { id: 'D_MKT', layer: 'DOMAIN', code: 'MKT', name: '营销云', children: [
    // nodeIds 来自投影器输出: 无前缀 code（SM 末端时叶子容器的 nodeIds = SM code）
    { id: 'SD_MKT-M', layer: 'SUB_DOMAIN', code: 'MKT-M', name: '营销中台', nodeIds: ['SM001'] },
  ] },
]

describe('deriveLayoutGroups', () => {
  it('容器树 → routeLayout 格式 groups（domain→children, 叶子 nodeIds→directNodes）', () => {
    const groups = deriveLayoutGroups(containers)
    expect(groups).toHaveLength(1)
    expect(groups[0].groupType).toBe('domain')
    expect(groups[0].elementCode).toBe('MKT')
    expect(groups[0].children).toHaveLength(1)
    const sd = groups[0].children[0]
    expect(sd.groupType).toBe('subDomain')
    // SM 末端以 directNodes 直挂子领域 subgraph, 不再包 SM 容器 (消除重复容器)
    expect(sd.directNodes).toEqual(['SM001'])
    expect(sd.containers).toEqual([])
  })
})
