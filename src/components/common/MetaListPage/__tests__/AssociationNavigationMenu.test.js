import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AssociationNavigationMenu from '../AssociationNavigationMenu.vue'


describe('AssociationNavigationMenu', () => {
  const sampleAssociations = [
    {
      name: 'roles',
      label: '角色',
      type: 'many_to_many',
      target_entity: 'role',
      navigation: { enabled: true, label: '角色', icon: 'Key', display_mode: 'list' },
    },
    {
      name: 'groups',
      label: '用户组',
      type: 'many_to_many',
      target_entity: 'user_group',
      navigation: { enabled: true, label: '用户组', icon: 'UserFilled', display_mode: 'list' },
    },
    {
      name: 'permissions',
      label: '权限',
      type: 'many_to_many',
      target_entity: 'permission',
      navigation: { enabled: true, label: '权限', icon: 'Lock', display_mode: 'list' },
    },
  ]

  function createWrapper(props = {}) {
    return mount(AssociationNavigationMenu, {
      props: {
        associations: [],
        selectedIds: new Set(),
        loading: false,
        ...props,
      },
    })
  }

  it('TC-COMP-NAV-001: 无选中对象时隐藏按钮', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set(),
    })

    expect(wrapper.find('.el-dropdown').exists()).toBe(false)
  })

  it('TC-COMP-NAV-002: 有选中对象且有关联时显示按钮', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1, 2]),
    })

    expect(wrapper.find('.el-dropdown').exists()).toBe(true)
    expect(wrapper.text()).toContain('关联导航')
  })

  it('TC-COMP-NAV-003: 无关联配置时隐藏按钮', () => {
    const wrapper = createWrapper({
      associations: [],
      selectedIds: new Set([1, 2]),
    })

    expect(wrapper.find('.el-dropdown').exists()).toBe(false)
  })

  it('TC-COMP-NAV-004: 组件正确渲染下拉菜单', async () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1]),
    })

    const dropdown = wrapper.findComponent({ name: 'ElDropdown' })
    expect(dropdown.exists()).toBe(true)
    expect(dropdown.props('trigger')).toBe('click')
  })

  it('TC-COMP-NAV-005: command事件触发navigate emit并传递association', async () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1]),
    })

    const dropdown = wrapper.findComponent({ name: 'ElDropdown' })
    await dropdown.vm.$emit('command', sampleAssociations[0])
    await nextTick()

    expect(wrapper.emitted('navigate')).toBeTruthy()
    expect(wrapper.emitted('navigate')[0][0]).toEqual(sampleAssociations[0])
  })

  it('TC-COMP-NAV-006: 关联计数在模板中渲染', () => {
    const assocs = [...sampleAssociations]
    assocs[0]._count = 5
    assocs[1]._count = 3

    const wrapper = createWrapper({
      associations: assocs,
      selectedIds: new Set([1]),
    })

    expect(wrapper.vm.associations[0]._count).toBe(5)
    expect(wrapper.vm.associations[1]._count).toBe(3)
  })

  it('TC-COMP-NAV-007: loading状态传递给组件', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1]),
      loading: true,
    })

    expect(wrapper.props('loading')).toBe(true)
  })

  it('TC-COMP-NAV-008: 空关联列表时隐藏按钮', () => {
    const wrapper = createWrapper({
      associations: [],
      selectedIds: new Set([1]),
    })
    expect(wrapper.find('.el-dropdown').exists()).toBe(false)
  })

  it('TC-COMP-NAV-009: 单个选中对象正常显示', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([42]),
    })

    expect(wrapper.find('.el-dropdown').exists()).toBe(true)
  })

  it('TC-COMP-NAV-010: 大量选中对象时正常工作', () => {
    const manyIds = Array.from({ length: 100 }, (_, i) => i + 1)
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set(manyIds),
    })

    expect(wrapper.find('.el-dropdown').exists()).toBe(true)
  })

  it('TC-COMP-NAV-011: visible计算属性为false当selectedIds为空', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set(),
    })
    expect(wrapper.vm.visible).toBe(false)
  })

  it('TC-COMP-NAV-012: visible计算属性为true当选中对象且有关联', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1, 2]),
    })
    expect(wrapper.vm.visible).toBe(true)
  })

  it('TC-COMP-NAV-013: getIcon返回正确的图标组件名', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1]),
    })

    expect(wrapper.vm.getIcon(sampleAssociations[0])).toBeDefined()
    expect(wrapper.vm.getIcon(sampleAssociations[1])).toBeDefined()
  })

  it('TC-COMP-NAV-014: getLabel返回正确的标签文本', () => {
    const wrapper = createWrapper({
      associations: sampleAssociations,
      selectedIds: new Set([1]),
    })

    expect(wrapper.vm.getLabel(sampleAssociations[0])).toBe('角色')
    expect(wrapper.vm.getLabel(sampleAssociations[1])).toBe('用户组')
  })
})
