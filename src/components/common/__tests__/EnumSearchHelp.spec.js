import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import EnumSearchHelp from '@/components/common/EnumSearchHelp.vue'

const mockFetch = vi.fn()
global.fetch = mockFetch

const mockCategoriesResponse = {
  success: true,
  data: {
    data: [
      { code: 'default', name: '默认', metadata: { description: '默认维度' } },
      { code: 'language', name: '语言', metadata: { description: '多语言支持' } },
      { code: 'region', name: '地区', metadata: { description: '地理区域' } },
      { code: 'priority', name: '优先级', metadata: { description: '优先级设置' } }
    ]
  }
}

describe('EnumSearchHelp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({
      json: () => Promise.resolve(mockCategoriesResponse)
    })
  })

  describe('基本渲染', () => {
    it('应该渲染搜索帮助按钮', () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })
      expect(wrapper.find('.btn-search-help').exists()).toBe(true)
    })

    it('应该渲染带图标的搜索按钮', () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })
      const btn = wrapper.find('.btn-search-help svg')
      expect(btn.exists()).toBe(true)
    })

    it('disabled 时按钮应该被禁用', () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: '',
          disabled: true
        }
      })
      expect(wrapper.find('.btn-search-help').attributes('disabled')).toBeDefined()
    })
  })

  describe('对话框行为', () => {
    it('点击按钮应该打开对话框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-dialog').exists()).toBe(true)
    })

    it('对话框应该显示正确的标题', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          title: '选择维度',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-header h4').text()).toBe('选择维度')
    })

    it('点击关闭按钮应该关闭对话框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      expect(wrapper.find('.search-help-dialog').exists()).toBe(true)

      await wrapper.find('.btn-close').trigger('click')
      await nextTick()
      expect(wrapper.find('.search-help-dialog').exists()).toBe(false)
    })

    it('点击遮罩应该关闭对话框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      expect(wrapper.find('.search-help-dialog').exists()).toBe(true)

      await wrapper.find('.search-help-overlay').trigger('click')
      await nextTick()
      expect(wrapper.find('.search-help-dialog').exists()).toBe(false)
    })

    it('点击对话框内部不应该关闭', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      await wrapper.find('.search-help-dialog').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-dialog').exists()).toBe(true)
    })
  })

  describe('数据加载', () => {
    it('打开对话框时应该加载数据', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/enum-types/dimension_key/values?page_size=100&is_active=true'
      )
    })

    it('应该显示加载状态', async () => {
      mockFetch.mockImplementation(() => new Promise(() => {}))

      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-loading').exists()).toBe(true)
    })

    it('加载完成后应该显示数据列表', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const items = wrapper.findAll('.search-help-item')
      expect(items.length).toBe(4)
      expect(items[0].find('.item-code').text()).toBe('default')
      expect(items[0].find('.item-name').text()).toBe('默认')
    })

    it('无数据时应该显示空状态', async () => {
      mockFetch.mockResolvedValue({
        json: () => Promise.resolve({ success: true, data: { data: [] } })
      })

      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      expect(wrapper.find('.search-help-empty').exists()).toBe(true)
    })
  })

  describe('搜索过滤', () => {
    it('应该显示搜索输入框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.filter-input').exists()).toBe(true)
    })

    it('输入搜索词应该过滤列表', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      await wrapper.find('.filter-input').setValue('语言')
      await nextTick()

      const items = wrapper.findAll('.search-help-item')
      expect(items.length).toBe(1)
      expect(items[0].find('.item-name').text()).toBe('语言')
    })

    it('应该支持按 code 搜索', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      await wrapper.find('.filter-input').setValue('region')
      await nextTick()

      const items = wrapper.findAll('.search-help-item')
      expect(items.length).toBe(1)
      expect(items[0].find('.item-code').text()).toBe('region')
    })

    it('按 ESC 应该关闭对话框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      await wrapper.find('.filter-input').trigger('keydown.esc')
      await nextTick()

      expect(wrapper.find('.search-help-dialog').exists()).toBe(false)
    })
  })

  describe('选择行为', () => {
    it('点击选项应该选中并关闭对话框', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      await wrapper.findAll('.search-help-item')[1].trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-dialog').exists()).toBe(false)
    })

    it('应该触发 update:modelValue 事件', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      await wrapper.findAll('.search-help-item')[2].trigger('click')
      await nextTick()

      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['region'])
    })

    it('应该触发 select 事件', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: ''
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      await wrapper.findAll('.search-help-item')[0].trigger('click')
      await nextTick()

      expect(wrapper.emitted('select')).toBeTruthy()
      expect(wrapper.emitted('select')[0][0]).toEqual({
        code: 'default',
        name: '默认',
        description: '默认维度'
      })
    })

    it('已选中的选项应该有视觉标识', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: 'language'
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))

      const selectedItem = wrapper.find('.search-help-item.is-selected')
      expect(selectedItem.exists()).toBe(true)
      expect(selectedItem.find('.item-code').text()).toBe('language')
    })
  })

  describe('新增按钮', () => {
    it('showNewButton 为 true 时应该显示新增按钮', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: '',
          showNewButton: true
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-footer .btn-new').exists()).toBe(true)
    })

    it('showNewButton 为 false 时不应该显示新增按钮', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: '',
          showNewButton: false
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      expect(wrapper.find('.search-help-footer').exists()).toBe(false)
    })

    it('点击新增按钮应该触发 new 事件', async () => {
      const wrapper = mount(EnumSearchHelp, {
        props: {
          enumType: 'dimension_key',
          modelValue: '',
          showNewButton: true
        }
      })

      await wrapper.find('.btn-search-help').trigger('click')
      await nextTick()

      await wrapper.find('.search-help-footer .btn-new').trigger('click')
      await nextTick()

      expect(wrapper.emitted('new')).toBeTruthy()
    })
  })
})
