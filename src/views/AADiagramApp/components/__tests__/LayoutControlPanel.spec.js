import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LayoutControlPanel from '../LayoutControlPanel.vue'
import LayoutGroupNode from '../LayoutGroupNode.vue'
import { groupExpansionState } from '@/composables/useGroupExpansion'

describe('LayoutControlPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // [FIX 2026-08-04] 重置模块级展开状态，避免"全部展开/收起"测试污染后续用例
    //   （toggle 测试点击后 mode 残留为 'collapse'，导致后续 LayoutGroupNode 的
    //   immediate watch 把叶子容器折叠 → 断言叶子数失败）
    groupExpansionState.mode = 'none'
    groupExpansionState.version = 0
  })

  const modelValue = {
    enabled: true, groups: [
      { id: 'g1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
        containers: [], children: [] }
    ], engine: 'elk', preserveOrder: true
  }

  // [LEVEL 2026-08-06] 展开层级下拉: 面板使用 el-dropdown, 测试中桩掉以稳定渲染
  const dropdownStubs = {
    'el-dropdown': { template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>', props: ['trigger'], emits: ['command'] },
    'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
    'el-dropdown-item': { template: '<div class="el-dropdown-item" @click="$emit(\'command\', command)"><slot /></div>', props: ['command', 'disabled'], emits: ['command'] },
    'el-icon': { template: '<i class="el-icon"><slot /></i>' }
  }

  const mountPanel = (props = {}) => {
    return mount(LayoutControlPanel, {
      props: { modelValue, containers: [], domainProducts: [], chartType: 'businessObject', ...props },
      global: { stubs: dropdownStubs }
    })
  }

  it('渲染树节点', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('领域A')
    expect(wrapper.find('.lgn-node').exists()).toBe(true)
  })

  it('渲染展开层级选择器 (LEVEL 2026-08-06)', async () => {
    const wrapper = mountPanel()
    expect(wrapper.find('.lcp-toolbar').exists()).toBe(true)
    // 触发按钮 + 4 个层级选项
    expect(wrapper.text()).toContain('展开层级')
    expect(wrapper.text()).toContain('展开到领域')
    expect(wrapper.text()).toContain('展开到子领域')
    expect(wrapper.text()).toContain('展开到服务模块')
    expect(wrapper.text()).toContain('展开到业务对象')
    expect(wrapper.text()).toContain('新增')
  })

  it('展开到服务模块: 折叠 BO 叶容器 (LEVEL 2026-08-06)', async () => {
    const levelModel = {
      enabled: true, groups: [
        { id: 'd1', title: '领域A', groupType: 'domain', enabled: true, visible: true, containers: [], children: [
          { id: 'sd1', title: '子领域1', groupType: 'subDomain', enabled: true, visible: true, containers: [], children: [
            { id: 'sm1', title: '服务模块1', groupType: 'serviceModule', enabled: true, visible: true,
              containers: [{ id: 'bo1', name: '业务对象1' }], children: [] }
          ] }
        ] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: levelModel })
    wrapper.vm.handleExpandToLevel('serviceModule')
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    const domain = updated.groups[0]
    const sub = domain.children[0]
    const sm = sub.children[0]
    expect(domain.collapsed).toBe(false)      // 领域展开 (level 0 < 2)
    expect(sub.collapsed).toBe(false)         // 子领域展开 (level 1 < 2)
    expect(sm.collapsed).toBe(true)           // 服务模块折叠 (level 2 >= 2)
    expect(sm.containers[0].collapsed).toBe(true) // BO 叶折叠
  })

  it('展开到领域: 更深层级全部折叠 (LEVEL 2026-08-06)', async () => {
    const levelModel = {
      enabled: true, groups: [
        { id: 'd1', title: '领域A', groupType: 'domain', enabled: true, visible: true, containers: [], children: [
          { id: 'sd1', title: '子领域1', groupType: 'subDomain', enabled: true, visible: true, containers: [], children: [
            { id: 'sm1', title: '服务模块1', groupType: 'serviceModule', enabled: true, visible: true,
              containers: [{ id: 'bo1', name: '业务对象1' }], children: [] }
          ] }
        ] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: levelModel })
    wrapper.vm.handleExpandToLevel('domain')
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    const updated = emitted[emitted.length - 1][0]
    const domain = updated.groups[0]
    const sub = domain.children[0]
    const sm = sub.children[0]
    // [LEVEL 2026-08-06] "展开到领域" = 只展示领域: 领域折叠为聚合节点, 子领域及以下全部隐藏
    expect(domain.collapsed).toBe(true)   // 领域折叠 (level 0 >= 0)
    expect(sub.collapsed).toBe(true)      // 子领域折叠 (level 1 >= 0)
    expect(sm.collapsed).toBe(true)       // 服务模块折叠 (level 2 >= 0)
    expect(sm.containers[0].collapsed).toBe(true) // BO 叶折叠 (level 3 >= 0)
  })

  it('分组下的业务对象节点作为叶子节点渲染', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'sm1', title: '服务模块A', groupType: 'serviceModule', enabled: true, visible: true,
          containers: [{ id: 'bo1', name: '业务对象1' }, { id: 'bo2', name: '业务对象2' }],
          children: [] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: model })
    // [ADV 2026-08-07] 业务对象叶子默认隐藏, 需开启"高级设置"开关才渲染
    wrapper.vm.showAdvancedSettings = true
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.lgn-container-leaf').length).toBe(2)
    expect(wrapper.text()).toContain('业务对象1')
    expect(wrapper.text()).toContain('业务对象2')
  })

  it('LEAF 叶子节点提供可见/禁用开关 (update-container)', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'sm1', title: '服务模块A', groupType: 'serviceModule', enabled: true, visible: true,
          containers: [{ id: 'bo1', name: '业务对象1', enabled: true, visible: true }],
          children: [] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: model })
    // [ADV 2026-08-07] 业务对象叶子默认隐藏, 需开启"高级设置"开关才渲染
    wrapper.vm.showAdvancedSettings = true
    await wrapper.vm.$nextTick()
    // 叶子节点有启用/可见两个开关按钮 (禁用按钮需高级设置打开才展示)
    expect(wrapper.findAll('.lgn-leaf-toggle').length).toBe(2)
    // 触发禁用 -> 更新容器 enabled
    wrapper.findComponent(LayoutGroupNode).vm.$emit('update-container', {
      groupId: 'sm1', containerId: 'bo1', updates: { enabled: false }
    })
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    expect(updated.groups[0].containers[0].enabled).toBe(false)
  })

  it('拖拽分组到另一分组下（move-group）', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'g1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
          containers: [], children: [] },
        { id: 'g2', title: '领域B', groupType: 'domain', enabled: true, visible: true,
          containers: [], children: [] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: model })
    const nodes = wrapper.findAllComponents(LayoutGroupNode)
    // 触发 g2 拖拽到 g1 下（move-group）
    nodes[0].vm.$emit('move-group', { sourceGroupId: 'g2', targetGroupId: 'g1' })
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    expect(updated.groups.length).toBe(1)
    expect(updated.groups[0].children[0].id).toBe('g2')
  })

  it('LEAF 拖拽叶子节点到另一分组 (remove + assign)', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'g1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
          containers: [{ id: 'c1', name: '对象A', nodes: ['c1'] }], children: [] },
        { id: 'g2', title: '领域B', groupType: 'domain', enabled: true, visible: true,
          containers: [], children: [] }
      ], engine: 'elk', preserveOrder: true
    }
    const containers = [{ id: 'c1', name: '对象A', nodes: ['c1'] }]
    const wrapper = mountPanel({ modelValue: model, containers })
    // 从 g1 移除容器 c1, 再分配到 g2
    wrapper.findComponent(LayoutGroupNode).vm.$emit('remove-container', { groupId: 'g1', containerId: 'c1' })
    await wrapper.vm.$nextTick()
    wrapper.findComponent(LayoutGroupNode).vm.$emit('assign-container', {
      groupId: 'g2', container: { id: 'c1', name: '对象A', nodes: ['c1'] }
    })
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    // g1 不再持有 c1, g2 持有 c1
    expect(updated.groups[0].containers.length).toBe(0)
    expect(updated.groups[1].containers.length).toBe(1)
  })

  it('REORDER 同级分组拖拽重排 (reorder-groups 嵌套层级)', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'd1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
          containers: [], children: [
            { id: 'sd1', title: '子领域1', groupType: 'subDomain', parentId: 'd1', containers: [], children: [] },
            { id: 'sd2', title: '子领域2', groupType: 'subDomain', parentId: 'd1', containers: [], children: [] }
          ] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: model })
    // 触发 sd2 重排到 sd1 前（同级 reorder-groups）
    wrapper.findComponent(LayoutGroupNode).vm.$emit('reorder-groups', {
      sourceGroupId: 'sd2', targetGroupId: 'sd1', parentId: 'd1'
    })
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    expect(updated.groups[0].children.map(c => c.id)).toEqual(['sd2', 'sd1'])
  })

  it('REORDER 群组内叶子容器重排 (reorder-containers)', async () => {
    const model = {
      enabled: true, groups: [
        { id: 'sm1', title: '服务模块A', groupType: 'serviceModule', enabled: true, visible: true,
          containers: [{ id: 'bo1', name: '对象1' }, { id: 'bo2', name: '对象2' }],
          children: [] }
      ], engine: 'elk', preserveOrder: true
    }
    const wrapper = mountPanel({ modelValue: model })
    // 触发 bo2 重排到 bo1 前
    wrapper.findComponent(LayoutGroupNode).vm.$emit('reorder-containers', {
      groupId: 'sm1', sourceContainerId: 'bo2', targetContainerId: 'bo1'
    })
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const updated = emitted[emitted.length - 1][0]
    expect(updated.groups[0].containers.map(c => c.id)).toEqual(['bo2', 'bo1'])
  })
})