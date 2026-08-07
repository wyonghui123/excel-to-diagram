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
    // [ADV 2026-08-07] 启用/禁用按钮默认隐藏, 需打开"高级设置"才展示
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [], showAdvancedSettings: true } })
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

  it('LEAF 叶子容器提供启用/可见开关并 emit update-container', async () => {
    const group = makeGroup({
      containers: [{ id: 'c1', name: '业务对象1', enabled: true, visible: true }]
    })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [], showBusinessObjects: true, showAdvancedSettings: true } })
    // 叶子节点有启用/可见两个开关 (禁用按钮需高级设置打开才展示)
    const toggles = wrapper.findAll('.lgn-leaf-toggle')
    expect(toggles.length).toBe(2)
    // 点击启用开关 -> 禁用 (enabled: false)
    await toggles[0].trigger('click')
    expect(wrapper.emitted('update-container')?.[0]?.[0]).toMatchObject({
      groupId: 'g1', containerId: 'c1', updates: { enabled: false }
    })
    // 点击可见开关 -> 隐藏边框 (visible: false)
    await toggles[1].trigger('click')
    expect(wrapper.emitted('update-container')?.[1]?.[0]).toMatchObject({
      groupId: 'g1', containerId: 'c1', updates: { visible: false }
    })
  })

  it('LEAF 叶子容器可拖拽 (dragstart 携带 container 数据)', async () => {
    const group = makeGroup({
      containers: [{ id: 'c1', name: '业务对象1', enabled: true, visible: true }]
    })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [], showBusinessObjects: true } })
    const leaf = wrapper.find('.lgn-container-leaf')
    expect(leaf.attributes('draggable')).toBe('true')
    const data = {}
    data.setData = (k, v) => { data[k] = v }
    await leaf.trigger('dragstart', { dataTransfer: data })
    const payload = JSON.parse(data['text/plain'])
    expect(payload.type).toBe('container')
    expect(payload.container.id).toBe('c1')
  })

  it('[FOCUS] 双击标题文字仅进入编辑, 不触发 request-chart-focus (.stop 隔离)', async () => {
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [] } })
    await wrapper.find('.lgn-title-text').trigger('dblclick')
    expect(wrapper.emitted('request-chart-focus')).toBeUndefined()
    expect(wrapper.vm.isEditingTitle).toBe(true)
  })

  it('[FOCUS] 双击分组行非文字区域 → request-chart-focus (container)', async () => {
    const group = makeGroup({ elementCode: 'DOM1' })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    await wrapper.find('.lgn-row').trigger('dblclick')
    expect(wrapper.emitted('request-chart-focus')?.[0]?.[0]).toEqual({ type: 'container', id: 'DOM1' })
  })

  it('[FOCUS] 双击叶子容器 → request-chart-focus (node)', async () => {
    const group = makeGroup({
      containers: [{ id: 'c1', name: '业务对象1', elementCode: 'BO1', enabled: true, visible: true }]
    })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    await wrapper.find('.lgn-container-leaf').trigger('dblclick')
    expect(wrapper.emitted('request-chart-focus')?.[0]?.[0]).toEqual({ type: 'node', id: 'BO1' })
  })

  // [FIX 2026-08-05] 服务模块图叶子(服务模块)也是 g.node, 必须发 type:'node'。
  //   之前发 type:'container' → highlightTargetElement 用 [data-container-code]/.subgraph/.cluster
  //   匹配不到, 导致服务模块图双击叶子无高亮 (E2E C07 失败根因)。
  it('[FOCUS] 双击服务模块叶子 → request-chart-focus (node, 非 container)', async () => {
    const group = makeGroup({
      containers: [{
        id: 'SM_G_SM1', name: '服务模块1', type: 'serviceModule', groupType: 'serviceModule',
        elementCode: 'SM1', enabled: true, visible: true,
        elementRef: { type: 'serviceModule', code: 'SM1', name: '服务模块1' }
      }]
    })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    await wrapper.find('.lgn-container-leaf').trigger('dblclick')
    const emitted = wrapper.emitted('request-chart-focus')
    expect(emitted).toBeTruthy()
    // @vue/test-utils 的 dblclick 不传 event, e.target.closest 为 null → 不跳过
    expect(emitted[0][0]).toEqual({ type: 'node', id: 'SM1' })
  })
})