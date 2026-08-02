import { describe, it, expect } from 'vitest'
import { deriveLayoutGroups } from '../layoutGroupsDeriver.js'

const containers = [
  { id: 'D_MKT', layer: 'DOMAIN', code: 'MKT', name: '营销云', children: [
    // nodeIds 来自投影器输出: 无前缀 code（SM 末端时叶子容器的 nodeIds = SM code）
    { id: 'SD_MKT-M', layer: 'SUB_DOMAIN', code: 'MKT-M', name: '营销中台', nodeIds: ['SM001'] },
  ] },
]

describe('deriveLayoutGroups', () => {
  it('容器树 → LayoutControlPanel 格式 groups（domain→children, SM 终端→containers）', () => {
    const groups = deriveLayoutGroups(containers)
    expect(groups).toHaveLength(1)
    expect(groups[0].groupType).toBe('domain')
    expect(groups[0].elementCode).toBe('MKT')
    expect(groups[0].children).toHaveLength(1)
    const sd = groups[0].children[0]
    expect(sd.groupType).toBe('subDomain')
    expect(sd.containers[0].groupType).toBe('serviceModule')
    expect(sd.containers[0].elementCode).toBe('SM001')   // elementCode 无前缀
    expect(sd.containers[0].id).toBe('SM_SM001')         // SM 终端 id 带前缀（createGroupId）
  })
})
