/**
 * AssociationCell.spec.js - 关联单元格组件测试
 *
 * 测试核心功能：
 * 1. count 模式 - 徽章显示和链接点击
 * 2. tags 模式 - 标签渲染和 maxTags 截断
 * 3. names 模式 - 逗号分隔显示
 * 4. 空数据时显示"未分配"
 * 5. handleClick/handleItemClick emit navigate 事件
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AssociationCell from '@/components/bo/AssociationCell.vue'

const createWrapper = (props = {}) => {
  return mount(AssociationCell, {
    props: {
      row: { id: 1 },
      column: { prop: 'roles', label: '角色' },
      ...props,
    },
    global: {
      stubs: {
        'el-link': {
          template: '<a class="el-link" @click="$emit(\'click\')"><slot /></a>',
          props: ['type', 'underline'],
        },
        'el-badge': {
          template: '<span class="el-badge"><slot /><sup class="el-badge__content">{{ value }}</sup></span>',
          props: ['value'],
        },
        'el-tag': {
          template: '<span class="el-tag" @click="$emit(\'click\')"><slot /></span>',
          props: ['type', 'size'],
        },
      },
    },
  })
}

describe('AssociationCell', () => {
  describe('count mode', () => {
    it('shows badge with count when count > 0', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 5 },
        column: { prop: 'roles', displayMode: 'count' },
      })
      expect(wrapper.find('.el-badge').exists()).toBe(true)
      expect(wrapper.find('.association-label').exists()).toBe(true)
    })

    it('shows empty text when count is 0', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 0 },
        column: { prop: 'roles', displayMode: 'count' },
      })
      expect(wrapper.find('.association-empty').exists()).toBe(true)
      expect(wrapper.find('.association-empty').text()).toBe('未分配')
    })

    it('emits navigate on click when count > 0', async () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 3 },
        column: {
          prop: 'roles',
          displayMode: 'count',
          navigateTo: { objectType: 'user', filterField: 'user_id', title: '角色' },
        },
      })
      await wrapper.find('.el-link').trigger('click')
      expect(wrapper.emitted('navigate')).toBeTruthy()
      expect(wrapper.emitted('navigate')[0][0].objectType).toBe('user')
    })

    it('does not emit navigate without navigateTo config', async () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 3 },
        column: { prop: 'roles', displayMode: 'count' },
      })
      await wrapper.find('.el-link').trigger('click')
      expect(wrapper.emitted('navigate')).toBeFalsy()
    })

    it('falls back to items.length when no count field', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }] },
        column: { prop: 'roles', displayMode: 'count' },
      })
      expect(wrapper.vm.count).toBe(2)
    })
  })

  describe('tags mode', () => {
    it('renders tags for items', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }] },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.find('.association-tags').exists()).toBe(true)
      const tags = wrapper.findAll('.el-tag')
      expect(tags.length).toBe(2)
    })

    it('truncates tags with maxTags and shows more link', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [
          { id: 1, name: 'admin' },
          { id: 2, name: 'user' },
          { id: 3, name: 'editor' },
        ]},
        column: { prop: 'roles', displayMode: 'tags', maxTags: 2 },
      })
      const tags = wrapper.findAll('.el-tag')
      expect(tags.length).toBe(2)
      expect(wrapper.find('.more-link').exists()).toBe(true)
      expect(wrapper.find('.more-link').text()).toBe('+1')
    })

    it('shows empty text when no items', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [] },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.find('.association-empty').exists()).toBe(true)
    })

    it('emits navigate on tag click', async () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, name: 'admin' }] },
        column: {
          prop: 'roles',
          displayMode: 'tags',
          navigateTo: { objectType: 'role', filterField: 'user_id' },
        },
      })
      await wrapper.find('.el-tag').trigger('click')
      expect(wrapper.emitted('navigate')).toBeTruthy()
      expect(wrapper.emitted('navigate')[0][0].targetId).toBe(1)
    })

    it('displays name, display_name, code, or id', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, display_name: '管理员' }] },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.find('.el-tag').text()).toBe('管理员')
    })

    it('defaults maxTags to 2', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, name: 'a' }, { id: 2, name: 'b' }, { id: 3, name: 'c' }] },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.vm.maxTags).toBe(2)
    })
  })

  describe('names mode', () => {
    it('renders comma-separated names', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }] },
        column: { prop: 'roles', displayMode: 'names' },
      })
      expect(wrapper.find('.association-names').exists()).toBe(true)
      expect(wrapper.find('.association-names').text()).toBe('admin, user')
    })

    it('shows empty text when no items', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [] },
        column: { prop: 'roles', displayMode: 'names' },
      })
      expect(wrapper.find('.association-empty').exists()).toBe(true)
    })

    it('uses display_name or code when name is not available', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: [{ id: 1, code: 'ADMIN' }] },
        column: { prop: 'roles', displayMode: 'names' },
      })
      expect(wrapper.find('.association-names').text()).toBe('ADMIN')
    })
  })

  describe('computed properties', () => {
    it('defaults displayMode to count', () => {
      const wrapper = createWrapper({
        row: { id: 1 },
        column: { prop: 'roles' },
      })
      expect(wrapper.vm.displayMode).toBe('count')
    })

    it('uses association key from column.association', () => {
      const wrapper = createWrapper({
        row: { id: 1, user_roles: [{ id: 1, name: 'admin' }] },
        column: { prop: 'x', association: 'user_roles', displayMode: 'tags' },
      })
      expect(wrapper.vm.associationKey).toBe('user_roles')
      expect(wrapper.vm.items).toHaveLength(1)
    })

    it('handles items nested in .items property', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: { items: [{ id: 1, name: 'admin' }] } },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.vm.items).toHaveLength(1)
    })

    it('handles non-array values', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles: null },
        column: { prop: 'roles', displayMode: 'tags' },
      })
      expect(wrapper.vm.items).toEqual([])
    })

    it('computes label from navigateTo.title or column.label', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 1 },
        column: {
          prop: 'roles',
          displayMode: 'count',
          navigateTo: { title: '关联角色' },
        },
      })
      expect(wrapper.vm.label).toBe('关联角色')
    })

    it('falls back label to column.label', () => {
      const wrapper = createWrapper({
        row: { id: 1, roles_count: 1 },
        column: { prop: 'roles', displayMode: 'count', label: '角色' },
      })
      expect(wrapper.vm.label).toBe('角色')
    })
  })
})
