import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LayoutControlPanel from '../LayoutControlPanel.vue'

describe('LayoutControlPanel', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  const modelValue = {
    enabled: true, groups: [
      { id: 'g1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
        containers: [], children: [] }
    ], engine: 'elk', preserveOrder: true
  }

  it('渲染树节点', () => {
    const wrapper = mount(LayoutControlPanel, {
      props: { modelValue, containers: [], domainProducts: [], chartType: 'businessObject' }
    })
    expect(wrapper.text()).toContain('领域A')
    expect(wrapper.find('.lgn-node').exists()).toBe(true)
  })

  it('搜索过滤节点', async () => {
    const wrapper = mount(LayoutControlPanel, {
      props: { modelValue, containers: [], domainProducts: [], chartType: 'businessObject' }
    })
    const input = wrapper.find('.lcp-search-input input')
    await input.setValue('不存在')
    expect(wrapper.findAll('.lgn-node').length).toBe(0)
  })
})