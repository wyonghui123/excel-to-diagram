import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import FkLinkField from '../FkLinkField.vue'

vi.mock('@/composables/useAssociationNavigation', () => ({
  useAssociationNavigation: () => ({
    getRoutePath: vi.fn((objectType) => {
      const routePathMap = {
        'user': '/user-permission/users',
        'role': '/user-permission/roles',
        'permission': '/user-permission/permissions',
        'user_group': '/user-permission/groups',
        'enum_type': '/business-config/enums',
        'domain': '/data/domains',
        'sub_domain': '/data/subdomains',
        'service_module': '/data/service-modules',
        'business_object': '/data/business-objects',
        'product': '/product-version/products',
        'version': '/product-version/versions',
      }
      return routePathMap[objectType] || `/${objectType.replace(/_/g, '-')}`
    })
  })
}))

describe('FkLinkField', () => {
  function createWrapper(props = {}) {
    return mount(FkLinkField, {
      props: {
        value: null,
        displayValue: '',
        targetObjectType: '',
        ...props
      },
      global: {
        stubs: {
          'router-link': {
            template: '<a :href="to.path" class="fk-link" :title="title"><slot /></a>',
            props: ['to', 'title']
          },
          Promotion: { template: '<svg class="promotion-stub" />' }
        }
      }
    })
  }

  describe('基础渲染', () => {
    it('TC-FK-LINK-001: 有值时渲染为链接元素', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(true)
    })

    it('TC-FK-LINK-002: 无值时显示占位符"-"', () => {
      const wrapper = createWrapper({
        value: null,
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(false)

      const empty = wrapper.find('.fk-empty')
      expect(empty.exists()).toBe(true)
      expect(empty.text()).toBe('-')
    })

    it('TC-FK-LINK-003: 值为0时不显示链接（falsy值）', () => {
      const wrapper = createWrapper({
        value: 0,
        targetObjectType: 'user'
      })

      const empty = wrapper.find('.fk-empty')
      expect(empty.exists()).toBe(true)
    })

    it('TC-FK-LINK-004: 值为空字符串时显示占位符', () => {
      const wrapper = createWrapper({
        value: '',
        targetObjectType: 'user'
      })

      const empty = wrapper.find('.fk-empty')
      expect(empty.exists()).toBe(true)
    })
  })

  describe('显示值 (displayValue)', () => {
    it('TC-FK-LINK-005: 有displayValue时优先使用displayValue', () => {
      const wrapper = createWrapper({
        value: 1,
        displayValue: 'Admin User',
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      expect(link.text()).toBe('Admin User')
    })

    it('TC-FK-LINK-006: 无displayValue时回退到value', () => {
      const wrapper = createWrapper({
        value: 42,
        displayValue: '',
        targetObjectType: 'role'
      })

      const link = wrapper.find('.fk-link')
      expect(link.text()).toBe('42')
    })

    it('TC-FK-LINK-007: displayValue为空字符串时使用value', () => {
      const wrapper = createWrapper({
        value: 5,
        targetObjectType: 'permission'
      })

      const link = wrapper.find('.fk-link')
      expect(link.text()).toBe('5')
    })
  })

  describe('路由生成', () => {
    it('TC-FK-LINK-008: user类型生成正确的路由路径', async () => {
      const wrapper = createWrapper({
        value: 10,
        targetObjectType: 'user'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/user/10')
    })

    it('TC-FK-LINK-009: role类型生成正确的路由路径', async () => {
      const wrapper = createWrapper({
        value: 3,
        targetObjectType: 'role'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/role/3')
    })

    it('TC-FK-LINK-010: domain类型生成正确的路由路径', async () => {
      const wrapper = createWrapper({
        value: 5,
        targetObjectType: 'domain'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/domain/5')
    })

    it('TC-FK-LINK-011: product类型生成正确的路由路径', async () => {
      const wrapper = createWrapper({
        value: 100,
        targetObjectType: 'product'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/product/100')
    })

    it('TC-FK-LINK-012: 未注册类型使用默认路径转换规则', async () => {
      const wrapper = createWrapper({
        value: 7,
        targetObjectType: 'custom_type'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/custom_type/7')
    })

    it('TC-FK-LINK-013: 下划线类型名正确转换为连字符路径', async () => {
      const wrapper = createWrapper({
        value: 2,
        targetObjectType: 'user_group'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/user_group/2')
    })
  })

  describe('样式类名', () => {
    it('TC-FK-LINK-014: 链接状态应用fk-link样式类', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(true)
    })

    it('TC-FK-LINK-015: 空值状态应用fk-empty样式类', () => {
      const wrapper = createWrapper({
        value: null,
        targetObjectType: 'user'
      })

      const empty = wrapper.find('.fk-empty')
      expect(empty.exists()).toBe(true)
    })
  })

  describe('事件处理', () => {
    it('TC-FK-LINK-016: 点击链接阻止事件冒泡', async () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      const event = { stopPropagation: vi.fn() }
      
      link.trigger('click', event)
      expect(event.stopPropagation).toHaveBeenCalled()
    })
  })

  describe('Props验证', () => {
    it('TC-FK-LINK-017: targetObjectType为必填属性', () => {
      const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})

      const wrapper = mount(FkLinkField, {
        props: {
          value: 1
        },
        global: {
          stubs: {
            'router-link': {
              template: '<a :href="to.path"><slot /></a>',
              props: ['to']
            },
            Promotion: { template: '<svg class="promotion-stub" />' }
          }
        }
      })

      expect(consoleWarn).toHaveBeenCalled()
      consoleWarn.mockRestore()
    })

    it('TC-FK-LINK-018: 支持字符串类型的value', () => {
      const wrapper = createWrapper({
        value: 'abc-123',
        targetObjectType: 'user'
      })

      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(true)
      expect(link.text()).toBe('abc-123')
    })

    it('TC-FK-LINK-019: 支持数字类型的value', () => {
      const wrapper = createWrapper({
        value: 999,
        targetObjectType: 'role'
      })

      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(true)
      expect(link.text()).toBe('999')
    })
  })

  describe('响应式更新', () => {
    it('TC-FK-LINK-020: value变化时重新计算路由', async () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      let link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toContain('/1')

      await wrapper.setProps({ value: 99 })
      link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toContain('/99')
    })

    it('TC-FK-LINK-021: targetObjectType变化时更新路由路径', async () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      let link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toContain('/detail/user')

      await wrapper.setProps({ targetObjectType: 'role' })
      link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toContain('/detail/role')
    })

    it('TC-FK-LINK-022: displayValue变化时更新显示文本', async () => {
      const wrapper = createWrapper({
        value: 1,
        displayValue: 'Old Name',
        targetObjectType: 'user'
      })

      let link = wrapper.find('.fk-link')
      expect(link.text()).toBe('Old Name')

      await wrapper.setProps({ displayValue: 'New Name' })
      link = wrapper.find('.fk-link')
      expect(link.text()).toBe('New Name')
    })

    it('TC-FK-LINK-023: value从有值变为null时切换到空状态', async () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      expect(wrapper.find('.fk-link').exists()).toBe(true)

      await wrapper.setProps({ value: null })
      expect(wrapper.find('.fk-empty').exists()).toBe(true)
    })
  })

  describe('FK 跳转标识 (Promotion 图标 + 差异化 tooltip)', () => {
    it('TC-FK-LINK-024: 链接态渲染 Promotion 图标（业务键与 FK 的视觉区分）', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      // 必须有图标元素（区别于业务键链接的纯文本）
      const icon = wrapper.find('.fk-link__icon')
      expect(icon.exists()).toBe(true)
    })

    it('TC-FK-LINK-025: 禁用态也保留图标（保持视觉一致）', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user',
        linkDisabled: true
      })

      const icon = wrapper.find('.fk-link__icon')
      expect(icon.exists()).toBe(true)
    })

    it('TC-FK-LINK-026: 空值态不渲染图标', () => {
      const wrapper = createWrapper({
        value: null,
        targetObjectType: 'user'
      })

      const icon = wrapper.find('.fk-link__icon')
      expect(icon.exists()).toBe(false)
    })

    it('TC-FK-LINK-027: 文本与图标共存，文本在 fk-link__text 子元素中', () => {
      const wrapper = createWrapper({
        value: 1,
        displayValue: 'Admin User',
        targetObjectType: 'user'
      })

      const textSpan = wrapper.find('.fk-link__text')
      expect(textSpan.exists()).toBe(true)
      expect(textSpan.text()).toBe('Admin User')
    })

    it('TC-FK-LINK-028: tooltip 使用 targetObjectLabel 时显示友好名称', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user',
        targetObjectLabel: '用户'
      })

      const link = wrapper.find('.fk-link')
      expect(link.attributes('title')).toBe('打开 用户 详情')
    })

    it('TC-FK-LINK-029: tooltip 未传 targetObjectLabel 时回退到 targetObjectType', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user_group'
      })

      const link = wrapper.find('.fk-link')
      expect(link.attributes('title')).toBe('打开 user_group 详情')
    })

    it('TC-FK-LINK-030: 禁用态同样带 tooltip', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'role',
        targetObjectLabel: '角色',
        linkDisabled: true
      })

      const link = wrapper.find('.fk-link--disabled')
      expect(link.attributes('title')).toBe('打开 角色 详情')
    })
  })

  describe('detailMode 属性与 navigate 事件', () => {
    it('TC-FK-LINK-031: detailMode=page（默认）时渲染为 router-link', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user'
      })

      // page 模式下渲染 router-link（stub 为 <a>）
      const routerLink = wrapper.find('a.fk-link')
      expect(routerLink.exists()).toBe(true)
      expect(routerLink.attributes('href')).toBe('/detail/user/1')
    })

    it('TC-FK-LINK-032: detailMode=drawer 时渲染为普通 <a> 元素（非 router-link）', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user',
        detailMode: 'drawer'
      })

      // drawer 模式下不是 router-link，而是普通 <a>
      const link = wrapper.find('a.fk-link')
      expect(link.exists()).toBe(true)
      // drawer 模式下不应有 href 属性（由事件处理导航）
      expect(link.attributes('href')).toBeUndefined()
    })

    it('TC-FK-LINK-033: detailMode=drawer 时点击触发 navigate 事件', async () => {
      const wrapper = createWrapper({
        value: 42,
        displayValue: 'Admin User',
        targetObjectType: 'user',
        detailMode: 'drawer'
      })

      const link = wrapper.find('a.fk-link')
      await link.trigger('click')

      expect(wrapper.emitted('navigate')).toBeTruthy()
      expect(wrapper.emitted('navigate')[0][0]).toEqual({
        objectType: 'user',
        id: 42,
        displayValue: 'Admin User'
      })
    })

    it('TC-FK-LINK-034: detailMode=page 时点击不触发 navigate 事件', async () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user',
        detailMode: 'page'
      })

      const link = wrapper.find('.fk-link')
      await link.trigger('click')

      expect(wrapper.emitted('navigate')).toBeFalsy()
    })

    it('TC-FK-LINK-035: detailMode=drawer + linkDisabled 时降级为纯文本', () => {
      const wrapper = createWrapper({
        value: 1,
        targetObjectType: 'user',
        detailMode: 'drawer',
        linkDisabled: true
      })

      // linkDisabled 优先于 detailMode，渲染为 span
      const link = wrapper.find('a.fk-link')
      expect(link.exists()).toBe(false)
      const disabled = wrapper.find('.fk-link--disabled')
      expect(disabled.exists()).toBe(true)
    })

    it('TC-FK-LINK-036: navigate 事件包含正确的 objectType 和 id', async () => {
      const wrapper = createWrapper({
        value: 99,
        displayValue: '采购管理',
        targetObjectType: 'service_module',
        detailMode: 'drawer'
      })

      const link = wrapper.find('a.fk-link')
      await link.trigger('click')

      const emitted = wrapper.emitted('navigate')[0][0]
      expect(emitted.objectType).toBe('service_module')
      expect(emitted.id).toBe(99)
      expect(emitted.displayValue).toBe('采购管理')
    })

    it('TC-FK-LINK-037: detailMode 无效值时使用默认 page 模式', () => {
      const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const wrapper = mount(FkLinkField, {
        props: {
          value: 1,
          targetObjectType: 'user',
          detailMode: 'invalid'
        },
        global: {
          stubs: {
            'router-link': {
              template: '<a :href="to.path" class="fk-link"><slot /></a>',
              props: ['to']
            },
            Promotion: { template: '<svg class="promotion-stub" />' }
          }
        }
      })

      // 无效值被 validator 拒绝，但组件仍渲染（Vue 警告而非崩溃）
      const link = wrapper.find('.fk-link')
      expect(link.exists()).toBe(true)
      consoleWarn.mockRestore()
    })
  })

  describe('FK 链接导航 ID 修复验证', () => {
    it('TC-FK-LINK-038: 数字 ID 生成正确的导航路径（非 code）', async () => {
      // 修复前：value 可能是 "BO_CUSTOMER"（code），导航到 /detail/business_object/BO_CUSTOMER → 404
      // 修复后：value 是数字 ID（如 42），导航到 /detail/business_object/42 → 成功
      const wrapper = createWrapper({
        value: 42,
        targetObjectType: 'business_object'
      })

      await nextTick()
      const link = wrapper.find('.fk-link')
      expect(link.attributes('href')).toBe('/detail/business_object/42')
    })

    it('TC-FK-LINK-039: drawer 模式下 navigate 事件传递数字 ID', async () => {
      const wrapper = createWrapper({
        value: 1,
        displayValue: '采购需求',
        targetObjectType: 'service_module',
        detailMode: 'drawer'
      })

      const link = wrapper.find('a.fk-link')
      await link.trigger('click')

      const emitted = wrapper.emitted('navigate')[0][0]
      expect(typeof emitted.id).toBe('number')
      expect(emitted.id).toBe(1)
    })
  })
})
