import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import NavigationSourceInfo from '../NavigationSourceInfo.vue'


describe('NavigationSourceInfo', () => {
  function createWrapper(props = {}) {
    return mount(NavigationSourceInfo, {
      props: {
        sourceType: '',
        sourceIds: [],
        sourceNames: [],
        associationName: '',
        associationLabel: '',
        ...props,
      },
    })
  }

  it('TC-COMP-SRC-001: 有来源信息时显示信息栏', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1, 2],
      sourceNames: ['Admin', 'Editor'],
      associationName: 'users',
      associationLabel: '用户',
    })

    expect(wrapper.find('.nav-source-info').exists()).toBe(true)
    expect(wrapper.text()).toContain('Admin')
    expect(wrapper.text()).toContain('Editor')
    expect(wrapper.text()).toContain('用户')
  })

  it('TC-COMP-SRC-002: 无来源信息时不渲染', () => {
    const wrapper = createWrapper()

    expect(wrapper.find('.nav-source-info').exists()).toBe(false)
  })

  it('TC-COMP-SRC-003: 缺少sourceType时不渲染', () => {
    const wrapper = createWrapper({
      sourceIds: [1],
      sourceNames: ['Test'],
      associationName: 'users',
    })

    expect(wrapper.find('.nav-source-info').exists()).toBe(false)
  })

  it('TC-COMP-SRC-004: 空sourceIds时不渲染', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [],
      sourceNames: [],
      associationName: 'users',
    })

    expect(wrapper.find('.nav-source-info').exists()).toBe(false)
  })

  it('TC-COMP-SRC-005: 显示多个对象数量标签', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1, 2, 3],
      sourceNames: ['R1', 'R2', 'R3'],
      associationName: 'users',
      associationLabel: '关联用户',
    })

    expect(wrapper.find('.nav-source-info__tag').exists()).toBe(true)
    expect(wrapper.text()).toContain('3 个对象')
  })

  it('TC-COMP-SRC-006: 单个对象不显示数量标签', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1],
      sourceNames: ['Admin'],
      associationName: 'users',
    })

    expect(wrapper.find('.nav-source-info__tag').exists()).toBe(false)
  })

  it('TC-COMP-SRC-007: 点击返回按钮触发navigate-back事件', async () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1],
      sourceNames: ['Admin'],
      associationName: 'users',
    })

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('navigate-back')).toBeTruthy()
  })

  it('TC-COMP-SRC-008: 返回按钮文本包含返回来源', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1],
      sourceNames: ['Admin'],
      associationName: 'users',
    })

    const btn = wrapper.find('button')
    expect(btn.text()).toContain('返回来源')
  })

  it('TC-COMP-SRC-009: 无sourceNames时使用ID回退显示', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [42],
      sourceNames: [],
      associationName: 'users',
    })

    expect(wrapper.text()).toContain('#42')
  })

  it('TC-COMP-SRC-010: 使用associationLabel作为显示名称', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1],
      sourceNames: ['RoleA'],
      associationName: 'users_assoc',
      associationLabel: '关联用户列表',
    })

    expect(wrapper.text()).toContain('关联用户列表')
  })

  it('TC-COMP-SRC-011: 无associationLabel时使用associationName', () => {
    const wrapper = createWrapper({
      sourceType: 'role',
      sourceIds: [1],
      sourceNames: ['RoleA'],
      associationName: 'my_users',
    })

    expect(wrapper.text()).toContain('my_users')
  })
})
