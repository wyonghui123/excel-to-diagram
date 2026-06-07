import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ManagementDimensionSelector from './ManagementDimensionSelector.vue'

const mockDimensions = [
  {
    id: 'product',
    name: '产品',
    code: 'PRODUCT',
    description: '产品维度',
    icon: 'product',
    ruleCount: 5,
    disabled: false
  },
  {
    id: 'version',
    name: '版本',
    code: 'VERSION',
    description: '版本维度',
    icon: 'version',
    ruleCount: 3,
    disabled: false
  },
  {
    id: 'domain',
    name: '领域',
    code: 'DOMAIN',
    description: '领域维度',
    icon: 'domain',
    ruleCount: 8,
    disabled: false
  },
  {
    id: 'sub-domain',
    name: '子领域',
    code: 'SUB_DOMAIN',
    description: '子领域维度',
    icon: 'sub-domain',
    ruleCount: 12,
    disabled: true
  }
]

describe('ManagementDimensionSelector', () => {
  it('应该正确渲染组件', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    expect(wrapper.find('.management-dimension-selector').exists()).toBe(true)
    expect(wrapper.find('.management-dimension-selector__title').text()).toBe('管理维度选择器')
  })

  it('应该正确渲染维度列表', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    const items = wrapper.findAll('.dimension-item')
    expect(items.length).toBe(4)
  })

  it('应该显示维度信息', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    const firstItem = wrapper.find('.dimension-item')
    expect(firstItem.find('.dimension-item__name').text()).toBe('产品')
    expect(firstItem.find('.dimension-item__description').text()).toBe('产品维度')
    expect(firstItem.find('.dimension-item__rules').text()).toContain('5 规则')
  })

  it('应该支持 v-model 绑定', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        modelValue: '',
        dimensions: mockDimensions
      }
    })

    const firstItem = wrapper.find('.dimension-item')
    await firstItem.trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['product'])
  })

  it('应该高亮选中的维度', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        modelValue: 'product',
        dimensions: mockDimensions
      }
    })

    const firstItem = wrapper.find('.dimension-item')
    expect(firstItem.classes()).toContain('dimension-item--selected')
    expect(firstItem.find('.dimension-item__check').exists()).toBe(true)
  })

  it('应该支持搜索过滤', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      },
      global: {
        stubs: {
          'el-input': {
            template: '<input v-model="modelValue" @input="$emit(\'input\', $event)" />',
            props: ['modelValue']
          }
        }
      }
    })

    const searchInput = wrapper.find('input')
    await searchInput.setValue('产品')

    const items = wrapper.findAll('.dimension-item')
    expect(items.length).toBe(1)
    expect(items[0].find('.dimension-item__name').text()).toBe('产品')
  })

  it('应该支持按编码搜索', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      },
      global: {
        stubs: {
          'el-input': {
            template: '<input v-model="modelValue" @input="$emit(\'input\', $event)" />',
            props: ['modelValue']
          }
        }
      }
    })

    const searchInput = wrapper.find('input')
    await searchInput.setValue('DOMAIN')

    const items = wrapper.findAll('.dimension-item')
    expect(items.length).toBe(2)
  })

  it('应该支持视图模式切换', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        viewMode: 'card',
        dimensions: mockDimensions
      }
    })

    const listButton = wrapper.findAll('el-button-stub')[0]
    await listButton.trigger('click')

    expect(wrapper.emitted('view-mode-change')).toBeTruthy()
    expect(wrapper.emitted('view-mode-change')[0]).toEqual(['list'])
  })

  it('应该应用正确的视图模式类', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        viewMode: 'list',
        dimensions: mockDimensions
      }
    })

    const content = wrapper.find('.management-dimension-selector__dimensions')
    expect(content.classes()).toContain('management-dimension-selector__dimensions--list')
  })

  it('应该禁用不可用的维度', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    const disabledItem = wrapper.findAll('.dimension-item')[3]
    expect(disabledItem.classes()).toContain('dimension-item--disabled')

    await disabledItem.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  it('应该显示加载状态', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: [],
        loading: true
      }
    })

    expect(wrapper.find('.management-dimension-selector__loading').exists()).toBe(true)
    expect(wrapper.find('.management-dimension-selector__loading').text()).toContain('加载中')
  })

  it('应该显示空状态', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: []
      }
    })

    expect(wrapper.find('.management-dimension-selector__empty').exists()).toBe(true)
  })

  it('应该正确映射图标', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    const vm = wrapper.vm
    expect(vm.getIconComponent('product')).toBeDefined()
    expect(vm.getIconComponent('version')).toBeDefined()
    expect(vm.getIconComponent('unknown')).toBeDefined()
  })

  it('应该响应式更新视图模式', async () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        viewMode: 'card',
        dimensions: mockDimensions
      }
    })

    expect(wrapper.vm.localViewMode).toBe('card')

    await wrapper.setProps({ viewMode: 'list' })
    expect(wrapper.vm.localViewMode).toBe('list')
  })

  it('应该支持移动端响应式布局', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        viewMode: 'card',
        dimensions: mockDimensions
      }
    })

    const content = wrapper.find('.management-dimension-selector__dimensions')
    expect(content.exists()).toBe(true)
  })

  it('应该显示维度规则数量', () => {
    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: mockDimensions
      }
    })

    const items = wrapper.findAll('.dimension-item__rules')
    expect(items[0].text()).toContain('5 规则')
    expect(items[1].text()).toContain('3 规则')
    expect(items[2].text()).toContain('8 规则')
  })

  it('应该处理没有规则数量的维度', () => {
    const dimensionsWithoutCount = [
      {
        id: 'test',
        name: '测试维度',
        code: 'TEST',
        icon: 'default'
      }
    ]

    const wrapper = mount(ManagementDimensionSelector, {
      props: {
        dimensions: dimensionsWithoutCount
      }
    })

    const rulesText = wrapper.find('.dimension-item__rules').text()
    expect(rulesText).toContain('0 规则')
  })
})
