import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LayoutGroupNode from '../LayoutGroupNode.vue'

describe('LayoutGroupNode', () => {
  function makeGroup(overrides = {}) {
    return {
      id: 'g1', title: '领域A', groupType: 'domain', direction: 'TB',
      visible: true, enabled: true, containers: [], children: [],
      ...overrides
    }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('渲染标题与类型图标', () => {
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [] } })
    expect(wrapper.text()).toContain('领域A')
  })

  it('点击启用切换 emit update', async () => {
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [] } })
    const eye = wrapper.find('.lgn-eye')
    await eye.trigger('click')
    expect(wrapper.emitted('update')?.[0]?.[0]).toMatchObject({ id: 'g1', updates: { enabled: false } })
  })

  it('有子节点时展开/收起', async () => {
    const group = makeGroup({ children: [makeGroup({ id: 'g2', title: '子领域' })] })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    expect(wrapper.findAll('.lgn-node').length).toBe(2) // 根(depth0)默认展开, 含子节点
    await wrapper.find('.lgn-caret').trigger('click') // 收起
    expect(wrapper.findAll('.lgn-node').length).toBe(1)
    await wrapper.find('.lgn-caret').trigger('click') // 再展开
    expect(wrapper.findAll('.lgn-node').length).toBe(2)
  })

  it('删除 emit delete', async () => {
    const group = makeGroup({ groupType: 'custom' })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    await wrapper.find('.lgn-delete').trigger('click')
    expect(wrapper.emitted('delete')?.[0]?.[0]).toBe('g1')
  })
})