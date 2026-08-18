import { describe, it, expect } from 'vitest'
import { decideEntryState } from '../scaleGuardEntry'
import { expandGroupsToLevel } from '@/services/expandLevel'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }
const groups = [{ id: 'd1', groupType: 'domain', collapsed: false, directNodes: [], children: [], containers: [] }]

describe('scaleGuard entry', () => {
  it('decideEntryState: 返回 {level, counts}', () => {
    const r = decideEntryState({ nodes: 500, relations: 700 }, cfg)
    expect(r.level).toBe('hard')
    expect(r.counts.relations).toBe(700)
    expect(decideEntryState({ nodes: 50, relations: 100 }, cfg).level).toBe('ok')
  })
  it('折叠到服务模块层动作 = expandGroupsToLevel(groups, serviceModule) 可执行', () => {
    const r = expandGroupsToLevel(groups, 'serviceModule')
    expect(typeof r.collapsedCount).toBe('number')
  })
})
